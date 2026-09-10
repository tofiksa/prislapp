from app.parsers.base import ParsedReceipt
from app.parsers.rema1000 import detect_rema1000, parse_rema1000
from app.parsers.generic import parse_generic
from app.parsers.retail import parse_retail
import re


def parse_receipt_text(text: str) -> ParsedReceipt:
    if detect_rema1000(text):
        return parse_rema1000(text)
    if re.search(r"(?im)^EP\s|europris", text):
        return parse_retail(text, "europris")
    if re.search(r"(?im)^normal\b", text):
        return parse_retail(text, "normal")
    return parse_generic(text)
