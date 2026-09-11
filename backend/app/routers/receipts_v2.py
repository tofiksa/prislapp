"""S05-A: /v2/receipts — kladd, bekreftelse og retting som revisjoner.

`PUT /receipts/{id}/confirm` (v1) beholdes uendret til klienten bytter.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.receipt_v2 import (
    ReceiptConfirmV2Request,
    ReceiptDraftRequest,
    ReceiptRevisionResponse,
)
from app.services.receipt_revision_service import ReceiptRevisionService

router = APIRouter(prefix="/v2/receipts", tags=["receipts"])


@router.put("/{receipt_id}/draft", response_model=ReceiptRevisionResponse)
async def put_receipt_draft(
    receipt_id: uuid.UUID,
    body: ReceiptDraftRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await ReceiptRevisionService(db).save_draft(current_user.id, receipt_id, body)


@router.post("/{receipt_id}/confirm", response_model=ReceiptRevisionResponse)
async def confirm_receipt_v2(
    receipt_id: uuid.UUID,
    body: ReceiptConfirmV2Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await ReceiptRevisionService(db).confirm(current_user.id, receipt_id, body)


@router.post("/{receipt_id}/revisions", response_model=ReceiptRevisionResponse)
async def create_receipt_revision(
    receipt_id: uuid.UUID,
    body: ReceiptConfirmV2Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await ReceiptRevisionService(db).create_revision(current_user.id, receipt_id, body)
