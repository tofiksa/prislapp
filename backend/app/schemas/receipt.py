from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


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


class OcrExtractionSummary(BaseModel):
    quality: str | None = None
    pipeline_version: str | None = None
    store_chain: str | None = None
    store_state: str | None = None
    total_state: str | None = None
    computed_items_total: Decimal | None = None
    warnings: list[str] = Field(default_factory=list)


class ReceiptDetailResponse(ReceiptSummaryResponse):
    raw_ocr_text: str | None
    items: list[ReceiptItemResponse] = Field(default_factory=list)
    extraction: OcrExtractionSummary | None = None


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
    raw_product_name: str = Field(min_length=1, max_length=512)
    quantity: Decimal = Field(gt=0, max_digits=10, decimal_places=3)
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    line_total: Decimal = Field(ge=0, max_digits=10, decimal_places=2)

    @field_validator("raw_product_name")
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Product name cannot be blank")
        return value.strip()


class ReceiptConfirmRequest(BaseModel):
    store_name: str | None = Field(default=None, max_length=255)
    purchase_date: datetime | None = None
    total: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    items: list[ReceiptConfirmItem] = Field(min_length=1, max_length=500)


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
