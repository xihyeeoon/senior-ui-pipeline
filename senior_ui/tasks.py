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
     "required_error_paths": ["wrong-account", "wrong-bank"]}

경로는 저장소 루트 기준이고 구분자는 '/' 다. 기본 과제는 이체다 - 과제를
고르지 않은 실행은 전과 같아야 한다.
"""
import io
import json
import os

from .config import ROOT, TASKS_DIR

DEFAULT_TASK = "transfer"

# 과제 파일에 꼭 있어야 할 칸. 빠진 칸을 다른 과제의 값으로 메우지 않는다.
KEYS = ("id", "description", "original", "flow", "done_expect",
        "required_truth", "required_error_paths")


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
    desc = task["description"]
    task["description"] = "\n".join(desc) if isinstance(desc, list) else str(desc)
    return task
