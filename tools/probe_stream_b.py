"""Stream B only (Playwright property extraction). Needs NO OpenAI key."""
import asyncio, json, os, sys
from playwright.async_api import async_playwright

ROOT    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "vendor", "designrepair", "backend")
OUT     = os.path.join(ROOT, "outputs")
sys.path.insert(0, BACKEND)

from core.analysis_groups import (load_page, get_text_properties, get_all_colors,
    get_label_properties, get_clickable_properties, get_layout_properties,
    get_groups_with_playwright)

URL = os.environ.get("DESIGNREPAIR_URL", "http://localhost:3000/")

async def main():
    async with async_playwright() as pw:
        page = await load_page(pw, URL)
        res = {}
        for name, fn in [("Text", get_text_properties), ("Color", get_all_colors),
                         ("Label", get_label_properties), ("Clickable", get_clickable_properties),
                         ("Spacing", get_layout_properties)]:
            try:
                v = await fn(page); res[name] = v
                print(f"{name:10s} -> {len(v)} items")
            except Exception as e:
                res[name] = {"ERROR": repr(e)}
                print(f"{name:10s} -> ERROR {e!r}")
        try:
            g = await get_groups_with_playwright(page)
            print("groups     ->", type(g).__name__, len(g) if hasattr(g, "__len__") else "")
            res["_groups_raw"] = str(g)[:5000]
        except Exception as e:
            print("groups     -> ERROR", repr(e))
        dest = os.path.join(OUT, "stream_b_properties.json")
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=2, ensure_ascii=False, default=str)
        print("saved ->", dest)
        await page.close()

asyncio.run(main())
