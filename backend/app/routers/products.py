import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.receipt import ProductSearchResponse, ProductSummaryResponse
from app.services.product_price_service import ProductPriceService

router = APIRouter(prefix="/products", tags=["products"])


@router.get("/search", response_model=ProductSearchResponse)
async def search_products(
    q: str = Query(..., min_length=1),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ProductPriceService(db)
    products = await service.search_products(current_user.id, q)
    return ProductSearchResponse(
        items=[
            ProductSummaryResponse(
                id=str(product.id),
                canonical_name=product.canonical_name,
                category=product.category,
            )
            for product in products
        ],
    )


@router.get("/{product_id}/my-prices")
async def get_my_prices(
    product_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ProductPriceService(db)
    result = await service.get_my_prices(current_user.id, uuid.UUID(product_id))
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return result
