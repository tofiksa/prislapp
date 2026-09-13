"""Tests for Norwegian money parsing and total selection."""

from decimal import Decimal

import pytest

from app.parsers.amounts import parse_money_amount
from app.parsers.totals import extract_totals_from_text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("20,00", Decimal("20.00")),
        ("20.00", Decimal("20.00")),
        ("1 234,50", Decimal("1234.50")),
        ("NOK 1.234,50", Decimal("1234.50")),
        ("kr 20,00", Decimal("20.00")),
        ("-5,00", Decimal("-5.00")),
    ],
)
def test_parse_money_amount(text, expected):
    result = parse_money_amount(text)
    assert result.value == expected


def test_rema_discount_total():
    text = "REMA 1000 METRO SENTER\nMELK 15 25,00\nRABATT -5,00\nTOTALT 20,00"
    total = extract_totals_from_text(text)
    assert total.printed_total == Decimal("20.00")


def test_kiwi_total_on_next_line():
    text = "KIWI OSLO\nMELK 25,00\nTOTALT\n20,00"
    total = extract_totals_from_text(text)
    assert total.printed_total == Decimal("20.00")


def test_kiwi_thousands_separator():
    text = "KIWI OSLO\nVARE 99,00\nTOTALT 1 234,50"
    total = extract_totals_from_text(text)
    assert total.printed_total == Decimal("1234.50")


def test_sum_before_final_total():
    text = "KIWI OSLO\nMELK 25,00\nSUM 25,00\nRABATT -5,00\nTOTALT 20,00"
    total = extract_totals_from_text(text)
    assert total.printed_total == Decimal("20.00")


def test_normal_cash_change_not_trade_total():
    text = (
        "Normal Oslo, Thon Senter Triaden\n"
        "Vare 1 50,00\nVare 2 50,00\n"
        "I alt kr. 100,00\nKontant -200,00\nVekslepenger 100,00"
    )
    total = extract_totals_from_text(text)
    assert total.printed_total == Decimal("100.00")


def test_rema_mva_table_does_not_override_sum_varer():
    text = (
        "REMA 1000 METRO SENTER\n"
        "Sum 7 varer 158,83\n"
        "MVA-grunnlag\n15% 152,08\n25% 6,75\nTotalt 158,83"
    )
    total = extract_totals_from_text(text)
    assert total.printed_total == Decimal("158.83")


def test_conflicting_totals_abstain():
    text = "KIWI OSLO\nVARE 10,00\nTOTALT 15,00\nTOTALT 20,00"
    total = extract_totals_from_text(text)
    assert total.printed_total is None
    assert total.state == "uncertain"
