r"""Restructure-and-audit loop: ask an LLM for a redesigned transfer prototype,
audit it with tools/audit.py, feed the fatal findings back, up to N attempts.

What used to be three manual steps - paste a prompt into a chat, save the HTML
it returns, run audit.py, read the JSON, ask again - is one command:

  1. serve the project root on :3003 (only if nothing is listening already)
  2. up to --attempts times:
       a. build the prompt from docs/restructure-prompt.md (+ the previous
          attempt's fatal list on a retry), call the model
       b. split the reply into HTML + flow JSON, save both under outputs/
       c. audit it - audit.py is imported and called, never edited
       d. stop on pass; otherwise carry the fatal list into the next prompt
  3. stop the server if this script started it
  4. copy the final build to outputs/restructured_auto.html (+ .flow.json,
     audit_auto.json) and write summary.json next to the per-attempt files

Everything from a run lands in outputs/restructure_auto/<timestamp>/:
  attempt_N.prompt.txt   the exact prompt sent
  attempt_N.response.txt the raw reply
  attempt_N.html / attempt_N.flow.json
  attempt_N.audit.json   audit.py's report (or the parse/validation failure)
  shots/attempt_N/       one screenshot per screen reached
  run.log, summary.json

Usage:
  python tools/run_restructure.py                 # real model, 3 attempts
  python tools/run_restructure.py --attempts 2 --model gpt-4o
  python tools/run_restructure.py --mock pass     # no API: replays Run 1
  python tools/run_restructure.py --mock fail     # no API: a broken flow, every attempt fails

The key comes from .envs (OPENAI_API_KEY=...) or the environment. The model
comes from --model, then RESTRUCTURE_MODEL, then DESIGNREPAIR_MODEL, then gpt-4o.
Exit: 0 = a build passed, 1 = every attempt failed, 2 = could not run.
"""
import argparse
import asyncio
import datetime
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import audit as A                                            # noqa: E402
import audit_stage as S                                      # noqa: E402

PORT = 3003
PROMPT_FILE = os.path.join(ROOT, "docs", "restructure-prompt.md")
ORIGINAL_FILE = os.path.join(ROOT, "inputs", "original_transfer.html")
ORIGINAL_URL = "http://localhost:%d/inputs/original_transfer.html" % PORT
RUNS_DIR = os.path.join(ROOT, "outputs", "restructure_auto")


# --------------------------------------------------------------------------- #
# setup
# --------------------------------------------------------------------------- #
def load_env():
    """OPENAI_API_KEY from .envs if the environment does not have it. The file
    is KEY=value lines, quotes optional, '#' comments."""
    if os.environ.get("OPENAI_API_KEY"):
        return
    path = os.path.join(ROOT, ".envs")
    if not os.path.exists(path):
        return
    for line in io.open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def listening(port):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def ensure_server(log):
    """Return the Popen we started, or None if :3003 was already up (then we
    leave it alone at the end too)."""
    if listening(PORT):
        log("server: :%d already listening, reusing it" % PORT)
        return None
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(PORT), "--directory", ROOT],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        if listening(PORT):
            log("server: started http.server on :%d (pid %d)" % (PORT, proc.pid))
            return proc
        time.sleep(0.1)
    proc.kill()
    raise RuntimeError("could not start http.server on :%d" % PORT)


def load_template():
    text = io.open(PROMPT_FILE, encoding="utf-8").read()
    m = re.search(r"<!-- PROMPT -->\n(.*?)<!-- /PROMPT -->", text, re.S)
    if not m:
        raise RuntimeError("no <!-- PROMPT --> block in " + PROMPT_FILE)
    return m.group(1)


def build_prompt(template, original_html, retry_block):
    return (template.replace("{{ORIGINAL_HTML}}", original_html)
                    .replace("{{RETRY_BLOCK}}", retry_block))


def one_line(s):
    """Playwright errors carry a multi-line call log; keep it on one line so
    the log and the retry list stay one finding per line."""
    return re.sub(r"\s*\n\s*", " / ", str(s)).strip()


def retry_block(report, prev_html, prev_flow_text):
    """The slot the template leaves for a retry: every fatal, then the previous
    output so the model repairs it instead of starting over."""
    lines = []
    for f in report.get("fatal", []):
        where = ("screen=%s: " % f["screen"]) if f.get("screen") else ""
        lines.append("- [%s] %s%s" % (f.get("check") or "?", where, one_line(f.get("detail", ""))))
    if not lines:
        lines.append("- (fatal 목록이 비어 있지만 통과하지 못했다)")
    parts = [
        "## 이전 시도의 실패", "",
        "직전 출력은 검사에서 다음 fatal 에 걸렸다. 아래 목록을 모두 고쳐서 HTML 과 흐름 명세를",
        "다시 전체로 출력하라. 설계를 처음부터 새로 하지 말고 직전 출력을 고쳐라.", "",
        *lines, "",
    ]
    if prev_flow_text:
        parts += ["### 직전 흐름 명세", "", "```json", prev_flow_text.strip(), "```", ""]
    if prev_html:
        parts += ["### 직전 HTML", "", "```html", prev_html.strip(), "```", ""]
    return "\n".join(parts)


# --------------------------------------------------------------------------- #
# the model
# --------------------------------------------------------------------------- #
def call_model(model, prompt, max_tokens):
    from openai import OpenAI
    client = OpenAI()
    t0 = time.time()
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_completion_tokens=max_tokens,
    )
    choice = resp.choices[0]
    usage = getattr(resp, "usage", None)
    return {
        "text": choice.message.content or "",
        "finish_reason": choice.finish_reason,
        "seconds": round(time.time() - t0, 1),
        "usage": {"prompt": getattr(usage, "prompt_tokens", None),
                  "completion": getattr(usage, "completion_tokens", None)} if usage else None,
    }


def mock_reply(mode):
    """No API: replay Run 1. 'fail' hands back a flow whose second step clicks
    a selector that does not exist, so every attempt dies on screen 2."""
    html = io.open(os.path.join(ROOT, "outputs", "restructured_transfer.html"),
                   encoding="utf-8").read()
    flow = json.load(io.open(os.path.join(ROOT, "tools", "flows", "restructured.json"),
                             encoding="utf-8"))
    flow["name"] = "auto"
    if mode == "fail":
        flow["steps"][1]["click"] = "[data-action='does-not-exist']"
    text = "```html\n%s\n```\n\n```json\n%s\n```\n" % (
        html, json.dumps(flow, ensure_ascii=False, indent=2))
    return {"text": text, "finish_reason": "stop", "seconds": 0.0, "usage": None}


FENCE = re.compile(r"```(html|json)[ \t]*\r?\n(.*?)\r?\n[ \t]*```", re.S)


def parse_reply(text):
    """Last ```html``` block and last ```json``` block. Raises ValueError with
    a message meant to go straight into the next prompt."""
    blocks = {}
    for kind, body in FENCE.findall(text):
        blocks[kind] = body
    if "html" not in blocks:
        raise ValueError("답에 ```html 코드 블록이 없다")
    if "json" not in blocks:
        raise ValueError("답에 ```json 흐름 명세 블록이 없다")
    html = blocks["html"]
    if "<html" not in html.lower() or "</html>" not in html.lower():
        raise ValueError("html 블록이 완전한 문서가 아니다 (<html> … </html> 필요)")
    try:
        flow = json.loads(blocks["json"])
    except json.JSONDecodeError as e:
        raise ValueError("흐름 명세가 JSON 으로 읽히지 않는다: %s" % e)
    return html, flow, blocks["json"]


def validate_flow(flow, html):
    """Shape checks audit.py would otherwise crash on, phrased for the model."""
    problems = []
    if not isinstance(flow, dict):
        return ["흐름 명세가 객체가 아니다"]
    steps = flow.get("steps")
    if not isinstance(steps, list) or not steps:
        problems.append("steps 가 비어 있다")
        steps = []
    # literal names only - a template literal like data-screen="${x}" in the
    # script is not a screen
    screens = set(re.findall(r'data-screen="([a-z0-9_-]+)"', html))
    if steps and isinstance(steps[0], dict) and ("click" in steps[0] or "do" in steps[0]):
        problems.append("steps[0] 은 시작 화면이므로 동작(click/do)이 없어야 한다. 각 step 의 "
                        "screen 은 그 동작을 한 *뒤에* 도착해 있는 화면이다 — 동작이 일어나는 "
                        "화면이 아니다. 목록 전체를 한 칸씩 다시 맞춰라")
    # audit.py reads the handler with exactly this pattern; a switch/case or a
    # differently named variable makes every data-action look dead to it.
    handled = set(re.findall(r"a\s*===\s*'([a-z-]+)'", html))
    actions = set(re.findall(r'data-action="([^"]+)"', html))
    if not handled:
        problems.append("클릭 처리기에 `a==='이름'` 분기가 하나도 없다. switch/case 나 다른 변수 "
                        "이름은 검사기가 읽지 못한다. `const a = el.dataset.action;` 뒤에 "
                        "`if(a==='이름'){…} else if(a==='이름'){…}` 형식으로 써라")
    else:
        dead = sorted(actions - handled)
        if dead:
            problems.append("data-action 이 있지만 `a==='…'` 분기가 없는 것: " + ", ".join(dead))
    for i, st in enumerate(steps):
        if not isinstance(st, dict) or "screen" not in st:
            problems.append("steps[%d] 에 screen 이 없다" % i)
            continue
        if st["screen"] not in screens:
            problems.append("steps[%d].screen=%r 은 HTML 의 data-screen 에 없다 (있는 것: %s)"
                            % (i, st["screen"], ", ".join(sorted(screens))))
        if i > 0 and "click" not in st and "do" not in st:
            problems.append("steps[%d] (%s) 에 click 도 do 도 없다" % (i, st["screen"]))
    ids = set(re.findall(r'\bid="([^"]+)"', html))
    req = flow.get("required_ids")
    if not isinstance(req, list):
        problems.append("required_ids 가 목록이 아니다")
        req = []
    for must in ("phone", "dn-amt"):
        if must not in req:
            problems.append("required_ids 에 %r 이 없다" % must)
        if must not in ids:
            problems.append("HTML 에 id=%r 요소가 없다" % must)
    missing = [i for i in req if i not in ids]
    if missing:
        problems.append("required_ids 중 HTML 에 없는 id: " + ", ".join(missing))
    expect = flow.get("expect")
    if not isinstance(expect, dict):
        problems.append("expect 가 객체가 아니다")
    else:
        done = expect.get("done") or []
        if not any(isinstance(p, list) and len(p) == 2 and p[0] == "#dn-amt" for p in done):
            problems.append('expect.done 에 ["#dn-amt", "{AMOUNT_SHOWN}"] 이 없다')
    if flow.get("derived_from_original", False):
        problems.append("derived_from_original 은 false 여야 한다")
    unseen = screens - {st.get("screen") for st in steps if isinstance(st, dict)}
    if unseen:
        problems.append("steps 가 지나가지 않는 화면: " + ", ".join(sorted(unseen)))
    return problems


def failure_report(kind, detail):
    """An audit-shaped report for a reply that never reached the audit, so the
    retry block and summary treat it like any other fatal."""
    return {"passed": False,
            "fatal": [{"check": kind, "screen": None, "detail": detail}],
            "warning": [], "metrics": {"flow": "auto", "not_audited": True}}


# --------------------------------------------------------------------------- #
# audit (tools/audit.py, called as a library)
# --------------------------------------------------------------------------- #
def run_audit(orig_snapshot, orig_html, html_path, flow_path, url, shots, stage):
    """audit.py 로 검사한 뒤 단계 밖 검사를 걷어낸다. 와이어프레임 단계에서는
    대비·레이아웃·상태 색·미정의 클래스를 보지 않는다 - 아직 채우지 않은
    디테일이기 때문이다. 걸러낸 이유는 checks_stood_down 에 남는다."""
    flow = A.load_flow(flow_path)
    rep_html = io.open(html_path, encoding="utf-8").read()
    rep = asyncio.run(A.drive(url, flow, want_shots=shots))
    report = A.audit(orig_snapshot, rep, orig_html, rep_html, flow)
    report = S.apply_stage(report, stage)
    report["inputs"] = {"original": ORIGINAL_URL, "repaired": url, "flow": flow_path,
                        "stage": stage}
    return report


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--attempts", type=int, default=3)
    ap.add_argument("--model", default=None)
    ap.add_argument("--max-tokens", type=int, default=16000,
                    help="completion cap; the HTML alone is ~12k tokens")
    ap.add_argument("--mock", choices=["pass", "fail"], default=None,
                    help="skip the API and replay Run 1 (fail: with a broken flow)")
    ap.add_argument("--original", default=ORIGINAL_FILE)
    ap.add_argument("--stage", choices=sorted(S.STAGES), default="styled",
                    help="검사 단계. wireframe 은 A·B·C·F 만 본다")
    args = ap.parse_args()

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = os.path.join(RUNS_DIR, stamp + ("-mock-" + args.mock if args.mock else ""))
    os.makedirs(run_dir, exist_ok=True)
    log_path = os.path.join(run_dir, "run.log")

    def log(msg):
        line = "%s %s" % (datetime.datetime.now().strftime("%H:%M:%S"), msg)
        print(line, flush=True)
        with io.open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    load_env()
    model = args.model or os.environ.get("RESTRUCTURE_MODEL") \
        or os.environ.get("DESIGNREPAIR_MODEL") or "gpt-4o"
    if not args.mock and not os.environ.get("OPENAI_API_KEY"):
        print("no OPENAI_API_KEY in the environment or .envs", file=sys.stderr)
        return 2

    try:
        template = load_template()
        original_html = io.open(args.original, encoding="utf-8").read()
    except (OSError, RuntimeError) as e:
        print("cannot start: %s" % e, file=sys.stderr)
        return 2

    log("run: %s | model=%s | attempts=%d | stage=%s | mock=%s"
        % (run_dir, model, args.attempts, args.stage, args.mock))
    server = None
    summary = {"run_dir": run_dir, "model": model, "mock": args.mock,
               "stage": args.stage, "attempts": [], "passed": False, "final": None}
    try:
        server = ensure_server(log)
        base_flow = A.load_flow(None)
        log("audit: driving the original once (baseline for contrast / language)")
        orig_snapshot = asyncio.run(A.drive(ORIGINAL_URL, base_flow))

        prev = {"report": None, "html": None, "flow_text": None}
        for n in range(1, args.attempts + 1):
            log("---- attempt %d/%d" % (n, args.attempts))
            block = retry_block(prev["report"], prev["html"], prev["flow_text"]) \
                if prev["report"] else ""
            prompt = build_prompt(template, original_html, block)
            p = os.path.join(run_dir, "attempt_%d" % n)
            io.open(p + ".prompt.txt", "w", encoding="utf-8", newline="\n").write(prompt)
            log("prompt: %d chars%s" % (len(prompt), " (with retry block)" if block else ""))

            if args.mock:
                reply = mock_reply(args.mock)
            else:
                try:
                    reply = call_model(model, prompt, args.max_tokens)
                except Exception as e:                       # network, 429, auth
                    log("model: call failed: %s" % e)
                    report = failure_report("LLM", "모델 호출 실패: %s" % e)
                    json.dump(report, io.open(p + ".audit.json", "w", encoding="utf-8"),
                              ensure_ascii=False, indent=2)
                    summary["attempts"].append({"n": n, "stage": "call", "passed": False,
                                                "error": str(e)})
                    prev = {"report": report, "html": prev["html"], "flow_text": prev["flow_text"]}
                    continue
            io.open(p + ".response.txt", "w", encoding="utf-8", newline="\n").write(reply["text"])
            log("model: %s chars, finish=%s, %ss, usage=%s"
                % (len(reply["text"]), reply["finish_reason"], reply["seconds"], reply["usage"]))

            entry = {"n": n, "finish_reason": reply["finish_reason"], "usage": reply["usage"],
                     "seconds": reply["seconds"]}
            try:
                if reply["finish_reason"] == "length":
                    raise ValueError("답이 길이 제한에서 잘렸다 (finish_reason=length). "
                                     "코드 블록 두 개만, 군더더기 없이 출력하라")
                html, flow, flow_text = parse_reply(reply["text"])
                flow.setdefault("name", "auto")
                flow["derived_from_original"] = False
                problems = validate_flow(flow, html)
            except ValueError as e:
                log("parse: %s" % e)
                report = failure_report("PARSE", str(e))
                entry.update(stage="parse", passed=False, fatal=1)
                json.dump(report, io.open(p + ".audit.json", "w", encoding="utf-8"),
                          ensure_ascii=False, indent=2)
                summary["attempts"].append(entry)
                prev = {"report": report, "html": prev["html"], "flow_text": prev["flow_text"]}
                continue

            html_path, flow_path = p + ".html", p + ".flow.json"
            io.open(html_path, "w", encoding="utf-8", newline="\n").write(html)
            io.open(flow_path, "w", encoding="utf-8", newline="\n").write(
                json.dumps(flow, ensure_ascii=False, indent=2))
            entry["html"], entry["flow"] = html_path, flow_path

            if problems:
                log("flow: %d problem(s): %s" % (len(problems), " | ".join(problems)[:300]))
                report = {"passed": False, "warning": [], "metrics": {"flow": "auto", "not_audited": True},
                          "fatal": [{"check": "FLOW", "screen": None, "detail": d} for d in problems]}
                entry.update(stage="flow", passed=False, fatal=len(problems))
            else:
                rel = os.path.relpath(html_path, ROOT).replace(os.sep, "/")
                url = "http://localhost:%d/%s" % (PORT, rel)
                shots = os.path.join(run_dir, "shots", "attempt_%d" % n)
                os.makedirs(shots, exist_ok=True)
                try:
                    report = run_audit(orig_snapshot, original_html, html_path,
                                       flow_path, url, shots, args.stage)
                except Exception as e:                       # a flow audit.py cannot drive
                    log("audit: crashed: %s: %s" % (type(e).__name__, e))
                    report = failure_report("AUDIT", "검사기가 흐름 명세를 실행하지 못했다: %s: %s"
                                            % (type(e).__name__, e))
                entry.update(stage="audit", passed=bool(report.get("passed")),
                             fatal=len(report.get("fatal", [])),
                             warning=len(report.get("warning", [])))
                m = report.get("metrics", {})
                log("audit: passed=%s fatal=%d warning=%d screens=%s/%s"
                    % (report.get("passed"), len(report.get("fatal", [])),
                       len(report.get("warning", [])), m.get("screens_reached"),
                       m.get("screens_expected")))
                for f in report.get("fatal", [])[:8]:
                    log("  F [%s] %s%s" % (f.get("check"), ("%s: " % f["screen"]) if f.get("screen") else "",
                                          one_line(f.get("detail", ""))[:160]))

            json.dump(report, io.open(p + ".audit.json", "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
            summary["attempts"].append(entry)
            summary["final"] = {"attempt": n, "html": html_path, "flow": flow_path,
                                "audit": p + ".audit.json"}
            if report.get("passed"):
                summary["passed"] = True
                log("PASSED on attempt %d" % n)
                break
            prev = {"report": report, "html": html, "flow_text": flow_text}
        else:
            log("no attempt passed")
    finally:
        if server:
            server.terminate()
            log("server: stopped (pid %d)" % server.pid)

    # the last build that got as far as a file, passed or not
    if summary["final"]:
        f = summary["final"]
        shutil.copy2(f["html"], os.path.join(ROOT, "outputs", "restructured_auto.html"))
        shutil.copy2(f["flow"], os.path.join(ROOT, "outputs", "restructured_auto.flow.json"))
        shutil.copy2(f["audit"], os.path.join(ROOT, "outputs", "audit_auto.json"))
        log("final: attempt %d -> outputs/restructured_auto.html (+ .flow.json, audit_auto.json)"
            % f["attempt"])
    json.dump(summary, io.open(os.path.join(run_dir, "summary.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    log("summary: %s" % os.path.join(run_dir, "summary.json"))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
