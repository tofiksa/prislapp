"""Request- og responsmodeller for /v2/receipts.

Penger og mengder er desimalstrenger. Et JSON-tall avvises, fordi flyttall ikke
kan bære et betalt beløp uten tap. Selve desimaltypen er delt i `schemas.v2`.
"""

from __future__ import annotations

import uuid
from datetime import date, time

from pydantic import BaseModel, Field

from app.domain.pricing import Condition, DatePrecision, LineType, PriceBasis
from app.domain.units import QuantityUnit
from app.schemas.v2 import DecimalString, decimal_string

__all__ = [
    "DecimalString",
    "decimal_string",
    "MAX_LINES",
    "ReceiptLineInput",
    "ReceiptDraftRequest",
    "ReceiptConfirmV2Request",
    "ReconciliationResponse",
    "ReceiptRevisionResponse",
]

MAX_LINES = 500


class ReceiptLineInput(BaseModel):
    """Én kvitteringslinje med stabil ID. Ukjent verdi sendes som `unknown`."""

    id: uuid.UUID
    raw_product_name: str = Field(min_length=1, max_length=512)
    user_product_id: uuid.UUID | None = None
    quantity: DecimalString | None = None
    quantity_unit: QuantityUnit = QuantityUnit.UNKNOWN
    line_type: LineType = LineType.UNKNOWN
    net_line_total: DecimalString | None = None
    printed_unit_price: DecimalString | None = None
    price_basis: PriceBasis = PriceBasis.UNKNOWN
    condition: Condition = Condition.UNKNOWN


class ReceiptDraftRequest(BaseModel):
    expected_version: int = Field(ge=0)
    mutation_id: uuid.UUID
    store_id: uuid.UUID | None = None
    purchase_date: date | None = None
    purchase_time: time | None = None
    date_precision: DatePrecision = DatePrecision.UNKNOWN
    printed_total: DecimalString | None = None
    lines: list[ReceiptLineInput] = Field(default_factory=list, max_length=MAX_LINES)


class ReceiptConfirmV2Request(ReceiptDraftRequest):
    accept_reconciliation_gap: bool = False


class ReconciliationResponse(BaseModel):
    status: str
    printed_total: str | None = None
    computed_total: str | None = None
    difference: str | None = None
    gap_accepted: bool = False
    reason: str | None = None


class ReceiptRevisionResponse(BaseModel):
    receipt_id: str
    revision: int
    status: str
    price_data_version: int
    reconciliation: ReconciliationResponse
