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


def parse_plan(text, original_screens):
    """`(diagnosis, plan)`. 쓸 수 없으면 PlanProblems."""
    try:
        data = json.loads(_json_text(text))
    except json.JSONDecodeError as e:
        raise PlanProblems(["답이 JSON 으로 읽히지 않는다: %s. ```json 블록 하나만 "
                            "출력하라." % e])
    if not isinstance(data, dict):
        raise PlanProblems(["최상위가 객체가 아니다 (지금은 %s). diagnosis 와 plan "
                            "을 가진 객체 하나여야 한다." % type_of(data)])
    diagnosis, plan = data.get("diagnosis"), data.get("plan")
    problems = plan_problems(diagnosis, plan, original_screens)
    if problems:
        raise PlanProblems(problems)
    return diagnosis, plan


def _items(problems, where, value, keys):
    """목록이고, 원소가 객체이고, 필요한 키가 있는지. 쓸 수 있는 원소만 돌려준다."""
    if not isinstance(value, list) or not value:
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


def plan_problems(diagnosis, plan, original_screens):
    """진단·계획의 모양과, 서로 가리키는 이름이 실제로 있는지.

    어느 진단에도 대응하지 않는 변경, 대응이 없는 진단은 문제로 세지 않는다 -
    설계 판단이지 형식이 아니다. 기록에는 그대로 남는다.
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

    changes = _items(problems, "plan.changes", plan.get("changes"), CHANGE_KEYS)
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
    return problems


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
