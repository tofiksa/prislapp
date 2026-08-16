import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


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

    receipt: Mapped["Receipt"] = relationship(back_populates="items")  # noqa: F821
