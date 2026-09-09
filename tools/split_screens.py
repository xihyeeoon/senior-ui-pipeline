r"""Split original_transfer.html into 8 standalone screen pages for DesignRepair.

Why split: DesignRepair analyses one rendered page at a time. In the original
file only `.screen.on` is displayed, so Playwright would extract properties from
the home screen alone and the repair step would rewrite all 544 lines - including
the transition script - in a single LLM call. Splitting gives each screen its own
page and its own file, and keeps the script out of the model's hands entirely.

The markup is captured from the live DOM after calling show(name), so the parts
built by JS (the 37-bank grid, the shuffled password pad) are baked in.

Usage:  python tools/split_screens.py        # needs the repo served on :3003
Output: outputs/screens/<name>.html  +  _shell.json (head/style for reassembly)
"""
import asyncio
import json
import os
import re

from playwright.async_api import async_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "inputs", "original_transfer.html")
OUT = os.path.join(ROOT, "outputs", "screens")
URL = "http://localhost:3003/inputs/original_transfer.html"

SCREENS = ["home", "recipient", "bank", "account", "amount",
           "confirm", "password", "done"]

TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>%(title)s</title>
<style>
%(style)s
</style>
</head>
<body>
<div id="phone">
%(section)s
</div>
</body>
</html>
"""


async def main():
    src = open(SRC, encoding="utf-8").read()
    style = re.search(r"<style>(.*?)</style>", src, re.S).group(1).strip()

    os.makedirs(OUT, exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={"width": 390, "height": 844})
        await page.goto(URL, wait_until="networkidle")

        for name in SCREENS:
            # `function show()` is a top-level declaration, so it lives on window.
            await page.evaluate("n => window.show(n)", name)
            await asyncio.sleep(0.2)
            html = await page.evaluate(
                "n => document.querySelector('[data-screen=\"' + n + '\"]').outerHTML", name)
            dest = os.path.join(OUT, name + ".html")
            with open(dest, "w", encoding="utf-8") as f:
                f.write(TEMPLATE % {"title": "이체 화면 · " + name,
                                    "style": style, "section": html})
            print("%-10s %6d chars -> outputs/screens/%s.html" % (name, len(html), name))
        await browser.close()

    with open(os.path.join(OUT, "_shell.json"), "w", encoding="utf-8") as f:
        json.dump({"screens": SCREENS}, f, ensure_ascii=False, indent=2)
    print("wrote outputs/screens/_shell.json")


asyncio.run(main())
