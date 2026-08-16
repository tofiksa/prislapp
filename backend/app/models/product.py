import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    canonical_name: Mapped[str] = mapped_column(String(512))
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ean: Mapped[str | None] = mapped_column(String(32), nullable=True)

    aliases: Mapped[list["ProductAlias"]] = relationship(  # noqa: F821
        back_populates="product",
        cascade="all, delete-orphan",
    )


class ProductAlias(Base):
    __tablename__ = "product_aliases"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), index=True)
    alias_name: Mapped[str] = mapped_column(String(512), index=True)
    store_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("stores.id"),
        nullable=True,
    )

    product: Mapped["Product"] = relationship(back_populates="aliases")  # noqa: F821


class PriceObservation(Base):
    __tablename__ = "price_observations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), index=True)
    store_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stores.id"), index=True)
    receipt_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("receipt_items.id"),
        index=True,
    )
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
