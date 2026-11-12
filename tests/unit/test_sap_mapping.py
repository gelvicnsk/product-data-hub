"""Lecture des formats source et normalisation des colonnes, sans base de données."""

from __future__ import annotations

import pandas as pd
import pytest

from ingestion.extract_erp import read_sap_csv
from ingestion.extract_plm import read_plm_json
from ingestion.loader import iter_records, normalize_columns, snake_case


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("MATNR", "matnr"),
        ("MAKTX_LONG", "maktx_long"),
        ("LastModifiedDate", "last_modified_date"),
        ("AccountId", "account_id"),
        ("Id", "id"),
        ("CurrencyIsoCode", "currency_iso_code"),
        ("mfr_part_number", "mfr_part_number"),
        (" Unit Price ", "unit_price"),
    ],
)
def test_snake_case(raw, expected):
    assert snake_case(raw) == expected


def test_normalize_columns_rejects_collisions():
    with pytest.raises(ValueError, match="double"):
        normalize_columns(pd.DataFrame(columns=["AccountId", "account_id"]))


def test_iter_records_turns_empty_values_into_null():
    df = pd.DataFrame({"a": ["x", "", None], "b": [1.5, float("nan"), 2]})
    assert list(iter_records(df)) == [("x", "1.5"), (None, None), (None, "2.0")]


def test_sap_csv_is_read_as_text(tmp_path):
    path = tmp_path / "MBEW_20261001.csv"
    path.write_text("MATNR;STPRS\n000000000010000001;593,28\n000000000010000002;\n")
    df = read_sap_csv(path)
    assert df.loc[0, "MATNR"] == "000000000010000001"  # zéros conservés
    assert df.loc[0, "STPRS"] == "593,28"  # décimale non interprétée
    assert df.loc[1, "STPRS"] == ""  # vide -> NULL au chargement


def test_plm_json_must_be_a_list(tmp_path):
    path = tmp_path / "plm.json"
    path.write_text('{"part_number": "PN-1"}')
    with pytest.raises(ValueError, match="liste"):
        read_plm_json(path)
