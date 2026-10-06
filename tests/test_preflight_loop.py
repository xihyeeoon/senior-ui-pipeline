r"""최신 모델로 처음 돌린 두 실행에서 나온 형식 검사의 거짓 실패.

gpt-6.1-sol (outputs/restructure_auto/20261006-124055) 과 gpt-6-astra
(20261006-124838) 의 실제 답을 tests/fixtures/real_runs/ 에 그대로 복사해
두고, 그 답을 형식 검사에 다시 넣는다. 두 실행 모두 설계와 상관없는 형식
실패로 시도를 썼다 - 여기 있는 것은 그 실패가 검사기 쪽 잘못이었는지 본다.

모델도 브라우저도 부르지 않는다.
"""
import io
import json
import os

import _api

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL = os.path.join(ROOT, "tests", "fixtures", "real_runs")

reply = _api.reply_module
preserve = _api.preserve_module


def real(model, n):
    """그 실행의 n 번째 답 (HTML, 흐름 명세)."""
    path = os.path.join(REAL, model, "attempt_%d.response.txt" % n)
    html, flow, _text = _api.parse_reply(io.open(path, encoding="utf-8").read())
    return html, flow


def real_data(model):
    """그 실행에서 도구가 넣어 준 선택지 데이터 (attempt_1.html 의 블록)."""
    return json.load(io.open(os.path.join(REAL, model, "preserved.json"),
                             encoding="utf-8"))


# --------------------------------------------------------------------- #
# 1. 선택지 참조 검사 - 별칭으로 읽은 것도 읽은 것이다
# --------------------------------------------------------------------- #
def test_both_real_first_attempts_read_the_data_through_an_alias():
    """두 모델의 첫 시도는 `const P = window.PRESERVED;` 로 받아 `P.BANKS` 로
    읽었다. 전에는 "선택지 데이터를 읽지 않는다" 로 떨어졌다."""
    for model in ("sol", "astra"):
        html, _flow = real(model, 1)
        assert "const P" in html and "window.PRESERVED;" in html.replace(" ", "")
        data = real_data(model)
        assert preserve.names_read(html, list(data)) == list(data), model
        assert _api.preserved_problems(html, data) == [], model


def test_common_alias_forms_count_as_reading():
    data = {"BANKS": ["가", "나"], "SECS": ["다", "라"]}
    forms = [
        "const P = window.PRESERVED; P.BANKS.map(f); P['SECS'].map(f);",
        "let D = PRESERVED || {}; draw(D.BANKS); draw(D[\"SECS\"]);",
        "const {BANKS, SECS: s} = window.PRESERVED;",
        "const P = window.PRESERVED; const {BANKS, ...rest} = P; rest.SECS;",
        "window.PRESERVED?.BANKS; PRESERVED?.['SECS'];",
        "var P = window['PRESERVED']; P.BANKS; P.SECS;",
    ]
    for js in forms:
        html = "<html><body><script>%s</script></body></html>" % js
        assert _api.preserved_problems(html, data) == [], js


def test_writing_the_list_without_reading_the_data_still_fails():
    """별칭을 인정해도, 목록을 직접 쓰고 전역을 읽지 않는 답은 그대로 떨어진다.
    이름만 같은 다른 변수(`X.BANKS`, `obj.P.SECS`)도 읽은 것이 아니다."""
    data = {"BANKS": ["가", "나", "다"], "SECS": ["라", "마"]}
    for js in ["const BANKS = ['가','나']; BANKS.map(f);",
               "const P = other; P.BANKS; X.BANKS; obj.P.SECS;",
               "const {BANKS} = somethingElse;"]:
        html = "<html><body><script>%s</script></body></html>" % js
        probs = _api.preserved_problems(html, data)
        assert len(probs) == 1 and "BANKS" in probs[0], js


def test_the_preserved_none_mock_still_fails_the_format_check():
    """6-2 의 preserved-none - 은행 네 개를 직접 쓰고 PRESERVED 를 읽지 않는다."""
    html = _api.model_module.mock_build("preserved-none")
    probs = _api.preserved_problems(html, real_data("sol"))
    assert len(probs) == 1
    assert "BANKS" in probs[0].split(".")[0]


def test_the_message_and_the_prompt_show_the_accepted_forms():
    """기술 계약이므로 인정되는 모양을 예로 적는다 - 형식 오류와 프롬프트가 같은
    글을 쓴다."""
    probs = _api.preserved_problems("<html><script>1;</script></html>",
                                    {"BANKS": ["가", "나"]})
    assert "const P = window.PRESERVED; P.BANKS" in probs[0]
    assert "const {BANKS} = window.PRESERVED" in probs[0]
    snap = {"screens": {"s": {"choices": {"pick": ["가", "나", "다"]}}}}
    html = ("<html><body><script>const BANKS = ['가','나','다'];"
            "draw(BANKS, 'pick');</script></body></html>")
    block = _api.choices_block(snap, html)
    assert "const P = window.PRESERVED; P.BANKS" in block


# --------------------------------------------------------------------- #
# 2. 완료 화면 키 - 마지막 화면의 이름
# --------------------------------------------------------------------- #
loop = _api.loop_module
DONE_PROBLEM = "expect 의 키 'done' 는 steps 의 화면이 아니다"


def make_run(out_root):
    """check_reply 하나만 보는 Run. 로그는 리스트에 쌓인다."""
    import argparse
    args = argparse.Namespace(
        attempts=2, format_attempts=None, audit_attempts=None, infra_attempts=3,
        model="test-model", max_tokens=1000, mock=None, temperature=0.0,
        seed=20260101, original=None, stage="wireframe", delay=0)
    lines = []
    r = loop.Run(args, lines.append, str(out_root), "test-model", "T", "<html></html>")
    r.log_lines = lines
    return r


def test_astra_wrote_done_for_a_last_screen_named_complete():
    """astra 의 1·3 번째 답은 마지막 화면을 complete 로 지어 놓고 expect 의 키를
    done 으로 적었다. 받아들이기 전에는 형식 문제였다."""
    for n in (1, 3):
        html, flow = real("astra", n)
        assert flow["steps"][-1]["screen"] == "complete"
        assert list(flow["expect"]) == ["done"]
        assert any(DONE_PROBLEM in p for p in _api.validate_flow(flow, html))
        assert reply.accept_done_alias(flow) == "complete"
        assert flow["expect"] == {"complete": [["#dn-amt", "{AMOUNT_SHOWN}"]]}
        probs = _api.validate_flow(flow, html)
        assert not any("expect" in p for p in probs), probs


def test_done_is_left_alone_when_the_flow_has_a_done_screen():
    """sol 의 마지막 화면은 정말 done 이다 - 그 칸은 그 화면의 것이다."""
    _html, flow = real("sol", 1)
    before = json.dumps(flow, sort_keys=True)
    assert reply.accept_done_alias(flow) is None
    assert json.dumps(flow, sort_keys=True) == before


def test_done_screen_used_only_by_an_error_path_blocks_the_alias():
    flow = {"steps": [{"screen": "a"}, {"screen": "b", "click": "#x"}],
            "expect": {"done": [["#dn-amt", "{AMOUNT_SHOWN}"]]},
            "error_paths": [{"id": "e", "expect_screen": "done", "back_to": "a"}]}
    assert reply.accept_done_alias(flow) is None
    assert "done" in flow["expect"]


def test_done_pairs_join_an_existing_last_screen_entry():
    flow = {"steps": [{"screen": "a"}, {"screen": "fin", "click": "#x"}],
            "expect": {"fin": [["#x", "1"]],
                       "done": [["#x", "1"], ["#dn-amt", "{AMOUNT_SHOWN}"]]}}
    assert reply.accept_done_alias(flow) == "fin"
    assert flow["expect"] == {"fin": [["#x", "1"], ["#dn-amt", "{AMOUNT_SHOWN}"]]}


def test_the_loop_records_that_it_took_done_as_the_last_screen(tmp_path):
    """받아들였다는 사실은 run.log 와 시도 기록에 남고, 검사기가 여는 흐름
    명세에는 마지막 화면의 칸으로 적힌다."""
    r = make_run(tmp_path)
    text = io.open(os.path.join(REAL, "astra", "attempt_3.response.txt"),
                   encoding="utf-8").read()
    entry = {}
    build, _outcome = loop.check_reply(r, str(tmp_path / "attempt_3"), entry,
                                       {"text": text, "finish_reason": "stop"})
    assert entry["done_alias"] == "complete"
    assert any("'done'" in l and "'complete'" in l for l in r.log_lines)
    saved = json.load(io.open(build["flow_path"], encoding="utf-8"))
    assert "done" not in saved["expect"] and "complete" in saved["expect"]
    assert not any("expect" in p for p in build["problems"]), build["problems"]


def test_the_prompt_examples_no_longer_name_the_last_screen_done():
    """예시의 마지막 화면이 done 이면 모델은 그것을 고정된 키로 읽는다. 완료
    화면의 키가 마지막 화면의 이름이라는 것을 글로도 적는다."""
    for task in ("transfer", "bill"):
        p = _api.load_task(task)["prompt"]
        example = json.loads("\n".join(p["flow_example"]).replace("\"...\"", "\"x\""))
        assert example["steps"][-1]["screen"] != "done"
        assert list(example["expect"]) == [example["steps"][-1]["screen"]]
        assert "마지막 화면의 이름" in "\n".join(p["flow_done"])
        assert "`done`" not in "\n".join(p["flow_done"])


# --------------------------------------------------------------------- #
# 3. 오류 경로 back_to - 정답 경로의 화면이고 완료 화면이 아니면 된다
# --------------------------------------------------------------------- #
def test_both_real_first_attempts_send_the_bank_error_to_the_bank_screen():
    """sol 은 계좌 화면(account)에서 은행 오류를 알리고 뒤의 bank 로, astra 는
    recipient-details 에서 알리고 뒤의 bank-select 로 보냈다. 전의 규칙("오류가
    나타난 화면이거나 그보다 앞")으로는 둘 다 형식 문제였다."""
    for model, back in (("sol", "bank"), ("astra", "bank-select")):
        html, flow = real(model, 1)
        wb = [e for e in flow["error_paths"] if e["id"] == "wrong-bank"][0]
        assert wb["back_to"] == back
        order = [s["screen"] for s in flow["steps"]]
        assert order.index(back) > order.index(wb["expect_screen"])
        probs = _api.validate_flow(flow, html)
        assert not any("back_to" in p for p in probs), (model, probs)
