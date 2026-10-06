# senior-ui-pipeline

고령 사용자가 은행 이체 과업을 혼자 끝낼 수 있도록 화면 구조를 LLM 으로 다시
짜고, 그 산출물을 자동으로 검사하고, 실제 고령 피험자에게 돌려 보는 파이프라인.

```
캡처 → LLM 재구성 → 검사기 → (스타일 이식) → 실험
```

산출물은 **와이어프레임 수준의 구조 시안**이고 시각 디테일은 디자이너가 채운다.
그 전제가 아래 모든 것을 — 특히 검사를 두 단계로 나눈 것을 — 결정한다.

2026-09-30 에 DesignRepair 를 연구에서 뺐고, 관련 코드와 자료는 커밋 `66186fe`
까지의 히스토리에 있다.

## 설치

Python 3.12. `.venv` 에는 **pip 이 없고** [uv](https://docs.astral.sh/uv/) 로
관리한다.

```powershell
uv venv .venv                                   # 없을 때만
uv pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

`requirements.txt` 는 실제로 import 하는 것만 적는다 — playwright(검사기),
openai(재구성 루프), pytest(테스트). 서버·세션 저장·색인은 전부 표준
라이브러리로 돈다.

LLM 을 부르는 것은 재구성 루프 하나뿐이고, 키는 `.envs` 의 `OPENAI_API_KEY=…`
또는 환경변수에서 읽는다. 검사기·뷰어·실험 서버는 키가 없어도 돈다.

## Layout

| Path | What | Tracked |
|---|---|---|
| `senior_ui/` | 이 프로젝트에서 쓴 코드 전부 — 재구성 루프, 검사기, 뷰어 색인, 실험 서버. 모두 `python -m senior_ui.…` 로 실행한다. | yes |
| `web/` | 브라우저에서 열리는 것 — `dashboard.html`(내부 확인용 4화면), `session.html`(HTML 실험 장치 - 본실험에 쓰지 않는다. `--session` 을 줄 때만 서빙된다). | yes |
| `flows/` | 흐름 파일. 검사기가 화면을 어떤 순서로 어떻게 몰고 다니는지의 명세. `original.json` 과 재구성본별 `restructured`·`run2`·`run3`·`run4`. `allowed_removals.json` 은 그것들과 다르다 — 과제별로 "빼도 되는 선택지" 를 적는 곳이고, **연구자만** 손으로 고친다 (아래 참고). | yes |
| `inputs/` | 파이프라인이 읽는 것. `original_transfer.html` 이 8화면 이체 시제품이고 모든 갈래가 여기서 출발한다. `*.png` 는 실제 SOL 캡처라 추적하지 않는다 (실명이 보인다). | html 만 |
| `kb/` | 재구성본 사후 대조용 규칙 46개. 생성에는 쓰지 않는다. | yes |
| `results/` | 남겨야 할 증거. 재구성본 html, 그 검사 JSON, 스크린샷, 자동 실행 폴더 사본. `python -m senior_ui.collect_results` 가 `outputs/` 에서 복사해 온다. | **yes** |
| `tests/` | 회귀 테스트와 기준값. 구조를 정리해도 동작이 그대로인지 파일 비교로 확인한다. 자세한 것은 `tests/README.md`. | yes |
| `docs/` | 이 문서들. 재구성 프롬프트 템플릿(`restructure-prompt.md`)도 여기 있고 루프가 그 파일을 읽어 모델에 보낸다. | yes |
| `outputs/` | 실행 산출물. 크고 대부분 재생성 가능하므로 ignore 한다 — 그래서 `results/` 가 있다. | no |
| `.mock-outputs/` | `--mock` 실행의 기본 산출물 폴더 (`config.MOCK_OUTPUTS_DIR`). `outputs/` 와 떼어 놓는다 — `--mock pass` · `preserved-all` 은 실제로 통과하므로, 같은 폴더를 쓰면 연습으로 돌린 mock 이 `outputs/restructured_auto.*` 를 덮는다. `outputs/restructured_auto.*` 는 실제 실행만 쓴다. | no |
| `sessions/` | 피험자 세션 기록. 사람에게서 받은 자료라 저장소에 넣지 않는다. | no |
| `.venv/`, `.envs` | Python 환경과 `OPENAI_API_KEY`. | no |

`outputs/` 를 ignore 하면서 `results/` 를 따로 두는 이유는 하나다. 재구성본은
LLM 이 쓴 것이라 다시 만들려면 API 비용이 들고 바이트까지 같게 재현되지도
않는다. `collect_results` 가 그것들만 골라 추적되는 자리로 옮긴다.

## 실행

서버를 한 번 띄워 두고 그대로 둔다. 모든 도구가 이 포트의 같은 루트를 본다.

```powershell
.\.venv\Scripts\python.exe -m http.server 3003 --directory .
```

재구성 루프 — 프롬프트 조립 → 모델 호출 → 검사 → fatal 을 다음 프롬프트에
되먹임, 통과하거나 예산이 끝날 때까지:

```powershell
.\.venv\Scripts\python.exe -m senior_ui.restructure --stage wireframe
.\.venv\Scripts\python.exe -m senior_ui.restructure --mock pass    # API 없이 확인
```

`--mock pass` 는 통과한다. Run 1 빌드에는 원본 숫자판의 `00` 과 금액 버튼의
`전액` 이 없는데, 원본의 숫자판·빠른 금액이 스크립트 배열이 된 뒤로 pass 는 그
배열(`window.PRESERVED.AMT_KEYS` · `QUICK`)을 읽어 그린다. Run 1 은 옛 원본의
과제로 만든 빌드라 받는 사람 이름도 지금 원본의 정답(김철수)으로 바꿔 끼운다
(`model.NAME_SWAP`). 통과하므로 `designer_brief.md` 가 생기고
승격도 일어나지만, mock 은 기본으로 `.mock-outputs/` 에 쓰므로
`outputs/restructured_auto.*` 는 그대로다 — 그 자리는 실제 실행만 쓴다. 다른
폴더에 쓰려면 환경변수 `SENIOR_UI_OUTPUTS` 를 준다 (주면 그것이 이긴다).

승격 이름은 과제마다 따로다. 이체는 `restructured_auto.*` · `audit_auto.json`
그대로이고, 공과금(`--task bill`)은 `restructured_auto_bill.*` ·
`audit_auto_bill.json` 이다 (`.model.html` · `.plan.json` · `.diagnosis.json` ·
`.designer_brief.md` 와 실행 이름 사본도 같은 규칙 — `loop.promoted_name`). 두
과제를 번갈아 돌려도 한 과제의 "지금 쓰는 재구성본" 이 다른 과제 것으로 덮이지
않는다. 대시보드 색인은 audit 이 비교한 원본으로 과제를 알아보고 (`task`),
같은 id 의 행은 실행 폴더 이름으로 가른다.

`PYTHONUTF8=1` 은 더 이상 필요 없다. 모든 명령줄이 맨 앞에서
`senior_ui._cli.setup_stdout()` 을 불러 stdout 을 UTF-8 로 맞춘다.

종료 코드는 `0` = 통과한 빌드가 있다, `1` = 전부 실패, `2` = 아예 돌지 못했다
(레이트 리밋 · API 가 요청을 거절함 · 인프라 예산 소진 · 시작 자체를 못 함).
떨어진 빌드는 다시 만들고, 돌지 못한 실행은 다시 만들 것이 없다.

한 실행의 모든 것이 `outputs/restructure_auto/<타임스탬프>/` 에 남는다 — 보낸
프롬프트 전문, 받은 답 전문, 시도별 html·흐름·검사 결과, 화면별 스크린샷,
`run.log`, `summary.json`. 모델을 바꾸는 법과 처음 쓰는 모델을 먼저 확인하는 명령 둘
(`--list-models` · `--probe`)은 아래 "모델 바꾸기".

검사기만 따로 돌리기:

```powershell
.\.venv\Scripts\python.exe -m senior_ui.audit `
   --flow flows\run4.json `
   --build http://localhost:3003/results/restructured_run4.html `
   --build-file results\restructured_run4.html `
   --stage wireframe --out outputs\audit_run4.json
```

나머지:

```powershell
.\.venv\Scripts\python.exe -m senior_ui.viewer.build_index --print    # 뷰어 색인
.\.venv\Scripts\python.exe -m senior_ui.collect_results               # outputs -> results
.\.venv\Scripts\python.exe -m senior_ui.experiment.server             # 대시보드 서버 (또는 시작.bat)
.\.venv\Scripts\python.exe -m senior_ui.experiment.report             # 세션 집계
```

### 모델 바꾸기

기본 모델은 `senior_ui/config.py` 의 `DEFAULT_MODEL` 한 곳에 있다 (지금 `gpt-4o`).
한 번만 바꿔 돌리려면 `--model` 을 준다. 정하는 순서는 `--model` → 환경 변수
`RESTRUCTURE_MODEL` → `DESIGNREPAIR_MODEL` → `config.DEFAULT_MODEL` 이다
(`loop.model_choice`). `.envs` 에 남은 환경 변수가 기본값을 이길 수 있으므로,
어디서 왔는지가 run.log 첫 줄(`model=… (출처 …)`)과 `summary.json` 의
`model_source` 에 남는다. API 가 실제로 답한 판 이름(`gpt-4o` 는 날짜가 붙은
판으로 풀린다)은 호출마다 `model: 응답 모델 …` 줄과 `summary.response_models` 에
남는다.

```powershell
.\.venv\Scripts\python.exe -m senior_ui.restructure --model gpt-5 --reasoning-effort medium
```

**처음 쓰는 모델은 먼저 확인 명령 둘로 본다.** 둘 다 실행 폴더를 만들지 않고,
결과를 화면과 `outputs/model-probe.log` (덧붙임) 에 쓴다. 키는 루프와 같이
`.envs` 또는 환경에서 읽는다. 종료 코드 `0` = 확인함, `2` = 키 없음 · API 거절 ·
연결 실패.

```powershell
# 이 키로 쓸 수 있는 gpt- 모델 (models.list, 요금 없음)
.\.venv\Scripts\python.exe -m senior_ui.restructure --list-models

# 아주 짧은 요청 하나 (출력 16 토큰) - 분당 한도 · 실제 모델 · 거절된 인자
.\.venv\Scripts\python.exe -m senior_ui.restructure --probe gpt-5
```

- `--list-models` 는 `gpt-` 로 시작하는 것만 이름 순서(`gpt-5.2` < `gpt-5.10`)로
  보이고, 옆에 도구가 그 모델을 어떻게 부를지(chat/responses · 추론형 여부, 표에
  없으면 "모름")와 가격표가 채워졌는지를 적는다. o 계열(`o3` 등)은 개수만 센다.
- `--probe <모델>` 은 **실제 실행과 같은 방식으로** 보낸다 (`model.call_model`,
  `--api` · `--reasoning-effort` · `--temperature` · `--seed` 를 따른다). 보낸 인자,
  지원하지 않는 인자 오류가 있었는지, 실제 모델 이름, 응답 헤더의 분당 토큰 한도
  (남은 양) · 분당 요청 한도, 끝난 모양(출력 · 생각 토큰)을 보인다. 인자가
  거절되면 그것을 빼고 한 번 더 보낸다 — 400 은 요금이 없으므로 요금이 드는
  요청은 하나다. 추론형은 16 토큰을 생각에 다 쓰고 `length` 로 끝날 수 있는데,
  확인 명령에서는 정상이다.

**모델마다 부르는 방식** (`model.profile_for`, 표는 `model.FAMILIES`):

| 모델 | API | 길이 인자 | temperature | seed | reasoning_effort |
|---|---|---|---|---|---|
| `gpt-4o*` · `gpt-4.1*` | Chat Completions | `max_completion_tokens` | 보냄 | 보냄 | — |
| `o1` · `o3` · `o4-mini` · `gpt-5` 이후 | Chat Completions | `max_completion_tokens` | **안 보냄** | 보냄 | `--reasoning-effort` 를 줄 때만 |
| `…-pro` · `codex` · `deep-research` | **Responses** | `max_output_tokens` | 안 보냄 | 없음 | `reasoning.effort` |
| 표에 없는 모델 | gpt-4o 처럼 | `max_completion_tokens` | 보냄 | 보냄 | — (run.log 에 경고) |

- 모델이 `unsupported_parameter` / `unsupported_value` 로 거절한 인자가 `temperature`
  · `seed` · `reasoning_effort` 따위면 빼고 다시 보낸다. 뺀 것은 로그와
  `calls[].dropped` 에 남는다. 보내지 않은 temperature · seed 는 재현 기록에
  `null` 로 남는다 (모델의 기본값이 쓰였다).
- `--api chat|responses` 로 표의 API 를 덮을 수 있다. OpenAI 는 추론형에
  Responses 를 권하지만, 이 도구는 한 번 묻고 한 번 받으므로 Responses 가 이어 주는
  생각 항목을 쓸 일이 없어 Chat 을 기본으로 둔다 — gpt-4o 실행과 같은 모양
  (`finish_reason` · `seed` · `system_fingerprint`)으로 기록이 남는다.
- `--reasoning-effort` 를 주지 않으면 보내지 않는다. 모델마다 받는 값과 기본값이
  다르다 (`gpt-5` 는 minimal~high · 기본 medium, `gpt-5.1`·`5.2` 는 기본 none,
  `gpt-6.1-sol` 은 none 이 없다). 보낸 값은 `summary.model_call.reasoning_effort`.
- **생각(reasoning) 토큰은 출력 한도 안에서 쓰이고 출력 요금으로 매겨진다.**
  `--max-tokens 14000` 은 gpt-4o 의 답(3,300~3,500 토큰)에 맞춘 값이라 추론형에는
  모자랄 수 있다 — OpenAI 는 처음에 25,000 을 남겨 두라고 한다. 생각이 한도를 다
  쓰면 보이는 답이 빈 채로 잘려 오고, 그 시도는 잘림(형식 실패)으로 센다. 잘림
  줄에 생각 토큰이 적힌다. 분당 한도는 입력에 이 한도를 더해 세므로 한도를 늘리면
  "요청 하나가 분당 한도보다 크다" 에 걸리기 쉽다 — `--probe` 로 그 모델의 분당
  한도를 먼저 본다.
- 잘림 판정: Chat 은 `finish_reason == "length"`, Responses 는 `status ==
  "incomplete"` 이고 `incomplete_details.reason == "max_output_tokens"` (루프에서는
  `length` 로 맞춘다).
- 토큰 어림은 그 모델의 인코딩이다 (`tiktoken.encoding_name_for_model`). tiktoken
  0.14 는 gpt-4o · gpt-4.1 · o 계열 · `gpt-5*` 를 모두 `o200k_base` 로 알고, gpt-6
  계열은 모른다 — 그때는 `o200k_base` 로 세고 method 에 `(대체)` 를 붙인다.

**기록되는 것** (`summary.json`):

| 키 | 내용 |
|---|---|
| `model` · `model_source` | 보낸 모델 이름과 그 출처 |
| `response_models` | API 가 답한 판 이름들 (mock 은 빈 목록) |
| `model_call` | 이번 실행의 부르는 방식 (API · 길이 인자 · temperature/seed 를 보냈나 · 추론형 · 인코딩 · reasoning_effort) |
| `tokens.*.reasoning` | 생각 토큰 (출력 `completion` 에 포함된 몫) |
| `attempts[].calls[].ratelimit` · `ratelimit` | 호출마다의 응답 헤더 `x-ratelimit-limit-tokens` · `-remaining-tokens` · `-limit-requests`, 그리고 마지막 값 |
| `cost` | 시도별·전체 예상 금액 (USD) |

**가격 표**는 `senior_ui/config.py` 의 `MODEL_PRICES` 한 곳이다 — 100만 토큰당
`{"input", "output"}`. `gpt-4o` (2.50 / 10.00) 만 채워 두었고 나머지는 `None` 이다.
비어 있으면 금액은 `null` 이고 run.log 끝에 "가격표에 … 가 비어 있다" 가 남는다.
이름은 `--model` 에 주는 그대로 찾는다 (날짜 붙은 판은 따로 적는다). 금액 = 입력 ×
input + 출력 × output 이고, 출력은 생각 토큰을 포함하므로 따로 더하지 않는다.
캐시된 입력의 할인은 넣지 않았다 — 상한 쪽 어림이다.

출처 (2026-10 확인): [Reasoning models](https://developers.openai.com/api/docs/guides/reasoning)
· [Using the latest model](https://developers.openai.com/api/docs/guides/latest-model)
· [Rate limits](https://developers.openai.com/api/docs/guides/rate-limits)
· [Migrate to Responses](https://developers.openai.com/api/docs/guides/migrate-to-responses)
· [Models](https://developers.openai.com/api/docs/models)
· [Pricing](https://developers.openai.com/api/docs/pricing)
· 설치된 `openai` 3.8.0 의 `types/chat/completion_create_params.py` (`max_tokens` 는
o 계열과 맞지 않는다) · `types/shared/reasoning_effort.py`.

### 입력의 선택지 데이터는 도구가 지킨다 (`window.PRESERVED`)

자동 Run 4·5 에서 LLM 은 원본의 선택지 67개를 다시 타이핑하며 3~9개로 줄였다.
프롬프트에 "하나도 빠뜨리지 마라" 를 넣어도 아홉 시도 모두 4개였다
(`docs/variance-notes.md`). 그래서 데이터는 도구가 들고 있는다.

- **뽑기** — 입력 HTML 에서 스크립트 배열로 그려지는 선택지를 이름과 원소로
  꺼낸다 (`senior_ui/restructure/preserve.py`). 선택지 집합을 모으는 방식은
  검사 I 와 같다. 마크업에 직접 쓰인 선택지(숫자판 등)는 대상이 아니다.
- **넣기** — 재설계 HTML 의 첫 스크립트 앞에
  `<script id="preserved-data">window.PRESERVED = {…}</script>` 를 넣는다.
  모델이 같은 이름을 배열 리터럴로 다시 선언하면 그 초기화 식만 참조로 바꾼다 —
  선언을 지우면 그 이름을 쓰는 코드가 `ReferenceError` 로 죽고, 그대로 두면
  모델이 타이핑한 짧은 목록이 이긴다. 바꾼 이름은 `run.log` 와 `summary.json`
  에 남는다.
- **참조 검사** — 스크립트가 그 이름을 읽는지 형식 검사 단계에서 본다 (브라우저
  없음). 읽지 않으면 검사기까지 가지 않는다. 값을 하나도 빠뜨리지 않고 직접 쓴
  목록은 요구하지 않는다.
- **검사 I** — 그 블록(`script#preserved-data`)은 "값이 있다" 의 증거로 세지
  않는다. 세면 모델이 하나도 그리지 않아도 통과한다. 대신 걷는 동안 렌더링된
  DOM 에서 모은 선택지 값을 함께 본다. `choice_values_kept` 가 판정 기준이고
  `choice_values_selectable` 는 그중 DOM 에서 고를 수 있던 수다 — 둘이 다르면
  경고가 난다 (fatal 아님).

**모델이 만든 것과 도구가 고친 것은 파일로 갈라 둔다.** 검사기가 여는 파일과
승격되는 산출물(`outputs/restructured_auto.html`)에는 데이터 블록이 들어 있다 —
그래야 디자이너가 그 파일만 열어도 목록이 그려진다. 넣기 전의 HTML 은
`attempt_N.model.html` 로 남고 `outputs/restructured_auto.model.html` 로도
승격된다. 도구가 바꾼 자리는 파일 안에 주석으로 표시되고
(`/* 도구가 바꿨다: … */`), 그 사실은 `run.log` 와 `summary.json` 의
`attempts[n].preserved` · `final.preserved` 에 남는다.

이름은 `senior_ui/preserved.py` 한 곳에만 있다. API 없이 확인하려면
`--mock preserved-all` / `preserved-some` / `preserved-none` 셋을 돌린다.

### 오류 경로 (`error_paths`, 검사 J)

원본에는 잘못된 입력에서 뜨는 오류가 둘 있다 — 계좌번호가 틀림(`wrong-account`),
은행이 틀림(`wrong-bank`). 정답 경로만 걸으면 재설계에서 오류 처리가 통째로 빠져도
보이지 않으므로, 흐름 파일에 오류 경로를 적고 검사기가 그것을 따로 걷는다.

- **무엇이 오류인가는 과제가 정한다.** `flows/original.json` 의 `error_paths` 가
  오류마다 `about` · `condition` · 쓰는 틀린 값(`uses`) · 알림 글로 인정할 단어
  (`notice_any`)를 갖고, 틀린 값 자체는 `truth` 에 있다 (`ACCOUNT_WRONG` ·
  `BANK_WRONG`). 프롬프트(`{{ERRORS}}`)에는 조건과 자리표시자 **이름** 만 들어간다.
- **어떻게 알릴지는 모델이 정한다.** 모델의 흐름 명세는 오류마다 `from_step` ·
  `inputs` · `expect_screen` · `recover` · `back_to` 를 적는다. 팝업이 아니어도,
  같은 화면에서 바로 알려도, [다음] 을 끄고 이유를 보여도 된다.
- **검사 J** 는 오류 경로마다 새 페이지에서 정답대로 `from_step` 까지 간 뒤 잘못된
  입력을 넣는다. `expect_screen` 에 있고 새 글이 나타나야 하며(fatal), `recover`
  뒤에 `back_to` 에 있어야 하고(fatal), `back_to` 는 오류가 나타난 화면이거나
  그보다 앞이어야 한다(fatal). 새 글에 `notice_any` 단어가 없으면 warning 이다.
  눌러 넣은 값이 화면에 되비친 것은 새 글로 세지 않는다.
- 흐름에 오류 경로가 없으면 J 는 물러난다 — 옛 흐름(Run 1~4)의 판정은 그대로다.
  재구성 루프는 과제의 오류 경로를 모두 요구한다 (빠지면 형식 검사에서 떨어진다).
- 화면 덮기 규칙은 "모든 화면은 정답 경로나 오류 경로가 지나가야 한다" 다.
- 통과한 실행의 `designer_brief.md` 에 오류 경로 표가 생기고, 걷기는 오류 상태를
  `shots/attempt_N/audit_error_<id>.png` 로 남긴다.

API 없이 확인하려면 `--mock errors-undeclared` (오류 경로를 적지 않음 → 형식 검사
실패)와 `--mock errors-unhandled` (적었지만 오류 처리가 없음 → 검사 J 실패)를
돌린다. 나머지 다섯 mock 은 Run 1 빌드에 화면 안 오류 안내를 바꿔 끼운다.

### 빼도 되는 선택지 (`flows/allowed_removals.json`)

검사 I 는 원본에 있던 선택지가 생성물에 없으면 fatal 을 낸다. 안전을 이유로
일부러 뺀 것까지 세면 고칠 수 없는 fatal 이 루프에 계속 남으므로, 흐름 파일의
`choices_removed` 로 "일부러 뺐다" 를 선언할 수 있다.

그 선언은 **연구자의 판단**이다. 그런데 재구성 루프에서는 흐름 명세를 모델이
쓴다 — 모델이 스스로 `choices_removed` 를 적으면 자기가 뺀 선택지를 자기가
면제해 검사 I 를 피해 간다. 그래서 루프는 모델이 쓴 `choices_removed` 를 지우고
(지웠다는 사실은 `run.log` 와 `summary.json` 의 시도 기록에 남는다), 허용하는
제거는 이 파일 하나에서만 읽어 **검사 직전에** 흐름에 합친다.

```json
{
  "transfer": {
    "quick": {"values": ["all"], "reason": "왜 빼도 되는지 — 반드시 적는다"}
  }
}
```

지금은 비어 있다 (`{"transfer": {}}`). 무엇을 넣을지는 연구자가 정한다. 모양이
틀린 파일은 조용히 무시되지 않고 실행이 멈춘다 — 적어 두었는데 무시되면
연구자는 적었다고 믿고 결과는 다르게 나온다.

## The auditor

`python -m senior_ui.audit` drives the original and the build under test through
the same 8-screen task and diffs them. It prints machine-readable JSON and exits
0 only when nothing fatal fired, so it can gate a regenerate-on-failure loop.

Exit 1 means it audited the build and the build failed. Exit 2 means the audit
itself could not run - inputs or flow unreadable, no browser, anything that
stops the drive - and the JSON then carries that reason as its single fatal.
The caller has to tell those two apart: a build that failed gets regenerated, an
auditor that could not run does not.

### Counting fatals across runs

A task that stops early fails every screen after the stop, so a raw fatal count
rewards builds that get further and punishes ones that stall at screen two -
which makes the number useless for comparing runs. The report therefore splits
them:

| field | meaning |
|---|---|
| `fatal_root` | independent failures |
| `fatal_derived` | "never reached", caused by the stop recorded in `stopped_at` |
| `fatal_duplicates_removed` | same (check, screen, detail) seen more than once, because the flow revisits a screen |

Compare `fatal_root` between runs; `fatal_total` is the sum as before. Derived
findings carry `derived_from` naming the screen that stopped the task.

### Flow files: two ways to enter text

A flow's `type` action works with either input style, and the selector says
which.

```json
{"type": "{ACCOUNT}", "key": "[data-action='acc-num'][data-v='%s']"}   // 숫자판
{"type": "{ACCOUNT}", "key": "#acc-input"}                             // 입력 칸
```

A `%s` means there is one button per digit, and the auditor clicks them in turn.
No `%s` means the selector addresses a field, and the auditor calls `fill()`
once. A design with a real `<input>` should use the second form.

Models often write the first form while building the second -
`"input[data-action='x'][data-v='%s']"` - because the example they read showed a
keypad. Dropping the `%s` attribute from that selector leaves a real element; if
it is an `<input>` or `<textarea>`, the auditor fills it and records what it did
in `metrics.flow_notes`. It does not silently accept the mismatch.

| | Check | Severity |
|---|---|---|
| A | 8 screens reached, amount round-trips, `data-action`/`id`/`data-screen` preserved | fatal |
| B | displayed values match what was entered; no injected `alert()`/`onclick`; no hardcoded numbers | fatal |
| C | `data-action` with no branch in the handler; `data-action` that disappeared | fatal |
| D | low-contrast count must not grow; new text must not rely on inherited colour; an already-low-contrast element must not gain readable text | warning |
| E | overlapping text, content spilling out of its box, newly wrapping text, screens much taller | warning |
| F | English words the original did not have (runtime and markup-only) | warning |
| G | `.x` and `.x.on` must still render differently | warning |
| H | classes the markup uses that no stylesheet defines | warning |
| I | values the original offered as choices must still exist somewhere in the build | fatal |

H is not in the original brief. It was added because it is the shared root cause
of two rendering failures: example1's `bg-primary`/`text-primary` and the
transfer run's `sr-only`. A class no stylesheet defines does nothing, so a label
meant to be hidden shows up and a colour meant to be applied never lands.

One module per check under `senior_ui/audit/checks/`, each with a single
`run(ctx)` and a docstring saying what that check does and does not see.
`core.py` only orchestrates; `context.py` holds the inputs every check shares;
the JS that runs inside the page lives in `probes.py`; `flow.py` loads and
validates a flow file; `drive.py` walks the page with Playwright.

The JSON is for machines. `python -m senior_ui.audit.report` turns any number of
those files into one side-by-side Markdown table (overview, per-check A–I, the
metrics behind each check, what was stood down, and with `--details` every
finding):

```powershell
.\.venv\Scripts\python.exe -m senior_ui.audit.report `
   Run1=results\audit_restructured.v3.json Run2=results\audit_run2.v3.json `
   Run3=results\audit_run3.v3.json Run4=results\audit_run4.v3.json `
   --details --out results\audit-report.md
```

Run 4 is audited at the wireframe stage (`--stage wireframe`); the other three
use the default, styled. Each run keeps the stage its earlier report used.

The `.v3.json` reports are the four runs re-audited after the screen-measurement
and robustness fixes (`fix/audit-accuracy-2`); they are the current numbers. The
`.v2.json` ones are from after the counting fixes (`fix/audit-counting`), and the
files without a suffix are older still - their `fatal_total` is 0 even where the
fatal list is not empty, which is the bug those fixes removed. All three are kept
as they were.

Known gaps, both real: it cannot tell that `☆` labelled "선택됨" is factually
inverted (that needs a declared class↔label mapping), and it has no
duplicate-text check, so `confirm`'s doubled "수수료 무료" passes.

## Two audit stages

Because the tool emits a wireframe first and a styled build later, the checks
split in two. The stage is one argument on the auditor's own CLI - there is no
separate wrapper.

| stage | checks | why |
|---|---|---|
| `wireframe` | A 과제 완주 · B 표시 정확성 · C 죽은 컨트롤 · F 언어 · I 선택지 보존 · J 오류 경로 | contrast, layout, state colour and undefined classes are about detail nobody has filled in yet |
| `styled` | A~J | everything |

```powershell
.\.venv\Scripts\python.exe -m senior_ui.audit `
   --flow flows\restructured.json `
   --build http://localhost:3003/results/restructured_transfer.html `
   --build-file results\restructured_transfer.html --stage wireframe
```

The stage can also live in the flow file as `"stage": "wireframe"`; the flag
wins. A flow with neither runs everything, so existing flows behave as before.
Dropped checks are recorded in `checks_stood_down` with the reason, the same
place the auditor already notes what it stood down.

## The viewer

`시작.bat` (or `python -m senior_ui.experiment.server`) serves the dashboard on
127.0.0.1 - and only what the dashboard reads - then opens
**`web/dashboard.html`** - four pages for checking where things stand
while working:

| | |
|---|---|
| 대시보드 | one row per build: passed, fatal, warning, screens, low-contrast before→after, flow |
| 화면 비교 | 2-4 builds side by side at 390px, each with its own screen picker. Screen names differ between designs (original `account` vs Run 1 `accno`+`bank`), so nothing is auto-synced. A screenshot mode swaps the iframes for the png in `outputs/shots`, which needs no server and shows the state as captured. |
| 검사 결과 | audits side by side, folded per check A-J. Findings link to that screen's screenshot; stood-down checks say why; the metric table is folded away because a count is not a grade. |
| 변경 추적 | the changelog's changes with rule filters, and all 46 KB rules split by whether a table actually cites them |

It reads one file, `outputs/index.json`, written by
**`python -m senior_ui.viewer.build_index`**. Builds are discovered, not listed:
each audit JSON records the URL of the build it drove and the flow it used, so a
new build with its own audit appears without editing anything. Screenshots are
matched by flow name, then build id, then the older flat `before_`/`after_`
convention.

```powershell
.\.venv\Scripts\python.exe -m senior_ui.viewer.build_index --print
```

The "다시 읽기" button asks the server to rebuild the index first, so editing a
file and pressing it is enough. `builds[].attempts` is reserved for the
generate-audit-regenerate loop and is empty until that lands.

Two numbers the viewer deliberately keeps apart: the changelog's tables cite
**26** of the 46 rules, while the document claims **33** are met. The extra 7 are
the author's own judgement with no table behind them, which the document itself
flags as optimistic.

## 테스트

구조를 정리해도 동작이 그대로인지 파일 비교로 확인한다. 기준값은
`tests/baseline/` 에 있고, 입력은 `results/` 의 고정된 파일이다.

```powershell
.\.venv\Scripts\python.exe -m pytest                # 브라우저 없음 (32건, 몇 초)
.\.venv\Scripts\python.exe -m pytest -m browser     # 실제로 다시 걷는다 (18건, 2분 15초)
```

`pytest.ini` 의 `addopts` 가 `-m "not browser"` 라서 기본 실행은 브라우저를
띄우지 않는다. `-m browser` 는 Playwright 로 원본과 재구성본을 실제로 다시 몰고
다니며 저장된 스냅샷과 비교한다. 서버는 테스트가 직접 띄운다.

**기준값을 다시 뽑는 것은 동작을 의도적으로 바꿨을 때만이다.**

```powershell
.\.venv\Scripts\python.exe tests\capture_baseline.py
```

`:3003` 을 이미 누가 쓰고 있으면 캡처는 멈춘다 — 기준값은 그 포트가 서빙하는
내용에 전적으로 달려 있어서, 남이 띄운 서버를 그대로 쓰면 기준값이 무엇을
기준으로 한 것인지 알 수 없어진다. 실행마다 흔들리는 값(원본 시제품의 비밀번호
숫자판 셔플)을 어떻게 빼는지, 지금 기준값에 어떤 동작이 담겨 있는지는
`tests/README.md` 에 적혀 있다.

## 파이프라인과 그 밖에 있는 것

| | |
|---|---|
| **파이프라인** | 위의 사슬. `senior_kb.csv` 는 여기 들어가지 않는다. |
| **실험 조건** | 원본 vs 재구성본, 두 조건, 실제 고령 피험자. |
| **보관 자료** | `kb/senior_kb.csv`. 남겨 두지만 생성에는 쓰지 않는다. |

`kb/senior_kb.csv` 는 **사후 대조** 용이다 — 만들어진 설계가 결과적으로 어떤
규칙에 해당하는지 나중에 확인하는 것. 재구성본을 만들 때 모델에 주지 않았고
앞으로도 주지 않는다. 자세한 것은 `kb/README.md`.

## 알려진 문제

- 오류 팝업 화면과 '모든 화면을 흐름이 지나가야 한다' 규칙의 충돌 — 9-2 단계에서 해결

## 다른 문서

| | |
|---|---|
| `CONTINUE.md` | 지금 어디까지 왔고 무엇이 남았나. 새 세션이 먼저 읽는 한 장. |
| `experiment-guide.md` | 실험 당일 절차. 준비·진행·집계. |
| `restructure-prompt.md` | 재구성 프롬프트 템플릿. 루프가 이 파일을 읽는다. |
| `restructure-runs.md` | 손수 제작 Run 1·2·3 비교. |
| `variance-notes.md` | 같은 프롬프트를 다시 돌릴 때 무엇이 달라지는가. |
| `restructure-changelog.md` | Run 1 의 변경 내역과 KB 규칙 사후 대조. |
| `defect-types.md` | 생성물에 반복해 나타나는 결함 유형. 검사기에 넣을 후보. |
| `input-contract.md` | 앞단(스크린샷 → HTML)이 지켜야 할 입력 HTML 의 약속. 뒤쪽이 무엇을 읽고 그중 무엇이 스크린샷에서 오는가. |
