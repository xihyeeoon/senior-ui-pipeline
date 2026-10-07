r"""원본 이체의 계좌번호 화면 - 키패드는 입력란을 눌러야 열린다 (11-11).

실제 앱과 더미앱 A1(senior-ui-dummy-app 4cd2179, 병합 82d44ed)은 계좌번호 화면에
들어오면 키패드가 닫혀 있고, 계좌번호 입력란을 눌러야 열린다. 원본 HTML 은 입력 중
캡처 한 장을 "늘 떠 있는 것" 으로 읽어 처음부터 키패드를 띄우고 있었다.

  - 들어오면 #acc-pad 가 보이지 않는다. [다음] 은 맨 아래 그대로
  - 입력란(#acc-field, data-action="acc-field")을 누르면 키패드가 그 자리 · 모양으로 열린다
  - 한 번 열리면 이 화면에 있는 동안 열려 있다 - 은행 시트 · 오류 팝업 · 금액 화면의 ‹
    뒤에도. 받는 사람에서 다시 들어오면 닫힌 채로 시작한다
  - 숨어 있어도 acc-num 버튼은 DOM 에 있다 - 검사 I 의 원본 선택지(acc-num 10)는 그대로

흐름(flows/original.json)은 이 전환을 걸음으로 적는다 - account 다음 걸음이 입력란
누르기(방문 이름 account#2)이고, 오류 경로 둘도 숫자를 넣기 전에 입력란을 누른다.

  .\.venv\Scripts\python.exe -m pytest tests/test_account_keypad.py
  .\.venv\Scripts\python.exe -m pytest -m browser tests/test_account_keypad.py
"""
import io
import json
import os
import re
import time

import pytest

import _api
import capture_baseline as C

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ORIGINAL = os.path.join(ROOT, *C.ORIGINAL_REL.split("/"))
FLOW = os.path.join(ROOT, "flows", "original.json")

FIELD = "[data-action='acc-field']"
STATE = "키패드 열림 — 계좌번호 입력란을 누른 뒤"


def html():
    return io.open(ORIGINAL, encoding="utf-8").read()


def raw_flow():
    return json.load(io.open(FLOW, encoding="utf-8"))


# --------------------------------------------------------------------- #
# 원본 HTML (브라우저 없음)
# --------------------------------------------------------------------- #
def test_the_account_field_is_the_only_new_hook():
    """입력란에 data-action 하나만 더한다. 처리기에 그 분기가 있다 (검사 C).

    원본은 스크린샷의 대역이다 - 화면에 없는 정보(data-role 같은 것)를 넣지 않는다.
    data-* 는 기술 계약의 것(화면 이름 · 동작 · 선택지 값 · 빈 칸 글자)만 쓴다."""
    text = html()
    field = re.search(r'<div class="accfield"[^>]*>', text).group(0)
    assert 'id="acc-field"' in field and 'data-action="acc-field"' in field
    assert "a==='acc-field'" in text
    assert set(re.findall(r"\bdata-([a-z-]+)=", text)) == {
        "screen", "action", "v", "bank", "empty"}


# --------------------------------------------------------------------- #
# 흐름 (브라우저 없음)
# --------------------------------------------------------------------- #
def test_the_flow_taps_the_field_right_after_arriving():
    """정상 경로: account 도착 바로 뒤에 입력란 누르기 (account#2). 그 뒤는 그대로."""
    flow = raw_flow()
    steps = flow["steps"]
    assert [s["screen"] for s in steps] == [
        "home", "recipient", "account", "account", "bank", "amount", "confirm",
        "password", "done"]
    assert _api.flow_module.visit_keys(steps)[3] == "account#2"
    assert steps[3] == {"screen": "account", "click": FIELD, "state": STATE}
    # 전환을 연구자가 적는 칸은 그 걸음 하나에만 있다
    assert [i for i, s in enumerate(steps) if "state" in s] == [3]


def _first(items, pred):
    return next(i for i, it in enumerate(items) if pred(it))


def test_error_paths_tap_the_field_before_typing_digits():
    """오류 경로도 숫자를 넣기 전에 입력란을 누른다 - 정답 경로가 이미 열어 두었어도
    오류 경로 하나만 읽어서 무엇을 누르는지 알 수 있게."""
    for ep in raw_flow()["error_paths"]:
        inputs = ep["inputs"]
        tap = _first(inputs, lambda it: it.get("click") == FIELD)
        digits = _first(inputs, lambda it: "acc-num" in it.get("key", ""))
        assert tap < digits, ep["id"]
        # 오류를 일으키는 마지막 동작은 그대로다 (검사 J 의 trigger)
        assert "click" in inputs[-1] and inputs[-1]["click"] != FIELD


def test_required_ids_name_both_ends_of_the_transition():
    """전환의 두 끝 - 누르는 입력란과 열리는 키패드 - 은 이 문서를 고친 빌드가
    지켜야 할 id 다."""
    req = raw_flow()["required_ids"]
    assert "acc-field" in req and "acc-pad" in req
    for i in req:
        assert 'id="%s"' % i in html(), i


# --------------------------------------------------------------------- #
# 브라우저 - 원본을 실제로 누른다
# --------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def browser(server):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        try:
            yield b
        finally:
            b.close()


@pytest.fixture
def page(browser):
    p = browser.new_page(viewport={"width": 390, "height": 844})
    js_errors = []
    p.on("pageerror", lambda e: js_errors.append(str(e)))
    p.goto("%s/%s" % (C.BASE_URL, C.ORIGINAL_REL), wait_until="networkidle")
    yield p
    assert js_errors == []
    p.close()


def wait_screen(page, name, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if page.evaluate("() => window.__screen()") == name and page.evaluate(
                "() => document.querySelector('.screen.on').dataset.screen") == name:
            return True
        page.wait_for_timeout(50)
    return False


def click(page, sel, then):
    page.click(sel)
    assert wait_screen(page, then), (sel, then)


def pad_shown(page):
    return page.is_visible("#acc-pad")


def rect(page, sel):
    return page.eval_on_selector(sel, "e => { const r = e.getBoundingClientRect();"
                                      " return [r.x, r.y, r.width, r.height]; }")


def to_account(page):
    click(page, "[data-action='go-recipient']", "recipient")
    click(page, "[data-action='go-account']", "account")


def type_account(page, digits):
    for d in digits:
        page.click("[data-action='acc-num'][data-v='%s']" % d)


def pick_bank(page, bank):
    click(page, "[data-action='open-bank']", "bank")
    click(page, "[data-action='pick-bank'][data-bank='%s']" % bank, "account")


def value(page):
    return page.inner_text("#acc-input").strip()


@pytest.mark.browser
def test_keypad_is_closed_on_entry_and_opens_on_the_field(page):
    to_account(page)
    assert not pad_shown(page)
    # 숨어 있어도 계좌 숫자판 열 개는 DOM 에 있다 (검사 I 는 DOM 에서 모은다)
    assert page.eval_on_selector_all("[data-action='acc-num']", "es => es.length") == 10
    nxt = rect(page, "#acc-next")
    assert nxt[1] + nxt[3] + 18 == 844          # [다음] 은 맨 아래 (margin-bottom 18)

    page.click(FIELD)
    assert pad_shown(page)
    assert wait_screen(page, "account")          # 같은 화면이다
    assert rect(page, "#acc-next") == nxt        # 키패드가 열려도 [다음] 자리는 그대로
    pad = rect(page, "#acc-pad")
    # 예전과 같은 자리 · 모양 - [다음] 바로 위, 폭 가득, 66px 네 줄
    assert pad[0] == 0 and pad[2] == 390 and pad[3] == 4 * 66
    assert pad[1] + pad[3] + 10 == nxt[1]        # [다음] 의 margin-top 10
    type_account(page, "12")
    assert value(page) == "12"


@pytest.mark.browser
def test_keypad_stays_open_across_the_bank_sheet_and_the_error_popup(page):
    to_account(page)
    page.click(FIELD)
    type_account(page, "12")
    # 시트를 ✕ 로 닫아도, 은행을 골라 닫아도 열려 있다
    click(page, "[data-action='open-bank']", "bank")
    click(page, "[data-action='close-bank']", "account")
    assert pad_shown(page)
    pick_bank(page, "신한")
    assert pad_shown(page) and value(page) == "12"
    # 틀린 계좌 → ELB00016 → [확인] - 그 전 상태(키패드 열림 · 입력값) 그대로
    click(page, "#acc-next", "err-account")
    click(page, "[data-screen='err-account'] .ebtn", "account")
    assert pad_shown(page) and value(page) == "12"
    # 팝업 바깥(덮개의 위쪽 모서리 - 가운데는 팝업이 덮는다)을 눌러 닫아도 같다
    click(page, "#acc-next", "err-account")
    page.click("[data-screen='err-account'] .dimmer", position={"x": 10, "y": 10})
    assert wait_screen(page, "account")
    assert pad_shown(page)


@pytest.mark.browser
def test_keypad_stays_open_when_coming_back_from_amount(page):
    """금액 화면의 ‹ 는 계좌 화면을 다시 만들지 않는다 (Flutter maybePop) - 그대로다."""
    to_account(page)
    page.click(FIELD)
    type_account(page, "110234567890")
    pick_bank(page, "신한")
    click(page, "#acc-next", "amount")
    click(page, "[data-action='back-account']", "account")
    assert pad_shown(page) and value(page) == "110234567890"


@pytest.mark.browser
@pytest.mark.parametrize("leave", ["back-recipient", "close-account"])
def test_keypad_is_closed_again_on_reentry(page, leave):
    to_account(page)
    page.click(FIELD)
    assert pad_shown(page)
    click(page, "[data-action='%s']" % leave, "recipient")
    click(page, "[data-action='go-account']", "account")
    assert not pad_shown(page)

# 흐름대로 원본을 걸었을 때(account 닫힘 · account#2 열림 · acc-num 10 · 오류 경로 둘)는
# test_error_paths_browser.test_original_vs_original_walks_both_error_paths 가 본다 -
# drive 는 asyncio 이고, 이 파일의 sync 브라우저와 한 스레드에서 함께 돌 수 없다.
