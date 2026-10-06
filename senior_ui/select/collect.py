r"""실행 폴더 하나에서 고르기에 쓸 값을 모은다.

새로 걷지 않는다 - 루프가 남긴 summary.json 과 마지막 시도의 audit·plan JSON
만 읽는다. 브라우저도 모델도 부르지 않는다.

summary 에 적힌 경로는 실행 당시의 절대 경로다. 폴더를 옮기면(results/runs/
로 복사하면) 그 경로는 옛 자리를 가리키므로, 파일은 **실행 폴더 안의 같은
이름** 을 먼저 찾는다.

값이 없으면 None 이다. 0 으로 메우지 않는다 - "기록이 없다" 와 "0개다" 는
다른 사실이고, 순위표에서는 "-" 로 보인다.
"""
import io
import json
import os

from senior_ui.tasks import DEFAULT_TASK, task_names

SUMMARY = "summary.json"
BRIEF = "designer_brief.md"

# 설계를 고칠 기회를 쓴 시도. 연결 실패(call · rate_limit · api_rejected)는
# 모델이 아무것도 내지 않았으므로 시도로 세지 않는다.
DESIGN_STAGES = ("plan", "parse", "flow", "truncated", "audit")


def _load(path):
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


def local(run_dir, path):
    """summary 에 적힌 파일의 지금 자리. 실행 폴더 안의 같은 이름이 먼저다."""
    if not path:
        return None
    here = os.path.join(run_dir, os.path.basename(str(path).replace("\\", "/")))
    if os.path.exists(here):
        return here
    return path if os.path.exists(path) else None


def _final_entry(summary):
    """마지막 시도의 summary 항목 (final.attempt 와 n 이 같은 것)."""
    n = (summary.get("final") or {}).get("attempt")
    for a in reversed(summary.get("attempts") or []):
        if a.get("n") == n and a.get("stage") in DESIGN_STAGES:
            return a
    return None


def _count(entry, report, key):
    if entry is not None and isinstance(entry.get(key), int):
        return entry[key]
    if report is not None and isinstance(report.get(key), list):
        return len(report[key])
    return None


def _failures(summary, kind, stages):
    budget = summary.get("budget") or {}
    if isinstance(budget.get(kind + "_used"), int):
        return budget[kind + "_used"]
    attempts = summary.get("attempts") or []
    return sum(1 for a in attempts if a.get("stage") in stages and not a.get("passed"))


def _choice_groups(metrics):
    original = metrics.get("choice_groups_original") or {}
    kept = metrics.get("choice_values_kept") or {}
    selectable = metrics.get("choice_values_selectable") or {}
    groups = list(original) + [g for g in list(kept) + list(selectable) if g not in original]
    out = {}
    for g in groups:
        if g not in out:
            out[g] = {"original": original.get(g), "kept": kept.get(g),
                      "selectable": selectable.get(g)}
    return out


def _error_paths(metrics):
    out = {}
    for name, p in (metrics.get("error_paths") or {}).items():
        p = p or {}
        out[name] = {"appeared": p.get("appeared"), "recovered": p.get("recovered"),
                     "ok": bool(p.get("appeared")) and bool(p.get("recovered"))}
    return out


def _unmatched_changes(plan):
    """진단에 대응되지 않은 변경 - addresses 가 비어 있는 변경의 id."""
    if plan is None:
        return None
    return [c.get("id") for c in plan.get("changes") or [] if not c.get("addresses")]


def run_task(summary, name):
    """실행의 과제. 과제 칸이 없는 옛 summary 는 기본 과제(이체)다 - 공과금이
    생기기 전의 실행이고, 그 뒤로는 루프가 늘 적는다."""
    return summary.get("task") or DEFAULT_TASK


def task_from_name(name):
    """summary 를 못 읽은 폴더의 과제 - 루프가 폴더 이름에 붙인 과제 이름.
    기본 과제는 이름에 붙지 않는다 (loop.run)."""
    parts = name.split("-")[2:]
    for t in task_names():
        if t != DEFAULT_TASK and t in parts:
            return t
    return DEFAULT_TASK


def empty_row(name, run_dir, error):
    return {"name": name, "dir": run_dir, "error": error, "task": task_from_name(name)}


def collect(run_dir):
    """실행 폴더 하나의 값. summary 를 못 읽으면 error 칸만 채워 돌려준다."""
    run_dir = os.path.abspath(run_dir)
    name = os.path.basename(run_dir.rstrip("\\/"))
    path = os.path.join(run_dir, SUMMARY)
    if not os.path.exists(path):
        return empty_row(name, run_dir, "summary.json 없음")
    try:
        s = _load(path)
    except (OSError, ValueError) as e:
        return empty_row(name, run_dir, "summary.json 을 읽지 못함: %s" % e)

    final = s.get("final") or {}
    entry = _final_entry(s)
    report = None
    audit_path = local(run_dir, final.get("audit"))
    if audit_path:
        try:
            report = _load(audit_path)
        except (OSError, ValueError):
            report = None
    metrics = (report or {}).get("metrics") or {}

    plan = None
    plan_path = local(run_dir, final.get("plan"))
    if plan_path:
        try:
            plan = _load(plan_path)
        except (OSError, ValueError):
            plan = None
    plan_sum = s.get("plan") or {}

    attempts = s.get("attempts") or []
    preserved = final.get("preserved")
    git = s.get("git") or {}
    total = (s.get("tokens") or {}).get("total") or {}
    cost = s.get("cost") or {}
    unmatched = _unmatched_changes(plan)
    brief = local(run_dir, final.get("brief")) or local(run_dir, os.path.join(run_dir, BRIEF))

    screens = metrics.get("data-screen_repaired")
    if screens is None and plan is not None:
        screens = len(plan.get("screens") or [])

    return {
        "name": name,
        "dir": run_dir,
        "error": None,
        "task": run_task(s, name),
        "mock": s.get("mock"),
        # 결과
        "passed": s.get("passed") is True,
        "stopped_reason": s.get("stopped_reason"),
        "attempts": sum(1 for a in attempts if a.get("stage") in DESIGN_STAGES),
        "format_failures": _failures(s, "format", ("plan", "parse", "flow", "truncated")),
        "audit_failures": _failures(s, "audit", ("audit",)),
        "final_attempt": final.get("attempt"),
        "fatal": _count(entry, report, "fatal"),
        "warning": _count(entry, report, "warning"),
        # 도구가 고친 흔적 · 재현 조건
        "redeclared": None if preserved is None else list(preserved.get("redeclared") or []),
        "truncated": any(a.get("truncated") or a.get("stage") == "truncated"
                         for a in attempts),
        "dirty": git.get("dirty"),
        "dirty_files": git.get("dirty_files") or [],
        "commit": git.get("commit"),
        "branch": git.get("branch"),
        "model": s.get("model"),
        "response_models": s.get("response_models") or [],
        "reasoning_effort": (s.get("model_call") or {}).get("reasoning_effort"),
        # 구조
        "screens": screens,
        "screens_reached": metrics.get("screens_reached"),
        "data_actions": metrics.get("data-action_repaired"),
        "choice_groups": _choice_groups(metrics),
        "error_paths": _error_paths(metrics),
        # 비용
        "input_tokens": total.get("prompt"),
        "output_tokens": total.get("completion"),
        "reasoning_tokens": total.get("reasoning"),
        "cost_usd": cost.get("total_usd"),
        # 진단 · 계획
        "diagnoses": plan_sum.get("diagnosis_count"),
        "changes": len(plan.get("changes") or []) if plan is not None
        else plan_sum.get("changes"),
        "unmatched_changes": None if unmatched is None else len(unmatched),
        "unmatched_change_ids": unmatched or [],
        "unaddressed_diagnoses": plan_sum.get("unaddressed") or [],
        # 파일
        "html": local(run_dir, final.get("html")),
        "audit": audit_path,
        "brief": brief,
    }
