# Image de l'ingestion batch (utilisée plus tard par Airflow et par le CronJob Kubernetes).
#   docker build -f ingestion/Dockerfile -t product-hub-ingestion .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
RUN pip install --no-cache-dir "pandas>=2.2" "numpy>=1.26" "psycopg[binary]>=3.2" "httpx>=0.27"

COPY ingestion/ ./ingestion/

RUN useradd --create-home --uid 10001 hub
USER hub

ENTRYPOINT ["python", "-m", "ingestion.run"]
CMD ["--all"]
