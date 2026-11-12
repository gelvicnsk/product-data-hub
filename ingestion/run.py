"""Point d'entrée de l'ingestion batch.

    python -m ingestion.run --date 2026-10-05          # une journée
    python -m ingestion.run --all                      # toutes les journées déposées, dans l'ordre
    python -m ingestion.run --date 2026-10-05 --source erp crm
    python -m ingestion.run --date 2026-10-05 --force  # recharge même les fichiers déjà traités

Pour une journée D, chaque source est chargée « comme à la fin de D » : les
fichiers du dossier D, et pour le CRM les modifications jusqu'à D 23:59:59.
Code retour 1 si au moins un chargement a échoué (utile pour Airflow).
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterable
from datetime import date
from pathlib import Path

import httpx
import psycopg

from ingestion import db
from ingestion.extract_catalog import extract_catalog_day
from ingestion.extract_crm import extract_crm
from ingestion.extract_erp import extract_erp_day
from ingestion.extract_plm import extract_plm_day
from ingestion.loader import LoadResult

SOURCES = ("erp", "plm", "catalog", "crm")


def available_days(landing_dir: Path) -> list[date]:
    """Journées présentes dans la zone de dépôt, toutes sources confondues."""
    days = set()
    for source in ("erp", "plm", "catalog"):
        folder = landing_dir / source
        if folder.is_dir():
            for child in folder.iterdir():
                try:
                    days.add(date.fromisoformat(child.name))
                except ValueError:
                    continue
    return sorted(days)


def run_day(
    conn: psycopg.Connection,
    client: httpx.Client | None,
    landing_dir: Path,
    day: date,
    sources: Iterable[str],
    force: bool = False,
    page_size: int = 200,
) -> list[LoadResult]:
    results: list[LoadResult] = []
    if "erp" in sources:
        results += extract_erp_day(conn, landing_dir, day, force)
    if "plm" in sources:
        results += extract_plm_day(conn, landing_dir, day, force)
    if "catalog" in sources:
        results += extract_catalog_day(conn, landing_dir, day, force)
    if "crm" in sources and client is not None:
        results += extract_crm(conn, client, day, page_size)
    return results


def print_results(day: date, results: list[LoadResult]) -> None:
    print(f"\n== {day.isoformat()} ==")
    for r in results:
        detail = f"  ({r.message})" if r.message else ""
        print(f"  {r.status:<8} {r.source:<8} raw.{r.table:<18} {r.rows:>6} lignes{detail}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingestion batch du Product Data Hub")
    when = parser.add_mutually_exclusive_group(required=True)
    when.add_argument("--date", type=date.fromisoformat, help="journée à charger (AAAA-MM-JJ)")
    when.add_argument("--all", action="store_true", help="toutes les journées déposées")
    parser.add_argument("--source", nargs="+", choices=SOURCES, default=list(SOURCES))
    parser.add_argument("--force", action="store_true", help="recharger les fichiers déjà traités")
    args = parser.parse_args(argv)

    landing_dir = Path(os.getenv("LANDING_DIR", "data/landing"))
    days = available_days(landing_dir) if args.all else [args.date]
    if not days:
        print(f"Aucune journée trouvée dans {landing_dir} : lancer d'abord `make generate`.")
        return 1

    page_size = int(os.getenv("CRM_PAGE_SIZE", "200"))
    crm_url = os.getenv("CRM_API_URL", "http://localhost:8010")
    failed = 0
    with db.connect() as conn, httpx.Client(base_url=crm_url, timeout=30) as client:
        for day in days:
            results = run_day(conn, client, landing_dir, day, args.source, args.force, page_size)
            print_results(day, results)
            failed += sum(r.status == "failed" for r in results)

    if failed:
        print(f"\n{failed} chargement(s) en échec : voir meta.load_log", file=sys.stderr)
        return 1
    print("\nIngestion terminée sans erreur.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
