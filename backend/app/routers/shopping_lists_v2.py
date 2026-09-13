"""S06-A: /v2/shopping-lists og /v2/sync.

Arkivering skjer via `status`, sletting via `deleted` i PATCH. Begge er
mutasjoner med `mutation_id` og `expected_version`, slik at en retry uten nett
ikke gir to effekter.
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.shopping_list import (
    ShoppingListCollectionResponse,
    ShoppingListCopyRequest,
    ShoppingListCreateRequest,
    ShoppingListFromReceiptRequest,
    ShoppingListItemCreateRequest,
    ShoppingListItemPatchRequest,
    ShoppingListItemResponse,
    ShoppingListPatchRequest,
    ShoppingListResponse,
    SyncRequest,
    SyncResponseBody,
)
from app.schemas.shopping_list_price_summary import ShoppingListPriceSummaryResponse
from app.services.shopping_list_price_summary_service import (
    ShoppingListPriceSummaryService,
)
from app.services.shopping_list_service import ShoppingListService

router = APIRouter(prefix="/v2/shopping-lists", tags=["shopping-lists"])
sync_router = APIRouter(prefix="/v2", tags=["shopping-lists"])


@router.post("", response_model=ShoppingListResponse, status_code=201)
async def create_shopping_list(
    body: ShoppingListCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await ShoppingListService(db).create_list(current_user.id, body)


@router.get("", response_model=ShoppingListCollectionResponse)
async def list_shopping_lists(
    cursor: str | None = Query(None),
    limit: int | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, next_cursor = await ShoppingListService(db).list_lists(
        current_user.id,
        cursor=cursor,
        limit=limit,
    )
    return ShoppingListCollectionResponse(items=items, next_cursor=next_cursor)


@router.post("/from-receipt", response_model=ShoppingListResponse, status_code=201)
async def create_shopping_list_from_receipt(
    body: ShoppingListFromReceiptRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await ShoppingListService(db).create_list_from_receipt(current_user.id, body)


@router.get("/{list_id}", response_model=ShoppingListResponse)
async def get_shopping_list(
    list_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await ShoppingListService(db).get_list(current_user.id, list_id)


@router.get("/{list_id}/price-summary", response_model=ShoppingListPriceSummaryResponse)
async def get_shopping_list_price_summary(
    list_id: uuid.UUID,
    include_conditional: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await ShoppingListPriceSummaryService(db).get_price_summary(
        current_user.id,
        list_id,
        include_conditional=include_conditional,
    )


@router.patch("/{list_id}", response_model=ShoppingListResponse)
async def patch_shopping_list(
    list_id: uuid.UUID,
    body: ShoppingListPatchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await ShoppingListService(db).patch_list(current_user.id, list_id, body)


@router.post("/{list_id}/copy", response_model=ShoppingListResponse, status_code=201)
async def copy_shopping_list(
    list_id: uuid.UUID,
    body: ShoppingListCopyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await ShoppingListService(db).copy_list(current_user.id, list_id, body)


@router.post("/{list_id}/items", response_model=ShoppingListItemResponse, status_code=201)
async def add_shopping_list_item(
    list_id: uuid.UUID,
    body: ShoppingListItemCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await ShoppingListService(db).create_item(current_user.id, list_id, body)


@router.patch("/{list_id}/items/{item_id}", response_model=ShoppingListItemResponse)
async def patch_shopping_list_item(
    list_id: uuid.UUID,
    item_id: uuid.UUID,
    body: ShoppingListItemPatchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await ShoppingListService(db).patch_item(current_user.id, list_id, item_id, body)


@sync_router.post("/sync", response_model=SyncResponseBody)
async def sync_shopping_lists(
    body: SyncRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await ShoppingListService(db).sync(current_user.id, body)
