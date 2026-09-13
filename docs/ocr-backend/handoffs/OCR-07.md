# OCR-07 handoff

## Delivered

- Migration **012**: `ocr_extraction_json`, `ocr_quality`, `ocr_pipeline_version` on `receipts`
- Worker uses structured pipeline + extraction metadata
- v1 API: optional `extraction` block on `ReceiptDetailResponse`
- Uncertain store → no auto-created global `Store`; suggestion in JSON metadata only

## Migration

```bash
cd backend && .venv/bin/python -m alembic upgrade head
```

## API example (fields only)

```json
{
  "total": "158.83",
  "extraction": {
    "quality": "review_ready",
    "pipeline_version": "1.0.0",
    "store_chain": "rema1000",
    "store_state": "accepted",
    "total_state": "accepted"
  }
}
```

## Tests

```bash
cd backend && .venv/bin/python -m pytest tests/test_migration_012.py tests/test_receipt_worker.py tests/contracts/ -q
```

## Android follow-up

Display `extraction.warnings`, `total_state`, `computed_items_total` in review UI. Older clients benefit from better prefilled values only.

## Retention

Extraction JSON follows 30-day image retention; deleted with receipt.
