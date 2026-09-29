r"""What the pipeline actually contains right now, as one JSON structure.

The project has two branches over the same input - a rule-based repair and an
LLM restructuring - and the only way to see where either one stands has been to
list directories and open audit JSON by hand. This walks the declared pipeline
and reports, for every stage and artefact: does the file exist, when was it
written, is it older than its own input (stale), and what did the auditor say.

Importing it gives you state(); running it prints the same thing as JSON, or as
a short text summary with --text.

The pipeline is declared in STAGES below, not discovered. A stage that was never
run shows up as missing rather than silently vanishing, which is the whole point.
"""
import datetime
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _p(*parts):
    return os.path.join(ROOT, *parts)


# --------------------------------------------------------------------------- #
# the pipeline, declared
# --------------------------------------------------------------------------- #
# Each artefact: key, 표시 이름, path, kind, and where it came from.
#   derived_from - 이 입력에서 도구가 자동 생성한다. 입력보다 오래되면 경고.
#   references   - 이 입력을 보고 사람/LLM 이 새로 설계했다. 입력이 바뀌어도
#                  자동으로 낡지 않으므로 경고 대신 참조 관계만 기록한다.
# 둘을 섞으면 원본을 한 번 손볼 때마다 모든 줄에 경고가 켜져 아무도 안 본다.
STAGES = [
    {
        "id": "input",
        "name": "입력",
        "note": "모든 갈래가 같은 원본에서 출발합니다.",
        "artefacts": [
            {"key": "original", "name": "원본 프로토타입", "path": "inputs/original_transfer.html",
             "kind": "prototype", "screens": 8,
             "desc": "신한 SOL 이체 화면을 8화면으로 재현한 것. 실제 캡처를 보고 만들었습니다."},
            {"key": "kb", "name": "고령자 규칙 KB", "path": "kb/senior_kb.csv",
             "kind": "data",
             "desc": "규칙 46개 (SDF-* 41, KS-* 5). 규칙 기반 갈래만 이것을 씁니다."},
        ],
    },
    {
        "id": "rule",
        "name": "갈래 A · 규칙 기반 수리",
        "note": "DesignRepair 가 화면을 하나씩 고칩니다. 화면 안은 고치지만 구조는 못 바꿉니다.",
        "tool": "tools/split_screens.py → tools/run_screens.py → tools/reassemble.py",
        "artefacts": [
            {"key": "repaired", "name": "수리본", "path": "outputs/repaired_transfer.html",
             "kind": "prototype", "screens": 8, "derived_from": ["original", "kb"],
             "audit": "outputs/audit.json", "flow": "tools/flows/original.json",
             "desc": "규칙을 적용해 고친 결과. 화면 수와 구조는 원본 그대로입니다."},
        ],
    },
    {
        "id": "llm",
        "name": "갈래 B · LLM 재구성",
        "note": "규칙을 주지 않고 과업의 어려움만 보고 다시 설계합니다. 구조가 바뀝니다.",
        "tool": "대화로 생성 (Run 1~3) / tools/run_restructure.py (자동)",
        "artefacts": [
            {"key": "run1", "name": "재구성 Run 1", "path": "outputs/restructured_transfer.html",
             "kind": "prototype", "screens": 9, "references": ["original"],
             "audit": "outputs/audit_restructured.json", "flow": "tools/flows/restructured.json",
             "desc": "9화면. 은행 확인과 예금주 확인을 각각 독립 화면으로 나눴습니다. 실험 조건으로 씁니다."},
            {"key": "run2", "name": "재구성 Run 2", "path": "outputs/restructured_run2.html",
             "kind": "prototype", "screens": 7, "references": ["original"],
             "audit": "outputs/audit_run2.json", "flow": "tools/flows/run2.json",
             "desc": "7화면. 은행을 계좌 화면에, 예금주 확인을 금액 화면에 흡수했습니다."},
            {"key": "run3", "name": "재구성 Run 3", "path": "outputs/restructured_run3.html",
             "kind": "prototype", "screens": 8, "references": ["original"],
             "audit": "outputs/audit_run3.json", "flow": "tools/flows/run3.json",
             "desc": "8화면. 본인 확인을 확인 화면 위 모달로 옮겼습니다."},
            {"key": "auto", "name": "자동 생성본", "path": "outputs/restructured_auto.html",
             "kind": "prototype", "references": ["original"], "optional": True,
             "audit": "outputs/audit_auto.json",
             "desc": "run_restructure.py 가 마지막으로 만든 것. 아직 검사를 통과한 적이 없습니다."},
        ],
    },
    {
        "id": "audit",
        "name": "검사기",
        "note": "같은 과업으로 몰아 A~H 를 봅니다. 재구성본은 원본과 화면이 달라 일부 검사가 생략됩니다.",
        "tool": "tools/audit.py --flow tools/flows/<흐름>.json",
        "artefacts": [],   # 검사 결과는 각 산출물에 붙여 보여준다
    },
    {
        "id": "study",
        "name": "고령자 실험",
        "note": "원본과 Run 1 을 실제 고령 사용자에게. 검사기가 못 보는 것을 봅니다.",
        "tool": "tools/session_server.py → tools/session_report.py",
        "artefacts": [
            {"key": "sessions", "name": "세션 기록", "path": "sessions", "kind": "sessions",
             "desc": "피험자 x 조건 하나에 파일 하나. 저장소에는 올리지 않습니다."},
        ],
    },
]


# --------------------------------------------------------------------------- #
# 이 연구가 묻는 것과, 지금까지의 답
# --------------------------------------------------------------------------- #
# 대시보드 첫 화면은 파일 개수가 아니라 이것을 보여준다. 파일이 몇 개인지는
# 아무도 묻지 않았고, 아래 다섯 줄이 이 저장소가 존재하는 이유다.
#
# `evidence` 는 그 답을 뒷받침하는 값을 실제 audit 결과에서 끌어올 키다.
# `by_hand` 로 표시된 것은 측정 도구가 없어 손으로 센 값이며, 출처를 밝힌다.
QUESTIONS = [
    {"q": "규칙 기반으로 고령자 화면을 고칠 수 있는가",
     "a": "화면 안은 고치지만 구조는 못 바꾼다",
     "status": "answered",
     "detail": "저대비 텍스트는 66→56 으로 줄었지만 화면 수·구조는 그대로이고, "
               "죽은 컨트롤과 원본에 없던 alert() 가 생겼다.",
     "see": "repaired"},
    {"q": "LLM 재구성은 되는가",
     "a": "된다 — 구조를 바꾸고 검사도 통과했다",
     "status": "answered",
     "detail": "세 번 모두 fatal 0. 저대비 텍스트는 66→3.",
     "see": "run1"},
    {"q": "같은 프롬프트로 세 번 돌리면 같은 설계가 나오는가",
     "a": "아니다 — 9·7·8 화면으로 갈라진다",
     "status": "answered",
     "detail": "어디서 화면을 자를지가 매번 다르다. 돈이 나가기 전 명시적 확인이 "
               "3·1·3 회, 긴 경로 탭 수가 30·28·30 회. (손으로 셈 — docs/restructure-runs.md)",
     "see": "run2"},
    {"q": "검사기가 그 설계 차이를 잡아내는가",
     "a": "못 잡는다 — 셋이 완전히 같게 나온다",
     "status": "key",
     "detail": "화면 수가 다르고 확인 지점이 다른데도 fatal 0 / warning 0 으로 동일하다. "
               "갈라지는 것은 전부 검사기 밖의 지표다. 이것이 이 프로젝트의 핵심 발견이고, "
               "고령자 실험을 하는 이유다.",
     "see": "run3"},
    {"q": "그래서 실제 고령 사용자에게는 어떤가",
     "a": "아직 모른다",
     "status": "open",
     "detail": "원본과 Run 1 을 놓고 실험 중. 검사기가 못 보는 것을 사람이 보는지가 남은 질문이다.",
     "see": "sessions"},
]

# 나란히 놓고 봐야 하는 값들. Run 1·2·3 의 열이 똑같다는 것이 눈에 보여야 한다.
COMPARE_ROWS = [
    {"key": "low_contrast", "label": "저대비 텍스트", "from": "audit", "group": "seen"},
    {"key": "fatal", "label": "fatal", "from": "audit", "group": "seen"},
    {"key": "warning", "label": "warning", "from": "audit", "group": "seen"},
    {"key": "screens", "label": "화면 수", "from": "declared", "group": "unseen"},
    {"key": "taps", "label": "긴 경로 탭 수", "from": "by_hand", "group": "unseen"},
    {"key": "confirms", "label": "돈 나가기 전 확인", "from": "by_hand", "group": "unseen"},
]

GROUP_LABELS = {
    "seen": "검사기가 보는 값",
    "unseen": "검사기가 보지 않는 값",
}

# 측정 도구가 없어 손으로 센 값. docs/restructure-runs.md 의 표에서 옮겼다.
# 자동으로 재지 못하므로 빌드를 고치면 여기도 고쳐야 한다.
BY_HAND = {
    "run1": {"taps": 30, "confirms": 3},
    "run2": {"taps": 28, "confirms": 1},
    "run3": {"taps": 30, "confirms": 3},
}

CHECK_NAMES = {
    "A": "과업 완료·구조 보존", "B": "표시 정확성", "C": "죽은 컨트롤", "D": "대비",
    "E": "레이아웃", "F": "언어", "G": "상태 구분", "H": "미정의 클래스",
}


def _stat(rel):
    full = _p(rel.replace("/", os.sep))
    if not os.path.exists(full):
        return {"exists": False, "path": rel}
    if os.path.isdir(full):
        files = [f for f in os.listdir(full) if not f.startswith(".")]
        newest = max([os.path.getmtime(os.path.join(full, f)) for f in files], default=os.path.getmtime(full))
        return {"exists": bool(files), "empty_dir": not files, "path": rel, "is_dir": True,
                "count": len(files), "mtime": newest, "when": _when(newest)}
    m = os.path.getmtime(full)
    return {"exists": True, "path": rel, "is_dir": False, "size": os.path.getsize(full),
            "mtime": m, "when": _when(m)}


def _when(ts):
    return datetime.datetime.fromtimestamp(ts).strftime("%m/%d %H:%M")


def _audit_summary(rel):
    """The auditor's verdict, reduced to what a dashboard row needs."""
    full = _p(rel.replace("/", os.sep))
    if not os.path.exists(full):
        return {"exists": False, "path": rel}
    try:
        with io.open(full, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return {"exists": True, "path": rel, "error": str(e)}

    by_check = {}
    for sev in ("fatal", "warning"):
        for item in d.get(sev) or []:
            c = item.get("check") or "?"
            by_check.setdefault(c, {"fatal": 0, "warning": 0})[sev] += 1
    m = d.get("metrics") or {}
    return {
        "exists": True, "path": rel,
        "passed": bool(d.get("passed")),
        "fatal": len(d.get("fatal") or []),
        "warning": len(d.get("warning") or []),
        "by_check": by_check,
        "screens_reached": m.get("screens_reached"),
        "screens_expected": m.get("screens_expected"),
        "low_contrast_before": m.get("low_contrast_before"),
        "low_contrast_after": m.get("low_contrast_after"),
        "stood_down": m.get("checks_stood_down") or [],
        "flow": m.get("flow"),
        "when": _when(os.path.getmtime(full)),
        "mtime": os.path.getmtime(full),
        "fatal_items": [{"check": x.get("check"), "screen": x.get("screen"),
                         "detail": (x.get("detail") or "")[:300]}
                        for x in (d.get("fatal") or [])[:20]],
        "warning_items": [{"check": x.get("check"), "screen": x.get("screen"),
                           "detail": (x.get("detail") or "")[:300]}
                          for x in (d.get("warning") or [])[:40]],
    }


def state():
    out = {"root": ROOT, "generated": datetime.datetime.now().isoformat(timespec="seconds"),
           "stages": [], "check_names": CHECK_NAMES}
    times = {}

    # first pass: file facts, so derived_from can compare timestamps
    for stage in STAGES:
        for a in stage["artefacts"]:
            st = _stat(a["path"])
            times[a["key"]] = st.get("mtime")

    for stage in STAGES:
        s = {k: stage[k] for k in ("id", "name", "note") if k in stage}
        s["tool"] = stage.get("tool")
        s["artefacts"] = []
        for a in stage["artefacts"]:
            row = dict(a)
            row["file"] = _stat(a["path"])
            row["audit"] = _audit_summary(a["audit"]) if a.get("audit") else None
            row["flow_file"] = _stat(a["flow"]) if a.get("flow") else None

            # stale = the output predates something it was made from
            stale = []
            mine = row["file"].get("mtime")
            if mine:
                for src in a.get("derived_from") or []:
                    t = times.get(src)
                    if t and t > mine:
                        stale.append(src)
            row["stale_against"] = stale

            # an audit that predates the build it judged is out of date
            if row["audit"] and row["audit"].get("mtime") and mine:
                row["audit_stale"] = row["audit"]["mtime"] < mine
            else:
                row["audit_stale"] = False
            s["artefacts"].append(row)
        out["stages"].append(s)

    # sessions are their own thing: count participants, not bytes
    sess_dir = _p("sessions")
    files = sorted(f for f in os.listdir(sess_dir)) if os.path.isdir(sess_dir) else []
    files = [f for f in files if f.endswith(".json")]
    pids, conds = set(), {}
    for name in files:
        try:
            with io.open(os.path.join(sess_dir, name), encoding="utf-8") as f:
                d = json.load(f)
            pids.add(d.get("participant"))
            conds[d.get("condition")] = conds.get(d.get("condition"), 0) + 1
        except Exception:
            continue
    out["sessions"] = {"files": len(files), "participants": len(pids),
                       "by_condition": conds}

    # 첫 화면용. 파일 통계가 아니라 연구의 진행 상태를 낸다.
    idx = {a["key"]: a for st in out["stages"] for a in st["artefacts"]}

    def audit_of(key):
        a = idx.get(key) or {}
        au = a.get("audit")
        return au if (au and au.get("exists") and "error" not in au) else None

    # 나란히 비교할 열: 원본, 규칙기반, 재구성 3개
    cols = []
    for key, label in [("original", "원본"), ("repaired", "규칙 기반"),
                       ("run1", "Run 1"), ("run2", "Run 2"), ("run3", "Run 3")]:
        a = idx.get(key)
        if not a or not a["file"]["exists"]:
            continue
        au = audit_of(key)
        vals = {"screens": a.get("screens")}
        if key == "original":
            # 원본은 검사 대상이 아니라 기준선이다. 저대비 수치는 다른 빌드의
            # audit 이 기록한 "before" 값에서 가져온다.
            any_audit = next((audit_of(k) for k in ("repaired", "run1", "run2", "run3")
                              if audit_of(k)), None)
            vals["low_contrast"] = any_audit.get("low_contrast_before") if any_audit else None
            vals["fatal"] = None
            vals["warning"] = None
        elif au:
            vals["low_contrast"] = au.get("low_contrast_after")
            vals["fatal"] = au["fatal"]
            vals["warning"] = au["warning"]
        vals.update(BY_HAND.get(key, {}))
        cols.append({"key": key, "label": label, "values": vals})

    # 재구성 세 열이 실제로 같은지 확인한다. 같다는 것이 핵심 발견이므로
    # 문장으로 주장하지 않고 값에서 확인한 뒤 표시한다.
    runs = [c for c in cols if c["key"] in ("run1", "run2", "run3")]
    identical = []
    for row in COMPARE_ROWS:
        vs = [c["values"].get(row["key"]) for c in runs]
        if len(runs) > 1 and all(v is not None for v in vs) and len(set(vs)) == 1:
            identical.append(row["key"])

    differing = []
    for row in COMPARE_ROWS:
        vs = [c["values"].get(row["key"]) for c in runs]
        if len(runs) > 1 and all(v is not None for v in vs) and len(set(vs)) > 1:
            differing.append(row["key"])

    out["research"] = {
        "questions": QUESTIONS,
        "group_labels": GROUP_LABELS,
        "runs_differ_on": differing,
        "compare_rows": COMPARE_ROWS,
        "compare_cols": cols,
        "runs_identical_on": identical,
        "study": {"participants": len(pids), "target": "8~12",
                  "sessions": len(files), "deadline": "10/16"},
    }

    # 작업 위생 - 진짜 손봐야 하는 것만. 검사 실패는 여기 넣지 않는다.
    # 규칙 기반의 fatal 7 은 고칠 버그가 아니라 이 연구의 결과이기 때문이다.
    out["upkeep"] = {
        "stale": [a["name"] for st in out["stages"] for a in st["artefacts"]
                  if a.get("stale_against")],
        "audit_stale": [a["name"] for st in out["stages"] for a in st["artefacts"]
                        if a.get("audit_stale")],
        "unaudited": [a["name"] for st in out["stages"] for a in st["artefacts"]
                      if a.get("kind") == "prototype" and a["file"]["exists"]
                      and a.get("audit") and not a["audit"].get("exists")],
    }
    return out


def _text(s):
    lines = []
    for stage in s["stages"]:
        lines.append("")
        lines.append("== %s" % stage["name"])
        if stage.get("tool"):
            lines.append("   도구: %s" % stage["tool"])
        for a in stage["artefacts"]:
            f = a["file"]
            mark = "있음" if f["exists"] else "없음"
            extra = ""
            if f["exists"] and not f.get("is_dir"):
                extra = " · %s · %.0fKB" % (f["when"], f["size"] / 1024.0)
            elif f["exists"]:
                extra = " · %s · 파일 %d개" % (f["when"], f["count"])
            lines.append("   [%s] %-16s %s%s" % (mark, a["name"], a["path"], extra))
            if a.get("stale_against"):
                lines.append("        ! 입력(%s)보다 오래됨 - 다시 만들어야 할 수 있습니다"
                             % ", ".join(a["stale_against"]))
            au = a.get("audit")
            if au and au.get("exists") and "error" not in au:
                lines.append("        검사: %s  fatal %d / warning %d  (%s)"
                             % ("통과" if au["passed"] else "실패", au["fatal"],
                                au["warning"], au["when"]))
                if a.get("audit_stale"):
                    lines.append("        ! 검사 결과가 빌드보다 오래됨 - 다시 검사해야 합니다")
            elif au and not au.get("exists"):
                lines.append("        검사: 아직 없음 (%s)" % au["path"])
    se = s["sessions"]
    lines.append("")
    lines.append("== 실험 세션")
    lines.append("   피험자 %d명 · 파일 %d개 · %s"
                 % (se["participants"], se["files"],
                    ", ".join("%s %d" % kv for kv in se["by_condition"].items()) or "없음"))
    return "\n".join(lines)


def main():
    as_text = "--text" in sys.argv
    s = state()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if as_text:
        print(_text(s))
    else:
        json.dump(s, sys.stdout, ensure_ascii=False, indent=2)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
