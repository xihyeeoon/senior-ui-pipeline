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


def run_audit(flow_file, rep_page, orig_page=None, orig_flow_file=None,
              orig_html=None):
    """fixture 페이지를 실제로 걷고 audit() 을 돌려 리포트를 돌려준다.

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
    return _api.audit(orig, rep,
                      html_of_orig if orig_html is None else orig_html,
                      rep_html, flow)


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


def test_only_those_two_are_fatal(b_contains):
    """재현 페이지는 그 둘 말고는 아무 결함도 없어야 한다. 다른 fatal 이 섞이면
    위의 두 테스트가 무엇을 세고 있는지 알 수 없다."""
    assert len(b_contains["fatal"]) == 2, details(b_contains["fatal"])
    assert b_contains["warning"] == []


def test_decoration_only_differences_still_pass(b_decorated):
    """'10,000원' 과 '3333-0000-0000-0' 은 과제가 넣은 값 그대로다.

    고치기 전: 하이픈이 든 계좌는 "포함" 비교에서도 떨어졌다 - 거짓 통과를
    고치는 김에 이 거짓 실패도 같이 사라져야 한다.
    """
    assert fatals(b_decorated, "B") == [], details(b_decorated["fatal"])
    assert b_decorated["passed"] is True, details(b_decorated["fatal"])


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

