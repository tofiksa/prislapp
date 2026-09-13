"""Tests for OCR extraction contract serialization and validation."""

from decimal import Decimal

import pytest

from app.domain.receipt_extraction import (
    FieldCandidate,
    OcrDocument,
    OcrToken,
    ReasonCode,
    ReceiptExtractionResult,
    StoreExtraction,
    TotalExtraction,
    extraction_roundtrip_json,
    extraction_to_dict,
)


def test_roundtrip_with_norwegian_text_and_decimals():
    result = ReceiptExtractionResult(
        store=StoreExtraction(
            chain="rema1000",
            branch_text="METRO SENTER",
            observed_text="REMA 1000 METRO SENTER",
            resolution="branch",
            state="accepted",
        ),
        total=TotalExtraction(
            printed_total=Decimal("158.83"),
            computed_items_total=Decimal("158.83"),
            computed_items_complete=True,
            state="accepted",
        ),
        quality="review_ready",
    )
    roundtripped = extraction_roundtrip_json(result)
    assert roundtripped.store.chain == "rema1000"
    assert roundtripped.total.printed_total == Decimal("158.83")


def test_null_score_and_missing_total():
    token = OcrToken(token_id="T1", text="TOTALT", ocr_score=None)
    result = ReceiptExtractionResult(
        total=TotalExtraction(
            printed_total=None,
            state="missing",
            reason_codes=(ReasonCode.TOTAL_NOT_FOUND,),
        ),
        document=OcrDocument(
            schema_version="1.0.0",
            engine="rapidocr",
            model_id=None,
            preprocess_version="1.0.0",
            original_width=100,
            original_height=200,
            tokens=(token,),
            plain_text="TOTALT",
        ),
    )
    payload = extraction_to_dict(result)
    assert payload["total"]["printed_total"] is None
    assert payload["document"]["tokens"][0]["ocr_score"] is None


def test_invalid_polygon_rejected():
    with pytest.raises(ValueError):
        OcrToken(token_id="T1", text="x", polygon=[[float("nan"), 0.5]])


def test_broken_evidence_reference_rejected():
    with pytest.raises(ValueError, match="unknown token"):
        OcrDocument(
            schema_version="1.0.0",
            engine="test",
            model_id=None,
            preprocess_version="1.0.0",
            original_width=10,
            original_height=10,
            lines=(
                __import__("app.domain.receipt_extraction", fromlist=["OcrLine"]).OcrLine(
                    line_id="L1",
                    token_ids=("missing",),
                ),
            ),
        )


def test_conflicting_totals_example():
    result = ReceiptExtractionResult(
        total=TotalExtraction(
            state="uncertain",
            reason_codes=(ReasonCode.TOTAL_AMBIGUOUS,),
            candidates=(
                FieldCandidate(
                    candidate_id="c1",
                    value_decimal=Decimal("15.00"),
                    rule_id="total_label",
                    state="uncertain",
                ),
                FieldCandidate(
                    candidate_id="c2",
                    value_decimal=Decimal("20.00"),
                    rule_id="total_label",
                    state="uncertain",
                ),
            ),
        ),
    )
    payload = extraction_to_dict(result)
    assert payload["total"]["state"] == "uncertain"
    assert len(payload["total"]["candidates"]) == 2
