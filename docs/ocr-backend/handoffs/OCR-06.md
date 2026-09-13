# OCR-06 handoff

## Delivered

- `backend/app/services/receipt_extraction_service.py` — unified pipeline
- `parse_receipt_text()` in `backend/app/parsers/__init__.py` routes through pipeline
- Tests: `backend/tests/test_receipt_extraction_pipeline.py`

## Public entry points

- `parse_receipt_text_v2(text) -> (ReceiptExtractionResult, ParsedReceipt)`
- `parse_receipt_text(text) -> ParsedReceipt` (legacy-compatible)

## Behaviour changes

- All six baseline text bugs fixed via public entry
- **Removed** hidden `sum(items)` as `ParsedReceipt.total`
- Item parsers selected from detected chain; generic fallback when unknown
- Quality: `review_ready` / `review_required` / `unreadable`

## Test command

```bash
cd backend && .venv/bin/python -m pytest tests/test_receipt_extraction_pipeline.py tests/test_rema1000_parser.py -q
```

Result: **9 passed**

## OCR-07 wiring

Worker calls `parse_receipt_text_v2()` and persists extraction metadata.
