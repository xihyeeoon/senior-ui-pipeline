r"""모델 바꾸기 준비 - 기본값 · 모델별 부르는 방식 · 분당 한도 기록 · 확인 명령 · 가격.

실제 API 는 절대 부르지 않는다. openai.OpenAI 를 tests/fake_openai.py 의 대역으로
바꿔 끼우거나, loop.call_model 을 바꿔 끼운다 (test_restructure_bugs.py 의 run_loop).
"""
import io
import json
import os

import pytest

import _api
import fake_openai as F
from test_restructure_bugs import (GOOD_REPLY, fake_run_env, out_root,  # noqa: F401
                                   run_dirs, run_loop)

from senior_ui import config

loop = _api.loop_module
model = _api.model_module


def run_log(summary):
    path = os.path.join(summary["run_dir"], "run.log")
    return io.open(path, encoding="utf-8").read().splitlines()


def replying(response_model="gpt-4o-2026-01-01", usage=None, **extra):
    """call_model 대역. 응답 모델 이름과 usage 를 정해 돌려준다."""
    def call(model_name, prompt, max_tokens, log=None, **kw):
        out = {"text": GOOD_REPLY, "finish_reason": "stop", "seconds": 0.0,
               "usage": usage, "model": response_model,
               "system_fingerprint": "fp_abc", "max_tokens": max_tokens}
        out.update(extra)
        return out
    return call


# ===================================================================== #
# 1. 모델 설정 - 기본값은 config.py 한 곳, --model 로 바꾼다
# ===================================================================== #
@pytest.fixture
def no_model_env(monkeypatch):
    for name in config.MODEL_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def args_with(model_name=None):
    return type("A", (), {"model": model_name})()


def test_the_default_model_lives_in_config(no_model_env):
    assert config.DEFAULT_MODEL == "gpt-4o"
    assert loop.pick_model(args_with()) == "gpt-4o"
    no_model_env.setattr(config, "DEFAULT_MODEL", "gpt-other")
    assert loop.pick_model(args_with()) == "gpt-other"


def test_where_the_model_came_from_is_known(no_model_env):
    assert loop.model_choice(args_with()) == ("gpt-4o", "config.DEFAULT_MODEL")
    assert loop.model_choice(args_with("gpt-x")) == ("gpt-x", "--model")
    no_model_env.setenv("RESTRUCTURE_MODEL", "gpt-env")
    assert loop.model_choice(args_with()) == ("gpt-env", "RESTRUCTURE_MODEL")
    # --model 이 환경 변수를 이긴다
    assert loop.model_choice(args_with("gpt-x")) == ("gpt-x", "--model")


def test_the_cli_model_flag_defaults_to_nothing_so_config_decides():
    """--model 의 기본값을 파서에 또 적으면 config 와 두 군데가 된다."""
    args = _api.restructure_parser().parse_args([])
    assert args.model is None


def test_run_log_first_line_names_the_model(fake_run_env, out_root, no_model_env):
    _code, summary = run_loop(fake_run_env, out_root, replying(), attempts=1,
                              model="gpt-4o")
    first = run_log(summary)[0]
    assert "model=gpt-4o" in first and "--model" in first


def test_run_log_first_line_says_when_it_is_the_default(fake_run_env, out_root,
                                                        no_model_env):
    _code, summary = run_loop(fake_run_env, out_root, replying(), attempts=1,
                              model=None)
    first = run_log(summary)[0]
    assert "model=gpt-4o" in first and "config.DEFAULT_MODEL" in first
    assert summary["model"] == "gpt-4o"
    assert summary["model_source"] == "config.DEFAULT_MODEL"


def test_the_summary_keeps_what_the_api_said_it_was(fake_run_env, out_root):
    """별칭(gpt-4o)은 날짜가 붙은 판으로 풀린다. 그 이름을 실행 단위로 남긴다."""
    _code, summary = run_loop(fake_run_env, out_root, replying(), attempts=1,
                              model="gpt-4o")
    assert summary["model"] == "gpt-4o"
    assert summary["response_models"] == ["gpt-4o-2026-01-01"]
    assert any("응답 모델" in l and "gpt-4o-2026-01-01" in l for l in run_log(summary))


def test_mock_runs_have_no_response_model(fake_run_env, out_root):
    _code, summary = run_loop(fake_run_env, out_root, replying(response_model=None),
                              attempts=1)
    assert summary["response_models"] == []

