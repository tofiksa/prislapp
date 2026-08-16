import re
import unicodedata
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product, ProductAlias


def normalize_product_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name.lower())
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


class ProductService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def resolve_product(
        self,
        raw_name: str,
        store_id: uuid.UUID | None,
    ) -> Product:
        normalized = normalize_product_name(raw_name)
        if not normalized:
            normalized = raw_name.strip().lower()

        result = await self.db.execute(
            select(ProductAlias)
            .where(ProductAlias.alias_name == normalized)
            .limit(1),
        )
        alias = result.scalar_one_or_none()
        if alias:
            product = await self.db.get(Product, alias.product_id)
            if product:
                return product

        product = Product(canonical_name=raw_name.strip())
        self.db.add(product)
        await self.db.flush()

        self.db.add(
            ProductAlias(
                product_id=product.id,
                alias_name=normalized,
                store_id=store_id,
            ),
        )
        await self.db.flush()
        return product

    async def search_products_for_user(
        self,
        user_id: uuid.UUID,
        query: str,
        limit: int = 20,
    ) -> list[Product]:
        from app.models.receipt import Receipt
        from app.models.receipt_item import ReceiptItem

        normalized_query = normalize_product_name(query)
        if not normalized_query:
            return []

        pattern = f"%{normalized_query}%"
        result = await self.db.execute(
            select(Product)
            .join(ProductAlias, ProductAlias.product_id == Product.id)
            .join(ReceiptItem, ReceiptItem.product_id == Product.id)
            .join(Receipt, Receipt.id == ReceiptItem.receipt_id)
            .where(
                Receipt.user_id == user_id,
                ProductAlias.alias_name.like(pattern),
            )
            .distinct()
            .limit(limit),
        )
        return list(result.scalars().all())
