"""Export des marts et des snapshots PostgreSQL vers Parquet et DuckDB (analyse locale).

    python -m analytics.export_duckdb          # ou : make analytics

Sorties (dans data/analytics/) :
    <table>.parquet   un fichier par table, lisible par DuckDB, pandas, Spark, Power BI...
    hub.duckdb        base DuckDB autonome contenant les mêmes tables

Principes :
- Les TYPES PostgreSQL sont conservés (DECIMAL, DATE, TIMESTAMPTZ, BOOLEAN...) : on lit le
  schéma dans information_schema et on crée chaque table DuckDB avec les types
  correspondants, au lieu de laisser l'outil les deviner.
- NULL et chaîne vide restent distincts (COPY CSV de PostgreSQL : NULL non quoté, "" quoté).
- Écritures atomiques : fichier temporaire puis os.replace. Un lecteur (notebook, BI) ne voit
  jamais un fichier à moitié écrit ; DuckDB n'acceptant qu'un écrivain à la fois, on ne
  modifie jamais hub.duckdb en place.
"""

from __future__ import annotations

import argparse
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import duckdb
import psycopg

from ingestion.db import connect

SCHEMAS = ("marts", "snapshots")
OUTPUT_DIR = Path(os.getenv("ANALYTICS_DIR", "data/analytics"))


@dataclass(frozen=True)
class Column:
    name: str
    pg_type: str
    precision: int | None
    scale: int | None


def duckdb_type(col: Column) -> str:
    """Type DuckDB équivalent au type PostgreSQL (information_schema.columns.data_type)."""
    t = col.pg_type
    if t == "numeric":
        if col.precision is not None:
            return f"DECIMAL({min(col.precision, 38)},{col.scale or 0})"
        return "DOUBLE"  # numeric sans précision : pas d'équivalent DECIMAL exact
    mapping = {
        "bigint": "BIGINT",
        "integer": "INTEGER",
        "smallint": "SMALLINT",
        "double precision": "DOUBLE",
        "real": "FLOAT",
        "boolean": "BOOLEAN",
        "date": "DATE",
        "timestamp without time zone": "TIMESTAMP",
        "timestamp with time zone": "TIMESTAMPTZ",
        "text": "VARCHAR",
        "character varying": "VARCHAR",
        "character": "VARCHAR",
    }
    return mapping.get(t, "VARCHAR")


def list_tables(conn: psycopg.Connection, schemas: tuple[str, ...]) -> list[tuple[str, str]]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_schema = ANY(%s) AND table_type = 'BASE TABLE' ORDER BY 1, 2",
            (list(schemas),),
        )
        return cur.fetchall()


def table_columns(conn: psycopg.Connection, schema: str, table: str) -> list[Column]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name, data_type, numeric_precision, numeric_scale "
            "FROM information_schema.columns WHERE table_schema = %s AND table_name = %s "
            "ORDER BY ordinal_position",
            (schema, table),
        )
        return [Column(*row) for row in cur.fetchall()]


def dump_csv(conn: psycopg.Connection, schema: str, table: str, path: Path) -> None:
    """COPY ... TO STDOUT : rapide, et NULL (vide) distinct de "" (vide quoté)."""
    query = psycopg.sql.SQL("COPY {}.{} TO STDOUT WITH (FORMAT csv)").format(
        psycopg.sql.Identifier(schema), psycopg.sql.Identifier(table)
    )
    with conn.cursor() as cur, path.open("wb") as fh, cur.copy(query) as copy:
        for chunk in copy:
            fh.write(chunk)


def load_into_duckdb(db: duckdb.DuckDBPyConnection, name: str, columns: list[Column], csv: Path) -> int:
    ddl = ", ".join(f'"{c.name}" {duckdb_type(c)}' for c in columns)
    db.execute(f'CREATE TABLE "{name}" ({ddl})')
    types = "{" + ", ".join(f"'{c.name}': '{duckdb_type(c)}'" for c in columns) + "}"
    db.execute(
        f"""INSERT INTO "{name}" SELECT * FROM read_csv(?, header = false, columns = {types},
                allow_quoted_nulls = false, timestampformat = 'auto')""",
        [str(csv)],
    )
    return db.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]


def export(
    output_dir: Path = OUTPUT_DIR, schemas: tuple[str, ...] = SCHEMAS, dbname: str | None = None
) -> dict[str, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    final_db = output_dir / "hub.duckdb"
    tmp_db = output_dir / "hub.duckdb.tmp"
    tmp_db.unlink(missing_ok=True)

    counts: dict[str, int] = {}
    with connect(dbname) as pg, tempfile.TemporaryDirectory() as workdir:
        db = duckdb.connect(str(tmp_db))
        try:
            for schema, table in list_tables(pg, schemas):
                columns = table_columns(pg, schema, table)
                csv = Path(workdir) / f"{table}.csv"
                dump_csv(pg, schema, table, csv)
                counts[table] = load_into_duckdb(db, table, columns, csv)

                parquet = output_dir / f"{table}.parquet"
                tmp_parquet = output_dir / f"{table}.parquet.tmp"
                db.execute(f"""COPY "{table}" TO '{tmp_parquet}' (FORMAT parquet, COMPRESSION zstd)""")
                os.replace(tmp_parquet, parquet)
        finally:
            db.close()
    os.replace(tmp_db, final_db)  # remplacement atomique : jamais de base à moitié écrite
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    counts = export(args.output_dir)
    for table, n in counts.items():
        print(f"  {table:<32} {n:>7} lignes")
    print(f"Export terminé : {args.output_dir}/hub.duckdb + {len(counts)} fichiers Parquet")


if __name__ == "__main__":
    main()
