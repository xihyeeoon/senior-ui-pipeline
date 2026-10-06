r"""보기(see) 찍기와 펼치기(reveal)를 브라우저로 실제로 걷는다. `pytest -m browser` 로만 돈다.

  잘라 찍기      스크롤되는 화면을 맨 위부터 창 높이씩 잘라 찍는다 (화면 안의
                 스크롤 · 문서 스크롤 둘 다). 화면당 최대 4장, 남은 높이를 적는다.
                 다 찍은 뒤 스크롤 위치를 되돌린다.
  기본은 꺼짐    see 를 주지 않은 걷기는 전과 같다 (see/ 폴더가 없다).

  .\.venv\Scripts\python.exe -m pytest -m browser tests/test_visual_refine_browser.py
"""
import asyncio
import json
import os
import struct

import pytest
from playwright.async_api import async_playwright

import _api
import capture_baseline as C

pytestmark = pytest.mark.browser

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = "tests/fixtures/pages/see_scroll.html"
FLOW = os.path.join(HERE, "fixtures", "pages", "see_scroll.json")


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24])


def drive(tmp_path, **kw):
    flow = _api.load_flow(FLOW)
    return asyncio.run(_api.drive("%s/%s" % (C.BASE_URL, PAGE), flow,
                                  want_shots=str(tmp_path), **kw))


def test_see_slices_every_scrolling_screen_from_the_top(server, tmp_path):
    drive(tmp_path, see=True)
    index = json.load(open(os.path.join(tmp_path, "see", "index.json"), encoding="utf-8"))
    by = {}
    for item in index:
        by.setdefault(item["visit"], []).append(item)
    # 넘치지 않는 화면은 한 장
    assert [i["part"] for i in by["short"]] == [1] and by["short"][0]["more_px"] == 0
    # 화면 안에서 3,400 - (844 - 버튼 줄) 만큼 넘친다 - 4장에서 끊고 남은 높이를 적는다
    inner = by["inner"]
    assert [i["part"] for i in inner] == [1, 2, 3, 4]
    assert all(i["parts"] == 4 for i in inner)
    assert inner[-1]["more_px"] > 0 and all(i["more_px"] == 0 for i in inner[:-1])
    # 문서 스크롤도 잘라 찍는다
    assert len(by["page"]) >= 2
    for item in index:
        path = os.path.join(tmp_path, "see", item["file"])
        assert png_size(path) == (390, 844), item
    # 검사기가 찍던 그림은 그대로 있다
    assert os.path.exists(os.path.join(tmp_path, "audit_inner.png"))


def test_without_see_the_walk_takes_only_its_old_shots(server, tmp_path):
    drive(tmp_path)
    assert not os.path.exists(os.path.join(tmp_path, "see"))
    assert os.path.exists(os.path.join(tmp_path, "audit_inner.png"))


def test_see_puts_the_scroll_back_where_it_was(server, tmp_path):
    """inner 는 들어가면 300px 내려가 있다. 첫 장은 맨 위에서 찍고, 다 찍은
    뒤에는 300px 로 되돌린다 - 걷기의 다음 걸음이 보는 상태를 바꾸지 않는다."""
    async def go():
        async with async_playwright() as pw:
            b = await pw.chromium.launch()
            try:
                p = await b.new_page(viewport={"width": 390, "height": 844})
                await p.goto("%s/%s" % (C.BASE_URL, PAGE))
                await p.click("[data-action='go-inner']")
                first = await _api.capture_see(p, str(tmp_path), "inner")
                top = await p.evaluate(
                    "() => document.getElementById('inner-body').scrollTop")
                marked = await p.evaluate(
                    "() => document.querySelectorAll('[data-see-scroller]').length")
                return first, top, marked
            finally:
                await b.close()
    items, top, marked = asyncio.run(go())
    assert top == 300
    assert marked == 0
    assert items[0]["file"] == "inner.1.png"


# --------------------------------------------------------------------------- #
# 펼치기 (reveal) - mock 실행을 끝까지
# --------------------------------------------------------------------------- #
def run_mock(mode, *extra):
    summary, code = C.run_mock(["--mock", mode, "--attempts", "1", "--refine", "0"]
                               + list(extra))
    report = json.load(open(summary["final"]["audit"], encoding="utf-8")) \
        if summary.get("final") else None
    return summary, code, report


def test_a_list_revealed_by_a_declared_click_passes(server):
    """은행 목록을 6개 + [전체 보기] 로 그린 설계. 흐름 명세의 reveal 에 그
    조작을 적었다 - 검사기가 따로 걸어 펼친 값을 센다."""
    summary, code, report = run_mock("reveal")
    assert code == 0 and summary["passed"], summary.get("stopped_reason")
    assert [f for f in report["fatal"] if f["check"] == "I"] == []
    rv = report["metrics"]["reveal"]["pick-bank"]
    assert rv["error"] is None and rv["values"] >= 67


def test_the_same_list_without_reveal_fails_check_i(server):
    summary, code, report = run_mock("reveal-undeclared")
    assert code == 1 and not summary["passed"]
    i = [f for f in report["fatal"] if f["check"] == "I"]
    assert i and "reveal" not in report["metrics"]


# --------------------------------------------------------------------------- #
# 감사 3. 펼치기 규칙 - 보이는 data-action · 켜진 화면 안 · 같은 화면
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("sel,why", [
    ("#inner-body", "data-action 요소가 아니다"),
    ("[data-action='go-end']", "켜진 화면 밖의 요소다"),
    ("#nothing", "선택자에 맞는 요소가 없다"),
    ("#to-page", "누른 뒤 화면이 바뀌었다 (inner → page)"),
])
def test_walk_reveal_stops_at_a_rule_violation(server, sel, why):
    flow = _api.load_flow(FLOW)

    async def go():
        async with async_playwright() as pw:
            b = await pw.chromium.launch()
            try:
                return await _api.walk_reveal(b, "%s/%s" % (C.BASE_URL, PAGE), flow,
                                              {"at": "inner", "do": [{"click": sel}]})
            finally:
                await b.close()
    row = asyncio.run(go())
    assert len(row["violations"]) == 1, row
    assert why in row["violations"][0]


# --------------------------------------------------------------------------- #
# 보고 다듬기 - mock 실행을 끝까지
# --------------------------------------------------------------------------- #
def test_the_improve_mock_changes_what_the_screens_look_like(server):
    """--mock-refine improve 의 다듬은 빌드는 눈에 보이게 달라야 한다 - 설명서의 전후
    표가 그 차이를 보이는지 확인하는 mock 이다."""
    summary, code = C.run_mock(["--mock", "pass", "--mock-refine", "improve",
                                "--delay", "0"])
    assert code == 0 and summary["refine"]["final_label"] == "다듬기 1회차"
    brief = open(summary["final"]["brief"], encoding="utf-8").read()
    assert "최종: 다듬기 1회차 (시도 2)" in brief
    assert "| 바뀜 |" in brief


def test_the_break_mock_reverts_to_the_passed_build(server):
    summary, code = C.run_mock(["--mock", "pass", "--mock-refine", "break",
                                "--delay", "0"])
    assert code == 0 and summary["passed"] and summary["final"]["attempt"] == 1
    assert summary["refine"]["reverted"]["failed_attempts"] == [2, 3]
    brief = open(summary["final"]["brief"], encoding="utf-8").read()
    assert "최종: 생성 (다듬기 1회차가 실패해 되돌림) · 시도 1" in brief
