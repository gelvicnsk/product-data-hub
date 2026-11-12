# Product Data Hub : commandes du quotidien.  `make` ou `make help` pour la liste.

SHELL := /bin/bash
.DEFAULT_GOAL := help

# charge .env s'il existe et exporte ses variables vers les commandes
ifneq (,$(wildcard .env))
include .env
export
endif

PYTHON ?= .venv/bin/python
DBT    := cd dbt && ../.venv/bin/dbt
DATE   ?= 2026-10-01

.PHONY: help env env-upgrade install up down reset ps logs generate ingest ingest-day test test-unit \
        test-db test-integration lint format psql clean dbt-deps dbt-build dbt-docs check-anomalies \
        pipeline edr-report analytics duckdb-demo init-db snapshot-replay api-local token airflow-up airflow-down k8s-up k8s-down

help: ## Affiche cette aide
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

env: ## Crée .env à partir de .env.example, avec des mots de passe aléatoires
	@if [ -f .env ]; then \
	  echo ".env existe déjà : rien à faire (le supprimer pour le régénérer)"; \
	else \
	  cp .env.example .env && \
	  sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$$(openssl rand -hex 16)/" .env && \
	  sed -i "s/^API_DB_PASSWORD=.*/API_DB_PASSWORD=$$(openssl rand -hex 16)/" .env && \
	  sed -i "s/^API_WRITER_DB_PASSWORD=.*/API_WRITER_DB_PASSWORD=$$(openssl rand -hex 16)/" .env && \
	  sed -i "s/^KEYCLOAK_ADMIN_PASSWORD=.*/KEYCLOAK_ADMIN_PASSWORD=$$(openssl rand -hex 12)/" .env && \
	  sed -i "s/^KC_DEMO_READER_PASSWORD=.*/KC_DEMO_READER_PASSWORD=$$(openssl rand -hex 8)/" .env && \
	  sed -i "s/^KC_DEMO_STEWARD_PASSWORD=.*/KC_DEMO_STEWARD_PASSWORD=$$(openssl rand -hex 8)/" .env && \
	  sed -i "s/^HOST_UID=.*/HOST_UID=$$(id -u)/; s/^HOST_GID=.*/HOST_GID=$$(id -g)/" .env && \
	  echo ".env créé (mots de passe générés, UID/GID renseignés)"; \
	fi

env-upgrade: ## Ajoute à un .env existant les variables des étapes 5 à 8 (mots de passe générés)
	@for var in API_WRITER_DB_USER=api_writer API_WRITER_DB_PASSWORD=$$(openssl rand -hex 16) \
	  API_PORT=8002 AUTH_ENABLED=true KEYCLOAK_PORT=8180 KEYCLOAK_ADMIN_PASSWORD=$$(openssl rand -hex 12) \
	  KC_DEMO_READER_PASSWORD=$$(openssl rand -hex 8) KC_DEMO_STEWARD_PASSWORD=$$(openssl rand -hex 8) \
	  AIRFLOW_PORT=8082; do \
	  key=$${var%%=*}; grep -q "^$$key=" .env || { echo "$$var" >> .env; echo "ajouté : $$key"; }; \
	done

install: ## Crée l'environnement virtuel et installe les dépendances
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -e ".[dev]"

up: ## Démarre PostgreSQL, le faux CRM, Keycloak, les migrations et l'API
	docker compose up -d --build --wait

init-db: ## Rejoue init.sql sur une base existante (nouveaux rôles, base airflow)
	docker compose up -d --force-recreate --wait postgres
	docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U $(POSTGRES_USER) \
	  -d $(POSTGRES_DB) -f /docker-entrypoint-initdb.d/01-init.sql

down: ## Arrête les conteneurs (les données restent)
	docker compose down

reset: ## Arrête les conteneurs et supprime la base (repart de zéro)
	docker compose down -v

ps: ## État des conteneurs
	docker compose ps

logs: ## Suit les logs des conteneurs
	docker compose logs -f --tail 50

generate: ## Simule les 30 journées des systèmes source
	$(PYTHON) -m sources.simulate_days

ingest: ## Charge toutes les journées disponibles dans le schéma raw
	$(PYTHON) -m ingestion.run --all

ingest-day: ## Charge une seule journée :  make ingest-day DATE=2026-10-05
	$(PYTHON) -m ingestion.run --date $(DATE)

dbt-deps: ## Installe les paquets dbt (dbt_utils)
	$(DBT) deps --profiles-dir .

dbt-build: ## Construit et teste tous les modèles dbt
	$(DBT) build --profiles-dir .

dbt-docs: ## Génère et sert la documentation dbt (lignage) sur http://localhost:8081
	$(DBT) docs generate --profiles-dir . && $(DBT) docs serve --profiles-dir . --port 8081

edr-report: ## Rapport d'observabilité Elementary -> data/edr/report.html
	.venv/bin/edr report --profiles-dir dbt --project-dir dbt \
	  --file-path data/edr/report.html --open-browser false
	@echo "Ouvrir depuis Windows : explorer.exe \"$$(wslpath -w data/edr/report.html)\""

snapshot-replay: ## Rejoue les snapshots SCD2 jour par jour (comme le rattrapage Airflow)
	@for day in $$($(PYTHON) -c "from sources.config import SimConfig; print(*SimConfig.from_env().dates)"); do \
	  echo "== snapshot au $$day"; (cd dbt && ../.venv/bin/dbt snapshot --profiles-dir . -q --vars "{as_of_date: $$day}") || exit 1; \
	done

api-local: ## Lance l'API hors Docker (rechargement auto) sur http://localhost:8002/docs
	.venv/bin/alembic -c api/alembic.ini upgrade head
	KEYCLOAK_ISSUER=http://localhost:$(KEYCLOAK_PORT)/realms/product-hub \
	  .venv/bin/uvicorn api.main:app --reload --port $(API_PORT)

token: ## Affiche un jeton Keycloak :  make token WHO=alice  (ou WHO=bob)
	@scripts/get_token.sh $(or $(WHO),alice)

airflow-up: ## Démarre Airflow (http://localhost:8082) ; mot de passe admin dans les logs
	docker compose --profile airflow up -d --build airflow
	@echo "Mot de passe admin : docker compose logs airflow | grep -i password"

airflow-down: ## Arrête Airflow
	docker compose --profile airflow stop airflow

k8s-up: ## Déploie sur un cluster Kubernetes local (kind)
	scripts/k8s_up.sh

k8s-down: ## Supprime le cluster Kubernetes local
	scripts/k8s_down.sh

analytics: ## Exporte marts et snapshots en Parquet + DuckDB (data/analytics/)
	$(PYTHON) -m analytics.export_duckdb

duckdb-demo: ## Requêtes d'analyse DuckDB sur l'export (lancer make analytics avant)
	$(PYTHON) -m analytics.demo_queries

check-anomalies: ## Vérifie que chaque anomalie injectée est détectée par son test
	$(PYTHON) scripts/check_anomalies.py

pipeline: generate ingest dbt-build check-anomalies edr-report ## Tout le pipeline, jusqu'au rapport Elementary

test: ## Tous les tests (unitaires + intégration)
	$(PYTHON) -m pytest -q

test-unit: ## Tests unitaires seulement (sans base de données)
	$(PYTHON) -m pytest -q -m "not integration"

test-integration: ## Tests d'intégration (base $(POSTGRES_TEST_DB))
	$(PYTHON) -m pytest -q -m integration

test-db: ## Crée et initialise la base de test (une seule fois)
	docker compose exec -T postgres psql -U $(POSTGRES_USER) -d postgres -tc \
	  "SELECT 1 FROM pg_database WHERE datname = '$(POSTGRES_TEST_DB)'" | grep -q 1 || \
	  docker compose exec -T postgres psql -U $(POSTGRES_USER) -d postgres \
	  -c "CREATE DATABASE $(POSTGRES_TEST_DB)"
	docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U $(POSTGRES_USER) \
	  -d $(POSTGRES_TEST_DB) -f /docker-entrypoint-initdb.d/01-init.sql

lint: ## Vérifie le style du code
	$(PYTHON) -m ruff check .

format: ## Corrige le style automatiquement
	$(PYTHON) -m ruff check --fix .
	$(PYTHON) -m ruff format .

psql: ## Ouvre psql sur la base de développement
	docker compose exec postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

clean: ## Supprime les données générées et les caches
	rm -rf data/landing data/crm_db data/anomalies.json .pytest_cache .ruff_cache dbt/target dbt/logs data/edr/report.html
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
