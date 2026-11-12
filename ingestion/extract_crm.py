"""Extraction incrémentale du CRM par son API REST paginée.

Pour chaque entité (comptes, devis, lignes de devis) :
1. lire le watermark (plus grand LastModifiedDate déjà chargé) ;
2. demander à l'API les enregistrements modifiés depuis ce watermark, page par page ;
3. les charger en upsert sur (id, last_modified_date) : une version déjà chargée est
   remplacée, jamais dupliquée ;
4. avancer le watermark dans la MÊME transaction que les données.

Si le chargement échoue, le watermark ne bouge pas : la prochaine exécution
reprend au même point.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time

import httpx
import pandas as pd
import psycopg

from ingestion.loader import LoadResult, load_dataframe
from ingestion.watermark import get_watermark, set_watermark_sql

SOURCE = "crm"
ENTITIES = ("accounts", "quotes", "quote_lines")
SF_FORMAT = "%Y-%m-%dT%H:%M:%S.000+0000"


def fetch_all(
    client: httpx.Client,
    entity: str,
    *,
    modified_since: datetime | None,
    as_of: datetime | None,
    page_size: int,
) -> list[dict]:
    """Suit nextRecordsUrl jusqu'à done=true et renvoie tous les enregistrements."""
    params: dict[str, str | int] = {"page_size": page_size}
    if modified_since is not None:
        params["modified_since"] = modified_since.isoformat()
    if as_of is not None:
        params["as_of"] = as_of.isoformat()
    response = client.get(f"/api/v1/{entity}", params=params)
    records: list[dict] = []
    while True:
        response.raise_for_status()
        payload = response.json()
        records.extend(payload["records"])
        if payload["done"]:
            break
        response = client.get(payload["nextRecordsUrl"])  # l'URL suivante porte déjà les filtres
    return records


def end_of_day(day: date) -> datetime:
    return datetime.combine(day, time(23, 59, 59), tzinfo=UTC)


def extract_crm(
    conn: psycopg.Connection, client: httpx.Client, as_of_day: date, page_size: int = 200
) -> list[LoadResult]:
    results = []
    as_of = end_of_day(as_of_day)
    for entity in ENTITIES:
        table = f"crm_{entity}"
        since = get_watermark(conn, SOURCE, entity)
        call = f"GET /api/v1/{entity}?modified_since={since.isoformat() if since else ''}"
        try:
            records = fetch_all(client, entity, modified_since=since, as_of=as_of, page_size=page_size)
        except httpx.HTTPError as exc:
            results.append(
                LoadResult(SOURCE, table, call, 0, "failed", f"API CRM injoignable ou en erreur : {exc}")
            )
            continue
        if not records:
            results.append(LoadResult(SOURCE, table, call, 0, "skipped", "aucune modification"))
            continue

        df = pd.DataFrame(records).astype(object)
        new_watermark = (
            pd.to_datetime(df["LastModifiedDate"], format=SF_FORMAT, utc=True).max().to_pydatetime()
        )
        results.append(
            load_dataframe(
                conn,
                df,
                source=SOURCE,
                table=table,
                file_name=call,
                extract_date=as_of_day,
                mode="upsert",
                keys=["id", "last_modified_date"],
                after_load=set_watermark_sql(SOURCE, entity, new_watermark),
            )
        )
    return results
