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

# The two builds under comparison. `url` is what the phone loads in the frame.
CONDITIONS = [
    {"key": "original",
     "label": "원본 (신한 SOL 재현)",
     "url": "/inputs/original_transfer.html"},
    {"key": "restructured",
     "label": "재구성본 (Run 1)",
     "url": "/outputs/restructured_transfer.html"},
]
