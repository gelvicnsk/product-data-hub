"""Extraction des exports ERP (type SAP) déposés chaque nuit dans data/landing/erp/AAAA-MM-JJ/.

Fichiers attendus : MARA, MBEW, MARD, STPO (séparateur ';', tout lu en texte).
Un jour sans dossier est journalisé en 'skipped' : c'est ce trou que
Elementary signalera comme anomalie de fraîcheur.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import psycopg

from ingestion.loader import LoadResult, load_file_once, log_skipped

SOURCE = "erp"
TABLES = {"MARA": "erp_mara", "MBEW": "erp_mbew", "MARD": "erp_mard", "STPO": "erp_stpo"}


def read_sap_csv(path: Path) -> pd.DataFrame:
    # dtype=str : on garde '000000000010000000' et '1234,50' tels quels ; le typage est fait dans dbt
    return pd.read_csv(path, sep=";", dtype=str, keep_default_na=False, encoding="utf-8")


def extract_erp_day(
    conn: psycopg.Connection, landing_dir: Path, day: date, force: bool = False
) -> list[LoadResult]:
    folder = landing_dir / SOURCE / day.isoformat()
    if not folder.is_dir():
        return [
            log_skipped(
                conn,
                SOURCE,
                "erp_mara",
                f"{SOURCE}/{day.isoformat()}",
                day,
                "aucun export ERP pour cette journée",
            )
        ]
    results = []
    stamp = day.strftime("%Y%m%d")
    for prefix, table in TABLES.items():
        path = folder / f"{prefix}_{stamp}.csv"
        if not path.exists():
            results.append(log_skipped(conn, SOURCE, table, path.name, day, "fichier absent"))
            continue
        results.append(
            load_file_once(
                conn,
                source=SOURCE,
                table=table,
                path=path,
                landing_dir=landing_dir,
                extract_date=day,
                reader=read_sap_csv,
                force=force,
            )
        )
    return results
