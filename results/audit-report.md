# audit 비교

## 개요

|  | 규칙기반 | Run1 | Run2 | Run3 |
|---|---|---|---|---|
| 통과 | ✗ | ✓ | ✓ | ✓ |
| fatal | 7 | 0 | 0 | 0 |
| warning | 47 | 0 | 0 | 0 |
| 화면 수 (도달 / 흐름) | 8 / 8 | 9 / 9 | 7 / 7 | 8 / 8 |
| data-screen 수 | 8 | 9 | 7 | 8 |
| 저대비 텍스트 (원본 → 빌드) | 66 → 56 | 66 → 3 | 66 → 3 | 66 → 3 |
| 완료 화면 금액 | 10,000 | 10,000 | 10,000 | 10,000 |
| 흐름 파일 | original | restructured | run2 | run3 |
| 원본에서 파생 | 예 | 아니오 (새 설계) | 아니오 (새 설계) | 아니오 (새 설계) |
| 생략된 검사 | 없음 | 3 | 3 | 3 |

## 검사 항목별 (A~H)

| 검사 | 내용 | 심각도 | 규칙기반 | Run1 | Run2 | Run3 |
|---|---|---|---|---|---|---|
| A | 과업 완료 · 구조 보존 | fatal | fatal 1 | 0 △ | 0 △ | 0 △ |
| B | 표시 정확성 · 주입된 대화상자 | fatal | fatal 5 | 0 | 0 | 0 |
| C | 죽은 컨트롤 | fatal | fatal 1 | 0 | 0 | 0 |
| D | 대비 | warning | warning 18 | 0 | 0 | 0 |
| E | 레이아웃 | warning | warning 16 | 0 △ | 0 △ | 0 △ |
| F | 언어 (새 영어) | warning | warning 5 | 0 | 0 | 0 |
| G | 상태 구분 | warning | warning 1 | 0 | 0 | 0 |
| H | 미정의 클래스 | warning | warning 7 | 0 | 0 | 0 |

△ = 이 빌드에서 해당 검사의 일부가 생략됨 (아래 '생략된 검사' 참고)

## 핵심 지표

| 검사 | 지표 | 규칙기반 | Run1 | Run2 | Run3 |
|---|---|---|---|---|---|
| A | data-action 수 (원본 → 빌드) | 23 → 24 | 23 → 31 | 23 → 27 | 23 → 31 |
| A | id 수 (원본 → 빌드) | 15 → 15 | 15 → 29 | 15 → 32 | 15 → 30 |
| A | 화면별로 사라진 속성 | 1 (account) | 0 | 0 | 0 |
| B | 주입된 alert/confirm/prompt | 1 | 0 | 0 | 0 |
| B | 추가된 onclick | 1 | 0 | 0 | 0 |
| B | 과업 중 뜬 대화상자 | 1 | 0 | 0 | 0 |
| C | 처리기 없는 data-action (새로) | 1 | 0 | 0 | 0 |
| C | 원래부터 죽어 있던 것 | 0 | 0 | 0 | 0 |
| D | 색을 상속에만 의존하는 새 텍스트 | 18 | 0 | 0 | 0 |
| D | 저대비 요소에 글이 늘어남 | 0 | 0 | 0 | 0 |
| E | 새 겹침 | 6 | 0 | 0 | 0 |
| E | 새 넘침 | 2 | 0 | 0 | 0 |
| E | 새로 줄바꿈된 텍스트 | 8 | 0 | 0 | 0 |
| E | 원본보다 1.5배 이상 길어진 화면 | 0 | 0 | 0 | 0 |
| F | 새 영어 단어 (화면에 보임) | 11 (Account, Amount, Back, Bank, Close, Open …) | 0 | 0 | 0 |
| F | 새 영어 단어 (마크업에만) | 1 (Shuffle) | 0 | 0 | 0 |
| G | 무너진 상태 쌍 / 검사한 쌍 | 1 / 3 | 0 / 1 | 0 / 1 | 0 / 1 |
| H | 정의 안 된 클래스 | 4 (progress-bar, sr-only, svc-group, text) | 0 | 0 | 0 |

## 생략된 검사

**Run1**
- A/preservation (new design, nothing to preserve)
- A/per-screen attribute loss
- E/newly-wrapped text and height growth (no shared screens)

**Run2**
- A/preservation (new design, nothing to preserve)
- A/per-screen attribute loss
- E/newly-wrapped text and height growth (no shared screens)

**Run3**
- A/preservation (new design, nothing to preserve)
- A/per-screen attribute loss
- E/newly-wrapped text and height growth (no shared screens)

## 발견 목록

### 규칙기반
**A · 과업 완료 · 구조 보존 — fatal 1건**
- `account` data-action removed from this screen: back-recipient

**B · 표시 정확성 · 주입된 대화상자 — fatal 5건**
- alert() injected that the original never had: '1원이 전송됩니다.'
- injected alert() hardcodes 1 - the value is dynamic, so it will be wrong for any other amount
- onclick attribute added that the original did not have: button\|alert('1원이 전송됩니다.');
- `confirm` blocking alert during the task: '1원이 전송됩니다.'
- `confirm` dialog states 1 while the task used 10,000

**C · 죽은 컨트롤 — fatal 1건**
- data-action='back' has no branch in the handler - the control looks tappable and does nothing

**D · 대비 — warning 18건**
- `recipient` new text 'Back' takes its colour purely by inheritance (rgb(26, 26, 26)) - nothing sets a colour for it
- `recipient` new text 'Profile' takes its colour purely by inheritance (rgb(26, 26, 26)) - nothing sets a colour for it
- `recipient` new text 'Close' takes its colour purely by inheritance (rgb(26, 26, 26)) - nothing sets a colour for it
- `recipient` new text '즐겨찾기 추가됨' takes its colour purely by inheritance (rgb(26, 26, 26)) - nothing sets a colour for it
- `recipient` new text '즐겨찾기 추가됨' takes its colour purely by inheritance (rgb(26, 26, 26)) - nothing sets a colour for it
- `recipient` new text '즐겨찾기 추가됨' takes its colour purely by inheritance (rgb(26, 26, 26)) - nothing sets a colour for it
- `recipient` new text '즐겨찾기 추가됨' takes its colour purely by inheritance (rgb(26, 26, 26)) - nothing sets a colour for it
- `recipient` new text '즐겨찾기 추가됨' takes its colour purely by inheritance (rgb(26, 26, 26)) - nothing sets a colour for it
- `recipient` new text '즐겨찾기 추가됨' takes its colour purely by inheritance (rgb(26, 26, 26)) - nothing sets a colour for it
- `account` new text 'Step 1 of 3' takes its colour purely by inheritance (rgb(26, 26, 26)) - nothing sets a colour for it
- … 외 8건

**E · 레이아웃 — warning 16건**
- `home` '가입 즉시 1만원 올영 상품권' and '⌂' overlap by 52%
- `home` '가입 즉시 1만원 올영 상품권' and '홈' overlap by 44%
- `home` '가입 즉시 1만원 올영 상품권' and 'Ⓦ' overlap by 52%
- `home` '가입 즉시 1만원 올영 상품권' and '금융' overlap by 50%
- `home` '가입 즉시 1만원 올영 상품권' and '🎁' overlap by 52%
- `home` '가입 즉시 1만원 올영 상품권' and '혜택' overlap by 47%
- `amount` content spills 13px out of a 32px box (.ico): '‹Back to Account'
- `confirm` content spills 13px out of a 32px box (.ico): '‹Back to Amount'
- `recipient` 'Profile' now wraps onto 2 lines (.text) - it did not before
- `recipient` 'Close' now wraps onto 2 lines (.text) - it did not before
- … 외 6건

**F · 언어 (새 영어) — warning 5건**
- `recipient` English text not present in the original: Back, Close, Profile, of
- `account` English text not present in the original: Bank, Open, Selection, Step, of
- `amount` English text not present in the original: Account, Back, Close, to
- `confirm` English text not present in the original: Amount, Back, Close, to
- English added to the markup but overwritten before it renders: Shuffle

**G · 상태 구분 — warning 1건**
- .btn-next and .btn-next.on now render identically (background-image, background-position-x, background-position-y, background-size, background-repeat, background-attachment, background-origin, background-clip, background-color, color) - the state is no longer visible

**H · 미정의 클래스 — warning 7건**
- `home` class 'svc-group' is used 2x but no stylesheet defines it - it has no effect (e.g. '🅦급여클럽+급여이체 우대 혜택\n        ⚾SOL')
- `recipient` class 'text' is used 3x but no stylesheet defines it - it has no effect (e.g. 'Back')
- `recipient` class 'sr-only' is used 6x but no stylesheet defines it - it has no effect (e.g. '즐겨찾기 추가됨')
- `account` class 'progress-bar' is used 1x but no stylesheet defines it - it has no effect (e.g. 'Step 1 of 3')
- `account` class 'sr-only' is used 1x but no stylesheet defines it - it has no effect (e.g. 'Open Bank Selection')
- `amount` class 'sr-only' is used 2x but no stylesheet defines it - it has no effect (e.g. 'Back to Account')
- `confirm` class 'sr-only' is used 2x but no stylesheet defines it - it has no effect (e.g. 'Back to Amount')

### Run1
발견 없음.

### Run2
발견 없음.

### Run3
발견 없음.

## 입력

- 규칙기반: `http://localhost:3003/outputs/repaired_transfer.html`
- Run1: `http://localhost:3003/outputs/restructured_transfer.html`
- Run2: `http://localhost:3003/outputs/restructured_run2.html`
- Run3: `http://localhost:3003/outputs/restructured_run3.html`
