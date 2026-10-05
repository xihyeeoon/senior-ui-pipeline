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


# ===================================================================== #
# 2. 새 모델 대응 - 모델 이름에 따라 부르는 방식이 다르다
# ===================================================================== #
@pytest.mark.parametrize("name,api,reasoning,temperature", [
    ("gpt-4o", "chat", False, True),
    ("gpt-4o-2024-08-06", "chat", False, True),
    ("gpt-4.1-mini", "chat", False, True),
    ("o3", "chat", True, False),
    ("o4-mini", "chat", True, False),
    ("gpt-5", "chat", True, False),
    ("gpt-5.6-sol", "chat", True, False),
    ("gpt-6.1-sol", "chat", True, False),
    # Chat Completions 에 없는 모델은 Responses API 로만 부를 수 있다
    ("gpt-5-pro", "responses", True, False),
    ("gpt-5.5-pro", "responses", True, False),
    ("o3-pro", "responses", True, False),
    ("gpt-5.1-codex-max", "responses", True, False),
])
def test_known_models_get_their_own_way_of_calling(name, api, reasoning, temperature):
    p = model.profile_for(name)
    assert p["known"] is True
    assert (p["api"], p["reasoning"], p["temperature"]) == (api, reasoning, temperature)
    want = "max_output_tokens" if api == "responses" else "max_completion_tokens"
    assert p["length_param"] == want


def test_an_unknown_model_is_called_like_gpt_4o():
    p, base = model.profile_for("llama-9"), model.profile_for("gpt-4o")
    assert p["known"] is False
    for k in ("api", "length_param", "temperature", "seed", "reasoning"):
        assert p[k] == base[k]


def test_the_api_can_be_forced():
    p = model.profile_for("gpt-5", api="responses")
    assert p["api"] == "responses" and p["length_param"] == "max_output_tokens"
    assert p["seed"] is False                        # Responses 에는 seed 가 없다


def test_an_unknown_model_warns_in_run_log(fake_run_env, out_root):
    _code, summary = run_loop(fake_run_env, out_root, replying(), attempts=1,
                              model="llama-9")
    lines = run_log(summary)
    assert any("경고" in l and "llama-9" in l and "gpt-4o" in l for l in lines[:3])
    assert summary["model_call"]["known"] is False


def test_the_summary_records_how_the_model_was_called(fake_run_env, out_root):
    _code, summary = run_loop(fake_run_env, out_root, replying(), attempts=1,
                              model="gpt-5", reasoning_effort="low")
    mc = summary["model_call"]
    assert mc["api"] == "chat" and mc["reasoning"] is True
    assert mc["length_param"] == "max_completion_tokens"
    assert mc["temperature"] is False and mc["reasoning_effort"] == "low"


# ---- 실제로 보내는 인자 (가짜 클라이언트) ------------------------------ #
def test_gpt_4o_is_sent_exactly_as_before(monkeypatch):
    client = F.install(monkeypatch)
    model.call_model("gpt-4o", "p", 14000, temperature=0.0, seed=7)
    api, kw = client.sent[0]
    assert api == "chat"
    assert kw == {"model": "gpt-4o", "messages": [{"role": "user", "content": "p"}],
                  "max_completion_tokens": 14000, "temperature": 0.0, "seed": 7}


def test_a_reasoning_model_on_chat_drops_temperature(monkeypatch):
    client = F.install(monkeypatch)
    reply = model.call_model("gpt-5", "p", 14000, temperature=0.0, seed=7,
                             reasoning_effort="medium")
    api, kw = client.sent[0]
    assert api == "chat"
    assert "temperature" not in kw and "max_tokens" not in kw
    assert kw["max_completion_tokens"] == 14000
    assert kw["reasoning_effort"] == "medium"
    assert reply["temperature"] is None              # 보내지 않은 것은 None 으로 남긴다
    assert reply["sent"]["reasoning_effort"] == "medium"


def test_reasoning_effort_is_not_sent_unless_asked(monkeypatch):
    client = F.install(monkeypatch)
    model.call_model("gpt-5", "p", 14000)
    assert "reasoning_effort" not in client.sent[0][1]


def test_gpt_4o_never_gets_reasoning_effort(monkeypatch):
    client = F.install(monkeypatch)
    model.call_model("gpt-4o", "p", 14000, reasoning_effort="high")
    assert "reasoning_effort" not in client.sent[0][1]


def test_a_responses_only_model_goes_to_responses(monkeypatch):
    client = F.install(monkeypatch, [F.Reply(text="hello", reasoning=40, completion=50)])
    reply = model.call_model("gpt-5-pro", "p", 9000, temperature=0.0, seed=7,
                             reasoning_effort="high")
    api, kw = client.sent[0]
    assert api == "responses"
    assert kw == {"model": "gpt-5-pro", "input": "p", "max_output_tokens": 9000,
                  "reasoning": {"effort": "high"}}
    assert reply["text"] == "hello" and reply["finish_reason"] == "stop"
    assert reply["usage"] == {"prompt": 100, "completion": 50, "reasoning": 40}


def test_reasoning_tokens_are_kept_apart_on_chat(monkeypatch):
    F.install(monkeypatch, [F.Reply(completion=900, reasoning=700)])
    reply = model.call_model("o3", "p", 14000)
    assert reply["usage"] == {"prompt": 100, "completion": 900, "reasoning": 700}


def test_gpt_4o_usage_has_no_reasoning_count(monkeypatch):
    F.install(monkeypatch)
    reply = model.call_model("gpt-4o", "p", 14000)
    assert reply["usage"] == {"prompt": 100, "completion": 10, "reasoning": None}


def test_a_cut_responses_reply_is_length(monkeypatch):
    """Responses 에는 finish_reason 이 없다 - status=incomplete,
    incomplete_details.reason=max_output_tokens 가 잘림이다."""
    F.install(monkeypatch, [F.Reply(text="", truncated=True, completion=9000,
                                    reasoning=9000)])
    reply = model.call_model("gpt-5-pro", "p", 9000)
    assert reply["finish_reason"] == "length"
    assert reply["status"] == "incomplete"


def test_a_cut_chat_reply_is_length(monkeypatch):
    F.install(monkeypatch, [F.Reply(text="", truncated=True, reasoning=14000,
                                    completion=14000)])
    reply = model.call_model("gpt-5", "p", 14000)
    assert reply["finish_reason"] == "length" and reply["text"] == ""


def test_a_cut_reply_says_when_thinking_ate_the_budget(fake_run_env, out_root):
    """생각 토큰이 한도를 다 쓰면 보이는 답이 비어 온다. 잘림 줄에 그 사실을 적는다."""
    def cut(*a, **kw):
        return {"text": "", "finish_reason": "length", "seconds": 0.0,
                "usage": {"prompt": 10, "completion": 1000, "reasoning": 1000},
                "max_tokens": 1000}
    _code, summary = run_loop(fake_run_env, out_root, cut, attempts=1, model="gpt-5")
    a = summary["attempts"][0]
    assert a["stage"] == "truncated"
    assert a["reasoning_tokens"] == 1000
    lines = [l for l in run_log(summary) if "잘림" in l]
    assert lines and "생각" in lines[0]


@pytest.mark.parametrize("err", [
    F.unsupported("temperature", "unsupported_value", 0),
    F.unsupported("temperature"),
    F.unsupported("seed"),
])
def test_an_unsupported_parameter_is_dropped_and_resent(monkeypatch, err):
    """모르는 모델은 gpt-4o 방식으로 보낸다. 거절당한 인자는 빼고 다시 보내고,
    무엇을 뺐는지 남긴다 (400 은 요금이 없다)."""
    client = F.install(monkeypatch, [err, "ok"])
    lines = []
    reply = model.call_model("mystery-1", "p", 1000, log=lines.append,
                             temperature=0.0, seed=7)
    assert len(client.sent) == 2
    assert err.param in client.sent[0][1] and err.param not in client.sent[1][1]
    assert reply["dropped"] == [err.param]
    assert any("지원하지 않는" in l and err.param in l for l in lines)


def test_an_unsupported_parameter_we_cannot_drop_is_rejected(monkeypatch):
    F.install(monkeypatch, [F.unsupported("messages")])
    with pytest.raises(model.ApiRejected):
        model.call_model("mystery-1", "p", 1000)


def test_dropped_parameters_reach_the_summary(fake_run_env, out_root):
    _code, summary = run_loop(fake_run_env, out_root,
                              replying(dropped=["temperature"]), attempts=1,
                              model="mystery-1")
    call = summary["attempts"][0]["calls"][-1]
    assert call["dropped"] == ["temperature"]


@pytest.mark.parametrize("name", ["gpt-4o", "gpt-4.1", "o3", "gpt-5", "gpt-5.6-sol"])
def test_known_models_count_tokens_with_their_own_encoding(name):
    _n, method = model.estimate_tokens("안녕하세요", name)
    assert method == "tiktoken:o200k_base"


def test_a_model_tiktoken_does_not_know_falls_back_and_says_so():
    _n, method = model.estimate_tokens("안녕하세요", "gpt-6.1-sol")
    assert method == "tiktoken:o200k_base(대체)"


def test_the_summary_tokens_keep_reasoning_apart(fake_run_env, out_root):
    _code, summary = run_loop(
        fake_run_env, out_root,
        replying(usage={"prompt": 100, "completion": 900, "reasoning": 600}),
        attempts=1, model="gpt-5")
    t = summary["tokens"]
    assert t["by_stage"]["generate"]["reasoning"] == 600
    assert t["total"]["reasoning"] == 600
