import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class StoreIdentityLevel(str, enum.Enum):
    BRANCH = "branch"
    CHAIN_ONLY = "chain_only"
    UNKNOWN = "unknown"


class UserStore(Base):
    """Privat butikk. Normalisert navn alene er ikke bevis på at filialen er kjent."""

    __tablename__ = "user_stores"
    __table_args__ = (
        UniqueConstraint("user_id", "legacy_store_id", name="uq_user_stores_legacy"),
        Index("ix_user_stores_user_display_name", "user_id", "display_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    legacy_store_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("stores.id"),
        nullable=True,
    )
    display_name: Mapped[str] = mapped_column(String(255))
    chain: Mapped[str | None] = mapped_column(String(64), nullable=True)
    branch_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    identity_level: Mapped[str] = mapped_column(
        String(16),
        default=StoreIdentityLevel.UNKNOWN.value,
    )
    # Privat butikktekst fra OCR. Deles aldri med et kuratert butikkregister.
    raw_ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
