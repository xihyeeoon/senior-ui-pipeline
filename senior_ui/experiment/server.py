r"""Run the elderly-participant sessions from a phone, collect the logs on the PC.

The prototypes already record every tap; what was missing was a way to run a
session on a real device and get the data back. This serves the project root
over the local network, hands web/session.html the condition and task
definitions, and writes one JSON file per participant x condition.

  1. PC and phone on the same Wi-Fi
  2. python -m senior_ui.experiment.server
  3. open the printed http://<PC ip>:3003/web/session.html on the phone

Saved to sessions/P01_1_original.json:
  participant, condition, order_index, task, completed, elapsed_ms,
  metrics (seconds / taps / misses / backs / deletes / dwell per screen)
  and the full event log, so anything not summarised can still be recovered.

Options:
  --port 3003          the port to serve on
  --sessions <dir>     where to write (default: sessions/)
  --task-file <json>   replace the built-in task list

Task and condition definitions live in CONDITIONS / TASKS below. Changing the
task wording is a one-line edit there - it is read by the phone at page load.
"""
import argparse
import io
import json
import os
import re
import socket
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


def allowed(rel):
    """바로잡은 경로가 허용 목록에 있는가. 파일을 보지 않는다."""
    return any(p.fullmatch(rel) for p in ALLOW)


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


def local_ip():
    """The address the phone should use. Needs no reachable network."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def make_handler(sessions_dir, tasks):
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
            if not allowed(rel):
                self.send_error(404, "Not found")
                return None
            return "/" + rel

        def list_directory(self, path):
            self.send_error(404, "Not found")
            return None

        def _json(self, code, payload):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.split("?")[0] == "/api/config":
                return self._json(200, {"conditions": CONDITIONS, "tasks": tasks})
            if self.path.split("?")[0] == "/api/reindex":
                try:
                    return self._json(200, reindex())
                except Exception as e:
                    return self._json(500, {"error": "%s: %s" % (type(e).__name__, e)})
            if self.path.split("?")[0] == "/api/sessions":
                files = sorted(os.listdir(sessions_dir)) if os.path.isdir(sessions_dir) else []
                return self._json(200, {"files": [f for f in files if f.endswith(".json")]})

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
            if self.path.split("?")[0] != "/api/session":
                return self._json(404, {"error": "unknown endpoint"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
                data = json.loads(self.rfile.read(n).decode("utf-8"))
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
    return ap


def main():
    args = build_parser().parse_args()

    tasks = TASKS
    if args.task_file:
        tasks = json.load(io.open(args.task_file, encoding="utf-8"))

    os.makedirs(args.sessions, exist_ok=True)
    try:
        r = reindex()
        print(" 인덱스: 빌드 %d개 · 변경 %d건" % (r["builds"], r["changes"]))
    except Exception as e:
        print(" 인덱스를 만들지 못했습니다: %s" % e)
    ip = local_ip()
    handler = make_handler(args.sessions, tasks)

    print("=" * 62)
    print(" 실험 진행 서버")
    print("=" * 62)
    print(" 폰에서 열 주소 — 실험 진행 (PC 와 같은 Wi-Fi 여야 합니다):")
    print()
    print("     http://%s:%d/web/session.html" % (ip, args.port))
    print()
    print(" PC 브라우저에서 열 주소 — 파이프라인 확인:")
    print()
    print("     http://localhost:%d/web/dashboard.html" % args.port)
    print()
    print(" 조건 : " + " / ".join(c["label"] for c in CONDITIONS))
    print(" 과업 : " + " / ".join(t["name"] for t in tasks))
    print(" 저장 : %s" % args.sessions)
    print()
    print(" 연결이 안 되면 PC 방화벽에서 이 포트를 열어야 합니다:")
    print('   New-NetFirewallRule -DisplayName "senior-ui 실험" -Direction Inbound '
          "-LocalPort %d -Protocol TCP -Action Allow" % args.port)
    print("=" * 62)
    print(" Ctrl+C 로 종료")
    print()

    srv = make_server(args.port, handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n종료했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
