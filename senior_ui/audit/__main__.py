r"""검사기 CLI. 원본과 생성물을 같은 과제로 한 번씩 걷고 비교한다.

옛 tools/audit.py 와 tools/audit_stage.py 의 main() 을 하나로 합친 것이다.
둘은 같은 일을 했고, 뒤의 것이 앞의 것을 부른 다음 단계 밖 검사를 걷어내기만
했다. 이제 단계는 이 CLI 의 인자 하나다.

  wireframe   A 과제 완주 · B 표시 정확성 · C 죽은 컨트롤 · F 언어 · I 선택지 ·
              J 오류 경로
  styled      A~J 전부

흐름 파일은 누가 썼는지에 따라 두 가지로 읽는다 (inputs.researcher_flow).

  연구자 흐름   flows/ 아래 (과제의 원본 흐름, 옛 Run 흐름). 흐름 파일을 그대로
                믿는다 - 자기 truth, 흐름의 task. 단계는 --stage, 없으면 흐름의
                "stage", 그것도 없으면 styled 다. 단계를 적지 않은 옛 흐름은
                예전과 똑같이 전부 검사한다.
  모델 흐름     그 밖 (재구성 루프의 attempt_N.flow.json 등). 루프와 같은 판정
                입력(inputs.judged_flow)을 거친다 - 판정 기준은 흐름이 아니라
                과제에서 온다. 과제는 --task, 없으면 transfer. 단계는 --stage,
                없으면 config.DEFAULT_STAGE. 흐름에 적힌 task · stage · truth 는
                듣지 않는다. 그래서 루프가 실행의 과제 · 단계로 판정한 빌드는
                같은 --task · --stage 로 다시 검사하면 같은 판정을 받는다.

Usage:
  python -m senior_ui.audit \
      --build http://localhost:3003/outputs/restructured_auto.html \
      --build-file outputs/restructured_auto.html \
      --flow flows/restructured.json \
      --stage wireframe --out outputs/audit_wireframe.json

--repaired / --repaired-file 은 --build / --build-file 의 옛 이름이고 그대로
받는다. 출력 JSON 의 키(inputs.repaired 등)도 바꾸지 않는다 - results/ 에 쌓인
옛 JSON 과 같은 모양이어야 하기 때문이다.

Exit: 0 = passed, 1 = fatal findings, 2 = the audit itself could not run -
inputs or flow unreadable, or anything that stops the drive or the audit itself.
The report-shaped JSON then carries the reason as its single fatal.
"""
import argparse
import asyncio
import io
import json
import os
import sys
import traceback

from .._cli import setup_stdout
from ..config import OUTPUTS_DIR, url_for
from ..tasks import abs_path, load_task, task_names
from .core import audit
from .drive import drive
from .flow import load_flow
from .inputs import judged_flow, read_flow, researcher_flow
from .stage import STAGES, apply_stage


def cannot_run(detail, out=None):
    """검사기 자체가 돌지 못했을 때. 리포트 모양 그대로 내보낸다 - 재생성 루프가
    이것도 다른 fatal 과 같은 방식으로 읽기 때문이다.

    종료 코드는 2 다. 1 은 "검사했고 빌드가 떨어졌다" 이므로, 검사기가 돌지
    못한 것에 같은 코드를 쓰면 부르는 쪽이 둘을 구분할 수 없다.

    `out`(--out)에도 쓴다. 쓰지 않으면 그 자리에 지난 판정이 남고, 색인은 그것을
    지금의 판정으로 보여 준다 (감사 B-15). 쓰지 못하면 stdout 으로만 낸다."""
    report = {"passed": False,
              "fatal": [{"check": None, "screen": None, "detail": detail}],
              "warning": [], "metrics": {}}
    if out:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
            with io.open(out, "w", encoding="utf-8", newline="\n") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
        except OSError as e:
            print("--out 에 쓰지 못했다: %s" % e, file=sys.stderr)
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 2


def main(argv=None):
    # 무엇이든 찍기 전에 맞춘다 (senior_ui/_cli.py).
    setup_stdout()
    ap = argparse.ArgumentParser(prog="python -m senior_ui.audit")
    ap.add_argument("--task", choices=task_names(), default=None,
                    help="과제 (tasks/<이름>.json). 주지 않으면 연구자 흐름은 흐름 "
                         "파일의 task, 모델 흐름은 transfer. 기본 원본과 원본을 "
                         "걷는 흐름, 모델 흐름의 판정 기준이 여기서 온다")
    ap.add_argument("--original", default=None,
                    help="원본의 URL. 주지 않으면 과제 파일의 original")
    ap.add_argument("--build", "--repaired", dest="build", required=True,
                    help="검사할 빌드의 URL (--repaired 는 옛 이름)")
    ap.add_argument("--original-file", default=None,
                    help="원본 파일. 주지 않으면 과제 파일의 original")
    ap.add_argument("--build-file", "--repaired-file", dest="build_file",
                    required=True,
                    help="같은 빌드의 파일 경로 (--repaired-file 은 옛 이름)")
    ap.add_argument("--out", default=os.path.join(OUTPUTS_DIR, "audit.json"))
    ap.add_argument("--flow", default=None,
                    help="flow file describing the screens and how to reach them")
    ap.add_argument("--stage", choices=sorted(STAGES), default=None,
                    help="검사 단계. 주지 않으면 연구자 흐름은 흐름 파일의 stage "
                         "(없으면 styled), 모델 흐름은 config.DEFAULT_STAGE")
    ap.add_argument("--shots", default=None, help="directory to save screenshots in")
    args = ap.parse_args(argv)


    # 흐름을 먼저 읽는다 - 과제(그리고 기본 원본)는 흐름이 정할 수 있다.
    # 모델 흐름은 루프와 같은 판정 입력으로 바꾼다 - 판정 기준은 과제에서 온다.
    author = "researcher" if researcher_flow(args.flow) else "model"
    try:
        if author == "researcher":
            flow = load_flow(args.flow, task=args.task)
            stage = args.stage or flow.get("stage") or "styled"
        else:
            flow = judged_flow(read_flow(args.flow), task=args.task, stage=args.stage)
            stage = flow["stage"]
        task = load_task(flow["task"])
    except (OSError, ValueError, RuntimeError) as e:
        return cannot_run("cannot read the flow: %s" % e, args.out)
    args.original = args.original or url_for(task["original"])
    args.original_file = args.original_file or abs_path(task["original"])

    try:
        orig_html = io.open(args.original_file, encoding="utf-8").read()
        rep_html = io.open(args.build_file, encoding="utf-8").read()
    except OSError as e:
        return cannot_run("cannot read inputs: %s" % e, args.out)

    if stage not in STAGES:
        print("알 수 없는 단계: %s (가능: %s)" % (stage, ", ".join(sorted(STAGES))),
              file=sys.stderr)
        return 2

    if args.shots:
        os.makedirs(args.shots, exist_ok=True)
    try:
        # 새 설계는 원본을 그 과제의 원본 흐름으로 걷는다.
        base_flow = load_flow(None, task=task["id"]) \
            if not flow.get("derived_from_original", True) else flow
    except (OSError, ValueError) as e:
        return cannot_run("cannot read the flow: %s" % e, args.out)

    # 브라우저가 없다, 흐름 파일이 검사기가 모르는 모양이다, 쓸 수 없는 경로다 -
    # 전부 "빌드가 떨어졌다" 가 아니라 "검사하지 못했다" 다. 역추적만 남기고
    # 1 로 끝나면 부르는 쪽이 그 둘을 구분할 수 없으므로, 리포트 모양으로 적어
    # 2 로 끝낸다. 역추적은 사람이 고칠 수 있게 stderr 로 보낸다.
    try:
        # 원본은 비교 기준이다. 새 설계를 검사할 때는 원본의 오류 경로를 걷지
        # 않는다 - 오류 경로는 빌드의 흐름으로 빌드를 걷는다.
        orig = asyncio.run(drive(args.original, base_flow,
                                 errors=base_flow is flow))
        rep = asyncio.run(drive(args.build, flow, want_shots=args.shots))

        report = audit(orig, rep, orig_html, rep_html, flow)
        report = apply_stage(report, stage)
        # 키 이름은 바꾸지 않는다. results/ 의 옛 JSON 과 같은 모양이어야 한다.
        report["inputs"] = {"original": args.original, "repaired": args.build,
                            "flow": args.flow or "(builtin original)",
                            "stage": stage, "flow_author": author}

        if args.out:
            os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
            with io.open(args.out, "w", encoding="utf-8", newline="\n") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
    except Exception as e:
        traceback.print_exc()
        return cannot_run("검사기 자체가 멈췄다: %s: %s" % (type(e).__name__, e),
                          args.out)

    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
