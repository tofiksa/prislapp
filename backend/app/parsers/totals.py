"""Total candidate collection and selection for Norwegian receipts."""

from __future__ import annotations

import re
import uuid
import unicodedata
from dataclasses import dataclass
from decimal import Decimal

from app.domain.receipt_extraction import FieldCandidate, ReasonCode, TotalExtraction
from app.parsers.amounts import extract_amounts_from_line, normalize_money_text, parse_money_amount


def _normalize_label(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    ).lower()

# Final trade sum labels (higher priority)
_FINAL_TOTAL_PATTERNS = [
    (re.compile(r"(?i)^total(?:t)?\s*:?\s*(.*)$"), "total_label"),
    (re.compile(r"(?i)^(?:å|a)\s+betale\s*:?\s*(.*)$"), "a_betale"),
    (re.compile(r"(?i)^til\s+betaling\s*:?\s*(.*)$"), "til_betaling"),
    (re.compile(r"(?i)^i\s+alt\s+kr\.?\s*:?\s*(.*)$"), "i_alt_kr"),
    (re.compile(r"(?i)^sum\s+\d+\s+varer\s+(.*)$"), "sum_n_varer"),
]

# Subtotals / intermediate — lower priority, not payment
_SUBTOTAL_PATTERNS = [
    re.compile(r"(?i)^sum\s*:?\s*(.*)$"),
    re.compile(r"(?i)^delsum\s*:?\s*(.*)$"),
    re.compile(r"(?i)^subtotal\s*:?\s*(.*)$"),
]

# Never trade sum — payment/tax/change
_NEGATIVE_LABEL_PATTERNS = [
    re.compile(r"(?i)^(?:kontant|kort|visa|bank|terminal|betaling|gavekort)\b"),
    re.compile(r"(?i)^(?:vekslepenger|tilbake|byttepenger|change)\b"),
    re.compile(r"(?i)^(?:mva|moms|mva-grunnlag|avgift)\b"),
    re.compile(r"(?i)^(?:rabatt|du\s+sparte)\b"),
    re.compile(r"(?i)^(?:org\.?\s*nr|tlf|telefon)\b"),
]

_FINAL_LABEL_ONLY = re.compile(
    r"(?i)^(?:total(?:t)?|(?:å|a)\s+betale|til\s+betaling|i\s+alt\s+kr\.?|sum\s+\d+\s+varer)\s*:?\s*$",
)


@dataclass
class LineContext:
    line_id: str
    text: str
    section: str = "unknown"
    next_line_text: str | None = None
    prev_line_text: str | None = None


@dataclass
class TotalCandidateInternal:
    candidate_id: str
    amount: Decimal
    rule_id: str
    line_id: str
    label_text: str
    priority: int
    is_final: bool
    evidence_token_ids: tuple[str, ...] = ()


def _is_negative_label(line: str) -> bool:
    normalized = normalize_money_text(line)
    return any(p.search(normalized) for p in _NEGATIVE_LABEL_PATTERNS)


def _extract_amount_from_remainder(remainder: str) -> Decimal | None:
    if not remainder.strip():
        return None
    parsed = parse_money_amount(remainder)
    return parsed.value


def _collect_from_line(ctx: LineContext) -> list[TotalCandidateInternal]:
    candidates: list[TotalCandidateInternal] = []
    line = ctx.text.strip()
    if not line or _is_negative_label(line):
        return candidates

    normalized = _normalize_label(line)

    for pattern, rule_id in _FINAL_TOTAL_PATTERNS:
        match = pattern.match(normalized)
        if match:
            remainder = match.group(1).strip() if match.lastindex else ""
            amount = _extract_amount_from_remainder(remainder)
            if amount is None and ctx.next_line_text:
                next_amount = parse_money_amount(ctx.next_line_text.strip())
                if next_amount.value is not None and not _is_negative_label(ctx.next_line_text):
                    amount = next_amount.value
                    rule_id = f"{rule_id}_next_line"
            if amount is not None:
                candidates.append(
                    TotalCandidateInternal(
                        candidate_id=str(uuid.uuid4()),
                        amount=amount,
                        rule_id=rule_id,
                        line_id=ctx.line_id,
                        label_text=line,
                        priority=100 if rule_id.startswith("sum_n_varer") else 90,
                        is_final=True,
                    ),
                )
            return candidates

    if _FINAL_LABEL_ONLY.match(normalized) and ctx.next_line_text:
        next_amount = parse_money_amount(ctx.next_line_text.strip())
        if next_amount.value is not None and not _is_negative_label(ctx.next_line_text):
            candidates.append(
                TotalCandidateInternal(
                    candidate_id=str(uuid.uuid4()),
                    amount=next_amount.value,
                    rule_id="label_only_next_line",
                    line_id=ctx.line_id,
                    label_text=line,
                    priority=85,
                    is_final=True,
                ),
            )
        return candidates

    for pattern in _SUBTOTAL_PATTERNS:
        match = pattern.match(normalized)
        if match:
            amount = _extract_amount_from_remainder(match.group(1))
            if amount is not None:
                candidates.append(
                    TotalCandidateInternal(
                        candidate_id=str(uuid.uuid4()),
                        amount=amount,
                        rule_id="subtotal",
                        line_id=ctx.line_id,
                        label_text=line,
                        priority=40,
                        is_final=False,
                    ),
                )
            return candidates

    return candidates


def collect_total_candidates(lines: list[LineContext]) -> list[TotalCandidateInternal]:
    all_candidates: list[TotalCandidateInternal] = []
    for i, ctx in enumerate(lines):
        enriched = LineContext(
            line_id=ctx.line_id,
            text=ctx.text,
            section=ctx.section,
            next_line_text=lines[i + 1].text if i + 1 < len(lines) else None,
            prev_line_text=lines[i - 1].text if i > 0 else None,
        )
        all_candidates.extend(_collect_from_line(enriched))
    return all_candidates


def select_printed_total(
    candidates: list[TotalCandidateInternal],
    computed_items_total: Decimal | None = None,
    computed_items_complete: bool = False,
) -> TotalExtraction:
    if not candidates:
        reason = (ReasonCode.TOTAL_NOT_FOUND,)
        return TotalExtraction(
            printed_total=None,
            computed_items_total=computed_items_total,
            computed_items_complete=computed_items_complete,
            state="missing",
            reason_codes=reason,
        )

    final_candidates = [c for c in candidates if c.is_final]
    if not final_candidates:
        final_candidates = candidates

    # Group by amount
    by_amount: dict[Decimal, list[TotalCandidateInternal]] = {}
    for c in final_candidates:
        by_amount.setdefault(c.amount, []).append(c)

    if len(by_amount) > 1:
        # Multiple conflicting final totals
        field_candidates = tuple(
            FieldCandidate(
                candidate_id=c.candidate_id,
                value_decimal=c.amount,
                value_text=str(c.amount),
                rule_id=c.rule_id,
                state="uncertain",
                rank_score=float(c.priority),
            )
            for c in final_candidates
        )
        return TotalExtraction(
            printed_total=None,
            computed_items_total=computed_items_total,
            computed_items_complete=computed_items_complete,
            state="uncertain",
            candidates=field_candidates,
            reason_codes=(ReasonCode.TOTAL_AMBIGUOUS,),
        )

    # Single amount — pick highest priority candidate
    amount = next(iter(by_amount))
    group = by_amount[amount]
    best = max(group, key=lambda c: c.priority)

    field_candidates = tuple(
        FieldCandidate(
            candidate_id=c.candidate_id,
            value_decimal=c.amount,
            value_text=str(c.amount),
            rule_id=c.rule_id,
            state="accepted" if c.candidate_id == best.candidate_id else "uncertain",
            rank_score=float(c.priority),
        )
        for c in final_candidates
    )

    reconciliation_hint = None
    reason_codes: tuple[ReasonCode, ...] = ()
    if (
        computed_items_total is not None
        and computed_items_complete
        and computed_items_total != amount
    ):
        reconciliation_hint = "items_mismatch"
        reason_codes = (ReasonCode.TOTAL_ITEMS_MISMATCH,)

    return TotalExtraction(
        printed_total=amount,
        computed_items_total=computed_items_total,
        computed_items_complete=computed_items_complete,
        state="accepted",
        selected_candidate_id=best.candidate_id,
        candidates=field_candidates,
        reason_codes=reason_codes,
    )


def extract_totals_from_text(
    text: str,
    *,
    computed_items_total: Decimal | None = None,
    computed_items_complete: bool = False,
    excluded_line_ids: set[str] | None = None,
) -> TotalExtraction:
    """Text-only total extraction entry point."""
    lines_raw = text.splitlines()
    contexts = [
        LineContext(line_id=f"L{i:04d}", text=line.strip())
        for i, line in enumerate(lines_raw)
        if line.strip()
    ]
    if excluded_line_ids:
        contexts = [c for c in contexts if c.line_id not in excluded_line_ids]

    candidates = collect_total_candidates(contexts)
    return select_printed_total(candidates, computed_items_total, computed_items_complete)


def total_line_patterns_for_exclusion() -> list[re.Pattern[str]]:
    """Patterns for lines that must not become product items."""
    return [
        re.compile(p.pattern) for p, _ in _FINAL_TOTAL_PATTERNS
    ] + _SUBTOTAL_PATTERNS + _NEGATIVE_LABEL_PATTERNS
