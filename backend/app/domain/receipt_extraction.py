"""Structured OCR extraction contract — internal typed model for receipt field evidence."""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Literal

FieldState = Literal["accepted", "uncertain", "missing"]
SectionType = Literal["header", "items", "totals", "payment", "tax", "footer", "unknown"]
StoreResolution = Literal["branch", "chain_only", "unknown"]
ReceiptQuality = Literal["review_ready", "review_required", "unreadable"]

MAX_TOKENS = 10_000
MAX_PAYLOAD_BYTES = 2_000_000


class ReasonCode(str, Enum):
    TOTAL_NOT_FOUND = "TOTAL_NOT_FOUND"
    TOTAL_AMBIGUOUS = "TOTAL_AMBIGUOUS"
    TOTAL_ITEMS_MISMATCH = "TOTAL_ITEMS_MISMATCH"
    ITEMS_INCOMPLETE = "ITEMS_INCOMPLETE"
    STORE_UNRESOLVED = "STORE_UNRESOLVED"
    BRANCH_UNRESOLVED = "BRANCH_UNRESOLVED"
    MULTIPLE_DOCUMENTS = "MULTIPLE_DOCUMENTS"
    IMAGE_TOO_SMALL = "IMAGE_TOO_SMALL"
    OCR_TIMEOUT = "OCR_TIMEOUT"


def _decimal_to_str(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _str_to_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid decimal string: {value!r}") from exc


def _validate_polygon(polygon: list[list[float]] | None) -> list[list[float]] | None:
    if polygon is None:
        return None
    if len(polygon) < 3:
        raise ValueError("Polygon must have at least 3 points")
    for point in polygon:
        if len(point) != 2:
            raise ValueError("Each polygon point must be [x, y]")
        for coord in point:
            if not isinstance(coord, (int, float)) or math.isnan(coord) or math.isinf(coord):
                raise ValueError("Polygon coordinates must be finite numbers")
            if coord < 0 or coord > 1:
                raise ValueError("Normalized polygon coordinates must be in [0, 1]")
    return polygon


@dataclass(frozen=True)
class OcrToken:
    token_id: str
    text: str
    polygon: list[list[float]] | None = None
    ocr_score: float | None = None
    source_pass: str = "primary"
    source_crop_id: str | None = None

    def __post_init__(self) -> None:
        if not self.token_id:
            raise ValueError("token_id is required")
        if self.ocr_score is not None and (math.isnan(self.ocr_score) or math.isinf(self.ocr_score)):
            raise ValueError("ocr_score must be finite")
        object.__setattr__(self, "polygon", _validate_polygon(self.polygon))


@dataclass(frozen=True)
class OcrLine:
    line_id: str
    token_ids: tuple[str, ...]
    section: SectionType = "unknown"
    reading_order: int = 0


@dataclass(frozen=True)
class OcrDocument:
    schema_version: str
    engine: str
    model_id: str | None
    preprocess_version: str
    original_width: int
    original_height: int
    document_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tokens: tuple[OcrToken, ...] = ()
    lines: tuple[OcrLine, ...] = ()
    plain_text: str = ""
    normalized_text: str = ""
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if len(self.tokens) > MAX_TOKENS:
            raise ValueError(f"Token count exceeds limit ({MAX_TOKENS})")
        token_ids = {t.token_id for t in self.tokens}
        for line in self.lines:
            for tid in line.token_ids:
                if tid not in token_ids:
                    raise ValueError(f"Line {line.line_id} references unknown token {tid}")


@dataclass(frozen=True)
class FieldCandidate:
    candidate_id: str
    value_text: str | None = None
    value_decimal: Decimal | None = None
    evidence_token_ids: tuple[str, ...] = ()
    rule_id: str = ""
    ocr_score: float | None = None
    rank_score: float = 0.0
    state: FieldState = "uncertain"
    reason_codes: tuple[ReasonCode, ...] = ()


@dataclass(frozen=True)
class StoreExtraction:
    chain: str | None = None
    branch_text: str | None = None
    observed_text: str | None = None
    resolved_user_store_id: str | None = None
    resolution: StoreResolution = "unknown"
    state: FieldState = "missing"
    selected_candidate_id: str | None = None
    candidates: tuple[FieldCandidate, ...] = ()
    reason_codes: tuple[ReasonCode, ...] = ()


@dataclass(frozen=True)
class TotalExtraction:
    printed_total: Decimal | None = None
    computed_items_total: Decimal | None = None
    computed_items_complete: bool = False
    currency: str = "NOK"
    reconciliation_hint: str | None = None
    state: FieldState = "missing"
    selected_candidate_id: str | None = None
    candidates: tuple[FieldCandidate, ...] = ()
    negative_evidence_token_ids: tuple[str, ...] = ()
    reason_codes: tuple[ReasonCode, ...] = ()


@dataclass(frozen=True)
class ExtractionProvenance:
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    attempt_id: str | None = None
    pipeline_version: str = "1.0.0"
    rules_version: str = "1.0.0"
    metadata_retention_days: int = 30


@dataclass
class ReceiptExtractionResult:
    store: StoreExtraction = field(default_factory=StoreExtraction)
    total: TotalExtraction = field(default_factory=TotalExtraction)
    document: OcrDocument | None = None
    quality: ReceiptQuality = "review_required"
    provenance: ExtractionProvenance = field(default_factory=ExtractionProvenance)
    warnings: list[str] = field(default_factory=list)


def token_to_dict(token: OcrToken) -> dict[str, Any]:
    return {
        "token_id": token.token_id,
        "text": token.text,
        "polygon": token.polygon,
        "ocr_score": token.ocr_score,
        "source_pass": token.source_pass,
        "source_crop_id": token.source_crop_id,
    }


def token_from_dict(data: dict[str, Any]) -> OcrToken:
    return OcrToken(
        token_id=data["token_id"],
        text=data["text"],
        polygon=data.get("polygon"),
        ocr_score=data.get("ocr_score"),
        source_pass=data.get("source_pass", "primary"),
        source_crop_id=data.get("source_crop_id"),
    )


def document_to_dict(document: OcrDocument) -> dict[str, Any]:
    return {
        "schema_version": document.schema_version,
        "engine": document.engine,
        "model_id": document.model_id,
        "preprocess_version": document.preprocess_version,
        "original_width": document.original_width,
        "original_height": document.original_height,
        "document_id": document.document_id,
        "tokens": [token_to_dict(t) for t in document.tokens],
        "lines": [
            {
                "line_id": line.line_id,
                "token_ids": list(line.token_ids),
                "section": line.section,
                "reading_order": line.reading_order,
            }
            for line in document.lines
        ],
        "plain_text": document.plain_text,
        "normalized_text": document.normalized_text,
        "diagnostics": document.diagnostics,
    }


def document_from_dict(data: dict[str, Any]) -> OcrDocument:
    return OcrDocument(
        schema_version=data["schema_version"],
        engine=data["engine"],
        model_id=data.get("model_id"),
        preprocess_version=data["preprocess_version"],
        original_width=data["original_width"],
        original_height=data["original_height"],
        document_id=data.get("document_id", str(uuid.uuid4())),
        tokens=tuple(token_from_dict(t) for t in data.get("tokens", [])),
        lines=tuple(
            OcrLine(
                line_id=line["line_id"],
                token_ids=tuple(line["token_ids"]),
                section=line.get("section", "unknown"),
                reading_order=line.get("reading_order", 0),
            )
            for line in data.get("lines", [])
        ),
        plain_text=data.get("plain_text", ""),
        normalized_text=data.get("normalized_text", ""),
        diagnostics=data.get("diagnostics", {}),
    )


def extraction_to_dict(result: ReceiptExtractionResult) -> dict[str, Any]:
    def candidate_dict(c: FieldCandidate) -> dict[str, Any]:
        return {
            "candidate_id": c.candidate_id,
            "value_text": c.value_text,
            "value_decimal": _decimal_to_str(c.value_decimal),
            "evidence_token_ids": list(c.evidence_token_ids),
            "rule_id": c.rule_id,
            "ocr_score": c.ocr_score,
            "rank_score": c.rank_score,
            "state": c.state,
            "reason_codes": [r.value for r in c.reason_codes],
        }

    payload = {
        "store": {
            "chain": result.store.chain,
            "branch_text": result.store.branch_text,
            "observed_text": result.store.observed_text,
            "resolved_user_store_id": result.store.resolved_user_store_id,
            "resolution": result.store.resolution,
            "state": result.store.state,
            "selected_candidate_id": result.store.selected_candidate_id,
            "candidates": [candidate_dict(c) for c in result.store.candidates],
            "reason_codes": [r.value for r in result.store.reason_codes],
        },
        "total": {
            "printed_total": _decimal_to_str(result.total.printed_total),
            "computed_items_total": _decimal_to_str(result.total.computed_items_total),
            "computed_items_complete": result.total.computed_items_complete,
            "currency": result.total.currency,
            "reconciliation_hint": result.total.reconciliation_hint,
            "state": result.total.state,
            "selected_candidate_id": result.total.selected_candidate_id,
            "candidates": [candidate_dict(c) for c in result.total.candidates],
            "negative_evidence_token_ids": list(result.total.negative_evidence_token_ids),
            "reason_codes": [r.value for r in result.total.reason_codes],
        },
        "quality": result.quality,
        "provenance": {
            "run_id": result.provenance.run_id,
            "attempt_id": result.provenance.attempt_id,
            "pipeline_version": result.provenance.pipeline_version,
            "rules_version": result.provenance.rules_version,
            "metadata_retention_days": result.provenance.metadata_retention_days,
        },
        "warnings": result.warnings,
    }
    if result.document is not None:
        payload["document"] = document_to_dict(result.document)
    return payload


def extraction_from_dict(data: dict[str, Any]) -> ReceiptExtractionResult:
    def candidate_from_dict(c: dict[str, Any]) -> FieldCandidate:
        return FieldCandidate(
            candidate_id=c["candidate_id"],
            value_text=c.get("value_text"),
            value_decimal=_str_to_decimal(c.get("value_decimal")),
            evidence_token_ids=tuple(c.get("evidence_token_ids", [])),
            rule_id=c.get("rule_id", ""),
            ocr_score=c.get("ocr_score"),
            rank_score=c.get("rank_score", 0.0),
            state=c.get("state", "uncertain"),
            reason_codes=tuple(ReasonCode(r) for r in c.get("reason_codes", [])),
        )

    store_data = data.get("store", {})
    total_data = data.get("total", {})
    prov_data = data.get("provenance", {})

    return ReceiptExtractionResult(
        store=StoreExtraction(
            chain=store_data.get("chain"),
            branch_text=store_data.get("branch_text"),
            observed_text=store_data.get("observed_text"),
            resolved_user_store_id=store_data.get("resolved_user_store_id"),
            resolution=store_data.get("resolution", "unknown"),
            state=store_data.get("state", "missing"),
            selected_candidate_id=store_data.get("selected_candidate_id"),
            candidates=tuple(candidate_from_dict(c) for c in store_data.get("candidates", [])),
            reason_codes=tuple(ReasonCode(r) for r in store_data.get("reason_codes", [])),
        ),
        total=TotalExtraction(
            printed_total=_str_to_decimal(total_data.get("printed_total")),
            computed_items_total=_str_to_decimal(total_data.get("computed_items_total")),
            computed_items_complete=total_data.get("computed_items_complete", False),
            currency=total_data.get("currency", "NOK"),
            reconciliation_hint=total_data.get("reconciliation_hint"),
            state=total_data.get("state", "missing"),
            selected_candidate_id=total_data.get("selected_candidate_id"),
            candidates=tuple(candidate_from_dict(c) for c in total_data.get("candidates", [])),
            negative_evidence_token_ids=tuple(total_data.get("negative_evidence_token_ids", [])),
            reason_codes=tuple(ReasonCode(r) for r in total_data.get("reason_codes", [])),
        ),
        document=document_from_dict(data["document"]) if "document" in data else None,
        quality=data.get("quality", "review_required"),
        provenance=ExtractionProvenance(
            run_id=prov_data.get("run_id", str(uuid.uuid4())),
            attempt_id=prov_data.get("attempt_id"),
            pipeline_version=prov_data.get("pipeline_version", "1.0.0"),
            rules_version=prov_data.get("rules_version", "1.0.0"),
            metadata_retention_days=prov_data.get("metadata_retention_days", 30),
        ),
        warnings=list(data.get("warnings", [])),
    )


def extraction_roundtrip_json(result: ReceiptExtractionResult) -> ReceiptExtractionResult:
    encoded = json.dumps(extraction_to_dict(result), ensure_ascii=False)
    if len(encoded.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise ValueError("Serialized extraction exceeds payload limit")
    return extraction_from_dict(json.loads(encoded))
