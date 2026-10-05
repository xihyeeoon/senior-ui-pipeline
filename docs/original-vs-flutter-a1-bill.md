# 공과금 원본 HTML 대 Flutter A1 공과금

본실험은 Flutter 더미앱(`senior-ui-dummy-app`, 커밋 `00834ca`)으로 한다. 재설계의 입력인
`inputs/original_bill.html` 은 참가자가 보는 A1 공과금 화면과 같아야 한다. 이 문서는
둘을 화면마다 비교한 것이다 (2026-10-05, 원본을 만든 직후).

비교 대상은 화면 흐름 · 문구 · 누를 수 있는 요소 · 입력 방식 · 데이터 · 오류 동작이다.
색 · 크기 · 아이콘 모양 · 간격은 비교하지 않는다. 캡처는 대조용으로만 봤다 — 더미앱이
캡처와 다르면 **더미앱을 따랐다** (참가자가 보는 것이 더미앱이다).

읽은 Flutter 파일: `lib/screens/a1_home.dart`, `sh_menu.dart`, `sh_menu_search.dart`,
`a1_bill_home.dart`, `a1_bill_pay_camera.dart`, `a1_bill_pay_info.dart`,
`a1_bill_pay_password.dart`, `a1_bill_pay_done.dart`; `lib/data/sh_dummy.dart`,
`sh_menu_data.dart`; `lib/widgets/sh_security_keypad.dart`, `sh_common.dart`;
`lib/experiment/screen_names.dart`.

판정: **같음** · **다름·유지** (이유를 적음). 고칠 것으로 남긴 차이는 없다.
"테스트" 열은 `tests/test_original_bill.py` 에서 그 동작을 확인하는 함수다.

## 1. 화면 목록과 순서

| 순서 | HTML `data-screen` | Flutter 라우트 이름 | 판정 |
|---|---|---|---|
| 1 | `home` | `home` (A1Home) | 같음 |
| 2 | `menu` | `menu` (ShMenu) | 같음 (범위 B — 5절) |
| 3 | `search` | `menu_search` (ShMenuSearch) | 같음 |
| 4 | `bill-home` | `bill_home` (A1BillHome) | 같음 |
| 5 | `camera` | `bill_camera` | 같음 |
| 6 | `info` | `bill_info` | 같음 |
| 7 | `password` | `bill_password` | 같음 |
| 8 | `done` | `bill_done` | 같음 |
| — | 없음 | (오류 팝업 없음) | 같음 — 둘 다 공과금 경로에 오류가 없다 |

`a1_bill_main.dart` · `a1_bill_input.dart` 는 더미앱 안에서 어디서도 열리지 않아 넣지
않았다.

## 2. 화면별

### home

| 항목 | HTML | Flutter | 판정 |
|---|---|---|---|
| 문구 · 카드 | 이체 원본의 홈과 같다 | A1Home | 같음 (이체 원본에서 이미 맞췄다, `original-vs-flutter-a1.md`) |
| 전체메뉴 진입 | 네 번째 아이콘 ⌕ → menu | 줄+돋보기 아이콘 → ShMenu | 같음 |
| [이체] | 무동작 | 이체 과제로 | **다름·유지** — 한 과제 원본에 다른 과제 경로를 넣지 않는다 (이체 원본에서 전체메뉴를 무동작으로 둔 것과 같은 판단) |
| 그 밖의 아이콘 · 카드 · 탭바 | 무동작 | 범위 밖 | 같음 |

### menu

| 항목 | HTML | Flutter | 판정 | 테스트 |
|---|---|---|---|---|
| 위 막대 | ‹ → home, 채팅 · 설정 · 로그아웃 무동작 | 같음 | 같음 | `test_back_and_close_destinations`, `test_out_of_scope_does_nothing` |
| 검색창 | "상품, 메뉴, 혜택 등을 검색해보세요" → search | 같음 | 같음 | `test_flow_walks_every_step_to_done` |
| 탭 바 7개 | 누르면 그 카테고리로 스크롤, 스크롤하면 지금 탭에 불 | 같음 (스크롤 스파이) | 같음 | `test_menu_tab_scrolls_to_its_category` |
| 칩 | 소분류가 둘 이상인 탭만, 누르면 그 소분류로 | 같음 | 같음 | `test_direct_menu_route` |
| 항목 | 납부하기 → bill-home, 나머지 무동작 | 같음 (나머지는 `showOutOfScope`) | 같음 | `test_direct_menu_route`, `test_out_of_scope_does_nothing` |
| 항목 범위 | 은행 69 + 카드 › 대표 생활요금 4. 다른 탭은 제목만 | 7탭 293 | **다름·유지** — 범위 B (5절) |
| 처음 상태 | 홈에서 열 때마다 맨 위 · [은행] | 새로 push | 같음 |

### search

| 항목 | HTML | Flutter | 판정 | 테스트 |
|---|---|---|---|---|
| 빈칸 / 1글자 / 2글자 이상 | "찾으시는 메뉴를 입력해보세요" / "검색버튼(돋보기)을 눌러주세요" / 결과 + AI 푸터 | 같음 | 같음 | `test_search_states` |
| ⓧ | 글자가 있을 때만, 누르면 비운다 | 같음 | 같음 | `test_search_states` |
| 돋보기 · AI 푸터 | 무동작 | 범위 밖 | 같음 | |
| 결과 | 별칭 "공과금납부"(은행) 먼저, 그다음 메뉴 순서. 앞부분 일치는 파랑 | 같음 | 같음 | `test_search_states` |
| 맞추는 방법 | 완성된 글자끼리 포함 여부 | 자모로 나눠 포함 여부 (`jamoKey`) | **다름·유지** — 차이는 조합 중인 글자("공ㄱ")에서만 난다. 2글자 이상 완성된 검색어("공과", "전기", "납부")의 결과는 같다. 재설계 입력에 자모 분해기를 넣으면 원본이 커진다 |
| "공과" | 공과금납부 | 같음 | 같음 | 흐름 `steps` |
| "전기" | 카드 › 전기 요금 하나 (누르면 무동작) | 같음 | 같음 | `test_search_states` |
| "납부" | 공과금납부 · 납부하기 · 자동납부 · 납부내역 조회 | 위 넷 + 카드 › 분할납부 | **다름·유지** — 범위 B. A 판이면 같아진다 |
| 결과 → bill-home | 공과금납부 · 납부하기 | 같음 | 같음 | |
| ‹ | menu (스크롤 그대로) | `maybePop` | 같음 | `test_back_and_close_destinations` |
| 다시 들어올 때 | 메뉴에서 오면 빈칸, bill-home 에서 ‹ 로 오면 검색어 그대로 | 같음 | 같음 | `test_search_states`, `test_back_and_close_destinations` |
| 기록 | `text_input` (`field: menu_search`) | 같음 | 같음 | |

### bill-home

| 항목 | HTML | Flutter | 판정 | 테스트 |
|---|---|---|---|---|
| 문구 | 히어로 · [납부하기]/[조회하기] 카드 · 지로번호 등록 · 섹션 5 · 항목 18 · 부제 3 | 같음 | 같음 | `test_out_of_scope_does_nothing` (18개) |
| [납부하기] | → camera | 같음 | 같음 | |
| 항목 18 · [조회하기] · 지로번호 등록 · 고객센터 · 홈 | 무동작 | 범위 밖 | 같음 | `test_out_of_scope_does_nothing` |
| ‹ | 들어온 화면 (menu 또는 search) | `maybePop` | 같음 | `test_direct_menu_route`, `test_back_and_close_destinations` |
| 항목 아이콘 | 빈 사각형 | 캡처의 아이콘 에셋 | **다름·유지** — 시각 |

### camera

| 항목 | HTML | Flutter | 판정 |
|---|---|---|---|
| 문구 | "지로번호가 잘 보이게 준비해주세요" · "고지서를 사각형에 맞춰 촬영해주세요" | 같음 | 같음 |
| 셔터 | → info | `pushReplacement` → 납부정보 | 같음 |
| ✕ | → bill-home | `maybePop` | 같음 (`test_back_and_close_destinations`) |

캡처와는 다르다 (더미앱을 따랐다): 캡처 `납부하기/0.png` 는 첫 문구를 가로로 누운
안내 카드 안에 보이고 그 카드에 ✕ 가 하나 더 있다. `1.png` 는 실제 카메라 화면 위에
"고지서를 사각형에 맞춰 촬영해주세요" 를 띄운다. 더미앱은 두 상태를 한 화면으로 합쳤다.

### info

| 항목 | HTML | Flutter | 판정 | 테스트 |
|---|---|---|---|---|
| 제목 | 전기요금 납부 | 같음 | 같음 | |
| 납부정보 여섯 줄 | 1700000000 · 홍길동 · 202607 · 31500000000000 · ○○동 ●●●-● · 2,160원 | `ShDummy` 같음 | 같음 | 흐름 `expect.info` |
| 출금계좌 | [금융거래한도계좌2]신한 주거래 우대통장(저축예금) · 신한 110-000-000000 · 출금가능금액 1,000,000 | 같음 | 같음 | 흐름 `expect.info` |
| 출금계좌 ⌄ | 누를 수 없다 | 아이콘만 (탭 처리 없음) | 같음 | |
| [납부] | → password | 같음 | 같음 | |
| ‹ | → bill-home | `maybePop` (촬영은 바꿔치기로 사라졌다) | 같음 | `test_back_and_close_destinations` |
| 고객센터 · 홈 | 무동작 | 범위 밖 | 같음 | |

### password

| 항목 | HTML | Flutter | 판정 | 테스트 |
|---|---|---|---|---|
| 문구 | 계좌 비밀번호, 점 4개 | 같음 | 같음 | |
| 키패드 | 파란 보안 키패드, 숫자 10 섞임 + [재배열] + ⌫ (이체 원본과 같은 방식) | `ShSecurityKeypad.shinhan` | 같음 | `test_password_keypad` |
| 섞는 때 | 화면을 열 때 · [재배열] | `initState` · 재배열 | 같음 | `test_password_keypad` |
| 점 | 빈 · 채움 두 상태 | 같음 | 같음 | |
| 판정 | 없음, 4자리면 0.18초 뒤 done | 같음 ("실제 검증은 없다") | 같음 | `test_no_error_popup_on_the_path` |
| ✕ | → info | `maybePop` | 같음 | `test_back_and_close_destinations` |

### done

| 항목 | HTML | Flutter | 판정 | 테스트 |
|---|---|---|---|---|
| 문구 | 납부완료 · 출금계좌 · 납부금액 2,160원 · 납부일 2026.08.07 10:11 · 납부정보 다섯 줄 · 안내 한 줄 | 같음 | 같음 | 흐름 `expect.done` |
| [확인] · 홈 아이콘 | → home | `popToConditionHome` | 같음 | `test_done_confirm_returns_home`, `test_done_home_icon_returns_home` |
| 고객센터 | 무동작 | 범위 밖 | 같음 | |

## 3. 데이터

`sh_dummy.dart` 의 공과금 값(고객명 · 전자납부번호 · 청구연월 · 지정 계좌 · 주소 ·
금액 · 출금가능금액 · 납부일)과 출금계좌(이름 · 번호)를 그대로 썼다. 캡처의 실명 ·
실번호 · 실잔액(628,117)은 쓰지 않았다. 메뉴 데이터는 `sh_menu_data.dart` 그대로다
(B 판은 그 일부, 전체는 `docs/bill-menu-full.json`).

## 4. 오류 동작

둘 다 없다. 더미앱의 오류 팝업 둘(ELB00016 · ETA00325)은 이체 전용이다
(`ShDummy.checkTransfer`). 흐름 파일의 `error_paths` 는 빈 목록이다.

## 5. 더미앱과 다른 점 (모아서)

| # | 다른 점 | 이유 |
|---|---|---|
| 1 | 메뉴는 은행 탭 + 카드 › 대표 생활요금만. 다른 탭은 이름만 | 범위 B (토큰 한도). A 판으로 바꿀 자리가 있다 (`original-bill-scope.md` 6절). Flutter C 에서는 그 탭들을 A1 그대로 둔다 |
| 2 | 그 결과 "납부" 검색에서 카드 › 분할납부가 빠진다 | 1 과 같다 |
| 3 | 검색은 완성된 글자끼리 맞춘다 (더미앱은 자모) | 조합 중인 글자에서만 차이. 원본 크기 |
| 4 | 홈 [이체] 무동작 | 과제 하나의 원본 |
| 5 | 아이콘 · 일러스트는 글자 기호와 빈 사각형 | 시각은 같을 필요가 없다 |
