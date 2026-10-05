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

`PYTHONUTF8=1` 은 더 이상 필요 없다. 모든 명령줄이 맨 앞에서
`senior_ui._cli.setup_stdout()` 을 불러 stdout 을 UTF-8 로 맞춘다.

종료 코드는 `0` = 통과한 빌드가 있다, `1` = 전부 실패, `2` = 아예 돌지 못했다
(레이트 리밋 · API 가 요청을 거절함 · 인프라 예산 소진 · 시작 자체를 못 함).
떨어진 빌드는 다시 만들고, 돌지 못한 실행은 다시 만들 것이 없다.

한 실행의 모든 것이 `outputs/restructure_auto/<타임스탬프>/` 에 남는다 — 보낸
프롬프트 전문, 받은 답 전문, 시도별 html·흐름·검사 결과, 화면별 스크린샷,
`run.log`, `summary.json`.

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

이름은 `senior_ui/preserved.py` 한 곳에만 있다. API 없이 확인하려면
`--mock preserved-all` / `preserved-some` / `preserved-none` 셋을 돌린다.

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
| `wireframe` | A 과제 완주 · B 표시 정확성 · C 죽은 컨트롤 · F 언어 · I 선택지 보존 | contrast, layout, state colour and undefined classes are about detail nobody has filled in yet |
| `styled` | A~I | everything |

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
| 검사 결과 | audits side by side, folded per check A-I. Findings link to that screen's screenshot; stood-down checks say why; the metric table is folded away because a count is not a grade. |
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
