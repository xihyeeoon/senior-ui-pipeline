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
# 다듬기(보고 다듬기)의 시도. 설계를 처음 통과시키기까지의 시도 수 · 실패 수에
# 넣지 않고 따로 센다.
REFINE_PHASES = ("refine", "refine_fix")


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


def _truncation(attempts, final_n):
    """(마지막 시도가 잘렸나, 중간 시도의 잘림 횟수).

    마지막 시도만 최종 시안을 만든다. 중간 시도가 잘렸어도 그다음 시도가 다시
    물어 시안을 냈으면 그 시안과는 상관없다 - 그래서 문지기는 마지막 것만 보고,
    중간의 잘림은 횟수로만 남긴다."""
    # 다듬기 시도의 잘림은 중간 잘림에 넣지 않는다 - 다듬기가 떨어지면 최종은 그
    # 전의 통과한 빌드로 되돌아간다 (final.attempt 가 그것을 가리킨다).
    cut = [a.get("n") for a in attempts
           if (a.get("truncated") or a.get("stage") == "truncated")
           and (a.get("phase") not in REFINE_PHASES or a.get("n") == final_n)]
    if final_n is None:
        design = [a.get("n") for a in attempts if a.get("stage") in DESIGN_STAGES]
        final_n = design[-1] if design else None
    return final_n in cut and final_n is not None, sum(1 for n in cut if n != final_n)


def _count(entry, report, key):
    if entry is not None and isinstance(entry.get(key), int):
        return entry[key]
    if report is not None and isinstance(report.get(key), list):
        return len(report[key])
    return None


def _failures(summary, kind, stages):
    """생성 단계의 실패 수. 다듬기 시도(REFINE_PHASES)는 넣지 않는다 - 다듬기는 예산을
    따로 쓰고 summary.budget 에 들어가지 않는다. 그 수는 _refine_failures."""
    budget = summary.get("budget") or {}
    if isinstance(budget.get(kind + "_used"), int):
        return budget[kind + "_used"]
    attempts = summary.get("attempts") or []
    return sum(1 for a in attempts if a.get("stage") in stages and not a.get("passed")
               and a.get("phase") not in REFINE_PHASES)


def _refine_failures(summary, kind, stages):
    """다듬기의 실패 수. 다듬기 기록이 없으면(다듬기 전의 실행) None."""
    rf = summary.get("refine")
    if not isinstance(rf, dict):
        return None
    if isinstance(rf.get(kind + "_failures"), int):
        return rf[kind + "_failures"]
    return sum(1 for a in summary.get("attempts") or []
               if a.get("phase") in REFINE_PHASES and a.get("stage") in stages
               and not a.get("passed"))


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


def _warnings_by_check(report):
    """최종 검사의 경고를 검사별로 `{검사: {"count", "first"}}`. 리포트가 없으면
    None - 모른다. 고르기 규칙의 no_warning_checks 가 이것을 본다 (warning 총수만
    세면 "어느 검사의 경고인가" 를 규칙으로 말할 수 없다)."""
    if report is None:
        return None
    out = {}
    for w in report.get("warning") or []:
        c = out.setdefault(w.get("check") or "?", {"count": 0, "first": None})
        c["count"] += 1
        if c["first"] is None:
            c["first"] = w.get("detail")
    return out


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
    truncated, truncated_middle = _truncation(attempts, final.get("attempt"))
    brief = local(run_dir, final.get("brief")) or local(run_dir, os.path.join(run_dir, BRIEF))

    screens = metrics.get("data-screen_repaired")
    if screens is None and plan is not None:
        screens = len(plan.get("screens") or [])
    budget = s.get("budget") or {}
    refine = s.get("refine") if isinstance(s.get("refine"), dict) else {}
    reverted = refine.get("reverted") if isinstance(refine.get("reverted"), dict) else None

    return {
        "name": name,
        "dir": run_dir,
        "error": None,
        "task": run_task(s, name),
        "mock": s.get("mock"),
        # 결과
        "passed": s.get("passed") is True,
        "stopped_reason": s.get("stopped_reason"),
        "attempts": sum(1 for a in attempts if a.get("stage") in DESIGN_STAGES
                        and a.get("phase") not in REFINE_PHASES),
        "format_failures": _failures(s, "format", ("plan", "parse", "flow", "truncated")),
        "audit_failures": _failures(s, "audit", ("audit",)),
        "refine_format_failures": _refine_failures(s, "format",
                                                   ("plan", "parse", "flow", "truncated")),
        "refine_audit_failures": _refine_failures(s, "audit", ("audit",)),
        "final_attempt": final.get("attempt"),
        "fatal": _count(entry, report, "fatal"),
        "warning": _count(entry, report, "warning"),
        # 검사별 경고 (고르기 규칙의 no_warning_checks)
        "warning_by_check": _warnings_by_check(report),
        # 최종 빌드가 어디서 왔나 (보고 다듬기)
        "final_from": (s.get("refine") or {}).get("final_label"),
        # 실행 조건 - 고르기 규칙의 stage · budget 문지기가 본다 (감사 B-04). 기록이
        # 없으면 None 이다 (그 문지기는 "기록 없음" 으로 뺀다).
        "stage": s.get("stage"),
        "budget": {"format": budget.get("format_budget"),
                   "audit": budget.get("audit_budget"),
                   "refine": refine.get("budget")},
        # 다듬기가 떨어져 직전 통과 빌드로 되돌렸으면 그 회차 (gates.reverted)
        "reverted": reverted.get("round") if reverted else None,
        "reverted_to": reverted.get("to_attempt") if reverted else None,
        # 도구가 버그로 멈췄다 (종료 2). 통과한 빌드가 있어도 뺀다 (gates.no_internal_error)
        "internal_error": s.get("stopped_reason") == "internal_error",
        # 도구가 고친 흔적 · 재현 조건
        "redeclared": None if preserved is None else list(preserved.get("redeclared") or []),
        "truncated": truncated,
        "truncated_middle": truncated_middle,
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
