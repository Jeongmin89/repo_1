import Anthropic from "https://cdn.jsdelivr.net/npm/@anthropic-ai/sdk@1.8.0/+esm";
import { SYSTEM_PROMPT, splitMessage } from "./lib.js";

const $ = (id) => document.getElementById(id);
const REDIRECT_URI = location.origin + location.pathname; // 이 페이지 자체가 카카오 콜백
const MAX_SIDE = 1568;

// ── 저장소 (이 기기 브라우저에만 저장) ─────────────────────────
const store = {
  get(k, d = "") { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch {} },
  del(k) { try { localStorage.removeItem(k); } catch {} },
  json(k) { try { return JSON.parse(localStorage.getItem(k)); } catch { return null; } },
};
const cfg = () => ({
  claudeKey: store.get("claudeKey"),
  model: store.get("model", "claude-opus-5-5"),
  kakaoKey: store.get("kakaoKey"),
  kakaoSecret: store.get("kakaoSecret"),
});

// ── 카카오 ────────────────────────────────────────────────────
class KakaoAuthError extends Error {}

function kakaoLogin() {
  const { kakaoKey } = cfg();
  if (!kakaoKey) { openSettings("카카오 REST API 키를 먼저 입력해 주세요."); return; }
  const q = new URLSearchParams({ client_id: kakaoKey, redirect_uri: REDIRECT_URI,
                                  response_type: "code", scope: "talk_message" });
  location.href = `https://kauth.kakao.com/oauth/authorize?${q}`;
}

async function requestToken(params, previous) {
  const { kakaoKey, kakaoSecret } = cfg();
  const body = new URLSearchParams({ client_id: kakaoKey, ...params });
  if (kakaoSecret) body.set("client_secret", kakaoSecret);
  const res = await fetch("https://kauth.kakao.com/oauth/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded;charset=utf-8" },
    body,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = data.error_description || data.error || res.status;
    if (previous) throw new KakaoAuthError(`카카오 연결이 만료되었습니다. 다시 연결해 주세요. (${msg})`);
    throw new Error(`카카오 토큰 발급 실패: ${msg}`);
  }
  const now = Date.now();
  const token = { ...(previous || {}), ...data, expires_at: now + data.expires_in * 1000 };
  if (data.refresh_token_expires_in) token.refresh_expires_at = now + data.refresh_token_expires_in * 1000;
  store.set("kakaoToken", JSON.stringify(token));
  return token;
}

async function accessToken(force = false) {
  let t = store.json("kakaoToken");
  if (!t) throw new KakaoAuthError("카카오톡 연결이 필요합니다.");
  if (force || t.expires_at - 60_000 < Date.now()) {
    if (!t.refresh_token) throw new KakaoAuthError("카카오톡을 다시 연결해 주세요.");
    t = await requestToken({ grant_type: "refresh_token", refresh_token: t.refresh_token }, t);
  }
  return t.access_token;
}

async function sendKakaoText(text) {
  const template = {
    object_type: "text", text,
    link: { web_url: REDIRECT_URI, mobile_web_url: REDIRECT_URI },
    button_title: "사진설명톡 열기",
  };
  const body = new URLSearchParams({ template_object: JSON.stringify(template) });
  const post = (tok) => fetch("https://kapi.kakao.com/v2/api/talk/memo/default/send", {
    method: "POST",
    headers: { Authorization: `Bearer ${tok}`,
               "Content-Type": "application/x-www-form-urlencoded;charset=utf-8" },
    body,
  });
  let res = await post(await accessToken());
  if (res.status === 401) res = await post(await accessToken(true));
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    if (res.status === 401 || res.status === 403)
      throw new KakaoAuthError(`카카오 권한 오류: ${d.msg || res.status}. 다시 연결해 주세요.`);
    throw new Error(`카카오톡 전송 실패: ${d.msg || res.status}`);
  }
}

async function sendKakao(text) {
  const parts = splitMessage(text);
  for (const p of parts) await sendKakaoText(p);
  return parts.length;
}

// ── 이미지 처리 ───────────────────────────────────────────────
async function toJpegBase64(file) {
  // imageOrientation: 휴대폰 사진의 회전(EXIF) 반영
  const bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
  const scale = Math.min(1, MAX_SIDE / Math.max(bmp.width, bmp.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bmp.width * scale);
  canvas.height = Math.round(bmp.height * scale);
  canvas.getContext("2d").drawImage(bmp, 0, 0, canvas.width, canvas.height);
  bmp.close?.();
  return canvas.toDataURL("image/jpeg", 0.85).split(",")[1];
}

// ── Claude ────────────────────────────────────────────────────
async function describe(base64, note) {
  const { claudeKey, model } = cfg();
  const client = new Anthropic({ apiKey: claudeKey, dangerouslyAllowBrowser: true });
  let instruction = "이 사진을 설명해 주세요.";
  if (note) instruction += `\n\n사용자 메모(참고용): ${note}`;

  const params = {
    model,
    max_tokens: 16000,
    system: SYSTEM_PROMPT,
    messages: [{ role: "user", content: [
      { type: "image", source: { type: "base64", media_type: "image/jpeg", data: base64 } },
      { type: "text", text: instruction },
    ] }],
  };
  if (model !== "claude-haiku-5-5") {
    // 안전 분류기가 거절하면 서버가 다른 모델로 자동 재시도 (Haiku는 미지원)
    params.betas = ["server-side-fallback-2026-07-01"];
    params.fallbacks = "default";
  }

  let res;
  try {
    res = await client.beta.messages.create(params);
  } catch (e) {
    if (e instanceof Anthropic.AuthenticationError) throw new Error("Claude API 키가 올바르지 않습니다.");
    if (e instanceof Anthropic.RateLimitError) throw new Error("요청이 많습니다. 잠시 후 다시 시도해 주세요.");
    if (e instanceof Anthropic.APIError) throw new Error(`Claude 오류 (${e.status ?? "네트워크"}): ${e.message}`);
    throw e;
  }
  if (res.stop_reason === "refusal") throw new Error("이 사진은 설명을 생성할 수 없습니다.");
  const text = res.content.filter((b) => b.type === "text").map((b) => b.text).join("").trim();
  if (!text) throw new Error("설명 결과가 비어 있습니다.");
  return text;
}

// ── 화면 ──────────────────────────────────────────────────────
let files = [];

function renderKakaoStatus() {
  const t = store.json("kakaoToken");
  const on = !!t;
  $("kakaoStatus").textContent = on ? "✅ 카카오톡 연결됨" : "⚠️ 카카오톡 미연결";
  $("kakaoLogin").classList.toggle("hidden", on);
  $("kakaoLogout").classList.toggle("hidden", !on);
}

function openSettings(message) {
  $("settingsBox").open = true;
  $("settingsBox").scrollIntoView({ behavior: "smooth" });
  if (message) alert(message);
}

function loadSettingsForm() {
  const c = cfg();
  $("claudeKey").value = c.claudeKey;
  $("model").value = c.model;
  $("kakaoKey").value = c.kakaoKey;
  $("kakaoSecret").value = c.kakaoSecret;
  $("redirectUri").textContent = REDIRECT_URI;
}

function addResultRow(file) {
  $("resultsCard").classList.remove("hidden");
  const row = document.createElement("div");
  row.className = "result";
  const img = document.createElement("img");
  img.src = URL.createObjectURL(file);
  const body = document.createElement("div");
  body.className = "body";
  const status = document.createElement("div");
  status.className = "status";
  const pre = document.createElement("pre");
  body.append(status, pre);
  row.append(img, body);
  $("results").prepend(row);
  return {
    set(text, cls = "") { status.textContent = text; status.className = `status ${cls}`; },
    desc(text) { pre.textContent = text; },
  };
}

async function processAll() {
  const c = cfg();
  if (!c.claudeKey) return openSettings("Claude API 키를 먼저 입력해 주세요.");
  if (!store.json("kakaoToken")) return alert("먼저 위쪽의 '카카오 연결'을 눌러 주세요.");

  const note = $("note").value.trim();
  const batch = files;
  $("send").disabled = true;

  for (const file of batch) {
    const row = addResultRow(file);
    try {
      row.set("🖼️ 사진 준비 중…");
      const b64 = await toJpegBase64(file);
      row.set("🤖 설명 만드는 중…");
      const text = await describe(b64, note);
      row.desc(text);
      row.set("💬 카카오톡 보내는 중…");
      const n = await sendKakao(text);
      row.set(`✅ 카카오톡 전송 완료 (${n}건)`, "ok");
    } catch (e) {
      row.set(`❌ ${e.message}`, "err");
      if (e instanceof KakaoAuthError) { store.del("kakaoToken"); renderKakaoStatus(); break; }
    }
  }

  files = [];
  $("photos").value = "";
  $("thumbs").replaceChildren();
  $("send").disabled = true;
  $("send").textContent = "설명 만들어서 카카오톡으로 보내기";
}

async function handleKakaoCallback() {
  const q = new URLSearchParams(location.search);
  const code = q.get("code"), error = q.get("error");
  if (!code && !error) return;
  history.replaceState(null, "", REDIRECT_URI); // 주소창에서 code 제거
  if (error) return alert(`카카오 연결 실패: ${q.get("error_description") || error}`);
  try {
    await requestToken({ grant_type: "authorization_code", redirect_uri: REDIRECT_URI, code });
    renderKakaoStatus();
    await sendKakao("✅ 사진설명톡이 카카오톡에 연결되었습니다!");
    alert("카카오톡 연결 완료! '나와의 채팅'에서 테스트 메시지를 확인하세요.");
  } catch (e) {
    alert(e.message);
  }
}

function init() {
  loadSettingsForm();
  renderKakaoStatus();

  $("photos").addEventListener("change", (e) => {
    files = [...e.target.files];
    $("thumbs").replaceChildren(...files.map((f) => {
      const img = document.createElement("img");
      img.src = URL.createObjectURL(f);
      return img;
    }));
    $("send").disabled = files.length === 0;
    $("send").textContent = files.length > 1
      ? `${files.length}장 설명 만들어서 카카오톡으로 보내기`
      : "설명 만들어서 카카오톡으로 보내기";
  });
  $("send").addEventListener("click", processAll);
  $("kakaoLogin").addEventListener("click", kakaoLogin);
  $("kakaoLogout").addEventListener("click", () => {
    if (confirm("카카오톡 연결을 해제할까요?")) { store.del("kakaoToken"); renderKakaoStatus(); }
  });
  $("saveSettings").addEventListener("click", () => {
    store.set("claudeKey", $("claudeKey").value.trim());
    store.set("model", $("model").value);
    store.set("kakaoKey", $("kakaoKey").value.trim());
    store.set("kakaoSecret", $("kakaoSecret").value.trim());
    $("settingsBox").open = false;
    alert("저장했습니다.");
  });

  if (!cfg().claudeKey || !cfg().kakaoKey) $("settingsBox").open = true;
  handleKakaoCallback();
}

init();
