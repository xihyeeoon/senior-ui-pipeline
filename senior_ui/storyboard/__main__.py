r"""화면설계서 - 검사를 통과한 재구성 실행 하나에서 디자이너가 볼 설계서를 만든다.

실행 폴더를 읽기만 한다 (summary.json · 최종 HTML · 흐름 명세 · 계획 · 진단 · 최종
검사 결과). 결과는 <실행 폴더>/storyboard/ 에 쓴다.

Usage:
  python -m senior_ui.storyboard outputs/restructure_auto/<실행> --model gpt-6.1-sol
  python -m senior_ui.storyboard outputs/restructure_auto/<실행> --mock

--model 은 영역 묶기 호출의 모델이다 (주지 않으면 config.DEFAULT_MODEL). 키는 재구성
루프와 같이 환경 변수 또는 .envs 의 OPENAI_API_KEY 에서 읽는다. --mock 은 모델을
부르지 않고 정해진 영역 답을 쓴다 (키도 읽지 않는다). --mock 뒤의 모드는 시험용이다
(bad-then-good · bad - regions.MOCK_MODES).

Exit: 0 = 만들었다, 1 = 만들었지만 영역 묶기 모델을 부르지 못해 화면마다 "기타" 로
묶었다, 2 = 만들지 않았다 (통과하지 못한 실행 · 실행 폴더가 아님 · 서버 · 브라우저).
"""
import argparse
import sys

from senior_ui._cli import setup_stdout
from senior_ui import config

from . import regions as R
from .build import make
from .run import NotReady


def build_parser():
    ap = argparse.ArgumentParser(prog="python -m senior_ui.storyboard",
                                 description="검사를 통과한 재구성 실행의 화면설계서")
    ap.add_argument("run_dir", help="실행 폴더 (outputs/restructure_auto/<실행>)")
    who = ap.add_mutually_exclusive_group()
    who.add_argument("--model", default=None,
                     help="영역 묶기 모델 (기본 config.DEFAULT_MODEL = %s)" % config.DEFAULT_MODEL)
    who.add_argument("--mock", nargs="?", const=R.DEFAULT_MOCK, choices=R.MOCK_MODES,
                     default=None, help="모델을 부르지 않고 정해진 영역 답을 쓴다")
    ap.add_argument("--reasoning-effort", default=None,
                    help="추론형 모델의 노력 (기본 config.DEFAULT_REASONING_EFFORT)")
    ap.add_argument("--port", type=int, default=config.AUTO_PORT,
                    help="서버 포트. 주지 않으면 빈 포트에 제 서버를 띄우고 끝에서 끈다")
    ap.add_argument("--no-pdf", action="store_true", help="PDF 를 만들지 않는다")
    ap.add_argument("--concurrency", type=int, default=None,
                    help="동시에 여는 확인 페이지 수 (기본 walk.CONCURRENCY)")
    return ap


def main(argv=None):
    setup_stdout()
    args = build_parser().parse_args(argv)
    from . import walk as W
    try:
        code, data = make(args.run_dir, port=args.port, model=args.model, mock=args.mock,
                          pdf=not args.no_pdf, reasoning_effort=args.reasoning_effort,
                          concurrency=args.concurrency or W.CONCURRENCY)
    except NotReady as e:
        print("storyboard: 만들지 않았다 - %s" % e, file=sys.stderr)
        return 2
    except (R.CannotRun, RuntimeError) as e:
        print("storyboard: 돌지 못했다 - %s" % e, file=sys.stderr)
        return 2
    except Exception as e:                  # 브라우저 · 도구 버그 - 역추적을 남긴다
        import traceback
        traceback.print_exc()
        print("storyboard: 돌지 못했다 (도구 오류) - %s: %s" % (type(e).__name__, e),
              file=sys.stderr)
        return 2
    c = data["counts"]
    print("storyboard: 장 %d (화면 %d) · 항목 %d · 누르기 %d번 · 영역 묶기 %s · 종료 %d"
          % (c["sheets"], c["main_sheets"], c["items"], c["clicks"],
             "mock" if args.mock else (data["regions_call"].get("error") or "모델"), code))
    return code


if __name__ == "__main__":
    sys.exit(main())
