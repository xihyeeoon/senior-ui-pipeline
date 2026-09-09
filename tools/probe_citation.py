"""Run ONE property analysis call and dump the raw suggestion JSON,
which the pipeline computes but never writes to disk.
Usage: probe_citation.py <Property> <kb.csv> <pageurl> <outname>"""
import asyncio, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "vendor", "designrepair", "backend")); sys.path.insert(0, ROOT)
from dotenv import load_dotenv; load_dotenv(os.path.join(ROOT, ".envs"))

PROP, KB, URL, OUT = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]

from run_local import load_system_level_guidelines
from playwright.async_api import async_playwright
import core.analysis_groups as G

EXTRACT = {"Text": G.get_text_properties, "Color": G.get_all_colors,
           "Label": G.get_label_properties, "Clickable": G.get_clickable_properties,
           "Spacing": G.get_layout_properties}

async def main():
    fc = open(os.environ.get("PROBE_SRC", os.path.join(ROOT, "vendor", "designrepair", "examples", "example1.tsx")), encoding="utf-8").read()
    async with async_playwright() as pw:
        page = await G.load_page(pw, URL)
        props = await EXTRACT[PROP](page)
        await page.close()
    print(f"{PROP}: {len(props)} elements extracted")
    g = load_system_level_guidelines(KB)
    prompt, schema = G.assemble_analysis_property_prompt(fc, g[PROP], PROP, props)
    completion = await G.get_response(prompt, schema)
    dest = os.path.join(ROOT, "outputs", OUT)
    open(dest, "w", encoding="utf-8").write(completion)
    print("saved ->", dest)
    try:
        d = json.loads(completion)["bad_property_design"]
        print(f"suggestions: {len(d)}")
        for i, s in enumerate(d, 1):
            print(f"  [{i}] ref: {s.get('detailed_reference_from_guidelines','')[:150]}")
    except Exception as e:
        print("parse:", e)

asyncio.run(main())
