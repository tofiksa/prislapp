# OCR-04 handoff

## Delivered

- `OcrService.extract_document(bytes) -> OcrDocument` in `backend/app/services/ocr_service.py`
- `backend/app/parsers/layout.py` — rows, sections, text adapter
- Tests: `backend/tests/test_layout.py`

## Adapter contract

- RapidOCR 3.9.2, polygons normalized to EXIF-oriented original dimensions
- `extract_text()` unchanged (wrapper over document)
- Deterministic text serialization from token geometry

## Test command

```bash
cd backend && .venv/bin/python -m pytest tests/test_layout.py tests/test_ocr_service.py -q
```

Result: **7 passed**

## OCR-05 note

Image tiling/preprocess owned by `receipt_image_preprocessing.py`; OCR-04 adapter consumes its output.
