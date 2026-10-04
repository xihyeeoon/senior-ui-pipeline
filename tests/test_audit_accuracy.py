r"""검사기가 결함을 놓치는(거짓 통과) 것의 재현 테스트. `pytest -m browser` 로만.

`test_audit_bugs.py` 는 손으로 만든 스냅샷으로 판정 논리만 본다. 이 파일은 그
앞단까지 본다 - 작은 페이지를 실제로 브라우저로 걷고, 긁어 온 것으로 판정해서,
"결함이 있는데 통과했다" 를 그대로 재현한다. 긁어 오는 쪽(probes.py)과 판정하는
쪽(checks/)이 함께 맞아야 잡히는 결함들이라, 스냅샷을 손으로 만들면 재현 자체가
"내가 믿는 모양" 의 확인이 되어 버린다.

페이지와 그 흐름 파일은 tests/fixtures/pages/ 에 있다 (그 폴더의 README 참고).
버그 하나에 페이지 하나이고, 각 테스트는 고치기 전에 실패한다.

  .\.venv\Scripts\python.exe -m pytest -m browser tests/test_audit_accuracy.py
"""
import asyncio
import io
import os
import subprocess
import sys
import time

import pytest

import _api
import capture_baseline as C

pytestmark = pytest.mark.browser

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PAGES = os.path.join(HERE, "fixtures", "pages")
PAGES_REL = "tests/fixtures/pages"


# --------------------------------------------------------------------- #
# 서버 - test_drive.py 와 같은 규칙: 떠 있으면 그대로 쓰고 건드리지 않는다.
# 내가 띄운 것만 내가 끈다.
# --------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def server():
    if C.listening(C.PORT):
        yield None
        return
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(C.PORT), "--directory", ROOT],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        if C.listening(C.PORT):
            break
        time.sleep(0.1)
    else:
        proc.kill()
        pytest.fail(":%d 에 http.server 를 띄우지 못했습니다." % C.PORT)
    try:
        yield proc
    finally:
        proc.terminate()
        proc.wait()


# --------------------------------------------------------------------- #
# 페이지 하나를 걷고 audit() 을 돌린다
# --------------------------------------------------------------------- #
def page_path(name):
    return os.path.join(PAGES, name)


def page_url(name):
    return "%s/%s/%s" % (C.BASE_URL, PAGES_REL, name)


def read_page(name):
    return io.open(page_path(name), encoding="utf-8").read()


def drive_and_audit(flow_file, rep_page, orig_page=None, orig_flow_file=None,
                    orig_html=None):
    """fixture 페이지를 실제로 걷고, 긁어 온 것과 리포트를 함께 돌려준다.

    `orig_page` 를 주지 않으면 생성물 페이지를 원본으로도 쓴다. 그러면 원본
    대비 비교(D·E·F·G·H·I)가 전부 빈 결과가 되어, 재현하려는 검사의 fatal 만
    리포트에 남는다 - 테스트가 그 하나를 세고 있는지 의심할 필요가 없다.

    `orig_html` 은 스냅샷과 따로 줄 수 있다. 검사 C 는 처리기를 HTML 글자에서
    찾으므로, "빌드에는 처리기가 없고 원본에는 있다" 를 만들려면 둘이 달라야
    한다.
    """
    flow = _api.load_flow(page_path(flow_file))
    rep_html = read_page(rep_page)
    rep = asyncio.run(_api.drive(page_url(rep_page), flow))
    if orig_page is None:
        orig, html_of_orig = rep, rep_html
    else:
        orig = asyncio.run(_api.drive(
            page_url(orig_page), _api.load_flow(page_path(orig_flow_file
                                                          or flow_file))))
        html_of_orig = read_page(orig_page)
    report = _api.audit(orig, rep,
                        html_of_orig if orig_html is None else orig_html,
                        rep_html, flow)
    return {"orig": orig, "rep": rep, "report": report}


def run_audit(*a, **kw):
    """리포트만 보면 되는 검사용. 대부분의 테스트가 이것을 쓴다."""
    return drive_and_audit(*a, **kw)["report"]


def fatals(report, check=None):
    return [f for f in report["fatal"]
            if check is None or f.get("check") == check]


def details(findings):
    return [f.get("detail") or "" for f in findings]


# ===================================================================== #
# 1. 검사 B 가 "포함" 으로 비교한다
# ===================================================================== #
@pytest.fixture(scope="module")
def b_contains(server):
    return run_audit("b_contains.json", "b_contains.html")


@pytest.fixture(scope="module")
def b_decorated(server):
    return run_audit("b_decorated.json", "b_decorated.html")


def test_a_bigger_amount_does_not_pass_as_the_task_amount(b_contains):
    """110,000원 은 10,000 이 아니다.

    고치기 전: `expected not in got` 으로 비교해서, 과제가 넣은 값을 자기 안에
    품기만 하는 더 큰 값이 전부 통과했다 - 열한 배 금액이 통과한다.
    """
    hit = [f for f in fatals(b_contains, "B") if f.get("selector") == "#dn-amt"]
    assert len(hit) == 1, details(b_contains["fatal"])
    assert hit[0]["got"] == "110,000원"
    assert hit[0]["expected"] == "10,000"


def test_a_longer_account_does_not_pass_as_the_task_account(b_contains):
    """33330000000009 는 3333000000000 이 아니다 - 한 자리 더 길다."""
    hit = [f for f in fatals(b_contains, "B") if f.get("selector") == "#acc"]
    assert len(hit) == 1, details(b_contains["fatal"])
    assert hit[0]["got"] == "33330000000009"


def test_a_label_does_not_excuse_a_wrong_number(b_contains):
    """라벨이 붙어 있다고 숫자가 봐주어지는 것은 아니다.

    값이 아닌 글자는 함께 있어도 되지만, 그것은 숫자가 맞을 때의 이야기다.
    "보낼 돈 110,000원" 은 라벨을 떼어도 열한 배 금액이다.
    """
    hit = [f for f in fatals(b_contains, "B") if f.get("selector") == "#lab-amt"]
    assert len(hit) == 1, details(b_contains["fatal"])
    assert hit[0]["got"] == "보낼 돈 110,000원"


def test_only_those_three_are_fatal(b_contains):
    """재현 페이지는 그 셋 말고는 아무 결함도 없어야 한다. 다른 fatal 이 섞이면
    위의 세 테스트가 무엇을 세고 있는지 알 수 없다."""
    assert len(b_contains["fatal"]) == 3, details(b_contains["fatal"])
    assert b_contains["warning"] == []


def test_decoration_only_differences_still_pass(b_decorated):
    """'10,000원' 과 '3333-0000-0000-0' 은 과제가 넣은 값 그대로다.

    고치기 전: 하이픈이 든 계좌는 "포함" 비교에서도 떨어졌다 - 거짓 통과를
    고치는 김에 이 거짓 실패도 같이 사라져야 한다.
    """
    assert fatals(b_decorated, "B") == [], details(b_decorated["fatal"])
    assert b_decorated["passed"] is True, details(b_decorated["fatal"])


# 한 요소가 라벨과 값을 같이 담는 것은 흔한 모양이고 결함이 아니다. 아래 셋은
# Run1~3 에 실제로 있는 모양을 그대로 옮겨 놓은 것이다 - 요소 전체를 값으로
# 보면 세 빌드가 전부 여기서 떨어진다.
@pytest.mark.parametrize("sel,got", [
    ("#rv-acc", "카카오뱅크 3333000000000"),      # 계좌 앞에 은행 이름
    ("#rv-amt", "10,000원만 원"),                 # 금액 아래 한글 읽기(small)
    ("#am-acc", "카카오뱅크 3333 0000 0000 0"),   # 은행 이름 뒤에 끊어 쓴 계좌
])
def test_a_value_shown_next_to_a_label_passes(b_decorated, sel, got):
    assert [f for f in fatals(b_decorated, "B")
            if f.get("selector") == sel] == [], details(b_decorated["fatal"])
    assert dict(b_decorated["metrics"]["screens_landed_on"])          # 도착은 했다


def test_digits_separated_inside_the_number_are_joined(b_decorated):
    """숫자 사이의 하이픈·공백만 걷어낸다. "카카오뱅크 3333 0000 0000 0" 에서
    은행 이름과 계좌를 가르는 공백은 그대로 두고, 계좌 안의 공백만 붙인다."""
    from senior_ui.audit.checks.b_display import joined, shows
    assert joined("카카오뱅크 3333 0000 0000 0") == "카카오뱅크 3333000000000"
    assert shows("카카오뱅크 3333 0000 0000 0", "3333000000000")
    assert not shows("카카오뱅크 33330000000009", "3333000000000")


# ===================================================================== #
# 2. 화면 도착 판정이 window.__screen() 하나만 믿는다
# ===================================================================== #
# window.__screen() 은 전환 스크립트의 기록이다 (원본은
# `window.__screen = () => window.__task.screen`). 기록이 바뀌었다는 것은
# 화면이 바뀌었다는 것과 다른 일이다 - 기록만 바꾸고 on 클래스를 옮기지 않으면
# 사용자는 앞 화면에 그대로 서 있다. 그래서 켜진 화면의 data-screen 도 함께
# 본다.
@pytest.fixture(scope="module")
def arrival_lies(server):
    return run_audit("arrival_lies.json", "arrival_lies.html")


@pytest.fixture(scope="module")
def arrival_dark(server):
    return run_audit("arrival_dark.json", "arrival_dark.html")


@pytest.fixture(scope="module")
def b_scope(server):
    return run_audit("b_scope.json", "b_scope.html")


def test_bookkeeping_alone_does_not_count_as_arriving(arrival_lies):
    """기록만 'done' 이 되고 화면은 start 에 그대로 있으면 도착이 아니다.

    고치기 전: fatal 0건. __screen() 이 'done' 이라 했으므로 검사기는 완료
    화면에 도착했다고 보고, 거기서 재는 모든 것을 start 화면에서 재었다.
    """
    hit = [f for f in fatals(arrival_lies, "A") if f.get("screen") == "done"]
    assert len(hit) == 1, details(arrival_lies["fatal"])
    assert ".screen.on" in hit[0]["detail"]
    assert hit[0]["dom_screen"] == "start"


def test_a_wrong_landing_by_dom_is_where_it_stopped(arrival_lies):
    """도착하지 못한 것이므로 멈춘 곳으로 적힌다 - 엉뚱한 화면에 도착한 것과
    같은 취급이다."""
    assert arrival_lies["metrics"]["stopped_at"] == "done"


def test_the_arrival_mismatch_is_the_only_fatal(arrival_lies):
    """켜진 화면 안의 #amt 는 값이 맞다. 도착 판정 하나만 걸려야 한다."""
    assert len(arrival_lies["fatal"]) == 1, details(arrival_lies["fatal"])


def test_no_lit_screen_is_fatal(arrival_dark):
    """켜진 화면이 하나도 없으면 무엇이 보이는지 잴 수 없다.

    고치기 전: fatal 0건. 화면에 매인 probe 들이 빈 목록을 돌려주고, 빈 목록은
    "결함 없음" 과 구분되지 않았다 - 빈 화면이 가장 깨끗한 빌드로 보였다.
    """
    hit = [f for f in fatals(arrival_dark, "A") if "screen.on" in f["detail"]]
    assert len(hit) == 1, details(arrival_dark["fatal"])
    assert len(arrival_dark["fatal"]) == 1, details(arrival_dark["fatal"])


def test_screen_scoped_probes_return_null_when_nothing_is_lit(arrival_dark):
    """계약: 화면에 매인 probe 는 켜진 화면이 없을 때 [] 가 아니라 null 이다.
    빈 목록은 "쟀고 아무것도 없었다" 이고 null 은 "잴 수 없었다" 다."""
    row = arrival_dark["metrics"]["screens_unlit"]
    assert row == ["start"]


def test_b_does_not_read_values_from_a_screen_that_is_off(b_scope):
    """꺼진 화면에 남아 있는 옛 값은 사용자가 볼 수 없다.

    고치기 전: document.querySelector 가 문서 전체에서 첫 요소를 집었다.
    꺼진 화면의 '10,000원' 이 집혀, 켜진 화면이 '9,000원' 을 보여 주는데도
    통과했다.
    """
    hit = [f for f in fatals(b_scope, "B")
           if f.get("selector") == "[data-field='amt']"]
    assert len(hit) == 1, details(b_scope["fatal"])
    assert hit[0]["got"] == "9,000원"


def test_b_does_not_read_values_from_a_hidden_element(b_scope):
    """display:none 인 요소의 값도 사용자가 볼 수 없다. 켜진 화면 안이어도
    마찬가지다 - '김시현' 이 숨어 있고 '박철수' 가 보인다."""
    hit = [f for f in fatals(b_scope, "B")
           if f.get("selector") == "[data-field='name']"]
    assert len(hit) == 1, details(b_scope["fatal"])
    assert hit[0]["got"] == "박철수"


def test_b_scope_has_no_other_fatal(b_scope):
    assert len(b_scope["fatal"]) == 2, details(b_scope["fatal"])

# ===================================================================== #
# 3. 검사 C 가 처리기를 한 가지 모양으로만 읽는다
# ===================================================================== #
@pytest.fixture(scope="module")
def c_switch(server):
    return run_audit("c_switch.json", "c_switch.html")


@pytest.fixture(scope="module")
def c_nohandler(server):
    """처리기가 없는 빌드에, 처리기가 있는 진짜 원본을 orig_html 로 준다.
    "못 찾으면 원본 목록으로 대신한다" 가 거짓 통과가 되는 상황이다."""
    return run_audit("c_nohandler.json", "c_nohandler.html",
                     orig_html=io.open(os.path.join(ROOT, "inputs",
                                                    "original_transfer.html"),
                                       encoding="utf-8").read())


def test_switch_case_branches_are_read(c_switch):
    """`case '이름'` 도 분기다 - 눌리면 일이 일어난다.

    고치기 전: `a === '이름'` 홑따옴표 하나만 찾았다. 분기를 하나도 못 찾으면
    원본 목록으로 대신하는데 이 페이지의 원본은 자기 자신이라 그 목록도 비어,
    분기가 있는 조작부 세 개가 전부 "죽은 조작부" 로 걸렸다.
    """
    assert fatals(c_switch, "C") == [], details(c_switch["fatal"])
    assert c_switch["metrics"]["handled_actions"] == 3


def test_a_branch_written_only_in_a_korean_comment_is_not_a_branch(c_switch):
    """주석에 적힌 설명은 분기가 아니다.

    이 페이지의 주석에는 `a === '이름'` 이라는 설명이 그대로 들어 있다. 이름
    자리의 글자까지 받아 주면(유니코드 단어 글자) 그 설명이 분기로 잡히고, 처리기가
    주석뿐인 빌드가 "분기가 있다" 로 읽혀 검사 C 를 통과한다. 그래서 이름은
    ASCII 로만 읽는다.
    """
    assert c_switch["metrics"]["handled_actions"] == 3


def test_double_quoted_branches_are_read(c_switch):
    """`a === "이름"` 쌍따옴표도 같은 분기다. 위 테스트의 3 에 reset 이
    들어 있다는 것이 그 확인이고, 죽은 조작부가 없다는 것도 같은 말이다."""
    assert c_switch["metrics"]["dead_controls_new"] == 0


def test_c_switch_has_no_other_fatal(c_switch):
    assert c_switch["fatal"] == [], details(c_switch["fatal"])


def test_a_build_with_no_handler_at_all_is_fatal(c_nohandler):
    """처리기가 없으면 모든 조작부가 죽어 있다. 그것을 원본 목록으로 덮으면
    가장 깨진 빌드가 통과한다.

    고치기 전: fatal 0건. 빌드에서 분기를 못 찾자 원본의 분기 목록으로
    대신했고, 이 페이지의 data-action 이름(pick-bank · quick)은 원본이 다루는
    것들이라 "둘 다 처리된다" 로 읽혔다.
    """
    hit = fatals(c_nohandler, "C")
    assert len(hit) == 1, details(c_nohandler["fatal"])
    assert "처리기" in hit[0]["detail"]
    assert c_nohandler["metrics"]["handled_actions"] == 0


def test_the_original_handler_list_is_not_substituted(c_nohandler):
    """계약: 빌드의 처리기는 빌드에서만 읽는다. 원본 것으로 대신하지 않는다.
    대신했다면 pick-bank · quick 이 처리된 것으로 세졌을 것이다."""
    m = c_nohandler["metrics"]
    assert m["handled_actions"] == 0
    assert sorted(m["dead_controls_unverifiable"]) == ["pick-bank", "quick"]
    assert any(s.startswith("C/") for s in m["checks_stood_down"])

# ===================================================================== #
# 4. 검사 I 가 "문서 글자에 들어 있는가" 로만 찾는다
# ===================================================================== #
@pytest.fixture(scope="module")
def i_substring(server):
    return run_audit("i_substring.json", "i_build.html", orig_page="i_orig.html")


@pytest.fixture(scope="module")
def i_declared(server):
    """같은 두 페이지에, 뺀 선택지를 선언해 둔 흐름."""
    return run_audit("i_declared.json", "i_build.html", orig_page="i_orig.html")


def missing_of(report):
    return report["metrics"]["choice_values_missing"].get("quick", [])


def test_a_short_value_inside_another_word_is_not_present(i_substring):
    """'all' 은 class="small" 안에 있다. 거기 있다고 고를 수 있는 것은 아니다.

    고치기 전: `v not in ctx.rep_html` 로 찾아서, 'all' 이 'small' 안에서,
    '10000' 이 '110000' 안에서 맞았다. 빌드에 없는 선택지 둘이 남아 있는 것으로
    읽혔다.
    """
    assert missing_of(i_substring) == ["10000", "100000", "all"]


def test_values_kept_only_as_an_attribute_or_an_array_element_still_count(i_substring):
    """화면에 다 보일 필요는 없다는 규칙은 그대로다. 50000 은 data-v 로,
    70000 은 스크립트 배열 원소로만 있고 둘 다 남아 있는 것으로 센다."""
    assert i_substring["metrics"]["choice_values_kept"] == {"quick": 2}
    assert i_substring["metrics"]["choice_groups_original"] == {"quick": 5}


def test_the_missing_choices_are_one_fatal(i_substring):
    hit = fatals(i_substring, "I")
    assert len(hit) == 1, details(i_substring["fatal"])
    assert hit[0]["missing"] == ["10000", "100000", "all"]
    assert len(i_substring["fatal"]) == 1, details(i_substring["fatal"])


def test_a_declared_removal_is_not_fatal(i_declared):
    """일부러 뺀 선택지는 누락이 아니다.

    고치기 전: 선언할 방법이 없어서, 안전을 위해 뺀 선택지(전액 버튼)도
    누락으로 세졌다 - 고칠 수 없는 fatal 이 재생성 루프에 계속 남는다.
    """
    assert missing_of(i_declared) == ["10000", "100000"]
    hit = fatals(i_declared, "I")
    assert len(hit) == 1, details(i_declared["fatal"])
    assert hit[0]["missing"] == ["10000", "100000"]


def test_a_declared_removal_is_recorded_with_its_reason(i_declared):
    """fatal 로 세지 않는 대신 이유와 함께 남긴다 - 조용히 사라지면 안 된다."""
    m = i_declared["metrics"]
    by_design = m["choice_values_removed_by_design"]
    assert by_design["quick"]["values"] == ["all"]
    assert "changelog #15" in by_design["quick"]["reason"]
    stood = [s for s in m["checks_stood_down"] if s.startswith("I/")]
    assert len(stood) == 1
    assert "all" in stood[0] and "changelog #15" in stood[0]


def test_an_undeclared_removal_is_still_fatal(i_declared):
    """선언한 것만 빠진다. 10000 · 100000 은 선언하지 않았으므로 그대로 fatal
    이다 - 선언이 검사를 끄는 장치가 되어서는 안 된다."""
    assert i_declared["passed"] is False
    assert fatals(i_declared, "I")[0]["missing"] == ["10000", "100000"]


def test_declaring_a_removal_does_not_change_the_kept_count(i_declared):
    """선언한 값은 "남아 있다" 가 아니라 "일부러 뺐다" 다. 남은 개수는 실제로
    찾을 수 있는 값의 수 그대로여야 한다."""
    assert i_declared["metrics"]["choice_values_kept"] == {"quick": 2}

# --------------------------------------------------------------------- #
# 4-2. 경계는 값의 글자 종류마다 다르다
# --------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def i_suffix(server):
    return run_audit("i_suffix.json", "i_suffix_build.html",
                     orig_page="i_suffix_orig.html")


def test_a_hangul_value_may_grow_a_suffix(i_suffix):
    """원본의 "국민" 을 빌드가 "국민은행" 으로 쓰는 것은 그 은행을 뺀 것이
    아니다. 한글은 뒤에 말이 붙어 늘어나므로 앞쪽 경계만 본다.

    낱말 경계를 양쪽에 걸면 Run4 처럼 은행 이름을 길게 쓴 빌드에서 멀쩡한
    선택지가 전부 누락으로 세진다.
    """
    missing = i_suffix["metrics"]["choice_values_missing"].get("pick-bank", [])
    assert missing == ["가람"], details(i_suffix["fatal"])
    assert i_suffix["metrics"]["choice_values_kept"] == {"pick-bank": 2}


def test_the_boundary_rule_follows_the_characters_in_the_value():
    """계약: 값의 글자 종류가 경계를 정한다. 브라우저가 필요 없는 규칙이므로
    여기서 직접 본다."""
    from senior_ui.audit.checks.i_choices import present
    # 한글 - 뒤는 늘어나도 되고, 앞은 붙으면 안 된다
    assert present("국민", '<b data-bank="국민은행">')
    assert not present("국민", '<b data-bank="농협국민">')
    # 영문 - 앞뒤 모두 낱말 경계
    assert present("all", '<b data-v="all">')
    assert not present("all", '<p class="small">')
    # 숫자 - 숫자가 붙으면 안 되고, 한글 단위는 붙어도 된다
    assert present("10000", '<b data-v="10000">')
    assert present("10000", "<p>10000원</p>")
    assert not present("10000", '<b data-v="110000">')
    # 숫자 - 영문 글자가 붙은 것은 다른 토막이다 (색 코드의 00 은 숫자판이 아니다)
    assert not present("00", "<script>'#6B5B00'</script>")
    assert present("00", '<b data-v="00">')


# ===================================================================== #
# 5. 명암비가 눈에 보이는 색이 아니라 선언된 색을 잰다
# ===================================================================== #
# probes.CONTRAST 는 화면에 매이지 않고 문서 전체를 훑으므로, 꺼진 화면의 글은
# 사각형이 0 이어서 저절로 빠진다. 아래 페이지들은 켜진 화면 하나만 둔다.
def contrast_of(res, screen="start"):
    return res["rep"]["screens"][screen]["contrast"]


def undetermined_of(res, screen="start"):
    return res["rep"]["screens"][screen]["contrast_undetermined"]


def texts_of(rows):
    return sorted(x["text"] for x in rows)


@pytest.fixture(scope="module")
def d_alpha(server):
    return drive_and_audit("d_alpha.json", "d_alpha.html")


def test_a_translucent_text_colour_is_measured_as_it_looks(d_alpha):
    """rgba(17,17,17,0.25) 는 흰 배경에서 #c4c4c4 로 보인다 - 1.75:1 이다.

    고치기 전: 알파를 버리고 #111 로 재어 18.9:1 이 나왔다. 글자가 거의
    보이지 않는데 가장 선명한 글로 세졌다.
    """
    rows = [x for x in contrast_of(d_alpha) if x["text"] == "보낼 돈을 고르세요"]
    assert len(rows) == 1, texts_of(contrast_of(d_alpha))
    assert rows[0]["ratio"] < 2.0
    assert rows[0]["need"] == 4.5


def test_the_alpha_page_has_nothing_else_wrong(d_alpha):
    """같은 페이지의 읽히는 글은 걸리지 않는다 - 알파를 세기 시작했다고 멀쩡한
    글까지 잡으면 거짓 경보를 새로 만든 것이다."""
    assert texts_of(contrast_of(d_alpha)) == ["보낼 돈을 고르세요"]
    assert d_alpha["report"]["fatal"] == [], details(d_alpha["report"]["fatal"])


@pytest.fixture(scope="module")
def d_opacity(server):
    return drive_and_audit("d_opacity.json", "d_opacity.html")


def test_an_ancestors_opacity_reaches_the_text(d_opacity):
    """opacity:0.3 인 상자 안의 #111 글자는 #b8b8b8 로 보인다 - 1.99:1 이다.

    고치기 전: 요소 자신의 opacity 만 보았다. 글자 쪽은 opacity 1 이므로
    #111 그대로 18.9:1 이 나왔다 - 흐려진 것을 보지 못했다.
    """
    rows = [x for x in contrast_of(d_opacity) if x["text"] == "보낼 돈을 고르세요"]
    assert len(rows) == 1, texts_of(contrast_of(d_opacity))
    assert rows[0]["ratio"] < 2.5
    assert rows[0]["opacity"] == 0.3


def test_the_opacity_page_has_nothing_else_wrong(d_opacity):
    assert texts_of(contrast_of(d_opacity)) == ["보낼 돈을 고르세요"]
    assert d_opacity["report"]["fatal"] == [], details(d_opacity["report"]["fatal"])


@pytest.fixture(scope="module")
def d_modern_colour(server):
    return drive_and_audit("d_modern_colour.json", "d_modern_colour.html")


def test_an_oklch_colour_is_measured(d_modern_colour):
    """oklch(0.85 0.03 250) 은 rgb(192, 208, 225) 다 - 흰 배경에서 1.57:1.

    고치기 전: getComputedStyle 이 적힌 모양 그대로 돌려주고 rgba?() 글자만
    읽었으므로 "색을 알 수 없다" 가 되어 요소째로 검사에서 빠졌다.
    """
    rows = [x for x in contrast_of(d_modern_colour)
            if x["text"] == "보낼 돈을 고르세요"]
    assert len(rows) == 1, texts_of(contrast_of(d_modern_colour))
    assert rows[0]["ratio"] < 2.0
    assert rows[0]["seen"] == "rgb(192, 208, 225)"


def test_a_color_srgb_colour_is_measured(d_modern_colour):
    """color(srgb 0.8 0.82 0.85) 도 같은 길로 숫자가 된다."""
    rows = [x for x in contrast_of(d_modern_colour)
            if x["text"] == "받는 분을 고르세요"]
    assert len(rows) == 1, texts_of(contrast_of(d_modern_colour))
    assert rows[0]["ratio"] < 2.0
    assert rows[0]["seen"] == "rgb(204, 209, 217)"


def test_the_modern_colour_page_has_nothing_else_wrong(d_modern_colour):
    assert texts_of(contrast_of(d_modern_colour)) == ["받는 분을 고르세요",
                                                      "보낼 돈을 고르세요"]
    assert d_modern_colour["report"]["fatal"] == [], \
        details(d_modern_colour["report"]["fatal"])


@pytest.fixture(scope="module")
def d_bg_alpha(server):
    return drive_and_audit("d_bg_alpha.json", "d_bg_alpha.html")


def test_a_translucent_background_is_mixed_in(d_bg_alpha):
    """#111 상자에 알파 0.9 흰 베일이 덮이면 실제 배경은 #e7e7e7 이다.
    그 위의 흰 글자는 1.23:1 이다.

    고치기 전: 알파 0.95 미만인 층을 건너뛰고 불투명한 조상(#111)을 배경으로
    썼다. 흰 글자가 "어두운 바탕 위의 흰 글자" 로 읽혀 18.9:1 이 나왔다.
    """
    rows = [x for x in contrast_of(d_bg_alpha) if x["text"] == "보낼 돈을 고르세요"]
    assert len(rows) == 1, texts_of(contrast_of(d_bg_alpha))
    assert rows[0]["bg"] == "rgb(231, 231, 231)"
    assert rows[0]["ratio"] < 1.5


def test_the_bg_alpha_page_has_nothing_else_wrong(d_bg_alpha):
    assert texts_of(contrast_of(d_bg_alpha)) == ["보낼 돈을 고르세요"]
    assert d_bg_alpha["report"]["fatal"] == [], details(d_bg_alpha["report"]["fatal"])


@pytest.fixture(scope="module")
def d_gradient(server):
    return drive_and_audit("d_gradient.json", "d_gradient.html")


def test_text_on_a_gradient_is_undetermined_not_passing(d_gradient):
    """그라디언트 위의 글자는 잴 수 없다 - 왼쪽과 오른쪽의 바탕이 다르다.

    고치기 전: backgroundColor 가 rgba(0,0,0,0) 이라 투명으로 읽히고 배경이
    흰색으로 올라가, 검은 글자가 18.9:1 로 통과했다.
    """
    rows = [x for x in undetermined_of(d_gradient)
            if x["text"] == "보낼 돈을 고르세요"]
    assert len(rows) == 1, undetermined_of(d_gradient)
    assert "gradient" in rows[0]["background"]
    assert texts_of(contrast_of(d_gradient)) == []


def test_text_on_a_background_image_is_undetermined(d_gradient):
    """이미지 위도 같다 - 무슨 색이 깔렸는지 알 수 없다."""
    rows = [x for x in undetermined_of(d_gradient)
            if x["text"] == "받는 분을 고르세요"]
    assert len(rows) == 1, undetermined_of(d_gradient)
    assert "url(" in rows[0]["background"]


def test_an_opaque_layer_over_a_gradient_can_be_judged(d_gradient):
    """그라디언트를 불투명한 색으로 덮으면 아래가 무엇이든 가려진다 -
    판정 불가가 아니라 그 색으로 잰다. 넓게 포기하면 판정 불가가 통과의 새
    이름이 될 뿐이다."""
    assert texts_of(undetermined_of(d_gradient)) == ["받는 분을 고르세요",
                                                     "보낼 돈을 고르세요"]


def test_undetermined_is_counted_apart_from_low_contrast(d_gradient):
    """통과도 저명암도 아닌 세 번째 칸으로 센다."""
    m = d_gradient["report"]["metrics"]
    assert m["contrast_undetermined"] == 2
    assert m["low_contrast_after"] == 0
    hit = [w for w in d_gradient["report"]["warning"]
           if w["check"] == "D" and "판정할 수 없다" in w["detail"]]
    assert len(hit) == 2, details(d_gradient["report"]["warning"])


# ===================================================================== #
# 6. 검사 F 가 innerText 에 들어오는 글만 본다
# ===================================================================== #
@pytest.fixture(scope="module")
def f_attrs(server):
    return run_audit("f_attrs.json", "f_attrs_build.html",
                     orig_page="f_attrs_orig.html")


def warnings_of(report, check=None, source=None):
    return [w for w in report["warning"]
            if (check is None or w.get("check") == check)
            and (source is None or w.get("source") == source)]


def test_english_in_attributes_is_found(f_attrs):
    """placeholder · 입력값 · alt · aria-label · title 도 눈에 닿는 글이다.

    고치기 전: warning 0건. innerText 에는 들어오지 않고, 마크업에서 찾는
    쪽은 태그를 통째로 걷어내므로 속성값이 함께 사라졌다 - 화면이 영어로
    뒤덮여도 검사 F 는 할 말이 없었다.
    """
    hit = warnings_of(f_attrs, "F", "attribute")
    assert len(hit) == 1, details(f_attrs["warning"])
    assert sorted(hit[0]["words"]) == ["Account", "Bank", "Confirm", "Recipient",
                                       "Transfer", "fee", "logo", "number",
                                       "transfer"]


def test_korean_attributes_raise_nothing(f_attrs):
    """원본과 같은 자리의 한글은 새 영어가 아니다 - 속성을 보기 시작했다고
    멀쩡한 속성까지 잡으면 거짓 경보를 새로 만든 것이다."""
    assert warnings_of(f_attrs, "F", "runtime") == []
    assert warnings_of(f_attrs, "F", "markup") == []
    assert f_attrs["fatal"] == [], details(f_attrs["fatal"])


@pytest.fixture(scope="module")
def f_modal(server):
    return run_audit("f_modal.json", "f_modal_build.html",
                     orig_page="f_modal_orig.html")


def test_english_on_a_modal_outside_the_lit_screen_is_found(f_modal):
    """화면 위에 덮인 모달도 사용자가 읽는 글이다.

    고치기 전: warning 0건. 켜진 화면의 innerText 에는 모달이 들어오지 않고,
    글을 스크립트가 넣으므로 마크업에서 찾는 쪽도 보지 못했다.
    """
    hit = warnings_of(f_modal, "F", "offscreen")
    assert len(hit) == 1, details(f_modal["warning"])
    assert hit[0]["screen"] == "start"
    assert sorted(hit[0]["words"]) == ["Please", "Transfer", "failed", "retry"]


def test_the_modal_page_raises_nothing_else(f_modal):
    assert warnings_of(f_modal, "F", "runtime") == []
    assert warnings_of(f_modal, "F", "markup") == []
    assert f_modal["fatal"] == [], details(f_modal["fatal"])


# ===================================================================== #
# 7. 검사 D 가 새 설계에서 이름만 같은 화면과 견준다
# ===================================================================== #
@pytest.fixture(scope="module")
def d_newdesign(server):
    return run_audit("d_newdesign.json", "d_newdesign.html",
                     orig_page="d_newdesign_orig.html")


def stood_down(report, letter):
    return [s for s in report["metrics"]["checks_stood_down"]
            if s.startswith(letter + "/")]


def test_inherited_colour_runs_on_a_new_design(d_newdesign):
    """자기 색이 없어서 읽히지 않는 라벨은 새 설계에서도 걸려야 한다.

    고치기 전: 상속 색 검사가 shared 화면에서만 돌았다. 새 설계에서는 shared 가
    늘 비어 있으므로 아예 돌지 않았다 - 색이 없어 사라진 라벨이 통과했다.
    """
    hit = [w for w in warnings_of(d_newdesign, "D") if "상속" in w["detail"]]
    assert len(hit) == 1, details(d_newdesign["warning"])
    assert hit[0]["screen"] == "start"
    assert hit[0]["cls"] == ""
    assert hit[0]["tag"] == "span"
    assert d_newdesign["metrics"]["inherited_colour_unreadable"] == 1


def test_gained_text_does_not_compare_unrelated_screens(d_newdesign):
    """'start' 라는 이름이 같다고 같은 화면이 아니다.

    고치기 전: gained-text 비교가 want 전체에서 돌아, 원본의 .st(장식 ☆)와
    빌드의 .st(선택됨)를 견주고 "저대비 요소에 글이 늘었다" 고 했다 - 두
    설계의 .st 는 아무 관계가 없다.
    """
    assert d_newdesign["metrics"]["low_contrast_gained_text"] == 0
    assert [w for w in warnings_of(d_newdesign, "D")
            if "gained" in w["detail"]] == [], details(d_newdesign["warning"])


def test_the_count_comparison_stands_down_with_its_reason(d_newdesign):
    """하지 않은 비교는 조용히 사라지면 안 된다 - 이유를 적는다."""
    down = stood_down(d_newdesign, "D")
    assert len(down) == 2, down
    assert any("저명암 개수" in s for s in down)
    assert any("gained-text" in s for s in down)
    assert d_newdesign["metrics"]["low_contrast_before"] is None
    assert d_newdesign["metrics"]["low_contrast_after"] == 2


def test_the_new_design_page_has_nothing_else_wrong(d_newdesign):
    """이 페이지의 저대비 요소는 둘이다 - 색을 물려받은 것과 별표 자리의 것.
    기준 미달은 하나씩 적으므로 경고도 둘이고, 그 둘뿐이어야 한다."""
    assert len(warnings_of(d_newdesign, "D")) == 2, details(d_newdesign["warning"])
    assert d_newdesign["fatal"] == [], details(d_newdesign["fatal"])


# ===================================================================== #
# 8. 검사 H·G 가 @media·@supports·@layer 안의 규칙을 보지 않는다
# ===================================================================== #
@pytest.fixture(scope="module")
def hg_nested(server):
    return run_audit("hg_nested.json", "hg_nested.html",
                     orig_page="hg_nested_orig.html")


def test_classes_defined_inside_nested_blocks_are_defined(hg_nested):
    """@media · @supports · @layer 안에서 정의한 클래스도 정의된 것이다.

    고치기 전: H 경고 3건. cssRules 를 한 겹만 돌아서 조건 블록은 "선택자가
    없는 규칙" 으로 지나쳐졌고, 멀쩡한 클래스 셋이 전부 "아무 스타일시트도
    정의하지 않는다" 로 걸렸다.
    """
    assert warnings_of(hg_nested, "H") == [], details(hg_nested["warning"])
    assert hg_nested["metrics"]["undefined_classes_new"] == []


def test_state_pairs_inside_nested_blocks_are_checked(hg_nested):
    """조건 블록 안의 `.x.on` 도 상태 쌍이다.

    고치기 전: 짝을 집어 들지 못해 state_pairs_checked 가 1 (`.screen.on` 하나)
    이었다. 고른 칩이 안 고른 칩과 똑같이 보여도 검사 G 는 할 말이 없었다.
    """
    assert hg_nested["metrics"]["state_pairs_checked"] == 2
    hit = warnings_of(hg_nested, "G")
    assert len(hit) == 1, details(hg_nested["warning"])
    assert hit[0]["base"] == ".chip"
    assert hit[0]["state"] == "on"


def test_the_nested_page_has_nothing_else_wrong(hg_nested):
    assert hg_nested["fatal"] == [], details(hg_nested["fatal"])
    assert len(hg_nested["warning"]) == 1, details(hg_nested["warning"])


# ===================================================================== #
# 9. 검사 E 가 줄 수를 상자 높이로 센다
# ===================================================================== #
@pytest.fixture(scope="module")
def e_lines(server):
    return drive_and_audit("e_lines.json", "e_lines_build.html",
                           orig_page="e_lines_orig.html")


def wrapped_of(res, screen="start"):
    return {x["cls"]: x["lines"] for x in res["rep"]["screens"][screen]["wrapped"]}


def test_padding_does_not_make_a_second_line(e_lines):
    """위아래 여백이 붙은 한 줄은 한 줄이다.

    고치기 전: 상자 높이(getBoundingClientRect)를 줄 높이로 나눴다. 여백과
    테두리가 그 높이에 들어 있으므로, 여백 14px 만 붙은 한 줄이 두 줄로 읽혀
    "전에는 줄바꿈이 없었는데 이제 생겼다" 는 거짓 경보가 났다.
    """
    assert "padded" not in wrapped_of(e_lines)
    assert [w for w in e_lines["report"]["warning"]
            if w.get("check") == "E" and "padded" in (w["detail"] or "")] == []


def test_text_that_really_wraps_is_still_counted(e_lines):
    """정말로 넘어간 줄은 그대로 센다 - 여백을 빼기 시작했다고 진짜 줄바꿈까지
    놓치면 검사를 끈 것이다."""
    assert wrapped_of(e_lines)["long"] == 2
    hit = [w for w in e_lines["report"]["warning"]
           if w.get("check") == "E" and w.get("lines")]
    assert len(hit) == 1, details(e_lines["report"]["warning"])
    assert hit[0]["lines"] == 2
    assert e_lines["report"]["metrics"]["newly_wrapped_text"] == 1


def test_the_lines_page_has_nothing_else_wrong(e_lines):
    assert e_lines["report"]["fatal"] == [], details(e_lines["report"]["fatal"])
    assert len(e_lines["report"]["warning"]) == 1, \
        details(e_lines["report"]["warning"])


# ===================================================================== #
# 10. 걷기가 전환을 고정 시간만 기다린다
# ===================================================================== #
@pytest.fixture(scope="module")
def drive_slow(server):
    return run_audit("drive_slow.json", "drive_slow.html")


def test_a_slow_transition_is_waited_for(drive_slow):
    """1.2초 걸리는 전환은 결함이 아니다 - 조회를 기다리는 설계에 흔한 일이다.

    고치기 전: 누른 뒤 0.45초만 기다리고 긁었다. 아직 앞 화면에 서 있으므로
    "landed on 'start' instead" 와 "#amt is missing" 두 건이 났다 - 둘 다
    거짓 경보다.
    """
    assert drive_slow["fatal"] == [], details(drive_slow["fatal"])
    assert drive_slow["passed"] is True
    assert drive_slow["metrics"]["screens_landed_on"]["done"] == {
        "hook": "done", "dom": "done"}


@pytest.fixture(scope="module")
def drive_dialog_late(server):
    return run_audit("drive_dialog_late.json", "drive_dialog_late.html")


def test_a_dialog_raised_as_the_walk_ends_is_still_caught(drive_dialog_late):
    """마지막 화면에 도착한 뒤 0.12초 늦게 뜨는 alert 도 길을 막는 대화상자다.

    고치기 전: fatal 0건. 걷기가 끝나자마자 브라우저를 닫으므로 대화상자가
    아예 뜨지 못했다. 닫는 동안에는 타이머가 돌지 않는다 - 노출된 틈은 마지막
    화면을 긁은 뒤 20ms 쯤이다 (측정).

    걷는 중에 뜨는 대화상자는 전에도 잡혔다. 대화상자가 뜨면 페이지의 JS 가
    멈추므로 다음 evaluate 가 끝나지 않고 그 사이에 처리기가 돈다.
    """
    hit = [f for f in fatals(drive_dialog_late, "B") if "blocking" in f["detail"]]
    assert len(hit) == 1, details(drive_dialog_late["fatal"])
    assert hit[0]["screen"] == "done"
    assert "보내기 결과를 확인하세요" in hit[0]["detail"]
    assert drive_dialog_late["metrics"]["dialogs_during_task"] == 1


# ===================================================================== #
# 11. 같은 화면을 두 번 지나면 두 번째 방문이 첫 번째를 덮어쓴다
# ===================================================================== #
@pytest.fixture(scope="module")
def visit_twice(server):
    return drive_and_audit("visit_twice.json", "visit_twice.html")


def test_each_visit_is_kept_in_order(visit_twice):
    """방문은 순서대로 남는다 - 첫 방문은 화면 이름 그대로, 그다음은 `#2`."""
    assert list(visit_twice["rep"]["screens"]) == ["start", "detail",
                                                   "start#2", "done"]
    assert visit_twice["report"]["metrics"]["screens_in_flow"] == [
        "start", "detail", "start#2", "done"]


def test_the_first_visit_is_not_overwritten_by_the_second(visit_twice):
    """첫 방문의 틀린 금액은 사용자가 실제로 본 것이다.

    고치기 전: 두 번째 방문이 `screens['start']` 를 덮어썼다. 돌아왔을 때는
    금액이 고쳐져 있으므로 검사 B 는 통과했다 - 사용자가 틀린 값을 보고 지나간
    화면이 아무도 보지 못한 일이 됐다.
    """
    hit = [f for f in fatals(visit_twice["report"], "B")
           if f.get("selector") == "#amt"]
    assert len(hit) == 1, details(visit_twice["report"]["fatal"])
    assert hit[0]["screen"] == "start"
    assert hit[0]["got"] == "9,000원"


def test_the_second_visit_passes_on_its_own(visit_twice):
    """두 번째 방문은 고쳐진 값을 보여 준다 - 방문마다 따로 판정한다."""
    assert [f for f in fatals(visit_twice["report"], "B")
            if f.get("screen") == "start#2"] == []
    assert len(visit_twice["report"]["fatal"]) == 1, \
        details(visit_twice["report"]["fatal"])


# ===================================================================== #
# 12. 새 설계에서 기준 미달 대비를 아무도 말하지 않는다
# ===================================================================== #
@pytest.fixture(scope="module")
def d_below(server):
    return drive_and_audit("d_below.json", "d_below.html")


@pytest.fixture(scope="module")
def d_below_derived(server):
    return run_audit("d_below_derived.json", "d_below.html")


def test_text_under_the_threshold_is_warned_one_by_one(d_below):
    """3.25:1 짜리 안내문은 4.5:1 이 필요하다 - 읽을 수 없는 글이다.

    고치기 전: warning 0건. 새 설계에서는 개수의 전후 비교가 물러나고 그 자리에
    아무 말도 남지 않았으므로, 기준 미달인 글자가 조용히 통과했다.
    """
    hit = [w for w in warnings_of(d_below["report"], "D")
           if w.get("ratio") and "흐린 안내문" in w["detail"]]
    assert len(hit) == 1, details(d_below["report"]["warning"])
    w = hit[0]
    assert w["screen"] == "start"
    assert w["tag"] == "p"
    assert 3.0 < w["ratio"] < 3.5
    assert w["need"] == 4.5
    assert w["color"] == "rgb(138, 143, 152)"
    assert w["bg"] == "rgb(255, 255, 255)"


def test_the_threshold_is_kept_per_element(d_below):
    """같은 색의 26px 큰 글씨는 3.0:1 만 넘으면 된다 - 같은 3.25:1 로 통과한다.
    요소마다 경계를 지키지 않으면 멀쩡한 큰 글씨까지 잡는다."""
    assert [w for w in warnings_of(d_below["report"], "D")
            if "큰 글씨" in w["detail"]] == [], details(d_below["report"]["warning"])
    assert texts_of(contrast_of(d_below)) == ["물려받은 색입니다", "흐린 안내문입니다"]


def test_an_unreadable_inherited_colour_is_one_warning_not_two(d_below):
    """자기 색이 없어서 읽히지 않는 글자는 결함 하나다. 기준 미달 경고와 상속
    경고를 따로 내면 결함 하나가 경고 둘이 된다 - 상속이라는 사실을 그 경고에
    함께 담는다."""
    hit = [w for w in warnings_of(d_below["report"], "D")
           if "물려받은 색" in w["detail"]]
    assert len(hit) == 1, details(d_below["report"]["warning"])
    assert hit[0]["inherited"] is True
    assert "색을 정해 주는 규칙이 없다" in hit[0]["detail"]
    assert d_below["report"]["metrics"]["inherited_colour_unreadable"] == 1
    assert len(warnings_of(d_below["report"], "D")) == 2, \
        details(d_below["report"]["warning"])


def test_a_derived_build_is_unchanged(d_below_derived):
    """원본에서 파생된 빌드의 동작은 바뀌지 않는다. 같은 페이지를 원본으로도
    쓰면 전후 비교는 아무것도 찾지 못하고, 요소별 경고도 나지 않는다 - 그
    경고는 비교가 물러난 자리를 메우는 것이기 때문이다."""
    assert warnings_of(d_below_derived, "D") == [], \
        details(d_below_derived["warning"])
    assert d_below_derived["metrics"]["low_contrast_before"] == 2
    assert d_below_derived["metrics"]["low_contrast_after"] == 2
    assert d_below_derived["metrics"]["new_inherited_colour"] == 0
    assert d_below_derived["fatal"] == [], details(d_below_derived["fatal"])
