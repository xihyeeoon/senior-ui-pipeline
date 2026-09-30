r"""Audit one stage of the pipeline: wireframe, or the styled build after that.

The tool now produces two things in sequence.

    와이어프레임 (도구의 출력)  →  스타일 이식본 (실험 자극물)

A wireframe is a structural proposal. Judging it on contrast, spacing or state
colour is judging work that has not been done yet - a designer fills that in
later. So the wireframe stage runs only the checks that are about whether the
thing works at all, and the styled stage runs everything.

    wireframe   A 과제 완주 · B 표시 정확성 · C 죽은 컨트롤 · F 언어
    styled      A~H 전부

This does not modify tools/audit.py. It calls it, then drops the findings whose
check is out of scope for the stage and records what it dropped and why in
`checks_stood_down`, the same place audit.py already notes checks it stood down.
`passed` is recomputed from the remaining fatals.

The stage comes from the flow file's "stage" key, or --stage on the command
line, which wins. A flow without either runs everything, so existing flows keep
behaving exactly as before.

Usage:
  python tools/audit_stage.py --flow tools/flows/restructured.json \
      --repaired http://localhost:3003/outputs/restructured_transfer.html \
      --repaired-file outputs/restructured_transfer.html \
      --stage wireframe --out outputs/audit_wireframe.json
"""
import argparse
import asyncio
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import audit as A                                            # noqa: E402

# 단계별로 의미가 있는 검사. 와이어프레임에서 빠지는 것들(D 대비, E 레이아웃,
# G 상태 구분, H 미정의 클래스)은 전부 시각 디테일에 관한 것이고, 그 디테일은
# 아직 채워지지 않았다.
STAGES = {
    "wireframe": {
        "checks": ["A", "B", "C", "F"],
        "label": "와이어프레임",
        "why": "시각 디테일이 아직 없는 단계입니다. 대비·레이아웃·상태 색은 "
               "스타일 이식 후에 봅니다.",
    },
    "styled": {
        "checks": ["A", "B", "C", "D", "E", "F", "G", "H"],
        "label": "스타일 이식본",
        "why": None,
    },
}
ALL = STAGES["styled"]["checks"]


def apply_stage(report, stage):
    """단계 밖의 검사 결과를 걷어내고, 무엇을 왜 걷어냈는지 남긴다."""
    spec = STAGES[stage]
    keep = set(spec["checks"])
    dropped = [c for c in ALL if c not in keep]
    if not dropped:
        report.setdefault("metrics", {})["stage"] = stage
        return report

    names = A.__dict__.get("CHECK_NAMES", {})
    for sev in ("fatal", "warning"):
        report[sev] = [f for f in report.get(sev) or []
                       if (f.get("check") or "?") in keep or f.get("check") is None]

    m = report.setdefault("metrics", {})
    m["stage"] = stage
    m["stage_checks"] = spec["checks"]
    stood = list(m.get("checks_stood_down") or [])
    for c in dropped:
        stood.append("%s/스테이지 밖 (%s) - %s" % (c, spec["label"], spec["why"]))
    m["checks_stood_down"] = stood
    report["passed"] = not report.get("fatal")
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--original",
                    default="http://localhost:3003/inputs/original_transfer.html")
    ap.add_argument("--repaired", required=True)
    ap.add_argument("--original-file",
                    default=os.path.join(ROOT, "inputs", "original_transfer.html"))
    ap.add_argument("--repaired-file", required=True)
    ap.add_argument("--flow", default=None)
    ap.add_argument("--stage", choices=sorted(STAGES), default=None,
                    help="흐름 파일의 stage 를 덮어씁니다")
    ap.add_argument("--out", default=None)
    ap.add_argument("--shots", default=None)
    args = ap.parse_args()

    flow = A.load_flow(args.flow)
    stage = args.stage or flow.get("stage") or "styled"
    if stage not in STAGES:
        print("알 수 없는 단계: %s (가능: %s)" % (stage, ", ".join(sorted(STAGES))),
              file=sys.stderr)
        return 2

    try:
        orig_html = io.open(args.original_file, encoding="utf-8").read()
        rep_html = io.open(args.repaired_file, encoding="utf-8").read()
    except OSError as e:
        print("입력을 읽지 못했습니다: %s" % e, file=sys.stderr)
        return 2

    if args.shots:
        os.makedirs(args.shots, exist_ok=True)
    base_flow = A.load_flow(None) if not flow.get("derived_from_original", True) else flow
    orig = asyncio.run(A.drive(args.original, base_flow))
    rep = asyncio.run(A.drive(args.repaired, flow, want_shots=args.shots))

    report = A.audit(orig, rep, orig_html, rep_html, flow)
    report = apply_stage(report, stage)
    report["inputs"] = {"original": args.original, "repaired": args.repaired,
                        "flow": args.flow or "(builtin original)", "stage": stage}

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with io.open(args.out, "w", encoding="utf-8", newline="\n") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
