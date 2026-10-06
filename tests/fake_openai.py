r"""openai.OpenAI 의 대역. 실제 API 는 절대 부르지 않는다.

재구성 루프와 확인 명령(--list-models · --probe)은 SDK 의 세 자리만 쓴다.

  client.chat.completions.with_raw_response.create(...)   Chat Completions
  client.responses.with_raw_response.create(...)          Responses API
  client.models.list()                                    모델 목록

with_raw_response 는 응답 헤더(분당 한도)를 읽으려는 것이다. 돌려주는 것은
.headers 와 .parse() 를 가진 물건이다 - SDK 의 LegacyAPIResponse 와 같은 모양.

결과는 outcomes 목록에서 차례로 꺼낸다. 항목은 셋 중 하나다.

  "ok"                  정상 답 (Reply 의 기본값)
  Reply(...)            답의 모양을 손으로 정한다 (잘림 · 생각 토큰 · 응답 모델)
  Exception 인스턴스    그 예외를 올린다 (429 · 400 등, make_error 로 만든다)

보낸 인자는 client.sent 에 (api, kwargs) 로 쌓인다.
"""
import httpx
import openai

GOOD_TEXT = "OK"

# 실제 응답 헤더의 이름 그대로 (https://developers.openai.com/api/docs/guides/rate-limits)
HEADERS = {"x-ratelimit-limit-tokens": "30000",
           "x-ratelimit-remaining-tokens": "29000",
           "x-ratelimit-limit-requests": "500",
           "x-ratelimit-remaining-requests": "499",
           "x-request-id": "req_fake"}


class Reply:
    """정상 답 하나. Chat 과 Responses 에서 같은 값을 각자의 모양으로 낸다."""

    def __init__(self, text=GOOD_TEXT, prompt=100, completion=10, reasoning=None,
                 model="gpt-fake-2026-01-01", truncated=False, headers=None):
        self.text, self.prompt, self.completion = text, prompt, completion
        self.reasoning, self.model, self.truncated = reasoning, model, truncated
        self.headers = dict(HEADERS if headers is None else headers)

    def chat(self):
        details = None
        if self.reasoning is not None:
            details = _obj(reasoning_tokens=self.reasoning)
        msg = _obj(content=self.text)
        return _obj(
            choices=[_obj(message=msg,
                          finish_reason="length" if self.truncated else "stop")],
            usage=_obj(prompt_tokens=self.prompt, completion_tokens=self.completion,
                       completion_tokens_details=details),
            model=self.model, system_fingerprint="fp_fake")

    def responses(self):
        return _obj(
            output_text=self.text,
            status="incomplete" if self.truncated else "completed",
            incomplete_details=_obj(reason="max_output_tokens") if self.truncated else None,
            usage=_obj(input_tokens=self.prompt, output_tokens=self.completion,
                       output_tokens_details=_obj(reasoning_tokens=self.reasoning or 0)),
            model=self.model)


def _obj(**kw):
    return type("Obj", (), kw)()


class Raw:
    """SDK 의 LegacyAPIResponse 처럼 .headers 와 .parse() 를 가진다."""

    def __init__(self, parsed, headers):
        self._parsed = parsed
        self.headers = httpx.Headers(headers)

    def parse(self):
        return self._parsed


def make_error(cls, message, status, body=None, headers=None):
    """SDK 가 올리는 것과 같은 예외. code · param 은 body 에서 읽힌다."""
    req = httpx.Request("POST", "https://api.openai.com/v1/fake")
    resp = httpx.Response(status, request=req, headers=headers or {})
    return cls(message, response=resp, body=body)


def too_large(limit, requested, model="gpt-fake"):
    """요청 하나가 분당 한도보다 크다는 429."""
    return make_error(
        openai.RateLimitError,
        "Error code: 429 - Request too large for %s in organization org-x on tokens "
        "per min (TPM): Limit %d, Requested %d. The input or output tokens must be "
        "reduced in order to run successfully." % (model, limit, requested), 429)


def unsupported(param, code="unsupported_parameter", value=None):
    """추론형 모델이 temperature 같은 인자를 거절하는 400."""
    if code == "unsupported_value":
        msg = ("Unsupported value: '%s' does not support %s with this model. Only the "
               "default (1) value is supported." % (param, value))
    else:
        msg = "Unsupported parameter: '%s' is not supported with this model." % param
    body = {"message": msg, "type": "invalid_request_error", "param": param,
            "code": code}
    return make_error(openai.BadRequestError, "Error code: 400 - %s" % body, 400, body)


class _Endpoint:
    def __init__(self, client, api):
        self.client, self.api = client, api
        self.with_raw_response = self

    def create(self, **kw):
        self.client.sent.append((self.api, dict(kw)))
        out = self.client.outcomes.pop(0) if self.client.outcomes else "ok"
        if isinstance(out, Exception):
            raise out
        reply = Reply() if out == "ok" else out
        parsed = reply.chat() if self.api == "chat" else reply.responses()
        return Raw(parsed, reply.headers)


class _Models:
    def __init__(self, ids):
        self.ids = ids

    def list(self):
        return [_obj(id=i, created=1700000000, owned_by="system") for i in self.ids]


class FakeClient:
    def __init__(self, outcomes=None, model_ids=()):
        self.outcomes = list(outcomes or [])
        self.sent = []
        self.chat = _obj(completions=_Endpoint(self, "chat"))
        self.responses = _Endpoint(self, "responses")
        self.models = _Models(list(model_ids))


def install(monkeypatch, outcomes=None, model_ids=()):
    """openai.OpenAI 를 바꿔 끼운다. 만들어진 대역을 돌려준다."""
    client = FakeClient(outcomes, model_ids)
    monkeypatch.setattr(openai, "OpenAI", lambda *a, **kw: client)
    return client
