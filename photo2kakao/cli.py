"""명령줄 사용법.

  python -m photo2kakao login              # 카카오 로그인 (최초 1회)
  python -m photo2kakao send 사진.jpg [...] # 사진 설명을 카카오톡으로 전송
  python -m photo2kakao serve              # 업로드 웹 서버 실행
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .kakao import KakaoClient
from .pipeline import process_photo


def cmd_login(_args) -> int:
    client = KakaoClient()
    url = client.authorize_url()
    print("1) 아래 주소를 브라우저로 열어 카카오 로그인 후 동의하세요:\n")
    print("   " + url + "\n")
    webbrowser.open(url)
    print("2) 이동된 페이지의 주소창 URL 전체(또는 code 값)를 붙여넣으세요.")
    print("   (웹 서버를 실행 중이면 자동 처리되므로 이 단계는 필요 없습니다)")
    raw = input("> ").strip()
    code = parse_qs(urlparse(raw).query).get("code", [raw])[0]
    client.exchange_code(code)
    client.send_to_me("✅ 사진 설명 자동화가 카카오톡에 연결되었습니다!")
    print("로그인 완료! 카카오톡 '나와의 채팅'에서 테스트 메시지를 확인하세요.")
    return 0


def cmd_send(args) -> int:
    status = 0
    for path in args.photos:
        p = Path(path)
        try:
            result = process_photo(p.read_bytes(), filename=p.name, note=args.note)
        except Exception as exc:  # 여러 장 처리 시 하나 실패해도 계속
            print(f"[실패] {p}: {exc}", file=sys.stderr)
            status = 1
            continue
        print(f"[전송 완료 {result.messages_sent}건] {p}\n{result.description}\n")
    return status


def cmd_serve(args) -> int:
    import uvicorn

    uvicorn.run("photo2kakao.web:app", host=args.host, port=args.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="photo2kakao", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("login", help="카카오 로그인").set_defaults(func=cmd_login)

    p_send = sub.add_parser("send", help="사진 설명을 카카오톡으로 전송")
    p_send.add_argument("photos", nargs="+")
    p_send.add_argument("--note", help="사진에 대한 메모(선택)")
    p_send.set_defaults(func=cmd_send)

    p_serve = sub.add_parser("serve", help="업로드 웹 서버 실행")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)
