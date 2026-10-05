r"""재구성 루프의 버그 재현 테스트. 브라우저도, API 도 쓰지 않는다.

`test_baseline.py` 는 "지금 나오는 값" 을 못박는다 - 그래서 값이 틀렸을 때도
통과한다. 이 파일은 반대로 **무엇이 맞는 동작인지** 를 적는다. 버그 하나에
테스트 하나 이상이고, 각 테스트는 그 버그를 고치기 전에 실패한다.

모델은 절대 부르지 않는다. 두 가지로만 재현한다.

  - `loop.call_model` 을 바꿔 끼운다 (호출 실패·잘린 답 등)
  - `--mock` 이 읽는 것과 같은 답 문자열을 손으로 만든다

브라우저도 띄우지 않는다. `fake_run_env` 가 `ensure_server` · `A.drive` ·
`run_audit` 를 바꿔 끼워서, `loop.run()` 전체를 서버 없이 한 번 돌릴 수 있게
한다 - 루프가 실제로 끝나는지, 종료 코드가 무엇인지는 그렇게만 확인된다.
"""
import argparse
import io
import json
import os

import pytest

import _api

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

loop = _api.loop_module
model = _api.model_module


# --------------------------------------------------------------------- #
# 루프를 서버 없이 돌리기
# --------------------------------------------------------------------- #
def make_args(out_root, **kw):
    """`senior_ui.restructure.__main__` 이 만드는 것과 같은 모양의 args."""
    d = dict(attempts=2, format_attempts=None, audit_attempts=None,
             infra_attempts=3, model="test-model", max_tokens=1000, mock=None,
             temperature=0.0, seed=20260101,
             original=os.path.join(ROOT, "inputs", "original_transfer.html"),
             stage="styled", delay=0)
    d.update(kw)
    return argparse.Namespace(**d)


def make_run(out_root, **kw):
    """단계 함수 하나만 보는 테스트용 Run. 로그는 리스트에 쌓인다."""
    args = make_args(out_root, **kw)
    run_dir = str(out_root)
    lines = []
    r = loop.Run(args, lines.append, run_dir, "test-model", "TEMPLATE", "<html></html>")
    r.log_lines = lines
    return r


FAKE_SNAPSHOT = {"screens": {}, "reached": [], "dialogs": [], "js_errors": [],
                 "js_error_details": [], "missing_ids": [], "state_pairs": [],
                 "undefined_classes": [], "notes": [], "load_failed": None}


def passing_report():
    return {"passed": True, "fatal": [], "warning": [],
            "metrics": {"flow": "auto", "fatal_total": 0, "fatal_root": 0,
                        "fatal_derived": 0, "screens_reached": 1,
                        "screens_expected": 1, "stopped_at": None}}


@pytest.fixture
def out_root(request):
    """테스트가 쓰는 산출물 폴더. 저장소 루트 **아래** 에 둔다.

    검사기는 빌드를 :3003 이 서빙하는 http:// 로 열고 그 서버는 ROOT 만
    서빙하므로, 산출물이 밖에 있으면 실제 실행에서는 빌드를 열지 못한다.
    tmp_path 를 쓰면 그 사실이 테스트에서 드러나지 않는다.
    """
    import shutil
    d = os.path.join(ROOT, ".pytest-outputs", request.node.name[:60])
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def fake_run_env(monkeypatch, out_root):
    """`loop.run()` 을 서버·브라우저 없이 돌린다.

    바꿔 끼우는 것은 바깥 세계뿐이다 - 서버 띄우기, 원본을 한 번 걷기, 검사기
    호출. 루프 자신의 판단(예산·중단·종료 코드)은 그대로 돈다.
    """
    async def fake_drive(url, flow, want_shots=None):
        return dict(FAKE_SNAPSHOT)

    monkeypatch.setenv("SENIOR_UI_OUTPUTS", out_root)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-used")
    monkeypatch.setattr(loop, "ensure_server", lambda log: None)
    monkeypatch.setattr(loop.A, "drive", fake_drive)
    monkeypatch.setattr(loop.A, "load_flow", lambda p: {"name": "original", "steps": []})
    monkeypatch.setattr(loop, "choices_block", lambda snap, html: "")
    monkeypatch.setattr(loop, "load_template", lambda: "TEMPLATE {{ORIGINAL_HTML}} "
                                                       "{{RETRY_BLOCK}} {{CHOICES}}")
    monkeypatch.setattr(loop, "load_plan_template", lambda: PLAN_TEMPLATE)
    monkeypatch.setattr(loop, "run_audit",
                        lambda *a, **kw: passing_report())
    return monkeypatch


def run_dirs(out_root):
    """이 실행이 만든 실행 폴더들, 오래된 것부터."""
    d = os.path.join(out_root, "restructure_auto")
    return [os.path.join(d, n) for n in sorted(os.listdir(d))]


# 진단·계획 프롬프트의 대역. 이것으로 시작하는 프롬프트가 진단·계획 호출이다.
PLAN_TEMPLATE = ("PLAN_TEMPLATE {{ORIGINAL_HTML}} {{RETRY_BLOCK}} {{CHOICES}} "
                 "{{ORIGINAL_SCREENS}}")


def is_plan_prompt(prompt):
    return prompt.startswith("PLAN_TEMPLATE")


def run_loop(monkeypatch, out_root, call_model, plan_reply=None, **kw):
    """`call_model` 을 바꿔 끼우고 루프를 한 번 돌린다. (종료 코드, summary).

    진단·계획 호출에는 GOOD_PLAN_REPLY 로 답한다 - 이 파일의 테스트 대부분은
    생성 단계를 보고, 그 앞에 계획이 서 있기만 하면 된다. 진단·계획 호출까지
    `call_model` 이 받게 하려면 plan_reply=False 를 준다."""
    if plan_reply is False:
        fake = call_model
    else:
        text = plan_reply or GOOD_PLAN_REPLY

        def fake(model_, prompt, *a, **k):
            if is_plan_prompt(prompt):
                return {"text": text, "finish_reason": "stop", "seconds": 0.0,
                        "usage": None}
            return call_model(model_, prompt, *a, **k)
    monkeypatch.setattr(loop, "call_model", fake)
    code = loop.run(make_args(out_root, **kw))
    last = run_dirs(out_root)[-1]
    summary = json.load(io.open(os.path.join(last, "summary.json"),
                                encoding="utf-8"))
    return code, summary


# --------------------------------------------------------------------- #
# 재현에 쓰는 모델 답
# --------------------------------------------------------------------- #
def reply_text(html, flow):
    return "```html\n%s\n```\n\n```json\n%s\n```\n" % (
        html, json.dumps(flow, ensure_ascii=False, indent=2))


GOOD_HTML = """<html><body>
<div data-screen="start"><button data-action="go" id="phone">보내기</button></div>
<div data-screen="done"><span id="dn-amt">10,000</span></div>
<script>
function onClick(el){ const a = el.dataset.action; if (a === 'go') {} }
</script>
</body></html>"""

GOOD_FLOW = {"name": "auto", "required_ids": ["phone", "dn-amt"],
             "steps": [{"screen": "start"},
                       {"screen": "done", "click": "[data-action='go']"}],
             "expect": {"done": [["#dn-amt", "{AMOUNT_SHOWN}"]]}}

GOOD_REPLY = reply_text(GOOD_HTML, GOOD_FLOW)

# GOOD_HTML 에 맞는 진단·계획. from 은 실제 원본(inputs/original_transfer.html)
# 의 화면 이름이다 - 루프는 --original 의 파일을 읽는다.
GOOD_DIAGNOSIS = [{"id": "D1", "screen": "home", "element": "이체 버튼",
                   "problem": "작아서 못 찾는다", "evidence": "카드 안의 작은 버튼"}]
GOOD_PLAN = {"screens": [{"name": "start", "purpose": "시작", "from": ["home"]},
                         {"name": "done", "purpose": "끝", "from": ["done"]}],
             "changes": [{"id": "C1", "what": "버튼을 키운다", "why": "찾게",
                          "addresses": ["D1"], "from_screens": ["home"],
                          "to_screens": ["start"]}]}
GOOD_PLAN_REPLY = "```json\n%s\n```\n" % json.dumps(
    {"diagnosis": GOOD_DIAGNOSIS, "plan": GOOD_PLAN}, ensure_ascii=False)


def always_reply(*a, **kw):
    return {"text": GOOD_REPLY, "finish_reason": "stop", "seconds": 0.0,
            "usage": None}


# ===================================================================== #
# 1. 429 가 아닌 모델 호출 실패
# ===================================================================== #
def test_rejected_key_stops_the_loop(fake_run_env, out_root):
    """인증 오류는 다시 보내도 같은 답이 온다. 첫 실패에서 멈춰야 한다.

    고치기 전: 예산을 쓰지 않고 다음 시도로 넘어갔다 - 키가 틀리면 루프가
    끝나지 않았다.
    """
    calls = []

    def boom(*a, **kw):
        calls.append(1)
        raise model.ApiRejected("AuthenticationError: invalid api key")

    code, summary = run_loop(fake_run_env, out_root, boom, attempts=5)
    assert len(calls) == 1
    assert summary["stopped_reason"] == "api_rejected"
    assert code == 2


def test_rejected_key_does_not_spend_the_retry_budget(fake_run_env, out_root):
    """설계 실패가 아니므로 형식·검사 예산은 그대로 남아야 한다."""
    def boom(*a, **kw):
        raise model.ApiRejected("BadRequestError: model not found")

    _code, summary = run_loop(fake_run_env, out_root, boom, attempts=5)
    assert summary["budget"]["format_used"] == 0
    assert summary["budget"]["audit_used"] == 0


def test_network_errors_spend_the_infra_budget(fake_run_env, out_root):
    """네트워크 오류는 다음에 될 수 있다 - 다시 시도하되 끝은 있어야 한다."""
    calls = []

    def boom(*a, **kw):
        calls.append(1)
        raise model.InfraFailed("APIConnectionError: connection reset")

    code, summary = run_loop(fake_run_env, out_root, boom,
                             attempts=10, infra_attempts=3)
    assert len(calls) == 3
    assert summary["budget"]["infra_used"] == 3
    assert summary["stopped_reason"] == "infra_exhausted"
    assert code == 2
    # 설계 실패가 아니므로 다른 두 예산은 건드리지 않는다
    assert summary["budget"]["format_used"] == 0
    assert summary["budget"]["audit_used"] == 0


def test_api_error_text_never_reaches_the_prompt(fake_run_env, out_root):
    """API 오류 문구는 모델이 고칠 수 있는 것이 아니다. 프롬프트에 넣지 않는다.

    고치기 전: 호출 실패 리포트를 `prev` 에 넣어서, 다음 프롬프트의 재시도
    블록에 "모델 호출 실패: Connection reset" 이 그대로 실렸다.
    """
    state = {"n": 0}
    secret = "APIConnectionError: proxy 10.0.0.1 refused"

    def flaky(_model, _prompt, _max_tokens, _log=None, **kw):
        state["n"] += 1
        if state["n"] == 1:
            raise model.InfraFailed(secret)
        return {"text": GOOD_REPLY, "finish_reason": "stop", "seconds": 0.0,
                "usage": None}

    _code, _summary = run_loop(fake_run_env, out_root, flaky,
                               attempts=3, infra_attempts=3)
    prompts = prompts_of(out_root)
    assert len(prompts) == 2
    assert all(secret not in p for p in prompts)
    assert all("APIConnectionError" not in p for p in prompts)


# ===================================================================== #
# 5. 산출물 덮어쓰기
# ===================================================================== #
def failing_report():
    return {"passed": False,
            "fatal": [{"check": "A", "screen": "done", "detail": "금액이 틀렸다"}],
            "warning": [],
            "metrics": {"flow": "auto", "fatal_total": 1, "fatal_root": 1,
                        "fatal_derived": 0, "screens_reached": 1,
                        "screens_expected": 2, "stopped_at": "done"}}


def seed_promoted(out_root):
    """직전에 통과했던 빌드가 이미 자리에 있는 상태를 만든다."""
    import pathlib
    out = pathlib.Path(out_root)
    (out / "restructured_auto.html").write_text("KEEP ME", encoding="utf-8")
    return out


def test_a_failed_build_does_not_overwrite_the_promoted_copy(fake_run_env, out_root):
    """`restructured_auto.html` 은 "지금 쓰는 재구성본" 이다. 떨어진 빌드가 그
    자리에 올라오면 마지막으로 통과한 빌드가 조용히 사라진다 - 떨어졌다는 사실은
    summary.json 에만 남고 그 자리의 파일은 멀쩡해 보인다.

    고치기 전: 통과 여부와 무관하게 마지막 빌드를 복사했다.
    """
    out = seed_promoted(out_root)
    fake_run_env.setattr(loop, "run_audit", lambda *a, **kw: failing_report())

    code, summary = run_loop(fake_run_env, out_root, always_reply, attempts=1)
    assert summary["passed"] is False
    assert code == 1
    assert (out / "restructured_auto.html").read_text(encoding="utf-8") == "KEEP ME"


def test_a_passing_build_is_promoted(fake_run_env, out_root):
    out = seed_promoted(out_root)
    _code, summary = run_loop(fake_run_env, out_root, always_reply, attempts=1)
    assert summary["passed"] is True
    assert (out / "restructured_auto.html").read_text(encoding="utf-8") != "KEEP ME"
    assert (out / "restructured_auto.flow.json").exists()
    assert (out / "audit_auto.json").exists()


def test_a_passing_build_also_leaves_a_copy_named_after_the_run(fake_run_env, out_root):
    """통과한 실행이 둘이면 나중 것이 앞의 것을 덮는다. 비교할 수 있어야 한다."""
    out = seed_promoted(out_root)
    _code, summary = run_loop(fake_run_env, out_root, always_reply, attempts=1)
    name = os.path.basename(summary["run_dir"])
    assert (out / ("restructured_auto.%s.html" % name)).exists()
    assert (out / ("restructured_auto.%s.flow.json" % name)).exists()
    assert (out / ("audit_auto.%s.json" % name)).exists()


def test_the_run_writes_nothing_into_the_real_outputs_dir(fake_run_env, out_root):
    """테스트가 실제 outputs/ 를 mock 결과로 덮어쓰면 안 된다.

    고치기 전: OUTPUTS_DIR 이 상수여서 환경 변수로 옮길 수 없었고, 루프를 돌리는
    테스트는 돌 때마다 실제 `outputs/restructured_auto.*` 를 mock 결과로 바꿨다.
    """
    real = os.path.join(ROOT, "outputs")
    before = {n: os.path.getmtime(os.path.join(real, n))
              for n in os.listdir(real)} if os.path.isdir(real) else {}

    _code, summary = run_loop(fake_run_env, out_root, always_reply, attempts=1)
    assert summary["run_dir"].startswith(out_root)

    after = {n: os.path.getmtime(os.path.join(real, n))
             for n in os.listdir(real)} if os.path.isdir(real) else {}
    assert after == before


# ===================================================================== #
# 2. 재시도 상태
# ===================================================================== #
BAD_REPLY = "코드 블록 없이 설명만 적은 답"


def replies(*texts, finish="stop"):
    """정해진 순서대로 답을 내놓는 call_model 대역."""
    seq = list(texts)

    def call(*a, **kw):
        text = seq.pop(0) if len(seq) > 1 else seq[0]
        reason = finish if isinstance(finish, str) else finish[0]
        return {"text": text, "finish_reason": reason, "seconds": 0.0, "usage": None}
    return call


def prompts_of(out_root):
    import glob
    last = run_dirs(out_root)[-1]
    return [io.open(p, encoding="utf-8").read()
            for p in sorted(glob.glob(os.path.join(last, "attempt_*.prompt.txt")))]


def test_parse_failure_keeps_the_last_audited_findings(fake_run_env, out_root):
    """파싱이 실패한 시도는 검사받은 적이 없다. 검사 결과는 그 전 시도의 것이다.

    고치기 전: 직전 HTML 은 그대로 두면서 그 HTML 의 검사 결과는 파싱 실패
    리포트로 덮었다. 재시도 프롬프트가 HTML 과 어긋난 실패 목록을 보게 된다 -
    "이 HTML 을 고쳐라" 고 하면서 그 HTML 에서 나오지 않은 실패를 붙인 셈이다.
    """
    fake_run_env.setattr(loop, "run_audit", lambda *a, **kw: failing_report())
    call = replies(GOOD_REPLY, BAD_REPLY, GOOD_REPLY)

    _code, _summary = run_loop(fake_run_env, out_root, call, attempts=3)
    third = prompts_of(out_root)[2]
    # 2번 시도의 파싱 실패와, 1번 시도에서 실제로 검사받은 실패가 둘 다 있어야
    # 한다 - 한쪽이 다른 쪽을 덮으면 안 된다.
    assert "```html 코드 블록이 없다" in third
    assert "금액이 틀렸다" in third


def test_parse_failure_carries_the_html_that_was_audited(fake_run_env, out_root):
    """프롬프트에 실리는 HTML 과 흐름 명세는 그 실패 목록을 낸 바로 그 빌드다."""
    fake_run_env.setattr(loop, "run_audit", lambda *a, **kw: failing_report())
    call = replies(GOOD_REPLY, BAD_REPLY, GOOD_REPLY)

    _code, _summary = run_loop(fake_run_env, out_root, call, attempts=3)
    third = prompts_of(out_root)[2]
    assert "data-screen=\"start\"" in third      # 직전에 검사받은 HTML
    assert "\"required_ids\"" in third            # 그 HTML 과 짝인 흐름 명세


def test_a_truncated_answer_is_called_out_on_the_retry(fake_run_env, out_root):
    """길이 제한에 잘린 답은 "짧게 써라" 가 아니라 "잘렸다" 를 알려야 한다.

    고치기 전: 잘린 답도 보통의 파싱 실패와 같은 한 줄로 들어갔고, 같은 길이의
    답이 다시 와서 같은 자리에서 또 잘렸다.
    """
    call = replies("```html\n<html>여기서 잘림", finish="length")

    _code, summary = run_loop(fake_run_env, out_root, call, attempts=3)
    second = prompts_of(out_root)[1]
    assert "finish_reason=length" in second
    assert "[잘린 답]" in second
    assert summary["attempts"][0]["truncated"] is True


def test_the_truncation_notice_counts_how_many_times_it_happened(fake_run_env, out_root):
    """두 번째로 잘리면 그 사실이 보여야 한다 - 같은 지시를 반복해도 소용없다."""
    call = replies("```html\n<html>여기서 잘림", finish="length")

    _code, _summary = run_loop(fake_run_env, out_root, call, attempts=3)
    third = prompts_of(out_root)[2]
    assert "2번 연속" in third


# ===================================================================== #
# 3. 흐름 명세의 타입 검사
# ===================================================================== #
def test_a_flow_that_is_an_array_is_a_flow_problem(fake_run_env, out_root):
    """흐름 명세가 배열이면 FLOW 문제다. 루프가 멈추는 일이 되면 안 된다.

    고치기 전: `flow.setdefault("name", "auto")` 가 AttributeError 로 터졌고,
    그 예외는 ValueError 가 아니어서 아무도 받지 못했다 - 루프 전체가 역추적만
    남기고 죽었다.
    """
    call = replies(reply_text(GOOD_HTML, [{"screen": "start"}]))

    code, summary = run_loop(fake_run_env, out_root, call, attempts=1)
    assert summary["attempts"][0]["stage"] == "flow"
    assert code == 1
    report = json.load(io.open(os.path.join(summary["run_dir"],
                                            "attempt_1.audit.json"), encoding="utf-8"))
    assert [f["check"] for f in report["fatal"]] == ["FLOW"]


def test_a_list_valued_screen_is_a_flow_problem(fake_run_env, out_root):
    """screen 이 목록이면 FLOW 문제다.

    고치기 전: `st["screen"] not in screens` 가 집합에 목록을 넣어
    TypeError: unhashable type 으로 터졌다 - 역시 아무도 받지 못했다.
    """
    flow = json.loads(json.dumps(GOOD_FLOW))
    flow["steps"][1]["screen"] = ["done", "start"]
    call = replies(reply_text(GOOD_HTML, flow))

    code, summary = run_loop(fake_run_env, out_root, call, attempts=1)
    assert summary["attempts"][0]["stage"] == "flow"
    assert code == 1


def test_a_step_that_is_not_an_object_is_a_flow_problem(fake_run_env, out_root):
    flow = json.loads(json.dumps(GOOD_FLOW))
    flow["steps"][1] = "done"
    call = replies(reply_text(GOOD_HTML, flow))

    _code, summary = run_loop(fake_run_env, out_root, call, attempts=1)
    assert summary["attempts"][0]["stage"] == "flow"


def test_shape_problems_are_phrased_for_the_model(fake_run_env, out_root):
    """FLOW 문제는 다음 프롬프트로 간다. 모델이 읽고 고칠 수 있는 글이어야 한다."""
    call = replies(reply_text(GOOD_HTML, [{"screen": "start"}]),
                   reply_text(GOOD_HTML, GOOD_FLOW))

    _code, _summary = run_loop(fake_run_env, out_root, call, attempts=2)
    second = prompts_of(out_root)[1]
    assert "객체" in second


def test_summary_is_written_even_when_the_loop_dies(fake_run_env, out_root):
    """요약은 실행의 기록이다. 루프가 터져도 남아야 한다.

    고치기 전: summary.json 을 try/finally 밖에서 썼다. 루프 안에서 예외가
    나면 그 실행은 run.log 조각만 남기고 아무 기록도 남기지 않았다.
    """
    def explode(*a, **kw):
        raise KeyboardInterrupt("사용자가 끊었다")

    with pytest.raises(KeyboardInterrupt):
        run_loop(fake_run_env, out_root, explode, attempts=1)
    assert os.path.exists(os.path.join(run_dirs(out_root)[-1], "summary.json"))


# ===================================================================== #
# 4. 재현 기록
# ===================================================================== #
def recording_reply(seen):
    """call_model 이 실제로 받은 인자를 적어 두는 대역."""
    def call(model_name, prompt, max_tokens, log=None, **kw):
        seen.append(dict(kw, model=model_name))
        return {"text": GOOD_REPLY, "finish_reason": "stop", "seconds": 0.0,
                "usage": None, "model": "gpt-4o-2026-01-01",
                "system_fingerprint": "fp_abc123",
                "temperature": kw.get("temperature"), "seed": kw.get("seed")}
    return call


REPRO_KEYS = ["temperature", "seed", "response_model", "system_fingerprint",
              "openai_sdk", "prompt_template_sha256"]


def test_temperature_and_seed_are_set_not_left_to_the_default(fake_run_env, out_root):
    """지정하지 않으면 공급자의 기본값이 쓰이고, 그 값은 기록에 남지 않는다."""
    seen = []
    _code, _summary = run_loop(fake_run_env, out_root, recording_reply(seen),
                               attempts=1)
    assert seen[0]["temperature"] is not None
    assert seen[0]["seed"] is not None


def test_every_attempt_records_what_it_would_take_to_repeat_it(fake_run_env, out_root):
    """시도 하나를 다시 돌리려면 무엇이 필요한가 - 그것이 시도 기록에 있어야 한다.

    고치기 전: 기록은 finish_reason · usage · seconds 뿐이었다. 같은 프롬프트를
    같은 모델에 보내도 다른 답이 나오는 이유(temperature·seed·실제 응답 모델·
    system_fingerprint)는 아무 데도 남지 않았다.
    """
    _code, summary = run_loop(fake_run_env, out_root, recording_reply([]),
                              attempts=1)
    repro = summary["attempts"][0]["repro"]
    assert sorted(repro) == sorted(REPRO_KEYS)
    assert repro["response_model"] == "gpt-4o-2026-01-01"
    assert repro["system_fingerprint"] == "fp_abc123"
    assert repro["openai_sdk"]


def test_the_summary_records_it_once_for_the_run(fake_run_env, out_root):
    _code, summary = run_loop(fake_run_env, out_root, recording_reply([]),
                              attempts=1)
    assert sorted(summary["repro"]) == sorted(REPRO_KEYS)
    assert summary["repro"]["response_model"] is None    # 실행 자체는 모델이 없다


def test_the_prompt_template_is_fingerprinted(fake_run_env, out_root):
    """템플릿이 바뀌면 같은 입력도 다른 답을 낸다. 어느 템플릿이었는지 남긴다."""
    import hashlib
    fake_run_env.setattr(loop, "load_template", lambda: "바뀐 템플릿")
    _code, summary = run_loop(fake_run_env, out_root, recording_reply([]),
                              attempts=1)
    want = hashlib.sha256("바뀐 템플릿".encode("utf-8")).hexdigest()
    assert summary["repro"]["prompt_template_sha256"] == want
    assert summary["attempts"][0]["repro"]["prompt_template_sha256"] == want


# ===================================================================== #
# 6. --original 은 비교용 원본 실행에도 쓰인다
# ===================================================================== #
@pytest.fixture
def driven_urls(fake_run_env, monkeypatch):
    """원본을 걸을 때 쓴 URL 을 적어 둔다. fake_run_env 의 drive 를 덮는다."""
    seen = []

    async def fake_drive(url, flow, want_shots=None):
        seen.append(url)
        return dict(FAKE_SNAPSHOT)

    monkeypatch.setattr(loop.A, "drive", fake_drive)
    return seen


def test_the_default_original_is_the_one_the_comparison_walks(driven_urls, monkeypatch,
                                                              out_root):
    _code, _summary = run_loop(monkeypatch, out_root, always_reply, attempts=1)
    assert driven_urls[0].endswith("/inputs/original_transfer.html")


def test_original_flag_moves_the_comparison_run_too(driven_urls, monkeypatch, out_root):
    """--original 로 다른 원본을 주면 비교 기준도 그 파일이어야 한다.

    고치기 전: 프롬프트에 넣는 HTML 만 그 파일에서 읽고, 브라우저로 걷는 것은
    config.ORIGINAL_URL 로 못박혀 있었다. 대비·언어 검사의 기준이 프롬프트에
    넣은 원본과 다른 문서가 된다 - 아무 경고 없이.
    """
    other = os.path.join(ROOT, "results", "restructured_transfer.html")
    _code, _summary = run_loop(monkeypatch, out_root, always_reply, attempts=1,
                               original=other)
    assert driven_urls[0].endswith("/results/restructured_transfer.html")


def test_the_audit_compares_against_the_same_original(driven_urls, monkeypatch,
                                                      out_root):
    """검사 리포트의 inputs.original 도 같은 URL 이어야 한다."""
    seen = {}

    def spy(orig_snapshot, orig_html, html_path, flow_path, url, shots, stage,
            original_url=None, allowed_removals=None):
        seen["url"] = original_url
        return passing_report()

    monkeypatch.setattr(loop, "run_audit", spy)
    other = os.path.join(ROOT, "results", "restructured_transfer.html")
    # 계획의 from 은 그 원본의 화면 이름이어야 한다 - 다른 원본이면 이름도 다르다.
    plan = GOOD_PLAN_REPLY.replace('"home"', '"start"')
    run_loop(monkeypatch, out_root, always_reply, attempts=1, original=other,
             plan_reply=plan)
    assert seen["url"].endswith("/results/restructured_transfer.html")


def test_an_original_outside_the_repo_stops_the_run(driven_urls, monkeypatch,
                                                    out_root, tmp_path):
    """서버는 저장소 루트만 서빙한다. 밖의 파일은 브라우저가 열 수 없다 -
    못 연 채로 도는 대신 멈추고 그 이유를 말해야 한다."""
    other = tmp_path / "other_original.html"
    other.write_text("<html><body>다른 원본</body></html>", encoding="utf-8")

    code, summary = run_loop(monkeypatch, out_root, always_reply, attempts=1,
                             original=str(other))
    assert code == 2
    assert summary["stopped_reason"] == "cannot_start"


# ===================================================================== #
# 7. 3003 에 떠 있는 것이 이 저장소를 서빙하는가
# ===================================================================== #
import contextlib        # noqa: E402 - 아래 서버 테스트에서만 쓴다
import socket            # noqa: E402
import subprocess        # noqa: E402
import sys               # noqa: E402
import time              # noqa: E402

devserver = _api.devserver_module


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.contextmanager
def server_on(directory, port):
    """그 폴더를 서빙하는 http.server 를 띄운다."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1",
         "--directory", str(directory)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            if devserver.listening(port):
                break
            time.sleep(0.1)
        else:
            raise AssertionError("테스트용 서버를 띄우지 못했다")
        yield port
    finally:
        proc.kill()
        proc.wait(timeout=10)


def test_a_server_serving_this_repo_is_reused():
    port = free_port()
    with server_on(ROOT, port):
        lines = []
        assert devserver.ensure_server(lines.append, port=port) is None
        assert any("reusing" in x for x in lines), lines


def test_a_server_serving_something_else_stops_the_run(tmp_path):
    """포트에 무엇이든 떠 있으면 그대로 쓰고 있었다.

    다른 폴더를 서빙하는 서버를 모르고 쓰면 검사는 돌긴 하지만 그 결과가
    무엇을 뜻하는지 알 수 없다 - 빌드를 못 열어 전부 fatal 이 나거나, 더 나쁘게
    같은 이름의 다른 문서를 열어 통과한다.
    """
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs" / "original_transfer.html").write_text(
        "<html>남의 원본</html>", encoding="utf-8")
    port = free_port()
    with server_on(tmp_path, port):
        with pytest.raises(RuntimeError) as e:
            devserver.ensure_server(lambda m: None, port=port)
    assert ":%d" % port in str(e.value)


def test_a_server_that_does_not_have_the_file_at_all_stops_the_run(tmp_path):
    port = free_port()
    with server_on(tmp_path, port):
        with pytest.raises(RuntimeError):
            devserver.ensure_server(lambda m: None, port=port)


def test_the_loop_stops_cleanly_when_the_port_is_someone_elses(fake_run_env,
                                                               monkeypatch, out_root):
    """남의 서버를 만나면 역추적이 아니라 이유와 종료 코드 2 로 끝나야 한다."""
    def refuse(log, port=None):
        raise RuntimeError(":3003 에 이미 서버가 있지만 이 저장소를 서빙하지 않는다")

    monkeypatch.setattr(loop, "ensure_server", refuse)
    code, summary = run_loop(monkeypatch, out_root, always_reply, attempts=1)
    assert code == 2
    assert summary["stopped_reason"] == "cannot_start"
    assert summary["attempts"] == []


# ===================================================================== #
# 8. .envs 읽기
# ===================================================================== #
@pytest.fixture
def envs_file(monkeypatch, tmp_path):
    """.envs 를 임시 파일로 바꾸고 키를 비운다."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(model, "ROOT", str(tmp_path))
    return tmp_path / ".envs"


def test_a_bom_does_not_hide_the_first_key(envs_file, monkeypatch):
    """메모장이 저장한 .envs 는 BOM 으로 시작한다.

    고치기 전: utf-8 로 읽어서 첫 줄의 키 이름이 '\ufeffOPENAI_API_KEY' 가
    되었다. 키는 파일에 분명히 있는데 "no OPENAI_API_KEY" 로 끝난다.
    """
    envs_file.write_bytes("OPENAI_API_KEY=sk-test-1\n".encode("utf-8-sig"))
    model.load_env()
    assert os.environ.get("OPENAI_API_KEY") == "sk-test-1"


def test_a_plain_utf8_envs_still_works(envs_file):
    envs_file.write_bytes("OPENAI_API_KEY=sk-test-2\n".encode("utf-8"))
    model.load_env()
    assert os.environ.get("OPENAI_API_KEY") == "sk-test-2"


def test_a_file_that_is_not_utf8_says_so(envs_file):
    """cp949 로 저장된 .envs 는 UnicodeDecodeError 로 터졌다. 역추적만 남으면
    사용자는 무슨 파일이 문제인지도 모른다."""
    envs_file.write_bytes("# 주석\nOPENAI_API_KEY=sk-test-3\n".encode("cp949"))
    with pytest.raises(RuntimeError) as e:
        model.load_env()
    assert ".envs" in str(e.value)
    assert "utf-8" in str(e.value).lower()


def test_an_unreadable_envs_stops_the_run_with_a_reason(fake_run_env, monkeypatch,
                                                        out_root, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(model, "ROOT", str(tmp_path))
    (tmp_path / ".envs").write_bytes(
        "# 열쇠\nOPENAI_API_KEY=sk-x\n".encode("cp949"))

    code, summary = run_loop(monkeypatch, out_root, always_reply, attempts=1)
    assert code == 2
    assert summary["stopped_reason"] == "cannot_start"


# ===================================================================== #
# 9. 레이트 리밋으로 멈췄을 때의 종료 코드
# ===================================================================== #
def test_a_rate_limited_run_exits_2(fake_run_env, out_root):
    """429 로 멈춘 것은 "빌드가 떨어졌다" 가 아니라 "돌지 못했다" 다.

    문서는 2 = 아예 돌지 못했다 라고 적고 있었는데, 실제로는 통과만 보고 1 을
    돌려주었다. 부르는 쪽은 다시 만들 것이 없는 실행을 다시 만들게 된다.
    """
    def throttled(*a, **kw):
        raise model.RateLimited("429 Too Many Requests")

    code, summary = run_loop(fake_run_env, out_root, throttled, attempts=3)
    assert summary["stopped_reason"] == "rate_limit"
    assert code == 2


def test_a_build_that_simply_failed_still_exits_1(fake_run_env, out_root):
    """구분이 서야 뜻이 있다. 떨어진 빌드는 그대로 1 이다."""
    fake_run_env.setattr(loop, "run_audit", lambda *a, **kw: failing_report())
    code, summary = run_loop(fake_run_env, out_root, always_reply, attempts=1)
    assert summary["stopped_reason"] == "budget_exhausted"
    assert code == 1


# ===================================================================== #
# 10. 콘솔 출력 인코딩
# ===================================================================== #
# `if __name__ == "__main__"` 이 있는 파일 전부. 하나라도 빠지면 그 CLI 는
# cp949 콘솔에서 한글을 찍다 죽는다.
CLI_FILES = ["senior_ui/audit/__main__.py", "senior_ui/audit/report.py",
             "senior_ui/restructure/__main__.py", "senior_ui/collect_results.py",
             "senior_ui/experiment/report.py", "senior_ui/experiment/server.py",
             "senior_ui/viewer/build_index.py"]


def test_the_list_of_clis_is_complete():
    """CLI 가 늘면 이 목록도 늘어야 한다. 늘지 않으면 아래 검사가 헛돈다."""
    import glob
    found = set()
    for path in glob.glob(os.path.join(ROOT, "senior_ui", "**", "*.py"),
                          recursive=True):
        if 'if __name__ == "__main__"' in io.open(path, encoding="utf-8").read():
            found.add(os.path.relpath(path, ROOT).replace(os.sep, "/"))
    assert found == set(CLI_FILES)


def test_every_cli_calls_setup_stdout_first():
    """CLI 마다 따로 쓰면 빠뜨린다. 실제로 재구성 루프가 빠뜨리고 있었다."""
    for rel in CLI_FILES:
        src = io.open(os.path.join(ROOT, rel), encoding="utf-8").read()
        assert "setup_stdout()" in src, rel
        assert "sys.stdout.reconfigure" not in src, "%s 가 아직 직접 맞춘다" % rel


def test_setup_stdout_survives_a_stream_it_cannot_change():
    """출력 인코딩을 맞추려다 프로그램을 죽이면 본말이 뒤집힌다."""
    class Stubborn(object):
        def reconfigure(self, **kw):
            raise ValueError("이 스트림은 못 바꾼다")

    cli = _api.cli_module
    old = sys.stdout
    try:
        sys.stdout = Stubborn()
        cli.setup_stdout()
    finally:
        sys.stdout = old


def test_a_mock_run_survives_a_cp949_console(out_root):
    """PYTHONUTF8 없이, PYTHONIOENCODING=cp949 로 --mock pass 가 끝까지 간다.

    고치기 전: 요약을 찍는 마지막 단계에서 UnicodeEncodeError 로 죽었다.
    결과 파일은 다 남았는데 종료 코드만 뒤집힌다 - 통과한 실행이 실패로 보인다.
    """
    env = dict(os.environ, PYTHONIOENCODING="cp949",
               SENIOR_UI_OUTPUTS=out_root)
    env.pop("PYTHONUTF8", None)
    p = subprocess.run(
        [sys.executable, "-m", "senior_ui.restructure", "--mock", "pass",
         "--attempts", "1"],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8",
        errors="replace")
    assert "UnicodeEncodeError" not in (p.stderr or ""), p.stderr[-2000:]
    assert p.returncode in (0, 1), p.stderr[-2000:]
    assert " summary: " in (p.stdout or "")


# ===================================================================== #
# 11. "의도한 제거" 선언은 모델이 쓸 수 없다
# ===================================================================== #
REMOVED_FLOW = dict(GOOD_FLOW, choices_removed={
    "pick-bank": {"values": ["나은행", "다은행"], "reason": "화면을 줄이려고 뺐다"}})


def one_missing_choice(**flow_kw):
    """원본에 세 개짜리 선택지가 있고 빌드에는 하나만 있다 -> 검사 I 가 본다.

    스냅샷 만드는 helper 는 test_audit_bugs 의 것을 그대로 쓴다. 검사 I 를
    보는 입력이 두 파일에서 갈라지면 안 된다.
    """
    import test_audit_bugs as AB
    orig = AB.snap({"start": AB.row("start", choices={
        "pick-bank": ["가은행", "나은행", "다은행"]})})
    rep = AB.snap({"start": AB.done_row("start")})
    return _api.audit(orig, rep, "", "<html>가은행</html>",
                      AB.flow(["start"], **flow_kw))


def test_check_I_catches_values_the_model_declared_removed(fake_run_env, out_root):
    """모델이 쓴 choices_removed 는 검사 I 를 피해 가는 장치가 된다.

    검사 I 는 흐름 명세의 choices_removed 를 읽어 그 값을 누락으로 세지 않는다
    (4-1 에서 더한 것이다). 그 선언은 연구자가 하는 것인데, 재구성 루프에서는
    흐름 명세를 모델이 쓴다 - 모델이 스스로 "일부러 뺐다" 고 적으면 검사가
    꺼진다.
    """
    seen = {}

    def spy(orig_snapshot, orig_html, html_path, flow_path, url, shots, stage,
            original_url=None, allowed_removals=None):
        seen["flow"] = json.load(io.open(flow_path, encoding="utf-8"))
        return passing_report()

    fake_run_env.setattr(loop, "run_audit", spy)
    call = replies(reply_text(GOOD_HTML, REMOVED_FLOW))
    _code, summary = run_loop(fake_run_env, out_root, call, attempts=1)

    # 검사기에 가는 흐름 명세에는 모델이 쓴 선언이 없어야 한다
    assert "choices_removed" not in seen["flow"]
    assert summary["attempts"][0]["choices_removed_dropped"] == ["pick-bank"]


def test_dropping_the_declaration_is_written_down(fake_run_env, out_root):
    """조용히 지우면 "검사가 통과했다" 와 "선언을 지웠다" 를 구분할 수 없다."""
    call = replies(reply_text(GOOD_HTML, REMOVED_FLOW))
    _code, summary = run_loop(fake_run_env, out_root, call, attempts=1)
    log = io.open(os.path.join(summary["run_dir"], "run.log"),
                  encoding="utf-8").read()
    assert "choices_removed" in log
    assert "pick-bank" in log


def test_a_flow_without_the_declaration_is_untouched(fake_run_env, out_root):
    _code, summary = run_loop(fake_run_env, out_root, always_reply, attempts=1)
    assert "choices_removed_dropped" not in summary["attempts"][0]


def test_the_allowed_list_comes_from_the_researchers_file():
    """허용하는 제거는 연구자가 관리하는 파일 하나에서만 읽는다."""
    allowed = _api.load_allowed_removals("transfer")
    assert allowed == {}          # 지금은 비어 있다 - 무엇을 넣을지는 연구자가 정한다


def test_the_allowed_list_is_merged_just_before_the_audit(tmp_path):
    """합치는 자리는 검사 직전이다 - 모델이 쓴 흐름 명세에 섞이지 않는다."""
    flow = {"name": "auto", "steps": [{"screen": "start"}]}
    path = tmp_path / "flow.json"
    path.write_text(json.dumps(flow), encoding="utf-8")
    allowed = {"quick": {"values": ["all"], "reason": "연구자가 허용했다"}}

    merged = _api.merge_allowed_removals(_api.load_flow(str(path)), allowed)
    assert merged["choices_removed"] == allowed


def test_the_declared_values_are_still_counted_when_nobody_allowed_them():
    """모델이 쓴 선언이 지워졌으면, 그 값은 그대로 누락이다."""
    report = one_missing_choice()
    assert [f["check"] for f in report["fatal"]] == ["I"]
    assert report["metrics"]["choice_values_missing"]["pick-bank"] == ["나은행", "다은행"]


def test_a_researcher_allowed_removal_is_still_honoured():
    """장치 자체를 없애는 것이 아니다. 연구자가 적은 것은 그대로 빠진다."""
    report = one_missing_choice(choices_removed={
        "pick-bank": {"values": ["나은행", "다은행"], "reason": "연구자가 허용했다"}})
    assert report["fatal"] == []


# ===================================================================== #
# 12. 입력의 선택지 데이터는 도구가 지킨다
# ===================================================================== #
# 자동 Run 4·5 에서 LLM 은 원본의 선택지 67개를 다시 타이핑하며 3~9개로 줄였다.
# 프롬프트에 "하나도 빠뜨리지 마라" 를 넣어도 9번 시도 모두 4개였다. 그래서
# 데이터는 도구가 들고 있고, 모델은 window.PRESERVED 를 참조해 그린다.
#
# 뽑기·넣기·참조 검사 자체는 tests/test_data_preservation.py 가 본다. 여기서
# 보는 것은 루프가 그것들을 어느 자리에서 쓰는가다.
PRESERVE_DATA = {"PICKS": ["가", "나", "다"]}

READS_HTML = GOOD_HTML.replace(
    "const a = el.dataset.action;",
    "const a = el.dataset.action; window.PRESERVED.PICKS.forEach(x=>x);")

# 데이터를 읽기도 하고, 같은 이름을 배열 리터럴로 다시 선언하기도 한 답.
# 참조 검사는 통과하므로 검사까지 가고, 도구가 그 선언을 고친 HTML 이
# 통과한 산출물이 된다.
REDECLARED_HTML = READS_HTML.replace(
    "<script>", "<script>\nconst PICKS = ['가'];", 1)


@pytest.fixture
def preserving(fake_run_env):
    """원본에서 뽑는 단계만 고정한다. 그 뒤는 루프가 그대로 돈다."""
    fake_run_env.setattr(loop, "preserved_data",
                         lambda snap, html: dict(PRESERVE_DATA))
    return fake_run_env


def test_the_preserved_data_is_injected_into_the_build(preserving, out_root):
    """검사기가 여는 파일에 데이터 블록이 있어야 한다. 모델이 쓴 HTML 에
    그대로 두면 모델이 타이핑한 짧은 목록이 그 자리에 남는다."""
    seen = {}

    def spy(orig_snapshot, orig_html, html_path, flow_path, url, shots, stage,
            original_url=None, allowed_removals=None):
        seen["html"] = io.open(html_path, encoding="utf-8").read()
        return passing_report()

    preserving.setattr(loop, "run_audit", spy)
    _code, _summary = run_loop(preserving, out_root,
                               replies(reply_text(READS_HTML, GOOD_FLOW)),
                               attempts=1)
    assert 'id="preserved-data"' in seen["html"]
    for v in PRESERVE_DATA["PICKS"]:
        assert v in seen["html"]


def test_a_build_that_never_reads_the_data_never_reaches_the_audit(preserving,
                                                                   out_root):
    """참조하지 않는 답은 형식 실패다. 브라우저를 띄울 일이 없다."""
    audits = []

    def spy(*a, **kw):
        audits.append(1)
        return passing_report()

    preserving.setattr(loop, "run_audit", spy)
    _code, summary = run_loop(preserving, out_root,
                              replies(reply_text(GOOD_HTML, GOOD_FLOW)),
                              attempts=1)
    assert audits == []
    assert summary["attempts"][0]["stage"] == "flow"
    assert summary["budget"]["format_used"] == 1
    assert summary["budget"]["audit_used"] == 0


def test_the_retry_block_says_which_names_were_not_read(preserving, out_root):
    call = replies(reply_text(GOOD_HTML, GOOD_FLOW))
    _code, _summary = run_loop(preserving, out_root, call, attempts=2)
    second = prompts_of(out_root)[1]
    assert "PRESERVED" in second
    assert "PICKS" in second


def test_the_reference_check_reads_the_models_html_not_the_injected_one(
        preserving, out_root):
    """도구가 넣은 블록은 `window.PRESERVED = {...}` 로 쓴다. 주입 뒤의 HTML 로
    검사하면 그 블록이 "읽었다" 로 세어져 검사가 늘 통과한다."""
    _code, summary = run_loop(preserving, out_root,
                              replies(reply_text(GOOD_HTML, GOOD_FLOW)),
                              attempts=1)
    assert summary["attempts"][0]["preserved"]["read"] == []


def test_the_summary_records_the_names_and_counts(preserving, out_root):
    """시도마다 넣은 데이터의 이름·개수, 같은 이름을 선언했는지, 참조했는지."""
    preserving.setattr(loop, "run_audit", lambda *a, **kw: passing_report())
    _code, summary = run_loop(preserving, out_root,
                              replies(reply_text(READS_HTML, GOOD_FLOW)),
                              attempts=1)
    assert summary["preserved"] == {"PICKS": 3}
    got = summary["attempts"][0]["preserved"]
    assert got["injected"] == {"PICKS": 3}
    assert got["redeclared"] == []
    assert got["read"] == ["PICKS"]


def test_the_summary_records_a_redeclaration(preserving, out_root):
    """모델이 같은 이름을 다시 타이핑했다는 사실 자체가 결과다."""
    preserving.setattr(loop, "run_audit", lambda *a, **kw: passing_report())
    _code, summary = run_loop(preserving, out_root,
                              replies(reply_text(REDECLARED_HTML, GOOD_FLOW)),
                              attempts=1)
    assert summary["attempts"][0]["preserved"]["redeclared"] == ["PICKS"]


def test_an_input_without_script_drawn_choices_changes_nothing(fake_run_env,
                                                              out_root):
    """뽑을 데이터가 없으면 아무것도 넣지 않고, 참조도 요구하지 않는다."""
    fake_run_env.setattr(loop, "preserved_data", lambda snap, html: {})
    fake_run_env.setattr(loop, "run_audit", lambda *a, **kw: passing_report())
    _code, summary = run_loop(fake_run_env, out_root,
                              replies(reply_text(GOOD_HTML, GOOD_FLOW)),
                              attempts=1)
    assert summary["passed"] is True
    assert summary["preserved"] == {}


def test_a_rewritten_declaration_is_recorded_on_the_final_build(preserving,
                                                               out_root):
    """통과한 산출물이 모델이 쓴 그대로가 아닐 수 있다.

    모델이 데이터를 읽으면서 같은 이름을 배열로도 선언하면, 참조 검사는
    통과하고 도구가 그 선언을 고친다. 그 빌드가 통과하면 승격되는 산출물이
    모델의 것이 아니다 - 연구에서 둘을 구분해야 하므로 그 사실이 승격된
    파일 옆과 기록에 남아야 한다.
    """
    preserving.setattr(loop, "run_audit", lambda *a, **kw: passing_report())
    _code, summary = run_loop(preserving, out_root,
                              replies(reply_text(REDECLARED_HTML, GOOD_FLOW)),
                              attempts=1)
    assert summary["passed"] is True
    assert summary["final"]["preserved"]["redeclared"] == ["PICKS"]

    build = io.open(os.path.join(out_root, "restructured_auto.html"),
                    encoding="utf-8").read()
    assert 'id="preserved-data"' in build
    assert "도구가 바꿨다" in build          # 파일이 스스로 말한다

    model = os.path.join(out_root, "restructured_auto.model.html")
    assert os.path.exists(model), "모델이 쓴 HTML 이 승격되지 않았다"
    assert "const PICKS = ['가']" in io.open(model, encoding="utf-8").read()

    log = io.open(os.path.join(summary["run_dir"], "run.log"),
                  encoding="utf-8").read()
    assert "모델이 쓴 그대로가 아니다" in log


def test_nothing_extra_is_promoted_when_there_is_no_data(fake_run_env,
                                                        out_root):
    """뽑을 데이터가 없는 입력에서는 승격되는 파일이 전과 같다."""
    fake_run_env.setattr(loop, "preserved_data", lambda snap, html: {})
    fake_run_env.setattr(loop, "run_audit", lambda *a, **kw: passing_report())
    _code, summary = run_loop(fake_run_env, out_root,
                              replies(reply_text(GOOD_HTML, GOOD_FLOW)),
                              attempts=1)
    assert summary["passed"] is True
    assert summary["final"]["preserved"] is None
    assert not os.path.exists(os.path.join(out_root,
                                           "restructured_auto.model.html"))
