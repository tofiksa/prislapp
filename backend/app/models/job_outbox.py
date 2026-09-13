"""S10-B: transaksjonell outbox for OCR-jobber. Ikke listemutasjoner."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class JobOutboxStatus(str, enum.Enum):
    PENDING = "pending"
    PUBLISHED = "published"
    PROCESSING = "processing"
    DONE = "done"
    FAILED_PERMANENT = "failed_permanent"


class JobAggregateType(str, enum.Enum):
    RECEIPT = "receipt"


class JobType(str, enum.Enum):
    OCR_PROCESS = "ocr_process"


class JobOutbox(Base):
    __tablename__ = "job_outbox"
    __table_args__ = (
        Index("ix_job_outbox_user_id", "user_id"),
        Index("ix_job_outbox_status_created_at", "status", "created_at"),
        Index(
            "uq_job_outbox_active_ocr",
            "job_type",
            "aggregate_id",
            unique=True,
            sqlite_where=text("status NOT IN ('done', 'failed_permanent')"),
            postgresql_where=text("status NOT IN ('done', 'failed_permanent')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    aggregate_type: Mapped[str] = mapped_column(String(32))
    aggregate_id: Mapped[uuid.UUID] = mapped_column()
    job_type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(
        String(32),
        default=JobOutboxStatus.PENDING.value,
        server_default=JobOutboxStatus.PENDING.value,
    )
    attempt_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
