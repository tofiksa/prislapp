from __future__ import annotations

import hashlib
import platform
import subprocess
import uuid
from functools import lru_cache
from io import BytesIO

from PIL import Image, ImageOps

from app.domain.receipt_extraction import OcrDocument, OcrToken
from app.services.receipt_image_preprocessing import PREPROCESS_VERSION, preprocess_receipt_image

SCHEMA_VERSION = "1.0.0"
ENGINE_NAME = "rapidocr"
ENGINE_VERSION = "3.9.2"

_MAX_SIDE_PX = 2500
_MIN_SIDE_PX = 1000


@lru_cache(maxsize=1)
def _ocr_engine():
    from rapidocr import RapidOCR

    return RapidOCR(
        params={
            "Det.lang_type": "en",
            "Rec.lang_type": "no",
            "Global.log_level": "error",
        },
    )


def _git_revision() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()[:12]
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _model_id() -> str | None:
    try:
        import rapidocr

        version = getattr(rapidocr, "__version__", ENGINE_VERSION)
        return f"rapidocr-{version}"
    except ImportError:
        return None


def _prepare_image(image_bytes: bytes) -> tuple[Image.Image, int, int]:
    with Image.open(BytesIO(image_bytes)) as img:
        image = ImageOps.exif_transpose(img) or img
        orig_w, orig_h = image.size
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        else:
            image = image.copy()
    return _resize_for_ocr(image), orig_w, orig_h


def _resize_for_ocr(image: Image.Image) -> Image.Image:
    width, height = image.size
    longest = max(width, height)
    if longest <= 0:
        return image
    if longest > _MAX_SIDE_PX:
        scale = _MAX_SIDE_PX / longest
    elif longest < _MIN_SIDE_PX:
        scale = _MIN_SIDE_PX / longest
    else:
        return image
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return image.resize(new_size, Image.Resampling.LANCZOS)


def _normalize_polygon(box, img_w: int, img_h: int) -> list[list[float]] | None:
    if box is None or img_w <= 0 or img_h <= 0:
        return None
    try:
        points = []
        for point in box:
            x = float(point[0]) / img_w
            y = float(point[1]) / img_h
            points.append([min(1.0, max(0.0, x)), min(1.0, max(0.0, y))])
        return points
    except (TypeError, ValueError, IndexError):
        return None


def _result_to_tokens(result, img_w: int, img_h: int, source_pass: str = "primary") -> list[OcrToken]:
    txts = getattr(result, "txts", None)
    if txts is None or len(txts) == 0:
        return []
    boxes = getattr(result, "boxes", None)
    scores = getattr(result, "scores", None)

    tokens: list[OcrToken] = []
    for i, text in enumerate(txts):
        if not text:
            continue
        box = boxes[i] if boxes is not None and i < len(boxes) else None
        score = float(scores[i]) if scores is not None and i < len(scores) else None
        tokens.append(
            OcrToken(
                token_id=f"T{i:04d}",
                text=str(text),
                polygon=_normalize_polygon(box, img_w, img_h),
                ocr_score=score,
                source_pass=source_pass,
            ),
        )
    return tokens


def _tokens_to_text(tokens: list[OcrToken]) -> str:
    if not tokens:
        return ""
    with_boxes = [t for t in tokens if t.polygon]
    if not with_boxes:
        return "\n".join(t.text for t in tokens if t.text)

    indexed = []
    for token in with_boxes:
        ys = [p[1] for p in token.polygon]
        xs = [p[0] for p in token.polygon]
        y_center = sum(ys) / len(ys)
        height = max(ys) - min(ys) if ys else 0.02
        indexed.append((y_center, min(xs), height, token.text))

    rows: list[list[tuple]] = []
    for entry in sorted(indexed):
        y_center, x_min, height, text = entry
        placed = False
        for row in rows:
            row_y, _, row_h, _ = row[0]
            if abs(y_center - row_y) <= max(0.005, min(height, row_h) * 0.5):
                row.append(entry)
                placed = True
                break
        if not placed:
            rows.append([entry])

    return "\n".join(
        " ".join(t[3] for t in sorted(row, key=lambda t: t[1]))
        for row in rows
    )


def _result_to_text(result) -> str:
    txts = getattr(result, "txts", None)
    if txts is None or len(txts) == 0:
        return ""
    boxes = getattr(result, "boxes", None)
    if boxes is None:
        return "\n".join(str(text) for text in txts if text)

    tokens = []
    for box, text in zip(boxes, txts):
        ys = [float(point[1]) for point in box]
        tokens.append((sum(ys) / len(ys), min(float(p[0]) for p in box), max(ys) - min(ys), str(text)))
    rows = []
    for token in sorted(tokens):
        if rows and abs(token[0] - rows[-1][0][0]) <= max(1, min(token[2], rows[-1][0][2]) * 0.5):
            rows[-1].append(token)
        else:
            rows.append([token])
    return "\n".join(" ".join(t[3] for t in sorted(row, key=lambda t: t[1])) for row in rows)


class OcrService:
    def extract_text(self, image_bytes: bytes) -> str:
        if not image_bytes:
            return ""
        document = self.extract_document(image_bytes)
        return document.plain_text

    def extract_document(self, image_bytes: bytes) -> OcrDocument:
        if not image_bytes:
            return OcrDocument(
                schema_version=SCHEMA_VERSION,
                engine=ENGINE_NAME,
                model_id=_model_id(),
                preprocess_version=PREPROCESS_VERSION,
                original_width=0,
                original_height=0,
                plain_text="",
                diagnostics={"empty_input": True},
            )

        preprocessed = preprocess_receipt_image(image_bytes)
        all_tokens: list[OcrToken] = []
        orig_w = orig_h = 0

        for tile in preprocessed.tiles:
            image = tile.image
            img_w, img_h = image.size
            if tile.tile_index == 0:
                orig_w = tile.transform.original_width
                orig_h = tile.transform.original_height

            result = _ocr_engine()(image)
            tile_tokens = _result_to_tokens(
                result,
                img_w,
                img_h,
                source_pass="primary" if tile.tile_count == 1 else f"tile_{tile.tile_index}",
            )
            # Offset token IDs for multi-tile
            for tok in tile_tokens:
                all_tokens.append(
                    OcrToken(
                        token_id=f"{tok.token_id}_{tile.tile_index}" if tile.tile_count > 1 else tok.token_id,
                        text=tok.text,
                        polygon=tok.polygon,
                        ocr_score=tok.ocr_score,
                        source_pass=tok.source_pass,
                        source_crop_id=str(tile.tile_index) if tile.tile_count > 1 else None,
                    ),
                )

        plain_text = _tokens_to_text(all_tokens)

        from app.parsers.layout import enrich_document_with_layout

        document = OcrDocument(
            schema_version=SCHEMA_VERSION,
            engine=ENGINE_NAME,
            model_id=_model_id(),
            preprocess_version=PREPROCESS_VERSION,
            original_width=orig_w,
            original_height=orig_h,
            document_id=str(uuid.uuid4()),
            tokens=tuple(all_tokens),
            plain_text=plain_text,
            normalized_text=plain_text,
            diagnostics={
                "engine_version": ENGINE_VERSION,
                "git_revision": _git_revision(),
                "platform": platform.platform(),
                "tile_count": len(preprocessed.tiles),
                "preprocess_elapsed_s": round(preprocessed.elapsed_seconds, 3),
                "text_hash": hashlib.sha256(plain_text.encode()).hexdigest()[:16],
            },
        )
        return enrich_document_with_layout(document)
