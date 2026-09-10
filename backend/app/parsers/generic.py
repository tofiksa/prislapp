"""Conservative fallback for Norwegian receipts; uncertain text remains for review."""
import re
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.parsers.base import ParsedReceipt, ParsedReceiptItem

DATE = re.compile(r"(\d{2})[./ -](\d{2})[./ -](\d{4}|\d{2})(?:\s+(\d{2}):(\d{2}))?")
ITEM = re.compile(r"^(.+?)\s+(-?\d+[,.]\d{2})\s*$")
TOTAL = re.compile(r"^(?:total|totalt|sum(?:\s+\d+\s+varer)?|å betale)\s*:?\s*(\d+[,.]\d{2})$", re.I)
PAYMENT = re.compile(r"^(?:visa|bank|kort|kontant|mva|moms|org|tlf|terminal|betaling|rabatt|du sparte)\b", re.I)


def parse_date(text: str) -> datetime | None:
    match = DATE.search(text)
    if not match:
        return None
    day, month, year, hour, minute = match.groups()
    try:
        return datetime(int(year) + (2000 if len(year) == 2 else 0), int(month), int(day),
                        int(hour or 0), int(minute or 0), tzinfo=ZoneInfo("Europe/Oslo"))
    except ValueError:
        return None


def parse_generic(text: str) -> ParsedReceipt:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    parsed = ParsedReceipt(purchase_date=parse_date(text))
    if lines:
        parsed.store_name = lines[0][:255]
    for line in lines:
        total = TOTAL.match(line)
        if total:
            parsed.total = Decimal(total.group(1).replace(",", "."))
            break
        if PAYMENT.match(line) or DATE.search(line):
            continue
        match = ITEM.match(line)
        if match and any(char.isalpha() for char in match.group(1)):
            amount = Decimal(match.group(2).replace(",", "."))
            if amount >= 0:
                parsed.items.append(ParsedReceiptItem(raw_name=match.group(1), line_total=amount))
    if parsed.total is None and parsed.items:
        parsed.total = sum((item.line_total for item in parsed.items), Decimal("0"))
    return parsed
