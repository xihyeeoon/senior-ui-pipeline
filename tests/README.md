# 정리 전 기준값과 회귀 테스트

구조 정리는 동작을 바꾸지 않아야 한다. 이 폴더는 그 "바꾸지 않았음" 을 사람 눈이
아니라 파일 비교로 확인하기 위한 것이다. `tools/` 는 한 줄도 건드리지 않는다.

## 쓰는 법

```powershell
.\.venv\Scripts\python.exe -m pytest                # 빠름, 브라우저 없음 (25건, 0.2초)
.\.venv\Scripts\python.exe -m pytest -m browser     # 실제로 다시 걷는다 (18건, 2분 15초)
```

기준값을 다시 뽑을 일이 생기면 (= 동작을 의도적으로 바꿨을 때만):

```powershell
.\.venv\Scripts\python.exe tests/capture_baseline.py
```

`:3003` 을 이미 누가 쓰고 있으면 캡처는 멈춘다. 기준값은 그 포트가 서빙하는
내용에 전적으로 달려 있어서, 남이 띄운 서버를 그대로 쓰면 기준값이 무엇을 기준으로
한 것인지 알 수 없어진다.

## 파일

| 파일 | 하는 일 |
|---|---|
| `_api.py` | 테스트가 쓰는 함수를 한곳에서만 가져오는 어댑터 |
| `ignore.py` | 실행마다 달라지는 키 목록(`IGNORE`)과 비교 전 정규화 |
| `capture_baseline.py` | 기준값을 한 번 뽑는 스크립트 |
| `test_baseline.py` | 저장된 스냅샷으로 다시 계산해 비교 (브라우저 없음) |
| `test_drive.py` | 브라우저로 실제로 다시 걷고 비교 (`-m browser`) |
| `baseline/` | 기준값. 마지막 캡처 실행의 결과다 |
| `fixtures/sessions/` | `session_report` 용 가짜 세션 4건 |

### `_api.py` 가 있는 이유

테스트 본문은 `tools/` 를 직접 import 하지 않는다. 전부 `_api.py` 를 거친다.
정리 단계에서 파일이 옮겨지거나 이름이 바뀌면 **`_api.py` 의 import 줄만** 고치면
되고, 테스트 본문은 한 줄도 고치지 않는다. 고쳐야 할 곳이 생기면 그것은
"구조만 정리" 가 아니라는 신호다.

## 기준값에 들어 있는 것

네 가지 경우를 `audit.py` 의 `main()` 과 같은 순서
(원본 drive → 빌드 drive → `audit()` → `apply_stage`)로 실행한 결과다.

| 이름 | 빌드 | 흐름 |
|---|---|---|
| `original_vs_original` | `inputs/original_transfer.html` | `tools/flows/original.json` |
| `run1` | `results/restructured_transfer.html` | `tools/flows/restructured.json` |
| `run2` | `results/restructured_run2.html` | `tools/flows/run2.json` |
| `run3` | `results/restructured_run3.html` | `tools/flows/run3.json` |

빌드는 `results/` 에서 가져온다. `outputs/` 는 `.gitignore` 에 있어 PC 마다 내용이
달라서 기준값의 입력이 될 수 없다.

경우마다 `snapshots.json`(drive 결과 그대로) · `audit.json` ·
`audit.styled.json` · `audit.wireframe.json` 이 있고, `run1~3` 에는
`validate_flow.json` 이 더 있다. 그 밖에:

- `retry_block/{run1,run2,run3,synthetic}.txt` — 합성 리포트는 실제 실행 세 개로는
  다 밟히지 않는 세 갈래(파생 fatal · `stack` 이 붙은 JS 오류 · Playwright 로그
  형식의 detail)를 한자리에 넣은 것이다.
- `brief_failure.txt` — 1,100자짜리 Playwright 로그를 한 줄로 접은 결과
- `parse_reply.json` — `mock_reply` 의 답을 `parse_reply` 로 되읽은 결과
  (HTML 은 28KB 라 해시만 남긴다)
- `mock_pass.json` / `mock_fail.json` — `--mock pass --attempts 1` 과
  `--mock fail --attempts 2 --delay 0` 의 `summary.json`
- `session_report.md` / `.csv`

### 지금 기준값이 담고 있는 동작 (참고)

| 경우 | passed | fatal | warning | 화면 |
|---|---|---|---|---|
| `original_vs_original` | ○ | 0 | 0 | 8/8 |
| `run1` | ✕ | 1 | 0 | 9/9 |
| `run2` | ✕ | 1 | 0 | 7/7 |
| `run3` | ✕ | 1 | 0 | 8/8 |

`run1~3` 의 fatal 1건은 모두 검사 I(선택지 보존)다 — 원본의 `pick-bank` 67개 중
58개가 생성물에 없다. mock 실행은 둘 다 `passed=false` 로 끝난다.

**주의할 점이 하나 있다.** `audit.json` 의 `metrics.fatal_total` 은 0 인데
`fatal` 목록에는 1건이 있다. `audit.py` 가 `fatal_total` 을 세는 자리가 검사 I 가
findings 를 넣는 자리보다 앞이라서 그렇다. 이것은 정리 전부터 그런 동작이고, 이번
단계는 동작을 바꾸지 않으므로 그대로 기준값에 담았다. 고칠지 말지는 나중 판단이다
— 다만 정리 중에 **우연히** 고쳐지면 `pytest` 가 실패하므로 바로 드러난다.

## 무시하는 키 (`IGNORE`)

`capture_baseline.py` 를 두 번 돌려 모든 출력 파일을 키 단위로 비교했다. 실제로
달라진 것은 **딱 한 가지 원인**뿐이었다.

> 원본 시제품의 비밀번호 숫자판은 그릴 때마다 숫자를 섞는다.
> `inputs/original_transfer.html` 의 `const nums = [0..9].sort(()=>Math.random()-0.5)`
> 이고, 화면의 `재배열` 버튼도 같은 함수를 다시 부른다.

그래서 섞인 순서가 그대로 들어가는 세 경로만 비교에서 뺀다
(`tests/ignore.py` 의 `SNAPSHOT`).

| 키 | 왜 흔들리는가 |
|---|---|
| `screens.*.choices.pw` | 숫자판 버튼 값을 DOM 순서로 모은다. 선택지 수집은 문서 전체를 보기 때문에 모든 화면 행에 들어간다 |
| `screens.password.text` | 화면 텍스트에 숫자판 순서가 그대로 들어간다 (`… 2 5 9 0 7 8 3 6 1 재배열 4 ⌫`) |
| `screens.password.wrapped` | 줄바꿈 수집 항목의 `text` 와 순서가 숫자 버튼이다 |

`choices` 전체가 아니라 `choices.pw` 만 뺀 것은 일부러다. `choices` 를 통째로
빼면 검사 I 가 보는 `pick-bank` 67개 선택지 집합까지 비교에서 사라진다 — 그것은
지금 fatal 1건의 주제이고, 가장 지켜야 할 값이다. `screens.*.text` 도 통째로
빼지 않고 `password` 화면만 뺐다. 나머지 화면의 텍스트는 두 실행이 똑같았고, 검사
F(언어)가 보는 값이다.

`REPORT` 는 **비어 있다.** 측정 결과 `audit()` · `apply_stage()` ·
`validate_flow` · `retry_block` · mock 실행 `summary.json` · `session_report` 의
출력은 두 실행이 바이트까지 같았다. 리포트는 무시할 키 없이 그대로 비교한다 —
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

## `outputs/` 에 대해

`mock_reply` 는 `outputs/restructured_transfer.html` 을 읽는다. `outputs/` 는
추적하지 않으므로 그 파일이 없을 수 있다. 없을 때만 `capture_baseline.py` 가
`results/` 의 사본을 복사하고, 복사했으면 마지막에 그렇다고 알린다.
