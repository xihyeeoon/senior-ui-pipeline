r"""12번 실행에 맞춘 설정 - 출력 길이 · 호출 사이 대기 · reasoning_effort.

배경: gpt-6.1-sol · gpt-6-astra 의 분당 토큰 한도는 500,000 이다 (gpt-4o 는
30,000). 한도 때문에 낮춰 둔 값들을 추론형일 때만 다시 정했다. gpt-4o 로 부를
때의 값과 동작은 그대로다 - 이체 기준값이 그것으로 뽑혀 있다.

실제 API 는 절대 부르지 않는다. loop.call_model 을 바꿔 끼우거나 (run_loop),
openai.OpenAI 를 tests/fake_openai.py 의 대역으로 바꿔 끼운다.
"""
import io
import os

import pytest

import _api
from test_restructure_bugs import (GOOD_PLAN_REPLY, always_reply,  # noqa: F401
                                   fake_run_env, is_plan_prompt, out_root, run_loop)

from senior_ui import config

loop = _api.loop_module
model = _api.model_module


def run_log(summary):
    path = os.path.join(summary["run_dir"], "run.log")
    return io.open(path, encoding="utf-8").read().splitlines()


def recording(calls, ratelimit=None):
    """call_model 대역. 호출마다 (단계, max_tokens, 나머지 인자) 를 쌓는다."""
    def call(model_, prompt, max_tokens, log=None, **kw):
        stage = "plan" if is_plan_prompt(prompt) else "gen"
        calls.append((stage, max_tokens, kw))
        if stage == "plan":
            out = {"text": GOOD_PLAN_REPLY, "finish_reason": "stop", "seconds": 0.0,
                   "usage": None}
        else:
            out = always_reply()
        out["ratelimit"] = ratelimit
        return out
    return call


def caps(calls):
    return [(stage, cap) for stage, cap, _kw in calls]


# ===================================================================== #
# 1. 출력 길이 기본값 - 추론형은 생각 토큰도 이 안에서 쓴다
# ===================================================================== #
def test_the_cli_leaves_the_output_caps_to_the_model():
    """파서에 숫자를 적어 두면 모델과 상관없이 그 값이 간다."""
    args = _api.restructure_parser().parse_args([])
    assert args.max_tokens is None and args.plan_max_tokens is None


def test_gpt_4o_keeps_its_caps(fake_run_env, out_root):
    calls = []
    run_loop(fake_run_env, out_root, recording(calls), plan_reply=False, attempts=1,
             model="gpt-4o", max_tokens=None)
    assert caps(calls) == [("plan", 6000), ("gen", 14000)]


@pytest.mark.parametrize("name", ["gpt-6.1-sol", "gpt-6-astra", "gpt-5"])
def test_a_reasoning_model_gets_room_to_think(fake_run_env, out_root, name):
    calls = []
    run_loop(fake_run_env, out_root, recording(calls), plan_reply=False, attempts=1,
             model=name, max_tokens=None)
    assert caps(calls) == [("plan", 25000), ("gen", 32000)]


def test_the_caps_are_written_in_config():
    assert config.OUTPUT_CAPS == {"gpt-4o": {"generate": 14000, "plan": 6000},
                                  "reasoning": {"generate": 32000, "plan": 25000}}
    # OpenAI: 처음에는 생각과 출력에 적어도 25,000 을 남겨 두라
    assert min(config.OUTPUT_CAPS["reasoning"].values()) >= 25000


def test_caps_given_on_the_command_line_win(fake_run_env, out_root):
    calls = []
    run_loop(fake_run_env, out_root, recording(calls), plan_reply=False, attempts=1,
             model="gpt-6.1-sol", max_tokens=9000, plan_max_tokens=3000)
    assert caps(calls) == [("plan", 3000), ("gen", 9000)]


def test_run_log_says_which_caps_were_used(fake_run_env, out_root):
    _code, summary = run_loop(fake_run_env, out_root, recording([]), attempts=1,
                              model="gpt-6.1-sol", max_tokens=None)
    line = next(l for l in run_log(summary) if "max_tokens" in l and "기본값" in l)
    assert "32000" in line and "25000" in line
