"""Image preprocessing for OCR — preserve readability on long receipts."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from io import BytesIO

from PIL import Image, ImageOps

PREPROCESS_VERSION = "1.0.0"
_DEFAULT_MAX_SIDE = 2500
_DEFAULT_MIN_SIDE = 1000
_DEFAULT_MAX_TILES = 3
_DEFAULT_TILE_OVERLAP = 0.15
_DEFAULT_OCR_BUDGET_SECONDS = 45.0


@dataclass
class ImageTransform:
    original_width: int
    original_height: int
    processed_width: int
    processed_height: int
    scale_x: float
    scale_y: float
    exif_applied: bool = True
    crop_box: tuple[int, int, int, int] | None = None


@dataclass
class ProcessedImage:
    image: Image.Image
    transform: ImageTransform
    tile_index: int = 0
    tile_count: int = 1


@dataclass
class PreprocessResult:
    tiles: list[ProcessedImage] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    budget_exceeded: bool = False


def _load_exif_corrected(image_bytes: bytes) -> tuple[Image.Image, bool]:
    with Image.open(BytesIO(image_bytes)) as img:
        corrected = ImageOps.exif_transpose(img) or img
        if corrected.mode not in ("RGB", "L"):
            corrected = corrected.convert("RGB")
        else:
            corrected = corrected.copy()
    return corrected, True


def _scale_image(image: Image.Image, max_side: int, min_side: int) -> tuple[Image.Image, float]:
    width, height = image.size
    longest = max(width, height)
    if longest <= 0:
        return image, 1.0
    scale = 1.0
    if longest > max_side:
        scale = max_side / longest
    elif longest < min_side:
        scale = min_side / longest
    if scale == 1.0:
        return image, 1.0
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return image.resize(new_size, Image.Resampling.LANCZOS), scale


def _should_tile(image: Image.Image, max_side: int) -> bool:
    width, height = image.size
    aspect = height / max(width, 1)
    return height > max_side * 1.5 or aspect > 3.0


def _create_tiles(image: Image.Image, max_tiles: int, overlap: float) -> list[Image.Image]:
    width, height = image.size
    if not _should_tile(image, _DEFAULT_MAX_SIDE):
        return [image]

    tile_height = int(height / max_tiles)
    overlap_px = int(tile_height * overlap)
    tiles: list[Image.Image] = []
    y = 0
    while y < height and len(tiles) < max_tiles:
        y_end = min(height, y + tile_height + overlap_px)
        box = (0, y, width, y_end)
        tiles.append(image.crop(box))
        if y_end >= height:
            break
        y += tile_height
    return tiles or [image]


def preprocess_receipt_image(
    image_bytes: bytes,
    *,
    max_side: int = _DEFAULT_MAX_SIDE,
    min_side: int = _DEFAULT_MIN_SIDE,
    max_tiles: int = _DEFAULT_MAX_TILES,
    budget_seconds: float = _DEFAULT_OCR_BUDGET_SECONDS,
) -> PreprocessResult:
    """Normalize EXIF, scale and optionally tile long receipts."""
    start = time.monotonic()
    original, exif_applied = _load_exif_corrected(image_bytes)
    orig_w, orig_h = original.size

    scaled, scale = _scale_image(original, max_side, min_side)
    tile_images = _create_tiles(scaled, max_tiles, _DEFAULT_TILE_OVERLAP)

    tiles: list[ProcessedImage] = []
    for idx, tile in enumerate(tile_images):
        tw, th = tile.size
        tiles.append(
            ProcessedImage(
                image=tile,
                transform=ImageTransform(
                    original_width=orig_w,
                    original_height=orig_h,
                    processed_width=tw,
                    processed_height=th,
                    scale_x=scale,
                    scale_y=scale,
                    exif_applied=exif_applied,
                ),
                tile_index=idx,
                tile_count=len(tile_images),
            ),
        )

    elapsed = time.monotonic() - start
    return PreprocessResult(
        tiles=tiles,
        elapsed_seconds=elapsed,
        budget_exceeded=elapsed > budget_seconds,
    )


def map_polygon_to_original(
    polygon: list[list[float]],
    transform: ImageTransform,
    tile_y_offset: float = 0.0,
) -> list[list[float]]:
    """Map normalized tile coordinates back to original image space."""
    if not polygon:
        return polygon
    scale = transform.scale_x
    result = []
    for x, y in polygon:
        orig_x = x / scale if scale else x
        orig_y = (y + tile_y_offset) / scale if scale else y
        result.append([
            min(1.0, max(0.0, orig_x / transform.original_width if transform.original_width else orig_x)),
            min(1.0, max(0.0, orig_y / transform.original_height if transform.original_height else orig_y)),
        ])
    return result
