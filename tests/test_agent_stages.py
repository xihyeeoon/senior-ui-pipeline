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


# ===================================================================== #
# 6. 반성 (재시도 때만)
# ===================================================================== #
def reflection(changes=(), cause="처리기가 선언하지 않은 이름을 읽었다", keep=("C1",)):
    return {"cause": cause, "plan_changes": list(changes), "keep": list(keep)}


def retry_text(refl, html=GOOD_HTML, flow=GOOD_FLOW):
    """반성 → html → 흐름 명세 순서의 답."""
    head = ("```json\n%s\n```\n\n" % json.dumps(refl, ensure_ascii=False)) \
        if refl is not None else ""
    return head + reply_text(html, flow)


def answers(*texts):
    """생성 호출에 차례로 답한다 (진단·계획은 run_loop 가 답한다)."""
    seq = list(texts)

    def call(*a, **kw):
        text = seq.pop(0) if len(seq) > 1 else seq[0]
        return {"text": text, "finish_reason": "stop", "seconds": 0.0, "usage": None}
    return call


def audit_fails_then_passes(fake_run_env):
    reports = [failing_report(), passing_report()]
    fake_run_env.setattr(loop, "run_audit",
                         lambda *a, **kw: reports.pop(0) if len(reports) > 1
                         else reports[0])


def test_the_reflection_request_is_a_blank_form():
    values = _example_values(_api.prompt_module.reflection_request())
    assert values
    assert all(v.startswith("<") and v.endswith(">") for v in values), values


def test_only_the_retry_prompt_asks_for_a_reflection(fake_run_env, out_root):
    fake_run_env.setattr(loop, "run_audit", lambda *a, **kw: failing_report())
    run_loop(fake_run_env, out_root, always_reply, attempts=2)
    first, second = prompts_of(out_root)
    assert "반성" not in first
    assert "반성 먼저" in second
    # 반성 요청은 실패 목록보다 앞이다 - 코드보다 반성을 먼저 쓰게 한다
    assert second.index("반성 먼저") < second.index("이전 시도의 실패")


def test_the_reflection_is_saved(fake_run_env, out_root):
    audit_fails_then_passes(fake_run_env)
    _code, summary = run_loop(fake_run_env, out_root,
                              answers(GOOD_REPLY, retry_text(reflection())),
                              attempts=2)
    d = last_run(out_root)
    assert read_json(os.path.join(d, "attempt_2.reflection.json")) == reflection()
    assert summary["attempts"][1]["reflection"].endswith("attempt_2.reflection.json")
    assert summary["passed"] is True


def test_a_plan_change_in_the_reflection_updates_the_plan(fake_run_env, out_root):
    """반성이 화면을 더하면 그 화면을 가진 HTML 이 일치 검사를 지난다."""
    audit_fails_then_passes(fake_run_env)
    add = {"op": "add", "target": "screen", "after": "start",
           "new": {"name": "middle", "purpose": "가운데", "from": []},
           "why": "한 화면에 한 가지 일만"}
    html = GOOD_HTML.replace('<div data-screen="done">',
                             '<div data-screen="middle"></div><div data-screen="done">')
    flow = json.loads(json.dumps(GOOD_FLOW))
    flow["steps"].insert(1, {"screen": "middle", "click": "[data-action='go']"})
    _code, summary = run_loop(fake_run_env, out_root,
                              answers(GOOD_REPLY, retry_text(reflection([add]), html, flow)),
                              attempts=2)
    d = last_run(out_root)
    names = [s["name"] for s in read_json(os.path.join(d, "attempt_2.plan.json"))["screens"]]
    assert names == ["start", "middle", "done"]
    assert read_json(os.path.join(d, "attempt_1.plan.json")) == GOOD_PLAN
    assert summary["attempts"][1]["stage"] == "audit"
    assert summary["attempts"][1]["plan_changes"] == 1
    assert summary["final"]["plan"].endswith("attempt_2.plan.json")


def test_a_plan_change_that_cannot_apply_is_a_format_failure(fake_run_env, out_root):
    fake_run_env.setattr(loop, "run_audit", lambda *a, **kw: failing_report())
    bad = {"op": "change", "target": "C9", "new": {"what": "x"}, "why": "y"}
    _code, summary = run_loop(fake_run_env, out_root,
                              answers(GOOD_REPLY, retry_text(reflection([bad]))),
                              attempts=3)
    assert summary["attempts"][1]["stage"] == "flow"
    d = last_run(out_root)
    assert read_json(os.path.join(d, "attempt_2.plan.json")) == GOOD_PLAN
    assert "C9" in prompts_of(out_root)[2]


def test_a_missing_reflection_is_recorded_not_failed(fake_run_env, out_root):
    """반성이 없다고 재시도 한 번을 버리지는 않는다. 없다는 사실은 남긴다."""
    audit_fails_then_passes(fake_run_env)
    _code, summary = run_loop(fake_run_env, out_root,
                              answers(GOOD_REPLY, retry_text(None)), attempts=2)
    assert summary["passed"] is True
    assert summary["attempts"][1]["reflection"] is None
    assert summary["attempts"][1]["reflection_missing"] is True


@pytest.mark.parametrize("change,want", [
    ({"op": "change", "target": "C1", "new": {"what": "더 키운다"}, "why": "-"},
     lambda p: p["changes"][0]["what"] == "더 키운다"),
    ({"op": "remove", "target": "C1", "why": "-"},
     lambda p: p["changes"] == []),
    ({"op": "add", "target": "change", "why": "-",
      "new": {"id": "C2", "what": "a", "why": "b", "addresses": ["D1"],
              "from_screens": ["done"], "to_screens": ["done"]}},
     lambda p: [c["id"] for c in p["changes"]] == ["C1", "C2"]),
    ({"op": "add", "target": "screen", "why": "-",
      "new": {"name": "tail", "purpose": "끝 다음", "from": []}},
     lambda p: [s["name"] for s in p["screens"]] == ["start", "done", "tail"]),
    ({"op": "change", "target": "screen:done", "new": {"purpose": "완료"}, "why": "-"},
     lambda p: p["screens"][1]["purpose"] == "완료"),
    ({"op": "remove", "target": "screen:done", "why": "-"},
     lambda p: [s["name"] for s in p["screens"]] == ["start"]),
])
def test_plan_changes_apply(change, want):
    new, problems = plan_mod.apply_changes(GOOD_PLAN, GOOD_DIAGNOSIS, [change], ORIGINAL)
    assert problems == []
    assert want(new)
    assert [s["name"] for s in GOOD_PLAN["screens"]] == ["start", "done"]   # 원본 그대로


@pytest.mark.parametrize("change,needle", [
    ({"op": "change", "target": "C9", "new": {}, "why": "-"}, "C9"),
    ({"op": "rename", "target": "C1", "why": "-"}, "op"),
    ({"op": "remove", "target": "screen:ghost", "why": "-"}, "ghost"),
    ({"op": "remove", "target": "screen:start", "why": "-"}, "to_screens"),
])
def test_plan_changes_that_cannot_apply_say_why(change, needle):
    _new, problems = plan_mod.apply_changes(GOOD_PLAN, GOOD_DIAGNOSIS, [change], ORIGINAL)
    assert any(needle in p for p in problems), problems


def test_the_mock_retry_answer_starts_with_a_reflection():
    text = model.mock_reply("fail", reflect=True)["text"]
    refl, problems = plan_mod.parse_reflection(text)
    assert problems == [] and refl["plan_changes"] == []
    html, _flow, _t = _api.parse_reply(text)            # 흐름은 여전히 마지막 json
    assert "<html" in html.lower()


# ===================================================================== #
# 7. 실행 기록 - 커밋 · 작업 트리 · 토큰
# ===================================================================== #
CLEAN = {"commit": "a" * 40, "branch": "feat/x", "dirty": False, "dirty_files": []}
DIRTY = {"commit": "b" * 40, "branch": "feat/x", "dirty": True,
         "dirty_files": ["senior_ui/restructure/loop.py"]}


def run_log(summary):
    return io.open(os.path.join(summary["run_dir"], "run.log"),
                   encoding="utf-8").read().splitlines()


def test_git_state_reads_this_repo():
    got = loop.git_state()
    assert re.match(r"^[0-9a-f]{40}$", got["commit"])
    assert isinstance(got["dirty"], bool)
    assert isinstance(got["dirty_files"], list)


def test_the_summary_records_the_commit_and_a_clean_tree(fake_run_env, out_root):
    fake_run_env.setattr(loop, "git_state", lambda: dict(CLEAN))
    _code, summary = run_loop(fake_run_env, out_root, always_reply, attempts=1)
    assert summary["git"] == CLEAN
    assert "경고" not in run_log(summary)[0]


def test_a_dirty_tree_is_warned_on_the_first_line_and_still_runs(fake_run_env, out_root):
    """자동 실행 7회가 모두 커밋되지 않은 코드에서 돌아 조건을 되짚을 수 없었다."""
    fake_run_env.setattr(loop, "git_state", lambda: dict(DIRTY))
    code, summary = run_loop(fake_run_env, out_root, always_reply, attempts=1)
    first = run_log(summary)[0]
    assert "경고" in first and "깨끗하지 않다" in first and "b" * 7 in first
    assert summary["git"]["dirty"] is True
    assert summary["passed"] is True and code == 0


def test_no_git_is_recorded_as_unknown(monkeypatch):
    def boom(*a, **kw):
        raise OSError("git 없음")
    monkeypatch.setattr(loop.subprocess, "run", boom)
    got = loop.git_state()
    assert got["commit"] is None and got["dirty"] is None


def test_tokens_are_estimated_with_tiktoken():
    n, method = model.estimate_tokens("이체 과업을 끝낼 수 있도록 다시 설계하라")
    assert n > 0 and method.startswith("tiktoken")


def test_without_tiktoken_the_estimate_falls_back_to_characters(monkeypatch):
    monkeypatch.setattr(model, "_encoder", lambda: None)
    n, method = model.estimate_tokens("가" * 290)
    assert n == 100 and method.startswith("chars")


def usage_reply(prompt_tokens, completion_tokens):
    def call(model_, prompt, *a, **kw):
        if is_plan_prompt(prompt):
            text, u = GOOD_PLAN_REPLY, {"prompt": 900, "completion": 100}
        else:
            text, u = GOOD_REPLY, {"prompt": prompt_tokens,
                                   "completion": completion_tokens}
        return {"text": text, "finish_reason": "stop", "seconds": 0.0, "usage": u}
    return call


def test_the_summary_records_tokens_by_stage(fake_run_env, out_root):
    reports = [failing_report(), passing_report()]
    fake_run_env.setattr(loop, "run_audit", lambda *a, **kw: reports.pop(0))
    _code, summary = run_loop(fake_run_env, out_root, usage_reply(1000, 300),
                              plan_reply=False, attempts=2)
    t = summary["tokens"]
    assert set(t["by_stage"]) == {"plan", "generate", "retry"}
    assert t["by_stage"]["plan"]["prompt"] == 900
    assert t["by_stage"]["generate"]["completion"] == 300
    assert t["by_stage"]["retry"]["calls"] == 1
    assert all(s["estimated_prompt"] > 0 for s in t["by_stage"].values())
    assert t["total"]["prompt"] == 900 + 1000 + 1000
    # 첫 시도 = 진단·계획 + 생성
    first = t["first_attempt"]
    assert first["prompt"] == 1900 and first["completion"] == 400
    assert first["estimated_prompt"] == (t["by_stage"]["plan"]["estimated_prompt"]
                                         + t["by_stage"]["generate"]["estimated_prompt"])


def test_every_call_logs_its_estimate_before_it_is_sent(fake_run_env, out_root):
    _code, summary = run_loop(fake_run_env, out_root, always_reply, attempts=1,
                              max_tokens=14000, plan_max_tokens=6000)
    lines = [l for l in run_log(summary) if "tokens:" in l]
    assert any("plan" in l and "6000" in l for l in lines)
    assert any("generate" in l and "14000" in l for l in lines)
    assert summary["attempts"][0]["calls"][0]["stage"] == "plan"


def test_mock_usage_stays_unknown_not_zero(fake_run_env, out_root):
    _code, summary = run_loop(fake_run_env, out_root, always_reply, attempts=1)
    assert summary["tokens"]["by_stage"]["generate"]["prompt"] is None


def test_the_loop_waits_between_the_two_calls(fake_run_env, out_root):
    slept = []
    fake_run_env.setattr(loop.time, "sleep", slept.append)
    run_loop(fake_run_env, out_root, always_reply, attempts=1, delay=60)
    assert slept == [60]


def test_the_new_defaults():
    args = _api.restructure_parser().parse_args([])
    assert args.delay == 60
    assert args.max_tokens == 14000
    assert args.plan_max_tokens == 6000


# ===================================================================== #
# 8. 분당 한도 (429) - 재시도 프롬프트가 커서 생긴다
# ===================================================================== #
def fake_openai(monkeypatch, outcomes):
    """openai.OpenAI 를 바꿔 끼운다. outcomes 의 각 항목은 429 의 문구이거나
    "ok". 보낸 max_completion_tokens 를 차례로 돌려준다."""
    import openai
    sent = []

    def make_429(msg):
        e = openai.RateLimitError.__new__(openai.RateLimitError)
        Exception.__init__(e, msg)
        return e

    class Resp:
        def __init__(self):
            msg = type("M", (), {"content": GOOD_REPLY})()
            self.choices = [type("C", (), {"message": msg, "finish_reason": "stop"})()]
            self.usage = type("U", (), {"prompt_tokens": 25000,
                                        "completion_tokens": 3000})()
            self.model, self.system_fingerprint = "gpt-4o-x", "fp"

    class Completions:
        def create(self, **kw):
            sent.append(kw["max_completion_tokens"])
            out = outcomes.pop(0)
            if out != "ok":
                raise make_429(out)
            return Resp()

    class Client:
        def __init__(self):
            self.chat = type("Ch", (), {"completions": Completions()})()

    monkeypatch.setattr(openai, "OpenAI", Client)
    return sent


TOO_LARGE = ("Error code: 429 - Request too large for gpt-4o in organization org-x "
             "on tokens per min (TPM): Limit 30000, Requested 40000. The input or "
             "output tokens must be reduced in order to run successfully.")
BUSY = ("Error code: 429 - Rate limit reached for gpt-4o on tokens per min (TPM): "
        "Limit 30000, Used 25000, Requested 14000. Please try again in 18s.")


def test_a_busy_minute_is_waited_out_not_counted(monkeypatch):
    """보통의 429 는 기다렸다 다시 보낸다. 시도 실패가 아니다."""
    slept = []
    monkeypatch.setattr(model.time, "sleep", slept.append)
    sent = fake_openai(monkeypatch, [BUSY, BUSY, "ok"])
    reply = model.call_model("gpt-4o", "p", 14000, backoff=(20, 45, 90))
    assert reply["text"] == GOOD_REPLY
    assert slept == [20, 45]
    assert sent == [14000, 14000, 14000]


def test_a_request_too_large_for_the_minute_shrinks_its_cap(monkeypatch):
    """프롬프트 + max_tokens 가 분당 한도 하나를 넘으면 기다려도 풀리지 않는다.
    재시도는 입력이 2만~2만 6천이라 14,000 을 더하면 그렇게 된다."""
    slept, lines = [], []
    monkeypatch.setattr(model.time, "sleep", slept.append)
    sent = fake_openai(monkeypatch,
                       [TOO_LARGE.replace("Requested 40000", "Requested 38000"), "ok"])
    reply = model.call_model("gpt-4o", "p", 14000, log=lines.append,
                             backoff=(20, 45))
    assert reply["text"] == GOOD_REPLY
    assert slept == []                                   # 기다리지 않았다
    assert sent == [14000, 14000 - 8000 - model.MARGIN]
    assert reply["max_tokens"] == sent[1]
    assert any("분당 한도" in l for l in lines)


def test_a_request_that_cannot_fit_at_all_stops_at_once(monkeypatch):
    slept = []
    monkeypatch.setattr(model.time, "sleep", slept.append)
    huge = TOO_LARGE.replace("Requested 40000", "Requested 50000")
    fake_openai(monkeypatch, [huge])
    with pytest.raises(model.RateLimited) as e:
        model.call_model("gpt-4o", "p", 14000, backoff=(20, 45, 90, 180))
    assert slept == []
    assert "분당 한도" in str(e.value)


def test_a_rate_limit_on_a_retry_does_not_spend_the_budget(fake_run_env, out_root):
    """재시도에서 429 로 멈춰도 설계 실패로 세지 않는다 - 예산은 그대로, 종료 2."""
    fake_run_env.setattr(loop, "run_audit", lambda *a, **kw: failing_report())
    calls = []

    def call(*a, **kw):
        calls.append(1)
        if len(calls) == 1:
            return always_reply()
        raise model.RateLimited("429 Too Many Requests")

    code, summary = run_loop(fake_run_env, out_root, call, attempts=3)
    assert summary["stopped_reason"] == "rate_limit" and code == 2
    assert summary["budget"]["audit_used"] == 1           # 첫 시도의 검사 실패뿐
    assert summary["budget"]["format_used"] == 0
    assert summary["attempts"][-1]["stage"] == "rate_limit"


# ===================================================================== #
# 9. 디자이너용 설명서
# ===================================================================== #
brief = _api.brief_module

BRIEF_PLAN = {
    "screens": [{"name": "start", "purpose": "시작", "from": ["home"]},
                {"name": "pick", "purpose": "은행 고르기", "from": ["bank", "account"]},
                {"name": "check", "purpose": "새로 넣은 확인", "from": []},
                {"name": "done", "purpose": "끝", "from": ["done"]}],
    "changes": [{"id": "C1", "what": "버튼을 키운다", "why": "찾게",
                 "addresses": ["D1"], "from_screens": ["home"], "to_screens": ["start"]},
                {"id": "C2", "what": "확인 화면을 더한다", "why": "잘못 보내지 않게",
                 "addresses": [], "from_screens": [], "to_screens": ["check"]}]}
BRIEF_DIAG = [{"id": "D1", "screen": "home", "element": "이체 버튼",
               "problem": "작아서 못 찾는다", "evidence": "카드 안의 작은 버튼"}]
BRIEF_REPORT = {
    "passed": True, "fatal": [],
    "warning": [{"check": "F", "screen": "start", "detail": "영어 낱말 LTE"},
                {"check": "I", "screen": None,
                 "detail": "원본의 pick-bank 선택지 67개 중 63개는 … 고를 수 없었다"}],
    "metrics": {"choice_values_kept": {"pick-bank": 67, "num": 11},
                "choice_values_selectable": {"pick-bank": 4, "num": 11},
                "choice_values_removed_by_design": {
                    "quick": {"values": ["all"], "reason": "전액은 실수가 크다"}}}}


def render(tmp_path, **kw):
    shots = tmp_path / "shots" / "attempt_2"
    shots.mkdir(parents=True)
    (shots / "audit_start.png").write_bytes(b"png")
    (shots / "audit_pick.png").write_bytes(b"png")
    args = dict(run_name="20261005-120000", attempt=2, plan=BRIEF_PLAN,
                diagnosis=BRIEF_DIAG, report=BRIEF_REPORT,
                original_screens=ORIGINAL, shots_dir=str(shots),
                brief_dir=str(tmp_path), preserved={"BANKS": 38, "SECS": 29},
                redeclared=[], model_html=None, git=CLEAN, reflections=[])
    args.update(kw)
    return brief.render_brief(**args)


def section(md, title):
    """'## title' 부터 다음 '## ' 앞까지."""
    start = md.index("## " + title)
    nxt = md.find("\n## ", start + 3)
    return md[start: nxt if nxt >= 0 else len(md)]


def test_the_brief_maps_every_original_screen(tmp_path):
    md = section(render(tmp_path), "화면 대응")
    assert "| bank | pick |" in md and "| account | pick |" in md
    assert "| home | start |" in md
    assert "recipient" in md and "없어짐" in md             # 계획이 쓰지 않은 원본 화면
    assert "| (새 화면) | check |" in md


def test_the_brief_lists_changes_with_the_diagnosis_they_answer(tmp_path):
    md = section(render(tmp_path), "변경 목록")
    assert "C1" in md and "버튼을 키운다" in md and "찾게" in md
    assert "D1" in md and "작아서 못 찾는다" in md
    assert "C2" in md and "대응하는 진단 없음" in md


def test_the_brief_links_the_screenshots_the_checker_took(tmp_path):
    md = section(render(tmp_path), "화면별 스크린샷")
    assert "(shots/attempt_2/audit_start.png)" in md
    assert "(shots/attempt_2/audit_pick.png)" in md
    assert "check" in md and "스크린샷 없음" in md


def test_the_brief_lists_what_a_person_must_check(tmp_path):
    md = section(render(tmp_path), "사람이 확인할 것")
    assert "영어 낱말 LTE" in md
    assert "pick-bank" in md and "67" in md and "4" in md   # kept / selectable 차이
    assert "| num |" not in md                               # 차이 없는 것은 빼고
    assert "quick" in md and "전액은 실수가 크다" in md       # 실제로 쓰인 허용 제거
    assert "도구가 고친 것: 없음" in md


def test_the_brief_says_when_the_tool_rewrote_the_models_list(tmp_path):
    md = render(tmp_path, redeclared=["BANKS"],
                model_html=str(tmp_path / "restructured_auto.model.html"))
    part = section(md, "사람이 확인할 것")
    assert "BANKS" in part and "restructured_auto.model.html" in part


def test_the_brief_names_where_the_choice_data_comes_from(tmp_path):
    md = render(tmp_path)
    assert "window.PRESERVED" in md and "BANKS 38" in md


def test_the_brief_shows_the_reflections_when_the_plan_moved(tmp_path):
    md = render(tmp_path, reflections=[{"attempt": 2, "cause": "선택자가 없다",
                                        "plan_changes": 1}])
    assert "선택자가 없다" in md


def test_the_brief_records_a_dirty_tree(tmp_path):
    md = render(tmp_path, git=DIRTY)
    assert "깨끗하지 않" in md


def shooting_audit(*a, **kw):
    """검사기 대역. 받은 스크린샷 폴더에 start 화면 한 장을 찍는다."""
    shots = a[5]
    io.open(os.path.join(shots, "audit_start.png"), "wb").write(b"png")
    return passing_report()


def test_a_passing_run_writes_the_brief(fake_run_env, out_root):
    fake_run_env.setattr(loop, "run_audit", shooting_audit)
    _code, summary = run_loop(fake_run_env, out_root, always_reply, attempts=1)
    d = last_run(out_root)
    md = io.open(os.path.join(d, "designer_brief.md"), encoding="utf-8").read()
    assert "(shots/attempt_1/audit_start.png)" in md
    assert summary["final"]["brief"].endswith("designer_brief.md")
    # 승격된 사본은 outputs/ 에서 열어도 링크가 맞는다
    promoted = io.open(os.path.join(out_root, "restructured_auto.designer_brief.md"),
                       encoding="utf-8").read()
    name = os.path.basename(d)
    assert "(restructure_auto/%s/shots/attempt_1/audit_start.png)" % name in promoted


def test_a_failed_run_writes_no_brief(fake_run_env, out_root):
    fake_run_env.setattr(loop, "run_audit", lambda *a, **kw: failing_report())
    run_loop(fake_run_env, out_root, always_reply, attempts=1)
    assert not os.path.exists(os.path.join(last_run(out_root), "designer_brief.md"))


# ===================================================================== #
# 10. 대시보드 "변경 추적" - plan.json 이 있는 빌드
# ===================================================================== #
def test_the_index_attaches_a_build_s_plan(out_root):
    rel = os.path.relpath(out_root, ROOT).replace(os.sep, "/")
    base = os.path.join(out_root, "restructured_auto")
    io.open(base + ".html", "w", encoding="utf-8").write("<html></html>")
    json.dump(GOOD_PLAN, io.open(base + ".plan.json", "w", encoding="utf-8"))
    json.dump(GOOD_DIAGNOSIS, io.open(base + ".diagnosis.json", "w", encoding="utf-8"))
    got = _api.index_plan_of(rel + "/restructured_auto.html")
    assert got["plan"] == GOOD_PLAN and got["diagnosis"] == GOOD_DIAGNOSIS
    assert got["path"] == rel + "/restructured_auto.plan.json"


def test_a_build_without_a_plan_has_none(out_root):
    rel = os.path.relpath(out_root, ROOT).replace(os.sep, "/")
    assert _api.index_plan_of(rel + "/nothing.html") is None


def test_the_prompt_does_not_suggest_features_the_original_lacks():
    """원본에 없는 기능(은행 추정)을 프롬프트가 먼저 제안하면 모델은 원본에
    없는 번호→은행 표를 지어낸다 - 손수 Run 1~3 의 케이뱅크가 그렇게 생겼다.
    원본에 있는 조회(예금주)는 원본이 보여 주는 값으로만 흉내 낸다."""
    for t in (_api.load_template(), _api.load_plan_template()):
        assert "은행 추정" not in t
    assert "원본에 있는 동작만, 원본이 보여 주는 값으로 흉내 낸다" in _api.load_template()
