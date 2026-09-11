"""Responsmodeller for GET /v2/shopping-lists/{id}/price-summary.

Hver linje har en status. En vare uten sammenlignbar pris får `null` og en
konkret grunn, aldri `"0.00"`, fordi null kroner er en påstand om pris.
"""

from __future__ import annotations

from pydantic import BaseModel


class SummaryLowestResponse(BaseModel):
    amount: str
    # ID-en, ikke bare navnet: to butikker kan hete det samme, og S07-C må kunne
    # gruppere per butikk uten å sammenligne tekst.
    store_id: str
    store_name: str
    identity_level: str
    purchase_date: str
    age_label: str
    price_basis: str
    disclaimer: str


class PriceSummaryLineResponse(BaseModel):
    item_id: str
    product_id: str | None = None
    free_text: str | None = None
    quantity: str
    quantity_unit: str
    status: str
    reason: str | None = None
    historical_lowest: SummaryLowestResponse | None = None
    # Antall butikker linjen faktisk kan sammenlignes over. 1 er et ærlig svar,
    # ikke en sammenligning.
    eligible_store_count: int


class ShoppingListPriceSummaryResponse(BaseModel):
    list_id: str
    # `version` dekker bare listens egne felter. En cache må nøkle på
    # `content_revision`, som endres av enhver linjeendring.
    list_version: int
    content_revision: int
    price_data_version: int
    calculated_at: str
    policy_version: str
    include_conditional: bool
    lines: list[PriceSummaryLineResponse]
