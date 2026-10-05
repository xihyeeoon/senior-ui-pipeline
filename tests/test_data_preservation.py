r"""입력이 가진 선택지 데이터를 도구가 지키는 장치의 재현 테스트.

브라우저도 API 도 쓰지 않는다. 자동 Run 4·5 에서 LLM 은 원본의 선택지 67개를
3~9개로 줄여 썼고, 프롬프트에 "하나도 빠뜨리지 마라" 를 넣어도 9번 시도 모두
4개였다 (docs/variance-notes.md). 말로 지시하는 방법은 효과가 없었으므로, 이
장치는 데이터를 도구가 들고 있다 - 모델은 그것을 참조해 그린다.

세 부분이다.

  뽑기   입력 HTML 의 스크립트 배열에서 선택지 데이터를 이름과 원소로 꺼낸다
  넣기   재설계 HTML 에 도구가 데이터 블록을 넣는다
  검사   재설계 HTML 의 스크립트가 그 데이터를 실제로 읽는지 본다 (형식 검사)

은행·이체에 묶인 이름은 테스트에서도 쓰지 않는다 - 합성 입력으로도 같은 결과가
나와야 한다 (test_extraction_works_on_any_input).
"""
import io
import json
import os
import re

import pytest

import _api

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIGINAL = os.path.join(ROOT, "inputs", "original_transfer.html")

preserve = _api.preserve_module


def original_html():
    return io.open(ORIGINAL, encoding="utf-8").read()


def orig_snapshot():
    """tests/baseline 에 저장된 원본 drive 결과. 브라우저를 띄우지 않는다."""
    path = os.path.join(ROOT, "tests", "baseline", "original_vs_original",
                        "snapshots.json")
    if not os.path.exists(path):
        pytest.skip("기준값이 없습니다. tests/capture_baseline.py 를 먼저 실행하세요.")
    return json.load(io.open(path, encoding="utf-8"))["orig"]


def snap(choices):
    """손으로 만든 스냅샷 하나. {action: [값들]} 만 들어 있으면 된다."""
    return {"screens": {"s1": {"choices": choices}}}


# --------------------------------------------------------------------- #
# 1. 뽑기
# --------------------------------------------------------------------- #
def test_script_arrays_behind_a_choice_group_are_extracted():
    """원본의 은행 목록은 마크업에 없다 - 스크립트 배열이 런타임에 그린다.
    그 배열을 이름과 원소로 꺼내야 도구가 그 데이터를 들고 있을 수 있다."""
    got = preserve.preserved_data(orig_snapshot(), original_html())
    assert sorted(got) == ["BANKS", "SECS", "nums"]
    assert len(got["BANKS"]) == 38
    assert len(got["SECS"]) == 29
    assert len(got["nums"]) == 10


def test_extracted_values_are_the_originals_own_strings():
    got = preserve.preserved_data(orig_snapshot(), original_html())
    assert got["BANKS"][0] == "신한"
    assert got["BANKS"][-1] == "관세"
    assert got["SECS"][-1] == "NH투자증권"
    assert got["nums"] == [str(n) for n in range(10)]


def test_choices_written_straight_into_the_markup_are_not_preserved():
    """숫자판처럼 마크업에 직접 쓰인 선택지는 대상이 아니다. LLM 이 그대로
    옮기거나 바꿀 수 있고, 도구가 지켜야 할 데이터가 아니다."""
    got = preserve.preserved_data(orig_snapshot(), original_html())
    flat = [v for items in got.values() for v in items]
    assert "00" not in flat          # num 숫자판
    assert "all" not in flat         # quick 전액


def test_arrays_that_are_not_choices_are_not_preserved():
    """원본의 COLORS 는 배열이지만 선택지가 아니다. 선택지 집합과 겹치지
    않으므로 나오지 않아야 한다."""
    got = preserve.preserved_data(orig_snapshot(), original_html())
    assert not any(v.startswith("#") for items in got.values() for v in items)


def test_extraction_works_on_any_input():
    """은행·이체에 묶이지 않는다. 합성 입력도 같은 규칙으로 돈다."""
    html = ("<html><body><div id=\"g\"></div><script>\n"
            "  const FRUITS = ['사과','배','감','밤'];\n"
            "  const SIZES = ['S','M'];\n"
            "  render(FRUITS);\n"
            "</script></body></html>")
    got = preserve.preserved_data(snap({"pick": ["사과", "배", "감", "밤"]}), html)
    assert got == {"FRUITS": ["사과", "배", "감", "밤"]}


def test_a_group_with_one_value_is_not_a_choice():
    html = "<html><body><script>const X = ['하나'];</script></body></html>"
    assert preserve.preserved_data(snap({"pick": ["하나"]}), html) == {}


# --------------------------------------------------------------------- #
# 2. 넣기
# --------------------------------------------------------------------- #
MODEL_HTML = ("<html lang=\"ko\"><head><style>.a{color:#111}</style></head>\n"
              "<body><div id=\"phone\"></div>\n"
              "<script>\n"
              "const BANKS = ['신한','국민'];\n"
              "document.body.innerHTML = BANKS.join();\n"
              "</script>\n"
              "</body></html>")

DATA = {"BANKS": ["신한", "국민", "농협"], "SECS": ["가증권", "나증권"]}


def data_block_of(html):
    m = re.search(r'<script[^>]*id="%s"[^>]*>(.*?)</script>'
                  % preserve.DATA_BLOCK_ID, html, re.S)
    assert m, "데이터 블록이 없다"
    return m.group(1)


def test_the_data_block_goes_in_front_of_the_models_script():
    """모델의 스크립트가 돌기 전에 데이터가 있어야 한다. 뒤에 넣으면 모델의
    코드가 아직 없는 전역을 읽는다."""
    out, _ = preserve.inject(MODEL_HTML, DATA)
    block_at = out.index('id="%s"' % preserve.DATA_BLOCK_ID)
    assert block_at < out.index("document.body.innerHTML")
    # 첫 <script> 가 데이터 블록이다
    assert out.index("<script") == out.rindex("<script", 0, block_at)


def test_every_value_is_in_the_injected_block():
    body = data_block_of(preserve.inject(MODEL_HTML, DATA)[0])
    assert "window.%s" % preserve.GLOBAL_NAME in body
    for name, items in DATA.items():
        for v in items:
            assert v in body, "%s 의 %r 이 데이터 블록에 없다" % (name, v)


def test_a_redeclared_array_keeps_its_name_and_loses_its_literal():
    """모델이 같은 이름을 다시 타이핑하면 그 짧은 목록이 이긴다. 선언을 지우면
    그 이름을 쓰는 코드가 ReferenceError 로 죽으므로, 선언은 남기고 초기화 식만
    참조로 바꾼다."""
    out, redeclared = preserve.inject(MODEL_HTML, DATA)
    assert redeclared == ["BANKS"]
    assert "const BANKS = window.%s.BANKS" % preserve.GLOBAL_NAME in out
    assert "['신한','국민']" not in out
    assert "BANKS.join()" in out          # 쓰는 쪽은 그대로 돈다


def test_a_model_that_already_references_the_data_is_not_a_redeclaration():
    html = MODEL_HTML.replace("const BANKS = ['신한','국민'];",
                              "const BANKS = window.PRESERVED.BANKS;")
    out, redeclared = preserve.inject(html, DATA)
    assert redeclared == []
    assert "const BANKS = window.PRESERVED.BANKS;" in out


def test_a_value_that_closes_the_script_tag_cannot_break_the_block():
    out, _ = preserve.inject(MODEL_HTML, {"X": ["a</script><b>", "b"]})
    assert "</script><b>" not in out
    assert out.count("</script>") == 2    # 데이터 블록 + 모델의 스크립트


def test_injection_without_any_script_still_lands_in_the_document():
    out, _ = preserve.inject("<html><body><p>없다</p></body></html>", DATA)
    assert 'id="%s"' % preserve.DATA_BLOCK_ID in out
    assert out.index("</script>") < out.index("</body>")


def test_nothing_is_injected_when_there_is_no_data():
    assert preserve.inject(MODEL_HTML, {}) == (MODEL_HTML, [])


# --------------------------------------------------------------------- #
# 3. 참조 검사 (형식 검사 단계 - 규칙 기반, 브라우저 없음)
# --------------------------------------------------------------------- #
def test_a_build_that_never_reads_the_data_is_a_format_problem():
    problems = _api.preserved_problems(MODEL_HTML, DATA)
    assert len(problems) == 1
    assert "BANKS" in problems[0] and "SECS" in problems[0]
    assert preserve.GLOBAL_NAME in problems[0]


def test_both_ways_of_reading_the_data_count():
    html = ("<html><body><script>\n"
            "  const a = window.PRESERVED.BANKS;\n"
            "  const b = PRESERVED['SECS'];\n"
            "</script></body></html>")
    assert _api.preserved_problems(html, DATA) == []


def test_only_the_names_that_are_never_read_are_reported():
    html = ("<html><body><script>window.PRESERVED.BANKS.forEach(x=>x);"
            "</script></body></html>")
    problems = _api.preserved_problems(html, DATA)
    assert len(problems) == 1
    assert "SECS" in problems[0]
    assert "BANKS" not in problems[0]


def test_reading_the_name_outside_a_script_does_not_count():
    """마크업에 글자로 적어 둔 것은 읽는 것이 아니다."""
    html = ("<html><body><p>window.PRESERVED.BANKS</p><script>1;</script>"
            "</body></html>")
    assert len(_api.preserved_problems(html, {"BANKS": DATA["BANKS"]})) == 1


def test_checking_after_injection_would_always_pass():
    """주입한 뒤의 문서로 검사하면 안 된다.

    그 문서에는 도구가 넣은 블록(`window.PRESERVED = {...}`)이 있어 모든 값이
    원문에 생기고, 모델이 다시 선언한 자리도 이미 참조로 바뀌어 있다. 무엇을
    보내도 통과하므로, 검사는 **넣기 전** 의 HTML 로 한다.
    """
    injected, _ = preserve.inject(MODEL_HTML, DATA)
    assert _api.preserved_problems(injected, DATA) == []
    assert len(_api.preserved_problems(MODEL_HTML, DATA)) == 1


def test_a_list_written_out_in_full_need_not_be_read():
    """값을 하나도 빠뜨리지 않고 직접 쓴 목록은 참조를 요구하지 않는다. 그때는
    참조하든 않든 결과가 같고, 요구하면 재시도를 한 번 헛되게 쓴다."""
    html = ("<html><body>"
            "<b data-v=\"가증권\">가증권</b><b data-v=\"나증권\">나증권</b>"
            "<script>1;</script></body></html>")
    assert _api.preserved_problems(html, {"SECS": DATA["SECS"]}) == []
    # 하나라도 빠지면 그대로 형식 문제다
    assert len(_api.preserved_problems(html, {"SECS": DATA["SECS"] + ["다증권"]})) == 1


def test_no_names_means_no_problem():
    assert _api.preserved_problems(MODEL_HTML, {}) == []


# --------------------------------------------------------------------- #
# 4. 검사 I 가 데이터 블록에 속지 않는다
# --------------------------------------------------------------------- #
# 고치기 전: 검사 I 는 재설계 HTML 의 **원문** 에서 값을 찾았다. 도구가 데이터
# 블록을 넣으면 모든 값이 원문에 생기므로, 모델이 하나도 그리지 않아도 통과했다 -
# 데이터를 지키려고 만든 장치가 그 데이터를 지켰는지 보는 검사를 꺼 버린다.
#
# 이제 블록을 빼고 보되, 블록을 참조해 **그린** 것은 렌더링된 DOM 에서 센다.
def audit_with(rep_html, rep_choices=None):
    """원본에 세 개짜리 선택지가 있는 상태에서 빌드를 검사한다."""
    import test_audit_bugs as AB
    orig = AB.snap({"start": AB.row("start",
                                    choices={"pick": ["가은행", "나은행", "다은행"]})})
    rep = AB.snap({"start": AB.row("start", shown=[["#dn-amt", "10,000"]],
                                   choices=rep_choices or {})})
    return _api.audit(orig, rep, "", rep_html, AB.flow(["start"]))


def test_check_I_is_not_fooled_by_the_tools_data_block():
    """데이터 블록만 있고 아무것도 그리지 않은 빌드는 통과하면 안 된다."""
    block = preserve.data_block({"P": ["가은행", "나은행", "다은행"]})
    report = audit_with("<html><body>%s</body></html>" % block)
    assert [f["check"] for f in report["fatal"]] == ["I"]
    assert report["metrics"]["choice_values_kept"] == {"pick": 0}
    assert report["metrics"]["choice_values_selectable"] == {"pick": 0}


def test_a_build_that_draws_them_all_from_the_block_passes():
    """반대쪽도 맞아야 한다 - 블록을 참조해 전부 그린 빌드는 통과한다.

    그 빌드의 **원문** 에는 값이 한 글자도 없다. 값은 런타임에 생긴다. 원문만
    보면 하라고 한 일을 한 답이 떨어진다.
    """
    block = preserve.data_block({"P": ["가은행", "나은행", "다은행"]})
    report = audit_with("<html><body>%s</body></html>" % block,
                        rep_choices={"pick": ["가은행", "나은행", "다은행"]})
    assert report["fatal"] == []
    assert report["metrics"]["choice_values_kept"] == {"pick": 3}
    assert report["metrics"]["choice_values_selectable"] == {"pick": 3}
    assert report["warning"] == []


def test_a_build_that_draws_only_some_of_them_fails():
    """`slice(0, 2)` 처럼 일부만 그린 빌드는 검사 I 에서 떨어진다."""
    block = preserve.data_block({"P": ["가은행", "나은행", "다은행"]})
    report = audit_with("<html><body>%s</body></html>" % block,
                        rep_choices={"pick": ["가은행", "나은행"]})
    assert [f["check"] for f in report["fatal"]] == ["I"]
    assert report["metrics"]["choice_values_missing"] == {"pick": ["다은행"]}
    assert report["metrics"]["choice_values_selectable"] == {"pick": 2}


# --------------------------------------------------------------------- #
# 5. 문서에는 있지만 고를 수 없던 값은 경고다 (fatal 아님)
# --------------------------------------------------------------------- #
def test_a_value_in_the_document_but_never_selectable_is_a_warning():
    """"전체 보기" 뒤나 검색 결과로만 나오는 목록은 검사기가 그 버튼을 누르지
    않으면 DOM 에 나타나지 않는다. fatal 로 하면 정상 설계가 떨어진다."""
    report = audit_with("<html><body><p>가은행 나은행 다은행</p></body></html>",
                        rep_choices={"pick": ["가은행"]})
    assert report["fatal"] == []
    assert report["passed"] is True
    assert report["metrics"]["choice_values_kept"] == {"pick": 3}
    assert report["metrics"]["choice_values_selectable"] == {"pick": 1}

    warn = [w for w in report["warning"] if w["check"] == "I"]
    assert len(warn) == 1
    assert warn[0]["not_selectable"] == ["나은행", "다은행"]
    assert "2개" in warn[0]["detail"]
    assert "나은행" in warn[0]["detail"]


def test_a_missing_value_is_not_also_a_warning():
    """없는 값은 fatal 이다. 경고까지 겹쳐 내면 같은 일을 두 번 말한다."""
    report = audit_with("<html><body><p>가은행</p></body></html>",
                        rep_choices={"pick": ["가은행"]})
    assert [f["check"] for f in report["fatal"]] == ["I"]
    assert [w for w in report["warning"] if w["check"] == "I"] == []


def test_a_hidden_choice_is_still_selectable():
    """숨김·접힘은 괜찮다는 규칙은 그대로다. probe 는 켜지지 않은 화면 안의
    선택지도 모으므로, 접어 둔 목록은 경고가 되지 않는다."""
    report = audit_with("<html><body><p>가은행 나은행 다은행</p></body></html>",
                        rep_choices={"pick": ["가은행", "나은행", "다은행"]})
    assert report["warning"] == []
