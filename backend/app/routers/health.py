from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import check_minio, check_postgres
from app.errors import not_ready
from app.services.ocr_outbox import check_readiness

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    return {"status": "ok"}


@router.get("/ready")
async def ready_check(db: AsyncSession = Depends(get_db)):
    postgres_ok = await check_postgres(db)
    if not postgres_ok:
        raise not_ready()
    if not check_minio():
        raise not_ready()
    if not await check_readiness(db):
        raise not_ready()
    return {"status": "ok"}
