# OCR-05 handoff

## Delivered

- `backend/app/services/receipt_image_preprocessing.py`
- Integrated into `OcrService.extract_document()` (tiling for long receipts)
- Config defaults: max side 2500, max 3 tiles, 45s budget flag

## Policy

- EXIF normalize once; original bytes untouched in storage
- Long receipts: overlapping vertical tiles with dedup via token ID assignment per tile
- Targeted second-pass API stub via preprocess module (full pipeline hook in OCR-06 uses standard pass)

## Measurement

Benchmark image mode on holdout measures OCR+parser end-to-end. No quality regression enforced until holdout images run locally.

## Negative evaluation note

Aggressive deskew/contrast filters **not enabled** — no demonstrated gain on current fixture set.
