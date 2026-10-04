# audit 비교

## 개요

|  | Run1 | Run2 | Run3 | Run4 |
|---|---|---|---|---|
| 통과 | ✗ | ✗ | ✗ | ✗ |
| fatal | 3 (독립 3 · 파생 0) | 3 (독립 3 · 파생 0) | 3 (독립 3 · 파생 0) | 2 (독립 2 · 파생 0) |
| warning | 0 | 0 | 0 | 8 |
| 화면 수 (도달 / 흐름) | 9 / 9 | 7 / 7 | 8 / 8 | 8 / 8 |
| data-screen 수 | 9 | 7 | 8 | 7 |
| 저대비 텍스트 (원본 → 빌드) | – → 3 | – → 3 | – → 3 | – → 0 |
| 완료 화면 금액 | 10,000 | 10,000 | 10,000 | 10,000 |
| 흐름 파일 | restructured | run2 | run3 | run4 |
| 원본에서 파생 | 아니오 (새 설계) | 아니오 (새 설계) | 아니오 (새 설계) | 아니오 (새 설계) |
| 생략된 검사 | 5 | 5 | 5 | 9 |

fatal 행의 '독립' 은 `fatal_root`, '파생' 은 `fatal_derived` (한 번 멈춘 탓에 줄줄이 따라온 '도달 못 함') 다. run 끼리 비교할 때는 독립 쪽을 본다.

## 검사 항목별 (A~I)

| 검사 | 내용 | 심각도 | Run1 | Run2 | Run3 | Run4 |
|---|---|---|---|---|---|---|
| A | 과업 완료 · 구조 보존 | fatal | 0 △ | 0 △ | 0 △ | 0 △ |
| B | 표시 정확성 · 주입된 대화상자 | fatal | 0 | 0 | 0 | 0 |
| C | 죽은 컨트롤 | fatal | 0 | 0 | 0 | 0 |
| D | 대비 | warning | 0 △ | 0 △ | 0 △ | 0 △ |
| E | 레이아웃 | warning | 0 △ | 0 △ | 0 △ | 0 △ |
| F | 언어 (새 영어) | warning | 0 | 0 | 0 | warning 8 |
| G | 상태 구분 | warning | 0 | 0 | 0 | 0 △ |
| H | 미정의 클래스 | warning | 0 | 0 | 0 | 0 △ |
| I | 선택지 보존 | fatal | fatal 3 | fatal 3 | fatal 3 | fatal 2 |

△ = 이 빌드에서 해당 검사의 일부가 생략됨 (아래 '생략된 검사' 참고)

## 핵심 지표

| 검사 | 지표 | Run1 | Run2 | Run3 | Run4 |
|---|---|---|---|---|---|
| A | data-action 수 (원본 → 빌드) | 23 → 31 | 23 → 27 | 23 → 31 | 23 → 13 |
| A | id 수 (원본 → 빌드) | 15 → 29 | 15 → 32 | 15 → 30 | 15 → 11 |
| A | 화면별로 사라진 속성 | 0 | 0 | 0 | 0 |
| B | 주입된 alert/confirm/prompt | 0 | 0 | 0 | 0 |
| B | 추가된 onclick | 0 | 0 | 0 | 0 |
| B | 과업 중 뜬 대화상자 | 0 | 0 | 0 | 0 |
| C | 처리기 없는 data-action (새로) | 0 | 0 | 0 | 0 |
| C | 원래부터 죽어 있던 것 | 0 | 0 | 0 | 0 |
| D | 색을 상속에만 의존하는 새 텍스트 | – | – | – | – |
| D | 상속받은 색이 읽히지 않는 텍스트 | 0 | 0 | 0 | 0 |
| D | 명암비 판정 불가 (그라디언트·이미지 위) | 0 | 0 | 0 | 0 |
| D | 저대비 요소에 글이 늘어남 | 0 | 0 | 0 | 0 |
| E | 새 겹침 | 0 | 0 | 0 | 0 |
| E | 새 넘침 | 0 | 0 | 0 | 0 |
| E | 새로 줄바꿈된 텍스트 | 0 | 0 | 0 | 0 |
| E | 원본보다 1.5배 이상 길어진 화면 | 0 | 0 | 0 | 0 |
| F | 새 영어 단어 (화면에 보임) | 0 | 0 | 0 | 1 (LTE) |
| F | 새 영어 단어 (마크업에만) | 0 | 0 | 0 | 0 |
| G | 무너진 상태 쌍 / 검사한 쌍 | 0 / 1 | 0 / 1 | 0 / 1 | 0 / 1 |
| H | 정의 안 된 클래스 | 0 | 0 | 0 | 6 (blank, cur, dots, okc, okwrap, q2) |
| I | 빌드에 없는 원본 선택지 | pick-bank 58개, quick 1개, num 1개 | pick-bank 58개, quick 1개, num 1개 | pick-bank 58개, quick 1개, num 1개 | pick-bank 64개, quick 4개 |

## 생략된 검사

**Run1**
- A/preservation (new design, nothing to preserve)
- A/per-screen attribute loss
- D/저명암 개수 전후 비교 (합계·화면별) - 새 설계라 짝이 되는 원본 화면이 없다. 화면 이름이 같다고 같은 화면이 아니므로, 견주면 두 설계가 다른 것을 결함으로 읽는다.
- D/gained-text (저대비 요소에 글이 늘었는지) - 새 설계라 짝이 되는 원본 화면이 없다. 화면 이름이 같다고 같은 화면이 아니므로, 견주면 두 설계가 다른 것을 결함으로 읽는다.
- E/newly-wrapped text and height growth (no shared screens)

**Run2**
- A/preservation (new design, nothing to preserve)
- A/per-screen attribute loss
- D/저명암 개수 전후 비교 (합계·화면별) - 새 설계라 짝이 되는 원본 화면이 없다. 화면 이름이 같다고 같은 화면이 아니므로, 견주면 두 설계가 다른 것을 결함으로 읽는다.
- D/gained-text (저대비 요소에 글이 늘었는지) - 새 설계라 짝이 되는 원본 화면이 없다. 화면 이름이 같다고 같은 화면이 아니므로, 견주면 두 설계가 다른 것을 결함으로 읽는다.
- E/newly-wrapped text and height growth (no shared screens)

**Run3**
- A/preservation (new design, nothing to preserve)
- A/per-screen attribute loss
- D/저명암 개수 전후 비교 (합계·화면별) - 새 설계라 짝이 되는 원본 화면이 없다. 화면 이름이 같다고 같은 화면이 아니므로, 견주면 두 설계가 다른 것을 결함으로 읽는다.
- D/gained-text (저대비 요소에 글이 늘었는지) - 새 설계라 짝이 되는 원본 화면이 없다. 화면 이름이 같다고 같은 화면이 아니므로, 견주면 두 설계가 다른 것을 결함으로 읽는다.
- E/newly-wrapped text and height growth (no shared screens)

**Run4**
- A/preservation (new design, nothing to preserve)
- A/per-screen attribute loss
- D/저명암 개수 전후 비교 (합계·화면별) - 새 설계라 짝이 되는 원본 화면이 없다. 화면 이름이 같다고 같은 화면이 아니므로, 견주면 두 설계가 다른 것을 결함으로 읽는다.
- D/gained-text (저대비 요소에 글이 늘었는지) - 새 설계라 짝이 되는 원본 화면이 없다. 화면 이름이 같다고 같은 화면이 아니므로, 견주면 두 설계가 다른 것을 결함으로 읽는다.
- E/newly-wrapped text and height growth (no shared screens)
- D/스테이지 밖 (와이어프레임) - 시각 디테일이 아직 없는 단계입니다. 대비·레이아웃·상태 색은 스타일 이식 후에 봅니다.
- E/스테이지 밖 (와이어프레임) - 시각 디테일이 아직 없는 단계입니다. 대비·레이아웃·상태 색은 스타일 이식 후에 봅니다.
- G/스테이지 밖 (와이어프레임) - 시각 디테일이 아직 없는 단계입니다. 대비·레이아웃·상태 색은 스타일 이식 후에 봅니다.
- H/스테이지 밖 (와이어프레임) - 시각 디테일이 아직 없는 단계입니다. 대비·레이아웃·상태 색은 스타일 이식 후에 봅니다.

## 발견 목록

### Run1
**I · 선택지 보존 — fatal 3건**
- 원본의 num 선택지 11개 중 1개가 생성물에 없다 (예: 00). 화면에 모두 보일 필요는 없지만 값 자체는 모두 접근 가능해야 한다. 검색이나 단계적 선택으로 찾을 수 있게 포함하라.
- 원본의 pick-bank 선택지 67개 중 58개가 생성물에 없다 (예: BNK투자증권, BNP파리바, BOA, DB증권, HSBC …). 화면에 모두 보일 필요는 없지만 값 자체는 모두 접근 가능해야 한다. 검색이나 단계적 선택으로 찾을 수 있게 포함하라.
- 원본의 quick 선택지 4개 중 1개가 생성물에 없다 (예: all). 화면에 모두 보일 필요는 없지만 값 자체는 모두 접근 가능해야 한다. 검색이나 단계적 선택으로 찾을 수 있게 포함하라.

### Run2
**I · 선택지 보존 — fatal 3건**
- 원본의 num 선택지 11개 중 1개가 생성물에 없다 (예: 00). 화면에 모두 보일 필요는 없지만 값 자체는 모두 접근 가능해야 한다. 검색이나 단계적 선택으로 찾을 수 있게 포함하라.
- 원본의 pick-bank 선택지 67개 중 58개가 생성물에 없다 (예: BNK투자증권, BNP파리바, BOA, DB증권, HSBC …). 화면에 모두 보일 필요는 없지만 값 자체는 모두 접근 가능해야 한다. 검색이나 단계적 선택으로 찾을 수 있게 포함하라.
- 원본의 quick 선택지 4개 중 1개가 생성물에 없다 (예: all). 화면에 모두 보일 필요는 없지만 값 자체는 모두 접근 가능해야 한다. 검색이나 단계적 선택으로 찾을 수 있게 포함하라.

### Run3
**I · 선택지 보존 — fatal 3건**
- 원본의 num 선택지 11개 중 1개가 생성물에 없다 (예: 00). 화면에 모두 보일 필요는 없지만 값 자체는 모두 접근 가능해야 한다. 검색이나 단계적 선택으로 찾을 수 있게 포함하라.
- 원본의 pick-bank 선택지 67개 중 58개가 생성물에 없다 (예: BNK투자증권, BNP파리바, BOA, DB증권, HSBC …). 화면에 모두 보일 필요는 없지만 값 자체는 모두 접근 가능해야 한다. 검색이나 단계적 선택으로 찾을 수 있게 포함하라.
- 원본의 quick 선택지 4개 중 1개가 생성물에 없다 (예: all). 화면에 모두 보일 필요는 없지만 값 자체는 모두 접근 가능해야 한다. 검색이나 단계적 선택으로 찾을 수 있게 포함하라.

### Run4
**F · 언어 (새 영어) — warning 8건**
- `start` English text not present in the original: LTE
- `account` English text not present in the original: LTE
- `bank` English text not present in the original: LTE
- `account#2` English text not present in the original: LTE
- `amount` English text not present in the original: LTE
- `confirm` English text not present in the original: LTE
- `password` English text not present in the original: LTE
- `done` English text not present in the original: LTE

**I · 선택지 보존 — fatal 2건**
- 원본의 pick-bank 선택지 67개 중 64개가 생성물에 없다 (예: BNK투자증권, BNP파리바, BOA, DB증권, HSBC …). 화면에 모두 보일 필요는 없지만 값 자체는 모두 접근 가능해야 한다. 검색이나 단계적 선택으로 찾을 수 있게 포함하라.
- 원본의 quick 선택지 4개 중 4개가 생성물에 없다 (예: 10000, 100000, 50000, all). 화면에 모두 보일 필요는 없지만 값 자체는 모두 접근 가능해야 한다. 검색이나 단계적 선택으로 찾을 수 있게 포함하라.

## 입력

- Run1: `http://localhost:3003/results/restructured_transfer.html`
- Run2: `http://localhost:3003/results/restructured_run2.html`
- Run3: `http://localhost:3003/results/restructured_run3.html`
- Run4: `http://localhost:3003/results/restructured_run4.html`
