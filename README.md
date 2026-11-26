# 📷 사진 설명 → 카카오톡 자동 전송

사진을 업로드하면 **Claude(비전 AI)** 가 사진 설명을 한국어로 만들어 **내 카카오톡('나와의 채팅')** 으로 보내 주는 프로그램입니다.

```
[사진 업로드] ─▶ [Claude API: 사진 설명 생성] ─▶ [카카오 '나에게 보내기' API] ─▶ 📱 카카오톡
 (웹/휴대폰/CLI/단축어)
```

## 📱 스마트폰만으로 쓰기 (추천) — 사진설명톡 웹앱

PC나 서버 없이 **휴대폰 브라우저에서 사진을 골라** 바로 보내는 웹앱이 `docs/` 폴더에 있습니다.
GitHub Pages로 무료 배포되며, 주소는 **https://jeongmin89.github.io/repo_1/** 입니다.

### 최초 1회 설정
1. **GitHub Pages 켜기**: 저장소 → Settings → Pages → Source: *Deploy from a branch* →
   Branch: `claude/photo-description-kakao-automation-yf3giv`, 폴더 `/docs` → Save (1~2분 후 주소 활성화)
2. **Kakao Developers** ([developers.kakao.com](https://developers.kakao.com)) 에서 앱 생성 후
   - 앱 키의 **REST API 키** 복사
   - 플랫폼 → **Web 사이트 도메인**: `https://jeongmin89.github.io`
   - 카카오 로그인 **활성화 ON**, **Redirect URI**: `https://jeongmin89.github.io/repo_1/`
   - 동의항목 → **카카오톡 메시지 전송(talk_message)** 사용 설정
   - 보안 → Client Secret 을 사용 중이면 그 값도 복사 (웹앱 설정에 입력)
3. **Claude API 키** 발급: [platform.claude.com](https://platform.claude.com/) → 크레딧 충전 → API Keys
4. 휴대폰에서 웹앱 주소 접속 → **⚙️ 설정**에 키 입력·저장 → **카카오 연결** → 카카오톡으로 로그인
5. (선택) 브라우저 메뉴 → **홈 화면에 추가** 하면 앱처럼 아이콘으로 실행됩니다.

### 사용
**📷 사진 고르기** → 갤러리에서 선택(여러 장 가능) 또는 촬영 → (선택) 메모 → **보내기** →
카카오톡 '나와의 채팅'에 설명이 도착합니다.

> 키는 그 휴대폰 브라우저에만 저장되고 Claude·카카오 서버로만 전송됩니다. 다른 사람에게 휴대폰을 빌려줄 때는 주의하세요.
> 설정에서 모델을 **Haiku 5.5**로 바꾸면 비용이 1장당 몇 원 수준으로 줄어듭니다.

---

## PC/서버 버전 (Python)

## 기능
- 휴대폰 브라우저에서도 쓸 수 있는 업로드 웹 페이지 (`/`)
- 자동화용 JSON API (`POST /api/photos`) — iOS 단축어, 안드로이드 Tasker 등과 연동
- 명령줄로 여러 장 한 번에 전송 (`python -m photo2kakao send *.jpg`)
- 휴대폰 사진 회전 보정, 큰 사진 자동 축소, iPhone HEIC 지원
- 카카오 토큰 자동 갱신, 200자 제한을 넘는 설명은 자동으로 여러 메시지로 분할

## 1. 준비물

### (1) Claude API 키
[Claude Console](https://platform.claude.com/) 에서 API 키를 발급받습니다.

### (2) 카카오 개발자 앱 설정 ([developers.kakao.com](https://developers.kakao.com))
1. **내 애플리케이션 → 애플리케이션 추가하기**
2. **앱 키** 에서 `REST API 키` 복사
3. **플랫폼 → Web 플랫폼 등록**: `http://localhost:8000` (서버를 외부에 둔다면 그 주소도 추가)
4. **카카오 로그인 → 활성화 설정 ON**, **Redirect URI** 에 `http://localhost:8000/oauth/kakao/callback` 등록
5. **카카오 로그인 → 동의항목 → 카카오톡 메시지 전송(talk_message)** 을 '선택 동의' 이상으로 설정
6. (선택) **보안 → Client Secret** 을 사용하면 그 값을 `.env` 에 입력

## 2. 설치

```bash
git clone <이 저장소>
cd repo_1
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # 그리고 .env 파일에 키 값들을 채워 넣기
```

## 3. 실행

```bash
python -m photo2kakao serve
```

1. 브라우저에서 http://localhost:8000 접속
2. **카카오 로그인** 클릭 → 동의 → 카카오톡에 "연결되었습니다" 메시지가 오면 성공 (최초 1회)
3. 사진을 선택하고 **보내기** → 잠시 후 카카오톡으로 설명이 도착합니다 🎉

> 같은 와이파이의 휴대폰에서 `http://<PC의 IP>:8000` 으로 접속하면 휴대폰 사진도 바로 올릴 수 있습니다.
> 외부 인터넷에 공개할 경우 반드시 `.env` 에 `APP_PASSWORD` 를 설정하세요.

### 명령줄로 사용
```bash
python -m photo2kakao login                       # (웹 서버 없이) 카카오 로그인
python -m photo2kakao send photo1.jpg photo2.png --note "제주 여행"
```

### 자동화 API (iOS 단축어 / Tasker / curl)
```bash
curl -X POST http://localhost:8000/api/photos \
  -H "X-App-Password: 비밀번호" \
  -F "photo=@photo.jpg" -F "note=가족 모임"
# → {"description": "...", "messages_sent": 2}
```
**iOS 단축어 예시**: 공유 시트에서 받기(이미지) → *URL 콘텐츠 가져오기* (방법: POST, 본문: 양식, `photo` = 단축어 입력, 헤더 `X-App-Password`) 로 만들면, 사진 앱에서 **공유 → 단축어** 한 번으로 카카오톡에 설명이 전송됩니다.

## 설정값 (.env)
| 변수 | 설명 | 기본값 |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude API 키 | (필수) |
| `CLAUDE_MODEL` | 사용할 모델 | `claude-opus-5-5` |
| `CLAUDE_EFFORT` | 사고 깊이 `low`/`medium`/`high` (낮을수록 빠르고 저렴) | `medium` |
| `KAKAO_REST_API_KEY` | 카카오 REST API 키 | (필수) |
| `KAKAO_CLIENT_SECRET` | Client Secret (사용 시) | |
| `KAKAO_REDIRECT_URI` | 카카오에 등록한 Redirect URI | `http://localhost:8000/oauth/kakao/callback` |
| `KAKAO_LINK_URL` | 메시지 버튼 링크 (등록된 Web 도메인) | `http://localhost:8000` |
| `KAKAO_TOKEN_PATH` | 토큰 저장 파일 | `.kakao_token.json` |
| `APP_PASSWORD` | 업로드 비밀번호 | (없음) |

## 참고 / 제한 사항
- 카카오 '나에게 보내기'는 **본인 계정의 나와의 채팅**으로만 보낼 수 있습니다 (친구에게 보내기는 별도 심사 필요).
- 텍스트 메시지는 1건당 200자 제한이 있어 긴 설명은 `(1/2)`, `(2/2)` 처럼 나뉘어 전송됩니다.
- 카카오 access token(약 6시간)은 자동 갱신되며, refresh token(약 2개월)이 만료되면 다시 로그인하면 됩니다.
- 안전 정책상 Claude가 설명을 거절하면 서버 측 fallback 모델로 자동 재시도합니다.
- `.env`, `.kakao_token.json` 은 비밀 정보이므로 git 에 올리지 마세요 (`.gitignore` 처리됨).

## 개발
```bash
pip install pytest httpx
pytest -q
```

## 구조
```
photo2kakao/
  config.py       # .env 설정
  image_utils.py  # 회전 보정·축소·JPEG 변환
  describer.py    # Claude 비전으로 설명 생성
  kakao.py        # 카카오 OAuth + 나에게 보내기 + 메시지 분할
  pipeline.py     # 사진 → 설명 → 전송
  web.py          # FastAPI 업로드 서버 / JSON API / 카카오 로그인 콜백
  cli.py          # login / send / serve 명령
tests/test_app.py
```
