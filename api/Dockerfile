# Image de l'API.  docker build -f api/Dockerfile -t product-hub-api .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
RUN pip install --no-cache-dir \
      "fastapi>=0.115" "uvicorn>=0.30" "pydantic>=2.7" "pydantic-settings>=2.3" \
      "sqlalchemy>=2.0,<2.2" "psycopg[binary]>=3.2" "alembic>=1.13" "PyJWT[crypto]>=2.8"

COPY api/ ./api/

RUN useradd --create-home --uid 10001 api
USER api

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
