# OCR extraction contract (v1.0.0)

Internal typed model: `backend/app/domain/receipt_extraction.py`

## Core types

| Symbol | Purpose |
|---|---|
| `OcrDocument` | Structured OCR output with tokens, lines, engine/preprocess metadata |
| `OcrToken` | Text, optional score, normalized polygon, source pass/crop |
| `OcrLine` | Token IDs, section (`header\|items\|totals\|payment\|tax\|footer\|unknown`) |
| `FieldCandidate` | Typed value + evidence + rule ID + `accepted\|uncertain\|missing` |
| `StoreExtraction` | Chain, branch text, resolution (`branch\|chain_only\|unknown`) |
| `TotalExtraction` | `printed_total`, `computed_items_total`, candidates, negative evidence |
| `ReceiptExtractionResult` | Combined store/total/quality/provenance |

Money in JSON is **decimal string**, never float.

## Compatibility

1. `OcrService.extract_text(bytes)` remains the legacy wrapper.
2. `parse_receipt_text(str)` now routes through `receipt_extraction_service` (OCR-06).
3. `ParsedReceipt.total` = selected printed total or **null** (no item-sum fallback).
4. v1 `ReceiptDetailResponse` adds optional `extraction` summary (OCR-07).
5. OCR suggestions are never confirmed revisions.

## Example (accepted total)

```json
{
  "store": {
    "chain": "rema1000",
    "branch_text": "METRO SENTER",
    "resolution": "branch",
    "state": "accepted"
  },
  "total": {
    "printed_total": "158.83",
    "computed_items_total": "158.83",
    "computed_items_complete": true,
    "state": "accepted"
  },
  "quality": "review_ready"
}
```

## Example (abstain)

```json
{
  "total": {
    "printed_total": null,
    "state": "uncertain",
    "reason_codes": ["TOTAL_AMBIGUOUS"]
  }
}
```
