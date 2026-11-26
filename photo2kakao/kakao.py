"""카카오 로그인(OAuth) + 카카오톡 '나에게 보내기' API 클라이언트.

참고 문서
- 카카오 로그인 REST API: https://developers.kakao.com/docs/latest/ko/kakaologin/rest-api
- 카카오톡 메시지(나에게 보내기): https://developers.kakao.com/docs/latest/ko/message/rest-api
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

from .config import Settings, get_settings

AUTH_URL = "https://kauth.kakao.com/oauth/authorize"
TOKEN_URL = "https://kauth.kakao.com/oauth/token"
MEMO_SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"

# 텍스트 템플릿의 text 필드는 최대 200자
KAKAO_TEXT_LIMIT = 200


class KakaoError(RuntimeError):
    pass


class KakaoNotAuthorizedError(KakaoError):
    """아직 카카오 로그인을 하지 않았거나 refresh token이 만료됨."""


# ── 토큰 저장/갱신 ─────────────────────────────────────────────


class TokenStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict | None:
        if not self.path.exists():
            return None
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, token: dict) -> None:
        self.path.write_text(json.dumps(token, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            self.path.chmod(0o600)
        except OSError:  # pragma: no cover (Windows 등)
            pass


class KakaoClient:
    def __init__(self, settings: Settings | None = None, session: requests.Session | None = None):
        self.settings = settings or get_settings()
        self.http = session or requests.Session()
        self.store = TokenStore(self.settings.kakao_token_path)

    # OAuth ---------------------------------------------------------

    def authorize_url(self) -> str:
        self._require_app_key()
        params = {
            "client_id": self.settings.kakao_rest_api_key,
            "redirect_uri": self.settings.kakao_redirect_uri,
            "response_type": "code",
            "scope": "talk_message",
        }
        return f"{AUTH_URL}?{urlencode(params)}"

    def exchange_code(self, code: str) -> dict:
        data = {
            "grant_type": "authorization_code",
            "client_id": self.settings.kakao_rest_api_key,
            "redirect_uri": self.settings.kakao_redirect_uri,
            "code": code,
        }
        return self._request_token(data, previous=None)

    def refresh(self, token: dict) -> dict:
        if not token.get("refresh_token"):
            raise KakaoNotAuthorizedError("refresh token이 없습니다. 다시 로그인해 주세요.")
        data = {
            "grant_type": "refresh_token",
            "client_id": self.settings.kakao_rest_api_key,
            "refresh_token": token["refresh_token"],
        }
        return self._request_token(data, previous=token)

    def _request_token(self, data: dict, previous: dict | None) -> dict:
        self._require_app_key()
        if self.settings.kakao_client_secret:
            data["client_secret"] = self.settings.kakao_client_secret
        resp = self.http.post(TOKEN_URL, data=data, timeout=10)
        if resp.status_code != 200:
            if previous is not None:
                raise KakaoNotAuthorizedError(
                    f"토큰 갱신 실패({resp.status_code}): {resp.text}. 다시 로그인해 주세요."
                )
            raise KakaoError(f"토큰 발급 실패({resp.status_code}): {resp.text}")

        body = resp.json()
        token = dict(previous or {})
        token.update(body)  # 갱신 응답엔 refresh_token이 없을 수 있음 → 기존 값 유지
        now = time.time()
        token["expires_at"] = now + int(body.get("expires_in", 0))
        if "refresh_token_expires_in" in body:
            token["refresh_token_expires_at"] = now + int(body["refresh_token_expires_in"])
        self.store.save(token)
        return token

    def is_authorized(self) -> bool:
        return self.store.load() is not None

    def access_token(self, force_refresh: bool = False) -> str:
        token = self.store.load()
        if token is None:
            raise KakaoNotAuthorizedError("카카오 로그인이 필요합니다.")
        if force_refresh or token.get("expires_at", 0) - 60 < time.time():
            token = self.refresh(token)
        return token["access_token"]

    # 메시지 --------------------------------------------------------

    def send_to_me(self, text: str, button_title: str = "자세히 보기") -> int:
        """긴 텍스트는 200자 단위로 나누어 여러 메시지로 전송. 전송한 메시지 수를 반환."""
        chunks = split_message(text)
        for i, chunk in enumerate(chunks, start=1):
            if len(chunks) > 1:
                chunk = _with_page_marker(chunk, i, len(chunks))
            self._send_text(chunk, button_title)
        return len(chunks)

    def _send_text(self, text: str, button_title: str) -> None:
        template = {
            "object_type": "text",
            "text": text,
            "link": {
                "web_url": self.settings.kakao_link_url,
                "mobile_web_url": self.settings.kakao_link_url,
            },
            "button_title": button_title,
        }
        payload = {"template_object": json.dumps(template, ensure_ascii=False)}

        resp = self._post_memo(payload, self.access_token())
        if resp.status_code == 401:  # 토큰이 서버에서 만료된 경우 한 번 갱신 후 재시도
            resp = self._post_memo(payload, self.access_token(force_refresh=True))
        if resp.status_code != 200:
            raise KakaoError(f"카카오톡 전송 실패({resp.status_code}): {resp.text}")

    def _post_memo(self, payload: dict, access_token: str) -> requests.Response:
        return self.http.post(
            MEMO_SEND_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            data=payload,
            timeout=10,
        )

    def _require_app_key(self) -> None:
        if not self.settings.kakao_rest_api_key:
            raise KakaoError("KAKAO_REST_API_KEY 가 설정되지 않았습니다 (.env 확인).")


# ── 메시지 분할 ───────────────────────────────────────────────

_PAGE_MARKER_RESERVE = 8  # " (10/10)" 등


def _with_page_marker(chunk: str, i: int, n: int) -> str:
    return f"{chunk}\n({i}/{n})"


def split_message(text: str, limit: int = KAKAO_TEXT_LIMIT) -> list[str]:
    """줄/문장 경계를 최대한 지키면서 limit 이하 조각으로 나눔."""
    text = text.strip()
    if len(text) <= limit:
        return [text]

    budget = limit - _PAGE_MARKER_RESERVE
    # 줄 단위 → 문장 단위 → 글자 단위 순으로 잘게 쪼갠 조각들
    pieces: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if len(line) <= budget:
            pieces.append(line)
            continue
        for sentence in re.split(r"(?<=[.!?。])\s+", line):
            sentence = sentence.strip()
            while len(sentence) > budget:
                pieces.append(sentence[:budget])
                sentence = sentence[budget:]
            if sentence:
                pieces.append(sentence)

    chunks: list[str] = []
    current = ""
    for piece in pieces:
        candidate = f"{current}\n{piece}" if current else piece
        if len(candidate) <= budget:
            current = candidate
        else:
            chunks.append(current)
            current = piece
    if current:
        chunks.append(current)
    return chunks
