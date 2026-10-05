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
def make_args(tmp_path, **kw):
    """`senior_ui.restructure.__main__` 이 만드는 것과 같은 모양의 args."""
    d = dict(attempts=2, format_attempts=None, audit_attempts=None,
             infra_attempts=3, model="test-model", max_tokens=1000, mock=None,
             temperature=0.0, seed=20260101,
             original=os.path.join(ROOT, "inputs", "original_transfer.html"),
             stage="styled", delay=0)
    d.update(kw)
    return argparse.Namespace(**d)


def make_run(tmp_path, **kw):
    """단계 함수 하나만 보는 테스트용 Run. 로그는 리스트에 쌓인다."""
    args = make_args(tmp_path, **kw)
    run_dir = str(tmp_path)
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
def fake_run_env(monkeypatch, tmp_path):
    """`loop.run()` 을 서버·브라우저 없이 돌린다.

    바꿔 끼우는 것은 바깥 세계뿐이다 - 서버 띄우기, 원본을 한 번 걷기, 검사기
    호출. 루프 자신의 판단(예산·중단·종료 코드)은 그대로 돈다.
    """
    async def fake_drive(url, flow, want_shots=None):
        return dict(FAKE_SNAPSHOT)

    monkeypatch.setenv("SENIOR_UI_OUTPUTS", str(tmp_path / "outputs"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-used")
    monkeypatch.setattr(loop, "ensure_server", lambda log: None)
    monkeypatch.setattr(loop.A, "drive", fake_drive)
    monkeypatch.setattr(loop.A, "load_flow", lambda p: {"name": "original", "steps": []})
    monkeypatch.setattr(loop, "choices_block", lambda snap, html: "")
    monkeypatch.setattr(loop, "load_template", lambda: "TEMPLATE {{ORIGINAL_HTML}} "
                                                       "{{RETRY_BLOCK}} {{CHOICES}}")
    monkeypatch.setattr(loop, "run_audit",
                        lambda *a, **kw: passing_report())
    return monkeypatch


def run_loop(monkeypatch, tmp_path, call_model, **kw):
    """`call_model` 을 바꿔 끼우고 루프를 한 번 돌린다. (종료 코드, summary)."""
    monkeypatch.setattr(loop, "call_model", call_model)
    code = loop.run(make_args(tmp_path, **kw))
    runs = sorted((tmp_path / "outputs" / "restructure_auto").iterdir())
    summary = json.load(io.open(str(runs[-1] / "summary.json"), encoding="utf-8"))
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


def always_reply(*a, **kw):
    return {"text": GOOD_REPLY, "finish_reason": "stop", "seconds": 0.0,
            "usage": None}


# ===================================================================== #
# 1. 429 가 아닌 모델 호출 실패
# ===================================================================== #
def test_rejected_key_stops_the_loop(fake_run_env, tmp_path):
    """인증 오류는 다시 보내도 같은 답이 온다. 첫 실패에서 멈춰야 한다.

    고치기 전: 예산을 쓰지 않고 다음 시도로 넘어갔다 - 키가 틀리면 루프가
    끝나지 않았다.
    """
    calls = []

    def boom(*a, **kw):
        calls.append(1)
        raise model.ApiRejected("AuthenticationError: invalid api key")

    code, summary = run_loop(fake_run_env, tmp_path, boom, attempts=5)
    assert len(calls) == 1
    assert summary["stopped_reason"] == "api_rejected"
    assert code == 2


def test_rejected_key_does_not_spend_the_retry_budget(fake_run_env, tmp_path):
    """설계 실패가 아니므로 형식·검사 예산은 그대로 남아야 한다."""
    def boom(*a, **kw):
        raise model.ApiRejected("BadRequestError: model not found")

    _code, summary = run_loop(fake_run_env, tmp_path, boom, attempts=5)
    assert summary["budget"]["format_used"] == 0
    assert summary["budget"]["audit_used"] == 0


def test_network_errors_spend_the_infra_budget(fake_run_env, tmp_path):
    """네트워크 오류는 다음에 될 수 있다 - 다시 시도하되 끝은 있어야 한다."""
    calls = []

    def boom(*a, **kw):
        calls.append(1)
        raise model.InfraFailed("APIConnectionError: connection reset")

    code, summary = run_loop(fake_run_env, tmp_path, boom,
                             attempts=10, infra_attempts=3)
    assert len(calls) == 3
    assert summary["budget"]["infra_used"] == 3
    assert summary["stopped_reason"] == "infra_exhausted"
    assert code == 2
    # 설계 실패가 아니므로 다른 두 예산은 건드리지 않는다
    assert summary["budget"]["format_used"] == 0
    assert summary["budget"]["audit_used"] == 0


def test_api_error_text_never_reaches_the_prompt(fake_run_env, tmp_path):
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

    _code, _summary = run_loop(fake_run_env, tmp_path, flaky,
                               attempts=3, infra_attempts=3)
    runs = sorted((tmp_path / "outputs" / "restructure_auto").iterdir())
    prompts = [io.open(str(p), encoding="utf-8").read()
               for p in sorted(runs[-1].glob("attempt_*.prompt.txt"))]
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


def seed_promoted(tmp_path):
    """직전에 통과했던 빌드가 이미 자리에 있는 상태를 만든다."""
    out = tmp_path / "outputs"
    out.mkdir(parents=True, exist_ok=True)
    (out / "restructured_auto.html").write_text("KEEP ME", encoding="utf-8")
    return out


def test_a_failed_build_does_not_overwrite_the_promoted_copy(fake_run_env, tmp_path):
    """`restructured_auto.html` 은 "지금 쓰는 재구성본" 이다. 떨어진 빌드가 그
    자리에 올라오면 마지막으로 통과한 빌드가 조용히 사라진다 - 떨어졌다는 사실은
    summary.json 에만 남고 그 자리의 파일은 멀쩡해 보인다.

    고치기 전: 통과 여부와 무관하게 마지막 빌드를 복사했다.
    """
    out = seed_promoted(tmp_path)
    fake_run_env.setattr(loop, "run_audit", lambda *a, **kw: failing_report())

    code, summary = run_loop(fake_run_env, tmp_path, always_reply, attempts=1)
    assert summary["passed"] is False
    assert code == 1
    assert (out / "restructured_auto.html").read_text(encoding="utf-8") == "KEEP ME"


def test_a_passing_build_is_promoted(fake_run_env, tmp_path):
    out = seed_promoted(tmp_path)
    _code, summary = run_loop(fake_run_env, tmp_path, always_reply, attempts=1)
    assert summary["passed"] is True
    assert (out / "restructured_auto.html").read_text(encoding="utf-8") != "KEEP ME"
    assert (out / "restructured_auto.flow.json").exists()
    assert (out / "audit_auto.json").exists()


def test_a_passing_build_also_leaves_a_copy_named_after_the_run(fake_run_env, tmp_path):
    """통과한 실행이 둘이면 나중 것이 앞의 것을 덮는다. 비교할 수 있어야 한다."""
    out = seed_promoted(tmp_path)
    _code, summary = run_loop(fake_run_env, tmp_path, always_reply, attempts=1)
    name = os.path.basename(summary["run_dir"])
    assert (out / ("restructured_auto.%s.html" % name)).exists()
    assert (out / ("restructured_auto.%s.flow.json" % name)).exists()
    assert (out / ("audit_auto.%s.json" % name)).exists()


def test_the_run_writes_nothing_into_the_real_outputs_dir(fake_run_env, tmp_path):
    """테스트가 실제 outputs/ 를 mock 결과로 덮어쓰면 안 된다.

    고치기 전: OUTPUTS_DIR 이 상수여서 환경 변수로 옮길 수 없었고, 루프를 돌리는
    테스트는 돌 때마다 실제 `outputs/restructured_auto.*` 를 mock 결과로 바꿨다.
    """
    real = os.path.join(ROOT, "outputs")
    before = {n: os.path.getmtime(os.path.join(real, n))
              for n in os.listdir(real)} if os.path.isdir(real) else {}

    _code, summary = run_loop(fake_run_env, tmp_path, always_reply, attempts=1)
    assert summary["run_dir"].startswith(str(tmp_path))

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


def prompts_of(tmp_path):
    runs = sorted((tmp_path / "outputs" / "restructure_auto").iterdir())
    return [io.open(str(p), encoding="utf-8").read()
            for p in sorted(runs[-1].glob("attempt_*.prompt.txt"))]


def test_parse_failure_keeps_the_last_audited_findings(fake_run_env, tmp_path):
    """파싱이 실패한 시도는 검사받은 적이 없다. 검사 결과는 그 전 시도의 것이다.

    고치기 전: 직전 HTML 은 그대로 두면서 그 HTML 의 검사 결과는 파싱 실패
    리포트로 덮었다. 재시도 프롬프트가 HTML 과 어긋난 실패 목록을 보게 된다 -
    "이 HTML 을 고쳐라" 고 하면서 그 HTML 에서 나오지 않은 실패를 붙인 셈이다.
    """
    fake_run_env.setattr(loop, "run_audit", lambda *a, **kw: failing_report())
    call = replies(GOOD_REPLY, BAD_REPLY, GOOD_REPLY)

    _code, _summary = run_loop(fake_run_env, tmp_path, call, attempts=3)
    third = prompts_of(tmp_path)[2]
    # 2번 시도의 파싱 실패와, 1번 시도에서 실제로 검사받은 실패가 둘 다 있어야
    # 한다 - 한쪽이 다른 쪽을 덮으면 안 된다.
    assert "```html 코드 블록이 없다" in third
    assert "금액이 틀렸다" in third


def test_parse_failure_carries_the_html_that_was_audited(fake_run_env, tmp_path):
    """프롬프트에 실리는 HTML 과 흐름 명세는 그 실패 목록을 낸 바로 그 빌드다."""
    fake_run_env.setattr(loop, "run_audit", lambda *a, **kw: failing_report())
    call = replies(GOOD_REPLY, BAD_REPLY, GOOD_REPLY)

    _code, _summary = run_loop(fake_run_env, tmp_path, call, attempts=3)
    third = prompts_of(tmp_path)[2]
    assert "data-screen=\"start\"" in third      # 직전에 검사받은 HTML
    assert "\"required_ids\"" in third            # 그 HTML 과 짝인 흐름 명세


def test_a_truncated_answer_is_called_out_on_the_retry(fake_run_env, tmp_path):
    """길이 제한에 잘린 답은 "짧게 써라" 가 아니라 "잘렸다" 를 알려야 한다.

    고치기 전: 잘린 답도 보통의 파싱 실패와 같은 한 줄로 들어갔고, 같은 길이의
    답이 다시 와서 같은 자리에서 또 잘렸다.
    """
    call = replies("```html\n<html>여기서 잘림", finish="length")

    _code, summary = run_loop(fake_run_env, tmp_path, call, attempts=3)
    second = prompts_of(tmp_path)[1]
    assert "finish_reason=length" in second
    assert "[잘린 답]" in second
    assert summary["attempts"][0]["truncated"] is True


def test_the_truncation_notice_counts_how_many_times_it_happened(fake_run_env, tmp_path):
    """두 번째로 잘리면 그 사실이 보여야 한다 - 같은 지시를 반복해도 소용없다."""
    call = replies("```html\n<html>여기서 잘림", finish="length")

    _code, _summary = run_loop(fake_run_env, tmp_path, call, attempts=3)
    third = prompts_of(tmp_path)[2]
    assert "2번 연속" in third


# ===================================================================== #
# 3. 흐름 명세의 타입 검사
# ===================================================================== #
def test_a_flow_that_is_an_array_is_a_flow_problem(fake_run_env, tmp_path):
    """흐름 명세가 배열이면 FLOW 문제다. 루프가 멈추는 일이 되면 안 된다.

    고치기 전: `flow.setdefault("name", "auto")` 가 AttributeError 로 터졌고,
    그 예외는 ValueError 가 아니어서 아무도 받지 못했다 - 루프 전체가 역추적만
    남기고 죽었다.
    """
    call = replies(reply_text(GOOD_HTML, [{"screen": "start"}]))

    code, summary = run_loop(fake_run_env, tmp_path, call, attempts=1)
    assert summary["attempts"][0]["stage"] == "flow"
    assert code == 1
    report = json.load(io.open(os.path.join(summary["run_dir"],
                                            "attempt_1.audit.json"), encoding="utf-8"))
    assert [f["check"] for f in report["fatal"]] == ["FLOW"]


def test_a_list_valued_screen_is_a_flow_problem(fake_run_env, tmp_path):
    """screen 이 목록이면 FLOW 문제다.

    고치기 전: `st["screen"] not in screens` 가 집합에 목록을 넣어
    TypeError: unhashable type 으로 터졌다 - 역시 아무도 받지 못했다.
    """
    flow = json.loads(json.dumps(GOOD_FLOW))
    flow["steps"][1]["screen"] = ["done", "start"]
    call = replies(reply_text(GOOD_HTML, flow))

    code, summary = run_loop(fake_run_env, tmp_path, call, attempts=1)
    assert summary["attempts"][0]["stage"] == "flow"
    assert code == 1


def test_a_step_that_is_not_an_object_is_a_flow_problem(fake_run_env, tmp_path):
    flow = json.loads(json.dumps(GOOD_FLOW))
    flow["steps"][1] = "done"
    call = replies(reply_text(GOOD_HTML, flow))

    _code, summary = run_loop(fake_run_env, tmp_path, call, attempts=1)
    assert summary["attempts"][0]["stage"] == "flow"


def test_shape_problems_are_phrased_for_the_model(fake_run_env, tmp_path):
    """FLOW 문제는 다음 프롬프트로 간다. 모델이 읽고 고칠 수 있는 글이어야 한다."""
    call = replies(reply_text(GOOD_HTML, [{"screen": "start"}]),
                   reply_text(GOOD_HTML, GOOD_FLOW))

    _code, _summary = run_loop(fake_run_env, tmp_path, call, attempts=2)
    second = prompts_of(tmp_path)[1]
    assert "객체" in second


def test_summary_is_written_even_when_the_loop_dies(fake_run_env, tmp_path):
    """요약은 실행의 기록이다. 루프가 터져도 남아야 한다.

    고치기 전: summary.json 을 try/finally 밖에서 썼다. 루프 안에서 예외가
    나면 그 실행은 run.log 조각만 남기고 아무 기록도 남기지 않았다.
    """
    def explode(*a, **kw):
        raise KeyboardInterrupt("사용자가 끊었다")

    with pytest.raises(KeyboardInterrupt):
        run_loop(fake_run_env, tmp_path, explode, attempts=1)
    runs = sorted((tmp_path / "outputs" / "restructure_auto").iterdir())
    assert (runs[-1] / "summary.json").exists()


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


def test_temperature_and_seed_are_set_not_left_to_the_default(fake_run_env, tmp_path):
    """지정하지 않으면 공급자의 기본값이 쓰이고, 그 값은 기록에 남지 않는다."""
    seen = []
    _code, _summary = run_loop(fake_run_env, tmp_path, recording_reply(seen),
                               attempts=1)
    assert seen[0]["temperature"] is not None
    assert seen[0]["seed"] is not None


def test_every_attempt_records_what_it_would_take_to_repeat_it(fake_run_env, tmp_path):
    """시도 하나를 다시 돌리려면 무엇이 필요한가 - 그것이 시도 기록에 있어야 한다.

    고치기 전: 기록은 finish_reason · usage · seconds 뿐이었다. 같은 프롬프트를
    같은 모델에 보내도 다른 답이 나오는 이유(temperature·seed·실제 응답 모델·
    system_fingerprint)는 아무 데도 남지 않았다.
    """
    _code, summary = run_loop(fake_run_env, tmp_path, recording_reply([]),
                              attempts=1)
    repro = summary["attempts"][0]["repro"]
    assert sorted(repro) == sorted(REPRO_KEYS)
    assert repro["response_model"] == "gpt-4o-2026-01-01"
    assert repro["system_fingerprint"] == "fp_abc123"
    assert repro["openai_sdk"]


def test_the_summary_records_it_once_for_the_run(fake_run_env, tmp_path):
    _code, summary = run_loop(fake_run_env, tmp_path, recording_reply([]),
                              attempts=1)
    assert sorted(summary["repro"]) == sorted(REPRO_KEYS)
    assert summary["repro"]["response_model"] is None    # 실행 자체는 모델이 없다


def test_the_prompt_template_is_fingerprinted(fake_run_env, tmp_path):
    """템플릿이 바뀌면 같은 입력도 다른 답을 낸다. 어느 템플릿이었는지 남긴다."""
    import hashlib
    fake_run_env.setattr(loop, "load_template", lambda: "바뀐 템플릿")
    _code, summary = run_loop(fake_run_env, tmp_path, recording_reply([]),
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
                                                              tmp_path):
    _code, _summary = run_loop(monkeypatch, tmp_path, always_reply, attempts=1)
    assert driven_urls[0].endswith("/inputs/original_transfer.html")


def test_original_flag_moves_the_comparison_run_too(driven_urls, monkeypatch, tmp_path):
    """--original 로 다른 원본을 주면 비교 기준도 그 파일이어야 한다.

    고치기 전: 프롬프트에 넣는 HTML 만 그 파일에서 읽고, 브라우저로 걷는 것은
    config.ORIGINAL_URL 로 못박혀 있었다. 대비·언어 검사의 기준이 프롬프트에
    넣은 원본과 다른 문서가 된다 - 아무 경고 없이.
    """
    other = os.path.join(ROOT, "results", "restructured_transfer.html")
    _code, _summary = run_loop(monkeypatch, tmp_path, always_reply, attempts=1,
                               original=other)
    assert driven_urls[0].endswith("/results/restructured_transfer.html")


def test_the_audit_compares_against_the_same_original(driven_urls, monkeypatch,
                                                      tmp_path):
    """검사 리포트의 inputs.original 도 같은 URL 이어야 한다."""
    seen = {}

    def spy(orig_snapshot, orig_html, html_path, flow_path, url, shots, stage,
            original_url=None):
        seen["url"] = original_url
        return passing_report()

    monkeypatch.setattr(loop, "run_audit", spy)
    other = os.path.join(ROOT, "results", "restructured_transfer.html")
    run_loop(monkeypatch, tmp_path, always_reply, attempts=1, original=other)
    assert seen["url"].endswith("/results/restructured_transfer.html")


def test_an_original_outside_the_repo_stops_the_run(driven_urls, monkeypatch, tmp_path):
    """서버는 저장소 루트만 서빙한다. 밖의 파일은 브라우저가 열 수 없다 -
    못 연 채로 도는 대신 멈추고 그 이유를 말해야 한다."""
    other = tmp_path / "other_original.html"
    other.write_text("<html><body>다른 원본</body></html>", encoding="utf-8")

    code, summary = run_loop(monkeypatch, tmp_path, always_reply, attempts=1,
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


def test_the_loop_stops_cleanly_when_the_port_is_someone_elses(monkeypatch, tmp_path,
                                                               fake_run_env):
    """남의 서버를 만나면 역추적이 아니라 이유와 종료 코드 2 로 끝나야 한다."""
    def refuse(log, port=None):
        raise RuntimeError(":3003 에 이미 서버가 있지만 이 저장소를 서빙하지 않는다")

    monkeypatch.setattr(loop, "ensure_server", refuse)
    code, summary = run_loop(monkeypatch, tmp_path, always_reply, attempts=1)
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
                                                        tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(model, "ROOT", str(tmp_path))
    (tmp_path / ".envs").write_bytes(
        "# 열쇠\nOPENAI_API_KEY=sk-x\n".encode("cp949"))

    code, summary = run_loop(monkeypatch, tmp_path, always_reply, attempts=1)
    assert code == 2
    assert summary["stopped_reason"] == "cannot_start"


# ===================================================================== #
# 9. 레이트 리밋으로 멈췄을 때의 종료 코드
# ===================================================================== #
def test_a_rate_limited_run_exits_2(fake_run_env, tmp_path):
    """429 로 멈춘 것은 "빌드가 떨어졌다" 가 아니라 "돌지 못했다" 다.

    문서는 2 = 아예 돌지 못했다 라고 적고 있었는데, 실제로는 통과만 보고 1 을
    돌려주었다. 부르는 쪽은 다시 만들 것이 없는 실행을 다시 만들게 된다.
    """
    def throttled(*a, **kw):
        raise model.RateLimited("429 Too Many Requests")

    code, summary = run_loop(fake_run_env, tmp_path, throttled, attempts=3)
    assert summary["stopped_reason"] == "rate_limit"
    assert code == 2


def test_a_build_that_simply_failed_still_exits_1(fake_run_env, tmp_path):
    """구분이 서야 뜻이 있다. 떨어진 빌드는 그대로 1 이다."""
    fake_run_env.setattr(loop, "run_audit", lambda *a, **kw: failing_report())
    code, summary = run_loop(fake_run_env, tmp_path, always_reply, attempts=1)
    assert summary["stopped_reason"] == "budget_exhausted"
    assert code == 1
