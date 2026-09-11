import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.errors import not_found
from app.models.user import User
from app.schemas.v2 import (
    UserProductListResponse,
    UserProductResponse,
    UserStoreListResponse,
    UserStoreResponse,
)
from app.services.private_catalog_service import PrivateCatalogService

router = APIRouter(prefix="/v2/me", tags=["me"])


@router.get("/products", response_model=UserProductListResponse)
async def list_my_products(
    q: str | None = Query(None),
    sort: str = Query("recent"),
    cursor: str | None = Query(None),
    limit: int | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    products, next_cursor = await PrivateCatalogService(db).list_products(
        current_user.id,
        query=q,
        sort=sort,
        cursor=cursor,
        limit=limit,
    )
    return UserProductListResponse(
        items=[UserProductResponse.from_model(product) for product in products],
        next_cursor=next_cursor,
    )


@router.get("/products/{product_id}", response_model=UserProductResponse)
async def get_my_product(
    product_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        parsed_id = uuid.UUID(product_id)
    except ValueError as exc:
        raise not_found() from exc

    product = await PrivateCatalogService(db).get_product(current_user.id, parsed_id)
    if product is None:
        # Fremmed eier og ukjent ID gir samme svar.
        raise not_found()
    return UserProductResponse.from_model(product)


@router.get("/stores", response_model=UserStoreListResponse)
async def list_my_stores(
    cursor: str | None = Query(None),
    limit: int | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stores, next_cursor = await PrivateCatalogService(db).list_stores(
        current_user.id,
        cursor=cursor,
        limit=limit,
    )
    return UserStoreListResponse(
        items=[UserStoreResponse.from_model(store) for store in stores],
        next_cursor=next_cursor,
    )
