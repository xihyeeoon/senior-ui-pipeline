r"""한 곳에만 적는 값들.

포트 3003, 원본 시제품의 경로와 URL, 산출물 폴더, 실험 조건. 옮기기 전에는
이것들이 파일마다 복사되어 있었다. 포트 하나를 바꾸려면 다섯 군데를 고쳐야
했고, 고쳐지지 않은 한 군데는 조용히 어긋났다.

실험 조건(CONDITIONS)이 여기 있는 이유는 다르다. 조건을 정의하던 곳은 실험
서버이고 그것을 읽어 가던 곳은 뷰어 색인이었는데, 서버가 색인을 다시 만들기
위해 뷰어를 import 하고 있어서 둘이 맞물려 있었다. 어느 쪽도 다른 쪽의 주인이
아니므로 값을 여기로 빼서 고리를 끊는다.
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 개발용 http.server · 실험 서버 · 검사기가 모두 이 포트의 같은 루트를 본다.
PORT = 3003
BASE_URL = "http://localhost:%d" % PORT

FLOWS_DIR = os.path.join(ROOT, "flows")
TASKS_DIR = os.path.join(ROOT, "tasks")          # 과제 정의 (senior_ui/tasks.py)
OUTPUTS_DIR = os.path.join(ROOT, "outputs")      # .gitignore - 재생성 가능
RESULTS_DIR = os.path.join(ROOT, "results")      # 추적함 - 남겨야 할 증거

# 산출물 폴더를 옮길 수 있게 하는 환경 변수. 테스트가 쓴다.
OUTPUTS_ENV = "SENIOR_UI_OUTPUTS"

# --mock 실행의 기본 산출물 폴더 (.gitignore). mock 의 pass · preserved-all 은
# 실제로 통과해 restructured_auto.* 로 승격되므로, outputs/ 를 같이 쓰면 연습으로
# 돌린 mock 이 실제 실행의 결과를 덮는다. outputs/restructured_auto.* 는 실제
# 실행만 쓴다.
MOCK_OUTPUTS_DIR = os.path.join(ROOT, ".mock-outputs")


def outputs_dir(mock=False):
    """산출물을 쓸 폴더. 기본은 OUTPUTS_DIR 이고 SENIOR_UI_OUTPUTS 로 바꾼다.
    mock 실행의 기본은 MOCK_OUTPUTS_DIR 이다 (환경 변수를 주면 그것이 이긴다).

    상수가 아니라 함수인 이유는 테스트다. 재구성 루프를 한 번 돌리면 마지막
    빌드가 `outputs/restructured_auto.*` 로 복사되는데, 그 루프를 돌리는 테스트가
    있으므로 테스트를 한 번 돌릴 때마다 실제 산출물이 mock 결과로 덮여 쓰였다.
    상수를 import 해 두면 테스트가 환경 변수를 세워도 이미 늦으므로, 쓰는
    자리에서 매번 읽는다.

    옮길 자리는 저장소 루트 아래여야 한다. 검사기는 빌드를 file:// 이 아니라
    :3003 이 서빙하는 http:// 로 열고, 그 서버는 ROOT 만 서빙한다. 밖에 두면
    검사기가 빌드를 열지 못해 첫 화면에서 멈추고, 그것이 설계 실패처럼 보인다.
    """
    return os.environ.get(OUTPUTS_ENV) or (MOCK_OUTPUTS_DIR if mock else OUTPUTS_DIR)


def inside_root(path):
    """그 경로가 저장소 루트 안에 있는가. 서버가 서빙할 수 있는 범위다."""
    rel = os.path.relpath(os.path.abspath(path), ROOT)
    return not rel.startswith(os.pardir) and not os.path.isabs(rel)

# 모든 갈래가 여기서 출발한다.
ORIGINAL_FILE = os.path.join(ROOT, "inputs", "original_transfer.html")
ORIGINAL_REL = "inputs/original_transfer.html"


def url_for(path):
    """루트 기준 경로를 서버가 서빙하는 URL 로. 구분자는 항상 '/' 다."""
    return "%s/%s" % (BASE_URL, str(path).replace(os.sep, "/").lstrip("/"))


ORIGINAL_URL = url_for(ORIGINAL_REL)

# 재구성 루프가 부르는 모델. 정하는 순서는 --model, 환경 변수(아래 순서), 이 값이다
# (restructure.loop.model_choice). 실행마다 어디서 왔는지가 run.log 첫 줄과
# summary.json 의 model_source 에 남는다. 모델마다 부르는 방식이 다르다 -
# restructure.model.profile_for.
DEFAULT_MODEL = "gpt-4o"
MODEL_ENV_VARS = ("RESTRUCTURE_MODEL", "DESIGNREPAIR_MODEL")

# 추론형 모델이 생각에 쓸 노력. --reasoning-effort 를 주지 않으면 이 값을 보낸다
# (restructure.loop.effort_choice). 모델의 기본값에 맡기면 그 값이 어디에도 남지
# 않고, 모델이 기본값을 바꾸면 같은 명령이 다른 조건으로 돈다. 보낸 값과 출처는
# run.log 첫 줄과 summary.json 의 model_call.reasoning_effort 에 남는다.
# medium 은 gpt-6.1-sol · gpt-6-astra 가 받는 값(low~max)이고, OpenAI 문서가 말하는
# gpt-5.5 · gpt-6.1-sol 의 기본값과 같다 (2026-10-06 확인). 추론형이 아니면 보내지
# 않는다.
DEFAULT_REASONING_EFFORT = "medium"

# 재구성 루프의 검사 단계 (--stage). 루프가 만드는 것은 와이어프레임이고, 지금까지의
# 자동 실행(Run 2~5)도 모두 --stage wireframe 을 손으로 주고 돌았다. 기본값이
# styled 인 채로 남아 있어서 첫 실제 실행(gpt-6.1-sol · gpt-6-astra, 2026-10-06)이
# 말없이 styled 로 돌았다 - styled 는 2026-09-30 --stage 를 처음 붙일 때(c297a52)
# "기존 동작 그대로" 를 위해 고른 값이다. 보낸 값과 출처는 run.log 첫 줄과
# summary.json 의 stage · stage_source 에 남는다 (restructure.loop.stage_choice).
DEFAULT_STAGE = "wireframe"

# 재시도 예산 (--format-attempts · --audit-attempts, 둘 다 한 번에는 --attempts).
# 코드의 기본값은 처음부터 3 이었고, 형식 5 · 검사 6 은 2026-10-01 의 세 실행
# (20261001-104938 · -125247 · -144134, docs/variance-notes.md)이 명령줄로 준
# 값이다. 그 뒤 명령줄 없이 돈 첫 실제 실행이 3 · 3 으로 돌았다. 형식 실패를
# 줄이는 고침(별칭 참조 · 완료 화면 키 · back_to)과 함께 그 값으로 되돌린다.
# 값과 출처는 run.log 첫 줄과 summary.json 의 budget · budget_source 에 남는다
# (restructure.loop.budget_choice).
DEFAULT_BUDGET = {"format": 5, "audit": 6}

# 모델별 100만 토큰당 가격 (USD). summary.json 의 cost 가 이 표로 시도별·전체
# 예상 금액을 센다. None 이면 금액은 null 이다 - 0 이 아니라 "모른다".
#
#   이름은 --model 에 주는 그대로 찾는다. 날짜가 붙은 판(gpt-4o-2024-05-13 등)은
#   별칭과 값이 다를 수 있으므로 쓰려면 따로 적는다.
#   output 은 생각(reasoning) 토큰에도 매겨진다 - completion 이 생각을 포함하므로
#   따로 더하지 않는다.
#   캐시된 입력의 할인은 넣지 않았다. 그래서 금액은 상한 쪽 어림이다.
#
# 채운 것은 셋이다. 나머지는 연구자가 공식 가격표를 보고 채운다
# (https://developers.openai.com/api/docs/pricing).
#
#   gpt-6.1-sol · gpt-6-astra: 2026-10-06 공식 가격표에서 확인. Standard 단계의
#   "Short context" 값이다 (입력 272K 토큰 이하 - 이 도구의 프롬프트는 3만 안팎).
#   입력이 272K 를 넘으면 값이 다르다 (sol 4.00 / 15.00, astra 20.00 / 75.00).
#   Batch · Flex 단계의 할인 가격은 넣지 않았다 - 이 도구는 Standard 로 부른다.
MODEL_PRICES = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4.1": None,
    "o3": None,
    "o4-mini": None,
    "gpt-5": None,
    "gpt-5.4": None,
    "gpt-5.5": None,
    "gpt-5.6-sol": None,
    "gpt-5.6-terra": None,
    "gpt-5.6-luna": None,
    "gpt-6-astra": {"input": 10.00, "output": 50.00},   # 2026-10-06 확인
    "gpt-6.1-sol": {"input": 2.00, "output": 10.00},    # 2026-10-06 확인
    "gpt-6-luna": None,
}

# 출력 길이 기본값 (completion 상한, 생각 토큰 포함). --max-tokens ·
# --plan-max-tokens 를 주지 않으면 부르는 방식(restructure.model.profile_for)의
# "추론형인가" 로 고른다 (restructure.loop.output_caps).
#
#   gpt-4o    gpt-4o 의 답(HTML + 흐름 명세)은 3,300~3,500 토큰이었다. 분당 한도
#             30,000 이 입력에 이 값을 더해 세므로 낮춰 둔 값이다. 이체 기준값이
#             이 값으로 뽑혀 있어 바꾸지 않는다. 표에 없는 모델도 이것을 쓴다.
#   reasoning 추론형은 생각 토큰도 같은 상한 안에서 쓰고, 생각이 다 쓰면 보이는
#             답이 빈 채로 잘려 온다. OpenAI 는 "처음 실험할 때는 생각과 출력에
#             적어도 25,000 을 남겨 두라" 고 한다 (Reasoning models 안내,
#             2026-10-06 확인). 생성은 그보다 넉넉히 32,000 (답 3,500 에 생각 몫),
#             진단·계획은 답이 짧아도 생각은 같이 하므로 그 최소인 25,000 이다.
#             상한은 쓴 만큼만 요금이 매겨지고, 분당 500,000 에서는 입력 3만 +
#             32,000 도 한 요청에 넉넉하다. gpt-6.1-sol · gpt-6-astra 의 최대 출력은
#             128K 다.
OUTPUT_CAPS = {"gpt-4o": {"generate": 14000, "plan": 6000},
               "reasoning": {"generate": 32000, "plan": 25000}}

# 모델 호출 사이 대기(초) - 진단·계획과 생성 사이, 시도와 시도 사이. --delay 를
# 주지 않으면 OUTPUT_CAPS 와 같은 방식으로 고른다 (restructure.loop.call_delay).
#
#   gpt-4o    원본 HTML 이 두 호출에 다 들어가서 같은 1분 안에 보내면 분당
#             30,000 을 넘었다. 그 동작 그대로 - 헤더는 보지 않고 늘 60초.
#   reasoning gpt-6.1-sol · gpt-6-astra 는 분당 500,000 이다 (2026-10-06 --probe).
#             짧게 5초만 두고, 대신 호출 직전에 직전 응답 헤더의 남은 토큰을 본다
#             - 다음 요청(예상 입력 + max_tokens)보다 적을 때만 모자란 만큼 더
#             기다린다 (restructure.model.wait_for_tokens). 한도가 작은 추론형을
#             불러도 그 확인이 지킨다.
DELAY = {"gpt-4o": 60.0, "reasoning": 5.0}

# The two builds under comparison. `url` is what the phone loads in the frame.
CONDITIONS = [
    {"key": "original",
     "label": "원본 (신한 SOL 재현)",
     "url": "/inputs/original_transfer.html"},
    {"key": "restructured",
     "label": "재구성본 (Run 1)",
     "url": "/outputs/restructured_transfer.html"},
]
