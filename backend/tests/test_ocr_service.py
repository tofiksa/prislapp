from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from app.services.ocr_service import OcrService


def _render_receipt_jpeg(text: str, *, rotate_clockwise_90: bool = False) -> bytes:
    image = Image.new("RGB", (1400, 500), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=72)
    draw.text((80, 180), text, fill="black", font=font)
    if rotate_clockwise_90:
        image = image.rotate(-90, expand=True)
    buffer = BytesIO()
    if rotate_clockwise_90:
        exif = Image.Exif()
        exif[0x0112] = 8  # rotate 90° CCW to display upright
        image.save(buffer, format="JPEG", quality=95, exif=exif)
    else:
        image.save(buffer, format="JPEG", quality=95)
    return buffer.getvalue()


def test_extract_text_reads_printed_receipt_header():
    image_bytes = _render_receipt_jpeg("REMA 1000 METRO SENTER")

    text = OcrService().extract_text(image_bytes)

    normalized = " ".join(text.upper().split())
    assert "REMA 1000" in normalized
    assert "placeholder" not in text.lower()


def test_extract_text_reads_exif_rotated_phone_photo():
    image_bytes = _render_receipt_jpeg("REMA 1000", rotate_clockwise_90=True)

    text = OcrService().extract_text(image_bytes)

    normalized = " ".join(text.upper().split())
    assert "REMA 1000" in normalized
