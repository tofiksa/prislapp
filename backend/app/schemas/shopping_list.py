"""Request- og responsmodeller for /v2/shopping-lists og /v2/sync.

Mengder er desimalstrenger. Mutasjoner sender eksplisitte feltverdier, aldri en
«toggle», slik at en retry ikke krysser av og på igjen.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from app.domain.units import QuantityUnit
from app.models.shopping_list import ShoppingListStatus
from app.schemas.v2 import DecimalString

MAX_MUTATIONS_PER_SYNC = 500


class ShoppingListCreateRequest(BaseModel):
    mutation_id: uuid.UUID
    # Klientgenerert ID gjør at listen kan opprettes offline og synkes senere.
    id: uuid.UUID | None = None
    name: str = Field(max_length=255)


class ShoppingListPatchRequest(BaseModel):
    """Arkivering skjer via `status`, sletting via `deleted`."""

    mutation_id: uuid.UUID
    expected_version: int = Field(ge=0)
    name: str | None = Field(default=None, max_length=255)
    status: ShoppingListStatus | None = None
    deleted: bool | None = None


class ShoppingListCopyRequest(BaseModel):
    mutation_id: uuid.UUID
    id: uuid.UUID | None = None
    name: str | None = Field(default=None, max_length=255)
    unchecked_only: bool = False


class ShoppingListFromReceiptRequest(BaseModel):
    receipt_id: uuid.UUID
    mutation_id: uuid.UUID
    id: uuid.UUID | None = None
    name: str | None = Field(default=None, max_length=255)


class ShoppingListItemCreateRequest(BaseModel):
    mutation_id: uuid.UUID
    id: uuid.UUID | None = None
    user_product_id: uuid.UUID | None = None
    free_text: str | None = Field(default=None, max_length=255)
    quantity: DecimalString
    quantity_unit: QuantityUnit
    checked: bool = False
    # Uten posisjon havner linjen sist blant de aktive linjene.
    position: int | None = Field(default=None, ge=0)


class ShoppingListItemPatchRequest(BaseModel):
    """Mengde, avkryssing, posisjon og sletting settes eksplisitt, aldri som toggle."""

    mutation_id: uuid.UUID
    expected_version: int = Field(ge=0)
    quantity: DecimalString | None = None
    quantity_unit: QuantityUnit | None = None
    checked: bool | None = None
    position: int | None = Field(default=None, ge=0)
    deleted: bool | None = None


class SyncListCreate(ShoppingListCreateRequest):
    operation: Literal["list_create"]


class SyncListPatch(ShoppingListPatchRequest):
    operation: Literal["list_patch"]
    list_id: uuid.UUID


class SyncItemCreate(ShoppingListItemCreateRequest):
    operation: Literal["item_create"]
    list_id: uuid.UUID


class SyncItemPatch(ShoppingListItemPatchRequest):
    operation: Literal["item_patch"]
    list_id: uuid.UUID
    item_id: uuid.UUID


SyncMutation = Annotated[
    Union[SyncListCreate, SyncListPatch, SyncItemCreate, SyncItemPatch],
    Field(discriminator="operation"),
]


class SyncRequest(BaseModel):
    """`cursor: null` betyr at klienten ber om et fullt snapshot."""

    cursor: str | None = None
    mutations: list[SyncMutation] = Field(
        default_factory=list,
        max_length=MAX_MUTATIONS_PER_SYNC,
    )


class ShoppingListItemResponse(BaseModel):
    id: str
    user_product_id: str | None = None
    free_text: str | None = None
    quantity: str
    quantity_unit: str
    checked: bool
    position: int
    version: int
    deleted: bool = False


class ShoppingListResponse(BaseModel):
    id: str
    name: str
    status: str
    version: int
    deleted: bool = False
    # Endres av enhver endring på listen eller linjene. Avledet prising må bruke
    # denne, ikke `version`, som cachenøkkel.
    content_revision: int
    created_at: str
    updated_at: str
    items: list[ShoppingListItemResponse]


class ShoppingListCollectionResponse(BaseModel):
    items: list[ShoppingListResponse]
    next_cursor: str | None = None


class SyncConflictResponse(BaseModel):
    """Mutasjonen er ikke utført. `local` er det klienten sendte."""

    operation: str
    mutation_id: str
    code: str
    message: str
    field_errors: list[dict] = Field(default_factory=list)
    local: dict | None = None
    server: dict | None = None


class SyncResponseBody(BaseModel):
    """Ved `full_snapshot` er linjene komplette; ellers er de bare de endrede."""

    cursor: str
    price_data_version: int
    full_snapshot: bool = False
    # Tom inntil S03-B kan slå sammen private produkter.
    replaced_product_ids: list[dict] = Field(default_factory=list)
    lists: list[ShoppingListResponse]
    conflicts: list[SyncConflictResponse]
