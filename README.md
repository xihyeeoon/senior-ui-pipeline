# senior-ui-pipeline

고령 사용자가 은행 앱의 과업 — **이체**와 **공과금 납부** — 을 혼자 끝낼 수 있도록 화면
구조를 LLM 으로 다시 짜고, 그 결과를 도구가 직접 걸어 보고 검사해, 디자이너가 볼
**화면설계서**로 내는 도구다.

HCI 연구에서 **조건 C** 를 만드는 데 쓴다. 실험은 Flutter 더미앱(`senior-ui-dummy-app`)의 세
조건을 실제 고령 피험자에게 돌린다.

| 조건 | 무엇 |
|---|---|
| A1 | 원본 재현 (신한 SOL 화면을 그대로) |
| A2 | 배포된 고령자 모드 |
| **C** | **이 도구의 재설계** — 디자이너가 화면설계서를 보고 더미앱에 옮긴다 |

**도구의 결과물은 화면설계서다. 재구성 HTML 은 검증용 속 재료다.** 모델이 만든 HTML 은
검사기가 걸어 보고 판정하기 위한 것이고, 디자이너가 받는 것은 검사를 통과한 HTML 에서 뽑은
설계서 — 와이어플로 한 장, 기능-화면 표, 화면마다 정보칸 · 로우파이 와이어프레임 그림(회색
상자와 글자) · 그림 위의 번호 영역 · 설명 표(영역별 요소 · 클릭 결과 주석 · 예외) — 다. 색 ·
모양은 디자이너의 몫이라 넣지 않는다 (위치 · 크기 · 글자 크기 · 굵기는 설계 결정이라 남긴다).

자세한 것은 [`docs/README.md`](docs/README.md) (운영 문서 전부) 와 아래 각 절의 링크.

## 원칙

1. **규칙 목록이 없다.** 고령자 UX 규칙을 모델에게 주지 않는다. 모델은 원본의 화면 그림과
   코드를 보고 고령 사용자가 어디서 멈추고 무엇을 잘못 누를지 직접 진단하고, 그 진단에
   대응하는 변경을 계획한다. `kb/senior_kb.csv` 는 만들어진 설계를 나중에 대조하는 데만
   쓴다 ([`kb/README.md`](kb/README.md)).
2. **보여 주는 방식은 자유다.** 화면을 몇 개로 나눌지, 순서 · 배치 · 묶음 · 접기, 오류를
   어떻게 알릴지는 모델이 정한다. 도구는 그것을 판정하지 않는다.
3. **할 수 있는 일은 줄이지 않는다.** 아래 "보존 대상" 은 하나라도 빠지면 검사에서 떨어진다.
   방해 항목이 지워지면 재설계가 "더 좋은 설계" 가 아니라 "항목이 적어서" 쉬워지기 때문이다.
4. **역할은 연구자가 과제 파일에 선언한다.** 무엇이 정답이고, 무엇이 오류이고, 어느 무리가
   선택지가 아니고, 어느 버튼이 과제 밖 입구인지는 `tasks/<과제>.json` 에 연구자가 적는다.
   모델도 도구도 추측하지 않는다.
5. **판정은 모델의 말을 믿지 않는다.** 모델이 흐름 명세에 적은 정답 · 완료 화면 값 · 면제
   선언은 버리고 과제에서 읽는다 (`audit/inputs.judged_flow`). 설계서의 "누르면 어디로" 는
   도구가 실제로 눌러 본 것만 적는다.

## 보존 대상

| 무엇 | 정의 | 누가 정하나 | 검사 |
|---|---|---|---|
| 과제 완주 | 흐름 명세의 정답 경로를 끝까지 걸을 수 있고, 완료 화면에 과제가 정한 값(보낸 금액 · 납부 번호)이 보인다 | 과제 파일 `done_expect` · 원본 흐름의 정답(`truth`) | A |
| 선택지 값 | 원본에서 같은 `data-action` 을 가진 형제 둘 이상인 무리의 값 — 은행 67개, 숫자판, 빠른 금액, 메뉴 항목 289개 … 숨기거나 접어도 되지만 값이 빠지면 안 된다 | 원본 HTML. 과제의 `not_choices`(선택지가 아닌 무리)와 연구자 파일 `flows/allowed_removals.json`(일부러 뺀 값)은 뺀다 | I |
| 과제 밖 입구 | 과제 경로 위 화면의 다른 메뉴 · 버튼 (원본에 `data-action="oos-…"` 로 붙였다). 누를 수 있게 남아 있어야 한다 — 같은 화면이 아니어도, 접어 두어도 된다 | 과제 파일 `entrances` (더미앱 A1 의 OutOfScope 대상, 연구자 확정) | K |
| 오류 처리 | 과제가 정한 잘못된 입력마다 오류 상태가 나타나고, 무엇이 틀렸는지 새 글이 보이고, 고칠 화면으로 돌아갈 수 있다 | 과제 파일 `required_error_paths` · 원본 흐름의 `error_paths` 정의 | J |

선택지 데이터는 도구가 지킨다 — 원본의 스크립트 배열을 꺼내 재설계 HTML 에
`window.PRESERVED` 로 넣는다. 모델이 67개를 다시 타이핑하다 4개로 줄이는 일이 되풀이됐기
때문이다 ([`docs/variance-notes.md`](docs/variance-notes.md)).

## 한 번 실행의 흐름

```
 tasks/<과제>.json  +  inputs/original_<과제>.html  +  flows/<원본 흐름>.json
                │
 [1] 원본 걷기 (도구)        원본을 흐름대로 한 번 걷는다 → 기준 스냅샷 · 화면 그림 · 선택지 데이터
                │
 [2] 진단 · 계획 (모델)      원본 그림 + HTML → 진단 D1… · 계획 (화면 · 변경 C1… · 오류마다 알리는 곳)
                │
 [3] 생성 (모델)             계획 + 원본 → 재설계 HTML + 흐름 명세 (정답 경로 · 오류 경로 · 펼치기)
                │
 [4] 형식 검사 (도구)        답 가르기 · 흐름 명세의 모양 · 계획과 화면 · 선택지 데이터 참조
                │            → window.PRESERVED 넣기                       (브라우저 없음)
 [5] 검사기 (도구)           원본과 빌드를 같은 과제로 걷고 견준다 — 검사 A~K
                │
        fatal ──┴──▶ [6] 반성 · 재시도 (모델)  검사 결과를 되먹여 원인부터 쓰고 고친다
                │        예산 형식 5 · 검사 6, 같은 실패가 두 번이면 멈춘다 (stuck)
              통과
                │
 [7] 보고 다듬기 (모델)      통과한 빌드의 그림을 보여 주고 다듬게 한다 (기본 2회) — 다시 검사를
                │            통과해야 최종, 떨어지면 직전 통과 빌드로 되돌린다
 [8] 설명서 · 설계서         designer_brief.md (자동) · 화면설계서 (python -m senior_ui.storyboard)
```

[8] 의 설계서만 따로 실행한다 — 실행이 끝난 폴더를 읽기만 해서 만든다 (재구성 · 검사 · 고르기는 바꾸지 않는다).

## 검사 A~K

검사기(`python -m senior_ui.audit`)는 원본과 빌드를 같은 과제로 걸으며 화면마다 긁어 견준다.
fatal 이 하나라도 있으면 떨어진다. 재구성은 **와이어프레임 단계**로 돈다 — 시각 디테일(대비 ·
레이아웃 · 상태 색 · 정의 안 된 클래스)은 아직 아무도 채우지 않았으므로 보지 않는다.

| | 검사 | 심각도 | 와이어프레임 단계 |
|---|---|---|---|
| A | 과제 완주 — 흐름의 모든 화면에 닿고, 완료 화면에 과제의 값, 기술 계약(`data-screen` · `id`) | fatal | ✓ |
| B | 표시 정확성 — 넣은 값이 그대로 보이는가, 주입된 `alert()` · 박아 넣은 숫자가 없는가 | fatal | ✓ |
| C | 죽은 컨트롤 — 처리기에 분기가 없는 `data-action`, 사라진 `data-action` | fatal | ✓ |
| D | 대비 — 저대비 글이 늘지 않는가 | warning | |
| E | 레이아웃 — 겹침 · 넘침 · 새 줄바꿈 · 훨씬 길어진 화면 | warning | |
| F | 언어 — 원본에 없던 영어 낱말 | warning | ✓ |
| G | 상태 — `.x` 와 `.x.on` 이 다르게 그려지는가 | warning | |
| H | 정의 안 된 클래스 | warning | |
| I | 선택지 보존 — 원본의 선택지 값이 빌드 어딘가에 남았는가 (펼치기 포함) | fatal | ✓ |
| J | 오류 경로 — 잘못된 입력마다 오류 상태 · 새 글 · 고칠 곳으로 되돌아가기 | fatal | ✓ |
| K | 과제 밖 입구 — 원본의 `oos-*` 가 누를 수 있게 남았는가 | fatal | ✓ |

검사마다 무엇을 보고 무엇을 보지 못하는지는 [`docs/README.md`](docs/README.md) 의 "The
auditor" 와 `senior_ui/audit/checks/` 의 모듈마다의 설명.

## 과제 파일의 칸 (`tasks/<과제>.json`)

과제 하나가 파일 하나다 (`tasks/transfer.json` · `tasks/bill.json`). 칸이 빠지면 다른 과제의
값으로 메우지 않고 멈춘다.

| 칸 | 뜻 |
|---|---|
| `id` · `label` | 과제 이름 (`transfer` / 이체, `bill` / 공과금 납부) |
| `description` | 프롬프트의 과제 문단 |
| `original` · `flow` | 원본 HTML 과 그것을 걷는 원본 흐름 (정답 `truth` · 오류 정의 `error_paths` 가 여기 있다) |
| `done_expect` | 완료 화면에서 확인할 `[선택자, 값]` (검사 A) |
| `required_truth` | 원본 흐름의 정답에 꼭 있어야 할 키 |
| `keep_on_screen` | 원본 화면에 있던 그 값(받는 사람 이름 등)이 빌드에서 사라지면 경고 (검사 B) |
| `dialog_ok_values` | 대화상자가 말해도 되는 숫자 (검사 B) |
| `required_error_paths` | 반드시 걸어야 할 오류 경로 (검사 J). 공과금은 없다 |
| `not_choices` | 같은 이름의 형제 무리지만 **선택지가 아닌** 것과 이유 — 공과금의 메뉴 칩 · 탭 (검사 I 에서 뺀다) |
| `entrances` | 과제 밖 입구 목록 — `oos-*` 이름 · 라벨 · 출처 (검사 K) |
| `prompt` | 재구성 프롬프트의 과제별 문단 |

연구자가 손으로 고치는 파일이 둘 더 있다 — `flows/allowed_removals.json` (선택지인데 일부러
빼도 되는 값, 지금은 비어 있다) 과 `flows/selection_rule.json` (C 후보를 고르는 규칙).

## 설치

Python 3.12. `.venv` 는 [uv](https://docs.astral.sh/uv/) 로 관리한다 (pip 이 없다).

```powershell
uv venv .venv
uv pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

모델을 부르는 것은 재구성 루프와 설계서의 영역 묶기 둘이다. 키는 환경 변수 또는 `.envs` 의
`OPENAI_API_KEY=…` 에서 읽는다. 검사기 · 고르기 · 설계서의 `--mock` 은 키 없이 돈다.

## 명령

```powershell
# 재구성 - 진단 · 계획 → 생성 → 형식 검사 → 검사기 → 반성 · 재시도 → 다듬기 → 설명서
.\.venv\Scripts\python.exe -m senior_ui.restructure --model gpt-6.1-sol                  # 이체
.\.venv\Scripts\python.exe -m senior_ui.restructure --model gpt-6.1-sol --task bill      # 공과금
.\.venv\Scripts\python.exe -m senior_ui.restructure --mock pass                          # API 없이

# 화면설계서 - 통과한 실행 하나에서
.\.venv\Scripts\python.exe -m senior_ui.storyboard outputs\restructure_auto\<실행> --model gpt-6.1-sol
.\.venv\Scripts\python.exe -m senior_ui.storyboard outputs\restructure_auto\<실행> --mock
.\.venv\Scripts\python.exe -m senior_ui.storyboard outputs\restructure_auto\<실행> --regions-from <저장된 storyboard.json>

# C 후보 고르기 - 과제마다 여러 번 돌린 실행에 순위를 매긴다
.\.venv\Scripts\python.exe -m senior_ui.select --task transfer

# 검사기만 (루프가 만든 빌드를 다시 검사할 때는 --task 를 꼭 준다)
.\.venv\Scripts\python.exe -m senior_ui.audit --task bill --flow <흐름> --build <URL> --build-file <파일>

# 이 작업 트리를 127.0.0.1:3003 에 띄워 두기 (검사기 CLI 를 여러 번 돌리거나 빌드를 열어 볼 때)
.\.venv\Scripts\python.exe -m senior_ui.devserver
```

재구성 · 설계서 · 시험은 실행마다 빈 포트에 제 서버를 띄우고 끝에서 제 것만 끈다 — 동시에
돌려도 된다. 서버는 루프백(127.0.0.1)에만 연다 (루트에 `.envs` 와 `sessions/` 가 있다).
종료 코드는 대체로 `0` = 됐다, `1` = 돌았지만 떨어졌다, `2` = 돌지 못했다 (명령마다
[`docs/README.md`](docs/README.md)).

모델 바꾸기 · 실행 설정(출력 길이 · 대기 · reasoning_effort) · 처음 쓰는 모델 확인
(`--list-models` · `--probe`)은 [`docs/README.md`](docs/README.md) 의 "모델 바꾸기".

## 출력 폴더

```
outputs/restructure_auto/<실행>/          실행 하나의 모든 것 (실행 = 시각[-과제][-mock 모드])
  attempt_1.plan_prompt.txt · plan_response.txt · diagnosis.json · plan.json   진단 · 계획
  attempt_N.prompt.txt · response.txt      보낸 프롬프트 전문 · 받은 답 전문
  attempt_N.html · model.html · flow.json  빌드 (도구가 선택지 데이터를 넣은 것 · 모델이 쓴 그대로) · 흐름 명세
  attempt_N.audit.json                     검사 결과
  attempt_N.reflection.json · critique.json  반성 · 다듬기 비평
  shots/                                   검사기가 찍은 화면 그림 (원본 · 시도별)
  designer_brief.md                        디자이너용 변경 설명서 (통과했을 때)
  run.log · summary.json                   로그 · 요약 (통과 · 최종 빌드 · 토큰 · 비용 · 커밋)
  storyboard/                              화면설계서 (python -m senior_ui.storyboard 를 돌렸을 때)
    index.html · storyboard.pdf · storyboard.json · shots/ · wireframe.html · regions.*.txt
outputs/restructured_auto[_bill].*         지금 쓰는 재구성본 (통과한 최종 빌드의 사본)
outputs/selection/<과제>_<시각>.md · .json  고르기 결과
.mock-outputs/                             --mock 실행 (실제 결과와 떼어 둔다)
results/                                   남겨야 할 증거 (추적한다 - outputs/ 는 추적하지 않는다)
```

## 비용 어림

가격은 `senior_ui/config.py` 의 `MODEL_PRICES` (100만 토큰당, `gpt-6.1-sol` 입력 2.00 · 출력
10.00). 실행마다 실제 금액이 `summary.json` 의 `cost` 와 `storyboard.json` 의
`regions_call.cost_usd` 에 남는다.

| | 예 (실제 실행) | 금액 |
|---|---|---|
| 재구성 — 이체, gpt-6.1-sol | `20261006-124055` (시도 2) · `20261007-102041` (시도 3, 다듬기 1회) · `20261006-215902` (시도 4) | $0.35 · $0.57 · $0.65 |
| 재구성 — 공과금, gpt-6.1-sol | `20261007-103023-bill` (시도 4, 통과 못 함) | $0.80 |
| 재구성 — 이체, gpt-6-astra | `20261006-124838` (시도 4) | $3.11 |
| 화면설계서 영역 묶기 (호출 한 번) | 이체 장 10 · 항목 91 / 공과금 장 18 · 항목 404 (11-12 시험의 프롬프트로 어림) | 약 $0.08 / 약 $0.19 (다시 묻기까지 가면 두 배 가까이) |

설계서는 시간이 더 든다 — 요소마다 다시 걸어 눌러 보므로 이체 1분 남짓, 공과금 3분 남짓.

## C 후보 고르기

과제마다 재구성을 여러 번 돌린 뒤 실험에 쓸 하나를 고르는 것을 돕는다. 도구는 순위표와
비교 보고서를 만들고, 고르는 것은 연구자다. 문지기(통과 · 도구가 고친 흔적 없음 · 잘림 없음 ·
깨끗한 작업 트리 · mock 아님 · 모델 · 단계 · 예산 …)를 지난 실행 중 **가장 전형적인 시안**
(화면 수 · data-action 수 · 변경 수가 중앙값에 가까운 것)이 1등이다. 규칙은 코드가 아니라
`flows/selection_rule.json` 에 있다. [`docs/README.md`](docs/README.md) 의 "C 후보 고르기".

## 시험

```powershell
.\.venv\Scripts\python.exe -m pytest                # 브라우저 없음
.\.venv\Scripts\python.exe -m pytest -m browser     # 실제로 다시 걷는다 (설계서 셋을 끝까지 만드는 것 포함)
```

구조를 정리해도 동작이 그대로인지 기준값(`tests/baseline/`)과 파일로 비교한다. 기준값은 동작을
일부러 바꿨을 때만 `tests/capture_baseline.py` 로 다시 뽑는다 (`--only bill` · `--only
storyboard` 는 그 부분만). 실제 API 는 부르지 않는다 — 모델이 필요한 곳은 mock · 가짜 OpenAI
(`tests/fake_openai.py`) · 저장된 실제 답(`tests/fixtures/real_runs/`)으로 돈다.
[`tests/README.md`](tests/README.md).

## 한계

- **스크린샷 한 장은 동작을 담지 못한다.** 그래서 설계서는 요소마다 실제로 눌러 본 결과와
  오류 · 펼친 뒤 같은 조건별 화면을 따로 둔다. 그래도 눌러 본 것은 흐름 명세가 적은 상태에서의
  한 번이다 — 입력값에 따라 갈라지는 다른 갈래는 오류 경로 · 펼치기로 적힌 것만 보인다. 선택지
  무리는 대표 하나만 누른다.
- **시각은 범위 밖이다.** 와이어프레임 단계라 대비 · 레이아웃 · 상태 색 · 정의 안 된 클래스(D ·
  E · G · H)는 판정하지 않고, 설계서의 그림도 회색이다. 색 · 모양은 디자이너가 채운다.
- **보고 다듬기는 지금 기본으로 켜져 있다** (`--refine 2`, `config.DEFAULT_REFINE`, 고르기
  규칙도 refine 2 를 요구한다). 다듬은 빌드도 검사를 다시 통과해야 최종이 되지만, 다듬기가
  시각 품질을 판정하지는 않는다. 끄려면 `--refine 0` (그때는 고르기 규칙의 `budget.refine` 도
  0 으로).
- **앞단(스크린샷 → HTML)은 아직 없다.** 지금은 사람이 만든 `inputs/original_*.html` 이 그
  대역이다. 앞단이 지킬 약속은 [`docs/input-contract.md`](docs/input-contract.md).
- 알려진 문제 목록은 [`docs/README.md`](docs/README.md) 의 "알려진 문제".

## 문서

| | |
|---|---|
| [`docs/README.md`](docs/README.md) | 운영 문서 — 실행 · 모델 · 데이터 보존 · 오류 경로 · 선택지 아님 · 고르기 · 화면설계서 · 검사기 · 뷰어 · 시험 |
| [`docs/storyboard.md`](docs/storyboard.md) | 화면설계서 — 칸마다 출처, 만드는 법, `storyboard.json`, 시간 · 비용, 한계 |
| [`docs/restructure-prompt.md`](docs/restructure-prompt.md) | 재구성 프롬프트 템플릿 (루프가 이 파일을 읽는다) |
| [`docs/input-contract.md`](docs/input-contract.md) | 입력 HTML 의 약속 |
| [`docs/experiment-guide.md`](docs/experiment-guide.md) | 실험 당일 절차 |
| [`docs/variance-notes.md`](docs/variance-notes.md) | 같은 프롬프트를 다시 돌리면 무엇이 달라지나 |
| [`docs/defect-types.md`](docs/defect-types.md) | 생성물에 되풀이되는 결함 유형 |
| [`tests/README.md`](tests/README.md) | 시험과 기준값 |
