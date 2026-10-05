r"""Restructure-and-audit loop: ask an LLM for a redesigned transfer prototype,
audit it with senior_ui.audit, feed the fatal findings back, up to N attempts.

What used to be three manual steps - paste a prompt into a chat, save the HTML
it returns, run audit.py, read the JSON, ask again - is one command:

  1. serve the project root on :3003 (only if nothing is listening already)
  2. up to --attempts times:
       a. build the prompt from docs/restructure-prompt.md (+ the previous
          attempt's fatal list on a retry), call the model
       b. split the reply into HTML + flow JSON, save both under outputs/
       c. audit it - senior_ui.audit is imported and called, never edited
       d. stop on pass; otherwise carry the fatal list into the next prompt
  3. stop the server if this script started it
  4. copy the final build to outputs/restructured_auto.html (+ .flow.json,
     audit_auto.json, .model.html) and write summary.json next to the
     per-attempt files

Everything from a run lands in outputs/restructure_auto/<timestamp>/:
  attempt_N.prompt.txt   the exact prompt sent
  attempt_N.response.txt the raw reply
  attempt_N.html         도구가 선택지 데이터를 넣은 뒤 - 검사기가 여는 것
  attempt_N.model.html   넣기 전, 모델이 쓴 그대로 (넣을 데이터가 있을 때만)
  attempt_N.flow.json
  attempt_N.audit.json   the audit's report (or the parse/validation failure)
  shots/attempt_N/       one screenshot per screen reached
  run.log, summary.json

This file is the command line and nothing else. The work is split up:

  prompt.py      프롬프트 조립 (템플릿 · 선택지 · 재시도 블록)
  model.py       모델 호출 · 키 읽기 · mock
  reply.py       답 가르기 · 흐름 명세 모양 검사
  audit_call.py  검사기를 라이브러리로 부른다
  loop.py        재시도 루프 · 예산 · 요약 (run)

Usage:
  python -m senior_ui.restructure                 # real model, 3 attempts
  python -m senior_ui.restructure --attempts 2 --model gpt-4o
  python -m senior_ui.restructure --mock pass     # no API: replays Run 1
  python -m senior_ui.restructure --mock fail     # no API: a broken flow, every attempt fails

mock 모드는 다섯이고 Run 1 빌드의 은행 목록 한 줄에서만 다르다 (model.MOCKS).

  pass            목록을 window.PRESERVED 로 바꿔 끼운다 - 검사까지 가고 떨어진다
  fail            같은 빌드 + 둘째 걸음이 없는 선택자를 클릭하는 흐름
  preserved-all   데이터를 참조해 전부 그린다 (+ 원본 숫자판의 '00'·'전액')  -> 통과
  preserved-some  참조는 하지만 slice(0, 4) 로 일부만 그린다  -> 검사 I 에서 실패
  preserved-none  참조하지 않고 직접 네 개를 쓴다  -> 형식 검사에서 실패

The key comes from .envs (OPENAI_API_KEY=...) or the environment. The model
comes from --model, then RESTRUCTURE_MODEL, then DESIGNREPAIR_MODEL, then gpt-4o.
Exit: 0 = a build passed, 1 = every attempt failed, 2 = could not run.

"돌지 못했다"(2)에 들어가는 것은 넷이다 - 레이트 리밋으로 멈춤, API 가 요청을
거절함(키·권한·잘못된 요청), 인프라 예산 소진, 시작 자체를 못 함(입력·흐름·
서버). 전부 "다시 만들 빌드가 없다" 이므로 떨어진 빌드(1)와 구분해야 한다.
정하는 곳은 loop.exit_code() 한 곳이다.
"""
import argparse
import sys

from senior_ui._cli import setup_stdout
from senior_ui.audit.stage import STAGES
from senior_ui.config import ORIGINAL_FILE

from .loop import run
from .model import MODES, SEED, TEMPERATURE


def main():
    # 무엇이든 찍기 전에 맞춘다 (senior_ui/_cli.py).
    setup_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--attempts", type=int, default=3,
                    help="두 예산의 기본값")
    ap.add_argument("--format-attempts", type=int, default=None,
                    help="흐름 명세 형식 오류에 쓸 재시도 횟수 (기본: --attempts)")
    ap.add_argument("--audit-attempts", type=int, default=None,
                    help="검사 fatal 에 쓸 재시도 횟수 (기본: --attempts)")
    ap.add_argument("--infra-attempts", type=int, default=3,
                    help="모델에 닿지 못했을 때(연결 실패) 쓸 재시도 횟수")
    ap.add_argument("--model", default=None)
    ap.add_argument("--temperature", type=float, default=TEMPERATURE,
                    help="못박아 보낸다. 기본 %s - 재현에 가장 가깝다" % TEMPERATURE)
    ap.add_argument("--seed", type=int, default=SEED,
                    help="못박아 보낸다. 기본 %s" % SEED)
    ap.add_argument("--max-tokens", type=int, default=16000,
                    help="completion cap; the HTML alone is ~12k tokens")
    ap.add_argument("--mock", choices=MODES, default=None,
                    help="API 없이 Run 1 을 되읽는다. 모드마다 은행 목록 "
                         "한 줄이 다르다 - model.MOCKS 참고")
    ap.add_argument("--original", default=ORIGINAL_FILE)
    ap.add_argument("--stage", choices=sorted(STAGES), default="styled",
                    help="검사 단계. wireframe 은 A·B·C·F·I 만 본다")
    ap.add_argument("--delay", type=float, default=15.0,
                    help="시도 사이 대기(초). 프롬프트가 커서 TPM 한도에 걸리기 쉽다")
    return run(ap.parse_args())


if __name__ == "__main__":
    sys.exit(main())
