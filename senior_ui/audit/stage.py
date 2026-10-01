r"""Audit one stage of the pipeline: wireframe, or the styled build after that.

The tool now produces two things in sequence.

    와이어프레임 (도구의 출력)  →  스타일 이식본 (실험 자극물)

A wireframe is a structural proposal. Judging it on contrast, spacing or state
colour is judging work that has not been done yet - a designer fills that in
later. So the wireframe stage runs only the checks that are about whether the
thing works at all, and the styled stage runs everything.

    wireframe   A 과제 완주 · B 표시 정확성 · C 죽은 컨트롤 · F 언어
    styled      A~H 전부

This does not modify core.py. It takes the report core.audit() already produced,
drops the findings whose check is out of scope for the stage, and records what
it dropped and why in `checks_stood_down` - the same place core.audit() already
notes checks it stood down. `passed` is recomputed from the remaining fatals.

The stage comes from the flow file's "stage" key, or --stage on the command
line, which wins (see __main__.py). A flow without either runs everything, so
existing flows keep behaving exactly as before.
"""

# 단계별로 의미가 있는 검사. 와이어프레임에서 빠지는 것들(D 대비, E 레이아웃,
# G 상태 구분, H 미정의 클래스)은 전부 시각 디테일에 관한 것이고, 그 디테일은
# 아직 채워지지 않았다.
STAGES = {
    "wireframe": {
        # I(선택지 보존)는 시각 디테일이 아니라 구조 문제이므로 여기서도 본다.
        "checks": ["A", "B", "C", "F", "I"],
        "label": "와이어프레임",
        "why": "시각 디테일이 아직 없는 단계입니다. 대비·레이아웃·상태 색은 "
               "스타일 이식 후에 봅니다.",
    },
    "styled": {
        "checks": ["A", "B", "C", "D", "E", "F", "G", "H", "I"],
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
