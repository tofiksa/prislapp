from app.parsers.base import ParsedReceipt
from app.parsers.rema1000 import detect_rema1000, parse_rema1000


def parse_receipt_text(text: str) -> ParsedReceipt:
    if detect_rema1000(text):
        return parse_rema1000(text)
    return ParsedReceipt()
