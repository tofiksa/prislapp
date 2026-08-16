import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.product import PriceObservation
from app.models.receipt import Receipt, ReceiptStatus
from app.models.receipt_item import ReceiptItem
from app.models.store import Store
from app.models.user import User
from app.services.product_service import ProductService
from app.services.storage_service import StorageService
from app.services.store_service import normalize_store_name


class ReceiptService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.storage = StorageService()

    async def create_receipt(
        self,
        user: User,
        image_bytes: bytes,
        content_type: str = "image/jpeg",
    ) -> Receipt:
        receipt_id = uuid.uuid4()
        extension = "jpg" if "jpeg" in content_type else "png"
        object_name = f"{user.id}/{receipt_id}.{extension}"
        self.storage.upload_receipt(object_name, image_bytes, content_type)

        receipt = Receipt(
            id=receipt_id,
            user_id=user.id,
            status=ReceiptStatus.UPLOADED.value,
            image_path=object_name,
            image_expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.receipt_image_retention_days),
        )
        self.db.add(receipt)
        await self.db.commit()
        await self.db.refresh(receipt)
        return receipt

    async def mark_processing(self, receipt_id: uuid.UUID) -> None:
        receipt = await self._get_receipt_by_id(receipt_id)
        if receipt:
            receipt.status = ReceiptStatus.PROCESSING.value
            await self.db.commit()

    async def get_receipt_for_user(
        self,
        receipt_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Receipt | None:
        result = await self.db.execute(
            select(Receipt)
            .options(selectinload(Receipt.items), selectinload(Receipt.store))
            .where(Receipt.id == receipt_id, Receipt.user_id == user_id),
        )
        return result.scalar_one_or_none()

    async def list_receipts_for_user(
        self,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        store_id: uuid.UUID | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        status: str | None = None,
    ) -> tuple[list[Receipt], int]:
        offset = (page - 1) * page_size
        filters = [Receipt.user_id == user_id]
        if store_id:
            filters.append(Receipt.store_id == store_id)
        if from_date:
            filters.append(Receipt.purchase_date >= from_date)
        if to_date:
            filters.append(Receipt.purchase_date <= to_date)
        if status:
            filters.append(Receipt.status == status)

        count_result = await self.db.execute(
            select(func.count()).select_from(Receipt).where(*filters),
        )
        total = count_result.scalar_one()

        result = await self.db.execute(
            select(Receipt)
            .options(selectinload(Receipt.store))
            .where(*filters)
            .order_by(Receipt.created_at.desc())
            .offset(offset)
            .limit(page_size),
        )
        return list(result.scalars().all()), total

    async def _get_receipt_by_id(self, receipt_id: uuid.UUID) -> Receipt | None:
        result = await self.db.execute(select(Receipt).where(Receipt.id == receipt_id))
        return result.scalar_one_or_none()

    async def get_receipt_by_id(self, receipt_id: uuid.UUID) -> Receipt | None:
        result = await self.db.execute(
            select(Receipt)
            .options(selectinload(Receipt.items), selectinload(Receipt.store))
            .where(Receipt.id == receipt_id),
        )
        return result.scalar_one_or_none()

    async def get_or_create_store(
        self,
        name: str,
        chain: str | None,
    ) -> Store:
        normalized = normalize_store_name(name)
        result = await self.db.execute(
            select(Store).where(Store.normalized_name == normalized),
        )
        store = result.scalar_one_or_none()
        if store:
            return store

        store = Store(name=name, normalized_name=normalized, chain=chain)
        self.db.add(store)
        await self.db.flush()
        return store

    async def save_parsed_receipt(
        self,
        receipt_id: uuid.UUID,
        raw_ocr_text: str,
        store: Store | None,
        purchase_date: datetime | None,
        total: Decimal | None,
        items: list[dict],
    ) -> Receipt | None:
        receipt = await self._get_receipt_by_id(receipt_id)
        if not receipt:
            return None

        receipt.raw_ocr_text = raw_ocr_text
        receipt.store_id = store.id if store else None
        receipt.purchase_date = purchase_date
        receipt.total = total
        receipt.status = ReceiptStatus.READY_FOR_REVIEW.value

        for item in items:
            self.db.add(
                ReceiptItem(
                    receipt_id=receipt.id,
                    raw_product_name=item["raw_product_name"],
                    quantity=item["quantity"],
                    unit_price=item.get("unit_price"),
                    line_total=item["line_total"],
                ),
            )

        await self.db.commit()
        return receipt

    async def mark_failed(self, receipt_id: uuid.UUID) -> None:
        receipt = await self._get_receipt_by_id(receipt_id)
        if receipt:
            receipt.status = ReceiptStatus.FAILED.value
            await self.db.commit()

    async def confirm_receipt(
        self,
        receipt_id: uuid.UUID,
        user_id: uuid.UUID,
        store_name: str | None,
        purchase_date: datetime | None,
        total: Decimal | None,
        items: list[dict],
    ) -> Receipt | None:
        receipt = await self.get_receipt_for_user(receipt_id, user_id)
        if not receipt:
            return None
        if receipt.status != ReceiptStatus.READY_FOR_REVIEW.value:
            raise ValueError("Receipt is not ready for review")

        if store_name:
            store = await self.get_or_create_store(store_name, None)
            receipt.store_id = store.id
        store = receipt.store

        if purchase_date is not None:
            receipt.purchase_date = purchase_date
        if total is not None:
            receipt.total = total

        await self.db.execute(
            delete(ReceiptItem).where(ReceiptItem.receipt_id == receipt.id),
        )
        await self.db.flush()

        product_service = ProductService(self.db)
        observed_at = receipt.purchase_date or datetime.now(timezone.utc)
        store_id = store.id if store else None

        for item in items:
            product = await product_service.resolve_product(
                item["raw_product_name"],
                store_id,
            )
            receipt_item = ReceiptItem(
                receipt_id=receipt.id,
                product_id=product.id,
                raw_product_name=item["raw_product_name"],
                quantity=item["quantity"],
                unit_price=item.get("unit_price"),
                line_total=item["line_total"],
            )
            self.db.add(receipt_item)
            await self.db.flush()

            if store_id:
                self.db.add(
                    PriceObservation(
                        user_id=user_id,
                        product_id=product.id,
                        store_id=store_id,
                        receipt_item_id=receipt_item.id,
                        price=item["line_total"],
                        observed_at=observed_at,
                    ),
                )

        receipt.status = ReceiptStatus.CONFIRMED.value
        await self.db.commit()
        return await self.get_receipt_for_user(receipt_id, user_id)

    async def delete_receipt(
        self,
        receipt_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        receipt = await self.get_receipt_for_user(receipt_id, user_id)
        if not receipt:
            return False

        item_ids = [item.id for item in receipt.items]
        if item_ids:
            await self.db.execute(
                delete(PriceObservation).where(
                    PriceObservation.receipt_item_id.in_(item_ids),
                ),
            )

        await self.db.delete(receipt)
        await self.db.commit()
        return True

    async def list_stores_for_user(self, user_id: uuid.UUID) -> list[Store]:
        result = await self.db.execute(
            select(Store)
            .join(Receipt, Receipt.store_id == Store.id)
            .where(Receipt.user_id == user_id, Receipt.status == ReceiptStatus.CONFIRMED.value)
            .distinct()
            .order_by(Store.name),
        )
        return list(result.scalars().all())
