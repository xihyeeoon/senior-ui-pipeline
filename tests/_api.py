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
from senior_ui.audit import stage as _audit_stage            # noqa: E402
from senior_ui.restructure import __main__ as _run_restructure  # noqa: E402
from senior_ui.experiment import report as _session_report    # noqa: E402
# ======================================================================= #

# ---- senior_ui/audit (core.audit · drive.drive · flow.load_flow) ------- #
audit = _audit.audit
drive = _audit.drive
load_flow = _audit.load_flow

# ---- senior_ui/audit/stage.py ------------------------------------------ #
apply_stage = _audit_stage.apply_stage
STAGES = _audit_stage.STAGES

# ---- senior_ui/restructure/__main__.py --------------------------------- #
validate_flow = _run_restructure.validate_flow
parse_reply = _run_restructure.parse_reply
retry_block = _run_restructure.retry_block
brief_failure = _run_restructure.brief_failure
mock_reply = _run_restructure.mock_reply
listening = _run_restructure.listening
PORT = _run_restructure.PORT
# 프롬프트 조립 - 템플릿 읽기 / 선택지 블록 / 슬롯 채우기
load_template = _run_restructure.load_template
choices_block = _run_restructure.choices_block
build_prompt = _run_restructure.build_prompt

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
