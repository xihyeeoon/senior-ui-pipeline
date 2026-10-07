r"""설계서 조립 - 실행 폴더를 읽고, 걷고, 영역을 묶고, storyboard/ 에 쓴다.

storyboard/ 에 남는 것:

  storyboard.json        설계서의 모든 내용 (그림 말고는 이것으로 다시 그린다 - render.py)
  index.html             설계서 (가로 A4 - 맨 앞장 · 와이어플로 · 기능-화면 표 · 화면마다 한 장)
  storyboard.pdf         index.html 을 브라우저(Chromium)로 인쇄한 것
  shots/<상태>.png       로우파이 와이어프레임 그림 (390px 폭, 2배 해상도)
  shots/<상태>.marked.png 요소 번호를 얹은 그림 (모델에게 보낸 것, 1배)
  wireframe.html         그림용 사본 - 최종 HTML 에 로우파이 덮개만 넣었다
  regions.prompt.txt · regions.response.txt (+ regions.retry.*)  영역 묶기 호출 기록
  storyboard.log         한 줄씩 무엇을 했는지

실행 폴더의 다른 파일은 고치지 않는다.
"""
import io
import json
import os
import re
import shutil
import time

from senior_ui import config
from senior_ui.audit.flow import load_flow, visit_keys
from senior_ui.audit.inputs import judged_flow, read_flow
from senior_ui.devserver import ensure_server

from . import features as F
from . import regions as R
from . import render
from . import walk as W
from .run import head_commit, load_run, original_fingerprint

OUT_DIR = "storyboard"
JSON_NAME = "storyboard.json"
# 2: 장마다 화면 이름(title · name · name_source)과 경로(path), 원본 걷기(original) ·
#    기능-화면 표(features) (11-12b)
SCHEMA = 2
# 화면 이름이 없을 때 쓰는 계획의 화면 목적 앞부분의 길이
NAME_CHARS = 20

# 한 줄로 보는 행 - 위쪽 끝이 이만큼 안에 있으면 같은 줄로 보고 왼쪽부터 번호를 매긴다.
ROW_TOLERANCE = 6

KIND_LABEL = {"visit": "다시 지날 때", "error": "오류", "reveal": "펼친 뒤"}


def sheet_id(screen, suffix=None):
    base = "scr-%s" % (screen or "unknown")
    return base if not suffix else "%s--%s" % (base, suffix)


def safe(s):
    return re.sub(r"[^0-9A-Za-z_.-]", "_", str(s))


# --------------------------------------------------------------------------- #
# 요소 → 번호 매긴 항목
# --------------------------------------------------------------------------- #
def union(boxes):
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[0] + b[2] for b in boxes)
    y1 = max(b[1] + b[3] for b in boxes)
    return [x0, y0, x1 - x0, y1 - y0]


def itemize(raw, groups):
    """보이는 요소들을 설계서의 항목으로. 선택지 무리(검사 I 가 세는 것)는 그 상태에서
    둘 이상 보이면 항목 하나로 묶는다 - 대표 하나만 눌러 본다. 번호(e1, e2 …)는 위에서
    아래, 같은 줄이면 왼쪽부터.

    대표는 읽는 순서(위에서 아래, 왼쪽부터)로 첫 것이다 - 꺼진 것은 뒤로. 비밀번호
    숫자판처럼 그릴 때마다 섞는 무리도 설계서의 페이지는 난수를 고정하므로(walk.
    SEEDED_RANDOM) 같은 대표가 된다. 값 순서로 고르면 금액 숫자판의 대표가 '0' 이 되어
    빈 칸에서 누르면 아무 일도 없다."""
    by_action = {}
    for r in raw:
        if r["action"] in groups:
            by_action.setdefault(r["action"], []).append(r)
    grouped = {a for a, m in by_action.items() if len(m) >= 2}
    items = []
    for r in raw:
        if r["action"] in grouped:
            continue
        items.append({"kind": "element", "action": r["action"], "text": r["text"],
                      "aria": r["aria"], "value": r["value"], "id": r["id"],
                      "tag": r["tag"], "box": list(r["box"]), "disabled": r["disabled"],
                      "entrance": W.is_entrance(r["action"]),
                      "_index": r["index"], "_members": [r["index"]]})
    for a in sorted(grouped):
        members = by_action[a]
        values = sorted({m["value"] for m in members})
        rep = min(members, key=lambda m: (m["disabled"], m["box"][1], m["box"][0],
                                          m["index"]))
        items.append({"kind": "group", "action": a,
                      "text": rep["text"], "aria": rep["aria"], "value": rep["value"],
                      "id": None, "tag": rep["tag"], "box": union([m["box"] for m in members]),
                      "disabled": all(m["disabled"] for m in members),
                      "entrance": W.is_entrance(a),
                      "group": {"count": len(members), "values": values},
                      "_index": rep["index"], "_members": [m["index"] for m in members]})
    items.sort(key=lambda it: (it["box"][1], it["box"][0]))
    rows, row = [], []
    for it in items:
        if row and it["box"][1] - row[0]["box"][1] > ROW_TOLERANCE:
            rows.append(row)
            row = []
        row.append(it)
    if row:
        rows.append(row)
    out = []
    for row in rows:
        out += sorted(row, key=lambda it: (it["box"][0], it["box"][1]))
    for i, it in enumerate(out, 1):
        it["no"] = "e%d" % i
    return out


def target_of(item):
    """확인 페이지에서 그 항목을 찾는 법. 무리는 값으로 찾는다 (순번은 섞일 수 있다)."""
    return {"index": item["_index"], "action": item["action"], "value": item["value"],
            "by_value": item["kind"] == "group"}


def item_for_index(items, index, raw):
    """요소 순번 → 그 상태의 항목 번호. 무리의 일원이면 그 무리."""
    if index is None:
        return None
    for it in items:
        if index in it["_members"]:
            return it
    action = next((r["action"] for r in raw if r["index"] == index), None)
    if action:
        for it in items:
            if it["kind"] == "group" and it["action"] == action:
                return it
    return None


# --------------------------------------------------------------------------- #
# 흐름 명세의 조작 → 사람이 읽는 말
# --------------------------------------------------------------------------- #
def click_selectors(actions):
    out = []
    for a in actions or []:
        if isinstance(a, dict) and isinstance(a.get("click"), str):
            out.append(a["click"])
    return out


def describe_actions(actions, flow, sel_index, items, raw):
    """흐름 명세의 조작 목록을 `[{"type", ...}]` 로. 누르기는 그 상태의 요소 번호로."""
    out = []
    for a in actions or []:
        if not isinstance(a, dict):
            continue
        if "type" in a:
            out.append({"type": "type", "value": a["type"]})
        elif "click" in a and isinstance(a["click"], str):
            sel = W.filled(a["click"], flow)
            it = item_for_index(items, (sel_index or {}).get(sel), raw)
            row = {"type": "click", "selector": a["click"]}
            if "repeat" in a:
                row["repeat"] = int(a["repeat"])
            if it:
                row.update(item=it["no"], text=it["text"] or it["aria"] or it["action"])
            out.append(row)
    return out


# --------------------------------------------------------------------------- #
# 걷기 결과 → 장(sheet)
# --------------------------------------------------------------------------- #
def assemble(run, flow, states, walked, groups):
    """상태마다 걸은 결과를 설계서의 장으로. `(sheets, flow_info)`.

    화면마다 본 장 하나 - 정답 경로에서 그 화면을 처음 지나는 상태. 나머지(다시 지남 ·
    오류 · 펼친 뒤)는 그 화면의 조건별 장이다. 정답 경로가 지나지 않는 화면은 그
    화면에 처음 닿은 조건별 상태가 본 장이 된다."""
    plan = run.get("plan_data") or {}
    purposes = {s.get("name"): s for s in plan.get("screens") or [] if isinstance(s, dict)}
    by_key = {st["key"]: st for st in states}
    rows = []
    for st in states:
        got = walked["states"].get(st["key"]) or {}
        landed = got.get("dom_screen") or got.get("landed_on") or st.get("screen")
        rows.append((st, got, landed))
    main_of = {}
    for st, got, landed in rows:
        if st["kind"] == "visit" and st["nth"] == 1 and landed not in main_of:
            main_of[landed] = st["key"]
    for st, got, landed in rows:
        if landed not in main_of:
            main_of[landed] = st["key"]

    sheets = {}
    for st, got, landed in rows:
        is_main = main_of.get(landed) == st["key"]
        if is_main:
            sid = sheet_id(landed)
        elif st["kind"] == "visit":
            sid = sheet_id(landed, "visit-%d" % st["nth"])
        elif st["kind"] == "error":
            sid = sheet_id(landed, "error-%s" % safe(st["id"]))
        else:
            sid = sheet_id(landed, "reveal-%s" % safe(st["action"]))
        raw = got.get("items") or []
        items = itemize(raw, groups)
        clicks = (walked.get("clicks") or {}).get(st["key"]) or {}
        for it in items:
            res = dict(clicks.get(it["no"]) or {"kind": "failed",
                                                "detail": "눌러 보지 않았다"})
            if res.get("kind") == "screen":
                res["to_id"] = sheet_id(res["to"])
            it["result"] = res
        p = purposes.get(landed) or {}
        sheet = {"id": sid, "screen": landed, "state": st["key"], "kind": st["kind"],
                 "main": is_main, "expected_screen": st.get("screen"),
                 "purpose": p.get("purpose"), "from_original": p.get("from") or [],
                 "picture": rel_shot(got.get("picture")),
                 "marked": rel_shot(got.get("marked")),
                 "size": got.get("size"), "scale": W.PICTURE_SCALE,
                 "grown": got.get("grown") or 0,
                 "clipped": got.get("clipped") or 0, "covered": got.get("covered") or 0,
                 "dialogs": got.get("dialogs") or [], "error": got.get("error"),
                 "items": items, "regions": [], "conditions": [], "of": None,
                 "condition": None, "_raw": raw, "_sel": got.get("selector_index") or {}}
        sheets[st["key"]] = sheet

    ordered = []
    for st, got, landed in rows:
        sh = sheets[st["key"]]
        if not sh["main"]:
            parent = sheets[main_of[landed]]
            sh["of"] = parent["id"]
            sh["purpose"] = parent["purpose"]
            parent["conditions"].append(sh["id"])
    # 장의 순서: 계획의 화면 순서 → 본 장 다음에 그 조건별 장들
    plan_order = [s.get("name") for s in plan.get("screens") or [] if isinstance(s, dict)]
    mains = [sheets[k] for k in dict.fromkeys(main_of[s] for s in main_of)]
    mains.sort(key=lambda sh: (plan_order.index(sh["screen"]) if sh["screen"] in plan_order
                               else len(plan_order), [r[0]["key"] for r in rows].index(
                                   sh["state"])))
    for m in mains:
        ordered.append(m)
        ordered += [sh for sh in sheets.values() if sh["of"] == m["id"]]

    flow_info = flow_order(run, flow, states, sheets, by_key)
    for sh in ordered:
        sh["condition"] = condition_text(sh, by_key[sh["state"]], run, sheets, flow_info)
        sh["path"] = path_of(by_key[sh["state"]], flow, sheets)
    return ordered, flow_info


def path_of(state, flow, sheets):
    """그 장에 이르는 경로 - 정답 경로의 걸음마다의 장 id, 그 상태의 방문까지. 조건별
    상태(오류 · 펼친 뒤)는 그 끝에 제 장을 붙인다. 같은 장이 잇달아 오면 하나로."""
    visits = visit_keys(flow.get("steps") or [])
    upto = visits.index(state["visit"]) if state["visit"] in visits else -1
    out = []
    for v in visits[:upto + 1]:
        sh = sheets.get("visit:%s" % v)
        if sh and (not out or out[-1] != sh["id"]):
            out.append(sh["id"])
    if state["kind"] != "visit":
        out.append(sheets[state["key"]]["id"])
    return out


def purpose_head(purpose, limit=NAME_CHARS):
    """계획의 화면 목적 앞부분 - 첫 문장, 길면 limit 자에서 자른다."""
    if not purpose:
        return None
    text = " ".join(str(purpose).split())
    first = re.split(r"(?<=[.!?。])\s+", text)[0].rstrip(".。 ")
    return first if len(first) <= limit else first[:limit - 1].rstrip() + "…"


def name_sheets(sheets):
    """장마다 화면 이름. 영역 묶기의 화면 이름(그 장, 없으면 본 장의 것)이 있으면 그것
    (출처 model), 없으면 계획의 화면 목적 앞부분 (plan), 그것도 없으면 화면 이름 (screen)."""
    by_id = {s["id"]: s for s in sheets}
    for sh in sheets:
        parent = by_id.get(sh.get("of")) or {}
        title = sh.get("title") or parent.get("title")
        head = purpose_head(sh.get("purpose"))
        if title:
            sh["name"], sh["name_source"] = title, "model"
        elif head:
            sh["name"], sh["name_source"] = head, "plan"
        else:
            sh["name"], sh["name_source"] = sh.get("screen") or sh["id"], "screen"


def rel_shot(path):
    return "shots/%s" % os.path.basename(path) if path else None


def flow_order(run, flow, states, sheets, by_key):
    """맨 앞장의 화면 순서 - 정답 경로의 걸음마다 어느 장이고 앞 장에서 무엇을 해서
    왔는가. 오류 경로 · 펼치기는 따로."""
    steps = flow.get("steps") or []
    visits = visit_keys(steps)
    order = []
    prev = None
    for i, (step, visit) in enumerate(zip(steps, visits)):
        sh = sheets.get("visit:%s" % visit)
        actions = step.get("do") if "do" in step else (
            [{"click": step["click"]}] if "click" in step else [])
        how = describe_actions(actions, flow, prev["_sel"] if prev else None,
                               prev["items"] if prev else [], prev["_raw"] if prev else [])
        order.append({"step": i + 1, "visit": visit, "sheet": sh["id"] if sh else None,
                      "screen": sh["screen"] if sh else step.get("screen"), "how": how})
        prev = sh
    defs = {e.get("id"): e for e in _task_errors(run["task"])}
    errors = []
    for st in states:
        if st["kind"] != "error":
            continue
        sh, src = sheets[st["key"]], sheets.get("visit:%s" % st["visit"])
        d = defs.get(st["id"]) or {}
        errors.append({
            "id": st["id"], "about": d.get("about"), "condition": d.get("condition"),
            "uses": d.get("uses") or [], "from_sheet": src["id"] if src else None,
            "sheet": sh["id"],
            "inputs": describe_actions(st["extra"], flow, src["_sel"] if src else None,
                                       src["items"] if src else [],
                                       src["_raw"] if src else []),
            "recover": describe_actions(st.get("recover"), flow, sh["_sel"], sh["items"],
                                        sh["_raw"]),
            "back_to": st.get("back_to"),
            "back_to_sheet": sheet_id(st["back_to"]) if st.get("back_to") else None})
    reveals = []
    for st in states:
        if st["kind"] != "reveal":
            continue
        sh, src = sheets[st["key"]], sheets.get("visit:%s" % st["visit"])
        reveals.append({"action": st["action"], "at_sheet": src["id"] if src else None,
                        "sheet": sh["id"],
                        "how": describe_actions(st["extra"], flow,
                                                src["_sel"] if src else None,
                                                src["items"] if src else [],
                                                src["_raw"] if src else [])})
    return {"steps": order, "errors": errors, "reveals": reveals}


def _task_errors(task):
    from senior_ui.audit.flow import task_error_paths
    try:
        return task_error_paths(task)
    except (OSError, ValueError):
        return []


def condition_text(sheet, st, run, sheets, flow_info):
    """조건별 장이 어떤 조건에서 나오는가 - 흐름 명세의 error_paths · reveal · steps 에서."""
    if sheet["main"] and st["kind"] == "visit":
        return None
    if st["kind"] == "visit":
        return "정답 경로에서 이 화면을 %d번째로 지날 때 (흐름 명세 steps 의 '%s')" \
            % (st["nth"], st["visit"])
    if st["kind"] == "error":
        e = next((x for x in flow_info["errors"] if x["id"] == st["id"]), {})
        about = e.get("about") or e.get("condition") or ""
        return ("오류 경로 '%s'%s — %s 에서 잘못된 값(%s)을 넣은 뒤 (흐름 명세 error_paths)"
                % (st["id"], " (%s)" % about if about else "",
                   e.get("from_sheet") or st["visit"],
                   ", ".join(e.get("uses") or []) or "과제의 틀린 값"))
    return ("'%s' 을 펼친 뒤 — %s 에서 펼치는 조작을 한 상태 (흐름 명세 reveal)"
            % (st["action"], sheet_id(st.get("screen")) if st.get("screen") else st["visit"]))


# --------------------------------------------------------------------------- #
# 맨 앞장의 자료
# --------------------------------------------------------------------------- #
def front_matter(run, plan, diagnosis):
    summ = run["summary"]
    diag = diagnosis if isinstance(diagnosis, list) else []
    by_id = {d.get("id"): d for d in diag if isinstance(d, dict)}
    changes = []
    for c in (plan or {}).get("changes") or []:
        if not isinstance(c, dict):
            continue
        changes.append({"id": c.get("id"), "what": c.get("what"), "why": c.get("why"),
                        "addresses": [{"id": a, "screen": (by_id.get(a) or {}).get("screen"),
                                       "problem": (by_id.get(a) or {}).get("problem")}
                                      for a in c.get("addresses") or []],
                        "from_screens": c.get("from_screens") or [],
                        "to_screens": c.get("to_screens") or []})
    kinds, screens = {}, {}
    for d in diag:
        if not isinstance(d, dict):
            continue
        k = d.get("evidence_kind") or "missing"
        kinds[k] = kinds.get(k, 0) + 1
        screens[d.get("screen")] = screens.get(d.get("screen"), 0) + 1
    git = summ.get("git") or {}
    refine = summ.get("refine") or {}
    return {
        "task": {"id": run["task"], "label": run["task_def"].get("label") or run["task"],
                 "description": run["task_def"]["description"]},
        "changes": changes,
        "diagnosis": {"count": len(diag), "evidence_kinds": kinds, "by_screen": screens,
                      "items": [{"id": d.get("id"), "screen": d.get("screen"),
                                 "element": d.get("element"), "problem": d.get("problem"),
                                 "evidence_kind": d.get("evidence_kind")}
                                for d in diag if isinstance(d, dict)]},
        "run": {"id": run["name"], "task": run["task"], "model": summ.get("model"),
                "model_source": summ.get("model_source"), "mock": summ.get("mock"),
                "stage": summ.get("stage"),
                "final_attempt": (run["final"] or {}).get("attempt"),
                "final_label": refine.get("final_label") or "생성",
                "commit": git.get("commit"), "dirty": git.get("dirty"),
                "original": original_fingerprint(run["task_def"], git.get("commit")),
                "cost_usd": (summ.get("cost") or {}).get("total_usd")},
    }


# --------------------------------------------------------------------------- #
# 전부
# --------------------------------------------------------------------------- #
class Log:
    def __init__(self, path, echo=True):
        self.path, self.echo = path, echo
        self.t0 = time.time()

    def __call__(self, msg):
        line = "[%5.1fs] %s" % (time.time() - self.t0, msg)
        if self.echo:
            print(line, flush=True)
        with io.open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def public(sheets):
    """storyboard.json 에 쓰는 장 - 안에서만 쓰는 칸(_로 시작)을 뺀다."""
    out = []
    for sh in sheets:
        row = {k: v for k, v in sh.items() if not k.startswith("_")}
        row["items"] = [{k: v for k, v in it.items() if not k.startswith("_")}
                        for it in sh["items"]]
        out.append(row)
    return out


def inspect(build_url, wire_url, flow, groups, shots_dir, log=print,
            concurrency=W.CONCURRENCY, original=None):
    """걷기만 - 상태들과 걸은 결과. 단위 시험이 작은 HTML 로 이것을 부른다.
    original = (원본 URL, 원본 흐름) 이면 원본도 한 번 걷는다 (walked["original"])."""
    states = W.states_of(flow)
    for st in states:
        st["file_id"] = safe(st["key"].replace(":", "-"))
    raw_cache = {}

    def number(raw):
        return [(it["no"], it["box"]) for it in itemize(raw, groups)]

    def selectors_for(st):
        sels = []
        steps = flow.get("steps") or []
        if st["kind"] == "visit":
            if st["upto"] + 1 < len(steps):
                nxt = steps[st["upto"] + 1]
                sels += click_selectors(nxt.get("do") if "do" in nxt else
                                        [{"click": nxt["click"]}] if "click" in nxt else [])
            for other in states:
                if other["kind"] in ("error", "reveal") and other["visit"] == st["visit"]:
                    sels += click_selectors(other["extra"])
        elif st["kind"] == "error":
            sels += click_selectors(st.get("recover"))
        return [W.filled(s, flow) for s in dict.fromkeys(sels)]

    def targets_for(st, got):
        items = itemize(got.get("items") or [], groups)
        raw_cache[st["key"]] = items
        return [(it["no"], target_of(it)) for it in items]

    walked = W.walk(build_url, wire_url, flow, states, shots_dir, number, selectors_for,
                    targets_for, log=log, concurrency=concurrency, original=original)
    return states, walked


def make(run_dir, port=config.AUTO_PORT, model=None, mock=None, log_echo=True,
         pdf=True, reasoning_effort=None, concurrency=W.CONCURRENCY):
    """실행 폴더 하나의 설계서. 돌려주는 것은 `(code, storyboard_or_reason)`.

    0 = 만들었다, 1 = 만들었지만 영역 묶기를 모델로 하지 못했다 (화면마다 "기타"),
    2 = 만들 수 없는 실행이다 (load_run 의 NotReady) - 아무것도 쓰지 않는다."""
    run = load_run(run_dir)                     # NotReady 는 부르는 쪽이 받는다
    if not config.inside_root(run["dir"]):
        raise R.CannotRun("실행 폴더가 저장소 밖이다 (%s) - 서버가 그 파일을 주지 못한다"
                          % run["dir"])
    out = os.path.join(run["dir"], OUT_DIR)
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(os.path.join(out, "shots"))
    log = Log(os.path.join(out, "storyboard.log"), echo=log_echo)
    t0 = time.time()
    log("실행 %s · 과제 %s · 최종 시도 %s" % (run["name"], run["task"],
                                          (run["final"] or {}).get("attempt")))
    html = io.open(run["html"], encoding="utf-8").read()
    wire_path = os.path.join(out, "wireframe.html")
    with io.open(wire_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(W.wire_copy(html))
    flow = judged_flow(read_flow(run["flow"]), task=run["task"],
                       stage=run["summary"].get("stage"))
    metrics = run["audit_report"].get("metrics") or {}
    groups = sorted((metrics.get("choice_groups_original") or {}).keys())
    log("선택지 무리 (최종 검사의 choice_groups_original): %s" % (", ".join(groups) or "없음"))

    lines = []
    proc = ensure_server(lines.append, port=port)
    for l in lines:
        log(l)
    try:
        base = config.base_url(getattr(proc, "port", None) or port or config.PORT)
        rel = lambda p: os.path.relpath(p, config.ROOT).replace(os.sep, "/")
        build_url = "%s/%s" % (base, rel(run["html"]))
        wire_url = "%s/%s" % (base, rel(wire_path))
        orig_rel = run["task_def"]["original"]
        orig_flow = load_flow(None, task=run["task"])
        states, walked = inspect(build_url, wire_url, flow, groups,
                                 os.path.join(out, "shots"), log=log,
                                 concurrency=concurrency,
                                 original=("%s/%s" % (base, orig_rel), orig_flow))
        sheets, flow_info = assemble(run, flow, states, walked, groups)
        front = front_matter(run, run.get("plan_data"), run.get("diagnosis_data"))
        log("장 %d (본 장 %d) · 항목 %d · 누르기 %d번 · 그림 %.1f초 · 누르기 %.1f초"
            % (len(sheets), sum(1 for s in sheets if s["main"]),
               sum(len(s["items"]) for s in sheets), walked.get("click_count", 0),
               walked["seconds"].get("pictures", 0), walked["seconds"].get("clicks", 0)))

        call = R.group(sheets, model=model, mock=mock, out_dir=out, log=log,
                       reasoning_effort=reasoning_effort)
        name_sheets(sheets)
        survey = walked.get("original") or {}
        where = F.where_in_original(survey)
        table = F.matrix(sheets, flow_info, groups, metrics.get("choice_groups_original"),
                         (run["task_def"].get("entrances") or {}).get("items"),
                         _task_errors(run["task"]), where)
        if table["missing"]:
            log("기능-화면 표: 어느 장에서도 보지 못한 줄 %d - %s"
                % (len(table["missing"]), ", ".join(table["missing"])))
        data = {
            "schema": SCHEMA,
            "generated": {"at": time.strftime("%Y-%m-%d %H:%M:%S"),
                          "tool_commit": head_commit(),
                          "seconds": {"pictures": walked["seconds"].get("pictures"),
                                      "clicks": walked["seconds"].get("clicks"),
                                      "total": None}},
            **front,
            "flow": flow_info,
            "original": {"html": orig_rel,
                         "steps": [{"visit": st["visit"], "lit": st["lit"]}
                                   for st in survey.get("steps") or []],
                         "error": survey.get("error"), "where": where},
            "features": table,
            "choice_groups": groups,
            "counts": {"sheets": len(sheets),
                       "main_sheets": sum(1 for s in sheets if s["main"]),
                       "items": sum(len(s["items"]) for s in sheets),
                       "elements": sum(len(s["_raw"]) for s in sheets),
                       "clicks": walked.get("click_count", 0)},
            "sheets": public(sheets),
            "regions_call": call,
        }
        data["generated"]["seconds"]["total"] = round(time.time() - t0, 1)
        with io.open(os.path.join(out, JSON_NAME), "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        page = render.render(data)
        with io.open(os.path.join(out, "index.html"), "w", encoding="utf-8",
                     newline="\n") as f:
            f.write(page)
        log("index.html · storyboard.json 을 썼다")
        if pdf:
            pdf_path = os.path.join(out, "storyboard.pdf")
            render.print_pdf("%s/%s" % (base, rel(os.path.join(out, "index.html"))), pdf_path)
            log("storyboard.pdf 를 썼다 (Chromium 인쇄)")
    finally:
        if proc is not None:
            proc.terminate()
            proc.wait()
            log("server: 띄운 서버를 껐다 (pid %d)" % proc.pid)
    code = 1 if call.get("error") else 0
    log("끝 (%.1f초) - %s" % (time.time() - t0, out))
    return code, data
