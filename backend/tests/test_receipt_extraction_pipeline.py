"""End-to-end parser pipeline tests for baseline bug fixes."""

from decimal import Decimal

from app.parsers import parse_receipt_text
from app.services.receipt_extraction_service import parse_receipt_text_v2
from tests.fixtures.rema1000_ocr import REMA1000_SAMPLE_OCR


def test_baseline_rema_split_lines_fixed():
    text = "REMA 1000\nMETRO SENTER\nMELK 15 25,00\nSUM 1 VARER 25,00"
    extraction, parsed = parse_receipt_text_v2(text)
    assert extraction.store.chain == "rema1000"
    assert extraction.store.branch_text == "METRO SENTER"
    assert parsed.total == Decimal("25.00")


def test_all_six_baseline_bugs_via_public_entry():
    cases = [
        ("REMA 1000\nMETRO SENTER\nMELK 15 25,00\nSUM 1 VARER 25,00", "rema1000", Decimal("25.00")),
        ("REMA 1000 METRO SENTER\nMELK 15 25,00\nRABATT -5,00\nTOTALT 20,00", "rema1000", Decimal("20.00")),
        ("KIWI OSLO\nMELK 25,00\nTOTALT\n20,00", "kiwi", Decimal("20.00")),
        ("KIWI OSLO\nVARE 99,00\nTOTALT 1 234,50", "kiwi", Decimal("1234.50")),
        ("KIWI OSLO\nMELK 25,00\nSUM 25,00\nRABATT -5,00\nTOTALT 20,00", "kiwi", Decimal("20.00")),
    ]
    for text, chain, total in cases:
        parsed = parse_receipt_text(text)
        assert parsed.store_chain == chain
        assert parsed.total == total


def test_velkommen_not_store_name():
    text = "VELKOMMEN\nKIWI OSLO\nMELK 25,00\nTOTALT 25,00"
    parsed = parse_receipt_text(text)
    assert parsed.store_chain == "kiwi"
    assert parsed.store_name != "VELKOMMEN"


def test_rema_fixture_no_item_sum_fallback_when_total_missing():
    text = REMA1000_SAMPLE_OCR.replace("Sum 7 varer                            158,83", "Sum 7 varer")
    parsed = parse_receipt_text(text)
    assert parsed.total is None
    assert len(parsed.items) == 7


def test_rema_fixture_keeps_correct_total():
    parsed = parse_receipt_text(REMA1000_SAMPLE_OCR)
    assert parsed.total == Decimal("158.83")
    assert len(parsed.items) == 7
