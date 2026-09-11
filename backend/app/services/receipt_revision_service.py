"""S05-A: kladd, bekreftelse og retting av kvitteringer som atomiske revisjoner.

Reglene som styrer modulen:

- `user_id` kommer bare fra autentisering. Fremmed kvittering, butikk eller vare
  gir 404, slik at eierskap ikke lekker.
- Samme `(user_id, operation, mutation_id)` med samme payload gir det lagrede
  svaret. Annet innhold gir 409. `expected_version` som ikke matcher gir 409 med
  gjeldende versjon.
- Bare gjeldende bekreftede revisjon publiserer priser. Ved revisjon N settes
  observasjonene fra N-1 ut av kraft i samme transaksjon som `price_data_version`
  økes.
- Ukjent dato settes aldri fra `now()`. Kvitteringen kan bekreftes med ukjent
  butikk, dato eller identitet; da blir linjene bare ikke rangerbare.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, time, timezone
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.pricing import (
    DateSource,
    LineType,
    PricingLine,
    PricingResult,
    evaluate_line,
)
from app.domain.units import QuantityUnit
from app.errors import ApiError, FieldError, not_found
from app.models.account_ledger import AccountLedger
from app.models.product import PriceObservation
from app.models.receipt import Receipt, ReceiptStatus
from app.models.receipt_item import ReceiptItem
from app.models.receipt_revision import (
    PriceObservationV2,
    ReceiptMutation,
    ReceiptOperation,
    ReceiptRevision,
    ReceiptRevisionLine,
    ReconciliationStatus,
    RevisionStatus,
)
from app.models.user_product import UserProduct
from app.models.user_store import UserStore
from app.schemas.receipt_v2 import (
    ReceiptConfirmV2Request,
    ReceiptDraftRequest,
    decimal_string,
)

# Pant, gebyr, retur og rabattjusteringer inngår i avstemmingen sammen med
# varelinjene. Bare `unknown` holdes utenfor, fordi typen ikke er avklart.
RECONCILED_LINE_TYPES = frozenset(
    {
        LineType.PRODUCT,
        LineType.DEPOSIT,
        LineType.FEE,
        LineType.RETURN,
        LineType.DISCOUNT,
    },
)
RECONCILIATION_TOLERANCE = Decimal("0.01")
NOK_QUANTUM = Decimal("0.01")
COMPARISON_CURRENCY = "NOK"

# `evaluate_line` kjenner ikke butikken. Uten butikk er linjen lagret, men den
# kan ikke rangeres mot andre butikker.
UNKNOWN_STORE_REASON = "unknown_store"

MISSING_PRINTED_TOTAL = "missing_printed_total"
UNRESOLVED_LINE_AMOUNTS = "unresolved_line_amounts"

QUALITY_RANKABLE = "rankable"
QUALITY_RANKABLE_UNDATED = "rankable_undated"


def version_conflict(current_version: int) -> ApiError:
    return ApiError(
        409,
        "VERSION_CONFLICT",
        "Kvitteringen er endret. Hent gjeldende versjon og prøv igjen.",
        [
            FieldError(
                "expected_version",
                "stale_version",
                f"Gjeldende versjon er {current_version}.",
            ),
        ],
        extra={"current_version": current_version},
    )


def mutation_conflict() -> ApiError:
    return ApiError(
        409,
        "MUTATION_CONFLICT",
        "Samme endrings-ID er allerede brukt med et annet innhold.",
        [
            FieldError(
                "mutation_id",
                "payload_mismatch",
                "Bruk en ny endrings-ID for nytt innhold.",
            ),
        ],
    )


def receipt_state_conflict(status: str) -> ApiError:
    return ApiError(
        409,
        "RECEIPT_STATE_CONFLICT",
        "Kvitteringen er ikke i en tilstand som tillater denne handlingen.",
        [FieldError("status", "unexpected_status", f"Gjeldende status er {status}.")],
    )


def reconciliation_gap(difference: Decimal) -> ApiError:
    return ApiError(
        400,
        "RECONCILIATION_GAP",
        "Summen av linjene stemmer ikke med trykt total. Rett linjene eller godta avviket.",
        [
            FieldError(
                "reconciliation",
                "gap_requires_acceptance",
                f"Avviket er {difference} kr.",
            ),
        ],
    )


def duplicate_line_id() -> ApiError:
    return ApiError(
        400,
        "VALIDATION_ERROR",
        "Hver linje må ha en egen ID.",
        [FieldError("lines", "duplicate_line_id", "To linjer har samme ID.")],
    )


@dataclass(frozen=True)
class Reconciliation:
    status: ReconciliationStatus
    printed_total: Decimal | None
    computed_total: Decimal | None
    difference: Decimal | None
    gap_accepted: bool
    reason: str | None

    def as_response(self) -> dict:
        return {
            "status": self.status.value,
            "printed_total": decimal_string(self.printed_total),
            "computed_total": decimal_string(self.computed_total),
            "difference": decimal_string(self.difference),
            "gap_accepted": self.gap_accepted,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class QualifiedLine:
    """En linje med kvalifiseringen som gjelder for den i denne revisjonen."""

    position: int
    result: PricingResult
    exclusion_reasons: tuple[str, ...]
    eligible: bool


def payload_hash(request: ReceiptDraftRequest) -> str:
    """Stabil hash av innholdet, uten selve mutasjons-ID-en."""
    payload = request.model_dump(mode="json", exclude={"mutation_id"})
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def reconcile(
    lines: list,
    printed_total: Decimal | None,
    accept_gap: bool,
    enforce_gap: bool,
) -> Reconciliation:
    """Avstem sum av netto linjebeløp mot trykt total.

    Uten trykt total finnes ingen uavhengig avstemming; den beregnede summen
    merkes og er ikke et bevis på at kvitteringen stemmer. En linje med uavklart
    beløp inngår ikke i summen, men gjør den ufullstendig, og det er nettopp et
    slikt avvik brukeren må forklare eller rette.

    `enforce_gap` gjelder bekreftelse. En kladd lagres også med avvik, ellers
    ville brukeren mistet arbeidet sitt i stedet for å få rette det.
    """
    included = [line for line in lines if line.line_type in RECONCILED_LINE_TYPES]
    unresolved = any(line.net_line_total is None for line in included)
    computed = sum(
        (line.net_line_total for line in included if line.net_line_total is not None),
        Decimal("0"),
    ).quantize(NOK_QUANTUM)
    reason = UNRESOLVED_LINE_AMOUNTS if unresolved else None

    if printed_total is None:
        return Reconciliation(
            status=ReconciliationStatus.UNVERIFIABLE,
            printed_total=None,
            computed_total=computed,
            difference=None,
            gap_accepted=False,
            reason=MISSING_PRINTED_TOTAL,
        )

    difference = (computed - printed_total).quantize(NOK_QUANTUM)
    if abs(difference) <= RECONCILIATION_TOLERANCE:
        status = ReconciliationStatus.BALANCED
    elif accept_gap:
        status = ReconciliationStatus.GAP_ACCEPTED
    elif enforce_gap:
        raise reconciliation_gap(difference)
    else:
        status = ReconciliationStatus.GAP

    return Reconciliation(
        status=status,
        printed_total=printed_total,
        computed_total=computed,
        difference=difference,
        gap_accepted=status is ReconciliationStatus.GAP_ACCEPTED,
        reason=reason,
    )


class ReceiptRevisionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def save_draft(
        self,
        user_id: uuid.UUID,
        receipt_id: uuid.UUID,
        request: ReceiptDraftRequest,
    ) -> dict:
        return await self._apply(
            user_id,
            receipt_id,
            request,
            ReceiptOperation.DRAFT,
            allowed_statuses=(ReceiptStatus.READY_FOR_REVIEW,),
            confirming=False,
            accept_gap=False,
        )

    async def confirm(
        self,
        user_id: uuid.UUID,
        receipt_id: uuid.UUID,
        request: ReceiptConfirmV2Request,
    ) -> dict:
        return await self._apply(
            user_id,
            receipt_id,
            request,
            ReceiptOperation.CONFIRM,
            allowed_statuses=(ReceiptStatus.READY_FOR_REVIEW,),
            confirming=True,
            accept_gap=request.accept_reconciliation_gap,
        )

    async def create_revision(
        self,
        user_id: uuid.UUID,
        receipt_id: uuid.UUID,
        request: ReceiptConfirmV2Request,
    ) -> dict:
        return await self._apply(
            user_id,
            receipt_id,
            request,
            ReceiptOperation.REVISION,
            allowed_statuses=(ReceiptStatus.CONFIRMED,),
            confirming=True,
            accept_gap=request.accept_reconciliation_gap,
        )

    async def _apply(
        self,
        user_id: uuid.UUID,
        receipt_id: uuid.UUID,
        request: ReceiptDraftRequest,
        operation: ReceiptOperation,
        allowed_statuses: tuple[ReceiptStatus, ...],
        confirming: bool,
        accept_gap: bool,
    ) -> dict:
        digest = payload_hash(request)
        await self._lock_mutation(user_id, operation, request.mutation_id)

        replay = await self._replay(
            user_id,
            operation,
            receipt_id,
            request.mutation_id,
            digest,
        )
        if replay is not None:
            return replay

        receipt = await self._owned_receipt(user_id, receipt_id)
        if receipt.status not in {status.value for status in allowed_statuses}:
            raise receipt_state_conflict(receipt.status)
        if request.expected_version != receipt.version:
            raise version_conflict(receipt.version)

        user_store = await self._owned_store(user_id, request.store_id)
        identities = await self._owned_identities(user_id, request)
        self._assert_unique_line_ids(request)

        reconciliation = reconcile(
            request.lines,
            request.printed_total,
            accept_gap,
            enforce_gap=confirming,
        )
        qualified = self._qualify(request, identities, user_store)

        revision_number = receipt.version + 1
        revision = await self._upsert_revision(
            receipt,
            user_id,
            revision_number,
            request,
            operation,
            digest,
            reconciliation,
            confirmed=confirming,
        )
        await self._write_lines(revision, request, qualified)

        price_data_version = await self._price_data_version(user_id)
        if confirming:
            await self._publish_prices(receipt, revision, request, qualified, user_store)
            price_data_version = await self._bump_price_data_version(user_id)
            receipt.version = revision_number
            receipt.status = ReceiptStatus.CONFIRMED.value
            self._apply_receipt_fields(receipt, request)

        response = {
            "receipt_id": str(receipt.id),
            "revision": revision_number,
            "status": revision.status,
            "price_data_version": price_data_version,
            "reconciliation": reconciliation.as_response(),
        }
        self.db.add(
            ReceiptMutation(
                user_id=user_id,
                operation=operation.value,
                mutation_id=request.mutation_id,
                payload_hash=digest,
                receipt_id=receipt.id,
                response=response,
            ),
        )

        try:
            await self.db.commit()
        except IntegrityError:
            # To samtidige forsøk med samme mutasjons-ID: den som mistet kappløpet
            # leverer det lagrede svaret i stedet for å skrive en ny revisjon.
            await self.db.rollback()
            replay = await self._replay(
                user_id,
                operation,
                receipt_id,
                request.mutation_id,
                digest,
            )
            if replay is None:
                raise
            return replay
        return response

    async def _lock_mutation(
        self,
        user_id: uuid.UUID,
        operation: ReceiptOperation,
        mutation_id: uuid.UUID,
    ) -> None:
        """Serialiser samtidige retries av samme mutasjon på tvers av prosesser."""
        if self.db.bind is None or self.db.bind.dialect.name != "postgresql":
            return
        key = hashlib.sha256(
            f"{user_id}:{operation.value}:{mutation_id}".encode(),
        ).digest()[:8]
        await self.db.execute(
            sa.text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": int.from_bytes(key, "big", signed=True)},
        )

    async def _mutation_record(
        self,
        user_id: uuid.UUID,
        operation: ReceiptOperation,
        mutation_id: uuid.UUID,
    ) -> ReceiptMutation | None:
        result = await self.db.execute(
            sa.select(ReceiptMutation).where(
                ReceiptMutation.user_id == user_id,
                ReceiptMutation.operation == operation.value,
                ReceiptMutation.mutation_id == mutation_id,
            ),
        )
        return result.scalar_one_or_none()

    async def _replay(
        self,
        user_id: uuid.UUID,
        operation: ReceiptOperation,
        receipt_id: uuid.UUID,
        mutation_id: uuid.UUID,
        digest: str,
    ) -> dict | None:
        record = await self._mutation_record(user_id, operation, mutation_id)
        if record is None:
            return None
        # Nøkkelen er kontoens, så en gjenbrukt endrings-ID på en annen
        # kvittering er nytt innhold, ikke en retry av det samme.
        if record.payload_hash != digest or record.receipt_id != receipt_id:
            raise mutation_conflict()
        return record.response

    async def _owned_receipt(self, user_id: uuid.UUID, receipt_id: uuid.UUID) -> Receipt:
        result = await self.db.execute(
            sa.select(Receipt).where(Receipt.id == receipt_id, Receipt.user_id == user_id),
        )
        receipt = result.scalar_one_or_none()
        if receipt is None:
            raise not_found()
        return receipt

    async def _owned_store(
        self,
        user_id: uuid.UUID,
        store_id: uuid.UUID | None,
    ) -> UserStore | None:
        if store_id is None:
            return None
        result = await self.db.execute(
            sa.select(UserStore).where(UserStore.id == store_id, UserStore.user_id == user_id),
        )
        store = result.scalar_one_or_none()
        if store is None:
            raise not_found()
        return store

    async def _owned_identities(
        self,
        user_id: uuid.UUID,
        request: ReceiptDraftRequest,
    ) -> dict[uuid.UUID, UserProduct]:
        wanted = {line.user_product_id for line in request.lines if line.user_product_id}
        if not wanted:
            return {}
        result = await self.db.execute(
            sa.select(UserProduct).where(
                UserProduct.id.in_(wanted),
                UserProduct.user_id == user_id,
            ),
        )
        owned = {product.id: product for product in result.scalars().all()}
        if len(owned) != len(wanted):
            # En annen eiers vare-ID i request body gir samme svar som ukjent ID.
            raise not_found()
        return owned

    @staticmethod
    def _assert_unique_line_ids(request: ReceiptDraftRequest) -> None:
        line_ids = [line.id for line in request.lines]
        if len(set(line_ids)) != len(line_ids):
            raise duplicate_line_id()

    def _qualify(
        self,
        request: ReceiptDraftRequest,
        identities: dict[uuid.UUID, UserProduct],
        user_store: UserStore | None,
    ) -> list[QualifiedLine]:
        qualified: list[QualifiedLine] = []
        for position, line in enumerate(request.lines):
            identity = identities.get(line.user_product_id) if line.user_product_id else None
            result = evaluate_line(
                PricingLine(
                    line_type=line.line_type,
                    currency=COMPARISON_CURRENCY,
                    quantity=line.quantity,
                    quantity_unit=line.quantity_unit,
                    net_line_total=line.net_line_total,
                    printed_unit_price=line.printed_unit_price,
                    condition=line.condition,
                    user_product_id=line.user_product_id,
                    identity_status=identity.identity_status if identity else None,
                    date_precision=request.date_precision,
                    pack_content=identity.pack_content if identity else None,
                    pack_unit=(
                        QuantityUnit(identity.pack_unit)
                        if identity
                        else QuantityUnit.UNKNOWN
                    ),
                ),
            )
            reasons = [reason.value for reason in result.exclusion_reasons]
            if user_store is None:
                reasons.append(UNKNOWN_STORE_REASON)
            qualified.append(
                QualifiedLine(
                    position=position,
                    result=result,
                    exclusion_reasons=tuple(reasons),
                    eligible=result.eligible and user_store is not None,
                ),
            )
        return qualified

    async def _upsert_revision(
        self,
        receipt: Receipt,
        user_id: uuid.UUID,
        revision_number: int,
        request: ReceiptDraftRequest,
        operation: ReceiptOperation,
        digest: str,
        reconciliation: Reconciliation,
        confirmed: bool,
    ) -> ReceiptRevision:
        """Kladden på gjeldende revisjonsnummer gjenbrukes; bekreftede rader røres ikke."""
        result = await self.db.execute(
            sa.select(ReceiptRevision).where(
                ReceiptRevision.receipt_id == receipt.id,
                ReceiptRevision.revision == revision_number,
                ReceiptRevision.status == RevisionStatus.DRAFT.value,
            ),
        )
        revision = result.scalar_one_or_none()
        if revision is None:
            revision = ReceiptRevision(
                receipt_id=receipt.id,
                user_id=user_id,
                revision=revision_number,
            )
            self.db.add(revision)
        else:
            await self.db.execute(
                sa.delete(ReceiptRevisionLine).where(
                    ReceiptRevisionLine.revision_id == revision.id,
                ),
            )

        revision.status = (
            RevisionStatus.CONFIRMED.value if confirmed else RevisionStatus.DRAFT.value
        )
        revision.operation = operation.value
        revision.mutation_id = request.mutation_id
        revision.payload_hash = digest
        revision.user_store_id = request.store_id
        revision.purchase_date = request.purchase_date
        revision.purchase_time = request.purchase_time
        revision.date_precision = request.date_precision.value
        # Klienten sender en verdi brukeren eller OCR har lest, aldri en gjettet dato.
        revision.date_source = (
            DateSource.USER.value
            if request.purchase_date is not None
            else DateSource.UNKNOWN.value
        )
        revision.printed_total = reconciliation.printed_total
        revision.computed_total = reconciliation.computed_total
        revision.reconciliation_difference = reconciliation.difference
        revision.reconciliation_status = reconciliation.status.value
        revision.reconciliation_reason = reconciliation.reason
        revision.gap_accepted = reconciliation.gap_accepted
        revision.confirmed_at = datetime.now(timezone.utc) if confirmed else None
        await self.db.flush()
        return revision

    async def _write_lines(
        self,
        revision: ReceiptRevision,
        request: ReceiptDraftRequest,
        qualified: list[QualifiedLine],
    ) -> None:
        for line, qualification in zip(request.lines, qualified):
            self.db.add(
                ReceiptRevisionLine(
                    revision_id=revision.id,
                    line_id=line.id,
                    position=qualification.position,
                    raw_product_name=line.raw_product_name,
                    user_product_id=line.user_product_id,
                    quantity=line.quantity,
                    quantity_unit=line.quantity_unit.value,
                    line_type=line.line_type.value,
                    net_line_total=line.net_line_total,
                    printed_unit_price=line.printed_unit_price,
                    price_basis=qualification.result.price_basis.value,
                    condition=line.condition.value,
                    currency=COMPARISON_CURRENCY,
                    comparison_price=qualification.result.comparison_price,
                    eligible=qualification.eligible,
                    eligible_for_dated_ranking=(
                        qualification.result.eligible_for_dated_ranking
                        and qualification.eligible
                    ),
                    exclusion_reasons=list(qualification.exclusion_reasons),
                ),
            )
        await self.db.flush()

    async def _publish_prices(
        self,
        receipt: Receipt,
        revision: ReceiptRevision,
        request: ReceiptDraftRequest,
        qualified: list[QualifiedLine],
        user_store: UserStore | None,
    ) -> None:
        """Sett forrige revisjons observasjoner ut av kraft og skriv de nye."""
        await self.db.execute(
            sa.update(PriceObservationV2)
            .where(
                PriceObservationV2.receipt_id == receipt.id,
                PriceObservationV2.is_current.is_(True),
            )
            .values(is_current=False),
        )
        # v1-observasjonene er avledet av den gamle bekreftelsen. De ville ellers
        # stått igjen som et gjeldende, feil minimum etter en retting.
        await self.db.execute(
            sa.delete(PriceObservation).where(
                PriceObservation.receipt_item_id.in_(
                    sa.select(ReceiptItem.id).where(ReceiptItem.receipt_id == receipt.id),
                ),
            ),
        )

        if user_store is None:
            return

        for line, qualification in zip(request.lines, qualified):
            if not qualification.eligible or qualification.result.comparison_price is None:
                continue
            self.db.add(
                PriceObservationV2(
                    user_id=receipt.user_id,
                    user_product_id=line.user_product_id,
                    user_store_id=user_store.id,
                    receipt_id=receipt.id,
                    revision_id=revision.id,
                    line_id=line.id,
                    revision=revision.revision,
                    price=qualification.result.comparison_price,
                    price_basis=qualification.result.price_basis.value,
                    quantity_unit=line.quantity_unit.value,
                    currency=COMPARISON_CURRENCY,
                    purchase_date=request.purchase_date,
                    date_precision=request.date_precision.value,
                    condition=line.condition.value,
                    quality_status=(
                        QUALITY_RANKABLE
                        if qualification.result.eligible_for_dated_ranking
                        else QUALITY_RANKABLE_UNDATED
                    ),
                    is_current=True,
                ),
            )
        await self.db.flush()

    @staticmethod
    def _apply_receipt_fields(receipt: Receipt, request: ReceiptDraftRequest) -> None:
        """Speil bekreftede datofelter og trykt total på kvitteringen.

        Ukjent dato forblir null. Midnatt er ingen oppgradering til kjent
        klokkeslett; det er `date_precision` som bærer presisjonen.
        """
        if request.purchase_date is None:
            receipt.purchase_date = None
            receipt.purchase_time = None
        else:
            receipt.purchase_date = datetime.combine(
                request.purchase_date,
                request.purchase_time or time.min,
                tzinfo=timezone.utc,
            )
            receipt.purchase_time = request.purchase_time
        receipt.date_precision = request.date_precision.value
        # Klienten sender en dato brukeren har bekreftet eller rettet. OCR-kilde
        # settes av S05-B, som eier parserproveniensen.
        receipt.date_source = (
            DateSource.USER.value
            if request.purchase_date is not None
            else DateSource.UNKNOWN.value
        )
        if request.printed_total is not None:
            # Uten trykt total står den gamle avlesningen igjen på v1-raden.
            # Revisjonen bærer at totalen ikke er avklart; rågrunnlaget slettes ikke.
            receipt.total = request.printed_total

    async def _ledger(self, user_id: uuid.UUID) -> AccountLedger:
        result = await self.db.execute(
            sa.select(AccountLedger).where(AccountLedger.user_id == user_id),
        )
        ledger = result.scalar_one_or_none()
        if ledger is None:
            ledger = AccountLedger(user_id=user_id, price_data_version=1)
            self.db.add(ledger)
            await self.db.flush()
        return ledger

    async def _price_data_version(self, user_id: uuid.UUID) -> int:
        return (await self._ledger(user_id)).price_data_version

    async def _bump_price_data_version(self, user_id: uuid.UUID) -> int:
        ledger = await self._ledger(user_id)
        ledger.price_data_version += 1
        ledger.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return ledger.price_data_version
