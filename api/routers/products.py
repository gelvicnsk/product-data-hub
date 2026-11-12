"""Golden record produit : consultation (rôle reader)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from api.auth import require_role
from api.database import read_session
from api.models import PriceHistory, Product
from api.schemas import Page, PricePeriodOut, ProductOut

router = APIRouter(prefix="/products", tags=["produits"], dependencies=[Depends(require_role("reader"))])

SessionDep = Annotated[Session, Depends(read_session)]


@router.get("", response_model=Page[ProductOut])
def list_products(
    session: SessionDep,
    family: str | None = None,
    lifecycle_state: str | None = None,
    in_catalog: bool | None = None,
    suspected_duplicate: bool | None = None,
    q: Annotated[str | None, Query(description="recherche dans le nom, MATNR ou référence")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Page[ProductOut]:
    stmt = select(Product)
    if family:
        stmt = stmt.where(Product.family == family)
    if lifecycle_state:
        stmt = stmt.where(Product.lifecycle_state == lifecycle_state)
    if in_catalog is not None:
        stmt = stmt.where(Product.is_in_catalog.is_(in_catalog))
    if suspected_duplicate is not None:
        stmt = stmt.where(Product.is_suspected_duplicate.is_(suspected_duplicate))
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(
                Product.product_name.ilike(pattern),
                Product.matnr.ilike(pattern),
                Product.mfr_part_number.ilike(pattern),
            )
        )

    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = session.scalars(
        stmt.order_by(Product.product_id).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return Page(
        total=total, page=page, page_size=page_size, items=[ProductOut.model_validate(r) for r in rows]
    )


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: int, session: SessionDep) -> Product:
    product = session.get(Product, product_id)
    if product is None:
        raise HTTPException(404, f"Produit {product_id} inconnu")
    return product


@router.get("/{product_id}/price-history", response_model=list[PricePeriodOut])
def price_history(product_id: int, session: SessionDep) -> list[PriceHistory]:
    if session.get(Product, product_id) is None:
        raise HTTPException(404, f"Produit {product_id} inconnu")
    stmt = (
        select(PriceHistory)
        .where(PriceHistory.product_id == product_id)
        .order_by(PriceHistory.plant, PriceHistory.valid_from)
    )
    return list(session.scalars(stmt))
