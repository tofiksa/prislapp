"""Prisobservasjoner lest for flere private varer om gangen.

S04-B leser én vare, S07-A leser hele handlelisten. Begge trenger den samme
oversettelsen fra lagrede rader til `Observation`, og den bor derfor her. Antall
varer endrer bare IN-listen, ikke antall spørringer: uten dette ville en liste
på 100 linjer blitt 100 prisoppslag.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.price_history import BRANCH_IDENTITY, Observation, RankingExclusion, Source
from app.domain.pricing import DatePrecision, ExclusionReason
from app.models.receipt import Receipt, ReceiptStatus
from app.models.receipt_revision import (
    PriceObservationV2,
    ReceiptRevision,
    ReceiptRevisionLine,
    RevisionStatus,
)
from app.models.user_store import UserStore

CONDITIONAL = ExclusionReason.CONDITIONAL.value
UNKNOWN_DATE = ExclusionReason.UNKNOWN_DATE.value

Grouped = dict[uuid.UUID, list[Observation]]


def line_reasons(
    line: ReceiptRevisionLine,
    include_conditional: bool,
) -> tuple[str, ...]:
    """Linjens egne grunner, med vilkårsfilteret anvendt.

    `include_conditional` slår bare av `conditional`. Ukjent rabatt, enhet,
    identitet eller vilkår er fortsatt ikke rangerbart, uansett filter.
    """
    reasons = tuple(line.exclusion_reasons or ())
    if include_conditional and line.comparison_price is not None:
        reasons = tuple(reason for reason in reasons if reason != CONDITIONAL)
    return reasons


def ranking_reasons(
    line_reasons: tuple[str, ...],
    purchase_date,
    date_precision: str,
    store_identity: str | None,
) -> tuple[str, ...]:
    reasons = [reason for reason in line_reasons if reason != UNKNOWN_DATE]
    if purchase_date is None or date_precision == DatePrecision.UNKNOWN.value:
        reasons.append(UNKNOWN_DATE)
    if store_identity != BRANCH_IDENTITY:
        # Kjede uten filial og ukjent butikk er ikke sammenlignbare butikker.
        reasons.append(RankingExclusion.STORE_NOT_BRANCH.value)
    return tuple(reasons)


class PriceObservationLoader:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def observations(
        self,
        user_id: uuid.UUID,
        product_ids: list[uuid.UUID],
        include_conditional: bool,
    ) -> Grouped:
        """Hele grunnlaget per vare: publiserte priser og utelukket historikk.

        Linje-ID-en er bare unik innenfor sin revisjon, så revisjonen må være
        med i nøkkelen. Ellers ville to kvitteringer med samme linje-ID blitt
        ett kjøp, og det ene kjøpet forsvunnet ut av historikken.
        """
        published = await self.published(user_id, product_ids)
        seen = {
            (row.source.revision_id, row.source.line_id)
            for rows in published.values()
            for row in rows
        }
        unpublished = await self.unpublished(user_id, product_ids, include_conditional)

        grouped: Grouped = {key: list(rows) for key, rows in published.items()}
        for product_id, rows in unpublished.items():
            grouped.setdefault(product_id, []).extend(
                row
                for row in rows
                if (row.source.revision_id, row.source.line_id) not in seen
            )
        return grouped

    async def published(
        self,
        user_id: uuid.UUID,
        product_ids: list[uuid.UUID],
    ) -> Grouped:
        """Gjeldende, kvalifiserte observasjoner for alle varene i ett oppslag."""
        if not product_ids:
            return {}

        result = await self.db.execute(
            sa.select(PriceObservationV2, UserStore, ReceiptRevision.purchase_time)
            .join(UserStore, UserStore.id == PriceObservationV2.user_store_id)
            .join(ReceiptRevision, ReceiptRevision.id == PriceObservationV2.revision_id)
            .where(
                PriceObservationV2.user_id == user_id,
                PriceObservationV2.user_product_id.in_(product_ids),
                PriceObservationV2.is_current.is_(True),
            ),
        )

        grouped: Grouped = {}
        for observation, store, purchase_time in result.all():
            grouped.setdefault(observation.user_product_id, []).append(
                Observation(
                    row_id=observation.id,
                    price=observation.price,
                    price_basis=observation.price_basis,
                    purchase_date=observation.purchase_date,
                    date_precision=observation.date_precision,
                    purchase_time=purchase_time,
                    store_id=store.id,
                    store_name=store.display_name,
                    store_identity=store.identity_level,
                    condition=observation.condition,
                    source=Source(
                        receipt_id=observation.receipt_id,
                        revision_id=observation.revision_id,
                        revision=observation.revision,
                        line_id=observation.line_id,
                    ),
                    reasons=ranking_reasons(
                        (),
                        observation.purchase_date,
                        observation.date_precision,
                        store.identity_level,
                    ),
                ),
            )
        return grouped

    async def unpublished(
        self,
        user_id: uuid.UUID,
        product_ids: list[uuid.UUID],
        include_conditional: bool,
    ) -> Grouped:
        """Linjer på gjeldende revisjon som ikke ble kvalifisert til pris."""
        if not product_ids:
            return {}

        result = await self.db.execute(
            sa.select(ReceiptRevisionLine, ReceiptRevision, UserStore)
            .join(ReceiptRevision, ReceiptRevision.id == ReceiptRevisionLine.revision_id)
            .join(Receipt, Receipt.id == ReceiptRevision.receipt_id)
            .outerjoin(UserStore, UserStore.id == ReceiptRevision.user_store_id)
            .where(
                ReceiptRevision.user_id == user_id,
                ReceiptRevisionLine.user_product_id.in_(product_ids),
                ReceiptRevision.status == RevisionStatus.CONFIRMED.value,
                Receipt.status == ReceiptStatus.CONFIRMED.value,
                # Bare gjeldende revisjon; en rettet linje er ikke lenger et faktum.
                Receipt.version == ReceiptRevision.revision,
            ),
        )

        grouped: Grouped = {}
        for line, revision, store in result.all():
            grouped.setdefault(line.user_product_id, []).append(
                Observation(
                    row_id=line.id,
                    price=line.comparison_price,
                    price_basis=line.price_basis,
                    purchase_date=revision.purchase_date,
                    date_precision=revision.date_precision,
                    purchase_time=revision.purchase_time,
                    store_id=store.id if store else None,
                    store_name=store.display_name if store else None,
                    store_identity=store.identity_level if store else None,
                    condition=line.condition,
                    source=Source(
                        receipt_id=revision.receipt_id,
                        revision_id=revision.id,
                        revision=revision.revision,
                        line_id=line.line_id,
                    ),
                    reasons=ranking_reasons(
                        line_reasons(line, include_conditional),
                        revision.purchase_date,
                        revision.date_precision,
                        store.identity_level if store else None,
                    ),
                ),
            )
        return grouped
