#!/usr/bin/env python3
"""Line-level receipt evaluation: which OCR lines should become items, and which should not.

Fixture format (one OCR line per row, prefixed with a label):

    + Q LETTMELK 1% 15% 31,40        item line — must become exactly one item
    + BROKKOLI 29,90 => BROKKOLI ; 29.90   optional expected name ; line_total
    ~ 1,045kg × kr 29,90             modifier of the item above (weight, discount) — not its own item
    - Sum 7 varer 158,83             must NOT become an item
    # comment                        ignored

Usage:
    python scripts/evaluate_receipt_lines.py                 # evaluate all fixtures
    python scripts/evaluate_receipt_lines.py path/to/file.txt
    python scripts/evaluate_receipt_lines.py --draft receipt.png > tests/fixtures/ocr/lines/new.txt
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.parsers.base import ParsedReceiptItem  # noqa: E402
from app.services.receipt_extraction_service import parse_receipt_text_v2  # noqa: E402

LINES_DIR = BACKEND_ROOT / "tests" / "fixtures" / "ocr" / "lines"
_AMOUNT = re.compile(r"-?\d+[,.]\d{2}")
_LABELS = {"+", "~", "-"}


@dataclass
class LabelledLine:
    number: int
    label: str
    text: str
    expected_name: str | None = None
    expected_total: Decimal | None = None


@dataclass
class LineIssue:
    kind: str  # missed | unexpected | wrong_value
    line: LabelledLine | None
    detail: str


@dataclass
class FixtureReport:
    path: Path
    expected_items: int
    predicted_items: int
    issues: list[LineIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def parse_fixture(content: str) -> list[LabelledLine]:
    lines: list[LabelledLine] = []
    for number, raw in enumerate(content.splitlines(), start=1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        label, _, rest = raw.partition(" ")
        if label not in _LABELS:
            raise ValueError(f"line {number}: expected label '+', '~' or '-', got {raw!r}")
        text, _, expectation = rest.partition(" => ")
        entry = LabelledLine(number=number, label=label, text=text.strip())
        if expectation:
            name, _, total = expectation.partition(";")
            entry.expected_name = name.strip() or None
            entry.expected_total = Decimal(total.strip().replace(",", ".")) if total.strip() else None
        lines.append(entry)
    return lines


def _default_total(text: str) -> Decimal | None:
    amounts = _AMOUNT.findall(text)
    return Decimal(amounts[-1].replace(",", ".")) if amounts else None


def _line_matches_item(line: LabelledLine, item: ParsedReceiptItem) -> bool:
    return item.raw_name.strip() and line.text.startswith(item.raw_name.strip())


def evaluate(lines: list[LabelledLine]) -> tuple[list[LineIssue], int, int]:
    text = "\n".join(line.text for line in lines)
    _, parsed = parse_receipt_text_v2(text)
    remaining = list(parsed.items)
    issues: list[LineIssue] = []
    expected = [line for line in lines if line.label == "+"]

    for line in expected:
        match = next((item for item in remaining if _line_matches_item(line, item)), None)
        if match is None:
            issues.append(LineIssue("missed", line, "no item extracted from this line"))
            continue
        remaining.remove(match)
        want_total = line.expected_total if line.expected_total is not None else _default_total(line.text)
        if want_total is not None and match.line_total != want_total:
            issues.append(LineIssue("wrong_value", line, f"line_total {match.line_total} != expected {want_total}"))
        if line.expected_name is not None and match.raw_name.strip() != line.expected_name:
            issues.append(LineIssue("wrong_value", line, f"name {match.raw_name!r} != expected {line.expected_name!r}"))

    for item in remaining:
        source = next((line for line in lines if line.label != "+" and _line_matches_item(line, item)), None)
        issues.append(LineIssue("unexpected", source, f"item {item.raw_name!r} {item.line_total} should not exist"))

    return issues, len(expected), len(parsed.items)


def evaluate_file(path: Path) -> FixtureReport:
    issues, expected, predicted = evaluate(parse_fixture(path.read_text(encoding="utf-8")))
    return FixtureReport(path=path, expected_items=expected, predicted_items=predicted, issues=issues)


def draft_from_image(image_path: Path) -> str:
    """OCR an image and pre-label lines with the current parser's guess, for a human to correct."""
    from app.services.ocr_service import OcrService

    text = OcrService().extract_text(image_path.read_bytes())
    _, parsed = parse_receipt_text_v2(text)
    remaining = list(parsed.items)
    out = [f"# draft from {image_path.name} — labels are the parser's guess; correct them by hand"]
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        probe = LabelledLine(0, "+", stripped)
        match = next((item for item in remaining if _line_matches_item(probe, item)), None)
        if match is not None:
            remaining.remove(match)
        out.append(f"{'+' if match else '-'} {stripped}")
    return "\n".join(out) + "\n"


def _print_report(report: FixtureReport) -> None:
    status = "OK  " if report.ok else "FAIL"
    print(f"{status} {report.path.name}: expected {report.expected_items} items, got {report.predicted_items}")
    for issue in report.issues:
        where = f"line {issue.line.number} [{issue.line.label}] {issue.line.text!r}" if issue.line else "(no source line)"
        print(f"     {issue.kind:<11} {where}: {issue.detail}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--draft", type=Path, help="OCR an image and print a pre-labelled fixture")
    args = parser.parse_args()

    if args.draft:
        sys.stdout.write(draft_from_image(args.draft))
        return 0

    paths = args.paths or sorted(LINES_DIR.glob("*.txt"))
    reports = [evaluate_file(path) for path in paths]
    for report in reports:
        _print_report(report)
    failed = sum(not r.ok for r in reports)
    print(f"\n{len(reports) - failed}/{len(reports)} fixtures pass")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
