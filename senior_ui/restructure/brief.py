r"""통과한 실행마다 디자이너에게 넘길 변경 설명서(designer_brief.md)를 쓴다.

결과물은 디자이너가 보고 실제 앱에 입히는 **구조 시안** 이다. 시각 디테일은
평가 대상이 아니므로 설명서도 다루지 않는다. 설명서가 답하는 것은 넷이다.

    1. 원본의 어느 화면이 재설계의 어느 화면이 되었나      (계획의 from)
    2. 무엇을 왜 바꿨나, 그것이 어느 진단에 대응하나        (계획의 changes)
    3. 각 화면은 어떻게 생겼나                              (검사기가 찍은 스크린샷)
    4. 잘못 입력하면 어떻게 되나                            (계획의 errors · 검사 J 가
                                                            걸어 본 결과)
    5. 사람이 따로 봐야 할 것                               (warning · 도구가 고친 것 ·
                                                            일부러 뺀 선택지)
    6. 스크린샷을 보고 무엇을 다듬었나                      (다듬기 회차마다 비평 ·
                                                            바꾼 것 · 전후 스크린샷)

맨 위 한 줄은 최종 빌드가 어디서 왔는지다 - 생성인지 다듬기 몇 회차인지, 다듬기가
실패해 되돌렸는지 (summary 의 refine.final_from · reverted).

전부 실행 폴더에 이미 있는 파일에서 옮긴다. 새로 판단하는 것은 없다.

render_brief 는 순수 함수다 (파일을 읽지 않는다). 링크는 설명서가 놓이는
폴더 기준 상대 경로로 쓴다 - 실행 폴더의 원본과 outputs/ 로 올라간 사본은 같은
스크린샷을 가리키지만 링크 글자가 다르다.
"""
import io
import json
import os

from senior_ui.audit.flow import original_error_paths
from senior_ui.preserved import GLOBAL_NAME


def _cell(s):
    """표 칸 안의 글. 줄바꿈과 | 는 표를 깨뜨린다."""
    return " ".join(str(s if s is not None else "").split()).replace("|", "\\|")


def _link(path, base):
    return os.path.relpath(path, base).replace(os.sep, "/")


# 진단의 근거가 무엇이었나 (plan.EVIDENCE_KINDS). 빠지거나 틀린 값은 "미표시".
EVIDENCE_LABEL = {"screen": "화면", "code": "코드", "both": "화면+코드"}


def evidence_label(d):
    return EVIDENCE_LABEL.get(d.get("evidence_kind"), "미표시")


def final_line(refine, attempt):
    """설명서 맨 위 한 줄. 예: "최종: 다듬기 1회차 (시도 3)" · "최종: 생성 (다듬기
    2회차가 실패해 되돌림) · 시도 1". 다듬기 기록이 없는 실행(다듬기 전의 실행)은
    "최종: 생성 (시도 N)"."""
    label = (refine or {}).get("final_label") or "생성"
    if "(" in label:
        return "최종: %s · 시도 %d" % (label, attempt)
    return "최종: %s (시도 %d)" % (label, attempt)


def _see_items(folder):
    """see/index.json 의 방문별 그림 파일들. `{방문: [경로…]}` (순서대로)."""
    out = {}
    index = os.path.join(folder or "", "index.json")
    if not folder or not os.path.exists(index):
        return out
    for it in json.load(io.open(index, encoding="utf-8")):
        out.setdefault(it["visit"], []).append(os.path.join(folder, it["file"]))
    return out


def _same_pictures(a, b):
    """두 그림 목록이 바이트로 같은가. 같은 브라우저 · 같은 크기로 찍으므로 화면이
    그대로면 PNG 도 같다."""
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        with open(x, "rb") as f, open(y, "rb") as g:
            if f.read() != g.read():
                return False
    return True


def shot_pairs(before, after):
    """`[(방문, 전 그림, 후 그림, 바뀜?)]`. 첫 장끼리 잇고, 바뀜은 모든 장으로 본다."""
    b, a = _see_items(before), _see_items(after)
    rows = []
    for visit in list(a) + [v for v in b if v not in a]:
        bb, aa = b.get(visit) or [], a.get(visit) or []
        changed = None if not (bb and aa) else not _same_pictures(bb, aa)
        rows.append((visit, bb[0] if bb else None, aa[0] if aa else None, changed))
    return rows


def refine_section(refine, brief_dir):
    """보고 다듬기 절. 다듬기 기록이 없으면 빈 목록."""
    rounds = (refine or {}).get("rounds") or []
    if not rounds:
        return []
    out = ["## 보고 다듬기", "",
           "검사를 통과한 빌드의 스크린샷을 모델에게 보여 주고, 60대 이상 사용자가 처음 "
           "볼 때 어디서 멈추고 무엇을 못 읽고 무엇을 잘못 누를지 화면을 보고 판단하게 "
           "했다. 다듬은 빌드는 검사를 다시 통과해야 최종이 된다.", ""]
    if refine.get("reverted"):
        out += ["**되돌림**: %s — 최종은 직전에 통과한 시도 %s 다." % (
            refine["reverted"]["reason"], refine["reverted"]["to_attempt"]), ""]
    for x in rounds:
        crit = None
        if x.get("critique") and os.path.exists(x["critique"]):
            crit = json.load(io.open(x["critique"], encoding="utf-8"))
        if x.get("stopped") == "done":
            result = "고칠 것이 없다고 답했다 — 다듬기를 멈췄다"
        elif x.get("became_final"):
            result = "통과 — 새 최종 (시도 %s)" % (x.get("fix_attempt") or x["attempt"])
            if x.get("fix_attempt"):
                result += " · 처음 다듬은 빌드는 떨어져 한 번 고쳤다"
        elif x.get("stopped") == "reverted":
            result = "다듬은 빌드와 고친 빌드가 모두 떨어졌다 — 되돌림"
        elif x.get("stopped") == "call_failed":
            result = "모델 호출이 실패했다 — 최종은 그대로"
        else:
            result = "통과하지 못함"
        out += ["### %d회차 — 시도 %s 의 빌드를 다듬음 (시도 %s)" % (
            x["round"], x.get("from_attempt"), x["attempt"]), "",
            "결과: %s. 비평 %s건 · keep %s건 · done=%s · 그림 %s장." % (
                result, x.get("issues") if x.get("issues") is not None else "?",
                x.get("keep") if x.get("keep") is not None else "?",
                {True: "true", False: "false"}.get(x.get("done"), "?"), x.get("images")),
            ""]
        issues = [i for i in (crit or {}).get("issues") or [] if isinstance(i, dict)]
        if issues:
            out += ["| 화면 | 어디서 왜 막히나 | 그림에서 본 것 | 고친 것 |",
                    "|---|---|---|---|"]
            out += ["| %s | %s | %s | %s |" % tuple(
                _cell(i.get(k)) for k in ("screen", "problem", "seen", "fix"))
                for i in issues]
            out.append("")
        keep = (crit or {}).get("keep") if isinstance((crit or {}).get("keep"), list) else []
        if keep:
            out += ["그대로 둔 것:", ""] + ["- %s" % _cell(k) for k in keep] + [""]
        pairs = shot_pairs(x.get("before_shots"), x.get("after_shots"))             if x.get("after_shots") else []
        if pairs:
            out += ["전후 스크린샷 (첫 장끼리, 바뀜은 모든 장을 견준 것):", "",
                    "| 화면 | 전 | 후 | |", "|---|---|---|---|"]
            for visit, b, a, changed in pairs:
                out.append("| `%s` | %s | %s | %s |" % (
                    visit,
                    "[전](%s)" % _link(b, brief_dir) if b else "-",
                    "[후](%s)" % _link(a, brief_dir) if a else "-",
                    {True: "바뀜", False: "그대로", None: "-"}[changed]))
            out.append("")
    return out


def mapping_rows(plan, original_screens):
    """`(원본 화면, 재설계 화면)` 줄들. 원본 화면 순서, 그다음 새 화면."""
    rows = []
    for orig in original_screens:
        targets = [sc["name"] for sc in plan["screens"] if orig in (sc.get("from") or [])]
        rows.append((orig, ", ".join(targets) if targets else "(없어짐)"))
    for sc in plan["screens"]:
        if not sc.get("from"):
            rows.append(("(새 화면)", sc["name"]))
    return rows


def choice_gaps(metrics):
    """검사 I 의 kept 와 selectable 이 다른 것. `[(action, kept, selectable)]`."""
    kept = metrics.get("choice_values_kept") or {}
    sel = metrics.get("choice_values_selectable") or {}
    return [(a, kept[a], sel.get(a)) for a in sorted(kept)
            if sel.get(a) is not None and sel.get(a) != kept[a]]


def _j_result(res, warned):
    """검사 J 가 걸어 본 결과 한 칸."""
    if res is None:
        return "걷지 않음"
    if not res.get("appeared"):
        return "실패 — 오류 상태가 나타나지 않음 (켜진 화면 %s)" % (res.get("landed_on") or "?")
    if not res.get("recovered"):
        return "실패 — 되돌아가지 못함 (켜진 화면 %s)" % (res.get("recovered_to") or "?")
    return "통과 · 경고 (알림 글에 과제의 단어가 없음)" if warned else "통과"


def error_rows(errors, plan, metrics, warnings):
    """오류 경로 표의 줄. 과제가 정한 오류마다 하나 (원본 흐름의 error_paths)."""
    planned = {e.get("id"): e for e in (plan or {}).get("errors") or []
               if isinstance(e, dict)}
    walked = metrics.get("error_paths") or {}
    warned = {w.get("error_path") for w in warnings or [] if w.get("check") == "J"}
    ids = [e["id"] for e in errors or [] if "id" in e] or list(planned)
    defs = {e["id"]: e for e in errors or [] if "id" in e}
    rows = []
    for eid in ids:
        d, p, res = defs.get(eid) or {}, planned.get(eid) or {}, walked.get(eid)
        where = ("`%s` — %s" % (p["screen"], p.get("how") or "")) if p.get("screen")             else "계획에 없음"
        rows.append({
            "id": eid, "about": d.get("about") or "",
            "input": ", ".join("`{%s}`" % k for k in d.get("uses") or []) or "-",
            "where": where,
            "shown": " / ".join((res or {}).get("notice") or []) if (res or {}).get("appeared")
            else "-",
            "back_to": (res or {}).get("recovered_to") or p.get("back_to") or "-",
            "result": _j_result(res, eid in warned)})
    return rows


def render_brief(run_name, attempt, plan, diagnosis, report, original_screens,
                 shots_dir, brief_dir, preserved=None, redeclared=None,
                 model_html=None, git=None, reflections=None, errors=None,
                 refine=None):
    report = report or {}
    metrics = report.get("metrics") or {}
    diag = {d["id"]: d for d in diagnosis or []}
    out = ["# 디자이너용 변경 설명서", "", final_line(refine, attempt), ""]

    head = "실행 `%s` · 시도 %d 에서 검사를 통과한 빌드" % (run_name, attempt)
    if git and git.get("commit"):
        head += " · 커밋 `%s`" % git["commit"][:12]
        if git.get("dirty"):
            head += " (작업 트리가 깨끗하지 않았다 — 커밋에 없는 변경 위에서 돌았다)"
    out += [head + ".", "",
            "이 파일은 구조 시안의 설명이다. 색·글꼴·간격 같은 시각 디테일은 평가하지 "
            "않았다. 화면 구성과 흐름, 그리고 바꾼 이유를 옮겨 적는다.", ""]

    out += ["## 화면 대응", "", "| 원본 | 재설계 |", "|---|---|"]
    out += ["| %s | %s |" % (_cell(a), _cell(b)) for a, b in mapping_rows(plan, original_screens)]
    out += ["", "재설계 화면의 순서와 하는 일:", ""]
    out += ["%d. `%s` — %s" % (i + 1, sc["name"], sc.get("purpose", ""))
            for i, sc in enumerate(plan["screens"])]
    out.append("")

    out += ["## 변경 목록", "", "| # | 무엇을 | 왜 | 대응하는 진단 | 원본 → 재설계 |",
            "|---|---|---|---|---|"]
    for c in plan.get("changes") or []:
        answered = "; ".join("%s %s" % (d, diag[d]["problem"]) if d in diag else d
                             for d in c.get("addresses") or []) or "대응하는 진단 없음"
        where = "%s → %s" % (", ".join(c.get("from_screens") or []) or "-",
                             ", ".join(c.get("to_screens") or []) or "-")
        out.append("| %s | %s | %s | %s | %s |" % (
            _cell(c.get("id")), _cell(c.get("what")), _cell(c.get("why")),
            _cell(answered), _cell(where)))
    out.append("")
    if diagnosis:
        out += ["진단 (원본에서 고령 사용자가 막힐 곳과 그 근거 — 근거가 화면 그림에서 "
                "왔는지 코드에서 왔는지를 [ ] 에 적는다):", ""]
        out += ["- **%s** `%s` %s — %s (근거[%s]: %s)" % (
            d["id"], d.get("screen"), d.get("element"), d.get("problem"),
            evidence_label(d), d.get("evidence"))
            for d in diagnosis]
        out.append("")
    if reflections:
        out += ["재시도에서의 반성 (계획이 바뀐 경우 그 이유):", ""]
        out += ["- 시도 %s: %s (계획 변경 %s건)" % (x["attempt"], x["cause"],
                                               x.get("plan_changes", 0))
                for x in reflections]
        out.append("")

    rows = error_rows(errors, plan, metrics, report.get("warning"))
    if rows:
        out += ["## 오류 경로", "",
                "원본에는 잘못된 입력에서 뜨는 오류가 있다. 재설계가 그 오류를 어디서 "
                "어떻게 알리고 어디로 돌아가게 하는지, 그리고 검사기가 틀린 값을 넣어 "
                "걸어 보았을 때 실제로 보인 글이다 (검사 J).", "",
                "| 오류 | 원본 조건 | 잘못된 입력 | 알리는 곳 · 방법 (계획) | 실제로 보인 글 "
                "| 돌아가는 화면 | 검사 J |", "|---|---|---|---|---|---|---|"]
        out += ["| %s | %s | %s | %s | %s | %s | %s |" % tuple(
            _cell(r[k]) for k in ("id", "about", "input", "where", "shown", "back_to",
                                  "result")) for r in rows]
        out.append("")
        for r in rows:
            shot = os.path.join(shots_dir, "audit_error_%s.png" % r["id"])
            if os.path.exists(shot):
                out.append("- `%s` 오류 상태 — [%s](%s)" % (
                    r["id"], os.path.basename(shot), _link(shot, brief_dir)))
        out.append("")

    out += refine_section(refine, brief_dir)

    out += ["## 화면별 스크린샷", "", "검사기가 과제를 걸으며 찍은 것이다.", ""]
    for sc in plan["screens"]:
        shot = os.path.join(shots_dir, "audit_%s.png" % sc["name"])
        if os.path.exists(shot):
            out.append("- `%s` — [%s](%s)" % (sc["name"], os.path.basename(shot),
                                             _link(shot, brief_dir)))
        else:
            out.append("- `%s` — 스크린샷 없음 (검사기가 걷는 경로에 없던 화면)"
                       % sc["name"])
    out.append("")

    out += ["## 사람이 확인할 것", ""]
    warnings = report.get("warning") or []
    out += ["### 검사의 경고 (%d건)" % len(warnings), ""]
    out += (["- [%s] %s%s" % (w.get("check"), ("`%s`: " % w["screen"]) if w.get("screen")
                               else "", _cell(w.get("detail")))
             for w in warnings] or ["없음"])
    out.append("")
    gaps = choice_gaps(metrics)
    out += ["### 선택지: 문서에 있는 것과 고를 수 있던 것의 차이", ""]
    if gaps:
        out += ["검사기가 걷는 동안 DOM 에서 고를 수 없던 값이 있다. \"전체 보기\" 뒤나 "
                "검색 결과로만 나오는 목록이면 정상이다 — 실제 앱에서 그 길이 있는지 본다.",
                "", "| 선택지 | 문서에 있음 | 걷는 동안 고를 수 있음 |", "|---|---|---|"]
        out += ["| %s | %s | %s |" % (a, k, s) for a, k, s in gaps]
    else:
        out.append("없음")
    out.append("")
    not_choices = metrics.get("choice_groups_not_choices") or {}
    out += ["### 선택지가 아니라고 선언한 무리", ""]
    if not_choices:
        out += ["원본에서 같은 `data-action` 을 가진 형제 무리지만 과제 파일(`not_choices`)이 "
                "선택지가 아니라고 선언한 것이다. 검사 I 는 이 무리가 남았는지 세지 않았다.",
                "",
                "| 무리 (`data-action`) | 원본의 값 | 이유 |", "|---|---|---|"]
        out += ["| `%s` | %s | %s |" % (a, d.get("values"), _cell(d.get("reason")))
                for a, d in sorted(not_choices.items())]
    else:
        out.append("없음")
    out.append("")
    out += ["### 도구가 고친 것", ""]
    if redeclared:
        out.append("도구가 고친 것: 모델이 %s 의 목록을 직접 다시 써서, 도구가 그 선언을 "
                   "입력의 데이터(`window.%s`)로 바꿨다. 모델이 쓴 그대로의 HTML 은 `%s` "
                   "에 있다." % (", ".join(redeclared), GLOBAL_NAME,
                                _link(model_html, brief_dir) if model_html else "?"))
    else:
        out.append("도구가 고친 것: 없음")
    out.append("")
    removed = metrics.get("choice_values_removed_by_design") or {}
    out += ["### 의도한 제거로 허락된 선택지", "",
            "연구자가 `flows/allowed_removals.json` 에 적어 둔 것 가운데 이 빌드에서 "
            "실제로 빠진 것이다.", ""]
    out += (["- `%s`: %s — %s" % (a, ", ".join(d.get("values") or []),
                                   d.get("reason") or "이유가 적혀 있지 않다")
             for a, d in sorted(removed.items())] or ["없음"])
    out.append("")

    out += ["## 선택지 데이터의 출처", ""]
    if preserved:
        out.append("선택지 목록(%s)은 `window.%s` 에서 온다 — 도구가 원본 HTML 에서 "
                   "꺼내 재설계 HTML 의 `<script id=\"preserved-data\">` 에 넣은 것이다. "
                   "목록을 실제 앱으로 옮길 때는 이 블록을 출처로 쓴다."
                   % (", ".join("%s %d" % (n, c) for n, c in preserved.items()),
                      GLOBAL_NAME))
    else:
        out.append("이 입력에는 도구가 넣은 선택지 데이터(`window.%s`)가 없다 — 선택지는 "
                   "재설계 HTML 의 마크업에 직접 있다." % GLOBAL_NAME)
    out.append("")
    return "\n".join(out)


def _read(path):
    return json.load(io.open(path, encoding="utf-8")) if path and os.path.exists(path) \
        else None


def write_brief(summary, original_screens, brief_path, errors=None):
    """summary.json 이 가리키는 파일들로 설명서를 쓴다. 쓴 경로를 돌려준다.

    통과한 빌드에만 부른다. 계획이 없으면(진단·계획 단계 이전의 실행) 쓰지
    않는다 - 대응표와 변경 목록이 설명서의 몸통이다.

    `errors` 는 과제가 정한 오류 경로다. 주지 않으면 기본 과제(이체)의 것."""
    final = summary.get("final") or {}
    plan = _read(final.get("plan"))
    if not plan:
        return None
    reflections = []
    for a in summary.get("attempts") or []:
        refl = _read(a.get("reflection"))
        if refl:
            reflections.append({"attempt": a["n"], "cause": refl.get("cause"),
                                "plan_changes": a.get("plan_changes", 0)})
    run_dir = summary["run_dir"]
    text = render_brief(
        run_name=os.path.basename(run_dir), attempt=final["attempt"], plan=plan,
        diagnosis=_read(final.get("diagnosis")) or [],
        report=_read(final.get("audit")), original_screens=original_screens,
        shots_dir=os.path.join(run_dir, "shots", "attempt_%d" % final["attempt"]),
        brief_dir=os.path.dirname(os.path.abspath(brief_path)),
        preserved=summary.get("preserved"),
        redeclared=(final.get("preserved") or {}).get("redeclared"),
        model_html=final.get("model_html_promoted") or final.get("model_html"),
        git=summary.get("git"), reflections=reflections,
        errors=original_error_paths() if errors is None else errors,
        refine=summary.get("refine"))
    io.open(brief_path, "w", encoding="utf-8", newline="\n").write(text)
    return brief_path
