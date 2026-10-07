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
import subprocess
import sys
import time
import traceback

from playwright.async_api import Error as PlaywrightError

from senior_ui import audit as A
from senior_ui import config
from senior_ui.audit.drive import SHOT_SAFE
from senior_ui.audit.flow import required_errors
from senior_ui.audit.inputs import load_allowed_removals, model_claims
from senior_ui.config import OUTPUTS_ENV, ROOT, inside_root, outputs_dir, url_for
from senior_ui.devserver import ensure_server
from senior_ui.tasks import DEFAULT_TASK, abs_path, load_task

from .audit_call import run_audit
from .brief import write_brief
from .model import (MOCK_TASK, TEMPERATURE, SEED, ApiRejected, InfraFailed,
                    RateLimited, call_model, cost_usd, describe, describe_ratelimit,
                    estimate_tokens, load_env, mock_plan_reply, mock_reply, price_for,
                    profile_for, sdk_version, wait_for_tokens, describe_images,
                    model_text, prompt_record, mock_refine_reply,
                    mock_refine_fix_reply)
from .plan import (PlanProblems, apply_changes, critique_issues, evidence_kinds,
                   match_problems, parse_critique, parse_plan, parse_reflection,
                   plan_report, screens_in, unaddressed)
from .preserve import inject, names_read, optional_names, preserved_data
from .prompt import (BUILD_SHOTS_INTRO, build_plan_prompt, build_prompt,
                     build_refine_prompt, choices_block, errors_block,
                     load_plan_template, load_refine_template, load_template,
                     model_input_html, one_line, REFINE_FIX_NOTE,
                     plan_retry_block, retry_block, shots_section, with_reflection)
from .reply import (FlowShape, accept_done_alias, failure_report, parse_reply,
                    preserved_problems, problems_report, validate_flow)

def runs_dir(mock=False):
    """실행 폴더들이 쌓이는 곳. 산출물 폴더와 같이 움직인다 (config.outputs_dir)."""
    return os.path.join(outputs_dir(mock), "restructure_auto")

def output_caps(profile, args=None):
    """`{"generate", "plan"}` - 이 실행의 두 호출의 길이 제한.

    진단·계획 호출은 생성 호출과 따로 둔다 - 분당 한도는 max_tokens 를 미리
    잡아 두고 세므로, 계획 JSON 에 생성과 같은 한도를 주면 쓰지도 않을 토큰이
    한도를 먹는다. 주지 않은 쪽은 config.OUTPUT_CAPS 에서 추론형이냐로 고른다 -
    추론형은 생각 토큰도 이 안에서 쓴다."""
    caps = dict(config.OUTPUT_CAPS["reasoning" if profile["reasoning"] else "gpt-4o"])
    given = {"generate": getattr(args, "max_tokens", None),
             "plan": getattr(args, "plan_max_tokens", None)}
    caps.update({k: v for k, v in given.items() if v})
    return caps


def effort_choice(profile, args=None):
    """`(reasoning_effort, 어디서 왔나)`. 추론형이 아니면 (None, None) - 보내지 않는다.

    추론형인데 --reasoning-effort 를 주지 않았으면 config.DEFAULT_REASONING_EFFORT
    를 보낸다. 모델의 기본값에 맡기면 그 값이 기록에 남지 않는다 - 모델마다
    다르고, 같은 모델도 바뀔 수 있다."""
    if not profile["reasoning"]:
        return None, None
    given = getattr(args, "reasoning_effort", None)
    if given:
        return given, "--reasoning-effort"
    return config.DEFAULT_REASONING_EFFORT, "config.DEFAULT_REASONING_EFFORT"


def stage_choice(args):
    """`(검사 단계, 어디서 왔나)`. --stage 를 주면 그 값, 아니면 config.DEFAULT_STAGE."""
    given = getattr(args, "stage", None)
    if given:
        return given, "--stage"
    return config.DEFAULT_STAGE, "config.DEFAULT_STAGE"


def budget_choice(args):
    """`{"format": (횟수, 출처), "audit": (횟수, 출처), "infra": (횟수, 출처)}`.

    예산마다 --format-attempts · --audit-attempts · --infra-attempts, 그다음 설계
    예산 둘을 한 번에 정하는 --attempts (infra 에는 닿지 않는다), 그다음
    config.DEFAULT_BUDGET 순서다."""
    out = {}
    for kind in ("format", "audit", "infra"):
        own = getattr(args, kind + "_attempts", None)
        both = getattr(args, "attempts", None) if kind != "infra" else None
        if own is not None:
            out[kind] = (own, "--%s-attempts" % kind)
        elif both is not None:
            out[kind] = (both, "--attempts")
        else:
            out[kind] = (config.DEFAULT_BUDGET[kind], "config.DEFAULT_BUDGET")
    return out


def see_choice(args):
    """`(보기를 켜는가, 어디서 왔나)`. --see off 면 끈다 - 화면을 보여 주지 않던
    전의 동작으로, 보여 준 효과를 견줄 때 쓴다."""
    given = getattr(args, "see", None)
    if given:
        return given != "off", "--see"
    return True, "기본값 (켜짐)"


def refine_choice(args):
    """`(다듬기 횟수, 어디서 왔나)`. --refine N, 아니면 config.DEFAULT_REFINE."""
    given = getattr(args, "refine", None)
    if given is not None:
        return given, "--refine"
    return config.DEFAULT_REFINE, "config.DEFAULT_REFINE"


# 그림 이름표. 원본은 진단·계획 호출에, 빌드는 다듬기 호출에 들어간다.
ORIGINAL_LABELS = {"screen": "원본 화면", "error": "원본 오류 상태"}
BUILD_LABELS = {"screen": "화면", "error": "오류 상태"}


def see_images(shots, labels, error_ids=()):
    """찍어 둔 그림들을 `[{"label", "path"}]` 로. 화면은 see/index.json 순서,
    그 뒤에 오류 상태(audit_error_<id>.png, 과제의 오류 순서). 없는 것은 건너뛴다.

    이름표에는 화면 이름과, 스크롤되는 화면이면 몇 번째 장인지와 몇 px 내린
    모습인지를 적는다. 4장에서 끊긴 화면은 남은 높이도 적는다."""
    if not shots:
        return []
    out = []
    index = os.path.join(shots, "see", "index.json")
    items = json.load(io.open(index, encoding="utf-8")) if os.path.exists(index) else []
    for it in items:
        label = "%s %s" % (labels["screen"], it["visit"])
        if it["parts"] > 1:
            label += " — 스크롤 %d/%d (%s)" % (
                it["part"], it["parts"],
                "맨 위" if it["offset"] == 0 else "%dpx 내린 모습" % it["offset"])
        if it.get("more_px"):
            label += " · 아래로 %dpx 더 있음 (찍지 않음)" % it["more_px"]
        path = os.path.join(shots, "see", it["file"])
        if os.path.exists(path):
            out.append({"label": label, "path": path})
    for eid in error_ids:
        path = os.path.join(shots, "audit_error_%s.png" % SHOT_SAFE.sub("_", eid))
        if os.path.exists(path):
            out.append({"label": "%s %s — 잘못된 값을 넣은 직후" % (labels["error"], eid),
                        "path": path})
    return out


def describe_settings(stage, budget):
    """run.log 첫 줄에 잇는 검사 단계와 예산. 출처가 같으면 한 번만 적는다."""
    (f, fs), (a, as_) = budget["format"], budget["audit"]
    money = ("예산 형식 %d · 검사 %d (출처 %s)" % (f, a, fs) if fs == as_
             else "예산 형식 %d (출처 %s) · 검사 %d (출처 %s)" % (f, fs, a, as_))
    if "infra" in budget:
        money += " · 인프라 %d (출처 %s)" % budget["infra"]
    return "stage=%s (출처 %s) · %s" % (stage[0], stage[1], money)


def call_delay(profile, args=None):
    """모델 호출 사이 대기(초). --delay 를 주면 그 값, 아니면 config.DELAY."""
    given = getattr(args, "delay", None)
    if given is not None:
        return given
    return config.DELAY["reasoning" if profile["reasoning"] else "gpt-4o"]


def cap_source(profile):
    """run.log 에 적는, 기본값이 어디서 왔는지."""
    return "기본값 config.OUTPUT_CAPS[%r]" % ("reasoning" if profile["reasoning"]
                                            else "gpt-4o")

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

    def __init__(self, fmt, aud, infra):
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


class Stopped(Exception):
    """설계와 무관한 이유로 실행을 여기서 끝낸다 - 시도 안 깊은 곳(검사기 호출)
    에서 run() 까지 곧장 올라간다. `reason` 이 summary.stopped_reason 이 된다."""

    def __init__(self, reason):
        Exception.__init__(self, reason)
        self.reason = reason


class Run:
    """한 실행이 공유하는 것들. 단계 함수들은 이것만 주고받는다."""

    def __init__(self, args, log, run_dir, model, template, original_html,
                 original_url=None, plan_template="", task=None, model_source=None,
                 refine_template=""):
        self.args = args
        self.refine_template = refine_template
        # 프롬프트에 넣는 원본과 브라우저가 걷는 원본은 같은 문서다.
        self.original_url = original_url
        self.log = log
        self.run_dir = run_dir
        self.model = model
        self.template = template
        self.plan_template = plan_template
        self.original_html = original_html
        # 모델에 보내는 원본 - 주석을 뺀 것 (prompt.model_input_html). 검사기의
        # 비교 기준은 위의 원본 그대로다.
        self.model_original = model_input_html(original_html)
        # 원본의 화면 이름. 계획의 from 이 가리킬 수 있는 이름들이다.
        self.original_screens = screens_in(original_html)
        # 이 실행의 과제 (tasks/<과제>.json). 과제가 정한 오류 경로는 계획 ·
        # 프롬프트의 오류 조건 · 형식 검사 · 설명서가 같은 목록을 쓴다.
        self.task = task or load_task(DEFAULT_TASK)
        self.errors = required_errors(self.task["id"])
        # 진단과 지금의 계획. 계획은 실행에 하나이고 재시도에서 고쳐진다.
        self.diagnosis = None
        self.plan = None
        # 직전 진단·계획 답의 문제. 다음 진단·계획 프롬프트로 간다.
        self.plan_error = None
        # 이번 생성 프롬프트가 반성을 요청했는가 (재시도일 때).
        self.asked_reflection = False
        # 이 시도의 모델 호출들, 그리고 실행 전체의 (시도 번호, 호출) 목록.
        # 단계별 토큰은 끝에 이것으로 센다 (tally_tokens).
        self.calls = []
        self.all_calls = []
        # 못박아 두는 값. 지정하지 않으면 공급자의 기본값이 쓰이고 그 값은
        # 기록에 남지 않는다 - 나중에 "그때 무엇이 달랐나" 를 물을 수 없다.
        self.temperature = getattr(args, "temperature", TEMPERATURE)
        self.seed = getattr(args, "seed", SEED)
        # 모델마다 부르는 방식 (model.profile_for). 생각에 쓸 노력은 추론형이면
        # 주지 않아도 config 의 기본값을 보낸다 (effort_choice).
        self.api = getattr(args, "api", None)
        self.profile = profile_for(model, self.api)
        # 그 부르는 방식에서 실제로 보내는 값 (sent_values). 재현 기록은 이것만 적는다.
        self.sent = sent_values(self.profile, self.temperature, self.seed)
        self.reasoning_effort = effort_choice(self.profile, args)[0]
        # 두 호출의 길이 제한 (output_caps). 주지 않았으면 모델에 맞춘 기본값.
        self.caps = output_caps(self.profile, args)
        # 호출 사이 대기 (call_delay). 추론형이면 호출 직전에 직전 응답 헤더의
        # 남은 토큰도 본다 (wait_tokens) - 그 헤더와 받은 때를 들고 있는다.
        self.delay = call_delay(self.profile, args)
        self.last_ratelimit = None
        self.last_ratelimit_at = None
        self.choices = ""
        # 입력이 가진 선택지 데이터. 실행마다 한 번 뽑아 시도마다 넣는다.
        # {배열 이름: [원소들]} (preserve.preserved_data).
        self.preserved = {}
        # 그중 읽으라고 하지 않는 이름 - 과제가 선택지가 아니라고 선언한 무리만
        # 받치는 배열 (preserve.optional_names, 공과금의 MENU_TABS).
        self.preserved_optional = []
        # 연구자가 관리하는 "빼도 되는 선택지" 목록. 검사 직전에 흐름에 합친다.
        self.allowed_removals = {}
        self.orig_snapshot = None
        budget = budget_choice(args)
        self.budget = Budget(budget["format"][0], budget["audit"][0],
                             budget["infra"][0])
        # 보기 (--see): 원본 그림을 진단·계획 호출에 넣는가. 원본 그림은 실행
        # 시작 때 한 번 찍는다 (run).
        self.see, see_source = see_choice(args)
        self.original_images = []
        # 보고 다듬기 (--refine): 통과한 빌드를 그림으로 보여 주고 다듬게 하는
        # 횟수. 형식 · 검사 예산과 따로 센다.
        self.refine, refine_source = refine_choice(args)
        # 마지막으로 **검사까지 간** 빌드와 그 결과. 셋은 늘 같은 시도의 것이다.
        self.last = {"report": None, "html": None, "flow_text": None}
        # 마지막 형식 오류. 검사 결과와 다른 것이므로 따로 들고 있는다 - 한쪽을
        # 다른 쪽에 넣으면 재시도 프롬프트가 둘 중 하나를 잃는다.
        self.last_error = None
        # 길이 제한에 잘린 답이 연속 몇 번인지. 둘째 번부터는 안내가 달라진다.
        self.truncated = 0
        # 과제는 실행 기록 안에 있어야 한다 - 여러 실행을 모아 볼 때 과제를 가른다.
        # model 은 보낸 이름, response_models 는 API 가 답한 이름들이다. 별칭
        # (gpt-4o)은 날짜가 붙은 판으로 풀리고, 그 판은 말없이 바뀐다.
        self.summary = {"run_dir": run_dir, "model": model, "model_source": model_source,
                        "response_models": [],
                        "model_call": dict(self.profile,
                                           reasoning_effort=self.reasoning_effort),
                        "mock": args.mock,
                        "task": self.task["id"],
                        "stage": args.stage,
                        "stage_source": getattr(args, "stage_source", None),
                        "budget_source": {k: v[1] for k, v in budget.items()},
                        "preserved": {}, "plan": None,
                        "repro": repro(template, temperature=self.sent["temperature"],
                                       seed=self.sent["seed"]),
                        "attempts": [], "passed": False, "final": None,
                        "budget": {}, "stopped_reason": None, "trend": [],
                        "git": None, "tokens": None,
                        # 마지막 실제 호출이 받은 분당 한도 (호출마다는 calls[].ratelimit)
                        "ratelimit": None,
                        # 시도별·전체 예상 금액 (config.MODEL_PRICES, tally_cost)
                        "cost": None,
                        "see": {"on": self.see, "source": see_source,
                                "original_images": 0},
                        "refine": {"budget": self.refine, "source": refine_source,
                                   "rounds": [], "final_from": None,
                                   "final_label": None, "reverted": None,
                                   "format_failures": 0, "audit_failures": 0}}


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


def model_choice(args):
    """`(모델 이름, 어디서 왔나)`. --model, 환경 변수, config.DEFAULT_MODEL 순서다.

    어디서 왔는지를 함께 돌려주는 이유는 환경 변수다. .envs 나 셸에 남아 있던
    RESTRUCTURE_MODEL 하나가 기본값을 말없이 이기면, 실행 기록의 모델 이름만
    보고는 그것이 의도한 것인지 알 수 없다.

    mock 실행은 환경 변수를 보지 않는다 (--model 은 본다). mock 기준값(tests/
    baseline/mock_*.json)은 모델에 따라 부르는 방식 · 길이 제한 · 가격표가 갈리는데,
    셸에 남은 변수 하나로 그것이 PC 마다 달라지면 기준값 비교가 뜻을 잃는다
    (감사 B-26). .envs 도 읽지 않는다 (run).
    """
    if getattr(args, "model", None):
        return args.model, "--model"
    if not getattr(args, "mock", None):
        for name in config.MODEL_ENV_VARS:
            if os.environ.get(name):
                return os.environ[name], name
    return config.DEFAULT_MODEL, "config.DEFAULT_MODEL"


# mock 실행이 run.log 둘째 줄에 남기는 말. PC 마다 같은 글이다 - 변수가 있었는지는
# 적지 않는다 (있었든 없었든 듣지 않았다).
MOCK_ENV_NOTE = ("mock: .envs 와 환경 변수(%s)의 모델 값은 읽지 않는다 - mock 결과가 "
                 "PC 마다 달라지지 않게")


def pick_model(args):
    return model_choice(args)[0]


def sent_values(profile, temperature, seed):
    """`{"temperature", "seed"}` - 그 부르는 방식(model.profile_for)에서 실제로 보내는
    값. 보내지 않는 것은 None 이다 (model.request_kwargs 와 같은 규칙).

    재현 기록(repro)은 이것만 적는다. 추론형은 temperature 를 받지 않는데 실행
    전체의 repro 에 0.0 이 적혀, 같은 summary 의 model_call.temperature=false ·
    시도별 None 과 모순됐다 (감사 B-18)."""
    return {"temperature": temperature if profile["temperature"] else None,
            "seed": seed if profile["seed"] else None}


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


def git_state():
    """실행 당시의 커밋과 작업 트리가 깨끗했는지.

    자동 실행 7회가 모두 커밋되지 않은 코드에서 돌아서, 나중에 그 조건을
    되짚을 수 없었다 (docs/variance-notes.md). 커밋 해시만으로는 부족하다 -
    작업 트리가 깨끗하지 않으면 그 해시가 실행된 코드를 가리키지 않는다.

    git 이 없거나 저장소가 아니면 모두 None 이다. 모른다는 것도 기록이다.
    """
    def git(*args):
        return subprocess.run(["git"] + list(args), cwd=ROOT, capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              check=True).stdout
    try:
        commit = git("rev-parse", "HEAD").strip()
        branch = git("rev-parse", "--abbrev-ref", "HEAD").strip()
        status = git("status", "--porcelain")
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "branch": None, "dirty": None, "dirty_files": []}
    files = [line[3:] for line in status.splitlines() if line.strip()]
    return {"commit": commit, "branch": branch, "dirty": bool(files),
            "dirty_files": files[:50]}


def dirty_warning(git):
    """run.log 첫 줄(모델 다음)에 잇는 경고. 깨끗하면 None. 실행은 막지 않는다."""
    if not git or not git.get("dirty"):
        return None
    files = git.get("dirty_files") or []
    return ("경고: 작업 트리가 깨끗하지 않다 — 커밋 %s 에 없는 변경 %d건 위에서 "
            "돈다 (%s%s). 이 실행의 조건을 커밋 해시만으로 되짚을 수 없다."
            % ((git.get("commit") or "?")[:12], len(files), ", ".join(files[:5]),
               " …" if len(files) > 5 else ""))


def _sum(calls, key):
    """호출들의 usage 합. 하나도 모르면 None - 0 과 "모른다" 는 다르다."""
    vals = [(c.get("usage") or {}).get(key) for c in calls]
    vals = [v for v in vals if v is not None]
    return sum(vals) if vals else None


def _tally(calls):
    """completion 은 생각 토큰을 포함한다 (요금도 출력으로 매겨진다). reasoning 은
    그중 생각에 쓴 몫 - 추론형이 아니면 None 이거나 0 이다."""
    return {"calls": len(calls),
            "estimated_prompt": sum(c["estimated_prompt"] for c in calls),
            "images": sum(c.get("images") or 0 for c in calls),
            "estimated_images": sum(c.get("estimated_images") or 0 for c in calls),
            "max_tokens": sum(c["max_tokens"] for c in calls),
            "prompt": _sum(calls, "prompt"),
            "completion": _sum(calls, "completion"),
            "reasoning": _sum(calls, "reasoning")}


def tally_tokens(r):
    """단계별 · 전체 · 첫 시도의 토큰. 예상(보내기 전 어림)과 실측(usage)을 함께.

    단계는 셋이다 - plan (진단·계획), generate (첫 생성), retry (반성 + 생성).
    """
    calls = [c for _n, c in r.all_calls]
    if not calls:
        return None
    stages = {}
    for c in calls:
        stages.setdefault(c["stage"], []).append(c)
    first = [c for n, c in r.all_calls if n == 1]
    return {"method": calls[0].get("method"),
            "by_stage": {k: _tally(v) for k, v in stages.items()},
            "total": _tally(calls),
            "first_attempt": _tally(first) if first else None}


def _add(values):
    """금액들의 합. 하나도 모르면 None - 0 과 "모른다" 는 다르다."""
    values = [v for v in values if v is not None]
    return round(sum(values), 6) if values else None


def tally_cost(r):
    """시도별 · 전체 예상 금액 (USD). 가격은 config.MODEL_PRICES 의 이 모델 값.

    가격이 비었거나 usage 가 없으면(mock) 금액은 null 이다. 캐시된 입력의
    할인은 넣지 않으므로 상한 쪽 어림이다."""
    price = price_for(r.model)
    attempts = []
    for n in sorted({n for n, _c in r.all_calls}):
        attempts.append({"attempt": n, "usd": _add(
            cost_usd(c.get("usage"), price) for m, c in r.all_calls if m == n)})
    return {"currency": "USD", "price_model": r.model, "per_million": price,
            "by_attempt": attempts, "total_usd": _add(a["usd"] for a in attempts),
            "note": "입력 x input + 출력(생각 포함) x output, 100만 토큰당. 캐시 할인 "
                    "미반영 (상한)"}


def log_cost(r):
    c = r.summary.get("cost")
    if not c or not c["by_attempt"]:
        return
    if c["per_million"] is None:
        r.log("예상 금액: 가격표에 %s 가 비어 있다 — null (config.MODEL_PRICES)"
              % c["price_model"])
        return
    def usd(v):
        return "-" if v is None else "$%.4f" % v
    r.log("예상 금액: %s · 전체 %s (가격표 %s %.2f / %.2f, 캐시 할인 미반영)"
          % (" · ".join("시도 %d %s" % (a["attempt"], usd(a["usd"]))
                        for a in c["by_attempt"]),
             usd(c["total_usd"]), c["price_model"], c["per_million"]["input"],
             c["per_million"]["output"]))


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
    images = r.original_images
    prompt = build_plan_prompt(r.plan_template, r.model_original, r.choices,
                               r.original_screens, plan_retry_block(r.plan_error),
                               errors=errors_block(r.errors),
                               shots=shots_section(images))
    io.open(p + ".plan_prompt.txt", "w", encoding="utf-8", newline="\n").write(
        prompt_record(prompt, images, r.model, base=r.run_dir))
    r.log("plan prompt: %d chars%s%s" % (len(prompt),
                                         " (with retry block)" if r.plan_error else "",
                                         " + 그림 %d장" % len(images) if images else ""))
    reply, outcome = ask_model(r, n, p, prompt, r.caps["plan"], mock_plan_reply, "plan",
                               images=images)
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
        diagnosis, plan = parse_plan(reply["text"], r.original_screens,
                                     [e["id"] for e in r.errors])
    except PlanProblems as e:
        r.log("plan: %d problem(s): %s" % (len(e.problems),
                                           " | ".join(e.problems)[:300]))
        entry = dict(call, n=n, stage="plan", passed=False, fatal=len(e.problems),
                     calls=list(r.calls))
        if reply["finish_reason"] == "length":
            note_truncated(r, entry, "plan")
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
    kinds = evidence_kinds(diagnosis)
    r.summary["plan"] = {"attempt": n, "diagnosis": p + ".diagnosis.json",
                         "diagnosis_count": len(diagnosis),
                         # 근거의 종류 - 화면 그림을 보고 한 진단이 얼마나 되나
                         "evidence_kinds": kinds,
                         "screens": [sc["name"] for sc in plan["screens"]],
                         "changes": len(plan["changes"]),
                         "unaddressed": left}
    r.log("plan: 근거 화면 %d · 코드 %d · 둘 다 %d · 미표시 %d"
          % (kinds["screen"], kinds["code"], kinds["both"], kinds["missing"]))
    r.log("plan: 진단 %d · 화면 %d (%s) · 변경 %d%s"
          % (len(diagnosis), len(plan["screens"]),
             ", ".join(sc["name"] for sc in plan["screens"]), len(plan["changes"]),
             (" / 대응하는 변경이 없는 진단: %s" % ", ".join(left)) if left else ""))
    return call, None


def wait_tokens(r, need):
    """추론형이면, 직전 응답 헤더의 남은 토큰이 이번 요청(need)보다 적을 때만
    모자란 만큼 기다린다. 기다린 초를 돌려준다 (안 기다렸으면 0).

    gpt-4o 는 보지 않는다 - 늘 60초를 기다리던 동작 그대로다 (config.DELAY)."""
    if not r.profile["reasoning"] or not r.last_ratelimit:
        return 0
    elapsed = time.monotonic() - r.last_ratelimit_at
    wait = wait_for_tokens(r.last_ratelimit, need, elapsed)
    if wait:
        r.log("대기 %ds — 남은 토큰 %s (직전 응답 헤더, %.0f초 전) 이 이번 요청 %d "
              "(예상 입력 + max_tokens) 보다 적다. 분당 한도 %s"
              % (wait, r.last_ratelimit.get("remaining_tokens"), elapsed, need,
                 r.last_ratelimit.get("limit_tokens")))
        time.sleep(wait)
    return wait


def ask_model(r, n, p, prompt, max_tokens, mock, stage, images=None):
    """모델에 한 번 묻는다. 진단·계획과 생성이 같은 길을 쓴다.

    보내기 전에 예상 토큰을 로그에 남긴다. 분당 한도는 입력에 max_tokens 를
    더해 세므로 그 합도 적는다 - 한도에 걸렸을 때 어느 호출이 얼마였는지를
    로그만 보고 알 수 있어야 한다.

    그림(images)이 있으면 그 수와 예상 토큰을 호출 기록에 남기고, 예상 입력에
    더한다 (model.describe_images). 한 호출의 그림이 config.IMAGE_WARN_COUNT 를
    넘으면 경고 한 줄을 쓴다 - 막지는 않는다.

    돌려주는 것은 (reply, outcome). reply 가 None 이면 이 시도가 모델 호출에서
    끝난 것이고 outcome 이 다음에 할 일이다."""
    images = images or []
    text_est, method = estimate_tokens(model_text(prompt, images), r.model)
    pics = describe_images(images, r.model)
    est = text_est + pics["estimated"]
    call = {"stage": stage, "estimated_prompt": est, "method": method,
            "max_tokens": max_tokens, "usage": None,
            "images": pics["count"], "estimated_images": pics["estimated"]}
    if images:
        call["image_method"] = pics["method"]
    r.calls.append(call)
    r.all_calls.append((n, call))
    r.log("tokens: %s 예상 입력 %d (%s%s) + max_tokens %d = 분당 한도 계산 %d"
          % (stage, est, method,
             " · 그림 %d장 %d토큰 %s" % (pics["count"], pics["estimated"], pics["method"])
             if images else "", max_tokens, est + max_tokens))
    if pics["count"] > config.IMAGE_WARN_COUNT:
        r.log("경고: %s 호출에 그림이 %d장이다 (config.IMAGE_WARN_COUNT %d 초과) — 그림만 "
              "예상 %d토큰" % (stage, pics["count"], config.IMAGE_WARN_COUNT,
                            pics["estimated"]))
    if r.args.mock:
        # mock 의 답은 모델 없이 만든 것이다. 재현 기록은 이 실행의 부르는 방식이
        # 보냈을 값으로 적는다 - 답이 들고 오는 상수(model.TEMPERATURE)가 아니라.
        reply = dict(mock(r.args.mock), **r.sent)
    else:
        waited = wait_tokens(r, est + max_tokens)
        if waited:
            call["waited_for_tokens"] = waited
        try:
            reply = call_model(r.model, prompt, max_tokens, r.log,
                               temperature=r.temperature, seed=r.seed,
                               reasoning_effort=r.reasoning_effort, api=r.api,
                               **({"images": images} if images else {}))
        except RateLimited as e:
            # 설계 실패가 아니다. 예산을 깎지 않고 여기서 멈춘다.
            r.log("중단: 인프라 한도 — 백오프를 다 쓰고도 429 (%s)" % e)
            r.summary["stopped_reason"] = "rate_limit"
            _dump(failure_report("INFRA", "인프라 한도로 중단: %s" % e), p + ".audit.json")
            r.summary["attempts"].append({"n": n, "stage": "rate_limit",
                                          "passed": False, "error": str(e),
                                          "calls": list(r.calls)})
            return None, STOP
        except ApiRejected as e:
            # 키·권한·요청 자체가 틀렸다. 다시 보내도 같은 답이 오므로, 여기서
            # 멈추지 않으면 예산과 무관하게 같은 실패만 반복된다.
            r.log("중단: API 가 요청을 거절했다 — 다시 보내도 같은 답이 온다 (%s)" % e)
            if images:
                # 그림을 빼고 다시 보내면 모델이 화면을 보지 않은 답이 "본 답" 으로
                # 기록된다. 조용히 바꾸지 않고 멈춘다.
                r.log("중단: 그림 %d장을 넣은 %s 요청이었다 — 그림을 빼고 다시 보내지 "
                      "않는다. 그림 없이 돌리려면 --see off · --refine 0. 이 모델이 그림을 "
                      "받는지는 --probe %s --image 로 먼저 본다"
                      % (len(images), stage, r.model))
            r.summary["stopped_reason"] = "api_rejected"
            _dump(failure_report("INFRA", "API 가 요청을 거절했다: %s" % e),
                  p + ".audit.json")
            r.summary["attempts"].append({"n": n, "stage": "api_rejected",
                                          "passed": False, "error": str(e),
                                          "calls": list(r.calls)})
            return None, STOP
        except InfraFailed as e:                     # 연결 실패·타임아웃·5xx
            # 설계 실패가 아니므로 형식·검사 예산은 건드리지 않는다. 대신 인프라
            # 예산을 쓴다 - 다시 될 수도 있지만 무한히 기다리지는 않는다.
            #
            # 오류 문구는 프롬프트로 가지 않는다 (r.last 를 그대로 둔다). 모델이
            # 고칠 수 있는 것이 아니고, 직전에 검사받은 빌드의 실패 목록을
            # API 오류로 덮으면 다음 시도가 고칠 것을 잃는다.
            #
            # 그 밖의 예외는 여기서 받지 않는다. 바깥 문제는 call_model 이 셋
            # (RateLimited · ApiRejected · InfraFailed)으로 갈라 올리므로, 그 밖의
            # 것은 도구의 버그다 - run() 이 실행을 멈추고 2 로 끝낸다 (D-6).
            kind = "InfraFailed"
            r.budget.spend("infra")
            r.log("model: 호출 실패 (인프라 %d/%d) — %s: %s"
                  % (r.budget.infra_used, r.budget.budget["infra"], kind, e))
            _dump(failure_report("INFRA", "모델 호출 실패: %s: %s" % (kind, e)),
                  p + ".audit.json")
            r.summary["attempts"].append({"n": n, "stage": "call", "passed": False,
                                          "error": "%s: %s" % (kind, e),
                                          "calls": list(r.calls)})
            if r.budget.out_of("infra"):
                r.log("인프라 재시도 예산 소진 (%d회) — 모델에 닿지 못했다"
                      % r.budget.infra_used)
                r.summary["stopped_reason"] = "infra_exhausted"
                return None, STOP
            return None, GO_ON
    call["usage"] = reply.get("usage")
    if images and (call["usage"] or {}).get("prompt") is not None:
        # 실측 입력에서 글의 어림을 뺀 것. 그림 토큰의 실측에 가장 가까운 값이다.
        call["measured_images"] = call["usage"]["prompt"] - text_est
        r.log("그림: %d장 — 실측 입력 %d − 글 어림 %d = %d (어림 %d)"
              % (pics["count"], call["usage"]["prompt"], text_est,
                 call["measured_images"], pics["estimated"]))
    if reply.get("dropped"):
        # 모델이 거절해 빼고 보낸 인자 (model.DROPPABLE). 그 인자는 이제 보내지 않는
        # 것이므로 실행 전체의 재현 기록에서도 지운다.
        call["dropped"] = list(reply["dropped"])
        for k in ("temperature", "seed"):
            if k in reply["dropped"]:
                r.sent[k] = None
                r.summary["repro"][k] = None
    if not r.args.mock:
        # 분당 한도는 모델·계정마다 다르다. 실제 호출이 받은 값을 남긴다.
        call["ratelimit"] = reply.get("ratelimit")
        if call["ratelimit"]:
            r.summary["ratelimit"] = call["ratelimit"]
            r.last_ratelimit, r.last_ratelimit_at = call["ratelimit"], time.monotonic()
        r.log("분당 한도 (%s 응답 헤더): %s" % (stage, describe_ratelimit(call["ratelimit"])))
    if reply.get("max_tokens") not in (None, max_tokens):
        # 분당 한도에 맞추느라 줄여서 보냈다 (model.shrink_for_minute)
        call["max_tokens_sent"] = reply["max_tokens"]
    if reply.get("model") and reply["model"] not in r.summary["response_models"]:
        r.summary["response_models"].append(reply["model"])
    if reply.get("model") or reply.get("system_fingerprint"):
        r.log("model: 응답 모델 %s (fingerprint %s)"
              % (reply.get("model"), reply.get("system_fingerprint")))
    return reply, None


def note_truncated(r, entry, phase):
    """답이 길이 제한에서 잘렸다. 일반 형식 실패와 따로 남긴다.

    잘린 답은 겉모양이 형식 실패와 같다 - 블록이 닫히지 않았으니 "블록이 없다"
    로 보인다. 그러나 원인은 내용이 아니라 길이 제한이고, 그 제한은 분당 한도에
    맞추느라 줄였을 수도 있다 (model.shrink_for_minute). 그래서 그때 실제로 보낸
    max_tokens 를 함께 적는다. 형식 예산은 그대로 쓴다 - 다시 물어야 하는 것은
    같다."""
    call = r.calls[-1] if r.calls else {}
    cap = call.get("max_tokens_sent", call.get("max_tokens"))
    entry.update(stage="truncated", phase=phase, truncated=True, max_tokens=cap)
    # 추론형은 생각 토큰도 같은 한도 안에서 쓴다. 생각이 한도를 거의 다 쓰면
    # 보이는 답이 비어 오는데, 그때 "짧게 써라" 는 안내는 도움이 되지 않는다 -
    # 한도를 늘리거나 생각에 쓸 노력을 낮춰야 한다. 그래서 그 몫을 함께 적는다.
    usage = call.get("usage") or {}
    thinking = ""
    if usage.get("reasoning"):
        entry["reasoning_tokens"] = usage["reasoning"]
        thinking = " — 그중 생각 토큰 %d / 출력 %s" % (usage["reasoning"],
                                                usage.get("completion"))
        if usage.get("completion") and usage["reasoning"] >= 0.9 * usage["completion"]:
            thinking += (" (생각이 한도를 거의 다 썼다 - --max-tokens 를 늘리거나 "
                         "--reasoning-effort 를 낮춘다)")
    r.log("잘림: %s 답이 max_tokens %s 에서 잘렸다 (finish_reason=length)%s — 형식 "
          "실패로 세고 다시 묻는다" % (phase, cap, thinking))


def request_reply(r, n, p, stage=None, mock=None):
    """계획을 넣은 프롬프트를 보내고 답을 받아 적는다.

    `stage` · `mock` 은 다듬기의 고치기 호출이 준다 - 토큰을 refine_fix 로 세고,
    mock 실행이면 다듬기 mock 의 고치기 답을 쓴다.

    돌려주는 것은 (reply, outcome). reply 가 None 이면 이 시도가 모델 호출에서
    끝난 것이고 outcome 이 다음에 할 일이다."""
    block = retry_block(r.last["report"], r.last["html"], r.last["flow_text"],
                        error=r.last_error, truncated=r.truncated) \
        if (r.last["report"] or r.last_error or r.truncated) else ""
    # 재시도에서는 코드보다 반성을 먼저 쓰게 한다. 그래서 실패 목록보다 앞이다.
    r.asked_reflection = bool(block)
    block = with_reflection(block)
    if block and stage == "refine_fix":
        block = REFINE_FIX_NOTE + "\n\n" + block
    prompt = build_prompt(r.template, r.model_original, block, r.choices, plan_text(r),
                          errors=errors_block(r.errors))
    io.open(p + ".prompt.txt", "w", encoding="utf-8", newline="\n").write(prompt)
    r.log("prompt: %d chars%s" % (len(prompt), " (with retry block)" if block else ""))

    reflect = r.asked_reflection
    reply, outcome = ask_model(r, n, p, prompt, r.caps["generate"],
                               mock or (lambda mode: mock_reply(mode, reflect=reflect)),
                               stage or ("retry" if reflect else "generate"))
    if reply is None:
        return None, outcome
    io.open(p + ".response.txt", "w", encoding="utf-8", newline="\n").write(reply["text"])
    r.log("model: %s chars, finish=%s, %ss, usage=%s"
          % (len(reply["text"]), reply["finish_reason"], reply["seconds"], reply["usage"]))
    return reply, None


def note_model_claims(r, entry, flow):
    """모델이 흐름 명세에 적은 판정 기준(truth · choices_removed · stage 등)을
    남긴다. 버리는 일은 판정 입력을 만드는 곳(audit.inputs.judged_flow)이 한다 -
    루프와 검사기 CLI 가 같은 함수를 거치므로, 여기서 따로 지우면 두 곳이 같은
    일을 하게 된다. 흐름 명세 파일은 모델이 쓴 그대로 남는다.

    조용히 넘어가지 않는다. 남기지 않으면 "모델이 적지 않았다" 와 "적었는데
    버렸다" 를 구분할 수 없고, 모델이 판정 기준을 고르려 했다는 것 자체가
    결과다. choices_removed 는 검사 I 를 피해 가는 장치였으므로 action 이름까지
    적는다 - 허용하는 제거는 flows/allowed_removals.json 에서만 읽는다.
    """
    claims = model_claims(flow, r.task["id"])
    if not claims:
        return
    entry["model_claims_dropped"] = claims
    if "choices_removed" in claims:
        spec = flow["choices_removed"]
        names = sorted(spec) if isinstance(spec, dict) else [str(spec)]
        entry["choices_removed_dropped"] = names
        r.log("flow: 모델이 쓴 choices_removed 를 판정에 쓰지 않는다 (%s). 허용하는 "
              "제거는 flows/allowed_removals.json 에서만 읽는다." % ", ".join(names))
    r.log("flow: 모델이 쓴 판정 기준 %s 는 판정에 쓰지 않는다 - 과제와 연구자 파일의 "
          "것으로 판정한다" % ", ".join(claims))


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
    if changes and entry.get("phase") == "refine_fix":
        # 다듬기 중에는 화면 구성을 바꾸지 않는다. 적용하지 않고 남긴다 - 바뀐
        # 화면으로 답했으면 아래 일치 검사가 형식 문제로 잡는다.
        entry["plan_changes"] = 0
        entry["plan_changes_ignored"] = len(changes)
        r.log("reflection: 다듬기의 고치기라 계획 변경 %d건을 적용하지 않았다 (화면 "
              "구성 고정)" % len(changes))
        return []
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
        note_model_claims(r, entry, flow)
        # 마지막 화면을 다른 이름으로 지어 놓고 완료 칸만 "done" 으로 적은 흐름.
        # done 화면이 없을 때만 받고, 받은 사실을 남긴다 (reply.accept_done_alias).
        alias = accept_done_alias(flow)
        if alias:
            entry["done_alias"] = alias
            r.log("flow: expect 의 'done' 을 마지막 화면 %r 의 칸으로 받았다 - 흐름 "
                  "명세에 done 화면이 없다" % alias)
        # 과제가 정한 오류 경로를 모두 적었는지, 완료 화면에서 과제의 값을
        # 확인하는지도 본다 (과제 파일 · 과제의 원본 흐름).
        problems = validate_flow(flow, html, r.errors, r.task["done_expect"])
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
            note_truncated(r, entry, "retry" if r.asked_reflection else "generate")
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
    problems = problems + preserved_problems(html, r.preserved, r.preserved_optional)
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

    report = _drive_audit(r, n, entry, build)
    # 펼치기(reveal) 규칙 위반은 흐름 명세의 형식 문제다 - 검사기가 걸어 봐야 알 수
    # 있어 검사 I 의 fatal 로 오지만, 형식 예산을 쓴다.
    violated = [f["detail"] for f in report.get("fatal") or [] if f.get("reveal_violation")]
    if violated:
        r.log("flow: reveal 규칙 위반 %d건: %s" % (len(violated), " | ".join(violated)[:300]))
        entry.update(stage="flow", passed=False, fatal=len(violated))
        r.budget.spend("format")
        return problems_report(violated)
    entry.update(stage="audit", passed=bool(report.get("passed")),
                 fatal=len(report.get("fatal", [])),
                 warning=len(report.get("warning", [])))
    if not report.get("passed"):
        r.budget.spend("audit")
    _note_audit(r, n, report)
    return report


def _drive_audit(r, n, entry, build):
    """브라우저를 띄워 한 번 걷는다.

    설계가 걷기를 막는 것(선택자가 없다 · 화면이 켜지지 않는다)은 걷기가 리포트에
    적는다 - 설계 실패다. 여기까지 올라오는 예외는 둘 중 하나다 (감사 D-6 (가)).

      바깥 문제   브라우저(Playwright)가 실패했거나 시간 안에 답하지 않았다. 인프라
                  예산 하나를 쓰고 **같은 빌드**를 다시 검사한다 - 모델과 무관하다.
                  예산을 다 쓰면 실행을 멈춘다 (infra_exhausted, 종료 2).
      도구 버그   그 밖의 예외. 잡지 않는다 - run() 이 멈추고 2 로 끝낸다. 전에는
                  "검사기가 흐름 명세를 실행하지 못했다" 로 모델에게 가고 검사 예산을
                  썼다 - 모델이 고칠 수 없는 것을 고치라고 했다.
    """
    rel = os.path.relpath(build["html_path"], ROOT).replace(os.sep, "/")
    shots = os.path.join(r.run_dir, "shots", "attempt_%d" % n)
    os.makedirs(shots, exist_ok=True)
    while True:
        try:
            return run_audit(r.orig_snapshot, r.original_html, build["html_path"],
                             build["flow_path"], url_for(rel), shots, r.args.stage,
                             original_url=r.original_url,
                             allowed_removals=r.allowed_removals,
                             task=r.task["id"],
                             **({"see": True} if r.refine > 0 else {}))
        except PlaywrightError as e:
            why = "%s: %s" % (type(e).__name__, one_line(str(e))[:300])
            r.budget.spend("infra")
            entry.setdefault("audit_infra_failures", []).append(why)
            r.log("audit: 브라우저 실패 (인프라 %d/%d) — %s"
                  % (r.budget.infra_used, r.budget.budget["infra"], why))
            if r.budget.out_of("infra"):
                r.log("인프라 재시도 예산 소진 (%d회) — 검사기를 돌리지 못했다"
                      % r.budget.infra_used)
                entry.update(stage="audit_infra", passed=False)
                r.summary["attempts"].append(entry)
                raise Stopped("infra_exhausted")
            r.log("audit: 같은 빌드를 다시 검사한다")


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


def attempt(r, n, stage=None, mock=None):
    """한 번의 시도. 돌려주는 것은 STOP 또는 GO_ON.

    `stage` · `mock` 은 다듬기의 고치기 시도가 준다 (refine_round)."""
    b = r.budget
    r.log("---- attempt %d (형식 %d/%d · 검사 %d/%d)"
          % (n, b.format_used, b.budget["format"], b.audit_used, b.budget["audit"]))
    p = os.path.join(r.run_dir, "attempt_%d" % n)
    r.calls = []

    plan_call = None
    if r.plan is None:
        plan_call, outcome = request_plan(r, n, p)
        if outcome is not None:
            return outcome
        # 두 호출이 같은 1분 안에 들어가면 분당 한도를 넘는다 - 원본 HTML 이
        # 두 프롬프트에 다 들어 있다.
        if r.delay and not r.args.mock:
            r.log("대기 %ss (진단·계획 → 생성)" % r.delay)
            time.sleep(r.delay)
    # 이 시도가 따른 계획. 재시도에서 계획이 바뀌면 시도마다 다른 파일이 된다.
    _dump(r.plan, p + ".plan.json")

    reply, outcome = request_reply(r, n, p, stage=stage, mock=mock)
    if reply is None:
        return outcome
    entry = {"n": n, "finish_reason": reply["finish_reason"], "usage": reply["usage"],
             "seconds": reply["seconds"], "repro": repro(r.template, reply),
             "plan": p + ".plan.json", "calls": r.calls}
    if plan_call:
        entry["plan_call"] = plan_call
    if stage:
        entry["phase"] = stage
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


def log_tokens(r):
    """단계별 토큰을 한 줄씩. 예상은 늘 있고, 실측은 API 가 알려 준 것만."""
    t = r.summary.get("tokens")
    if not t:
        return
    r.log("")
    r.log("토큰 (예상 입력 / 실측 입력 / 실측 출력 / 그중 생각, %s)" % t["method"])
    rows = [(k, v) for k, v in t["by_stage"].items()] + [("total", t["total"])]
    if t["first_attempt"]:
        rows.append(("첫 시도", t["first_attempt"]))
    for name, v in rows:
        r.log("  %-8s 호출 %d | %6d | %6s | %6s | %6s"
              % (name, v["calls"], v["estimated_prompt"],
                 "-" if v["prompt"] is None else v["prompt"],
                 "-" if v["completion"] is None else v["completion"],
                 "-" if v.get("reasoning") is None else v["reasoning"]))


# outputs/ 안에서 "지금 쓰는 것" 을 가리키는 이름들. 실행 이름이 붙은 사본은
# 같은 이름에 실행 폴더 이름이 하나 끼어든다 (%s). {task} 자리에는 과제가
# 들어간다 - 이체는 빈 글자라 이름이 전과 같고, 공과금은 _bill 이다
# (restructured_auto_bill.html). 과제를 넣지 않으면 두 과제를 번갈아 돌릴 때
# 나중 과제가 앞 과제의 "지금 쓰는 재구성본" 을 말없이 덮는다.
PROMOTED = [("html", "restructured_auto{task}%s.html"),
            ("flow", "restructured_auto{task}%s.flow.json"),
            ("audit", "audit_auto{task}%s.json"),
            # 이 빌드를 만든 진단과 계획. 승격된 산출물만 보는 사람도 "무엇을
            # 근거로 무엇을 바꿨는지" 를 같은 자리에서 찾을 수 있어야 한다.
            ("plan", "restructured_auto{task}%s.plan.json"),
            ("diagnosis", "restructured_auto{task}%s.diagnosis.json"),
            # 주입 전, 모델이 쓴 그대로. 승격된 산출물에는 도구가 넣은
            # 데이터 블록과 고친 선언이 들어 있으므로, 둘을 나란히 두지
            # 않으면 "모델이 만든 것" 을 되찾을 수 없다. 뽑을 데이터가
            # 없는 입력에서는 이 자리가 비고, 그때는 건너뛴다.
            ("model_html", "restructured_auto{task}%s.model.html")]

# 승격된 설명서의 이름. 다른 산출물과 같이 restructured_auto{task} 로 시작한다.
BRIEF = "designer_brief.md"
PROMOTED_BRIEF = "restructured_auto{task}%s.designer_brief.md"


def task_tag(task_id):
    """승격 이름에 끼우는 과제 표시. 기본 과제(이체)는 빈 글자다."""
    return "" if task_id == DEFAULT_TASK else "_" + task_id


def promoted_name(key, task_id, suffix=""):
    """그 과제의 승격 파일 이름. key 는 PROMOTED 의 칸이거나 "brief" 다.
    suffix 는 "" (지금 쓰는 것) 또는 "." + 실행 이름 (사본)."""
    pattern = PROMOTED_BRIEF if key == "brief" else dict(PROMOTED)[key]
    return pattern.format(task=task_tag(task_id)) % suffix


def copy_final(r):
    """통과한 빌드만 outputs/ 로 올린다. 사본은 실행 이름으로도 하나 남긴다.

    통과 여부와 무관하게 복사하던 것을 바꿨다. `restructured_auto.html` 은
    뷰어와 실험 조건이 "지금 쓰는 재구성본" 으로 읽는 이름인데, 떨어진 빌드가
    그 자리에 올라오면 마지막으로 통과한 빌드가 조용히 사라진다 - 떨어졌다는
    사실은 summary.json 에만 남고, 그 자리의 파일은 멀쩡해 보인다.

    실행 이름이 붙은 사본을 함께 두는 이유는 그 반대다. 통과한 실행이 둘 이상
    이면 나중 것이 앞의 것을 덮는데, 둘을 비교할 수 있어야 한다.

    이름은 과제마다 따로다 (promoted_name).
    """
    f = r.summary["final"]
    if not f:
        return
    tid = r.task["id"]
    if not r.summary.get("passed"):
        r.log("final: 통과한 빌드가 없다 — outputs/%s 는 그대로 둔다"
              % (promoted_name("html", tid).rsplit(".", 1)[0] + ".*"))
        return
    out, name = outputs_dir(bool(r.args.mock)), os.path.basename(r.run_dir)
    os.makedirs(out, exist_ok=True)
    promoted = []
    for key, _pattern in PROMOTED:
        if not f.get(key):
            continue
        shutil.copy2(f[key], os.path.join(out, promoted_name(key, tid)))
        shutil.copy2(f[key], os.path.join(out, promoted_name(key, tid, "." + name)))
        promoted.append(promoted_name(key, tid))
    r.log("final: attempt %d -> %s (+ .%s 사본)"
          % (f["attempt"], ", ".join(promoted), name))
    # 도구가 모델의 목록을 고쳤다면, 통과한 산출물이 모델이 쓴 그대로가
    # 아니다. 조용히 넘기면 연구에서 그 둘을 구분할 길이 없다.
    pres = f.get("preserved") or {}
    if pres.get("redeclared"):
        r.log("final: 주의 - 이 산출물은 모델이 쓴 그대로가 아니다. 도구가 "
              "%s 의 선언을 입력의 데이터로 바꿨다. 모델이 쓴 것은 %s 다."
              % (", ".join(pres["redeclared"]), promoted_name("model_html", tid)))
    if f.get("model_html"):
        f["model_html_promoted"] = os.path.join(out, promoted_name("model_html", tid))
    write_briefs(r, out, name)


def write_briefs(r, out, name):
    """통과한 빌드의 디자이너용 설명서 (brief.py). 실행 폴더에 하나, outputs/ 에
    하나(+ 실행 이름 사본). 링크가 설명서의 폴더 기준이므로 복사하지 않고 따로
    쓴다 - 같은 스크린샷을 가리키되 링크 글자가 다르다."""
    f = r.summary["final"]
    tid = r.task["id"]
    path = write_brief(r.summary, r.original_screens, os.path.join(r.run_dir, BRIEF),
                       errors=r.errors)
    if not path:
        r.log("final: 계획이 없어 설명서를 쓰지 않았다")
        return
    f["brief"] = path
    promoted = write_brief(r.summary, r.original_screens,
                           os.path.join(out, promoted_name("brief", tid)), errors=r.errors)
    shutil.copy2(promoted, os.path.join(out, promoted_name("brief", tid, "." + name)))
    f["brief_promoted"] = promoted
    r.log("final: 디자이너용 설명서 -> %s (+ %s)" % (path, promoted_name("brief", tid)))


# --------------------------------------------------------------------------- #
# 보고 다듬기
# --------------------------------------------------------------------------- #
def refine(r, n):
    """통과한 빌드를 그림으로 보여 주고 다듬게 한다. 최대 r.refine 회.

    한 회차는 다듬기 호출 하나와, 다듬은 빌드가 떨어졌을 때 고치기 호출 하나다.
    통과하면 그것이 새 최종이고 다음 회차는 그 빌드를 다듬는다. 고치기까지
    떨어지면 직전에 통과한 빌드를 최종으로 되돌리고 다듬기를 끝낸다 - 통과한
    결과를 잃지 않는다.

    예산은 형식 · 검사 예산과 따로다. 회차 안에서는 루프의 단계 함수를 그대로
    쓰되, 그 함수들이 쓰는 예산을 이 회차의 것으로 잠시 바꿔 끼운다 - 다듬기의
    실패가 생성 예산을 깎지도, 생성 예산이 다듬기를 막지도 않는다."""
    rf = r.summary["refine"]
    rf["final_from"] = "generate"
    rf["final_label"] = final_label(rf)
    if r.refine <= 0:
        r.log("다듬기: 꺼짐 (--refine 0)")
        return n
    main_budget = r.budget
    try:
        for k in range(1, r.refine + 1):
            if r.delay and not r.args.mock:
                time.sleep(r.delay)
            n, go_on = refine_round(r, k, n)
            if not go_on:
                break
    finally:
        r.budget = main_budget
    final = r.summary["final"] or {}
    rf["final_label"] = final_label(rf)
    r.log("다듬기: 끝 — 최종은 %s (시도 %s)%s"
          % (final_label(rf), final.get("attempt"),
             " · 되돌림: %s" % rf["reverted"]["reason"] if rf.get("reverted") else ""))
    return n


def final_label(rf):
    """설명서 맨 위 한 줄과 run.log 가 쓰는 "최종이 어디서 왔나"."""
    rounds = rf.get("rounds") or []
    if rf.get("final_from") == "refine":
        last = max((x for x in rounds if x.get("became_final")),
                   key=lambda x: x["round"], default=None)
        label = "다듬기 %s회차" % (last["round"] if last else "?")
    else:
        label = "생성"
    if rf.get("reverted"):
        label += " (다듬기 %s회차가 실패해 되돌림)" % rf["reverted"]["round"]
    return label


def _round_cost(r, attempts):
    calls = [c for m, c in r.all_calls if m in attempts]
    return {"tokens": _tally(calls) if calls else None,
            "usd": _add(cost_usd(c.get("usage"), price_for(r.model)) for c in calls)}


def refine_round(r, k, n):
    """다듬기 한 회차. `(마지막 시도 번호, 다음 회차로 가는가)`."""
    rf = r.summary["refine"]
    best = dict(r.summary["final"])
    best_n = best["attempt"]
    n += 1
    p = os.path.join(r.run_dir, "attempt_%d" % n)
    r.calls = []
    r.budget = Budget(1, 1, r.budget.budget["infra"])
    shots = os.path.join(r.run_dir, "shots", "attempt_%d" % best_n)
    images = see_images(shots, BUILD_LABELS, [e["id"] for e in r.errors])
    row = {"round": k, "attempt": n, "from_attempt": best_n, "images": len(images),
           "before_shots": os.path.join(shots, "see"), "after_shots": None,
           "critique": None, "issues": None, "keep": None, "done": None,
           "passed": None, "fix_attempt": None, "fix_passed": None,
           "became_final": False, "stopped": None}
    rf["rounds"].append(row)
    r.log("---- 다듬기 %d/%d (시도 %d — 시도 %d 의 빌드, 그림 %d장)"
          % (k, r.refine, n, best_n, len(images)))

    model_html = io.open(best.get("model_html") or best["html"], encoding="utf-8").read()
    flow_text = io.open(best["flow"], encoding="utf-8").read()
    prompt = build_refine_prompt(
        r.refine_template, model_html, flow_text, plan_text(r), r.choices,
        errors_block(r.errors),
        shots=shots_section(images, "지금 화면", BUILD_SHOTS_INTRO))
    io.open(p + ".refine_prompt.txt", "w", encoding="utf-8", newline="\n").write(
        prompt_record(prompt, images, r.model, base=r.run_dir))
    refine_mode = getattr(r.args, "mock_refine", None) or "done"
    reply, outcome = ask_model(
        r, n, p, prompt, r.caps["generate"],
        lambda mode: mock_refine_reply(refine_mode, mode, k), "refine", images=images)

    def finish(stopped, go_on):
        row["stopped"] = stopped
        # 이 회차의 형식 · 검사 실패. 생성 예산(summary.budget)과 섞지 않는다.
        row["format_failures"] = r.budget.format_used
        row["audit_failures"] = r.budget.audit_used
        rf["format_failures"] = rf.get("format_failures", 0) + r.budget.format_used
        rf["audit_failures"] = rf.get("audit_failures", 0) + r.budget.audit_used
        row.update(_round_cost(r, [x for x in (n, row.get("fix_attempt")) if x]))
        return (row.get("fix_attempt") or n), go_on

    if reply is None:
        r.log("다듬기 %d: 모델 호출에서 끝났다 — 최종은 그대로 (시도 %d)" % (k, best_n))
        return finish("call_failed", False)
    io.open(p + ".response.txt", "w", encoding="utf-8", newline="\n").write(reply["text"])
    critique, problems = parse_critique(reply["text"])
    if critique is not None:
        row["critique"] = p + ".critique.json"
        _dump(critique, row["critique"])
        row["issues"] = len(critique_issues(critique))
        row["keep"] = len(critique.get("keep") or []) \
            if isinstance(critique.get("keep"), list) else None
        row["done"] = critique.get("done") if isinstance(critique.get("done"), bool) \
            else None
        if problems:
            row["critique_problems"] = problems
        r.log("다듬기 %d: 비평 %s건 · keep %s · done=%s%s"
              % (k, row["issues"], row["keep"], row["done"],
                 (" (비평 모양 문제: %s)" % " | ".join(problems)[:200]) if problems else ""))
    else:
        r.log("다듬기 %d: 비평 블록이 없다" % k)
    if row["done"] is True and row["issues"] == 0:
        # 빌드가 없는 회차는 시도 목록(attempts)에 넣지 않는다 - 그 호출의 토큰은
        # 이 회차 기록과 tokens.by_stage.refine 에 남는다.
        r.log("다듬기 %d: 모델이 더 고칠 것이 없다고 했다 — 멈춘다" % k)
        return finish("done", False)

    # 다듬은 빌드. 생성 시도와 같은 단계 함수로 모양을 보고 검사한다.
    r.last = {"report": None, "html": model_html, "flow_text": flow_text}
    r.last_error, r.truncated, r.asked_reflection = None, 0, False
    entry = {"n": n, "phase": "refine", "finish_reason": reply["finish_reason"],
             "usage": reply["usage"], "seconds": reply["seconds"],
             "repro": repro(r.refine_template, reply), "plan": p + ".plan.json",
             "calls": r.calls, "critique": row["critique"]}
    _dump(r.plan, p + ".plan.json")
    build, _outcome = check_reply(r, p, entry, reply, n)
    passed = False
    if build is not None:
        report = audit_build(r, n, entry, build)
        record(r, n, p, entry, report, build)
        passed = bool(report.get("passed"))
        row["after_shots"] = os.path.join(r.run_dir, "shots", "attempt_%d" % n, "see")
    row["passed"] = passed
    if passed:
        return _refine_passed(r, k, n, row, critique, finish)

    # 떨어졌다. 보통 재시도 블록(반성 + 실패 목록)으로 한 번 고치게 한다.
    r.log("다듬기 %d: 다듬은 빌드가 떨어졌다 — 한 번 고치게 한다" % k)
    if r.delay and not r.args.mock:
        time.sleep(r.delay)
    fix_n = n + 1
    row["fix_attempt"] = fix_n
    r.calls = []
    attempt(r, fix_n, stage="refine_fix",
            mock=lambda mode: mock_refine_fix_reply(refine_mode, mode))
    fixed = (r.summary["final"] or {}).get("attempt") == fix_n and \
        bool(r.summary["attempts"] and r.summary["attempts"][-1].get("passed"))
    row["fix_passed"] = fixed
    if fixed:
        row["after_shots"] = os.path.join(r.run_dir, "shots", "attempt_%d" % fix_n, "see")
        return _refine_passed(r, k, fix_n, row, critique, finish)

    # 고치기도 떨어졌다. 직전에 통과한 빌드를 최종으로 되돌린다. final 은 그 빌드의
    # 기록 그대로다 - final.attempt 가 실제 최종 빌드를 가리켜야 고르기(잘림 판정 ·
    # 마지막 시도의 값)가 맞는 시도를 본다.
    r.summary["final"] = best
    r.summary["passed"] = True
    rf["reverted"] = {"round": k, "to_attempt": best_n,
                      "failed_attempts": [n, fix_n],
                      "reason": "다듬기 %d회차의 빌드(시도 %d)와 고친 빌드(시도 %d)가 "
                                "모두 검사를 통과하지 못했다" % (k, n, fix_n)}
    r.log("다듬기 %d: 고친 빌드도 떨어졌다 — 직전에 통과한 시도 %d 를 최종으로 되돌린다"
          % (k, best_n))
    return finish("reverted", False)


def _refine_passed(r, k, n, row, critique, finish):
    rf = r.summary["refine"]
    rf["final_from"] = "refine"
    rf["reverted"] = None
    row["became_final"] = True
    r.log("다듬기 %d: 통과 — 시도 %d 가 새 최종이다" % (k, n))
    if row["done"] is True:
        r.log("다듬기 %d: 모델이 이번 수정으로 끝났다고 했다 (done=true) — 멈춘다" % k)
        return finish("done_after_fix", False)
    return finish(None, True)


# --------------------------------------------------------------------------- #
# 종료 코드
# --------------------------------------------------------------------------- #
# 이 이유로 멈춘 실행은 "빌드가 떨어졌다" 가 아니라 "돌지 못했다" 다. 부르는
# 쪽은 둘을 구분해야 한다 - 떨어진 빌드는 다시 만들고, 돌지 못한 실행은 다시
# 만들 것이 없다. senior_ui.audit 의 종료 코드 규약과 같다 (docs/README.md).
CANNOT_RUN = {"rate_limit", "api_rejected", "infra_exhausted", "cannot_start",
              "internal_error"}


def exit_code(summary):
    """0 = 통과한 빌드가 있다, 1 = 전부 실패, 2 = 아예 돌지 못했다.

    도구가 버그로 멈췄으면(internal_error) 통과한 빌드가 있어도 2 다. 0 이면
    부르는 쪽은 그 실행이 끝까지 멀쩡히 돌았다고 믿는다 - 다듬기나 승격 도중에
    멈췄어도."""
    if summary.get("stopped_reason") == "internal_error":
        return 2
    if summary.get("passed"):
        return 0
    return 2 if summary.get("stopped_reason") in CANNOT_RUN else 1


def note_internal_error(r, e):
    """도구의 버그로 멈췄다. 역추적은 run.log 에, 종류와 문구는 summary 에 남긴다.
    설계 실패로 세지 않고(예산을 쓰지 않는다) 모델에게도 보내지 않는다."""
    r.log("내부 오류 — 도구의 버그로 실행을 멈춘다 (설계 실패로 세지 않는다):\n%s"
          % traceback.format_exc().rstrip())
    r.summary["stopped_reason"] = "internal_error"
    r.summary["error"] = "%s: %s" % (type(e).__name__, e)


def run(args):
    """한 실행 전체. 돌려주는 것이 프로세스의 종료 코드다 - exit_code 참고."""
    # 검사기는 빌드를 :3003 이 서빙하는 http:// 로 연다. 그 서버는 저장소
    # 루트만 서빙하므로, 산출물 폴더가 밖에 있으면 검사기가 빌드를 열지 못해
    # 첫 화면에서 멈춘다 - 그것이 설계 실패처럼 보인다.
    # mock 실행은 기본으로 .mock-outputs/ 에 쓴다 (config.outputs_dir).
    mock = bool(args.mock)
    if not inside_root(outputs_dir(mock)):
        print("cannot start: %s 가 저장소 루트 밖을 가리킨다 (%s). 검사기는 "
              ":3003 이 서빙하는 %s 안의 파일만 열 수 있다."
              % (OUTPUTS_ENV, outputs_dir(mock), ROOT), file=sys.stderr)
        return 2

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    # 실행 폴더 이름에 과제를 붙인다. 기본 과제(이체)는 전처럼 붙이지 않는다.
    task_name = getattr(args, "task", None) or DEFAULT_TASK
    run_dir = os.path.join(runs_dir(mock),
                           stamp + ("" if task_name == DEFAULT_TASK else "-" + task_name)
                           + ("-mock-" + args.mock if args.mock else ""))
    os.makedirs(run_dir, exist_ok=True)
    log = make_logger(os.path.join(run_dir, "run.log"))
    git = git_state()

    def cannot_start(why):
        """실행을 시작하지 못했다 (종료 2). Run 이 서기 전이라도 summary 를 남긴다 -
        남기지 않으면 그 실행 폴더에는 run.log 조각만 있다 (감사 B-16)."""
        log("cannot start: %s" % why)
        print("cannot start: %s" % why, file=sys.stderr)
        _dump({"run_dir": run_dir, "task": task_name, "passed": False, "attempts": [],
               "stopped_reason": "cannot_start", "error": str(why), "git": git},
              os.path.join(run_dir, "summary.json"))
        log("summary: %s" % os.path.join(run_dir, "summary.json"))
        return 2

    # mock 은 키가 필요 없고, .envs 에 적힌 모델 값이 mock 을 바꿔서도 안 된다
    # (model_choice). 그래서 읽지 않는다.
    if not mock:
        try:
            load_env()
        except RuntimeError as e:
            return cannot_start(e)
    # 첫 줄은 모델이다 - 어느 모델로 돌았는지가 run.log 를 여는 사람에게 가장 먼저
    # 보여야 한다. 모델은 .envs 의 환경 변수로도 정해지므로 키를 읽은 뒤에 고른다.
    # API 가 답한 실제 판 이름은 호출마다 "model: 응답 모델" 줄로, 실행 전체는
    # summary.json 의 response_models 로 남는다.
    #
    # 작업 트리가 깨끗하지 않으면 그 경고도 같은 첫 줄에 잇는다 - 그 사실 역시
    # run.log 를 여는 사람에게 가장 먼저 보여야 한다. 실행은 막지 않는다.
    model, source = model_choice(args)
    warning = dirty_warning(git)
    #
    # 추론형이면 보낸 reasoning_effort 와 그 출처도 첫 줄에 남긴다 - 모델과 같이
    # 결과를 가르는 조건이다 (effort_choice). gpt-4o 의 첫 줄은 전과 같다.
    profile = profile_for(model, getattr(args, "api", None))
    effort, effort_source = effort_choice(profile, args)
    # 검사 단계와 재시도 예산도 결과를 가르는 조건이다. 둘 다 기본값이 말없이
    # 바뀐 적이 있으므로(config.DEFAULT_STAGE · DEFAULT_BUDGET) 출처와 함께 첫
    # 줄에 둔다. 단계는 여기서 정해 args 에 적는다 - 검사기와 summary 가 그것을 읽는다.
    args.stage, args.stage_source = stage_choice(args)
    log("model=%s (출처 %s)%s — API 가 답한 판 이름은 호출마다 '응답 모델' 줄에 남는다"
        % (model, source,
           " · reasoning_effort=%s (출처 %s)" % (effort, effort_source) if effort else "")
        + " | " + describe_settings((args.stage, args.stage_source), budget_choice(args))
        + (" | " + warning if warning else ""))
    if mock:
        log(MOCK_ENV_NOTE % ", ".join(config.MODEL_ENV_VARS))
    if not profile["known"]:
        log("경고: 모르는 모델 %s — gpt-4o 처럼 부른다 (%s). 모델이 거절하는 인자는 "
            "빼고 다시 보낸다. 처음이면 --probe %s 로 먼저 확인한다"
            % (model, describe(profile), model))
    log("model: 부르는 방식 %s · 토큰 어림 %s · reasoning_effort %s"
        % (describe(profile), profile["encoding"], effort or "해당 없음"))
    caps = output_caps(profile, args)
    log("model: max_tokens 생성 %d (%s) · 진단·계획 %d (%s) · 호출 사이 대기 %gs%s"
        % (caps["generate"], "--max-tokens" if getattr(args, "max_tokens", None)
           else cap_source(profile),
           caps["plan"], "--plan-max-tokens" if getattr(args, "plan_max_tokens", None)
           else cap_source(profile),
           call_delay(profile, args),
           " + 남은 토큰이 모자라면 더" if profile["reasoning"] else ""))
    if not args.mock and not os.environ.get("OPENAI_API_KEY"):
        return cannot_start("no OPENAI_API_KEY in the environment or .envs")

    try:
        # 과제가 프롬프트의 과제 설명과 기본 원본을 정한다. 과제를 주지 않은
        # 실행(테스트가 손으로 만든 인자 포함)은 기본 과제다.
        task = load_task(getattr(args, "task", None) or DEFAULT_TASK)
        if not getattr(args, "original", None):
            args.original = abs_path(task["original"])
        # mock 은 한 과제의 빌드를 되읽는다. 다른 과제로 돌리면 결과에 뜻이 없다.
        if args.mock and MOCK_TASK.get(args.mock) != task["id"]:
            raise RuntimeError("--mock %s 는 %s 과제의 mock 이다 (지금 과제: %s)"
                               % (args.mock, MOCK_TASK.get(args.mock), task["id"]))
        template = load_template(task["id"])
        plan_template = load_plan_template(task["id"])
        refine_template = load_refine_template(task["id"])
        original_html = io.open(args.original, encoding="utf-8").read()
        orig_url = original_url(args.original)
        allowed = load_allowed_removals(task["id"])
    except (OSError, RuntimeError, ValueError) as e:
        return cannot_start(e)

    budget = budget_choice(args)
    log("run: %s | model=%s | 예산 형식 %d · 검사 %d | stage=%s | mock=%s | original=%s"
        % (run_dir, model, budget["format"][0], budget["audit"][0], args.stage,
           args.mock, orig_url)
        + ("" if task["id"] == DEFAULT_TASK else " | task=%s" % task["id"]))
    try:
        # 과제의 필수 오류 경로(required_errors)가 원본 흐름에 정의되지 않았으면
        # 여기서 멈춘다 - 과제 파일의 문제이고 실행을 시작할 수 없다.
        r = Run(args, log, run_dir, model, template, original_html, orig_url,
                plan_template=plan_template, task=task, model_source=source,
                refine_template=refine_template)
    except (OSError, RuntimeError, ValueError) as e:
        return cannot_start(e)
    r.summary["git"] = git
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
        # 과제의 원본 흐름으로 걷는다 - 다른 과제의 흐름으로 걸으면 첫 화면에서
        # 멈추고, 선택지 요약 · 지킬 데이터가 빈다.
        # 비교 기준으로만 쓰므로 원본의 오류 경로는 걷지 않는다 - 모델의 설계는
        # 원본과 화면이 다르고, 오류 경로는 생성물의 흐름으로 걷는다.
        #
        # 보기가 켜져 있으면(--see) 같은 걷기에서 원본 화면을 찍는다 - 진단·계획
        # 호출에 그림으로 들어간다. 오류 상태도 찍으려고 오류 경로까지 걷지만,
        # 그 결과는 스냅샷에서 떼어 둔다 - 비교 기준은 전과 같아야 한다.
        #
        # 원본 흐름을 읽지 못했거나 브라우저가 원본을 걷지 못했으면 비교 기준이
        # 없다 - 시작하지 못한 것이다 (종료 2). 전에는 역추적과 함께 종료 1(= 전부
        # 실패)이었다 (감사 B-16). 그 밖의 예외는 도구의 버그다 (아래 except).
        shots = os.path.join(run_dir, "shots", "original") if r.see else None
        try:
            base_flow = A.load_flow(None, task=task["id"])
            log("audit: driving the original once (baseline for contrast / language)")
            snap = asyncio.run(A.drive(r.original_url, base_flow, errors=r.see,
                                       want_shots=shots, see=r.see))
        except (PlaywrightError, OSError, ValueError) as e:
            why = "원본을 걷지 못했다: %s: %s" % (type(e).__name__, one_line(str(e)))
            log("cannot start: %s" % why)
            print("cannot start: %s" % why, file=sys.stderr)
            r.summary["stopped_reason"] = "cannot_start"
            r.summary["error"] = why
            return exit_code(r.summary)
        snap.pop("error_paths", None)
        r.orig_snapshot = snap
        r.original_images = see_images(shots, ORIGINAL_LABELS,
                                       [e["id"] for e in r.errors]) if r.see else []
        r.summary["see"]["original_images"] = len(r.original_images)
        if r.see:
            log("보기: 원본 그림 %d장 (%s)" % (len(r.original_images),
                                          os.path.relpath(shots, run_dir)))
        r.choices = choices_block(r.orig_snapshot, original_html,
                                  not_choices=task["not_choices"])
        if r.choices:
            log("선택지: %s" % " / ".join(
                l.strip() for l in r.choices.splitlines() if l.startswith("  ")))
        # 입력이 스크립트 배열로 그리는 선택지. 모델이 다시 타이핑하지 않도록
        # 도구가 들고 있다가 시도마다 재설계 HTML 에 넣는다.
        r.preserved = preserved_data(r.orig_snapshot, original_html)
        r.summary["preserved"] = {n: len(v) for n, v in r.preserved.items()}
        r.preserved_optional = optional_names(r.orig_snapshot, original_html,
                                              task["not_choices"])
        if r.preserved:
            log("지킬 데이터: %s%s" % (" / ".join(
                "%s %d개" % (n, len(v)) for n, v in r.preserved.items()),
                (" — 읽지 않아도 되는 것(선택지가 아닌 무리의 것): %s"
                 % ", ".join(r.preserved_optional)) if r.preserved_optional else ""))

        n = 0
        while True:
            n += 1
            if n > 1 and r.delay and not args.mock:
                time.sleep(r.delay)
            if attempt(r, n) is STOP:
                break
        if r.summary["passed"]:
            refine(r, n)

        if not r.summary["passed"]:
            log("통과 없음 — 형식 재시도 %d회 / 검사 재시도 %d회"
                % (r.budget.format_used, r.budget.audit_used))
            if r.summary["stopped_reason"] is None:
                r.summary["stopped_reason"] = "budget_exhausted"
        log_trend(r)
    except Stopped as e:
        # 설계와 무관한 이유로 멈췄다 (검사기의 인프라 예산 소진 등). 무엇 때문인지는
        # 멈춘 곳이 run.log 에 이미 적었다.
        r.summary["stopped_reason"] = e.reason
    except Exception as e:
        # 도구의 버그 (감사 D-6 (가)). 예산을 쓰는 실패로 바꾸지 않고 여기서 멈춘다.
        note_internal_error(r, e)
    finally:
        if server:
            server.terminate()
            log("server: stopped (pid %d)" % server.pid)
        # 요약은 이 실행의 기록이다. 루프가 터져도(흐름 명세가 검사기를 터뜨린다,
        # 사용자가 끊는다) 남아야 한다 - 밖에 두면 그런 실행은 run.log 조각
        # 말고는 아무것도 남기지 않는다.
        r.summary["budget"] = r.budget.as_dict()
        r.summary["tokens"] = tally_tokens(r)
        log_tokens(r)
        r.summary["cost"] = tally_cost(r)
        log_cost(r)
        copy_final(r)
        _dump(r.summary, os.path.join(run_dir, "summary.json"))
        log("summary: %s" % os.path.join(run_dir, "summary.json"))
    return exit_code(r.summary)
