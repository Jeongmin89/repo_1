"""업로드된 이미지를 Claude API에 보내기 좋은 JPEG로 정규화."""

from __future__ import annotations

import io

from PIL import Image, ImageOps

try:  # iPhone HEIC 지원 (선택)
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # pragma: no cover
    pass

# Claude 비전 입력은 긴 변 ~1568px 정도면 충분하고, 그 이상은 토큰만 늘어남
MAX_SIDE = 1568


class InvalidImageError(ValueError):
    pass


def prepare_image(data: bytes, max_side: int = MAX_SIDE) -> bytes:
    """이미지 바이트를 받아 회전 보정·축소한 JPEG 바이트를 반환."""
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:  # Pillow는 다양한 예외를 던짐
        raise InvalidImageError("이미지 파일을 읽을 수 없습니다.") from exc

    img = ImageOps.exif_transpose(img)  # 휴대폰 사진 회전 정보 반영
    if img.mode != "RGB":
        img = img.convert("RGB")
    img.thumbnail((max_side, max_side))

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85)
    return out.getvalue()
