import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
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


class IdentityStatus(str, enum.Enum):
    CONFIRMED = "confirmed"
    UNRESOLVED = "unresolved"
    INHERITED = "inherited"


class AliasSource(str, enum.Enum):
    OCR = "ocr"
    USER = "user"
    BACKFILL = "backfill"


class AliasMatchMethod(str, enum.Enum):
    EXACT = "exact"
    USER_CONFIRMED = "user_confirmed"
    INHERITED = "inherited"


class UserProduct(Base):
    """Privat vareidentitet. Eierens fasit; global `products` er bare kompatibilitetslag."""

    __tablename__ = "user_products"
    __table_args__ = (
        UniqueConstraint("user_id", "legacy_product_id", name="uq_user_products_legacy"),
        Index("ix_user_products_user_display_name", "user_id", "display_name"),
        Index("ix_user_products_user_last_purchased_at", "user_id", "last_purchased_at"),
        Index("ix_user_products_user_purchase_count", "user_id", "purchase_count"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    legacy_product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id"),
        nullable=True,
    )
    display_name: Mapped[str] = mapped_column(String(512))
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    variant: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pack_content: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    pack_unit: Mapped[str] = mapped_column(String(16), default="unknown")
    pack_count: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    identity_status: Mapped[str] = mapped_column(
        String(16),
        default=IdentityStatus.UNRESOLVED.value,
    )
    # Avledet av eierens egne bekreftede linjer, lagret for stabil cursor-sortering.
    last_purchased_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    purchase_count: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    aliases: Mapped[list["UserProductAlias"]] = relationship(  # noqa: F821
        back_populates="user_product",
        cascade="all, delete-orphan",
    )


class UserProductAlias(Base):
    """Privat varetekst. Original tekst bevares, og den deles aldri med andre eiere."""

    __tablename__ = "user_product_aliases"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "normalized_text",
            "context_key",
            name="uq_user_product_aliases_context",
        ),
        Index("ix_user_product_aliases_user_text", "user_id", "normalized_text"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    user_product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_products.id"),
        index=True,
    )
    normalized_text: Mapped[str] = mapped_column(String(512))
    raw_text: Mapped[str | None] = mapped_column(String(512), nullable=True)
    store_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("stores.id"),
        nullable=True,
    )
    chain: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # NULL er ikke lik NULL i en unik nøkkel, så butikk-/kjedekonteksten
    # materialiseres her for at duplikater faktisk skal avvises.
    context_key: Mapped[str] = mapped_column(String(64), default="")
    source: Mapped[str] = mapped_column(String(16))
    match_method: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    user_product: Mapped["UserProduct"] = relationship(back_populates="aliases")  # noqa: F821


def alias_context_key(store_id: uuid.UUID | None, chain: str | None) -> str:
    """Butikk slår kjede; uten begge deler er aliaset kontekstfritt."""
    if store_id is not None:
        return f"store:{store_id}"
    if chain:
        return f"chain:{chain.strip().lower()}"
    return ""
