import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.product import PriceObservation, Product
from app.models.receipt import Receipt, ReceiptStatus
from app.models.receipt_item import ReceiptItem
from app.models.store import Store
from app.schemas.receipt import (
    LatestStorePriceResponse,
    PriceObservationResponse,
    ProductPricesResponse,
    ProductSummaryResponse,
    StoreResponse,
)
from app.services.product_service import ProductService


class ProductPriceService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.product_service = ProductService(db)

    async def search_products(
        self,
        user_id: uuid.UUID,
        query: str,
        limit: int = 20,
    ) -> list[Product]:
        return await self.product_service.search_products_for_user(
            user_id,
            query,
            limit=limit,
        )

    async def get_product_for_user(
        self,
        user_id: uuid.UUID,
        product_id: uuid.UUID,
    ) -> Product | None:
        result = await self.db.execute(
            select(Product)
            .join(ReceiptItem, ReceiptItem.product_id == Product.id)
            .join(Receipt, Receipt.id == ReceiptItem.receipt_id)
            .where(
                Product.id == product_id,
                Receipt.user_id == user_id,
                Receipt.status == ReceiptStatus.CONFIRMED.value,
            )
            .limit(1),
        )
        return result.scalar_one_or_none()

    async def get_my_prices(
        self,
        user_id: uuid.UUID,
        product_id: uuid.UUID,
    ) -> ProductPricesResponse | None:
        product = await self.get_product_for_user(user_id, product_id)
        if not product:
            return None

        result = await self.db.execute(
            select(PriceObservation, Store)
            .join(Store, Store.id == PriceObservation.store_id)
            .where(
                PriceObservation.user_id == user_id,
                PriceObservation.product_id == product_id,
            )
            .order_by(PriceObservation.price.asc(), PriceObservation.observed_at.desc()),
        )
        rows = result.all()

        observations = [
            PriceObservationResponse(
                store=StoreResponse(
                    id=str(store.id),
                    name=store.name,
                    chain=store.chain,
                ),
                price=observation.price,
                observed_at=observation.observed_at,
            )
            for observation, store in rows
        ]

        latest_by_store: dict[uuid.UUID, LatestStorePriceResponse] = {}
        for observation, store in rows:
            if store.id not in latest_by_store:
                latest_by_store[store.id] = LatestStorePriceResponse(
                    store=StoreResponse(
                        id=str(store.id),
                        name=store.name,
                        chain=store.chain,
                    ),
                    price=observation.price,
                    observed_at=observation.observed_at,
                )

        return ProductPricesResponse(
            product=ProductSummaryResponse(
                id=str(product.id),
                canonical_name=product.canonical_name,
                category=product.category,
            ),
            cheapest=observations[0] if observations else None,
            observations=observations,
            latest_by_store=list(latest_by_store.values()),
        )
