r"""실행 폴더 읽기. 쓰지 않는다.

설계서는 검사를 통과한 HTML 에서만 뽑는다. 통과하지 못한 실행 · 막혀 멈춘 실행 ·
최종 검사 결과가 통과가 아닌 실행은 만들지 않고 이유를 돌려준다 (NotReady, 종료 2).

summary.json 의 경로는 그 실행을 돌린 PC 의 절대 경로다. 실행 폴더를 옮겼을 수
있으므로(results/runs/ 사본) 같은 이름의 파일이 실행 폴더 안에 있으면 그것을 쓴다.
"""
import hashlib
import io
import json
import os
import subprocess

from senior_ui import tasks as T
from senior_ui.config import ROOT

SUMMARY = "summary.json"


class NotReady(Exception):
    """설계서를 만들 수 없는 실행이다. 메시지가 이유다."""


def _read_json(path):
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


def local(run_dir, path):
    """summary 가 가리키는 파일 - 실행 폴더 안에 같은 이름이 있으면 그것."""
    if not path:
        return None
    here = os.path.join(run_dir, os.path.basename(str(path)))
    if os.path.exists(here):
        return here
    return str(path) if os.path.exists(str(path)) else None


def load_run(run_dir):
    """`{"dir", "name", "summary", "task", "html", "flow", "audit", "plan", "diagnosis",
    "audit_report", "plan_data", "diagnosis_data"}`. 만들 수 없으면 NotReady."""
    run_dir = os.path.abspath(run_dir)
    if not os.path.isdir(run_dir):
        raise NotReady("실행 폴더가 없다: %s" % run_dir)
    sp = os.path.join(run_dir, SUMMARY)
    if not os.path.exists(sp):
        raise NotReady("%s 이 없다 - 도중에 멈춘 실행이거나 실행 폴더가 아니다" % SUMMARY)
    try:
        summary = _read_json(sp)
    except (ValueError, OSError) as e:
        raise NotReady("%s 을 읽지 못했다: %s" % (SUMMARY, e))
    if summary.get("stopped_reason") == "stuck":
        raise NotReady("같은 실패가 되풀이되어 멈춘 실행이다 (stopped_reason: stuck) - "
                       "통과한 빌드가 없다")
    if not summary.get("passed"):
        raise NotReady("통과하지 못한 실행이다 (passed: %s, stopped_reason: %s) - 설계서는 "
                       "검사를 통과한 HTML 에서만 뽑는다"
                       % (summary.get("passed"), summary.get("stopped_reason")))
    final = summary.get("final") or {}
    files = {k: local(run_dir, final.get(k)) for k in ("html", "flow", "audit", "plan",
                                                       "diagnosis")}
    for k in ("html", "flow", "audit"):
        if not files[k]:
            raise NotReady("최종 빌드의 %s 파일이 실행 폴더에 없다 (summary.final.%s = %s)"
                           % (k, k, final.get(k)))
    report = _read_json(files["audit"])
    if not report.get("passed"):
        raise NotReady("최종 빌드의 검사 결과(%s)가 통과가 아니다 - fatal %d건"
                       % (os.path.basename(files["audit"]), len(report.get("fatal") or [])))
    task = summary.get("task") or T.DEFAULT_TASK
    try:
        task_def = T.load_task(task)
    except ValueError as e:
        raise NotReady("과제를 읽지 못했다: %s" % e)
    return {"dir": run_dir, "name": os.path.basename(run_dir), "summary": summary,
            "task": task, "task_def": task_def, "final": final,
            "audit_report": report,
            "plan_data": _read_json(files["plan"]) if files["plan"] else None,
            "diagnosis_data": _read_json(files["diagnosis"]) if files["diagnosis"] else None,
            **files}


def git(*args):
    try:
        return subprocess.run(["git"] + list(args), cwd=ROOT, capture_output=True,
                              check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None


def fingerprint(data):
    """줄끝을 LF 로 맞춘 내용의 sha256. Windows 작업 트리는 CRLF 로 체크아웃되고
    (core.autocrlf) 저장소의 파일은 LF 라, 그대로 재면 같은 원본이 둘로 보인다."""
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def original_fingerprint(task_def, commit=None):
    """원본 HTML 의 지문 (fingerprint). 실행의 커밋에서 그 파일을 읽을 수 있으면 그것
    (실행이 본 원본), 아니면 지금 파일. 둘이 다르면 same_as_now 가 false 다."""
    rel = task_def["original"]
    path = T.abs_path(rel)
    now = None
    if os.path.exists(path):
        with open(path, "rb") as f:
            now = fingerprint(f.read())
    at_commit = git("show", "%s:%s" % (commit, rel)) if commit else None
    if at_commit is not None:
        sha = fingerprint(at_commit)
        return {"path": rel, "sha256": sha, "source": "commit",
                "same_as_now": sha == now}
    return {"path": rel, "sha256": now, "source": "now", "same_as_now": True}


def head_commit():
    out = git("rev-parse", "HEAD")
    return out.decode("ascii", "replace").strip() if out else None
