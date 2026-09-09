r"""Run DesignRepair's Playwright extractors over every split screen.

No OpenAI key needed - this only answers "would this property run at all?",
since analysis_groups skips any property whose extraction is empty.

Usage: python tools/probe_screens.py     # needs the repo served on :3003
"""
import asyncio
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "vendor", "designrepair", "backend"))

from core.analysis_groups import (load_page, get_text_properties, get_all_colors,
                                  get_label_properties, get_clickable_properties,
                                  get_layout_properties)

SCREENS = ["home", "recipient", "bank", "account", "amount",
           "confirm", "password", "done"]
EXTRACT = [("Text", get_text_properties), ("Color", get_all_colors),
           ("Label", get_label_properties), ("Clickable", get_clickable_properties),
           ("Spacing", get_layout_properties)]


async def main():
    from playwright.async_api import async_playwright
    rows = {}
    async with async_playwright() as pw:
        for name in SCREENS:
            page = await load_page(
                pw, "http://localhost:3003/outputs/screens/%s.html" % name)
            row = {}
            for prop, fn in EXTRACT:
                try:
                    row[prop] = len(await fn(page))
                except Exception as e:
                    row[prop] = "ERR %s" % type(e).__name__
            rows[name] = row
            await page.close()
            print("%-10s %s" % (name, row))
    dest = os.path.join(ROOT, "outputs", "screen_extraction.json")
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print("saved ->", dest)

    hdr = ["screen"] + [p for p, _ in EXTRACT]
    print("\n" + " | ".join("%-9s" % h for h in hdr))
    for name in SCREENS:
        print(" | ".join(["%-9s" % name] + ["%-9s" % rows[name][p] for p, _ in EXTRACT]))


asyncio.run(main())
