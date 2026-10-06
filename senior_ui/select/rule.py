r"""규칙 파일 읽기 · 문지기(gates) · 줄 세우기(ordering).

규칙은 flows/selection_rule.json 에 있다. 여기에는 규칙을 **적용하는 법**
만 있다 - 어느 값을 볼지, 어떤 순서로 볼지, 가중치가 얼마인지는 전부 파일에서
온다. 규칙을 바꾸려고 이 파일을 고칠 일이 생기면 그것은 규칙 파일의 형식을
넓히는 일이다.

모르는 칸은 멈춘다. 오타 난 문지기 이름을 조용히 넘기면 그 문지기는 없는 것과
같고, 그 규칙으로 고른 결과는 적힌 규칙과 다르다.
"""
import hashlib
import io
import json
import os
import statistics
import subprocess

from senior_ui.config import FLOWS_DIR, ROOT

DEFAULT_RULE = os.path.join(FLOWS_DIR, "selection_rule.json")

GATES = ("passed", "no_redeclared", "no_truncated", "clean_tree", "not_mock", "model")

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
def gate_reasons(row, gates):
    """이 실행이 어긴 문지기마다 이유 한 줄. 비어 있으면 후보다."""
    if row.get("error"):
        return [row["error"]]
    out = []
    if gates.get("passed") and not row.get("passed"):
        why = row.get("stopped_reason")
        out.append("통과하지 못함" + (" (%s)" % why if why else ""))
    if gates.get("no_redeclared") and row.get("redeclared"):
        out.append("도구가 고침: redeclared %s" % ", ".join(row["redeclared"]))
    if gates.get("no_truncated") and row.get("truncated"):
        out.append("답이 길이 제한에서 잘린 시도가 있음")
    if gates.get("clean_tree") and row.get("dirty") is not False:
        out.append("작업 트리가 깨끗하지 않음" if row.get("dirty")
                   else "작업 트리 기록 없음 (git.dirty)")
    if gates.get("not_mock") and row.get("mock"):
        out.append("mock 실행 (%s)" % row["mock"])
    want = gates.get("model")
    if want and row.get("model") != want:
        out.append("모델이 %s 아님 (%s)" % (want, row.get("model")))
    return out


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


def rank(rows, rule):
    """규칙을 적용한 결과.

    {"candidates": [후보 행, 순위 순], "excluded": [제외 행],
     "representative": {"metrics", "stats", "by_run"} 또는 None}
    행마다 "rank" (후보만) 와 "excluded_because" (제외만) 를 붙인다."""
    gates = rule["gates"]
    candidates, excluded = [], []
    for row in rows:
        reasons = gate_reasons(row, gates)
        row = dict(row, excluded_because=reasons, rank=None)
        (excluded if reasons else candidates).append(row)

    rep_rule = next((o for o in rule["ordering"] if o["by"] == REPRESENTATIVE), None)
    rep, stats = {}, {}
    if rep_rule:
        rep, stats = representative(candidates, rep_rule["metrics"])
        for row in candidates:
            row["representative"] = rep[row["name"]]

    candidates.sort(key=lambda r: tuple(_key_part(r, o, rep) for o in rule["ordering"])
                    + (r["name"],))
    for i, row in enumerate(candidates, 1):
        row["rank"] = i
    excluded.sort(key=lambda r: r["name"])
    return {"candidates": candidates, "excluded": excluded,
            "representative": None if not rep_rule else
            {"metrics": rep_rule["metrics"], "stats": stats}}
