r"""Turn the saved participant sessions into a readable comparison.

senior_ui.experiment.server writes one JSON per participant x condition. This reads
them all and prints, as Markdown:

  1. 진행 현황  - who has done what, and what is still missing
  2. 피험자별   - one row per participant per condition
  3. 조건 비교  - the two conditions side by side (median, mean, range)
  4. 화면별 체류 - where the time actually went, per condition
  5. 막힌 지점   - screens with the most misses / backs / deletes

The median is the headline: with 8-12 participants one very slow session moves
the mean a lot, and in this population that session is common.

No inferential statistics here on purpose. n is small, the design is
within-subject, and picking a test is the researcher's call - the per-session
numbers are all present so any test can be run elsewhere. --csv writes a tidy
one-row-per-session file for exactly that.

Usage:
  python -m senior_ui.experiment.report
  python -m senior_ui.experiment.report --sessions sessions --out results/session-report.md
  python -m senior_ui.experiment.report --csv results/sessions.csv
"""
import argparse
import csv
import io
import json
import os
import statistics as st
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

# (key in metrics, 표시 이름, 단위, 낮을수록 좋은가)
MEASURES = [
    ("seconds", "걸린 시간", "초", True),
    ("taps", "누른 횟수", "회", True),
    ("misses", "빗나간 탭", "회", True),
    ("backs", "되돌아가기", "회", True),
    ("deletes", "지우기", "회", True),
    ("unique_screens", "거친 화면", "개", None),   # 우열 판정 없음
]


def load(sessions_dir):
    rows = []
    if not os.path.isdir(sessions_dir):
        return rows
    for name in sorted(os.listdir(sessions_dir)):
        if not name.endswith(".json"):
            continue
        with io.open(os.path.join(sessions_dir, name), encoding="utf-8") as f:
            try:
                d = json.load(f)
            except json.JSONDecodeError as e:
                sys.stderr.write("건너뜀 (JSON 오류) %s: %s\n" % (name, e))
                continue
        d["_file"] = name
        rows.append(d)
    return rows


def esc(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def table(header, body):
    out = ["| " + " | ".join(esc(h) for h in header) + " |",
           "|" + "|".join("---" for _ in header) + "|"]
    for r in body:
        out.append("| " + " | ".join(esc(c) for c in r) + " |")
    return "\n".join(out)


def fmt(v, unit):
    if v is None:
        return "–"
    if unit == "초":
        return "%.1f" % v
    return "%g" % v


def progress(rows, conditions):
    pids = sorted({r["participant"] for r in rows})
    body = []
    for pid in pids:
        mine = [r for r in rows if r["participant"] == pid]
        cells, done = [], 0
        for c in conditions:
            hit = next((r for r in mine if r["condition"] == c), None)
            if hit is None:
                cells.append("–")
            else:
                cells.append("완료" if hit.get("completed") else "중단")
                done += 1
        order = " → ".join(r["condition"] for r in sorted(mine, key=lambda r: r.get("order_index", 0)))
        body.append([pid, *cells, order, "○" if done == len(conditions) else "미완"])
    return table(["피험자", *conditions, "순서", "전부"], body)


def per_session(rows):
    body = []
    for r in sorted(rows, key=lambda r: (r["participant"], r.get("order_index", 0))):
        m = r.get("metrics") or {}
        body.append([
            r["participant"], r["condition"], (r.get("order_index", 0) + 1),
            "완료" if r.get("completed") else "중단",
            "%.1f" % m.get("seconds", 0), m.get("taps", "–"), m.get("misses", "–"),
            m.get("backs", "–"), m.get("deletes", "–"),
        ])
    return table(["피험자", "조건", "순서", "결과", "시간(초)", "탭", "빗나감", "되돌아", "지우기"], body)


def summarise(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return None, None, None, None, 0
    return (st.median(vals), st.mean(vals), min(vals), max(vals), len(vals))


def compare(rows, conditions, completed_only):
    used = [r for r in rows if (not completed_only or r.get("completed"))]
    body = []

    # 완료율이 머리에 온다. 나머지 지표는 "끝낸 사람" 안에서의 차이일 뿐이고,
    # 끝내지 못한 것이야말로 이 연구가 묻는 실패다.
    rates = {}
    cells = []
    for c in conditions:
        mine = [r for r in rows if r["condition"] == c]
        done = [r for r in mine if r.get("completed")]
        rates[c] = (len(done) / len(mine) * 100) if mine else None
        cells.append("–" if not mine else "%d/%d (%.0f%%)" % (len(done), len(mine), rates[c]))
    gap = "–"
    if len(conditions) == 2 and all(rates.get(c) is not None for c in conditions):
        d = rates[conditions[1]] - rates[conditions[0]]
        gap = "=" if d == 0 else ("%s%.0f%%p%s" % ("+" if d > 0 else "", d,
                                                   " 유리" if d > 0 else " 불리"))
    body.append(["**과업 완료**", "명", *cells, gap])
    for key, label, unit, lower_better in MEASURES:
        cells = []
        meds = {}
        for c in conditions:
            vals = [(r.get("metrics") or {}).get(key) for r in used if r["condition"] == c]
            med, mean, lo, hi, n = summarise(vals)
            meds[c] = med
            cells.append("–" if med is None else
                         "%s / %s / %s~%s (n=%d)" % (fmt(med, unit), fmt(mean, unit),
                                                     fmt(lo, unit), fmt(hi, unit), n))
        diff = "–"
        if all(meds.get(c) is not None for c in conditions) and len(conditions) == 2:
            a, b = meds[conditions[0]], meds[conditions[1]]
            d = b - a
            if a:
                pct = d / a * 100
                arrow = "↓" if d < 0 else ("↑" if d > 0 else "=")
                verdict = ""
                if lower_better is not None and d != 0:
                    verdict = " 유리" if (d < 0) == lower_better else " 불리"
                diff = "%s %s%.0f%%%s" % (arrow, "+" if d > 0 else "", pct, verdict)
        body.append([label, unit, *cells, diff])
    head = ["지표", "단위", *["%s\n중앙값/평균/범위" % c for c in conditions],
            "%s 대비" % conditions[0]]
    return table(head, body)


def dwell(rows, conditions):
    body, seen = [], []
    per = {c: {} for c in conditions}
    for r in rows:
        c = r["condition"]
        for screen, ms in ((r.get("metrics") or {}).get("dwell_ms") or {}).items():
            per[c].setdefault(screen, []).append(ms / 1000.0)
            if (c, screen) not in seen:
                seen.append((c, screen))
    for c in conditions:
        for screen in sorted(per[c], key=lambda s: -st.median(per[c][s])):
            vals = per[c][screen]
            body.append([c, screen, "%.1f" % st.median(vals), "%.1f" % max(vals), len(vals)])
    return table(["조건", "화면", "중앙 체류(초)", "최대(초)", "n"], body)


def trouble(rows, conditions):
    """Where people got stuck: misses / backs / deletes attributed to the screen
    they happened on. This is the part that says which screen to fix next."""
    acc = {}
    for r in rows:
        c = r["condition"]
        for e in r.get("log") or []:
            if e.get("type") != "tap":
                continue
            screen = e.get("screen") or "?"
            k = (c, screen)
            a = acc.setdefault(k, {"miss": 0, "back": 0, "del": 0, "tap": 0})
            a["tap"] += 1
            act = e.get("action") or ""
            if not e.get("valid"):
                a["miss"] += 1
            if act.startswith("back"):
                a["back"] += 1
            if act.endswith("del"):
                a["del"] += 1
    body = []
    for (c, screen), a in sorted(acc.items(), key=lambda kv: -(kv[1]["miss"] + kv[1]["back"] + kv[1]["del"])):
        if a["miss"] + a["back"] + a["del"] == 0:
            continue
        body.append([c, screen, a["tap"], a["miss"], a["back"], a["del"]])
    if not body:
        return "빗나간 탭·되돌아가기·지우기가 한 건도 없습니다."
    return table(["조건", "화면", "총 탭", "빗나감", "되돌아", "지우기"], body)


def write_csv(rows, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    cols = ["participant", "condition", "order_index", "task", "completed",
            "seconds", "taps", "misses", "backs", "deletes",
            "screens_visited", "unique_screens", "file"]
    with io.open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in sorted(rows, key=lambda r: (r["participant"], r.get("order_index", 0))):
            m = r.get("metrics") or {}
            w.writerow([r.get("participant"), r.get("condition"), r.get("order_index"),
                        r.get("task"), int(bool(r.get("completed"))),
                        round(m.get("seconds", 0), 2), m.get("taps"), m.get("misses"),
                        m.get("backs"), m.get("deletes"), m.get("screens_visited"),
                        m.get("unique_screens"), r.get("_file")])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", default=os.path.join(ROOT, "sessions"))
    ap.add_argument("--out", default=None, help="write the Markdown here as well")
    ap.add_argument("--csv", default=None, help="also write one row per session")
    ap.add_argument("--completed-only", action="store_true",
                    help="조건 비교에서 중단된 세션을 뺀다 (기본: 전부 포함)")
    args = ap.parse_args()

    rows = load(args.sessions)
    if not rows:
        print("세션 파일이 없습니다: %s" % args.sessions)
        print("python -m senior_ui.experiment.server 로 실험을 진행하면 여기에 쌓입니다.")
        return 1

    conditions = []
    for r in rows:
        if r["condition"] not in conditions:
            conditions.append(r["condition"])
    conditions.sort()

    pids = {r["participant"] for r in rows}
    parts = [
        "# 실험 세션 집계", "",
        "피험자 %d명 · 세션 %d건 · 조건 %s" % (len(pids), len(rows), ", ".join(conditions)),
        "", "## 1. 진행 현황", "", progress(rows, conditions), "",
        "## 2. 피험자별", "", per_session(rows), "",
        "## 3. 조건 비교", "",
        "%s 기준입니다. 중앙값을 먼저 보세요 — 표본이 작아 한 명이 평균을 크게 흔듭니다." %
        ("완료한 세션만" if args.completed_only else "중단 포함 전체 세션"),
        "", compare(rows, conditions, args.completed_only), "",
        "## 4. 화면별 체류", "", dwell(rows, conditions), "",
        "## 5. 막힌 지점", "",
        "빗나간 탭은 \"어디를 눌러야 할지 몰랐다\", 되돌아가기와 지우기는 \"잘못 갔다\"는 신호입니다.",
        "", trouble(rows, conditions), "",
    ]
    md = "\n".join(parts)

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with io.open(args.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(md)
    if args.csv:
        write_csv(rows, args.csv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(md)
    if args.out:
        sys.stdout.write("\n(저장: %s)\n" % args.out)
    if args.csv:
        sys.stdout.write("(CSV: %s)\n" % args.csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
