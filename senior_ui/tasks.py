r"""과제 정의 읽기. 과제 하나가 tasks/<이름>.json 하나다.

과제마다 다른 것 - 프롬프트의 과제 설명, 출발점이 되는 원본 HTML, 그 원본을
걷는 흐름 파일, 완료 화면에서 확인할 값, 흐름의 truth 에 꼭 있어야 할 키,
반드시 걸어야 할 오류 경로 - 을 한 파일에 모은다. 코드에 두면 과제를 하나 더
다룰 때마다 그 자리들을 찾아 고쳐야 하고, 한 자리만 빠져도 다른 과제의 값으로
조용히 돈다.

    {"id": "transfer",
     "label": "이체",
     "description": ["프롬프트의 {{TASK}} 에 들어갈 글, 한 줄에 한 원소"],
     "original": "inputs/original_transfer.html",
     "flow": "flows/original.json",
     "done_expect": [["#dn-amt", "{AMOUNT_SHOWN}"]],
     "required_truth": ["ACCOUNT", "AMOUNT", "BANK", "NAME"],
     "keep_on_screen": {"NAME": "recipient name"},
     "dialog_ok_values": ["AMOUNT_SHOWN", "AMOUNT", "ACCOUNT"],
     "required_error_paths": ["wrong-account", "wrong-bank"]}

그 밖에 `prompt` 칸이 재구성 프롬프트의 과제 문단을 담는다 - 문서의
`{{TASK_<칸>}}` 슬롯 하나에 줄 목록 하나 (restructure/prompt.py 의 _with_task).

`not_choices` 는 원본에서 같은 data-action 을 가진 형제 무리 가운데 **선택지가
아닌 것** 과 그 이유다 - `{"menu-chip": "분류로 스크롤하는 표지판 — 찾아가는 수단"}`.
검사 I 는 형제 무리를 선택지로 세는데, 누르면 스크롤만 하는 표지판 · 탭은 고르는
대상이 아니다. 연구자가 정하는 칸이고(11-9), 판정 입력(audit.inputs.judged_flow ·
flow.load_flow)이 흐름에 붙인다. 없으면 빈 선언이다. flows/allowed_removals.json
(선택지인데 일부러 뺀 값)과는 다른 뜻이다.

경로는 저장소 루트 기준이고 구분자는 '/' 다. 기본 과제는 이체다 - 과제를
고르지 않은 실행은 전과 같아야 한다.
"""
import hashlib
import io
import json
import os

from .config import ROOT, TASKS_DIR

DEFAULT_TASK = "transfer"

# 과제 파일에 꼭 있어야 할 칸. 빠진 칸을 다른 과제의 값으로 메우지 않는다.
#
#   keep_on_screen    원본 화면에 있던 그 값이 빌드 화면에서 사라지면 검사 B 가
#                     경고한다. {truth 키: 경고에 쓸 이름}
#   dialog_ok_values  대화상자가 말해도 되는 숫자 (truth 키). 그 밖의 숫자를
#                     말하는 대화상자는 검사 B 가 그 숫자를 함께 적는다
KEYS = ("id", "description", "original", "flow", "done_expect",
        "required_truth", "required_error_paths", "keep_on_screen",
        "dialog_ok_values")


def task_names():
    """tasks/ 에 있는 과제 이름들."""
    if not os.path.isdir(TASKS_DIR):
        return []
    return sorted(f[:-len(".json")] for f in os.listdir(TASKS_DIR)
                  if f.endswith(".json"))


def task_path(name):
    return os.path.join(TASKS_DIR, "%s.json" % name)


def abs_path(rel):
    """과제 파일의 루트 기준 경로를 절대 경로로. 이미 절대 경로면 그대로."""
    if os.path.isabs(str(rel)):
        return str(rel)
    return os.path.join(ROOT, *str(rel).split("/"))


def fingerprint(data):
    """줄끝을 LF 로 맞춘 내용(bytes)의 sha256. Windows 작업 트리는 CRLF 로 체크아웃되고
    (core.autocrlf) 저장소의 파일은 LF 라, 그대로 재면 같은 원본이 PC 마다 둘로 보인다."""
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def file_sha256(path):
    """파일 하나의 지문 (fingerprint). 읽지 못하면 OSError."""
    with open(path, "rb") as f:
        return fingerprint(f.read())


def original_sha256(name=None):
    """과제의 원본 HTML(과제 파일의 original)의 지금 지문.

    재구성 실행은 쓴 원본의 지문을 summary.json 과 run.log 첫 줄에 남기고
    (restructure/loop.py), 고르기의 문지기 original: "current" 가 그것을 이 값과
    견준다 (select/rule.py) - 원본이 고쳐지면 고치기 전 원본으로 만든 실행은 같은
    조건의 반복이 아니다."""
    return file_sha256(abs_path(load_task(name)["original"]))


def not_choices_of(task, path):
    """과제의 선택지 아님 선언 `{data-action: 이유}`. 칸이 없으면 빈 선언.

    이유가 없거나 모양이 틀린 선언은 멈춘다 - 무리 하나를 검사 I 에서 빼는 일이라,
    조용히 받거나 버리면 연구자가 적은 것과 판정이 다르게 돈다."""
    spec = task.get("not_choices", {})
    if not isinstance(spec, dict) or not all(
            isinstance(why, str) and why.strip() for why in spec.values()):
        raise ValueError('%s 의 not_choices 는 {"<data-action>": "<이유>"} 여야 한다 '
                         "(이유는 빈 글이 아니다)" % path)
    return dict(spec)


def load_task(name=None):
    """과제 정의 하나. `description` 은 줄을 이은 문자열로 돌려준다.

    없는 과제나 칸이 빠진 파일은 ValueError 로 멈춘다 - 조용히 기본 과제로
    넘어가면 공과금이라고 믿고 돌린 실행이 이체로 돈다."""
    name = name or DEFAULT_TASK
    path = task_path(name)
    if not os.path.exists(path):
        raise ValueError("과제 %r 이 없다 (%s). 있는 것: %s"
                         % (name, path, ", ".join(task_names()) or "없음"))
    with io.open(path, encoding="utf-8") as f:
        task = json.load(f)
    missing = [k for k in KEYS if k not in task]
    if missing:
        raise ValueError("%s 에 %s 가 없다" % (path, ", ".join(missing)))
    if task["id"] != name:
        raise ValueError("%s 의 id 는 %r 이어야 한다 (지금은 %r)"
                         % (path, name, task["id"]))
    task["not_choices"] = not_choices_of(task, path)
    desc = task["description"]
    task["description"] = "\n".join(desc) if isinstance(desc, list) else str(desc)
    return task
