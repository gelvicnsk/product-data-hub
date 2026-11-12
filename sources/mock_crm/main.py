"""Faux CRM type Salesforce : API REST en lecture, paginée, filtrable par date de modification.

    uvicorn sources.mock_crm.main:app --port 8010

    GET /health
    GET /api/v1/{entity}?modified_since=...&as_of=...&page_size=200
        entity : accounts | quotes | quote_lines
        as_of           l'API répond « comme à cette date » (simulation du temps qui passe)
        modified_since  ne renvoie que les enregistrements modifiés à partir de cette date (incluse)

Réponse paginée, sur le modèle de l'API Salesforce :
    {"totalSize": 1234, "done": false, "nextRecordsUrl": "/api/v1/quotes?...&cursor=200",
     "records": [...]}
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode

import pandas as pd
from fastapi import FastAPI, HTTPException, Query

from sources.generate_crm import ENTITIES

app = FastAPI(title="Mock CRM (type Salesforce)", version="1.0")

SF_FORMAT = "%Y-%m-%dT%H:%M:%S.000+0000"


def crm_db_dir() -> Path:
    landing = Path(os.getenv("LANDING_DIR", "data/landing"))
    return Path(os.getenv("CRM_DB_DIR", str(landing.parent / "crm_db")))


_cache: dict[str, tuple[float, pd.DataFrame]] = {}


def _versions(entity: str) -> pd.DataFrame:
    """Toutes les versions d'une entité ; relues si le fichier a changé."""
    path = crm_db_dir() / f"{entity}.jsonl"
    if not path.exists():
        raise HTTPException(503, f"Base CRM absente : {path}. Lancer la simulation d'abord.")
    mtime = path.stat().st_mtime
    if entity not in _cache or _cache[entity][0] != mtime:
        df = pd.read_json(path, lines=True, dtype=False)
        df["_modified"] = pd.to_datetime(df["LastModifiedDate"], format=SF_FORMAT, utc=True)
        _cache[entity] = (mtime, df)
    return _cache[entity][1]


def _parse(value: str | None, name: str) -> datetime | None:
    if value is None:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(422, f"{name} : date ISO 8601 attendue, reçu {value!r}") from exc
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/v1/{entity}")
def list_records(
    entity: str,
    modified_since: str | None = None,
    as_of: str | None = None,
    page_size: Annotated[int, Query(ge=1, le=2000)] = 200,
    cursor: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    if entity not in ENTITIES:
        raise HTTPException(404, f"Entité inconnue : {entity}. Valeurs : {', '.join(ENTITIES)}")
    since, until = _parse(modified_since, "modified_since"), _parse(as_of, "as_of")

    df = _versions(entity)
    if until is not None:
        df = df[df["_modified"] <= until]
    # état de chaque enregistrement à la date as_of : sa dernière version
    df = df.sort_values(["_modified", "Id"]).drop_duplicates("Id", keep="last")
    if since is not None:
        df = df[df["_modified"] >= since]
    df = df.sort_values(["_modified", "Id"])

    page = df.iloc[cursor : cursor + page_size].drop(columns="_modified")
    next_cursor = cursor + page_size
    done = next_cursor >= len(df)
    params = {
        k: v
        for k, v in {"modified_since": modified_since, "as_of": as_of, "page_size": page_size}.items()
        if v is not None
    }
    return {
        "totalSize": int(len(df)),
        "done": done,
        "nextRecordsUrl": None
        if done
        else f"/api/v1/{entity}?{urlencode({**params, 'cursor': next_cursor})}",
        "records": page.astype(object).where(page.notna(), None).to_dict(orient="records"),
    }
