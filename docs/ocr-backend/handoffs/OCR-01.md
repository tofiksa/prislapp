# OCR-01 handoff

## Delivered

- `backend/app/domain/receipt_extraction.py` — typed contract + JSON roundtrip
- `docs/ocr-backend/contracts.md`
- Tests: `backend/tests/test_receipt_extraction_contract.py`

## Exported symbols

`OcrDocument`, `OcrToken`, `OcrLine`, `FieldCandidate`, `StoreExtraction`, `TotalExtraction`, `ReceiptExtractionResult`, `ReasonCode`, `extraction_to_dict`, `extraction_from_dict`, `extraction_roundtrip_json`

## Test command

```bash
cd backend && .venv/bin/python -m pytest tests/test_receipt_extraction_contract.py -q
```

Result: **5 passed**

## Downstream notes

OCR-02/03/04 consume `FieldCandidate`, `ReasonCode`, and text-only adapters. OCR-07 persists `extraction_to_dict()` without full document tokens.
