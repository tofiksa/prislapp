import uuid
from datetime import datetime, timezone
from io import BytesIO

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Response, UploadFile, status
from PIL import Image, UnidentifiedImageError
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.receipt import Receipt, ReceiptStatus
from app.schemas.receipt import (
    ReceiptConfirmRequest,
    ReceiptDetailResponse,
    ReceiptItemResponse,
    ReceiptListResponse,
    ReceiptSummaryResponse,
    ReceiptUploadResponse,
    StoreResponse,
)
from app.services.receipt_service import ReceiptService
from app.services.storage_service import StorageService
from app.worker.tasks import process_receipt

router = APIRouter(prefix="/receipts", tags=["receipts"])


def _to_summary(receipt) -> ReceiptSummaryResponse:
    store = None
    if receipt.store:
        store = StoreResponse(
            id=str(receipt.store.id),
            name=receipt.store.name,
            chain=receipt.store.chain,
        )
    return ReceiptSummaryResponse(
        id=str(receipt.id),
        status=receipt.status,
        total=receipt.total,
        purchase_date=receipt.purchase_date,
        store=store,
        created_at=receipt.created_at,
    )


def _to_detail(receipt) -> ReceiptDetailResponse:
    summary = _to_summary(receipt)
    items = [
        ReceiptItemResponse(
            id=str(item.id),
            raw_product_name=item.raw_product_name,
            quantity=item.quantity,
            unit_price=item.unit_price,
            line_total=item.line_total,
        )
        for item in receipt.items
    ]
    return ReceiptDetailResponse(
        **summary.model_dump(),
        raw_ocr_text=receipt.raw_ocr_text,
        items=items,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ReceiptUploadResponse)
async def upload_receipt(
    file: UploadFile = File(...),
    idempotency_key: uuid.UUID | None = Header(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an image",
        )

    image_bytes = await file.read(20 * 1024 * 1024 + 1)
    if len(image_bytes) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image exceeds 20 MB")
    if not image_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file",
        )

    try:
        with Image.open(BytesIO(image_bytes)) as image:
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise HTTPException(status_code=400, detail="Invalid image") from exc

    service = ReceiptService(db)
    if idempotency_key:
        # Serialize concurrent retries for the same capture across API processes.
        if db.bind.dialect.name == "postgresql":
            lock_key = int.from_bytes(idempotency_key.bytes[:8], "big", signed=True)
            await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
        existing = await db.get(Receipt, idempotency_key)
        if existing:
            if existing.user_id != current_user.id:
                raise HTTPException(status_code=409, detail="Capture ID already used")
            if existing.status == ReceiptStatus.UPLOADED.value:
                await run_in_threadpool(process_receipt.delay, str(existing.id))
            return ReceiptUploadResponse(id=str(existing.id), status=existing.status)
    receipt = await service.create_receipt(
        current_user,
        image_bytes,
        file.content_type or "image/jpeg",
        receipt_id=idempotency_key,
    )
    await run_in_threadpool(process_receipt.delay, str(receipt.id))

    return ReceiptUploadResponse(id=str(receipt.id), status=receipt.status)


@router.get("", response_model=ReceiptListResponse)
async def list_receipts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    store_id: uuid.UUID | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    status: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ReceiptService(db)
    receipts, total = await service.list_receipts_for_user(
        current_user.id,
        page=page,
        page_size=page_size,
        store_id=store_id,
        from_date=from_date,
        to_date=to_date,
        status=status,
    )
    return ReceiptListResponse(
        items=[_to_summary(r) for r in receipts],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{receipt_id}", response_model=ReceiptDetailResponse)
async def get_receipt(
    receipt_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ReceiptService(db)
    receipt = await service.get_receipt_for_user(
        receipt_id,
        current_user.id,
    )
    if not receipt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receipt not found")
    return _to_detail(receipt)


@router.get("/{receipt_id}/image")
async def get_receipt_image(
    receipt_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    receipt = await ReceiptService(db).get_receipt_for_user(receipt_id, current_user.id)
    if not receipt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receipt not found")
    expires = receipt.image_expires_at.replace(tzinfo=timezone.utc) if receipt.image_expires_at.tzinfo is None else receipt.image_expires_at
    if not receipt.image_path or expires <= datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Original image expired")
    data = await run_in_threadpool(StorageService().download_receipt, receipt.image_path)
    return Response(content=data, media_type="image/jpeg")


@router.put("/{receipt_id}/confirm", response_model=ReceiptDetailResponse)
async def confirm_receipt(
    receipt_id: uuid.UUID,
    body: ReceiptConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ReceiptService(db)
    try:
        receipt = await service.confirm_receipt(
            receipt_id,
            current_user.id,
            body.store_name,
            body.purchase_date,
            body.total,
            [item.model_dump() for item in body.items],
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if not receipt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receipt not found")
    return _to_detail(receipt)


@router.delete("/{receipt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_receipt(
    receipt_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ReceiptService(db)
    deleted = await service.delete_receipt(receipt_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receipt not found")


@router.post("/{receipt_id}/retry", response_model=ReceiptUploadResponse)
async def retry_receipt(
    receipt_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    receipt = await ReceiptService(db).get_receipt_for_user(receipt_id, current_user.id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    if receipt.status != ReceiptStatus.FAILED.value:
        raise HTTPException(status_code=409, detail="Only failed receipts can be retried")
    expires = receipt.image_expires_at.replace(tzinfo=timezone.utc) if receipt.image_expires_at.tzinfo is None else receipt.image_expires_at
    if not receipt.image_path or expires <= datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Original image expired; capture it again")
    receipt.status = ReceiptStatus.UPLOADED.value
    await db.commit()
    await run_in_threadpool(process_receipt.delay, str(receipt.id))
    return ReceiptUploadResponse(id=str(receipt.id), status=receipt.status)
