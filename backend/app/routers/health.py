from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import check_minio, check_postgres

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    postgres_ok = await check_postgres(db)
    minio_ok = check_minio()
    status_value = "ok" if postgres_ok and minio_ok else "degraded"
    return {
        "status": status_value,
        "postgres": "ok" if postgres_ok else "error",
        "minio": "ok" if minio_ok else "error",
    }
