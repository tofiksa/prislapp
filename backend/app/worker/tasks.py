import uuid
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionLocal, engine
from app.models.receipt import Receipt, ReceiptStatus
from app.parsers import parse_receipt_text
from app.services.ocr_service import OcrService
from app.services.receipt_service import ReceiptService
from app.services.storage_service import StorageService
from app.worker.celery_app import celery_app


async def process_receipt_with_db(receipt_id: str, db: AsyncSession) -> None:
    receipt_uuid = uuid.UUID(receipt_id)
    service = ReceiptService(db)
    result = await db.execute(select(Receipt).where(Receipt.id == receipt_uuid).with_for_update())
    receipt = result.scalar_one_or_none()
    if not receipt or receipt.status != ReceiptStatus.UPLOADED.value:
        return

    receipt.status = ReceiptStatus.PROCESSING.value
    await db.flush()

    try:
        storage = StorageService()
        image_bytes = storage.download_receipt(receipt.image_path)
        raw_text = OcrService().extract_text(image_bytes)
        if not raw_text.strip():
            raise ValueError("No readable text in receipt image")
        parsed = parse_receipt_text(raw_text)

        store = None
        if parsed.store_name:
            store = await service.get_or_create_store(parsed.store_name, parsed.store_chain)

        items = [
            {
                "raw_product_name": item.raw_name,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "line_total": item.line_total,
            }
            for item in parsed.items
        ]

        await service.save_parsed_receipt(
            receipt_uuid,
            raw_text,
            store,
            parsed.purchase_date,
            parsed.total,
            items,
        )
    except Exception:
        logging.getLogger(__name__).exception("Receipt processing failed: %s", receipt_uuid)
        await db.rollback()
        await service.mark_failed(receipt_uuid)


async def _process_receipt_async(receipt_id: str) -> None:
    try:
        async with SessionLocal() as db:
            await process_receipt_with_db(receipt_id, db)
    finally:
        await engine.dispose()


@celery_app.task(name="process_receipt", acks_late=True, reject_on_worker_lost=True)
def process_receipt(receipt_id: str) -> None:
    import asyncio

    asyncio.run(_process_receipt_async(receipt_id))


@celery_app.task(name="delete_expired_images")
def delete_expired_images() -> int:
    import asyncio

    async def cleanup():
        try:
            async with SessionLocal() as db:
                return await ReceiptService(db).delete_expired_images()
        finally:
            await engine.dispose()

    return asyncio.run(cleanup())
