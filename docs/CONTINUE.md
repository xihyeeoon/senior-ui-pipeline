# 이어서 작업하기

2026-10-02 기준. 새 세션이 첫 턴부터 이어갈 수 있도록 현재 상태와 남은 일을 적어둔다.
구조와 실행법은 `README.md`, 재구성 변경 내역은 `restructure-changelog.md`,
재구성 3회 비교는 `restructure-runs.md`, 자동 실행의 편차는 `variance-notes.md`,
실험 절차는 `experiment-guide.md` 에 있다. 이 문서는 그것들을 읽기 전에 보는 한 장이다.

## 지금 어디까지 왔나

**파이프라인**

```
캡처 → LLM 재구성 → 검사기 → (스타일 이식) → 실험
```

**보관 자료** — `kb/senior_kb.csv`. 파이프라인에 쓰지 않는다. 지우지도 않는다.
용도는 **재구성본 사후 대조** 하나다.

**질문:** 고령자가 이체 과업을 끝낼 수 있게 화면 구조를 다시 짤 수 있는가. 도구의
산출물은 **와이어프레임 수준의 구조 시안**이고 시각 디테일은 디자이너가 채운다.

**답 (현재까지):** LLM 재구성은 구조를 바꾸고 검사를 통과했다. 다만 3회 반복하면
"어디서 자를지" 가 매번 다르고(9·7·8화면), **검사기는 그 차이를 구분하지 못한다** —
셋 다 fatal 0 / warning 0. 갈라지는 것은 검사기 밖의 지표(돈 나가기 전 확인
3·1·3, 탭 수 30·28·30)다. 세 재구성본은 같은 조건을 받았으므로 이 비교는 유효하다.

(검사 I 추가 이전 기준. 현재 기준은 아래 산출물 표와 그 밑의 주를 참고한다.)

**DesignRepair 계열은 연구에서 뺐다 (2026-09-30).** 도구의 목적이 다르고(완성된
화면의 시각 품질 vs 구조 시안), 같은 입력 단위를 줄 수 없어(전체 파일은 TPM 한도
초과) 공정한 비교가 성립하지 않는다. "규칙 기반이 구조를 바꿀 수 있는가" 는 더
이상 연구 질문이 아니다. 경위는 히스토리 참고 (커밋 `66186fe` 까지).

| 산출물 | 위치 | 상태 |
|---|---|---|
| 원본 프로토타입 (8화면, 실제 캡처 반영) | `inputs/original_transfer.html` | 완료 |
| LLM 재구성 Run 1 (9화면) | `results/restructured_transfer.html` + `flows/restructured.json` | audit **fatal 0 / warning 0** |
| LLM 재구성 Run 2 (7화면) | `results/restructured_run2.html` + `flows/run2.json` | audit **fatal 0 / warning 0** |
| LLM 재구성 Run 3 (8화면) | `results/restructured_run3.html` + `flows/run3.json` | audit **fatal 0 / warning 0** |
| LLM 재구성 Run 4 (7화면, 자동 파이프라인) | `results/restructured_run4.html` + `flows/run4.json` | 당시 통과 / 현재 검사기 기준 **I fatal 2** |
| 3회 비교 | `docs/restructure-runs.md` | 완료 (탭 수·확인 횟수는 손으로 셈) |
| 검사기 | `senior_ui/audit/` + `flows/*.json` | 완료, 다섯 흐름 모두 동작 |
| 변경 기록 (28건, SDF 대조) | `docs/restructure-changelog.md` | 완료 |

**표의 fatal 수치는 그 판정을 받은 시점 기준이다.** Run 1·2·3 의 `fatal 0` 은
검사 I(선택지 보존, `b2db795`)가 생기기 전의 값이다. 지금 검사기로 다시 걸으면
셋 다 I 에서 fatal 3건이 난다 (원본 `pick-bank` 67개 중 58개, `quick` 4개 중 1개,
`num` 11개 중 1개 누락) — 측정값은 `tests/baseline/` 에 있고 근거는
`tests/README.md` 에 적혀 있다. Run 4 의 두 수치는
`results/audit_run4.json`(당시)과 `results/audit_run4.recheck.json`(집계 버그를
고치기 전의 재검사)이다. **네 run 의 지금 수치는 `results/audit_*.v3.json` 에 있다**
(Run 1·2·3 은 fatal 3 · warning 3, Run 4 는 fatal 2 · warning 8). Run 1·2·3 의
warning 3 은 검사 D 가 기준에 못 미치는 글자를 하나씩 적은 것이다 — 눌릴 수 없는
'다음' 버튼 둘(2.52:1)과 금액 자리의 '0원'(2.61:1)이고 셋 다 3.0:1 이 필요하다.
`.v2.json` 은 그 앞 단계의
기록이고 `fix/audit-accuracy-1` 이전 수치이므로 더 이상 지금 수치가 아니다 —
그 커밋들에서 검사 I 가 낱말 단위로 찾게 되면서 Run 1·2·3 의 fatal 이 1 에서 3 으로
늘었다.

마지막 코드 변경: **2026-10-01 코드 정리** — DesignRepair 시기 파일 삭제, `tools/`
를 `senior_ui/` 패키지와 `web/`·`flows/` 로 이동, 큰 함수 분리. 동작은 바꾸지
않았고 `tests/` 의 기준값 비교로 확인했다 (`refactor/cleanup` 브랜치).

## 남은 일 (미뤄둔 순서대로)

1. ~~Run 2·Run 3 구현~~ **완료 (2026-09-17).** 결과는 `restructure-runs.md`. 이전
   대화의 설계 표는 없어서 CONTINUE 의 요약만으로 Run 1 코드 위에 구현했다 — 따라서
   Run 1 에 더 강하게 닻내림돼 있다. 후속: 검사기에 "돈 나가기 전 명시적 확인 횟수"와
   "화면당 결정 수" 지표를 넣어야 셋이 갈라진다. 지금은 손으로 센 값이다.
2. **재구성본 화면별 분리본.** 화면을 파일로 쪼개는 도구(`tools/split_screens.py`,
   정리 전 경로)는 DesignRepair 시기 파일이라 삭제했다 — 히스토리 참고. 원본 8 ↔ 재구성 9 를
   비교창에 나란히 놓으려면 원본 경로와 화면 목록을 인자로 받는 형태로 새로 써야
   한다. Run 2·3·4 도 같은 도구로 나눠야 한다.
3. **3회 반복을 제대로 재기.** 지금의 Run 1·2·3 은 한 대화 안에서 연달아 만든 것이라
   뒤 설계가 앞에 닻내림된다. 측정된 편차는 하한이다. 서로 모르는 세 세션에서
   같은 프롬프트로 돌려야 진짜 편차가 나온다.
4. ~~`inputs/1.png`~`8.png` 처리 결정~~ **추적 해제 (2026-10-01).** `git rm --cached`
   로 9개를 빼고 `.gitignore` 에 `/inputs/*.png` 를 넣었다. 파일은 로컬에 그대로
   있다. **다만 히스토리에는 남아 있다** — `69565f3` 커밋이 그 파일들을 담고 있어서,
   저장소를 public 으로 돌리거나 외부에 넘기려면 그 전에 히스토리를 고쳐야 한다
   (`git filter-repo --path inputs/1.png --invert-paths` 등, force push 필요).
   지금은 private 이므로 당장의 노출은 없다.
5. **옛 폴더 이름 변경.** `C:\Users\xihye\designrepair` 에는 9월 10일에 생긴
   **별개의 이커머스 DesignRepair 프로젝트**가 들어 있다. 이 저장소와 무관하다.
   `designrepair-ecommerce` 로 바꾸기로 했으나 VS Code 워크스페이스가 잡고 있어
   실패했다. 그 창을 닫은 뒤 `Rename-Item` 하면 된다.

## 본실험 전 할 일 (지금 하지 않음)

1. **재구성본 스타일을 원본 CSS 로 통일.** 지금은 구조와 시각이 한꺼번에 다르다.
   비교 변수를 구조 하나로 좁히려면 색·글꼴·여백을 원본과 같게 맞춰야 한다.
2. **`senior_kb.csv` 를 와이어프레임 범위로 정리.** 색·대비·여백 항목은 이 단계에서
   판정할 수 없다. 사후 대조에 쓸 때 그 항목들을 빼야 한다.
3. **`outputs/` 를 실험별 하위 폴더로 분리.** 지금 세 실험이 이름으로만 구분된다.
   경로가 바뀌면 `senior_ui/collect_results.py` 와 `results/` 사본도 따라 고쳐야 한다.

## 반드시 알아야 할 함정

- **`outputs/` 는 ignore 대상.** 손으로 쓴 `restructured_transfer.html`,
  `restructured_run2.html`, `restructured_run3.html` 이 거기 있다. 고치면
  `python -m senior_ui.collect_results` 를 돌려야 `results/` 사본이 따라온다.
  안 돌리면 커밋되는 사본이 낡은 채 남는다. 테스트의 기준값도 `results/` 를 입력으로
  쓰므로, 사본이 낡으면 `pytest` 가 보는 것도 낡은 것이다.
- **재구성 루프는 `PYTHONUTF8=1` 이 있어야 한다.** 파일은 전부
  `encoding="utf-8"` 로 열지만, 로그를 찍는 `restructure/loop.py` 의 `log()` 는
  stdout 을 UTF-8 로 맞추지 않는다. cp949 콘솔에서 실행하면 요약을 찍다가
  `UnicodeEncodeError` 로 죽는다 (실행 자체는 이미 끝난 뒤다).
  `$env:PYTHONUTF8=1` 을 앞에 두거나 `시작.bat` 처럼 환경에 넣어 둔다.
  검사기·`audit.report`·`build_index`·`experiment.report` 는 스스로
  `reconfigure` 하므로 필요 없다 — 단 `experiment.report` 의 "세션 파일이
  없습니다" 한 줄만 그 앞에서 찍힌다.
- **검사기는 흐름 파일이 필요하다.** `--flow flows/original.json` (기본),
  `restructured.json`, `run2.json`, `run3.json`, `run4.json`.
  `derived_from_original: false` 면 화면 대응이 필요한 검사는 수행하지 않고
  `checks_stood_down` 에 기록한다. **화면 이름이 같다고 같은 화면이 아니다** —
  원본과 재구성본 둘 다 `bank`, `amount` 가 있고 전혀 다른 화면이다.
- **검사는 두 단계다.** 와이어프레임은 A·B·C·F·I 만(`--stage wireframe`), 스타일
  이식 후에는 A~I 전부. 대비·레이아웃·상태 색을 아직 채우지 않은 산출물에 D·E·G·H
  를 들이대면 없는 일을 트집 잡는 셈이다. 무엇을 왜 건너뛰었는지는
  `checks_stood_down` 에 남는다.
- **검사기 F 항목은 `<title>` 의 영어도 잡는다.** "Run 2" 라고 쓰면 warning 이 난다.
  제목은 한글로 ("2회차").
- **셸 기본 폴더가 옛 경로일 수 있다.** 이전 세션이 `designrepair` 에서 시작됐다.
  새 세션은 `senior-ui-pipeline` 에서 시작해야 맞다. 명령은 절대경로로 쓰는 편이
  안전하다.
- **서버는 프로젝트 루트를 3003 으로 서빙한다.** 모든 도구의 기본 URL 이 여기를
  가정한다. 안 떠 있으면:
  `.\.venv\Scripts\python.exe -m http.server 3003 --directory .`
- **`.venv` 에는 pip 이 없다.** 패키지는 `uv pip install -r requirements.txt` 로
  넣는다.

## 아직 답 안 난 판단

- **비밀번호 셔플 제거** — 재구성본은 고정 배열이다. 보안 장치를 끈 것이라 은행
  보안팀이 결정할 사항. 설계상 권고로만 둔다.
- **비밀번호 4자리 자동 진행** — 확인 버튼 없이 완료로 넘어간다. 원본과 같은
  동작이지만 KS-4(의도치 않은 화면 전환) 경계선. 재검토 여지.
- **은행 추정 기능** — `3333` → 카카오뱅크처럼 앞자리로 추정한다. SOL 에 이미
  있는지 확인 안 됨. 없으면 새로 구현해야 하는 항목.
- **changelog 의 규칙 커버리지 33/46** — 내가 내 결과물을 채점한 것이라 낙관 쪽으로
  기운다. "부분 충족" 기준에 따라 달라진다. 표에서 실제 인용된 것은 26개다.
- **changelog 의 "해당 없음" 판정** — #11(account 분할)에 SDF-G2-3, #12(예금주 확인)에
  SDF-G9-3 이 실제로 대응한다. KB 에 구조 규칙이 11개 있다. 재판정이 필요하다.
- **검사 I 와 설계 판단의 충돌** — 원본의 `전액` 버튼을 안전을 위해 의도적으로
  지운 것(changelog #15)도 지금은 fatal 로 센다. 안전한 제거와 귀찮아서 빠뜨린
  것을 구분하지 못한다. `defect-types.md` 참고.

## 30초 상태 확인

**`시작.bat` 을 더블클릭하면** 확인 화면이 열립니다 (빌드 목록·화면 비교·검사 결과·변경 추적).
터미널로 보려면:

```powershell
cd C:\Users\xihye\senior-ui-pipeline
.\.venv\Scripts\python.exe -m senior_ui.viewer.build_index --print
```

옛 방식:

```powershell
cd C:\Users\xihye\senior-ui-pipeline
git log --oneline -3
.\.venv\Scripts\python.exe -m http.server 3003 --directory .   # 다른 터미널에서
.\.venv\Scripts\python.exe -m senior_ui.audit --flow flows\restructured.json `
   --build http://localhost:3003/results/restructured_transfer.html `
   --build-file results\restructured_transfer.html
# 지금 기준의 기대값: fatal 3 (검사 I 선택지 보존), fatal_total 3,
#                     warning 3 (검사 D 기준 미달 대비), exit 1

# 네 빌드를 한 표로 (JSON 은 사람이 못 읽는다)
.\.venv\Scripts\python.exe -m senior_ui.audit.report `
   Run1=results\audit_restructured.v3.json Run2=results\audit_run2.v3.json `
   Run3=results\audit_run3.v3.json Run4=results\audit_run4.v3.json `
   --details --out results\audit-report.md
```

Run 4 는 와이어프레임 단계로 검사한다 (`--stage wireframe`). 나머지 셋은 기본값인
styled 다 - 각 run 은 앞선 리포트와 같은 단계를 쓴다.

`.v3.json` 은 화면 측정과 실행 견고성을 고친 뒤(`fix/audit-accuracy-2`) 다시
검사한 것이다. `.v2.json` 은 집계 버그를 고친 뒤(`fix/audit-counting`)의 기록이고,
`.v2` 가 없는 파일은 그보다 더 앞이다 - fatal 목록은 비어 있지 않은데
`fatal_total` 이 0 인, 그 버그 자체의 기록이다. 셋 다 덮어쓰지 않고 남겨 둔다.
