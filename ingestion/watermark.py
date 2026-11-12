"""Watermarks des extractions incrémentales (meta.extract_watermark).

Le watermark d'une entité est le plus grand LastModifiedDate déjà chargé.
L'extraction suivante demande les enregistrements modifiés À PARTIR de cette
date (borne incluse) : les enregistrements à la frontière sont relus, puis
dédoublonnés par l'upsert. On ne perd donc rien, et on ne duplique rien.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import psycopg


def get_watermark(conn: psycopg.Connection, source: str, entity: str) -> datetime | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT watermark FROM meta.extract_watermark WHERE source = %s AND entity = %s",
            (source, entity),
        )
        row = cur.fetchone()
    conn.commit()
    return row[0] if row else None


def set_watermark_sql(source: str, entity: str, value: datetime) -> Callable[[psycopg.Cursor], None]:
    """Met à jour le watermark dans la transaction du chargement (jamais en arrière)."""

    def _set(cur: psycopg.Cursor) -> None:
        cur.execute(
            "INSERT INTO meta.extract_watermark (source, entity, watermark) VALUES (%s, %s, %s) "
            "ON CONFLICT (source, entity) DO UPDATE "
            "SET watermark = GREATEST(meta.extract_watermark.watermark, EXCLUDED.watermark), "
            "updated_at = now()",
            (source, entity, value),
        )

    return _set
