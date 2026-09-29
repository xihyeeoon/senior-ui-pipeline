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

    # 첫 화면용 요약. 이 프로젝트가 지금까지 알아낸 것을 숫자로 줄인 것.
    protos = [a for st in out["stages"] for a in st["artefacts"]
              if a.get("kind") == "prototype" and a["file"]["exists"]]
    audited = [a for a in protos if a.get("audit") and a["audit"].get("exists")
               and "error" not in a["audit"]]
    out["summary"] = {
        "prototypes": len(protos),
        "audited": len(audited),
        "passing": len([a for a in audited if a["audit"]["passed"]]),
        "failing": [{"name": a["name"], "fatal": a["audit"]["fatal"]}
                    for a in audited if not a["audit"]["passed"]],
        "unaudited": [a["name"] for a in protos
                      if not (a.get("audit") and a["audit"].get("exists"))],
        "stale": [a["name"] for st in out["stages"] for a in st["artefacts"]
                  if a.get("stale_against")],
        "audit_stale": [a["name"] for st in out["stages"] for a in st["artefacts"]
                        if a.get("audit_stale")],
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
