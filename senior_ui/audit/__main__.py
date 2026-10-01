r"""검사기 CLI. 원본과 생성물을 같은 과제로 한 번씩 걷고 비교한다.

옛 tools/audit.py 와 tools/audit_stage.py 의 main() 을 하나로 합친 것이다.
둘은 같은 일을 했고, 뒤의 것이 앞의 것을 부른 다음 단계 밖 검사를 걷어내기만
했다. 이제 단계는 이 CLI 의 인자 하나다.

  wireframe   A 과제 완주 · B 표시 정확성 · C 죽은 컨트롤 · F 언어 · I 선택지
  styled      A~I 전부

단계는 --stage 가 가장 세고, 없으면 흐름 파일의 "stage", 그것도 없으면 styled
다. 즉 단계를 적지 않은 기존 흐름은 예전과 똑같이 전부 검사한다.

Usage:
  python -m senior_ui.audit \
      --build http://localhost:3003/outputs/restructured_auto.html \
      --build-file outputs/restructured_auto.html \
      --flow flows/restructured.json \
      --stage wireframe --out outputs/audit_wireframe.json

--repaired / --repaired-file 은 --build / --build-file 의 옛 이름이고 그대로
받는다. 출력 JSON 의 키(inputs.repaired 등)도 바꾸지 않는다 - results/ 에 쌓인
옛 JSON 과 같은 모양이어야 하기 때문이다.

Exit: 0 = passed, 1 = fatal findings, 2 = the audit itself could not run.
"""
import argparse
import asyncio
import io
import json
import os
import sys

from ..config import ORIGINAL_FILE, ORIGINAL_URL, OUTPUTS_DIR
from .core import audit
from .drive import drive
from .flow import load_flow
from .stage import STAGES, apply_stage


def cannot_run(detail):
    """검사기 자체가 돌지 못했을 때. 리포트 모양 그대로 내보낸다 - 재생성 루프가
    이것도 다른 fatal 과 같은 방식으로 읽기 때문이다."""
    json.dump({"passed": False,
               "fatal": [{"check": None, "screen": None, "detail": detail}],
               "warning": [], "metrics": {}},
              sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 2


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m senior_ui.audit")
    ap.add_argument("--original", default=ORIGINAL_URL)
    ap.add_argument("--build", "--repaired", dest="build", required=True,
                    help="검사할 빌드의 URL (--repaired 는 옛 이름)")
    ap.add_argument("--original-file", default=ORIGINAL_FILE)
    ap.add_argument("--build-file", "--repaired-file", dest="build_file",
                    required=True,
                    help="같은 빌드의 파일 경로 (--repaired-file 은 옛 이름)")
    ap.add_argument("--out", default=os.path.join(OUTPUTS_DIR, "audit.json"))
    ap.add_argument("--flow", default=None,
                    help="flow file describing the screens and how to reach them")
    ap.add_argument("--stage", choices=sorted(STAGES), default=None,
                    help="흐름 파일의 stage 를 덮어씁니다")
    ap.add_argument("--shots", default=None, help="directory to save screenshots in")
    args = ap.parse_args(argv)

    try:
        orig_html = io.open(args.original_file, encoding="utf-8").read()
        rep_html = io.open(args.build_file, encoding="utf-8").read()
    except OSError as e:
        return cannot_run("cannot read inputs: %s" % e)

    try:
        flow = load_flow(args.flow)
    except (OSError, ValueError) as e:
        return cannot_run("cannot read the flow: %s" % e)

    stage = args.stage or flow.get("stage") or "styled"
    if stage not in STAGES:
        print("알 수 없는 단계: %s (가능: %s)" % (stage, ", ".join(sorted(STAGES))),
              file=sys.stderr)
        return 2

    if args.shots:
        os.makedirs(args.shots, exist_ok=True)
    try:
        base_flow = load_flow(None) \
            if not flow.get("derived_from_original", True) else flow
    except (OSError, ValueError) as e:
        return cannot_run("cannot read the flow: %s" % e)

    orig = asyncio.run(drive(args.original, base_flow))
    rep = asyncio.run(drive(args.build, flow, want_shots=args.shots))

    report = audit(orig, rep, orig_html, rep_html, flow)
    report = apply_stage(report, stage)
    # 키 이름은 바꾸지 않는다. results/ 의 옛 JSON 과 같은 모양이어야 한다.
    report["inputs"] = {"original": args.original, "repaired": args.build,
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
