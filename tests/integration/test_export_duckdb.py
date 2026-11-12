"""Export PostgreSQL -> Parquet / DuckDB : types, NULL et écriture atomique."""

from __future__ import annotations

import os
from decimal import Decimal

import duckdb
import pytest

from analytics.export_duckdb import export

pytestmark = pytest.mark.integration


@pytest.fixture
def export_source(test_conn):
    with test_conn.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS export_test CASCADE; CREATE SCHEMA export_test")
        cur.execute("""
            CREATE TABLE export_test.sample (
                id bigint, price numeric(18, 3), label text, active boolean,
                day date, at timestamptz)""")
        cur.execute("""
            INSERT INTO export_test.sample VALUES
              (1, 1234.500, 'avec, virgule et "guillemets"', true, '2026-10-01', '2026-10-01 10:00+00'),
              (2, NULL, '', false, NULL, NULL),
              (3, 0.001, NULL, NULL, '2026-10-31', '2026-10-31 23:59+00')""")
    test_conn.commit()
    yield
    with test_conn.cursor() as cur:
        cur.execute("DROP SCHEMA export_test CASCADE")
    test_conn.commit()


def test_export_keeps_types_values_and_nulls(export_source, tmp_path):
    counts = export(
        tmp_path, schemas=("export_test",), dbname=os.getenv("POSTGRES_TEST_DB", "product_hub_test")
    )
    assert counts == {"sample": 3}
    assert (tmp_path / "sample.parquet").exists()
    assert not list(tmp_path.glob("*.tmp"))  # aucun fichier temporaire laissé

    db = duckdb.connect(str(tmp_path / "hub.duckdb"), read_only=True)
    types = dict(
        db.execute(
            "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'sample'"
        ).fetchall()
    )
    assert types["price"] == "DECIMAL(18,3)" and types["active"] == "BOOLEAN"
    assert types["day"] == "DATE" and types["at"] == "TIMESTAMP WITH TIME ZONE"

    rows = db.execute("SELECT id, price, label FROM sample ORDER BY id").fetchall()
    assert rows[0] == (1, Decimal("1234.500"), 'avec, virgule et "guillemets"')
    assert rows[1][1] is None and rows[1][2] == ""  # chaîne vide conservée, pas transformée en NULL
    assert rows[2][2] is None  # NULL conservé
    parquet = db.execute(f"SELECT count(*) FROM read_parquet('{tmp_path}/sample.parquet')").fetchone()
    assert parquet == (3,)
