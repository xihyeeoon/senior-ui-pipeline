r"""고르기 결과를 JSON 과 md 로 쓴다. 둘은 같은 내용이다.

JSON 이 원본이고 md 는 사람이 읽는 모양이다. JSON 에는 그때 쓴 규칙 전문과
그 출처(sha256 · 커밋)가 들어 있어서, 규칙을 바꾼 뒤에도 그 결과를 그 규칙과
함께 다시 읽을 수 있다 (--compare · --rule <결과 JSON>).

"연구자 결정" 칸은 비워 둔다. 도구는 순위만 낸다 - 무엇을 쓸지는 연구자가
정하고, 1등이 아닌 것을 쓰면 그 이유를 적는다.
"""
import datetime
import io
import json
import os

from senior_ui.config import ROOT

DECISION = {"chosen": "", "same_as_rank1": None, "reason": ""}


def rel_path(path):
    """저장소 안이면 루트 기준 '/' 경로, 밖이면 그대로."""
    if not path:
        return path
    rel = os.path.relpath(os.path.abspath(path), ROOT)
    return path if rel.startswith("..") else rel.replace("\\", "/")


def _row_out(row):
    out = dict(row)
    for k in ("dir", "html", "audit", "brief"):
        out[k] = rel_path(out.get(k))
    return out


def build(task, rule, source, ranked, rows_source, created=None):
    """결과 JSON 의 몸통."""
    cands = ranked["candidates"]
    return {
        "task": task,
        "created": (created or datetime.datetime.now()).isoformat(timespec="seconds"),
        "runs_source": rows_source,
        "rule": dict(source, content=rule),
        "rank1": cands[0]["name"] if cands else None,
        "counts": {"runs": len(cands) + len(ranked["excluded"]),
                   "candidates": len(cands), "excluded": len(ranked["excluded"])},
        "representative": ranked["representative"],
        "ranking": [_row_out(r) for r in cands + ranked["excluded"]],
        "researcher_decision": dict(DECISION),
    }


# --------------------------------------------------------------------------- #
# 지난 결과와 나란히
# --------------------------------------------------------------------------- #
def _ordering_line(ordering):
    out = []
    for o in ordering:
        if o["by"] == "representative":
            out.append("representative(%s)" % ", ".join(
                "%s x%g" % (m, w) for m, w in o["metrics"].items()))
        else:
            out.append("%s %s" % (o["by"], o.get("order", "asc")))
    return " > ".join(out)


def compare(prev, cur):
    """지난 고르기 결과와 지금 결과. 규칙에서 바뀐 것과 실행마다 순위가 어떻게
    달라졌는지."""
    pr, cr = prev["rule"]["content"], cur["rule"]["content"]
    gates = []
    for k in sorted(set(pr.get("gates", {})) | set(cr.get("gates", {}))):
        a, b = pr.get("gates", {}).get(k, "(없음)"), cr.get("gates", {}).get(k, "(없음)")
        if a != b:
            gates.append({"gate": k, "before": a, "after": b})
    po, co = _ordering_line(pr["ordering"]), _ordering_line(cr["ordering"])
    before = {r["name"]: r for r in prev["ranking"]}
    after = {r["name"]: r for r in cur["ranking"]}
    runs = []
    for name in sorted(set(before) | set(after)):
        a, b = before.get(name), after.get(name)
        runs.append({"name": name,
                     "before": None if a is None else (a.get("rank"), a.get("excluded_because")),
                     "after": None if b is None else (b.get("rank"), b.get("excluded_because"))})
    return {"previous": {"file": prev.get("_path"), "created": prev.get("created"),
                         "rank1": prev.get("rank1"),
                         "rule_sha256": prev["rule"].get("sha256"),
                         "rule_repo_commit": prev["rule"].get("repo_commit")},
            "rule_changed": prev["rule"].get("sha256") != cur["rule"].get("sha256"),
            "gates_changed": gates,
            "ordering": {"before": po, "after": co, "changed": po != co},
            "rank1": {"before": prev.get("rank1"), "after": cur.get("rank1")},
            "runs": runs}


# --------------------------------------------------------------------------- #
# md
# --------------------------------------------------------------------------- #
def _f(v):
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "✓" if v else "✗"
    if isinstance(v, float):
        return ("%.4f" % v).rstrip("0").rstrip(".")
    return str(v)


def _short(commit):
    return commit[:7] if commit else "-"


def _cell(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


def _link(path, md_dir):
    if not path:
        return None
    full = path if os.path.isabs(path) else os.path.join(ROOT, path)
    return os.path.relpath(full, md_dir).replace("\\", "/")


def _choices(groups):
    if not groups:
        return "-"
    out = []
    for g, v in groups.items():
        mark = "" if v.get("kept") == v.get("original") == v.get("selectable") else " ⚠"
        out.append("%s %s/%s/%s%s" % (g, _f(v.get("kept")), _f(v.get("selectable")),
                                      _f(v.get("original")), mark))
    return ", ".join(out)


def _errors(paths):
    if not paths:
        return "-"
    return ", ".join("%s %s" % (k, "✓" if v.get("ok") else "✗") for k, v in paths.items())


def _rank_or_out(t):
    if t is None:
        return "(없음)"
    rank, reasons = t
    return str(rank) if rank else "제외: " + "; ".join(reasons or [])


def render(result, md_path):
    md_dir = os.path.dirname(os.path.abspath(md_path))
    rule, rows = result["rule"], result["ranking"]
    by_name = {r["name"]: r for r in rows}
    top = by_name.get(result["rank1"])
    src = result["runs_source"]
    out = ["# C 후보 고르기 - %s (%s)" % (result["task"], result["created"]), ""]

    out.append("도구는 순위표만 낸다. 무엇을 쓸지는 연구자가 정한다 - 같은 이름의 "
               "`.json` 의 `researcher_decision` 을 채운다 (아래 '연구자 결정').")
    out.append("")
    out.append("- 규칙: `%s` - sha256 `%s`, 규칙 파일의 마지막 커밋 `%s`, 저장소 HEAD `%s`%s"
               % (rule.get("path"), (rule.get("sha256") or "")[:12],
                  _short(rule.get("rule_file_commit")), _short(rule.get("repo_commit")),
                  " - **커밋하지 않은 수정이 있다**" if rule.get("rule_file_dirty") else ""))
    if rule.get("replayed_from"):
        out.append("- 이 규칙은 지난 결과 `%s` 에서 다시 쓴 것이다" % rule["replayed_from"])
    out.append("- 본 실행: %d개 (후보 %d, 제외 %d) - %s"
               % (result["counts"]["runs"], result["counts"]["candidates"],
                  result["counts"]["excluded"],
                  "기본 (%s)" % src["patterns"][0] if src.get("default")
                  else "--runs %s" % " ".join(src.get("patterns") or [])))
    if src.get("skipped_other_task"):
        out.append("- 다른 과제의 실행 %d개는 넣지 않았다" % len(src["skipped_other_task"]))
    if top:
        link = _link(top.get("brief"), md_dir)
        out.append("- **1등: `%s`** - 설명서: %s" % (
            top["name"], "[designer_brief.md](%s)" % link if link else "없음"))
    else:
        out.append("- **후보가 없다** - 모든 실행이 문지기에서 빠졌다")
    out.append("")

    out += ["## 순위표", "",
            "| 순위 | 실행 | 통과 | 시도 (형식 실패/검사 실패) | fatal / warning | 화면 "
            "| data-action | 진단 / 변경 (진단 없는 변경) | 대표성 거리 | 도구가 고침 "
            "| 잘림 (마지막) | 중간 잘림 | dirty | 모델 · effort | 커밋 | 제외 이유 |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if r.get("error"):
            out.append("| - | `%s` |%s %s |" % (r["name"], " |" * 13, _cell(r["error"])))
            continue
        rep = (r.get("representative") or {}).get("distance")
        out.append("| %s | `%s` | %s | %s (%s/%s) | %s / %s | %s | %s | %s / %s (%s) | %s "
                   "| %s | %s | %s | %s | %s · %s | `%s` | %s |" % (
                       r["rank"] or "-", r["name"], _f(r["passed"]), _f(r["attempts"]),
                       _f(r["format_failures"]), _f(r["audit_failures"]), _f(r["fatal"]),
                       _f(r["warning"]), _f(r["screens"]), _f(r["data_actions"]),
                       _f(r["diagnoses"]), _f(r["changes"]), _f(r["unmatched_changes"]),
                       _f(rep), _cell(", ".join(r["redeclared"])) if r["redeclared"]
                       else ("-" if r["redeclared"] is None else "없음"),
                       _f(r["truncated"]), _f(r.get("truncated_middle")), _f(r["dirty"]),
                       _f(r["model"]),
                       _f(r["reasoning_effort"]), _short(r["commit"]),
                       _cell("; ".join(r["excluded_because"])) or "-"))
    out.append("")

    real = [r for r in rows if not r.get("error")]
    out += ["## 구조 - 선택지 · 오류 경로", "",
            "선택지는 그룹마다 `kept/selectable/원본` (셋이 다르면 ⚠). 오류 경로는 검사 J "
            "의 결과 (나타남과 되돌아옴이 둘 다 참이면 ✓).", "",
            "| 실행 | 닿은 화면 | 선택지 | 오류 경로 (J) |", "|---|---|---|---|"]
    for r in real:
        out.append("| `%s` | %s | %s | %s |" % (r["name"], _f(r["screens_reached"]),
                                               _cell(_choices(r["choice_groups"])),
                                               _cell(_errors(r["error_paths"]))))
    out.append("")

    out += ["## 비용", "", "| 실행 | 입력 토큰 | 출력 토큰 (생각 포함) | 생각 토큰 | 예상 금액 USD |",
            "|---|---|---|---|---|"]
    for r in real:
        out.append("| `%s` | %s | %s | %s | %s |" % (
            r["name"], _f(r["input_tokens"]), _f(r["output_tokens"]),
            _f(r["reasoning_tokens"]), _f(r["cost_usd"])))
    out.append("")

    rep = result.get("representative")
    if rep:
        out += ["## 대표성 계산", "",
                "후보들 사이의 중앙값과 범위. 거리 = 합(가중치 x |값 - 중앙값| / (최댓값 - "
                "최솟값)). 범위가 0 이면 그 값의 몫은 0, 값이 없으면 1.", "",
                "| 값 | 가중치 | 중앙값 | 최솟값 | 최댓값 |", "|---|---|---|---|---|"]
        for m, w in rep["metrics"].items():
            st = rep["stats"].get(m) or {}
            out.append("| %s | %s | %s | %s | %s |" % (m, _f(w), _f(st.get("median")),
                                                     _f(st.get("min")), _f(st.get("max"))))
        out.append("")

    out += ["## 쓴 규칙", "", "```json",
            json.dumps(rule["content"], ensure_ascii=False, indent=2), "```", ""]

    out += ["## 연구자 결정", "",
            "같은 이름의 `.json` 맨 끝 `researcher_decision` 을 채운다. 이 md 는 고치지 "
            "않는다.", "", "```json",
            json.dumps({"researcher_decision": {
                "chosen": "<실행 이름>", "same_as_rank1": "true/false",
                "reason": "1등을 쓰지 않으면 그 이유"}}, ensure_ascii=False, indent=2),
            "```", "",
            "채운 파일은 results/ 로 옮길 때 함께 간다 (15번).", ""]

    cmp_ = result.get("compare")
    if cmp_:
        p = cmp_["previous"]
        out += ["## 지난 고르기와 비교", "",
                "- 지난 결과: `%s` (%s), 규칙 sha256 `%s`, HEAD `%s`"
                % (p.get("file"), p.get("created"), (p.get("rule_sha256") or "")[:12],
                   _short(p.get("rule_repo_commit"))),
                "- 규칙이 바뀌었나: %s" % ("예" if cmp_["rule_changed"] else "아니오"),
                "- 1등: `%s` -> `%s`" % (cmp_["rank1"]["before"], cmp_["rank1"]["after"])]
        for g in cmp_["gates_changed"]:
            out.append("- 문지기 %s: %s -> %s" % (g["gate"], _f(g["before"]), _f(g["after"])))
        if cmp_["ordering"]["changed"]:
            out.append("- 순서: `%s` -> `%s`" % (cmp_["ordering"]["before"],
                                                cmp_["ordering"]["after"]))
        out += ["", "| 실행 | 지난 순위 | 지금 순위 |", "|---|---|---|"]
        for r in cmp_["runs"]:
            out.append("| `%s` | %s | %s |" % (r["name"], _cell(_rank_or_out(r["before"])),
                                               _cell(_rank_or_out(r["after"]))))
        out.append("")
    return "\n".join(out)


def write(result, out_dir, task, now=None):
    """(md 경로, json 경로). 같은 초에 두 번 돌면 뒤에 -2, -3 을 붙인다."""
    os.makedirs(out_dir, exist_ok=True)
    stamp = (now or datetime.datetime.now()).strftime("%Y%m%d-%H%M%S")
    base, n = os.path.join(out_dir, "%s_%s" % (task, stamp)), 1
    while os.path.exists(base + (".json" if n == 1 else "-%d.json" % n)):
        n += 1
    base = base if n == 1 else "%s-%d" % (base, n)
    md, js = base + ".md", base + ".json"
    with io.open(js, "w", encoding="utf-8", newline="\n") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    with io.open(md, "w", encoding="utf-8", newline="\n") as f:
        f.write(render(result, md))
    return md, js
