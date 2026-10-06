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

