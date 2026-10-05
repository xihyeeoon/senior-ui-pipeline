r"""진단·계획 단계의 답을 읽고, 규칙으로 모양을 본다.

재구성을 한 번에 받으면 모델이 무엇을 보고 무엇을 바꿨는지가 HTML 안에 묻힌다.
그래서 첫 호출은 HTML 을 만들지 않고 진단과 계획만 JSON 으로 받는다
(docs/restructure-prompt.md 의 PLAN_PROMPT). 그 JSON 이 실행 폴더에 남는
"판단의 기록" 이고, 디자이너에게 넘기는 변경 설명서의 재료다.

여기 있는 검사는 reply.py 의 흐름 명세 검사와 같은 성격이다 - 규칙으로 보고,
브라우저를 띄우지 않고, 메시지가 그대로 다음 프롬프트로 간다.

계획 JSON 안의 선택지 목록은 막지 않는다. 데이터를 지키는 곳은 생성 단계의 참조
검사와 검사 I 다. 계획이 "어떤 목록을 어떻게 보일지" 를 말하는 것은 정상이다.
"""
import json
import re

from .reply import FENCE, type_of

# data-screen 이름. 템플릿 리터럴(data-screen="${x}")은 화면이 아니므로 글자
# 그대로 적힌 것만 센다 - reply.validate_flow 와 같은 규칙이다.
SCREEN_ATTR = re.compile(r'data-screen="([a-z0-9_-]+)"')
SCREEN_NAME = re.compile(r"^[a-z][a-z0-9_-]*$")
DIAG_ID = re.compile(r"^D\d+$")
CHANGE_ID = re.compile(r"^C\d+$")

DIAG_KEYS = ("id", "screen", "element", "problem", "evidence")
SCREEN_KEYS = ("name", "purpose", "from")
CHANGE_KEYS = ("id", "what", "why", "addresses", "from_screens", "to_screens")
# 오류를 어떻게 보일지. id 는 과제가 정한 오류(원본 흐름의 error_paths)다.
ERROR_KEYS = ("id", "screen", "how", "back_to")


class PlanProblems(ValueError):
    """진단·계획 답을 쓸 수 없다. 문제 목록이 그대로 다음 프롬프트로 간다."""

    def __init__(self, problems):
        ValueError.__init__(self, " | ".join(problems))
        self.problems = list(problems)


def screens_in(html):
    """HTML 의 data-screen 이름들. 처음 나온 순서로, 겹치지 않게."""
    seen = []
    for name in SCREEN_ATTR.findall(html or ""):
        if name not in seen:
            seen.append(name)
    return seen


def _json_text(text):
    """답에서 JSON 을 꺼낸다. 코드 블록이 있으면 그것이고, 없으면 답 전체다 -
    "블록 하나만" 이라고 해도 블록 없이 JSON 만 보내는 답이 있다."""
    blocks = [body for kind, body in FENCE.findall(text or "") if kind == "json"]
    return blocks[0] if blocks else (text or "").strip()


def parse_plan(text, original_screens, error_ids=None):
    """`(diagnosis, plan)`. 쓸 수 없으면 PlanProblems.

    `error_ids` 는 과제가 정한 오류다. 주면 계획이 오류마다 어떻게 보일지
    (`plan.errors`) 를 적어야 한다."""
    try:
        data = json.loads(_json_text(text))
    except json.JSONDecodeError as e:
        raise PlanProblems(["답이 JSON 으로 읽히지 않는다: %s. ```json 블록 하나만 "
                            "출력하라." % e])
    if not isinstance(data, dict):
        raise PlanProblems(["최상위가 객체가 아니다 (지금은 %s). diagnosis 와 plan "
                            "을 가진 객체 하나여야 한다." % type_of(data)])
    diagnosis, plan = data.get("diagnosis"), data.get("plan")
    problems = plan_problems(diagnosis, plan, original_screens,
                             error_ids=error_ids)
    if problems:
        raise PlanProblems(problems)
    return diagnosis, plan


def _items(problems, where, value, keys, allow_empty=False):
    """목록이고, 원소가 객체이고, 필요한 키가 있는지. 쓸 수 있는 원소만 돌려준다."""
    if not isinstance(value, list) or not (value or allow_empty):
        problems.append("%s 가 비어 있지 않은 목록이 아니다 (지금은 %s)"
                        % (where, type_of(value)))
        return []
    good = []
    for i, it in enumerate(value):
        if not isinstance(it, dict):
            problems.append("%s[%d] 가 객체가 아니다 (지금은 %s)"
                            % (where, i, type_of(it)))
            continue
        missing = [k for k in keys if k not in it]
        if missing:
            problems.append("%s[%d] 에 %s 가 없다" % (where, i, ", ".join(missing)))
            continue
        good.append(it)
    return good


def _names(problems, where, value):
    """문자열 목록인지. 아니면 문제를 적고 빈 목록."""
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        problems.append("%s 는 문자열 목록이어야 한다 (지금은 %s)"
                        % (where, type_of(value)))
        return []
    return value


def _unique_ids(problems, where, items, pattern, form):
    ids = []
    for i, it in enumerate(items):
        v = it.get("id")
        if not isinstance(v, str) or not pattern.match(v):
            problems.append("%s[%d].id=%r 은 %s 꼴이 아니다" % (where, i, v, form))
        elif v in ids:
            problems.append("%s 의 id %s 가 겹친다" % (where, v))
        else:
            ids.append(v)
    return ids


def plan_problems(diagnosis, plan, original_screens, revised=False,
                  error_ids=None):
    """진단·계획의 모양과, 서로 가리키는 이름이 실제로 있는지.

    어느 진단에도 대응하지 않는 변경, 대응이 없는 진단은 문제로 세지 않는다 -
    설계 판단이지 형식이 아니다. 기록에는 그대로 남는다.

    revised 는 반성으로 고친 계획이다. 처음 세운 계획은 변경이 하나는 있어야
    하지만, 반성이 변경을 모두 거둬들이는 것은 막지 않는다.

    error_ids 는 과제가 정한 오류다. 주면 `plan.errors` 가 오류마다 하나씩 -
    어느 화면에서(`screen`) 어떻게(`how`) 알리고 어디로 돌아가는지(`back_to`) -
    있어야 한다. 두 화면 이름은 plan.screens 의 것이다. 주지 않아도
    `plan.errors` 가 있으면 화면 이름은 본다.
    """
    problems = []
    orig = set(original_screens)
    diags = _items(problems, "diagnosis", diagnosis, DIAG_KEYS)
    diag_ids = _unique_ids(problems, "diagnosis", diags, DIAG_ID, "D숫자")
    for i, d in enumerate(diags):
        if orig and d.get("screen") not in orig:
            problems.append("diagnosis[%d].screen=%r 은 원본의 화면이 아니다 "
                            "(원본: %s)" % (i, d.get("screen"), ", ".join(original_screens)))

    if not isinstance(plan, dict):
        problems.append("plan 이 객체가 아니다 (지금은 %s). screens 와 changes 를 "
                        "가진 객체여야 한다." % type_of(plan))
        return problems
    screens = _items(problems, "plan.screens", plan.get("screens"), SCREEN_KEYS)
    names = []
    for i, sc in enumerate(screens):
        name = sc.get("name")
        if not isinstance(name, str) or not SCREEN_NAME.match(name):
            problems.append("plan.screens[%d].name=%r 은 영문 소문자 이름이 아니다 "
                            "(숫자·-·_ 가능, 글자로 시작)" % (i, name))
        elif name in names:
            problems.append("plan.screens 에 %s 가 두 번 있다" % name)
        else:
            names.append(name)
        bad = [s for s in _names(problems, "plan.screens[%d].from" % i, sc.get("from"))
               if orig and s not in orig]
        if bad:
            problems.append("plan.screens[%d].from 의 %s 는 원본의 화면이 아니다 "
                            "(원본: %s)" % (i, ", ".join(bad), ", ".join(original_screens)))

    changes = _items(problems, "plan.changes", plan.get("changes"), CHANGE_KEYS,
                     allow_empty=revised)
    _unique_ids(problems, "plan.changes", changes, CHANGE_ID, "C숫자")
    for i, c in enumerate(changes):
        where = "plan.changes[%d]" % i
        bad = [x for x in _names(problems, where + ".addresses", c.get("addresses"))
               if x not in diag_ids]
        if bad:
            problems.append("%s.addresses 의 %s 는 diagnosis 에 없는 id 다"
                            % (where, ", ".join(bad)))
        bad = [x for x in _names(problems, where + ".from_screens", c.get("from_screens"))
               if orig and x not in orig]
        if bad:
            problems.append("%s.from_screens 의 %s 는 원본의 화면이 아니다"
                            % (where, ", ".join(bad)))
        bad = [x for x in _names(problems, where + ".to_screens", c.get("to_screens"))
               if x not in names]
        if bad:
            problems.append("%s.to_screens 의 %s 는 plan.screens 에 없다"
                            % (where, ", ".join(bad)))
    problems += _error_problems(plan, names, error_ids)
    return problems


def _error_problems(plan, names, error_ids):
    """plan.errors 의 모양. 과제의 오류가 모두 있고, 화면 이름이 계획에 있는지."""
    problems = []
    errs = plan.get("errors")
    if not error_ids and errs is None:
        return problems
    items = _items(problems, "plan.errors", errs, ERROR_KEYS,
                   allow_empty=not error_ids)
    have = [e.get("id") for e in items]
    for eid in error_ids or []:
        if eid not in have:
            problems.append("plan.errors 에 오류 %s 가 없다. 이 오류를 어느 화면에서 "
                            "어떻게 알리고 어디로 돌아가게 할지 적어라." % eid)
    for i, e in enumerate(items):
        where = "plan.errors[%d]" % i
        if error_ids and e.get("id") not in error_ids:
            problems.append("%s.id=%r 은 과제의 오류가 아니다 (있는 것: %s)"
                            % (where, e.get("id"), ", ".join(error_ids)))
        for key in ("screen", "back_to"):
            if e.get(key) not in names:
                problems.append("%s.%s=%r 은 plan.screens 에 없다"
                                % (where, key, e.get(key)))
    return problems


def match_problems(plan, html):
    """계획의 화면과 생성된 HTML 의 화면이 같은지. 어긋나면 형식 문제다.

    계획을 따로 받는 이유는 "무엇을 바꿨는가" 의 기록이다. 생성물이 계획과
    다른 화면을 가지면 그 기록이 생성물을 설명하지 못한다 - 설명서의 화면
    대응표가 없는 화면을 가리키게 된다. 그래서 검사기에 넣기 전에 막는다.

    고치는 길은 둘이다 - HTML 을 계획에 맞추거나, 재시도의 반성에서 계획을
    바꾸거나. 메시지는 둘 다 적는다.
    """
    planned = [sc.get("name") for sc in (plan or {}).get("screens") or []]
    built = screens_in(html)
    extra = [s for s in built if s not in planned]
    missing = [s for s in planned if s not in built]
    problems = []
    if extra:
        problems.append(
            "계획에 없는 화면이 HTML 에 있다: %s. 계획의 화면은 %s 이다. data-screen "
            "이름을 계획과 같게 하거나, 계획을 바꿔야 한다면 반성의 plan_changes 에 "
            "적어라." % (", ".join(extra), ", ".join(planned)))
    if missing:
        problems.append(
            "계획에 있는 화면이 HTML 에 없다: %s. 계획의 모든 화면을 "
            '<section class="screen" data-screen="이름"> 으로 만들거나, 계획을 '
            "바꿔야 한다면 반성의 plan_changes 에 적어라." % ", ".join(missing))
    return problems


# --------------------------------------------------------------------------- #
# 반성 (재시도 때만)
# --------------------------------------------------------------------------- #
# 재시도 답은 ```json(반성) → ```html → ```json(흐름 명세) 순서다. 반성은 "왜
# 떨어졌는가" 와 "그래서 계획의 무엇을 바꾸는가" 의 기록이고, 계획을 바꾸는
# 유일한 길이다 - 생성 답이 말없이 계획과 다른 화면을 만들면 일치 검사에서
# 떨어진다.
OPS = ("add", "change", "remove")


def parse_reflection(text):
    """`(반성, 문제들)`. 반성 블록이 없으면 `(None, [])`.

    반성은 `cause` 를 가진 첫 json 블록이다. 흐름 명세는 마지막 json 블록이므로
    (reply.parse_reply) 둘이 섞이지 않는다.
    """
    for kind, body in FENCE.findall(text or ""):
        if kind != "json":
            continue
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "cause" in data:
            return data, reflection_problems(data)
    return None, []


def reflection_problems(refl):
    problems = []
    if not isinstance(refl.get("cause"), str) or not refl["cause"].strip():
        problems.append("반성의 cause 가 비어 있다. 실패의 원인을 한 문장으로 적어라.")
    changes = refl.get("plan_changes", [])
    if not isinstance(changes, list):
        problems.append("반성의 plan_changes 가 목록이 아니다 (지금은 %s). 바꿀 것이 "
                        "없으면 [] 로 둔다." % type_of(changes))
    if not isinstance(refl.get("keep", []), list):
        problems.append("반성의 keep 이 목록이 아니다 (지금은 %s)"
                        % type_of(refl.get("keep")))
    return problems


def _find(items, key, value):
    for i, it in enumerate(items):
        if it.get(key) == value:
            return i
    return None


def apply_changes(plan, diagnosis, changes, original_screens):
    """반성의 plan_changes 를 계획에 적용한다. `(새 계획, 문제들)`.

    받은 계획은 고치지 않는다 - 시도마다 따른 계획이 파일로 남아야 하므로,
    앞 시도의 계획이 뒤에서 바뀌면 기록이 거짓이 된다. 하나라도 적용하지 못하면
    문제를 돌려주고, 부르는 쪽은 계획을 바꾸지 않는다.

        change + C번호         그 변경의 칸을 new 로 고친다
        remove + C번호         그 변경을 뺀다
        add    + change        new 가 새 변경 하나
        add    + screen        new 가 새 화면 하나 (after 가 있으면 그 화면 뒤)
        change + screen:이름   그 화면의 칸을 new 로 고친다
        remove + screen:이름   그 화면을 뺀다
        change + error:id      그 오류를 보이는 방법(plan.errors)을 고친다

    오류는 더하거나 뺄 수 없다 - 무엇이 오류인지는 과제가 정한다.
    """
    new = json.loads(json.dumps(plan))
    screens, items = new.setdefault("screens", []), new.setdefault("changes", [])
    problems = []
    for i, ch in enumerate(changes or []):
        where = "plan_changes[%d]" % i
        if not isinstance(ch, dict):
            problems.append("%s 가 객체가 아니다" % where)
            continue
        op, target, body = ch.get("op"), ch.get("target"), ch.get("new")
        if op not in OPS:
            problems.append("%s.op=%r 은 add · change · remove 중 하나가 아니다"
                            % (where, op))
            continue
        if not isinstance(target, str):
            problems.append("%s.target 이 문자열이 아니다" % where)
            continue
        if op != "remove" and not isinstance(body, dict):
            problems.append("%s.new 가 객체가 아니다 (%s 에는 new 가 필요하다)"
                            % (where, op))
            continue
        if op == "add" and target == "change":
            items.append(body)
        elif op == "add" and target == "screen":
            after = ch.get("after")
            at = _find(screens, "name", after) if after else None
            if after and at is None:
                problems.append("%s.after=%r 은 계획에 없는 화면이다" % (where, after))
                continue
            screens.insert(len(screens) if at is None else at + 1, body)
        elif target.startswith("screen:"):
            at = _find(screens, "name", target[len("screen:"):])
            if at is None:
                problems.append("%s.target=%r - 계획에 그런 화면이 없다" % (where, target))
            elif op == "remove":
                screens.pop(at)
            elif op == "change":
                screens[at].update(body)
            else:
                problems.append("%s: 화면을 더할 때는 target 을 \"screen\" 으로 쓴다"
                                % where)
        elif target.startswith("error:"):
            errs = new.setdefault("errors", [])
            at = _find(errs, "id", target[len("error:"):])
            if at is None:
                problems.append("%s.target=%r - 계획에 그런 오류가 없다" % (where, target))
            elif op == "change":
                body.pop("id", None)
                errs[at].update(body)
            else:
                problems.append("%s: 오류는 change 로 고치기만 한다 - 더하거나 뺄 수 "
                                "없다" % where)
        elif CHANGE_ID.match(target):
            at = _find(items, "id", target)
            if at is None:
                problems.append("%s.target=%s - 계획에 그런 변경이 없다" % (where, target))
            elif op == "remove":
                items.pop(at)
            elif op == "change":
                items[at].update(body)
            else:
                problems.append("%s: 변경을 더할 때는 target 을 \"change\" 로 쓴다"
                                % where)
        else:
            problems.append("%s.target=%r 은 C번호 · change · screen · screen:이름 · "
                            "error:id 중 하나가 아니다" % (where, target))
    if problems:
        return plan, problems
    # 고치기 전의 계획이 가졌던 오류는 고친 뒤에도 모두 있어야 한다.
    ids = [e.get("id") for e in plan.get("errors") or [] if isinstance(e, dict)]
    after = plan_problems(diagnosis, new, original_screens, revised=True,
                          error_ids=ids or None)
    if after:
        return plan, ["반성의 plan_changes 를 적용한 계획이 맞지 않는다: " + p
                      for p in after]
    return new, []


def plan_report(problems):
    """계획을 세우지 못한 시도도 다른 실패와 같은 리포트 모양으로 남긴다."""
    return {"passed": False, "warning": [],
            "metrics": {"flow": "auto", "not_audited": True},
            "fatal": [{"check": "PLAN", "screen": None, "detail": d}
                      for d in problems]}


def unaddressed(diagnosis, plan):
    """어느 변경도 대응하지 않는 진단 id. 형식 문제가 아니라 기록할 사실이다."""
    used = {a for c in (plan or {}).get("changes") or [] for a in c.get("addresses") or []}
    return [d["id"] for d in diagnosis or [] if d.get("id") not in used]
