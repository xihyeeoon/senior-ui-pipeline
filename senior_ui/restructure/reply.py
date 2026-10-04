r"""모델의 답을 HTML + 흐름 명세로 가르고, 검사기에 넣기 전에 모양을 본다.

parse_reply 는 코드 블록 두 개를 떼어 내고, validate_flow 는 검사기가 그대로
돌면 터질 모양을 미리 잡는다. 두 쪽 다 실패 메시지가 바로 다음 프롬프트에
들어가므로, 메시지는 사람보다 모델이 읽는 글이다.

validate_flow 는 검사 하나에 함수 하나다 (_check_*). 아래 CHECKS 의 순서가
problems 목록의 순서이고, 그 순서는 재시도 프롬프트에 그대로 나타난다 -
바꾸면 출력이 바뀐다.
"""
import json
import re

from ..audit.handlers import handled_actions

FENCE = re.compile(r"```(html|json)[ \t]*\r?\n(.*?)\r?\n[ \t]*```", re.S)


def parse_reply(text):
    """Last ```html``` block and last ```json``` block. Raises ValueError with
    a message meant to go straight into the next prompt."""
    blocks = {}
    for kind, body in FENCE.findall(text):
        blocks[kind] = body
    if "html" not in blocks:
        raise ValueError("답에 ```html 코드 블록이 없다")
    if "json" not in blocks:
        raise ValueError("답에 ```json 흐름 명세 블록이 없다")
    html = blocks["html"]
    if "<html" not in html.lower() or "</html>" not in html.lower():
        raise ValueError("html 블록이 완전한 문서가 아니다 (<html> … </html> 필요)")
    try:
        flow = json.loads(blocks["json"])
    except json.JSONDecodeError as e:
        raise ValueError("흐름 명세가 JSON 으로 읽히지 않는다: %s" % e)
    return html, flow, blocks["json"]


# --------------------------------------------------------------------------- #
# 흐름 명세 검사 - 하나에 함수 하나
# --------------------------------------------------------------------------- #
def _steps_of(flow):
    """steps 를 목록으로 정규화한다. 모양이 틀리면 빈 목록 - 비어 있다는 사실은
    _check_steps 가 problems 에 적는다."""
    steps = flow.get("steps")
    return steps if isinstance(steps, list) and steps else []


def _check_steps(flow, html, steps, screens):
    """steps 목록 자체의 모양. 첫 단계는 시작 화면이므로 동작이 없어야 한다."""
    problems = []
    if not steps:
        problems.append("steps 가 비어 있다")
    elif isinstance(steps[0], dict) and ("click" in steps[0] or "do" in steps[0]):
        problems.append("steps[0] 은 시작 화면이므로 동작(click/do)이 없어야 한다. 각 step 의 "
                        "screen 은 그 동작을 한 *뒤에* 도착해 있는 화면이다 — 동작이 일어나는 "
                        "화면이 아니다. 목록 전체를 한 칸씩 다시 맞춰라")
    return problems


def _check_handlers(flow, html, steps, screens):
    """클릭 처리기가 검사기가 읽을 수 있는 모양인지, 분기 없는 data-action 이
    있는지.

    읽는 함수는 검사 C 와 같은 것이다 (audit/handlers.py). 두 곳이 각자 읽으면
    "검사기가 읽는 모양" 이라고 모델에게 알려 주는 것과 검사기가 실제로 읽는
    것이 갈라진다."""
    problems = []
    handled = handled_actions(html)
    actions = set(re.findall(r'data-action="([^"]+)"', html))
    if not handled:
        problems.append("클릭 처리기에 data-action 분기가 하나도 없다. 검사기가 읽는 모양은 "
                        "`a === '이름'` 과 `switch(a){ case '이름': }` 두 가지다 (따옴표는 "
                        "홑/쌍 둘 다 된다). 다른 변수 이름은 읽지 못한다 - "
                        "`const a = el.dataset.action;` 뒤에 그 두 모양 중 하나로 써라")
    else:
        dead = sorted(actions - handled)
        if dead:
            problems.append("data-action 이 있지만 분기가 없는 것: " + ", ".join(dead))
    return problems


def _check_step_screens(flow, html, steps, screens):
    """단계마다 screen 이 있고, 그 이름이 HTML 에 실제로 있고, 첫 단계 말고는
    동작이 하나는 있는지."""
    problems = []
    for i, st in enumerate(steps):
        if not isinstance(st, dict) or "screen" not in st:
            problems.append("steps[%d] 에 screen 이 없다" % i)
            continue
        if st["screen"] not in screens:
            problems.append("steps[%d].screen=%r 은 HTML 의 data-screen 에 없다 (있는 것: %s)"
                            % (i, st["screen"], ", ".join(sorted(screens))))
        if i > 0 and "click" not in st and "do" not in st:
            problems.append("steps[%d] (%s) 에 click 도 do 도 없다" % (i, st["screen"]))
    return problems


def _has_click(item):
    return isinstance(item, dict) and "click" in item


def _check_transitions(flow, html, steps, screens):
    """화면을 넘기는 것은 클릭뿐이다. 타이핑으로 끝나는 단계는 다음 화면에 도달할
    수단이 없고, 검사기는 아직 켜지지 않은 화면 안의 요소를 찾다 멈춘다. 이것은
    브라우저를 띄우지 않고도 흐름 명세만 보면 알 수 있다."""
    problems = []
    for i, st in enumerate(steps[:-1]):          # 마지막 화면은 넘어갈 곳이 없다
        if not isinstance(st, dict) or "screen" not in st:
            continue
        nxt = steps[i + 1].get("screen") if isinstance(steps[i + 1], dict) else "?"
        here = st["screen"]
        if "do" not in st:
            continue                              # click 하나짜리 단계는 문제없다
        do = st["do"] if isinstance(st["do"], list) else [st["do"]]
        if not do:
            continue
        if not any(_has_click(x) for x in do):
            problems.append(
                "흐름 명세: %r 의 do 에 클릭이 하나도 없다. 타이핑과 대기만으로는 "
                "화면이 바뀌지 않으므로 %r 로 갈 수 없다. %s 에서 %s 로 넘어가는 "
                "클릭 단계를 추가하라." % (here, nxt, here, nxt))
        elif not _has_click(do[-1]):
            kind = "type" if "type" in do[-1] else list(do[-1])[0] if do[-1] else "?"
            problems.append(
                "흐름 명세: %r 의 마지막 동작이 %s 이다. 타이핑은 화면을 넘기지 "
                "않으므로 %r 로 갈 수 없다. %s 에서 %s 로 넘어가는 클릭 단계를 "
                "추가하라." % (here, kind, nxt, here, nxt))
    return problems


OMIT = r"(\.\.\.|…|\betc\b|\bother\b|생략|나머지)"


def _check_omissions(flow, html, steps, screens):
    """값싼 조기 탐지. "나머지는 생략" 하고 끝낸 목록은 검사기 I 가 잡지만,
    브라우저를 띄우기 전에 걸러내면 한 번 덜 돈다. I 의 대체가 아니라 차단이다."""
    problems = []
    for m in re.finditer(r"<(ul|ol|select|tbody)\b[^>]*>(.*?)</\1>", html, re.S | re.I):
        tail = m.group(2)[-400:]
        if re.search(r"<!--[^-]*?%s.*?-->" % OMIT, tail, re.I | re.S) \
                or re.search(r">\s*%s\s*<" % OMIT, tail, re.I):
            problems.append(
                '목록이 "생략" 표시로 끝난다 (… / etc / other / 생략). 원본에 있던 '
                "선택지는 하나도 빠뜨리면 안 된다. 화면에 몇 개를 보일지는 네가 정하되 "
                "값은 전부 포함하라.")
            break
    return problems


def _check_ids(flow, html, steps, screens):
    """required_ids 가 목록인지, 과제가 반드시 쓰는 두 id 가 양쪽에 다 있는지."""
    problems = []
    ids = set(re.findall(r'\bid="([^"]+)"', html))
    req = flow.get("required_ids")
    if not isinstance(req, list):
        problems.append("required_ids 가 목록이 아니다")
        req = []
    for must in ("phone", "dn-amt"):
        if must not in req:
            problems.append("required_ids 에 %r 이 없다" % must)
        if must not in ids:
            problems.append("HTML 에 id=%r 요소가 없다" % must)
    missing = [i for i in req if i not in ids]
    if missing:
        problems.append("required_ids 중 HTML 에 없는 id: " + ", ".join(missing))
    return problems


def _check_expect(flow, html, steps, screens):
    """완료 화면에서 금액을 확인할 짝이 있는지."""
    problems = []
    expect = flow.get("expect")
    if not isinstance(expect, dict):
        problems.append("expect 가 객체가 아니다")
    else:
        done = expect.get("done") or []
        if not any(isinstance(p, list) and len(p) == 2 and p[0] == "#dn-amt" for p in done):
            problems.append('expect.done 에 ["#dn-amt", "{AMOUNT_SHOWN}"] 이 없다')
    return problems


def _check_derived(flow, html, steps, screens):
    """새 설계이므로 원본에서 파생된 빌드가 아니다."""
    if flow.get("derived_from_original", False):
        return ["derived_from_original 은 false 여야 한다"]
    return []


def _check_coverage(flow, html, steps, screens):
    """HTML 에 있지만 흐름이 지나가지 않는 화면."""
    unseen = screens - {st.get("screen") for st in steps if isinstance(st, dict)}
    if unseen:
        return ["steps 가 지나가지 않는 화면: " + ", ".join(sorted(unseen))]
    return []


# 이 순서가 problems 의 순서다.
CHECKS = [_check_steps, _check_handlers, _check_step_screens, _check_transitions,
          _check_omissions, _check_ids, _check_expect, _check_derived,
          _check_coverage]


def validate_flow(flow, html):
    """Shape checks the audit would otherwise crash on, phrased for the model."""
    if not isinstance(flow, dict):
        return ["흐름 명세가 객체가 아니다"]
    # literal names only - a template literal like data-screen="${x}" in the
    # script is not a screen
    screens = set(re.findall(r'data-screen="([a-z0-9_-]+)"', html))
    steps = _steps_of(flow)
    problems = []
    for check in CHECKS:
        problems += check(flow, html, steps, screens)
    return problems


def failure_report(kind, detail):
    """An audit-shaped report for a reply that never reached the audit, so the
    retry block and summary treat it like any other fatal."""
    return {"passed": False,
            "fatal": [{"check": kind, "screen": None, "detail": detail}],
            "warning": [], "metrics": {"flow": "auto", "not_audited": True}}
