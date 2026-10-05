r"""재구성 루프를 진단 → 계획 → 생성 → 검사 → 반성으로 나눈 것의 테스트.

API 도 브라우저도 쓰지 않는다. 루프를 서버 없이 돌리는 도구(fake_run_env ·
run_loop)는 test_restructure_bugs.py 의 것을 그대로 쓴다 - 두 파일이 각자 만들면
"루프를 어떻게 돌리는가" 가 갈라진다.

이 파일이 지키는 것은 "에이전트가 무엇을 근거로 무엇을 바꿨는지가 파일로
남는다" 는 것이다.
"""
import io
import json
import os
import re

import pytest

import _api
from test_restructure_bugs import (GOOD_DIAGNOSIS, GOOD_FLOW, GOOD_HTML, GOOD_PLAN,
                                   GOOD_PLAN_REPLY, GOOD_REPLY, ROOT, always_reply,
                                   failing_report, fake_run_env, is_plan_prompt,
                                   out_root, passing_report, prompts_of, reply_text,
                                   run_dirs, run_loop)

loop = _api.loop_module
plan_mod = _api.plan_module
model = _api.model_module

__all__ = ["fake_run_env", "out_root"]          # pytest 가 fixture 로 찾는다

ORIGINAL = ["home", "recipient", "account", "bank", "amount", "confirm",
            "password", "done"]


def plan_json(diagnosis=None, plan=None):
    return json.dumps({"diagnosis": GOOD_DIAGNOSIS if diagnosis is None else diagnosis,
                       "plan": GOOD_PLAN if plan is None else plan},
                      ensure_ascii=False)


def problems_of(diagnosis=None, plan=None):
    try:
        plan_mod.parse_plan(plan_json(diagnosis, plan), ORIGINAL)
    except plan_mod.PlanProblems as e:
        return e.problems
    return []


def last_run(out_root):
    return run_dirs(out_root)[-1]


def read_json(path):
    return json.load(io.open(path, encoding="utf-8"))


# ===================================================================== #
# 1. 진단·계획 답 읽기 (규칙, 브라우저 없음)
# ===================================================================== #
def test_a_good_plan_is_read_with_or_without_a_fence():
    d, p = plan_mod.parse_plan(GOOD_PLAN_REPLY, ORIGINAL)
    assert d == GOOD_DIAGNOSIS and p == GOOD_PLAN
    d, p = plan_mod.parse_plan(plan_json(), ORIGINAL)
    assert p == GOOD_PLAN


def test_text_that_is_not_json_is_a_plan_problem():
    with pytest.raises(plan_mod.PlanProblems) as e:
        plan_mod.parse_plan("진단은 이렇습니다 …", ORIGINAL)
    assert "JSON" in e.value.problems[0]


@pytest.mark.parametrize("change,needle", [
    (lambda d, p: d[0].update(id="X1"), "D숫자"),
    (lambda d, p: d.append(dict(d[0])), "겹친다"),
    (lambda d, p: d[0].pop("evidence"), "evidence"),
    (lambda d, p: d[0].update(screen="nowhere"), "원본의 화면이 아니다"),
    (lambda d, p: p["screens"][0].update(name="Start"), "영문 소문자"),
    (lambda d, p: p["screens"][0].update(**{"from": ["nowhere"]}), "원본의 화면이 아니다"),
    (lambda d, p: p["changes"][0].update(addresses=["D9"]), "diagnosis 에 없는 id"),
    (lambda d, p: p["changes"][0].update(to_screens=["ghost"]), "plan.screens 에 없다"),
    (lambda d, p: p["changes"][0].update(from_screens="home"), "문자열 목록"),
    (lambda d, p: p.update(screens=[]), "비어 있지 않은 목록"),
])
def test_plan_problems_name_what_is_wrong(change, needle):
    d, p = json.loads(json.dumps(GOOD_DIAGNOSIS)), json.loads(json.dumps(GOOD_PLAN))
    change(d, p)
    got = problems_of(d, p)
    assert any(needle in x for x in got), got


def test_choice_values_inside_the_plan_are_not_blocked():
    """데이터를 지키는 곳은 생성 단계의 참조 검사와 검사 I 다. 계획이 목록을
    어떻게 보일지 말하는 것은 정상이다."""
    p = json.loads(json.dumps(GOOD_PLAN))
    p["changes"][0]["what"] = "신한, 국민, 카카오뱅크, 농협, 우리, 하나 를 먼저 보인다"
    assert problems_of(None, p) == []


def test_an_unaddressed_diagnosis_is_recorded_not_rejected():
    d = GOOD_DIAGNOSIS + [{"id": "D2", "screen": "bank", "element": "x",
                           "problem": "y", "evidence": "z"}]
    assert problems_of(d, None) == []
    assert plan_mod.unaddressed(d, GOOD_PLAN) == ["D2"]


# ===================================================================== #
# 2. 프롬프트
# ===================================================================== #
def test_the_task_is_written_once_and_both_prompts_use_it():
    """과제를 바꾸는 날 한 곳만 고치게 한다."""
    doc = io.open(os.path.join(ROOT, "docs", "restructure-prompt.md"),
                  encoding="utf-8").read()
    task = _api.prompt_module.load_block("TASK", doc).strip()
    assert doc.count(task) == 1
    assert task in _api.load_template()
    assert task in _api.load_plan_template()
    assert "{{TASK}}" not in _api.load_template()
    assert "{{TASK}}" not in _api.load_plan_template()


def _example_values(template):
    """프롬프트 안 JSON 예시의 문자열 값들 (id 제외)."""
    block = re.search(r"```json\n(.*?)\n```", template, re.S).group(1)
    out = []

    def walk(v, key=None):
        if isinstance(v, dict):
            for k, x in v.items():
                walk(x, k)
        elif isinstance(v, list):
            for x in v:
                walk(x, key)
        elif isinstance(v, str) and key != "id":
            out.append(v)
    walk(json.loads(block))
    return out


def test_the_plan_example_is_a_blank_form_not_a_design_idea():
    """예시에 구체적인 아이디어를 쓰면 모델이 그것을 베낀다. 칸 모양만 보인다."""
    values = _example_values(_api.load_plan_template())
    assert values
    assert all(v.startswith("<") and v.endswith(">") for v in values), values


def test_the_plan_prompt_has_every_slot_filled():
    t = _api.load_plan_template()
    for slot in ("{{ORIGINAL_HTML}}", "{{RETRY_BLOCK}}", "{{CHOICES}}",
                 "{{ORIGINAL_SCREENS}}"):
        assert slot in t
    got = _api.build_plan_prompt(t, "<html>원본</html>", "선택지", ORIGINAL)
    assert "{{" not in got
    assert "home, recipient" in got


def test_the_generation_prompt_carries_the_plan():
    got = _api.build_prompt(_api.load_template(), "<html></html>", "", "",
                            json.dumps(GOOD_PLAN, ensure_ascii=False))
    assert "{{PLAN}}" not in got
    assert '"버튼을 키운다"' in got
    assert "계획에 없는 큰 변경" in got


# ===================================================================== #
# 3. 루프 - 진단·계획 단계
# ===================================================================== #
def test_the_first_attempt_leaves_its_diagnosis_and_plan(fake_run_env, out_root):
    _code, summary = run_loop(fake_run_env, out_root, always_reply, attempts=1)
    d = last_run(out_root)
    assert read_json(os.path.join(d, "attempt_1.diagnosis.json")) == GOOD_DIAGNOSIS
    assert read_json(os.path.join(d, "attempt_1.plan.json")) == GOOD_PLAN
    assert os.path.exists(os.path.join(d, "attempt_1.plan_prompt.txt"))
    assert os.path.exists(os.path.join(d, "attempt_1.plan_response.txt"))
    assert summary["plan"]["screens"] == ["start", "done"]
    assert summary["final"]["plan"].endswith("attempt_1.plan.json")
    assert summary["final"]["diagnosis"].endswith("attempt_1.diagnosis.json")


def test_the_plan_is_asked_once_per_run(fake_run_env, out_root):
    """재시도마다 계획을 새로 세우지 않는다 - 바뀌는 것은 반성으로 남긴다."""
    seen = []

    def call(model_, prompt, *a, **kw):
        seen.append("plan" if is_plan_prompt(prompt) else "gen")
        if is_plan_prompt(prompt):
            return {"text": GOOD_PLAN_REPLY, "finish_reason": "stop",
                    "seconds": 0.0, "usage": None}
        return always_reply()

    fake_run_env.setattr(loop, "run_audit", lambda *a, **kw: failing_report())
    _code, summary = run_loop(fake_run_env, out_root, call, plan_reply=False,
                              attempts=2)
    assert seen == ["plan", "gen", "gen"]
    d = last_run(out_root)
    assert os.path.exists(os.path.join(d, "attempt_2.plan.json"))
    assert not os.path.exists(os.path.join(d, "attempt_2.diagnosis.json"))


def test_an_unusable_plan_is_a_format_failure(fake_run_env, out_root):
    """생성 호출까지 가지 않고, 형식 예산을 쓰고, 다음 계획 프롬프트에 이유가 간다."""
    seen = []
    answers = ["계획은 이렇습니다", GOOD_PLAN_REPLY]

    def call(model_, prompt, *a, **kw):
        seen.append(prompt)
        if is_plan_prompt(prompt):
            return {"text": answers.pop(0), "finish_reason": "stop",
                    "seconds": 0.0, "usage": None}
        return always_reply()

    _code, summary = run_loop(fake_run_env, out_root, call, plan_reply=False,
                              attempts=2)
    assert summary["attempts"][0]["stage"] == "plan"
    assert summary["budget"]["format_used"] == 1
    assert [is_plan_prompt(p) for p in seen] == [True, True, False]
    assert "직전 답의 문제" in seen[1]
    assert summary["passed"] is True
    report = read_json(os.path.join(last_run(out_root), "attempt_1.audit.json"))
    assert report["fatal"][0]["check"] == "PLAN"


def test_a_plan_that_never_comes_ends_the_run(fake_run_env, out_root):
    def call(*a, **kw):
        return {"text": "JSON 아님", "finish_reason": "stop", "seconds": 0.0,
                "usage": None}
    code, summary = run_loop(fake_run_env, out_root, call, plan_reply=False,
                             attempts=2)
    assert [a["stage"] for a in summary["attempts"]] == ["plan", "plan"]
    assert summary["passed"] is False and code == 1


def test_a_rejected_plan_call_stops_like_any_other_call(fake_run_env, out_root):
    def call(*a, **kw):
        raise model.ApiRejected("AuthenticationError: invalid api key")
    code, summary = run_loop(fake_run_env, out_root, call, plan_reply=False,
                             attempts=3)
    assert summary["stopped_reason"] == "api_rejected" and code == 2


def test_the_plan_call_has_its_own_token_cap(fake_run_env, out_root):
    caps = []

    def call(model_, prompt, max_tokens, *a, **kw):
        caps.append(("plan" if is_plan_prompt(prompt) else "gen", max_tokens))
        if is_plan_prompt(prompt):
            return {"text": GOOD_PLAN_REPLY, "finish_reason": "stop",
                    "seconds": 0.0, "usage": None}
        return always_reply()

    run_loop(fake_run_env, out_root, call, plan_reply=False, attempts=1,
             plan_max_tokens=6000, max_tokens=14000)
    assert caps == [("plan", 6000), ("gen", 14000)]


def test_a_passing_build_promotes_its_plan_and_diagnosis(fake_run_env, out_root):
    run_loop(fake_run_env, out_root, always_reply, attempts=1)
    assert read_json(os.path.join(out_root, "restructured_auto.plan.json")) == GOOD_PLAN
    assert read_json(os.path.join(out_root, "restructured_auto.diagnosis.json")) \
        == GOOD_DIAGNOSIS


# ===================================================================== #
# 4. mock
# ===================================================================== #
@pytest.mark.parametrize("mode", model.MODES)
def test_every_mock_mode_has_a_plan_that_fits_its_build(mode):
    reply = model.mock_plan_reply(mode)
    _d, p = plan_mod.parse_plan(reply["text"], ORIGINAL)
    built = plan_mod.screens_in(model.mock_build(mode))
    assert sorted(sc["name"] for sc in p["screens"]) == sorted(built)


# ===================================================================== #
# 5. 계획-결과 일치 검사 (규칙, 브라우저 없음)
# ===================================================================== #
def html_with(*screens):
    return "".join('<section data-screen="%s"></section>' % s for s in screens)


def test_a_build_that_matches_its_plan_has_no_problems():
    assert plan_mod.match_problems(GOOD_PLAN, html_with("start", "done")) == []


def test_a_screen_the_plan_does_not_have_is_a_problem():
    got = plan_mod.match_problems(GOOD_PLAN, html_with("start", "extra", "done"))
    assert len(got) == 1 and "extra" in got[0] and "계획에 없는" in got[0]


def test_a_planned_screen_the_build_lacks_is_a_problem():
    got = plan_mod.match_problems(GOOD_PLAN, html_with("start"))
    assert len(got) == 1 and "done" in got[0]


def test_a_renamed_screen_names_both_sides():
    got = " ".join(plan_mod.match_problems(GOOD_PLAN, html_with("begin", "done")))
    assert "begin" in got and "start" in got


MISMATCHED_HTML = GOOD_HTML.replace('data-screen="start"', 'data-screen="begin"')
MISMATCHED_FLOW = json.loads(json.dumps(GOOD_FLOW).replace('"start"', '"begin"'))


def test_a_build_off_its_plan_is_a_format_failure(fake_run_env, out_root):
    """흐름 명세는 맞지만 화면 이름이 계획과 다르다 - 검사기까지 가지 않는다."""
    audits = []

    def spy(*a, **kw):
        audits.append(1)
        return passing_report()

    fake_run_env.setattr(loop, "run_audit", spy)

    def call(*a, **kw):
        return {"text": reply_text(MISMATCHED_HTML, MISMATCHED_FLOW),
                "finish_reason": "stop", "seconds": 0.0, "usage": None}

    _code, summary = run_loop(fake_run_env, out_root, call, attempts=2)
    assert audits == []
    assert summary["attempts"][0]["stage"] == "flow"
    assert summary["budget"]["format_used"] >= 1
    second = prompts_of(out_root)[1]
    assert "begin" in second and "계획" in second
