FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
RUN pip install --no-cache-dir "fastapi>=0.115" "uvicorn>=0.30" "pandas>=2.2" "numpy>=1.26"

COPY sources/ ./sources/

# utilisateur non root (docker-compose le remplace par HOST_UID:HOST_GID)
RUN useradd --create-home --uid 10001 crm
USER crm

EXPOSE 8010
CMD ["uvicorn", "sources.mock_crm.main:app", "--host", "0.0.0.0", "--port", "8010"]
