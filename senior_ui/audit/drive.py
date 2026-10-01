r"""흐름 파일대로 페이지를 한 번 걷고, 검사가 필요한 것을 전부 긁어 온다.

판정은 하지 않는다 - 판정은 core.py 의 audit() 이 이 결과를 보고 한다. 페이지
안에서 실행되는 JavaScript 조각은 probes.py 에 있다.
"""
import asyncio
import os
import re

from playwright.async_api import async_playwright

from . import probes as P
from .flow import fill

# A `%s`-bearing attribute selector, e.g. the [data-v='%s'] in
# "[data-action='acc-num'][data-v='%s']". Dropping it leaves the selector that
# addresses the field itself.
PER_CHAR_ATTR = re.compile(r"\[[^\]]*%s[^\]]*\]")

TAG_OF = """sel => { const e = document.querySelector(sel);
                     return e ? e.tagName.toLowerCase() : null; }"""


async def run_actions(page, spec, notes=None):
    """One step of a flow file: click / type / repeat / wait, in order.

    `type` covers both ways a design can take text:

      keypad   "[data-action='acc-num'][data-v='%s']"  - one click per character
      field    "#acc-input"                            - one fill()

    The selector says which: a `%s` means there is a button per digit. A design
    that uses a real <input> has no such buttons, so it writes the field's own
    selector instead.

    Models often write both at once - "input[data-action='x'][data-v='%s']" -
    having read the keypad example but built a field. The element is an input,
    there are no per-digit buttons, and driving it as a keypad stalls on a
    selector that matches nothing. So when the `%s` selector points at an
    input/textarea once the `%s` attribute is dropped, fill it and record that
    in `notes`; the report surfaces it rather than silently accepting it.
    """
    for item in (spec if isinstance(spec, list) else [spec]):
        if "wait" in item and "click" not in item and "repeat" not in item:
            await asyncio.sleep(float(item["wait"]))
            continue
        if "type" in item:
            key, value = item["key"], fill(item["type"])
            if "%s" not in key:
                await page.fill(key, value)
                continue
            base = PER_CHAR_ATTR.sub("", key)
            tag = await page.evaluate(TAG_OF, base) if base != key else None
            if tag in ("input", "textarea"):
                await page.fill(base, value)
                if notes is not None:
                    notes.append(
                        "flow: type key %r has %%s but addresses an <%s>; filled "
                        "%r via %r instead of clicking per character"
                        % (key, tag, value, base))
                continue
            for ch in value:
                await page.click(key % ch)
            continue
        if "repeat" in item:
            for _ in range(int(item["repeat"])):
                await page.click(fill(item["click"]))
                await asyncio.sleep(float(item.get("wait", 0.1)))
            continue
        if "click" in item:
            await page.click(fill(item["click"]))
            if item.get("wait"):
                await asyncio.sleep(float(item["wait"]))


SELECTOR_IN_ERROR = re.compile(r'waiting for locator\("([^"]+)"\)')

WHERE_IS = """sel => {
  let el = null;
  try { el = document.querySelector(sel); } catch (e) { return null; }
  const on = document.querySelector('.screen.on');
  const current = on ? on.dataset.screen : null;
  if (!el) return {found: false, current: current};
  const sec = el.closest('[data-screen]');
  return {found: true, owner: sec ? sec.dataset.screen : null, current: current};
}"""


async def where_is(page, error_text):
    """실패한 선택자가 어느 화면 안에 있는지 알아낸다.

    "보이지 않음" 만으로는 요소를 고쳐야 하는지 화면 전환을 고쳐야 하는지 알 수
    없다. 요소가 다른 화면 안에 멀쩡히 있다면 문제는 요소가 아니라 거기까지
    가지 못한 것이다."""
    m = SELECTOR_IN_ERROR.search(error_text or "")
    if not m:
        return None
    try:
        info = await page.evaluate(WHERE_IS, m.group(1))
    except Exception:
        return None
    if not info:
        return None
    sel = m.group(1)
    if not info.get("found"):
        return "%s 는 문서 어디에도 없다 (지금 화면: %s)" % (sel, info.get("current"))
    owner, current = info.get("owner"), info.get("current")
    if owner and current and owner != current:
        return ("%s 는 %r 화면에 있는데 지금 켜진 화면은 %r 이다. "
                "요소가 아니라 화면 전환을 확인하라." % (sel, owner, current))
    return None


async def drive(url, flow, want_shots=None):
    """Walk the task once and collect everything the checks need."""
    data = {"screens": {}, "dialogs": [], "js_errors": [], "reached": [],
            "missing_ids": [], "state_pairs": [], "load_failed": None,
            "notes": [], "js_error_details": [], "flow": flow["name"]}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={"width": 390, "height": 844})
        def _on_pageerror(e):
            # 메시지만 남기면 "S is not defined" 뿐이라 어디를 고칠지 알 수 없다.
            # stack 에 파일과 줄 번호가 들어 있으므로 함께 보관한다.
            data["js_errors"].append(str(e))
            data["js_error_details"].append({
                "name": getattr(e, "name", None),
                "message": str(e),
                "stack": getattr(e, "stack", None),
            })
        page.on("pageerror", _on_pageerror)

        async def on_dialog(d):
            data["dialogs"].append({"screen": data["reached"][-1] if data["reached"]
                                    else "?", "type": d.type, "message": d.message})
            await d.dismiss()
        page.on("dialog", lambda d: asyncio.ensure_future(on_dialog(d)))

        try:
            await page.goto(url, wait_until="networkidle")
        except Exception as e:
            data["load_failed"] = "%s: %s" % (type(e).__name__, e)
            await browser.close()
            return data

        data["missing_ids"] = await page.evaluate(
            "ids => ids.filter(i => !document.getElementById(i))",
            flow["required_ids"])
        data["state_pairs"] = await page.evaluate(P.STATE_PAIRS)
        data["undefined_classes"] = await page.evaluate(P.UNDEFINED_CLASSES)

        for step in flow["steps"]:
            name = step["screen"]
            try:
                if "do" in step:
                    await run_actions(page, step["do"], data["notes"])
                elif "click" in step:
                    await run_actions(page, {"click": step["click"]}, data["notes"])
            except Exception as e:
                msg = "%s: %s" % (type(e).__name__, e)
                hint = await where_is(page, msg)
                if hint:
                    msg += " || " + hint
                data["screens"][name] = {"error": msg}
                break
            await asyncio.sleep(0.45)

            at = await page.evaluate("() => window.__screen && window.__screen()")
            data["reached"].append(at)
            row = {"landed_on": at}
            row.update(await page.evaluate(P.INVENTORY))
            row["choices"] = await page.evaluate(P.CHOICE_GROUPS)
            row["contrast"] = await page.evaluate(P.CONTRAST)
            row["inherited"] = await page.evaluate(P.INHERITED_COLOUR)
            row["overlap"] = await page.evaluate(P.OVERLAP)
            row["overflow"] = await page.evaluate(P.OVERFLOW)
            row["wrapped"] = await page.evaluate(P.WRAPPED)
            row["shown"] = await page.evaluate(
                """sels => sels.map(s => {
                     const e = document.querySelector(s);
                     return [s, e ? e.textContent.trim() : null];
                   })""",
                [fill(s) for s, _ in flow["expect"].get(name, [])])
            data["screens"][name] = row
            if want_shots:
                await page.screenshot(path=os.path.join(
                    want_shots, "audit_%s.png" % name))
        await browser.close()
    return data
