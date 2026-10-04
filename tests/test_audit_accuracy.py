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
