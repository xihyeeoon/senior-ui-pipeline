r"""기능-화면 표 - "기능은 줄이지 않는다" 의 확인표.

줄은 기능, 칸은 화면(본 장의 화면 ID). 그 기능의 요소가 그 화면의 어느 장에서 보였으면
표시한다.

  ●  바로 보임   그 화면의 본 장 · 다시 지나는 장 · 오류 장에서 보였다
  ○  펼쳐야 보임 그 화면의 펼친 뒤 장에서만 보였다

표시는 모두 도구가 모은 것이다 - 장마다 보인 data-action 요소(덮개 아래에 깔린 것은
빼고), 흐름 명세가 정한 걸음과 오류 경로. 모델의 말(계획 · 영역 설명)로는 표시하지
않는다. 줄에 표시가 하나도 없으면 설계서의 어느 장에서도 그 기능을 보지 못한 것이다.

줄의 다섯 무리:

  steps      과제 단계 - 정답 경로의 걸음마다 (흐름 명세 steps), 그 걸음의 장
  choices    선택지 무리 - 최종 검사의 choice_groups_original (검사 I 가 세는 것) 중
             숫자판이 아닌 것. 이름과 원본의 값 수
  inputs     입력 수단 - 숫자판(무리의 값이 모두 1~3자리 숫자인 것)과 입력 칸(data-action
             이 붙은 input · textarea · select)
  errors     오류 회복 - 흐름 명세 error_paths 마다, 오류가 보이는 장
  entrances  과제 밖 입구 - 과제 파일의 entrances. 이름은 원본에 붙인 aria-label

"원본 화면" 칸은 그 기능이 원본에서 어느 화면에 있었는가다. 출처가 줄마다 다르다:

  steps      계획의 화면 목록(from) - 재구성 실행의 모델이 쓴 것
  choices · inputs  원본을 그 과제의 흐름대로 걸으며 그 이름의 요소가 그려진 화면
             (도구 확인 - walk.survey)
  errors     과제의 원본 흐름이 정한 오류 화면(expect_screen)과 되돌아가는 화면
  entrances  과제 파일의 화면 (연구자 확정)
"""
import re

DIRECT, REVEALED = "●", "○"
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


def place(sheets, match):
    """match(항목) 이 참인 항목이 보인 장들을 칸마다 모은다.
    `{칸: {"mark", "count", "sheets"}}` - 바로 보인 장이 하나라도 있으면 ●."""
    col = column_of(sheets)
    cells = {}
    for sh in sheets:
        found = [it for it in sh["items"] if match(it)]
        if not found:
            continue
        mark = REVEALED if sh["kind"] == "reveal" else DIRECT
        n = sum(it["group"]["count"] if it["kind"] == "group" else 1 for it in found)
        c = cells.get(col[sh["id"]])
        if c is None or (c["mark"] == REVEALED and mark == DIRECT):
            cells[col[sh["id"]]] = {"mark": mark, "count": n, "sheets": [sh["id"]]}
        elif c["mark"] == mark:
            c["count"] = max(c["count"], n)
            c["sheets"].append(sh["id"])
    return cells


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


def matrix(sheets, flow_info, groups, group_counts, entrances, task_errors, where):
    """기능-화면 표. `{"columns", "rows", "missing"}` - missing 은 표시가 하나도 없는 줄.

    줄은 `{"section", "key", "cells", "original", "original_from", ...}` 에 무리마다
    그릴 때 쓸 칸이 더 있다 (steps: step · sheet · how / choices · inputs: action · kind ·
    count_original · keys · text / errors: id · about · sheet · recover · back_to_sheet ·
    original_back_to / entrances: id · action · label)."""
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

    values = {}
    for sh in sheets:
        for it in sh["items"]:
            if it["kind"] == "group":
                values.setdefault(it["action"], set()).update(it["group"]["values"])
    pads, picks = [], []
    for a in groups:
        vals = sorted(values.get(a) or [])
        row = {"key": a, "action": a, "count_original": (group_counts or {}).get(a),
               "cells": place(sheets, lambda it, a=a: it["action"] == a),
               "original": list(where.get(a) or []), "original_from": "survey"}
        if is_keypad(vals):
            pads.append(dict(row, section="inputs", kind="keypad", keys=len(vals)))
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
