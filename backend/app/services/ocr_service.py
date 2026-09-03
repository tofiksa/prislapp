from functools import lru_cache
from io import BytesIO

from PIL import Image, ImageOps

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


def _prepare_image(image_bytes: bytes) -> Image.Image:
    with Image.open(BytesIO(image_bytes)) as img:
        image = ImageOps.exif_transpose(img) or img
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        else:
            image = image.copy()
    return _resize_for_ocr(image)


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


def _result_to_text(result) -> str:
    txts = getattr(result, "txts", None)
    if not txts:
        return ""
    boxes = getattr(result, "boxes", None)
    if boxes is None:
        return "\n".join(str(text) for text in txts if text)

    lines = sorted(
        zip(boxes, txts),
        key=lambda item: (float(item[0][0][1]), float(item[0][0][0])),
    )
    return "\n".join(str(text) for _, text in lines if text)


class OcrService:
    def extract_text(self, image_bytes: bytes) -> str:
        if not image_bytes:
            return ""
        image = _prepare_image(image_bytes)
        result = _ocr_engine()(image)
        return _result_to_text(result)
