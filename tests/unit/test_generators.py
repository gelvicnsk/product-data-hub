"""La simulation doit être reproductible et contenir exactement les anomalies annoncées."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from sources.simulate_days import anomalies_path, crm_db_dir, simulate
from tests.conftest import SMALL_ANOMALIES, small_config


def _digest(folder: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        h.update(path.relative_to(folder).as_posix().encode())
        h.update(path.read_bytes())
    return h.hexdigest()


def test_same_seed_gives_identical_files(tmp_path):
    a, b = small_config(tmp_path / "a"), small_config(tmp_path / "b")
    simulate(a)
    simulate(b)
    assert _digest(a.landing_dir.parent) == _digest(b.landing_dir.parent)


def test_other_seed_gives_other_files(tmp_path):
    a, b = small_config(tmp_path / "a"), small_config(tmp_path / "b", seed=8)
    simulate(a)
    simulate(b)
    assert _digest(a.landing_dir) != _digest(b.landing_dir)


def test_anomaly_counts_match_configuration(sim):
    cfg, log = sim
    written = json.loads(anomalies_path(cfg).read_text())
    assert written["counts"] == SMALL_ANOMALIES
    assert log.counts == SMALL_ANOMALIES


def test_sap_export_conventions(sim):
    cfg, _ = sim
    mara = pd.read_csv(cfg.landing_dir / "erp/2026-10-01/MARA_20261001.csv", sep=";", dtype=str)
    assert mara["MATNR"].str.fullmatch(r"\d{18}").all()
    assert mara["ERSDA"].str.fullmatch(r"\d{8}").all()
    mbew = pd.read_csv(cfg.landing_dir / "erp/2026-10-01/MBEW_20261001.csv", sep=";", dtype=str)
    assert mbew["STPRS"].str.contains(",").all()  # décimale à la française
    assert not mbew["STPRS"].str.contains(r"\.").any()


def test_duplicates_share_manufacturer_reference(sim):
    cfg, log = sim
    mara = pd.read_csv(cfg.landing_dir / "erp/2026-10-01/MARA_20261001.csv", sep=";", dtype=str)
    for dup in log.details["duplicate_material"]:
        rows = mara[mara["MFRPN"] == dup["mfrpn"]]
        assert len(rows) == 2


def test_non_positive_prices_are_exported(sim):
    cfg, log = sim
    mbew = pd.read_csv(cfg.landing_dir / "erp/2026-10-01/MBEW_20261001.csv", sep=";", dtype=str)
    prices = mbew["STPRS"].str.replace(",", ".").astype(float)
    assert (prices <= 0).sum() == SMALL_ANOMALIES["non_positive_price"]


def test_delivery_incidents(sim):
    cfg, log = sim
    missing_day = cfg.dates[cfg.erp_missing_day]
    assert not (cfg.landing_dir / "erp" / missing_day.isoformat()).exists()
    assert log.incidents["erp_missing_export"] == missing_day.isoformat()

    renamed_day = cfg.dates[cfg.erp_renamed_column_day]
    header = (
        (cfg.landing_dir / "erp" / renamed_day.isoformat() / f"MARA_{renamed_day:%Y%m%d}.csv")
        .read_text()
        .splitlines()[0]
    )
    assert "MAKTX_LONG" in header.split(";")


def test_crm_keeps_one_version_per_change(sim):
    cfg, _ = sim
    quotes = pd.read_json(crm_db_dir(cfg) / "quotes.jsonl", lines=True, dtype=False)
    # plusieurs versions pour certains devis, toutes partant de Draft
    versions = quotes.groupby("Id").size()
    assert (versions > 1).any()
    first = quotes.drop_duplicates("Id", keep="first")
    assert (first["Status"] == "Draft").all()


def test_unknown_products_are_absent_from_erp(sim):
    cfg, log = sim
    mara = pd.read_csv(cfg.landing_dir / "erp/2026-10-01/MARA_20261001.csv", sep=";", dtype=str)
    known = set(mara["MATNR"].str.lstrip("0"))
    for item in log.details["unknown_product_in_quotes"]:
        assert item["product_code"] not in known
