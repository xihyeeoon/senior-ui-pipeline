r"""Walk the live app screen by screen and audit what a user actually sees.

Static markup is not the whole story: buildPwPad() rewrites the keypad on load,
so repairs written into the password markup never reach the screen. This drives
the real transitions, then measures contrast and screenshots each screen.

Usage: python tools/runtime_audit.py <url> <out-prefix>
"""
import asyncio
import json
import os
import sys

from playwright.async_api import async_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from check_contrast import JS as CONTRAST_JS          # noqa: E402

URL = sys.argv[1] if len(sys.argv) > 1 else ""
PREFIX = sys.argv[2] if len(sys.argv) > 2 else "runtime"
SHOTS = os.path.join(ROOT, "outputs", "shots")

# (screen, how to get there from the previous one)
STEPS = [
    ("home", None),
    ("recipient", "[data-action='go-recipient']"),
    ("account", "[data-action='go-account']"),
    # the bank sheet is a modal opened from the account screen
    ("bank", "[data-action='open-bank']"),
    ("amount", "__account"),
    ("confirm", "__amount"),
    ("password", "[data-action='send']"),
    ("done", "__pw"),
]


async def main():
    os.makedirs(SHOTS, exist_ok=True)
    result = {}
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        page = await b.new_page(viewport={"width": 390, "height": 844})
        page.on("dialog", lambda d: asyncio.ensure_future(d.dismiss()))
        await page.goto(URL, wait_until="networkidle")

        for name, how in STEPS:
            if how == "__account":
                # pick the bank in the sheet, which returns to the account
                # screen, then tap the 13 digits on the app's own keypad
                await page.click("[data-action='pick-bank'][data-bank='카카오뱅크']")
                await asyncio.sleep(0.3)
                for d in "3333000000000":
                    await page.click("[data-action='acc-num'][data-v='%s']" % d)
                await page.click("#acc-next")
            elif how == "__amount":
                for d in "10000":
                    await page.click("[data-action='num'][data-v='%s']" % d)
                await page.click("#amt-next")
            elif how == "__pw":
                for _ in range(4):
                    await page.click("#pwpad [data-action='pw']")
                    await asyncio.sleep(0.15)
            elif how:
                await page.click(how)
            await asyncio.sleep(0.5)

            at = await page.evaluate("() => window.__screen()")
            rows = await page.evaluate(CONTRAST_JS)
            # only count what is inside the visible screen
            rows = [r for r in rows if r["ratio"] < r["need"]]
            shot = os.path.join(SHOTS, "%s_%s.png" % (PREFIX, name))
            await page.screenshot(path=shot)
            result[name] = {"landed_on": at, "low_contrast": len(rows), "rows": rows}
            print("%-10s at=%-10s low-contrast=%d" % (name, at, len(rows)))
        await b.close()

    dest = os.path.join(ROOT, "outputs", "runtime_%s.json" % PREFIX)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("total low-contrast:", sum(v["low_contrast"] for v in result.values()))
    print("saved ->", dest, "| shots ->", SHOTS)


if __name__ == "__main__":
    asyncio.run(main())
