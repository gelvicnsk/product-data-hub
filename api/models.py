"""Modèles ORM SQLAlchemy 2.x (annotations Mapped[...]).

Deux familles, deux métadonnées :
- MartsBase / MetaBase : tables construites par dbt et par l'ingestion. L'API ne fait
  que les LIRE ; Alembic ne les gère pas (elles sont recréées à chaque `dbt build`).
- AppBase : tables propres à l'API (schéma app), versionnées par Alembic.

Pas de clé étrangère de app vers marts : dbt supprime et recrée les tables des marts
à chaque build, une contrainte bloquerait ce DROP. L'existence du produit est vérifiée
par l'API au moment de la demande.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Identity, Index, MetaData, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class MartsBase(DeclarativeBase):
    metadata = MetaData(schema="marts")


class MetaBase(DeclarativeBase):
    metadata = MetaData(schema="meta")


class AppBase(DeclarativeBase):
    metadata = MetaData(schema="app")


# --- marts (lecture seule) -----------------------------------------------------


class Product(MartsBase):
    __tablename__ = "dim_product"

    product_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    matnr: Mapped[str]
    mfr_part_number: Mapped[str | None]
    product_name: Mapped[str]
    description: Mapped[str | None]
    description_source: Mapped[str]
    family: Mapped[str]
    material_type: Mapped[str]
    lifecycle_state: Mapped[str]
    revision: Mapped[str | None]
    standard_price: Mapped[Decimal | None]
    currency: Mapped[str | None]
    has_valid_price: Mapped[bool]
    last_accepted_unit_price: Mapped[Decimal | None]
    catalog_sku: Mapped[str | None]
    catalog_match_method: Mapped[str | None]
    plm_part_number: Mapped[str | None]
    is_in_plm: Mapped[bool]
    is_in_catalog: Mapped[bool]
    is_suspected_duplicate: Mapped[bool]


class PriceHistory(MartsBase):
    __tablename__ = "fct_price_history"

    product_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    plant: Mapped[str] = mapped_column(primary_key=True)
    valid_from: Mapped[date] = mapped_column(primary_key=True)
    valid_to: Mapped[date | None]
    standard_price: Mapped[Decimal]
    previous_price: Mapped[Decimal | None]
    change_pct: Mapped[Decimal | None]
    currency: Mapped[str | None]
    is_current: Mapped[bool]


class CatalogGap(MartsBase):
    __tablename__ = "mart_catalog_gaps"

    product_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    gap_type: Mapped[str] = mapped_column(primary_key=True)
    matnr: Mapped[str]
    product_name: Mapped[str]
    family: Mapped[str]
    is_suspected_duplicate: Mapped[bool]


class EolQuoteLine(MartsBase):
    __tablename__ = "mart_eol_products_in_quotes"

    quote_line_id: Mapped[str] = mapped_column(primary_key=True)
    quote_number: Mapped[str]
    quote_status: Mapped[str]
    quote_date: Mapped[date]
    account_name: Mapped[str | None]
    product_id: Mapped[int] = mapped_column(BigInteger)
    product_name: Mapped[str]
    lifecycle_state_at_quote: Mapped[str]
    quantity: Mapped[int]
    line_amount: Mapped[Decimal]


class LoadLog(MetaBase):
    __tablename__ = "load_log"

    load_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source: Mapped[str]
    target_table: Mapped[str]
    file_name: Mapped[str | None]
    extract_date: Mapped[date | None]
    rows_loaded: Mapped[int | None]
    status: Mapped[str]
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# --- app (gérée par Alembic) ----------------------------------------------------

CORRECTION_FIELDS = ("product_name", "description", "family", "lifecycle_state", "standard_price")
CORRECTION_STATUSES = ("open", "accepted", "rejected")


class CorrectionRequest(AppBase):
    """Demande de correction d'un attribut du golden record, saisie par un data steward."""

    __tablename__ = "correction_request"
    __table_args__ = (
        CheckConstraint(f"status IN {CORRECTION_STATUSES}", name="ck_correction_status"),
        CheckConstraint(f"field IN {CORRECTION_FIELDS}", name="ck_correction_field"),
        Index("ix_correction_request_product_id", "product_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    product_id: Mapped[int] = mapped_column(BigInteger)
    field: Mapped[str] = mapped_column(String(50))
    current_value: Mapped[str | None] = mapped_column(Text)
    proposed_value: Mapped[str] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), server_default="open")
    requested_by: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_by: Mapped[str | None] = mapped_column(String(100))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
