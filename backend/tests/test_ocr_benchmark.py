"""Benchmark tooling tests."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = BACKEND_ROOT / "tests" / "fixtures" / "ocr"


def test_manifest_loads():
    manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["fixtures"]) >= 6
    ids = {f["id"] for f in manifest["fixtures"]}
    assert "baseline-rema-metro-split-lines" in ids


def test_benchmark_metrics_with_fake_predictions():
    from scripts.benchmark_receipts import FixtureResult, _aggregate

    results = [
        FixtureResult("a", "development", Decimal("10.00"), Decimal("10.00"), True, False, True, True, False, 1.0),
        FixtureResult("b", "development", Decimal("20.00"), None, False, True, True, None, False, 1.0),
        FixtureResult("c", "development", Decimal("30.00"), Decimal("25.00"), False, False, True, None, True, 1.0),
    ]
    agg = _aggregate(results)
    assert agg["false_confident_total_count"] == 1
    assert agg["total_exact_rate"] == pytest.approx(1 / 3)
    assert agg["total_coverage"] == pytest.approx(2 / 3)


def test_benchmark_cli_parser_mode(tmp_path):
    from scripts.benchmark_receipts import run_benchmark

    output = tmp_path / "report.json"
    report = run_benchmark("parser", "development", output)
    assert output.exists()
    assert "aggregate" in report
    assert report["mode"] == "parser"
