r"""모델 호출과, 모델 없이 도는 대역.

키 읽기(load_env) · 실제 호출(call_model) · API 없이 Run 1 을 다시 재생하는
mock_reply 가 여기 있다. 돌려주는 모양은 셋 다 같다:
{"text", "finish_reason", "seconds", "usage"}.
"""
import io
import json
import math
import os
import re
import time

from senior_ui.audit.flow import original_truth
from senior_ui.config import FLOWS_DIR, OUTPUTS_DIR, RESULTS_DIR, ROOT, outputs_dir


ENVS = ".envs"


def read_envs(path):
    """.envs 의 줄들. utf-8-sig 로 읽는다.

    BOM 을 떼는 이유는 메모장이다. Windows 의 메모장이 UTF-8 로 저장하면 파일이
    BOM 으로 시작하고, utf-8 로 읽으면 첫 줄의 키 이름이 '﻿OPENAI_API_KEY'
    가 된다 - 키는 파일에 분명히 있는데 "no OPENAI_API_KEY" 로 끝난다. 그 한
    글자는 눈에 보이지도 않는다.

    cp949 로 저장된 파일은 읽을 수 없다. 역추적만 남기면 무슨 파일이 문제인지도
    알 수 없으므로 어느 파일을 어떻게 저장해야 하는지로 바꿔 올린다.
    """
    try:
        return io.open(path, encoding="utf-8-sig").read().splitlines()
    except UnicodeDecodeError as e:
        raise RuntimeError(
            "%s 를 UTF-8 로 읽지 못했다 (%s 번째 바이트). 이 파일은 UTF-8 로 "
            "저장해야 한다 - 메모장이면 '다른 이름으로 저장'에서 인코딩을 "
            "UTF-8 로 고른다." % (path, e.start))


def load_env():
    """OPENAI_API_KEY from .envs if the environment does not have it. The file
    is KEY=value lines, quotes optional, '#' comments."""
    if os.environ.get("OPENAI_API_KEY"):
        return
    path = os.path.join(ROOT, ENVS)
    if not os.path.exists(path):
        return
    for line in read_envs(path):
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


# --------------------------------------------------------------------------- #
# 모델마다 부르는 방식
# --------------------------------------------------------------------------- #
# gpt-4o 뒤의 모델(o 계열 · gpt-5 이후)은 대부분 "추론형" 이다. 부르는 방식에서
# 달라지는 것은 넷이다 (출처는 docs/README.md 의 "모델 바꾸기").
#
#   길이 인자    Chat Completions 는 max_completion_tokens, Responses API 는
#                max_output_tokens. 옛 max_tokens 는 추론형이 거절한다. 어느
#                쪽이든 **생각(reasoning) 토큰을 포함한** 출력 상한이다.
#   temperature  추론형은 보내면 400 이다 (값이 0 이면 unsupported_value, 아예
#                못 받으면 unsupported_parameter). 추론형에는 보내지 않는다.
#   seed         Chat Completions 에만 있다 (Responses 에는 인자가 없다).
#   API          Chat Completions 에 없는 모델(…-pro · codex · deep-research)은
#                Responses API 로만 부를 수 있다.
#
# 그 밖의 추론형은 Chat Completions 로 부른다. OpenAI 는 추론형에 Responses 를
# 권하지만, 이 도구의 호출은 한 번 묻고 한 번 받는 것이라 Responses 가 이어 주는
# 생각 항목을 쓸 일이 없고, Chat 으로 두면 gpt-4o 실행과 같은 모양(finish_reason ·
# seed · system_fingerprint)으로 기록이 남는다. --api responses 로 바꿀 수 있다.
#
# 표에 없는 모델은 gpt-4o 처럼 부르고 run.log 에 경고를 쓴다. 거절된 인자는
# 빼고 다시 보낸다 (DROPPABLE) - 400 은 요금이 없다.
GPT_4O_WAY = {"api": "chat", "reasoning": False, "temperature": True, "seed": True}
REASONING_CHAT = {"api": "chat", "reasoning": True, "temperature": False, "seed": True}
REASONING_RESPONSES = {"api": "responses", "reasoning": True, "temperature": False,
                       "seed": False}

# (이름 정규식, 계열, 방식). 위에서부터 처음 맞는 것을 쓴다.
FAMILIES = [
    # Chat Completions: Not supported - Responses API 에만 있다.
    (r"^o\d+(-mini)?-(pro|deep-research)", "o-responses-only", REASONING_RESPONSES),
    (r"^gpt-\d+(\.\d+)?-pro", "gpt-pro", REASONING_RESPONSES),
    (r"codex", "codex", REASONING_RESPONSES),
    (r"^computer-use", "computer-use", REASONING_RESPONSES),
    # 지금 쓰는 모델과 같은 방식
    (r"^(gpt-4o|chatgpt-4o|gpt-4\.1)", "gpt-4o", GPT_4O_WAY),
    # 추론형 (o1 · o3 · o4-mini · gpt-5 이후). gpt-5-chat-latest 처럼 이름에 -chat
    # 이 붙은 것은 추론형인지 확인하지 못해 표에 넣지 않는다 (모르는 모델로 부른다).
    (r"^o\d", "o-series", REASONING_CHAT),
    (r"^gpt-([5-9]|\d\d)(?!.*-chat)", "gpt-5+", REASONING_CHAT),
]

# 추론형이 거절할 수 있는, 빼도 요청의 뜻이 바뀌지 않는 인자들. 이것 말고 다른
# 인자를 거절하면 (messages · 길이 인자 등) 다시 보내도 같으므로 ApiRejected 다.
DROPPABLE = ("temperature", "seed", "reasoning_effort", "reasoning", "top_p")
UNSUPPORTED = ("unsupported_parameter", "unsupported_value")

# 생각에 쓸 노력. SDK 의 ReasoningEffort 와 같은 값들이다. 모델마다 받는 값과
# 기본값이 다르다 (gpt-5 는 minimal~high · 기본 medium, gpt-5.1 은 기본 none,
# gpt-6.1-sol 은 none 이 없다). call_model 은 받은 것만 보낸다. 재구성 루프는
# 추론형이면 주지 않아도 config.DEFAULT_REASONING_EFFORT 를 넘긴다 - 모델의
# 기본값에 맡기면 그 값이 기록에 남지 않는다 (loop.effort_choice).
REASONING_EFFORTS = ["none", "minimal", "low", "medium", "high", "xhigh", "max"]
APIS = ["auto", "chat", "responses"]


def profile_for(name, api=None):
    """그 모델을 어떻게 부를지. 표(FAMILIES)에 없으면 gpt-4o 방식에 known=False.

    api 를 주면("chat" · "responses") 표의 API 를 덮는다. Responses 에는 seed 가
    없으므로 그때는 seed 를 보내지 않는다."""
    family, way = None, GPT_4O_WAY
    for pattern, fam, w in FAMILIES:
        if re.search(pattern, name or ""):
            family, way = fam, w
            break
    p = dict(way, family=family, known=family is not None)
    if api and api != "auto":
        p["api"] = api
    if p["api"] == "responses":
        p["seed"] = False
    p["length_param"] = ("max_output_tokens" if p["api"] == "responses"
                         else "max_completion_tokens")
    enc, fallback = encoding_for(name)
    p["encoding"] = (enc + "(대체)") if (enc and fallback) else enc
    return p


def describe(p):
    """run.log 와 확인 명령에 쓰는 한 줄."""
    return ("%s · %s · 길이 인자 %s · temperature %s · seed %s"
            % (p["api"], "추론형" if p["reasoning"] else "추론형 아님",
               p["length_param"], "보냄" if p["temperature"] else "안 보냄",
               "보냄" if p["seed"] else "안 보냄"))


# --------------------------------------------------------------------------- #
# 토큰 어림과 분당 한도
# --------------------------------------------------------------------------- #
# tiktoken 이 없을 때의 대비. 이 저장소의 원본 HTML 에서 잰 비율이다 (글자
# 30,966 / o200k 토큰 10,546 = 2.94). 한글이 많은 글일수록 정확하다.
CHARS_PER_TOKEN = 2.9

# tiktoken 이 모르는 모델(gpt-6 계열 등)에 쓰는 인코딩. gpt-4o 이후 OpenAI 모델이
# 모두 이것이다 (tiktoken 0.14 의 표). 대체로 셌다는 사실은 method 에 남는다.
FALLBACK_ENCODING = "o200k_base"


def encoding_for(model):
    """`(인코딩 이름, 대체인가)`. tiktoken 이 없으면 (None, False)."""
    try:
        import tiktoken
    except ImportError:
        return None, False
    if not model:
        return FALLBACK_ENCODING, False
    try:
        return tiktoken.encoding_name_for_model(model), False
    except KeyError:
        return FALLBACK_ENCODING, True


def _encoder(name=FALLBACK_ENCODING):
    """그 인코딩의 토크나이저. tiktoken 이 없거나 사전을 받지 못하면 None."""
    try:
        import tiktoken
        return tiktoken.get_encoding(name)
    except Exception:                                # 설치 안 됨 · 오프라인
        return None


def estimate_tokens(text, model=None):
    """`(토큰 수, 어떻게 셌는가)`. 보내기 전에 로그에 남기려는 것이다.

    인코딩은 그 모델의 것이다 (tiktoken.encoding_name_for_model). tiktoken 이
    모르는 모델이면 o200k_base 로 세고 method 에 "(대체)" 를 붙인다."""
    name, fallback = encoding_for(model)
    enc = _encoder(name) if name else None
    if enc is not None:
        return (len(enc.encode(text or "", disallowed_special=())),
                "tiktoken:%s%s" % (name, "(대체)" if fallback else ""))
    return int(round(len(text or "") / CHARS_PER_TOKEN)), "chars/%s" % CHARS_PER_TOKEN


# 요청 하나가 분당 한도보다 크면 429 의 문구가 "Request too large … Limit N,
# Requested M" 이다. 분당 한도는 입력에 max_tokens 를 더해 세므로, 재시도처럼
# 입력이 2만을 넘는 프롬프트에 14,000 을 붙이면 이렇게 된다. 기다려도 풀리지
# 않는다 - 줄여서 보내야 한다. 길이 인자의 이름(max_completion_tokens ·
# max_output_tokens)과 상관없이 같은 상한이다.
TOO_LARGE = re.compile(r"Request too large.*?Limit (\d+), Requested (\d+)", re.S)
# 줄여도 이보다 작으면 보내지 않는다. 답(HTML + 흐름 명세)이 이보다 짧은 적이
# 없다 - 자동 Run 4·5 의 답이 3,300~3,500 토큰이었다. 더 줄이면 잘린 답만 온다.
# 추론형은 생각 토큰도 이 안에서 쓰므로 실제로는 더 많이 필요하다.
MIN_COMPLETION = 4000
# 한도에 꼭 맞추지 않고 남겨 두는 몫. 서버가 세는 입력이 우리 어림과 조금 다르다.
MARGIN = 500


def shrink_for_minute(message, cap, log=None):
    """요청 하나가 분당 한도보다 크다는 429 이면 줄인 max_tokens 를, 아니면 None.

    줄여도 MIN_COMPLETION 에 못 미치면 RateLimited 를 바로 올린다 - 기다리는
    동안 풀릴 일이 아니므로 백오프를 다 쓰고 멈추는 것은 몇 분을 버릴 뿐이다.
    """
    m = TOO_LARGE.search(message or "")
    if not m:
        return None
    limit, requested = int(m.group(1)), int(m.group(2))
    if requested <= limit:
        return None
    smaller = cap - (requested - limit) - MARGIN
    if smaller < MIN_COMPLETION:
        raise RateLimited(
            "요청 하나가 분당 한도보다 크다 (한도 %d, 요청 %d). max_tokens 를 %d 까지 "
            "줄여야 하는데 답에 필요한 %d 보다 작다 - 기다려도 풀리지 않는다. 입력을 "
            "줄이거나 한도가 큰 계정이 필요하다." % (limit, requested, smaller,
                                                MIN_COMPLETION))
    if log:
        log("429 — 요청 하나가 분당 한도보다 크다 (한도 %d, 요청 %d). max_tokens 를 "
            "%d → %d 로 줄여 바로 다시 보낸다" % (limit, requested, cap, smaller))
    return smaller


def price_for(model):
    """그 모델의 100만 토큰당 가격 {"input", "output"}. 표에 없거나 비었으면 None."""
    from senior_ui import config
    return config.MODEL_PRICES.get(model) or None


def cost_usd(usage, price):
    """호출 하나의 예상 금액. 가격이나 usage 를 모르면 None."""
    if not price or not usage or usage.get("prompt") is None \
            or usage.get("completion") is None:
        return None
    return (usage["prompt"] * price["input"]
            + usage["completion"] * price["output"]) / 1e6


# 분당 한도를 알려 주는 응답 헤더 (https://developers.openai.com/api/docs/guides/rate-limits).
# 모델마다 · 계정 등급마다 다르고 문서의 표가 실제와 다를 수 있으므로, 실제
# 호출이 받은 값을 남긴다. 이 계정은 gpt-4o 에서 분당 30,000 토큰이었다.
RATELIMIT_HEADERS = [("limit_tokens", "x-ratelimit-limit-tokens"),
                     ("remaining_tokens", "x-ratelimit-remaining-tokens"),
                     ("limit_requests", "x-ratelimit-limit-requests")]


def read_ratelimit(headers):
    """응답 헤더의 분당 한도. 셋 다 없으면 None (모른다)."""
    out = {}
    for key, name in RATELIMIT_HEADERS:
        v = (headers or {}).get(name)
        out[key] = int(v) if v is not None and str(v).isdigit() else v
    return out if any(v is not None for v in out.values()) else None


def describe_ratelimit(rl):
    """run.log 와 확인 명령에 쓰는 한 줄."""
    if not rl:
        return "응답 헤더에 없음"
    return ("토큰 %s (남은 %s) · 요청 %s"
            % (rl.get("limit_tokens"), rl.get("remaining_tokens"),
               rl.get("limit_requests")))


def wait_for_tokens(rl, need, elapsed):
    """다음 요청 전에 기다릴 초 (정수). 기다릴 일이 없거나 모르면 0.

    rl 은 직전 응답 헤더의 분당 한도(read_ratelimit), need 는 다음 요청이
    한도에서 먹을 양(예상 입력 + max_tokens), elapsed 는 그 헤더를 받은 뒤 지난
    초다. 분당 한도는 1분에 걸쳐 고르게 다시 찬다고 보고(초당 한도/60), 그동안
    찬 몫을 더한 남은 양이 need 보다 적을 때만 모자란 만큼 기다린다.

    need 가 한도보다 크면 기다려도 들어가지 않는다 - 다 찰 때까지만 기다리고
    나머지는 shrink_for_minute 이 맡는다. 그래서 60초를 넘지 않는다."""
    limit = (rl or {}).get("limit_tokens")
    left = (rl or {}).get("remaining_tokens")
    if not isinstance(limit, int) or not isinstance(left, int) or limit <= 0:
        return 0
    per_sec = limit / 60.0
    now = min(limit, left + elapsed * per_sec)
    short = min(need, limit) - now
    if short <= 0:
        return 0
    return int(math.ceil(short / per_sec))


# --------------------------------------------------------------------------- #
# 그림 (화면 스크린샷)
# --------------------------------------------------------------------------- #
# 프롬프트는 글 하나로 만들고, 그림이 들어갈 자리에 IMAGE_MARK 를 한 번 둔다
# (prompt.shots_section). 보낼 때 그 자리에서 글을 가르고 "이름표 글 + 그림" 을
# 차례로 끼운다 - 그림마다 바로 앞에 화면 이름이 온다. 기록(attempt_N.*prompt.txt)
# 에는 그림 대신 파일 경로 줄을 적는다 (prompt_record).
#
# 그림 하나는 {"label": 이름표, "path": PNG 경로} 다. 이 도구가 찍는 그림은
# 모두 PNG 이고, 크기는 파일 머리에서 읽는다 (Pillow 없이).
IMAGE_MARK = "[[그림 자리 - 도구가 이 자리에 그림을 끼운다]]"


PNG_MAGIC = bytes([0x89]) + b"PNG" + bytes([13, 10, 26, 10])


def png_size(path):
    """`(폭, 높이)`. PNG 가 아니면 ValueError."""
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] != PNG_MAGIC:
        raise ValueError("PNG 가 아니다: %s" % path)
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


def image_rule(model):
    """그 모델의 그림 토큰 규칙 (config.IMAGE_TOKENS). 표에 없으면 기본 규칙에
    known=False."""
    from senior_ui import config
    rule = config.IMAGE_TOKENS.get(model)
    if rule:
        return dict(rule, known=True)
    return dict(config.IMAGE_TOKENS_DEFAULT, known=False)


def image_tokens(width, height, model):
    """`(토큰, 어떻게 셌는가)`. 보내기 전 어림이다 - 실측은 usage 로 안다.

    패치 방식 (gpt-5.4 이후 · gpt-6-astra): 32px 패치 수 x 배수. 패치가 상한을
    넘으면 상한에 맞게 줄인 크기로 다시 센다. 타일 방식 (gpt-4o · gpt-4.1 ·
    gpt-5.1): 2048 정사각형 안으로 줄이고, 짧은 변이 768 을 넘으면 768 로 줄인
    뒤 512px 타일 수 x 타일 토큰 + 기본 토큰. 작은 그림은 키우지 않는다.
    출처: OpenAI 비전 안내 (2026-10-06 확인)."""
    rule = image_rule(model)
    w, h = float(width), float(height)
    if rule["method"] == "patch":
        patches = math.ceil(w / 32) * math.ceil(h / 32)
        if patches > rule["budget"]:
            k = math.sqrt(32 * 32 * rule["budget"] / (w * h))
            w, h = math.floor(w * k), math.floor(h * k)
            patches = min(rule["budget"], math.ceil(w / 32) * math.ceil(h / 32))
        tokens = int(math.ceil(patches * rule["multiplier"]))
        how = "patch x%s" % rule["multiplier"]
    else:
        if max(w, h) > 2048:
            k = 2048 / max(w, h)
            w, h = w * k, h * k
        if min(w, h) > 768:
            k = 768 / min(w, h)
            w, h = w * k, h * k
        tiles = math.ceil(math.floor(w) / 512) * math.ceil(math.floor(h) / 512)
        tokens = rule["base"] + tiles * rule["tile"]
        how = "tile %d+%d" % (rule["base"], rule["tile"])
    if not rule["known"]:
        how += " (표에 없는 모델 - 기본 규칙)"
    elif rule.get("estimated"):
        how += " (추정)"
    return tokens, how


def describe_images(images, model):
    """그림들의 `{"count", "estimated", "method", "sizes"}`. 없으면 count 0."""
    total, how, sizes = 0, None, []
    for img in images or []:
        w, h = png_size(img["path"])
        t, how = image_tokens(w, h, model)
        total += t
        sizes.append([w, h])
    return {"count": len(images or []), "estimated": total, "method": how,
            "sizes": sizes}


def _data_url(path):
    import base64
    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")


def image_label(i, n, img):
    return "[그림 %d/%d] %s" % (i, n, img["label"])


def content_parts(prompt, images, api, detail):
    """글과 그림을 그 API 의 content 목록으로. 그림은 IMAGE_MARK 자리에 들어간다.
    자리가 없으면 글 끝에 붙인다."""
    head, mark, tail = prompt.partition(IMAGE_MARK)
    if not mark:
        head, tail = prompt, ""
    text_type = "text" if api == "chat" else "input_text"
    parts = [{"type": text_type, "text": head}]
    for i, img in enumerate(images, 1):
        parts.append({"type": text_type, "text": image_label(i, len(images), img)})
        url = _data_url(img["path"])
        if api == "chat":
            parts.append({"type": "image_url", "image_url": {"url": url, "detail": detail}})
        else:
            parts.append({"type": "input_image", "image_url": url, "detail": detail})
    if tail:
        parts.append({"type": text_type, "text": tail})
    return parts


def model_text(prompt, images):
    """보내는 글만 - 그림 자리에 이름표들. 글 토큰의 어림은 이것으로 센다."""
    labels = "\n".join(image_label(i, len(images), img)
                       for i, img in enumerate(images or [], 1))
    return prompt.replace(IMAGE_MARK, labels)


def prompt_record(prompt, images, model=None, base=None):
    """기록에 남기는 프롬프트. 그림 자리에 그림마다 한 줄 - 이름표 · 파일 · 크기 ·
    예상 토큰. 그림이 없으면 자리 표시를 지운다 (프롬프트는 그대로다). 자리가
    없는 프롬프트에 그림을 보내면 끝에 붙으므로 (content_parts) 기록도 끝에 적는다."""
    if IMAGE_MARK not in prompt:
        if not images:
            return prompt
        prompt = prompt + "\n" + IMAGE_MARK
    lines = []
    for i, img in enumerate(images or [], 1):
        w, h = png_size(img["path"])
        t, _how = image_tokens(w, h, model)
        path = (os.path.relpath(img["path"], base).replace(os.sep, "/") if base
                else img["path"])
        lines.append("%s  <그림: %s %dx%d · 예상 %d토큰>"
                     % (image_label(i, len(images), img), path, w, h, t))
    return prompt.replace(IMAGE_MARK, "\n".join(lines))


def request_kwargs(model, prompt, cap, profile, temperature=None, seed=None,
                   reasoning_effort=None, images=None, detail=None):
    """그 모델의 방식대로 만든 요청 인자. 그림이 있으면 content 를 목록으로
    보낸다 (글 · 이름표 · 그림 …). 없으면 전과 같이 글 하나다."""
    chat = profile["api"] == "chat"
    kw = {"model": model}
    if images:
        from senior_ui import config
        content = content_parts(prompt, images, profile["api"],
                                detail or config.IMAGE_DETAIL)
    else:
        content = prompt.replace(IMAGE_MARK, "")
    if chat:
        kw["messages"] = [{"role": "user", "content": content}]
    elif images:
        kw["input"] = [{"role": "user", "content": content}]
    else:
        kw["input"] = content
    kw[profile["length_param"]] = cap
    if profile["temperature"] and temperature is not None:
        kw["temperature"] = temperature
    if profile["seed"] and seed is not None:
        kw["seed"] = seed
    if profile["reasoning"] and reasoning_effort:
        if chat:
            kw["reasoning_effort"] = reasoning_effort
        else:
            kw["reasoning"] = {"effort": reasoning_effort}
    return kw


def droppable(e, kw):
    """400 이 "이 모델은 그 인자를 받지 않는다" 이고 빼도 되는 인자면 그 이름."""
    param = (getattr(e, "param", None) or "").split(".")[0]
    if getattr(e, "code", None) in UNSUPPORTED and param in DROPPABLE and param in kw:
        return param
    return None


def read_reply(resp, api):
    """SDK 의 응답을 `(text, finish_reason, status, usage, fingerprint)` 로.

    잘림 판정은 API 마다 다르다. Chat 은 finish_reason == "length", Responses 는
    status == "incomplete" 에 incomplete_details.reason == "max_output_tokens".
    루프는 "length" 하나만 보므로 Responses 의 것을 거기에 맞춘다. 추론형은 생각이
    한도를 다 쓰면 보이는 답이 빈 채로 잘려 온다."""
    u = getattr(resp, "usage", None)
    if api == "responses":
        status = getattr(resp, "status", None)
        reason = getattr(getattr(resp, "incomplete_details", None), "reason", None)
        if status == "completed":
            finish = "stop"
        elif status == "incomplete":
            finish = "length" if reason == "max_output_tokens" else (reason or status)
        else:
            finish = status
        details = getattr(u, "output_tokens_details", None)
        usage = {"prompt": getattr(u, "input_tokens", None),
                 "completion": getattr(u, "output_tokens", None),
                 "reasoning": getattr(details, "reasoning_tokens", None)} if u else None
        return (getattr(resp, "output_text", "") or "", finish, status, usage, None)
    choice = resp.choices[0]
    details = getattr(u, "completion_tokens_details", None)
    usage = {"prompt": getattr(u, "prompt_tokens", None),
             "completion": getattr(u, "completion_tokens", None),
             "reasoning": getattr(details, "reasoning_tokens", None)} if u else None
    return (choice.message.content or "", choice.finish_reason, None, usage,
            getattr(resp, "system_fingerprint", None))


def call_model(model, prompt, max_tokens, log=None, backoff=(20, 45, 90, 180),
               temperature=TEMPERATURE, seed=SEED, reasoning_effort=None, api=None,
               images=None, detail=None):
    """시도마다 직전 HTML 전체를 다시 보내므로 프롬프트가 크다. 이 계정은 전에
    TPM 30,000 한도에 걸린 적이 있으므로 429 를 지수적으로 기다렸다 다시 친다.
    그래도 안 되면 RateLimited 를 올려 설계 실패와 섞이지 않게 한다.

    429 가운데 "요청 하나가 분당 한도보다 크다" 는 기다려서 풀리지 않으므로
    max_tokens 를 줄여 바로 다시 보낸다 (shrink_for_minute). 둘 다 시도 실패로
    세지 않는다 - 루프는 RateLimited 를 받으면 예산을 깎지 않고 멈춘다.

    모델마다 부르는 방식(profile_for)이 다르다. 모델이 "그 인자는 받지 않는다"
    는 400 을 내면 그 인자를 빼고 바로 다시 보낸다 (DROPPABLE). 뺀 것은 로그와
    돌려주는 dropped 에 남는다.

    429 가 아닌 실패는 ApiRejected 와 InfraFailed 로 갈라 올린다 - 어느 쪽인지는
    여기서만 알 수 있다 (openai 의 예외 종류). 루프는 그 종류만 보고 판단한다."""
    from openai import (OpenAI, APIConnectionError, AuthenticationError,
                        BadRequestError, InternalServerError, NotFoundError,
                        OpenAIError, PermissionDeniedError, RateLimitError)
    profile = profile_for(model, api)
    # 키가 아예 없으면 생성자부터 OpenAIError 다. 그것도 "다시 보내도 같다" 다.
    try:
        client = OpenAI()
    except OpenAIError as e:
        raise ApiRejected("%s: %s" % (type(e).__name__, e))
    endpoint = (client.responses if profile["api"] == "responses"
                else client.chat.completions)
    kw = request_kwargs(model, prompt, max_tokens, profile, temperature, seed,
                        reasoning_effort, images=images, detail=detail)
    t0 = time.time()
    waits, dropped = list(backoff), []
    while True:
        try:
            # 응답 헤더(분당 한도)를 읽으려고 with_raw_response 로 부른다.
            raw = endpoint.with_raw_response.create(**kw)
            resp = raw.parse()
            break
        except RateLimitError as e:
            if log:
                rl = read_ratelimit(getattr(getattr(e, "response", None), "headers", None))
                if rl:
                    log("429 — 분당 한도 %s" % describe_ratelimit(rl))
            smaller = shrink_for_minute(str(e), kw[profile["length_param"]], log)
            if smaller is not None:
                kw[profile["length_param"]] = smaller   # 기다리지 않고 바로 다시 보낸다
                continue
            if not waits:
                raise RateLimited(str(e))
            wait = waits.pop(0)
            if log:
                log("429 — %d초 기다렸다 다시 시도 (%d/%d)"
                    % (wait, len(backoff) - len(waits), len(backoff)))
            time.sleep(wait)
        except BadRequestError as e:
            param = droppable(e, kw)
            if param is None:
                raise ApiRejected("%s: %s" % (type(e).__name__, e))
            del kw[param]
            dropped.append(param)
            if log:
                log("경고: %s 가 지원하지 않는 인자 %s 를 빼고 다시 보낸다 (%s: %s)"
                    % (model, param, e.code, getattr(e, "message", e)))
        except (AuthenticationError, PermissionDeniedError, NotFoundError) as e:
            raise ApiRejected("%s: %s" % (type(e).__name__, e))
        except APIConnectionError as e:          # APITimeoutError 도 이 아래다
            raise InfraFailed("%s: %s" % (type(e).__name__, e))
        except InternalServerError as e:         # 5xx - 공급자 쪽 문제
            raise InfraFailed("%s: %s" % (type(e).__name__, e))
    text, finish, status, usage, fingerprint = read_reply(resp, profile["api"])
    return {
        "text": text,
        "finish_reason": finish,
        "seconds": round(time.time() - t0, 1),
        "usage": usage,
        # 보낸 것과 받은 것을 함께 적는다. --model gpt-4o 로 보내도 실제로
        # 답한 것은 그 별명이 가리키는 어느 판본이고, 그 판본이 바뀌면 같은
        # 프롬프트가 다른 답을 낸다. system_fingerprint 는 그 뒤의 구성이다.
        # 보내지 않은 temperature · seed 는 None 이다 (모델의 기본값이 쓰였다).
        "temperature": kw.get("temperature"),
        "seed": kw.get("seed"),
        "model": getattr(resp, "model", None),
        "system_fingerprint": fingerprint,
        # 실제로 보낸 길이 제한. 분당 한도에 맞추느라 줄였으면 요청한 값과 다르다.
        "max_tokens": kw[profile["length_param"]],
        "api": profile["api"],
        "status": status,
        # 프롬프트를 뺀 실제 요청 인자, 그리고 모델이 거절해 뺀 인자
        "sent": {k: v for k, v in kw.items() if k not in ("messages", "input")},
        # 이 호출에 넣은 그림 수 (화면 스크린샷)
        "images": len(images or []),
        "dropped": dropped,
        # 이 호출이 받은 응답 헤더의 분당 한도
        "ratelimit": read_ratelimit(raw.headers),
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


# --------------------------------------------------------------------------- #
# mock 이 Run 1 빌드에 가하는 바꿔치기
# --------------------------------------------------------------------------- #
# mock 은 API 없이 루프를 돌리는 대역이다. 선택지 데이터를 도구가 넣어 주게 된
# 뒤로는 Run 1 빌드를 그대로 되읽을 수 없다 - 그 빌드는 window.PRESERVED 를 읽지
# 않으므로 형식 검사에서 멈추고, 검사 경로를 한 번도 밟지 못한다. 그래서 은행
# 목록 한 줄을 모드마다 다르게 바꿔 끼운다. 모드들이 **그 한 줄에서만** 다르므로
# 결과가 갈리는 이유가 그 줄 하나로 좁혀진다.
#
# 자리를 찾지 못하면 멈춘다. 조용히 지나가면 "그 경우를 확인했다" 가 거짓이 된다.
BANKS_LINE = ("const BANKS = ['신한','국민','카카오뱅크','농협','우리','하나',"
              "'기업','토스뱅크'];")

# 도구가 넣어 준 데이터를 참조해 전부 그린다 (은행 38 + 증권사 29).
BANKS_ALL = ("const BANKS = window.PRESERVED.BANKS"
             ".concat(window.PRESERVED.SECS);")
# 참조는 하지만 일부만 그린다. 형식 검사는 통과하고 검사 I 에서 떨어진다.
BANKS_SOME = ("const BANKS = window.PRESERVED.BANKS"
              ".concat(window.PRESERVED.SECS).slice(0, 4);")
# 참조하지 않고 직접 네 개를 쓴다. Run 4·5 의 모델이 한 그대로다. 형식 검사에서
# 떨어진다 (검사기까지 가지 않는다).
BANKS_NONE = "const BANKS = ['신한','국민','카카오뱅크','농협'];"

# Run 1 은 옛 원본의 과제(김시현 · 카카오뱅크)로 만든 빌드다. 예금주 조회를
# 흉내 내는 두 자리가 받는 사람 이름을 박아 두었는데, 검사는 지금 원본의 정답
# (flows/original.json 의 truth)으로 하므로 그대로 두면 검사 B 가 모든 모드에서
# 이름 두 곳을 잡는다. 모드와 상관없는 차이이므로 다섯 모드 모두 바꿔 끼운다.
NAME_SWAP = ("S.name='김시현'", "S.name='김철수'")

# 원본에 있고 Run 1 빌드에는 없는 두 값 - 금액 숫자판의 '00' 과 빠른 금액의
# '전액'. 이것을 채워 두면 검사 I 의 결과가 은행 목록 하나로만 갈린다. 채우지
# 않으면 "전부 그린 응답" 도 다른 두 누락 때문에 떨어져서, 통과하는 모습을 볼 수
# 없다. 채우는 방법이 둘이다.
#
#   markup  두 값을 마크업에 직접 쓴다. 값이 하나도 빠지지 않았으므로 배열을
#           읽지 않아도 형식 검사를 지난다 (reply.preserved_problems).
#   arrays  숫자판과 빠른 금액을 도구가 넣어 준 배열(AMT_KEYS · QUICK)을 읽어
#           그린다. 원본의 숫자판이 배열이 된 뒤의, 지시대로 한 답이다.
PAD_MARKUP = [
    ('<button disabled></button><button data-action="amt-num" data-v="0">0</button>',
     '<button data-action="amt-num" data-v="00">00</button>'
     '<button data-action="amt-num" data-v="0">0</button>'),
    ('<button data-action="amt-set" data-v="100000">10만원</button>',
     '<button data-action="amt-set" data-v="100000">10만원</button>'
     '<button data-action="amt-set" data-v="all">전액</button>'),
]

AMT_ROWS = [
    '<button data-action="amt-num" data-v="1">1</button><button data-action="amt-num" '
    'data-v="2">2</button><button data-action="amt-num" data-v="3">3</button>',
    '<button data-action="amt-num" data-v="4">4</button><button data-action="amt-num" '
    'data-v="5">5</button><button data-action="amt-num" data-v="6">6</button>',
    '<button data-action="amt-num" data-v="7">7</button><button data-action="amt-num" '
    'data-v="8">8</button><button data-action="amt-num" data-v="9">9</button>',
    '<button disabled></button><button data-action="amt-num" data-v="0">0</button>'
    '<button class="word" data-action="amt-del">지우기</button>',
]
QUICK_ROWS = ['<button data-action="amt-set" data-v="%s">%s</button>' % (v, t)
              for v, t in (("10000", "1만원"), ("30000", "3만원"),
                           ("50000", "5만원"), ("100000", "10만원"))]
PAD_ARRAYS = (
    [(row, "") for row in AMT_ROWS[:3]]
    + [(AMT_ROWS[3], '<span id="mock-amt-pad"></span>')]
    + [(row, "") for row in QUICK_ROWS[:3]]
    + [(QUICK_ROWS[3], '<span id="mock-quick"></span>')]
    + [("else if(a==='amt-set'){ S.amount=el.dataset.v; renderAmount(); }",
        "else if(a==='amt-set'){ S.amount=el.dataset.v==='all' ? '100000' : "
        "el.dataset.v; renderAmount(); }"),
       ("</script>",
        "document.getElementById('mock-amt-pad').outerHTML = "
        "window.PRESERVED.AMT_KEYS.map(v=>'<button data-action=\"amt-num\" "
        "data-v=\"'+v+'\">'+v+'</button>').join('') + "
        "'<button class=\"word\" data-action=\"amt-del\">지우기</button>';\n"
        "document.getElementById('mock-quick').outerHTML = "
        "window.PRESERVED.QUICK.map(v=>'<button data-action=\"amt-set\" "
        "data-v=\"'+v+'\">'+(v==='all' ? '전액' : (v/10000)+'만원')+'</button>')"
        ".join('');\n</script>")])
PADS = {None: [], "markup": PAD_MARKUP, "arrays": PAD_ARRAYS}

# Run 1 에는 오류 처리가 없다 - 틀린 계좌번호도 틀린 은행도 그대로 보낸다.
# 원본의 두 오류(flows/original.json 의 error_paths)를 같은 화면 안의 안내 글로
# 알리게 바꿔 끼운다. 새 화면을 만들지 않으므로 계획(MOCK_PLAN)의 화면은 그대로다.
#
#   wrong-account  계좌 화면 [다음] 에서 정답 계좌가 아니면 그 화면 아래에 알리고
#                  머무른다. 숫자를 지우면 안내가 사라진다.
#   wrong-bank     확인 화면 [보내기] 에서 정답 은행이 아니면 그 화면에 알리고
#                  머무른다. [고치기] 로 계좌 화면에 돌아간다.
#
# 정답은 원본 HTML 이 가진 것(ANSWER_ACCOUNT · ANSWER_BANK)과 같은 값이다 - 모델도
# 원본에서 그것을 읽는다. 틀린 값(truth 의 ACCOUNT_WRONG · BANK_WRONG)은 쓰지 않는다.
def error_swaps():
    t = original_truth()
    clear = "document.getElementById('mock-acc-err').textContent=''; "
    return [
        ('<div class="count" id="acc-count">아직 누르지 않았습니다</div>',
         '<div class="count" id="acc-count">아직 누르지 않았습니다</div>\n'
         '    <div class="count" id="mock-acc-err"></div>'),
        ('<div class="fee">수수료 없음</div>',
         '<div class="fee">수수료 없음</div>\n'
         '    <div class="fee" id="mock-bank-err"></div>'),
        ("else if(a==='acc-num'){ if(S.acc.length<16){ S.acc+=el.dataset.v; renderAcc(); } }",
         "else if(a==='acc-num'){ if(S.acc.length<16){ S.acc+=el.dataset.v; renderAcc(); } "
         + clear + "}"),
        ("else if(a==='acc-del'){ S.acc=S.acc.slice(0,-1); renderAcc(); }",
         "else if(a==='acc-del'){ S.acc=S.acc.slice(0,-1); renderAcc(); " + clear + "}"),
        ("    if(S.acc.length<10) return;\n",
         "    if(S.acc.length<10) return;\n"
         "    if(S.acc!=='%s'){ document.getElementById('mock-acc-err').textContent="
         "'계좌번호가 맞지 않습니다. 받는 분 계좌번호를 다시 확인해 주세요.'; return; }\n"
         % t["ACCOUNT"]),
        ("  else if(a==='send'){\n",
         "  else if(a==='send'){\n"
         "    if(S.bank!=='%s'){ document.getElementById('mock-bank-err').textContent="
         "'받는 분의 은행이 맞지 않습니다. [고치기]를 눌러 은행을 다시 골라 주세요.'; "
         "return; }\n" % t["BANK"]),
        ("  else if(a==='edit-who'){ S.saved ? show('who') : show('accno'); }",
         "  else if(a==='edit-who'){ document.getElementById('mock-bank-err').textContent=''; "
         "S.saved ? show('who') : show('accno'); }"),
    ]


# 위 오류 처리를 걷는 오류 경로. 흐름은 Run 1 의 것(flows/restructured.json)이다.
MOCK_ERROR_PATHS = [
    {"id": "wrong-account", "from_step": "accno",
     "inputs": [{"type": "{ACCOUNT_WRONG}",
                 "key": "[data-action='acc-num'][data-v='%s']"},
                {"click": "#acc-next"}],
     "expect_screen": "accno", "expect_text_any": ["계좌번호"],
     "recover": [{"click": "[data-action='acc-del']"}], "back_to": "accno"},
    {"id": "wrong-bank", "from_step": "accno",
     "inputs": [{"type": "{ACCOUNT}", "key": "[data-action='acc-num'][data-v='%s']"},
                {"click": "#acc-next"},
                {"click": "[data-action='bank-other']"}, {"wait": 0.2},
                {"click": "[data-action='pick-bank'][data-bank='{BANK_WRONG}']"},
                {"click": "[data-action='who-yes']"},
                {"type": "{AMOUNT}", "key": "[data-action='amt-num'][data-v='%s']"},
                {"click": "#amt-next"},
                {"click": "[data-action='send']"}],
     "expect_screen": "review", "expect_text_any": ["은행"],
     "recover": [{"click": "[data-action='edit-who']"}], "back_to": "accno"},
]

# 오류를 어떻게 다루는가 - (HTML 에 오류 처리를 넣는가, 흐름에 오류 경로를 적는가)
ERRORS = {"handled": (True, True),
          # 오류 경로는 적었지만 HTML 은 Run 1 그대로 - 틀린 값으로 넘어간다.
          "unhandled": (False, True),
          # 둘 다 없다 - Run 1 그대로.
          "undeclared": (False, False)}

# (은행 목록 한 줄, 원본에 있고 Run 1 에 없는 두 값을 채우는 방법, 흐름을 깨뜨리는가,
#  오류 처리)
MOCKS = {
    # Run 1 을 되읽는다. 목록과 숫자판·빠른 금액을 도구가 넣은 배열에서 그리고,
    # 두 오류를 같은 화면에서 알린다. 지시대로 한 답이고, 통과해야 한다.
    "pass": (BANKS_ALL, "arrays", False, "handled"),
    # 둘째 걸음이 없는 선택자를 클릭한다 - 모든 시도가 화면 2에서 죽는다.
    "fail": (BANKS_ALL, "arrays", True, "handled"),
    # 목록은 참조하고 두 값은 마크업에 직접 썼다. 통과해야 한다.
    "preserved-all": (BANKS_ALL, "markup", False, "handled"),
    # 참조는 했지만 일부만 그렸다. 검사 I 에서 떨어져야 한다.
    "preserved-some": (BANKS_SOME, "markup", False, "handled"),
    # 참조하지 않고 직접 썼다. 형식 검사에서 떨어져야 한다.
    "preserved-none": (BANKS_NONE, "markup", False, "handled"),
    # pass 에서 오류 처리와 오류 경로를 모두 뺐다 (Run 1 그대로). 형식 검사가
    # 빠진 오류 경로를 잡는다 - 검사기까지 가지 않는다.
    "errors-undeclared": (BANKS_ALL, "arrays", False, "undeclared"),
    # 오류 경로는 적었지만 HTML 에 오류 처리가 없다. 형식 검사는 지나고, 검사 J
    # 가 "틀린 값으로 다음 화면에 넘어갔다" 로 잡는다.
    "errors-unhandled": (BANKS_ALL, "arrays", False, "unhandled"),
    # 은행 목록을 처음에는 6개만 그리고 [전체 보기] 를 눌러야 나머지를 그린다.
    # 흐름 명세의 reveal 에 그 조작을 적었다 - 통과해야 한다.
    "reveal": (BANKS_ALL, "arrays", False, "handled"),
    # 같은 HTML 인데 reveal 을 적지 않았다. 검사 I 에서 떨어져야 한다.
    "reveal-undeclared": (BANKS_ALL, "arrays", False, "handled"),
    # 과제 밖 입구(tasks/transfer.json 의 entrances)를 [다른 메뉴] 를 눌러야 그리는
    # 설계. 흐름 명세의 reveal 에 그 조작을 적었다 - 통과해야 한다 (검사 K).
    "entrances-reveal": (BANKS_ALL, "arrays", False, "handled"),
    # 입구를 접힌 블록(<details>)에 넣고, 펼치는 조작을 reveal 에 적었다 - 통과해야 한다.
    "entrances-folded": (BANKS_ALL, "arrays", False, "handled"),
    # 입구를 모두 지운 빌드 - Run 1 그대로 (예비 실행 20261006-215902 처럼 "돈 보내기"
    # 만 남았다). 검사 K 에서 떨어져야 한다.
    "entrances-none": (BANKS_ALL, "arrays", False, "handled"),
}
# 펼치기 설계를 쓰는 모드와, 흐름 명세에 reveal 을 적는가.
REVEAL_MODES = {"reveal": True, "reveal-undeclared": False}
# 은행 목록을 6개 + [전체 보기] 로 그리는 고침. Run 1 의 fillBankList 와 클릭 처리기.
REVEAL_SWAPS = [
    ("  const list=BANKS.filter(n=>!filter || n.indexOf(filter)>-1);",
     "  const found=BANKS.filter(n=>!filter || n.indexOf(filter)>-1);\n"
     "  const list=(filter || S.allBanks) ? found : found.slice(0, 6);"),
    ("    '<span>'+n+'</span></button>').join('');",
     "    '<span>'+n+'</span></button>').join('') +\n"
     "    ((filter || S.allBanks) ? '' : '<button class=\"bankrow\" "
     "data-action=\"show-all-banks\" id=\"show-all-banks\">전체 보기</button>');"),
    ("  else if(a==='bank-other'){",
     "  else if(a==='show-all-banks'){ S.allBanks=true; fillBankList(''); }\n"
     "  else if(a==='bank-other'){"),
]
# reveal 모드의 흐름 명세에 더하는 펼치기 조작. bank 화면에서 [다른 은행이에요] 로
# 목록을 열고 [전체 보기] 를 누른다.
MOCK_REVEAL = {"pick-bank": {"at": "bank", "do": [
    {"click": "[data-action='bank-other']"}, {"click": "#show-all-banks"}]}}
# 그 밖의 이체 모드의 흐름 명세에 더하는 펼치기 조작 (11-8 2-3). Run 1 빌드의 은행 목록은
# 문서에 다 있지만 [다른 은행이에요] 를 눌러야 보인다 - 정답 경로는 계좌번호로 짐작한 은행을
# 그대로 고르므로 목록을 열지 않는다. 검사 I 가 원본에서 보이던 값이 생성물에서 어느
# 상태에서 누를 수 있게 보이는지 세게 된 뒤로, 그 조작을 적지 않은 답은 떨어진다.
# reveal 모드는 제 조작(MOCK_REVEAL)이 있고, reveal-undeclared 는 일부러 적지 않는 모드다.
MOCK_BANK_REVEAL = {"pick-bank": {"at": "bank", "do": [
    {"click": "[data-action='bank-other']"}]}}
MODES = sorted(MOCKS)

# 과제 밖 입구를 어떻게 두는가 (검사 K). Run 1 빌드에는 입구가 하나도 없다 - 원본의
# 다른 메뉴를 다 지운 설계다. 그대로면 모든 모드가 검사 K 에서 떨어지므로, 다른 모드는
# 첫 화면에 입구를 모두 보이게 넣는다 (원본의 data-action 이름 그대로). 검사 K 는 걷는
# 동안 누를 수 있게 보인 것만 센다 - 접어 두면 펼치는 조작을 reveal 에 적어야 한다.
#
#   shown    첫 화면에 보이는 블록 (기본 - 아래 셋이 아닌 모든 이체 모드)
#   folded   접힌 블록(<details>). 흐름 명세의 reveal 에 펼치는 조작을 적는다
#   reveal   [다른 메뉴] 를 눌러야 그린다. 흐름 명세의 reveal 에 그 조작을 적는다
#   none     넣지 않는다 (Run 1 그대로)
ENTRANCE_MODES = {"entrances-reveal": "reveal", "entrances-folded": "folded",
                  "entrances-none": "none"}
ENTRANCES_AT = '<button class="secondary" data-action="noop">쓴 내역 보기</button>'
ENTRANCE_BRANCH_AT = "  else if(a==='bank-other'){"


def entrance_items():
    from senior_ui.tasks import load_task
    return load_task("transfer")["entrances"]["items"]


def entrance_buttons():
    return "".join('<button data-action="%s" aria-label="%s">%s</button>'
                   % (e["action"], e["label"], e["label"]) for e in entrance_items())


def entrance_branch(extra=""):
    names = ["mock-more"] + sorted({e["action"] for e in entrance_items()})
    return ("  else if(%s){ %s}\n"
            % (" || ".join("a==='%s'" % n for n in names),
               extra or "/* 과제 밖 입구 - 원본처럼 아무 일도 하지 않는다 */ "))


def entrance_swaps(how):
    """그 방식으로 입구를 넣는 바꿔치기들."""
    if how == "none":
        return []
    if how == "shown":
        return [(ENTRANCES_AT, ENTRANCES_AT + '\n    <div class="mock-more">'
                 + entrance_buttons() + '</div>'),
                (ENTRANCE_BRANCH_AT, entrance_branch() + ENTRANCE_BRANCH_AT)]
    if how == "folded":
        return [(ENTRANCES_AT, ENTRANCES_AT + '\n    <details class="mock-more"><summary '
                 'data-action="mock-more" id="mock-more">다른 메뉴</summary>'
                 + entrance_buttons() + '</details>'),
                (ENTRANCE_BRANCH_AT, entrance_branch() + ENTRANCE_BRANCH_AT)]
    # reveal: [다른 메뉴] 를 누르면 그린다. 그려진 입구는 아무 일도 하지 않는다.
    draw = ("if(a==='mock-more'){ document.getElementById('mock-more-list').innerHTML = %s; } "
            % repr(entrance_buttons()))
    return [(ENTRANCES_AT, ENTRANCES_AT + '\n    <button class="secondary" '
             'data-action="mock-more" id="mock-more">다른 메뉴</button>'
             '<span id="mock-more-list"></span>'),
            (ENTRANCE_BRANCH_AT, entrance_branch(draw) + ENTRANCE_BRANCH_AT)]


# entrances-reveal · entrances-folded 의 흐름 명세에 더하는 펼치기 조작. 첫 화면에서
# [다른 메뉴] 를 누른다 (접힌 블록이면 그것이 펼친다).
MOCK_ENTRANCE_REVEAL = {"oos-message": {"at": "start", "do": [{"click": "#mock-more"}]}}


def swap(html, old, new):
    """한 자리를 바꾼다. 그 자리가 없으면 멈춘다."""
    if old not in html:
        raise RuntimeError("mock: %s 에서 바꿀 자리를 찾지 못했다: %s…"
                           % (MOCK_BUILD, old[:60]))
    return html.replace(old, new, 1)


def mock_build(mode):
    """그 모드가 모델 답으로 내놓을 HTML."""
    banks, pad, _broken, errors = MOCKS[mode]
    html = swap(io.open(mock_build_path(), encoding="utf-8").read(),
                BANKS_LINE, banks)
    if ERRORS[errors][0]:
        for old, new in error_swaps():
            html = swap(html, old, new)
    # 이름은 두 자리 모두 바꾼다 (bank-yes · pick-bank).
    html = swap(html, *NAME_SWAP).replace(*NAME_SWAP)
    for old, new in PADS[pad]:
        html = swap(html, old, new)
    if mode in REVEAL_MODES:
        for old, new in REVEAL_SWAPS:
            html = swap(html, old, new)
    for old, new in entrance_swaps(ENTRANCE_MODES.get(mode, "shown")):
        html = swap(html, old, new)
    return html


# --------------------------------------------------------------------------- #
# mock 의 진단·계획
# --------------------------------------------------------------------------- #
# Run 1 빌드에 맞춘 진단과 계획. 화면은 그 빌드의 data-screen 아홉 개 그대로다 -
# 계획과 생성물이 어긋나면 일치 검사에서 떨어지므로, mock 이 생성 단계까지 가려면
# 계획이 빌드와 맞아야 한다. 내용은 docs/restructure-changelog.md 에서 옮겼다.
# 일곱 모드가 같은 계획을 쓴다 - 모드는 생성 답의 은행 목록 한 줄과 오류 처리에서만
# 다르다. 계획의 errors 는 pass 의 오류 처리(error_swaps)를 말한다.
MOCK_DIAGNOSIS = [
    {"id": "D1", "screen": "home", "element": "이체 입구",
     "problem": "이체 버튼이 첫 카드 안의 작은 버튼 하나라 시작점을 찾지 못한다",
     "evidence": "home 에 카드·블록 8개와 탭바 5개가 있고 이체는 그 중 하나의 작은 버튼"},
    {"id": "D2", "screen": "recipient", "element": "받는 사람 목록",
     "problem": "같은 이름이 두 번 나와 무엇이 다른지에서 멈춘다",
     "evidence": "김시현 카카오뱅크 행이 두 번 있다"},
    {"id": "D3", "screen": "bank", "element": "은행·증권사 타일 격자",
     "problem": "67개를 눈으로 훑어야 해서 찾다가 멈춘다",
     "evidence": "BANKS 38 + SECS 29 를 탭 두 개의 격자로 그린다"},
    {"id": "D4", "screen": "account", "element": "계좌번호 입력",
     "problem": "13자리를 넣는 동안 자릿수를 놓치고, 은행을 먼저 고르지 않으면 다음이 "
                "말없이 꺼져 있다",
     "evidence": "계좌 화면 [다음] 은 계좌 1자리와 은행 선택이 모두 있어야 켜진다"},
    {"id": "D5", "screen": "confirm", "element": "확인 표",
     "problem": "메모 두 줄이 섞여 무엇을 확인해야 하는지 흐려진다",
     "evidence": "받는분 메모 / 내통장 메모 행"},
    {"id": "D6", "screen": "done", "element": "완료 버튼 4개",
     "problem": "끝난 건지, 무엇을 더 해야 하는지에서 멈춘다",
     "evidence": "추가이체·상세보기·공유·확인 네 버튼"},
    {"id": "D7", "screen": "err-account", "element": "오류 팝업",
     "problem": "오류 코드와 은행 용어만 보여 무엇이 틀렸는지 모른다",
     "evidence": "ELB00016 · ETA00325 와 '과목코드 오류' 문구"},
]

MOCK_PLAN = {
    "screens": [
        {"name": "start", "purpose": "잔액을 보고 보내기를 시작한다", "from": ["home"]},
        {"name": "who", "purpose": "받는 사람을 고르거나 새 계좌로 간다",
         "from": ["recipient"]},
        {"name": "accno", "purpose": "계좌번호만 넣는다", "from": ["account"]},
        {"name": "bank", "purpose": "은행을 고른다", "from": ["bank"]},
        {"name": "whoconfirm", "purpose": "받는 사람이 맞는지 확인한다", "from": []},
        {"name": "amount", "purpose": "금액을 넣는다", "from": ["amount"]},
        {"name": "review", "purpose": "보낼 내용을 한 번 더 본다", "from": ["confirm"]},
        {"name": "auth", "purpose": "비밀번호로 본인 확인", "from": ["password"]},
        {"name": "done", "purpose": "보냈다는 것을 확인하고 처음으로", "from": ["done"]},
    ],
    "changes": [
        {"id": "C1", "what": "첫 화면을 잔액 한 줄과 버튼 둘로 줄인다",
         "why": "시작점이 화면에서 하나만 보이게", "addresses": ["D1"],
         "from_screens": ["home"], "to_screens": ["start"]},
        {"id": "C2", "what": "받는 사람 목록의 중복 행을 없앤다",
         "why": "같은 이름 두 줄에서 멈추지 않게", "addresses": ["D2"],
         "from_screens": ["recipient"], "to_screens": ["who"]},
        {"id": "C3", "what": "계좌번호 입력과 은행 선택을 두 화면으로 나눈다",
         "why": "한 화면에 한 가지 일만", "addresses": ["D4"],
         "from_screens": ["account", "bank"], "to_screens": ["accno", "bank"]},
        {"id": "C4", "what": "은행 화면에 검색을 두고 window.PRESERVED.BANKS · SECS "
                             "전체를 그 아래에 둔다",
         "why": "67개를 훑지 않고 찾게", "addresses": ["D3"],
         "from_screens": ["bank"], "to_screens": ["bank"]},
        {"id": "C5", "what": "받는 사람 확인 화면을 더한다",
         "why": "잘못 보내기 전에 이름으로 한 번 확인", "addresses": ["D4"],
         "from_screens": [], "to_screens": ["whoconfirm"]},
        {"id": "C6", "what": "확인 화면에서 메모 행을 뺀다",
         "why": "확인할 것만 남긴다", "addresses": ["D5"],
         "from_screens": ["confirm"], "to_screens": ["review"]},
        {"id": "C7", "what": "완료 화면의 버튼을 [처음으로] 하나로 줄인다",
         "why": "끝났다는 것이 분명하게", "addresses": ["D6"],
         "from_screens": ["done"], "to_screens": ["done"]},
        {"id": "C8", "what": "오류 팝업 두 개를 그 화면 안의 쉬운 안내 글로 바꾼다",
         "why": "무엇이 틀렸고 무엇을 하면 되는지 그 자리에서 알게", "addresses": ["D7"],
         "from_screens": ["err-account", "err-bank"], "to_screens": ["accno", "review"]},
    ],
    "errors": [
        {"id": "wrong-account", "screen": "accno",
         "how": "계좌번호 칸 아래에 맞지 않는다고 알리고 그 화면에 머문다",
         "back_to": "accno"},
        {"id": "wrong-bank", "screen": "review",
         "how": "보내기를 누르면 은행이 맞지 않는다고 알리고, [고치기]로 다시 고르게 한다",
         "back_to": "accno"},
    ],
}


# --------------------------------------------------------------------------- #
# 공과금 mock (bill-identity)
# --------------------------------------------------------------------------- #
# 위의 일곱은 모두 이체 Run 1 빌드를 되읽는다. 공과금 과제로 루프를 처음부터
# 끝까지 - 기준값 걷기 · 데이터 보존 · 형식 검사 · 검사기 A~J · 설명서 - 돌려 볼
# 길이 없었으므로, 공과금 원본을 거의 그대로 돌려주는 모드를 둔다. 실제 API 를
# 쓰기 전에 공과금 쪽 버그를 찾는 것이 목적이다.
#
# 바꾸는 것은 둘뿐이다. 선택지 배열의 선언을 window.PRESERVED 를 읽게 바꾸고
# (도구가 넣는 데이터를 읽지 않으면 형식 검사에서 떨어진다), 흐름 명세는
# flows/original_bill.json 의 걸음을 새 설계의 흐름 명세 모양으로 쓴다.
BILL_ORIGINAL = os.path.join(ROOT, "inputs", "original_bill.html")
BILL_FLOW = os.path.join(FLOWS_DIR, "original_bill.json")

# 공과금 원본에서 도구가 꺼내 넣어 주는 배열 (docs/input-contract.md 의 공과금 그룹 표).
# 범위 A (2026-10-06) 부터 메뉴 일곱 탭이 모두 차 있다 - B 판에서는 뒤의 다섯이 빈
# 배열이라 뽑히지 않았다.
BILL_ARRAYS = ["MENU_TABS", "MENU_BANK", "MENU_CARD", "MENU_STOCK", "MENU_INSURE",
               "MENU_BENEFIT", "MENU_GOODS", "MENU_HELP", "BILL_ITEMS", "PW_KEYS"]

# mock 모드 -> 그 모드가 되읽는 빌드의 과제. 다른 과제로 돌리면 루프가 시작하지 않는다.
BILL_MODES = ["bill-identity"]
MOCK_TASK = dict([(m, "transfer") for m in MODES] + [(m, "bill") for m in BILL_MODES])
ALL_MODES = MODES + BILL_MODES

BILL_SCREENS = ["home", "menu", "search", "bill-home", "camera", "info", "password",
                "done"]

BILL_DIAGNOSIS = [
    {"id": "D1", "screen": "menu", "element": "은행 탭 메뉴 목록",
     "problem": "납부하기가 긴 목록 중간에 있어 훑다가 지나친다",
     "evidence": "MENU_BANK 의 소분류 10개 · 항목 69개를 한 목록으로 그린다"},
    {"id": "D2", "screen": "bill-home", "element": "납부 항목 18개",
     "problem": "전기요금 항목을 눌러도 아무 일이 없어 어디로 가야 할지 모른다",
     "evidence": "BILL_ITEMS 의 항목은 pick-bill 로 무동작이고 [납부하기] 카드만 넘어간다"},
]

BILL_PLAN = {
    "screens": [{"name": n, "purpose": "원본 그대로", "from": [n]} for n in BILL_SCREENS],
    "changes": [
        {"id": "C1", "what": "바꾸지 않는다 (mock - 원본을 그대로 돌려준다)",
         "why": "루프가 공과금 과제를 끝까지 도는지 보려는 것", "addresses": ["D1", "D2"],
         "from_screens": ["menu", "bill-home"], "to_screens": ["menu", "bill-home"]},
    ],
    "errors": [],
}


def bill_build():
    """bill-identity 가 모델 답으로 내놓을 HTML. 선언 자리를 찾지 못하면 멈춘다."""
    html = io.open(BILL_ORIGINAL, encoding="utf-8").read()
    for name in BILL_ARRAYS:
        pat = re.compile(r"const %s = \[.*?\];" % name, re.S)
        if len(pat.findall(html)) != 1:
            raise RuntimeError("mock: %s 에서 %s 의 선언을 하나로 찾지 못했다"
                               % (BILL_ORIGINAL, name))
        html = pat.sub(lambda m: "const %s = window.PRESERVED.%s;" % (name, name), html)
    return html


def bill_flow():
    """flows/original_bill.json 의 걸음을 새 설계의 흐름 명세 모양으로."""
    src = json.load(io.open(BILL_FLOW, encoding="utf-8"))
    return {"name": "auto", "note": "mock bill-identity - 공과금 원본을 그대로 돌려준다",
            "derived_from_original": False,
            "required_ids": src["required_ids"], "steps": src["steps"],
            "expect": src["expect"], "done_amount": src["done_amount"],
            "error_paths": []}


def mock_plan_reply(mode):
    """No API: 진단·계획 단계의 답. 이체 일곱 모드가 같은 답을 쓰고, 공과금
    모드는 공과금 원본의 화면 그대로인 계획이다."""
    if mode not in MOCK_TASK:
        raise ValueError("mock 모드가 아니다: %s" % mode)
    diagnosis, plan = (BILL_DIAGNOSIS, BILL_PLAN) if mode in BILL_MODES \
        else (MOCK_DIAGNOSIS, MOCK_PLAN)
    text = "```json\n%s\n```\n" % json.dumps(
        {"diagnosis": diagnosis, "plan": plan}, ensure_ascii=False, indent=2)
    return {"text": text, "finish_reason": "stop", "seconds": 0.0, "usage": None,
            "temperature": TEMPERATURE, "seed": SEED,
            "model": None, "system_fingerprint": None}


# 재시도 답의 반성. 계획은 바꾸지 않는다 - mock 의 실패는 흐름 명세의 없는
# 선택자이고, 계획과는 무관하다.
MOCK_REFLECTION = {
    "cause": "흐름 명세의 둘째 걸음이 HTML 에 없는 선택자를 누른다",
    "plan_changes": [],
    "keep": [c["id"] for c in MOCK_PLAN["changes"]],
}


def mock_base(mode):
    """그 모드가 생성 답으로 내놓을 `(HTML, 흐름 명세)`."""
    if mode in BILL_MODES:
        html, flow = bill_build(), bill_flow()
    else:
        html = mock_build(mode)
        flow = json.load(io.open(os.path.join(FLOWS_DIR, "restructured.json"),
                                 encoding="utf-8"))
        flow["name"] = "auto"
        if MOCKS[mode][2]:
            flow["steps"][1]["click"] = "[data-action='does-not-exist']"
        if ERRORS[MOCKS[mode][3]][1]:
            flow["error_paths"] = json.loads(json.dumps(MOCK_ERROR_PATHS))
        if REVEAL_MODES.get(mode):
            flow["reveal"] = json.loads(json.dumps(MOCK_REVEAL))
        elif mode not in REVEAL_MODES:
            flow["reveal"] = json.loads(json.dumps(MOCK_BANK_REVEAL))
        if ENTRANCE_MODES.get(mode) in ("reveal", "folded"):
            flow["reveal"].update(json.loads(json.dumps(MOCK_ENTRANCE_REVEAL)))
    return html, flow


def _blocks(html, flow):
    return "```html\n%s\n```\n\n```json\n%s\n```\n" % (
        html, json.dumps(flow, ensure_ascii=False, indent=2))


def _reply(text):
    return {"text": text, "finish_reason": "stop", "seconds": 0.0, "usage": None,
            "temperature": TEMPERATURE, "seed": SEED,
            "model": None, "system_fingerprint": None}


def mock_reply(mode, reflect=False):
    """No API: Run 1 을 되읽는다. 모드마다 은행 목록 한 줄이 다르다 (MOCKS).

    'fail' 은 둘째 걸음이 없는 선택자를 클릭하는 흐름을 함께 내놓아, 모든 시도가
    화면 2에서 죽게 한다 - 재시도 루프가 검사 실패를 물고 도는 것을 확인하는
    모드다.
    """
    html, flow = mock_base(mode)
    text = _blocks(html, flow)
    if reflect:
        # 재시도 답은 반성이 코드 블록보다 앞이다 (docs/restructure-prompt.md
        # 의 REFLECT 블록).
        text = "```json\n%s\n```\n\n" % json.dumps(
            dict(MOCK_REFLECTION, keep=[c["id"] for c in (
                BILL_PLAN if mode in BILL_MODES else MOCK_PLAN)["changes"]]),
            ensure_ascii=False, indent=2) + text
    return _reply(text)


# --------------------------------------------------------------------------- #
# mock 의 보고 다듬기 (--mock-refine)
# --------------------------------------------------------------------------- #
# 다듬기 호출의 답. 생성 답(--mock)은 그대로 두고, 다듬기와 그 고치기 호출의 답만
# 이것으로 정한다. 모드마다 회차별로 다르다.
#
#   done            1회차에 "고칠 것 없음" (비평 하나). 최종 빌드는 그대로다.
#                   --mock 실행의 기본값 - 기존 mock 의 최종 빌드가 바뀌지 않는다.
#   improve         1회차: 비평 둘 + 눈에 보이게 고친 빌드 (통과). 2회차: 고칠 것 없음.
#   break           1회차: 비평 하나 + 흐름이 깨진 빌드 (검사 실패). 고치기 답도 깨져
#                   있다 - 직전에 통과한 빌드로 되돌아간다.
#   break-then-fix  1회차는 break 와 같고, 고치기 답은 고친 빌드 (통과).
REFINE_MODES = ["done", "improve", "break", "break-then-fix"]

MOCK_CRITIQUE_DONE = {
    "issues": [],
    "keep": ["화면마다 할 일 하나와 다음 버튼 하나 - 어디를 누를지 그림에서 바로 보인다"],
    "done": True}

MOCK_CRITIQUE = {
    "issues": [
        {"screen": "bank",
         "problem": "은행 이름 줄이 모두 같은 모양이라 어디까지가 목록인지, 아래에 더 있는지 "
                    "몰라 첫 화면에서 멈춘다",
         "seen": "화면 bank — 스크롤 1/2 그림에서 은행 줄 여섯 개가 같은 높이의 회색 상자로 "
                 "이어지고, 아래 끝이 잘린 줄이 없다",
         "fix": "목록 위에 '은행 67곳 — 아래로 내려 더 보기' 안내를 두고 목록 칸에 테두리를 준다"},
        {"screen": "amount",
         "problem": "다음 버튼이 숫자판과 같은 회색이라 무엇을 눌러야 끝나는지 못 찾는다",
         "seen": "화면 amount 그림에서 [다음] 이 숫자 버튼과 같은 색 · 같은 크기로 숫자판 "
                 "맨 아래 줄에 붙어 있다",
         "fix": "[다음] 을 숫자판과 떨어뜨리고 진한 바탕 · 큰 글자로 바꾼다"}],
    "keep": ["확인 화면의 받는 사람 · 금액 두 줄 배치는 그대로 둔다 - 그림에서 가장 크게 읽힌다"],
    "done": False}

MOCK_CRITIQUE_BREAK = {
    "issues": [
        {"screen": "who",
         "problem": "받는 사람 버튼 이름이 길어 두 줄로 꺾여 눌러야 할 곳이 흐려진다",
         "seen": "화면 who 그림에서 첫 버튼의 글이 두 줄로 꺾여 있다",
         "fix": "버튼 이름을 짧게 바꾼다"}],
    "keep": [],
    "done": False}

# improve 가 바꾸는 눈에 보이는 한 자리. 규칙만 더하므로 흐름과 선택자는 같다. Run 1
# 빌드의 .primary 는 이미 22px · 패딩 22px 이라 크기를 키우는 규칙은 화면을 바꾸지
# 않는다 - 바탕색과 테두리를 바꾼다 (흰 글자와의 대비는 더 커진다).
REFINE_STYLE = ("</style>",
                "#phone .primary{background:#0B3D91;border:3px solid #000}\n</style>")


def _json_block(obj):
    return "```json\n%s\n```\n\n" % json.dumps(obj, ensure_ascii=False, indent=2)


def _improved(mode):
    html, flow = mock_base(mode)
    return swap(html, *REFINE_STYLE), flow


def _broken(mode):
    html, flow = mock_base(mode)
    flow["steps"][1]["click"] = "[data-action='does-not-exist']"
    flow["steps"][1].pop("do", None)
    return html, flow


def mock_refine_reply(refine_mode, mode, round_no):
    """다듬기 호출의 답. `mode` 는 생성 답의 mock 모드 (그 빌드를 다듬는다)."""
    if refine_mode not in REFINE_MODES:
        raise ValueError("다듬기 mock 모드가 아니다: %s" % refine_mode)
    if refine_mode == "done" or (refine_mode == "improve" and round_no > 1):
        return _reply(_json_block(MOCK_CRITIQUE_DONE))
    if refine_mode == "improve":
        return _reply(_json_block(MOCK_CRITIQUE) + _blocks(*_improved(mode)))
    return _reply(_json_block(MOCK_CRITIQUE_BREAK) + _blocks(*_broken(mode)))


def mock_refine_fix_reply(refine_mode, mode):
    """다듬은 빌드가 떨어진 뒤의 고치기 답 (보통 재시도 - 반성이 먼저)."""
    keep = [c["id"] for c in (BILL_PLAN if mode in BILL_MODES else MOCK_PLAN)["changes"]]
    refl = dict(MOCK_REFLECTION, cause="다듬으며 바꾼 버튼의 선택자를 흐름 명세에 "
                                        "맞추지 않았다", keep=keep)
    blocks = _blocks(*(_broken(mode) if refine_mode == "break" else _improved(mode)))
    return _reply(_json_block(refl) + blocks)
