r"""Restructure-and-audit loop: ask an LLM for a redesigned transfer prototype,
audit it with senior_ui.audit, feed the fatal findings back, up to N attempts.

What used to be three manual steps - paste a prompt into a chat, save the HTML
it returns, run audit.py, read the JSON, ask again - is one command:

  1. serve the project root on :3003 (only if nothing is listening already)
  2. up to --attempts times:
       a. 진단·계획 (처음 한 번): 원본을 주고 {diagnosis, plan} JSON 하나를
          받는다 - 규칙으로 모양을 보고, --delay 만큼 기다린다
       b. 생성: 원본 + 계획을 주고 HTML + 흐름 명세를 받는다. 재시도면
          반성 JSON 이 먼저 오고, 그 plan_changes 가 계획을 고친다
       c. 형식 검사 + 계획-결과 일치 검사 (브라우저 없음)
       d. audit it - senior_ui.audit is imported and called, never edited
       e. stop on pass; otherwise carry the fatal list into the next prompt
  3. stop the server if this script started it
  4. copy the final build to outputs/restructured_auto.html (+ .flow.json,
     audit_auto.json, .plan.json, .diagnosis.json, .model.html,
     .designer_brief.md) and write summary.json next to the per-attempt files

Everything from a run lands in outputs/restructure_auto/<timestamp>/:
  attempt_N.prompt.txt   the exact prompt sent
  attempt_N.response.txt the raw reply
  attempt_N.html         도구가 선택지 데이터를 넣은 뒤 - 검사기가 여는 것
  attempt_N.model.html   넣기 전, 모델이 쓴 그대로 (넣을 데이터가 있을 때만)
  attempt_N.flow.json
  attempt_N.audit.json   the audit's report (or the parse/validation failure)
  attempt_N.plan_prompt.txt · .plan_response.txt   진단·계획 호출 (처음 한 번)
  attempt_N.diagnosis.json   진단 (계획을 세운 시도에만)
  attempt_N.plan.json        이 시도가 따른 계획 (반성이 고쳤으면 고친 것)
  attempt_N.reflection.json  반성 (재시도에만)
  shots/attempt_N/       one screenshot per screen reached
  designer_brief.md      디자이너용 변경 설명서 (통과한 실행에만)
  run.log, summary.json  run.log 첫 줄 = 모델과 그 출처 (+ 작업 트리 경고,
                         깨끗하지 않을 때)
                         summary.json 의 git · tokens = 커밋 · 단계별 토큰

This file is the command line and nothing else. The work is split up:

  prompt.py      프롬프트 조립 (템플릿 · 선택지 · 재시도 블록 · 반성 요청)
  model.py       모델 호출 · 키 읽기 · 토큰 어림 · mock
  reply.py       답 가르기 · 흐름 명세 모양 검사
  plan.py        진단·계획 읽기 · 계획-결과 일치 검사 · 반성 적용
  brief.py       디자이너용 변경 설명서
  audit_call.py  검사기를 라이브러리로 부른다
  loop.py        재시도 루프 · 예산 · 요약 (run)

Usage:
  python -m senior_ui.restructure --model gpt-6.1-sol   # real model, 형식 5 · 검사 6, wireframe
  python -m senior_ui.restructure --model gpt-6.1-sol --attempts 2
  python -m senior_ui.restructure --model gpt-6.1-sol --task bill   # 공과금 (기본 transfer)
  python -m senior_ui.restructure --mock pass     # no API: replays Run 1
  python -m senior_ui.restructure --mock fail     # no API: a broken flow, every attempt fails
  python -m senior_ui.restructure --list-models   # 이 키로 쓸 수 있는 gpt- 모델 (요금 없음)
  python -m senior_ui.restructure --probe gpt-5   # 아주 짧은 요청 하나: 분당 한도 · 실제 모델

이체 mock 모드는 열하나이고 Run 1 빌드를 되읽는다 (공과금은 bill-identity 하나). 모드마다
은행 목록 한 줄과,
원본에 있고 Run 1 에 없는 두 값(금액 숫자판의 00 · 빠른 금액의 전액)을 채우는
방법과, 원본의 두 오류(계좌번호 틀림 · 은행 틀림)를 다루는 방법이 다르다
(model.MOCKS). 받는 사람 이름은 모두 지금 원본의 정답으로 바꿔 끼운다
(model.NAME_SWAP). Run 1 에는 오류 처리가 없으므로, errors-* 가 아닌 모드는 두
오류를 같은 화면 안의 안내 글로 알리게 바꿔 끼우고 흐름에 오류 경로를 적는다
(model.error_swaps · MOCK_ERROR_PATHS).

  모두 진단·계획 답은 같다 (model.MOCK_PLAN - Run 1 빌드의 아홉 화면).

  pass            은행 목록 · 금액 숫자판 · 빠른 금액을 window.PRESERVED 의
                  배열(BANKS·SECS · AMT_KEYS · QUICK)을 읽어 그린다  -> 통과.
                  통과해도 outputs/ 는 건드리지 않는다 - mock 은 기본으로
                  .mock-outputs/ 에 쓴다 (SENIOR_UI_OUTPUTS 를 주면 그 폴더)
  fail            pass 와 같은 빌드 + 둘째 걸음이 없는 선택자를 클릭하는 흐름
  preserved-all   목록은 참조하고 '00'·'전액' 은 마크업에 직접 쓴다  -> 통과
  preserved-some  참조는 하지만 slice(0, 4) 로 일부만 그린다  -> 검사 I 에서 실패
  preserved-none  참조하지 않고 직접 네 개를 쓴다  -> 형식 검사에서 실패
  errors-undeclared  pass 에서 오류 처리와 오류 경로를 모두 뺐다 (Run 1 그대로)
                  -> 형식 검사에서 실패 (오류 경로가 없다)
  errors-unhandled   오류 경로는 적었지만 HTML 에 오류 처리가 없다
                  -> 검사 J 에서 실패 (틀린 값으로 다음 화면에 넘어간다)
  reveal          은행 목록을 6개 + [전체 보기] 로 그리고 흐름 명세에 reveal 을 적는다 -> 통과
  reveal-undeclared  같은 HTML 인데 reveal 을 적지 않았다 -> 검사 I 에서 실패
  entrances-reveal   과제 밖 입구(tasks/transfer.json 의 entrances)를 [다른 메뉴] 를
                  눌러야 그리고 흐름 명세에 reveal 을 적는다 -> 통과
  entrances-none  입구를 넣지 않는다 (Run 1 그대로 - 다른 메뉴를 다 지운 설계)
                  -> 검사 K 에서 실패

  위 둘이 아닌 이체 모드는 모두 첫 화면에 접힌 블록(<details>)으로 입구를 넣는다
  (model.ENTRANCE_MODES) - Run 1 에는 입구가 하나도 없어서, 넣지 않으면 모든 모드가
  검사 K 에서 떨어진다.

The key comes from .envs (OPENAI_API_KEY=...) or the environment. The model
comes from --model, then RESTRUCTURE_MODEL, then config.DEFAULT_MODEL (지금
gpt-6.1-sol). 어디서 왔는지는 run.log 첫 줄과 summary.json 의 model_source 에
남는다. --mock 은 .envs 와 RESTRUCTURE_MODEL 을 읽지 않는다 (--model 은 듣는다) -
mock 기준값이 PC 마다 달라지지 않게.
Exit: 0 = a build passed, 1 = every attempt failed, 2 = could not run.

"돌지 못했다"(2)에 들어가는 것은 넷이다 - 레이트 리밋으로 멈춤, API 가 요청을
거절함(키·권한·잘못된 요청), 인프라 예산 소진, 시작 자체를 못 함(입력·흐름·
서버). 전부 "다시 만들 빌드가 없다" 이므로 떨어진 빌드(1)와 구분해야 한다.
정하는 곳은 loop.exit_code() 한 곳이다.
"""
import argparse
import sys

from senior_ui._cli import setup_stdout
from senior_ui import config
from senior_ui.audit.stage import STAGES
from senior_ui.tasks import DEFAULT_TASK, task_names

from .loop import run
from .model import ALL_MODES, APIS, REASONING_EFFORTS, REFINE_MODES, SEED, TEMPERATURE
from .probe import list_models, probe


# --mock pass 가 무엇을 하는가. Run 1 빌드에는 원본 숫자판의 00 과 금액 버튼의
# 전액이 없다. 원본의 숫자판이 배열이 된 뒤로 pass 는 그 배열을 읽어 그리므로
# 통과한다.
MOCK_PASS_NOTE = ("pass 는 숫자판·빠른 금액까지 도구가 넣은 배열에서 그려 통과한다 "
                  "(mock 은 기본으로 .mock-outputs/ 에 쓰고 outputs/ 는 건드리지 않는다).")


def build_parser():
    ap = argparse.ArgumentParser()
    ap.add_argument("--attempts", type=int, default=None,
                    help="두 예산을 한 번에 정한다. 주지 않으면 config.DEFAULT_BUDGET "
                         "(형식 %(format)d · 검사 %(audit)d)" % config.DEFAULT_BUDGET)
    ap.add_argument("--format-attempts", type=int, default=None,
                    help="흐름 명세 형식 오류에 쓸 재시도 횟수 (기본: --attempts, "
                         "그다음 %d)" % config.DEFAULT_BUDGET["format"])
    ap.add_argument("--audit-attempts", type=int, default=None,
                    help="검사 fatal 에 쓸 재시도 횟수 (기본: --attempts, 그다음 %d)"
                         % config.DEFAULT_BUDGET["audit"])
    ap.add_argument("--infra-attempts", type=int, default=None,
                    help="설계와 무관한 실패 - 모델에 닿지 못했다 · 브라우저가 시간 안에 "
                         "답하지 않았다 - 에 쓸 재시도 횟수 (기본: config.DEFAULT_BUDGET "
                         "의 %d)" % config.DEFAULT_BUDGET["infra"])
    ap.add_argument("--model", default=None,
                    help="부를 모델. 주지 않으면 환경 변수 RESTRUCTURE_MODEL, 그다음 "
                         "config.DEFAULT_MODEL (%s). --mock 은 환경 변수를 듣지 않는다"
                         % config.DEFAULT_MODEL)
    ap.add_argument("--temperature", type=float, default=TEMPERATURE,
                    help="못박아 보낸다. 기본 %s - 재현에 가장 가깝다. 추론형 모델에는 "
                         "보내지 않는다 (받지 않는다)" % TEMPERATURE)
    ap.add_argument("--seed", type=int, default=SEED,
                    help="못박아 보낸다. 기본 %s. Responses API 로 부를 때는 보내지 "
                         "않는다 (인자가 없다)" % SEED)
    ap.add_argument("--reasoning-effort", choices=REASONING_EFFORTS, default=None,
                    help="추론형 모델이 생각에 쓸 노력. 주지 않으면 config."
                         "DEFAULT_REASONING_EFFORT (%s) 를 보낸다 - 모델의 기본값에 "
                         "맡기지 않는다. run.log 첫 줄과 summary 의 model_call 에 남는다. "
                         "--probe 는 줄 때만 보낸다" % config.DEFAULT_REASONING_EFFORT)
    ap.add_argument("--api", choices=APIS, default="auto",
                    help="auto 는 모델 이름으로 정한다 (model.profile_for). chat · "
                         "responses 로 덮을 수 있다")
    ap.add_argument("--max-tokens", type=int, default=None,
                    help="생성 호출의 completion cap (생각 토큰 포함). 주지 않으면 "
                         "모델에 맞춘 기본값 - gpt-4o %(g4)d, 추론형 %(rs)d "
                         "(config.OUTPUT_CAPS). 분당 한도는 입력에 이것을 더해 센다"
                         % {"g4": config.OUTPUT_CAPS["gpt-4o"]["generate"],
                            "rs": config.OUTPUT_CAPS["reasoning"]["generate"]})
    ap.add_argument("--plan-max-tokens", type=int, default=None,
                    help="진단·계획 호출의 completion cap (JSON 하나, 생각 토큰 포함). "
                         "주지 않으면 gpt-4o %(g4)d, 추론형 %(rs)d"
                         % {"g4": config.OUTPUT_CAPS["gpt-4o"]["plan"],
                            "rs": config.OUTPUT_CAPS["reasoning"]["plan"]})
    ap.add_argument("--mock", choices=ALL_MODES, default=None,
                    help="API 없이 Run 1 을 되읽는다. 모드마다 은행 목록 "
                         "한 줄이 다르다 - model.MOCKS 참고. %s" % MOCK_PASS_NOTE)
    ap.add_argument("--task", choices=task_names(), default=DEFAULT_TASK,
                    help="과제 (tasks/<이름>.json). 프롬프트의 과제 설명과 기본 원본이 "
                         "여기서 온다. 기본 %s" % DEFAULT_TASK)
    ap.add_argument("--original", default=None,
                    help="원본 HTML. 주지 않으면 과제 파일의 original")
    ap.add_argument("--stage", choices=sorted(STAGES), default=None,
                    help="검사 단계. wireframe 은 A·B·C·F·I·J 만 본다. 주지 않으면 "
                         "config.DEFAULT_STAGE (%s)" % config.DEFAULT_STAGE)
    ap.add_argument("--see", choices=["on", "off"], default=None,
                    help="원본 화면 그림을 진단·계획 호출에 넣는가. 주지 않으면 on. "
                         "off 는 그림 없이 글만 보내던 전의 동작이다")
    ap.add_argument("--refine", type=int, default=None, metavar="N",
                    help="보고 다듬기 횟수. 검사를 통과한 빌드의 스크린샷을 보여 주고 "
                         "다듬게 한다. 0 이면 끈다. 형식 · 검사 예산과 따로 센다. 주지 "
                         "않으면 config.DEFAULT_REFINE (%d)" % config.DEFAULT_REFINE)
    ap.add_argument("--mock-refine", choices=REFINE_MODES, default=None,
                    help="--mock 실행에서 다듬기 호출의 답 (model.REFINE_MODES). 주지 "
                         "않으면 done - 1회차에 고칠 것이 없다고 답해 최종 빌드가 "
                         "그대로다")
    ap.add_argument("--list-models", action="store_true",
                    help="이 키로 쓸 수 있는 gpt- 모델을 보이고 끝난다 (models.list, 요금 "
                         "없음). 실행 폴더를 만들지 않는다 - outputs/model-probe.log")
    ap.add_argument("--probe", metavar="MODEL", default=None,
                    help="그 모델에 아주 짧은 요청 하나를 실제 실행과 같은 방식으로 "
                         "보내고, 분당 한도 · 실제 모델 이름 · 지원하지 않는 인자 오류를 "
                         "보이고 끝난다. --api · --reasoning-effort · --temperature · "
                         "--seed 를 따른다. 실행 폴더를 만들지 않는다")
    ap.add_argument("--image", action="store_true",
                    help="--probe 와 함께: 같은 글에 화면 그림 한 장을 더해 한 번 더 보내 "
                         "그 모델이 그림을 받는지, 그림 한 장이 입력 토큰 몇 개인지 잰다 "
                         "(config.IMAGE_TOKENS 를 고칠 값). 요금이 드는 요청이 둘이다")
    ap.add_argument("--delay", type=float, default=None,
                    help="모델 호출 사이 대기(초) - 진단·계획과 생성 사이, 시도와 "
                         "시도 사이. 주지 않으면 gpt-4o %(g4)g, 추론형 %(rs)g "
                         "(config.DELAY). 추론형은 그와 함께 호출 직전에 직전 응답 "
                         "헤더의 남은 토큰을 보고, 다음 요청보다 적을 때만 더 기다린다"
                         % {"g4": config.DELAY["gpt-4o"], "rs": config.DELAY["reasoning"]})
    return ap


def main():
    # 무엇이든 찍기 전에 맞춘다 (senior_ui/_cli.py).
    setup_stdout()
    args = build_parser().parse_args()
    # 확인 명령은 루프를 돌리지 않는다 - 실행 폴더도 만들지 않는다 (probe.py).
    if args.list_models:
        return list_models()
    if args.probe:
        return probe(args.probe, temperature=args.temperature, seed=args.seed,
                     reasoning_effort=args.reasoning_effort, api=args.api,
                     image=args.image)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
