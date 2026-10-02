r"""재시도 루프. 한 번의 시도는 네 단계다.

    request_reply  프롬프트를 만들어 보내고 답을 받아 적는다
    check_reply    답을 HTML + 흐름 명세로 가르고 모양을 본다
    audit_build    검사기를 돌린다 (형식 문제로 멈췄으면 검사 전에 끝난다)
    record         리포트를 쓰고, 통과·예산을 보고 계속할지 정한다

예산은 둘이다 (Budget). 형식 오류(흐름 명세가 규격에 안 맞음)와 검사 fatal
(설계가 과제를 통과 못 함)은 다른 종류의 실패이고, 한쪽이 예산을 다 쓰면 다른
쪽은 재시도를 한 번도 못 받는 일이 생긴다 - Run 2 가 그랬다.

한 실행이 공유하는 것(설정·로거·요약·예산·직전 시도)은 Run 하나에 모아 단계
함수들이 그것을 주고받는다.
"""
import asyncio
import datetime
import io
import json
import os
import shutil
import sys
import time

from senior_ui import audit as A
from senior_ui.config import ORIGINAL_URL, OUTPUTS_DIR, ROOT, url_for
from senior_ui.devserver import ensure_server

from .audit_call import run_audit
from .model import RateLimited, call_model, load_env, mock_reply
from .prompt import build_prompt, choices_block, load_template, one_line, retry_block
from .reply import failure_report, parse_reply, validate_flow

RUNS_DIR = os.path.join(OUTPUTS_DIR, "restructure_auto")

# 한 번의 시도가 끝나는 방식
STOP = "stop"            # 루프를 끝낸다
GO_ON = "go_on"          # 다음 시도로


# --------------------------------------------------------------------------- #
# 예산
# --------------------------------------------------------------------------- #
class Budget:
    """형식 오류와 검사 fatal 에 따로 주는 재시도 예산."""

    def __init__(self, fmt, aud):
        self.budget = {"format": fmt, "audit": aud}
        self.used = {"format": 0, "audit": 0}

    @property
    def format_used(self):
        return self.used["format"]

    @property
    def audit_used(self):
        return self.used["audit"]

    def spend(self, kind):
        self.used[kind] += 1

    def out_of(self, kind):
        return self.used[kind] >= self.budget[kind]

    def exhausted(self):
        return self.out_of("format") and self.out_of("audit")

    def as_dict(self):
        return {"format_used": self.used["format"], "format_budget": self.budget["format"],
                "audit_used": self.used["audit"], "audit_budget": self.budget["audit"]}


class Run:
    """한 실행이 공유하는 것들. 단계 함수들은 이것만 주고받는다."""

    def __init__(self, args, log, run_dir, model, template, original_html):
        self.args = args
        self.log = log
        self.run_dir = run_dir
        self.model = model
        self.template = template
        self.original_html = original_html
        self.choices = ""
        self.orig_snapshot = None
        self.budget = Budget(
            args.format_attempts if args.format_attempts is not None else args.attempts,
            args.audit_attempts if args.audit_attempts is not None else args.attempts)
        self.prev = {"report": None, "html": None, "flow_text": None}
        self.summary = {"run_dir": run_dir, "model": model, "mock": args.mock,
                        "stage": args.stage, "attempts": [], "passed": False,
                        "final": None, "budget": {}, "stopped_reason": None,
                        "trend": []}


# --------------------------------------------------------------------------- #
# 설정
# --------------------------------------------------------------------------- #
def make_logger(log_path):
    """화면과 run.log 에 같은 줄을 적는다."""
    def log(msg):
        line = "%s %s" % (datetime.datetime.now().strftime("%H:%M:%S"), msg)
        print(line, flush=True)
        with io.open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    return log


def pick_model(args):
    return args.model or os.environ.get("RESTRUCTURE_MODEL") \
        or os.environ.get("DESIGNREPAIR_MODEL") or "gpt-4o"


def _dump(obj, path):
    json.dump(obj, io.open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------- #
# 한 번의 시도
# --------------------------------------------------------------------------- #
def request_reply(r, n, p):
    """프롬프트를 만들어 보내고 답을 받아 적는다.

    돌려주는 것은 (reply, outcome). reply 가 None 이면 이 시도가 모델 호출에서
    끝난 것이고 outcome 이 다음에 할 일이다."""
    block = retry_block(r.prev["report"], r.prev["html"], r.prev["flow_text"]) \
        if r.prev["report"] else ""
    prompt = build_prompt(r.template, r.original_html, block, r.choices)
    io.open(p + ".prompt.txt", "w", encoding="utf-8", newline="\n").write(prompt)
    r.log("prompt: %d chars%s" % (len(prompt), " (with retry block)" if block else ""))

    if r.args.mock:
        reply = mock_reply(r.args.mock)
    else:
        try:
            reply = call_model(r.model, prompt, r.args.max_tokens, r.log)
        except RateLimited as e:
            # 설계 실패가 아니다. 예산을 깎지 않고 여기서 멈춘다.
            r.log("중단: 인프라 한도 — 백오프를 다 쓰고도 429 (%s)" % e)
            r.summary["stopped_reason"] = "rate_limit"
            _dump(failure_report("INFRA", "인프라 한도로 중단: %s" % e), p + ".audit.json")
            r.summary["attempts"].append({"n": n, "stage": "rate_limit",
                                          "passed": False, "error": str(e)})
            return None, STOP
        except Exception as e:                       # network, auth
            # TODO 버그: 429 가 아닌 호출 실패는 예산을 쓰지 않고 다음 시도로 간다.
            # 키가 틀리면 같은 실패가 영원히 반복되고 루프가 끝나지 않는다.
            r.log("model: call failed: %s" % e)
            report = failure_report("LLM", "모델 호출 실패: %s" % e)
            _dump(report, p + ".audit.json")
            r.summary["attempts"].append({"n": n, "stage": "call", "passed": False,
                                          "error": str(e)})
            r.prev = {"report": report, "html": r.prev["html"],
                      "flow_text": r.prev["flow_text"]}
            return None, GO_ON
    io.open(p + ".response.txt", "w", encoding="utf-8", newline="\n").write(reply["text"])
    r.log("model: %s chars, finish=%s, %ss, usage=%s"
          % (len(reply["text"]), reply["finish_reason"], reply["seconds"], reply["usage"]))
    return reply, None


def check_reply(r, p, entry, reply):
    """답을 HTML + 흐름 명세로 가르고 모양을 본다. 파일로도 남긴다.

    돌려주는 것은 (build, outcome). build 가 None 이면 파싱이 실패해 이 시도가
    끝난 것이다."""
    try:
        if reply["finish_reason"] == "length":
            raise ValueError("답이 길이 제한에서 잘렸다 (finish_reason=length). "
                             "코드 블록 두 개만, 군더더기 없이 출력하라")
        html, flow, flow_text = parse_reply(reply["text"])
        flow.setdefault("name", "auto")
        flow["derived_from_original"] = False
        problems = validate_flow(flow, html)
    except ValueError as e:
        r.log("parse: %s" % e)
        report = failure_report("PARSE", str(e))
        entry.update(stage="parse", passed=False, fatal=1)
        _dump(report, p + ".audit.json")
        r.summary["attempts"].append(entry)
        # TODO 버그: 직전 HTML 은 그대로 두면서 그 HTML 의 검사 결과(report)는
        # 버린다. 재시도 프롬프트가 HTML 과 어긋난 실패 목록을 보게 된다.
        r.prev = {"report": report, "html": r.prev["html"],
                  "flow_text": r.prev["flow_text"]}
        r.budget.spend("format")
        if r.budget.out_of("format"):
            r.log("형식 재시도 예산 소진 (%d회)" % r.budget.format_used)
            return None, STOP
        return None, GO_ON

    html_path, flow_path = p + ".html", p + ".flow.json"
    io.open(html_path, "w", encoding="utf-8", newline="\n").write(html)
    io.open(flow_path, "w", encoding="utf-8", newline="\n").write(
        json.dumps(flow, ensure_ascii=False, indent=2))
    entry["html"], entry["flow"] = html_path, flow_path
    return {"html": html, "flow_text": flow_text, "problems": problems,
            "html_path": html_path, "flow_path": flow_path}, None


def audit_build(r, n, entry, build):
    """검사기를 돌린다. 형식 문제가 있으면 검사 전에 끝내고 그 모양의 리포트를
    돌려준다."""
    problems = build["problems"]
    if problems:
        r.log("flow: %d problem(s): %s" % (len(problems), " | ".join(problems)[:300]))
        entry.update(stage="flow", passed=False, fatal=len(problems))
        r.budget.spend("format")
        return {"passed": False, "warning": [],
                "metrics": {"flow": "auto", "not_audited": True},
                "fatal": [{"check": "FLOW", "screen": None, "detail": d}
                          for d in problems]}

    report = _drive_audit(r, n, build)
    entry.update(stage="audit", passed=bool(report.get("passed")),
                 fatal=len(report.get("fatal", [])),
                 warning=len(report.get("warning", [])))
    if not report.get("passed"):
        r.budget.spend("audit")
    _note_audit(r, n, report)
    return report


def _drive_audit(r, n, build):
    """브라우저를 띄워 한 번 걷는다. 검사기가 흐름을 아예 실행하지 못하는 것도
    결과이므로 리포트 모양으로 바꿔 돌려준다."""
    rel = os.path.relpath(build["html_path"], ROOT).replace(os.sep, "/")
    shots = os.path.join(r.run_dir, "shots", "attempt_%d" % n)
    os.makedirs(shots, exist_ok=True)
    try:
        return run_audit(r.orig_snapshot, r.original_html, build["html_path"],
                         build["flow_path"], url_for(rel), shots, r.args.stage)
    except Exception as e:                           # a flow audit.py cannot drive
        r.log("audit: crashed: %s: %s" % (type(e).__name__, e))
        return failure_report("AUDIT", "검사기가 흐름 명세를 실행하지 못했다: %s: %s"
                              % (type(e).__name__, e))


def _note_audit(r, n, report):
    """추이 표에 한 줄 더하고, 이번 검사 결과를 로그에 적는다."""
    m = report.get("metrics", {})
    r.summary["trend"].append({
        "attempt": n, "fatal_total": m.get("fatal_total"),
        "fatal_root": m.get("fatal_root"), "fatal_derived": m.get("fatal_derived"),
        "screens": "%s/%s" % (m.get("screens_reached"), m.get("screens_expected")),
        "stopped_at": m.get("stopped_at")})
    r.log("audit: passed=%s fatal=%d (근본 %s) warning=%d screens=%s/%s"
          % (report.get("passed"), len(report.get("fatal", [])), m.get("fatal_root"),
             len(report.get("warning", [])), m.get("screens_reached"),
             m.get("screens_expected")))
    for f in report.get("fatal", [])[:8]:
        r.log("  F [%s] %s%s" % (f.get("check"), ("%s: " % f["screen"]) if f.get("screen") else "",
                                 one_line(f.get("detail", ""))[:160]))


def record(r, n, p, entry, report, build):
    """리포트를 쓰고, 통과·예산을 보고 계속할지 정한다."""
    _dump(report, p + ".audit.json")
    r.summary["attempts"].append(entry)
    r.summary["final"] = {"attempt": n, "html": build["html_path"],
                          "flow": build["flow_path"], "audit": p + ".audit.json"}
    if report.get("passed"):
        r.summary["passed"] = True
        r.log("PASSED on attempt %d" % n)
        return STOP
    r.prev = {"report": report, "html": build["html"], "flow_text": build["flow_text"]}
    return _budget_stop(r, entry)


def _budget_stop(r, entry):
    """예산만 보고 루프를 끝낼지 정한다."""
    b = r.budget
    if b.exhausted():
        r.log("양쪽 예산 모두 소진 — 형식 %d회 / 검사 %d회" % (b.format_used, b.audit_used))
        return STOP
    if entry.get("stage") == "flow" and b.out_of("format"):
        r.log("형식 재시도 예산 소진 (%d회) — 검사까지 가지 못했다" % b.format_used)
        return STOP
    if entry.get("stage") == "audit" and b.out_of("audit"):
        r.log("검사 재시도 예산 소진 (%d회)" % b.audit_used)
        return STOP
    return GO_ON


def attempt(r, n):
    """한 번의 시도. 돌려주는 것은 STOP 또는 GO_ON."""
    b = r.budget
    r.log("---- attempt %d (형식 %d/%d · 검사 %d/%d)"
          % (n, b.format_used, b.budget["format"], b.audit_used, b.budget["audit"]))
    p = os.path.join(r.run_dir, "attempt_%d" % n)

    reply, outcome = request_reply(r, n, p)
    if reply is None:
        return outcome
    entry = {"n": n, "finish_reason": reply["finish_reason"], "usage": reply["usage"],
             "seconds": reply["seconds"]}
    build, outcome = check_reply(r, p, entry, reply)
    if build is None:
        return outcome
    report = audit_build(r, n, entry, build)
    return record(r, n, p, entry, report, build)


# --------------------------------------------------------------------------- #
# 요약
# --------------------------------------------------------------------------- #
def log_trend(r):
    """시도마다 fatal 이 줄었는지. 숫자 하나만 보면 알 수 없는 것이다."""
    if not r.summary["trend"]:
        return
    r.log("")
    r.log("fatal_root 추이")
    r.log("  시도 | fatal | 근본 | 파생 | 화면    | 멈춘 곳")
    for t in r.summary["trend"]:
        r.log("  %4s | %5s | %4s | %4s | %-7s | %s"
              % (t["attempt"], t["fatal_total"], t["fatal_root"],
                 t["fatal_derived"], t["screens"], t["stopped_at"] or "-"))


def copy_final(r):
    """파일까지 간 마지막 빌드를 통과 여부와 무관하게 outputs/ 로 복사한다."""
    f = r.summary["final"]
    if not f:
        return
    shutil.copy2(f["html"], os.path.join(OUTPUTS_DIR, "restructured_auto.html"))
    shutil.copy2(f["flow"], os.path.join(OUTPUTS_DIR, "restructured_auto.flow.json"))
    shutil.copy2(f["audit"], os.path.join(OUTPUTS_DIR, "audit_auto.json"))
    r.log("final: attempt %d -> outputs/restructured_auto.html (+ .flow.json, audit_auto.json)"
          % f["attempt"])


# --------------------------------------------------------------------------- #
def run(args):
    """한 실행 전체. 돌려주는 것이 프로세스의 종료 코드다 -
    0 = 통과한 빌드가 있다, 1 = 전부 실패, 2 = 아예 돌지 못했다."""
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = os.path.join(RUNS_DIR, stamp + ("-mock-" + args.mock if args.mock else ""))
    os.makedirs(run_dir, exist_ok=True)
    log = make_logger(os.path.join(run_dir, "run.log"))

    load_env()
    model = pick_model(args)
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
    r = Run(args, log, run_dir, model, template, original_html)
    server = None
    try:
        server = ensure_server(log)
        # 대비·언어 검사의 기준이 되는 원본 스냅샷. 실행마다 한 번만 걷는다.
        base_flow = A.load_flow(None)
        log("audit: driving the original once (baseline for contrast / language)")
        r.orig_snapshot = asyncio.run(A.drive(ORIGINAL_URL, base_flow))
        r.choices = choices_block(r.orig_snapshot, original_html)
        if r.choices:
            log("선택지: %s" % " / ".join(
                l.strip() for l in r.choices.splitlines() if l.startswith("  ")))

        n = 0
        while True:
            n += 1
            if n > 1 and args.delay and not args.mock:
                time.sleep(args.delay)
            if attempt(r, n) is STOP:
                break

        if not r.summary["passed"]:
            log("통과 없음 — 형식 재시도 %d회 / 검사 재시도 %d회"
                % (r.budget.format_used, r.budget.audit_used))
            if r.summary["stopped_reason"] is None:
                r.summary["stopped_reason"] = "budget_exhausted"
        log_trend(r)
        r.summary["budget"] = r.budget.as_dict()
    finally:
        if server:
            server.terminate()
            log("server: stopped (pid %d)" % server.pid)

    copy_final(r)
    _dump(r.summary, os.path.join(run_dir, "summary.json"))
    log("summary: %s" % os.path.join(run_dir, "summary.json"))
    return 0 if r.summary["passed"] else 1
