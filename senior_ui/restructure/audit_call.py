r"""검사기를 라이브러리로 부르는 한 지점.

senior_ui.audit 은 이 루프 때문에 한 줄도 바뀌지 않는다. 부르는 쪽이 흐름을
읽고, 브라우저로 한 번 걷고, 단계 밖 검사를 걷어내고, 무엇을 검사했는지
inputs 에 적는다 - CLI(senior_ui/audit/__main__.py)가 하는 일과 같은 순서다.
"""
import asyncio
import io

from senior_ui import audit as A
from senior_ui.audit import stage as S
from senior_ui.config import ORIGINAL_URL


def run_audit(orig_snapshot, orig_html, html_path, flow_path, url, shots, stage):
    """senior_ui.audit 로 검사한 뒤 단계 밖 검사를 걷어낸다. 와이어프레임 단계에서는
    대비·레이아웃·상태 색·미정의 클래스를 보지 않는다 - 아직 채우지 않은
    디테일이기 때문이다. 걸러낸 이유는 checks_stood_down 에 남는다."""
    flow = A.load_flow(flow_path)
    rep_html = io.open(html_path, encoding="utf-8").read()
    rep = asyncio.run(A.drive(url, flow, want_shots=shots))
    report = A.audit(orig_snapshot, rep, orig_html, rep_html, flow)
    report = S.apply_stage(report, stage)
    report["inputs"] = {"original": ORIGINAL_URL, "repaired": url, "flow": flow_path,
                        "stage": stage}
    return report
