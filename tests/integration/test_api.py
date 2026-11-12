"""Comportement fonctionnel de l'API sur une base de test (marts minimaux)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def reader(make_token):
    return {"Authorization": f"Bearer {make_token(roles=['reader'], username='alice')}"}


@pytest.fixture
def steward(make_token):
    return {"Authorization": f"Bearer {make_token(roles=['reader', 'data_steward'], username='bob')}"}


def test_list_and_filter_products(api_client, reader):
    page = api_client.get("/products", headers=reader).json()
    assert page["total"] == 2
    filtered = api_client.get("/products", headers=reader, params={"in_catalog": False}).json()
    assert [p["product_id"] for p in filtered["items"]] == [10000002]
    search = api_client.get("/products", headers=reader, params={"q": "orion"}).json()
    assert search["total"] == 1


def test_pagination_bounds(api_client, reader):
    assert api_client.get("/products", headers=reader, params={"page_size": 500}).status_code == 422
    page2 = api_client.get("/products", headers=reader, params={"page": 2, "page_size": 1}).json()
    assert page2["total"] == 2 and len(page2["items"]) == 1


def test_product_detail_and_price_history(api_client, reader):
    assert api_client.get("/products/10000001", headers=reader).json()["family"] == "Accélérateurs"
    assert api_client.get("/products/42", headers=reader).status_code == 404
    history = api_client.get("/products/10000001/price-history", headers=reader).json()
    assert [h["is_current"] for h in history] == [False, True]


def test_quality_summary(api_client, reader):
    summary = api_client.get("/quality/summary", headers=reader).json()
    assert summary["products"] == 2
    assert summary["not_in_catalog"] == 1
    assert summary["invalid_prices"] == 1


def test_correction_workflow(api_client, steward, reader):
    created = api_client.post(
        "/corrections",
        headers=steward,
        json={
            "product_id": 10000001,
            "field": "family",
            "proposed_value": "Processeurs",
            "comment": "mal classé",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["requested_by"] == "bob"
    assert body["current_value"] == "Accélérateurs"  # valeur du golden record au moment de la demande
    assert body["status"] == "open"

    listed = api_client.get("/corrections", headers=reader).json()
    assert [c["id"] for c in listed] == [body["id"]]

    reviewed = api_client.patch(f"/corrections/{body['id']}", headers=steward, json={"status": "accepted"})
    assert reviewed.json()["reviewed_by"] == "bob"
    again = api_client.patch(f"/corrections/{body['id']}", headers=steward, json={"status": "rejected"})
    assert again.status_code == 409


def test_correction_validation(api_client, steward):
    unknown_field = {"product_id": 10000001, "field": "matnr", "proposed_value": "x"}
    assert api_client.post("/corrections", headers=steward, json=unknown_field).status_code == 422
    unknown_product = {"product_id": 1, "field": "family", "proposed_value": "x"}
    assert api_client.post("/corrections", headers=steward, json=unknown_product).status_code == 404
