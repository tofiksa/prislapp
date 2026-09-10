from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool

from app.database import engine
from app.routers import auth, health, products, receipts, stores
from app.services.storage_service import StorageService


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await run_in_threadpool(StorageService().ensure_bucket)
    except Exception:
        logging.getLogger(__name__).exception("Unable to initialize receipt storage")
    yield
    await engine.dispose()


app = FastAPI(title="Prislapp API", version="0.1.0", lifespan=lifespan)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(receipts.router)
app.include_router(products.router)
app.include_router(stores.router)


@app.get("/")
async def root():
    return {"name": "Prislapp API", "version": "0.1.0"}
