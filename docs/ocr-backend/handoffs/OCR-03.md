# OCR-03 handoff

## Delivered

- `backend/app/parsers/store_detection.py`
- Alias register `CHAIN_ALIASES` version **1.0.0**
- Tests: `backend/tests/test_store_detection.py`

## API

- `detect_store(text, user_store_contexts=None) -> StoreExtraction`
- `UserStoreContext` for injected private store aliases (no DB in parser)

## Test command

```bash
cd backend && .venv/bin/python -m pytest tests/test_store_detection.py -q
```

Result: **6 passed**

## OCR-06/07 integration

Pipeline calls `detect_store()` first. Worker only creates legacy `Store` when `state == accepted`.
