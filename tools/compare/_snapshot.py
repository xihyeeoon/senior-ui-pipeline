"""Snapshot each variant's rendered DOM so the standalone bundle needs no React."""
import asyncio, json, os
from playwright.async_api import async_playwright

ART = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "outputs", "compare")

VARIANTS = ["orig", "base", "senior"]

async def main():
    out = {}
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        for vid in VARIANTS:
            p = await b.new_page(viewport={"width": 1280, "height": 1000})
            await p.goto(f"http://localhost:3003/outputs/compare/{vid}.html",
                         wait_until="networkidle")
            await asyncio.sleep(1)
            out[vid] = await p.evaluate("document.getElementById('root').innerHTML")
            print(f"{vid}: {len(out[vid])} chars")
            await p.close()
        await b.close()
    with open(os.path.join(ART, "_snapshots.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print("saved _snapshots.json")

asyncio.run(main())
