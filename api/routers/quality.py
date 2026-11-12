"""Indicateurs de qualité des données (rôle reader)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.auth import require_role
from api.database import read_session
from api.models import CatalogGap, EolQuoteLine, LoadLog, Product
from api.schemas import CatalogGapOut, EolQuoteLineOut, Page, QualitySummaryOut, SourceLoadOut

router = APIRouter(prefix="/quality", tags=["qualité"], dependencies=[Depends(require_role("reader"))])

SessionDep = Annotated[Session, Depends(read_session)]


@router.get("/summary", response_model=QualitySummaryOut)
def summary(session: SessionDep) -> QualitySummaryOut:
    counts = session.execute(
        select(
            func.count(),
            func.count().filter(Product.is_in_catalog.is_(False)),
            func.count().filter(Product.is_suspected_duplicate.is_(True)),
            func.count().filter(Product.has_valid_price.is_(False)),
        )
    ).one()
    eol = session.scalar(select(func.count()).select_from(EolQuoteLine)) or 0

    since = datetime.now(UTC) - timedelta(hours=24)
    loads = session.execute(
        select(
            LoadLog.source,
            func.max(LoadLog.finished_at).filter(LoadLog.status == "success"),
            func.max(LoadLog.extract_date).filter(LoadLog.status == "success"),
            func.count().filter(LoadLog.status == "failed", LoadLog.started_at >= since),
        )
        .group_by(LoadLog.source)
        .order_by(LoadLog.source)
    ).all()
    return QualitySummaryOut(
        products=counts[0],
        not_in_catalog=counts[1],
        suspected_duplicates=counts[2],
        invalid_prices=counts[3],
        eol_quote_lines=eol,
        sources=[
            SourceLoadOut(source=s, last_success_at=t, last_extract_date=d, failed_last_24h=f)
            for s, t, d, f in loads
        ],
    )


@router.get("/catalog-gaps", response_model=Page[CatalogGapOut])
def catalog_gaps(
    session: SessionDep,
    gap_type: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Page[CatalogGapOut]:
    stmt = select(CatalogGap)
    if gap_type:
        stmt = stmt.where(CatalogGap.gap_type == gap_type)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = session.scalars(
        stmt.order_by(CatalogGap.product_id).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return Page(
        total=total, page=page, page_size=page_size, items=[CatalogGapOut.model_validate(r) for r in rows]
    )


@router.get("/eol-quotes", response_model=list[EolQuoteLineOut])
def eol_quotes(session: SessionDep) -> list[EolQuoteLine]:
    return list(session.scalars(select(EolQuoteLine).order_by(EolQuoteLine.quote_date.desc())))
