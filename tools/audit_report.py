r"""Render one or more tools/audit.py reports as a side-by-side Markdown table.

audit.py writes JSON for a regenerate-on-failure loop; nobody can read three of
them next to each other. This takes any number of those files and prints:

  1. overview      - passed, fatal / warning counts, screens, low-contrast
                     before -> after, which flow drove the build
  2. per check A-H - fatal / warning per check per build, with a mark on any
                     check the audit stood down for that build
  3. key metrics   - the numbers behind each check (dead controls, overlaps,
                     new English words, ...)
  4. stood down    - what was skipped and why, per build
  5. findings      - with --details, every finding grouped by check (capped by
                     --max per check)

Usage:
  python tools/audit_report.py results/audit.json results/audit_restructured.json
  python tools/audit_report.py 규칙기반=results/audit.json Run1=results/audit_restructured.json \
      Run2=results/audit_run2.json Run3=results/audit_run3.json --details --out docs/audit-report.md

A bare path is labelled by its file name with the "audit_" prefix dropped, so
results/audit_run2.json becomes "run2".
"""
import argparse
import io
import json
import os
import sys

CHECKS = [
    ("A", "과업 완료 · 구조 보존"),
    ("B", "표시 정확성 · 주입된 대화상자"),
    ("C", "죽은 컨트롤"),
    ("D", "대비"),
    ("E", "레이아웃"),
    ("F", "언어 (새 영어)"),
    ("G", "상태 구분"),
    ("H", "미정의 클래스"),
    ("I", "선택지 보존"),
]
SEVERITY = {"A": "fatal", "B": "fatal", "C": "fatal",
            "D": "warning", "E": "warning", "F": "warning",
            "G": "warning", "H": "warning"}


def load(arg):
    """'label=path' or 'path' -> (label, report)."""
    if "=" in arg and not os.path.exists(arg):
        label, path = arg.split("=", 1)
    else:
        label, path = None, arg
    with io.open(path, encoding="utf-8") as f:
        rep = json.load(f)
    if not label:
        label = os.path.splitext(os.path.basename(path))[0]
        if label.startswith("audit_"):
            label = label[len("audit_"):]
        elif label == "audit":
            label = "audit"
    rep.setdefault("fatal", [])
    rep.setdefault("warning", [])
    rep.setdefault("metrics", {})
    return label, rep


def count_by_check(findings):
    out = {}
    for f in findings:
        out[f.get("check") or "?"] = out.get(f.get("check") or "?", 0) + 1
    return out


def stood_down_by_check(metrics):
    """checks_stood_down entries look like 'A/preservation (...)'. Map each to
    its check letter; anything without a letter prefix goes under '?'."""
    out = {}
    for s in metrics.get("checks_stood_down") or []:
        letter = s.split("/", 1)[0].strip() if "/" in s else "?"
        out.setdefault(letter, []).append(s)
    return out


def esc(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def table(header, rows):
    lines = ["| " + " | ".join(esc(h) for h in header) + " |",
             "|" + "|".join("---" for _ in header) + "|"]
    for r in rows:
        lines.append("| " + " | ".join(esc(c) for c in r) + " |")
    return "\n".join(lines)


def fmt_num(v, dash="–"):
    return dash if v is None else str(v)


def overview(builds):
    header = ["", *[l for l, _ in builds]]
    rows = []

    def row(name, fn):
        rows.append([name, *[fn(r) for _, r in builds]])

    row("통과", lambda r: "✓" if r.get("passed") else "✗")
    row("fatal", lambda r: len(r["fatal"]))
    row("warning", lambda r: len(r["warning"]))
    row("화면 수 (도달 / 흐름)", lambda r: "%s / %s" % (
        fmt_num(r["metrics"].get("screens_reached")),
        fmt_num(r["metrics"].get("screens_expected"))))
    row("data-screen 수", lambda r: fmt_num(r["metrics"].get("data-screen_repaired")))
    row("저대비 텍스트 (원본 → 빌드)", lambda r: "%s → %s" % (
        fmt_num(r["metrics"].get("low_contrast_before")),
        fmt_num(r["metrics"].get("low_contrast_after"))))
    row("완료 화면 금액", lambda r: fmt_num(r["metrics"].get("done_amount")))
    row("흐름 파일", lambda r: fmt_num(r["metrics"].get("flow")))
    row("원본에서 파생", lambda r: "예" if r["metrics"].get("derived_from_original", True) else "아니오 (새 설계)")
    row("생략된 검사", lambda r: len(r["metrics"].get("checks_stood_down") or []) or "없음")
    return table(header, rows)


def per_check(builds):
    header = ["검사", "내용", "심각도", *[l for l, _ in builds]]
    rows = []
    for letter, name in CHECKS:
        cells = []
        for _, r in builds:
            fat = count_by_check(r["fatal"]).get(letter, 0)
            warn = count_by_check(r["warning"]).get(letter, 0)
            down = stood_down_by_check(r["metrics"]).get(letter)
            if fat and warn:
                cell = "fatal %d · warning %d" % (fat, warn)
            elif fat:
                cell = "fatal %d" % fat
            elif warn:
                cell = "warning %d" % warn
            else:
                cell = "0"
            if down:
                cell += " △"
            cells.append(cell)
        rows.append([letter, name, SEVERITY[letter], *cells])
    note = "△ = 이 빌드에서 해당 검사의 일부가 생략됨 (아래 '생략된 검사' 참고)"
    return table(header, rows) + "\n\n" + note


def key_metrics(builds):
    header = ["검사", "지표", *[l for l, _ in builds]]
    rows = []

    def m(letter, name, key, fn=None):
        cells = []
        for _, r in builds:
            v = r["metrics"].get(key)
            cells.append(fn(v) if fn else fmt_num(v))
        rows.append([letter, name, *cells])

    def count_or_list(v):
        if v is None:
            return "–"
        if isinstance(v, list):
            return "0" if not v else "%d (%s)" % (len(v), ", ".join(map(str, v[:6])) + (" …" if len(v) > 6 else ""))
        if isinstance(v, dict):
            return "0" if not v else "%d (%s)" % (len(v), ", ".join(map(str, list(v)[:6])))
        return str(v)

    rows.append(["A", "data-action 수 (원본 → 빌드)",
                 *["%s → %s" % (fmt_num(r["metrics"].get("data-action_original")),
                                fmt_num(r["metrics"].get("data-action_repaired")))
                   for _, r in builds]])
    rows.append(["A", "id 수 (원본 → 빌드)",
                 *["%s → %s" % (fmt_num(r["metrics"].get("id_original")),
                                fmt_num(r["metrics"].get("id_repaired")))
                   for _, r in builds]])
    m("A", "화면별로 사라진 속성", "per_screen_attr_loss", count_or_list)
    m("B", "주입된 alert/confirm/prompt", "injected_dialog_calls")
    m("B", "추가된 onclick", "onclick_added")
    m("B", "과업 중 뜬 대화상자", "dialogs_during_task")
    m("C", "처리기 없는 data-action (새로)", "dead_controls_new")
    m("C", "원래부터 죽어 있던 것", "dead_controls_pre_existing", count_or_list)
    m("D", "색을 상속에만 의존하는 새 텍스트", "new_inherited_colour")
    m("D", "저대비 요소에 글이 늘어남", "low_contrast_gained_text")
    m("E", "새 겹침", "overlaps_new")
    m("E", "새 넘침", "overflows_new")
    m("E", "새로 줄바꿈된 텍스트", "newly_wrapped_text")
    m("E", "원본보다 1.5배 이상 길어진 화면", "screens_much_taller")
    m("F", "새 영어 단어 (화면에 보임)", "new_english_words", count_or_list)
    m("F", "새 영어 단어 (마크업에만)", "new_english_words_markup_only", count_or_list)
    rows.append(["G", "무너진 상태 쌍 / 검사한 쌍",
                 *["%s / %s" % (fmt_num(r["metrics"].get("state_pairs_collapsed")),
                                fmt_num(r["metrics"].get("state_pairs_checked")))
                   for _, r in builds]])
    m("H", "정의 안 된 클래스", "undefined_classes_new", count_or_list)
    return table(header, rows)


def stood_down(builds):
    out = []
    any_ = False
    for label, r in builds:
        items = r["metrics"].get("checks_stood_down") or []
        if not items:
            continue
        any_ = True
        out.append("**%s**" % esc(label))
        for s in items:
            out.append("- " + esc(s))
        out.append("")
    if not any_:
        return "생략된 검사 없음."
    return "\n".join(out).rstrip()


def details(builds, cap):
    out = []
    for label, r in builds:
        out.append("### %s" % esc(label))
        if not r["fatal"] and not r["warning"]:
            out.append("발견 없음.\n")
            continue
        for letter, name in CHECKS:
            for sev, lst in (("fatal", r["fatal"]), ("warning", r["warning"])):
                hits = [f for f in lst if f.get("check") == letter]
                if not hits:
                    continue
                out.append("**%s · %s — %s %d건**" % (letter, name, sev, len(hits)))
                for f in hits[:cap]:
                    scr = f.get("screen")
                    out.append("- %s%s" % ("`%s` " % scr if scr else "", esc(f.get("detail", ""))))
                if len(hits) > cap:
                    out.append("- … 외 %d건" % (len(hits) - cap))
                out.append("")
        others = [f for f in r["fatal"] + r["warning"]
                  if f.get("check") not in dict(CHECKS)]
        if others:
            out.append("**기타**")
            for f in others[:cap]:
                out.append("- " + esc(f.get("detail", "")))
            out.append("")
    return "\n".join(out).rstrip()


def render(builds, want_details, cap, title):
    parts = ["# %s" % title, ""]
    parts += ["## 개요", "", overview(builds), ""]
    parts += ["## 검사 항목별 (A~H)", "", per_check(builds), ""]
    parts += ["## 핵심 지표", "", key_metrics(builds), ""]
    parts += ["## 생략된 검사", "", stood_down(builds), ""]
    if want_details:
        parts += ["## 발견 목록", "", details(builds, cap), ""]
    inputs = ["- %s: `%s`" % (esc(l), esc(r.get("inputs", {}).get("repaired", "?")))
              for l, r in builds]
    parts += ["## 입력", ""] + inputs + [""]
    return "\n".join(parts)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("reports", nargs="+", help="audit JSON, or label=path")
    ap.add_argument("--details", action="store_true", help="list every finding by check")
    ap.add_argument("--max", type=int, default=10, help="findings shown per check (with --details)")
    ap.add_argument("--title", default="audit 비교")
    ap.add_argument("--out", help="write Markdown here as well as stdout")
    args = ap.parse_args()

    builds = [load(a) for a in args.reports]
    md = render(builds, args.details, args.max, args.title)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with io.open(args.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(md)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
