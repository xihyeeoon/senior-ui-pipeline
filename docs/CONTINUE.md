# 이어서 작업하기

2026-09-17 기준. 새 세션이 첫 턴부터 이어갈 수 있도록 현재 상태와 남은 일을 적어둔다.
구조와 실행법은 `README.md`, 실험 결과는 `senior-kb-handoff.md`, 재구성 변경 내역은
`restructure-changelog.md`, 재구성 3회 비교는 `restructure-runs.md`,
실험 절차는 `experiment-guide.md`, DesignRepair 를 왜 뺐는지는
`comparison-validity.md`(닫힘) 에 있다. 이 문서는 그것들을 읽기 전에 보는 한 장이다.

## 지금 어디까지 왔나

**파이프라인**

```
캡처 → LLM 재구성 → 검사기 → (스타일 이식) → 실험
```

**보관 자료** — DesignRepair 결과, `kb/senior_kb.csv`. 파이프라인에 쓰지 않는다.
지우지도 않는다. 사후 대조와 기록용이다.

**질문:** 고령자가 이체 과업을 끝낼 수 있게 화면 구조를 다시 짤 수 있는가. 도구의
산출물은 **와이어프레임 수준의 구조 시안**이고 시각 디테일은 디자이너가 채운다.

**답 (현재까지):** LLM 재구성은 구조를 바꾸고 검사를 통과했다. 다만 3회 반복하면
"어디서 자를지" 가 매번 다르고(9·7·8화면), **검사기는 그 차이를 구분하지 못한다** —
셋 다 fatal 0 / warning 0. 갈라지는 것은 검사기 밖의 지표(돈 나가기 전 확인
3·1·3, 탭 수 30·28·30)다. 세 재구성본은 같은 조건을 받았으므로 이 비교는 유효하다.

**DesignRepair 계열은 연구에서 뺐다 (2026-09-30).** 도구의 목적이 다르고(완성된
화면의 시각 품질 vs 구조 시안), 같은 입력 단위를 줄 수 없어(전체 파일은 TPM 한도
초과) 공정한 비교가 성립하지 않는다. "규칙 기반이 구조를 바꿀 수 있는가" 는 더
이상 연구 질문이 아니다. 경위는 `comparison-validity.md` — 닫힌 문서다.

| 산출물 | 위치 | 상태 |
|---|---|---|
| 원본 프로토타입 (8화면, 실제 캡처 반영) | `inputs/original_transfer.html` | 완료 |
| 규칙 기반 수리본 | `outputs/repaired_transfer.html` | audit **fatal 7 / warning 47** |
| LLM 재구성 Run 1 (9화면) | `outputs/restructured_transfer.html` | audit **fatal 0 / warning 0** |
| LLM 재구성 Run 2 (7화면) | `outputs/restructured_run2.html` + `tools/flows/run2.json` | audit **fatal 0 / warning 0** |
| LLM 재구성 Run 3 (8화면) | `outputs/restructured_run3.html` + `tools/flows/run3.json` | audit **fatal 0 / warning 0** |
| 3회 비교 | `docs/restructure-runs.md` | 완료 (탭 수·확인 횟수는 손으로 셈) |
| 검사기 | `tools/audit.py` + `tools/flows/*.json` | 완료, 네 흐름 모두 동작 |
| 변경 기록 (28건, SDF 대조) | `docs/restructure-changelog.md` | 완료 |

마지막 커밋: `8c8c5ca 재구성 변경 기록과 이어서 작업하기 문서`
(그 뒤 Run 2·3 구현 — `outputs/restructured_run{2,3}.html`, `tools/flows/run{2,3}.json`,
`docs/restructure-runs.md`, `results/` 사본 — 은 2026-09-17 작업분, 커밋 여부는 git status 로 확인)

## 남은 일 (미뤄둔 순서대로)

1. ~~Run 2·Run 3 구현~~ **완료 (2026-09-17).** 결과는 `restructure-runs.md`. 이전
   대화의 설계 표는 없어서 CONTINUE 의 요약만으로 Run 1 코드 위에 구현했다 — 따라서
   Run 1 에 더 강하게 닻내림돼 있다. 후속: 검사기에 "돈 나가기 전 명시적 확인 횟수"와
   "화면당 결정 수" 지표를 넣어야 셋이 갈라진다. 지금은 손으로 센 값이다.
2. **재구성본 화면별 분리본.** `tools/split_screens.py` 가 원본 경로와 `SCREENS`
   목록을 상수로 갖고 있어 인자를 받도록 고쳐야 한다. 원본 8 ↔ 재구성 9 를
   비교창에 나란히 놓으려면 필요하다. Run 2·3 도 같은 도구로 나눠야 한다.
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
   경로가 바뀌면 `collect_results.py` 와 `results/` 사본도 따라 고쳐야 한다.

## 반드시 알아야 할 함정

- **`outputs/` 와 `logs/` 는 ignore 대상.** 손으로 쓴 `restructured_transfer.html`,
  `restructured_run2.html`, `restructured_run3.html` 이 거기 있다. 고치면 `python tools/collect_results.py` 를 돌려야 `results/` 사본이
  따라온다. 안 돌리면 커밋되는 사본이 낡은 채 남는다.
- **`PYTHONUTF8=1` 없이 DesignRepair 를 돌리면 죽는다.** 업스트림이 인코딩 없이
  파일을 열어 cp949 로 쓰다 `⌂` 에서 터진다. `tools/run_screens.py` 가 자동으로
  넣는다. 직접 `run_local.py` 를 부를 때는 환경변수를 직접 줘야 한다.
- **검사기는 흐름 파일이 필요하다.** `--flow tools/flows/original.json` (기본),
  `restructured.json`, `run2.json`, `run3.json`. `derived_from_original: false` 면 화면 대응이 필요한 검사는
  수행하지 않고 `checks_stood_down` 에 기록한다. **화면 이름이 같다고 같은 화면이
  아니다** — 원본과 재구성본 둘 다 `bank`, `amount` 가 있고 전혀 다른 화면이다.
- **검사는 두 단계다.** 와이어프레임은 A·B·C·F 만(`tools/audit_stage.py --stage
  wireframe`), 스타일 이식 후에는 A~H 전부. 대비·레이아웃·상태 색을 아직 채우지
  않은 산출물에 D·E·G·H 를 들이대면 없는 일을 트집 잡는 셈이다. `audit.py` 는
  그대로 두고 래퍼가 걸러내며, 무엇을 왜 건너뛰었는지는 `checks_stood_down` 에 남는다.
- **검사기 F 항목은 `<title>` 의 영어도 잡는다.** "Run 2" 라고 쓰면 warning 이 난다.
  제목은 한글로 ("2회차").
- **셸 기본 폴더가 옛 경로일 수 있다.** 이전 세션이 `designrepair` 에서 시작됐다.
  새 세션은 `senior-ui-pipeline` 에서 시작해야 맞다. 명령은 절대경로로 쓰는 편이
  안전하다.
- **서버는 프로젝트 루트를 3003 으로 서빙한다.** 모든 도구의 기본 URL 이 여기를
  가정한다. 안 떠 있으면:
  `.\.venv\Scripts\python.exe -m http.server 3003 --directory .`

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

## 30초 상태 확인

**`시작.bat` 을 더블클릭하면** 확인 화면이 열립니다 (빌드 목록·화면 비교·검사 결과·변경 추적).
터미널로 보려면:

```powershell
cd C:\Users\xihye\senior-ui-pipeline
.\.venv\Scripts\python.exe tools\build_index.py --print
```

옛 방식:

```powershell
cd C:\Users\xihye\senior-ui-pipeline
git log --oneline -3
.\.venv\Scripts\python.exe -m http.server 3003 --directory .   # 다른 터미널에서
$env:PYTHONUTF8=1
.\.venv\Scripts\python.exe tools\audit.py --flow tools\flows\restructured.json `
   --repaired http://localhost:3003/outputs/restructured_transfer.html `
   --repaired-file outputs\restructured_transfer.html
# 기대: passed true, fatal 0, warning 0, exit 0

# 네 빌드를 한 표로 (JSON 은 사람이 못 읽는다)
.\.venv\Scripts\python.exe tools\audit_report.py 규칙기반=results\audit.json `
   Run1=results\audit_restructured.json Run2=results\audit_run2.json Run3=results\audit_run3.json `
   --details --out results\audit-report.md
```
