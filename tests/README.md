# 정리 전 기준값과 회귀 테스트

구조 정리는 동작을 바꾸지 않아야 한다. 이 폴더는 그 "바꾸지 않았음" 을 사람 눈이
아니라 파일 비교로 확인하기 위한 것이다. `senior_ui/` 는 한 줄도 건드리지 않는다.

예외가 한 건 있다. `senior_ui/audit/report.py` 는 어떤 audit JSON 을 줘도
`KeyError: 'I'` 로 죽었다 (검사 I 를 더한 `b2db795` 부터). 실행이 안 되면 정리 후에
달라졌는지 확인할 방법이 없으므로, 죽지 않게만 고치고 (`SEVERITY` 에 `I` 추가,
제목의 `A~H` → `A~I`) 그 상태를 기준값으로 잡았다. 리포트 내용 자체의 다른 문제는
그때 그대로 두었고 `fix/audit-counting` 에서 고쳤다 — 아래 '`report/` 에 담긴
동작' 을 보라.

## 쓰는 법

```powershell
.\.venv\Scripts\python.exe -m pytest                # 빠름, 브라우저 없음 (1분 남짓)
.\.venv\Scripts\python.exe -m pytest -m browser     # 실제로 다시 걷는다 (10분 남짓)
```

기준값을 다시 뽑을 일이 생기면 (= 동작을 의도적으로 바꿨을 때만):

```powershell
.\.venv\Scripts\python.exe tests/capture_baseline.py
```

건수는 적지 않는다 — 늘 바뀐다 (`pytest --co -q` 로 본다).

브라우저 테스트(`conftest.py` 의 `server` fixture 하나를 함께 쓴다) · 기준값 캡처 · 그
안의 mock 실행은 저마다 빈 포트에 제 서버를 띄운다 (`config.AUTO_PORT`, 11-9). 그래서
**같은 포트를 명시하지 않으면 동시에 돌려도 된다** — 전에는 모두 `:3003` 하나를 써서
먼저 끝난 쪽이 다른 쪽이 쓰던 서버를 껐다. 테스트가 여는 주소는 fixture 가 실제 포트로
맞춘다 (`capture_baseline.BASE_URL`). `--port N` 을 주면 (`pytest -m browser --port
3010`, `capture_baseline.py --port 3010`) 그 포트에 이미 있는 서버가 **이 작업 트리를**
서빙할 때만 그대로 쓰고 (`senior_ui/devserver.py` 의 확인 파일 `/.devserver-id`), 아니면
멈춘다. 기준값은 그 포트가 서빙하는 내용에 전적으로 달려 있어서, 다른 worktree · 다른
폴더의 서버를 그대로 쓰면 기준값이 무엇을 기준으로 한 것인지 알 수 없어진다.

기준값을 다시 뽑을 때는 차이를 전부 보고 설명되는 파일만 바꾼다. 전체를 다시 뽑으면
원본의 비밀번호 숫자판이 다시 섞여 스냅샷이 바이트 단위로 달라진다 — 그 차이뿐인
스냅샷은 되돌린다 (`--out <다른 폴더>` 로 뽑아 견준다).

## 파일

| 파일 | 하는 일 |
|---|---|
| `_api.py` | 테스트가 쓰는 함수를 한곳에서만 가져오는 어댑터 |
| `ignore.py` | 실행마다 달라지는 키 목록(`IGNORE`)과 비교 전 정규화 |
| `capture_baseline.py` | 기준값을 한 번 뽑는 스크립트 |
| `test_baseline.py` | 저장된 스냅샷으로 다시 계산해 비교 (브라우저 없음) |
| `test_drive.py` | 브라우저로 실제로 다시 걷고 비교 (`-m browser`) |
| `test_restructure_bugs.py` | 재구성 루프의 버그 재현. 모델도 브라우저도 부르지 않는다 |
| `test_model_upgrade.py` | 모델 바꾸기 준비 - 기본값 · 모델별 부르는 방식 · 분당 한도 · 확인 명령 · 가격. 실제 API 는 부르지 않는다 |
| `test_run_settings.py` | 12번 실행 설정 - 추론형의 출력 길이 · 호출 사이 대기(남은 토큰 확인) · reasoning_effort 를 늘 보내고 남기기. gpt-4o 는 그대로인지. 실제 API 는 부르지 않는다 |
| `test_select.py` | C 후보 고르기 (`python -m senior_ui.select`) - 가짜 실행 폴더 다섯(통과 셋 · 실패 하나 · 도구가 고친 것 하나)으로 순위와 제외 이유, 규칙 파일의 문지기 · 순서 · 가중치, 결과에 남는 규칙과 커밋, 지난 결과와 나란히. `-m browser` 에서는 mock 실행(preserved-all · bill-identity)을 실제로 돌리고 그 폴더로 끝까지 돈다 |
| `test_preflight_loop.py` | 최신 모델(gpt-6.1-sol · gpt-6-astra) 첫 실행의 형식 검사 거짓 실패 - 실제 답을 `fixtures/real_runs/` 에 복사해 두고 다시 넣는다. 모델도 브라우저도 부르지 않는다 |
| `test_judge_inputs.py` | 판정 입력(`audit/inputs.judged_flow`) - 모델이 쓴 truth · 완료 화면 값 · done_amount · derived_from_original · task · stage 가 판정을 바꾸지 못하는지, 같은 빌드를 루프와 검사기 CLI 가 같게 판정하는지, 오류 경로에서 뜬 대화상자를 판정하는지. 걷기만 가짜다 |
| `test_entrances.py` | 과제 밖 입구 (검사 K) - 과제 파일의 확정 목록(이름은 탭 대상마다 하나), 원본의 data-action · aria-label · 무동작 분기, 판정(이름 + 누를 수 있게 보임 · 지운 빌드 fatal · 숨긴 것은 안 셈 · reveal 뒤 통과 · 글자는 기록만 · 겹침 사례 일곱), 프롬프트의 한 문장과 기술 계약 한 줄. `-m browser` 에서는 mock 넷(entrances-none · -reveal · -folded · pass)과, 실제 원본에서 입구 하나만 지운 빌드 일곱(같은 낱말은 남김)을 실제로 걷는다 |
| `test_format_rules.py` | 형식 검사(`reply.py`)가 검사기의 규칙 함수(back_to · 화면 목록 · 방문 이름 · 조작부 이름)를 그대로 쓰는지 |
| `test_tool_failures.py` | 도구 버그(종료 2 · internal_error) · 바깥 문제(인프라 예산) · 시작 실패(cannot_start) · CLI 의 `--out` · 인프라 예산의 출처 |
| `test_real_runs_browser.py` | `fixtures/real_runs/` 의 첫 답을 루프의 길과 CLI 로 실제로 판정한다 (sol 은 K fatal 1 - 입구 31개 중 2개만 남았다 · astra 는 J 1 · K 1). `-m browser` |
| `test_ports.py` | 자동 실행의 포트 (11-9) - 루프 · pytest · 캡처는 빈 포트, 사람이 띄우는 서버는 3003, 둘이 같이 떠도 서로 끄지 않음, 루프백만, `--port` 일 때는 확인 파일로 재사용, 루프가 실제 포트로 원본 · 빌드를 여는지, 문서의 동시 실행 규칙. 서버는 띄우지만 브라우저는 부르지 않는다 |
| `test_stuck.py` | 같은 실패의 되풀이 = 막힘(stuck, 11-9) - fatal 의 (검사 · 대상 · 개수), 같은 실패 두 번이면 남은 예산을 쓰지 않고 멈춤, 바뀐 실패 · 개수만 다른 실패 · 사이에 낀 형식 실패는 계속, 통과한 실행은 막히지 않음, 고르기 도구가 stuck 을 통과 못 한 실행으로 봄. 모델도 브라우저도 부르지 않는다 (mock 은 `test_drive` 의 `mock_stuck`) |
| `test_refine_reveal.py` | 다듬기의 reveal 형식 (11-9) - 생성 · 다듬기 프롬프트가 같은 reveal 모양 블록을 쓰는지, 형식 검사가 배열로 온 reveal 을 (원소마다 action 이 있으면) 한 번 객체로 바꿔 받고 그 사실을 남기는지, 예비 실행 두 번의 다듬기 답(`fixtures/real_runs/refine_*`)이 형식 검사를 지나는지. 모델도 브라우저도 부르지 않는다 |
| `test_no_original.py` | 검사기는 원본 없이 통과를 내지 않는다 (11-9b) - 원본을 열지 못했거나 화면을 하나도 읽지 못하면 CLI 는 종료 2 (빌드는 걷지 않는다), 재구성 루프는 시작에서 cannot_start. `-m browser` 에서는 아무도 듣지 않는 포트의 원본 URL 로 CLI 를 실제로 돌린다 |
| `test_group_source.py` | 선택지 무리는 원본이 정한다 (11-9b) - 원본에서 무리였던 이름(`i_choices.original_groups`, 선언된 not_choices 는 뺀다)만 넘기는지, 생성물은 보지 않는지. `-m browser` 에서는 `fixtures/pages/i_one_per_section` 을 실제로 걸어 (가) 분류마다 하나씩 놓인 원본 무리의 값을 이전 규칙은 놓치고 새 규칙은 걸음마다 · reveal 에서 모두 세는지, (나) 화면마다 하나씩인 뒤로가기는 무리가 되지 않는지 본다 |
| `test_choice_roles.py` | 선택지 아님 선언(과제 파일 `not_choices`, 11-9) - 과제 파일의 모양, 판정 입력이 붙이고 모델의 것은 버리는지, 검사 I 가 선언된 무리를 판정에서 빼고 `choice_groups_not_choices` 로 남기는지, 프롬프트 · 형식 검사가 그 무리만 받치는 `MENU_TABS` 의 참조를 요구하지 않는지, 설명서의 표. `-m browser` 에서는 저장된 공과금 답 셋(`fixtures/real_runs/bill_sol`)을 바뀐 검사기로 판정한다 (11-9 에서는 셋 다 I 하나 - 항목이 하나뿐인 분류의 메뉴 항목 6개, 무리를 원본이 정한 11-9b 부터 셋 다 fatal 없음) |
| `test_storyboard.py` | 화면설계서 (`python -m senior_ui.storyboard`, 11-12) - 보이는 요소를 번호 매긴 항목으로 (선택지 무리는 하나, 대표는 읽는 순서의 첫 것), 누르기 결과의 말 (다른 화면 · 같은 화면 · 아무 일 없음 · 꺼짐), 영역 묶기의 검사 · 한 번 다시 묻기 · "기타" · mock 의 정해진 답 · mock 은 키를 읽지 않음 · 모델 호출 기록 (가짜 호출), 단 나누기 · 동작 문구, 통과하지 못한 실행은 만들지 않음 (종료 2), 원본 지문의 줄끝. 11-12b 의 형식 - 로우파이 덮개가 배치 속성을 쓰지 않고 걷는 동안 꺼져 있는지, 주석 꼴 동작 문구, 장 제목 꼬리표 · 예외(비활성 · 모델이 표시한 빈 화면만), 화면 이름(영역 묶기 답 → 계획의 화면 목적 앞부분) · 경로 · 정보칸, 와이어플로(흐름 명세에서만 화살표 · 한 장에 들거나 띠마다 나눔), 기능-화면 표(● 흐름이 머무는 상태 · ○ 조건별 장 · 선택지 · 숫자판은 원본의 값으로 검사 I 의 경계 규칙대로 찾고 찾은 수 · 빌드의 이름 · 값이 아닌 글자는 보지 않음 · 원본 값이 없으면 이름으로 · 입력 칸 · 원본 화면 칸 · 보지 못한 줄, 11-12c), `--regions-from`(모델 없이 다시 쓰기 · 번호가 다르면 종료 2). `-m browser` 에서는 (가) `fixtures/storyboard/actions.html` 로 동작 확인 - 다른 화면 · 같은 화면 · 아무 일 없음 · 무리 · 꺼짐 · 과제 밖 입구 · 가려진 요소 · 늦게 넘어가는 화면 · 스크롤 화면 한 장 · 오류 · 펼침 · 덮개를 켜기 전후 위치 · 크기 · 글자 크기 · 굵기가 같은지 · 덮개 표시가 요소 값에 섞이지 않는지 · 원본 걷기(선택지 무리의 값까지), (나) mock pass 실행 · 저장된 이체 답 · 저장된 공과금 답으로 끝까지 만들어 `baseline/storyboard/` 와 견주고, 실행 폴더의 원래 파일이 바이트까지 그대로인지 · `index.html` 이 `storyboard.json` 만으로 다시 그려지는지 · mock pass 에서 다른 이름(amt-num · amt-set)으로 그린 숫자판 · 빠른 금액이 값으로 찾아지는지 본다, (다) 저장된 이체 답의 설계서를 그 `storyboard.json` 으로 `--regions-from` 해서 영역이 그대로인지 · 한 요소를 뺀 답으로는 만들지 않는지 |
| `storyboard_fixture.py` | 저장된 실제 답(`fixtures/real_runs/`)으로 실행 폴더를 꾸민다 - 루프와 같은 순서로 답을 받고 검사도 루프의 길로 돌려 `summary.json` 까지. 설계서 기준값과 시험이 쓴다 |
| `fixtures/storyboard/` | 설계서 동작 확인용 작은 HTML 과 그 흐름 명세 (`actions.html` · `actions.flow.json`) |
| `fixtures/real_runs/` | 실제 실행의 답 그대로 (`sol` = `outputs/restructure_auto/20261006-124055`, `astra` = `20261006-124838`, `bill_sol` = `20261007-103023-bill` 의 시도 2 · 3 · 4, `refine_215902` · `refine_102041` = 두 실행의 다듬기 답 `refine.response.txt` 와 그때의 계획). `attempt_N.response.txt` · 첫 계획(`plan.json`) · 도구가 넣은 선택지 데이터(`preserved.json`, `attempt_N.html` 의 블록). 설계서의 맨 앞장에 쓰려고 그 실행의 진단(`diagnosis.json` - `refine_102041` · `bill_sol`)과 `bill_sol` 의 계획(`plan.json`, 시도 4 의 것)을 실행 폴더에서 그대로 더했다 (11-12) |
| `fake_openai.py` | `openai.OpenAI` 의 대역 (with_raw_response 의 헤더 · Responses · models.list · 429 · 400) |
| `baseline/` | 기준값. 마지막 캡처 실행의 결과다 |
| `fixtures/sessions/` | `session_report` 용 가짜 세션 4건 |
| `fixtures/report/` | `audit.report` 의 입력으로 고정해 둔 audit JSON 4건 |

### `_api.py` 가 있는 이유

테스트 본문은 `senior_ui/` 를 직접 import 하지 않는다. 전부 `_api.py` 를 거친다.
정리 단계에서 파일이 옮겨지거나 이름이 바뀌면 **`_api.py` 의 import 줄만** 고치면
되고, 테스트 본문은 한 줄도 고치지 않는다. 고쳐야 할 곳이 생기면 그것은
"구조만 정리" 가 아니라는 신호다.

## 기준값에 들어 있는 것

네 가지 경우를 `audit.py` 의 `main()` 과 같은 순서
(원본 drive → 빌드 drive → `audit()` → `apply_stage`)로 실행한 결과다.

| 이름 | 빌드 | 흐름 |
|---|---|---|
| `original_vs_original` | `inputs/original_transfer.html` | `flows/original.json` |
| `run1` | `results/restructured_transfer.html` | `flows/restructured.json` |
| `run2` | `results/restructured_run2.html` | `flows/run2.json` |
| `run3` | `results/restructured_run3.html` | `flows/run3.json` |

빌드는 `results/` 에서 가져온다. `outputs/` 는 `.gitignore` 에 있어 PC 마다 내용이
달라서 기준값의 입력이 될 수 없다.

경우마다 `snapshots.json`(drive 결과 그대로) · `audit.json` ·
`audit.styled.json` · `audit.wireframe.json` 이 있고, `run1~3` 에는
`validate_flow.json` 이 더 있다. 그 밖에:

- `retry_block/{run1,run2,run3,synthetic}.txt` — 합성 리포트는 실제 실행 세 개로는
  다 밟히지 않는 세 갈래(파생 fatal · `stack` 이 붙은 JS 오류 · Playwright 로그
  형식의 detail)를 한자리에 넣은 것이다.
- `brief_failure.txt` — 1,100자짜리 Playwright 로그를 한 줄로 접은 결과
- `prompt/choices_block.txt` — 원본이 가진 선택지 요약 (검사 I 가 세는 바로 그 집합)
- `prompt/attempt_1.txt` — 첫 시도의 프롬프트 **전문**
  (`build_prompt(load_template(), 원본 HTML, "", choices)`)
- `prompt/retry_run1.txt` — 재시도 프롬프트 전문. `retry_block/run1.txt` 를 슬롯에
  넣은 것이다 (`capture_baseline.PROMPT_RETRY_CASE`)
- `parse_reply.json` — `mock_reply` 의 답을 `parse_reply` 로 되읽은 결과
  (HTML 은 28KB 라 해시만 남긴다)
- `mock_*.json` — `--mock` 일곱 모드의 `summary.json`
  (`capture_baseline.MOCK_RUNS`). 일곱은 Run 1 빌드의 은행 목록 한 줄과
  `00`·`전액` 을 채우는 방법(배열을 읽는가, 마크업에 쓰는가)과 오류 처리
  (`model.ERRORS`)에서만 다르고, 그 차이 때문에 각각 다른 자리에서 갈린다.
  `mock_fail` 은 검사까지 가서 떨어진다 (`passed=false`, 종료 코드 1) — 두 시도가
  같은 fatal 이라 시도 2 에서 막힘(`stopped_reason: stuck`)으로 끝난다. `mock_stuck` 은
  `preserved-some` 을 예산 3 으로 돌려 남은 예산을 쓰지 않고 시도 2 에서 멈추는 것을 본다.
  `mock_pass` 와 `mock_preserved_all` 은 통과한다 (`passed=true`, 종료 코드 0),
  `mock_preserved_some` 은 검사 I 에서, `mock_preserved_none` 은 형식 검사에서
  떨어진다. `mock_errors_undeclared` 는 오류 경로를 적지 않아 형식 검사에서,
  `mock_errors_unhandled` 는 오류 경로는 적었지만 오류 처리가 없어 검사 J 에서
  떨어진다. `mock_entrances_none` 은 과제 밖 입구를 넣지 않아 검사 K 에서 떨어지고,
  `mock_entrances_reveal` 은 입구를 [다른 메뉴] 를 눌러야 그리고, `mock_entrances_folded`
  는 접힌 `<details>` 에 넣었지만, 둘 다 흐름 명세의 reveal 로 펼쳐 보아 통과한다.
  나머지 이체 모드는 첫 화면에 입구를 보이게 넣는다 (`model.ENTRANCE_MODES`). mock 실행은 `.mock-outputs/` 를 쓴다 — 통과한 빌드가
  `outputs/restructured_auto.*` 를 덮지 않게 떼어 놓았다 (이제 `--mock` 의
  기본값이기도 하다. 캡처는 같은 폴더를 환경 변수로 한 번 더 못박는다)
- `session_report.md` / `.csv`
- `bill/` — 공과금 과제 (`tasks/bill.json`). `original_vs_original/`
  (`inputs/original_bill.html` 을 `flows/original_bill.json` 으로, 이체와 같은 네
  파일) · `prompt/` (`choices_block.txt` · `plan.txt` · `attempt_1.txt` — 계획은
  `model.BILL_PLAN`) · `mock_bill_identity.json` (`--task bill --mock bill-identity`
  의 `summary.json`, 통과한다). 공과금만 다시 뽑을 때는
  `tests/capture_baseline.py --only bill` — 이체 기준값은 건드리지 않는다. 실행마다
  흔들리는 것은 이체와 같이 비밀번호 숫자판뿐이다 (`ignore.SNAPSHOT`, 두 번 뽑아
  견줘 확인했다)
- `storyboard/` — 화면설계서의 `storyboard.json` 셋 (그림은 두지 않는다). `mock_pass`
  (`--mock pass --attempts 1` 실행 - 장 11 · 항목 85), `refine_102041` (저장된 이체 답 -
  장 10 · 항목 91), `bill_sol_4` (저장된 공과금 답 - 장 18 · 항목 404). 영역은 `--mock` 의
  정해진 답이다. 저장 전에 만든 시각 · 도구 커밋 · 걸린 시간 · 실행 id · 커밋 · dirty ·
  원본 지문의 출처(값은 비교한다) · 호출 시간을 자리만 남긴다
  (`capture_baseline.strip_storyboard`). 설계서의 페이지는 시각과 난수를 고정하므로
  (`walk.FIXED_TIME` · `SEEDED_RANDOM`) 비밀번호 숫자판도 흔들리지 않는다 - 두 번 만들어
  기준값과 같았다. 이것만 다시 뽑을 때는 `tests/capture_baseline.py --only storyboard`
  (다른 기준값은 건드리지 않는다)
- `report/four_runs.md` / `report/four_runs.details.md` —
  `senior_ui.audit.report` 가 `fixtures/report/` 의 audit JSON 네 개를 나란히
  놓은 md (`--details` 를 붙인 것과 안 붙인 것)

### 지금 기준값이 담고 있는 동작 (참고)

`audit.json` (검사 전부) 기준. 괄호는 `audit.wireframe.json` (재구성 루프의 단계).

| 경우 | passed | fatal | warning | 화면 |
|---|---|---|---|---|
| `original_vs_original` | ○ | 0 | 3 (D 2 · J 1) (wireframe 1) | 8/8 |
| `bill/original_vs_original` | ○ | 0 | 2 (D 2) (wireframe 0) | 8/8 |
| `run1` | ✕ | 4 (I 3 · K 1) | 4 (D 3 · I 1) (wireframe 1) | 9/9 |
| `run2` | ✕ | 4 (I 3 · K 1) | 4 (D 3 · I 1) (wireframe 1) | 7/7 |
| `run3` | ✕ | 4 (I 3 · K 1) | 4 (D 3 · I 1) (wireframe 1) | 8/8 |

`run1~3` 의 fatal 중 셋은 검사 I(선택지 보존)다 — 원본의 `pick-bank` 67개 중 58개,
`quick` 의 `all`, `num` 의 `00` 이 생성물에 없다. 나머지 하나는 검사 K(과제 밖 입구)다 —
원본의 입구 31개가 하나도 없다. 원본 대 원본은 입구 31/31 (공과금 32/32). mock 실행:
`mock_pass` · `mock_preserved_all` · `mock_entrances_reveal` · `mock_entrances_folded` ·
`bill/mock_bill_identity` 는 통과하고, `mock_fail` 은 검사에서 (2회 - 같은 실패라 막힘), `mock_preserved_some` 은 검사 I 에서
(`mock_stuck` 은 같은 것을 예산 3 으로 - 시도 2 에서 막힘),
`mock_preserved_none` · `mock_errors_undeclared` 는 형식 검사에서,
`mock_errors_unhandled` 는 검사 J 에서, `mock_entrances_none` 은 검사 K 에서 떨어진다.

정리 단계에서는 `metrics.fatal_total` 이 0 인데 `fatal` 목록에는 1건이 있는 버그가
기준값에 담겨 있었다 (집계가 검사 I 보다 앞에 있었다). `fix/audit-counting` 에서
고쳤고, 지금은 `test_audit_bugs.py` 가 반대 — 목록과 숫자가 같다 — 를 단언한다.

### `report/` 에 담긴 동작

`report/` 는 `senior_ui.audit.report` 의 출력 전문이다. 정리 단계에서는 여기에
리포트 **내용**의 문제 두 가지가 그대로 담겨 있었고, 둘 다 `fix/audit-counting`
에서 고쳤다.

- `개요` 의 `fatal` 행이 총 개수 하나였다 → 이제 `fatal_root`(독립) ·
  `fatal_derived`(파생)를 함께 보이고, 표 아래에 두 값이 무엇인지 적는다.
- `핵심 지표` 표에 검사 I 행이 없었다 → 이제 "빌드에 없는 원본 선택지" 행이
  있다 (`pick-bank 58개` 처럼 개수만, 67개짜리 목록이 표를 덮지 않게).

### 입력은 `fixtures/report/` 에 고정해 둔다

`REPORT_ARGS` 는 `tests/fixtures/report/` 의 audit JSON 네 개(집계 버그를 고친 뒤
다시 검사한 Run 1~4 = `results/audit_*.v2.json` 의 사본)를 읽는다. `results/` 를
직접 읽지 않는 이유는 그 폴더가 파이프라인의 산출물이어서다 — 다시 검사하면
내용이 바뀌고, 그러면 리포트 기준값이 "`report.py` 가 달라졌는지" 가 아니라
"검사 결과가 달라졌는지" 를 따라 흔들린다. 사본은 고정물이므로 손으로만 바꾼다.

### `report/` 에서 제외한 값은 없다

날짜·시각처럼 실행마다 바뀌는 값을 비교에서 빼야 하는지 확인했는데, **뺄 것이
없었다.** 출력에 실행 시각이 들어가는 자리가 아예 없고(`render()` 는 제목·표·입력
목록만 쓴다), 입력 네 개는 고정물이다. `## 입력` 절에 적히는 경로도 그 JSON 안의
`inputs.repaired` 값(`http://localhost:3003/...`)이라 PC 마다 달라지지도 않는다.
그래서 두 md 는 전문을 바이트까지 비교한다.

확인 방법: `capture_baseline.capture_audit_report` 를 다른 폴더에 두 번 돌려
`tests/baseline/report/` 와 바이트 비교했다 — 세 출력이 모두 같았다.

## 무시하는 키 (`IGNORE`)

`capture_baseline.py` 를 두 번 돌려 모든 출력 파일을 키 단위로 비교했다. 실제로
달라진 것은 **딱 한 가지 원인**뿐이었다.

> 원본 시제품의 비밀번호 숫자판은 그릴 때마다 숫자를 섞는다.
> `inputs/original_transfer.html` 의 `keyButtons(shuffled(PW_KEYS), 'pw')`
> 이고, 화면의 `재배열` 버튼도 같은 함수를 다시 부른다.

그래서 섞인 순서가 그대로 들어가는 세 경로만 비교에서 뺀다
(`tests/ignore.py` 의 `SNAPSHOT`).

| 키 | 왜 흔들리는가 |
|---|---|
| `screens.*.choices.pw` | 숫자판 버튼 값을 DOM 순서로 모은다. 선택지 수집은 문서 전체를 보기 때문에 모든 화면 행에 들어간다 |
| `screens.password.text` | 화면 텍스트에 숫자판 순서가 그대로 들어간다 (`… 2 5 9 0 7 8 3 6 1 재배열 4 ⌫`) |
| `screens.password.wrapped` | 줄바꿈 수집 항목의 `text` 와 순서가 숫자 버튼이다 |

### 숫자판 순서는 `choices_block` 출력에 영향을 주지 않는다

프롬프트 기준값을 추가하면서 따로 확인했다. 원본을 두 번 `drive()` 해서
`choices.pw` 의 DOM 순서가 실제로 달라지는 것을 확인한 뒤(`['4','7','1',…]` →
`['7','4','8',…]`) 같은 스냅샷으로 `choices_block()` 을 부른 결과를 비교했다 —
**두 출력이 바이트까지 같았다.**

이유는 `choices_block` 이 값을 `set` 에 모아 **개수만** 쓰기 때문이다. 섞이는 것은
순서뿐이고 집합은 늘 `{0..9}` 라서 `pw — 10개 (PW_KEYS 10)` 라는 한 줄은 변하지 않는다.
값 자체나 순서를 프롬프트에 적는 자리가 생기면 이 성질이 깨지므로, 그때 다시
측정해야 한다. 그래서 `prompt/` 기준값은 브라우저 없이 저장된 스냅샷만으로 비교한다
(`tests/ignore.py` 에 넣을 것이 없다).

`choices` 전체가 아니라 `choices.pw` 만 뺀 것은 일부러다. `choices` 를 통째로
빼면 검사 I 가 보는 `pick-bank` 67개 선택지 집합까지 비교에서 사라진다 — 그것은
지금 fatal 1건의 주제이고, 가장 지켜야 할 값이다. `screens.*.text` 도 통째로
빼지 않고 `password` 화면만 뺐다. 나머지 화면의 텍스트는 두 실행이 똑같았고, 검사
F(언어)가 보는 값이다.

`REPORT` 는 **비어 있다.** 측정 결과 `audit()` · `apply_stage()` ·
`validate_flow` · `retry_block` · mock 실행 `summary.json` · `session_report` ·
`audit.report` 의 출력은 두 실행이 바이트까지 같았다. 리포트는 무시할 키 없이 그대로 비교한다 —
`fatal` / `warning` 은 순서까지 같아야 한다.

`test_baseline.py` 는 `IGNORE` 를 아예 쓰지 않는다. 저장된 스냅샷을 입력으로
쓰므로 입력이 고정되어 있고, 따라서 출력도 고정되어야 한다. 한 글자라도 다르면
실패다. `IGNORE` 는 브라우저를 다시 띄우는 `test_drive.py` 에서만 쓴다.

### mock 실행에서 지우는 값

이쪽은 "무시" 가 아니라 저장 전에 지운다 (`capture_baseline.strip_volatile`).

- `run_dir` — 실행 시각이 폴더 이름이다
- `attempts[].html` / `.flow`, `final.{html,flow,audit}` — 경로 안에 그 타임스탬프가
  들어 있어서 `<run>/attempt_1.html` 로 바꾼다
- `attempts[].seconds` — 걸린 시간
- `repro.openai_sdk` (요약과 시도 기록 양쪽) — 설치된 SDK 판이라 PC 마다 다르다.
  지우지 않고 `<sdk>` 로 바꾼다 — 값은 비교하지 않되 **기록이 있다**는 것은 비교한다.
  나머지 재현 기록(`temperature` · `seed` · `response_model` ·
  `system_fingerprint` · `prompt_template_sha256`)은 그대로 비교한다. 템플릿 해시는
  `docs/restructure-prompt.md` 가 바뀌면 달라지므로, 그때는 기준값도 같이 다시 뽑는다.

## `outputs/` 에 대해

`mock_reply` 는 `outputs/restructured_transfer.html` 을 읽는다. `outputs/` 는
추적하지 않으므로 그 파일이 없을 수 있다. 없을 때만 `capture_baseline.py` 가
`results/` 의 사본을 복사하고, 복사했으면 마지막에 그렇다고 알린다.

## 오류 경로 기준값 (2026-10-05, `feat/error-paths`)

검사 J 와 원본 흐름의 오류 경로를 더하며 다시 뽑았다. 정규화(`ignore.py`) 뒤에
남은 차이는 아래가 전부이고, Run 1~3 의 `passed` · fatal · warning 은 그대로다.

| 파일 | 차이 | 이유 |
|---|---|---|
| `run1~3/audit*.json` | `checks_stood_down` 끝에 `J/흐름에 오류 경로가 없다 …` 한 줄, 와이어프레임의 `stage_checks` 에 `J` | 옛 흐름에는 오류 경로가 없어 J 가 물러난다 |
| `*/snapshots.json` | `truth` 에 `ACCOUNT_WRONG` · `BANK_WRONG` | 원본 흐름의 truth 에 틀린 값을 더했다 |
| `original_vs_original/*` | `error_paths` (걷기 · metrics), warning 하나 (J, wrong-bank) | 원본의 은행 오류 문구("과목코드 오류")에 '은행' 이 없다 |
| `prompt/*.txt` | 오류 조건 절 · 흐름 명세의 `error_paths` 틀 · 새 화면 덮기 규칙 · 계획의 `errors` | `{{ERRORS}}` 슬롯. 틀린 값의 실제 값은 없다 (`test_error_paths.py` 가 본다) |
| `mock_*.json` | 예상 입력 토큰, 계획의 진단 7 · 변경 8, `mock_fail` 의 fatal 8 → 10 | 프롬프트가 길어졌다. MOCK_PLAN 에 오류 팝업 진단·변경. `fail` 의 둘은 J 의 파생 fatal |
| `mock_errors_*.json` | 새 파일 | 새 mock 두 모드 |
| `parse_reply.json` | 흐름의 `error_paths`, HTML 해시 | mock 빌드에 오류 안내를 바꿔 끼웠다 |
| `report/four_runs*.md` | 제목 `A~J`, 표에 J 줄 | 리포트 표에 J |

## 모델 바꾸기 준비 기준값 (2026-10-06, `feat/model-upgrade`)

`mock_*.json` 여덟 개(이체 일곱 + `bill/mock_bill_identity.json`)만 다시 뽑았다
(`capture_baseline.run_mock` + `strip_volatile` 로 그 파일만 덮었다 - 스냅샷 ·
검사 · 프롬프트 기준값은 손대지 않았다). 차이는 **키 추가뿐** 이고, 기존 값은 하나도
바뀌거나 지워지지 않았다 (`passed` · 종료 코드 · fatal · 토큰 어림 그대로).

| 추가된 키 | mock 에서의 값 | 이유 |
|---|---|---|
| `model_source` | `"config.DEFAULT_MODEL"` | 모델이 어디서 왔나 |
| `response_models` | `[]` | API 가 답한 판 이름들 - mock 은 없다 |
| `model_call` | gpt-4o 방식 (chat · 추론형 아님 · temperature/seed 보냄 · o200k_base) | 모델별 부르는 방식 |
| `tokens.*.reasoning` | `null` | 생각 토큰 칸 |
| `ratelimit` | `null` | 응답 헤더의 분당 한도 - mock 은 호출이 없다 |
| `cost` | 가격 gpt-4o 2.50/10.00, 금액 `null` | usage 가 없으므로 금액은 모른다 |

git diff 의 지워진 줄 33개는 모두 `"completion": null` 뒤에 쉼표가 붙은 것이다
(그 뒤에 `reasoning` 이 붙었다).
