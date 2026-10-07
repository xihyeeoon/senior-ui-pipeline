r"""기능-화면 표 - "기능은 줄이지 않는다" 의 확인표.

줄은 기능, 칸은 화면(본 장의 화면 ID). 그 기능이 그 화면의 어느 장에서 보였으면
표시한다.

  ●  흐름이 머무는 상태(본 장 · 다시 지나는 장)에서 보였다
  ○  조건별 장(펼친 뒤 · 오류)에서만 보였다

오류 회복 줄만은 그 오류가 보이는 화면에 ● 다 (그 줄이 곧 그 조건이다).

표시는 모두 도구가 모은 것이다 - 장마다 보인 data-action 요소(덮개 아래에 깔린 것은
빼고), 흐름 명세가 정한 걸음과 오류 경로. 모델의 말(계획 · 영역 설명)로는 표시하지
않는다. 줄에 표시가 하나도 없으면 설계서의 어느 장에서도 그 기능을 보지 못한 것이다.

선택지 무리 · 숫자판은 값으로 찾는다 (11-12c). 원본의 무리마다 원본을 걸으며 모은 값
(walk.survey - 검사 I 가 원본에서 모으는 것과 같은 조각)을, 장마다 그 상태의 누를 수 있는
요소(data-action 이 무엇이든)의 값에서 검사 I 와 같은 경계 규칙(i_choices.present)으로
찾는다. 요소의 값은 검사 I 가 모으는 것과 같다 - data-action 말고 첫 data-* 값, 없으면
글자. 보이는 글자 전체로 찾지 않는다 - '1만원' 이라고 쓴 빠른 금액 단추(값 10000)가
숫자판의 '1' 로 잡힌다. 빌드가 같은 기능을 다른 이름으로 그려도(금액 숫자판을
amt-num 으로) 찾고, 찾은 값 수("38/67")와 빌드가 쓴 data-action 이름을 적는다. 원본의
값을 모으지 못했으면(원본을 열지 못한 경우) 이름으로 찾고 그렇다고 적는다 (by: name).
과제 밖 입구는 이름(oos-)으로 찾는다 - 계약상 이름이 보존된다.

생성물의 data-action 하나는 원본 무리 하나에만 센다 (11-12d). 값이 같은 무리(0~9 숫자판
셋 - 계좌번호 · 금액 · 비밀번호)가 서로를 찾지 않도록, 장마다 생성물의 data-action 마다 그
값들이 가장 많이 덮는 원본 무리 하나를 고른다. 동점이면 차례로 가른다:

  (1) 그 생성물 화면의 바탕 원본 화면(계획의 screens[].from)에 있던 무리
  (2) 이름이 같은 무리
  (3) 그래도 같으면 그 칸에 "같은 값" 이라고만 적고 줄에 "값이 같은 무리: <이름들>" -
      ● 도 ○ 도 아니고 찾은 수에도 넣지 않는다 (TIED)

줄의 다섯 무리:

  steps      과제 단계 - 정답 경로의 걸음마다 (흐름 명세 steps), 그 걸음의 장
  choices    선택지 무리 - 최종 검사의 choice_groups_original (검사 I 가 세는 것) 중
             숫자판이 아닌 것. 원본 이름 · 원본 값 수 · 찾은 값 수 · 빌드의 이름
  inputs     입력 수단 - 숫자판(원본의 값이 모두 1~3자리 숫자인 무리)과 입력 칸(빌드에서
             data-action 이 붙은 input · textarea · select - 이름으로)
  errors     오류 회복 - 흐름 명세 error_paths 마다, 오류가 보이는 장
  entrances  과제 밖 입구 - 과제 파일의 entrances. 이름은 원본에 붙인 aria-label

"원본 화면" 칸은 그 기능이 원본에서 어느 화면에 있었는가다. 출처가 줄마다 다르다:

  steps      계획의 화면 목록(from) - 재구성 실행의 모델이 쓴 것
  choices · inputs  원본을 그 과제의 흐름대로 걸으며 그 원본 이름의 요소가 그려진 화면
             (도구 확인 - walk.survey)
  errors     과제의 원본 흐름이 정한 오류 화면(expect_screen)과 되돌아가는 화면
  entrances  과제 파일의 화면 (연구자 확정)
"""
import re

from senior_ui.audit.checks.i_choices import present

DIRECT, REVEALED = "●", "○"
# 값이 같은 무리라 어느 무리인지 가를 수 없는 칸 - ● · ○ 로 세지 않는다
TIED = "="
SECTIONS = ("steps", "choices", "inputs", "errors", "entrances")
SECTION_LABEL = {"steps": "과제 단계", "choices": "선택지 무리", "inputs": "입력 수단",
                 "errors": "오류 회복", "entrances": "과제 밖 입구"}
ORIGINAL_FROM = {"plan": "계획", "survey": "도구 확인 (원본을 걸어 봄)",
                 "task_flow": "과제의 원본 흐름", "task": "과제 파일"}
KEYPAD_VALUE = re.compile(r"^\d{1,3}$")
FIELD_TAGS = ("input", "textarea", "select")


def columns(sheets):
    """칸 - 본 장의 화면 ID, 설계서의 장 순서대로."""
    return [s["id"] for s in sheets if s["main"]]


def column_of(sheets):
    return {s["id"]: (s["id"] if s["main"] else s["of"]) for s in sheets}


def mark_of(sheet):
    """● 흐름이 머무는 상태(정답 경로의 방문) / ○ 조건별 장(펼친 뒤 · 오류)."""
    return DIRECT if sheet["kind"] == "visit" else REVEALED


def place(sheets, match):
    """match(항목) 이 참인 항목이 보인 장들을 칸마다 모은다 (이름으로 찾기).
    `{칸: {"mark", "count", "sheets"}}` - 흐름이 머무는 장이 하나라도 있으면 ●."""
    col = column_of(sheets)
    cells = {}
    for sh in sheets:
        found = [it for it in sh["items"] if match(it)]
        if not found:
            continue
        mark = mark_of(sh)
        n = sum(it["group"]["count"] if it["kind"] == "group" else 1 for it in found)
        c = cells.get(col[sh["id"]])
        if c is None or (c["mark"] == REVEALED and mark == DIRECT):
            cells[col[sh["id"]]] = {"mark": mark, "count": n, "sheets": [sh["id"]]}
        elif c["mark"] == mark:
            c["count"] = max(c["count"], n)
            c["sheets"].append(sh["id"])
    return cells


def pressables(sheet):
    """그 상태의 누를 수 있는 요소마다 `(data-action, 값)`. 만들 때는 모은 요소
    그대로(_raw - 무리의 일원 하나하나), 저장된 장에서는 항목(무리는 일원들의 값)."""
    raw = sheet.get("_raw")
    if raw is not None:
        return [(r["action"], r.get("value") or "") for r in raw]
    out = []
    for it in sheet["items"]:
        if it["kind"] == "group":
            out += [(it["action"], v) for v in it["group"]["values"]]
        else:
            out.append((it["action"], it.get("value") or ""))
    return out


def assign(sheet, values, where):
    """그 상태의 생성물 data-action 마다 원본 무리 하나를 고른다.

    values 는 `{원본 무리: [값]}`, where 는 `{원본 이름: [원본 화면]}` (where_in_original).
    data-action 마다 그 요소들의 값이 덮는 원본 값의 수를 무리마다 세고(검사 I 의 경계 규칙),
    가장 많이 덮는 무리 하나에 붙인다. 동점이면 (1) 그 장의 바탕 원본 화면(from_original)에
    있던 무리, (2) 이름이 같은 무리, (3) 그래도 같으면 가르지 않는다.

    돌려주는 것: `(owned, tied)` - owned `{무리: {"found": 값 집합, "actions": 이름 집합}}`,
    tied `{무리: {"tied": 무리 집합, "actions": 이름 집합}}`."""
    by_action = {}
    for a, v in pressables(sheet):
        by_action.setdefault(a, []).append(v)
    base = set(sheet.get("from_original") or [])
    owned, tied = {}, {}
    for a, vals in by_action.items():
        blob = "\n".join(vals)
        cover = {}
        for g, vs in values.items():
            hit = {v for v in vs if present(v, blob)}
            if hit:
                cover[g] = hit
        if not cover:
            continue
        best = max(len(h) for h in cover.values())
        top = sorted(g for g, h in cover.items() if len(h) == best)
        if len(top) > 1:                                        # (1) 바탕 원본 화면
            top = [g for g in top if base & set(where.get(g) or [])] or top
        if len(top) > 1 and a in top:                           # (2) 같은 이름
            top = [a]
        if len(top) == 1:
            o = owned.setdefault(top[0], {"found": set(), "actions": set()})
            o["found"] |= cover[top[0]]
            o["actions"].add(a)
        else:                                                   # (3) 가르지 못함
            for g in top:
                t = tied.setdefault(g, {"tied": set(), "actions": set()})
                t["tied"] |= set(top)
                t["actions"].add(a)
    return owned, tied


def place_values(sheets, values, where):
    """값으로 찾기 - 무리마다 `(칸, 찾은 값 집합, 빌드의 data-action, 값이 같은 무리)`.

    칸은 `{칸: {"mark", "found", "of", "actions", "sheets", "found_conditional"?}}` 이거나
    가르지 못한 칸 `{"mark": TIED, "tied", "actions", "sheets"}`. 표시는 ● > ○ > TIED 차례로
    센다. found 는 그 표시(● 면 흐름이 머무는 장)의 장 하나에서 찾은 가장 많은 수,
    found_conditional 은 ● 칸에서 조건별 장(펼친 뒤 · 오류)이 더 많이 보일 때 그 수 -
    펼치면 더 보인다는 것을 감추지 않는다."""
    col = column_of(sheets)
    per = [(sh,) + assign(sh, values, where) for sh in sheets]
    out = {}
    for g, vs in values.items():
        cells, extra, total, names, tied_with = {}, {}, set(), set(), set()
        for sh, owned, tied in per:
            key, c = col[sh["id"]], cells.get(col[sh["id"]])
            if g in owned:
                found, actions = owned[g]["found"], owned[g]["actions"]
                total |= found
                names |= actions
                mark = mark_of(sh)
                if mark == REVEALED:
                    extra[key] = max(extra.get(key, 0), len(found))
                if c is None or c["mark"] == TIED or (c["mark"] == REVEALED and mark == DIRECT):
                    cells[key] = {"mark": mark, "found": len(found), "of": len(vs),
                                  "actions": sorted(actions), "sheets": [sh["id"]]}
                elif c["mark"] == mark:
                    c["found"] = max(c["found"], len(found))
                    c["actions"] = sorted(set(c["actions"]) | actions)
                    c["sheets"].append(sh["id"])
            elif g in tied:
                tied_with |= tied[g]["tied"]
                if c is None:
                    cells[key] = {"mark": TIED, "tied": sorted(tied[g]["tied"]),
                                  "actions": sorted(tied[g]["actions"]), "sheets": [sh["id"]]}
                elif c["mark"] == TIED:
                    c["tied"] = sorted(set(c["tied"]) | tied[g]["tied"])
                    c["actions"] = sorted(set(c["actions"]) | tied[g]["actions"])
                    c["sheets"].append(sh["id"])
        for key, c in cells.items():
            if c["mark"] == DIRECT and extra.get(key, 0) > c["found"]:
                c["found_conditional"] = extra[key]
        out[g] = (cells, total, names, sorted(tied_with))
    return out


def where_in_original(survey):
    """원본을 걸은 결과(walk.survey)에서 `{data-action: [화면, …]}` (처음 보인 순서)."""
    out = {}
    for st in (survey or {}).get("steps") or []:
        for screen, acts in (st.get("actions") or {}).items():
            for a in acts:
                if screen not in out.setdefault(a, []):
                    out[a].append(screen)
    return out


def is_keypad(values):
    return bool(values) and all(KEYPAD_VALUE.match(str(v)) for v in values)


def matrix(sheets, flow_info, groups, group_counts, entrances, task_errors, where,
           original_values=None):
    """기능-화면 표. `{"columns", "rows", "missing"}` - missing 은 표시가 하나도 없는 줄.

    original_values 는 원본의 무리마다 값 목록 `{원본 data-action: [값]}` (walk.survey).

    줄은 `{"section", "key", "cells", "original", "original_from", ...}` 에 무리마다
    그릴 때 쓸 칸이 더 있다 (steps: step · sheet · how / choices · 숫자판: action · kind ·
    by (value · name) · count_original · values · found · actions · tied / 입력 칸: action · text ·
    aria / errors: id · about · sheet · recover · back_to_sheet · original_back_to /
    entrances: id · action · label)."""
    by_id = {s["id"]: s for s in sheets}
    col = column_of(sheets)
    rows = []
    for st in flow_info.get("steps") or []:
        sh = by_id.get(st.get("sheet"))
        rows.append({"section": "steps", "key": "step-%d" % st["step"], "step": st["step"],
                     "sheet": st.get("sheet"), "how": st.get("how") or [],
                     "cells": ({col[sh["id"]]: {"mark": DIRECT, "sheets": [sh["id"]]}}
                               if sh else {}),
                     "original": list((sh or {}).get("from_original") or []),
                     "original_from": "plan"})

    built = {}                      # 이름으로 찾을 때 숫자판을 가르는 빌드의 값
    for sh in sheets:
        for it in sh["items"]:
            if it["kind"] == "group":
                built.setdefault(it["action"], set()).update(it["group"]["values"])
    pads, picks = [], []
    known = {a: sorted((original_values or {}).get(a) or []) for a in groups}
    by_value = place_values(sheets, {a: v for a, v in known.items() if v}, where)
    for a in groups:
        vals = known[a]
        row = {"key": a, "action": a, "count_original": (group_counts or {}).get(a),
               "original": list(where.get(a) or []), "original_from": "survey"}
        if vals:
            cells, found, names, tied = by_value[a]
            row.update(by="value", values=len(vals), found=len(found),
                       actions=sorted(names), tied=tied, cells=cells)
        else:
            row.update(by="name", values=None, found=None, actions=[a],
                       cells=place(sheets, lambda it, a=a: it["action"] == a))
        if is_keypad(vals or sorted(built.get(a) or [])):
            pads.append(dict(row, section="inputs", kind="keypad"))
        else:
            picks.append(dict(row, section="choices", kind="group"))
    fields = []
    for sh in sheets:
        for it in sh["items"]:
            a = it["action"]
            if it["kind"] == "element" and it.get("tag") in FIELD_TAGS and a not in groups \
                    and a not in [f["action"] for f in fields]:
                fields.append({"section": "inputs", "key": a, "action": a, "kind": "field",
                               "text": it.get("text"), "aria": it.get("aria"),
                               "cells": place(sheets, lambda x, a=a: x["action"] == a),
                               "original": list(where.get(a) or []),
                               "original_from": "survey"})
    rows += picks + pads + fields

    defs = {e.get("id"): e for e in task_errors or [] if isinstance(e, dict)}
    for e in flow_info.get("errors") or []:
        d = defs.get(e["id"]) or {}
        sid = e.get("sheet")
        rows.append({"section": "errors", "key": e["id"], "id": e["id"],
                     "about": e.get("about"), "sheet": sid, "recover": e.get("recover") or [],
                     "back_to_sheet": e.get("back_to_sheet"),
                     "cells": ({col[sid]: {"mark": DIRECT, "sheets": [sid]}}
                               if sid in col else {}),
                     "original": [d["expect_screen"]] if d.get("expect_screen") else [],
                     "original_back_to": d.get("back_to"), "original_from": "task_flow"})

    for ent in entrances or []:
        if not isinstance(ent, dict) or not ent.get("action"):
            continue
        a = ent["action"]
        rows.append({"section": "entrances", "key": ent.get("id") or a, "id": ent.get("id"),
                     "action": a, "label": ent.get("label"),
                     "cells": place(sheets, lambda it, a=a: it["action"] == a),
                     "original": [ent["screen"]] if ent.get("screen") else [],
                     "original_from": "task"})
    return {"columns": columns(sheets), "rows": rows,
            "missing": ["%s:%s" % (r["section"], r["key"]) for r in rows if not r["cells"]]}
