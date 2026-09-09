r"""Report low-contrast text on a rendered page (WCAG 2.1 ratio).

Written for the example1 failure mode: a repair adds a <span> with no colour
class, so it inherits the default near-black and lands on a dark background.
Walks every element holding its own text, resolves the effective background by
climbing ancestors until something is opaque, and flags anything under
threshold - 3.0 for large text (>=24px, or >=18.66px bold), 4.5 otherwise.

Usage: python tools/check_contrast.py <url> [screen-name-for-label]
"""
import asyncio
import json
import sys

from playwright.async_api import async_playwright

JS = r"""
() => {
  const lum = c => {
    const f = v => { v /= 255; return v <= 0.03928 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4); };
    return 0.2126*f(c[0]) + 0.7152*f(c[1]) + 0.0722*f(c[2]);
  };
  const parse = s => {
    const m = (s||'').match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(',').map(x => parseFloat(x.trim()));
    return { rgb: [p[0], p[1], p[2]], a: p.length > 3 ? p[3] : 1 };
  };
  /* Climb until an ancestor paints something opaque; body/html default to white. */
  const bgOf = el => {
    let n = el;
    while (n && n.nodeType === 1) {
      const c = parse(getComputedStyle(n).backgroundColor);
      if (c && c.a > 0.95) return c.rgb;
      n = n.parentElement;
    }
    return [255, 255, 255];
  };
  const ratio = (a, b) => {
    const l1 = lum(a), l2 = lum(b);
    return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
  };

  const out = [];
  document.querySelectorAll('*').forEach(el => {
    /* only elements holding their own text */
    const own = Array.from(el.childNodes)
      .filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join(' ').trim();
    if (!own) return;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || +cs.opacity === 0) return;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return;

    const fg = parse(cs.color);
    if (!fg || fg.a < 0.1) return;
    const bg = bgOf(el);
    const size = parseFloat(cs.fontSize);
    const weight = parseInt(cs.fontWeight, 10) || 400;
    const large = size >= 24 || (size >= 18.66 && weight >= 700);
    const need = large ? 3.0 : 4.5;
    const cr = ratio(fg.rgb, bg);
    if (cr < need) {
      out.push({
        text: own.slice(0, 40),
        tag: el.tagName.toLowerCase(),
        cls: (el.getAttribute('class') || '').slice(0, 40),
        color: cs.color, bg: 'rgb(' + bg.join(', ') + ')',
        fontSize: Math.round(size * 10) / 10,
        ratio: Math.round(cr * 100) / 100, need
      });
    }
  });
  return out;
}
"""


async def main():
    url = sys.argv[1]
    label = sys.argv[2] if len(sys.argv) > 2 else url
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        p = await b.new_page(viewport={"width": 390, "height": 844})
        await p.goto(url, wait_until="networkidle")
        await asyncio.sleep(0.6)
        rows = await p.evaluate(JS)
        await b.close()

    print("%-10s low-contrast text elements: %d" % (label, len(rows)))
    for r in sorted(rows, key=lambda x: x["ratio"])[:12]:
        print("   %.2f:1 (need %.1f)  %-6s %-18s color=%-20s bg=%-18s  %r"
              % (r["ratio"], r["need"], r["tag"], r["cls"], r["color"], r["bg"], r["text"]))
    return rows


if __name__ == "__main__":
    rows = asyncio.run(main())
    if len(sys.argv) > 3:
        with open(sys.argv[3], "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        print("saved ->", sys.argv[3])
