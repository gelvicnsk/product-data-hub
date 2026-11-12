"""Demandes de correction du golden record.

Lecture : rôle reader. Création et revue : rôle data_steward.
Les demandes sont écrites dans app.correction_request avec un rôle PostgreSQL
qui ne peut écrire QUE dans ce schéma (moindre privilège).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.auth import User, require_role
from api.database import read_session, write_session
from api.models import CorrectionRequest, Product
from api.schemas import CorrectionIn, CorrectionOut, CorrectionReview

router = APIRouter(prefix="/corrections", tags=["corrections"])

ReadSession = Annotated[Session, Depends(read_session)]
WriteSession = Annotated[Session, Depends(write_session)]


@router.get("", response_model=list[CorrectionOut], dependencies=[Depends(require_role("reader"))])
def list_corrections(session: WriteSession, status_filter: str | None = None) -> list[CorrectionRequest]:
    stmt = select(CorrectionRequest).order_by(CorrectionRequest.id.desc())
    if status_filter:
        stmt = stmt.where(CorrectionRequest.status == status_filter)
    return list(session.scalars(stmt))


@router.post("", response_model=CorrectionOut, status_code=status.HTTP_201_CREATED)
def create_correction(
    body: CorrectionIn,
    reader: ReadSession,
    session: WriteSession,
    user: Annotated[User, Depends(require_role("data_steward"))],
) -> CorrectionRequest:
    product = reader.get(Product, body.product_id)
    if product is None:
        raise HTTPException(404, f"Produit {body.product_id} inconnu")
    current = getattr(product, body.field)
    correction = CorrectionRequest(
        product_id=body.product_id,
        field=body.field,
        current_value=None if current is None else str(current),
        proposed_value=body.proposed_value,
        comment=body.comment,
        requested_by=user.username,
    )
    session.add(correction)
    session.commit()
    session.refresh(correction)
    return correction


@router.patch("/{correction_id}", response_model=CorrectionOut)
def review_correction(
    correction_id: int,
    body: CorrectionReview,
    session: WriteSession,
    user: Annotated[User, Depends(require_role("data_steward"))],
) -> CorrectionRequest:
    correction = session.get(CorrectionRequest, correction_id)
    if correction is None:
        raise HTTPException(404, f"Demande {correction_id} inconnue")
    if correction.status != "open":
        raise HTTPException(409, f"Demande déjà traitée ({correction.status})")
    correction.status = body.status
    correction.reviewed_by = user.username
    correction.reviewed_at = datetime.now(UTC)
    session.commit()
    session.refresh(correction)
    return correction
