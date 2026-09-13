# OCR-08 handoff — engine evaluation

## Recommendation: **Keep RapidOCR 3.9.2**

## Method

Parser-mode benchmark on development fixtures isolates parsing from OCR. Image-mode on holdout measures end-to-end with current engine + new preprocessing.

## Candidates evaluated

| Candidate | Status |
|---|---|
| RapidOCR 3.9.2 (control) | **Default — kept** |
| Alternative local engines (PaddleOCR, Tesseract) | Not installed — no CI dependency on model downloads |
| External managed OCR | **Not run** — no data-flow approval |

## Findings

- Documented baseline failures were **parser bugs**, reproduced without OCR; fixed in OCR-02/03/06.
- RapidOCR reads golden Rema/Normal images correctly with existing test suite.
- No evidence that engine swap alone fixes remaining issues before parsing improvements.

## Decision

Do **not** change production engine. Re-evaluate after 30+ holdout receipts if image-mode errors persist.

## Reproducibility

```bash
cd backend
.venv/bin/python scripts/benchmark_receipts.py --mode parser --output /tmp/parser.json
.venv/bin/python scripts/benchmark_receipts.py --mode image --split holdout --output /tmp/image.json
```
