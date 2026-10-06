r"""공과금 원본(inputs/original_bill.html)을 흐름 파일대로 브라우저로 걷는다.
`pytest -m browser` 로만 돈다.

  흐름대로 끝까지   flows/original_bill.json 의 steps 를 한 걸음씩 걷고, 걸음마다
                    __screen() 과 켜진 화면이 기대 화면인지, expect 의 값이 보이는지
  오류 경로         흐름의 error_paths 를 걷는다. Flutter 더미앱의 공과금 경로에는
                    오류 팝업이 없어 지금은 빈 목록이다 - 그것도 확인한다
  메뉴에서 바로     steps 는 검색을 거친다 (화면 덮기 규칙). 메뉴 목록에서 바로
                    납부하기로 가는 길은 여기서 따로 걷는다
  뒤로 · 닫기       Flutter 의 maybePop · 바꿔치기를 따른 목적지 (기본 규칙의 예외)
  범위 밖           눌러도 아무 일도 하지 않는다

검사기 코드와 같은 걸음 규칙(click · do · type · repeat · wait)을 여기서 짧게 다시
쓴다. 테스트는 senior_ui 를 직접 부르지 않고 _api 만 거치는데, 걸음 함수는 _api
가 내보내지 않는다.

  .\.venv\Scripts\python.exe -m pytest -m browser tests/test_original_bill.py
"""
import io
import json
import os
import time

import pytest
from playwright.sync_api import sync_playwright

import _api
import capture_baseline as C

pytestmark = pytest.mark.browser

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REL = "inputs/original_bill.html"
FLOW = os.path.join(ROOT, "flows", "original_bill.json")
URL = "%s/%s" % (C.BASE_URL, REL)


def load_flow():
    return _api.load_flow(FLOW)


def fill(s, truth):
    for k, v in truth.items():
        s = s.replace("{%s}" % k, v)
    return s


@pytest.fixture(scope="module")
def browser(server):
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
    p.goto(URL, wait_until="networkidle")
    p.js_errors = js_errors
    yield p
    assert js_errors == []
    p.close()


def screen(page):
    return page.evaluate("() => window.__screen()")


def lit(page):
    return page.evaluate(
        "() => [...document.querySelectorAll('.screen.on')].map(s => s.dataset.screen)")


def wait_screen(page, name, timeout=3.0):
    """__screen() 과 켜진 화면이 둘 다 name 이 될 때까지 기다린다."""
    end = time.time() + timeout
    while time.time() < end:
        if screen(page) == name and lit(page) == [name]:
            return True
        page.wait_for_timeout(50)
    return False


def act(page, spec, truth):
    """흐름 파일의 걸음 하나 (drive.run_actions 와 같은 규칙)."""
    items = spec if isinstance(spec, list) else [spec]
    for item in items:
        if "type" in item:
            value, key = fill(item["type"], truth), item["key"]
            if "%s" in key:
                for ch in value:
                    page.click(key % ch)
            else:
                page.fill(key, value)
        elif "repeat" in item:
            for _ in range(item["repeat"]):
                page.click(fill(item["click"], truth))
                page.wait_for_timeout(int(item.get("wait", 0) * 1000))
        elif "click" in item:
            page.click(fill(item["click"], truth))
        elif "wait" in item:
            page.wait_for_timeout(int(item["wait"] * 1000))


def step_spec(step):
    return step["do"] if "do" in step else (
        {"click": step["click"]} if "click" in step else [])


def walk_to(page, flow, last):
    """steps 를 처음부터 `last` 화면까지 걷는다."""
    for step in flow["steps"]:
        act(page, step_spec(step), flow["truth"])
        assert wait_screen(page, step["screen"]), (step["screen"], screen(page), lit(page))
        if step["screen"] == last:
            return
    raise AssertionError("steps 에 %r 가 없다" % last)


def click(page, sel, then):
    page.click(sel)
    assert wait_screen(page, then), (sel, then, screen(page), lit(page))


# --------------------------------------------------------------------- #
# 흐름 파일대로 끝까지
# --------------------------------------------------------------------- #
def test_flow_walks_every_step_to_done(page):
    flow = load_flow()
    truth = flow["truth"]
    names = [s["screen"] for s in flow["steps"]]
    assert names == ["home", "menu", "search", "bill-home", "camera",
                     "info", "password", "done"]
    missing = page.evaluate("ids => ids.filter(i => !document.getElementById(i))",
                            flow["required_ids"])
    assert missing == []
    assert wait_screen(page, "home")
    for step in flow["steps"][1:]:
        act(page, step_spec(step), truth)
        assert wait_screen(page, step["screen"]), (step["screen"], screen(page))
        for sel, want in flow["expect"].get(step["screen"], []):
            got = page.inner_text(sel).strip()
            assert got == fill(want, truth), (sel, got)
    kinds = [e["type"] for e in page.evaluate("() => window.__dump()")]
    assert "submit" in kinds


def test_every_screen_is_walked(page):
    """화면 덮기 규칙: 모든 화면은 정답 경로나 오류 경로 중 하나가 지나간다."""
    flow = load_flow()
    sections = set(page.evaluate(
        "() => [...document.querySelectorAll('section.screen')].map(s => s.dataset.screen)"))
    walked = {s["screen"] for s in flow["steps"]}
    walked |= {e["expect_screen"] for e in flow["error_paths"]}
    assert sections == walked


def test_done_confirm_returns_home(page):
    flow = load_flow()
    walk_to(page, flow, "done")
    click(page, "[data-screen='done'] .btn-primary", "home")
    assert page.evaluate("() => window.__dump().some(e => e.type === 'task_end')")


# --------------------------------------------------------------------- #
# 오류 경로
# --------------------------------------------------------------------- #
def test_error_paths(browser):
    """흐름의 오류 경로마다: from_step 까지 걷고, 틀린 입력을 넣으면 오류 화면이
    뜨고, recover 를 누르면 back_to 로 돌아간다. 더미앱 공과금 경로에는 오류
    팝업이 없으므로(비밀번호도 판정하지 않는다) 지금은 빈 목록이고, 원본에도
    오류 화면이 없다."""
    flow = load_flow()
    assert flow["error_paths"] == []
    for ep in flow["error_paths"]:
        page = browser.new_page(viewport={"width": 390, "height": 844})
        try:
            page.goto(URL, wait_until="networkidle")
            walk_to(page, flow, ep["from_step"])
            act(page, ep["inputs"], flow["truth"])
            assert wait_screen(page, ep["expect_screen"]), ep["id"]
            act(page, ep["recover"], flow["truth"])
            assert wait_screen(page, ep["back_to"]), ep["id"]
        finally:
            page.close()


def test_no_error_popup_on_the_path(page):
    """비밀번호는 어떤 4자리도 통과한다 (Flutter: 실제 검증은 없다)."""
    flow = load_flow()
    walk_to(page, flow, "password")
    for _ in range(4):
        page.click("#pwpad [data-action='pw'][data-v='0']")
    assert wait_screen(page, "done")
    assert not page.evaluate(
        "() => window.__dump().some(e => e.type === 'error_popup')")


# --------------------------------------------------------------------- #
# 메뉴에서 바로 가는 길
# --------------------------------------------------------------------- #
def test_direct_menu_route(page):
    """홈 → 전체메뉴 → [은행] 탭 → [세금/공과금] 칩 → 납부하기 → … → 완료."""
    click(page, "[data-action='go-menu']", "menu")
    page.click("[data-action='menu-tab'][data-tab='은행']")
    page.click("[data-action='menu-chip'][data-chip='은행::세금/공과금']")
    page.wait_for_timeout(100)
    assert page.is_visible("[data-action='menu-item'][data-item='납부하기']")
    click(page, "[data-action='menu-item'][data-item='납부하기']", "bill-home")
    # 메뉴에서 들어왔으니 ‹ 는 메뉴로
    click(page, "[data-screen='bill-home'] [data-action='back-bill-home']", "menu")
    click(page, "[data-action='menu-item'][data-item='납부하기']", "bill-home")
    click(page, "[data-action='pay-start']", "camera")
    click(page, "[data-action='shutter']", "info")
    click(page, "[data-action='pay']", "password")
    for _ in range(4):
        page.click("#pwpad [data-action='pw']")
    assert wait_screen(page, "done")


def test_the_menu_is_scope_a(page):
    """범위 A (2026-10-06): 일곱 탭 전부 - docs/bill-menu-full.json 과 같은 순서."""
    full = json.load(io.open(os.path.join(ROOT, "docs", "bill-menu-full.json"),
                             encoding="utf-8"))
    want = [it for tab in full["tabs"] for sec in tab["sections"] for it in sec["items"]]
    assert len(want) == 293
    click(page, "[data-action='go-menu']", "menu")
    got = page.eval_on_selector_all("[data-action='menu-item']",
                                    "els => els.map(e => e.dataset.item)")
    assert got == want


def test_menu_tab_scrolls_to_its_category(page):
    click(page, "[data-action='go-menu']", "menu")
    page.click("[data-action='menu-tab'][data-tab='카드']")
    page.wait_for_timeout(100)
    assert page.is_visible("[data-action='menu-item'][data-item='전기 요금']")
    assert page.get_attribute(".mtab.act", "data-tab") == "카드"


# --------------------------------------------------------------------- #
# 뒤로 · 닫기 (기본 규칙의 예외)
# --------------------------------------------------------------------- #
def test_back_and_close_destinations(page):
    flow = load_flow()
    walk_to(page, flow, "bill-home")
    # 검색에서 들어왔으니 ‹ 는 검색으로, 검색어는 남아 있다
    click(page, "[data-screen='bill-home'] [data-action='back-bill-home']", "search")
    assert page.input_value("#search-input") == flow["truth"]["QUERY"]
    click(page, "[data-action='search-hit'][data-item='공과금납부']", "bill-home")
    click(page, "[data-action='pay-start']", "camera")
    # 촬영 ✕ → 세금/공과금 메인 (메인 아님)
    click(page, "[data-screen='camera'] [data-action='to-bill-home']", "bill-home")
    click(page, "[data-action='pay-start']", "camera")
    click(page, "[data-action='shutter']", "info")
    # 납부정보 ‹ → 세금/공과금 메인 (촬영은 바꿔치기로 사라졌다)
    click(page, "[data-screen='info'] [data-action='to-bill-home']", "bill-home")
    click(page, "[data-action='pay-start']", "camera")
    click(page, "[data-action='shutter']", "info")
    click(page, "[data-action='pay']", "password")
    # 비밀번호 ✕ → 납부정보
    click(page, "[data-action='close-password']", "info")
    # 검색 ‹ → 메뉴, 메뉴 ‹ → 홈
    click(page, "[data-screen='info'] [data-action='to-bill-home']", "bill-home")
    click(page, "[data-screen='bill-home'] [data-action='back-bill-home']", "search")
    click(page, "[data-action='back-menu']", "menu")
    click(page, "[data-screen='menu'] [data-action='back-home']", "home")


def test_done_home_icon_returns_home(page):
    flow = load_flow()
    walk_to(page, flow, "done")
    click(page, "[data-screen='done'] .navbar [data-action='finish']", "home")


# --------------------------------------------------------------------- #
# 범위 밖 · 검색
# --------------------------------------------------------------------- #
def test_out_of_scope_does_nothing(page):
    flow = load_flow()
    # 홈의 [이체] 는 이 과제에서 범위 밖
    page.click("[data-screen='home'] .btn-sm")
    assert wait_screen(page, "home")
    click(page, "[data-action='go-menu']", "menu")
    for item in ("계좌이체", "자동납부", "전기 요금"):
        page.click("[data-action='menu-item'][data-item='%s']" % item)
        assert wait_screen(page, "menu"), item
    page.click("[data-screen='menu'] .navbar .ico >> nth=1")       # 고객센터 채팅
    assert wait_screen(page, "menu")
    click(page, "[data-action='menu-item'][data-item='납부하기']", "bill-home")
    bills = page.eval_on_selector_all("[data-action='pick-bill']",
                                      "els => els.map(e => e.dataset.bill)")
    assert len(bills) == 18 and "전기요금/TV수신료" in bills
    for b in bills:
        page.click("[data-action='pick-bill'][data-bill='%s']" % b)
        assert wait_screen(page, "bill-home"), b
    page.click("[data-screen='bill-home'] .half >> nth=1")         # 조회하기
    page.click("[data-screen='bill-home'] .giro")                  # 지로번호 등록
    page.click("[data-screen='bill-home'] .navbar .ico >> nth=2")  # 홈 아이콘
    assert wait_screen(page, "bill-home")


def test_search_states(page):
    click(page, "[data-action='go-menu']", "menu")
    click(page, "[data-action='open-search']", "search")
    assert "찾으시는 메뉴를 입력해보세요" in page.inner_text("#search-body")
    page.fill("#search-input", "공")
    assert "검색버튼(돋보기)을" in page.inner_text("#search-body")
    assert page.query_selector("[data-action='search-hit']") is None
    assert page.is_visible("#search-clear")
    page.fill("#search-input", "전기")
    hits = page.eval_on_selector_all("[data-action='search-hit']",
                                     "els => els.map(e => e.dataset.item)")
    assert hits == ["전기 요금"]          # Flutter 와 같다 - 카드 탭의 항목 하나
    page.click("[data-action='search-hit'][data-item='전기 요금']")
    assert wait_screen(page, "search")    # 범위 밖
    page.fill("#search-input", "납부")
    hits = page.eval_on_selector_all("[data-action='search-hit']",
                                     "els => els.map(e => e.dataset.item)")
    # 범위 A: 카드 › 분할납부 까지 - Flutter 더미앱과 같다 (B 판에서는 빠졌다)
    assert hits == ["공과금납부", "납부하기", "자동납부", "납부내역 조회", "분할납부"]
    page.click("#search-clear")
    assert page.input_value("#search-input") == ""
    assert not page.is_visible("#search-clear")
    # 메뉴에서 다시 들어오면 검색어가 비어 있다
    page.fill("#search-input", "공과")
    click(page, "[data-action='back-menu']", "menu")
    click(page, "[data-action='open-search']", "search")
    assert page.input_value("#search-input") == ""


def test_password_keypad(page):
    flow = load_flow()
    walk_to(page, flow, "password")
    keys = lambda: page.eval_on_selector_all(  # noqa: E731
        "#pwpad [data-action='pw']", "els => els.map(e => e.dataset.v)")
    assert sorted(keys()) == list("0123456789")
    orders = {tuple(keys())}
    for _ in range(5):
        page.click("[data-action='pw-shuffle']")
        orders.add(tuple(keys()))
    assert len(orders) > 1                # 재배열하면 자리가 바뀐다
    page.click("#pwpad [data-action='pw'] >> nth=0")
    page.click("#pwpad [data-action='pw'] >> nth=0")
    assert page.eval_on_selector_all("#pw-dots i.fill", "els => els.length") == 2
    page.click("[data-action='pw-del']")
    assert page.eval_on_selector_all("#pw-dots i.fill", "els => els.length") == 1
    for _ in range(3):
        page.click("#pwpad [data-action='pw'] >> nth=0")
    assert wait_screen(page, "done")


def test_flow_file_shape():
    """9·9-2번 형식: truth 블록 · error_paths · 검사기가 읽는다."""
    raw = json.load(io.open(FLOW, encoding="utf-8"))
    assert raw["truth"]["AMOUNT"] == "2160"
    assert raw["truth"]["ENO"] == "1700000000"
    assert raw["truth"]["CUSTOMER"] == "홍길동"
    assert raw["task"] == "bill"
    # 이체에 맞춰 넣었던 이름은 걷어 냈다 (11번 단계)
    assert not {"ACCOUNT", "BANK", "NAME"} & set(raw["truth"])
    assert raw["done_amount"] == "#dn-paid"
    assert raw["error_paths"] == []
    assert not [k for k in raw["truth"] if k.endswith("_WRONG")]
    flow = load_flow()
    assert flow["truth"]["AMOUNT_SHOWN"] == "2,160"


def test_done_screen_fits_without_scrolling(page):
    """납부완료 화면은 실제 앱 캡처(더미앱 docs/screenshots/03_공과금납부/납부하기/6.png)
    처럼 안내 문구까지 스크롤 없이 다 보이고 [확인] 버튼과 겹치지 않는다.

    고치기 전: 행 간격이 넓고 "고객전용지정 계좌번호" 가 두 줄로 꺾여 본문이 넘쳤다.
    안내 문구가 스크롤 영역 아래로 잘려, 검사 E 는 그것을 [확인] 버튼과 61% 겹침으로
    적었다 - 원본에만 있는 문제는 재설계 모델이 가짜 문제로 진단한다."""
    flow = load_flow()
    walk_to(page, flow, "done")
    got = page.evaluate("""() => {
      const s = document.querySelector("[data-screen='done']");
      const body = s.querySelector('.body');
      const r = e => e.getBoundingClientRect();
      const labels = [...s.querySelectorAll('.kv .k')].map(e => r(e).height);
      return {scroll: body.scrollHeight - body.clientHeight,
              note_bottom: r(s.querySelector('.note')).bottom, body_bottom: r(body).bottom,
              button_top: r(s.querySelector('.btn-primary')).top,
              label_max: Math.max(...labels), label_min: Math.min(...labels)};
    }""")
    assert got["scroll"] <= 0, got
    assert got["note_bottom"] <= got["body_bottom"] <= got["button_top"], got
    assert got["label_max"] == got["label_min"], got        # 라벨이 꺾이지 않는다
