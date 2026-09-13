"""Tests for layout building and OCR document adapter."""

from app.domain.receipt_extraction import OcrDocument, OcrToken
from app.parsers.layout import build_lines_from_text, build_lines_from_tokens, tokens_from_text_lines
from app.services.ocr_service import OcrService


def test_build_lines_from_text_sections():
    text = "REMA 1000\nProduktnavn\nMelk 15,00\nSum 1 varer 25,00\nKontant 50,00"
    lines = build_lines_from_text(text)
    sections = {line.section for line in lines}
    assert "header" in sections
    assert "totals" in sections or any("Sum" in line.text for line in lines)


def test_tokens_reading_order_stable():
    tokens = [
        OcrToken(token_id="T1", text="TOTALT", polygon=[[0.1, 0.9], [0.2, 0.9], [0.2, 0.95], [0.1, 0.95]]),
        OcrToken(token_id="T2", text="100,00", polygon=[[0.7, 0.9], [0.9, 0.9], [0.9, 0.95], [0.7, 0.95]]),
    ]
    lines = build_lines_from_tokens(tokens)
    assert len(lines) == 1
    assert "TOTALT" in lines[0].text
    assert "100,00" in lines[0].text


def test_text_only_tokens():
    text = "Line A\nLine B"
    tokens = tokens_from_text_lines(text)
    assert len(tokens) == 2


def test_extract_document_on_synthetic_image():
    from io import BytesIO

    from PIL import Image, ImageDraw

    img = Image.new("RGB", (400, 200), "white")
    draw = ImageDraw.Draw(img)
    draw.text((20, 20), "REMA 1000", fill="black")
    buf = BytesIO()
    img.save(buf, format="JPEG")
    doc = OcrService().extract_document(buf.getvalue())
    assert doc.schema_version == "1.0.0"
    assert doc.engine == "rapidocr"
