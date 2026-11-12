"""Comportement de l'API du faux CRM et de la pagination côté extracteur (sans base)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from ingestion.extract_crm import end_of_day, fetch_all


def test_pagination_returns_every_record_once(sim, crm_client):
    as_of = end_of_day(date(2026, 10, 6))
    total = crm_client.get("/api/v1/quotes", params={"as_of": as_of.isoformat()}).json()["totalSize"]
    records = fetch_all(crm_client, "quotes", modified_since=None, as_of=as_of, page_size=7)
    ids = [r["Id"] for r in records]
    assert len(ids) == total
    assert len(set(ids)) == total


def test_as_of_hides_the_future(sim, crm_client):
    day1 = fetch_all(
        crm_client, "quotes", modified_since=None, as_of=end_of_day(date(2026, 10, 1)), page_size=500
    )
    assert all(r["CreatedDate"] < "2026-10-02" for r in day1)
    assert all(r["Status"] == "Draft" for r in day1)


def test_modified_since_is_inclusive(sim, crm_client):
    as_of = end_of_day(date(2026, 10, 6))
    everything = fetch_all(crm_client, "quotes", modified_since=None, as_of=as_of, page_size=500)
    boundary = max(
        datetime.strptime(r["LastModifiedDate"], "%Y-%m-%dT%H:%M:%S.000+0000").replace(tzinfo=UTC)
        for r in everything
    )
    again = fetch_all(crm_client, "quotes", modified_since=boundary, as_of=as_of, page_size=500)
    assert len(again) >= 1  # la borne est relue : c'est l'upsert qui évite le doublon


def test_unknown_entity_and_bad_date(sim, crm_client):
    assert crm_client.get("/api/v1/opportunities").status_code == 404
    assert crm_client.get("/api/v1/quotes", params={"as_of": "hier"}).status_code == 422
