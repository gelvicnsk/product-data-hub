"""Fixtures partagées : une petite simulation et une base PostgreSQL de test dédiée.

Les tests d'intégration n'utilisent JAMAIS la base de développement : ils se
connectent à POSTGRES_TEST_DB (créée et initialisée par `make test-db`), et la
vident avant chaque test. Sans base joignable, ils sont ignorés (skip).
"""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import psycopg
import pytest

from sources.config import SimConfig
from sources.simulate_days import simulate

SMALL_ANOMALIES = {
    "unknown_product_in_quotes": 3,
    "eol_product_in_quotes": 2,
    "missing_catalog_description": 4,
    "missing_from_catalog": 5,
    "duplicate_material": 2,
    "non_positive_price": 3,
}


def small_config(tmp_path: Path, **overrides) -> SimConfig:
    cfg = SimConfig(
        seed=7,
        days=6,
        n_materials=300,
        n_accounts=40,
        quotes_per_day=10,
        erp_missing_day=2,
        quote_volume_drop_day=3,
        erp_renamed_column_day=4,
        anomalies=dict(SMALL_ANOMALIES),
        landing_dir=tmp_path / "landing",
    )
    return replace(cfg, **overrides)


@pytest.fixture
def sim(tmp_path: Path):
    """Simulation de 6 journées dans un dossier temporaire ; renvoie (config, journal)."""
    cfg = small_config(tmp_path)
    log = simulate(cfg)
    return cfg, log


@pytest.fixture
def crm_client(sim, monkeypatch):
    """Client HTTP branché directement sur l'application du faux CRM (sans serveur)."""
    from fastapi.testclient import TestClient

    from sources.mock_crm import main as crm_main

    cfg, _ = sim
    monkeypatch.setenv("CRM_DB_DIR", str(cfg.landing_dir.parent / "crm_db"))
    crm_main._cache.clear()
    with TestClient(crm_main.app) as client:
        yield client


@pytest.fixture
def test_conn():
    """Connexion à la base de test, remise à zéro avant le test."""
    from ingestion.db import conninfo_from_env

    dbname = os.getenv("POSTGRES_TEST_DB", "product_hub_test")
    try:
        conn = psycopg.connect(conninfo_from_env(dbname), connect_timeout=3)
    except (psycopg.OperationalError, RuntimeError) as exc:
        pytest.skip(f"base de test {dbname} indisponible : {exc}")
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('meta.load_log') IS NOT NULL")
        if not cur.fetchone()[0]:
            conn.close()
            pytest.skip(f"{dbname} n'est pas initialisée : lancer `make test-db`")
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'raw'")
        for (table,) in cur.fetchall():
            cur.execute(f'DROP TABLE raw."{table}"')
        cur.execute("TRUNCATE meta.load_log, meta.processed_files, meta.extract_watermark")
    conn.commit()
    yield conn
    conn.close()
