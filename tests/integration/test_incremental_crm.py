"""Extraction incrémentale du CRM : watermark, versions, reprise après échec."""

from __future__ import annotations

from datetime import date

import pytest

from ingestion.extract_crm import extract_crm
from ingestion.watermark import get_watermark

pytestmark = pytest.mark.integration


def _scalar(conn, query, params=None):
    with conn.cursor() as cur:
        cur.execute(query, params)
        value = cur.fetchone()[0]
    conn.commit()
    return value


def test_watermark_advances_day_after_day(sim, crm_client, test_conn):
    extract_crm(test_conn, crm_client, date(2026, 10, 1), page_size=20)
    w1 = get_watermark(test_conn, "crm", "quotes")
    extract_crm(test_conn, crm_client, date(2026, 10, 2), page_size=20)
    w2 = get_watermark(test_conn, "crm", "quotes")
    assert w1 is not None and w2 > w1
    assert w1.date() == date(2026, 10, 1)


def test_second_day_only_fetches_changes(sim, crm_client, test_conn):
    extract_crm(test_conn, crm_client, date(2026, 10, 1))
    day1 = _scalar(test_conn, "SELECT count(*) FROM raw.crm_quotes")
    results = extract_crm(test_conn, crm_client, date(2026, 10, 2))
    fetched = next(r for r in results if r.table == "crm_quotes").rows
    total_day2 = crm_client.get("/api/v1/quotes", params={"as_of": "2026-10-02T23:59:59+00:00"}).json()[
        "totalSize"
    ]
    assert fetched < total_day2  # pas une relecture complète
    assert _scalar(test_conn, "SELECT count(*) FROM raw.crm_quotes") > day1


def test_status_changes_are_kept_as_versions(sim, crm_client, test_conn):
    for day in sim[0].dates:
        extract_crm(test_conn, crm_client, day)
    versions = _scalar(test_conn, "SELECT count(*) FROM raw.crm_quotes")
    distinct_quotes = _scalar(test_conn, "SELECT count(DISTINCT id) FROM raw.crm_quotes")
    duplicates = _scalar(
        test_conn, "SELECT count(*) - count(DISTINCT (id, last_modified_date)) FROM raw.crm_quotes"
    )
    assert versions > distinct_quotes  # certains devis ont changé de statut
    assert duplicates == 0  # mais aucune version n'est en double


def test_failed_call_does_not_move_the_watermark(sim, crm_client, test_conn, monkeypatch):
    import httpx

    extract_crm(test_conn, crm_client, date(2026, 10, 1))
    before = get_watermark(test_conn, "crm", "quotes")

    def broken_get(*_args, **_kwargs):
        raise httpx.ConnectError("CRM indisponible")

    monkeypatch.setattr(crm_client, "get", broken_get)
    results = extract_crm(test_conn, crm_client, date(2026, 10, 2))
    assert {r.status for r in results} == {"failed"}
    assert get_watermark(test_conn, "crm", "quotes") == before
