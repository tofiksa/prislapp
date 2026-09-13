"""S05-A: revisjoner av en kvittering, revisjonslinjer og gjeldende prisobservasjoner.

Retting er en revisjon, ikke en usporbar overskriving. `receipt_items` holder
gjeldende linjeverdier for v1-visning, mens `receipt_revision_lines` er det
uforanderlige bildet av hver revisjon. Bare siste bekreftede revisjon har
gjeldende prisobservasjoner.
"""

import enum
import uuid
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.domain.pricing import Condition, DatePrecision, DateSource, LineType, PriceBasis
from app.domain.units import QuantityUnit

COMPARISON_PRICE_TYPE = Numeric(20, 6)


class RevisionStatus(str, enum.Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"


class ReconciliationStatus(str, enum.Enum):
    BALANCED = "balanced"
    # Et avvik en kladd kan bære. Bekreftelse krever at brukeren godtar det
    # eller retter linjene.
    GAP = "gap"
    GAP_ACCEPTED = "gap_accepted"
    # Uten trykt total, eller med uavklarte linjebeløp, finnes ingen uavhengig
    # avstemming. En beregnet total er ikke et bevis på at summen stemmer.
    UNVERIFIABLE = "unverifiable"


class ReceiptOperation(str, enum.Enum):
    DRAFT = "receipt_draft"
    CONFIRM = "receipt_confirm"
    REVISION = "receipt_revision"


class ReceiptRevision(Base):
    __tablename__ = "receipt_revisions"
    __table_args__ = (
        UniqueConstraint("receipt_id", "revision", name="uq_receipt_revisions_number"),
        Index("ix_receipt_revisions_user_receipt", "user_id", "receipt_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    receipt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("receipts.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default=RevisionStatus.DRAFT.value)
    operation: Mapped[str] = mapped_column(String(32))
    # Mutasjonen som skrev denne revisjonen. Selve idempotensnøkkelen bor i
    # `receipt_mutations`, slik at en kladd som overskrives ikke sletter den.
    mutation_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_store_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_stores.id"),
        nullable=True,
    )
    # Kjøpsdatoen hører til revisjonen. Ukjent dato forblir null; opplasting og
    # bekreftelse er aldri skjult kjøpsdato.
    purchase_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    purchase_time: Mapped[time | None] = mapped_column(Time(), nullable=True)
    date_precision: Mapped[str] = mapped_column(
        String(16),
        default=DatePrecision.UNKNOWN.value,
        server_default=DatePrecision.UNKNOWN.value,
    )
    date_source: Mapped[str] = mapped_column(
        String(16),
        default=DateSource.UNKNOWN.value,
        server_default=DateSource.UNKNOWN.value,
    )
    printed_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    computed_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    reconciliation_difference: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )
    reconciliation_status: Mapped[str] = mapped_column(
        String(16),
        default=ReconciliationStatus.UNVERIFIABLE.value,
        server_default=ReconciliationStatus.UNVERIFIABLE.value,
    )
    reconciliation_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    gap_accepted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    lines: Mapped[list["ReceiptRevisionLine"]] = relationship(
        back_populates="revision_row",
        cascade="all, delete-orphan",
    )


class ReceiptRevisionLine(Base):
    """Uforanderlig linjebilde.

    `line_id` er den klientgenererte, stabile linje-ID-en. Den peker ikke på
    `receipt_items`, fordi v1-linjene beholdes urørt som rå avlesning inntil
    klienten bytter til v2.
    """

    __tablename__ = "receipt_revision_lines"
    __table_args__ = (
        UniqueConstraint("revision_id", "line_id", name="uq_receipt_revision_lines_line"),
        Index("ix_receipt_revision_lines_line_id", "line_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    revision_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("receipt_revisions.id"),
        index=True,
    )
    line_id: Mapped[uuid.UUID] = mapped_column()
    position: Mapped[int] = mapped_column(Integer)
    raw_product_name: Mapped[str] = mapped_column(String(512))
    user_product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_products.id"),
        nullable=True,
    )
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    quantity_unit: Mapped[str] = mapped_column(
        String(16),
        default=QuantityUnit.UNKNOWN.value,
    )
    line_type: Mapped[str] = mapped_column(String(16), default=LineType.UNKNOWN.value)
    net_line_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    printed_unit_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    price_basis: Mapped[str] = mapped_column(String(16), default=PriceBasis.UNKNOWN.value)
    condition: Mapped[str] = mapped_column(String(16), default=Condition.UNKNOWN.value)
    # v1-linjer har ingen lest valuta. Null betyr ukjent, ikke NOK.
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    comparison_price: Mapped[Decimal | None] = mapped_column(
        COMPARISON_PRICE_TYPE,
        nullable=True,
    )
    eligible: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    eligible_for_dated_ranking: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="0",
    )
    # Lagret som liste med tekstkoder, slik at grunnen til utelukkelse ikke går
    # tapt når linjen senere rettes.
    exclusion_reasons: Mapped[list] = mapped_column(JSON, default=list)

    revision_row: Mapped["ReceiptRevision"] = relationship(back_populates="lines")


class PriceObservationV2(Base):
    """Privat prisobservasjon knyttet til linje, revisjon og butikk.

    Bare rader med `is_current` hører til gjeldende bekreftede revisjon. Gamle
    revisjoner beholdes som historikk, men publiserer ikke priser.
    """

    __tablename__ = "price_observations_v2"
    __table_args__ = (
        Index(
            "ix_price_observations_v2_current",
            "user_id",
            "user_product_id",
            "is_current",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    user_product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_products.id"),
        index=True,
    )
    user_store_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_stores.id"), index=True)
    receipt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("receipts.id"), index=True)
    revision_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("receipt_revisions.id"),
        index=True,
    )
    line_id: Mapped[uuid.UUID] = mapped_column()
    revision: Mapped[int] = mapped_column(Integer)
    price: Mapped[Decimal] = mapped_column(COMPARISON_PRICE_TYPE)
    price_basis: Mapped[str] = mapped_column(String(16))
    quantity_unit: Mapped[str] = mapped_column(String(16))
    currency: Mapped[str] = mapped_column(String(3), default="NOK")
    purchase_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    date_precision: Mapped[str] = mapped_column(String(16))
    condition: Mapped[str] = mapped_column(String(16))
    quality_status: Mapped[str] = mapped_column(String(24))
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class ReceiptMutation(Base):
    """Idempotensnøkkel `(user_id, operation, mutation_id)` med lagret svar.

    Svaret lagres slik at en retry etter tapt svar får den opprinnelige kroppen,
    også når kontoens prisdataversjon senere har økt av andre grunner.
    """

    __tablename__ = "receipt_mutations"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "operation",
            "mutation_id",
            name="uq_receipt_mutations_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    operation: Mapped[str] = mapped_column(String(32))
    mutation_id: Mapped[uuid.UUID] = mapped_column()
    payload_hash: Mapped[str] = mapped_column(String(64))
    receipt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("receipts.id"), index=True)
    response: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
