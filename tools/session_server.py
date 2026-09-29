r"""Run the elderly-participant sessions from a phone, collect the logs on the PC.

The prototypes already record every tap; what was missing was a way to run a
session on a real device and get the data back. This serves the project root
over the local network, hands tools/session.html the condition and task
definitions, and writes one JSON file per participant x condition.

  1. PC and phone on the same Wi-Fi
  2. python tools/session_server.py
  3. open the printed http://<PC ip>:3003/tools/session.html on the phone

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
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The two builds under comparison. `url` is what the phone loads in the frame.
CONDITIONS = [
    {"key": "original",
     "label": "원본 (신한 SOL 재현)",
     "url": "/inputs/original_transfer.html"},
    {"key": "restructured",
     "label": "재구성본 (Run 1)",
     "url": "/outputs/restructured_transfer.html"},
]

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
            # keep the console readable: only note saves and errors
            if "api/session" in (args[0] if args else ""):
                sys.stderr.write("  %s\n" % (fmt % args))

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
            if self.path.split("?")[0] == "/api/sessions":
                files = sorted(os.listdir(sessions_dir)) if os.path.isdir(sessions_dir) else []
                return self._json(200, {"files": [f for f in files if f.endswith(".json")]})
            return super().do_GET()

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=3003)
    ap.add_argument("--sessions", default=os.path.join(ROOT, "sessions"))
    ap.add_argument("--task-file", default=None,
                    help="JSON list of {name, instruction} to replace the built-in tasks")
    args = ap.parse_args()

    tasks = TASKS
    if args.task_file:
        tasks = json.load(io.open(args.task_file, encoding="utf-8"))

    os.makedirs(args.sessions, exist_ok=True)
    ip = local_ip()
    handler = make_handler(args.sessions, tasks)

    print("=" * 62)
    print(" 실험 진행 서버")
    print("=" * 62)
    print(" 폰에서 열 주소 (PC 와 같은 Wi-Fi 여야 합니다):")
    print()
    print("     http://%s:%d/tools/session.html" % (ip, args.port))
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

    srv = ThreadingHTTPServer(("0.0.0.0", args.port), handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n종료했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
