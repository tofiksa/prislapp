import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ReceiptStatus(str, enum.Enum):
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"


class Receipt(Base):
    __tablename__ = "receipts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    store_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("stores.id"),
        nullable=True,
    )
    purchase_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    total: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=ReceiptStatus.UPLOADED.value)
    image_path: Mapped[str] = mapped_column(String(512))
    image_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    raw_ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    store: Mapped["Store | None"] = relationship(back_populates="receipts")  # noqa: F821
    items: Mapped[list["ReceiptItem"]] = relationship(  # noqa: F821
        back_populates="receipt",
        cascade="all, delete-orphan",
    )
