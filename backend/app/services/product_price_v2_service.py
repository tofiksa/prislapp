"""S04-B: eierens prisoppslag for én privat vare.

Grunnlaget er gjeldende prisobservasjoner (`price_observations_v2` med
`is_current`). Linjene på samme gjeldende revisjon som ikke ble publisert, tas
med som utelukket historikk med grunn og kildehenvisning — et kjøp som ikke
kan rangeres, skal fortsatt kunne ses og forklares.

Oppsummeringene regnes over hele grunnlaget. Pagineringen gjelder bare
historikklisten, slik at side to ikke endrer hva minimumet er.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.money import display_nok
from app.domain.pricing import DatePrecision, ExclusionReason
from app.domain.price_history import (
    BRANCH_IDENTITY,
    PRICE_DISCLAIMER,
    Lowest,
    Observation,
    RankingExclusion,
    Source,
    StoreLatest,
    age_label,
    apply_price_basis,
    historical_lowest,
    latest_per_store,
    oslo_today,
)
from app.errors import not_found
from app.models.account_ledger import AccountLedger
from app.models.receipt import Receipt, ReceiptStatus
from app.models.receipt_revision import (
    PriceObservationV2,
    ReceiptRevision,
    ReceiptRevisionLine,
    RevisionStatus,
)
from app.models.user_product import UserProduct
from app.models.user_store import UserStore
from app.schemas.product_price_v2 import (
    AmountRangeResponse,
    HistoricalLowestResponse,
    LatestStorePriceResponse,
    PriceHistoryItemResponse,
    PriceHistoryResponse,
    ProductPriceResponse,
    SourceRefResponse,
    TiedStoreResponse,
)
from app.schemas.v2 import decimal_string
from app.services.pagination import decode_cursor, encode_cursor, page_size
from app.services.private_catalog_service import PrivateCatalogService

COMPARISON_CURRENCY = "NOK"
DEFAULT_PRICE_DATA_VERSION = 1
HISTORY_SCOPE = "product_prices:history"
# Ukjent dato sorteres sist uten å bli gjort om til en dato.
UNDATED_SORT_KEY = ""

CONDITIONAL = ExclusionReason.CONDITIONAL.value
UNKNOWN_DATE = ExclusionReason.UNKNOWN_DATE.value


class ProductPriceV2Service:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_product_prices(
        self,
        user_id: uuid.UUID,
        product_id: uuid.UUID,
        include_conditional: bool = False,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> ProductPriceResponse:
        product = await self._owned_product(user_id, product_id)
        today = oslo_today()

        observations = await self._observations(user_id, product_id, include_conditional)
        price_basis, observations = apply_price_basis(observations)
        rankable = [row for row in observations if row.ranked]

        lowest = historical_lowest(rankable)
        excluded = [row for row in observations if not row.ranked]
        page, next_cursor = self._page(observations, cursor, limit)

        return ProductPriceResponse(
            product_id=str(product.id),
            display_name=product.display_name,
            brand=product.brand,
            variant=product.variant,
            pack_content=decimal_string(product.pack_content),
            pack_unit=product.pack_unit,
            pack_count=decimal_string(product.pack_count),
            currency=COMPARISON_CURRENCY,
            price_basis=price_basis,
            price_data_version=await self._price_data_version(user_id),
            include_conditional=include_conditional,
            calculated_at=datetime.now(timezone.utc).isoformat(),
            historical_lowest=self._lowest_response(lowest, today),
            latest_by_store=[
                self._latest_response(row, today) for row in latest_per_store(rankable)
            ],
            eligible_store_count=len({row.store_id for row in rankable}),
            excluded_observation_count=len(excluded),
            excluded_reasons=self._reason_counts(excluded),
            history=self._history(page, len(observations), today),
            next_cursor=next_cursor,
        )

    async def _owned_product(
        self,
        user_id: uuid.UUID,
        product_id: uuid.UUID,
    ) -> UserProduct:
        product = await PrivateCatalogService(self.db).get_product(user_id, product_id)
        if product is None:
            # Fremmed eier og ukjent ID gir samme svar.
            raise not_found()
        return product

    async def _price_data_version(self, user_id: uuid.UUID) -> int:
        """Leser kontoens versjon. Et oppslag skriver aldri en ny hovedbok."""
        result = await self.db.execute(
            sa.select(AccountLedger.price_data_version).where(
                AccountLedger.user_id == user_id,
            ),
        )
        version = result.scalar_one_or_none()
        # Uten hovedbok finnes ingen prisdata ennå, og versjonen starter på 1.
        return DEFAULT_PRICE_DATA_VERSION if version is None else version

    async def _observations(
        self,
        user_id: uuid.UUID,
        product_id: uuid.UUID,
        include_conditional: bool,
    ) -> list[Observation]:
        published = await self._published(user_id, product_id)
        # Linje-ID-en er bare unik innenfor sin revisjon, så revisjonen må være
        # med i nøkkelen. Ellers ville to kvitteringer med samme linje-ID blitt
        # ett kjøp, og det ene kjøpet forsvunnet ut av historikken.
        seen = {(row.source.revision_id, row.source.line_id) for row in published}
        unpublished = await self._unpublished(user_id, product_id, include_conditional)
        return published + [
            row
            for row in unpublished
            if (row.source.revision_id, row.source.line_id) not in seen
        ]

    async def _published(
        self,
        user_id: uuid.UUID,
        product_id: uuid.UUID,
    ) -> list[Observation]:
        """Gjeldende, kvalifiserte observasjoner fra siste bekreftede revisjon."""
        result = await self.db.execute(
            sa.select(PriceObservationV2, UserStore, ReceiptRevision.purchase_time)
            .join(UserStore, UserStore.id == PriceObservationV2.user_store_id)
            .join(ReceiptRevision, ReceiptRevision.id == PriceObservationV2.revision_id)
            .where(
                PriceObservationV2.user_id == user_id,
                PriceObservationV2.user_product_id == product_id,
                PriceObservationV2.is_current.is_(True),
            ),
        )
        return [
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
                reasons=self._ranking_reasons(
                    (),
                    observation.purchase_date,
                    observation.date_precision,
                    store.identity_level,
                ),
            )
            for observation, store, purchase_time in result.all()
        ]

    async def _unpublished(
        self,
        user_id: uuid.UUID,
        product_id: uuid.UUID,
        include_conditional: bool,
    ) -> list[Observation]:
        """Linjer på gjeldende revisjon som ikke ble kvalifisert til pris."""
        result = await self.db.execute(
            sa.select(ReceiptRevisionLine, ReceiptRevision, UserStore)
            .join(ReceiptRevision, ReceiptRevision.id == ReceiptRevisionLine.revision_id)
            .join(Receipt, Receipt.id == ReceiptRevision.receipt_id)
            .outerjoin(UserStore, UserStore.id == ReceiptRevision.user_store_id)
            .where(
                ReceiptRevision.user_id == user_id,
                ReceiptRevisionLine.user_product_id == product_id,
                ReceiptRevision.status == RevisionStatus.CONFIRMED.value,
                Receipt.status == ReceiptStatus.CONFIRMED.value,
                # Bare gjeldende revisjon; en rettet linje er ikke lenger et faktum.
                Receipt.version == ReceiptRevision.revision,
            ),
        )
        return [
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
                reasons=self._ranking_reasons(
                    self._line_reasons(line, include_conditional),
                    revision.purchase_date,
                    revision.date_precision,
                    store.identity_level if store else None,
                ),
            )
            for line, revision, store in result.all()
        ]

    @staticmethod
    def _line_reasons(
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

    @staticmethod
    def _ranking_reasons(
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

    @staticmethod
    def _reason_counts(excluded: list[Observation]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in excluded:
            for reason in row.reasons:
                counts[reason] = counts.get(reason, 0) + 1
        return counts

    @staticmethod
    def _source(source: Source) -> SourceRefResponse:
        return SourceRefResponse(
            receipt_id=str(source.receipt_id),
            revision_id=str(source.revision_id),
            revision=source.revision,
            line_id=str(source.line_id),
        )

    def _lowest_response(
        self,
        lowest: Lowest | None,
        today,
    ) -> HistoricalLowestResponse | None:
        if lowest is None:
            # Ingen kvalifiserte observasjoner er et ærlig svar, ikke null kroner.
            return None
        primary = lowest.primary
        return HistoricalLowestResponse(
            amount=display_nok(lowest.price),
            purchase_date=primary.purchase_date.isoformat(),
            store_id=str(primary.store_id),
            store_name=primary.store_name,
            store_identity=primary.store_identity,
            condition=primary.condition,
            age_label=age_label(primary.purchase_date, today),
            disclaimer=PRICE_DISCLAIMER,
            source=self._source(primary.source),
            tied_stores=[
                TiedStoreResponse(
                    store_id=str(row.store_id),
                    name=row.store_name,
                    identity_level=row.store_identity,
                    purchase_date=row.purchase_date.isoformat(),
                )
                for row in lowest.tied
            ],
        )

    def _latest_response(self, latest: StoreLatest, today) -> LatestStorePriceResponse:
        return LatestStorePriceResponse(
            store_id=str(latest.store_id),
            store_name=latest.store_name,
            identity_level=latest.store_identity,
            certainty=latest.certainty.value,
            amount=None if latest.price is None else display_nok(latest.price),
            amount_range=(
                None
                if latest.price_range is None
                else AmountRangeResponse(
                    min=display_nok(latest.price_range[0]),
                    max=display_nok(latest.price_range[1]),
                )
            ),
            purchase_date=latest.purchase_date.isoformat(),
            condition=latest.condition,
            observation_count=latest.observation_count,
            age_label=age_label(latest.purchase_date, today),
            disclaimer=PRICE_DISCLAIMER,
            sources=[self._source(source) for source in latest.sources],
        )

    def _history(
        self,
        page: list[Observation],
        total_count: int,
        today,
    ) -> PriceHistoryResponse:
        return PriceHistoryResponse(
            items=[
                PriceHistoryItemResponse(
                    amount=None if row.price is None else display_nok(row.price),
                    price_basis=row.price_basis,
                    purchase_date=(
                        None if row.purchase_date is None else row.purchase_date.isoformat()
                    ),
                    date_precision=row.date_precision,
                    store_id=None if row.store_id is None else str(row.store_id),
                    store_name=row.store_name,
                    identity_level=row.store_identity,
                    condition=row.condition,
                    age_label=age_label(row.purchase_date, today),
                    ranked=row.ranked,
                    exclusion_reasons=list(row.reasons),
                    source=self._source(row.source),
                )
                for row in page
            ],
            total_count=total_count,
        )

    def _page(
        self,
        observations: list[Observation],
        cursor: str | None,
        limit: int | None,
    ) -> tuple[list[Observation], str | None]:
        """Nyeste kjøp først, udaterte sist, med ID som stabil sekundærnøkkel.

        Grunnlaget er én vare for én eier, altså like mange rader som eieren har
        kjøpt varen. Sorteringen gjøres derfor i minnet, slik at observasjoner og
        utelukkede linjer kan pagineres som én liste.
        """
        size = page_size(limit)
        ordered = sorted(observations, key=lambda row: str(row.row_id))
        ordered.sort(key=_sort_key, reverse=True)

        if cursor:
            key, row_id = decode_cursor(cursor, HISTORY_SCOPE)
            ordered = [
                row
                for row in ordered
                if _sort_key(row) < key
                or (_sort_key(row) == key and str(row.row_id) > str(row_id))
            ]

        if len(ordered) <= size:
            return ordered, None
        page = ordered[:size]
        last = page[-1]
        return page, encode_cursor(HISTORY_SCOPE, _sort_key(last), last.row_id)


def _sort_key(row: Observation) -> str:
    return UNDATED_SORT_KEY if row.purchase_date is None else row.purchase_date.isoformat()
