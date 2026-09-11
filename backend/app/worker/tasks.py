import uuid
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionLocal, engine
from app.parsers import parse_receipt_text
from app.services.ocr_outbox import (
    claim_ocr_job,
    complete_ocr_result,
    enqueue_ocr_job,
    fail_ocr_job,
    reconcile_job_outbox,
)
from app.services.ocr_service import OcrService
from app.services.receipt_service import ReceiptService
from app.services.storage_service import StorageService
from app.worker.celery_app import celery_app


def _is_permanent_ocr_error(exc: BaseException) -> bool:
    return isinstance(exc, ValueError) and "No readable text" in str(exc)


def _error_code(exc: BaseException) -> str:
    if _is_permanent_ocr_error(exc):
        return "EMPTY_OCR"
    name = type(exc).__name__
    if "timeout" in name.lower() or "connection" in name.lower():
        return "STORAGE_ERROR"
    return "OCR_FAILED"


async def process_receipt_with_db(receipt_id: str, db: AsyncSession) -> None:
    receipt_uuid = uuid.UUID(receipt_id)
    claimed = await claim_ocr_job(db, receipt_uuid)
    if claimed is None:
        from app.models.receipt import Receipt, ReceiptStatus

        receipt = await db.get(Receipt, receipt_uuid)
        if receipt is None or receipt.status != ReceiptStatus.UPLOADED.value:
            return
        await enqueue_ocr_job(db, receipt.user_id, receipt.id)
        await db.commit()
        claimed = await claim_ocr_job(db, receipt_uuid)
        if claimed is None:
            return

    service = ReceiptService(db)
    try:
        storage = StorageService()
        image_bytes = storage.download_receipt(claimed.image_path)
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

        await complete_ocr_result(
            db,
            receipt_uuid,
            claimed.attempt_id,
            raw_text,
            store,
            parsed.purchase_date,
            parsed.total,
            items,
        )
    except Exception as exc:
        logging.getLogger(__name__).exception("Receipt processing failed: %s", receipt_uuid)
        await db.rollback()
        await fail_ocr_job(
            db,
            receipt_uuid,
            claimed.attempt_id,
            _error_code(exc),
            permanent=_is_permanent_ocr_error(exc),
        )


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


@celery_app.task(name="reconcile_job_outbox")
def reconcile_job_outbox_task() -> int:
    import asyncio

    async def run() -> int:
        try:
            async with SessionLocal() as db:
                return await reconcile_job_outbox(db)
        finally:
            await engine.dispose()

    return asyncio.run(run())


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
