r"""대시보드를 보기 위한 서버. 127.0.0.1 에서만 열린다.

내부 확인용 대시보드(web/dashboard.html)와 그것이 읽는 것 - 색인, "화면
비교" 가 iframe 으로 여는 빌드 HTML, 그 화면의 스크린샷 - 만 서빙한다.
허용 목록은 ALLOW 에 있고, 거기 없는 것은 파일이 있어도 404 다. 전에는
프로젝트 루트 전체를 디렉터리 목록과 함께 LAN 에 서빙해서, 같은 Wi-Fi 의
누구나 .envs(API 키)·.git/·sessions/ 를 받아 갈 수 있었다.

  python -m senior_ui.experiment.server      (또는 시작.bat)
  http://localhost:3003/web/dashboard.html

본실험은 Flutter 더미앱(senior-ui-dummy-app)으로 한다. 여기 있는 HTML 실험
장치(web/session.html + POST /api/session)는 본실험에 쓰지 않으므로 기본으로
꺼져 있고, --session 을 줄 때만 켜진다. 기록 보관용이다.

Options:
  --port 3003          the port to serve on
  --session            HTML 실험 장치를 켠다 (기본 꺼짐)
  --sessions <dir>     --session 일 때 쓸 곳 (default: sessions/)
  --task-file <json>   replace the built-in task list
"""
import argparse
import io
import json
import os
import re
import sys
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from senior_ui.config import CONDITIONS, OUTPUTS_DIR, PORT, ROOT
from senior_ui.viewer import build_index

# What the participant is asked to do. The long task is the one the redesign
# was aimed at: a first-time account, typed in full. The short task exists to
# check whether the saved-recipient path helps too - both builds have one.
TASKS = [
    {"name": "긴 과업 · 처음 보내는 계좌",
     "instruction": "김시현 씨에게 1만 원을 보내 주세요. "
                    "계좌번호는 3333-0000-0000-0 이고, 카카오뱅크입니다. "
                    "저장된 목록에 있더라도 계좌번호를 직접 넣어서 보내 주세요."},
    {"name": "짧은 과업 · 저장된 사람",
     "instruction": "김시현 씨에게 1만 원을 보내 주세요."},
]


# 바인드 주소. 루프백만 - LAN 에 여는 옵션은 두지 않는다.
HOST = "127.0.0.1"

# 서빙하는 것의 전부. 루트 기준 경로가 이 중 하나와 정확히 맞지 않으면 404 다.
#
#   - 대시보드 자신(web/dashboard.html·css·js)과 그것이 읽는 색인
#   - "화면 비교" 가 iframe 으로 여는 빌드 HTML. outputs/restructure_auto/
#     <실행>/attempt_N.html 처럼 하위 폴더에 있는 것도 있어서 깊이를 제한하지
#     않는다. 대신 확장자가 .html 인 파일만 나간다
#   - 그 화면의 스크린샷 png
#
# 목록에 없는 것은 파일이 있어도 404 다. .envs(API 키) · .git/ · sessions/
# (피험자 기록) · inputs/*.png(실제 앱 캡처 - 실명이 보인다) 가 그렇다.
# 디렉터리는 끝이 파일 이름이어야 하는 이 목록에 걸릴 수 없으므로 목록도
# 저절로 꺼지지만, list_directory() 를 따로 막아 두어 우연에 기대지 않는다.
ALLOW = tuple(re.compile(x) for x in (
    r"web/dashboard\.[A-Za-z0-9]+",
    r"outputs/index\.json",
    r"inputs/original_transfer\.html",
    r"(?:outputs|results)/(?:[^/]+/)*[^/]+\.html",
    r"(?:outputs|results)/shots/(?:[^/]+/)*[^/]+\.png",
))


# --session 을 줄 때만 더해지는 것. HTML 실험 장치(web/session.html)는
# 본실험에 쓰지 않으므로 기본으로는 이것도 404 다.
SESSION_ALLOW = tuple(re.compile(x) for x in (
    r"web/session\.[A-Za-z0-9]+",
))

# 루프백으로 들어온 요청인가. 서버는 127.0.0.1 에만 바인드하므로 밖에서는
# 닿지 않지만, 세션 저장은 받는 쪽에서도 한 번 더 본다.
LOCAL = ("127.0.0.1", "::1", "::ffff:127.0.0.1")


def is_local(addr):
    return addr in LOCAL


def clean_path(path):
    """요청 경로를 루트 기준 상대 경로로 바로잡는다. 질의와 %XX 를 풀고
    '.' 과 '..' 을 접는다. 루트 위로 올라가려는 '..' 은 버린다.

    허용 목록은 이 결과로 본다. 받은 그대로 보면
    /web/dashboard.html/../../.envs 가 목록을 비켜 간다."""
    path = urllib.parse.unquote(urllib.parse.urlsplit(path).path)
    out = []
    for seg in path.replace("\\", "/").split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if out:
                out.pop()
            continue
        out.append(seg)
    return "/".join(out)


def allowed(rel, with_session=False):
    """바로잡은 경로가 허용 목록에 있는가. 파일을 보지 않는다."""
    pats = ALLOW + SESSION_ALLOW if with_session else ALLOW
    return any(p.fullmatch(rel) for p in pats)


def make_server(port, handler):
    return ThreadingHTTPServer((HOST, port), handler)


def reindex():
    """outputs/index.json 을 다시 만든다. 뷰어의 '다시 읽기' 가 부른다."""
    idx = build_index.build()
    out = os.path.join(OUTPUTS_DIR, "index.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with io.open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(idx, f, ensure_ascii=False, indent=1)
    return {"ok": True, "builds": len(idx["builds"]), "changes": len(idx["changes"]),
            "generated": idx["generated"]}


def make_handler(sessions_dir, tasks, allow_session=False):
    """allow_session=False 면 HTML 실험 장치(web/session.* · /api/config ·
    /api/sessions · /api/session)가 전부 404 다. 대시보드만 쓸 때의 기본값."""

    class H(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=ROOT, **kw)

        def log_message(self, fmt, *args):
            # 콘솔은 저장된 세션만 적는다. args[0] 은 요청 줄일 때도 있고
            # send_error() 가 부를 때는 HTTPStatus 다 - 문자열인지 먼저 본다.
            # 보지 않으면 in 이 TypeError 를 내고, 응답을 쓰기도 전에
            # 연결이 끊어져 모든 404 가 빈 응답이 된다.
            first = args[0] if args else ""
            if isinstance(first, str) and "api/session" in first:
                sys.stderr.write("  %s\n" % (fmt % args))

        def _static(self):
            """허용 목록에 있으면 바로잡은 경로를, 아니면 404 를 보내고
            None 을 돌려준다."""
            rel = clean_path(self.path)
            if not allowed(rel, allow_session):
                self.send_error(404, "Not found")
                return None
            return "/" + rel

        def _body(self):
            """요청 본문을 다 읽어 돌려준다. 길이가 없거나 이상하면 빈
            바이트열이다."""
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return b""
            out = []
            while n > 0:
                chunk = self.rfile.read(min(n, 65536))
                if not chunk:
                    break
                out.append(chunk)
                n -= len(chunk)
            return b"".join(out)

        def list_directory(self, path):
            self.send_error(404, "Not found")
            return None

        def _json(self, code, payload, headers=()):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            for k, v in headers:
                self.send_header(k, v)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if allow_session and self.path.split("?")[0] == "/api/config":
                return self._json(200, {"conditions": CONDITIONS, "tasks": tasks})
            if allow_session and self.path.split("?")[0] == "/api/sessions":
                files = sorted(os.listdir(sessions_dir)) if os.path.isdir(sessions_dir) else []
                return self._json(200, {"files": [f for f in files if f.endswith(".json")]})
            if self.path.split("?")[0] == "/api/reindex":
                # 색인을 새로 쓰는 일이다. GET 으로 받으면 주소창에 한 번
                # 넣는 것으로도, 브라우저의 선읽기로도 돌아간다.
                return self._json(405, {"error": "POST 로 보내세요"},
                                  [("Allow", "POST")])
            p = self._static()
            if p is None:
                return
            self.path = p
            return super().do_GET()

        def do_HEAD(self):
            p = self._static()
            if p is None:
                return
            self.path = p
            return super().do_HEAD()

        def do_POST(self):
            # 본문은 무엇을 돌려주든 먼저 다 읽는다. 읽지 않고 응답하고
            # 닫으면 받지 않은 바이트가 남아 연결이 RST 로 끊기고(Windows
            # 10053), 이미 보낸 응답까지 같이 사라진다. 그러면 "꺼져
            # 있습니다" 라는 404 가 서버가 죽은 것과 구별되지 않는다.
            raw = self._body()
            route = self.path.split("?")[0]

            if route == "/api/reindex":
                try:
                    return self._json(200, reindex())
                except Exception as e:
                    return self._json(500, {"error": "%s: %s" % (type(e).__name__, e)})
            if route != "/api/session":
                return self._json(404, {"error": "unknown endpoint"})
            if not allow_session:
                # 본실험은 Flutter 더미앱으로 한다. --session 없이는 세션을
                # 받지 않는다 - 폴더도 만들지 않는다.
                return self._json(404, {"error": "session saving is off (--session)"})
            if not is_local(self.client_address[0]):
                return self._json(403, {"error": "127.0.0.1 에서만 받습니다"})
            try:
                data = json.loads(raw.decode("utf-8"))
            except Exception as e:
                return self._json(400, {"error": "bad payload: %s" % e})

            pid = data.get("participant")
            cond = str(data.get("condition") or "unknown")
            if not isinstance(pid, int) or pid <= 0:
                return self._json(400, {"error": "participant must be a positive integer"})
            cond = re.sub(r"[^a-z0-9_-]", "", cond.lower()) or "unknown"
            order = data.get("order_index", 0)

            os.makedirs(sessions_dir, exist_ok=True)
            name = "P%02d_%d_%s.json" % (pid, int(order) + 1, cond)
            path = os.path.join(sessions_dir, name)
            with io.open(path, "w", encoding="utf-8", newline="\n") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            m = data.get("metrics") or {}
            sys.stderr.write(
                "저장 %s | %.1f초 · %s탭 · 빗나감 %s · 되돌아가기 %s · %s\n"
                % (name, m.get("seconds", 0), m.get("taps", "?"), m.get("misses", "?"),
                   m.get("backs", "?"), "완료" if data.get("completed") else "중단"))
            return self._json(200, {"ok": True, "file": name})

    return H


def build_parser():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--sessions", default=os.path.join(ROOT, "sessions"))
    ap.add_argument("--task-file", default=None,
                    help="JSON list of {name, instruction} to replace the built-in tasks")
    ap.add_argument("--session", action="store_true",
                    help="HTML 실험 장치(web/session.html · /api/session)를 켠다. "
                         "본실험은 Flutter 더미앱으로 하므로 기본은 꺼짐이다")
    return ap


def banner(port, sessions_dir, tasks, allow_session=False):
    """서버가 띄우는 안내. 테스트가 이것을 그대로 본다.

    폰에서 여는 주소와 방화벽 안내는 LAN 에 서빙할 때의 안내였다. 서버를
    루프백으로 돌린 뒤에도 그 안내가 남아 있으면 사람이 다시 구멍을 낸다."""
    L = ["=" * 62,
         " 대시보드",
         "=" * 62,
         " 이 PC 의 브라우저에서 엽니다 (다른 기기에서는 열리지 않습니다):",
         "",
         "     http://localhost:%d/web/dashboard.html" % port,
         ""]
    if allow_session:
        L += [" HTML 실험 장치 (--session) - 기록 보관용. 본실험은 Flutter 더미앱입니다:",
              "",
              "     http://localhost:%d/web/session.html" % port,
              "",
              " 조건 : " + " / ".join(c["label"] for c in CONDITIONS),
              " 과업 : " + " / ".join(t["name"] for t in tasks),
              " 저장 : %s" % sessions_dir,
              ""]
    L += ["=" * 62, " Ctrl+C 로 종료", ""]
    return "\n".join(L)


def main():
    args = build_parser().parse_args()

    tasks = TASKS
    if args.task_file:
        tasks = json.load(io.open(args.task_file, encoding="utf-8"))

    if args.session:
        os.makedirs(args.sessions, exist_ok=True)
    try:
        r = reindex()
        print(" 인덱스: 빌드 %d개 · 변경 %d건" % (r["builds"], r["changes"]))
    except Exception as e:
        print(" 인덱스를 만들지 못했습니다: %s" % e)
    handler = make_handler(args.sessions, tasks, allow_session=args.session)
    print(banner(args.port, args.sessions, tasks, allow_session=args.session))

    srv = make_server(args.port, handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n종료했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
