r"""테스트가 쓰는 함수를 한 곳에서만 가져오는 어댑터.

테스트 본문은 `senior_ui/` 를 직접 import 하지 않는다. 전부 이 파일을 거친다.
정리 단계에서 파일이 옮겨지거나 이름이 바뀌면 아래 "지금 위치" 블록의 import
줄만 고치면 되고, 테스트 본문은 한 줄도 고치지 않는다. 그것이 이 파일의
유일한 존재 이유다.

이 파일 자체는 아무 동작도 바꾸지 않는다 - 이름만 다시 내보낸다.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 패키지는 레포 루트 아래에 있다. 설치하지 않고 돌리므로 루트만 길에 올린다.
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ======================================================================= #
# 지금 위치 - 정리 단계에서 고칠 곳은 여기까지다.
# ======================================================================= #
from senior_ui import audit as _audit                        # noqa: E402
from senior_ui import _cli                                   # noqa: E402
from senior_ui import config as _config                      # noqa: E402
from senior_ui import devserver as _devserver                # noqa: E402
from senior_ui.audit import core as _audit_core              # noqa: E402
from senior_ui.audit import __main__ as _audit_cli           # noqa: E402
from senior_ui.audit import stage as _audit_stage            # noqa: E402
from senior_ui.audit import report as _audit_report          # noqa: E402
from senior_ui.restructure import audit_call as _audit_call  # noqa: E402
from senior_ui.audit import inputs as _audit_inputs          # noqa: E402
from senior_ui.restructure import loop as _loop              # noqa: E402
from senior_ui.restructure import model as _model            # noqa: E402
from senior_ui.restructure import plan as _plan              # noqa: E402
from senior_ui.restructure import brief as _brief            # noqa: E402
from senior_ui.viewer import build_index as _build_index     # noqa: E402
from senior_ui.restructure import __main__ as _restructure_cli  # noqa: E402
from senior_ui.restructure import preserve as _preserve      # noqa: E402
from senior_ui.restructure import prompt as _prompt          # noqa: E402
from senior_ui.restructure import reply as _reply            # noqa: E402
from senior_ui.experiment import report as _session_report    # noqa: E402
from senior_ui.experiment import server as _exp_server        # noqa: E402
from senior_ui import tasks as _tasks                        # noqa: E402
from senior_ui.select import __main__ as _select_cli         # noqa: E402
from senior_ui.select import collect as _select_collect      # noqa: E402
from senior_ui.select import rule as _select_rule            # noqa: E402
# ======================================================================= #

# ---- senior_ui/audit (core.audit · drive.drive · flow.load_flow) ------- #
audit = _audit.audit
drive = _audit.drive
load_flow = _audit.load_flow
# 보기(see) - 모델에게 보여 줄 그림을 잘라 찍는다
import importlib                                              # noqa: E402
_audit_drive = importlib.import_module("senior_ui.audit.drive")
capture_see = _audit_drive.capture_see
see_parts = _audit_drive.see_parts
walk_reveal = _audit_drive.walk_reveal

# ---- senior_ui/audit/stage.py ------------------------------------------ #
apply_stage = _audit_stage.apply_stage
STAGES = _audit_stage.STAGES

# 집계 함수는 core 와 stage 가 같은 것을 써야 한다. 그 "같은 것" 을 확인하려면
# 테스트가 두 모듈을 볼 수 있어야 하므로 모듈째로 내보낸다.
count_fatals = _audit_core.count_fatals
audit_core_module = _audit_core
audit_stage_module = _audit_stage

# ---- senior_ui/audit/__main__.py (CLI - 종료 코드까지) ----------------- #
audit_cli_main = _audit_cli.main
audit_cli_module = _audit_cli

# ---- senior_ui/audit/report.py (여러 audit 를 나란히 놓는 md) ----------- #
ar_main = _audit_report.main
ar_load = _audit_report.load
ar_render = _audit_report.render
ar_CHECKS = _audit_report.CHECKS
ar_SEVERITY = _audit_report.SEVERITY

# ---- senior_ui/restructure/reply.py (답 가르기 · 흐름 명세 모양) -------- #
validate_flow = _reply.validate_flow
parse_reply = _reply.parse_reply
# 흐름 명세 검사가 처리기를 읽을 때 쓰는 함수. 검사 C 와 같은 것이어야 한다.
validate_flow_handlers = _reply.handled_actions

# ---- senior_ui/restructure/preserve.py (선택지 데이터 뽑기 · 넣기) ------ #
# 뽑고 넣고 읽는지 보는 세 가지를 테스트가 하나씩 보므로 모듈째로 내보낸다.
preserve_module = _preserve
# 참조 검사의 집은 형식 검사 쪽이다 (reply.py) - 브라우저 없이 규칙으로 본다.
preserved_problems = _reply.preserved_problems
reply_module = _reply

# ---- senior_ui/restructure/prompt.py ----------------------------------- #
# 프롬프트 조립 - 템플릿 읽기 / 선택지 블록 / 슬롯 채우기 / 재시도 블록
load_template = _prompt.load_template
choices_block = _prompt.choices_block
build_prompt = _prompt.build_prompt
retry_block = _prompt.retry_block
brief_failure = _prompt.brief_failure
# 진단·계획 프롬프트. 과제 설명(과제 파일)을 생성 프롬프트와 같이 쓴다.
load_plan_template = _prompt.load_plan_template
build_plan_prompt = _prompt.build_plan_prompt
prompt_module = _prompt

# ---- senior_ui/tasks.py (과제 정의 tasks/<이름>.json) ------------------- #
load_task = _tasks.load_task
task_names = _tasks.task_names
tasks_module = _tasks

# ---- senior_ui/restructure/__main__.py (명령줄 기본값) ------------------ #
restructure_parser = _restructure_cli.build_parser
restructure_cli = _restructure_cli

# ---- senior_ui/restructure/brief.py (디자이너용 설명서) ----------------- #
brief_module = _brief

# ---- senior_ui/viewer/build_index.py (대시보드 색인) --------------------- #
# 빌드 옆의 plan.json 을 "변경 추적" 탭에 붙이는 곳
index_plan_of = _build_index.plan_of
build_index_module = _build_index

# ---- senior_ui/restructure/plan.py (진단·계획 · 일치 검사 · 반성) ------- #
plan_module = _plan

# ---- senior_ui/restructure/model.py (API 없이 도는 대역) --------------- #
mock_reply = _model.mock_reply
# 호출 실패의 종류를 가르는 예외들. 루프가 그 종류로 판단하므로 테스트도 같은
# 것을 던져야 한다.
model_module = _model

# ---- senior_ui/restructure/loop.py (재시도 루프 · 예산 · 종료 코드) ----- #
# 버그 재현 테스트는 단계 함수를 하나씩 부르고 루프 안의 이름을 바꿔 끼우므로
# 모듈째로 내보낸다.
loop_module = _loop

# ---- senior_ui/restructure/audit_call.py -------------------------------- #
# 루프가 검사기를 부르는 곳.
audit_call_module = _audit_call

# ---- senior_ui/audit/inputs.py (판정 입력) ------------------------------ #
# 모델 흐름 + 과제 -> 판정에 쓰는 흐름. 루프와 CLI 가 같은 함수를 부른다.
# 허용하는 제거 목록(연구자 파일)도 여기서 읽는다.
judged_flow = _audit_inputs.judged_flow
load_allowed_removals = _audit_inputs.load_allowed_removals
inputs_module = _audit_inputs

# ---- senior_ui/devserver.py · senior_ui/config.py ---------------------- #
listening = _devserver.listening
ensure_server = _devserver.ensure_server
# 포트에 떠 있는 서버가 이 저장소를 서빙하는지 보는 부분까지 테스트가 본다.
devserver_module = _devserver
cli_module = _cli
PORT = _config.PORT
ROOT_DIR = _config.ROOT
config_module = _config

# ---- senior_ui/experiment/server.py (대시보드 서버) --------------------- #
srv_make_handler = _exp_server.make_handler
srv_make_server = _exp_server.make_server
srv_parser = _exp_server.build_parser
srv_is_local = _exp_server.is_local
srv_module = _exp_server
srv_banner = _exp_server.banner

# ---- senior_ui/experiment/report.py (집계 함수) ------------------------- #
sr_load = _session_report.load
sr_progress = _session_report.progress
sr_per_session = _session_report.per_session
sr_summarise = _session_report.summarise
sr_compare = _session_report.compare
sr_dwell = _session_report.dwell
sr_trouble = _session_report.trouble
sr_write_csv = _session_report.write_csv
sr_table = _session_report.table
sr_main = _session_report.main

# ---- senior_ui/audit/flow.py (정답 값 · 오류 경로 정의) ----------------- #
flow_module = _audit.flow
# 검사 J (오류 경로) 와 그 판정이 쓰는 문맥. 손으로 만든 걷기 결과로 판정만
# 따로 보기 위해 내보낸다.
from senior_ui.audit.checks import j_errors                  # noqa: E402
from senior_ui.audit.context import AuditContext             # noqa: E402
# 검사 B (표시 정확도). 과제가 정한 값으로 보는지 손으로 만든 스냅샷으로 본다.
from senior_ui.audit.checks import b_display                 # noqa: E402
# 검사 A (과제 완수). 완료 화면의 값을 과제에서 읽는지 손으로 만든 스냅샷으로 본다.
from senior_ui.audit.checks import a_completion                # noqa: E402
# 처리기 분기 · 조작부 이름을 읽는 규칙. 검사 C 와 형식 검사가 함께 쓴다.
from senior_ui.audit import handlers as handlers_module      # noqa: E402

# ---- senior_ui/select (C 후보 고르기) ----------------------------------- #
select_main = _select_cli.main
select_collect = _select_collect.collect
select_rule_module = _select_rule
DEFAULT_SELECTION_RULE = _select_rule.DEFAULT_RULE
