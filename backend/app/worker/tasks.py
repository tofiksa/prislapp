import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionLocal
from app.models.receipt import Receipt, ReceiptStatus
from app.parsers import parse_receipt_text
from app.services.ocr_service import OcrService
from app.services.receipt_service import ReceiptService
from app.services.storage_service import StorageService
from app.worker.celery_app import celery_app


async def process_receipt_with_db(receipt_id: str, db: AsyncSession) -> None:
    receipt_uuid = uuid.UUID(receipt_id)
    service = ReceiptService(db)
    result = await db.execute(select(Receipt).where(Receipt.id == receipt_uuid))
    receipt = result.scalar_one_or_none()
    if not receipt:
        return

    receipt.status = ReceiptStatus.PROCESSING.value
    await db.commit()

    try:
        storage = StorageService()
        image_bytes = storage.download_receipt(receipt.image_path)
        raw_text = OcrService().extract_text(image_bytes)
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
        await service.mark_failed(receipt_uuid)


async def _process_receipt_async(receipt_id: str) -> None:
    async with SessionLocal() as db:
        await process_receipt_with_db(receipt_id, db)


@celery_app.task(name="process_receipt")
def process_receipt(receipt_id: str) -> None:
    import asyncio

    asyncio.run(_process_receipt_async(receipt_id))
