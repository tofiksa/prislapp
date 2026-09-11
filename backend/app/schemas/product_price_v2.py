"""Responsmodeller for GET /v2/me/products/{id}/prices.

Beløp er desimalstrenger avrundet på visningsgrensen, aldri JSON-tall.
`historical_lowest` og `latest_by_store` er to forskjellige påstander og deler
derfor ikke felt.
"""

from __future__ import annotations

from pydantic import BaseModel


class SourceRefResponse(BaseModel):
    """Kvitteringen et kjøp kan åpnes fra, også når kjøpet er utelukket."""

    receipt_id: str
    revision_id: str
    revision: int
    line_id: str


class TiedStoreResponse(BaseModel):
    store_id: str
    name: str
    identity_level: str
    purchase_date: str


class HistoricalLowestResponse(BaseModel):
    amount: str
    purchase_date: str
    store_id: str
    store_name: str
    store_identity: str
    condition: str
    age_label: str
    disclaimer: str
    source: SourceRefResponse
    tied_stores: list[TiedStoreResponse]


class AmountRangeResponse(BaseModel):
    min: str
    max: str


class LatestStorePriceResponse(BaseModel):
    """`certainty` skiller et sikkert siste kjøp fra samme-dags-usikkerhet.

    Ved `same_day_uncertain` er `amount` null og `amount_range` satt: vi vet hva
    varen kostet den dagen, men ikke hvilket av kjøpene som var det siste.
    """

    store_id: str
    store_name: str
    identity_level: str
    certainty: str
    amount: str | None = None
    amount_range: AmountRangeResponse | None = None
    purchase_date: str
    condition: str | None = None
    observation_count: int
    age_label: str
    disclaimer: str
    sources: list[SourceRefResponse]


class PriceHistoryItemResponse(BaseModel):
    amount: str | None = None
    price_basis: str
    purchase_date: str | None = None
    date_precision: str
    store_id: str | None = None
    store_name: str | None = None
    identity_level: str | None = None
    condition: str
    age_label: str | None = None
    ranked: bool
    exclusion_reasons: list[str]
    source: SourceRefResponse


class PriceHistoryResponse(BaseModel):
    items: list[PriceHistoryItemResponse]
    # Hele grunnlaget, ikke bare den returnerte siden.
    total_count: int


class ProductPriceResponse(BaseModel):
    product_id: str
    display_name: str
    brand: str | None = None
    variant: str | None = None
    pack_content: str | None = None
    pack_unit: str
    pack_count: str | None = None
    currency: str
    price_basis: str
    # Kontoens cachenøkkel: endret versjon betyr at pris-cachen er foreldet.
    price_data_version: int
    include_conditional: bool
    # Uthenting er ikke et nytt kjøp, så «hentet» står ved siden av «kjøpt».
    calculated_at: str
    historical_lowest: HistoricalLowestResponse | None = None
    latest_by_store: list[LatestStorePriceResponse]
    eligible_store_count: int
    excluded_observation_count: int
    excluded_reasons: dict[str, int]
    history: PriceHistoryResponse
    next_cursor: str | None = None
