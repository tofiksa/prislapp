"""S04-A: kvalifiseringsreglene i `app.domain.pricing` utenfor C00-fixturene."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.domain.pricing import (
    Condition,
    DatePrecision,
    ExclusionReason,
    LineType,
    PackageIdentity,
    PriceBasis,
    PricingLine,
    evaluate_line,
    same_package_minimum,
    standardized_quantity_price,
)
from app.domain.units import QuantityUnit

RESOLVED_PRODUCT_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")


def _line(**overrides) -> PricingLine:
    """En avklart pakningslinje på 40,00 for to pakker."""
    defaults = {
        "line_type": LineType.PRODUCT,
        "currency": "NOK",
        "quantity_unit": QuantityUnit.EACH,
        "package_count": Decimal("2"),
        "net_line_total": Decimal("40.00"),
        "condition": Condition.NONE,
        "user_product_id": RESOLVED_PRODUCT_ID,
        "identity_status": "confirmed",
        "date_precision": DatePrecision.DATE,
    }
    defaults.update(overrides)
    return PricingLine(**defaults)


def test_resolved_line_is_eligible_without_reasons():
    result = evaluate_line(_line())

    assert result.eligible is True
    assert result.exclusion_reasons == ()
    assert result.eligible_for_dated_ranking is True


def test_deposit_line_is_never_a_product_minimum():
    result = evaluate_line(_line(line_type=LineType.DEPOSIT))

    assert result.eligible is False
    assert ExclusionReason.NON_PRODUCT_LINE in result.exclusion_reasons
    assert result.eligible_for_dated_ranking is False


@pytest.mark.parametrize("line_type", [LineType.FEE, LineType.RETURN, LineType.UNKNOWN])
def test_fee_return_and_unknown_lines_are_not_product_minimums(line_type):
    result = evaluate_line(_line(line_type=line_type))

    assert result.eligible is False
    assert ExclusionReason.NON_PRODUCT_LINE in result.exclusion_reasons


def test_unknown_unit_gives_no_price_basis_and_no_price():
    result = evaluate_line(_line(quantity_unit=QuantityUnit.UNKNOWN))

    assert result.eligible is False
    assert result.price_basis is PriceBasis.UNKNOWN
    assert result.comparison_price is None
    assert ExclusionReason.UNKNOWN_UNIT in result.exclusion_reasons


def test_foreign_currency_is_archived_but_not_compared():
    result = evaluate_line(_line(currency="SEK"))

    assert result.eligible is False
    assert result.comparison_price is None
    assert ExclusionReason.NON_NOK in result.exclusion_reasons


def test_line_without_private_product_is_not_rankable():
    result = evaluate_line(_line(user_product_id=None, identity_status=None))

    assert result.eligible is False
    assert ExclusionReason.UNRESOLVED_IDENTITY in result.exclusion_reasons


@pytest.mark.parametrize("identity_status", ["unresolved", "inherited"])
def test_unresolved_and_inherited_identity_are_not_rankable(identity_status):
    result = evaluate_line(_line(identity_status=identity_status))

    assert result.eligible is False
    assert ExclusionReason.UNRESOLVED_IDENTITY in result.exclusion_reasons


@pytest.mark.parametrize(
    "condition",
    [Condition.MEMBER, Condition.MULTI_BUY, Condition.COUPON],
)
def test_conditional_lines_are_not_standard_price_basis(condition):
    result = evaluate_line(_line(condition=condition))

    assert result.eligible is False
    assert ExclusionReason.CONDITIONAL in result.exclusion_reasons
    # Prisen finnes fortsatt, den er bare ikke standardgrunnlag.
    assert result.comparison_price == Decimal("20.000000")


def test_unknown_condition_is_not_qualified():
    result = evaluate_line(_line(condition=Condition.UNKNOWN))

    assert result.eligible is False
    assert ExclusionReason.UNKNOWN_CONDITION in result.exclusion_reasons


@pytest.mark.parametrize("package_count", [Decimal("0"), Decimal("-1")])
def test_non_positive_quantity_gives_no_price(package_count):
    result = evaluate_line(_line(package_count=package_count))

    assert result.eligible is False
    assert result.comparison_price is None
    assert ExclusionReason.NON_POSITIVE_QUANTITY in result.exclusion_reasons


def test_each_line_without_package_count_uses_the_counted_quantity():
    result = evaluate_line(_line(package_count=None, quantity=Decimal("2")))

    assert result.eligible is True
    assert result.comparison_price == Decimal("20.000000")


def test_each_line_without_any_count_is_not_priced():
    result = evaluate_line(_line(package_count=None, quantity=None))

    assert result.eligible is False
    assert result.comparison_price is None
    assert ExclusionReason.UNKNOWN_QUANTITY in result.exclusion_reasons


def test_printed_unit_price_is_read_not_used_as_truth():
    result = evaluate_line(_line(printed_unit_price=Decimal("999.00")))

    assert result.comparison_price == Decimal("20.000000")


def test_grams_are_normalised_to_kilograms_before_comparison():
    result = evaluate_line(
        _line(
            quantity_unit=QuantityUnit.G,
            quantity=Decimal("400"),
            package_count=None,
            net_line_total=Decimal("24.90"),
        ),
    )

    assert result.price_basis is PriceBasis.PER_KG
    assert result.comparison_price == Decimal("62.250000")


def test_millilitres_are_normalised_to_litres_before_comparison():
    result = evaluate_line(
        _line(
            quantity_unit=QuantityUnit.ML,
            quantity=Decimal("500"),
            package_count=None,
            net_line_total=Decimal("12.50"),
        ),
    )

    assert result.price_basis is PriceBasis.PER_LITRE
    assert result.comparison_price == Decimal("25.000000")


def test_reasons_accumulate_for_a_line_with_several_problems():
    result = evaluate_line(
        _line(
            line_type=LineType.UNKNOWN,
            quantity_unit=QuantityUnit.UNKNOWN,
            condition=Condition.UNKNOWN,
            date_precision=DatePrecision.UNKNOWN,
        ),
    )

    assert set(result.exclusion_reasons) == {
        ExclusionReason.NON_PRODUCT_LINE,
        ExclusionReason.UNKNOWN_UNIT,
        ExclusionReason.UNKNOWN_CONDITION,
        ExclusionReason.UNKNOWN_DATE,
    }


def test_standardised_kilo_price_needs_known_package_content():
    price_basis, price = standardized_quantity_price(_line())

    assert price_basis is PriceBasis.UNKNOWN
    assert price is None


def test_standardised_kilo_price_is_separate_from_the_package_minimum():
    line = _line(pack_content=Decimal("400"), pack_unit=QuantityUnit.G)

    result = evaluate_line(line)
    price_basis, price = standardized_quantity_price(line)

    assert result.price_basis is PriceBasis.PER_PACKAGE
    assert result.comparison_price == Decimal("20.000000")
    assert price_basis is PriceBasis.PER_KG
    assert price == Decimal("50.000000")


def test_same_package_minimum_normalises_units():
    assert (
        same_package_minimum(
            PackageIdentity(Decimal("0.400"), QuantityUnit.KG),
            PackageIdentity(Decimal("400"), QuantityUnit.G),
        )
        is True
    )


def test_unknown_package_content_is_never_the_same_minimum():
    assert (
        same_package_minimum(
            PackageIdentity(None, QuantityUnit.UNKNOWN),
            PackageIdentity(None, QuantityUnit.UNKNOWN),
        )
        is False
    )
