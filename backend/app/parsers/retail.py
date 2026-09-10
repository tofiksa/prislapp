import re
import unicodedata
from decimal import Decimal

from app.parsers.base import ParsedReceipt, ParsedReceiptItem
from app.parsers.generic import parse_date


def parse_retail(text: str, chain: str) -> ParsedReceipt:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    store_pattern = r"^EP\s+(.+?)(?:\s+Tlf.*)?$" if chain == "europris" else r"^Normal\s+(.+)$"
    store = next((line for line in lines if re.match(store_pattern, line, re.I)), chain.title())
    store = re.split(r"\s+Tlf", store, flags=re.I)[0]
    parsed = ParsedReceipt(store_chain=chain, store_name=store, purchase_date=parse_date(text))
    item_pattern = (r"^(.+?)\s+(?:15|25)%?\s+(\d+[,.]\d{2})(?:\s|$)" if chain == "europris"
                    else r"^(.+?)\s+(\d+[,.]\d{2})\s*[A-Z]?$")
    for line in lines:
        normalized = "".join(c for c in unicodedata.normalize("NFKD", line) if not unicodedata.combining(c)).lower()
        total = re.match(r"^(?:a betale|i alt kr\.?)\s+(\d+[,.]\d{2})", normalized)
        if total:
            parsed.total = Decimal(total.group(1).replace(",", "."))
            break
        if re.match(r"^(?:kontant|tilbake|vekslepenger|mva|sum|dato|org|tlf)\b", normalized):
            continue
        match = re.match(item_pattern, line)
        if match and any(c.isalpha() for c in match.group(1)):
            parsed.items.append(ParsedReceiptItem(raw_name=match.group(1), line_total=Decimal(match.group(2).replace(",", "."))))
    return parsed
