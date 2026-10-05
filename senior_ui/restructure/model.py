r"""모델 호출과, 모델 없이 도는 대역.

키 읽기(load_env) · 실제 호출(call_model) · API 없이 Run 1 을 다시 재생하는
mock_reply 가 여기 있다. 돌려주는 모양은 셋 다 같다:
{"text", "finish_reason", "seconds", "usage"}.
"""
import io
import json
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
# 토큰 어림과 분당 한도
# --------------------------------------------------------------------------- #
# tiktoken 이 없을 때의 대비. 이 저장소의 원본 HTML 에서 잰 비율이다 (글자
# 30,966 / o200k 토큰 10,546 = 2.94). 한글이 많은 글일수록 정확하다.
CHARS_PER_TOKEN = 2.9


def _encoder():
    """gpt-4o 계열의 토크나이저. tiktoken 이 없거나 사전을 받지 못하면 None."""
    try:
        import tiktoken
        return tiktoken.get_encoding("o200k_base")
    except Exception:                                # 설치 안 됨 · 오프라인
        return None


def estimate_tokens(text):
    """`(토큰 수, 어떻게 셌는가)`. 보내기 전에 로그에 남기려는 것이다."""
    enc = _encoder()
    if enc is not None:
        return len(enc.encode(text or "", disallowed_special=())), "tiktoken:o200k_base"
    return int(round(len(text or "") / CHARS_PER_TOKEN)), "chars/%s" % CHARS_PER_TOKEN


# 요청 하나가 분당 한도보다 크면 429 의 문구가 "Request too large … Limit N,
# Requested M" 이다. 분당 한도는 입력에 max_tokens 를 더해 세므로, 재시도처럼
# 입력이 2만을 넘는 프롬프트에 14,000 을 붙이면 이렇게 된다. 기다려도 풀리지
# 않는다 - 줄여서 보내야 한다.
TOO_LARGE = re.compile(r"Request too large.*?Limit (\d+), Requested (\d+)", re.S)
# 줄여도 이보다 작으면 보내지 않는다. 답(HTML + 흐름 명세)이 이보다 짧은 적이
# 없다 - 자동 Run 4·5 의 답이 3,300~3,500 토큰이었다. 더 줄이면 잘린 답만 온다.
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


def call_model(model, prompt, max_tokens, log=None, backoff=(20, 45, 90, 180),
               temperature=TEMPERATURE, seed=SEED):
    """시도마다 직전 HTML 전체를 다시 보내므로 프롬프트가 크다. 이 계정은 전에
    TPM 30,000 한도에 걸린 적이 있으므로 429 를 지수적으로 기다렸다 다시 친다.
    그래도 안 되면 RateLimited 를 올려 설계 실패와 섞이지 않게 한다.

    429 가운데 "요청 하나가 분당 한도보다 크다" 는 기다려서 풀리지 않으므로
    max_tokens 를 줄여 바로 다시 보낸다 (shrink_for_minute). 둘 다 시도 실패로
    세지 않는다 - 루프는 RateLimited 를 받으면 예산을 깎지 않고 멈춘다.

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
    waits, cap = list(backoff), max_tokens
    while True:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=cap,
                temperature=temperature,
                seed=seed,
            )
            break
        except RateLimitError as e:
            smaller = shrink_for_minute(str(e), cap, log)
            if smaller is not None:
                cap = smaller                    # 기다리지 않고 바로 다시 보낸다
                continue
            if not waits:
                raise RateLimited(str(e))
            wait = waits.pop(0)
            if log:
                log("429 — %d초 기다렸다 다시 시도 (%d/%d)"
                    % (wait, len(backoff) - len(waits), len(backoff)))
            time.sleep(wait)
        except (AuthenticationError, PermissionDeniedError, BadRequestError,
                NotFoundError) as e:
            raise ApiRejected("%s: %s" % (type(e).__name__, e))
        except APIConnectionError as e:          # APITimeoutError 도 이 아래다
            raise InfraFailed("%s: %s" % (type(e).__name__, e))
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
        # 실제로 보낸 길이 제한. 분당 한도에 맞추느라 줄였으면 요청한 값과 다르다.
        "max_tokens": cap,
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
}
MODES = sorted(MOCKS)


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


def mock_plan_reply(mode):
    """No API: 진단·계획 단계의 답. 다섯 모드가 같은 답을 쓴다."""
    if mode not in MOCKS:
        raise ValueError("mock 모드가 아니다: %s" % mode)
    text = "```json\n%s\n```\n" % json.dumps(
        {"diagnosis": MOCK_DIAGNOSIS, "plan": MOCK_PLAN}, ensure_ascii=False, indent=2)
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


def mock_reply(mode, reflect=False):
    """No API: Run 1 을 되읽는다. 모드마다 은행 목록 한 줄이 다르다 (MOCKS).

    'fail' 은 둘째 걸음이 없는 선택자를 클릭하는 흐름을 함께 내놓아, 모든 시도가
    화면 2에서 죽게 한다 - 재시도 루프가 검사 실패를 물고 도는 것을 확인하는
    모드다.
    """
    html = mock_build(mode)
    flow = json.load(io.open(os.path.join(FLOWS_DIR, "restructured.json"),
                             encoding="utf-8"))
    flow["name"] = "auto"
    if MOCKS[mode][2]:
        flow["steps"][1]["click"] = "[data-action='does-not-exist']"
    if ERRORS[MOCKS[mode][3]][1]:
        flow["error_paths"] = json.loads(json.dumps(MOCK_ERROR_PATHS))
    text = "```html\n%s\n```\n\n```json\n%s\n```\n" % (
        html, json.dumps(flow, ensure_ascii=False, indent=2))
    if reflect:
        # 재시도 답은 반성이 코드 블록보다 앞이다 (docs/restructure-prompt.md
        # 의 REFLECT 블록).
        text = "```json\n%s\n```\n\n" % json.dumps(
            MOCK_REFLECTION, ensure_ascii=False, indent=2) + text
    return {"text": text, "finish_reason": "stop", "seconds": 0.0, "usage": None,
            "temperature": TEMPERATURE, "seed": SEED,
            "model": None, "system_fingerprint": None}
