r"""입력이 가진 선택지 데이터를 꺼내고, 재설계 HTML 에 넣는다.

자동 Run 4·5 가 보여 준 것은 이렇다. 원본은 은행 38개와 증권사 29개를 스크립트
배열로 들고 있고, LLM 은 재설계할 때 그 목록을 **다시 타이핑한다** - 그러면서
3~9개로 줄인다. 프롬프트에 "배열은 원본 그대로 두고 참조해 그려라, 값은 하나도
빠뜨리지 마라" 를 넣은 Run 5 도 9번 시도 모두 4개였다 (docs/variance-notes.md).
말로 지시하는 방법은 효과가 없었다.

그래서 데이터는 도구가 들고 있는다. 모델은 화면 구조와 보여 주는 방식을 자유롭게
정하되(화면 수·순서·검색·탭·자주 쓰는 항목 먼저), 선택지 데이터는 다시 타이핑하지
않고 `window.PRESERVED.<이름>` 을 참조해 그린다.

이 파일이 하는 일은 셋이다.

    preserved_data   입력 HTML 에서 "스크립트 배열로 그려지는 선택지" 를 꺼낸다
    inject           재설계 HTML 에 데이터 블록을 넣는다
    names_read       재설계 HTML 의 스크립트가 그 데이터를 읽는지 본다

은행·금융에 묶인 이름은 한 줄도 없다. 판단 기준은 "같은 data-action 을 공유하는
반복 요소" 와 "그 값들을 담고 있는 스크립트 배열" 뿐이므로, 사람이 만든 원본이든
나중에 스크린샷에서 만든 HTML 이든 같은 규칙으로 돈다.

선택지 집합을 모으는 방식은 검사 I 와 같다 (`choice_groups`). 모델이 보는 것과
검사가 세는 것이 어긋나면, 지키라고 넣어 준 데이터와 지켰는지 보는 기준이 다른
것이 된다.
"""
import json
import re

from senior_ui.preserved import DATA_BLOCK_ID, GLOBAL_NAME

# 스크립트 안의 배열 선언 하나. 원소에 `]` 가 없으므로 여러 줄에 걸쳐 적은
# 배열도 하나로 잡힌다 (원본의 BANKS 가 네 줄이다).
ARRAY_DECL = re.compile(r"(?:const|let|var)\s+([A-Za-z_]\w*)\s*=\s*\[([^\]]*)\]")

SCRIPT = re.compile(r"<script[^>]*>(.*?)</script>", re.S | re.I)

# 모델이 같은 이름을 **배열 리터럴로** 다시 선언한 자리. `= window.PRESERVED.X`
# 처럼 참조로 쓴 것은 걸리지 않는다 - `=` 바로 뒤가 `[` 여야 한다.
DECL_LITERAL = r"\b(const|let|var)(\s+%s\s*=\s*)\[[^\]]*\]"

# 데이터를 **읽는** 자리. `window.` 는 있어도 없어도 되고, 점 표기와 대괄호
# 표기를 둘 다 본다. 도구가 넣은 블록(`window.PRESERVED = {...}`)은 이름 뒤가
# `=` 이므로 걸리지 않는다 - 그것을 "읽었다" 로 세면 검사가 늘 통과한다.
READ = (r"(?:window\s*\.\s*)?%s\s*(?:\.\s*%s\b|\[\s*[\"']%s[\"']\s*\])"
        % (GLOBAL_NAME, "%s", "%s"))

FIRST_SCRIPT = re.compile(r"<script\b", re.I)

# 고친 자리에 남기는 표시. 산출물을 그냥 열어 본 사람이 "이 줄은 모델이 쓴
# 것이 아니다" 를 파일 안에서 알 수 있어야 한다 - 연구에서 모델이 만든 것과
# 도구가 고친 것을 구분해야 하기 때문이다.
REWRITE_MARK = " /* 도구가 바꿨다: 모델이 쓴 목록을 입력의 것으로 */"


def scripts(html):
    """문서 안의 스크립트 본문을 모두 이어 붙인 것."""
    return "\n".join(SCRIPT.findall(html or ""))


def script_arrays(html):
    """스크립트 안의 배열 선언. `[(이름, [원소들])]`.

    원소는 문자열로 돌려준다. 원본은 은행 이름을 문자열로, 숫자판을 숫자로
    적지만 선택지로서는 둘 다 "고를 수 있는 값" 하나이고, DOM 의 `data-*` 로
    내려가면 어차피 문자열이 된다 - 검사 I 가 세는 것도 그 문자열이다.
    """
    return [(name, [v.strip().strip("'\"") for v in body.split(",") if v.strip()])
            for name, body in ARRAY_DECL.findall(scripts(html))]


def choice_groups(snapshot):
    """스냅샷이 모은 선택지 집합. `{action: {값들}}`.

    검사 I 가 원본에서 모으는 바로 그 집합이다 (`i_choices.run`). 두 곳이
    각자 모으면 모델에게 지키라고 준 데이터와 검사가 세는 값이 갈라진다.
    """
    groups = {}
    for row in (snapshot.get("screens") or {}).values():
        for action, vals in (row.get("choices") or {}).items():
            groups.setdefault(action, set()).update(vals)
    return groups


def backing(vals, arrays):
    """그 선택지 값을 담고 있는 스크립트 배열. `[(이름, 원소 수)]`.

    절반 넘게 겹치면 그 배열이 그 목록이라고 본다. 전부 겹칠 것을 요구하면
    배열 하나가 두 묶음으로 나뉘어 그려지는 경우(원본의 은행 38 + 증권사 29)를
    놓치고, 하나만 겹쳐도 된다고 하면 색 배열 같은 것이 섞여 들어온다.
    """
    return [(name, len(items)) for name, items in arrays
            if items and len(set(items) & vals) >= max(2, len(items) // 2)]


def split_groups(snapshot, html):
    """선택지를 둘로 가른다. `(스크립트가 그리는 것, 마크업에 직접 있는 것)`.

    원소는 `(action, 값 개수, [(배열 이름, 원소 수)])` 이고, 값이 많은 것부터다.

    가르는 기준은 마크업에 그 `data-action` 이 몇 번 적혀 있는지다. 값보다 적게
    적혀 있으면 나머지는 스크립트가 그린 것이다 - 원본의 은행 목록은 마크업에
    템플릿 조각 하나뿐이고 67개가 런타임에 생긴다.

    값이 둘 미만인 묶음은 선택지가 아니다. 검사 I 와 같은 기준이다.
    """
    groups = choice_groups(snapshot)
    arrays = script_arrays(html)
    generated, inline = [], []
    for action, vals in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        if len(vals) < 2:
            continue
        in_markup = len(re.findall(r'data-action="%s"' % re.escape(action),
                                   html or ""))
        if in_markup < len(vals):
            generated.append((action, len(vals), backing(vals, arrays)))
        else:
            inline.append((action, len(vals), []))
    return generated, inline


def preserved_data(snapshot, html):
    """스크립트 배열로 그려지는 선택지 데이터. `{배열 이름: [원소들]}`.

    도구가 이것을 들고 있다가 재설계 HTML 에 그대로 넣는다. 모델은 이 값을
    다시 타이핑하지 않는다.

    마크업에 직접 쓰인 선택지(숫자판 등)는 여기 들어오지 않는다. 그것은 모델이
    그대로 옮기거나 바꿀 수 있는 것이고, 지키라고 넘겨 줄 데이터가 아니다.
    """
    arrays = dict(script_arrays(html))
    generated, _inline = split_groups(snapshot, html)
    out = {}
    for _action, _count, src in generated:
        for name, _n in src:
            if name in arrays:
                out.setdefault(name, arrays[name])
    return out


def data_block(data):
    """데이터 블록 하나. 모델의 스크립트보다 앞에 놓인다."""
    body = json.dumps(data, ensure_ascii=False)
    # 값에 `</script>` 가 들어 있으면 블록이 거기서 끝나고 그 뒤가 마크업이
    # 된다. `<` 를 전부 JSON 이스케이프로 바꾸면 그 일이 생기지 않고, JSON 으로
    # 읽은 값은 원래 글자 그대로다. 입력이 무엇이든 돌아야 하므로 막아 둔다.
    body = body.replace("<", "\\u003c")
    # 블록이 스스로 무엇인지 말하게 한다. 이 파일은 디자이너와 연구자가 그냥
    # 열어 보는 산출물이고, 그때 "이 줄은 모델이 쓴 것이 아니다" 가 파일 안에
    # 적혀 있어야 한다 - summary.json 을 같이 열어 보지는 않는다.
    return ('<script id="%s">/* 도구가 넣었다: 입력 HTML 이 가진 선택지 데이터. '
            '모델이 쓴 것이 아니다. */\n'
            'window.%s = %s;</script>'
            % (DATA_BLOCK_ID, GLOBAL_NAME, body))


def redeclare(html, names):
    """모델이 다시 타이핑한 배열 선언의 **초기화 식만** 참조로 바꾼다.

    돌려주는 것은 `(고친 HTML, 고친 이름들)`.

    세 가지 중에 이것을 고른 이유다.

      그대로 두기   모델이 타이핑한 짧은 목록이 이긴다. 데이터 블록은 들어가고
                    화면은 4개만 그린다 - 장치가 아무 일도 하지 않은 것이 된다.
      선언을 지우기 그 이름을 쓰는 코드가 ReferenceError 로 죽는다. JS 오류 하나가
                    클릭 처리기를 멈추게 하므로 모든 검사가 그 결과만 본다.
      초기화 식만   선언은 남으니 쓰는 쪽 코드는 그대로 돌고, 값은 입력의 것이
                    된다. 모델의 설계는 건드리지 않고 데이터만 바로잡는다.

    조용히 바꾸지 않는다. 고친 이름을 돌려주고 부르는 쪽이 기록한다 - 모델이
    목록을 다시 타이핑했다는 사실 자체가 결과다.
    """
    changed = []
    for name in names:
        pattern = re.compile(DECL_LITERAL % re.escape(name))
        html, n = pattern.subn(
            lambda m: "%s%swindow.%s.%s%s" % (m.group(1), m.group(2), GLOBAL_NAME,
                                              name, REWRITE_MARK),
            html)
        if n:
            changed.append(name)
    return html, changed


def place(html, block):
    """데이터 블록을 문서에 끼운다.

    모델의 첫 스크립트보다 앞이다. 뒤에 넣으면 모델의 코드가 아직 세워지지 않은
    전역을 읽는다. 스크립트가 하나도 없으면 문서가 닫히기 전에 둔다 - 그런 답은
    클릭 처리기가 없어서 형식 검사에서 따로 걸리지만, 블록이 문서 밖으로 나가는
    일은 없어야 한다.
    """
    m = FIRST_SCRIPT.search(html)
    if m:
        return html[:m.start()] + block + "\n" + html[m.start():]
    low = html.lower()
    for tag in ("</body>", "</html>"):
        i = low.find(tag)
        if i >= 0:
            return html[:i] + block + "\n" + html[i:]
    return html + "\n" + block + "\n"


def inject(html, data):
    """재설계 HTML 에 데이터 블록을 넣는다.

    돌려주는 것은 `(HTML, 모델이 같은 이름을 다시 선언한 이름들)`. 넣을 데이터가
    없으면 받은 것을 그대로 돌려준다 - 입력에 스크립트로 그리는 선택지가 없으면
    이 장치는 아무 일도 하지 않는다.
    """
    if not data:
        return html, []
    html, changed = redeclare(html, list(data))
    return place(html, data_block(data)), changed


def names_read(html, names):
    """재설계 HTML 의 스크립트가 실제로 읽는 이름. `names` 의 순서로.

    마크업에 글자로 적어 둔 것은 읽는 것이 아니므로 스크립트 안에서만 본다.
    """
    body = scripts(html)
    return [n for n in names
            if re.search(READ % (re.escape(n), re.escape(n)), body)]
