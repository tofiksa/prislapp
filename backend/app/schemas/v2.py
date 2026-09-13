"""Responsmodeller for /v2. Penger og mengder er desimalstrenger, aldri JSON-tall."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator

from app.models.user_product import UserProduct
from app.models.user_store import UserStore

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


# Et JSON-tall avvises, fordi flyttall ikke kan bære et betalt beløp uten tap.
DecimalString = Annotated[Decimal, BeforeValidator(_decimal_from_string)]


def decimal_string(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


class FieldErrorResponse(BaseModel):
    field: str
    code: str
    message: str


class ErrorResponse(BaseModel):
    code: str
    message: str
    field_errors: list[FieldErrorResponse] = []
    retryable: bool
    request_id: str


class UserProductResponse(BaseModel):
    id: str
    display_name: str
    brand: str | None = None
    variant: str | None = None
    pack_content: str | None = None
    pack_unit: str
    pack_count: str | None = None
    identity_status: str
    last_purchased_at: str | None = None
    purchase_count: int
    version: int

    @classmethod
    def from_model(cls, product: UserProduct) -> "UserProductResponse":
        return cls(
            id=str(product.id),
            display_name=product.display_name,
            brand=product.brand,
            variant=product.variant,
            pack_content=decimal_string(product.pack_content),
            pack_unit=product.pack_unit,
            pack_count=decimal_string(product.pack_count),
            identity_status=product.identity_status,
            last_purchased_at=(
                product.last_purchased_at.date().isoformat()
                if product.last_purchased_at
                else None
            ),
            purchase_count=product.purchase_count,
            version=product.version,
        )


class UserProductListResponse(BaseModel):
    items: list[UserProductResponse]
    next_cursor: str | None = None


class UserStoreResponse(BaseModel):
    id: str
    display_name: str
    chain: str | None = None
    branch_name: str | None = None
    identity_level: str
    version: int

    @classmethod
    def from_model(cls, store: UserStore) -> "UserStoreResponse":
        return cls(
            id=str(store.id),
            display_name=store.display_name,
            chain=store.chain,
            branch_name=store.branch_name,
            identity_level=store.identity_level,
            version=store.version,
        )


class UserStoreListResponse(BaseModel):
    items: list[UserStoreResponse]
    next_cursor: str | None = None
