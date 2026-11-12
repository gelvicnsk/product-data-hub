"""Rejouer une ingestion ne doit jamais dupliquer ni perdre de données."""

from __future__ import annotations

import pandas as pd
import pytest

from ingestion.loader import load_dataframe
from ingestion.run import available_days, run_day

pytestmark = pytest.mark.integration

COUNT_SQL = """
SELECT 'erp_mara', count(*) FROM raw.erp_mara
UNION ALL SELECT 'erp_mbew', count(*) FROM raw.erp_mbew
UNION ALL SELECT 'plm_lifecycle', count(*) FROM raw.plm_lifecycle
UNION ALL SELECT 'catalog_products', count(*) FROM raw.catalog_products
UNION ALL SELECT 'crm_quotes', count(*) FROM raw.crm_quotes
UNION ALL SELECT 'crm_quote_lines', count(*) FROM raw.crm_quote_lines
ORDER BY 1
"""


def _counts(conn) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute(COUNT_SQL)
        rows = dict(cur.fetchall())
    conn.commit()
    return rows


def _ingest_all(conn, client, cfg, force=False):
    results = []
    for day in available_days(cfg.landing_dir):
        results += run_day(
            conn, client, cfg.landing_dir, day, ("erp", "plm", "catalog", "crm"), force=force, page_size=50
        )
    return results


def test_second_run_changes_nothing(sim, crm_client, test_conn):
    cfg, _ = sim
    first = _ingest_all(test_conn, crm_client, cfg)
    assert not [r for r in first if r.status == "failed"]
    before = _counts(test_conn)

    second = _ingest_all(test_conn, crm_client, cfg)
    file_loads = [r for r in second if r.source != "crm"]
    assert {r.status for r in file_loads} == {"skipped"}  # fichiers déjà connus
    assert not [r for r in second if r.status == "failed"]
    # le CRM relit les enregistrements à la borne du watermark : l'upsert les absorbe
    assert _counts(test_conn) == before


def test_forced_reload_replaces_the_partition(sim, crm_client, test_conn):
    cfg, _ = sim
    _ingest_all(test_conn, crm_client, cfg)
    before = _counts(test_conn)
    _ingest_all(test_conn, crm_client, cfg, force=True)
    assert _counts(test_conn) == before


def test_missing_erp_day_is_logged_as_skipped(sim, crm_client, test_conn):
    cfg, _ = sim
    _ingest_all(test_conn, crm_client, cfg)
    missing = cfg.dates[cfg.erp_missing_day]
    with test_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw.erp_mara WHERE _extract_date = %s", (missing,))
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT status FROM meta.load_log WHERE source = 'erp' AND extract_date = %s", (missing,))
        assert [r[0] for r in cur.fetchall()] == ["skipped"]


def test_renamed_column_is_added_not_fatal(sim, crm_client, test_conn):
    cfg, _ = sim
    _ingest_all(test_conn, crm_client, cfg)
    renamed = cfg.dates[cfg.erp_renamed_column_day]
    with test_conn.cursor() as cur:
        cur.execute(
            "SELECT count(maktx), count(maktx_long) FROM raw.erp_mara WHERE _extract_date = %s", (renamed,)
        )
        maktx, maktx_long = cur.fetchone()
    assert maktx == 0 and maktx_long > 0


def test_failed_load_leaves_no_partial_data(test_conn):
    df = pd.DataFrame({"MATNR": ["1", "2"]})

    def boom(_cur):
        raise RuntimeError("panne simulée après le COPY")

    result = load_dataframe(
        test_conn,
        df,
        source="test",
        table="t_fail",
        file_name="f.csv",
        extract_date=pd.Timestamp("2026-10-01").date(),
        after_load=boom,
    )
    assert result.status == "failed"
    with test_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.t_fail')")
        assert cur.fetchone()[0] is None  # même la création de table est annulée
        cur.execute("SELECT status, error_message FROM meta.load_log WHERE source = 'test'")
        status, message = cur.fetchone()
    assert status == "failed" and "panne simulée" in message
