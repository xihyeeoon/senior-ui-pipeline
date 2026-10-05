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
