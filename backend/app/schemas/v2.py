"""Responsmodeller for /v2. Penger og mengder er desimalstrenger, aldri JSON-tall."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from app.models.user_product import UserProduct
from app.models.user_store import UserStore


def _decimal_string(value: Decimal | None) -> str | None:
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
            pack_content=_decimal_string(product.pack_content),
            pack_unit=product.pack_unit,
            pack_count=_decimal_string(product.pack_count),
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
