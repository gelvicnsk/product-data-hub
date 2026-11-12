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
\getenv writer_password API_WRITER_DB_PASSWORD
\getenv writer_user API_WRITER_DB_USER

-- :{?var} vaut vrai si la variable psql existe (\getenv ne la crée pas si l'env est absent)
\if :{?api_password}
\else
    \set api_password ''
\endif
SELECT :'api_password' = '' AS missing_api_password \gset
\if :missing_api_password
    -- ON_ERROR_STOP : l'exception arrête le script avec un code d'erreur
    DO $$ BEGIN RAISE EXCEPTION 'API_DB_PASSWORD est vide ou absente : initialisation arrêtée'; END $$;
\endif

\if :{?api_user}
\else
    \set api_user api_reader
\endif

\if :{?writer_password}
\else
    \set writer_password ''
\endif
SELECT :'writer_password' = '' AS missing_writer_password \gset
\if :missing_writer_password
    DO $$ BEGIN RAISE EXCEPTION 'API_WRITER_DB_PASSWORD est vide ou absente : initialisation arrêtée'; END $$;
\endif

\if :{?writer_user}
\else
    \set writer_user api_writer
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

-- --- Rôle d'écriture de l'API : uniquement le schéma app -------------------------
-- Les tables de app sont créées par Alembic (avec le rôle propriétaire) ; les
-- privilèges par défaut ci-dessous les rendent accessibles à ce rôle dès leur création.
SELECT format('CREATE ROLE %I LOGIN', :'writer_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'writer_user') \gexec

ALTER ROLE :"writer_user" WITH LOGIN PASSWORD :'writer_password';

GRANT CONNECT ON DATABASE :"DBNAME" TO :"writer_user";
GRANT USAGE ON SCHEMA app TO :"writer_user";
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA app TO :"writer_user";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA app TO :"writer_user";
ALTER DEFAULT PRIVILEGES IN SCHEMA app GRANT SELECT, INSERT, UPDATE ON TABLES TO :"writer_user";
ALTER DEFAULT PRIVILEGES IN SCHEMA app GRANT USAGE, SELECT ON SEQUENCES TO :"writer_user";

-- --- Base de métadonnées d'Airflow ------------------------------------------------
SELECT 'CREATE DATABASE airflow'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'airflow')
  AND current_database() <> 'airflow' \gexec
