r"""Scan what the pipeline has produced and write outputs/index.json for the viewer.

web/dashboard.html reads this one file instead of guessing at paths.
Nothing here defines a new format: every field is lifted out of files the
pipeline already writes.

  outputs/audit*.json              the verdicts - and, via their `inputs` block,
                                   which build and which flow each one judged
  outputs/*.html                   the builds themselves
  flows/*.json                     screen order
  outputs/shots/**/*.png           per-screen screenshots
  docs/restructure-changelog.md    the 37 changes
  kb/senior_kb.csv                 the 46 rules, to mark which were cited
  inputs/original_transfer.html    the baseline

Builds are discovered, not listed. An audit JSON records the URL of the build it
drove, so a new build with its own audit appears here without editing anything.
NAMES below only prettifies labels; an unknown build still shows up, named after
its file.

inputs/*.png (the real SOL captures) are never indexed - they show a real name.

Usage:
  python -m senior_ui.viewer.build_index                  -> outputs/index.json
  python -m senior_ui.viewer.build_index --out somewhere.json
  python -m senior_ui.viewer.build_index --print          -> stdout summary
"""
import argparse
import csv
import datetime
import io
import json
import os
import re
import sys

from senior_ui._cli import setup_stdout
from senior_ui.config import CONDITIONS, ROOT
from senior_ui.config import FLOWS_DIR as FLOWS
from senior_ui.config import OUTPUTS_DIR as OUTPUTS

SHOTS = os.path.join(OUTPUTS, "shots")

# Nicer labels for builds we happen to know. Anything missing falls back to the
# file name, so a new build still appears.
NAMES = {
    "restructured_transfer": "재구성 Run 1",
    "restructured_run2": "재구성 Run 2",
    "restructured_run3": "재구성 Run 3",
    "restructured_auto": "자동 생성본",
    "original_transfer": "원본",
}
ORDER = ["restructured_transfer", "restructured_run2",
         "restructured_run3", "restructured_auto"]


# --------------------------------------------------------------------------- #
# 두 개의 층
# --------------------------------------------------------------------------- #
#   파이프라인   캡처 → LLM 재구성 → 검사기 → (스타일 이식) → 실험
#                senior_kb.csv 는 여기 쓰이지 않는다. 재구성본의 변경을 규칙
#                id 에 대응시키는 사후 대조에만 쓴다.
#   실험 조건    원본 vs 재구성본 둘.
#
# 규칙 기반 수리본은 2026-09-30 에 연구에서 빠졌다. 파일도 산출물도 더는 없으므로
# 이름으로 걸러낼 것이 없다.
PIPELINE = [
    {"id": "capture", "name": "캡처", "note": "신한 SOL 화면을 8화면 시제품으로",
     "artifact": "inputs/original_transfer.html"},
    {"id": "restructure", "name": "LLM 재구성", "note": "과업의 어려움을 보고 구조를 다시 설계",
     "artifact": "outputs/restructured_*.html"},
    {"id": "audit", "name": "검사기", "note": "와이어프레임은 A·B·C·F·I, 스타일 이식 후 A~I",
     "artifact": "senior_ui/audit/stage.py"},
    {"id": "style", "name": "스타일 이식", "note": "시각 디테일을 채운다 — 아직",
     "artifact": None},
    {"id": "study", "name": "실험", "note": "원본 vs 재구성본, 고령 사용자",
     "artifact": "senior_ui/experiment/server.py"},
]

BANNER = "현재 파이프라인은 LLM 직접 재구성만 사용합니다."

KB_NOTE = ("senior_kb.csv 대조는 사후 확인입니다. 생성에 규칙을 사용하지 않았습니다.")

CHECK_NAMES = {
    "A": "과업 완료·구조 보존", "B": "표시 정확성", "C": "죽은 컨트롤", "D": "대비",
    "E": "레이아웃", "F": "언어", "G": "상태 구분", "H": "미정의 클래스",
    "I": "선택지 보존",
}


def rel(path):
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def read_json(path):
    try:
        with io.open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def when(ts):
    return datetime.datetime.fromtimestamp(ts).strftime("%m/%d %H:%M") if ts else None


# --------------------------------------------------------------------------- #
# builds
# --------------------------------------------------------------------------- #
def url_to_rel(u):
    """An audit records the build as a URL served from the project root."""
    if not u:
        return None
    m = re.sub(r"^https?://[^/]+/", "", u)
    return m if m and not m.startswith("http") else None


def screens_of(html_path):
    """Screen ids in document order, straight from the markup."""
    try:
        with io.open(html_path, encoding="utf-8") as f:
            src = f.read()
    except OSError:
        return []
    seen, out = set(), []
    for name in re.findall(r'data-screen="([a-z0-9_-]+)"', src):
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def shot_dirs():
    """Every directory under outputs/shots that holds png, plus the root."""
    dirs = {}
    if not os.path.isdir(SHOTS):
        return dirs
    for base, _, files in os.walk(SHOTS):
        pngs = [f for f in files if f.lower().endswith(".png")]
        if pngs:
            dirs[rel(base)] = sorted(pngs)
    return dirs


SHOT_PATTERNS = [
    re.compile(r"^audit_(?P<screen>[a-z0-9_-]+)\.png$", re.I),
    re.compile(r"^after_(?P<screen>[a-z0-9_-]+)\.png$", re.I),
    re.compile(r"^before_(?P<screen>[a-z0-9_-]+)\.png$", re.I),
]


def match_shots(dirs, flow_name, build_id, want_prefix=None):
    """Screenshots for one build, keyed by screen name.

    Directories are matched by flow name (outputs/shots/run2 for the run2 flow),
    then by build id. The flat before_*.png files in outputs/shots are the
    original's screens. Nothing is hardcoded per build beyond that naming
    convention.
    """
    candidates = []
    for d in dirs:
        leaf = d.rsplit("/", 1)[-1]
        if flow_name and leaf == flow_name:
            candidates.append(d)
        elif leaf == build_id:
            candidates.append(d)

    out = {}
    for d in candidates:
        for f in dirs[d]:
            for pat in SHOT_PATTERNS:
                m = pat.match(f)
                if m:
                    out.setdefault(m.group("screen"), d + "/" + f)
                    break
    if out:
        return out
    # fall back to the flat before_/after_ files
    root = rel(SHOTS)
    if want_prefix and root in dirs:
        for f in dirs[root]:
            m = re.match(r"^%s_(?P<screen>[a-z0-9_-]+)\.png$" % want_prefix, f, re.I)
            if m:
                out[m.group("screen")] = root + "/" + f
    return out


def audit_digest(d, path):
    """Everything the viewer needs from one audit report."""
    by_check = {}
    for sev in ("fatal", "warning"):
        for item in d.get(sev) or []:
            c = item.get("check") or "?"
            by_check.setdefault(c, {"fatal": 0, "warning": 0})[sev] += 1
    m = d.get("metrics") or {}
    stood = {}
    for s in m.get("checks_stood_down") or []:
        letter = s.split("/", 1)[0].strip() if "/" in s else "?"
        stood.setdefault(letter, []).append(s)

    def items(sev):
        return [{"check": x.get("check"), "screen": x.get("screen"),
                 "detail": x.get("detail") or ""}
                for x in (d.get(sev) or [])]

    return {
        "path": rel(path), "when": when(mtime(path)), "mtime": mtime(path),
        "passed": bool(d.get("passed")),
        "fatal": len(d.get("fatal") or []), "warning": len(d.get("warning") or []),
        "by_check": by_check, "stood_down": stood,
        "findings": {"fatal": items("fatal"), "warning": items("warning")},
        "metrics": m,
    }


def flow_path_of(flow_raw):
    """audit JSON 이 적어 둔 흐름 파일을 지금 레이아웃에서 찾는다.

    results/ 의 옛 JSON 에는 "tools/flows/run2.json" 같은 이동 전 경로가 그대로
    들어 있다. 그것들은 증거 파일이므로 고치지 않는다 - 대신 읽는 쪽이 옛 경로도
    알아보게 한다. 경로가 그 자리에 없으면 파일 이름만 떼어 flows/ 에서 찾는다.
    """
    if not flow_raw or flow_raw.startswith("("):
        return None
    f = flow_raw.replace("\\", "/")
    if ROOT.replace("\\", "/") in f:
        f = rel(os.path.normpath(flow_raw))
    if os.path.exists(os.path.join(ROOT, f)):
        return f
    name = f.rsplit("/", 1)[-1]
    return "flows/" + name if os.path.exists(os.path.join(FLOWS, name)) else None


def audited_builds():
    """outputs/ 의 audit*.json 을 훑어 (파일 이름, 경로, 리포트, 빌드 경로) 를 낸다.

    빌드는 목록이 아니라 발견된다. audit JSON 이 자기가 검사한 빌드의 URL 을
    적어 두므로, 새 빌드에 audit 이 하나 생기면 아무것도 고치지 않아도 여기
    나타난다. 그 빌드가 더 이상 없으면(옛 레이아웃) 건너뛴다."""
    for name in sorted(os.listdir(OUTPUTS)) if os.path.isdir(OUTPUTS) else []:
        if not (name.startswith("audit") and name.endswith(".json")):
            continue
        path = os.path.join(OUTPUTS, name)
        d = read_json(path)
        if not d or "metrics" not in d:
            continue
        build_rel = url_to_rel((d.get("inputs") or {}).get("repaired"))
        if not build_rel or not os.path.exists(os.path.join(ROOT, build_rel)):
            continue      # audit of a build that no longer exists (old layout)
        yield name, path, d, build_rel


def merge_audit(prev, name, path, d):
    """같은 빌드의 audit 를 이미 본 적이 있을 때 둘을 어떻게 둘지 정한다.

    돌려주는 것은 새 기록의 other_audits 에 들어갈 목록, 또는 None - None 이면
    이번 audit 을 버리고 이미 있는 기록을 그대로 둔다.

    The audit CLI writes both --out and a stdout copy; the stdout one is a duplicate
    and never interesting. 같은 빌드를 다른 흐름으로 검사한 것이면 둘 다
    남긴다. 조건을 바꾸면 결과가 어떻게 달라지는지가 이 프로젝트에서 가장 알고
    싶은 것이다."""
    if "_stdout" in name:
        return None
    newer = (mtime(path) or 0) > (prev["audit"]["mtime"] or 0)
    prev_flow = (prev["audit"].get("metrics") or {}).get("flow")
    this_flow = (d.get("metrics") or {}).get("flow")
    if prev_flow == this_flow:
        return prev.get("other_audits", []) if newer else None
    if newer:
        prev.setdefault("other_audits", []).insert(
            0, dict(prev["audit"], flow=prev_flow))
        return prev.pop("other_audits")
    prev.setdefault("other_audits", []).append(
        dict(audit_digest(d, path), flow=this_flow))
    return None


def pair_screens(build_rel, flow_rel, flow_name, dirs):
    """화면과 그 화면의 스크린샷을 짝지어 둔다. 화면 이름은 마크업 순서,
    스크린샷은 흐름 이름이나 빌드 id 로 찾은 폴더에서 온다."""
    stem = os.path.splitext(os.path.basename(build_rel))[0]
    return {
        "flow": {"name": flow_name, "path": flow_rel,
                 "steps": (read_json(os.path.join(ROOT, flow_rel)) or {}).get("steps")
                          if flow_rel else None},
        "screens": screens_of(os.path.join(ROOT, build_rel)),
        "shots": match_shots(dirs, flow_name, stem),
    }


def plan_of(build_rel):
    """빌드 옆에 재구성 루프가 남긴 진단·계획이 있으면 그것. 없으면 None.

    루프는 통과한 빌드를 restructured_auto.html 로 올리면서 그 계획을
    restructured_auto.plan.json 으로, 진단을 .diagnosis.json 으로, 설명서를
    .designer_brief.md 로 함께 올린다 (restructure/loop.py 의 PROMOTED). 손으로
    만든 Run 1~3 에는 이것이 없고, 그 변경 기록은 changelog 에 있다.
    """
    stem = os.path.splitext(os.path.join(ROOT, build_rel))[0]
    plan_path = stem + ".plan.json"
    if not os.path.exists(plan_path):
        return None

    def load(p):
        return json.load(io.open(p, encoding="utf-8")) if os.path.exists(p) else None
    brief = stem + ".designer_brief.md"
    return {"path": rel(plan_path), "plan": load(plan_path),
            "diagnosis": load(stem + ".diagnosis.json") or [],
            "brief": rel(brief) if os.path.exists(brief) else None}


def build_row(build_rel, path, d, dirs, alts):
    """색인에 들어갈 빌드 한 줄."""
    flow_rel = flow_path_of((d.get("inputs") or {}).get("flow") or "")
    flow_name = (d.get("metrics") or {}).get("flow") or (
        os.path.splitext(os.path.basename(flow_rel))[0] if flow_rel else None)
    stem = os.path.splitext(os.path.basename(build_rel))[0]
    return {
        "id": stem,
        "name": NAMES.get(stem, stem),
        "layer": "pipeline",
        "layer_note": None,
        "html": build_rel,
        "when": when(mtime(os.path.join(ROOT, build_rel))),
        "audit": audit_digest(d, path),
        **pair_screens(build_rel, flow_rel, flow_name, dirs),
        # 같은 빌드를 다른 조건으로 검사한 것들
        "other_audits": alts,
        # 재구성 루프가 남긴 진단·계획 ("변경 추적" 탭이 보인다)
        "plan": plan_of(build_rel),
        # 자동 루프가 쌓을 시도 이력이 들어올 자리. 지금은 늘 비어 있다.
        "attempts": [],
    }


def collect_builds():
    dirs = shot_dirs()
    found = {}          # build rel path -> record
    for name, path, d, build_rel in audited_builds():
        prev = found.get(build_rel)
        if prev is None:
            alts = []
        else:
            alts = merge_audit(prev, name, path, d)
            if alts is None:
                continue
        found[build_rel] = build_row(build_rel, path, d, dirs, alts)

    builds = list(found.values())
    builds.sort(key=lambda b: (ORDER.index(b["id"]) if b["id"] in ORDER else 99, b["id"]))
    return builds, dirs


def study_conditions():
    """실험에 실제로 쓰는 두 조건. 정의는 senior_ui/config.py 한 곳에만 있다 -
    두 곳에 적으면 언젠가 어긋난다."""
    return [{"key": c["key"], "label": c["label"],
             "build": c["url"].lstrip("/")} for c in CONDITIONS]


def collect_baseline(dirs):
    path = os.path.join(ROOT, "inputs", "original_transfer.html")
    if not os.path.exists(path):
        return None
    return {
        "id": "original_transfer", "name": NAMES["original_transfer"],
        "layer": "input", "layer_note": "모든 갈래가 여기서 출발합니다.",
        "html": rel(path), "when": when(mtime(path)),
        "screens": screens_of(path),
        "shots": match_shots(dirs, None, "original_transfer", want_prefix="before"),
        "audit": None, "flow": {"name": "original", "path": "flows/original.json"},
        "attempts": [],
    }


# --------------------------------------------------------------------------- #
# changelog + KB
# --------------------------------------------------------------------------- #
RULE_RE = re.compile(r"\b((?:SDF|KS)-)?(G\d+-\d+|\d+)\b")


def parse_rules(cell):
    """The changelog abbreviates: 'SDF-G2-1, G2-2, G10-3' means all three are
    SDF. The prefix carries over until another one appears. 'KS-2, G4-4' is
    KS-2 then SDF-G4-4, since G-numbers only exist under SDF."""
    out, prefix = [], None
    if not cell or re.search(r"해당\s*없음|없음(?!\s*\()", cell):
        # "해당 없음" means no rule covers this change - that is a finding,
        # not a gap in parsing.
        if not re.search(r"(SDF|KS)-", cell or ""):
            return []
    for m in RULE_RE.finditer(cell or ""):
        pre, body = m.group(1), m.group(2)
        if pre:
            prefix = pre
        if body.startswith("G"):
            # G 번호는 SDF 에만 있다. 'SDF-G6-4, KS-5, G9-4' 에서 마지막 G9-4 가
            # 앞의 KS- 에 물들면 존재하지 않는 KS-G9-4 가 된다.
            out.append("SDF-" + body)
        elif prefix == "KS-":
            out.append("KS-" + body)
    seen, uniq = set(), []
    for r in out:
        if r not in seen:
            seen.add(r)
            uniq.append(r)
    return uniq


def strip_md(s):
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"`(.+?)`", r"\1", s)
    return s.strip()


def parse_changelog():
    path = os.path.join(ROOT, "docs", "restructure-changelog.md")
    if not os.path.exists(path):
        return []
    with io.open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    changes, section = [], None
    for line in lines:
        h = re.match(r"^##\s+(.*)", line)
        if h:
            section = strip_md(h.group(1))
            continue
        if not line.startswith("|") or re.match(r"^\|[\s:-]+\|", line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cells or cells[0] in ("#", "원본", "지표"):
            continue
        # 5 columns: # | 원본 | 재구성 | 왜 | 규칙
        # 3 columns: 원본 | 재구성 | 규칙   (the wording section)
        if len(cells) == 5 and re.match(r"^\d+$", cells[0]):
            num, before, after, why, rules = cells
            num = int(num)
        elif len(cells) == 3:
            # 용어 절은 원문에 번호가 없다. n=None 으로 두어 표시할 때 구분된다.
            num, before, after, why, rules = None, cells[0], cells[1], "", cells[2]
        else:
            continue
        ids = parse_rules(rules)
        raw = strip_md(rules)
        partial = bool(re.search(r"부분|경계선", raw)) or (
            bool(ids) and bool(re.search(r"없음", raw)))
        changes.append({
            "partial": partial,
            "n": num,
            "section": section,
            "before": strip_md(before), "after": strip_md(after),
            "why": strip_md(why),
            "rules": ids, "rules_raw": raw,
            "uncovered": not ids,
        })
    # 번호 없는 항목(용어 절)은 번호를 붙이지 않고 그대로 둔다.
    return changes


def parse_claims():
    """The changelog's own verdict on coverage, kept separate from what the
    tables actually cite. The document grades its own output, so the two
    numbers differ (33 claimed vs 26 cited) - the viewer shows both."""
    path = os.path.join(ROOT, "docs", "restructure-changelog.md")
    if not os.path.exists(path):
        return {"met": [], "not_met": []}
    with io.open(path, encoding="utf-8") as f:
        text = f.read()

    met = []
    m = re.search(r"결과적으로 충족된 것\*\*\s*[—-]\s*(.+?)\s*[—-]\s*\*\*\d+개",
                  text, re.S)
    if m:
        met = parse_rules(" ".join(m.group(1).splitlines()))

    not_met = []
    sec = re.search(r"\*\*충족하지 못한 것\*\*(.*?)(?:\n## |\Z)", text, re.S)
    if sec:
        for line in sec.group(1).splitlines():
            if not line.startswith("|") or re.match(r"^\|[\s:-]+\|", line):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) != 2 or cells[0] == "규칙":
                continue
            ids = parse_rules(cells[0])
            state = strip_md(cells[1])
            label = re.match(r"^([^.]+)\.", state)
            for rid in ids:
                not_met.append({"id": rid,
                                "state": label.group(1) if label else "미충족",
                                "why": state})
    return {"met": met, "not_met": not_met}


def parse_kb(changes, claims):
    path = os.path.join(ROOT, "kb", "senior_kb.csv")
    if not os.path.exists(path):
        return []
    cited, partial = {}, set()
    for c in changes:
        for r in c["rules"]:
            cited.setdefault(r, []).append(c["n"])
            if c.get("partial"):
                partial.add(r)
    claimed = set(claims.get("met") or [])
    shortfall = {x["id"]: x for x in claims.get("not_met") or []}
    rules = []
    with io.open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rid = (row.get("relation") or "").strip()
            if not rid:
                continue
            rules.append({
                "id": rid,
                "aspect": (row.get("system_design_aspect") or "").strip(),
                "property": (row.get("property") or "").strip(),
                "constraint": (row.get("constraint") or "").strip(),
                "content": (row.get("content") or "").strip(),
                "cited_by": cited.get(rid, []),
                "cited_partially": rid in partial,
                "claimed_met": rid in claimed,
                "shortfall": shortfall.get(rid),
            })
    return rules


# --------------------------------------------------------------------------- #
def build():
    builds, dirs = collect_builds()
    baseline = collect_baseline(dirs)
    changes = parse_changelog()
    claims = parse_claims()
    rules = parse_kb(changes, claims)
    conds = study_conditions()
    in_study = {c["build"] for c in conds}
    for b in ([baseline] if baseline else []) + builds:
        b["in_study"] = b["html"] in in_study

    return {
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "check_names": CHECK_NAMES,
        "pipeline": PIPELINE,
        "banner": BANNER,
        "kb_note": KB_NOTE,
        "study_conditions": conds,
        "baseline": baseline,
        "builds": builds,
        "changes": changes,
        "rules": rules,
        "claims": claims,
        "shot_dirs": dirs,
    }


def main():
    # 무엇이든 찍기 전에 맞춘다 (senior_ui/_cli.py).
    setup_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(OUTPUTS, "index.json"))
    ap.add_argument("--print", dest="show", action="store_true")
    args = ap.parse_args()

    idx = build()
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with io.open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(idx, f, ensure_ascii=False, indent=1)

    print("빌드 %d개, 변경 %d건, 규칙 %d개 -> %s"
          % (len(idx["builds"]), len(idx["changes"]), len(idx["rules"]), rel(args.out)))
    if args.show:
        for b in idx["builds"]:
            a = b["audit"]
            print("  %-22s %-26s fatal %-3d warning %-3d 화면 %-2d 샷 %d"
                  % (b["name"], b["html"], a["fatal"], a["warning"],
                     len(b["screens"]), len(b["shots"])))
        un = [c for c in idx["changes"] if c["uncovered"]]
        print("  규칙 없는 변경 %d건, 인용된 규칙 %d/%d"
              % (len(un), len([r for r in idx["rules"] if r["cited_by"]]), len(idx["rules"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
