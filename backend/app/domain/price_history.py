"""S04-B: prisalder, historisk minimum og siste observasjon per butikk.

Modulen er ren. Den kjenner verken database eller klokke: dagens dato sendes
inn, slik at «alder» er et regnestykke og ikke en bivirkning.

To regler bærer resten:

- «Siste» er bare «siste» når rekkefølgen faktisk kan avgjøres. Flere kjøp
  samme dag uten sikkert klokkeslett gir et prisspenn med merket usikkerhet,
  ikke en påstand om at den laveste var den siste.
- Et minimum sammenlignes bare innenfor ett prisgrunnlag. Kr/kg og pakningspris
  er to forskjellige tall, og det laveste av dem er ingen pris.
"""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, replace
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from zoneinfo import ZoneInfo

# Kjøpsdatoen er lest av en norsk kvittering, så alderen regnes fra norsk dato.
OSLO = ZoneInfo("Europe/Oslo")

AGE_RECENT = "registrert nylig"
AGE_OLDER = "eldre observasjon"
AGE_OLD = "gammel observasjon"
RECENT_MAX_DAYS = 30
OLDER_MAX_DAYS = 90

# Alderen sier når kjøpet skjedde, ikke hva varen koster nå.
PRICE_DISCLAIMER = "Dagens pris kan være annerledes"

BRANCH_IDENTITY = "branch"
UNKNOWN_BASIS = "unknown"


class RankingExclusion(str, Enum):
    """Grunner som først oppstår når observasjonene ses i sammenheng."""

    # Kjede uten filial er et kjøp med pris, men ikke en sammenlignbar butikk.
    STORE_NOT_BRANCH = "store_not_branch"
    PRICE_BASIS_MISMATCH = "price_basis_mismatch"


class Certainty(str, Enum):
    CERTAIN = "certain"
    SAME_DAY_UNCERTAIN = "same_day_uncertain"


def oslo_today(now: datetime | None = None) -> date:
    return (now or datetime.now(OSLO)).astimezone(OSLO).date()


def age_label(purchase_date: date | None, today: date) -> str | None:
    """Ukjent dato har ingen alder; en dato fram i tid regnes som nylig."""
    if purchase_date is None:
        return None
    days = (today - purchase_date).days
    if days <= RECENT_MAX_DAYS:
        return AGE_RECENT
    if days <= OLDER_MAX_DAYS:
        return AGE_OLDER
    return AGE_OLD


@dataclass(frozen=True)
class Source:
    """Kildehenvisningen et kjøp kan åpnes fra, også når det er utelukket."""

    receipt_id: uuid.UUID
    revision_id: uuid.UUID
    revision: int
    line_id: uuid.UUID


@dataclass(frozen=True)
class Observation:
    row_id: uuid.UUID
    price: Decimal | None
    price_basis: str
    purchase_date: date | None
    date_precision: str
    purchase_time: time | None
    store_id: uuid.UUID | None
    store_name: str | None
    store_identity: str | None
    condition: str
    source: Source
    # Tom liste betyr rangerbar. Grunnene bevares slik at klienten kan forklare
    # hvorfor et kjøp ikke er med i minimumet.
    #
    # Den som fyller listen, eier invarianten: en rangerbar observasjon har
    # kjent kjøpsdato og en butikk med filialidentitet. Uten den ville
    # `unknown_date` og `store_not_branch` bare vært etiketter, og et udatert
    # kjøp kunne blitt sortert som om det hadde en dato.
    reasons: tuple[str, ...] = ()

    @property
    def ranked(self) -> bool:
        return not self.reasons


def apply_price_basis(observations: list[Observation]) -> tuple[str, list[Observation]]:
    """Velg grunnlaget minimumet regnes i, og utelukk de andre.

    Grunnlaget med flest rangerbare observasjoner vinner; ved likt antall
    velges det nyeste kjøpets grunnlag. De øvrige beholdes i historikken med
    `price_basis_mismatch`, fordi de er ekte kjøp, bare ikke sammenlignbare.
    """
    rankable = [row for row in observations if row.ranked]
    if not rankable:
        return UNKNOWN_BASIS, observations

    counts = Counter(row.price_basis for row in rankable)
    most = max(counts.values())
    leaders = {basis for basis, count in counts.items() if count == most}
    if len(leaders) == 1:
        basis = leaders.pop()
    else:
        newest = max(
            (row for row in rankable if row.price_basis in leaders),
            key=lambda row: (row.purchase_date, row.row_id),
        )
        basis = newest.price_basis

    return basis, [
        row
        if row.price_basis == basis or not row.ranked
        else replace(row, reasons=(RankingExclusion.PRICE_BASIS_MISMATCH.value,))
        for row in observations
    ]


@dataclass(frozen=True)
class Lowest:
    price: Decimal
    primary: Observation
    # Alle delte førsteplasser, én per butikk, eldste kjøp først.
    tied: tuple[Observation, ...]


def historical_lowest(observations: list[Observation]) -> Lowest | None:
    rankable = [row for row in observations if row.ranked and row.price is not None]
    if not rankable:
        return None

    price = min(row.price for row in rankable)
    # Lik pris i samme butikk to ganger er én førsteplass; det første kjøpet
    # er det som faktisk viser når butikken hadde prisen.
    by_store: dict[uuid.UUID, Observation] = {}
    for row in sorted(rankable, key=lambda row: (row.purchase_date, row.row_id)):
        if row.price == price and row.store_id not in by_store:
            by_store[row.store_id] = row

    tied = tuple(by_store.values())
    return Lowest(price=price, primary=tied[0], tied=tied)


@dataclass(frozen=True)
class StoreLatest:
    store_id: uuid.UUID
    store_name: str
    store_identity: str
    purchase_date: date
    certainty: Certainty
    price: Decimal | None
    price_range: tuple[Decimal, Decimal] | None
    condition: str | None
    observation_count: int
    sources: tuple[Source, ...]


def latest_per_store(observations: list[Observation]) -> list[StoreLatest]:
    """Siste kjøp per butikk, eller den usikkerheten som faktisk finnes."""
    grouped: dict[uuid.UUID, list[Observation]] = {}
    for row in observations:
        if row.ranked and row.price is not None:
            grouped.setdefault(row.store_id, []).append(row)

    latest = [_store_latest(rows) for rows in grouped.values()]
    return sorted(latest, key=lambda row: (row.store_name.lower(), str(row.store_id)))


def _store_latest(rows: list[Observation]) -> StoreLatest:
    day = max(row.purchase_date for row in rows)
    same_day = sorted(
        (row for row in rows if row.purchase_date == day),
        key=lambda row: (row.price, row.row_id),
    )
    certain = _resolved_latest(same_day)
    conditions = {row.condition for row in same_day}
    reference = certain or same_day[0]

    return StoreLatest(
        store_id=reference.store_id,
        store_name=reference.store_name,
        store_identity=reference.store_identity,
        purchase_date=day,
        certainty=Certainty.CERTAIN if certain else Certainty.SAME_DAY_UNCERTAIN,
        price=certain.price if certain else None,
        price_range=(
            None if certain else (same_day[0].price, same_day[-1].price)
        ),
        condition=conditions.pop() if len(conditions) == 1 else None,
        observation_count=len(same_day),
        sources=(certain.source,) if certain else tuple(row.source for row in same_day),
    )


def _resolved_latest(same_day: list[Observation]) -> Observation | None:
    """Den observasjonen som beviselig er den siste, ellers ingen.

    Sikkert klokkeslett avgjør rekkefølgen. Uten det er rekkefølgen ukjent, men
    prisen er likevel entydig når alle kjøpene den dagen kostet det samme.
    """
    if len(same_day) == 1:
        return same_day[0]

    timed = [
        row
        for row in same_day
        if row.date_precision == "datetime" and row.purchase_time is not None
    ]
    if len(timed) == len(same_day):
        newest = max(row.purchase_time for row in timed)
        winners = [row for row in timed if row.purchase_time == newest]
        if len({row.price for row in winners}) == 1:
            return winners[0]
        return None

    if len({row.price for row in same_day}) == 1:
        return same_day[0]
    return None
