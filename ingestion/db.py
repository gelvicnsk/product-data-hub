"""Connexion à PostgreSQL à partir des variables d'environnement (voir .env.example)."""

from __future__ import annotations

import os

import psycopg


def conninfo_from_env(dbname: str | None = None) -> str:
    password = os.getenv("POSTGRES_PASSWORD")
    if not password:
        raise RuntimeError(
            "POSTGRES_PASSWORD n'est pas défini : créer .env (make env) puis le charger "
            "(set -a; source .env; set +a) ou passer par le Makefile."
        )
    return psycopg.conninfo.make_conninfo(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5433"),
        dbname=dbname or os.getenv("POSTGRES_DB", "product_hub"),
        user=os.getenv("POSTGRES_USER", "hub_admin"),
        password=password,
        application_name="product-hub-ingestion",
    )


def connect(dbname: str | None = None, autocommit: bool = False) -> psycopg.Connection:
    return psycopg.connect(conninfo_from_env(dbname), autocommit=autocommit)
