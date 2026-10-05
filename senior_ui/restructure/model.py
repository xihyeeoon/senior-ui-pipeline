r"""모델 호출과, 모델 없이 도는 대역.

키 읽기(load_env) · 실제 호출(call_model) · API 없이 Run 1 을 다시 재생하는
mock_reply 가 여기 있다. 돌려주는 모양은 셋 다 같다:
{"text", "finish_reason", "seconds", "usage"}.
"""
import io
import json
import os
import time

from senior_ui.config import FLOWS_DIR, OUTPUTS_DIR, RESULTS_DIR, ROOT, outputs_dir


def load_env():
    """OPENAI_API_KEY from .envs if the environment does not have it. The file
    is KEY=value lines, quotes optional, '#' comments."""
    if os.environ.get("OPENAI_API_KEY"):
        return
    path = os.path.join(ROOT, ".envs")
    if not os.path.exists(path):
        return
    for line in io.open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class ModelError(Exception):
    """모델 호출이 실패했다. 어느 것도 "설계가 과제를 통과 못 했다" 가 아니다.

    세 갈래를 가르는 이유는 부르는 쪽이 할 일이 전부 다르기 때문이다.

      RateLimited  429 가 백오프를 다 쓰고도 계속된다 - 지금은 못 돈다
      ApiRejected  키·권한·요청 자체가 틀렸다 - 다시 보내도 같은 답이 온다
      InfraFailed  연결이 되지 않았다 - 같은 요청이 다음에는 될 수 있다

    가르지 않으면 틀린 키 하나로 루프가 끝나지 않는다. 같은 호출이 같은 이유로
    실패하는데 그것이 "다음 시도로 넘어갈 일" 로 취급되기 때문이다.
    """


class RateLimited(ModelError):
    """백오프를 다 쓰고도 429 가 계속된 경우. 설계 실패가 아니라 인프라 한도다."""


class ApiRejected(ModelError):
    """인증·권한·잘못된 요청. 같은 요청을 다시 보내도 결과가 같으므로 멈춘다."""


class InfraFailed(ModelError):
    """연결 실패·타임아웃. 다시 시도할 값은 있지만 무한히 하지는 않는다."""


# 같은 프롬프트를 같은 모델에 보내도 답은 달라진다. 지정하지 않으면 공급자의
# 기본값이 쓰이고 그 값은 어디에도 남지 않으므로, 못박아 두고 기록한다. 0 이
# 재현에 가장 가깝고, seed 는 같은 값이기만 하면 된다.
TEMPERATURE = 0.0
SEED = 20260101


def sdk_version():
    """지금 쓰는 openai SDK 의 판. 같은 코드라도 SDK 가 다르면 답이 달라진다."""
    try:
        import openai
        return getattr(openai, "__version__", None)
    except ImportError:
        return None


def call_model(model, prompt, max_tokens, log=None, backoff=(20, 45, 90, 180),
               temperature=TEMPERATURE, seed=SEED):
    """시도마다 직전 HTML 전체를 다시 보내므로 프롬프트가 크다. 이 계정은 전에
    TPM 30,000 한도에 걸린 적이 있으므로 429 를 지수적으로 기다렸다 다시 친다.
    그래도 안 되면 RateLimited 를 올려 설계 실패와 섞이지 않게 한다.

    429 가 아닌 실패는 ApiRejected 와 InfraFailed 로 갈라 올린다 - 어느 쪽인지는
    여기서만 알 수 있다 (openai 의 예외 종류). 루프는 그 종류만 보고 판단한다."""
    from openai import (OpenAI, APIConnectionError, AuthenticationError,
                        BadRequestError, NotFoundError, OpenAIError,
                        PermissionDeniedError, RateLimitError)
    # 키가 아예 없으면 생성자부터 OpenAIError 다. 그것도 "다시 보내도 같다" 다.
    try:
        client = OpenAI()
    except OpenAIError as e:
        raise ApiRejected("%s: %s" % (type(e).__name__, e))
    t0 = time.time()
    for i, wait in enumerate((0,) + tuple(backoff)):
        if wait:
            if log:
                log("429 — %d초 기다렸다 다시 시도 (%d/%d)" % (wait, i, len(backoff)))
            time.sleep(wait)
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=max_tokens,
                temperature=temperature,
                seed=seed,
            )
            break
        except RateLimitError as e:
            last = e
        except (AuthenticationError, PermissionDeniedError, BadRequestError,
                NotFoundError) as e:
            raise ApiRejected("%s: %s" % (type(e).__name__, e))
        except APIConnectionError as e:          # APITimeoutError 도 이 아래다
            raise InfraFailed("%s: %s" % (type(e).__name__, e))
    else:
        raise RateLimited(str(last))
    choice = resp.choices[0]
    usage = getattr(resp, "usage", None)
    return {
        "text": choice.message.content or "",
        "finish_reason": choice.finish_reason,
        "seconds": round(time.time() - t0, 1),
        "usage": {"prompt": getattr(usage, "prompt_tokens", None),
                  "completion": getattr(usage, "completion_tokens", None)} if usage else None,
        # 보낸 것과 받은 것을 함께 적는다. --model gpt-4o 로 보내도 실제로
        # 답한 것은 그 별명이 가리키는 어느 판본이고, 그 판본이 바뀌면 같은
        # 프롬프트가 다른 답을 낸다. system_fingerprint 는 그 뒤의 구성이다.
        "temperature": temperature,
        "seed": seed,
        "model": getattr(resp, "model", None),
        "system_fingerprint": getattr(resp, "system_fingerprint", None),
    }


# mock 이 되읽는 Run 1 빌드. outputs/ 는 추적하지 않아서 없을 수 있고, 테스트는
# 산출물 폴더를 임시 폴더로 옮긴다 - 그래서 셋을 차례로 본다. 마지막 results/ 는
# 추적되는 사본이므로 어느 PC 에서나 있다.
MOCK_BUILD = "restructured_transfer.html"


def mock_build_path():
    for d in (outputs_dir(), OUTPUTS_DIR, RESULTS_DIR):
        path = os.path.join(d, MOCK_BUILD)
        if os.path.exists(path):
            return path
    raise FileNotFoundError("mock 이 읽을 %s 가 없다 (%s · %s)"
                            % (MOCK_BUILD, OUTPUTS_DIR, RESULTS_DIR))


def mock_reply(mode):
    """No API: replay Run 1. 'fail' hands back a flow whose second step clicks
    a selector that does not exist, so every attempt dies on screen 2."""
    html = io.open(mock_build_path(), encoding="utf-8").read()
    flow = json.load(io.open(os.path.join(FLOWS_DIR, "restructured.json"),
                             encoding="utf-8"))
    flow["name"] = "auto"
    if mode == "fail":
        flow["steps"][1]["click"] = "[data-action='does-not-exist']"
    text = "```html\n%s\n```\n\n```json\n%s\n```\n" % (
        html, json.dumps(flow, ensure_ascii=False, indent=2))
    return {"text": text, "finish_reason": "stop", "seconds": 0.0, "usage": None,
            "temperature": TEMPERATURE, "seed": SEED,
            "model": None, "system_fingerprint": None}
