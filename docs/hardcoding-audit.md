# 남은 하드코딩 전수 점검 (11번 단계 끝)

`feat/task-generic` 에서 과제 정의를 `tasks/<과제>.json` 으로 뺀 뒤, 레포에 남은 "특정 과제 ·
특정 값 · 특정 실행 · 특정 환경 · 숫자 상수" 에 묶인 곳을 모은 표다. **고치지 않았다** —
한 건(승격 산출물 이름)만 지시에 따라 11번에서 고쳤고 그렇게 적었다.

- 범위: `senior_ui/` · `web/` · `tests/*.py` · `docs/restructure-prompt.md` · `시작.bat`.
  `tests/fixtures/` · `tests/baseline/` 안의 값은 테스트 입력이라 세지 않았다. 테스트 코드가 특정
  Run 파일을 직접 가리키는 곳은 적었다.
- 같은 종류가 한 파일에 여러 번 나오면 한 줄로 묶고 줄 번호를 나열했다 (예: 잘라 보이는 글자 수).
- 줄 번호는 이 브랜치의 마지막 커밋 기준이다.
- 판단: **고쳐야 함** (어느 단계에서 고치면 좋을지 한 줄 제안) / **일부러 둠** / **모르겠음**.

## 요약

| 분류 | 행 | 고쳐야 함 | 일부러 둠 | 모르겠음 | 11번에서 고침 |
|---|---|---|---|---|---|
| 과제 | 38 | 11 | 23 | 4 | 0 |
| 값 | 7 | 1 | 6 | 0 | 0 |
| 실행 | 24 | 0 | 23 | 0 | 1 |
| 환경 | 13 | 2 | 11 | 0 | 0 |
| 상수 | 36 | 5 | 31 | 0 | 0 |
| **합** | **118** | **19** | **94** | **4** | **1** |

행은 아래 표의 줄 수다 (같은 종류를 한 줄로 묶은 것이 많다). "고쳐야 함" 19행은 아래
16항목이다 — 한 항목이 여러 파일에 걸치면 파일마다 한 행이다 (15번 · 16번).

### 고쳐야 함 (16) — 제안 단계

| # | 자리 | 한 줄 | 제안 |
|---|---|---|---|
| 1 | `reply.py:269` · `b_display.py` | 흐름 명세의 `expect` 완료 화면 키가 `"done"` 으로 박혀 있다. 모델이 마지막 화면을 다른 이름으로 지으면 `expect.done` 은 형식 검사를 지나고 검사 B 는 그 화면을 찾지 못해 **말없이 건너뛴다** (공과금의 `#dn-eno` 가 안 걸린다) | 12번 전 — 완료 화면 키를 `steps` 의 마지막 화면으로 보고, `expect` 키가 화면 이름인지 형식 검사에서 본다 |
| 2 | `a_completion.py:150,152` | 검사 A 가 `truth["AMOUNT_SHOWN"]` 을 바로 읽는다. 금액 없는 과제에서는 KeyError | 세 번째 과제를 더하기 전 — `done_expect` 의 짝을 과제에서 읽는다 |
| 3 | `a_completion.py:133` | `done_amount` 가 없을 때의 대체값 `"#dn-amt"` (이체 id) | 2번과 함께 — `flow.done_selector(task_of(flow))` |
| 4 | `b_display.py:100,130` | 대화상자 경고 문구가 "다른 금액이면 틀린다" · "the task used `AMOUNT_SHOWN`" — 공과금에서 걸린 숫자가 전자납부번호여도 금액을 말한다 | 2번과 함께 (문구만) |
| 5 | `config.py:58,59,67` | `ORIGINAL_FILE` · `ORIGINAL_URL` 은 이제 코드에서 쓰지 않는다. `ORIGINAL_REL` 만 `devserver` 가 쓴다 | 정리 단계 — 지우거나 `tasks/transfer.json` 에서 만든다 |
| 6 | `config.py:70–77` | 실험 조건(`CONDITIONS`)이 이체 원본과 `outputs/restructured_transfer.html`("재구성본 (Run 1)") 둘로 박혀 있다 | 실험 준비 단계 — 과제별 조건을 과제 파일이나 실험 설정 파일로 |
| 7 | `build_index.py:400,409` | 이체 원본 카드(`collect_baseline`)의 경로 · 흐름이 과제 파일이 아닌 글자다 | 정리 단계 — `tasks/transfer.json` 의 `original` · `flow` 로 (카드 모양은 그대로) |
| 8 | `model.py:535,536` | 공과금 mock 이 원본 · 흐름 경로를 `tasks/bill.json` 이 아닌 글자로 쓴다 | 바로 고칠 수 있음 — `load_task("bill")` |
| 9 | `restructure/__main__.py:1` | 모듈 설명이 "redesigned **transfer** prototype" | 정리 단계 (문서) |
| 10 | `docs/restructure-prompt.md:176` | "오류는 계획의 `errors` 대로 알린다." 가 오류 없는 과제(공과금)에도 그대로 들어간다 | 12번 전 — `{{TASK_*}}` 슬롯으로 |
| 11 | `docs/restructure-prompt.md:26,32` | 사람용 메모가 낡았다 — "치환 자리 다섯" (지금은 `{{TASK}}` · `{{TASK_*}}` 가 더 있다), "원본 흐름(`flows/original.json`)" (지금은 과제의 흐름) | 정리 단계 (문서) |
| 12 | `brief.py:207` | 설명서 문구가 데이터 블록 id `preserved-data` 를 `preserved.DATA_BLOCK_ID` 를 쓰지 않고 다시 적었다 | 정리 단계 |
| 13 | `capture_baseline.py:105` · `test_drive.py:73` · `test_audit_accuracy.py:44` | 테스트용 `http.server` 를 `--bind` 없이 띄운다 → 0.0.0.0. `devserver` · `test_devserver.py` 는 루프백만 허용한다 | 다음 테스트 정비 — `"--bind", "127.0.0.1"` (기준값과 무관) |
| 14 | `시작.bat:7,8,13` | 포트 3003 · 주소를 글자로 다시 적었다 (`config.PORT` 와 따로 논다) | 정리 단계 — 서버가 찍는 주소를 쓰거나 포트를 인자로 |
| 15 | `drive.py:299,406` · `web/dashboard.css:70–72` | 휴대폰 크기 390×844 (css 는 390×700) 가 여러 곳에 따로 있다 | 정리 단계 — `config.VIEWPORT` 하나로 |
| 16 | `report.py:209` · `dashboard.js:421,433` · `build_index.py:73` | 상수를 글로 다시 적었다 — "1.5배" (`e_layout.HEIGHT_GROWTH_LIMIT`), "KB 46개" (KB 행 수), "A·B·C·F·I·J" (`stage.STAGES`) | 정리 단계 — 그 상수를 읽어 문구를 만든다 |

**11번에서 고침 (1)** — `loop.py:838` `PROMOTED` · `PROMOTED_BRIEF`: 승격 이름에 과제가 없어
공과금 실행이 이체의 `outputs/restructured_auto.*` 를 덮었다. 이체는 이름 그대로, 공과금은
`restructured_auto_bill.*` (커밋 `ec8ae36`).

**모르겠음 (4)** — `experiment/server.py:39–46` (HTML 실험 장치의 이체 과업 문구, 옛 정답값),
`web/session.html:156,205` (조건 둘 · 송금 완료 `submit` 기준), `build_index.py:69` (파이프라인
설명 "8화면 시제품"), `tests/ignore.py:27–29` (흔들리는 값의 경로가 화면 이름 `password` · 동작
`pw` 로 박혀 있다 — 이체와 공과금은 우연히 같아서 맞는다. 공과금은 두 번 뽑아 확인했다).
판단 근거는 표의 이유 칸.

## 표

### senior_ui/config.py · tasks.py

| 파일:줄 | 무엇이 박혀 있나 | 분류 | 판단 | 이유 |
|---|---|---|---|---|
| `config.py:17,18` | `PORT = 3003`, `http://localhost` | 환경 | 일부러 둠 | 설정이 모이는 곳. 다른 파일은 여기서 읽는다 |
| `config.py:20–32` | 폴더 이름 `flows` · `tasks` · `outputs` · `results` · `.mock-outputs`, 환경 변수 `SENIOR_UI_OUTPUTS` | 환경 | 일부러 둠 | 설정이 모이는 곳 |
| `config.py:58,59,67` | `ORIGINAL_FILE` · `ORIGINAL_REL` · `ORIGINAL_URL` = 이체 원본 | 과제 | **고쳐야 함** | 위 5번 |
| `config.py:70–77` | `CONDITIONS` — 이체 원본, `outputs/restructured_transfer.html`, "원본 (신한 SOL 재현)" · "재구성본 (Run 1)" | 과제 | **고쳐야 함** | 위 6번 |
| `tasks.py:32` | `DEFAULT_TASK = "transfer"` | 과제 | 일부러 둠 | 과제를 주지 않은 실행이 전과 같아야 한다 (이체 기준값) |
| `tasks.py:9–21` | 과제 파일 모양 예시가 이체 값 | 과제 | 일부러 둠 | 설명용 예시 |

### senior_ui/audit/

| 파일:줄 | 무엇이 박혀 있나 | 분류 | 판단 | 이유 |
|---|---|---|---|---|
| `flow.py:30,37` | `TRUTH_KEYS` (ACCOUNT·AMOUNT·BANK·NAME) 가 `make_truth` 의 기본 필수 키 | 과제 | 일부러 둠 | 과제를 모르는 호출의 기본값. 흐름을 읽는 곳은 모두 과제의 `required_truth` 를 넘긴다 |
| `flow.py:49–55` | `AMOUNT` 를 특별히 다뤄 `AMOUNT_SHOWN` 을 천 단위 쉼표로 만든다 | 과제 | 일부러 둠 | 두 과제 모두 금액이 있다. 금액 없는 과제는 위 2번과 함께 본다 |
| `flow.py:119–131` | `original_truth()` · `original_error_paths()` = 이체, `done_selector` = `done_expect` 의 첫 짝 | 과제 | 일부러 둠 | 이체 mock 과 옛 호출용. 과제를 아는 곳은 `task_truth(task)` 를 쓴다 |
| `flow.py:167–178` | 설명에 "run4 의 흐름", `account#2` | 실행 | 일부러 둠 | 그 규칙이 생긴 이유 (기록) |
| `drive.py:50` | `truth or truth_of(None)` — 정답을 안 넘기면 이체 | 과제 | 일부러 둠 | 부르는 곳은 늘 그 흐름의 정답을 넘긴다 |
| `drive.py:19–48` | 설명 예시 `[data-action='acc-num'][data-v='%s']`, `#acc-input` | 과제 | 일부러 둠 | 걸음 문법을 보이는 예시 |
| `drive.py:94,194` | `SETTLE_TIMEOUT_MS = 3000`, `DIALOG_GRACE_MS = 400` | 상수 | 일부러 둠 | 이름 붙인 상수 한 곳, 근거가 주석에 있다 |
| `drive.py:76,235` | 반복 클릭 기본 0.1초, 대화상자 비우기 5회 | 상수 | 일부러 둠 | 걸음 규칙의 기본값 |
| `drive.py:299,406` | 화면 크기 390×844 (두 번) | 상수 | **고쳐야 함** | 위 15번 |
| `drive.py:362,461` | Playwright 기본 30초 제한에 기댄다 (코드에 없음) | 상수 | 일부러 둠 | 라이브러리 기본값 |
| `drive.py:357,458` | 스크린샷 이름 `audit_%s.png` · `audit_error_%s.png` | 실행 | 일부러 둠 | 색인 · 설명서가 같은 규칙으로 찾는다 |
| `probes.py:217` | 대비 기준 `large ? 3.0 : 4.5`, 큰 글씨 24px / 18.66px 굵게 | 상수 | 일부러 둠 | 판정 기준을 한 곳에 (WCAG) |
| `probes.py:95,96,192` | sRGB · 휘도 상수, `+ 0.05` | 상수 | 일부러 둠 | WCAG 식 |
| `probes.py:289,302,304,330,343,379` | 겹침 4px · 2px · 25%, 넘침 2px, 같은 줄 2px | 상수 | 일부러 둠 | 판정 기준 한 곳 |
| `probes.py:220–394` 여러 줄 | 글자 자르기 `.slice(0, 24/30/40/80)`, 결과 25개까지 | 상수 | 일부러 둠 | 보고용 길이 |
| `probes.py:471` | 상태 클래스 `on · act · active · selected · checked · disabled` | 상수 | 일부러 둠 | 검사 G 의 대상 목록 |
| `probes.py:540–554` | 선택지 묶음: 형제 2개 이상, 값 40자 이하 | 상수 | 일부러 둠 | 검사 I · 데이터 보존이 같은 규칙을 쓴다 |
| `probes.py:250,358,437,514,537` | 주석 예시 "recipient", "은행 38개와 증권사 29개", "example1" | 과제 | 일부러 둠 | 규칙의 근거 (기록) |
| `core.py:1,13` | 모듈 설명 "for the transfer prototype", "8 screens" | 과제 | 일부러 둠 | 설명 글. 판정에 쓰이지 않는다 (정리 때 같이 고쳐도 된다) |
| `handlers.py:29,30` | 클릭 처리기 변수 이름 `a` (`a === '이름'`, `case`) | 상수 | 일부러 둠 | HTML 기술 계약 (프롬프트 2절과 같다) |
| `stage.py:35–45` | 단계별 검사 묶음 (와이어프레임 A·B·C·F·I·J) | 상수 | 일부러 둠 | 단계의 정의가 여기 한 곳 |
| `a_completion.py:133` | 대체값 `"#dn-amt"` | 과제 | **고쳐야 함** | 위 3번 |
| `a_completion.py:150,152` | `truth["AMOUNT_SHOWN"]` | 과제 | **고쳐야 함** | 위 2번 |
| `a_completion.py:136,137` | 지표 키 `done_screen` · `done_amount` | 실행 | 일부러 둠 | 결과 JSON 의 키 (results/ 의 옛 JSON 과 같은 모양) |
| `b_display.py:22` | 숫자 사이 하이픈 · 공백을 걷는다 (계좌번호 끊어 쓰기) | 상수 | 일부러 둠 | 출금계좌 `110-000-000000` 도 같은 규칙으로 통과한다 |
| `b_display.py:100,130` | "other amount" · `AMOUNT_SHOWN` 문구 | 과제 | **고쳐야 함** | 위 4번 |
| `b_display.py:93,106` | `alert` · `confirm` · `prompt` | 상수 | 일부러 둠 | 기술 계약 (쓰지 말라는 것) |
| `d_contrast.py:89,115,173` · `e_layout.py:47,50,73` | 경고 20개까지 | 상수 | 일부러 둠 | 보고 길이 |
| `e_layout.py:7` | `HEIGHT_GROWTH_LIMIT = 1.5` | 상수 | 일부러 둠 | 판정 기준 한 곳 |
| `f_language.py:26` | 영어 단어 = 2자 이상 라틴 글자 | 상수 | 일부러 둠 | 판정 기준 |
| `f_language.py:107` | 주석 "37 bank" (원본은 38) | 값 | 일부러 둠 | 주석의 숫자만 틀렸다. 판정에는 영향 없음 (정리 때 같이 고친다) |
| `i_choices.py:44–57` | 한글 · 라틴 · 숫자 경계 규칙, 근거로 "국민 / 국민은행", 숫자판 `00` | 값 | 일부러 둠 | 규칙은 과제와 무관, 예시가 이체일 뿐 |
| `j_errors.py:39` | 알림 글을 견줄 때 숫자와 `원` 을 걷어 낸다 | 상수 | 일부러 둠 | 원화 앱. 다른 통화를 쓸 일이 없다 |
| `j_errors.py:28` · `d_contrast.py:28,122` · `h_undefined_class.py:4` | 근거로 "Run 1~4", "Run1 102건", "example1" | 실행 | 일부러 둠 | 기록 |
| `report.py:131` | 표 행 "완료 화면 금액" | 과제 | 일부러 둠 | 두 과제 모두 완료 화면에 금액이 있다 |
| `report.py:127,187–192,286` | `repaired` 가 든 옛 키 이름 | 실행 | 일부러 둠 | results/ 의 옛 JSON 과 같은 모양 |
| `report.py:209` | "1.5배" 를 글로 다시 적음 | 상수 | **고쳐야 함** | 위 16번 |
| `__main__.py:15–19` | 사용 예 `localhost:3003`, `restructured_auto.html`, `flows/restructured.json` | 실행 | 일부러 둠 | 사용법 글 |

### senior_ui/restructure/

| 파일:줄 | 무엇이 박혀 있나 | 분류 | 판단 | 이유 |
|---|---|---|---|---|
| `__main__.py:1` | "redesigned transfer prototype" | 과제 | **고쳐야 함** | 위 9번 |
| `__main__.py:51–78,97–101,126` | mock 설명 · 도움말이 Run 1 · 은행 목록 · 숫자판 | 과제 | 일부러 둠 | 이체 mock 일곱의 설명 (그 mock 은 이체 전용이다) |
| `__main__.py:106,112,119,135` | `--attempts 3`, `--infra-attempts 3`, `--max-tokens 14000`, `--delay 60` | 상수 | 일부러 둠 | 명령줄 기본값, 분당 한도 근거가 도움말에 있다 (테스트가 못박는다) |
| `__main__.py:128` | `--task` 기본 `transfer` | 과제 | 일부러 둠 | 이체 기준값 |
| `loop.py:58` | `PLAN_MAX_TOKENS = 6000` | 상수 | 일부러 둠 | 이름 붙인 상수 |
| `loop.py:209` | 모델 대체값 `"gpt-4o"` (환경 변수 `RESTRUCTURE_MODEL` · `DESIGNREPAIR_MODEL` 다음) | 환경 | 일부러 둠 | 재현 기록이 응답 모델을 따로 적는다. 바꿀 때는 `--model` |
| `loop.py:838–867` | 승격 이름 `restructured_auto*` | 실행 | **11번에서 고침** | 과제를 넣었다 (`promoted_name`) |
| `loop.py:937` | 종료 코드 2 의 이유 넷 | 상수 | 일부러 둠 | 종료 코드 규약 한 곳 |
| `loop.py` 여러 줄 | 시도 파일 이름 `attempt_N.*`, `run.log`, `summary.json` | 실행 | 일부러 둠 | 실행 폴더 규약 |
| `model.py:17,41–45` | `.envs`, `OPENAI_API_KEY` | 환경 | 일부러 둠 | 키를 읽는 곳 한 곳 |
| `model.py:85,86` | `TEMPERATURE = 0.0`, `SEED = 20260101` | 상수 | 일부러 둠 | 재현용으로 못박은 값, 기록에 남는다 |
| `model.py:110,119` | 토크나이저 `o200k_base` | 환경 | 일부러 둠 | gpt-4o 계열 어림 |
| `model.py:130,132,160` | `MIN_COMPLETION = 4000`, `MARGIN = 500`, 대기 20·45·90·180초 | 상수 | 일부러 둠 | 분당 한도 대응, 근거가 주석에 있다 |
| `model.py:232` | `MOCK_BUILD = "restructured_transfer.html"` | 실행 | 일부러 둠 | 이체 mock 은 Run 1 을 되읽는 것이 목적이다 |
| `model.py:254–413,448–520` | 이체 mock: 은행 목록 줄, `NAME_SWAP` 김시현→김철수, 숫자판 마크업, 오류 처리, `MOCK_PLAN` | 값 | 일부러 둠 | Run 1 빌드에 거는 고정물 (자리를 못 찾으면 멈춘다) |
| `model.py:270` | 주석 "다섯 모드" (지금은 일곱) | 값 | 일부러 둠 | 주석 숫자. 정리 때 같이 |
| `model.py:535,536` | 공과금 mock 의 원본 · 흐름 경로 | 과제 | **고쳐야 함** | 위 8번 |
| `model.py:539,546` | `BILL_ARRAYS`, `BILL_SCREENS` | 과제 | 일부러 둠 | 공과금 원본에 거는 고정물. 어긋나면 형식 검사에서 드러난다 |
| `reply.py:250` | 필수 id `phone` | 과제 | 일부러 둠 | HTML 기술 계약 (`#phone`) |
| `reply.py:269` | `expect` 의 완료 화면 키 `"done"` | 과제 | **고쳐야 함** | 위 1번 |
| `reply.py:217` | 생략 표시 `… etc other 생략 나머지` | 상수 | 일부러 둠 | 과제와 무관 |
| `plan.py:21–24` | 화면 이름 문자 규칙, 진단 `D\d+` · 변경 `C\d+` | 상수 | 일부러 둠 | 프롬프트 출력 형식과 짝 |
| `preserve.py:117,141` | 배열과 묶음이 반 이상 겹치면 출처, 묶음 2개 이상 | 상수 | 일부러 둠 | 검사 I 와 같은 규칙 |
| `preserve.py:3–132` | 근거로 "Run 4·5", "은행 38 + 증권사 29" | 실행 | 일부러 둠 | 기록 |
| `prompt.py:79,90` · `brief.py:251` · `audit_call.py:31,77` | 과제를 주지 않으면 이체 오류 경로 · 이체 과제 | 과제 | 일부러 둠 | 루프는 늘 과제를 넘긴다. 기본값은 이체 기준값용 |
| `prompt.py:244,284,288` | 실패 로그 200자, 오류 줄 앞뒤 1줄, 100자 | 상수 | 일부러 둠 | 재시도 블록 길이 |
| `brief.py:207` | `preserved-data` 를 글로 다시 | 값 | **고쳐야 함** | 위 12번 |
| `audit_call.py:26` | `flows/allowed_removals.json` | 실행 | 일부러 둠 | 연구자 파일 한 곳 (과제 키로 나뉜다) |

### senior_ui/experiment · viewer · 그 밖

| 파일:줄 | 무엇이 박혀 있나 | 분류 | 판단 | 이유 |
|---|---|---|---|---|
| `experiment/server.py:39–46` | HTML 실험 장치의 과업 문구 "김시현 씨에게 1만 원… 3333-0000-0000-0, 카카오뱅크" | 과제 | 모르겠음 | 본실험은 Flutter 더미앱이라 쓰지 않는 장치다. 다만 정답값이 지금 원본(김철수 · 110234567890)과 다르다 — 쓸 계획이 있으면 고쳐야 한다 |
| `experiment/server.py:50,83` | `127.0.0.1`, 루프백 주소 | 환경 | 일부러 둠 | 이 PC 에서만 열리게 하는 보안 결정 |
| `experiment/server.py:66–71` | 허용 목록 (과제 원본은 과제 파일에서, 시작할 때 한 번) | 환경 | 일부러 둠 | 과제를 더하면 서버를 다시 띄운다 |
| `experiment/report.py:137,153,201,203` | 조건 둘일 때만 차이, 동작 이름 `back*` · `*del` | 상수 | 일부러 둠 | 세션 지표의 규약 (HTML 실험 장치와 짝) |
| `viewer/build_index.py:47–55` | `NAMES` · `ORDER` — Run 1~3 · 자동 생성본 표시 이름 | 실행 | 일부러 둠 | 손수 Run 의 표시 이름. 모르는 빌드는 파일 이름으로 나온다 |
| `viewer/build_index.py:69` | 파이프라인 설명 "신한 SOL 화면을 8화면 시제품으로" | 과제 | 모르겠음 | 공과금도 8화면이라 틀린 말은 아니다. 과제별로 나눌지는 대시보드 설계 문제 |
| `viewer/build_index.py:73` | "와이어프레임은 A·B·C·F·I·J" 를 글로 다시 | 상수 | **고쳐야 함** | 위 16번 |
| `viewer/build_index.py:400,409` | 이체 원본 카드의 경로 · 흐름 | 과제 | **고쳐야 함** | 위 7번 |
| `viewer/build_index.py:408` | 이체 원본 스크린샷 = `outputs/shots/before_*.png` | 실행 | 일부러 둠 | 이체 원본의 스크린샷 규약. 공과금 카드는 폴더 이름으로 찾는다 |
| `viewer/build_index.py:456–536` | `docs/restructure-changelog.md` 의 문구에 거는 정규식, `kb/senior_kb.csv` | 실행 | 일부러 둠 | Run 1 의 손으로 쓴 변경 기록을 읽는 곳 |
| `collect_results.py:21–42` | Run 1~3 파일, Run 4 = `restructure_auto/20261001-125247/attempt_3` | 실행 | 일부러 둠 | 증거를 results/ 로 옮기는 일회성 목록. 공과금 산출물은 읽지 않는다 |
| `devserver.py:43` | 저장소 확인용 파일 = 이체 원본 | 과제 | 일부러 둠 | "이 저장소를 서빙하는가" 확인용. 어느 추적 파일이든 된다 |
| `devserver.py:37,55,84,88` | 0.3초 · 3초 · 50회 × 0.1초 | 상수 | 일부러 둠 | 서버 확인 대기 |
| `_cli.py:31` | stdout 을 UTF-8 로 (cp949 콘솔) | 환경 | 일부러 둠 | 환경 대응 한 곳 |

### web/ · 시작.bat

| 파일:줄 | 무엇이 박혀 있나 | 분류 | 판단 | 이유 |
|---|---|---|---|---|
| `web/dashboard.css:70–72` | 휴대폰 폭 390px (높이 700) | 상수 | **고쳐야 함** | 위 15번 |
| `web/dashboard.js:140` | 도움말 "원본 account ↔ Run 1 accno+bank" | 과제 | 일부러 둠 | 화면 이름이 빌드마다 다르다는 예시 |
| `web/dashboard.js:389` | "재구성 Run 1 — 손으로 쓴 변경 기록" | 실행 | 일부러 둠 | 그 기록이 실제로 Run 1 의 것이다 |
| `web/dashboard.js:421,433` | "KB 46개" · "규칙 46개" | 상수 | **고쳐야 함** | 위 16번 (색인의 규칙 수로) |
| `web/dashboard.js:14–26` | 이체 원본 = `baseline`, 다른 과제 원본 = `originals` | 과제 | 일부러 둠 | 이체 카드 모양을 바꾸지 않으려는 11번의 결정 |
| `web/session.html:156,205` | 조건 둘의 맞바꾸기, 완료 = 로그의 `submit` | 과제 | 모르겠음 | 본실험에서 쓰지 않는 장치. 공과금 원본도 `submit` 을 남겨 동작은 한다 |
| `web/session.html:197,288` | 0.4초 확인, 3초 길게 누르기 | 상수 | 일부러 둠 | 실험 장치의 조작 규약 |
| `시작.bat:2–4` | `chcp 65001`, `PYTHONUTF8=1` | 환경 | 일부러 둠 | Windows 실행기 |
| `시작.bat:7,8,13` | `127.0.0.1:3003`, `localhost:3003` 주소, 60회 × 0.5초 | 환경 | **고쳐야 함** | 위 14번 |
| `시작.bat:18` | `.\.venv\Scripts\python.exe` | 환경 | 일부러 둠 | Windows 전용 실행기 |

### tests/ (고정물 · 기준값 밖)

| 파일:줄 | 무엇이 박혀 있나 | 분류 | 판단 | 이유 |
|---|---|---|---|---|
| `capture_baseline.py:56–59` | 기준값 경우 — `results/restructured_transfer.html` · `restructured_run2/3.html` + `flows/restructured.json` · `run2/3.json` | 실행 | 일부러 둠 | 특정 Run 을 직접 가리킨다 — 기준값의 입력은 추적되는 results/ 사본이어야 한다 (tests/README) |
| `capture_baseline.py:72–75,275` | `fixtures/report/audit_*.v2.json` Run1~4, 재시도 프롬프트 = `run1` | 실행 | 일부러 둠 | 같은 이유 |
| `capture_baseline.py:387,390` | mock 입력으로 `outputs/restructured_transfer.html` ← `results/` 사본 | 실행 | 일부러 둠 | 이체 mock 이 Run 1 을 되읽는다 |
| `capture_baseline.py:458–486,522–607` | 세션 고정물 문구 · 값 (김시현 · 3333…, 화면 이름) | 값 | 일부러 둠 | session_report 의 고정 입력 (값 자체가 입력) |
| `capture_baseline.py:105` · `test_drive.py:73` · `test_audit_accuracy.py:44` | `http.server` 에 `--bind` 없음 | 환경 | **고쳐야 함** | 위 13번 |
| `capture_baseline.py:102` | `netstat -ano \| findstr` 안내 | 환경 | 일부러 둠 | Windows 사용 안내 문구 |
| `test_audit_bugs.py:371–374` | CLI 테스트가 `results/restructured_transfer.html` · `flows/restructured.json` 을 직접 가리킨다 | 실행 | 일부러 둠 | Run 1 을 고정 입력으로 쓴다 |
| `test_restructure_bugs.py:576,593` | "다른 원본" 으로 `results/restructured_transfer.html` | 실행 | 일부러 둠 | 같은 이유 |
| `test_restructure_bugs.py:329` | 진짜 `outputs/` 의 수정 시각을 본다 | 실행 | 일부러 둠 | 테스트가 실제 산출물을 덮지 않는지 확인하는 테스트 |
| `test_dashboard_server.py:141,142,190–193` | 막혀야 할 실제 캡처 `inputs/KakaoTalk_….png`, 열려야 할 `results/restructured_run4.html` 등 | 실행 | 일부러 둠 | 없으면 건너뛴다. 공과금 원본은 `test_task_generic` 이 본다 |
| `test_data_preservation.py:27,38` | 이체 원본 · 이체 기준값 스냅샷 | 과제 | 일부러 둠 | 이체의 데이터 보존을 못박는 테스트 |
| `test_error_paths.py:34,58,413` · `test_error_paths_browser.py:40,45,94` | 이체 흐름 · 오류 id · 트리거 화면 | 과제 | 일부러 둠 | 오류 경로가 있는 과제는 이체뿐이다 |
| `test_task_generic.py:22–24` | `TRANSFER_TRUTH` 를 테스트에 다시 적음 | 값 | 일부러 둠 | 이체가 바뀌지 않았음을 확인하는 값 |
| `ignore.py:27–29` | 흔들리는 값 경로 `choices.pw` · `password.text` · `password.wrapped` | 과제 | 모르겠음 | 이체에서 잰 경로가 공과금에도 우연히 맞는다 (두 번 뽑아 확인). 화면 이름이 다른 과제가 오면 다시 재야 한다 |
| `test_drive.py:5` | 설명 "브라우저 8회 + mock 2회" | 상수 | 일부러 둠 | 낡은 숫자 (정리 때) |
| `test_original_bill.py:139,212–360` | 공과금 화면 · 메뉴 · 정답값 | 과제 | 일부러 둠 | 공과금 원본 자체를 검사하는 테스트 |
| `*.py` 머리말 | `.\.venv\Scripts\python.exe -m pytest` | 환경 | 일부러 둠 | Windows 사용 안내 |

### docs/restructure-prompt.md

| 파일:줄 | 무엇이 박혀 있나 | 분류 | 판단 | 이유 |
|---|---|---|---|---|
| `:145–154` (PROMPT 2절) | `#phone`, 390×844, `data-screen` · `on`, `data-action` 과 `const a`, `data-v`, `__screen()` 등 | 과제 | 일부러 둠 | HTML 기술 계약 — 과제와 무관하게 같다 |
| `:163` | "흰 배경에서 4.5:1 이상" | 상수 | 일부러 둠 | 검사 D 의 기준과 같은 값 |
| `:176` | "오류는 계획의 `errors` 대로 알린다." | 과제 | **고쳐야 함** | 위 10번 |
| `:26,32` (사람용 메모) | "치환 자리 다섯", "원본 흐름(`flows/original.json`)" | 과제 | **고쳐야 함** | 위 11번 |
| `:7–12,43–51` (사람용 메모) | Run 1 출처, Run 4·5 · 67개 근거 | 실행 | 일부러 둠 | 기록 |
| `:262,263` (재시도 블록 모양 메모) | `screen=bank`, `bank-yes` | 과제 | 일부러 둠 | 사람용 예시 |
| `{{TASK_*}}` 슬롯들 | 과제마다 다른 문단 | — | — | 11번에서 과제 파일로 옮겼다 (표에서 세지 않음) |
