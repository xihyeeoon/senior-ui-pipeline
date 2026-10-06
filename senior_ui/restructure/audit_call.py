r"""검사기를 라이브러리로 부르는 한 지점.

senior_ui.audit 은 이 루프 때문에 한 줄도 바뀌지 않는다. 부르는 쪽이 흐름을
읽고, 브라우저로 한 번 걷고, 단계 밖 검사를 걷어내고, 무엇을 검사했는지
inputs 에 적는다 - CLI(senior_ui/audit/__main__.py)가 하는 일과 같은 순서다.
"""
import asyncio
import io
import json
import os

from senior_ui import audit as A
from senior_ui.audit import stage as S
from senior_ui.audit.flow import task_truth
from senior_ui.config import FLOWS_DIR
from senior_ui.tasks import DEFAULT_TASK, load_task


# 허용하는 제거를 적는 파일. 연구자가 손으로 관리하는 것이고, 이것 말고는
# 어디에서도 읽지 않는다.
#
# 검사 I 는 흐름 명세의 choices_removed 를 읽어 그 값을 누락으로 세지 않는다.
# 그 선언은 "연구자가 안전을 이유로 뺐다" 는 뜻인데, 재구성 루프에서는 흐름
# 명세를 **모델이** 쓴다 - 모델이 스스로 그것을 적으면 검사를 끄는 장치가 된다.
# 그래서 선언을 읽는 곳을 모델이 쓸 수 없는 파일 하나로 옮긴다.
ALLOWED_REMOVALS = os.path.join(FLOWS_DIR, "allowed_removals.json")

# 과제별로 적는다. 허용 목록이 과제끼리 섞이지 않게 하기 위해서다 - 한 과제에서
# 안전한 제거가 다른 과제에서도 안전하다는 보장은 없다. 부르는 쪽(루프)이 과제
# 이름을 넘기고, 주지 않으면 기본 과제다.
TASK = DEFAULT_TASK


def load_allowed_removals(task=TASK, path=ALLOWED_REMOVALS):
    """그 과제에서 빼도 되는 선택지. {action: {"values": [...], "reason": "..."}}.

    파일이 없으면 빈 선언이다 - 그때 검사 I 는 모든 누락을 fatal 로 센다.
    모양이 틀린 파일은 빈 선언으로 넘어가지 않고 멈춘다. 허용 목록을 적어
    두었는데 조용히 무시되면, 연구자는 적었다고 믿고 결과는 다르게 나온다.
    """
    if not os.path.exists(path):
        return {}
    try:
        data = json.load(io.open(path, encoding="utf-8-sig"))
    except ValueError as e:
        raise RuntimeError("%s 를 JSON 으로 읽지 못했다: %s" % (path, e))
    if not isinstance(data, dict):
        raise RuntimeError("%s 의 최상위는 과제 이름을 키로 하는 객체여야 한다" % path)
    allowed = data.get(task, {})
    if not isinstance(allowed, dict):
        raise RuntimeError("%s 의 %r 이 객체가 아니다" % (path, task))
    for action, d in allowed.items():
        if not isinstance(d, dict) or not isinstance(d.get("values"), list):
            raise RuntimeError('%s 의 %r/%r 은 {"values": [...], "reason": "..."} '
                               "여야 한다" % (path, task, action))
    return allowed


def merge_allowed_removals(flow, allowed):
    """검사 직전에 허용 목록을 흐름에 합친다.

    모델이 쓴 흐름 명세에 섞지 않고 여기서 합치는 이유는, 둘을 섞으면 어느
    것이 모델의 말이고 어느 것이 연구자의 말인지 다시 가를 수 없어서다.
    """
    flow["choices_removed"] = dict(allowed)
    return flow


def run_audit(orig_snapshot, orig_html, html_path, flow_path, url, shots, stage,
              original_url=None, allowed_removals=None, task=None, see=False):
    """senior_ui.audit 로 검사한 뒤 단계 밖 검사를 걷어낸다. 와이어프레임 단계에서는
    대비·레이아웃·상태 색·미정의 클래스를 보지 않는다 - 아직 채우지 않은
    디테일이기 때문이다. 걸러낸 이유는 checks_stood_down 에 남는다.

    `task` 는 이 실행의 과제다. 주지 않으면 기본 과제(이체)다. 모델의 흐름에
    적힌 task 는 듣지 않는다 - 과제는 실행이 정한다."""
    task = task or DEFAULT_TASK
    flow = merge_allowed_removals(A.load_flow(flow_path, task=task),
                                  allowed_removals or {})
    # 정답도 모델의 말을 듣지 않는다. 모델이 흐름 명세에 truth 를 적어도 검사는
    # 원본 과제의 정답(과제의 원본 흐름)으로 한다 - 모델이 정답을 고르게 두면
    # 자기가 보여 주는 값을 정답으로 적어 검사 B 를 끌 수 있다.
    flow["truth"] = task_truth(task)
    # 과제가 정한 오류 경로는 모두 걸어야 한다. 흐름 명세에서 빠졌으면 형식
    # 검사가 먼저 막지만, 검사 J 도 같은 목록으로 한 번 더 본다.
    flow["error_paths_required"] = list(load_task(task)["required_error_paths"])
    rep_html = io.open(html_path, encoding="utf-8").read()
    # see 는 다듬기가 모델에게 보여 줄 그림을 더 찍는다 (shots/see/). 검사는
    # 보지 않는다.
    rep = asyncio.run(A.drive(url, flow, want_shots=shots, see=see))
    report = A.audit(orig_snapshot, rep, orig_html, rep_html, flow)
    report = S.apply_stage(report, stage)
    # 비교 기준이 된 문서를 그대로 적는다. 부르는 쪽이 --original 로 바꿀 수
    # 있으므로, 여기서 못박으면 리포트가 비교하지 않은 문서를 가리키게 된다.
    report["inputs"] = {"original": original_url, "repaired": url,
                        "flow": flow_path, "stage": stage}
    return report
