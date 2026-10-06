r"""클릭 처리기가 분기로 다루는 data-action 이름을 읽는다.

두 곳이 같은 판단을 해야 한다. 검사 C (checks/c_dead_controls.py) 는 "눌러도
아무 일도 없는 조작부" 를 이 목록으로 가리고, 재구성 쪽의 흐름 명세 검사
(restructure/reply.py 의 _check_handlers) 는 같은 목록으로 모델에게 "이렇게
쓰면 검사기가 읽는다" 를 알려 준다. 한쪽만 넓히면 모델은 읽히는 모양으로 썼는데
검사기가 못 읽거나, 검사기는 읽는데 모델에게는 못 읽는다고 말하게 된다. 그래서
읽는 규칙은 이 파일 하나에만 둔다.

읽는 모양은 두 가지다. 변수 이름은 `a` 로 못박혀 있다 - 프롬프트가 그렇게
쓰라고 적어 두기 때문이다.

    if (a === 'go-next')      a === "go-next"       홑/쌍따옴표 둘 다
    switch (a) { case 'go-next':   case "go-next":  }

`a === …` 쪽은 `\ba` 로 시작한다. 그렇게 하지 않으면 `data === 'x'` 의 끝 글자
같은 것이 분기로 잡힌다.
"""
import re

# 이름에 쓸 수 있는 글자는 \w 와 하이픈이다. [a-z-] 로 좁히면 go2 · accNum ·
# acc_num 같은 이름을 쓴 빌드의 분기가 전부 없는 것으로 읽힌다.
#
# \w 는 ASCII 로만 읽는다 (re.ASCII). 이 레포의 주석과 프롬프트는 한국어이고
# 거기에는 `a === '이름'` 이라는 설명이 그대로 들어 있다. 유니코드 \w 로 읽으면
# 그 설명이 분기로 잡혀서, 처리기가 주석뿐인 빌드가 "분기가 있다" 로 읽힌다 -
# 검사 C 가 잡아야 하는 바로 그 빌드다. data-action 이름은 JS 문자열이자 HTML
# 속성값이고 실제로 전부 ASCII 다.
BRANCH = re.compile(r"\ba\s*===\s*['\"]([\w-]+)['\"]", re.ASCII)
CASE = re.compile(r"\bcase\s*['\"]([\w-]+)['\"]", re.ASCII)

PATTERNS = (BRANCH, CASE)

# 문서에 글자 그대로 적힌 data-action 이름. 스크립트의 템플릿이 그리는 이름
# (`data-action="${'num'}"`, `data-action="key-${k}"`)은 렌더되기 전에는 이름이
# 아니다 - 원본의 keyButtons 가 이 관용구를 쓴다.
ATTR = re.compile(r'data-action="([^"]+)"')


def handled_actions(html):
    """`html` 의 처리기가 분기로 다루는 data-action 이름의 집합."""
    out = set()
    for p in PATTERNS:
        out |= set(p.findall(html))
    return out


def literal_actions(html):
    """`html` 에 글자 그대로 적힌 data-action 이름의 집합. 템플릿(`${…}`)이 든
    값은 뺀다.

    검사 C 는 렌더된 DOM 의 data-action 으로 판정한다 - 템플릿이 그린 조작부도
    렌더된 이름(num)으로 본다. 브라우저 없이 미리 보는 형식 검사는 렌더된 이름을
    알 수 없으므로 템플릿 값은 판단하지 않고 검사 C 에 맡긴다. `${'num'}` 을
    이름으로 읽으면 분기가 멀쩡한 설계가 형식에서 떨어진다 (감사 B-11)."""
    return {a for a in ATTR.findall(html) if "${" not in a}
