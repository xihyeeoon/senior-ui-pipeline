r"""도구 내부 버그와 바깥 문제를 가른다 (감사 D-6 (가) · B-15 · B-16 · B-17 · B-33).

실패는 세 종류이고 할 일이 다르다.

  설계 실패     빌드가 과제를 통과하지 못했다 - 형식 · 검사 예산을 쓰고 모델이
                고친다 (검사 리포트의 fatal)
  바깥 문제     모델에 닿지 못했다 · 브라우저가 시간 안에 답하지 않았다 - 인프라
                예산을 쓰고 같은 일을 다시 한다. 모델에게 말하지 않는다
  도구 버그     우리 코드가 예외를 냈다 - 실행을 멈추고 종료 코드 2. run.log 와
                summary 에 남긴다. 설계 실패로 세지 않고 모델에게도 보내지 않는다

전에는 루프가 넓은 `except Exception` 으로 셋째를 첫째나 둘째로 셌다. 코드 버그가
"검사기가 흐름 명세를 실행하지 못했다" 로 모델에게 가고 검사 예산을 썼다.

브라우저도 모델도 부르지 않는다.
"""
import io
import json
import os
import sys

import openai
import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeout

import _api
import fake_openai
from test_restructure_bugs import (GOOD_REPLY, always_reply, fake_run_env,  # noqa: F401
                                   make_args, out_root, passing_report, run_dirs,
                                   run_loop)

loop = _api.loop_module
model = _api.model_module
config = _api.config_module


def counting(fn=always_reply):
    calls = []

    def call(*a, **kw):
        calls.append(1)
        return fn(*a, **kw)
    call.calls = calls
    return call


def audits(*outcomes):
    """run_audit 의 대역. 부를 때마다 outcomes 를 하나씩 쓴다 - 예외면 던지고,
    아니면 통과 리포트. 다 쓰면 마지막 것을 되풀이한다."""
    seen = []

    def run_audit(*a, **kw):
        out = outcomes[min(len(seen), len(outcomes) - 1)]
        seen.append(out)
        if isinstance(out, Exception):
            raise out
        return passing_report()
    run_audit.seen = seen
    return run_audit


def run_log(summary):
    return io.open(os.path.join(summary["run_dir"], "run.log"), encoding="utf-8").read()


# --------------------------------------------------------------------- #
# 1. 검사기 쪽 - 도구 버그는 멈추고, 브라우저 시간 초과만 인프라 예산 (B-17)
# --------------------------------------------------------------------- #
def test_a_bug_in_the_auditor_stops_the_run_with_2(fake_run_env, out_root):  # noqa: F811
    """고치기 전: KeyError 가 "검사기가 흐름 명세를 실행하지 못했다" AUDIT fatal 이
    되어 검사 예산을 쓰고, 그 문구가 다음 프롬프트로 모델에게 갔다. 예산이 남으면
    같은 버그를 시도마다 되풀이했다."""
    call = counting()
    fake_run_env.setattr(loop, "run_audit", audits(KeyError("steps")))
    code, summary = run_loop(fake_run_env, out_root, call, attempts=3)
    assert code == 2
    assert summary["stopped_reason"] == "internal_error"
    assert "KeyError" in summary["error"] and "steps" in summary["error"]
    assert summary["budget"]["audit_used"] == 0
    assert summary["budget"]["infra_used"] == 0
    assert len(call.calls) == 1                       # 모델에게 다시 묻지 않았다
    log = run_log(summary)
    assert "Traceback" in log and "KeyError" in log


def test_a_browser_timeout_reaudits_the_same_build(fake_run_env, out_root):  # noqa: F811
    """브라우저가 시간 안에 답하지 않은 것은 설계와 무관하다. 인프라 예산 하나를
    쓰고 같은 빌드를 다시 검사한다 - 모델에게 다시 묻지 않는다."""
    call = counting()
    audit = audits(PlaywrightTimeout("Timeout 30000ms exceeded"), None)
    fake_run_env.setattr(loop, "run_audit", audit)
    code, summary = run_loop(fake_run_env, out_root, call, attempts=3, infra_attempts=3)
    assert code == 0 and summary["passed"]
    assert len(audit.seen) == 2
    assert len(call.calls) == 1
    assert summary["budget"]["infra_used"] == 1
    assert summary["budget"]["audit_used"] == 0
    assert summary["attempts"][0]["audit_infra_failures"][0].startswith("TimeoutError")


def test_browser_timeouts_until_the_infra_budget_is_gone_stop_with_2(
        fake_run_env, out_root):  # noqa: F811
    call = counting()
    audit = audits(PlaywrightTimeout("Timeout 30000ms exceeded"))
    fake_run_env.setattr(loop, "run_audit", audit)
    code, summary = run_loop(fake_run_env, out_root, call, attempts=5, infra_attempts=3)
    assert code == 2
    assert summary["stopped_reason"] == "infra_exhausted"
    assert len(audit.seen) == 3 and len(call.calls) == 1
    assert summary["budget"]["infra_used"] == 3
    assert summary["budget"]["audit_used"] == 0
    assert summary["attempts"][-1]["stage"] == "audit_infra"


# --------------------------------------------------------------------- #
# 2. 모델 호출 쪽 - 연결 실패만 인프라 예산 (B-17)
# --------------------------------------------------------------------- #
def test_a_bug_around_the_model_call_stops_the_run_with_2(fake_run_env, out_root):  # noqa: F811
    """고치기 전: 모델 호출 둘레의 코드 버그(여기서는 KeyError)도 "연결 실패" 로
    세어 인프라 예산을 다 쓰고 infra_exhausted 로 끝났다."""
    calls = []

    def buggy(*a, **kw):
        calls.append(1)
        raise KeyError("choices")
    code, summary = run_loop(fake_run_env, out_root, buggy, attempts=3, infra_attempts=3)
    assert code == 2
    assert summary["stopped_reason"] == "internal_error"
    assert "KeyError" in summary["error"]
    assert len(calls) == 1
    assert summary["budget"]["infra_used"] == 0


def test_a_server_error_from_the_api_is_an_outside_problem(monkeypatch):
    """5xx 는 공급자 쪽 문제다 - 같은 요청이 다음에는 될 수 있다 (InfraFailed).
    고치기 전에는 SDK 의 예외가 그대로 올라왔고, 루프의 넓은 except 만이 그것을
    인프라로 셌다."""
    fake_openai.install(monkeypatch, [fake_openai.make_error(
        openai.InternalServerError, "Error code: 500 - server error", 500)])
    with pytest.raises(model.InfraFailed) as e:
        model.call_model("gpt-4o", "hi", 10, backoff=())
    assert "InternalServerError" in str(e.value)


# --------------------------------------------------------------------- #
# 5. 인프라 예산 3 은 config 에 하나 (B-33)
# --------------------------------------------------------------------- #
def test_the_infra_budget_lives_in_config():
    """고치기 전: 3 이 loop.Budget · loop.Run · restructure.__main__ 세 곳에 따로
    있었고 config.DEFAULT_BUDGET · budget_source · run.log 첫 줄에는 없었다."""
    assert config.DEFAULT_BUDGET["infra"] == 3
    args = _api.restructure_parser().parse_args([])
    assert args.infra_attempts is None
    got = loop.budget_choice(args)
    assert got["infra"] == (3, "config.DEFAULT_BUDGET")
    assert loop.budget_choice(make_args("x", infra_attempts=5))["infra"] == \
        (5, "--infra-attempts")


def test_the_infra_budget_and_its_source_are_written_down(fake_run_env, out_root):  # noqa: F811
    code, summary = run_loop(fake_run_env, out_root, always_reply, attempts=1,
                             infra_attempts=None)
    assert summary["budget_source"]["infra"] == "config.DEFAULT_BUDGET"
    assert summary["budget"]["infra_budget"] == 3
    first = run_log(summary).splitlines()[0]
    assert "인프라 3" in first and "config.DEFAULT_BUDGET" in first
