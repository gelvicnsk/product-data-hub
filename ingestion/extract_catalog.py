"""Extraction de l'export du catalogue produit (CSV, séparateur ',')."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import psycopg

from ingestion.loader import LoadResult, load_file_once, log_skipped

SOURCE = "catalog"
TABLE = "catalog_products"


def read_catalog_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, sep=",", dtype=str, keep_default_na=False, encoding="utf-8")


def extract_catalog_day(
    conn: psycopg.Connection, landing_dir: Path, day: date, force: bool = False
) -> list[LoadResult]:
    path = landing_dir / SOURCE / day.isoformat() / f"catalog_{day:%Y%m%d}.csv"
    if not path.exists():
        return [log_skipped(conn, SOURCE, TABLE, path.name, day, "aucun export catalogue")]
    return [
        load_file_once(
            conn,
            source=SOURCE,
            table=TABLE,
            path=path,
            landing_dir=landing_dir,
            extract_date=day,
            reader=read_catalog_csv,
            force=force,
        )
    ]
