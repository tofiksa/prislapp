from app.parsers import parse_receipt_text


class OcrService:
    """Placeholder OCR – stores stub text until real OCR is integrated."""

    def extract_text(self, image_bytes: bytes) -> str:
        if not image_bytes:
            return ""
        # Stub: acknowledge image received; real OCR (EasyOCR/PaddleOCR) replaces this.
        return "[OCR placeholder – image received, {} bytes]".format(len(image_bytes))
