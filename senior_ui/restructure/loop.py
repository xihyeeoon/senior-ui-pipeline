r"""재시도 루프. 한 번의 시도는 다섯 단계다.

    request_plan   진단·계획을 받는다 (계획이 아직 없을 때만 - 보통 첫 시도)
    request_reply  계획을 넣은 프롬프트를 보내고 HTML + 흐름 명세를 받는다
    check_reply    답을 HTML + 흐름 명세로 가르고 모양을 본다
    audit_build    검사기를 돌린다 (형식 문제로 멈췄으면 검사 전에 끝난다)
    record         리포트를 쓰고, 통과·예산을 보고 계속할지 정한다

진단·계획을 따로 받는 이유는 기록이다. 한 번에 받으면 모델이 무엇을 보고 무엇을
바꿨는지가 HTML 안에 묻힌다 - 따로 받으면 attempt_N.diagnosis.json ·
attempt_N.plan.json 으로 남는다 (plan.py).

예산은 둘이다 (Budget). 형식 오류(흐름 명세가 규격에 안 맞음)와 검사 fatal
(설계가 과제를 통과 못 함)은 다른 종류의 실패이고, 한쪽이 예산을 다 쓰면 다른
쪽은 재시도를 한 번도 못 받는 일이 생긴다 - Run 2 가 그랬다.

한 실행이 공유하는 것(설정·로거·요약·예산·직전 시도)은 Run 하나에 모아 단계
함수들이 그것을 주고받는다.
"""
import asyncio
import datetime
import hashlib
import io
import json
import os
import shutil
import sys
import time

from senior_ui import audit as A
from senior_ui.config import OUTPUTS_ENV, ROOT, inside_root, outputs_dir, url_for
from senior_ui.devserver import ensure_server

from .audit_call import load_allowed_removals, run_audit
from .model import (TEMPERATURE, SEED, ApiRejected, InfraFailed, RateLimited,
                    call_model, load_env, mock_plan_reply, mock_reply, sdk_version)
from .plan import (PlanProblems, apply_changes, match_problems, parse_plan,
                   parse_reflection, plan_report, screens_in, unaddressed)
from .preserve import inject, names_read, preserved_data
from .prompt import (build_plan_prompt, build_prompt, choices_block, load_plan_template,
                     load_template, one_line, plan_retry_block, retry_block,
                     with_reflection)
from .reply import (FlowShape, failure_report, parse_reply,
                    preserved_problems, problems_report, validate_flow)

def runs_dir():
    """실행 폴더들이 쌓이는 곳. 산출물 폴더와 같이 움직인다 (config.outputs_dir)."""
    return os.path.join(outputs_dir(), "restructure_auto")

# 진단·계획 호출의 길이 제한. 생성 호출(--max-tokens)과 따로 둔다 - 분당
# 한도는 max_tokens 를 미리 잡아 두고 세므로, 계획 JSON 에 생성과 같은 한도를
# 주면 쓰지도 않을 토큰이 한도를 먹는다.
PLAN_MAX_TOKENS = 6000

# 한 번의 시도가 끝나는 방식
STOP = "stop"            # 루프를 끝낸다
GO_ON = "go_on"          # 다음 시도로


# --------------------------------------------------------------------------- #
# 예산
# --------------------------------------------------------------------------- #
class Budget:
    """재시도 예산 셋. 셋인 이유는 실패의 종류가 셋이기 때문이다.

        format  흐름 명세가 규격에 안 맞는다      - 모델이 고칠 수 있다
        audit   설계가 과제를 통과 못 한다        - 모델이 고칠 수 있다
        infra   연결이 되지 않았다                - 모델과 무관하다

    앞의 둘을 가른 이유는 Run 2 다 - 한쪽이 예산을 다 쓰면 다른 쪽은 재시도를
    한 번도 못 받았다. infra 를 더한 이유는 그 반대다. 호출 실패는 예산을 전혀
    쓰지 않아서, 키가 틀리면 루프가 끝나지 않았다.
    """

    def __init__(self, fmt, aud, infra=3):
        self.budget = {"format": fmt, "audit": aud, "infra": infra}
        self.used = {"format": 0, "audit": 0, "infra": 0}

    @property
    def format_used(self):
        return self.used["format"]

    @property
    def audit_used(self):
        return self.used["audit"]

    @property
    def infra_used(self):
        return self.used["infra"]

    def spend(self, kind):
        self.used[kind] += 1

    def out_of(self, kind):
        return self.used[kind] >= self.budget[kind]

    def exhausted(self):
        """설계를 고칠 기회가 더 없다. infra 는 설계와 무관하므로 세지 않는다."""
        return self.out_of("format") and self.out_of("audit")

    def as_dict(self):
        return {"format_used": self.used["format"], "format_budget": self.budget["format"],
                "audit_used": self.used["audit"], "audit_budget": self.budget["audit"],
                "infra_used": self.used["infra"], "infra_budget": self.budget["infra"]}


class Run:
    """한 실행이 공유하는 것들. 단계 함수들은 이것만 주고받는다."""

    def __init__(self, args, log, run_dir, model, template, original_html,
                 original_url=None, plan_template=""):
        self.args = args
        # 프롬프트에 넣는 원본과 브라우저가 걷는 원본은 같은 문서다.
        self.original_url = original_url
        self.log = log
        self.run_dir = run_dir
        self.model = model
        self.template = template
        self.plan_template = plan_template
        self.original_html = original_html
        # 원본의 화면 이름. 계획의 from 이 가리킬 수 있는 이름들이다.
        self.original_screens = screens_in(original_html)
        # 진단과 지금의 계획. 계획은 실행에 하나이고 재시도에서 고쳐진다.
        self.diagnosis = None
        self.plan = None
        # 직전 진단·계획 답의 문제. 다음 진단·계획 프롬프트로 간다.
        self.plan_error = None
        # 이번 생성 프롬프트가 반성을 요청했는가 (재시도일 때).
        self.asked_reflection = False
        # 못박아 두는 값. 지정하지 않으면 공급자의 기본값이 쓰이고 그 값은
        # 기록에 남지 않는다 - 나중에 "그때 무엇이 달랐나" 를 물을 수 없다.
        self.temperature = getattr(args, "temperature", TEMPERATURE)
        self.seed = getattr(args, "seed", SEED)
        self.choices = ""
        # 입력이 가진 선택지 데이터. 실행마다 한 번 뽑아 시도마다 넣는다.
        # {배열 이름: [원소들]} (preserve.preserved_data).
        self.preserved = {}
        # 연구자가 관리하는 "빼도 되는 선택지" 목록. 검사 직전에 흐름에 합친다.
        self.allowed_removals = {}
        self.orig_snapshot = None
        self.budget = Budget(
            args.format_attempts if args.format_attempts is not None else args.attempts,
            args.audit_attempts if args.audit_attempts is not None else args.attempts,
            getattr(args, "infra_attempts", 3))
        # 마지막으로 **검사까지 간** 빌드와 그 결과. 셋은 늘 같은 시도의 것이다.
        self.last = {"report": None, "html": None, "flow_text": None}
        # 마지막 형식 오류. 검사 결과와 다른 것이므로 따로 들고 있는다 - 한쪽을
        # 다른 쪽에 넣으면 재시도 프롬프트가 둘 중 하나를 잃는다.
        self.last_error = None
        # 길이 제한에 잘린 답이 연속 몇 번인지. 둘째 번부터는 안내가 달라진다.
        self.truncated = 0
        self.summary = {"run_dir": run_dir, "model": model, "mock": args.mock,
                        "stage": args.stage, "preserved": {}, "plan": None,
                        "repro": repro(template, temperature=self.temperature,
                                       seed=self.seed),
                        "attempts": [], "passed": False, "final": None,
                        "budget": {}, "stopped_reason": None, "trend": []}


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


def original_url(path):
    """원본 파일을 서버가 서빙하는 URL 로.

    프롬프트에 넣는 HTML 과 브라우저로 걷는 문서는 같아야 한다. 걷는 쪽만
    config.ORIGINAL_URL 로 못박혀 있으면, --original 로 다른 파일을 줬을 때
    대비·언어 검사의 기준이 프롬프트에 넣은 원본과 다른 문서가 된다 - 아무
    경고 없이.

    서버는 저장소 루트만 서빙하므로 그 밖의 파일은 URL 이 없다. 열 수 없는
    것을 연 척하는 대신 RuntimeError 로 멈춘다.
    """
    rel = os.path.relpath(os.path.abspath(path), ROOT)
    if rel.startswith(os.pardir) or os.path.isabs(rel):
        raise RuntimeError("--original 은 저장소 안의 파일이어야 한다 (서버가 "
                           "서빙하는 범위 밖이다): %s" % path)
    return url_for(rel.replace(os.sep, "/"))


def pick_model(args):
    return args.model or os.environ.get("RESTRUCTURE_MODEL") \
        or os.environ.get("DESIGNREPAIR_MODEL") or "gpt-4o"


def repro(template, reply=None, temperature=TEMPERATURE, seed=SEED):
    """이 시도를 다시 돌리려면 알아야 하는 것.

    같은 프롬프트를 같은 모델에 보내도 답은 달라진다. 무엇이 달랐는지 나중에
    물을 수 있으려면 보낸 쪽(temperature · seed · 프롬프트 템플릿)과 답한
    쪽(실제 응답 모델 · system_fingerprint · SDK 판)을 함께 적어야 한다 -
    `--model gpt-4o` 는 별명이고, 그 별명이 가리키는 판본은 말없이 바뀐다.
    """
    reply = reply or {}
    return {"temperature": reply.get("temperature", temperature),
            "seed": reply.get("seed", seed),
            "response_model": reply.get("model"),
            "system_fingerprint": reply.get("system_fingerprint"),
            "openai_sdk": sdk_version(),
            "prompt_template_sha256":
                hashlib.sha256(template.encode("utf-8")).hexdigest()}


def _dump(obj, path):
    json.dump(obj, io.open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------- #
# 한 번의 시도
# --------------------------------------------------------------------------- #
def plan_text(r):
    """프롬프트에 넣는 계획. 사람도 읽으므로 들여 쓴다."""
    return json.dumps(r.plan, ensure_ascii=False, indent=2) if r.plan else ""


def request_plan(r, n, p):
    """진단·계획을 받는다. 돌려주는 것은 (호출 기록, outcome).

    outcome 이 None 이면 계획이 섰다 (r.diagnosis · r.plan). 아니면 이 시도는
    여기서 끝났고 outcome 이 다음에 할 일이다. 쓸 수 없는 답은 형식 실패다 -
    모델이 고칠 수 있는 것이므로 형식 예산을 쓴다."""
    prompt = build_plan_prompt(r.plan_template, r.original_html, r.choices,
                               r.original_screens, plan_retry_block(r.plan_error))
    io.open(p + ".plan_prompt.txt", "w", encoding="utf-8", newline="\n").write(prompt)
    r.log("plan prompt: %d chars%s" % (len(prompt),
                                       " (with retry block)" if r.plan_error else ""))
    reply, outcome = ask_model(r, n, p, prompt,
                               getattr(r.args, "plan_max_tokens", PLAN_MAX_TOKENS),
                               mock_plan_reply)
    if reply is None:
        return None, outcome
    io.open(p + ".plan_response.txt", "w", encoding="utf-8",
            newline="\n").write(reply["text"])
    r.log("plan: %s chars, finish=%s, %ss, usage=%s"
          % (len(reply["text"]), reply["finish_reason"], reply["seconds"], reply["usage"]))
    call = {"finish_reason": reply["finish_reason"], "usage": reply["usage"],
            "seconds": reply["seconds"]}
    try:
        if reply["finish_reason"] == "length":
            raise PlanProblems(["답이 길이 제한에서 잘렸다 (finish_reason=length). "
                                "진단과 변경의 문장을 짧게 써서 JSON 을 끝까지 닫아라."])
        diagnosis, plan = parse_plan(reply["text"], r.original_screens)
    except PlanProblems as e:
        r.log("plan: %d problem(s): %s" % (len(e.problems),
                                           " | ".join(e.problems)[:300]))
        entry = dict(call, n=n, stage="plan", passed=False, fatal=len(e.problems))
        _dump(plan_report(e.problems), p + ".audit.json")
        r.summary["attempts"].append(entry)
        r.plan_error = list(e.problems)
        r.budget.spend("format")
        if r.budget.out_of("format"):
            r.log("형식 재시도 예산 소진 (%d회) — 계획을 세우지 못했다"
                  % r.budget.format_used)
            return None, STOP
        return None, GO_ON

    r.plan_error = None
    r.diagnosis, r.plan = diagnosis, plan
    _dump(diagnosis, p + ".diagnosis.json")
    left = unaddressed(diagnosis, plan)
    r.summary["plan"] = {"attempt": n, "diagnosis": p + ".diagnosis.json",
                         "diagnosis_count": len(diagnosis),
                         "screens": [sc["name"] for sc in plan["screens"]],
                         "changes": len(plan["changes"]),
                         "unaddressed": left}
    r.log("plan: 진단 %d · 화면 %d (%s) · 변경 %d%s"
          % (len(diagnosis), len(plan["screens"]),
             ", ".join(sc["name"] for sc in plan["screens"]), len(plan["changes"]),
             (" / 대응하는 변경이 없는 진단: %s" % ", ".join(left)) if left else ""))
    return call, None


def ask_model(r, n, p, prompt, max_tokens, mock):
    """모델에 한 번 묻는다. 진단·계획과 생성이 같은 길을 쓴다.

    돌려주는 것은 (reply, outcome). reply 가 None 이면 이 시도가 모델 호출에서
    끝난 것이고 outcome 이 다음에 할 일이다."""
    if r.args.mock:
        reply = mock(r.args.mock)
    else:
        try:
            reply = call_model(r.model, prompt, max_tokens, r.log,
                               temperature=r.temperature, seed=r.seed)
        except RateLimited as e:
            # 설계 실패가 아니다. 예산을 깎지 않고 여기서 멈춘다.
            r.log("중단: 인프라 한도 — 백오프를 다 쓰고도 429 (%s)" % e)
            r.summary["stopped_reason"] = "rate_limit"
            _dump(failure_report("INFRA", "인프라 한도로 중단: %s" % e), p + ".audit.json")
            r.summary["attempts"].append({"n": n, "stage": "rate_limit",
                                          "passed": False, "error": str(e)})
            return None, STOP
        except ApiRejected as e:
            # 키·권한·요청 자체가 틀렸다. 다시 보내도 같은 답이 오므로, 여기서
            # 멈추지 않으면 예산과 무관하게 같은 실패만 반복된다.
            r.log("중단: API 가 요청을 거절했다 — 다시 보내도 같은 답이 온다 (%s)" % e)
            r.summary["stopped_reason"] = "api_rejected"
            _dump(failure_report("INFRA", "API 가 요청을 거절했다: %s" % e),
                  p + ".audit.json")
            r.summary["attempts"].append({"n": n, "stage": "api_rejected",
                                          "passed": False, "error": str(e)})
            return None, STOP
        except Exception as e:                       # 연결 실패·타임아웃·그 밖
            # 설계 실패가 아니므로 형식·검사 예산은 건드리지 않는다. 대신 인프라
            # 예산을 쓴다 - 다시 될 수도 있지만 무한히 기다리지는 않는다.
            #
            # 오류 문구는 프롬프트로 가지 않는다 (r.last 를 그대로 둔다). 모델이
            # 고칠 수 있는 것이 아니고, 직전에 검사받은 빌드의 실패 목록을
            # API 오류로 덮으면 다음 시도가 고칠 것을 잃는다.
            kind = "InfraFailed" if isinstance(e, InfraFailed) else type(e).__name__
            r.budget.spend("infra")
            r.log("model: 호출 실패 (인프라 %d/%d) — %s: %s"
                  % (r.budget.infra_used, r.budget.budget["infra"], kind, e))
            _dump(failure_report("INFRA", "모델 호출 실패: %s: %s" % (kind, e)),
                  p + ".audit.json")
            r.summary["attempts"].append({"n": n, "stage": "call", "passed": False,
                                          "error": "%s: %s" % (kind, e)})
            if r.budget.out_of("infra"):
                r.log("인프라 재시도 예산 소진 (%d회) — 모델에 닿지 못했다"
                      % r.budget.infra_used)
                r.summary["stopped_reason"] = "infra_exhausted"
                return None, STOP
            return None, GO_ON
    if reply.get("model") or reply.get("system_fingerprint"):
        r.log("model: 응답 %s (fingerprint %s)"
              % (reply.get("model"), reply.get("system_fingerprint")))
    return reply, None


def request_reply(r, n, p):
    """계획을 넣은 프롬프트를 보내고 답을 받아 적는다.

    돌려주는 것은 (reply, outcome). reply 가 None 이면 이 시도가 모델 호출에서
    끝난 것이고 outcome 이 다음에 할 일이다."""
    block = retry_block(r.last["report"], r.last["html"], r.last["flow_text"],
                        error=r.last_error, truncated=r.truncated) \
        if (r.last["report"] or r.last_error or r.truncated) else ""
    # 재시도에서는 코드보다 반성을 먼저 쓰게 한다. 그래서 실패 목록보다 앞이다.
    r.asked_reflection = bool(block)
    block = with_reflection(block)
    prompt = build_prompt(r.template, r.original_html, block, r.choices, plan_text(r))
    io.open(p + ".prompt.txt", "w", encoding="utf-8", newline="\n").write(prompt)
    r.log("prompt: %d chars%s" % (len(prompt), " (with retry block)" if block else ""))

    reflect = r.asked_reflection
    reply, outcome = ask_model(r, n, p, prompt, r.args.max_tokens,
                               lambda mode: mock_reply(mode, reflect=reflect))
    if reply is None:
        return None, outcome
    io.open(p + ".response.txt", "w", encoding="utf-8", newline="\n").write(reply["text"])
    r.log("model: %s chars, finish=%s, %ss, usage=%s"
          % (len(reply["text"]), reply["finish_reason"], reply["seconds"], reply["usage"]))
    return reply, None


def drop_declared_removals(r, flow):
    """모델이 쓴 choices_removed 를 지운다. 지운 action 이름을 돌려준다.

    검사 I 는 흐름 명세의 choices_removed 를 읽어 그 값을 누락으로 세지 않는다.
    그 선언은 "연구자가 안전을 이유로 뺐다" 는 뜻인데, 여기서는 흐름 명세를
    모델이 쓴다 - 모델이 스스로 그것을 적으면 자기가 뺀 선택지를 자기가 면제해
    검사 I 를 피해 간다.

    허용하는 제거는 연구자가 관리하는 파일에서만 온다 (audit_call). 그 목록은
    검사 직전에 합쳐지므로, 여기서 지우는 것은 모델의 말뿐이다.

    조용히 지우지 않는다. 남기지 않으면 "모델이 적지 않았다" 와 "적었는데
    지웠다" 를 구분할 수 없고, 모델이 검사를 피하려 했다는 사실 자체가 결과다.
    """
    spec = flow.pop("choices_removed", None)
    if not spec:
        return []
    names = sorted(spec) if isinstance(spec, dict) else [str(spec)]
    r.log("flow: 모델이 쓴 choices_removed 를 지웠다 (%s). 허용하는 제거는 "
          "flows/allowed_removals.json 에서만 읽는다." % ", ".join(names))
    return names


def note_reflection(r, p, entry, text):
    """재시도 답의 반성을 읽어 남긴다. `(반성, 문제들)`.

    반성이 없다고 이 시도를 버리지는 않는다 - 빌드는 멀쩡할 수 있고, 반성
    하나 때문에 재시도 예산을 쓰는 것은 기록을 얻으려다 설계를 잃는 일이다.
    없었다는 사실만 남긴다."""
    refl, problems = parse_reflection(text)
    if refl is None:
        entry["reflection"], entry["reflection_missing"] = None, True
        r.log("reflection: 없음 — 재시도 답이 반성 블록 없이 왔다")
        return None, []
    entry["reflection"] = p + ".reflection.json"
    _dump(refl, entry["reflection"])
    r.log("reflection: %s (계획 변경 %s건)"
          % (one_line(str(refl.get("cause")))[:160],
             len(refl.get("plan_changes") or []) if isinstance(
                 refl.get("plan_changes"), list) else "?"))
    return refl, problems


def revise_plan(r, n, p, entry, refl, problems):
    """반성의 plan_changes 를 계획에 적용한다. 돌려주는 것은 형식 문제들.

    적용하지 못하면 계획은 그대로 두고 문제를 돌려준다 - 그 문제는 흐름 명세
    문제와 같은 형식 실패로 다음 프롬프트에 간다. 적용하면 이 시도의
    attempt_N.plan.json 이 바뀐 계획이 된다 (앞 시도의 파일은 그대로다)."""
    if problems:
        return list(problems)
    changes = refl.get("plan_changes") or []
    if not changes:
        entry["plan_changes"] = 0
        return []
    new, bad = apply_changes(r.plan, r.diagnosis, changes, r.original_screens)
    if bad:
        entry["plan_changes_rejected"] = bad
        r.log("reflection: 계획 변경을 적용하지 못했다 — %s" % " | ".join(bad)[:300])
        return bad
    r.plan = new
    _dump(new, p + ".plan.json")
    entry["plan_changes"] = len(changes)
    if r.summary.get("plan") is not None:
        r.summary["plan"].setdefault("revised_on", []).append(n)
        r.summary["plan"]["screens"] = [sc["name"] for sc in new["screens"]]
        r.summary["plan"]["changes"] = len(new["changes"])
    r.log("reflection: 계획을 고쳤다 (%d건) — 화면 %s"
          % (len(changes), ", ".join(sc["name"] for sc in new["screens"])))
    return []


def check_reply(r, p, entry, reply, n=None):
    """답을 HTML + 흐름 명세로 가르고 모양을 본다. 파일로도 남긴다.

    돌려주는 것은 (build, outcome). build 가 None 이면 파싱이 실패해 이 시도가
    끝난 것이다."""
    refl, refl_problems = None, []
    if r.asked_reflection:
        refl, refl_problems = note_reflection(r, p, entry, reply["text"])
    truncated = reply["finish_reason"] == "length"
    try:
        if truncated:
            raise ValueError("답이 길이 제한에서 잘렸다 (finish_reason=length). "
                             "코드 블록 두 개만, 군더더기 없이 출력하라")
        html, flow, flow_text = parse_reply(reply["text"])
        flow.setdefault("name", "auto")
        flow["derived_from_original"] = False
        dropped = drop_declared_removals(r, flow)
        if dropped:
            entry["choices_removed_dropped"] = dropped
        problems = validate_flow(flow, html)
    except FlowShape as e:
        # 타입이 틀린 흐름 명세. 답의 형식 문제(PARSE)가 아니라 FLOW 문제다.
        r.log("flow: %d problem(s): %s" % (len(e.problems),
                                           " | ".join(e.problems)[:300]))
        entry.update(stage="flow", passed=False, fatal=len(e.problems))
        _dump(problems_report(e.problems), p + ".audit.json")
        r.summary["attempts"].append(entry)
        r.truncated, r.last_error = 0, list(e.problems)
        r.budget.spend("format")
        if r.budget.out_of("format"):
            r.log("형식 재시도 예산 소진 (%d회)" % r.budget.format_used)
            return None, STOP
        return None, GO_ON
    except ValueError as e:
        r.log("parse: %s" % e)
        report = failure_report("PARSE", str(e))
        entry.update(stage="parse", passed=False, fatal=1)
        if truncated:
            entry["truncated"] = True
        _dump(report, p + ".audit.json")
        r.summary["attempts"].append(entry)
        # 이 시도는 검사를 받은 적이 없다. r.last 는 마지막으로 **검사까지 간**
        # 빌드와 그 결과이므로 건드리지 않는다 - 덮으면 다음 프롬프트가 그 HTML
        # 에서 나오지 않은 실패 목록을 "이것을 고쳐라" 와 함께 보게 된다.
        if truncated:
            # 잘린 답은 형식 오류와 겉모양이 같다. 한 번만 말하게 한다.
            r.truncated += 1
            r.last_error = None
        else:
            r.truncated = 0
            r.last_error = str(e)
        r.budget.spend("format")
        if r.budget.out_of("format"):
            r.log("형식 재시도 예산 소진 (%d회)" % r.budget.format_used)
            return None, STOP
        return None, GO_ON

    # 여기까지 왔으면 답은 읽을 수 있는 모양이다. 형식 오류는 해결되었다.
    r.truncated, r.last_error = 0, None

    # 반성이 계획을 바꿨으면 그것부터 반영한다 - 아래 일치 검사는 바뀐 계획과
    # 비교해야 한다. 답 자체를 읽지 못한 시도에서는 계획을 바꾸지 않는다.
    if refl is not None:
        problems = problems + revise_plan(r, n, p, entry, refl, refl_problems)

    # 생성물이 계획의 화면을 그대로 가졌는지. 어긋나면 계획이 생성물을 설명하지
    # 못한다 (plan.match_problems). 흐름 명세 문제와 같은 형식 실패다.
    mismatch = match_problems(r.plan, html) if r.plan else []
    if mismatch:
        entry["plan_mismatch"] = mismatch
        problems = problems + mismatch

    # 선택지 데이터는 도구가 넣는다. 참조 검사는 **넣기 전** 의 HTML 로 한다 -
    # 넣은 뒤의 문서에는 `window.PRESERVED = {...}` 가 늘 있으므로, 그것으로
    # 보면 무엇을 보내도 "읽었다" 가 된다 (reply.preserved_problems).
    names = list(r.preserved)
    read = names_read(html, names)
    problems = problems + preserved_problems(html, r.preserved)
    build_html, redeclared = inject(html, r.preserved)
    if names:
        entry["preserved"] = {"injected": {n: len(v) for n, v in r.preserved.items()},
                              "redeclared": redeclared, "read": read}
        r.log("preserved: %s 를 넣었다 (참조 %s%s)"
              % (", ".join("%s %d" % (n, len(v)) for n, v in r.preserved.items()),
                 ", ".join(read) or "없음",
                 (" / 모델이 다시 선언한 것: %s" % ", ".join(redeclared))
                 if redeclared else ""))

    html_path, flow_path = p + ".html", p + ".flow.json"
    io.open(html_path, "w", encoding="utf-8", newline="\n").write(build_html)
    io.open(flow_path, "w", encoding="utf-8", newline="\n").write(
        json.dumps(flow, ensure_ascii=False, indent=2))
    entry["html"], entry["flow"] = html_path, flow_path
    if names:
        # 주입하기 **전**, 모델이 쓴 그대로. 연구에서 "모델이 만든 것" 과
        # "도구가 고친 것" 을 가르려면 둘이 파일로 나란히 있어야 한다 -
        # 답 전문(.response.txt)은 실행 폴더에만 있고 승격된 산출물 옆에는
        # 없다.
        entry["model_html"] = p + ".model.html"
        io.open(entry["model_html"], "w", encoding="utf-8",
                newline="\n").write(html)
    # `html` 은 **모델이 쓴** 것이다. 재시도 블록에 그대로 들어가므로 주입한
    # 것을 넣으면 모델이 자기가 쓰지 않은 데이터 블록을 프롬프트로 돌려받는다 -
    # 입력의 목록 전체가 프롬프트에 두 번 들어가고, 고칠 것도 아니다.
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
        return problems_report(problems)

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
                         build["flow_path"], url_for(rel), shots, r.args.stage,
                         original_url=r.original_url,
                         allowed_removals=r.allowed_removals)
    except Exception as e:                           # a flow the audit cannot drive
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
                          "flow": build["flow_path"],
                          "audit": p + ".audit.json",
                          # 이 빌드를 만들 때 쓴 계획과, 그 계획의 바탕인 진단
                          "plan": entry.get("plan"),
                          "diagnosis": (r.summary.get("plan") or {}).get("diagnosis"),
                          # 이 빌드에 도구가 무엇을 넣고 무엇을 고쳤는지.
                          # 시도 기록에만 두면, 승격된 산출물만 보는 사람은
                          # 그 파일의 어느 부분이 모델의 것인지 알 수 없다.
                          "preserved": entry.get("preserved"),
                          "model_html": entry.get("model_html")}
    if report.get("passed"):
        r.summary["passed"] = True
        r.log("PASSED on attempt %d" % n)
        return STOP
    r.last = {"report": report, "html": build["html"], "flow_text": build["flow_text"]}
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

    plan_call = None
    if r.plan is None:
        plan_call, outcome = request_plan(r, n, p)
        if outcome is not None:
            return outcome
        # 두 호출이 같은 1분 안에 들어가면 분당 한도를 넘는다 - 원본 HTML 이
        # 두 프롬프트에 다 들어 있다.
        if r.args.delay and not r.args.mock:
            r.log("대기 %ss (진단·계획 → 생성)" % r.args.delay)
            time.sleep(r.args.delay)
    # 이 시도가 따른 계획. 재시도에서 계획이 바뀌면 시도마다 다른 파일이 된다.
    _dump(r.plan, p + ".plan.json")

    reply, outcome = request_reply(r, n, p)
    if reply is None:
        return outcome
    entry = {"n": n, "finish_reason": reply["finish_reason"], "usage": reply["usage"],
             "seconds": reply["seconds"], "repro": repro(r.template, reply),
             "plan": p + ".plan.json"}
    if plan_call:
        entry["plan_call"] = plan_call
    build, outcome = check_reply(r, p, entry, reply, n)
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


# outputs/ 안에서 "지금 쓰는 것" 을 가리키는 이름들. 실행 이름이 붙은 사본은
# 같은 이름에 실행 폴더 이름이 하나 끼어든다.
PROMOTED = [("html", "restructured_auto%s.html"),
            ("flow", "restructured_auto%s.flow.json"),
            ("audit", "audit_auto%s.json"),
            # 이 빌드를 만든 진단과 계획. 승격된 산출물만 보는 사람도 "무엇을
            # 근거로 무엇을 바꿨는지" 를 같은 자리에서 찾을 수 있어야 한다.
            ("plan", "restructured_auto%s.plan.json"),
            ("diagnosis", "restructured_auto%s.diagnosis.json"),
            # 주입 전, 모델이 쓴 그대로. 승격된 산출물에는 도구가 넣은
            # 데이터 블록과 고친 선언이 들어 있으므로, 둘을 나란히 두지
            # 않으면 "모델이 만든 것" 을 되찾을 수 없다. 뽑을 데이터가
            # 없는 입력에서는 이 자리가 비고, 그때는 건너뛴다.
            ("model_html", "restructured_auto%s.model.html")]


def copy_final(r):
    """통과한 빌드만 outputs/ 로 올린다. 사본은 실행 이름으로도 하나 남긴다.

    통과 여부와 무관하게 복사하던 것을 바꿨다. `restructured_auto.html` 은
    뷰어와 실험 조건이 "지금 쓰는 재구성본" 으로 읽는 이름인데, 떨어진 빌드가
    그 자리에 올라오면 마지막으로 통과한 빌드가 조용히 사라진다 - 떨어졌다는
    사실은 summary.json 에만 남고, 그 자리의 파일은 멀쩡해 보인다.

    실행 이름이 붙은 사본을 함께 두는 이유는 그 반대다. 통과한 실행이 둘 이상
    이면 나중 것이 앞의 것을 덮는데, 둘을 비교할 수 있어야 한다.
    """
    f = r.summary["final"]
    if not f:
        return
    if not r.summary.get("passed"):
        r.log("final: 통과한 빌드가 없다 — outputs/restructured_auto.* 는 그대로 둔다")
        return
    out, name = outputs_dir(), os.path.basename(r.run_dir)
    os.makedirs(out, exist_ok=True)
    promoted = []
    for key, pattern in PROMOTED:
        if not f.get(key):
            continue
        shutil.copy2(f[key], os.path.join(out, pattern % ""))
        shutil.copy2(f[key], os.path.join(out, pattern % ("." + name)))
        promoted.append(pattern % "")
    r.log("final: attempt %d -> %s (+ .%s 사본)"
          % (f["attempt"], ", ".join(promoted), name))
    # 도구가 모델의 목록을 고쳤다면, 통과한 산출물이 모델이 쓴 그대로가
    # 아니다. 조용히 넘기면 연구에서 그 둘을 구분할 길이 없다.
    pres = f.get("preserved") or {}
    if pres.get("redeclared"):
        r.log("final: 주의 - 이 산출물은 모델이 쓴 그대로가 아니다. 도구가 "
              "%s 의 선언을 입력의 데이터로 바꿨다. 모델이 쓴 것은 %s 다."
              % (", ".join(pres["redeclared"]),
                 dict(PROMOTED)["model_html"] % ""))


# --------------------------------------------------------------------------- #
# 종료 코드
# --------------------------------------------------------------------------- #
# 이 이유로 멈춘 실행은 "빌드가 떨어졌다" 가 아니라 "돌지 못했다" 다. 부르는
# 쪽은 둘을 구분해야 한다 - 떨어진 빌드는 다시 만들고, 돌지 못한 실행은 다시
# 만들 것이 없다. senior_ui.audit 의 종료 코드 규약과 같다 (docs/README.md).
CANNOT_RUN = {"rate_limit", "api_rejected", "infra_exhausted", "cannot_start"}


def exit_code(summary):
    """0 = 통과한 빌드가 있다, 1 = 전부 실패, 2 = 아예 돌지 못했다."""
    if summary.get("passed"):
        return 0
    return 2 if summary.get("stopped_reason") in CANNOT_RUN else 1


def run(args):
    """한 실행 전체. 돌려주는 것이 프로세스의 종료 코드다 - exit_code 참고."""
    # 검사기는 빌드를 :3003 이 서빙하는 http:// 로 연다. 그 서버는 저장소
    # 루트만 서빙하므로, 산출물 폴더가 밖에 있으면 검사기가 빌드를 열지 못해
    # 첫 화면에서 멈춘다 - 그것이 설계 실패처럼 보인다.
    if not inside_root(outputs_dir()):
        print("cannot start: %s 가 저장소 루트 밖을 가리킨다 (%s). 검사기는 "
              ":3003 이 서빙하는 %s 안의 파일만 열 수 있다."
              % (OUTPUTS_ENV, outputs_dir(), ROOT), file=sys.stderr)
        return 2

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = os.path.join(runs_dir(),
                           stamp + ("-mock-" + args.mock if args.mock else ""))
    os.makedirs(run_dir, exist_ok=True)
    log = make_logger(os.path.join(run_dir, "run.log"))

    try:
        load_env()
    except RuntimeError as e:
        log("cannot start: %s" % e)
        print("cannot start: %s" % e, file=sys.stderr)
        _dump({"run_dir": run_dir, "passed": False, "attempts": [],
               "stopped_reason": "cannot_start", "error": str(e)},
              os.path.join(run_dir, "summary.json"))
        log("summary: %s" % os.path.join(run_dir, "summary.json"))
        return 2
    model = pick_model(args)
    if not args.mock and not os.environ.get("OPENAI_API_KEY"):
        print("no OPENAI_API_KEY in the environment or .envs", file=sys.stderr)
        return 2

    try:
        template = load_template()
        plan_template = load_plan_template()
        original_html = io.open(args.original, encoding="utf-8").read()
        orig_url = original_url(args.original)
        allowed = load_allowed_removals()
    except (OSError, RuntimeError) as e:
        log("cannot start: %s" % e)
        print("cannot start: %s" % e, file=sys.stderr)
        _dump({"run_dir": run_dir, "passed": False, "attempts": [],
               "stopped_reason": "cannot_start", "error": str(e)},
              os.path.join(run_dir, "summary.json"))
        log("summary: %s" % os.path.join(run_dir, "summary.json"))
        return 2

    log("run: %s | model=%s | attempts=%d | stage=%s | mock=%s | original=%s"
        % (run_dir, model, args.attempts, args.stage, args.mock, orig_url))
    r = Run(args, log, run_dir, model, template, original_html, orig_url,
            plan_template=plan_template)
    r.allowed_removals = allowed
    if allowed:
        log("선택지 제거 허용 (연구자 파일): %s" % ", ".join(sorted(allowed)))
    server = None
    try:
        # 띄우지 못했거나, 떠 있는 것이 이 저장소를 서빙하지 않는다. 둘 다
        # "빌드가 떨어졌다" 가 아니라 "돌지 못했다" 다.
        try:
            server = ensure_server(log)
        except RuntimeError as e:
            log("cannot start: %s" % e)
            print("cannot start: %s" % e, file=sys.stderr)
            r.summary["stopped_reason"] = "cannot_start"
            r.summary["error"] = str(e)
            return exit_code(r.summary)
        # 대비·언어 검사의 기준이 되는 원본 스냅샷. 실행마다 한 번만 걷는다.
        base_flow = A.load_flow(None)
        log("audit: driving the original once (baseline for contrast / language)")
        r.orig_snapshot = asyncio.run(A.drive(r.original_url, base_flow))
        r.choices = choices_block(r.orig_snapshot, original_html)
        if r.choices:
            log("선택지: %s" % " / ".join(
                l.strip() for l in r.choices.splitlines() if l.startswith("  ")))
        # 입력이 스크립트 배열로 그리는 선택지. 모델이 다시 타이핑하지 않도록
        # 도구가 들고 있다가 시도마다 재설계 HTML 에 넣는다.
        r.preserved = preserved_data(r.orig_snapshot, original_html)
        r.summary["preserved"] = {n: len(v) for n, v in r.preserved.items()}
        if r.preserved:
            log("지킬 데이터: %s" % " / ".join(
                "%s %d개" % (n, len(v)) for n, v in r.preserved.items()))

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
    finally:
        if server:
            server.terminate()
            log("server: stopped (pid %d)" % server.pid)
        # 요약은 이 실행의 기록이다. 루프가 터져도(흐름 명세가 검사기를 터뜨린다,
        # 사용자가 끊는다) 남아야 한다 - 밖에 두면 그런 실행은 run.log 조각
        # 말고는 아무것도 남기지 않는다.
        r.summary["budget"] = r.budget.as_dict()
        copy_final(r)
        _dump(r.summary, os.path.join(run_dir, "summary.json"))
        log("summary: %s" % os.path.join(run_dir, "summary.json"))
    return exit_code(r.summary)
