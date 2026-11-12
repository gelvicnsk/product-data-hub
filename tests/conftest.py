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


# --- API : base de test avec des marts minimaux, et jetons signés comme Keycloak ------

ISSUER = "http://keycloak.test/realms/product-hub"
AUDIENCE = "product-hub-api"


@pytest.fixture(scope="session")
def rsa_keys():
    from cryptography.hazmat.primitives.asymmetric import rsa

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private, private.public_key()


@pytest.fixture
def make_token(rsa_keys):
    """Fabrique un jeton d'accès au format Keycloak (RS256, realm_access.roles)."""
    import time

    import jwt

    private, _ = rsa_keys

    def _make(
        roles=("reader",), username="alice", *, audience=AUDIENCE, issuer=ISSUER, expires_in=300, key=None
    ):
        now = int(time.time())
        claims = {
            "iss": issuer,
            "aud": audience,
            "sub": f"id-{username}",
            "iat": now,
            "exp": now + expires_in,
            "preferred_username": username,
            "realm_access": {"roles": list(roles)},
        }
        return jwt.encode(claims, key or private, algorithm="RS256", headers={"kid": "test"})

    return _make


@pytest.fixture
def api_client(test_conn, rsa_keys, monkeypatch):
    """Client de l'API branché sur la base de test, avec les vrais rôles api_reader/api_writer."""
    from alembic import command
    from alembic.config import Config
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, text

    from api.config import Settings
    from api.main import create_app
    from api.models import MartsBase, PriceHistory, Product
    from ingestion.db import conninfo_from_env

    dbname = os.getenv("POSTGRES_TEST_DB", "product_hub_test")
    if not os.getenv("API_DB_PASSWORD") or not os.getenv("API_WRITER_DB_PASSWORD"):
        pytest.skip("API_DB_PASSWORD et API_WRITER_DB_PASSWORD sont nécessaires (voir .env)")

    # marts minimaux (dans la base de test seulement) + migrations Alembic du schéma app
    admin = create_engine("postgresql+psycopg://", creator=lambda: psycopg.connect(conninfo_from_env(dbname)))
    MartsBase.metadata.drop_all(admin)
    MartsBase.metadata.create_all(admin)
    monkeypatch.setenv("ALEMBIC_DB", dbname)
    command.upgrade(Config("api/alembic.ini"), "head")
    with admin.begin() as conn:
        conn.execute(text("TRUNCATE app.correction_request RESTART IDENTITY"))
        for row in [
            dict(
                product_id=10000001,
                matnr="000000000010000001",
                mfr_part_number="GX-1-A",
                product_name="Orion GPU accelerator G4",
                description="Accélérateur",
                description_source="catalog",
                family="Accélérateurs",
                material_type="HALB",
                lifecycle_state="ACTIVE",
                revision="A",
                standard_price=4200,
                currency="EUR",
                has_valid_price=True,
                is_in_plm=True,
                is_in_catalog=True,
                catalog_match_method="sku",
                is_suspected_duplicate=False,
            ),
            dict(
                product_id=10000002,
                matnr="000000000010000002",
                mfr_part_number="RK-2-B",
                product_name="Atlas rack server G2",
                description_source="erp",
                family="Serveurs rack",
                material_type="FERT",
                lifecycle_state="END_OF_LIFE",
                has_valid_price=False,
                standard_price=0,
                is_in_plm=True,
                is_in_catalog=False,
                is_suspected_duplicate=True,
            ),
        ]:
            conn.execute(Product.__table__.insert().values(**row))
        for row in [
            dict(
                product_id=10000001,
                plant="FR01",
                valid_from="2026-10-01",
                valid_to="2026-10-09",
                standard_price=4000,
                is_current=False,
                currency="EUR",
            ),
            dict(
                product_id=10000001,
                plant="FR01",
                valid_from="2026-10-10",
                standard_price=4200,
                previous_price=4000,
                change_pct=5,
                is_current=True,
                currency="EUR",
            ),
        ]:
            conn.execute(PriceHistory.__table__.insert().values(**row))
    admin.dispose()

    settings = Settings(
        postgres_host=os.getenv("POSTGRES_HOST", "localhost"),
        postgres_port=int(os.getenv("POSTGRES_PORT", "5433")),
        postgres_db=dbname,
        api_db_password=os.environ["API_DB_PASSWORD"],
        api_writer_db_password=os.environ["API_WRITER_DB_PASSWORD"],
        keycloak_issuer=ISSUER,
        keycloak_audience=AUDIENCE,
    )
    _, public = rsa_keys
    with TestClient(create_app(settings)) as client:
        # pas de Keycloak en test : la clé publique est fournie directement
        monkeypatch.setattr(client.app.state.token_verifier, "signing_key", lambda token: public)
        yield client
