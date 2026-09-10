from pathlib import Path

from app.parsers import parse_receipt_text
from app.services.ocr_service import OcrService
import pytest


def test_rema_fixture_image_reaches_review_with_product_lines():
    path = Path(__file__).resolve().parents[2] / "testdata/receipts/rema1000-metro-senter.png"
    text = OcrService().extract_text(path.read_bytes())
    parsed = parse_receipt_text(text)
    assert len(parsed.items) >= 5, text
    assert parsed.total is not None
    assert parsed.store_name and "REMA" in parsed.store_name.upper()


@pytest.mark.parametrize("filename", ["normal-triaden.png", "europris-normal-triaden.png"])
def test_generic_receipt_images_have_items(filename):
    path = Path(__file__).resolve().parents[2] / "testdata/receipts" / filename
    text = OcrService().extract_text(path.read_bytes())
    parsed = parse_receipt_text(text)
    assert parsed.items, text
