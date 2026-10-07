r"""검사기를 라이브러리로 부르는 한 지점.

부르는 쪽이 흐름을 읽고, 판정 입력으로 바꾸고(audit.inputs.judged_flow),
브라우저로 한 번 걷고, 단계 밖 검사를 걷어내고, 무엇을 검사했는지 inputs 에
적는다 - CLI(senior_ui/audit/__main__.py)가 모델 흐름에 하는 일과 같은 순서다.
판정 입력을 고치는 일은 여기서 하지 않는다. 그것은 judged_flow 한 곳에 있고 CLI
도 같은 함수를 부른다.
"""
import asyncio
import io

from senior_ui import audit as A
from senior_ui.audit import stage as S
from senior_ui.audit.checks.i_choices import original_groups
from senior_ui.audit.inputs import judged_flow, read_flow


def run_audit(orig_snapshot, orig_html, html_path, flow_path, url, shots, stage,
              original_url=None, allowed_removals=None, task=None, see=False):
    """senior_ui.audit 로 검사한 뒤 단계 밖 검사를 걷어낸다. 와이어프레임 단계에서는
    대비·레이아웃·상태 색·미정의 클래스를 보지 않는다 - 아직 채우지 않은
    디테일이기 때문이다. 걸러낸 이유는 checks_stood_down 에 남는다.

    `task` 는 이 실행의 과제다. 주지 않으면 기본 과제(이체)다. 모델의 흐름에
    적힌 task · truth · stage 같은 판정 기준은 judged_flow 가 버린다."""
    flow = judged_flow(read_flow(flow_path), task=task, stage=stage,
                       allowed_removals=allowed_removals)
    rep_html = io.open(html_path, encoding="utf-8").read()
    # see 는 다듬기가 모델에게 보여 줄 그림을 더 찍는다 (shots/see/). 검사는
    # 보지 않는다. 선택지 무리는 원본이 정한다 - 실행 시작에 걸은 원본 스냅샷에서
    # 무리였던 이름을 넘겨 생성물에서는 놓인 모양과 상관없이 센다.
    rep = asyncio.run(A.drive(url, flow, want_shots=shots, see=see,
                              original_groups=original_groups(orig_snapshot, flow)))
    report = A.audit(orig_snapshot, rep, orig_html, rep_html, flow)
    report = S.apply_stage(report, flow["stage"])
    # 비교 기준이 된 문서를 그대로 적는다. 부르는 쪽이 --original 로 바꿀 수
    # 있으므로, 여기서 못박으면 리포트가 비교하지 않은 문서를 가리키게 된다.
    report["inputs"] = {"original": original_url, "repaired": url,
                        "flow": flow_path, "stage": flow["stage"],
                        "flow_author": "model"}
    return report
