"""Request- og responsmodeller for /v2/receipts.

Penger og mengder er desimalstrenger. Et JSON-tall avvises, fordi flyttall ikke
kan bære et betalt beløp uten tap.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, time
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, Field

from app.domain.pricing import Condition, DatePrecision, LineType, PriceBasis
from app.domain.units import QuantityUnit

MAX_LINES = 500
_DECIMAL_STRING = re.compile(r"^-?[0-9]+(\.[0-9]+)?$")


def _decimal_from_string(value: Any) -> Any:
    if value is None or isinstance(value, Decimal):
        return value
    if isinstance(value, bool) or not isinstance(value, str):
        raise ValueError("beløp og mengder må sendes som desimalstreng")
    if not _DECIMAL_STRING.match(value):
        raise ValueError("beløp og mengder må sendes som desimalstreng")
    try:
        return Decimal(value)
    except InvalidOperation as exc:  # pragma: no cover - regexen fanger formatet
        raise ValueError("beløp og mengder må sendes som desimalstreng") from exc


DecimalString = Annotated[Decimal, BeforeValidator(_decimal_from_string)]


def decimal_string(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


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
