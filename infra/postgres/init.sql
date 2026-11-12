-- Initialisation de l'entrepôt du Product Data Hub.
-- Exécuté automatiquement par l'image postgres au premier démarrage
-- (docker-entrypoint-initdb.d), ou à la main :
--   psql -v ON_ERROR_STOP=1 -f infra/postgres/init.sql
-- Idempotent : peut être rejoué sans erreur.

\set ON_ERROR_STOP on
SET client_min_messages = warning;

-- Le mot de passe du rôle API vient de l'environnement, jamais du dépôt.
\getenv api_password API_DB_PASSWORD
\getenv api_user API_DB_USER

SELECT (:'api_password' = '' OR :'api_password' = ':api_password') AS missing_api_password \gset
\if :missing_api_password
    -- ON_ERROR_STOP : l'exception arrête le script avec un code d'erreur
    DO $$ BEGIN RAISE EXCEPTION 'API_DB_PASSWORD est vide ou absente : initialisation arrêtée'; END $$;
\endif

SELECT (:'api_user' = '' OR :'api_user' = ':api_user') AS missing_api_user \gset
\if :missing_api_user
    \set api_user api_reader
\endif

-- --- Schémas, de la donnée brute à la donnée exposée -------------------------
CREATE SCHEMA IF NOT EXISTS raw;           -- données telles que reçues des sources
CREATE SCHEMA IF NOT EXISTS staging;       -- dbt : nettoyage, typage
CREATE SCHEMA IF NOT EXISTS snapshots;     -- dbt : historique SCD type 2
CREATE SCHEMA IF NOT EXISTS intermediate;  -- dbt : rapprochement, règles de gestion
CREATE SCHEMA IF NOT EXISTS marts;         -- dbt : tables exposées
CREATE SCHEMA IF NOT EXISTS meta;          -- pilotage du pipeline
CREATE SCHEMA IF NOT EXISTS app;           -- base applicative de l'API (Alembic)

-- --- Journal des chargements ------------------------------------------------
CREATE TABLE IF NOT EXISTS meta.load_log (
    load_id       bigserial PRIMARY KEY,
    source        text        NOT NULL,   -- erp, plm, catalog, crm
    target_table  text        NOT NULL,   -- raw.erp_mara, ...
    file_name     text,                   -- fichier ou appel API d'origine
    extract_date  date,                   -- journée simulée
    rows_loaded   integer,
    status        text        NOT NULL DEFAULT 'running'
                  CHECK (status IN ('running', 'success', 'failed', 'skipped')),
    error_message text,
    started_at    timestamptz NOT NULL DEFAULT now(),
    finished_at   timestamptz
);
CREATE INDEX IF NOT EXISTS load_log_source_idx ON meta.load_log (source, started_at DESC);

-- --- Fichiers déjà traités (sources fichier : ERP, PLM, catalogue) -------------
CREATE TABLE IF NOT EXISTS meta.processed_files (
    source       text        NOT NULL,
    file_path    text        NOT NULL,    -- chemin relatif à la zone de dépôt
    checksum     text        NOT NULL,    -- sha256 du contenu
    rows_loaded  integer     NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source, file_path)
);

-- --- Watermarks des extractions incrémentales (source API : CRM) --------------
CREATE TABLE IF NOT EXISTS meta.extract_watermark (
    source      text        NOT NULL,
    entity      text        NOT NULL,     -- accounts, quotes, quote_lines
    watermark   timestamptz NOT NULL,     -- plus grand LastModifiedDate déjà chargé
    updated_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source, entity)
);

-- --- Rôle en lecture seule pour l'API ----------------------------------------
SELECT format('CREATE ROLE %I LOGIN', :'api_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'api_user') \gexec

ALTER ROLE :"api_user" WITH LOGIN PASSWORD :'api_password';
ALTER ROLE :"api_user" SET default_transaction_read_only = on;

GRANT CONNECT ON DATABASE :"DBNAME" TO :"api_user";
GRANT USAGE ON SCHEMA marts, meta TO :"api_user";
GRANT SELECT ON ALL TABLES IN SCHEMA marts, meta TO :"api_user";
-- Les tables que dbt créera plus tard dans marts seront lisibles automatiquement
ALTER DEFAULT PRIVILEGES IN SCHEMA marts GRANT SELECT ON TABLES TO :"api_user";
