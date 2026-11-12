"""Extraction de l'export PLM quotidien (JSON) déposé dans data/landing/plm/AAAA-MM-JJ/."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import psycopg

from ingestion.loader import LoadResult, load_file_once, log_skipped

SOURCE = "plm"
TABLE = "plm_lifecycle"


def read_plm_json(path: Path) -> pd.DataFrame:
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError(f"{path.name} : une liste d'objets JSON est attendue")
    return pd.DataFrame(records, dtype=str)


def extract_plm_day(
    conn: psycopg.Connection, landing_dir: Path, day: date, force: bool = False
) -> list[LoadResult]:
    path = landing_dir / SOURCE / day.isoformat() / f"plm_lifecycle_{day:%Y%m%d}.json"
    if not path.exists():
        return [log_skipped(conn, SOURCE, TABLE, path.name, day, "aucun export PLM")]
    return [
        load_file_once(
            conn,
            source=SOURCE,
            table=TABLE,
            path=path,
            landing_dir=landing_dir,
            extract_date=day,
            reader=read_plm_json,
            force=force,
        )
    ]
