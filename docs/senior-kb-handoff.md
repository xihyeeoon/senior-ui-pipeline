# DesignRepair × senior_kb.csv — 실행 결과 인수인계

작성 2026-09-07. 다른 세션/다른 Claude가 이 문서만 읽고 이어받을 수 있도록 정리한 것입니다.

## 무엇을 했나

DesignRepair 파이프라인을 **같은 입력**으로 두 번 돌리고 결과를 비교했습니다.
변수는 system-level 지식베이스 하나뿐입니다.

| 런 | KB | 출력 | 로그 |
|---|---|---|---|
| base | `vendor/designrepair/library/system_design_knowledge_base.csv` (업스트림, Material Design) | `outputs/example1_base/` | `logs/runA_base.log` |
| senior | `kb/senior_kb.csv` (교체본, 고령자 사용성 46행) | `outputs/example1_seniorkb/` | `logs/runC_seniorkb.log` |

공통 입력: `vendor/designrepair/examples/example1.tsx`, 렌더 페이지 `http://localhost:3000`
(정적 서버가 `page/` 를 서빙), 모델 `gpt-4o`.

재현 명령:

```powershell
$env:DESIGNREPAIR_MODEL     = "gpt-4o"
$env:DESIGNREPAIR_SYSTEM_KB = "C:\Users\xihye\senior-ui-pipeline\kb\senior_kb.csv"
C:\Users\xihye\senior-ui-pipeline\.venv\Scripts\python.exe C:\Users\xihye\senior-ui-pipeline\run_local.py
```

`run_local.py` 는 업스트림 `backend/test.py` 위에 KB 파일명, pydantic v2, 모델 리맵,
429 백오프, 출력 경로 5가지를 고친 러너입니다. 출력 폴더는 항상 `outputs/example1` 로
생기므로 런마다 이름을 바꿔 보관했습니다.

## senior_kb.csv 로드 결과

총 **46행**, 버려진 행 없음 (헤더 1행만 스킵).

| property | 행 수 | constraint |
|---|---|---|
| Group | 17 | 전부 hard |
| Text | 11 | 전부 hard |
| Clickable | 8 | 전부 hard |
| Label | 4 | 전부 hard |
| Color | 3 | 전부 hard |
| Spacing | 2 | 전부 hard |
| Icon | 1 | 전부 hard |

- **soft 규칙이 0개**입니다. 로더는 `{"soft": [], "hard": []}` 구조로 반환하므로
  soft를 참조하는 다운스트림 코드는 항상 빈 리스트를 받습니다.
- relation 컬럼이 규칙 ID입니다: `SDF-*` 41행 + `KS-*` 5행 (43~47행).
  업스트림 KB는 이 자리가 `Foundations > Layout > Group > hard > ...` 경로 문자열이라
  추적 가능한 ID가 없었습니다. **이게 KB 교체의 핵심 이득입니다.**

## 실행 결과 (senior 런)

**1. 완주 여부** — exit 0, `done ->` 도달, Traceback 없음.
`RateLimitError` 1회 발생 후 백오프 재시도로 성공. 산출물 3개 모두 기록됨.

**2. 실제 실행된 property — 5개**

| property | Playwright 추출 | KB 규칙 | 실행 |
|---|---|---|---|
| Group | (추출 안 함) | 17 | ✅ 코드 직접 분석 경로 |
| Icon | (추출 안 함) | 1 | ✅ 코드 직접 분석 경로 |
| Text | 14 | 11 | ✅ |
| Color | 53 | 3 | ✅ |
| Spacing | 8 | 2 | ✅ |
| Label | **0** | 4 | ⛔ 스킵 |
| Clickable | **0** | 8 | ⛔ 스킵 |

Group/Icon은 `vendor/designrepair/backend/core/analysis_groups.py:789` 의 `elif` 분기라 추출이 0이어도 항상 실행됩니다.
Label·Clickable 스킵은 base 런과 동일 조건이며 KB와 무관합니다 — example1 페이지에
버튼/링크/폼 라벨이 하나도 없어서 추출기가 0을 반환합니다.
**결과적으로 KB 46행 중 12행(26%)은 이 예제에서 평가조차 되지 않습니다.**
Clickable·Label 규칙을 검증하려면 인터랙티브 요소가 있는 다른 예제가 필요합니다.

**3. 제안 건수와 인용률**

| property | 제안 | SDF 인용 | distinct 규칙 |
|---|---|---|---|
| Group | 3 | 3 | SDF-G2-3, SDF-G3-4, SDF-G5-3 |
| Spacing | 2 | 2 | SDF-G2-4, SDF-G7-2 |
| Text | 4 | 4 | SDF-G1-1 (4건 전부 동일) |
| Color | 3 | 3 | SDF-G1-3 (3건 전부 동일) |
| Icon | 5 | **0** | — |
| 합계 | **17** | **12 (71%)** | 7개 |

base 런은 제안 12건 / 규칙 ID 인용 0건.

수치 출처: `repair_to_full_code()` 가 `vendor/designrepair/backend/core/analysis_utils.py:113` 에서 프롬프트 전체를
print하므로, stream B 프롬프트 안에 제안 JSON이 그대로 남습니다. 로그를 cp949로 읽어
`ast.literal_eval` 로 파싱했습니다. 파이프라인은 제안 JSON을 디스크에 쓰지 않습니다
(`tools/probe_citation.py` 가 단일 property를 재호출해 덤프하는 용도로 있지만,
그건 별도 API 호출이라 런과 다른 샘플이 나옵니다).

**4. base 대비 코드 변화** (`property_example1.tsx`)

| 항목 | Original | Base KB | Senior KB |
|---|---|---|---|
| 본문 텍스트 | 기본 | 변화 없음 | `text-lg` ×6 |
| 카드 제목 | `text-xl` | `text-xl` | `text-2xl` |
| h1 | `3xl/sm:5xl/xl:6xl` | 동일 | `4xl/sm:6xl/xl:7xl` |
| 배경 | `bg-black` | `bg-primary` (미정의) | `bg-gray-900` |
| 본문 색 | `text-zinc-200` | `text-primary` (미정의) | `text-white`/`gray-100` |
| 그리드 | `grid-cols-3` | `1/md:2/lg:3` | `grid-cols-2` |
| 카드 간격 | `gap-8` | `gap-4` | `gap-12` |
| 아이콘 불투명도 | `opacity-50` ×6 | 유지 | 제거 |
| 아이콘 레이블 | 없음 | 없음 | `span` 텍스트 추가 |

base는 Material 토큰 이름(`bg-primary`, `text-primary`)으로 치환하는 데 그쳤는데
**이 클래스들은 Tailwind에 존재하지 않아 실제로 스타일이 사라집니다** — 대비가 원본보다
나빠졌습니다. senior는 글자 확대 · 대비 강화 · 밀도 완화 · 아이콘 레이블로
고령자 지침이 의도한 변경을 실제로 냈습니다.

## 미해결 문제 3가지

1. **Icon 제안 5건이 규칙 ID를 누락.** KB 27행 relation은 `SDF-G6-4` 로 정상인데
   모델이 content 본문만 인용했습니다. 규칙 내용 반영은 정확하고 인용 포맷만 깨졌습니다.
2. **아이콘 레이블이 h2와 중복.** SDF-G6-4를 문자 그대로 적용해
   `<span>Smart Inbox</span>` 가 `<h2>Smart Inbox</h2>` 위에 생겼습니다.
   규칙 문구에 "이미 텍스트 제목이 있으면 중복하지 않는다" 조건을 추가하면 해소될 것으로 보입니다.
3. **그 span에 색 클래스가 없어 검정으로 렌더링됩니다.** `bg-gray-900` 위에 얹혀 거의 안 보이며,
   명도 대비를 요구하는 SDF-G1-3과 정면으로 충돌합니다. 2번과 함께 고쳐야 합니다.

추가 관찰: Text 11개 규칙 중 실제 인용된 건 SDF-G1-1 하나뿐이고, KS-* 5개 규칙은
한 건도 인용되지 않았습니다. 프롬프트에 실린 규칙 대비 실사용률이 낮습니다.

## 시각 비교

- **`outputs/compare/kb-compare.html`** — 파일 하나로 열리는 자립형 비교 페이지.
  서버·CDN·네트워크 전부 불필요 (Tailwind CSS와 렌더 DOM이 인라인).
  Original / Base / Senior 3단 비교, 렌더 폭 1280·768·390 전환, 패널 토글.
- 재생성: `tools/compare/make_standalone.py` 상단 주석에 순서가 적혀 있습니다
  (`build.js` → tailwind CLI → `_snapshot.py` → `make_standalone.py`).
- 개발용 서버 버전은 `tools/viewers/kb_compare.html` (프로젝트 루트를 3003으로 서빙).
- 캡처: `outputs/kb-compare.png`, `outputs/kb-compare-standalone.png`

## 주의

- `outputs/example1_senior/` 는 **11:14의 옛 결과**입니다. 지금은 없어진
  `kb/system_design_knowledge_base_senior.csv` 로 돌린 것이라 현재 KB와 무관합니다.
  이번 런은 `outputs/example1_seniorkb/` 입니다.
- Windows 콘솔 로그는 cp949로 기록됩니다. utf-8로 읽으면 한글이 깨집니다.

## 폴더 구조 (2026-09-09 정리)

`senior-ui-pipeline/` 로 재배치했습니다: `vendor/designrepair/`(업스트림 클론, 자체 git 유지), `kb/`, `inputs/`, `tools/`, `outputs/`, `logs/`, `results/`, `docs/`.
`outputs/` 와 `logs/` 는 .gitignore 되고, 추적할 근거는 `tools/collect_results.py` 가 `results/` 로 복사합니다. 배치 상세는 `docs/README.md` 참조.
