r"""모델 호출과, 모델 없이 도는 대역.

키 읽기(load_env) · 실제 호출(call_model) · API 없이 Run 1 을 다시 재생하는
mock_reply 가 여기 있다. 돌려주는 모양은 셋 다 같다:
{"text", "finish_reason", "seconds", "usage"}.
"""
import io
import json
import os
import time

from senior_ui.config import FLOWS_DIR, OUTPUTS_DIR, ROOT


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


class RateLimited(Exception):
    """백오프를 다 쓰고도 429 가 계속된 경우. 설계 실패가 아니라 인프라 한도다."""


def call_model(model, prompt, max_tokens, log=None, backoff=(20, 45, 90, 180)):
    """시도마다 직전 HTML 전체를 다시 보내므로 프롬프트가 크다. 이 계정은 전에
    TPM 30,000 한도에 걸린 적이 있으므로 429 를 지수적으로 기다렸다 다시 친다.
    그래도 안 되면 RateLimited 를 올려 설계 실패와 섞이지 않게 한다."""
    from openai import OpenAI
    from openai import RateLimitError
    client = OpenAI()
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
            )
            break
        except RateLimitError as e:
            last = e
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
    }


def mock_reply(mode):
    """No API: replay Run 1. 'fail' hands back a flow whose second step clicks
    a selector that does not exist, so every attempt dies on screen 2."""
    html = io.open(os.path.join(OUTPUTS_DIR, "restructured_transfer.html"),
                   encoding="utf-8").read()
    flow = json.load(io.open(os.path.join(FLOWS_DIR, "restructured.json"),
                             encoding="utf-8"))
    flow["name"] = "auto"
    if mode == "fail":
        flow["steps"][1]["click"] = "[data-action='does-not-exist']"
    text = "```html\n%s\n```\n\n```json\n%s\n```\n" % (
        html, json.dumps(flow, ensure_ascii=False, indent=2))
    return {"text": text, "finish_reason": "stop", "seconds": 0.0, "usage": None}
