"""Schémas Pydantic : ce que l'API reçoit et renvoie (contrat public, distinct des tables)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from api.models import CORRECTION_FIELDS

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    total: int
    page: int
    page_size: int
    items: list[T]


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int
    matnr: str
    mfr_part_number: str | None
    product_name: str
    description: str | None
    description_source: str
    family: str
    material_type: str
    lifecycle_state: str
    revision: str | None
    standard_price: Decimal | None
    currency: str | None
    has_valid_price: bool
    last_accepted_unit_price: Decimal | None
    is_in_plm: bool
    is_in_catalog: bool
    catalog_match_method: str | None
    is_suspected_duplicate: bool


class PricePeriodOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plant: str
    standard_price: Decimal
    previous_price: Decimal | None
    change_pct: Decimal | None
    valid_from: date
    valid_to: date | None
    is_current: bool


class CatalogGapOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int
    matnr: str
    product_name: str
    family: str
    gap_type: str
    is_suspected_duplicate: bool


class EolQuoteLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    quote_line_id: str
    quote_number: str
    quote_status: str
    quote_date: date
    account_name: str | None
    product_id: int
    product_name: str
    lifecycle_state_at_quote: str
    quantity: int
    line_amount: Decimal


class SourceLoadOut(BaseModel):
    source: str
    last_success_at: datetime | None
    last_extract_date: date | None
    failed_last_24h: int


class QualitySummaryOut(BaseModel):
    products: int
    not_in_catalog: int
    suspected_duplicates: int
    invalid_prices: int
    eol_quote_lines: int
    sources: list[SourceLoadOut]


class CorrectionIn(BaseModel):
    product_id: int
    field: Literal[CORRECTION_FIELDS]  # type: ignore[valid-type]
    proposed_value: str = Field(min_length=1, max_length=2000)
    comment: str | None = Field(default=None, max_length=2000)


class CorrectionReview(BaseModel):
    status: Literal["accepted", "rejected"]


class CorrectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    field: str
    current_value: str | None
    proposed_value: str
    comment: str | None
    status: str
    requested_by: str
    created_at: datetime
    reviewed_by: str | None
    reviewed_at: datetime | None
