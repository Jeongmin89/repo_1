"""Claude 비전으로 사진 설명 생성."""

from __future__ import annotations

import base64

import anthropic

from .config import get_settings
from .image_utils import prepare_image

SYSTEM_PROMPT = """\
당신은 사진을 한국어로 설명해 주는 도우미입니다.
설명은 카카오톡 메시지로 전송되므로 다음을 지켜 주세요.
- 첫 줄: 사진을 한 문장으로 요약한 제목 (이모지 1개로 시작)
- 이어서 3~5개의 짧은 문장으로 주요 대상, 배경·장소, 분위기, 눈에 띄는 디테일을 설명
- 사진 속 글자가 있으면 그대로 옮겨 적기
- 전체 500자 이내, 마크다운 기호(#, *, **) 사용 금지
- 확실하지 않은 내용은 추측이라고 밝히고, 사진 속 실존 인물의 신원은 단정하지 않기
"""


class DescriptionError(RuntimeError):
    pass


def describe_image(
    image_bytes: bytes,
    note: str | None = None,
    client: anthropic.Anthropic | None = None,
) -> str:
    """이미지를 설명하는 한국어 텍스트를 반환."""
    settings = get_settings()
    client = client or anthropic.Anthropic()

    jpeg = prepare_image(image_bytes)
    image_b64 = base64.standard_b64encode(jpeg).decode("utf-8")

    instruction = "이 사진을 설명해 주세요."
    if note:
        instruction += f"\n\n사용자 메모(참고용): {note.strip()}"

    response = client.beta.messages.create(
        model=settings.claude_model,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        output_config={"effort": settings.claude_effort},
        # 안전 분류기가 요청을 거절하면 서버가 다른 모델로 자동 재시도
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": instruction},
                ],
            }
        ],
    )

    if response.stop_reason == "refusal":
        raise DescriptionError("이 사진은 설명을 생성할 수 없습니다.")

    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if not text:
        raise DescriptionError("설명 생성 결과가 비어 있습니다.")
    return text
