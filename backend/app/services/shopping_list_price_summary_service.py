"""S07-A: ett prisoppslag for hele handlelisten.

Prisene hentes for alle varene på listen samtidig, og minimumet regnes per
linje i prosessen. Antall linjer endrer størrelsen på IN-listen, ikke antall
spørringer.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.money import display_nok
from app.domain.price_history import (
    PRICE_DISCLAIMER,
    Lowest,
    Observation,
    age_label,
    apply_price_basis,
    historical_lowest,
    oslo_today,
)
from app.errors import ApiError, not_found
from app.models.account_ledger import AccountLedger
from app.models.shopping_list import ShoppingList, ShoppingListItem
from app.schemas.shopping_list_price_summary import (
    PriceSummaryLineResponse,
    ShoppingListPriceSummaryResponse,
    SummaryLowestResponse,
)
from app.schemas.v2 import decimal_string
from app.services.price_observations import PriceObservationLoader

# Regelsettet svaret er regnet etter. Klienten kan skille to svar som ser like
# ut, men er regnet av forskjellige regler.
POLICY_VERSION = "p0-2026-09-11"
DEFAULT_PRICE_DATA_VERSION = 1

STATUS_HISTORICAL_LOWEST = "historical_lowest"
STATUS_NO_COMPARABLE_PRICE = "no_comparable_price"

# Fritekst er et notat, ikke en vare. Den har ingen historikk å mangle.
REASON_FREE_TEXT = "free_text_no_history"
# Varen finnes i katalogen, men er aldri registrert kjøpt.
REASON_NEVER_OBSERVED = "never_observed"
# Kjøpene finnes, men ingen av dem kan rangeres: kjede uten filial, ukjent dato,
# vilkårspris eller et annet prisgrunnlag. Grunnene per kjøp ligger i S04-B.
REASON_NO_QUALIFIED_OBSERVATION = "no_qualified_observation"


def _price_summary_unavailable() -> ApiError:
    """En feilet utregning er ikke «ingen pris».

    Tomme linjer eller manglende minimum ville sett ut som et faktum om
    brukerens historikk. Derfor svarer ruten 5xx med `retryable`, og klienten
    beholder den merkede cachen sin. Selve listen ligger på CRUD-rutene.
    """
    return ApiError(
        503,
        "PRICE_SUMMARY_UNAVAILABLE",
        "Prisene kunne ikke hentes nå. Prøv igjen.",
        retryable=True,
    )


class ShoppingListPriceSummaryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_price_summary(
        self,
        user_id: uuid.UUID,
        list_id: uuid.UUID,
        include_conditional: bool = False,
    ) -> ShoppingListPriceSummaryResponse:
        try:
            return await self._summary(user_id, list_id, include_conditional)
        except ApiError:
            # 404 er et svar om listen, ikke en prisfeil, og skal ikke skjules.
            raise
        except Exception as exc:
            raise _price_summary_unavailable() from exc

    async def _summary(
        self,
        user_id: uuid.UUID,
        list_id: uuid.UUID,
        include_conditional: bool,
    ) -> ShoppingListPriceSummaryResponse:
        shopping_list = await self._list_row(user_id, list_id)
        items = await self._items(shopping_list.id)

        product_ids = [item.user_product_id for item in items if item.user_product_id]
        observations = await PriceObservationLoader(self.db).observations(
            user_id,
            product_ids,
            include_conditional,
        )
        today = oslo_today()

        return ShoppingListPriceSummaryResponse(
            list_id=str(shopping_list.id),
            list_version=shopping_list.version,
            content_revision=shopping_list.content_seq,
            price_data_version=await self._price_data_version(user_id),
            calculated_at=datetime.now(timezone.utc).isoformat(),
            policy_version=POLICY_VERSION,
            include_conditional=include_conditional,
            lines=[
                self._line(item, observations.get(item.user_product_id, []), today)
                for item in items
            ],
        )

    def _line(
        self,
        item: ShoppingListItem,
        observations: list[Observation],
        today,
    ) -> PriceSummaryLineResponse:
        _, priced = apply_price_basis(observations)
        rankable = [row for row in priced if row.ranked]
        lowest = historical_lowest(rankable)

        return PriceSummaryLineResponse(
            item_id=str(item.id),
            product_id=None if item.user_product_id is None else str(item.user_product_id),
            free_text=item.free_text,
            quantity=decimal_string(item.quantity),
            quantity_unit=item.quantity_unit,
            status=STATUS_HISTORICAL_LOWEST if lowest else STATUS_NO_COMPARABLE_PRICE,
            reason=None if lowest else self._reason(item, observations),
            historical_lowest=self._lowest_response(lowest, today),
            eligible_store_count=len({row.store_id for row in rankable}),
        )

    @staticmethod
    def _reason(item: ShoppingListItem, observations: list[Observation]) -> str:
        if item.user_product_id is None:
            return REASON_FREE_TEXT
        if not observations:
            return REASON_NEVER_OBSERVED
        return REASON_NO_QUALIFIED_OBSERVATION

    @staticmethod
    def _lowest_response(lowest: Lowest | None, today) -> SummaryLowestResponse | None:
        if lowest is None:
            # Ingen kvalifisert observasjon er et ærlig svar, ikke null kroner.
            return None
        primary = lowest.primary
        return SummaryLowestResponse(
            amount=display_nok(lowest.price),
            store_id=str(primary.store_id),
            store_name=primary.store_name,
            identity_level=primary.store_identity,
            purchase_date=primary.purchase_date.isoformat(),
            age_label=age_label(primary.purchase_date, today),
            price_basis=primary.price_basis,
            disclaimer=PRICE_DISCLAIMER,
        )

    async def _list_row(self, user_id: uuid.UUID, list_id: uuid.UUID) -> ShoppingList:
        result = await self.db.execute(
            sa.select(ShoppingList).where(
                ShoppingList.id == list_id,
                ShoppingList.user_id == user_id,
                ShoppingList.deleted_at.is_(None),
            ),
        )
        shopping_list = result.scalar_one_or_none()
        if shopping_list is None:
            # Fremmed eier, ukjent ID og slettet liste gir samme svar.
            raise not_found()
        return shopping_list

    async def _items(self, list_id: uuid.UUID) -> list[ShoppingListItem]:
        """Slettede linjer utelates; de er ikke lenger en del av handleturen."""
        result = await self.db.execute(
            sa.select(ShoppingListItem)
            .where(
                ShoppingListItem.list_id == list_id,
                ShoppingListItem.deleted_at.is_(None),
            )
            .order_by(ShoppingListItem.position.asc(), ShoppingListItem.id.asc()),
        )
        return list(result.scalars().all())

    async def _price_data_version(self, user_id: uuid.UUID) -> int:
        result = await self.db.execute(
            sa.select(AccountLedger.price_data_version).where(
                AccountLedger.user_id == user_id,
            ),
        )
        version = result.scalar_one_or_none()
        return DEFAULT_PRICE_DATA_VERSION if version is None else version
