r"""규칙 파일 읽기 · 문지기(gates) · 줄 세우기(ordering).

규칙은 flows/selection_rule.json 에 있다. 여기에는 규칙을 **적용하는 법**
만 있다 - 어느 값을 볼지, 어떤 순서로 볼지, 가중치가 얼마인지는 전부 파일에서
온다. 규칙을 바꾸려고 이 파일을 고칠 일이 생기면 그것은 규칙 파일의 형식을
넓히는 일이다.

모르는 칸은 멈춘다. 오타 난 문지기 이름을 조용히 넘기면 그 문지기는 없는 것과
같고, 그 규칙으로 고른 결과는 적힌 규칙과 다르다.
"""
import collections
import hashlib
import io
import json
import os
import re
import statistics
import subprocess

from senior_ui.config import FLOWS_DIR, ROOT
from senior_ui.tasks import load_task, original_sha256

DEFAULT_RULE = os.path.join(FLOWS_DIR, "selection_rule.json")

GATES = ("passed", "no_redeclared", "no_truncated", "clean_tree", "not_mock", "model",
         "no_warning_checks", "stage", "budget", "commit", "reverted", "no_internal_error",
         "original")

# 실행 조건 문지기 (감사 B-04 · D-4 (가)). 값이 null 이거나 칸이 없으면 보지 않는다 -
# 칸이 생기기 전의 규칙(지난 결과 JSON)을 다시 쓸 때 그 규칙 그대로 돈다.
#   budget   {"format", "audit", "refine"} 중 적은 것만 본다 (summary.budget 의
#            format_budget · audit_budget, summary.refine.budget)
#   commit   null 이면 후보들 중 가장 많은 커밋을 기준으로 한다 (commit_basis)
#   reverted 다듬기가 떨어져 직전 통과 빌드로 되돌린 실행을 어떻게 하나
BUDGET_KEYS = (("format", "형식"), ("audit", "검사"), ("refine", "다듬기"))
REVERTED = ("allow", "last", "exclude")
#   original "current" 면 실행의 original_sha256 이 그 과제의 지금 원본 파일(과제 파일의
#            original)의 지문과 같아야 한다. 값이 없는 옛 실행도 뺀다 (11-11)
ORIGINAL = ("current",)
COMMIT = re.compile(r"^[0-9a-f]{7,40}$")

# 줄 세우기와 대표성에 쓸 수 있는 값 (collect.collect 의 칸).
NUMERIC = ("warning", "fatal", "attempts", "format_failures", "audit_failures",
           "screens", "data_actions", "changes", "unmatched_changes", "diagnoses",
           "input_tokens", "output_tokens", "reasoning_tokens", "cost_usd")
REPRESENTATIVE = "representative"

# 같다고 볼 자릿수. 대표성 거리는 나눗셈의 합이라 같은 값이 끝자리에서 갈린다.
ROUND = 9


class RuleError(ValueError):
    pass


# --------------------------------------------------------------------------- #
# 읽기
# --------------------------------------------------------------------------- #
def validate(rule):
    """형식이 맞지 않으면 RuleError. 맞으면 그대로 돌려준다."""
    if not isinstance(rule, dict):
        raise RuleError("규칙은 JSON 객체여야 한다")
    unknown = sorted(set(rule) - {"version", "note", "gates", "ordering"})
    if unknown:
        raise RuleError("모르는 칸: %s" % ", ".join(unknown))
    gates = rule.get("gates")
    if not isinstance(gates, dict):
        raise RuleError("gates 는 객체여야 한다")
    unknown = sorted(set(gates) - set(GATES))
    if unknown:
        raise RuleError("모르는 문지기: %s (있는 것: %s)"
                        % (", ".join(unknown), ", ".join(GATES)))
    for k, v in gates.items():
        if k == "model":
            if v is not None and not (isinstance(v, str) and v):
                raise RuleError("gates.model 은 null 이거나 모델 이름이어야 한다")
        elif k == "no_warning_checks":
            if not (isinstance(v, list) and all(isinstance(x, str) and x for x in v)):
                raise RuleError("gates.no_warning_checks 는 검사 이름(\"J\" 등)의 목록이어야 "
                                "한다")
        elif k == "stage":
            if v is not None and not (isinstance(v, str) and v):
                raise RuleError("gates.stage 는 null 이거나 검사 단계 이름이어야 한다")
        elif k == "budget":
            names = [b for b, _ in BUDGET_KEYS]
            if v is not None and not (
                    isinstance(v, dict) and set(v) <= set(names)
                    and all(isinstance(x, int) and not isinstance(x, bool) and x >= 0
                            for x in v.values())):
                raise RuleError("gates.budget 는 null 이거나 {%s} 중 몇 칸의 0 이상 정수여야 "
                                "한다" % ", ".join(names))
        elif k == "commit":
            if v is not None and not (isinstance(v, str) and COMMIT.match(v)):
                raise RuleError("gates.commit 은 null 이거나 커밋 해시(16진수 7~40자)여야 한다")
        elif k == "reverted":
            if v not in REVERTED:
                raise RuleError("gates.reverted 는 %s 중 하나여야 한다"
                                % " | ".join('"%s"' % x for x in REVERTED))
        elif k == "original":
            if v is not None and v not in ORIGINAL:
                raise RuleError("gates.original 은 null 이거나 %s 여야 한다"
                                % " | ".join('"%s"' % x for x in ORIGINAL))
        elif not isinstance(v, bool):
            raise RuleError("gates.%s 는 true/false 여야 한다" % k)
    ordering = rule.get("ordering")
    if not isinstance(ordering, list) or not ordering:
        raise RuleError("ordering 은 비어 있지 않은 목록이어야 한다")
    for i, o in enumerate(ordering):
        where = "ordering[%d]" % i
        if not isinstance(o, dict) or "by" not in o:
            raise RuleError("%s 에 by 가 없다" % where)
        if o["by"] == REPRESENTATIVE:
            extra = sorted(set(o) - {"by", "metrics"})
            metrics = o.get("metrics")
            if not isinstance(metrics, dict) or not metrics:
                raise RuleError("%s.metrics 는 비어 있지 않은 객체여야 한다" % where)
            for m, w in metrics.items():
                if m not in NUMERIC:
                    raise RuleError("%s.metrics 의 %s 는 모르는 값이다 (있는 것: %s)"
                                    % (where, m, ", ".join(NUMERIC)))
                if isinstance(w, bool) or not isinstance(w, (int, float)) or w < 0:
                    raise RuleError("%s.metrics.%s 의 가중치는 0 이상의 수여야 한다"
                                    % (where, m))
        else:
            extra = sorted(set(o) - {"by", "order"})
            if o["by"] not in NUMERIC:
                raise RuleError("%s.by=%r 는 모르는 값이다 (있는 것: %s, %s)"
                                % (where, o["by"], ", ".join(NUMERIC), REPRESENTATIVE))
            if o.get("order", "asc") not in ("asc", "desc"):
                raise RuleError("%s.order 는 asc 나 desc 여야 한다" % where)
        if extra:
            raise RuleError("%s 의 모르는 칸: %s" % (where, ", ".join(extra)))
    return rule


def _git(*args):
    try:
        return subprocess.run(["git"] + list(args), cwd=ROOT, capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def provenance(path, text):
    """그때 쓴 규칙이 무엇이었는지 - 내용 · 해시 · 커밋.

    파일의 커밋 해시만으로는 부족하다. 커밋한 뒤에 고쳐 놓고 돌렸으면 그 해시는
    쓴 규칙을 가리키지 않는다. 그래서 내용 전문과 sha256 을 함께 남기고, 저장소의
    것과 다른지(dirty)도 적는다."""
    rel = os.path.relpath(os.path.abspath(path), ROOT).replace("\\", "/")
    inside = not rel.startswith("..")
    head = _git("rev-parse", "HEAD")
    file_commit = _git("log", "-1", "--format=%H", "--", rel) if inside else None
    status = _git("status", "--porcelain", "--", rel) if inside else None
    return {"path": rel if inside else os.path.abspath(path),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "repo_commit": head,
            "rule_file_commit": file_commit or None,
            "rule_file_dirty": None if status is None else bool(status)}


def load_rule(path=None):
    """(규칙, 출처). 지난 고르기의 결과 JSON 을 주면 그때 쓴 규칙을 다시 쓴다."""
    path = path or DEFAULT_RULE
    try:
        text = io.open(path, encoding="utf-8").read()
        data = json.loads(text)
    except (OSError, ValueError) as e:
        raise RuleError("규칙 파일을 읽지 못했다 (%s): %s" % (path, e))
    if isinstance(data, dict) and isinstance(data.get("rule"), dict) \
            and "content" in data["rule"]:
        # 지난 고르기 결과 - 그때의 규칙과 그 출처를 그대로 쓴다.
        src = dict(data["rule"])
        rule = validate(src.pop("content"))
        src["replayed_from"] = os.path.abspath(path)
        return rule, src
    return validate(data), provenance(path, text)


# --------------------------------------------------------------------------- #
# 문지기
# --------------------------------------------------------------------------- #
def gate_reasons(row, gates, original=None):
    """이 실행이 어긴 문지기마다 이유 한 줄. 비어 있으면 후보다.

    `original` 은 그 과제의 지금 원본 `{"path", "sha256"}` 이다 (original_basis) -
    gates.original 이 켜져 있을 때만 쓴다."""
    if row.get("error"):
        return [row["error"]]
    out = []
    if gates.get("passed") and not row.get("passed"):
        why = row.get("stopped_reason")
        out.append("통과하지 못함" + (" (%s)" % why if why else ""))
    if gates.get("no_redeclared") and row.get("redeclared"):
        out.append("도구가 고침: redeclared %s" % ", ".join(row["redeclared"]))
    if gates.get("no_truncated") and row.get("truncated"):
        out.append("마지막 시도의 답이 길이 제한에서 잘림")
    if gates.get("clean_tree") and row.get("dirty") is not False:
        out.append("작업 트리가 깨끗하지 않음" if row.get("dirty")
                   else "작업 트리 기록 없음 (git.dirty)")
    if gates.get("not_mock") and row.get("mock"):
        out.append("mock 실행 (%s)" % row["mock"])
    # 이 검사들의 경고가 하나라도 있으면 뺀다. 기본 규칙은 ["J"] - 오류를 알리긴
    # 했지만 무엇이 틀렸는지 말하지 않는 글. 예비 실행(20261006-124838, gpt-6-astra)은
    # 은행 오류에 "계좌번호가 맞지 않습니다" 를 띄운 채 통과했다 - 원본의 같은
    # 문제를 스스로 진단해 놓고 똑같이 틀렸다.
    by_check = row.get("warning_by_check") or {}
    for check in gates.get("no_warning_checks") or []:
        hit = by_check.get(check)
        if hit and hit.get("count"):
            out.append("검사 %s 경고 %d건 (%s)" % (
                check, hit["count"], " ".join(str(hit.get("first") or "").split())[:80]))
    want = gates.get("model")
    if want and row.get("model") != want:
        out.append("모델이 %s 아님 (%s)" % (want, row.get("model")))
    # 실행 조건. 같은 조건의 반복이어야 고른 것이 "전형적인 시안" 이다 - 조건이 다른
    # 실행(예: 말없이 styled · 예산 3/3 으로 돈 20261006-124055)이 섞이면 안 된다.
    stage = gates.get("stage")
    if stage and row.get("stage") != stage:
        out.append("검사 단계가 %s 아님 (%s)" % (stage, row.get("stage") or "기록 없음"))
    off = budget_mismatch(row, gates.get("budget"))
    if off:
        out.append("예산이 규칙과 다름: " + " · ".join(off))
    why = original_reason(row, original) if gates.get("original") else None
    if why:
        out.append(why)
    if gates.get("no_internal_error") and row.get("internal_error"):
        out.append("도구 내부 오류로 끝남 (internal_error, 종료 2) - 통과한 빌드가 있어도 "
                   "뺀다")
    if gates.get("reverted") == "exclude" and row.get("reverted"):
        out.append("되돌린 실행 (다듬기 %s회차가 떨어져 시도 %s 이 최종)"
                   % (row["reverted"], row.get("reverted_to")))
    return out


def original_basis(task, gates):
    """그 과제의 지금 원본 `{"task", "path", "sha256"}` - gates.original 이 꺼져 있으면
    None. 원본 파일은 과제 파일(tasks/<과제>.json 의 original)이 정한다 - 공과금이면
    inputs/original_bill.html 이다. 지문은 재구성 루프가 남긴 것과 같은 함수로 잰다
    (tasks.fingerprint - 줄끝을 LF 로 맞춘 sha256)."""
    if not gates.get("original"):
        return None
    try:
        return {"task": task, "path": load_task(task)["original"],
                "sha256": original_sha256(task)}
    except (OSError, ValueError) as e:
        raise RuleError("과제 %s 의 원본 파일을 읽지 못했다 (gates.original): %s" % (task, e))


def original_reason(row, basis):
    """이 실행이 지금 원본으로 만든 것이 아니면 그 이유. 같으면 None.

    값이 없는 실행은 원본 지문을 남기기 전(11-11 전)의 실행이다 - 어느 원본으로
    만들었는지 모르므로 같은 이유로 뺀다."""
    if basis is None:
        return None
    mine = row.get("original_sha256")
    if mine == basis["sha256"]:
        return None
    return "다른 원본으로 만든 실행 (original_sha256 %s, 지금 %s %s)" % (
        mine[:12] if mine else "기록 없음 - 원본 지문을 남기기 전의 실행",
        basis["path"], basis["sha256"][:12])


def budget_mismatch(row, want):
    """규칙의 예산과 다른 칸마다 한 마디. 규칙에 적힌 칸만 본다."""
    have = row.get("budget") or {}
    out = []
    for key, label in BUDGET_KEYS:
        if not want or key not in want:
            continue
        got = have.get(key)
        if got != want[key]:
            out.append("%s %s (규칙 %d)" % (label, "기록 없음" if got is None else got,
                                          want[key]))
    return out


def _short(commit):
    return (commit or "")[:7]


def commit_basis(rows, pinned):
    """후보들이 기준으로 삼을 커밋. `{"commit", "source", "counts"}` 또는 None.

    규칙에 적었으면(pinned) 그것이다. 비워 두면 후보들 중 가장 많은 커밋이고,
    같은 수면 가장 나중에 돈 실행(이름이 시각이다)의 커밋이다. 커밋이 다른 실행은
    같은 코드로 돈 것이 아니므로 "같은 조건의 반복" 에서 뺀다."""
    counts = collections.Counter(r["commit"] for r in rows if r.get("commit"))
    if pinned:
        return {"commit": pinned, "source": "rule", "counts": dict(counts)}
    if not counts:
        return None
    top = max(counts.values())
    tied = {c for c, n in counts.items() if n == top}
    newest = max((r for r in rows if r.get("commit") in tied), key=lambda r: r["name"])
    return {"commit": newest["commit"], "source": "majority", "counts": dict(counts)}


def commit_reason(row, basis):
    """이 후보가 커밋 기준에서 벗어나는 이유. 맞으면 None."""
    if basis is None:
        return None
    mine = row.get("commit")
    if not mine:
        return "커밋 기록 없음 (git.commit)"
    if basis["source"] == "rule":
        if not mine.startswith(basis["commit"]):
            return "커밋이 규칙의 %s 아님 (%s)" % (_short(basis["commit"]), _short(mine))
        return None
    if mine != basis["commit"]:
        return ("커밋이 기준(%s, 후보 %d개 중 가장 많은 %d개)과 다름 (%s)"
                % (_short(basis["commit"]), sum(basis["counts"].values()),
                   basis["counts"][basis["commit"]], _short(mine)))
    return None


# --------------------------------------------------------------------------- #
# 대표성
# --------------------------------------------------------------------------- #
def representative(rows, metrics):
    """후보마다 {거리, 값별 내역}, 그리고 값마다 {중앙값, 최솟값, 최댓값}.

    거리는 값마다 |값 - 중앙값| / (최댓값 - 최솟값) 에 가중치를 곱해 더한다.
    중앙값 · 범위는 **후보들 사이에서** 잰다 - 떨어진 실행의 화면 수가
    "보통" 을 끌어당기면 안 된다. 값이 없는 후보는 그 값에서 가장 먼 것(1)으로
    친다."""
    stats = {}
    for m in metrics:
        vals = [r[m] for r in rows if isinstance(r.get(m), (int, float))]
        if vals:
            stats[m] = {"median": statistics.median(vals), "min": min(vals),
                        "max": max(vals)}
        else:
            stats[m] = {"median": None, "min": None, "max": None}
    per_row = {}
    for r in rows:
        parts, total = {}, 0.0
        for m, w in metrics.items():
            st, v = stats[m], r.get(m)
            if not isinstance(v, (int, float)) or st["median"] is None:
                d = 1.0
            else:
                span = st["max"] - st["min"]
                d = abs(v - st["median"]) / span if span else 0.0
            parts[m] = round(d, ROUND)
            total += w * d
        per_row[r["name"]] = {"distance": round(total, ROUND), "parts": parts}
    return per_row, stats


# --------------------------------------------------------------------------- #
# 줄 세우기
# --------------------------------------------------------------------------- #
def _key_part(row, o, rep):
    if o["by"] == REPRESENTATIVE:
        return (0, rep[row["name"]]["distance"])
    v = row.get(o["by"])
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return (1, 0)                       # 값이 없으면 맨 뒤
    return (0, v if o.get("order", "asc") == "asc" else -v)


def rank(rows, rule, task=None):
    """규칙을 적용한 결과.

    {"candidates": [후보 행, 순위 순], "excluded": [제외 행],
     "commit_basis", "original_basis",
     "representative": {"metrics", "stats", "by_run"} 또는 None}
    행마다 "rank" (후보만) 와 "excluded_because" (제외만) 를 붙인다.

    `task` 는 고르는 과제다 - gates.original 이 그 과제의 지금 원본과 견준다. 주지
    않으면 첫 실행의 과제."""
    gates = rule["gates"]
    task = task or next((r.get("task") for r in rows if r.get("task")), None)
    original = original_basis(task, gates)
    candidates, excluded = [], []
    for row in rows:
        reasons = gate_reasons(row, gates, original)
        row = dict(row, excluded_because=reasons, rank=None)
        (excluded if reasons else candidates).append(row)

    # 커밋은 다른 문지기를 다 지난 후보들 사이에서 맞춘다 - mock · dirty 같은 실행이
    # "가장 많은 커밋" 을 끌어가지 않게. 칸이 없는 옛 규칙은 보지 않는다.
    basis = commit_basis(candidates, gates.get("commit")) if "commit" in gates else None
    kept = []
    for row in candidates:
        why = commit_reason(row, basis)
        if why:
            row["excluded_because"] = [why]
            excluded.append(row)
        else:
            kept.append(row)
    candidates = kept

    rep_rule = next((o for o in rule["ordering"] if o["by"] == REPRESENTATIVE), None)
    rep, stats = {}, {}
    if rep_rule:
        rep, stats = representative(candidates, rep_rule["metrics"])
        for row in candidates:
            row["representative"] = rep[row["name"]]

    # reverted: "last" 면 되돌린 실행을 되돌리지 않은 실행 뒤로 미룬다 (그 안에서는
    # 규칙의 순서 그대로).
    last = gates.get("reverted") == "last"
    candidates.sort(key=lambda r: (1 if last and r.get("reverted") else 0,)
                    + tuple(_key_part(r, o, rep) for o in rule["ordering"]) + (r["name"],))
    for i, row in enumerate(candidates, 1):
        row["rank"] = i
    excluded.sort(key=lambda r: r["name"])
    return {"candidates": candidates, "excluded": excluded,
            "commit_basis": basis, "original_basis": original,
            "representative": None if not rep_rule else
            {"metrics": rep_rule["metrics"], "stats": stats}}
