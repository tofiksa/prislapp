"""Layout building from OCR tokens — rows, sections and reading order."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from app.domain.receipt_extraction import OcrDocument, OcrLine, OcrToken, SectionType

_SECTION_LABELS: list[tuple[re.Pattern[str], SectionType]] = [
    (re.compile(r"(?i)^(?:produktnavn|vare\s+navn|artikkel)"), "items"),
    (re.compile(r"(?i)^(?:sum\s+\d+\s+varer|total(?:t)?|i\s+alt|å\s+betale)"), "totals"),
    (re.compile(r"(?i)^(?:kontant|kort|visa|betaling|vekslepenger|tilbake)"), "payment"),
    (re.compile(r"(?i)^(?:mva|moms|mva-grunnlag|avgift)"), "tax"),
    (re.compile(r"(?i)^(?:kortinnehaverens|takk\s+for)"), "footer"),
    (re.compile(r"(?i)^(?:salgskvittering|rema\s*1000|normal|kiwi|europris|^ep\b)"), "header"),
]


@dataclass
class LayoutLine:
    line_id: str
    text: str
    token_ids: tuple[str, ...]
    section: SectionType
    reading_order: int
    y_center: float = 0.0


def _classify_section(text: str, current: SectionType) -> SectionType:
    for pattern, section in _SECTION_LABELS:
        if pattern.search(text):
            return section
    return current


def build_lines_from_tokens(tokens: list[OcrToken]) -> list[LayoutLine]:
    """Group tokens into rows by vertical overlap, sort by reading order."""
    if not tokens:
        return []

    indexed = []
    for token in tokens:
        if token.polygon:
            ys = [p[1] for p in token.polygon]
            xs = [p[0] for p in token.polygon]
            y_center = sum(ys) / len(ys)
            height = max(ys) - min(ys) if ys else 0.02
            x_min = min(xs)
        else:
            y_center = len(indexed) * 0.02
            height = 0.02
            x_min = 0.0
        indexed.append((y_center, height, x_min, token))

    indexed.sort(key=lambda t: (t[0], t[2]))

    rows: list[list[tuple[float, float, float, OcrToken]]] = []
    for entry in indexed:
        y_center, height, x_min, token = entry
        placed = False
        for row in rows:
            row_y = row[0][0]
            row_h = row[0][1]
            threshold = max(0.005, min(height, row_h) * 0.5)
            if abs(y_center - row_y) <= threshold:
                row.append(entry)
                placed = True
                break
        if not placed:
            rows.append([entry])

    lines: list[LayoutLine] = []
    current_section: SectionType = "header"
    for order, row in enumerate(rows):
        row.sort(key=lambda t: t[2])
        token_ids = tuple(t[3].token_id for t in row)
        text = " ".join(t[3].text for t in row if t[3].text)
        y_center = sum(t[0] for t in row) / len(row)
        current_section = _classify_section(text, current_section)
        lines.append(
            LayoutLine(
                line_id=f"L{order:04d}",
                text=text,
                token_ids=token_ids,
                section=current_section,
                reading_order=order,
                y_center=y_center,
            ),
        )
    return lines


def build_lines_from_text(text: str) -> list[LayoutLine]:
    """Text-only adapter — no geometry, line IDs only."""
    current_section: SectionType = "header"
    lines: list[LayoutLine] = []
    for i, raw in enumerate(text.splitlines()):
        stripped = raw.strip()
        if not stripped:
            continue
        current_section = _classify_section(stripped, current_section)
        lines.append(
            LayoutLine(
                line_id=f"L{i:04d}",
                text=stripped,
                token_ids=(f"T{i:04d}",),
                section=current_section,
                reading_order=len(lines),
            ),
        )
    return lines


def document_to_layout_lines(document: OcrDocument) -> list[LayoutLine]:
    if document.lines:
        return [
            LayoutLine(
                line_id=line.line_id,
                text=_line_text(document, line),
                token_ids=line.token_ids,
                section=line.section,
                reading_order=line.reading_order,
            )
            for line in sorted(document.lines, key=lambda ln: ln.reading_order)
        ]
    return build_lines_from_tokens(list(document.tokens))


def _line_text(document: OcrDocument, line: OcrLine) -> str:
    token_map = {t.token_id: t.text for t in document.tokens}
    return " ".join(token_map.get(tid, "") for tid in line.token_ids if token_map.get(tid))


def tokens_from_text_lines(text: str) -> tuple[OcrToken, ...]:
    """Create synthetic tokens from plain text for text-only pipeline."""
    tokens: list[OcrToken] = []
    for i, raw in enumerate(text.splitlines()):
        stripped = raw.strip()
        if stripped:
            tokens.append(OcrToken(token_id=f"T{i:04d}", text=stripped))
    return tuple(tokens)


def enrich_document_with_layout(document: OcrDocument) -> OcrDocument:
    layout_lines = build_lines_from_tokens(list(document.tokens))
    ocr_lines = tuple(
        OcrLine(
            line_id=line.line_id,
            token_ids=line.token_ids,
            section=line.section,
            reading_order=line.reading_order,
        )
        for line in layout_lines
    )
    return OcrDocument(
        schema_version=document.schema_version,
        engine=document.engine,
        model_id=document.model_id,
        preprocess_version=document.preprocess_version,
        original_width=document.original_width,
        original_height=document.original_height,
        document_id=document.document_id,
        tokens=document.tokens,
        lines=ocr_lines,
        plain_text=document.plain_text,
        normalized_text=document.normalized_text,
        diagnostics=document.diagnostics,
    )
