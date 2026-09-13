from app.parsers.base import ParsedReceipt


def parse_receipt_text(text: str) -> ParsedReceipt:
    """Parse receipt text using the unified extraction pipeline."""
    from app.services.receipt_extraction_service import parse_receipt_text_v2

    _, parsed = parse_receipt_text_v2(text)
    return parsed
