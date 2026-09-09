r"""Drive the 8-screen transfer task end to end and report where it breaks.

The flow the original supports (the recipient rows are decorative - they carry
no data-action, so the only way forward is "계좌번호 직접 입력"):

    home -> recipient -> bank -> account -> amount -> confirm -> password -> done

Usage: python tools/verify_flow.py <url>
"""
import asyncio
import os
import re
import sys

from playwright.async_api import async_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "inputs", "original_transfer.html")

URL = sys.argv[1] if len(sys.argv) > 1 else \
    "http://localhost:3003/inputs/original_transfer.html"

# Elements the transition script reaches for by id; losing any of them breaks it.
REQUIRED_IDS = ["phone", "grid-bank", "grid-sec", "tab-bank", "tab-sec",
                "picked-bank", "acc-input", "acc-next", "amt-acc",
                "amt-display", "amt-next", "cf-amt", "cf-acc",
                "dn-amt", "pw-dots", "pwpad"]


async def main():
    problems, steps = [], []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={"width": 390, "height": 844})
        errors, dialogs = [], []
        page.on("pageerror", lambda e: errors.append(str(e)))

        # Playwright dismisses dialogs silently by default, so an injected
        # alert() would pass unnoticed while blocking a real user every tap.
        async def on_dialog(d):
            dialogs.append("%s: %s" % (d.type, d.message))
            await d.dismiss()
        page.on("dialog", lambda d: asyncio.ensure_future(on_dialog(d)))

        await page.goto(URL, wait_until="networkidle")

        missing = await page.evaluate(
            "ids => ids.filter(i => !document.getElementById(i))", REQUIRED_IDS)
        if missing:
            problems.append("missing ids: " + ", ".join(missing))

        screens = await page.evaluate(
            "() => Array.from(document.querySelectorAll('[data-screen]'))"
            ".map(s => s.dataset.screen)")
        steps.append("screens present: %d %s" % (len(screens), screens))

        # A repair can invent a data-action the handler chain never branches on.
        # The control then looks tappable and does nothing.
        handled = set(re.findall(r"a==='([a-z-]+)'",
                                 open(SRC, encoding="utf-8").read()))
        used = set(await page.evaluate(
            "() => Array.from(document.querySelectorAll('[data-action]'))"
            ".map(e => e.dataset.action)"))
        dead = sorted(used - handled)
        if dead:
            problems.append("dead controls - data-action with no handler: %s"
                            % ", ".join(dead))
        steps.append("data-action values: %d used, %d handled" % (len(used), len(handled)))

        async def at():
            return await page.evaluate("() => window.__screen && window.__screen()")

        async def step(label, action, expect):
            try:
                await action()
            except Exception as e:
                problems.append("%s: %s" % (label, type(e).__name__))
                steps.append("%-22s FAILED (%s)" % (label, type(e).__name__))
                return False
            await asyncio.sleep(0.35)
            now = await at()
            ok = now == expect
            steps.append("%-22s -> %-10s %s" % (label, now, "ok" if ok else
                                                "EXPECTED " + expect))
            if not ok:
                problems.append("%s: landed on %r, expected %r" % (label, now, expect))
            return ok

        await step("tap 이체", lambda: page.click("[data-action='go-recipient']"), "recipient")
        await step("tap 계좌번호 직접 입력", lambda: page.click("[data-action='go-bank']"), "bank")
        await step("pick 카카오뱅크",
                   lambda: page.click("[data-action='pick-bank'][data-bank='카카오뱅크']"), "account")

        async def type_account():
            await page.fill("#acc-input", "3333000000000")
            await page.click("#acc-next")
        await step("type 계좌번호 + 다음", type_account, "amount")

        async def enter_amount():
            for d in "10000":
                await page.click("[data-action='num'][data-v='%s']" % d)
            await page.click("#amt-next")
        await step("금액 10,000 + 다음", enter_amount, "confirm")

        await step("tap 보내기", lambda: page.click("[data-action='send']"), "password")

        async def enter_pw():
            for _ in range(4):
                await page.click("#pwpad [data-action='pw']")
                await asyncio.sleep(0.12)
        await step("비밀번호 4자리", enter_pw, "done")

        if await at() == "done":
            shown = await page.evaluate(
                "() => { const a = document.getElementById('dn-amt');"
                " return a ? a.textContent : null; }")
            steps.append("done screen amount: %r" % shown)
            if shown != "10,000":
                problems.append("done screen shows %r, expected '10,000'" % shown)

        if errors:
            problems.append("JS errors: " + " | ".join(errors[:3]))
        if dialogs:
            problems.append("blocking dialogs during the task (%d): %s"
                            % (len(dialogs), " | ".join(dialogs[:3])))
        await browser.close()

    print("URL:", URL)
    for s in steps:
        print("  " + s)
    print("\nPROBLEMS:" if problems else "\nPROBLEMS: none")
    for p in problems:
        print("  - " + p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
