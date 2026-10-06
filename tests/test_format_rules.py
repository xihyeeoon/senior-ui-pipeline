r"""형식 검사(restructure/reply.py)와 검사기가 같은 규칙을 쓰는가 (감사 B-10 · B-11).

형식 검사는 검사기에 넣기 전에 "검사기가 그대로 돌면 떨어질 모양" 을 미리 잡는다.
같은 규칙을 두 곳에 따로 쓰면 한쪽만 고쳐지는 순간 둘이 갈라진다 - 형식 검사가
막는 것을 검사기는 받아 주거나, 그 반대가 된다. 10-06 에 back_to 규칙이 두 번
바뀌었고 두 번 다 두 곳을 함께 고쳐야 했다. 그래서 규칙 함수는 검사기 쪽에
하나만 두고 형식 검사는 그것을 가져다 쓴다.

브라우저도 모델도 부르지 않는다.
"""
import itertools

import _api

reply = _api.reply_module
J = _api.j_errors
F = _api.flow_module
H = _api.handlers_module


# --------------------------------------------------------------------- #
# 1. back_to · 화면 이름 목록 · 방문 키 - 검사기의 함수 그대로 (B-10)
# --------------------------------------------------------------------- #
def test_the_format_check_uses_the_auditors_rule_functions():
    """고치기 전: reply.py 가 back_to 규칙(j_errors.back_to_ok), 정답 경로의 화면
    목록(j_errors.step_screens), 방문 이름(flow.visit_keys)을 따로 다시 썼다."""
    assert reply.back_to_ok is J.back_to_ok
    assert reply.step_screens is J.step_screens
    assert reply.visit_keys is F.visit_keys
    assert not hasattr(reply, "_visits")


STEPS = [{"screen": "start"}, {"screen": "account", "click": "#a"},
         {"screen": "bank", "click": "#b"}, {"screen": "account", "click": "#c"},
         {"screen": "done", "click": "#d"}]
HTML = "".join('<div data-screen="%s"></div>' % s
               for s in ("start", "account", "bank", "done", "oops"))


def format_says_ok(exp, back):
    flow = {"steps": STEPS, "error_paths": [
        {"id": "e", "from_step": "account", "inputs": [{"click": "#x"}],
         "expect_screen": exp, "recover": [{"click": "#y"}], "back_to": back}]}
    probs = reply._check_error_paths(flow, HTML, STEPS,
                                     {"start", "account", "bank", "done", "oops"})
    return not [p for p in probs if ".back_to=" in p]


def test_the_format_check_and_check_J_agree_on_every_back_to():
    """오류 화면과 돌아갈 화면의 모든 짝에서 형식 검사와 검사 J 의 판단이 같다."""
    screens = J.step_screens(STEPS)
    done = J.done_screen(STEPS)
    names = ["start", "account", "bank", "done", "oops", "nowhere"]
    for exp, back in itertools.product(names, names):
        assert format_says_ok(exp, back) == J.back_to_ok(screens, back, exp, done), \
            (exp, back)


def test_visit_keys_reads_a_step_without_a_screen():
    """형식 검사는 화면 이름이 빠진 걸음도 센다 (그 문제를 적어야 하므로).
    visit_keys 는 그런 걸음을 None 의 방문으로 센다."""
    assert F.visit_keys([{"screen": "a"}, {"click": "#x"}, "odd", {"screen": "a"}]) == \
        ["a", None, "None#2", "a#2"]


# --------------------------------------------------------------------- #
# 2. 템플릿 data-action="${…}" - 검사 C 와 같이 렌더된 값으로 본다 (B-11)
# --------------------------------------------------------------------- #
KEYPAD = """<html><body><div data-screen="start" id="phone">
<div id="pad"></div><span id="dn-amt"></span></div>
<script>
document.getElementById('pad').innerHTML = [1,2,3].map(v =>
  `<button data-action="${'num'}" data-v="${v}">${v}</button>`).join('');
document.getElementById('pad').innerHTML += `<button data-action="key-${'x'}">x</button>`;
function onClick(el){ const a = el.dataset.action; if (a === 'num') {} }
</script></body></html>"""


def test_a_template_data_action_is_not_a_control_name():
    """원본(original_transfer.html 의 keyButtons)이 이 관용구를 쓴다.

    고치기 전: 형식 검사가 `${'num'}` 을 조작부 이름으로 뽑아 "data-action 이
    있지만 분기가 없는 것: ${'num'}" 형식 실패를 냈다 - 재시도 하나. 검사 C 는
    렌더된 DOM 의 data-action(num)을 보므로 두 판단이 갈렸다."""
    probs = reply._check_handlers({}, KEYPAD, [], set())
    assert probs == [], probs


def test_a_literal_data_action_without_a_branch_is_still_caught():
    html = KEYPAD.replace("</script>", "</script><button data-action=\"gone\">g</button>")
    probs = reply._check_handlers({}, html, [], set())
    assert probs == ["data-action 이 있지만 분기가 없는 것: gone"]


def test_the_literal_names_live_next_to_the_branch_reader():
    """조작부 이름을 읽는 규칙도 처리기 분기를 읽는 규칙과 같은 곳(audit/handlers.py)에
    둔다. 검사 C 는 렌더된 DOM 으로 판정하고, 형식 검사는 이 함수로 미리 본다."""
    assert H.literal_actions(KEYPAD) == set()
    assert H.literal_actions('<b data-action="go"></b><b data-action="a-${x}"></b>') == \
        {"go"}
    assert reply.literal_actions is H.literal_actions


# --------------------------------------------------------------------- #
# 3. 완료 화면의 값 짝은 모델에게 요구하지 않는다 - 판정이 과제에서 읽는다
# --------------------------------------------------------------------- #
from test_restructure_bugs import GOOD_FLOW, GOOD_HTML  # noqa: E402


def done_expect(task):
    return _api.load_task(task)["done_expect"]


def test_the_format_check_does_not_ask_for_the_done_pairs():
    """고치기 전: 완료 화면 칸에 과제의 짝(`["#dn-amt", "{AMOUNT_SHOWN}"]`)이 없으면
    형식 문제("expect.done 에 … 이 없다")였다 - 재시도 하나. 판정은 이제 모델의
    expect 가 아니라 과제의 done_expect 로 한다 (judged_flow, 16e0880). 이 요구는
    판정을 바꾸지 않고 재시도만 쓴다."""
    for expect in ({}, {"done": []}, {"done": [["#dn-amt", ""]]},
                   {"done": [["#note", "{NAME}"]]}):
        flow = dict(GOOD_FLOW, expect=expect)
        probs = reply.validate_flow(flow, GOOD_HTML, [], done_expect("transfer"))
        assert probs == [], (expect, probs)


def test_a_stray_expect_key_is_still_a_problem():
    """steps 의 방문 이름이 아닌 칸은 검사기가 보지 않는다 - 그것은 그대로 알린다."""
    flow = dict(GOOD_FLOW, expect={"nowhere": [["#x", "1"]]})
    probs = reply.validate_flow(flow, GOOD_HTML, [], done_expect("transfer"))
    assert len(probs) == 1 and "expect 의 키 'nowhere'" in probs[0]


def test_the_prompt_no_longer_asks_for_the_done_pairs():
    """프롬프트(과제 파일의 flow_done · flow_example)도 그 짝을 적으라고 하지 않는다."""
    import json
    for task in ("transfer", "bill"):
        p = _api.load_task(task)["prompt"]
        done = "\n".join(p["flow_done"])
        for sel, val in done_expect(task):
            assert '["%s", "%s"]' % (sel, val) not in done, task
        example = json.loads("\n".join(p["flow_example"]))
        sels = {sel for sel, _ in done_expect(task)}
        assert not [pair for pairs in example.get("expect", {}).values()
                    for pair in pairs if pair[0] in sels], task
        assert "done_amount" not in example, task
