from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import Base, engine
from app.routers import auth, health, receipts
from app.services.storage_service import StorageService


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        StorageService().ensure_bucket()
    except Exception:
        pass
    yield


app = FastAPI(title="Prislapp API", version="0.1.0", lifespan=lifespan)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(receipts.router)


@app.get("/")
async def root():
    return {"name": "Prislapp API", "version": "0.1.0"}
