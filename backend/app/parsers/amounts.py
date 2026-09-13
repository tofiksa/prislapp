"""Norwegian receipt money parsing — pure functions, no side effects."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.domain.money import NOK_QUANTUM

_NBSP = "\u00a0"
_NARROW_NBSP = "\u202f"

_CURRENCY_PREFIX = re.compile(
    r"(?i)(?:nok|kr\.?)\s*",
)
# Amount with optional thousands separator and comma/dot decimal.
_AMOUNT_CORE = re.compile(
    r"(-?\d{1,3}(?:[ \u00a0\u202f.]?\d{3})*(?:[,.]\d{2})|-?\d+[,.]\d{2})",
)


@dataclass(frozen=True)
class MoneyParseResult:
    value: Decimal | None
    raw_match: str | None = None
    error: str | None = None
    ambiguous: bool = False


def normalize_money_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    normalized = normalized.replace(_NBSP, " ").replace(_NARROW_NBSP, " ")
    return normalized.strip()


def parse_money_amount(text: str, *, require_context: bool = False) -> MoneyParseResult:
    """Parse a Norwegian money amount from text.

    Supports 20,00 / 20.00 / 1 234,50 / NOK 1.234,50 / kr 20,00.
    Ambiguous forms like bare 1.234 without decimal context return ambiguous=True.
    """
    if not text or not text.strip():
        return MoneyParseResult(value=None, error="empty")

    normalized = normalize_money_text(text)
    normalized = _CURRENCY_PREFIX.sub("", normalized).strip()

    match = _AMOUNT_CORE.search(normalized)
    if not match:
        return MoneyParseResult(value=None, error="no_amount")

    raw = match.group(1)
    cleaned = raw.replace(" ", "").replace(_NBSP, "").replace(_NARROW_NBSP, "")

    # Detect ambiguous thousand separator without decimal part
    if re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+", cleaned) and "," not in cleaned:
        if require_context:
            return MoneyParseResult(value=None, raw_match=raw, ambiguous=True, error="ambiguous_thousands")
        # With context (e.g. total label), treat as thousands
        cleaned = cleaned.replace(".", "")

    if "," in cleaned and "." in cleaned:
        # Norwegian: dot thousands, comma decimal
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    elif cleaned.count(".") > 1:
        cleaned = cleaned.replace(".", "")

    try:
        value = Decimal(cleaned).quantize(NOK_QUANTUM)
    except InvalidOperation:
        return MoneyParseResult(value=None, raw_match=raw, error="invalid_decimal")

    return MoneyParseResult(value=value, raw_match=raw)


def extract_amounts_from_line(line: str) -> list[tuple[Decimal, str, int]]:
    """Return (value, raw_match, start_pos) for all money amounts in a line."""
    normalized = normalize_money_text(line)
    results: list[tuple[Decimal, str, int]] = []
    for match in _AMOUNT_CORE.finditer(normalized):
        parsed = parse_money_amount(match.group(0))
        if parsed.value is not None and not parsed.ambiguous:
            results.append((parsed.value, match.group(0), match.start()))
    return results


def is_likely_quantity_not_money(text_before: str) -> bool:
    """Heuristic: number preceded by quantity indicators is not money."""
    stripped = text_before.rstrip()
    return bool(re.search(r"(?:\d+[,.]?\d*\s*(?:kg|stk|x|×)\s*$|^\s*\d+[,.]?\d*\s*$)", stripped, re.I))


def is_org_number_context(line: str) -> bool:
    return bool(re.search(r"(?i)\borg\.?\s*(?:nr\.?)?\b", line))


def is_mva_percent_context(line: str) -> bool:
    return bool(re.search(r"\d+\s*%", line) and re.search(r"(?i)\bmva\b", line))
