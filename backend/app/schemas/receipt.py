from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ReceiptItemResponse(BaseModel):
    id: str
    raw_product_name: str
    quantity: Decimal
    unit_price: Decimal | None
    line_total: Decimal

    model_config = {"from_attributes": True}


class StoreResponse(BaseModel):
    id: str
    name: str
    chain: str | None

    model_config = {"from_attributes": True}


class ReceiptSummaryResponse(BaseModel):
    id: str
    status: str
    total: Decimal | None
    purchase_date: datetime | None
    store: StoreResponse | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReceiptDetailResponse(ReceiptSummaryResponse):
    raw_ocr_text: str | None
    items: list[ReceiptItemResponse] = Field(default_factory=list)


class ReceiptListResponse(BaseModel):
    items: list[ReceiptSummaryResponse]
    total: int
    page: int
    page_size: int


class ReceiptUploadResponse(BaseModel):
    id: str
    status: str


class ReceiptConfirmItem(BaseModel):
    id: str | None = None
    raw_product_name: str
    quantity: Decimal
    unit_price: Decimal | None = None
    line_total: Decimal


class ReceiptConfirmRequest(BaseModel):
    store_name: str | None = None
    purchase_date: datetime | None = None
    total: Decimal | None = None
    items: list[ReceiptConfirmItem]


class ProductSummaryResponse(BaseModel):
    id: str
    canonical_name: str
    category: str | None = None

    model_config = {"from_attributes": True}


class ProductSearchResponse(BaseModel):
    items: list[ProductSummaryResponse]


class PriceObservationResponse(BaseModel):
    store: StoreResponse
    price: Decimal
    observed_at: datetime

    model_config = {"from_attributes": True}


class LatestStorePriceResponse(BaseModel):
    store: StoreResponse
    price: Decimal
    observed_at: datetime


class ProductPricesResponse(BaseModel):
    product: ProductSummaryResponse
    cheapest: PriceObservationResponse | None
    observations: list[PriceObservationResponse]
    latest_by_store: list[LatestStorePriceResponse]


class StoreListResponse(BaseModel):
    items: list[StoreResponse]
