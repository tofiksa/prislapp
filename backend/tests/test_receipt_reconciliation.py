"""S05-A: avstemmingen som ren funksjon, uten database eller HTTP."""

from dataclasses import dataclass
from decimal import Decimal

import pytest

from app.domain.pricing import LineType
from app.errors import ApiError
from app.models.receipt_revision import ReconciliationStatus
from app.services.receipt_revision_service import reconcile


@dataclass(frozen=True)
class _Line:
    line_type: LineType
    net_line_total: Decimal | None


def _line(line_type: str, amount: str | None) -> _Line:
    return _Line(
        LineType(line_type),
        None if amount is None else Decimal(amount),
    )


def _confirm(lines, printed_total: str | None, accept_gap: bool = False):
    return reconcile(
        lines,
        None if printed_total is None else Decimal(printed_total),
        accept_gap,
        enforce_gap=True,
    )


def test_deposit_fee_return_and_discount_all_count_in_the_sum():
    lines = [
        _line("product", "100.00"),
        _line("deposit", "3.00"),
        _line("fee", "2.50"),
        _line("return", "-20.00"),
        _line("discount", "-5.50"),
    ]

    result = _confirm(lines, "80.00")

    assert result.computed_total == Decimal("80.00")
    assert result.status is ReconciliationStatus.BALANCED


def test_a_line_of_unknown_type_is_left_out_of_the_sum():
    lines = [_line("product", "25.00"), _line("unknown", "999.00")]

    result = _confirm(lines, "25.00")

    assert result.computed_total == Decimal("25.00")
    assert result.status is ReconciliationStatus.BALANCED


def test_one_ore_is_within_tolerance_and_two_ore_is_a_gap():
    within = _confirm([_line("product", "25.01")], "25.00")

    assert within.status is ReconciliationStatus.BALANCED
    assert within.difference == Decimal("0.01")

    with pytest.raises(ApiError) as gap:
        _confirm([_line("product", "25.02")], "25.00")

    assert gap.value.status_code == 400
    assert gap.value.code == "RECONCILIATION_GAP"


def test_an_accepted_gap_is_recorded_as_accepted():
    result = _confirm([_line("product", "25.00")], "30.00", accept_gap=True)

    assert result.status is ReconciliationStatus.GAP_ACCEPTED
    assert result.gap_accepted is True
    assert result.difference == Decimal("-5.00")


def test_an_empty_receipt_does_not_reconcile_against_a_printed_total():
    with pytest.raises(ApiError):
        _confirm([], "25.00")


def test_a_receipt_without_lines_or_total_is_unverifiable():
    result = _confirm([], None)

    assert result.status is ReconciliationStatus.UNVERIFIABLE
    assert result.computed_total == Decimal("0.00")
    assert result.difference is None


def test_a_draft_keeps_a_gap_instead_of_being_rejected():
    result = reconcile(
        [_line("product", "25.00")],
        Decimal("100.00"),
        accept_gap=False,
        enforce_gap=False,
    )

    assert result.status is ReconciliationStatus.GAP
    assert result.gap_accepted is False
    assert result.difference == Decimal("-75.00")


def test_an_accepted_gap_does_not_mark_a_balanced_receipt_as_accepted():
    result = _confirm([_line("product", "25.00")], "25.00", accept_gap=True)

    assert result.status is ReconciliationStatus.BALANCED
    assert result.gap_accepted is False
