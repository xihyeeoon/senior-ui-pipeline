r"""정리 전의 동작을 기준값으로 한 번 뽑는다.

구조 정리는 동작을 바꾸지 않아야 한다. 그 "바꾸지 않았음" 을 사람 눈이 아니라
파일 비교로 확인하려면 정리 전 출력이 디스크에 있어야 한다. 이 스크립트가 그
출력을 만들고, tests/test_baseline.py 와 tests/test_drive.py 가 그것과 비교한다.

tools/ 는 한 줄도 건드리지 않는다. 전부 tests/_api.py 를 거쳐 호출한다.

  [1] audit.py main() 과 같은 순서로 4가지 경우
      원본 vs 원본 / Run1 / Run2 / Run3
  [2] retry_block (실제 리포트 3개 + 합성 리포트 1개) + brief_failure
  [3] 재구성 프롬프트 조립 (choices_block + 첫 시도 / 재시도 프롬프트 전문)
  [4] parse_reply / mock_reply
  [5] mock 실행 (--mock pass, --mock fail)
  [6] 가짜 세션 4건으로 session_report

빌드는 results/ 를 쓴다. outputs/ 는 .gitignore 에 있어 PC 마다 내용이 달라서
기준값의 입력으로 쓸 수 없다.

Usage:
  .\.venv\Scripts\python.exe tests/capture_baseline.py
  .\.venv\Scripts\python.exe tests/capture_baseline.py --out <다른 폴더>
"""
import argparse
import asyncio
import copy
import hashlib
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import _api                                                  # noqa: E402

PORT = _api.PORT
BASE_URL = "http://localhost:%d" % PORT

# (이름, 빌드 파일의 루트 기준 경로, 흐름 파일 이름 - None 이면 원본 흐름)
CASES = [
    ("original_vs_original", "inputs/original_transfer.html", None),
    ("run1", "results/restructured_transfer.html", "restructured.json"),
    ("run2", "results/restructured_run2.html", "run2.json"),
    ("run3", "results/restructured_run3.html", "run3.json"),
]
ORIGINAL_REL = "inputs/original_transfer.html"


def say(msg):
    print(msg, flush=True)


# --------------------------------------------------------------------- #
# 서버
# --------------------------------------------------------------------- #
def listening(port):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def start_server():
    """프로젝트 루트를 :3003 에 띄운다. 이미 떠 있으면 멈춘다 - 남이 띄운 서버가
    무엇을 서빙하는지 알 수 없고, 기준값은 서빙 내용에 전적으로 달려 있다."""
    if listening(PORT):
        raise SystemExit(
            "멈췄습니다: :%d 포트를 이미 누가 쓰고 있습니다.\n"
            "  기준값은 이 포트가 서빙하는 내용에 달려 있습니다. 남이 띄운 서버를\n"
            "  그대로 쓰면 기준값이 무엇을 기준으로 한 것인지 알 수 없게 됩니다.\n"
            "  그 서버를 끄고 다시 실행하세요 (확인: netstat -ano | findstr :%d)."
            % (PORT, PORT))
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(PORT), "--directory", ROOT],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        if listening(PORT):
            say("서버: http.server :%d 시작 (pid %d)" % (PORT, proc.pid))
            return proc
        time.sleep(0.1)
    proc.kill()
    raise SystemExit("멈췄습니다: :%d 에 http.server 를 띄우지 못했습니다." % PORT)


# --------------------------------------------------------------------- #
# 저장
# --------------------------------------------------------------------- #
def dump(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def dump_text(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def read(path):
    return io.open(path, encoding="utf-8").read()


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------- #
# [1] audit.py main() 과 같은 순서로 4가지 경우
# --------------------------------------------------------------------- #
def flow_path_of(flow_name):
    return os.path.join(ROOT, "tools", "flows", flow_name or "original.json")


def capture_cases(out):
    orig_html = read(os.path.join(ROOT, ORIGINAL_REL))
    orig_url = "%s/%s" % (BASE_URL, ORIGINAL_REL)
    reports = {}

    for name, rel, flow_name in CASES:
        flow_path = flow_path_of(flow_name)
        rep_url = "%s/%s" % (BASE_URL, rel)
        rep_html = read(os.path.join(ROOT, rel))

        # audit.py main() 과 같은 순서:
        #   흐름 읽기 -> 원본 drive -> 빌드 drive -> audit() -> apply_stage
        flow = _api.load_flow(flow_path)
        base_flow = _api.load_flow(None) \
            if not flow.get("derived_from_original", True) else flow

        say("  %s: 원본 drive" % name)
        orig = asyncio.run(_api.drive(orig_url, base_flow))
        say("  %s: 빌드 drive (%s)" % (name, rel))
        rep = asyncio.run(_api.drive(rep_url, flow))

        report = _api.audit(orig, rep, orig_html, rep_html, flow)
        d = os.path.join(out, name)
        dump(os.path.join(d, "snapshots.json"), {"orig": orig, "rep": rep})
        dump(os.path.join(d, "audit.json"), report)
        # apply_stage 는 리포트를 제자리에서 바꾼다. 사본을 넘긴다.
        for stage in ("styled", "wireframe"):
            dump(os.path.join(d, "audit.%s.json" % stage),
                 _api.apply_stage(copy.deepcopy(report), stage))
        if flow_name:
            dump(os.path.join(d, "validate_flow.json"),
                 _api.validate_flow(copy.deepcopy(flow), rep_html))
        m = report["metrics"]
        say("    -> fatal %d / warning %d / 화면 %s/%s"
            % (len(report["fatal"]), len(report["warning"]),
               m.get("screens_reached"), m.get("screens_expected")))
        reports[name] = (report, rep_html, flow_path)
    return reports


# --------------------------------------------------------------------- #
# [2] retry_block
# --------------------------------------------------------------------- #
# 합성 리포트. 실제 실행에서는 한자리에 모이기 어려운 세 가지를 일부러 함께
# 넣는다: 파생 fatal, stack 이 붙은 JS 오류, Playwright 로그 형식의 detail.
SYNTH_LINES = 420
SYNTH_HTML = "\n".join('  <div class="row">줄 %d</div>' % i
                       for i in range(1, SYNTH_LINES + 1))
SYNTH_FLOW_TEXT = json.dumps(
    {"name": "synthetic", "derived_from_original": False,
     "required_ids": ["phone", "dn-amt"],
     "steps": [{"screen": "start"},
               {"screen": "amount", "click": "[data-action='go-amount']"}],
     "expect": {"done": [["#dn-amt", "{AMOUNT_SHOWN}"]]}},
    ensure_ascii=False, indent=2)

PLAYWRIGHT_DETAIL = (
    "TimeoutError: Locator.click: Timeout 30000ms exceeded.\n"
    "Call log:\n"
    '  - waiting for locator("[data-action=\'go-amount\']")\n'
    '  -   locator resolved to <button disabled data-action="go-amount">'
    "다음</button>\n"
    "  - attempting click action\n"
    "  -   waiting for element to be visible, enabled and stable\n"
    "  -   element is not enabled\n"
    "  - retrying click action\n"
    " || [data-action='go-amount'] 는 'review' 화면에 있는데 지금 켜진 화면은 "
    "'amount' 이다. 요소가 아니라 화면 전환을 확인하라."
)

SYNTH_REPORT = {
    "passed": False,
    "fatal": [
        {"check": "A", "screen": None,
         "detail": "JavaScript errors during the task: "
                   "ReferenceError: S is not defined"},
        {"check": "A", "screen": "amount",
         "detail": "navigation failed: " + PLAYWRIGHT_DETAIL},
        {"check": "A", "screen": "review",
         "detail": "never reached - consequence of stopping at 'amount'",
         "derived_from": "amount"},
        {"check": "A", "screen": "done",
         "detail": "never reached - consequence of stopping at 'amount'",
         "derived_from": "amount"},
    ],
    "warning": [],
    "metrics": {
        "flow": "synthetic",
        "js_error_details": [
            {"name": "ReferenceError",
             "message": "ReferenceError: S is not defined",
             "stack": "ReferenceError: S is not defined\n"
                      "    at HTMLButtonElement.<anonymous> "
                      "(http://localhost:3003/synthetic.html:412:7)"},
            {"name": "ReferenceError",
             "message": "ReferenceError: S is not defined",
             "stack": "ReferenceError: S is not defined\n"
                      "    at show (http://localhost:3003/synthetic.html:412:7)"},
        ],
    },
}


def capture_retry_block(out, reports):
    d = os.path.join(out, "retry_block")
    for name, (report, rep_html, flow_path) in reports.items():
        if name == "original_vs_original":
            continue                      # b~d 만
        dump_text(os.path.join(d, "%s.txt" % name),
                  _api.retry_block(copy.deepcopy(report), rep_html,
                                   read(flow_path)))
    dump_text(os.path.join(d, "synthetic.txt"),
              _api.retry_block(copy.deepcopy(SYNTH_REPORT), SYNTH_HTML,
                               SYNTH_FLOW_TEXT))
    # brief_failure 는 retry_block 안에서 쓰이지만, 긴 Playwright 로그를 한 줄로
    # 접는 부분만 따로 고정해 둔다. 그 접기가 바뀌면 여기서 바로 드러난다.
    dump_text(os.path.join(out, "brief_failure.txt"),
              _api.brief_failure(PLAYWRIGHT_DETAIL) + "\n")
    say("  retry_block: run1 / run2 / run3 / synthetic, brief_failure")


# --------------------------------------------------------------------- #
# [3] 재구성 프롬프트 조립
# --------------------------------------------------------------------- #
# 재시도 프롬프트에 넣을 retry_block. 셋 중 하나만 고정하면 된다 - retry_block
# 자체는 [2] 에서 세 실행 + 합성까지 이미 고정했고, 여기서 보는 것은 그 블록이
# 템플릿의 슬롯에 들어간 뒤의 프롬프트 전문이다.
PROMPT_RETRY_CASE = "run1"


def capture_prompt(out):
    """choices_block 과 프롬프트 전문을 고정한다.

    원본 스냅샷은 [1] 이 방금 저장한 것을 다시 읽는다. 브라우저를 또 띄우지
    않으므로 입력이 고정되고, 따라서 출력도 고정되어야 한다 - 비밀번호 숫자판이
    섞여도 choices_block 은 값을 세기만 하므로 결과가 흔들리지 않는다
    (tests/README.md)."""
    orig_html = read(os.path.join(ROOT, ORIGINAL_REL))
    snaps = json.load(io.open(os.path.join(out, "original_vs_original",
                                           "snapshots.json"), encoding="utf-8"))
    choices = _api.choices_block(snaps["orig"], orig_html)
    template = _api.load_template()
    retry = read(os.path.join(out, "retry_block", "%s.txt" % PROMPT_RETRY_CASE))

    d = os.path.join(out, "prompt")
    dump_text(os.path.join(d, "choices_block.txt"), choices)
    dump_text(os.path.join(d, "attempt_1.txt"),
              _api.build_prompt(template, orig_html, "", choices))
    dump_text(os.path.join(d, "retry_%s.txt" % PROMPT_RETRY_CASE),
              _api.build_prompt(template, orig_html, retry, choices))
    say("  prompt: choices_block, 첫 시도, 재시도(%s)" % PROMPT_RETRY_CASE)


# --------------------------------------------------------------------- #
# [4] parse_reply / mock_reply
# --------------------------------------------------------------------- #
def capture_parse_reply(out):
    """mock_reply 가 만든 답을 parse_reply 로 되읽는다. HTML 은 28KB 라 해시만
    남긴다 - 바뀌었는지 알아내는 데는 그것으로 충분하다."""
    got = {}
    for mode in ("pass", "fail"):
        reply = _api.mock_reply(mode)
        html, flow, flow_text = _api.parse_reply(reply["text"])
        got[mode] = {
            "reply_finish_reason": reply["finish_reason"],
            "reply_text_sha256": sha(reply["text"]),
            "html_len": len(html),
            "html_sha256": sha(html),
            "flow": flow,
            "flow_text_sha256": sha(flow_text),
        }
    dump(os.path.join(out, "parse_reply.json"), got)
    say("  parse_reply: mock pass / fail")


# --------------------------------------------------------------------- #
# [5] mock 실행
# --------------------------------------------------------------------- #
def strip_volatile(summary):
    """실행마다 바뀌는 값을 지운다: run_dir, 경로 속 타임스탬프, seconds."""
    s = copy.deepcopy(summary)
    run_dir = (s.pop("run_dir", None) or "").replace("\\", "/")

    def fix(p):
        if not isinstance(p, str) or not run_dir:
            return p
        return p.replace("\\", "/").replace(run_dir, "<run>")

    for a in s.get("attempts") or []:
        a.pop("seconds", None)
        for k in ("html", "flow"):
            if k in a:
                a[k] = fix(a[k])
    if s.get("final"):
        for k in ("html", "flow", "audit"):
            if k in s["final"]:
                s["final"][k] = fix(s["final"][k])
    return s


def ensure_mock_input():
    """mock_reply 는 outputs/restructured_transfer.html 을 읽는다. outputs/ 는
    추적하지 않으므로 없을 수 있다. 그때만 results/ 의 사본을 둔다."""
    dst = os.path.join(ROOT, "outputs", "restructured_transfer.html")
    if os.path.exists(dst):
        return False
    src = os.path.join(ROOT, "results", "restructured_transfer.html")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    return True


MOCK_RUNS = [
    ("mock_pass", ["--mock", "pass", "--attempts", "1"]),
    ("mock_fail", ["--mock", "fail", "--attempts", "2", "--delay", "0"]),
]


def run_mock(args):
    cmd = [sys.executable, os.path.join(ROOT, "tools", "run_restructure.py")] + args
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    hits = [l for l in (p.stdout or "").splitlines() if " summary: " in l]
    if not hits:
        raise SystemExit("mock 실행에서 summary 경로를 찾지 못했습니다.\n"
                         "stdout:\n%s\nstderr:\n%s"
                         % ((p.stdout or "")[-2000:], (p.stderr or "")[-2000:]))
    path = hits[-1].split(" summary: ", 1)[1].strip()
    return json.load(io.open(path, encoding="utf-8")), p.returncode


def capture_mock(out):
    copied = ensure_mock_input()
    for name, args in MOCK_RUNS:
        say("  %s: python tools/run_restructure.py %s" % (name, " ".join(args)))
        summary, code = run_mock(args)
        dump(os.path.join(out, "%s.json" % name), strip_volatile(summary))
        say("    -> passed=%s exit=%d" % (summary.get("passed"), code))
    return copied


# --------------------------------------------------------------------- #
# [6] 가짜 세션 + session_report
# --------------------------------------------------------------------- #
# tools/session.html 이 /api/session 으로 보내는 그 형식이다 (participant /
# condition / condition_label / order_index / task / instruction / completed /
# started_at / elapsed_ms / screen_size / user_agent / metrics / log).
# 파일 이름은 session_server.py 가 붙이는 규칙
# "P%02d_%d_%s.json" % (pid, order_index + 1, condition) 을 그대로 쓴다.
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
      " (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
# 고정 시각. 실제 기록이 아니므로 아무 값이어도 되지만, 기준값이 흔들리지 않게
# 못박아 둔다.
T0 = 1759000000000
CONDITION_LABEL = {"original": "원본 (신한 SOL 재현)",
                   "restructured": "재구성본 (Run 1)"}
TASK_NAME = "긴 과업 · 처음 보내는 계좌"
TASK_INSTRUCTION = ("김시현 씨에게 1만 원을 보내 주세요. "
                    "계좌번호는 3333-0000-0000-0 이고, 카카오뱅크입니다. "
                    "저장된 목록에 있더라도 계좌번호를 직접 넣어서 보내 주세요.")


def expand_log(spec, t0):
    """("enter", 화면, dt) / ("tap", 화면, action, valid, dt) / ("submit", 화면, dt)
    를 시제품이 실제로 남기는 모양으로 펼친다 (inputs/original_transfer.html 의
    log() 를 그대로 따른다)."""
    log, t = [], t0
    for item in spec:
        kind, screen, dt = item[0], item[1], item[-1]
        t += dt
        if kind == "enter":
            log.append({"t": t, "screen": screen, "type": "screen_enter",
                        "to": screen})
        elif kind == "tap":
            action, valid = item[2], item[3]
            log.append({"t": t, "screen": screen, "type": "tap",
                        "x": 195, "y": 400, "valid": valid, "action": action,
                        "text": action or "", "tw": 120 if valid else None,
                        "th": 56 if valid else None})
        elif kind == "submit":
            log.append({"t": t, "screen": screen, "type": "submit",
                        "bank": "카카오뱅크", "account": "3333000000000",
                        "amount": 10000})
    return log


def metrics_of(log, elapsed, completed):
    """tools/session.html 의 metrics() 와 같은 계산. 가짜 세션이 실제 세션과 같은
    모양이 되도록 숫자를 손으로 적지 않고 여기서 센다."""
    taps = [e for e in log if e["type"] == "tap"]
    enters = [e for e in log if e["type"] == "screen_enter"]
    dwell = {}
    for i, e in enumerate(enters):
        end = enters[i + 1]["t"] if i + 1 < len(enters) \
            else (log[-1]["t"] if log else e["t"])
        dwell[e["to"]] = dwell.get(e["to"], 0) + (end - e["t"])

    def act(e):
        return e.get("action") or ""

    return {
        "seconds": elapsed / 1000.0,
        "completed": completed,
        "taps": len(taps),
        "misses": len([e for e in taps if not e["valid"]]),
        "backs": len([e for e in taps if act(e).startswith("back")]),
        "deletes": len([e for e in taps if act(e).endswith("del")]),
        "screens_visited": len(enters),
        "unique_screens": len({e["to"] for e in enters}),
        "dwell_ms": dwell,
    }


# 피험자 2명 × 조건 2개. 순서는 맞바꾼다(카운터밸런스). P02 의 원본 조건만
# completed=false 다 - 완료율 계산과 "중단 포함 / 완료만" 분기를 둘 다 밟게
# 하려면 미완 세션이 하나는 있어야 한다.
SESSIONS = [
    # (participant, condition, order_index, completed, elapsed_ms, log spec)
    (1, "original", 0, True, 92400, [
        ("enter", "home", 0),
        ("tap", "home", "go-recipient", True, 4200),
        ("enter", "recipient", 120),
        ("tap", "recipient", None, False, 6100),
        ("tap", "recipient", "go-account", True, 3800),
        ("enter", "account", 120),
        ("tap", "account", "open-bank", True, 9400),
        ("enter", "bank", 120),
        ("tap", "bank", "pick-bank", True, 12600),
        ("enter", "amount", 120),
        ("tap", "amount", "acc-num", True, 5200),
        ("tap", "amount", "acc-del", True, 2400),
        ("tap", "amount", "acc-num", True, 1900),
        ("tap", "amount", "amt-next", True, 7300),
        ("enter", "confirm", 120),
        ("tap", "confirm", "back-amount", True, 8800),
        ("enter", "amount", 120),
        ("tap", "amount", "amt-next", True, 4100),
        ("enter", "confirm", 120),
        ("tap", "confirm", "send", True, 5600),
        ("enter", "password", 120),
        ("tap", "password", "pw", True, 6400),
        ("submit", "password", 400),
        ("enter", "done", 120),
    ]),
    (1, "restructured", 1, True, 61300, [
        ("enter", "start", 0),
        ("tap", "start", "go-who", True, 3100),
        ("enter", "who", 120),
        ("tap", "who", "go-accno", True, 5400),
        ("enter", "accno", 120),
        ("tap", "accno", "acc-num", True, 8200),
        ("tap", "accno", "go-bank", True, 3300),
        ("enter", "bank", 120),
        ("tap", "bank", "pick-bank", True, 7700),
        ("enter", "amount", 120),
        ("tap", "amount", "num", True, 6100),
        ("tap", "amount", "go-review", True, 4200),
        ("enter", "review", 120),
        ("tap", "review", "send", True, 9300),
        ("enter", "auth", 120),
        ("tap", "auth", "pw", True, 4800),
        ("submit", "auth", 400),
        ("enter", "done", 120),
    ]),
    (2, "restructured", 0, True, 78900, [
        ("enter", "start", 0),
        ("tap", "start", None, False, 7400),
        ("tap", "start", "go-who", True, 4900),
        ("enter", "who", 120),
        ("tap", "who", "go-accno", True, 6600),
        ("enter", "accno", 120),
        ("tap", "accno", "acc-num", True, 11200),
        ("tap", "accno", "acc-del", True, 3100),
        ("tap", "accno", "go-bank", True, 4400),
        ("enter", "bank", 120),
        ("tap", "bank", "pick-bank", True, 9800),
        ("enter", "amount", 120),
        ("tap", "amount", "num", True, 7200),
        ("tap", "amount", "go-review", True, 3900),
        ("enter", "review", 120),
        ("tap", "review", "send", True, 6300),
        ("enter", "auth", 120),
        ("tap", "auth", "pw", True, 5200),
        ("submit", "auth", 400),
        ("enter", "done", 120),
    ]),
    (2, "original", 1, False, 184500, [
        ("enter", "home", 0),
        ("tap", "home", "go-recipient", True, 8800),
        ("enter", "recipient", 120),
        ("tap", "recipient", None, False, 14200),
        ("tap", "recipient", None, False, 9600),
        ("tap", "recipient", "go-account", True, 11300),
        ("enter", "account", 120),
        ("tap", "account", None, False, 21400),
        ("tap", "account", "open-bank", True, 16800),
        ("enter", "bank", 120),
        ("tap", "bank", None, False, 28900),
        ("tap", "bank", "back-account", True, 19700),
        ("enter", "account", 120),
        ("tap", "account", "acc-del", True, 13500),
        ("tap", "account", "open-bank", True, 17200),
        ("enter", "bank", 120),
    ]),
]


def write_fixtures(fixtures):
    if os.path.isdir(fixtures):
        shutil.rmtree(fixtures)
    os.makedirs(fixtures)
    for pid, cond, order, completed, elapsed, spec in SESSIONS:
        started = T0 + pid * 3600000 + order * 600000
        log = expand_log(spec, started)
        dump(os.path.join(fixtures, "P%02d_%d_%s.json" % (pid, order + 1, cond)), {
            "participant": pid,
            "condition": cond,
            "condition_label": CONDITION_LABEL[cond],
            "order_index": order,
            "task": TASK_NAME,
            "instruction": TASK_INSTRUCTION,
            "completed": completed,
            "started_at": started,
            "elapsed_ms": elapsed,
            "screen_size": [390, 844],
            "user_agent": UA,
            "metrics": metrics_of(log, elapsed, completed),
            "log": log,
        })
    say("  세션 고정물 %d건 -> %s"
        % (len(SESSIONS), os.path.relpath(fixtures, ROOT).replace(os.sep, "/")))


def capture_session_report(out, fixtures):
    """session_report 의 main() 을 그대로 부른다. 집계 함수만 따로 부르면 main()
    이 조립하는 부분(제목·절 순서·설명문)이 기준값에서 빠진다."""
    md_path = os.path.join(out, "session_report.md")
    csv_path = os.path.join(out, "session_report.csv")
    os.makedirs(out, exist_ok=True)
    argv = sys.argv
    sys.argv = ["session_report.py", "--sessions", fixtures,
                "--out", md_path, "--csv", csv_path]
    try:
        code = _api.sr_main()
    finally:
        sys.argv = argv
    if code != 0:
        raise SystemExit("session_report 가 %d 로 끝났습니다." % code)
    say("  session_report: md + csv")


# --------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "baseline"),
                    help="기준값을 쓸 폴더 (기본: tests/baseline)")
    ap.add_argument("--fixtures",
                    default=os.path.join(HERE, "fixtures", "sessions"))
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    out = os.path.abspath(args.out)
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)

    say("기준값 -> %s" % out)
    server = start_server()
    copied = False
    try:
        say("[1/6] audit.py main() 과 같은 순서로 4가지 경우")
        reports = capture_cases(out)
        say("[2/6] retry_block")
        capture_retry_block(out, reports)
        say("[3/6] 재구성 프롬프트 조립")
        capture_prompt(out)
        say("[4/6] parse_reply / mock_reply")
        capture_parse_reply(out)
        say("[5/6] mock 실행")
        copied = capture_mock(out)
    finally:
        server.terminate()
        server.wait()
        say("서버: 종료 (pid %d)" % server.pid)

    say("[6/6] session_report")
    write_fixtures(os.path.abspath(args.fixtures))
    capture_session_report(out, os.path.abspath(args.fixtures))

    if copied:
        say("")
        say("알림: outputs/restructured_transfer.html 이 없어서 results/ 의 사본을"
            " 복사했습니다 (mock_reply 가 그 경로를 읽습니다).")
    say("")
    say("끝. 기준값: %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
