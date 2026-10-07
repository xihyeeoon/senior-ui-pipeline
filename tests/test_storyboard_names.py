r"""설계서의 X 상자에 그림 자리의 이름을 보인다 (11-11 1-2).

원본은 로고 · 아이콘을 이름 붙은 그림 자리(role="img" + aria-label)로 둔다. 설계서의 로우파이
덮개는 그런 자리를 X 가 그어진 회색 상자로 그리는데, 무슨 그림인지 보이지 않았다. 이제 상자
안에 "[X] <aria-label>" 를 글로 보인다 - "[X] 신한 로고".

덮개 CSS 는 배치를 바꾸는 속성을 하나도 쓰지 않는다 (test_storyboard 의 LAYOUT_PROPS). 그래서
이름은 CSS 가 아니라 깨끗한 그림을 찍기 직전에 얹는 겹침 층(NAMES_ON)이고, 찍은 뒤 걷어낸다
(NAMES_OFF) - 번호 그림의 MARK_ON 과 같은 방식. 요소 목록(ELEMENTS)을 읽은 뒤에 얹으므로
요소 값에 섞이지 않는다.

  .\.venv\Scripts\python.exe -m pytest tests/test_storyboard_names.py
  .\.venv\Scripts\python.exe -m pytest -m browser tests/test_storyboard_names.py
"""
import asyncio
import io
import os
import pathlib

import pytest

import _api

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures", "storyboard", "pictures.html")
SLOT_IDS = ("big", "mid", "small", "clipped")


def walk_module():
    return _api.storyboard_walk


def test_the_names_are_an_overlay_not_cover_css():
    """덮개 CSS 는 그대로다 - 이름은 그 CSS 에 없다. 이름 층은 aria-label 을 읽고 "[X] " 를
    앞에 붙이며, 걷어내는 조각이 따로 있다."""
    w = walk_module()
    assert "aria-label" not in w.WIRE_CSS and w.NAME_PREFIX not in w.WIRE_CSS
    assert w.NAME_PREFIX == "[X] "
    assert "aria-label" in w.NAMES_ON and "sb-name-layer" in w.NAMES_ON
    assert "sb-name-layer" in w.NAMES_OFF
    assert w.NAME_OPTIONS["min_px"] <= w.NAME_OPTIONS["max_px"]


RECTS = r"""(ids) => ids.map(i => { const r = document.getElementById(i).getBoundingClientRect();
  return [r.x, r.y, r.width, r.height]; })"""


async def _wired(tmp_path):
    from playwright.async_api import async_playwright
    w = walk_module()
    wired = tmp_path / "pictures.wire.html"
    wired.write_text(w.wire_copy(io.open(FIX, encoding="utf-8").read()), encoding="utf-8")
    out = {}
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        try:
            page = await b.new_page(viewport={"width": 390, "height": 844})
            await page.goto(pathlib.Path(str(wired)).as_uri())
            await page.evaluate("() => window.__sbWire()")
            out["before"] = await page.evaluate(RECTS, list(SLOT_IDS))
            out["elements"] = await page.evaluate(w.ELEMENTS)
            out["names"] = await page.evaluate(w.NAMES_ON, w.NAME_OPTIONS)
            out["texts"] = await page.evaluate(
                "() => Array.from(document.querySelectorAll('#sb-name-layer span'))"
                ".map(s => s.textContent)")
            out["after"] = await page.evaluate(RECTS, list(SLOT_IDS))
            out["elements_after"] = await page.evaluate(w.ELEMENTS)
            await page.screenshot(path=str(tmp_path / "names.png"))
            await page.evaluate(w.NAMES_OFF)
            out["left"] = await page.evaluate("() => !!document.getElementById('sb-name-layer')")
        finally:
            await b.close()
    return out


@pytest.mark.browser
def test_each_named_slot_shows_its_name_inside_the_box(tmp_path):
    got = asyncio.run(_wired(tmp_path))
    by = {n["label"]: n for n in got["names"]}
    # 이름 없는 자리 · 숨은 자리는 보이지 않는다
    assert set(by) == {"받는 은행 로고", "신한 로고", "메시지 아이콘", "잘린 로고"}
    assert sorted(got["texts"]) == sorted("[X] " + k for k in by)
    # 상자 안에 들어가는 가장 큰 글자 - 큰 상자는 크게, 작은 상자는 하한
    opt = walk_module().NAME_OPTIONS
    assert by["받는 은행 로고"]["px"] == opt["max_px"]
    assert by["메시지 아이콘"]["px"] == opt["min_px"]
    # 이름 층은 상자 자리에 놓이고, 조상이 자른 상자는 보이는 만큼만 덮는다
    assert by["받는 은행 로고"]["box"][2:] == [84, 84]
    assert by["잘린 로고"]["box"][2] == 20
    # 얹어도 배치는 그대로, 요소 값 · 글에 섞이지 않는다
    assert got["before"] == got["after"]
    for items in (got["elements"]["items"], got["elements_after"]["items"]):
        pick = [i for i in items if i["action"] == "pick"][0]
        assert pick["value"] == "신한" and pick["text"] == "신한"
    assert got["left"] is False


@pytest.mark.browser
def test_the_picture_page_names_the_slots_and_takes_them_off(tmp_path):
    """그림 페이지(picture_state)가 깨끗한 그림을 찍을 때 이름을 얹고, 찍은 뒤 걷어낸다 -
    번호 그림(모델에게 보내는 것)에는 없다."""
    w = walk_module()
    wired = tmp_path / "pictures.wire.html"
    wired.write_text(w.wire_copy(io.open(FIX, encoding="utf-8").read()), encoding="utf-8")
    flow = {"name": "pictures", "steps": [{"screen": "a"}], "error_paths": [],
            "truth": {}}
    state = w.states_of(flow)[0]

    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b = await pw.chromium.launch()
            try:
                return await w.picture_state(b, pathlib.Path(str(wired)).as_uri(), flow, state,
                                             str(tmp_path), "a", lambda items: [])
            finally:
                await b.close()
    out = asyncio.run(go())
    assert out["error"] is None
    assert sorted(n["label"] for n in out["names"]) == [
        "메시지 아이콘", "받는 은행 로고", "신한 로고", "잘린 로고"]
    assert os.path.exists(out["picture"]) and os.path.exists(out["marked"])
