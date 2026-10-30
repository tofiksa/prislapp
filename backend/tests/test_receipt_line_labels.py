"""Line-level ground truth: each labelled OCR line must (not) become an item."""

from pathlib import Path

import pytest

from scripts.evaluate_receipt_lines import LINES_DIR, evaluate, evaluate_file, parse_fixture

FIXTURES = sorted(LINES_DIR.glob("*.txt"))


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_labelled_lines_match_parser(path: Path):
    report = evaluate_file(path)
    assert report.ok, "\n".join(
        f"{i.kind}: {i.line.text if i.line else '?'} — {i.detail}" for i in report.issues
    )


def test_evaluator_reports_missed_and_unexpected_lines():
    lines = parse_fixture(
        "- REMA 1000 METRO SENTER\n"
        "+ YOGHURT 15% 8,8O\n"
        "- Sum 1 varer 8,80\n"
    )
    issues, expected, _ = evaluate(lines)
    assert expected == 1
    assert [i.kind for i in issues] == ["missed"]


def test_fixture_rejects_unknown_label():
    with pytest.raises(ValueError):
        parse_fixture("* not a label\n")
