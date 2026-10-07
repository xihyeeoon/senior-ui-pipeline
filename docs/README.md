# senior-ui-pipeline

고령 사용자가 은행 앱의 과업 — 이체와 공과금 납부 (`tasks/transfer.json` ·
`tasks/bill.json`) — 을 혼자 끝낼 수 있도록 화면 구조를 LLM 으로 다시 짜고, 그
산출물을 자동으로 검사하고, 고른 시안을 실제 고령 피험자에게 돌려 보는 파이프라인.

```
캡처 → 원본 HTML → LLM 재구성 (와이어프레임) → 검사기 → C 후보 고르기
     → 화면설계서 (storyboard/) · 설명서 (designer_brief.md)
     → Flutter 더미앱의 C 조건 → 실험 (A1 · A2 · C)
```

산출물은 **와이어프레임 수준의 구조 시안**이고 시각 디테일은 디자이너가 채운다.
그 전제가 아래 모든 것을 — 특히 검사를 두 단계로 나눈 것을 — 결정한다.

**도구의 결과물은 화면설계서다. 재구성 HTML 은 검증용 속 재료다.** 루프가 만드는 HTML 은
검사기가 걸어 보고 판정하기 위한 것이고, 디자이너가 받는 것은 검사를 통과한 HTML 에서
뽑은 화면설계서(`python -m senior_ui.storyboard <실행 폴더>`)다 — 실무 와이어프레임
관례대로 와이어플로 한 장, 기능-화면 표, 화면마다 정보칸 · 로우파이 그림(회색 상자와 글자) ·
그림 위의 번호 영역 · 설명 표(영역별 요소 · 클릭 결과 주석 · 예외). 아래 '화면설계서' 절과
`docs/storyboard.md`.

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
openai(재구성 루프), tiktoken(보내기 전 토큰 어림, 없으면 글자 수로 어림),
pytest(테스트), httpx(테스트의 가짜 OpenAI 응답). 서버·세션 저장·색인은 전부 표준
라이브러리로 돈다. 빠진 것이 없는지는 테스트가 본다 (import 를 모아 대조).

LLM 을 부르는 것은 재구성 루프 하나뿐이고, 키는 `.envs` 의 `OPENAI_API_KEY=…`
또는 환경변수에서 읽는다. 검사기·뷰어·실험 서버는 키가 없어도 돈다.

## Layout

| Path | What | Tracked |
|---|---|---|
| `senior_ui/` | 이 프로젝트에서 쓴 코드 전부 — 재구성 루프, 검사기, 고르기, 화면설계서, 뷰어 색인, 실험 서버. 모두 `python -m senior_ui.…` 로 실행한다. | yes |
| `web/` | 브라우저에서 열리는 것 — `dashboard.html`(내부 확인용 4화면), `session.html`(HTML 실험 장치 - 본실험에 쓰지 않는다. `--session` 을 줄 때만 서빙된다). | yes |
| `flows/` | 흐름 파일. 검사기가 화면을 어떤 순서로 어떻게 몰고 다니는지의 명세. `original.json` 과 재구성본별 `restructured`·`run2`·`run3`·`run4`. `allowed_removals.json` 은 그것들과 다르다 — 과제별로 "빼도 되는 선택지" 를 적는 곳이고, **연구자만** 손으로 고친다 (아래 참고). `selection_rule.json` 은 C 후보를 고르는 규칙이다 (아래 'C 후보 고르기'). | yes |
| `tasks/` | 과제 정의 — `transfer.json`(이체) · `bill.json`(공과금). 프롬프트의 과제 문단과 대상 문구(`audience`), 원본 HTML · 원본 흐름, 완료 화면 값, 필수 오류 경로, 과제 밖 입구(`entrances`, 검사 K)가 과제마다 여기 있다 (`senior_ui/tasks.py`). | yes |
| `inputs/` | 파이프라인이 읽는 것. `original_transfer.html`(8화면 이체) · `original_bill.html`(8화면 공과금)이 원본 시제품이고 그 과제의 모든 갈래가 여기서 출발한다. `*.png` 는 실제 SOL 캡처라 추적하지 않는다 (실명이 보인다). | html 만 |
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

재구성 루프는 서버를 스스로 띄우고 끈다 (`senior_ui.devserver.ensure_server`). 검사기
CLI 를 여러 번 돌리거나 빌드를 브라우저로 열어 볼 때만 따로 띄워 둔다 — 이 작업 트리를
**루프백(127.0.0.1)에만** 서빙한다.

**자동 실행은 빈 포트를 잡는다 (11-9).** 재구성 루프 · `pytest` · 기준값 캡처는 실행마다
빈 포트(`config.AUTO_PORT` = 0)에 제 서버를 띄우고 끝에서 제 것만 끈다. 그래서
**같은 포트를 명시하지 않으면 동시에 돌려도 된다** — 루프 둘, 루프와 테스트, 테스트
둘. 전에는 모두 `:3003` 하나를 써서, 뒤에 시작한 쪽이 앞의 서버를 재사용하다가 앞의
쪽이 끝나며 끄면 걷던 도중에 끊겼다. 포트를 정해 쓰려면 `--port N`
(`python -m senior_ui.restructure --port 3010`, `pytest -m browser --port 3010`,
`tests/capture_baseline.py --port 3010`) — 그때는 그 포트에 떠 있는 서버를 아래의 확인
파일로 이 작업 트리일 때만 재사용한다. 사람이 띄우는 서버(아래 명령)와 대시보드
(`시작.bat`)는 `:3003` 그대로다. 주의: 같은 과제의 같은 `--mock` 을 같은 초에 두 번
띄우면 실행 폴더 이름(초 단위 시각 + 과제 + mock)이 겹친다 — 그때는 몇 초 띄워 시작한다.

```powershell
.\.venv\Scripts\python.exe -m senior_ui.devserver    # 127.0.0.1:3003, Ctrl+C 로 끈다
```

표준 라이브러리의 `http.server` 를 `--bind` 없이 띄우지 않는다 — 그러면 0.0.0.0 에
열려 같은 Wi-Fi 의 누구나 `.envs`(API 키) · `sessions/` 까지 받아 간다.
떠 있는 서버는 그것이 이 작업 트리를 서빙할 때만 재사용한다 — 작업 트리마다 다른 확인
파일 `/.devserver-id`(추적하지 않음)의 값을 대조한다. 다른 worktree 의 서버나 허용
목록만 서빙하는 대시보드 서버(`시작.bat`)가 떠 있으면 루프는 이유와 함께 멈춘다 (종료 2).

재구성 루프 — 프롬프트 조립 → 모델 호출 → 검사 → fatal 을 다음 프롬프트에
되먹임, 통과하거나 예산이 끝날 때까지:

```powershell
.\.venv\Scripts\python.exe -m senior_ui.restructure --model gpt-6.1-sol    # 기본 --stage wireframe · 예산 형식 5 · 검사 6
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

**같은 실패가 되풀이되면 예산이 남아도 멈춘다 (막힘, 11-9).** 검사까지 간 시도의
fatal 을 (검사 · 대상 · 개수)로 줄여 — 대상은 fatal 의 `action` · `error_path` ·
`screen` 중 처음 있는 것, 개수는 `missing` · `lost` 같은 목록의 길이 — 바로 앞
시도와 같으면 `stopped_reason: stuck` 으로 끝낸다. `summary.json` 의 `stuck`
(`{"attempt", "same_as", "fatal": [[검사, 대상, 개수], …]}`)과 `run.log` 의 "막힘(stuck)"
줄에 남고, 종료 코드는 1 이다. 바로 앞 시도가 형식에서 떨어졌으면 견주지 않고,
다듬기 회차는 보지 않는다. 고르기 도구는 stuck 실행을 통과하지 못한 실행으로 뺀다.
공과금 예비 실행(`20261007-103023-bill`)은 시도 3 · 4 가 같은 fatal 이었다 — 지금이면
시도 4 에서 멈춘다. API 없이 보려면 `--mock preserved-some --attempts 3` (시도 2 에서
멈춘다, 기준값 `mock_stuck.json`).

한 실행의 모든 것이 `outputs/restructure_auto/<타임스탬프>/` 에 남는다 — 보낸
프롬프트 전문, 받은 답 전문, 시도별 html·흐름·검사 결과, 화면별 스크린샷,
`run.log`, `summary.json`. 모델을 바꾸는 법과 처음 쓰는 모델을 먼저 확인하는 명령 둘
(`--list-models` · `--probe`)은 아래 "모델 바꾸기".

### 화면 보여 주기 (11-5)

모델은 이제 화면을 본다. 두 군데다.

- **보고 진단하기** (`--see`, 기본 on). 루프가 시작할 때 원본을 한 번 걸으며 화면마다
  스크린샷을 찍고 (스크롤되는 화면은 맨 위부터 창 높이씩 잘라 최대 4장, 오류 상태도),
  진단·계획 호출에 그림으로 넣는다. 그림은 `shots/original/see/`, 기록은
  `attempt_1.plan_prompt.txt` 의 그림 줄. 진단마다 `evidence_kind`(screen · code · both)를
  적게 해 `summary.plan.evidence_kinds` 로 센다. `--see off` 는 전의 동작이다.
  그림마다 이름표가 붙는다 — `원본 화면 <방문 이름>`, 흐름 걸음에 `state`(연구자가 적은
  그 상태의 이름)가 있으면 그 글자를 잇는다: `원본 화면 account#2 — 키패드 열림 —
  계좌번호 입력란을 누른 뒤`. 스크린샷 한 장은 무엇을 눌러 그 모습이 되었는지를 담지
  못하므로 상태 사이의 전환은 원본 흐름에 적고, 이 이름표가 모델에게 가는 전환 정보다
  (`see/index.json` 의 `state`, [`input-contract.md`](input-contract.md) 의 "입력
  약속"). 모델이 쓴 흐름 명세의 `state` 는 쓰지 않는다 — 형식 검사도 그 칸을 보지 않는다.
- **보고 다듬기** (`--refine N`, 기본 0 = 끔 — 2026-10-07 예비 실행 두 번에서 다듬기 전후 화면이 거의 같아 기본으로 껐다 (20261006-215902: 비평 3건 중 1건 반영, 20261007-102041: 시도 1 과 3 이 같음). 고르기 규칙 version 4 도 refine 0). 시도가 검사를 통과하면 그 빌드의
  스크린샷과 계획 · HTML · 흐름 명세를 주고 다듬게 한다. 답은 비평(json) → html → 흐름
  명세. 다듬은 빌드는 검사를 다시 통과해야 최종이 되고, 떨어지면 한 번 고치게 한 뒤
  그래도 떨어지면 직전에 통과한 빌드로 되돌린다. 기록은 `attempt_N.critique.json` ·
  `summary.refine` · 설명서의 "보고 다듬기" 절과 맨 위 "최종:" 줄. 다듬기를 끈 실행의
  설명서는 그 절이 "다듬기 안 함 (refine 0)" 한 줄이다.
  흐름 명세의 `reveal` 모양은 생성 · 다듬기 프롬프트가 같은 블록(`<!-- REVEAL -->`)을
  쓴다. 형식 검사는 배열로 온 `reveal` 을 원소마다 `action` 이 있으면
  `{action: {"at", "do"}}` 로 한 번 바꿔 받고(빈 배열은 빈 객체), 그 사실을 시도 기록의
  `reveal_from_list` 와 `run.log` 에 남긴다 — 예비 실행 두 번의 다듬기 답이 모두
  `"reveal": []` 로 형식에서 떨어져 고치기 호출을 한 번씩 더 썼다 (11-9).

호출마다 보낸 그림 수와 그림 토큰 어림이 `summary` 의 `calls[].images` ·
`estimated_images` (실제 실행이면 `measured_images` 도)에 남고, 한 호출에 그림이
`config.IMAGE_WARN_COUNT`(40)장을 넘으면 `run.log` 에 경고 한 줄을 쓴다. 그림 토큰
어림은 `config.IMAGE_TOKENS` 이고, 처음 쓰는 모델은 `--probe <모델> --image` 로
그림을 받는지와 한 장의 실측 토큰을 먼저 잰다.

API 없이: `--mock pass --mock-refine improve` (1회차에 다듬은 빌드가 통과해 최종이
된다) · `break` (다듬은 빌드와 고친 빌드가 떨어져 되돌린다) · `break-then-fix` ·
`done` (기본 - 고칠 것 없음). 긴 목록을 눌러 펼치는 설계는 `--mock reveal` (흐름
명세의 `reveal` 로 통과) · `reveal-undeclared` (같은 HTML, 검사 I 실패).

검사기만 따로 돌리기:

```powershell
.\.venv\Scripts\python.exe -m senior_ui.audit `
   --flow flows\run4.json `
   --build http://localhost:3003/results/restructured_run4.html `
   --build-file results\restructured_run4.html `
   --stage wireframe --out outputs\audit_run4.json
```

루프가 만든 빌드(모델 흐름 - `flows/` 밖의 흐름 파일)를 다시 검사할 때는 그 실행의
과제를 `--task` 로 꼭 준다. 없으면 판정하지 않고 종료 2 다. 원본(`--original`, 주지
않으면 `:3003` 의 과제 원본)을 읽지 못해도 판정하지 않고 종료 2 다. 판정 기준(정답 · 완료
화면 값 · 오류 경로)은 흐름이 아니라 과제에서 오고, 루프와 같은 판정 입력
(`senior_ui/audit/inputs.py` 의 `judged_flow`)을 거친다.

```powershell
.\.venv\Scripts\python.exe -m senior_ui.audit --task bill `
   --flow outputs\restructure_auto\<실행>\attempt_1.flow.json `
   --build http://localhost:3003/outputs/restructure_auto/<실행>/attempt_1.html `
   --build-file outputs\restructure_auto\<실행>\attempt_1.html
```

나머지:

```powershell
.\.venv\Scripts\python.exe -m senior_ui.storyboard outputs\restructure_auto\<실행> --mock   # 화면설계서
.\.venv\Scripts\python.exe -m senior_ui.viewer.build_index --print    # 뷰어 색인
.\.venv\Scripts\python.exe -m senior_ui.collect_results               # outputs -> results
.\.venv\Scripts\python.exe -m senior_ui.experiment.server             # 대시보드 서버 (또는 시작.bat)
.\.venv\Scripts\python.exe -m senior_ui.experiment.report             # 세션 집계
```

### 모델 바꾸기

기본 모델은 `senior_ui/config.py` 의 `DEFAULT_MODEL` 한 곳에 있다 (지금 `gpt-6.1-sol`,
12번 본 실행의 모델 — 고르기 규칙의 `gates.model` 과 같다). 그래도 실행 명령에는
`--model gpt-6.1-sol` 을 적는다 — 명령만 보고 조건을 알 수 있게. 한 번만 바꿔 돌리려면
`--model` 을 준다. 정하는 순서는 `--model` → 환경 변수
`RESTRUCTURE_MODEL` → `config.DEFAULT_MODEL` 이다 (`loop.model_choice`).
`DESIGNREPAIR_MODEL` 은 더 읽지 않는다 (연구에서 뺀 갈래의 이름). `.envs` 에 남은
환경 변수가 기본값을 이길 수 있으므로, 어디서 왔는지가 run.log 첫 줄(`model=… (출처 …)`)과
`summary.json` 의 `model_source` 에 남는다. `--mock` 실행은 `.envs` 도
`RESTRUCTURE_MODEL` 도 읽지 않는다 (`--model` 은 듣는다) — mock 기준값이 PC 마다
달라지지 않게. run.log 둘째 줄에 그 사실이 남는다. API 가 실제로 답한 판 이름(`gpt-4o` 는 날짜가 붙은
판으로 풀린다)은 호출마다 `model: 응답 모델 …` 줄과 `summary.response_models` 에
남는다.

```powershell
.\.venv\Scripts\python.exe -m senior_ui.restructure --model gpt-6.1-sol
.\.venv\Scripts\python.exe -m senior_ui.restructure --model gpt-6-astra --task bill --reasoning-effort high
```

**실행 설정 — 추론형이면 기본값이 다르다.** 아래 셋은 주지 않으면 부르는 방식이
추론형인지(`model.profile_for`)로 고른다. 값은 모두 `senior_ui/config.py` 한 곳에
있다. gpt-4o(와 표에 없는 모델)의 값과 동작은 전과 같다 — 이체 기준값이 그것으로
뽑혀 있다.

| 설정 | 인자 | gpt-4o | 추론형 (`gpt-6.1-sol` · `gpt-6-astra` …) | config |
|---|---|---|---|---|
| 생성 호출의 출력 길이 | `--max-tokens` | 14,000 | **32,000** | `OUTPUT_CAPS` |
| 진단·계획 호출의 출력 길이 | `--plan-max-tokens` | 6,000 | **25,000** | `OUTPUT_CAPS` |
| 호출 사이 대기 | `--delay` | 60초 | **5초** + 남은 토큰이 모자랄 때만 더 | `DELAY` |
| 생각에 쓸 노력 | `--reasoning-effort` | 보내지 않음 | **`medium`** 을 늘 보냄 | `DEFAULT_REASONING_EFFORT` |

- **출력 길이.** 추론형은 생각 토큰도 이 상한 안에서 쓴다. gpt-4o 의 답은
  3,300~3,500 토큰이었고 14,000 · 6,000 은 분당 30,000 에 맞춰 낮춘 값이라, 추론형이
  생각을 다 쓰면 보이는 답이 빈 채로 잘려 온다. OpenAI 는 "처음 실험할 때는 생각과
  출력에 적어도 25,000 을 남겨 두라" 고 한다 — 진단·계획은 그 최소, 생성은 넉넉히
  32,000. 상한은 쓴 만큼만 요금이 매겨진다. 쓴 값과 출처는 run.log 의 `model:
  max_tokens …` 줄, 호출마다는 `calls[].max_tokens`.
- **대기.** 60초는 gpt-4o 의 분당 30,000 때문이었다 (원본 HTML 이 두 호출에 다
  들어간다). gpt-6.1-sol · gpt-6-astra 는 분당 500,000 이다 (2026-10-06 `--probe`).
  추론형은 5초만 두고, 호출 직전에 직전 응답 헤더의 남은 토큰(그 뒤 지난 시간 동안
  찬 몫, 초당 한도/60 을 더해)을 이번 요청(예상 입력 + max_tokens)과 견준다. 적을
  때만 모자란 만큼 기다린다 (`model.wait_for_tokens`, 최대 60초). 기다리면 run.log
  에 `대기 Ns — 남은 토큰 …` 줄과 `calls[].waited_for_tokens` 가 남는다. gpt-4o 는
  헤더를 보지 않고 늘 60초다. `--delay` 를 주면 고정 대기만 그 값이 되고, 추론형의
  남은 토큰 확인은 그대로 한다.
- **reasoning_effort.** 주지 않았을 때 모델의 기본값에 맡기면 그 값이 어디에도 남지
  않고, 모델이 기본값을 바꾸면 같은 명령이 다른 조건으로 돈다. 그래서 추론형이면
  늘 보낸다 (`loop.effort_choice`). 보낸 값과 출처가 run.log **첫 줄**
  (`model=gpt-6.1-sol (출처 --model) · reasoning_effort=medium (출처
  config.DEFAULT_REASONING_EFFORT)`)과 `summary.model_call.reasoning_effort` 에
  남는다. gpt-4o 의 첫 줄은 전과 같다. `--probe` 는 줄 때만 보낸다 (16 토큰짜리
  확인 요청에 생각을 붙이지 않는다).

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
| `o1` · `o3` · `o4-mini` · `gpt-5` 이후 | Chat Completions | `max_completion_tokens` | **안 보냄** | 보냄 | 늘 보냄 — 주지 않으면 `medium` |
| `…-pro` · `codex` · `deep-research` | **Responses** | `max_output_tokens` | 안 보냄 | 없음 | `reasoning.effort` 로 늘 보냄 |
| 표에 없는 모델 | gpt-4o 처럼 | `max_completion_tokens` | 보냄 | 보냄 | — (run.log 에 경고) |

- 모델이 `unsupported_parameter` / `unsupported_value` 로 거절한 인자가 `temperature`
  · `seed` · `reasoning_effort` 따위면 빼고 다시 보낸다. 뺀 것은 로그와
  `calls[].dropped` 에 남는다. 보내지 않은 temperature · seed 는 재현 기록에
  `null` 로 남는다 (모델의 기본값이 쓰였다).
- `--api chat|responses` 로 표의 API 를 덮을 수 있다. OpenAI 는 추론형에
  Responses 를 권하지만, 이 도구는 한 번 묻고 한 번 받으므로 Responses 가 이어 주는
  생각 항목을 쓸 일이 없어 Chat 을 기본으로 둔다 — gpt-4o 실행과 같은 모양
  (`finish_reason` · `seed` · `system_fingerprint`)으로 기록이 남는다.
- 모델마다 받는 reasoning_effort 값과 기본값이 다르다 (`gpt-5` 는 minimal~high ·
  기본 medium, `gpt-5.1`·`5.2` 는 기본 none, `gpt-6.1-sol` · `gpt-6-astra` 는
  low~max). 기본으로 보내는 `medium` 이 거절되면 위의 규칙대로 빼고 다시 보내고
  `calls[].dropped` 에 남는다 — 그때는 다른 값을 `--reasoning-effort` 로 준다.
- **생각(reasoning) 토큰은 출력 한도 안에서 쓰이고 출력 요금으로 매겨진다.** 생각이
  한도를 다 쓰면 보이는 답이 빈 채로 잘려 오고, 그 시도는 잘림(형식 실패)으로 센다.
  잘림 줄에 생각 토큰이 적힌다 (생각이 90% 이상이면 `--max-tokens` 를 늘리거나
  `--reasoning-effort` 를 낮추라는 말도). 분당 한도는 입력에 이 한도를 더해 세므로,
  한도가 작은 계정·모델이면 "요청 하나가 분당 한도보다 크다" 에 걸릴 수 있다 —
  `--probe` 로 그 모델의 분당 한도를 먼저 본다.
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
| `model_call` | 이번 실행의 부르는 방식 (API · 길이 인자 · temperature/seed 를 보냈나 · 추론형 · 인코딩 · reasoning_effort — 추론형이면 늘 값이 있다, gpt-4o 는 `null`) |
| `tokens.*.reasoning` | 생각 토큰 (출력 `completion` 에 포함된 몫) |
| `attempts[].calls[].max_tokens` | 그 호출의 출력 길이 (분당 한도에 맞추느라 줄였으면 `max_tokens_sent` 도) |
| `attempts[].calls[].ratelimit` · `ratelimit` | 호출마다의 응답 헤더 `x-ratelimit-limit-tokens` · `-remaining-tokens` · `-limit-requests`, 그리고 마지막 값 |
| `attempts[].calls[].waited_for_tokens` | 남은 토큰이 모자라 그 호출 전에 더 기다린 초 (추론형, 기다렸을 때만) |
| `cost` | 시도별·전체 예상 금액 (USD) |
| `audience` | 프롬프트가 말한 대상 — 과제 파일의 `audience` (지금 "60대 이상 고령 사용자"). 과제 설명과 다듬기 프롬프트의 `{{AUDIENCE}}` 자리에 들어간다. 값을 바꾸는 것은 연구자 결정이다 (11-8) |
| `original` · `original_sha256` | 이 실행이 쓴 원본 HTML (루트 기준 경로)과 그 지문 — 줄끝을 LF 로 맞춘 sha256 (`tasks.fingerprint`). `run.log` 첫 줄에도 `original_sha256=… (경로)` 로 남는다. 시작하지 못한 실행에도 있다. 고르기의 문지기 `original` 이 지금 원본과 견준다 (11-11) |
| `entrance_distance` | 최종 빌드의 과제 밖 입구마다 원본 · 생성물에서 처음 누를 수 있게 보인 방문(`visit`), 그 입구를 보려고 누른 펼치기 횟수(`reveal`, 바로 보이면 0, 펼치기로 보였으면 그 reveal 이름 `via`), 그 화면 맨 위에서 입구 전체가 창 안에 들어오기까지의 스크롤 거리(`scroll_px`, 첫 화면 안이면 0). 보이지 않았으면 `null`. 검사 K 의 지표를 옮긴 것이고 **기록만** 한다 — 판정 · 고르기 문지기에 쓰지 않고 기준선 · 합격선도 없다. 남아 있는 것과 찾을 수 있는 것은 다르다 (Findlater, McGrenere 2007). 설명서의 "과제 밖 입구" 표가 같은 값이다 (11-8) |

**가격 표**는 `senior_ui/config.py` 의 `MODEL_PRICES` 한 곳이다 — 100만 토큰당
`{"input", "output"}`. 채운 것은 셋이다 — `gpt-4o` 2.50 / 10.00, `gpt-6.1-sol`
2.00 / 10.00, `gpt-6-astra` 10.00 / 50.00. 뒤의 둘은 2026-10-06 공식 가격표의
Standard 단계 "Short context"(입력 272K 이하) 값이다. 나머지는 `None` 이다.
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
  목록은 요구하지 않는다. 과제가 선택지가 아니라고 선언한 무리만 받치는 이름도
  요구하지 않는다 (아래 '선택지가 아닌 무리').
- **검사 I** — 그 블록(`script#preserved-data`)은 "값이 있다" 의 증거로 세지
  않는다. 세면 모델이 하나도 그리지 않아도 통과한다. 대신 걷는 동안 렌더링된
  DOM 에서 모은 선택지 값을 함께 본다. **무리는 원본이 정하고, 생성물에서는 놓인
  모양과 상관없이 센다** — 원본에서 무리였던 이름(`i_choices.original_groups`, 과제가
  선택지가 아니라고 선언한 이름은 뺀다)의 요소는 생성물에서 형제가 없어도 모두 세고,
  원본에서 무리가 아니던 이름은 형제 둘 이상일 때만 무리다 (11-9b).
  `choice_values_kept` 는 남아 있는 값의 수이고, `choice_values_selectable` 는 그중 걷는
  동안(정답 걸음 · reveal 뒤) 어느 상태에서 **누를 수 있게 보인** 값의 수다 — 그려져 있고
  크기 > 0, 자신이나 조상이 display · visibility · opacity 로 숨지 않았고 disabled 가
  아니다 (`probes.CHOICE_SHOWN`, 스냅샷의 `choices_shown`). 원본을 걷는 동안 원본에서
  보이던 값이 생성물에서 어느 상태에서도 보이지 않으면 fatal 이다 (11-8 2-3,
  `choice_values_not_selectable`). 전에는 문서 안에만 있으면 통과했다 — 공과금 실행
  20261007-201603-bill 의 전체메뉴는 분야 칸을 눌러도 닫힌 분류 제목만 보였다. 원본도
  걷는 동안 보이지 않던 값(이체 원본의 [증권사] 탭 29개 — 원본 흐름이 그 탭을 누르지
  않는다)은 검사 K 와 같은 규칙으로 요구하지 않는다 (`choice_values_shown_in_original` 이
  요구한 수, 차이는 경고). 그 값까지 요구하려면 원본 흐름에 탭을 여는 `reveal` 을 적는다.
  보이는 값의 수집이 없는 옛 스냅샷은 전처럼 DOM 에 있으면 고를 수 있다고 본다.

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
  뒤에 `back_to` 에 있어야 하고(fatal), `back_to` 는 정답 경로(`steps`)에 있는
  화면이고 완료 화면이 아니어야 한다(fatal) — 오류가 나타난 화면보다 뒤여도 된다
  (계좌 화면에서 은행 오류를 알리고 은행 고르기 화면으로 보내기). 새 글에
  `notice_any` 단어가 없으면 warning 이다.
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

### 선택지가 아닌 무리 (과제 파일의 `not_choices`)

검사 I 는 원본에서 같은 `data-action` 을 가진 형제 2개 이상을 선택지 무리로 본다.
그 규칙은 누르면 스크롤만 하는 표지판 · 탭도 선택지로 센다 — 공과금 원본의
`menu-chip`(60) · `menu-tab`(7) 은 `scrollMenuTo` 로 메뉴 항목(`menu-item`)을
찾아가는 수단이지 고르는 대상이 아니다. 예비 실행(`20261007-103023-bill`)의 시도
2 · 3 · 4 가 이 둘 때문에 같은 이유로 떨어졌다. 그래서 과제 파일이 "선택지가
아니다" 를 이유와 함께 선언한다 (연구자 결정, 2026-10-07).

```json
"not_choices": {"menu-chip": "분류로 스크롤하는 표지판 — 찾아가는 수단",
                "menu-tab": "분야로 스크롤하는 탭 — 찾아가는 수단"}
```

- 위의 `allowed_removals` 와 뜻이 다르다 — 그쪽은 "선택지인데 이 값은 빼도 된다",
  이쪽은 "이 무리는 처음부터 선택지가 아니다" 다. 섞지 않는다.
- 판정 입력(`audit.inputs.judged_flow` · 연구자 흐름은 `flow.load_flow`)이 과제의
  선언을 흐름에 붙인다. 모델이 흐름 명세에 `not_choices` 를 적으면 버리고
  `model_claims_dropped` 에 남긴다.
- 검사 I 는 선언된 무리를 판정에서 빼고 지표 `choice_groups_not_choices`
  (`{무리: {"values": 원본의 값 수, "reason": 이유}}`)와 `checks_stood_down` 에 남긴다.
  `choice_groups_original` · `choice_values_kept` 에는 들어가지 않는다.
- 그 무리만 받치는 배열(공과금의 `MENU_TABS`)도 `window.PRESERVED` 에는 그대로
  들어간다 — 모델이 써도 되고 안 써도 되는 데이터다. 프롬프트의 "빠뜨리지 말고
  참조하라" 와 형식 검사의 참조 요구에서만 빠진다.
- 설명서의 "선택지가 아니라고 선언한 무리" 표에 무리와 이유가 나온다.
- 이체 과제는 선언할 것이 없다 (`"not_choices": {}`) — `tab-bank` · `tab-sec` 는
  이름이 달라 한 무리가 아니다. 칸이 없는 과제 파일도 빈 선언이다. 이유가 빈
  선언은 받지 않고 멈춘다.

## 화면설계서 (`python -m senior_ui.storyboard`)

검사를 통과한 실행 하나에서 디자이너가 볼 설계서를 만든다. 실행 폴더를 **읽기만** 하고
(재구성 · 검사 · 고르기는 바꾸지 않는다) `<실행 폴더>/storyboard/` 에 `index.html` ·
`storyboard.pdf`(Chromium 인쇄, 가로 A4) · 화면별 그림 · `storyboard.json`(그림 말고는 이것으로
다시 그린다)을 쓴다. 통과하지 못한 실행은 만들지 않고 이유를 찍는다 (종료 2).

```powershell
.\.venv\Scripts\python.exe -m senior_ui.storyboard outputs\restructure_auto\<실행> --model gpt-6.1-sol
.\.venv\Scripts\python.exe -m senior_ui.storyboard outputs\restructure_auto\<실행> --mock    # API 없이
# 이미 모델로 만든 설계서를 새 형식으로 - 영역 답을 그대로 쓰고 모델을 부르지 않는다
.\.venv\Scripts\python.exe -m senior_ui.storyboard outputs\restructure_auto\<실행> `
    --regions-from outputs\restructure_auto\<실행>\storyboard\storyboard.json
```

차례는 맨 앞장 · 와이어플로(정답 경로는 번호 붙은 화살표, 오류는 점선 갈래와 되돌아가는
화살표, 화살표 옆에 누른 것) · 기능-화면 표("기능은 줄이지 않는다" 의 확인표 - ● 바로 보임 /
○ 펼쳐야 보임) · 화면마다 한 장(맨 위 정보칸 한 줄 - 화면 ID · 화면 이름 · 경로 · 원본 화면 ·
조건, 조건별 장은 [오류] · [펼침] 꼬리표). 그림은 로우파이다 - 배경 · 채우기 · 그림자 · 둥근
모서리를 없애고 누를 것과 묶음 상자는 1px 회색 테두리, 꺼진 버튼은 점선. 위치 · 크기 · 글자
크기 · 굵기는 설계 결정이므로 그대로 둔다 (11-12b).

"누르면 어디로 가는가" 는 **도구가 실제로 눌러서 확인한 것만** 적는다 — 요소마다 새
페이지에서 그 상태까지 흐름 명세대로 다시 걸은 뒤 최종 HTML 을 누른다. 모델은 영역 묶기와
설명 문장만 쓴다 (실행마다 호출 한 번, 어긋나면 한 번 더, 그래도면 "기타"). 설계서의 칸마다
출처가 붙는다:

| 칸 | 출처 |
|---|---|
| 화면 ID · 와이어프레임 그림 · 요소 번호/글자/위치 | 도구 확인 (흐름 명세대로 걸어 찍고 모은 것) |
| **요소와 동작** — "클릭 시 → [scr-amount] 이동" · "클릭 시 → 같은 화면에서 '…' 나타남" · "클릭해도 변화 없음" · "비활성 (…)" | **도구 확인** (눌러 본 결과) |
| 예외: 비활성 / 예외: 빈 화면 | 도구 확인 (꺼져 있던 것) / 모델 설명 (영역 묶기 답의 `empty_state` 만) |
| 와이어플로의 화살표 · 경로 · 기능-화면 표의 표시 | 흐름 명세 + 도구 확인 (모델 말로 만들지 않는다) |
| 선택지 무리 "N개 중 하나 선택 → …" · 과제 밖 입구 표시 | 도구 확인 (무리 = 최종 검사의 `choice_groups_original`, 입구 = `oos-*`) |
| 조건별 화면과 그 조건 | 흐름 명세 (`error_paths` · `reveal` · 두 번째 방문) · 과제의 오류 정의 |
| **영역 이름 · 설명 · 화면 이름** | **모델 설명** (`--mock` 은 정해진 답, 모델이 빠뜨린 요소는 "도구 묶음", 화면 이름이 없으면 계획의 화면 목적 앞부분) |
| 화면 목적 · 변경 목록 · 진단 요약 | 재구성 실행의 계획 · 진단 (그대로 옮김) |
| 실행 정보 | `summary.json` · git (원본 지문 = 실행 커밋의 원본 파일, 줄끝을 LF 로 맞춘 sha256) |

예상 금액은 이체 실행 하나에 약 $0.08, 공과금 약 $0.19 (gpt-6.1-sol, 다시 묻기까지 가면
두 배 가까이). 걸리는 시간은 이체 1분 남짓 · 공과금 3분 남짓 (거의 다 눌러 보기). 자세한 것 —
상태와 다시 걷는 법, 덮개, 긴 화면, 무리의 대표, 시각 · 난수 고정, `storyboard.json` 의 칸,
한계 — 은 `docs/storyboard.md`.

## C 후보 고르기 (`python -m senior_ui.select`)

12번 단계에서 과제마다 재구성을 여러 번 돌린 뒤, 실험에 쓸 하나(C 후보)를 고르는
것을 돕는다. 도구는 **순위표와 비교 보고서** 를 만든다. 고르는 것은 연구자다.

저장된 결과만 읽는다 — 실행 폴더의 `summary.json` 과 마지막 시도의
`attempt_N.audit.json` · `attempt_N.plan.json`. 모델도 브라우저도 부르지 않는다.

```powershell
# 기본: outputs/restructure_auto/ 아래의 그 과제 실행 전부
.\.venv\Scripts\python.exe -m senior_ui.select --task transfer

# 볼 실행을 정한다 (폴더 · glob · 실행들을 담은 폴더)
.\.venv\Scripts\python.exe -m senior_ui.select --task transfer --runs "outputs/restructure_auto/20261007-*"
.\.venv\Scripts\python.exe -m senior_ui.select --task transfer --runs results/runs

# 다른 규칙 파일
.\.venv\Scripts\python.exe -m senior_ui.select --task bill --rule my_rule.json

# 규칙을 바꾼 뒤 지난 결과와 나란히 / 지난 결과의 규칙을 그대로 다시 쓰기
.\.venv\Scripts\python.exe -m senior_ui.select --task transfer --compare outputs/selection/transfer_20261007-150000.json
.\.venv\Scripts\python.exe -m senior_ui.select --task transfer --rule outputs/selection/transfer_20261007-150000.json
```

- `results/runs/` 의 옛 실행은 `--runs` 로 줄 때만 본다.
- 다른 과제의 실행은 넣지 않는다 (몇 개를 뺐는지는 보고서에 적는다). 과제 칸이
  없는 옛 summary 는 이체다.
- `summary.json` 이 없는 실행 폴더(도중에 죽은 것)도 순위표에 "summary.json 없음"
  으로 남는다.
- 종료 코드: 0 = 후보가 있다, 1 = 보고서는 썼지만 후보가 없다, 2 = 돌지 못했다
  (규칙 파일이 틀렸다 · 실행 폴더가 없다).

### 결과

`outputs/selection/<과제>_<시각>.md` 와 같은 내용의 `.json`. 같은 초에 두 번 돌면
뒤에 `-2` 가 붙는다.

- **순위표** — 본 실행 전부. 후보는 순위로, 빠진 것은 빠진 이유와 함께.
  칸: 통과 · 시도 수 (형식 실패/검사 실패) · 최종 fatal/warning · 화면 수 ·
  data-action 수 · 진단 수/변경 수 (진단에 대응되지 않은 변경 수) · 대표성 거리 ·
  도구가 고친 것(`final.preserved.redeclared`) · 마지막 시도의 잘림 · 중간 시도의
  잘림 횟수 · 작업 트리 dirty · 모델 ·
  reasoning_effort · 실행 조건(검사 단계 · 예산 형식/검사/다듬기) · 되돌림(다듬기가
  떨어져 직전 통과 빌드가 최종이면 그 회차) · 커밋
- **커밋 기준** — 후보들이 맞춘 커밋과 그것이 어디서 왔는지 (규칙 / 가장 많은 커밋)
- **원본 기준** — 후보들이 맞춘 원본 파일과 그 지문 (`original_basis`, 문지기 `original`)
- **구조** — 선택지 그룹마다 `kept/selectable/원본`, 오류 경로마다 검사 J 결과
- **비용** — 입력 · 출력(생각 포함) · 생각 토큰, 예상 금액 (`summary.cost`)
- **대표성 계산** — 값마다 중앙값 · 최솟값 · 최댓값
- 1등의 설명서(`designer_brief.md`) 링크
- **쓴 규칙** — 전문, sha256, 저장소 HEAD, 규칙 파일의 마지막 커밋, 커밋하지 않은
  수정이 있는지. 커밋 해시만으로는 부족하다 — 고쳐 놓고 돌렸으면 그 해시는 쓴
  규칙을 가리키지 않는다.

`.json` 의 `researcher_decision` 은 비워 둔다. 연구자가 채운다.

```json
"researcher_decision": {"chosen": "<실행 이름>", "same_as_rank1": true, "reason": ""}
```

1등이 아닌 것을 쓰면 `reason` 에 이유를 적는다. 채운 파일은 results/ 로 옮길 때
함께 간다 (15번).

모델이 만든 것과 도구가 고친 것을 가른다. 모델이 입력의 선택지 목록을 직접 다시
선언해 도구가 그 선언을 입력 데이터로 바꿨으면(`final.preserved.redeclared` 가
비어 있지 않음) 그 빌드는 모델 혼자 만든 것이 아니므로 기본 규칙에서 빠진다.

### 규칙 파일 (`flows/selection_rule.json`)

규칙은 코드가 아니라 이 파일에 있다. 모르는 칸 · 문지기 · 값 이름은 실행을
멈춘다 (종료 2) — 오타 난 문지기를 조용히 넘기면 그 문지기는 없는 것과 같다.

```json
{
  "gates": {
    "passed": true,
    "no_redeclared": true,
    "no_truncated": true,
    "clean_tree": true,
    "not_mock": true,
    "model": "gpt-6.1-sol",
    "no_warning_checks": ["J"],
    "stage": "wireframe",
    "budget": {"format": 5, "audit": 6, "refine": 0},
    "commit": null,
    "reverted": "allow",
    "no_internal_error": true,
    "original": "current"
  },
  "ordering": [
    {"by": "representative", "metrics": {"screens": 1, "data_actions": 1, "changes": 1}},
    {"by": "warning", "order": "asc"},
    {"by": "attempts", "order": "asc"}
  ]
}
```

**gates** — 하나라도 어기면 후보에서 뺀다. `true` 면 보고 `false` 면 보지 않는다.

| 문지기 | 후보가 되려면 |
|---|---|
| `passed` | `summary.passed == true` (같은 실패가 되풀이되어 멈춘 실행 `stopped_reason: stuck` 은 기록이 어긋나 있어도 통과로 세지 않는다) |
| `no_redeclared` | `final.preserved.redeclared` 가 비어 있다 (도구가 고친 흔적이 없다) |
| `no_truncated` | **마지막 시도** 의 답이 길이 제한에서 잘리지 않았다. 중간 시도의 잘림은 최종 시안과 상관없으므로 빼지 않고, 순위표의 '중간 잘림' 열에 횟수로만 보인다 |
| `clean_tree` | `git.dirty == false`. 기록이 없는 옛 실행은 어긴 것으로 본다 |
| `not_mock` | mock 실행이 아니다 |
| `model` | `null` 이면 보지 않는다. 이름을 적으면 `summary.model` 이 그것과 같아야 한다. 지금은 12번 본 실행의 모델 `gpt-6.1-sol` (= `config.DEFAULT_MODEL`) |
| `no_warning_checks` | 최종 검사에 그 검사들의 경고가 하나도 없다. 기본 `["J"]` (오류 알림 글에 과제 단어가 없음) |
| `stage` | `summary.stage` 가 그 단계다 (기본 `wireframe`). 기록이 없으면 어긴 것 |
| `budget` | 적은 칸(`format` · `audit` · `refine`)이 `summary.budget.format_budget` · `audit_budget` · `summary.refine.budget` 과 같다. 기본은 `config` 의 기본값 5 · 6 · 0 (다듬기는 version 4 (11-8) 부터 0 — 다듬기를 켜고 돈 실행은 빠진다) |
| `commit` | `null` 이면 다른 문지기를 지난 실행들 중 **가장 많은 커밋** 이 기준이다 (같은 수면 가장 나중 실행의 커밋). 해시를 적으면 그 커밋(앞자리 일치)만. 기준과 다른 커밋의 실행은 이유와 함께 빠진다 |
| `reverted` | 다듬기가 떨어져 직전 통과 빌드가 최종인 실행: `"allow"` (기본) 후보로 인정하고 순위표 '되돌림' 열로 보인다 · `"last"` 되돌리지 않은 실행 뒤로 미룬다 · `"exclude"` 뺀다. 다듬기를 끈 실행(refine 0)에는 되돌림이 없다 |
| `no_internal_error` | 도구 내부 오류로 끝난 실행(`stopped_reason: internal_error`, 종료 2)은 통과한 빌드가 있어도 뺀다 |
| `original` | `"current"` 면 실행의 `original_sha256` 이 그 과제의 **지금** 원본 파일(과제 파일의 `original` — 이체 `inputs/original_transfer.html`, 공과금 `inputs/original_bill.html`)의 지문과 같아야 한다. 다르면 "다른 원본으로 만든 실행" 으로 빠지고, 지문이 없는 옛 실행(11-11 전)도 같은 이유로 빠진다. `null` 이면 보지 않는다. 지문은 줄끝을 LF 로 맞춘 sha256 이다 (`tasks.fingerprint` — 설계서의 원본 지문과 같은 함수). 규칙 version 3 (11-11) |

조건 문지기(`stage` · `budget` · `commit` · `reverted` · `no_internal_error` · `original`)는 칸이
없으면 보지 않는다 — 칸이 생기기 전의 지난 결과 JSON 을 `--rule` 로 다시 쓰면 그때
규칙 그대로 돈다.

**ordering** — 위에서부터 차례로 비교한다. 앞이 같을 때만 다음을 본다. 끝까지
같으면 실행 이름순 (정해진 순서를 내기 위해서일 뿐 뜻은 없다). 순서를 바꾸려면
목록의 순서를, 방향을 바꾸려면 `order` 를, 대표성의 무게를 바꾸려면 `metrics` 의
가중치를 고친다.

기본은 대표성 → warning → 시도 수다. 이 규칙은 여러 실행 중 **전형적인 시안** 을
고르는 것이므로 대표성이 먼저다 — warning 이 하나 적다고 가장 튀는 시안이 1등이
되면 안 된다. warning 과 시도 수는 대표성이 같을 때만 가른다.

- `{"by": <값>, "order": "asc" | "desc"}` — 모은 값 하나로 줄 세운다. 값이 없는
  실행은 맨 뒤. 값: `warning` `fatal` `attempts` `format_failures`
  `audit_failures` `screens` `data_actions` `changes` `unmatched_changes`
  `diagnoses` `input_tokens` `output_tokens` `reasoning_tokens` `cost_usd`
- `{"by": "representative", "metrics": {<값>: 가중치}}` — 후보들 사이에서 그 값들이
  중앙값에 가까운 것. 거리 = 합(가중치 × |값 − 중앙값| / (최댓값 − 최솟값)).
  중앙값과 범위는 **문지기를 지난 후보들 사이에서** 잰다 — 떨어진 실행이 "보통" 을
  끌어당기지 않게. 범위가 0 이면 그 값의 몫은 0, 값이 없는 후보는 1.

`screens` 는 검사기가 센 빌드의 `data-screen` 수(`metrics.data-screen_repaired`,
없으면 계획의 화면 수), `data_actions` 는 `metrics.data-action_repaired`,
`changes` 는 마지막 시도가 따른 계획의 변경 수, `unmatched_changes` 는 그중
`addresses` 가 빈 변경의 수다.

규칙을 바꾸면 `--compare <지난 결과 JSON>` 으로 지난 고르기와 나란히 본다 — 바뀐
문지기 · 순서, 1등이 어떻게 바뀌었는지, 실행마다 지난 순위와 지금 순위.
`--rule <지난 결과 JSON>` 은 그 결과에 담긴 규칙 전문으로 다시 고른다 (규칙
파일이 그 뒤에 바뀌었어도).

## The auditor

`python -m senior_ui.audit` drives the original and the build under test through
the same 8-screen task and diffs them. It prints machine-readable JSON and exits
0 only when nothing fatal fired, so it can gate a regenerate-on-failure loop.

Exit 1 means it audited the build and the build failed. Exit 2 means the audit
itself could not run - inputs or flow unreadable, no browser, anything that
stops the drive - and the JSON then carries that reason as its single fatal.
원본을 열지 못했거나 원본에서 화면을 하나도 읽지 못했을 때도 2 다 (11-9b,
`drive.nothing_read`) — 원본 없이 판정하면 원본과 견주는 검사가 빈 결과를 내 생성물이
"통과" 한다. `--original` 을 주지 않으면 원본은 `:3003` 에서 연다 (사람이 띄우는 서버).
재구성 루프는 같은 경우 실행 시작에서 멈춘다 (`cannot_start`, 종료 2).
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
| A | every screen of the flow reached, the task's done values shown (`done_expect`), `data-action`/`id`/`data-screen` preserved | fatal |
| B | displayed values match what was entered; no injected `alert()`/`onclick`; no hardcoded numbers | fatal |
| C | `data-action` with no branch in the handler; `data-action` that disappeared | fatal |
| D | low-contrast count must not grow; new text must not rely on inherited colour; an already-low-contrast element must not gain readable text | warning |
| E | overlapping text, content spilling out of its box, newly wrapping text, screens much taller | warning |
| F | English words the original did not have (runtime and markup-only) | warning |
| G | `.x` and `.x.on` must still render differently | warning |
| H | classes the markup uses that no stylesheet defines | warning |
| I | values the original offered as choices must still exist somewhere in the build; values the original showed on its walk must be pressable-visible in some state of the build's walk (a step or after a `reveal`) — 문서 안에만 있으면 fatal (11-8) | fatal |
| J | each required wrong input (the task's `required_error_paths`) brings up an error state with new text and `recover` leads back to a screen where it can be fixed; warns when the text has none of the task's words | fatal |
| K | 과제 밖 입구 — 과제 파일 `entrances` 의 메뉴 · 버튼 (더미앱 A1 의 OutOfScope 탭 대상, 연구자 확정)이 빌드 어딘가에 남아 있다. 원본의 `data-action` 이름(`oos-*`)을 그대로 가진 요소가 걷는 동안(reveal 포함) 누를 수 있게 보이면 있다 (그려져 있고 disabled 가 아니다, 같은 화면이 아니어도 된다). 원본을 걷는 동안 보인 입구만 센다. 글자 · `aria-label` 은 기록만 한다 (`entrances_shown_as`). 처음 보인 방문 · 펼치기 횟수 · 스크롤 거리도 기록만 한다 (`entrance_distance`, 11-8) | fatal |

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
those files into one side-by-side Markdown table (overview, per-check A–K, the
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
generate-audit-regenerate loop and is still empty — the viewer does not read the
loop's run folders yet (감사 B-20 · D-9, 열린 문제).

Two numbers the viewer deliberately keeps apart: the changelog's tables cite
**26** of the 46 rules, while the document claims **33** are met. The extra 7 are
the author's own judgement with no table behind them, which the document itself
flags as optimistic.

## 테스트

구조를 정리해도 동작이 그대로인지 파일 비교로 확인한다. 기준값은
`tests/baseline/` 에 있고, 입력은 `results/` 의 고정된 파일이다.

```powershell
.\.venv\Scripts\python.exe -m pytest                # 브라우저 없음 (1분 남짓)
.\.venv\Scripts\python.exe -m pytest -m browser     # 실제로 다시 걷는다 (10분 남짓)
```

`pytest.ini` 의 `addopts` 가 `-m "not browser"` 라서 기본 실행은 브라우저를
띄우지 않는다. `-m browser` 는 Playwright 로 원본과 재구성본을 실제로 다시 몰고
다니며 저장된 스냅샷과 비교한다. 서버는 테스트가 직접 띄운다 (`tests/conftest.py`
의 `server` 하나를 모든 브라우저 테스트가 함께 쓴다). 건수는 적지 않는다 — 늘
바뀐다. `pytest --co -q` 로 본다.

**기준값을 다시 뽑는 것은 동작을 의도적으로 바꿨을 때만이다.**

```powershell
.\.venv\Scripts\python.exe tests\capture_baseline.py
```

캡처는 빈 포트에 제 서버를 띄운다 (mock 실행도 저마다) — 같은 포트를 명시하지 않으면
동시에 돌려도 된다. `--port N` 을 주면 그 포트에 이미 있는 서버가 **이 작업 트리를**
서빙할 때만 그대로 쓰고 (확인 파일 `/.devserver-id`), 아니면 캡처는 멈춘다 — 기준값은
그 포트가 서빙하는 내용에 전적으로 달려 있어서, 다른 worktree · 다른 폴더의 서버를
쓰면 기준값이 무엇을 기준으로 한 것인지 알 수 없어진다. 실행마다 흔들리는 값(원본 시제품의 비밀번호
숫자판 셔플)을 어떻게 빼는지, 지금 기준값에 어떤 동작이 담겨 있는지는
`tests/README.md` 에 적혀 있다.

## 파이프라인과 그 밖에 있는 것

| | |
|---|---|
| **파이프라인** | 위의 사슬. `senior_kb.csv` 는 여기 들어가지 않는다. |
| **실험 조건** | Flutter 더미앱(`senior-ui-dummy-app`)의 A1 (원본 재현) · A2 (배포된 고령자 모드) · C (이 도구의 재설계를 옮긴 것), 실제 고령 피험자. HTML 실험 장치(`web/session.html`)는 보관용이다. |
| **보관 자료** | `kb/senior_kb.csv`. 남겨 두지만 생성에는 쓰지 않는다. |

`kb/senior_kb.csv` 는 **사후 대조** 용이다 — 만들어진 설계가 결과적으로 어떤
규칙에 해당하는지 나중에 확인하는 것. 재구성본을 만들 때 모델에 주지 않았고
앞으로도 주지 않는다. 자세한 것은 `kb/README.md`.

## 알려진 문제

외부 감사(2026-10-06)에서 남은 것 중 결과에 닿을 수 있는 것. 번호는 감사 보고서의 것이다.

- **B-08 · B-09** 결함 하나가 fatal 여럿으로 셀 수 있다 — 원본에서 파생된 흐름에서
  data-action 하나가 사라지면 A 두 건 + C 한 건, `__screen()` 훅이 없으면 방문마다 한 건.
  루프 빌드(새 설계)에는 앞의 것이 해당하지 않는다.
- **B-14** 산출물 폴더를 상수(`OUTPUTS_DIR`)로 정하는 곳과 함수(`outputs_dir()`)로 정하는
  곳이 섞여 있다 — `SENIOR_UI_OUTPUTS` 를 주면 검사기 CLI 의 기본 `--out` · 색인은
  여전히 `outputs/` 를 본다.
- **B-19** 설명서의 "모델이 쓴 HTML" 링크가 실행 이름 없는 승격 파일을 가리킨다.
- **B-20 · B-40 · B-48** 대시보드 · 색인이 루프 실행 · 공과금 · Flutter C 조건을 반쪽만
  보인다 (D-9 결정 대기).
- **B-21** 정답 값이 과제 파일의 프롬프트 글(`flow_values`)에 두 번째로 적혀 있다.
- **B-22** `test_a_mock_run_survives_a_cp949_console` 가 기본 묶음에서 실제 mock 실행
  (서버 · Chromium)을 돌린다 (D-10 결정 대기).
- **11-8** 기술 계약(`docs/restructure-prompt.md` 의 `CONTRACT`)은 아직 "선택 화면이 열렸을
  때 모든 값이 DOM 안에 있어야 한다 (숨김·접힘은 괜찮다)" 라고 말한다. 검사 I 는 이제 원본에서
  보이던 값이 걷는 동안(reveal 포함) 누를 수 있게 보여야 통과한다 — 접어 둔 목록은 펼치는
  조작을 `reveal` 에 적어야 한다. 프롬프트를 바꾸면 생성 · 다듬기 프롬프트의 글자가 달라지므로
  연구자 결정으로 남겨 두었다 (그 전까지는 떨어진 시도의 재시도 블록이 reveal 을 적으라고
  알린다).

## 다른 문서

| | |
|---|---|
| `CONTINUE.md` | **보관용** (2026-10-02 기준). 현재 상태는 이 README 한 곳이다 (감사 D-11). |
| `experiment-guide.md` | 실험 당일 절차. 준비·진행·집계. |
| `restructure-prompt.md` | 재구성 프롬프트 템플릿. 루프가 이 파일을 읽는다. |
| `restructure-runs.md` | 손수 제작 Run 1·2·3 비교. |
| `variance-notes.md` | 같은 프롬프트를 다시 돌릴 때 무엇이 달라지는가. |
| `restructure-changelog.md` | Run 1 의 변경 내역과 KB 규칙 사후 대조. |
| `defect-types.md` | 생성물에 반복해 나타나는 결함 유형. 검사기에 넣을 후보. |
| `input-contract.md` | 앞단(스크린샷 → HTML)이 지켜야 할 입력 HTML 의 약속. 뒤쪽이 무엇을 읽고 그중 무엇이 스크린샷에서 오는가. |
| `storyboard.md` | 화면설계서 — 결과물의 칸마다 출처, 만드는 법, `storyboard.json`, 시간 · 비용, 한계. |
