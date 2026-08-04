import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.parsers.base import ParsedReceipt, ParsedReceiptItem


REMA_HEADER_PATTERN = re.compile(r"(?i)rema\s*1000")
REMA_DATE_PATTERN = re.compile(r"(\d{2})\.(\d{2})\.(\d{2})\s+(\d{2}):(\d{2})")
REMA_STORE_LINE_PATTERN = re.compile(r"(?i)^rema\s*1000\s+(.+)$")
REMA_PRODUCT_LINE_PATTERN = re.compile(
    r"^(.+?)\s+(15|25)\s+(\d+[,.]\d{2})\s*$",
)
REMA_WEIGHT_LINE_PATTERN = re.compile(
    r"^\s*(\d+[,.]?\d*)\s*kg\s*x\s*kr\s*(\d+[,.]\d{2})\s*$",
    re.IGNORECASE,
)
REMA_TOTAL_PATTERN = re.compile(r"(?i)sum\s+\d+\s+varer\s+(\d+[,.]\d{2})")
STOP_SECTION_PATTERN = re.compile(r"(?i)kortinnehaverens")


def detect_rema1000(text: str) -> bool:
    header_lines = text.splitlines()[:15]
    return any(REMA_HEADER_PATTERN.search(line) for line in header_lines)


def _parse_norwegian_decimal(value: str) -> Decimal:
    return Decimal(value.replace(",", "."))


def _parse_rema_date(text: str) -> datetime | None:
    match = REMA_DATE_PATTERN.search(text)
    if not match:
        return None
    day, month, year, hour, minute = match.groups()
    full_year = 2000 + int(year)
    return datetime(full_year, int(month), int(day), int(hour), int(minute))


def _extract_store_name(lines: list[str]) -> str | None:
    for line in lines[:15]:
        match = REMA_STORE_LINE_PATTERN.match(line.strip())
        if match:
            store_suffix = match.group(1).strip()
            if store_suffix:
                return f"REMA 1000 {store_suffix}"
    return None


def parse_rema1000(text: str) -> ParsedReceipt:
    lines = text.splitlines()
    store_name = _extract_store_name(lines)
    purchase_date = _parse_rema_date(text)
    items: list[ParsedReceiptItem] = []
    pending_item: ParsedReceiptItem | None = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if STOP_SECTION_PATTERN.search(stripped):
            break

        weight_match = REMA_WEIGHT_LINE_PATTERN.match(line)
        if weight_match and pending_item is not None:
            quantity = _parse_norwegian_decimal(weight_match.group(1))
            unit_price = _parse_norwegian_decimal(weight_match.group(2))
            pending_item.quantity = quantity
            pending_item.unit_price = unit_price
            continue

        product_match = REMA_PRODUCT_LINE_PATTERN.match(stripped)
        if product_match:
            name = product_match.group(1).strip()
            price = _parse_norwegian_decimal(product_match.group(3))
            pending_item = ParsedReceiptItem(
                raw_name=name,
                line_total=price,
                quantity=Decimal("1"),
            )
            items.append(pending_item)
            continue

    total: Decimal | None = None
    total_match = REMA_TOTAL_PATTERN.search(text)
    if total_match:
        try:
            total = _parse_norwegian_decimal(total_match.group(1))
        except InvalidOperation:
            total = None

    if total is None and items:
        total = sum((item.line_total for item in items), Decimal("0"))

    return ParsedReceipt(
        store_chain="rema1000",
        store_name=store_name,
        purchase_date=purchase_date,
        total=total,
        items=items,
    )
