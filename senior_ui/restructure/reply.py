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

from ..audit.checks.i_choices import present
# 오류 경로 · 방문 이름의 규칙은 검사기의 것을 그대로 쓴다. 따로 쓰면 한쪽만
# 고쳐지는 순간 형식 검사와 검사 J 가 갈라진다 (감사 B-10).
from ..audit.checks.j_errors import back_to_ok, done_screen, step_screens
from ..audit.flow import visit_keys
from ..audit.handlers import handled_actions, literal_actions
from ..preserved import GLOBAL_NAME
from ..tasks import load_task
from .preserve import names_read

FENCE = re.compile(r"```(html|json)[ \t]*\r?\n(.*?)\r?\n[ \t]*```", re.S)


class FlowShape(ValueError):
    """흐름 명세의 타입이 틀렸다. 아래 검사들이 읽을 수 있는 모양이 아니다.

    형식 오류와 따로 두는 이유는 부르는 쪽이 다르게 다루기 때문이다 - 이것은
    PARSE 가 아니라 FLOW 문제이고, 문제 목록이 그대로 다음 프롬프트로 간다.
    """

    def __init__(self, problems):
        ValueError.__init__(self, " | ".join(problems))
        self.problems = list(problems)


# JSON 의 타입을 모델이 읽을 말로.
TYPE_NAME = {dict: "객체", list: "배열", str: "문자열", bool: "참/거짓",
             int: "숫자", float: "숫자", type(None): "빈 값"}


def type_of(v):
    return TYPE_NAME.get(type(v), type(v).__name__)


def shape_problems(flow):
    """json.loads 바로 뒤에 보는 타입 검사.

    아래의 다른 검사들은 전부 "흐름 명세는 이런 모양이다" 를 전제로 쓰여 있다.
    그 전제가 깨지면 검사가 문제를 돌려주는 대신 터진다 - 흐름 명세가 배열이면
    `flow.setdefault` 가 AttributeError 로, screen 이 목록이면 집합 검사가
    TypeError 로 죽는다. 둘 다 ValueError 가 아니라서 아무도 받지 못하고 실행
    전체가 역추적만 남겼다.

    그래서 타입만 먼저 보고, 틀린 것은 FLOW 문제로 돌려준다. 여기를 통과한
    흐름 명세는 아래 검사들이 터뜨릴 수 없는 모양이다.
    """
    if not isinstance(flow, dict):
        return ["흐름 명세가 객체가 아니다 (지금은 %s). 최상위는 steps · "
                "required_ids · expect 를 가진 객체 하나여야 한다." % type_of(flow)]
    problems = []
    steps = flow.get("steps")
    if steps is not None and not isinstance(steps, list):
        problems.append("steps 가 목록이 아니다 (지금은 %s)" % type_of(steps))
        steps = None
    for i, st in enumerate(steps or []):
        if not isinstance(st, dict):
            problems.append("steps[%d] 가 객체가 아니다 (지금은 %s). 단계 하나는 "
                            "screen 과 동작을 가진 객체다." % (i, type_of(st)))
            continue
        if "screen" in st and not isinstance(st["screen"], str):
            problems.append("steps[%d].screen 이 문자열이 아니다 (지금은 %s). 화면 "
                            "이름 하나만 적는다 - 한 단계는 한 화면이다."
                            % (i, type_of(st["screen"])))
        if "click" in st and not isinstance(st["click"], str):
            problems.append("steps[%d].click 이 문자열이 아니다 (지금은 %s). CSS "
                            "선택자 하나를 적는다." % (i, type_of(st["click"])))
        if "do" in st and not isinstance(st["do"], (list, dict)):
            problems.append("steps[%d].do 가 목록도 객체도 아니다 (지금은 %s)"
                            % (i, type_of(st["do"])))
    reveal = flow.get("reveal")
    if reveal is not None and not isinstance(reveal, dict):
        problems.append("reveal 이 객체가 아니다 (지금은 %s). 선택지의 data-action "
                        "마다 {\"at\": 화면, \"do\": [동작]} 하나다." % type_of(reveal))
        reveal = None
    for action, spec in (reveal or {}).items():
        if not isinstance(spec, dict):
            problems.append("reveal.%s 가 객체가 아니다 (지금은 %s). {\"at\": steps 의 "
                            "화면 이름, \"do\": [동작]} 이다." % (action, type_of(spec)))
            continue
        if not isinstance(spec.get("at"), str):
            problems.append("reveal.%s.at 이 문자열이 아니다 (지금은 %s). 펼치기 조작을 "
                            "할 화면 - steps 의 화면 이름 하나 - 를 적는다."
                            % (action, type_of(spec.get("at"))))
        if not isinstance(spec.get("do"), (list, dict)):
            problems.append("reveal.%s.do 가 목록도 객체도 아니다 (지금은 %s)"
                            % (action, type_of(spec.get("do"))))
    paths = flow.get("error_paths")
    if paths is not None and not isinstance(paths, list):
        problems.append("error_paths 가 목록이 아니다 (지금은 %s). 오류 경로 "
                        "하나가 객체 하나다." % type_of(paths))
        paths = None
    for i, ep in enumerate(paths or []):
        if not isinstance(ep, dict):
            problems.append("error_paths[%d] 가 객체가 아니다 (지금은 %s)"
                            % (i, type_of(ep)))
            continue
        for key in ("id", "from_step", "expect_screen", "back_to"):
            if key in ep and not isinstance(ep[key], str):
                problems.append("error_paths[%d].%s 가 문자열이 아니다 (지금은 %s)"
                                % (i, key, type_of(ep[key])))
        for key in ("inputs", "recover"):
            if key in ep and not isinstance(ep[key], (list, dict)):
                problems.append("error_paths[%d].%s 가 목록도 객체도 아니다 "
                                "(지금은 %s)" % (i, key, type_of(ep[key])))
    return problems


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
    # 타입 검사는 여기서 끝낸다. 아래 어디에서도 모양을 다시 의심하지 않는다.
    problems = shape_problems(flow)
    if problems:
        raise FlowShape(problems)
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
    actions = literal_actions(html)
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


def _done_of(done):
    """완료 화면에서 확인할 짝들. 주지 않으면 기본 과제(이체)의 것."""
    return load_task()["done_expect"] if done is None else done


def _check_ids(flow, html, steps, screens, done=None):
    """required_ids 가 목록인지, 과제가 반드시 쓰는 id - `#phone` 과 완료 화면의
    값 자리(과제의 done_expect) - 가 양쪽에 다 있는지."""
    problems = []
    ids = set(re.findall(r'\bid="([^"]+)"', html))
    req = flow.get("required_ids")
    if not isinstance(req, list):
        problems.append("required_ids 가 목록이 아니다")
        req = []
    musts = ["phone"] + [sel[1:] for sel, _ in _done_of(done) if sel.startswith("#")]
    for must in musts:
        if must not in req:
            problems.append("required_ids 에 %r 이 없다" % must)
        if must not in ids:
            problems.append("HTML 에 id=%r 요소가 없다" % must)
    missing = [i for i in req if i not in ids]
    if missing:
        problems.append("required_ids 중 HTML 에 없는 id: " + ", ".join(missing))
    return problems


def _check_expect(flow, html, steps, screens, done=None):
    """완료 화면에서 과제의 값(done_expect - 이체는 금액)을 확인할 짝이 있는지.

    완료 화면은 steps 의 마지막 화면이다 - 이름이 "done" 이 아니어도. 전에는
    expect 의 "done" 칸만 보아서, 마지막 화면을 finish 로 지은 설계가
    expect.done 을 적으면 형식 검사를 지나고 검사 B 는 그 칸을 말없이 건너뛰었다.
    같은 이유로 steps 의 방문 이름이 아닌 expect 칸도 문제로 센다 - 검사기는
    그 칸의 값을 보지 않는다."""
    problems = []
    expect = flow.get("expect")
    if not isinstance(expect, dict):
        problems.append("expect 가 객체가 아니다")
        return problems
    visits = visit_keys(steps)
    last = visits[-1] if visits else "done"
    pairs = expect.get(last) or []
    for sel, val in _done_of(done):
        if not any(isinstance(p, list) and len(p) == 2 and p[0] == sel for p in pairs):
            problems.append("expect.%s 에 %s 이 없다"
                            % (last, json.dumps([sel, val], ensure_ascii=False)))
    stray = [k for k in expect if visits and k not in visits]
    if stray:
        problems.append("expect 의 키 %s 는 steps 의 화면이 아니다 - 검사기는 그 값을 "
                        "보지 않는다. 키는 steps 의 screen 이름(같은 화면을 두 번 지나면 "
                        "\"이름#2\")이고, 완료 화면의 값은 마지막 화면(%s) 칸에 적는다 "
                        "(있는 것: %s)" % (", ".join(repr(k) for k in stray), last,
                                         ", ".join(visits)))
    return problems


DONE_ALIAS = "done"


def accept_done_alias(flow):
    """expect 의 "done" 칸을 마지막 화면의 칸으로 옮긴다. 옮겼으면 그 화면 이름을,
    아니면 None 을 돌려준다. 흐름 명세를 제자리에서 바꾼다.

    완료 화면의 칸은 마지막 화면의 이름이다 (_check_expect). 그런데 gpt-6-astra 는
    마지막 화면을 complete 로 지어 놓고 expect 의 키를 "done" 으로 네 번 중 두 번
    적었다 - 원본의 완료 화면 이름이 done 이고, 전의 프롬프트 예시도 done 이었다.
    무엇을 확인할지는 맞게 적었으므로 설계 실패가 아니다.

    그래서 흐름 명세에 "done" 이라는 화면이 **없을 때만** 마지막 화면의 별칭으로
    받는다. done 화면이 있으면 그 칸은 그 화면의 것이므로 건드리지 않는다 -
    그때 칸이 어긋난 것은 _check_expect 가 그대로 문제로 센다. 마지막 화면 칸이
    이미 있으면 거기 없는 짝만 더한다. 받았다는 사실은 부르는 쪽이 남긴다."""
    expect = flow.get("expect")
    if not isinstance(expect, dict) or DONE_ALIAS not in expect:
        return None
    steps = _steps_of(flow)
    named = {st.get("screen") for st in steps if isinstance(st, dict)}
    for e in _error_paths_of(flow):
        named |= {e.get("expect_screen"), e.get("back_to")}
    visits = visit_keys(steps)
    if not visits or DONE_ALIAS in named:
        return None
    last = visits[-1]
    moved = expect.pop(DONE_ALIAS)
    pairs = list(expect.get(last) or [])
    for p in moved if isinstance(moved, list) else []:
        if p not in pairs:
            pairs.append(p)
    expect[last] = pairs
    return last


def _error_paths_of(flow):
    paths = flow.get("error_paths")
    return [e for e in paths if isinstance(e, dict)] if isinstance(paths, list) else []


def _check_coverage(flow, html, steps, screens):
    """HTML 에 있지만 정답 경로도 오류 경로도 지나가지 않는 화면.

    오류를 알리는 화면(팝업 등)은 정답 경로가 지나가지 않는다. 전에는 이
    규칙이 정답 경로만 보았으므로, 오류 화면을 둔 설계는 흐름에 억지 우회
    경로를 넣어야 통과했다."""
    seen = {st.get("screen") for st in steps if isinstance(st, dict)}
    for e in _error_paths_of(flow):
        seen |= {e.get("expect_screen"), e.get("back_to")}
    unseen = screens - seen
    if unseen:
        return ["steps 와 error_paths 가 지나가지 않는 화면: "
                + ", ".join(sorted(unseen))]
    return []


def _check_error_paths(flow, html, steps, screens, required=None):
    """오류 경로의 칸이 걸을 수 있는 모양인지. 무엇이 오류인지는 과제가 정한다
    (`required` - 원본 흐름의 error_paths). 그 정의의 id 가 빠졌거나, 정의가
    정한 틀린 값의 자리표시자(`uses`)를 쓰지 않으면 문제다.

    틀린 값의 실제 값은 여기서도 말하지 않는다 - 모델이 그 값을 알면 "그 값일
    때만 오류를 띄우는" HTML 로 검사 J 를 지날 수 있다. 자리표시자 이름만 쓴다.

    back_to 는 정답 경로에 있는 화면이고 완료 화면이 아니어야 한다 (오류가
    나타난 화면 자신도 된다). 오류가 나타난 화면보다 뒤여도 된다 - 순서로 막던
    전의 규칙은 계좌 화면에서 은행 오류를 알리고 은행 고르기 화면으로 보낸
    gpt-6.1-sol 의 설계를 떨어뜨렸다. 실제로 돌아갈 수 있는지는 검사 J 가 걸어서
    본다 (j_errors.back_to_ok 와 같은 규칙)."""
    problems = []
    paths = _error_paths_of(flow)
    defs = {d["id"]: d for d in required or [] if isinstance(d, dict) and "id" in d}
    have = [e.get("id") for e in paths]
    for rid, d in defs.items():
        if rid not in have:
            problems.append(
                "오류 경로 %s 가 error_paths 에 없다 (%s). 이 오류를 어떻게 알리고 "
                "어디로 되돌아가는지 적어라. 잘못된 입력은 %s 로 넣는다."
                % (rid, d.get("about") or "?",
                   ", ".join("{%s}" % k for k in d.get("uses") or []) or "?"))
    order = step_screens(steps)
    visits = visit_keys(steps)
    done = done_screen(steps)
    for i, e in enumerate(paths):
        eid = e.get("id")
        where = "error_paths[%d] (%s)" % (i, eid or "id 없음")
        if not eid:
            problems.append("%s 에 id 가 없다" % where)
        elif defs and eid not in defs:
            problems.append("%s: 과제의 오류가 아니다 (있는 것: %s)"
                            % (where, ", ".join(defs)))
        if e.get("from_step") not in visits:
            problems.append("%s.from_step=%r 은 steps 의 화면이 아니다 (있는 것: %s)"
                            % (where, e.get("from_step"), ", ".join(visits)))
        exp, back = e.get("expect_screen"), e.get("back_to")
        if exp not in screens:
            problems.append("%s.expect_screen=%r 은 HTML 의 data-screen 에 없다"
                            % (where, exp))
        if back_to_ok(order, back, exp, done):
            pass
        elif back == done:
            problems.append("%s.back_to=%r 은 완료 화면이다. 고칠 수 있는 곳 - "
                            "steps 에 있는 화면 중 완료 화면이 아닌 곳 - 으로 돌아가야 "
                            "한다." % (where, back))
        else:
            problems.append("%s.back_to=%r 은 steps 의 화면도 오류가 나타난 화면도 "
                            "아니다" % (where, back))
        if not e.get("inputs"):
            problems.append("%s.inputs 가 비어 있다. 잘못된 입력을 넣는 동작을 적어라"
                            % where)
        if not e.get("recover") and back != exp:
            problems.append("%s.recover 가 비어 있다. %r 로 되돌아가는 동작을 적어라"
                            % (where, back))
        need = (defs.get(eid) or {}).get("uses") or []
        text = json.dumps(e.get("inputs"), ensure_ascii=False)
        for key in need:
            if "{%s}" % key not in text:
                problems.append("%s.inputs 가 {%s} 를 쓰지 않는다. 잘못된 값은 이 "
                                "자리표시자로만 넣는다." % (where, key))
    return problems


def _check_reveal(flow, html, steps, screens):
    """펼치기 조작(reveal)이 걸을 수 있는 모양인지. 모양(타입)은 shape_problems
    가 먼저 본다.

    선택지 목록의 일부만 먼저 보이고 눌러야 나머지가 만들어지는 설계("자주 쓰는
    은행 먼저 + 전체 보기")는 그 누르는 조작을 여기에 적는다. 검사기는 `at` 까지
    정답 걸음을 밟은 뒤 `do` 의 동작을 하나씩 실행하며 선택지를 모은다
    (drive.walk_reveal). 키는 선택지의 data-action 이다.

    `do` 는 click 만 된다. 펼치기는 사용자가 그 화면에서 버튼을 누르는 일이다 -
    타이핑 · 기다리기 · 되풀이를 허락하면 "검사기만 하는 조작" 으로 목록을 만들어
    검사 I 를 지날 수 있다. 누를 대상이 그 화면에 보이는 data-action 요소인지,
    누른 뒤에도 같은 화면인지는 걸어 봐야 알므로 drive.walk_reveal 이 본다."""
    problems = []
    visits = visit_keys(steps)
    for action, spec in (flow.get("reveal") or {}).items():
        where = "reveal.%s" % action
        if action not in html:
            problems.append("%s: %r 은 HTML 의 data-action 에 없다. 키는 펼친 뒤 "
                            "나타나는 선택지의 data-action 이다." % (where, action))
        if spec.get("at") not in visits:
            problems.append("%s.at=%r 은 steps 의 화면이 아니다 (있는 것: %s)"
                            % (where, spec.get("at"), ", ".join(visits)))
        if not spec.get("do"):
            problems.append("%s.do 가 비어 있다. 목록을 펼치는 조작을 적어라" % where)
        do = spec.get("do")
        for i, act in enumerate(do if isinstance(do, list) else [do]):
            if not (isinstance(act, dict) and set(act) == {"click"}
                    and isinstance(act["click"], str)):
                problems.append("%s.do[%d] 는 click 만 쓸 수 있다 (지금은 %s). 그 화면에 "
                                "보이는 data-action 버튼을 누르는 것만 적는다 - 예: "
                                '{"click": "#show-all"}'
                                % (where, i, json.dumps(act, ensure_ascii=False)[:80]))
    return problems


# 이 순서가 problems 의 순서다.
CHECKS = [_check_steps, _check_handlers, _check_step_screens, _check_transitions,
          _check_omissions, _check_ids, _check_expect, _check_coverage]
# derived_from_original 은 보지 않는다. 판정 입력(audit.inputs.judged_flow)이 모델
# 흐름을 늘 새 설계로 판정하므로, 그 칸 하나로 형식 재시도를 쓰게 할 까닭이 없다.
# 과제의 완료 화면 짝(done_expect)을 함께 받는 검사들.
DONE_CHECKS = (_check_ids, _check_expect)


def validate_flow(flow, html, required_errors=None, done_expect=None):
    """Shape checks the audit would otherwise crash on, phrased for the model.

    타입은 shape_problems 가 먼저 본다. 여기 아래의 검사들은 그 결과를 전제로
    쓰여 있으므로, 타입이 틀렸으면 그 목록만 돌려주고 끝낸다 - 전제가 깨진
    상태로 더 보면 문제를 돌려주는 대신 터진다.

    `required_errors` 는 과제가 정한 오류 경로(원본 흐름의 error_paths)다.
    재구성 루프만 넘긴다. 넘기지 않으면 빠진 오류 경로를 문제로 세지 않는다 -
    오류 경로가 생기기 전의 흐름(Run 1~4)을 다시 볼 때 결과가 같아야 한다.

    `done_expect` 는 과제가 정한 완료 화면의 짝(tasks/<과제>.json)이다. 주지
    않으면 기본 과제(이체)의 것이다."""
    bad_shape = shape_problems(flow)
    if bad_shape:
        return bad_shape
    # literal names only - a template literal like data-screen="${x}" in the
    # script is not a screen
    screens = set(re.findall(r'data-screen="([a-z0-9_-]+)"', html))
    steps = _steps_of(flow)
    done = _done_of(done_expect)
    problems = []
    for check in CHECKS:
        if check in DONE_CHECKS:
            problems += check(flow, html, steps, screens, done)
        else:
            problems += check(flow, html, steps, screens)
    problems += _check_error_paths(flow, html, steps, screens, required_errors)
    problems += _check_reveal(flow, html, steps, screens)
    return problems


# --------------------------------------------------------------------------- #
# 참조 검사 - 도구가 넣어 준 데이터를 읽는가
# --------------------------------------------------------------------------- #
def preserved_problems(html, data):
    """도구가 넣어 줄 선택지 데이터를 스크립트가 읽지 않으면 형식 문제다.

    위의 검사들과 같은 성격이다 - 규칙으로 보고, 브라우저를 띄우지 않고, 메시지가
    그대로 다음 프롬프트로 간다. 읽지 않았다는 것은 모델이 목록을 스스로 지어
    썼다는 뜻이고, 그 답은 검사까지 갈 필요가 없다.

    **주입하기 전** 의 HTML 로 불러야 한다. 도구가 넣는 블록은
    `window.PRESERVED = {...}` 로 쓰므로, 주입한 뒤의 문서로 보면 그 블록 하나가
    늘 있어서 무엇을 보내도 통과한다.

    값을 하나도 빠뜨리지 않고 직접 쓴 목록은 참조를 요구하지 않는다. 그때는
    참조하든 않든 결과가 같은데, 요구하면 숫자판을 마크업에 적은 설계가 그것
    때문에 재시도를 한 번 쓴다 - 이 장치는 재시도를 아끼려고 만든 것이다.
    값이 "있다" 를 보는 눈은 검사 I 와 같은 것을 쓴다 (i_choices.present).
    """
    if not data:
        return []
    read = names_read(html, list(data))
    missed = [n for n, vals in data.items()
              if n not in read and not all(present(v, html) for v in vals)]
    if not missed:
        return []
    return ["재설계 HTML 의 스크립트가 도구가 넣어 주는 선택지 데이터를 읽지 "
            "않는다: %s. 이 데이터는 window.%s.<이름> 으로 들어간다 - 목록을 "
            "직접 쓰지 말고 그 이름을 참조해 그려라 (%s). 몇 개를 어떻게 "
            "보일지는 네가 정하되 모든 값을 고를 수 있어야 한다."
            % (", ".join(missed), GLOBAL_NAME, read_forms(missed[0]))]


def read_forms(name):
    """검사기가 읽기로 세는 모양의 예. 프롬프트와 형식 오류가 같은 글을 쓴다
    (preserve.names_read 가 세는 모양 중 흔한 셋)."""
    return ("`window.{g}.{n}` · `const P = window.{g}; P.{n}` · "
            "`const {{{n}}} = window.{g}` 모두 된다".format(g=GLOBAL_NAME, n=name))


def problems_report(problems):
    """문제 목록을 검사 리포트 모양으로. 흐름 명세가 규격에 안 맞아 검사까지
    가지 못한 시도도 다른 실패와 같은 모양으로 기록된다."""
    return {"passed": False, "warning": [],
            "metrics": {"flow": "auto", "not_audited": True},
            "fatal": [{"check": "FLOW", "screen": None, "detail": d}
                      for d in problems]}


def failure_report(kind, detail):
    """An audit-shaped report for a reply that never reached the audit, so the
    retry block and summary treat it like any other fatal."""
    return {"passed": False,
            "fatal": [{"check": kind, "screen": None, "detail": detail}],
            "warning": [], "metrics": {"flow": "auto", "not_audited": True}}
