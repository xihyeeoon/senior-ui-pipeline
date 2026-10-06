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
from test_drive import server  # noqa: F401  (같은 서버 fixture 를 쓴다)

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
