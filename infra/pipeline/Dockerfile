# Image du pipeline batch : simulation des sources, ingestion, dbt (+ Elementary).
# Utilisée par Kubernetes (Job d'initialisation et CronJob quotidien).
#   docker build -f infra/pipeline/Dockerfile -t product-hub/pipeline:dev .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LANDING_DIR=/data/landing

RUN apt-get update && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN pip install --no-cache-dir \
      "pandas>=2.2" "numpy>=1.26" "psycopg[binary]>=3.2" "httpx>=0.27" \
      "dbt-core>=1.11,<1.12" "dbt-postgres>=1.11,<1.12" "elementary-data==0.26.1"

COPY sources/ ./sources/
COPY ingestion/ ./ingestion/
COPY scripts/ ./scripts/
COPY dbt/ ./dbt/
COPY infra/pipeline/run_pipeline.sh ./run_pipeline.sh

# paquets dbt installés au build : le conteneur n'a pas besoin d'Internet pour tourner
RUN cd dbt && dbt deps --profiles-dir . && rm -rf target logs

RUN useradd --create-home --uid 10001 pipeline \
 && chown -R pipeline /app && chmod +x run_pipeline.sh
USER pipeline

ENTRYPOINT ["./run_pipeline.sh"]
CMD ["daily"]
