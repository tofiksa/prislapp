from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.concurrency import run_in_threadpool

from app.database import engine
from app.errors import ApiError, api_error_handler, request_validation_error_handler
from app.routers import (
    auth,
    health,
    me_v2,
    products,
    receipts,
    receipts_v2,
    shopping_lists_v2,
    stores,
)
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
app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(RequestValidationError, request_validation_error_handler)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(receipts.router)
app.include_router(receipts_v2.router)
app.include_router(products.router)
app.include_router(stores.router)
app.include_router(me_v2.router)
app.include_router(shopping_lists_v2.router)
app.include_router(shopping_lists_v2.sync_router)


@app.get("/")
async def root():
    return {"name": "Prislapp API", "version": "0.1.0"}
