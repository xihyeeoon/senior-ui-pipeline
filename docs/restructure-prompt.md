# 재구성 프롬프트 템플릿

재구성 루프(`senior_ui/restructure/prompt.py`)가 이 파일을 읽어 LLM 에
보낸다. 실행은 `python -m senior_ui.restructure` 다. `<!-- PROMPT -->` 와
`<!-- /PROMPT -->` 사이만 프롬프트이고, 그 밖은 사람용 메모다.

**출처 메모.** Run 1 (`outputs/restructured_transfer.html`) 은 대화에서 직접 지시해 만들었고
그 문장은 저장소에 남아 있지 않다. 아래 본문은 `restructure-runs.md` 에 인용된 브리프
("고령자가 이체 과업을 끝낼 수 있게 화면을 다시 설계하라"), `restructure-changelog.md` 의
"규칙을 주지 않고 과업 수행의 어려움만 보고 설계" 원칙, 그리고 Run 1 이 실제로 지킨 기술
계약(검사기 `senior_ui/audit/` 가 요구하는 것)으로 복원한 것이다. 원래 쓰던 문장이 있으면 본문
1·2 절을 그것으로 바꾸면 된다. 3·4 절이 자동화를 위해 새로 붙인 두 가지다.

**과제 설명은 이 파일에 없다.** 아래 두 프롬프트의 `{{TASK}}` 에는 과제 파일
(`tasks/<과제>.json` 의 `description`)이 들어간다 — 과제를 바꿀 때 그 한 곳만 고친다.
과제는 `python -m senior_ui.restructure --task bill` 로 고르고, 기본은 `transfer` 다.
과제마다 다른 문단 — 완료 화면의 id 와 값, 과업 한 줄, 입력·확인 화면 규칙, 흐름 명세
예시, 치환 문자열, 오류 경로 규칙 — 도 이 파일에는 `{{TASK_<칸>}}` 슬롯만 있고 글은 과제
파일의 `prompt.<칸>` 에 있다 (`notes` · `rules` · `flow_example` · `flow_values` ·
`flow_errors` · `flow_done` · `plan_errors` · `plan_error_rule` · `plan_errors_form` ·
`errors_note`). 칸이 빠진 과제는 프롬프트를 만들지 않고 멈춘다. 오류 경로가 없는 과제
(공과금)는 오류 칸 다섯을 빈 목록으로 두어 오류 문장이 하나도 들어가지 않는다 — 원본에 없는
오류를 지어내라는 말로 읽히지 않게. 그래서 오류 칸의 슬롯은 앞뒤 줄바꿈을 칸의 글이 품는다
(빈 칸이 빈 줄을 남기지 않는다).
`<!-- PLAN_PROMPT -->` 는 첫 호출(진단·계획, JSON 하나)이고, `<!-- PROMPT -->` 는 둘째
호출(생성)과 재시도에 쓴다. 두 단계로 나눈 이유와 루프는 `senior_ui/restructure/loop.py`
머리말에 있다.

생성 프롬프트의 치환 자리 다섯: `{{ORIGINAL_HTML}}` (원본 파일 전체), `{{RETRY_BLOCK}}`
(재시도일 때만 채워짐, 첫 시도는 빈 문자열), `{{CHOICES}}` (원본이 가진 선택지 요약 —
검사 I 가 세는 바로 그 집합이다), `{{ERRORS}}` (원본의 오류 조건 — 검사 J 가 걷는
바로 그 오류들이다), `{{PLAN}}` (첫 호출이 세운 계획, 재시도에서 고쳐진 것).
진단·계획 프롬프트는 `{{PLAN}}` 대신 `{{ORIGINAL_SCREENS}}` (원본의 화면 이름)를 쓴다.

**원본 화면 그림.** 진단·계획 프롬프트의 `{{ORIGINAL_SHOTS}}` 에는 루프가 시작할 때
원본을 한 번 걸으며 찍은 그림이 들어간다 (화면마다, 스크롤되는 화면은 맨 위부터 창
높이씩 잘라 최대 4장, 그리고 오류 상태). 글 안에는 "## 원본 화면" 머리와 그림 자리
표시 하나만 들어가고, 보낼 때 그 자리에서 글을 갈라 그림마다 화면 이름표와 그림을
끼운다 (`model.content_parts`). 기록(`attempt_N.plan_prompt.txt`)에는 그림 대신 파일
경로 줄이 남는다. `--see off` 이면 이 자리는 빈 글자다 - 전의 프롬프트와 같다.
생성 · 재시도 프롬프트에는 그림을 넣지 않는다.

**오류 조건.** `{{ERRORS}}` 는 원본 흐름(`flows/original.json`)의 `error_paths` 에서
도구가 만든다 (`prompt.errors_block`). 넣는 것은 오류 id · 무엇이 틀렸는가 · 원본이
어떻게 하는가 · 잘못된 값의 **자리표시자 이름** 뿐이다. 잘못된 값의 실제 값
(`truth` 의 `ACCOUNT_WRONG` 등)은 넣지 않는다 — 모델이 그 값을 알면 "그 값일 때만
오류를 띄우는" HTML 로 검사 J 를 지날 수 있다 (`tests/test_error_paths.py` 가 확인한다).

**예시는 빈칸 틀로만 쓴다.** 프롬프트 안의 JSON 예시에 구체적인 디자인 아이디어를
적으면 모델이 그것을 베낀다 — "규칙 목록을 주지 않는다" 원칙과도 어긋난다
(`tests/test_agent_stages.py` 가 이것을 확인한다).

**선택지 데이터.** 스크립트 배열로 그려지는 선택지는 도구가 꺼내서
(`senior_ui/restructure/preserve.py`) 재설계 HTML 에 `<script id="preserved-data">
window.PRESERVED = {…}</script>` 로 다시 넣는다. 모델이 목록을 다시 타이핑하지
않게 하려는 것이다 — 자동 Run 4·5 는 원본의 67개를 3~9개로 줄여 썼고, 프롬프트에
"하나도 빠뜨리지 마라" 를 넣은 Run 5 도 9번 시도 모두 4개였다
(`docs/variance-notes.md`). 모델이 같은 이름을 배열 리터럴로 다시 선언하면 도구가
그 초기화 식만 `window.PRESERVED.<이름>` 참조로 바꾼다. 넣어 준 이름을 스크립트가
읽지 않으면 형식 검사에서 떨어진다 (브라우저를 띄우지 않는다) — 다만 그 목록의
값을 하나도 빠뜨리지 않고 직접 쓴 경우는 요구하지 않는다. 그때는 참조하든 않든
결과가 같은데, 요구하면 숫자판을 마크업에 적은 설계가 그것 때문에 재시도를 한 번
쓴다.

<!-- PLAN_PROMPT -->
## 1. 과제

{{TASK}}

이번 답에서는 HTML 을 만들지 않는다. 먼저 원본을 진단하고, 다시 설계할 계획을 세운다.
HTML 은 다음 단계에서 이 계획을 받아 만든다.

- 규칙 목록은 주지 않는다. 각 화면에서 고령 사용자가 어디서 멈추고, 무엇을 잘못 누르고,
  무엇을 못 읽을지를 원본에서 직접 보고 적어라.
- 아래 "원본 화면" 그림이 있으면 먼저 그림을 보라. 진단은 화면에서 보이는 것에서 시작한다.
- 진단마다 근거(`evidence`)를 적어라. 화면에서 보이는 것을 먼저 적는다 — 어느 화면 그림의
  어디에 무엇이 어떻게 보이는가. 코드는 화면으로 알 수 없는 동작(누르면 무슨 일이 생기는가,
  입력한 값이 지워지는가, 무엇이 갖춰져야 버튼이 켜지는가)을 말할 때만 근거로 쓴다. 그림에서
  보이는 것을 CSS 값으로 옮겨 적지 마라. 원본에서 가리킬 수 없는 일반론은 적지 마라.
- `evidence_kind` 에 근거의 종류를 적는다: 그림만 보고 `"screen"`, 코드만 보고 `"code"`,
  둘 다 `"both"`.
- 화면을 몇 개로 나눌지, 어떤 순서로 둘지는 자유다. 원본 구조를 지킬 필요 없다.
- 변경마다 어느 진단에 대응하는지(`addresses`)를 적어라.
- 원본의 화면은 다음과 같다: {{ORIGINAL_SCREENS}}

{{CHOICES}}

{{ERRORS}}

{{TASK_PLAN_ERRORS}}선택지 데이터를 계획에서 언급할 때는 `window.PRESERVED.<이름>` 의 이름으로만 말하고,
값을 다시 나열하지 마라.

## 2. 출력 형식

답은 ```` ```json ```` 코드 블록 하나뿐이다. 설명 문장을 앞뒤에 붙이지 마라.
아래는 칸의 모양이다. `<...>` 자리를 네 진단과 계획으로 채우고, 항목은 필요한 만큼 둔다.

```json
{
  "diagnosis": [
    {"id": "D1", "screen": "<원본 data-screen>", "element": "<요소>",
     "problem": "<고령 사용자가 어디서 왜 막히는지>",
     "evidence": "<원본의 무엇을 보고>",
     "evidence_kind": "<screen | code | both>"}
  ],
  "plan": {
    "screens": [
      {"name": "<새 화면 이름>", "purpose": "<이 화면에서 사용자가 하는 일>",
       "from": ["<바탕이 된 원본 data-screen>"]}
    ],
    "changes": [
      {"id": "C1", "what": "<무엇을 바꾸는가>", "why": "<왜>",
       "addresses": ["<진단 id>"], "from_screens": ["<원본 data-screen>"],
       "to_screens": ["<새 화면 이름>"]}
    ]{{TASK_PLAN_ERRORS_FORM}}
  }
}
```

규칙:
- 진단 id 는 `D1`, `D2` …, 변경 id 는 `C1`, `C2` … 로 겹치지 않게 매긴다.
- `screens[].name` 은 영문 소문자(숫자·`-`·`_` 가능)다. 이 이름이 그대로 재설계 HTML 의
  `data-screen` 이 된다. 순서는 사용자가 지나가는 순서로 둔다.
- `from` · `from_screens` 에는 원본의 화면 이름만 쓴다. 원본에 없던 새 화면이면 `from` 은 `[]`.
- `to_screens` 에는 `screens` 에 있는 이름만 쓴다.
- `addresses` 에는 `diagnosis` 에 있는 id 만 쓴다.{{TASK_PLAN_ERROR_RULE}}

{{RETRY_BLOCK}}

{{ORIGINAL_SHOTS}}## 원본

```html
{{ORIGINAL_HTML}}
```
<!-- /PLAN_PROMPT -->

<!-- PROMPT -->
## 1. 과제

{{TASK}}

아래 "계획" 은 이 원본을 진단해 세운 것이다. 이 계획대로 설계하라.

- 화면은 계획의 `screens` 와 같아야 한다. 각 화면의 `data-screen` 은 `screens[].name` 과
  한 글자도 다르지 않아야 하고, 계획에 없는 화면을 더하지 마라. 어긋나면 형식 오류로
  돌아온다.
- 계획에 없는 큰 변경(화면 추가·삭제·순서 변경, 과업 경로 변경)은 하지 마라. 글자·크기·
  배치 같은 세부는 네가 정한다.
{{TASK_NOTES}}
- 화면의 모든 글은 한국어로 쓴다. 영어 단어를 새로 넣지 않는다.

## 2. 지켜야 할 기술 계약 (검사기가 이 형식으로 화면을 몰고 다닌다)

- 파일 하나. 외부 자원 없음. `<html lang="ko">`.
- `<div id="phone">` 안에 화면들. 폭 390px, 높이 844px.
- 화면 하나는 `<section class="screen" data-screen="이름">`. 보이는 화면에만 `on` 클래스.
  화면 이름은 영문 소문자.
- 모든 조작은 `data-action="이름"` 속성으로 표시하고, `#phone` 에 붙인 **하나의** 클릭
  처리기 안에서 `const a = el.dataset.action;` 뒤 `if(a==='이름'){…} else if(a==='이름'){…}`
  형식으로 분기한다. 처리되지 않는 `data-action` 을 남기지 마라. `onclick` 속성, `alert()`,
  `confirm()`, `prompt()` 는 쓰지 마라.
- 숫자판은 버튼마다 `data-action` 과 `data-v="숫자"` 를 둔다.
- 전역에 `window.__screen()` (현재 화면 이름 반환), `window.__log` (배열), `window.__startTask()`,
  `window.__dump()` 를 둔다. 화면이 바뀔 때마다 `__log` 에 `{type:'screen_enter', to:이름}` 을 넣는다.
{{TASK_RULES}}
- **원본에 있던 선택지는 하나도 빠뜨리지 마라.** 스크립트 배열로 그려지는 목록은 도구가
  `window.PRESERVED.<이름>` 으로 넣어 준다 (아래 "원본이 가진 선택지" 참고). 그 목록을
  직접 타이핑하지 말고 그 이름을 참조해 그려라 - 넣어 준 이름을 하나라도 읽지 않으면
  형식 오류로 돌아온다. 화면에 몇 개를 어떻게 보일지는 네가 정하되(검색, 자주 쓰는 것
  먼저, 탭 등), 모든 값을 고를 수 있어야 하고, **선택 화면이 열렸을 때 모든 값이 DOM
  안에 있어야 한다** (숨김·접힘은 괜찮다). 검색창을 두더라도 검색어가 비었을 때는 전체
  목록이 DOM 에 있어야 한다.
- 텍스트 대비는 흰 배경에서 4.5:1 이상. 글자 색을 상속에만 맡기지 말고 규칙으로 지정하라.
- 마크업에서 쓰는 클래스는 모두 `<style>` 안에 정의하라.

{{CHOICES}}

{{ERRORS}}

## 계획

```json
{{PLAN}}
```

{{TASK_ERRORS_NOTE}}## 3. 흐름 명세도 함께 출력하라

검사기는 화면을 어떻게 지나가는지 모른다. 네가 만든 설계를 검사기가 처음부터 끝까지 몰고
갈 수 있도록 **흐름 명세 JSON** 을 HTML 과 함께 출력하라. 형식은 다음과 같다.

```json
{{TASK_FLOW_EXAMPLE}}
```

규칙:
- `steps` 는 검사기가 지나가는 순서. 각 항목의 `screen` 은 그 단계를 수행한 **뒤에 도착해
  있어야 할** 화면 이름(`data-screen` 값)이다. 첫 항목은 시작 화면이고 동작이 없다.
- 한 단계의 동작은 `click` 하나이거나 `do` 배열이다. `do` 의 항목은 `{"click": 선택자}`,
  `{"type": 문자열, "key": 선택자틀}` (문자열의 글자마다 `%s` 자리에 넣어 클릭),
  `{"repeat": n, "click": 선택자, "wait": 초}`, `{"wait": 초}` 중 하나.
{{TASK_FLOW_VALUES}}{{TASK_FLOW_ERRORS}}
{{TASK_FLOW_DONE}}
- `derived_from_original` 은 `false`.
- 선택자는 네 HTML 에 있는 것만 쓴다. 검사기는 없는 선택자에서 멈춘다.

## 4. 출력 형식

답은 코드 블록 두 개만으로 구성한다. 설명 문장을 앞뒤에 붙이지 마라.

1. ```` ```html ```` 블록 — 파일 전체
2. ```` ```json ```` 블록 — 흐름 명세

{{RETRY_BLOCK}}

## 원본

```html
{{ORIGINAL_HTML}}
```
<!-- /PROMPT -->

## 반성 요청 (재시도 때만)

재시도 프롬프트에서는 아래 블록이 `{{RETRY_BLOCK}}` 의 맨 앞, 실패 목록보다 위에
들어간다 (`prompt.reflection_request`). 코드보다 반성을 먼저 쓰게 하려는 것이다.
반성의 `plan_changes` 는 도구가 계획에 적용하고(`plan.apply_changes`), 바뀐 계획은
그 시도의 `attempt_N.plan.json` 으로 남는다.

<!-- REFLECT -->
## 반성 먼저

이번 답은 코드 블록 세 개다 — ```` ```json ```` (반성) → ```` ```html ```` → ```` ```json ````
(흐름 명세). 다른 설명은 붙이지 마라.

코드를 쓰기 전에, 아래 실패를 보고 반성을 먼저 써라. 아래는 칸의 모양이다. `<...>` 자리를
채우고, `plan_changes` 의 항목은 필요한 만큼 둔다.

```json
{"cause": "<실패의 원인 한 문장. 증상이 아니라 원인>",
 "plan_changes": [
   {"op": "<add | change | remove>",
    "target": "<C번호 | change | screen | screen:화면이름>",
    "new": {"<바꾸거나 더할 칸>": "<값>"},
    "why": "<왜 계획을 바꾸는가>"}
 ],
 "keep": ["<그대로 두는 계획 항목: C번호 또는 화면 이름>"]}
```

- 계획이 틀려서 떨어진 것이 아니면 `plan_changes` 는 `[]` 로 둔다. 구현만 고치면 되는
  실패에서 계획을 바꾸지 마라.
- `op` 와 `target` 의 짝: `change` + C번호 는 그 변경의 칸을 `new` 로 고친다. `remove` +
  C번호 는 그 변경을 뺀다. `add` + `change` 는 `new` 가 새 변경 하나다 (id 포함).
  `add` + `screen` 은 `new` 가 새 화면 하나다 (`name` · `purpose` · `from`, 넣을 자리는
  `"after": "<화면 이름>"`). `change` + `screen:이름` 은 그 화면의 칸을 고친다.
  `remove` + `screen:이름` 은 그 화면을 뺀다.
- 바꾼 계획은 도구가 반영한다. 이번 HTML 의 화면은 바뀐 계획과 같아야 한다.
<!-- /REFLECT -->

## 재시도 블록의 모양

`{{RETRY_BLOCK}}` 은 이전 시도가 검사에 떨어졌을 때만 채워진다. 스크립트가 만드는 내용:

```
## 이전 시도의 실패

직전 출력은 검사에서 다음 fatal 에 걸렸다. 아래 목록을 모두 고쳐서 HTML 과 흐름 명세를
다시 전체로 출력하라. 설계를 처음부터 새로 하지 말고 직전 출력을 고쳐라.

- [A] screen=bank: never reached (task stopped after 3 of 9 screens)
- [C] data-action='bank-yes' has no branch in the handler - ...

### 직전 흐름 명세
```json … ```

### 직전 HTML
```html … ```
```
