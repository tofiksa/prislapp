"""S04-A: de delte C00-fixturene kjøres gjennom den rene prisberegningen.

Fixturene beskriver pris-matematikken, ikke hele linjen. Felter som ikke står i
JSON-filen settes eksplisitt her til den avklarte varianten, slik at hver test
isolerer regelen fixturen faktisk beskriver.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from pathlib import Path

from app.domain.money import display_nok
from app.domain.pricing import (
    Condition,
    DatePrecision,
    LineType,
    PriceBasis,
    PackageIdentity,
    PricingLine,
    evaluate_line,
    same_package_minimum,
)
from app.domain.units import QuantityUnit

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = REPO_ROOT / "docs" / "contracts" / "fixtures"

RESOLVED_PRODUCT_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")


def _load_fixture(name: str) -> dict:
    with (FIXTURE_DIR / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def _decimal(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


def _line_from_fixture(fixture: dict, **overrides) -> PricingLine:
    """Bygg en linje fra fixturen med avklart identitet, valuta og vilkår."""
    defaults = {
        "line_type": LineType(fixture.get("line_type", "product")),
        "currency": fixture.get("currency", "NOK"),
        "quantity": _decimal(fixture.get("quantity")),
        "quantity_unit": QuantityUnit(fixture.get("quantity_unit", "each")),
        "package_count": _decimal(fixture.get("package_count")),
        "net_line_total": _decimal(fixture.get("net_line_total")),
        "condition": Condition(fixture.get("condition", "none")),
        "user_product_id": RESOLVED_PRODUCT_ID,
        "identity_status": "confirmed",
        "date_precision": DatePrecision.DATE,
    }
    defaults.update(overrides)
    return PricingLine(**defaults)


def _package_from_fixture(side: dict) -> PackageIdentity:
    return PackageIdentity(
        pack_content=_decimal(side.get("pack_content")),
        pack_unit=QuantityUnit(side.get("pack_unit", "unknown")),
    )


def test_two_packages_give_twenty_per_package():
    fixture = _load_fixture("two-packages.json")

    result = evaluate_line(_line_from_fixture(fixture))

    assert result.eligible is fixture["eligible"]
    assert result.price_basis == PriceBasis(fixture["price_basis"])
    assert result.comparison_price == Decimal(fixture["comparison_price"])
    assert display_nok(result.comparison_price) == fixture["display_price"]


def test_allocated_discount_prices_the_net_line_not_the_gross():
    fixture = _load_fixture("discount-allocated.json")
    gross = Decimal(fixture["gross_line_total"])
    allocated = Decimal(fixture["allocated_discount"])

    result = evaluate_line(_line_from_fixture(fixture))

    assert gross - allocated == Decimal(fixture["net_line_total"])
    assert result.eligible is fixture["eligible"]
    assert result.comparison_price == Decimal(fixture["comparison_price"])


def test_rounding_keeps_six_decimals_internally_and_two_when_shown():
    fixture = _load_fixture("rounding.json")

    result = evaluate_line(_line_from_fixture(fixture))

    assert result.comparison_price == Decimal(fixture["internal"])
    assert display_nok(result.comparison_price) == fixture["display"]


def test_unknown_date_is_not_a_dated_observation():
    fixture = _load_fixture("unknown-date.json")

    result = evaluate_line(
        _line_from_fixture(
            fixture,
            quantity_unit=QuantityUnit.EACH,
            package_count=Decimal("1"),
            net_line_total=Decimal("19.90"),
            date_precision=DatePrecision(fixture["date_precision"]),
        ),
    )

    assert fixture["purchase_date"] is None
    assert result.eligible_for_dated_ranking is fixture["eligible_for_dated_ranking"]
    assert "unknown_date" in result.exclusion_reasons


def test_different_pack_sizes_are_not_the_same_package_minimum():
    fixture = _load_fixture("pack-size-mismatch.json")

    same = same_package_minimum(
        _package_from_fixture(fixture["left"]),
        _package_from_fixture(fixture["right"]),
    )

    assert same is fixture["same_package_minimum"]


def test_old_and_newer_price_are_two_dated_observations():
    fixture = _load_fixture("old-and-newer-price.json")
    historical = fixture["historical_lowest"]
    latest = fixture["latest_by_store"][0]

    results = [
        evaluate_line(
            _line_from_fixture(
                fixture,
                package_count=Decimal("1"),
                net_line_total=Decimal(observation["amount"]),
            ),
        )
        for observation in (historical, latest)
    ]

    assert [result.comparison_price for result in results] == [
        Decimal("19.900000"),
        Decimal("29.900000"),
    ]
    assert all(result.eligible_for_dated_ranking for result in results)
    assert historical["purchase_date"] != latest["purchase_date"]


def test_unresolved_discount_gives_no_comparison_price():
    fixture = _load_fixture("discount-unresolved.json")

    result = evaluate_line(_line_from_fixture(fixture, package_count=Decimal("1")))

    assert result.eligible is fixture["eligible"]
    assert result.comparison_price is None
    assert list(result.exclusion_reasons) == fixture["exclusion_reasons"]


def test_kg_item_compares_per_kg_never_per_each():
    fixture = _load_fixture("kg-item.json")

    result = evaluate_line(_line_from_fixture(fixture))

    assert result.eligible is fixture["eligible"]
    assert result.price_basis == PriceBasis(fixture["price_basis"])
    assert result.comparison_price == Decimal(fixture["comparison_price"])
    assert display_nok(result.comparison_price) == fixture["display_price"]
