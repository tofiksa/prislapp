"""Eieravgrensede oppslag i den private katalogen med stabil cursor-paginering."""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiError, FieldError, invalid_cursor
from app.models.user_product import UserProduct, UserProductAlias
from app.models.user_store import UserStore
from app.services.product_service import normalize_product_name

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100
PRODUCT_SORTS = ("recent", "frequent", "name")

# Ukjent kjøpsdato sorteres sist uten å bli gjort om til en dato.
_UNKNOWN_DATE = datetime(1970, 1, 1, tzinfo=timezone.utc)


def page_size(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_PAGE_SIZE
    return max(1, min(limit, MAX_PAGE_SIZE))


def _encode_cursor(scope: str, key: str, row_id: uuid.UUID) -> str:
    payload = json.dumps({"s": scope, "k": key, "i": str(row_id)}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def _decode_cursor(cursor: str, scope: str) -> tuple[str, uuid.UUID]:
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()))
        if payload["s"] != scope:
            raise ValueError("cursor belongs to another ordering")
        return payload["k"], uuid.UUID(payload["i"])
    except (binascii.Error, KeyError, TypeError, ValueError, UnicodeDecodeError) as exc:
        raise invalid_cursor() from exc


def _like_pattern(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _keyset(expression, row_id_column, key: Any, row_id: uuid.UUID, descending: bool):
    """Neste side starter etter (sorteringsnøkkel, ID); ID-en gjør rekkefølgen stabil."""
    ahead = expression < key if descending else expression > key
    return sa.or_(ahead, sa.and_(expression == key, row_id_column > row_id))


class PrivateCatalogService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_products(
        self,
        user_id: uuid.UUID,
        query: str | None = None,
        sort: str = "recent",
        cursor: str | None = None,
        limit: int | None = None,
    ) -> tuple[list[UserProduct], str | None]:
        if sort not in PRODUCT_SORTS:
            raise ApiError(
                400,
                "INVALID_SORT",
                "Ukjent sortering.",
                [FieldError("sort", "unsupported_sort", "Sorteringen støttes ikke.")],
            )

        size = page_size(limit)
        expression, descending = self._product_sort_expression(sort)
        filters = [UserProduct.user_id == user_id]
        if query and query.strip():
            filters.append(self._product_search_filter(user_id, query.strip()))
        if cursor:
            key, row_id = _decode_cursor(cursor, f"products:{sort}")
            filters.append(
                _keyset(
                    expression,
                    UserProduct.id,
                    self._product_cursor_value(sort, key),
                    row_id,
                    descending,
                ),
            )

        ordering = expression.desc() if descending else expression.asc()
        result = await self.db.execute(
            sa.select(UserProduct)
            .where(*filters)
            .order_by(ordering, UserProduct.id.asc())
            .limit(size + 1),
        )
        products = list(result.scalars().all())
        if len(products) <= size:
            return products, None
        page = products[:size]
        last = page[-1]
        return page, _encode_cursor(
            f"products:{sort}",
            self._product_cursor_key(sort, last),
            last.id,
        )

    async def get_product(
        self,
        user_id: uuid.UUID,
        product_id: uuid.UUID,
    ) -> UserProduct | None:
        result = await self.db.execute(
            sa.select(UserProduct).where(
                UserProduct.id == product_id,
                UserProduct.user_id == user_id,
            ),
        )
        return result.scalar_one_or_none()

    async def list_stores(
        self,
        user_id: uuid.UUID,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> tuple[list[UserStore], str | None]:
        size = page_size(limit)
        expression = sa.func.lower(UserStore.display_name)
        filters = [UserStore.user_id == user_id]
        if cursor:
            key, row_id = _decode_cursor(cursor, "stores:name")
            filters.append(_keyset(expression, UserStore.id, key, row_id, descending=False))

        result = await self.db.execute(
            sa.select(UserStore)
            .where(*filters)
            .order_by(expression.asc(), UserStore.id.asc())
            .limit(size + 1),
        )
        stores = list(result.scalars().all())
        if len(stores) <= size:
            return stores, None
        page = stores[:size]
        last = page[-1]
        return page, _encode_cursor("stores:name", last.display_name.lower(), last.id)

    def _product_sort_expression(self, sort: str):
        if sort == "name":
            return sa.func.lower(UserProduct.display_name), False
        if sort == "frequent":
            return UserProduct.purchase_count, True
        return sa.func.coalesce(UserProduct.last_purchased_at, _UNKNOWN_DATE), True

    def _product_search_filter(self, user_id: uuid.UUID, query: str):
        matches = [
            sa.func.lower(UserProduct.display_name).like(
                _like_pattern(query.lower()),
                escape="\\",
            ),
        ]
        normalized = normalize_product_name(query)
        if normalized:
            matches.append(
                sa.select(sa.literal(1))
                .where(
                    UserProductAlias.user_product_id == UserProduct.id,
                    UserProductAlias.user_id == user_id,
                    UserProductAlias.normalized_text.like(
                        _like_pattern(normalized),
                        escape="\\",
                    ),
                )
                .exists(),
            )
        return sa.or_(*matches)

    def _product_cursor_key(self, sort: str, product: UserProduct) -> str:
        if sort == "name":
            return product.display_name.lower()
        if sort == "frequent":
            return str(product.purchase_count)
        return (product.last_purchased_at or _UNKNOWN_DATE).isoformat()

    def _product_cursor_value(self, sort: str, key: str) -> Any:
        if sort == "name":
            return key
        try:
            if sort == "frequent":
                return int(key)
            return datetime.fromisoformat(key)
        except ValueError as exc:
            raise invalid_cursor() from exc
