// 순수 함수 모음 (테스트 가능)

export const KAKAO_TEXT_LIMIT = 200; // 카카오 텍스트 템플릿 text 최대 길이
const PAGE_MARKER_RESERVE = 8;        // "\n(10/10)"

export const SYSTEM_PROMPT = `당신은 사진을 한국어로 설명해 주는 도우미입니다.
설명은 카카오톡 메시지로 전송되므로 다음을 지켜 주세요.
- 첫 줄: 사진을 한 문장으로 요약한 제목 (이모지 1개로 시작)
- 이어서 3~5개의 짧은 문장으로 주요 대상, 배경·장소, 분위기, 눈에 띄는 디테일을 설명
- 사진 속 글자가 있으면 그대로 옮겨 적기
- 전체 500자 이내, 마크다운 기호(#, *, **) 사용 금지
- 확실하지 않은 내용은 추측이라고 밝히고, 사진 속 실존 인물의 신원은 단정하지 않기`;

/** 줄/문장 경계를 최대한 지키며 카카오 200자 제한에 맞게 나눈 메시지 목록 */
export function splitMessage(text, limit = KAKAO_TEXT_LIMIT) {
  text = text.trim();
  if (text.length <= limit) return [text];

  const budget = limit - PAGE_MARKER_RESERVE;
  const pieces = [];
  for (let line of text.split(/\r?\n/)) {
    line = line.trim();
    if (!line) continue;
    if (line.length <= budget) { pieces.push(line); continue; }
    for (let s of line.split(/(?<=[.!?。])\s+/)) {
      s = s.trim();
      while (s.length > budget) { pieces.push(s.slice(0, budget)); s = s.slice(budget); }
      if (s) pieces.push(s);
    }
  }

  const chunks = [];
  let cur = "";
  for (const p of pieces) {
    const cand = cur ? `${cur}\n${p}` : p;
    if (cand.length <= budget) cur = cand;
    else { chunks.push(cur); cur = p; }
  }
  if (cur) chunks.push(cur);
  return chunks.map((c, i) => `${c}\n(${i + 1}/${chunks.length})`);
}
