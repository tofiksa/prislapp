# OCR-02 handoff

## Delivered

- `backend/app/parsers/amounts.py` — Norwegian money parsing
- `backend/app/parsers/totals.py` — candidate collection + selection
- Tests: `backend/tests/test_receipt_totals.py`

## API

- `parse_money_amount(text) -> MoneyParseResult`
- `extract_totals_from_text(text, ...) -> TotalExtraction`
- `collect_total_candidates(lines)` / `select_printed_total(candidates, ...)`

## Rules

- Endelig handelssum fra TOTAL/TOTALT/Å betale/I alt kr./Sum N varer
- Kontant/vekslepenger/MVA/rabatt er aldri handelssum
- Flere motstridende sluttotaler → abstain (`TOTAL_AMBIGUOUS`)
- Ingen varesum-fallback for trykt total

## Test command

```bash
cd backend && .venv/bin/python -m pytest tests/test_receipt_totals.py -q
```

Result: **14 passed**

## OCR-06 integration

Used by `receipt_extraction_service.extract_from_text()` before item parsing.
