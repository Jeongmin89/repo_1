"""사진 업로드 웹 서버 (휴대폰 브라우저에서도 사용 가능).

실행: uvicorn photo2kakao.web:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import hmac
import html

import anthropic
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .config import get_settings
from .describer import DescriptionError
from .image_utils import InvalidImageError
from .kakao import KakaoClient, KakaoError, KakaoNotAuthorizedError
from .pipeline import process_photo

MAX_UPLOAD_BYTES = 20 * 1024 * 1024

app = FastAPI(title="Photo → KakaoTalk")


def _page(body: str) -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>사진 설명 → 카카오톡</title>
<style>
 body{{font-family:-apple-system,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;
      max-width:520px;margin:0 auto;padding:16px;background:#fafafa;color:#222}}
 .card{{background:#fff;border-radius:12px;padding:20px;box-shadow:0 1px 4px #0001}}
 input,textarea,button{{width:100%;box-sizing:border-box;margin:8px 0;font-size:16px}}
 textarea{{min-height:60px;padding:8px}}
 button{{background:#FEE500;border:0;border-radius:8px;padding:14px;font-weight:700}}
 pre{{white-space:pre-wrap;background:#f3f3f3;padding:12px;border-radius:8px}}
 a{{color:#3c1e1e}}
</style></head><body><div class="card">{body}</div></body></html>"""
    )


def _check_password(password: str | None) -> None:
    expected = get_settings().app_password
    if expected and not hmac.compare_digest(password or "", expected):
        raise HTTPException(status_code=401, detail="비밀번호가 올바르지 않습니다.")


async def _read_upload(photo: UploadFile) -> bytes:
    data = await photo.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="파일이 너무 큽니다 (최대 20MB).")
    if not data:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    return data


def _run(data: bytes, filename: str | None, note: str | None):
    try:
        return process_photo(data, filename=filename, note=note or None)
    except KakaoNotAuthorizedError as exc:
        raise HTTPException(status_code=401, detail=f"{exc} → /oauth/kakao 로 로그인하세요.")
    except InvalidImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except DescriptionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except (KakaoError, anthropic.APIError) as exc:
        raise HTTPException(status_code=502, detail=str(exc))


# ── 페이지 ────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
def index():
    settings = get_settings()
    logged_in = KakaoClient().is_authorized()
    status = (
        "✅ 카카오톡 연결됨"
        if logged_in
        else '⚠️ 카카오톡 미연결 — <a href="/oauth/kakao">카카오 로그인</a>'
    )
    pw = (
        '<input type="password" name="password" placeholder="비밀번호" required>'
        if settings.app_password
        else ""
    )
    return _page(
        f"""<h2>📷 사진 설명 → 카카오톡</h2><p>{status}</p>
<form action="/upload" method="post" enctype="multipart/form-data">
  <input type="file" name="photo" accept="image/*" required>
  <textarea name="note" placeholder="(선택) 사진에 대한 메모 — 예: 제주도 여행 둘째 날"></textarea>
  {pw}
  <button type="submit">설명 생성 후 카카오톡으로 보내기</button>
</form>"""
    )


@app.post("/upload", response_class=HTMLResponse)
async def upload(
    photo: UploadFile = File(...),
    note: str = Form(""),
    password: str = Form(""),
):
    _check_password(password)
    data = await _read_upload(photo)
    try:
        result = _run(data, photo.filename, note)
    except HTTPException as exc:
        return _page(
            f"<h3>❌ 실패</h3><p>{html.escape(str(exc.detail))}</p><a href='/'>돌아가기</a>"
        )
    return _page(
        f"""<h3>✅ 카카오톡으로 전송했습니다 ({result.messages_sent}건)</h3>
<pre>{html.escape(result.description)}</pre><a href="/">다른 사진 보내기</a>"""
    )


# ── 자동화용 JSON API (iOS 단축어, Tasker, curl 등) ───────────


@app.post("/api/photos")
async def api_upload(
    photo: UploadFile = File(...),
    note: str = Form(""),
    x_app_password: str | None = Header(default=None),
):
    _check_password(x_app_password)
    data = await _read_upload(photo)
    result = _run(data, photo.filename, note)
    return JSONResponse(
        {"description": result.description, "messages_sent": result.messages_sent}
    )


# ── 카카오 로그인 ─────────────────────────────────────────────


@app.get("/oauth/kakao")
def kakao_login():
    try:
        return RedirectResponse(KakaoClient().authorize_url())
    except KakaoError as exc:
        return _page(f"<p>❌ {html.escape(str(exc))}</p>")


@app.get("/oauth/kakao/callback")
def kakao_callback(code: str | None = None, error: str | None = None,
                   error_description: str | None = None):
    if error or not code:
        msg = error_description or error or "인가 코드가 없습니다."
        return _page(f"<p>❌ 카카오 로그인 실패: {html.escape(msg)}</p><a href='/'>돌아가기</a>")
    try:
        client = KakaoClient()
        client.exchange_code(code)
        client.send_to_me("✅ 사진 설명 자동화가 카카오톡에 연결되었습니다!")
    except KakaoError as exc:
        return _page(f"<p>❌ {html.escape(str(exc))}</p><a href='/'>돌아가기</a>")
    return _page("<h3>✅ 카카오톡 연결 완료</h3><p>테스트 메시지를 확인해 보세요.</p>"
                 "<a href='/'>사진 보내러 가기</a>")
