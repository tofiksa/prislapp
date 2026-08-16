from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.receipt import StoreListResponse, StoreResponse
from app.services.receipt_service import ReceiptService

router = APIRouter(prefix="/stores", tags=["stores"])


@router.get("", response_model=StoreListResponse)
async def list_stores(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ReceiptService(db)
    stores = await service.list_stores_for_user(current_user.id)
    return StoreListResponse(
        items=[
            StoreResponse(
                id=str(store.id),
                name=store.name,
                chain=store.chain,
            )
            for store in stores
        ],
    )
