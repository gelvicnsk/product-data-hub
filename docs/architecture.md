# Architecture

```
 Sources simulées        Ingestion              dbt (PostgreSQL)                 Exposition
 ERP   CSV SAP ─┐                                                                 FastAPI ── Keycloak
 PLM   JSON    ─┼──▶  extracteurs  ──▶ raw ──▶ staging ──▶ intermediate ──▶ marts ─┤  (api_reader / api_writer)
 Catalogue CSV ─┤     idempotents          └──▶ snapshots (SCD2)                   └ rapport Elementary
 CRM   API REST ┘     + watermark
                                   Airflow : ingest → dbt_snapshot → dbt_build → quality_gate
```

| Couche | Technologie | Où |
|---|---|---|
| Simulation | Python, pandas, FastAPI (faux CRM) | `sources/` |
| Ingestion | Python, psycopg 3, httpx | `ingestion/` |
| Entrepôt | PostgreSQL 16 | `infra/postgres/init.sql` |
| Transformation | dbt-core 1.11, dbt_utils | `dbt/` |
| Observabilité | Elementary 0.26.1 | `dbt/` + `make edr-report` |
| API | FastAPI, SQLAlchemy 2.x, Alembic | `api/` |
| Authentification | Keycloak 26.6 (OIDC, JWT RS256) | `infra/keycloak/`, `api/auth.py` |
| Orchestration | Airflow 3.4 | `dags/`, `infra/airflow/` |
| Déploiement | Docker Compose (dev), Kubernetes kind + kustomize | `docker-compose.yml`, `k8s/` |
| CI | GitHub Actions : lint, tests, pipeline bout en bout, DAG, manifestes | `.github/workflows/ci.yml` |

Schémas PostgreSQL et règles du golden record : [data_model.md](data_model.md).
Anomalies injectées et leur détection : [anomalies.md](anomalies.md).
