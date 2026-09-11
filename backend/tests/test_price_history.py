"""S04-B: aldersgrenser, delte førsteplasser og samme-dags-usikkerhet, uten database."""

from __future__ import annotations

import uuid
from datetime import date, time
from decimal import Decimal

from app.domain.price_history import (
    AGE_OLD,
    AGE_OLDER,
    AGE_RECENT,
    Certainty,
    Observation,
    RankingExclusion,
    Source,
    age_label,
    apply_price_basis,
    historical_lowest,
    latest_per_store,
)

TODAY = date(2026, 9, 11)
STORE_A = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
STORE_B = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")


def _source() -> Source:
    return Source(
        receipt_id=uuid.uuid4(),
        revision_id=uuid.uuid4(),
        revision=1,
        line_id=uuid.uuid4(),
    )


def _observation(
    price: str | None,
    purchase_date: date | None = TODAY,
    *,
    store_id: uuid.UUID = STORE_A,
    store_name: str = "Rema 1000 Majorstuen",
    price_basis: str = "per_package",
    date_precision: str = "date",
    purchase_time: time | None = None,
    condition: str = "none",
    reasons: tuple[str, ...] = (),
) -> Observation:
    return Observation(
        row_id=uuid.uuid4(),
        price=None if price is None else Decimal(price),
        price_basis=price_basis,
        purchase_date=purchase_date,
        date_precision=date_precision,
        purchase_time=purchase_time,
        store_id=store_id,
        store_name=store_name,
        store_identity="branch",
        condition=condition,
        source=_source(),
        reasons=reasons,
    )


def test_a_purchase_thirty_days_ago_is_registered_recently():
    assert age_label(date(2026, 8, 12), TODAY) == AGE_RECENT


def test_a_purchase_thirty_one_days_ago_is_an_older_observation():
    assert age_label(date(2026, 8, 11), TODAY) == AGE_OLDER


def test_a_purchase_ninety_days_ago_is_still_an_older_observation():
    assert age_label(date(2026, 6, 13), TODAY) == AGE_OLDER


def test_a_purchase_ninety_one_days_ago_is_an_old_observation():
    assert age_label(date(2026, 6, 12), TODAY) == AGE_OLD


def test_an_unknown_date_has_no_age_label():
    assert age_label(None, TODAY) is None


def test_a_date_ahead_of_today_is_not_aged_backwards():
    assert age_label(date(2026, 9, 20), TODAY) == AGE_RECENT


def test_the_same_store_twice_at_the_lowest_price_is_one_first_place():
    lowest = historical_lowest(
        [
            _observation("19.90", date(2026, 8, 1)),
            _observation("19.90", date(2026, 8, 20)),
        ],
    )

    assert [row.purchase_date for row in lowest.tied] == [date(2026, 8, 1)]


def test_every_store_at_the_lowest_price_is_a_first_place():
    lowest = historical_lowest(
        [
            _observation("19.90", date(2026, 8, 20), store_id=STORE_B, store_name="Kiwi"),
            _observation("19.90", date(2026, 8, 1)),
            _observation("29.90", date(2026, 9, 1)),
        ],
    )

    assert lowest.price == Decimal("19.90")
    assert [row.store_id for row in lowest.tied] == [STORE_A, STORE_B]


def test_no_rankable_observation_has_no_lowest():
    assert historical_lowest([_observation("1.00", reasons=("unknown_date",))]) is None


def test_equal_prices_on_the_same_day_leave_no_uncertainty():
    latest = latest_per_store(
        [_observation("24.90", TODAY), _observation("24.90", TODAY)],
    )

    assert latest[0].certainty is Certainty.CERTAIN
    assert latest[0].price == Decimal("24.90")
    assert latest[0].observation_count == 2


def test_one_dated_purchase_without_a_time_is_still_the_latest():
    latest = latest_per_store(
        [_observation("29.90", date(2026, 9, 1)), _observation("19.90", date(2026, 8, 1))],
    )

    assert latest[0].certainty is Certainty.CERTAIN
    assert latest[0].price == Decimal("29.90")


def test_a_day_with_only_some_known_times_stays_uncertain():
    latest = latest_per_store(
        [
            _observation("19.90", TODAY, date_precision="datetime", purchase_time=time(18)),
            _observation("29.90", TODAY),
        ],
    )

    assert latest[0].certainty is Certainty.SAME_DAY_UNCERTAIN
    assert latest[0].price_range == (Decimal("19.90"), Decimal("29.90"))


def test_two_different_prices_at_the_same_known_time_stay_uncertain():
    latest = latest_per_store(
        [
            _observation("19.90", TODAY, date_precision="datetime", purchase_time=time(18)),
            _observation("29.90", TODAY, date_precision="datetime", purchase_time=time(18)),
        ],
    )

    assert latest[0].certainty is Certainty.SAME_DAY_UNCERTAIN


def test_uncertainty_hides_no_condition_it_cannot_vouch_for():
    latest = latest_per_store(
        [
            _observation("19.90", TODAY, condition="none"),
            _observation("29.90", TODAY, condition="member"),
        ],
    )

    assert latest[0].condition is None


def test_each_store_gets_its_own_latest_purchase():
    latest = latest_per_store(
        [
            _observation("29.90", date(2026, 9, 1)),
            _observation("24.90", date(2026, 8, 1), store_id=STORE_B, store_name="Kiwi"),
        ],
    )

    assert [(row.store_name, row.price) for row in latest] == [
        ("Kiwi", Decimal("24.90")),
        ("Rema 1000 Majorstuen", Decimal("29.90")),
    ]


def test_the_basis_with_most_observations_carries_the_minimum():
    basis, observations = apply_price_basis(
        [
            _observation("50.00", price_basis="per_kg"),
            _observation("40.00", price_basis="per_kg"),
            _observation("5.00", price_basis="per_package"),
        ],
    )

    assert basis == "per_kg"
    assert [row.reasons for row in observations] == [
        (),
        (),
        (RankingExclusion.PRICE_BASIS_MISMATCH.value,),
    ]


def test_an_equal_number_of_observations_follows_the_newest_purchase():
    basis, _ = apply_price_basis(
        [
            _observation("50.00", date(2026, 8, 1), price_basis="per_kg"),
            _observation("5.00", date(2026, 9, 1), price_basis="per_package"),
        ],
    )

    assert basis == "per_package"


def test_an_already_excluded_observation_keeps_its_own_reason():
    _, observations = apply_price_basis(
        [
            _observation("50.00", price_basis="per_kg"),
            _observation("5.00", price_basis="per_package", reasons=("unknown_date",)),
        ],
    )

    assert observations[1].reasons == ("unknown_date",)


def test_without_a_rankable_observation_the_basis_is_unknown():
    basis, _ = apply_price_basis([_observation("5.00", reasons=("unresolved_identity",))])

    assert basis == "unknown"
