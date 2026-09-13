# OCR-00 handoff

## Delivered

- Fixture manifest: `backend/tests/fixtures/ocr/manifest.json` (15 fixtures, development + holdout splits)
- Text fixtures under `backend/tests/fixtures/ocr/text/`
- Benchmark CLI: `backend/scripts/benchmark_receipts.py`

## Commands

```bash
cd backend
.venv/bin/python -m pytest tests/test_ocr_benchmark.py tests/test_ocr_service.py tests/test_receipt_images.py tests/test_rema1000_parser.py -q
.venv/bin/python scripts/benchmark_receipts.py --mode parser --split development --output /tmp/ocr-dev.json
.venv/bin/python scripts/benchmark_receipts.py --mode image --split holdout --output /tmp/ocr-holdout.json
```

## Baseline (development split, parser mode)

- Total exact rate: **90%** (9/10 with expected total)
- False confident totals: **1** (edge-conflicting-totals — expected until fixed in pipeline; now abstains)
- Known bugs from plan chapter 3 are tracked in manifest `known_bug` fields

## Verified image ground truth

| Image | Total | Items |
|---|---:|---:|
| rema1000-metro-senter.png | 158.83 | 7 |
| normal-triaden.png | 100.00 | 6 |
| europris-normal-triaden.png | null (cropped/multi-doc) | — |

## Data collection blocker

30+ consented receipts not yet collected. Tooling ready; see manifest `collection.status`.
