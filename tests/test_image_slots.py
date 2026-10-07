r"""원본의 그림 자리 - 로고 · 아이콘을 흉내 내지 않고 이름 붙인 자리로 (11-11 1-2).

실제 앱 스크린샷에는 은행 로고 · 아이콘 같은 그림이 보이고 더미앱 A1 도 그 자리에 그림을
그린다. 원본 HTML 은 그 자리를 색 동그라미에 첫 글자 · 기호 · 이모지로 흉내 냈고, 재설계
모델은 장식으로 보고 지웠다 (은행 목록이 글자만 67줄). 그림 파일은 넣지 않는다 - 흉내 낸
글자 대신 role="img" + aria-label "<무엇> 로고/아이콘" 의 회색 상자 X (CSS 클래스 pic).

  - 흉내 글자 · 기호 · 이모지가 원본에 남지 않는다 (조작 기호 ‹ ✕ › ⌄ ⓧ ⌫ ✓ ✎ ↻ ⓘ 는 둔다)
  - 그림 자리마다 이름이 있다. 이체 90 (홈 19 · 받는 사람 3 · 은행 시트 67 · 확인 1),
    공과금 52 (홈 19 · 메뉴 4 · 검색 3 · 세금/공과금 메인 21 · 납부정보 3 · 완료 2)
  - 선택지 값 · data-action 은 그대로 - 검사 I 의 원본 선택지(pick-bank 67 등)도 그대로
  - 상자는 CSS 로만 그린다 - 외부 자원 없음

  .\.venv\Scripts\python.exe -m pytest tests/test_image_slots.py
  .\.venv\Scripts\python.exe -m pytest -m browser tests/test_image_slots.py
"""
import asyncio
import io
import json
import os
import re

import pytest

import _api
import capture_baseline as C

T = _api.tasks_module

# 원본이 그림 대신 쓰던 글자 · 기호 · 이모지. 하나도 남지 않아야 한다.
IMITATIONS = "☺▤♤⌕👤▣💬⚙⎋⌂🍔📅🅦💳📈🛡Ⓦ🎁🧾🔍▭"
# 아이콘의 글자 표기인 조작 기호 - 흉내가 아니라서 둔다.
KEPT = {"transfer": "‹✕›⌄ⓧ⌫✓✎↻ⓘ", "bill": "‹✕›⌄ⓧ⌫✓"}

SLOT = re.compile(r'<(\w+) class="([^"]*\bpic\b[^"]*)"([^>]*)>')
# 마크업 · 스크립트 문자열에 적힌 그림 자리 수 (스크립트가 목록으로 그리는 것은 1번).
WRITTEN = {"transfer": 24, "bill": 35}
# 걸으며 그려진 그림 자리 - 화면마다 (오류 경로 · 펼침 없이 정답 경로에서 보이는 것).
# 은행 시트는 [은행] 탭의 38 이 보이고 [증권사] 탭의 29 는 숨어 있다 (ALL 은 화면 안 전부).
SHOWN = {"transfer": {"home": 19, "recipient": 3, "account": 0, "bank": 38, "amount": 0,
                      "confirm": 1, "password": 0, "done": 0},
         "bill": {"home": 19, "menu": 4, "search": 1, "bill-home": 21, "camera": 0,
                  "info": 3, "password": 0, "done": 2}}
CHOICES = {"transfer": {"pick-bank": 67, "acc-num": 10, "quick": 4, "num": 11, "pw": 10},
           "bill": {"menu-item": 289, "pick-bill": 18, "pw": 10}}


def html(task):
    return io.open(T.abs_path(T.load_task(task)["original"]), encoding="utf-8").read()


@pytest.mark.parametrize("task", ["transfer", "bill"])
def test_no_imitation_is_left(task):
    text = html(task)
    assert [g for g in IMITATIONS if g in text] == []
    # 조작 기호는 그대로다
    assert all(g in text for g in KEPT[task]), [g for g in KEPT[task] if g not in text]


@pytest.mark.parametrize("task", ["transfer", "bill"])
def test_every_slot_is_a_named_image(task):
    """그림 자리는 모두 role="img" 와 "… 로고" / "… 아이콘" 이름을 가진다. data-* 를
    더하지 않는다 - 선택지 값을 읽는 규칙(첫 data-*)이 그 요소를 보지 않게."""
    slots = SLOT.findall(html(task))
    assert len(slots) == WRITTEN[task]
    for tag, cls, rest in slots:
        assert 'role="img"' in rest, (tag, cls, rest)
        label = re.search(r'aria-label="([^"]+)"', rest).group(1)
        assert re.search(r" (로고|아이콘)$", label), label
        assert "data-" not in rest
    # 은행 · 증권사 로고는 그 항목의 이름을 따른다 (스크립트가 그린다)
    if task == "transfer":
        assert '<div class="bi pic" role="img" aria-label="${n} 로고"></div>${n}' in html(task)
        assert "COLORS" not in html(task)


@pytest.mark.parametrize("task", ["transfer", "bill"])
def test_the_box_is_drawn_by_css_only(task):
    css = re.search(r"#phone \.pic\{.*?\}\n\s*#phone \.pic\.em\{[^}]*\}", html(task), re.S)
    assert css, "pic 규칙이 없다"
    assert "url(" not in css.group(0)
    assert "linear-gradient" in css.group(0)


def test_entrance_records_say_there_is_no_glyph():
    """과제 파일의 입구 기록: 아이콘 입구는 원본에 보이는 글자가 없다 (판정에는 쓰지 않는 칸)."""
    for task, n in (("transfer", 6), ("bill", 12)):
        items = T.load_task(task)["entrances"]["items"]
        icons = [e for e in items if "그림 자리" in (e.get("remark") or "")]
        assert len(icons) == n and all(e["text"] is None for e in icons), task
        for e in icons:
            label = re.search(r'aria-label \\?"([^"\\]+)', e["remark"]).group(1)
            assert ('aria-label="%s"' % label) in html(task), (task, e["id"], label)


# --------------------------------------------------------------------- #
# 브라우저 - 원본을 흐름대로 걷는다
# --------------------------------------------------------------------- #
SLOTS_BY_SCREEN = r"""() => {
  const on = document.querySelector('.screen.on');
  const all = (on || document).querySelectorAll('[role="img"]').length;
  const shown = e => { const r = e.getBoundingClientRect();
    const cs = getComputedStyle(e);
    return r.width >= 1 && r.height >= 1 && cs.display !== 'none' && cs.visibility !== 'hidden'; };
  return {all: all, shown: Array.from((on || document).querySelectorAll('[role="img"]'))
                             .filter(shown).map(e => {
    const r = e.getBoundingClientRect();
    const pick = e.closest('[data-action]');
    return {label: e.getAttribute('aria-label'), w: Math.round(r.width), h: Math.round(r.height),
            text: e.textContent, bank: pick ? pick.getAttribute('data-bank') : null};
  })};
}"""


async def _walk_slots(url, flow):
    from playwright.async_api import async_playwright
    out = {}
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        try:
            page = await b.new_page(viewport={"width": 390, "height": 844})
            await page.goto(url, wait_until="networkidle")
            for step, visit in zip(flow["steps"], _api.flow_module.visit_keys(flow["steps"])):
                spec = step.get("do") or ({"click": step["click"]} if "click" in step else [])
                await _api.drive_module.run_actions(page, spec, None, flow["truth"])
                await _api.drive_module.settle(page, step["screen"])
                out[visit] = await page.evaluate(SLOTS_BY_SCREEN)
        finally:
            await b.close()
    return out


@pytest.mark.browser
@pytest.mark.parametrize("task", ["transfer", "bill"])
def test_the_original_walk_shows_named_slots_and_keeps_its_choices(server, task):
    t = T.load_task(task)
    flow = _api.load_flow(None, task=task)
    url = "%s/%s" % (C.BASE_URL, t["original"])
    slots = asyncio.run(_walk_slots(url, flow))
    got = {}
    for visit, seen in slots.items():
        items = seen["shown"]
        got[visit.split("#")[0]] = max(got.get(visit.split("#")[0], 0), len(items))
        for it in items:
            assert re.search(r" (로고|아이콘)$", it["label"] or ""), (visit, it)
            assert it["text"] == "" and it["w"] >= 10 and it["h"] >= 10, (visit, it)
    assert got == SHOWN[task]
    if task == "transfer":
        bank = slots["bank"]["shown"]
        assert slots["bank"]["all"] == 67                              # 은행 38 + 증권사 29
        assert sorted(i["label"] for i in bank) == sorted("%s 로고" % i["bank"] for i in bank)
        assert {(i["w"], i["h"]) for i in bank} == {(32, 32)}          # 예전 동그라미 크기
        assert [i["label"] for i in slots["confirm"]["shown"]] == ["신한 로고"]  # 고른 은행
    # 선택지 값 · 입구는 그대로 (검사 I · K 의 원본 기준)
    snap = asyncio.run(_api.drive(url, flow))
    report = _api.audit(snap, snap, html(task), html(task), flow)
    assert report["passed"], report["fatal"]
    assert report["metrics"]["choice_groups_original"] == CHOICES[task]
    assert report["metrics"]["entrances_original"] == len(t["entrances"]["items"])
