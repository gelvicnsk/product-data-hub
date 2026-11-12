"""Chargement idempotent dans le schéma raw, journalisé dans meta.load_log.

Principes :
- raw garde les VALEURS telles que reçues (tout en texte) ; seuls les noms de
  colonnes sont normalisés en snake_case (MATNR -> matnr, LastModifiedDate ->
  last_modified_date). Le typage se fait ensuite dans dbt (staging).
- Une colonne nouvelle dans la source est ajoutée à la table (évolution de
  schéma) au lieu de faire échouer le chargement ; Elementary la signalera.
- Rejouer un chargement ne crée jamais de doublon :
    * mode "partition" : on supprime la journée (_extract_date) puis on la recharge ;
    * mode "upsert"    : on remplace les lignes qui ont la même clé.
  Suppression et insertion se font dans la même transaction.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

import pandas as pd
import psycopg
from psycopg import sql

RAW_SCHEMA = "raw"
META_COLUMNS = ("_source_file", "_extract_date", "_loaded_at")


@dataclass
class LoadResult:
    source: str
    table: str
    file_name: str
    rows: int
    status: Literal["success", "skipped", "failed"]
    message: str = ""


def snake_case(name: str) -> str:
    """'LastModifiedDate' -> 'last_modified_date', 'MATNR' -> 'matnr', 'MAKTX_LONG' -> 'maktx_long'."""
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name.strip())
    return re.sub(r"[^0-9a-zA-Z_]+", "_", name).lower()


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    renamed = df.rename(columns=snake_case)
    dupes = renamed.columns[renamed.columns.duplicated()].tolist()
    if dupes:
        raise ValueError(f"Colonnes en double après normalisation : {dupes}")
    return renamed


def iter_records(df: pd.DataFrame) -> Iterable[tuple]:
    """Lignes prêtes pour COPY : texte, et None pour les valeurs vides."""
    for row in df.itertuples(index=False, name=None):
        yield tuple(
            None if (v is None or (isinstance(v, float) and pd.isna(v)) or v == "") else str(v) for v in row
        )


def ensure_table(cur: psycopg.Cursor, table: str, columns: list[str]) -> None:
    """Crée la table raw si besoin, puis ajoute les colonnes qui manquent."""
    ident = sql.Identifier(RAW_SCHEMA, table)
    cols = sql.SQL(", ").join(sql.SQL("{} text").format(sql.Identifier(c)) for c in columns)
    cur.execute(
        sql.SQL(
            "CREATE TABLE IF NOT EXISTS {} ({}, _source_file text NOT NULL, "
            "_extract_date date NOT NULL, _loaded_at timestamptz NOT NULL DEFAULT now())"
        ).format(ident, cols)
    )
    for c in columns:
        cur.execute(
            sql.SQL("ALTER TABLE {} ADD COLUMN IF NOT EXISTS {} text").format(ident, sql.Identifier(c))
        )


def _log_start(
    conn: psycopg.Connection, source: str, table: str, file_name: str, extract_date: date | None
) -> int:
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            "INSERT INTO meta.load_log (source, target_table, file_name, extract_date) "
            "VALUES (%s, %s, %s, %s) RETURNING load_id",
            (source, f"{RAW_SCHEMA}.{table}", file_name, extract_date),
        )
        return cur.fetchone()[0]


def _log_end(
    conn: psycopg.Connection, load_id: int, status: str, rows: int | None, error: str | None = None
) -> None:
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            "UPDATE meta.load_log SET status = %s, rows_loaded = %s, error_message = %s, "
            "finished_at = now() WHERE load_id = %s",
            (status, rows, error, load_id),
        )


def log_skipped(
    conn: psycopg.Connection, source: str, table: str, file_name: str, extract_date: date | None, reason: str
) -> LoadResult:
    load_id = _log_start(conn, source, table, file_name, extract_date)
    _log_end(conn, load_id, "skipped", 0, reason)
    return LoadResult(source, table, file_name, 0, "skipped", reason)


def load_dataframe(
    conn: psycopg.Connection,
    df: pd.DataFrame,
    *,
    source: str,
    table: str,
    file_name: str,
    extract_date: date,
    mode: Literal["partition", "upsert"] = "partition",
    keys: list[str] | None = None,
    after_load: Callable[[psycopg.Cursor], None] | None = None,
) -> LoadResult:
    """Charge df dans raw.<table> en une transaction ; after_load s'exécute dans la même."""
    if mode == "upsert" and not keys:
        raise ValueError("le mode upsert exige des colonnes clés")
    df = normalize_columns(df)
    columns = list(df.columns)
    if any(c in META_COLUMNS for c in columns):
        raise ValueError(f"colonne réservée dans les données : {columns}")
    target = sql.Identifier(RAW_SCHEMA, table)
    all_cols = [*columns, "_source_file", "_extract_date"]
    col_list = sql.SQL(", ").join(map(sql.Identifier, all_cols))

    load_id = _log_start(conn, source, table, file_name, extract_date)
    try:
        with conn.transaction(), conn.cursor() as cur:
            ensure_table(cur, table, columns)
            if mode == "partition":
                cur.execute(
                    sql.SQL("DELETE FROM {} WHERE _extract_date = %s").format(target), (extract_date,)
                )
                copy_target = target
            else:
                cur.execute(
                    sql.SQL("CREATE TEMP TABLE _incoming ON COMMIT DROP AS SELECT {} FROM {} LIMIT 0").format(
                        col_list, target
                    )
                )
                copy_target = sql.Identifier("_incoming")

            with cur.copy(sql.SQL("COPY {} ({}) FROM STDIN").format(copy_target, col_list)) as cp:
                for record in iter_records(df):
                    cp.write_row((*record, file_name, extract_date))

            if mode == "upsert":
                match = sql.SQL(" AND ").join(
                    sql.SQL("t.{k} = i.{k}").format(k=sql.Identifier(k)) for k in keys
                )
                cur.execute(sql.SQL("DELETE FROM {} t USING _incoming i WHERE {}").format(target, match))
                cur.execute(
                    sql.SQL("INSERT INTO {} ({}) SELECT DISTINCT {} FROM _incoming").format(
                        target, col_list, col_list
                    )
                )
            if after_load:
                after_load(cur)
    except Exception as exc:
        _log_end(conn, load_id, "failed", None, str(exc)[:2000])
        return LoadResult(source, table, file_name, 0, "failed", str(exc))

    _log_end(conn, load_id, "success", len(df))
    return LoadResult(source, table, file_name, len(df), "success")


# --- sources fichier : registre des fichiers déjà traités -----------------------


def file_checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def already_processed(conn: psycopg.Connection, source: str, rel_path: str, checksum: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT checksum FROM meta.processed_files WHERE source = %s AND file_path = %s",
            (source, rel_path),
        )
        row = cur.fetchone()
    conn.commit()
    return row is not None and row[0] == checksum


def mark_processed_sql(
    source: str, rel_path: str, checksum: str, rows: int
) -> Callable[[psycopg.Cursor], None]:
    """Enregistre le fichier comme traité, dans la transaction du chargement."""

    def _mark(cur: psycopg.Cursor) -> None:
        cur.execute(
            "INSERT INTO meta.processed_files (source, file_path, checksum, rows_loaded) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (source, file_path) DO UPDATE "
            "SET checksum = EXCLUDED.checksum, rows_loaded = EXCLUDED.rows_loaded, "
            "processed_at = now()",
            (source, rel_path, checksum, rows),
        )

    return _mark


def load_file_once(
    conn: psycopg.Connection,
    *,
    source: str,
    table: str,
    path: Path,
    landing_dir: Path,
    extract_date: date,
    reader: Callable[[Path], pd.DataFrame],
    force: bool = False,
) -> LoadResult:
    """Charge un fichier déposé, sauf s'il a déjà été chargé avec le même contenu."""
    rel = path.relative_to(landing_dir).as_posix()
    checksum = file_checksum(path)
    if not force and already_processed(conn, source, rel, checksum):
        return LoadResult(source, table, rel, 0, "skipped", "déjà chargé (même contenu)")
    df = reader(path)
    return load_dataframe(
        conn,
        df,
        source=source,
        table=table,
        file_name=rel,
        extract_date=extract_date,
        mode="partition",
        after_load=mark_processed_sql(source, rel, checksum, len(df)),
    )
