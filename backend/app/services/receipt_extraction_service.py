"""Receipt extraction pipeline — store, total and item parsing with quality signals."""

from __future__ import annotations

import re
from decimal import Decimal

from app.domain.receipt_extraction import ExtractionProvenance, ReasonCode, ReceiptExtractionResult, ReceiptQuality
from app.parsers.base import ParsedReceipt, ParsedReceiptItem
from app.parsers.generic import parse_date
from app.parsers.layout import build_lines_from_text, document_to_layout_lines
from app.parsers.rema1000 import parse_rema1000
from app.parsers.retail import parse_retail
from app.parsers.store_detection import UserStoreContext, detect_store
from app.parsers.totals import LineContext, collect_total_candidates, select_printed_total, total_line_patterns_for_exclusion

PIPELINE_VERSION = "1.0.0"
RULES_VERSION = "1.0.0"

_ITEM_LINE = re.compile(r"^(.+?)\s+(-?\d+[,.]\d{2})\s*$")
_MVA_ITEM = re.compile(r"^(.+?)\s+(?:15|25)%?\s+(-?\d+[,.]\d{2})\s*$")
_EXCLUSION_PATTERNS = total_line_patterns_for_exclusion()


def _line_is_excluded(line_text: str) -> bool:
    normalized = line_text.strip()
    if not normalized:
        return True
    return any(p.search(normalized) for p in _EXCLUSION_PATTERNS)


def _parse_items_generic(lines: list[str], excluded_ids: set[str], line_id_map: dict[str, str]) -> list[ParsedReceiptItem]:
    items: list[ParsedReceiptItem] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or _line_is_excluded(stripped):
            continue
        match = _MVA_ITEM.match(stripped) or _ITEM_LINE.match(stripped)
        if match and any(c.isalpha() for c in match.group(1)):
            amount = Decimal(match.group(2).replace(",", "."))
            if amount >= 0:
                items.append(ParsedReceiptItem(raw_name=match.group(1).strip(), line_total=amount))
    return items


def _select_item_parser(chain: str | None) -> str:
    if chain == "rema1000":
        return "rema1000"
    if chain == "europris":
        return "europris"
    if chain == "normal":
        return "normal"
    return "generic"


def _parse_items_for_chain(text: str, chain: str | None) -> tuple[list[ParsedReceiptItem], bool]:
    parser = _select_item_parser(chain)
    if parser == "rema1000":
        parsed = parse_rema1000(text)
        return parsed.items, True
    if parser in {"europris", "normal"}:
        parsed = parse_retail(text, parser)
        return parsed.items, True
    layout = build_lines_from_text(text)
    line_id_map = {ln.line_id: ln.text for ln in layout}
    excluded = {ln.line_id for ln in layout if _line_is_excluded(ln.text)}
    items = _parse_items_generic(list(line_id_map.values()), excluded, line_id_map)
    return items, False


def extract_from_text(
    text: str,
    *,
    user_store_contexts: list[UserStoreContext] | None = None,
) -> tuple[ReceiptExtractionResult, ParsedReceipt]:
    """Main text-only extraction pipeline."""
    if not text or not text.strip():
        result = ReceiptExtractionResult(quality="unreadable")
        result.total.reason_codes = (ReasonCode.TOTAL_NOT_FOUND,)
        result.store.reason_codes = (ReasonCode.STORE_UNRESOLVED,)
        return result, ParsedReceipt()

    store = detect_store(text, user_store_contexts=user_store_contexts)
    layout = build_lines_from_text(text)

    items, chain_parser_used = _parse_items_for_chain(text, store.chain)
    computed_total = sum((i.line_total for i in items), Decimal("0")) if items else None
    items_complete = chain_parser_used and len(items) > 0

    line_contexts = [
        LineContext(line_id=ln.line_id, text=ln.text, section=ln.section)
        for ln in layout
    ]
    candidates = collect_total_candidates(line_contexts)
    total = select_printed_total(candidates, computed_total, items_complete)

    # Build ParsedReceipt for legacy compatibility
    store_name = store.observed_text
    parsed = ParsedReceipt(
        store_chain=store.chain,
        store_name=store_name,
        purchase_date=parse_date(text),
        total=total.printed_total,  # null when uncertain — no item sum fallback
        items=items,
    )

    quality: ReceiptQuality = "review_ready"
    if total.state != "accepted" or store.state != "accepted":
        quality = "review_required"
    if ReasonCode.MULTIPLE_DOCUMENTS in store.reason_codes:
        quality = "review_required"
        parsed.store_name = None
        parsed.total = None

    warnings: list[str] = []
    if total.computed_items_total and total.printed_total is None:
        warnings.append("computed_items_total_available_without_printed_total")
    if ReasonCode.BRANCH_UNRESOLVED in store.reason_codes:
        warnings.append("branch_unresolved")

    result = ReceiptExtractionResult(
        store=store,
        total=total,
        quality=quality,
        warnings=warnings,
        provenance=ExtractionProvenance(
            pipeline_version=PIPELINE_VERSION,
            rules_version=RULES_VERSION,
        ),
    )

    return result, parsed


def parse_receipt_text_v2(
    text: str,
    *,
    user_store_contexts: list[UserStoreContext] | None = None,
) -> tuple[ReceiptExtractionResult, ParsedReceipt]:
    """Public v2 entry — used by updated parse_receipt_text."""
    return extract_from_text(text, user_store_contexts=user_store_contexts)
