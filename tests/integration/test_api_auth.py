"""Sécurité de l'API : jetons Keycloak, rôles, et moindre privilège côté PostgreSQL."""

from __future__ import annotations

import psycopg
import pytest

pytestmark = pytest.mark.integration


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_health_is_public(api_client):
    assert api_client.get("/health").json() == {"status": "ok"}


def test_missing_token_is_rejected(api_client):
    response = api_client.get("/products")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"expires_in": -60},  # expiré
        {"audience": "another-client"},  # mauvaise audience
        {"issuer": "http://evil.example/realms/product-hub"},  # mauvais émetteur
    ],
    ids=["expiré", "audience", "émetteur"],
)
def test_invalid_tokens_are_rejected(api_client, make_token, kwargs):
    assert api_client.get("/products", headers=bearer(make_token(**kwargs))).status_code == 401


def test_token_signed_with_another_key_is_rejected(api_client, make_token):
    from cryptography.hazmat.primitives.asymmetric import rsa

    forged = make_token(key=rsa.generate_private_key(public_exponent=65537, key_size=2048))
    assert api_client.get("/products", headers=bearer(forged)).status_code == 401


def test_reader_can_read_but_not_write(api_client, make_token):
    token = make_token(roles=["reader"])
    assert api_client.get("/products", headers=bearer(token)).status_code == 200
    response = api_client.post(
        "/corrections",
        headers=bearer(token),
        json={"product_id": 10000001, "field": "family", "proposed_value": "X"},
    )
    assert response.status_code == 403


def test_user_without_role_cannot_read(api_client, make_token):
    assert api_client.get("/products", headers=bearer(make_token(roles=[]))).status_code == 403


def test_api_reader_role_cannot_write_in_database(test_conn):
    import os

    from ingestion.db import conninfo_from_env

    conninfo = psycopg.conninfo.make_conninfo(
        conninfo_from_env(os.getenv("POSTGRES_TEST_DB", "product_hub_test")),
        user=os.getenv("API_DB_USER", "api_reader"),
        password=os.environ["API_DB_PASSWORD"],
    )
    with psycopg.connect(conninfo) as conn, conn.cursor() as cur, pytest.raises(psycopg.Error):
        cur.execute(
            "INSERT INTO app.correction_request (product_id, field, proposed_value, "
            "requested_by) VALUES (1, 'family', 'x', 'intrus')"
        )
