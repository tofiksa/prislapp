# OCR-09 handoff — release verification

## Release candidate

Branch: `feat/handlehjelp-p0` (working branch at implementation time)

## Verification run

```bash
cd backend
.venv/bin/python -m pytest -q                    # 469 passed, 60 skipped (1 pre-existing flaky v2 price date test)
.venv/bin/python -m pytest tests/contracts/ -q   # 28 passed
.venv/bin/python scripts/benchmark_receipts.py --mode parser --split development --output /tmp/ocr-dev.json
```

## Critical regressions

- Six baseline text bugs: **fixed** (`test_receipt_extraction_pipeline.py`)
- False sum fallback: **removed**
- Worker + outbox fencing: **preserved** (`test_receipt_worker.py`, `test_job_outbox.py`)

## Blockers for broad rollout

- Holdout set has only 3 images; target 30+ consented receipts not met
- PostgreSQL E2E with new OCR fields not run in this session (requires `PRISLAPP_POSTGRES_TEST_URL`)
- Manual staging/pilot approval required

## Rollback

1. Deploy previous worker build (legacy parser path)
2. Migration 012 is additive — old workers tolerate new nullable columns
3. Disable writer storing extraction JSON if needed; `Receipt.total` semantics unchanged for null

## Runbook thresholds (proposed)

Stop pilot if: any new false-confident accepted total on holdout; review draft overwrite; queue age > 2× lease

## Client metadata to surface later

`extraction.warnings`, `total_state`, `store_state`, `computed_items_total`
