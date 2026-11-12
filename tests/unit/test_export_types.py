"""Correspondance des types PostgreSQL -> DuckDB de l'export analytique."""

from __future__ import annotations

import pytest

from analytics.export_duckdb import Column, duckdb_type


@pytest.mark.parametrize(
    ("pg_type", "precision", "scale", "expected"),
    [
        ("numeric", 18, 3, "DECIMAL(18,3)"),
        ("numeric", None, None, "DOUBLE"),  # numeric sans précision : pas de DECIMAL exact
        ("numeric", 60, 2, "DECIMAL(38,2)"),  # DuckDB limite DECIMAL à 38 chiffres
        ("bigint", None, None, "BIGINT"),
        ("boolean", None, None, "BOOLEAN"),
        ("date", None, None, "DATE"),
        ("timestamp with time zone", None, None, "TIMESTAMPTZ"),
        ("timestamp without time zone", None, None, "TIMESTAMP"),
        ("text", None, None, "VARCHAR"),
        ("jsonb", None, None, "VARCHAR"),  # type inconnu : texte plutôt qu'une erreur
    ],
)
def test_duckdb_type(pg_type, precision, scale, expected):
    assert duckdb_type(Column("c", pg_type, precision, scale)) == expected
