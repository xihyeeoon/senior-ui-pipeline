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
