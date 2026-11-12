# Image Airflow du Product Data Hub.
# Airflow et les outils du pipeline (dbt, Elementary, ingestion) ont des dépendances qui se
# contredisent souvent : ils vivent dans deux environnements Python séparés. Les tâches du
# DAG appellent /opt/airflow/pipeline-venv/bin/dbt et .../python.
FROM apache/airflow:3.4.0-python3.12

RUN python -m venv /opt/airflow/pipeline-venv \
 && /opt/airflow/pipeline-venv/bin/pip install --no-cache-dir \
      "dbt-core>=1.11,<1.12" "dbt-postgres>=1.11,<1.12" "elementary-data==0.26.1" \
      "pandas>=2.2" "numpy>=1.26" "psycopg[binary]>=3.2" "httpx>=0.27"

# le code du projet est monté dans /opt/product-hub (docker-compose) : rien à copier ici
ENV PROJECT_DIR=/opt/product-hub \
    PIPELINE_BIN=/opt/airflow/pipeline-venv/bin
