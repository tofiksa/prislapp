"""S06-A: handlelister, listelinjer, egen idempotensnøkkel og synksekvens.

Sletting er en slettemarkør (`deleted_at`), ikke en fjernet rad. En klient som
har vært uten nett må få vite at raden er borte, ellers ville den lagt den inn
igjen ved neste sync.

`content_seq` er kontoens synsekvens for siste endring på listen *eller* en av
linjene. Den brukes til inkrementell sync og som innholdsrevisjon for avledet
prising, mens `version` bare teller listens egne felter. To tellere fordi en
linjeendring ikke skal gjøre et offline navnebytte til en konflikt, samtidig som
en gammel prissum ikke skal kunne knyttes til et nytt vareutvalg.
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.domain.units import QuantityUnit

# Ønsket mengde har inntil tre desimaler, som andre mengder i domenet.
QUANTITY_TYPE = Numeric(12, 3)


class ShoppingListStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class ShoppingListOperation(str, enum.Enum):
    """Egne operasjoner. Kvitteringsnøklene bor i `receipt_mutations`."""

    LIST_CREATE = "list_create"
    LIST_PATCH = "list_patch"
    ITEM_CREATE = "item_create"
    ITEM_PATCH = "item_patch"


class ShoppingList(Base):
    __tablename__ = "shopping_lists"
    __table_args__ = (
        Index("ix_shopping_lists_user_content_seq", "user_id", "content_seq"),
        Index("ix_shopping_lists_user_created_at", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(
        String(16),
        default=ShoppingListStatus.ACTIVE.value,
        server_default=ShoppingListStatus.ACTIVE.value,
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    content_seq: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    # Slettemarkøren beholdes i minst 90 dager, slik at sync kan fortelle en
    # klient som har vært offline at listen er borte.
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    items: Mapped[list["ShoppingListItem"]] = relationship(
        back_populates="shopping_list",
        cascade="all, delete-orphan",
    )


class ShoppingListItem(Base):
    """Én listelinje: privat vare *eller* fritekst, aldri begge.

    Fritekst slås ikke sammen med et kjent produkt. «Melk» brukeren skrev selv
    er ikke bevis for at det er den registrerte melken.
    """

    __tablename__ = "shopping_list_items"
    __table_args__ = (
        Index("ix_shopping_list_items_user_sync_seq", "user_id", "sync_seq"),
        Index("ix_shopping_list_items_list_position", "list_id", "position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Eieren gjentas her, slik at private oppslag ikke må gå via listen.
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    list_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shopping_lists.id"), index=True)
    user_product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_products.id"),
        nullable=True,
    )
    free_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(QUANTITY_TYPE)
    quantity_unit: Mapped[str] = mapped_column(
        String(16),
        default=QuantityUnit.UNKNOWN.value,
        server_default=QuantityUnit.UNKNOWN.value,
    )
    checked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    position: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    sync_seq: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    shopping_list: Mapped["ShoppingList"] = relationship(back_populates="items")


class ShoppingListMutation(Base):
    """Idempotensnøkkel `(user_id, operation, mutation_id)` med lagret svar.

    Egen tabell og eget operasjonsenum, slik at en listemutasjon aldri kan
    kollidere med en kvitteringsmutasjon.
    """

    __tablename__ = "shopping_list_mutations"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "operation",
            "mutation_id",
            name="uq_shopping_list_mutations_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    operation: Mapped[str] = mapped_column(String(32))
    mutation_id: Mapped[uuid.UUID] = mapped_column()
    # Hashen dekker både innholdet og ressursen mutasjonen peker på, slik at en
    # gjenbrukt endrings-ID på en annen liste er nytt innhold, ikke en retry.
    payload_hash: Mapped[str] = mapped_column(String(64))
    list_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("shopping_lists.id"),
        nullable=True,
        index=True,
    )
    item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("shopping_list_items.id"),
        nullable=True,
    )
    response: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class ShoppingListSyncState(Base):
    """Kontoens monotone synsekvens. Den er uavhengig av `price_data_version`."""

    __tablename__ = "shopping_list_sync_state"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
