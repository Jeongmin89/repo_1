import io
import json
import time
from types import SimpleNamespace

import pytest
from PIL import Image

from photo2kakao import describer, kakao, pipeline
from photo2kakao.config import Settings
from photo2kakao.image_utils import InvalidImageError, prepare_image


def _settings(tmp_path):
    return Settings(
        claude_model="claude-opus-5-5", claude_effort="medium",
        kakao_rest_api_key="KEY", kakao_client_secret="", kakao_redirect_uri="http://x/cb",
        kakao_link_url="http://x", kakao_token_path=tmp_path / "tok.json", app_password="",
    )


def _png(w=3000, h=2000):
    buf = io.BytesIO()
    Image.new("RGBA", (w, h), (255, 0, 0, 255)).save(buf, "PNG")
    return buf.getvalue()


class FakeResp:
    def __init__(self, status, body=None):
        self.status_code, self._body = status, body or {}
        self.text = json.dumps(self._body)

    def json(self):
        return self._body


class FakeHttp:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def post(self, url, **kw):
        self.calls.append((url, kw))
        return self.responses.pop(0)


def test_prepare_image_resizes_and_converts():
    out = Image.open(io.BytesIO(prepare_image(_png())))
    assert out.format == "JPEG" and max(out.size) == 1568


def test_prepare_image_rejects_garbage():
    with pytest.raises(InvalidImageError):
        prepare_image(b"not an image")


def test_split_message_respects_limit():
    text = "가나다라마바사. " * 80
    chunks = kakao.split_message(text)
    assert len(chunks) > 1
    assert all(len(kakao._with_page_marker(c, 10, 10)) <= 200 for c in chunks)
    assert kakao.split_message("짧은 글") == ["짧은 글"]


def test_send_refreshes_expired_token(tmp_path):
    s = _settings(tmp_path)
    s.kakao_token_path.write_text(json.dumps(
        {"access_token": "old", "refresh_token": "r", "expires_at": time.time() - 10}))
    http = FakeHttp([FakeResp(200, {"access_token": "new", "expires_in": 3600}),
                     FakeResp(200, {"result_code": 0})])
    client = kakao.KakaoClient(s, session=http)
    assert client.send_to_me("안녕") == 1
    assert http.calls[0][0] == kakao.TOKEN_URL
    assert http.calls[1][1]["headers"]["Authorization"] == "Bearer new"
    tmpl = json.loads(http.calls[1][1]["data"]["template_object"])
    assert tmpl["object_type"] == "text" and tmpl["text"] == "안녕"
    saved = json.loads(s.kakao_token_path.read_text())
    assert saved["refresh_token"] == "r"  # 기존 refresh token 유지


def test_not_logged_in(tmp_path):
    with pytest.raises(kakao.KakaoNotAuthorizedError):
        kakao.KakaoClient(_settings(tmp_path), session=FakeHttp([])).access_token()


def test_authorize_url(tmp_path):
    url = kakao.KakaoClient(_settings(tmp_path)).authorize_url()
    assert "client_id=KEY" in url and "scope=talk_message" in url


class FakeClaude:
    def __init__(self, stop_reason="end_turn", text="🌅 노을 사진"):
        self.kwargs = None
        resp = SimpleNamespace(stop_reason=stop_reason,
                               content=[SimpleNamespace(type="text", text=text)])
        outer = self

        class _M:
            def create(self, **kw):
                outer.kwargs = kw
                return resp

        self.beta = SimpleNamespace(messages=_M())


def test_describe_image_request_shape():
    fake = FakeClaude()
    assert describer.describe_image(_png(100, 100), note="여행", client=fake) == "🌅 노을 사진"
    content = fake.kwargs["messages"][0]["content"]
    assert content[0]["source"]["media_type"] == "image/jpeg"
    assert "여행" in content[1]["text"]
    assert fake.kwargs["fallbacks"] == "default"


def test_describe_image_refusal():
    with pytest.raises(describer.DescriptionError):
        describer.describe_image(_png(10, 10), client=FakeClaude(stop_reason="refusal"))


def test_pipeline(monkeypatch, tmp_path):
    s = _settings(tmp_path)
    s.kakao_token_path.write_text(json.dumps(
        {"access_token": "a", "refresh_token": "r", "expires_at": time.time() + 3600}))
    http = FakeHttp([FakeResp(200)])
    monkeypatch.setattr(pipeline, "describe_image", lambda b, note=None: "설명")
    r = pipeline.process_photo(b"x", filename="a.jpg", kakao=kakao.KakaoClient(s, session=http))
    assert r.messages_sent == 1
    assert "a.jpg" in json.loads(http.calls[0][1]["data"]["template_object"])["text"]


def test_web_index_and_upload(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from photo2kakao import web

    monkeypatch.setenv("KAKAO_TOKEN_PATH", str(tmp_path / "none.json"))
    c = TestClient(web.app)
    assert "카카오 로그인" in c.get("/").text
    monkeypatch.setattr(web, "process_photo",
                        lambda d, filename=None, note=None: pipeline.Result("<b>설명</b>", 1))
    r = c.post("/upload", files={"photo": ("a.jpg", b"123", "image/jpeg")})
    assert "&lt;b&gt;설명" in r.text
    r = c.post("/api/photos", files={"photo": ("a.jpg", b"123", "image/jpeg")})
    assert r.json() == {"description": "<b>설명</b>", "messages_sent": 1}
