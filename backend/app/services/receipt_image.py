"""Validering av kvitteringsbilder før OCR.

Låste grenser (S02-C), dokumentert også i docs/contracts/feil-og-offline.md:

- Maks opplasting: 20 MiB rå filbytes.
- Maks dekodet piksler: 40_000_000 (bredde × høyde).
- Maks side: 12_000 px i hver retning.
- Aksepter JPEG og PNG etter dekoding. Ingen stille nedskalering.
"""

from __future__ import annotations

import hashlib
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from app.errors import ApiError, FieldError

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MiB
MAX_DECODED_PIXELS = 40_000_000
MAX_SIDE_PX = 12_000
ACCEPTED_FORMATS = frozenset({"JPEG", "PNG"})
FORMAT_CONTENT_TYPES = {"JPEG": "image/jpeg", "PNG": "image/png"}


class InvalidImageError(ValueError):
    """Ugyldig eller ustøttet bilde. v1 400 beholdes."""


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inspect_receipt_image(image_bytes: bytes) -> tuple[str, int, int]:
    """Dekod JPEG/PNG og avvis farlige dimensjoner før OCR.

    Returnerer `(content_type, width, height)` etter dekoding.
    """
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            width, height = image.size
            fmt = (image.format or "").upper()
    except Image.DecompressionBombError as exc:
        raise image_too_large() from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise InvalidImageError("Invalid image") from exc

    if fmt not in ACCEPTED_FORMATS:
        raise InvalidImageError("Invalid image")
    if width > MAX_SIDE_PX or height > MAX_SIDE_PX:
        raise image_dimensions()
    if width * height > MAX_DECODED_PIXELS:
        raise image_too_large()

    try:
        with Image.open(BytesIO(image_bytes)) as image:
            image.verify()
    except Image.DecompressionBombError as exc:
        raise image_too_large() from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise InvalidImageError("Invalid image") from exc

    return FORMAT_CONTENT_TYPES[fmt], width, height


def image_dimensions() -> ApiError:
    return ApiError(
        413,
        "IMAGE_DIMENSIONS",
        "Bildet har for store dimensjoner.",
        [
            FieldError(
                "file",
                "dimensions",
                "Maks 12 000 piksler i hver retning.",
            ),
        ],
        retryable=False,
    )


def image_too_large() -> ApiError:
    return ApiError(
        413,
        "IMAGE_TOO_LARGE",
        "Bildet er for stort.",
        [
            FieldError(
                "file",
                "too_large",
                "Maks 40 000 000 dekodet piksler.",
            ),
        ],
        retryable=False,
    )


def idempotency_conflict() -> ApiError:
    return ApiError(
        409,
        "IDEMPOTENCY_CONFLICT",
        "Samme opplastingsnøkkel er allerede brukt med en annen fil.",
        [
            FieldError(
                "Idempotency-Key",
                "payload_mismatch",
                "Bruk en ny nøkkel for en ny fil.",
            ),
        ],
        retryable=False,
    )
