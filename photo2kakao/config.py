"""환경 변수(.env) 기반 설정."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    claude_model: str
    claude_effort: str
    kakao_rest_api_key: str
    kakao_client_secret: str
    kakao_redirect_uri: str
    kakao_link_url: str
    kakao_token_path: Path
    app_password: str


def get_settings() -> Settings:
    return Settings(
        claude_model=os.getenv("CLAUDE_MODEL", "claude-opus-5-5"),
        claude_effort=os.getenv("CLAUDE_EFFORT", "medium"),
        kakao_rest_api_key=os.getenv("KAKAO_REST_API_KEY", ""),
        kakao_client_secret=os.getenv("KAKAO_CLIENT_SECRET", ""),
        kakao_redirect_uri=os.getenv(
            "KAKAO_REDIRECT_URI", "http://localhost:8000/oauth/kakao/callback"
        ),
        kakao_link_url=os.getenv("KAKAO_LINK_URL", "http://localhost:8000"),
        kakao_token_path=Path(os.getenv("KAKAO_TOKEN_PATH", ".kakao_token.json")),
        app_password=os.getenv("APP_PASSWORD", ""),
    )
