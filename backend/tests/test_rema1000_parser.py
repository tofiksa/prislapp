from decimal import Decimal

from app.parsers.rema1000 import detect_rema1000, parse_rema1000
from tests.fixtures.rema1000_ocr import REMA1000_SAMPLE_OCR


def test_detect_rema1000():
    assert detect_rema1000(REMA1000_SAMPLE_OCR) is True
    assert detect_rema1000("KIWI OSLO\nSome other store") is False


def test_parse_rema1000_items():
    parsed = parse_rema1000(REMA1000_SAMPLE_OCR)
    assert parsed.store_chain == "rema1000"
    assert parsed.store_name == "REMA 1000 METRO SENTER"
    assert parsed.purchase_date is not None
    assert parsed.purchase_date.year == 2026
    assert parsed.purchase_date.month == 8
    assert parsed.purchase_date.day == 4
    assert parsed.total == Decimal("158.83")
    assert len(parsed.items) == 7

    names = [item.raw_name for item in parsed.items]
    assert "Q LETTMELK 1%" in names
    assert "NYPOTET LØSVEKT" in names
    assert "BÆREPOSE 80% RESIR" in names

    potato = next(item for item in parsed.items if item.raw_name == "NYPOTET LØSVEKT")
    assert potato.quantity == Decimal("1.045")
    assert potato.unit_price == Decimal("29.90")
    assert potato.line_total == Decimal("31.25")

    aubergine = next(item for item in parsed.items if item.raw_name == "AUBERGINE LØSVEKT")
    assert aubergine.quantity == Decimal("0.385")
    assert aubergine.unit_price == Decimal("61.90")
