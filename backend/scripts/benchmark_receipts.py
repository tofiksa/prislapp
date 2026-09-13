#!/usr/bin/env python3
"""Benchmark receipt parsing quality against fixture ground truth."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.domain.money import display_nok  # noqa: E402
from app.parsers import parse_receipt_text  # noqa: E402
from app.services.ocr_service import OcrService  # noqa: E402
from app.services.receipt_extraction_service import parse_receipt_text_v2  # noqa: E402

FIXTURES_DIR = BACKEND_ROOT / "tests" / "fixtures" / "ocr"
MANIFEST_PATH = FIXTURES_DIR / "manifest.json"


@dataclass
class Prediction:
    chain: str | None
    branch_text: str | None
    printed_total: Decimal | None
    item_count: int
    store_name: str | None


@dataclass
class FixtureResult:
    fixture_id: str
    split: str
    expected_total: Decimal | None
    predicted_total: Decimal | None
    total_exact: bool | None
    total_abstained: bool
    chain_match: bool | None
    branch_match: bool | None
    false_confident_total: bool
    elapsed_ms: float
    known_bug: str | None = None
    error: str | None = None


def _git_revision() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
            cwd=BACKEND_ROOT.parent,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _resolve_source(source: dict) -> Path:
    return (FIXTURES_DIR / source["file"]).resolve()


def _expected_decimal(value) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _predict_from_text(text: str) -> Prediction:
    extraction, parsed = parse_receipt_text_v2(text)
    return Prediction(
        chain=extraction.store.chain,
        branch_text=extraction.store.branch_text,
        printed_total=extraction.total.printed_total,
        item_count=len(parsed.items),
        store_name=parsed.store_name,
    )


def _predict_from_image(path: Path) -> Prediction:
    start = time.perf_counter()
    ocr = OcrService()
    text = ocr.extract_text(path.read_bytes())
    pred = _predict_from_text(text)
    _ = time.perf_counter() - start
    return pred


def _branch_matches(expected: dict, pred: Prediction) -> bool | None:
    exp_branch = expected.get("branch_text")
    if exp_branch is None:
        if expected.get("observed_contains"):
            return expected["observed_contains"].upper() in (pred.store_name or "").upper()
        return None
    if pred.branch_text is None:
        return False
    return exp_branch.lower() in pred.branch_text.lower()


def _evaluate_fixture(entry: dict, mode: str) -> FixtureResult:
    source = entry["source"]
    expected = entry["expected"]
    start = time.perf_counter()
    error = None
    try:
        if mode == "parser" or source["type"] == "text":
            text = _resolve_source(source).read_text(encoding="utf-8")
            pred = _predict_from_text(text)
        else:
            pred = _predict_from_image(_resolve_source(source))
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return FixtureResult(
            fixture_id=entry["id"],
            split=entry["split"],
            expected_total=_expected_decimal(expected.get("printed_total")),
            predicted_total=None,
            total_exact=False,
            total_abstained=True,
            chain_match=False,
            branch_match=False,
            false_confident_total=False,
            elapsed_ms=elapsed_ms,
            known_bug=entry.get("known_bug"),
            error=str(exc),
        )

    elapsed_ms = (time.perf_counter() - start) * 1000
    exp_total = _expected_decimal(expected.get("printed_total"))
    pred_total = pred.printed_total

    total_exact: bool | None
    if exp_total is None:
        total_exact = pred_total is None
    else:
        total_exact = pred_total == exp_total

    exp_chain = expected.get("chain")
    chain_match = None if exp_chain is None else pred.chain == exp_chain

    false_confident = False
    if exp_total is not None and pred_total is not None and pred_total != exp_total:
        false_confident = True
    if exp_total is None and pred_total is not None:
        false_confident = True

    return FixtureResult(
        fixture_id=entry["id"],
        split=entry["split"],
        expected_total=exp_total,
        predicted_total=pred_total,
        total_exact=total_exact,
        total_abstained=pred_total is None,
        chain_match=chain_match,
        branch_match=_branch_matches(expected, pred),
        false_confident_total=false_confident,
        elapsed_ms=elapsed_ms,
        known_bug=entry.get("known_bug"),
    )


def _aggregate(results: list[FixtureResult]) -> dict:
    with_expected = [r for r in results if r.expected_total is not None]
    total_correct = sum(1 for r in with_expected if r.total_exact)
    total_coverage = sum(1 for r in with_expected if r.predicted_total is not None)
    chain_cases = [r for r in results if r.chain_match is not None]
    chain_correct = sum(1 for r in chain_cases if r.chain_match)
    branch_cases = [r for r in results if r.branch_match is not None]
    branch_correct = sum(1 for r in branch_cases if r.branch_match)
    false_confident = sum(1 for r in results if r.false_confident_total)

    return {
        "total_precision": total_correct / total_coverage if total_coverage else None,
        "total_exact_rate": total_correct / len(with_expected) if with_expected else None,
        "total_coverage": total_coverage / len(with_expected) if with_expected else None,
        "chain_exact_rate": chain_correct / len(chain_cases) if chain_cases else None,
        "branch_exact_rate": branch_correct / len(branch_cases) if branch_cases else None,
        "false_confident_total_count": false_confident,
        "abstention_count": sum(1 for r in results if r.total_abstained),
    }


def run_benchmark(mode: str, split: str | None, output: Path) -> dict:
    manifest = _load_manifest()
    fixtures = manifest["fixtures"]
    if split:
        fixtures = [f for f in fixtures if f["split"] == split]

    results = [_evaluate_fixture(entry, mode) for entry in fixtures]
    report = {
        "mode": mode,
        "split_filter": split,
        "git_revision": _git_revision(),
        "platform": platform.platform(),
        "parser_version": "receipt_extraction_service/1.0.0",
        "ocr_engine": "rapidocr/3.9.2",
        "aggregate": _aggregate(results),
        "fixtures": [
            {
                "id": r.fixture_id,
                "split": r.split,
                "expected_total": display_nok(r.expected_total) if r.expected_total is not None else None,
                "predicted_total": display_nok(r.predicted_total) if r.predicted_total is not None else None,
                "total_exact": r.total_exact,
                "chain_match": r.chain_match,
                "branch_match": r.branch_match,
                "false_confident_total": r.false_confident_total,
                "elapsed_ms": round(r.elapsed_ms, 1),
                "known_bug": r.known_bug,
                "error": r.error,
            }
            for r in results
        ],
    }
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark receipt OCR/parsing quality")
    parser.add_argument(
        "--mode",
        choices=["parser", "image"],
        default="parser",
        help="parser=text fixtures only; image=OCR then parse",
    )
    parser.add_argument("--split", choices=["development", "holdout"], default=None)
    parser.add_argument("--output", type=Path, required=True, help="Output JSON report path")
    args = parser.parse_args()

    report = run_benchmark(args.mode, args.split, args.output)
    agg = report["aggregate"]
    print(f"Wrote report to {args.output}")
    print(f"Total exact rate: {agg.get('total_exact_rate')}")
    print(f"False confident totals: {agg.get('false_confident_total_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
