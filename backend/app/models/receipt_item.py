import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.domain.pricing import Condition, LineType, PriceBasis
from app.domain.units import QuantityUnit


class ReceiptItem(Base):
    __tablename__ = "receipt_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    receipt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("receipts.id"), index=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id"),
        nullable=True,
    )
    raw_product_name: Mapped[str] = mapped_column(String(512))
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3), default=Decimal("1"))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    line_total: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    line_type: Mapped[str] = mapped_column(
        String(16),
        default=LineType.UNKNOWN.value,
        server_default=LineType.UNKNOWN.value,
    )
    # Beløpet som faktisk inngår i prisobservasjonen. Null til rabattfordelingen
    # er avklart; `line_total` er fortsatt den rå avlesningen.
    net_line_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    # Lest enhetspris fra kvitteringen, ikke fasit for beregningen.
    printed_unit_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    quantity_unit: Mapped[str] = mapped_column(
        String(16),
        default=QuantityUnit.UNKNOWN.value,
        server_default=QuantityUnit.UNKNOWN.value,
    )
    price_basis: Mapped[str] = mapped_column(
        String(16),
        default=PriceBasis.UNKNOWN.value,
        server_default=PriceBasis.UNKNOWN.value,
    )
    condition: Mapped[str] = mapped_column(
        String(16),
        default=Condition.UNKNOWN.value,
        server_default=Condition.UNKNOWN.value,
    )

    receipt: Mapped["Receipt"] = relationship(back_populates="items")  # noqa: F821
