"""사진 → 설명 생성 → 카카오톡 전송을 하나로 묶은 파이프라인."""

from __future__ import annotations

from dataclasses import dataclass

from .describer import describe_image
from .kakao import KakaoClient


@dataclass
class Result:
    description: str
    messages_sent: int


def process_photo(
    image_bytes: bytes,
    filename: str | None = None,
    note: str | None = None,
    kakao: KakaoClient | None = None,
) -> Result:
    kakao = kakao or KakaoClient()
    # 로그인 안 된 상태라면 Claude 호출 전에 바로 실패시켜 비용 낭비 방지
    kakao.access_token()

    description = describe_image(image_bytes, note=note)
    header = f"📷 {filename}\n" if filename else "📷 사진 설명\n"
    sent = kakao.send_to_me(header + description)
    return Result(description=description, messages_sent=sent)
