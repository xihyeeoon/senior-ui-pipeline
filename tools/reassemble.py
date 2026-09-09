r"""Rebuild original_transfer.html from the 8 per-screen DesignRepair outputs.

Each screen was repaired against a copy of the same shared stylesheet, so the
outputs disagree about global CSS. This merges at rule level:

  * every screen agrees with the original  -> keep the original rule
  * exactly one screen changed it          -> take that screen's version
  * several screens changed it differently -> take the owning screen's version
    (the one whose selector prefix belongs to it), else the first, and record
    the disagreement in the report

The transition <script> is copied over untouched - it was never sent to the
model, which is the point of splitting by screen in the first place.

Usage: python tools/reassemble.py [--from property]   # default: merged output
Output: outputs/repaired_transfer.html + outputs/reassembly_report.json
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "inputs", "original_transfer.html")
DEST = os.path.join(ROOT, "outputs", "repaired_transfer.html")
SCREENS = ["home", "recipient", "bank", "account", "amount",
           "confirm", "password", "done"]

# Which screen owns which selector prefix, for conflict resolution.
OWNER = {
    "home": [".home", ".card", ".acctrow", ".logo", ".acctname", ".acctamt",
             ".btn-sm", ".membership", ".btn-wide", ".rowlist", ".svc",
             ".pointbar", ".footlinks", ".tabbar"],
    "recipient": [".h1", ".inputline", ".filterrow", ".person", ".av", ".nm",
                  ".ac", ".st", ".pill", ".tag", ".lbl"],
    "bank": [".sheet", ".sheetwrap", ".sheethead", ".tabs", ".grid", ".bk", ".bi"],
    "account": [".field", ".tempnote", ".btn-next"],
    "amount": [".amthead", ".amtq", ".amtsub", ".quick", ".keypad"],
    "confirm": [".center", ".bigav", ".q2", ".fee", ".summary", ".srow",
                ".btn-primary"],
    "password": [".pwtitle", ".dots", ".pwpad"],
    "done": [".okwrap", ".okc", ".okbtns", ".bottom2"],
}


def parse_css(css):
    """Flat stylesheet -> ordered [(selector, body, raw_comment_before)]."""
    rules, pos, pending = [], 0, ""
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css, re.S):
        before = css[pos:m.start()]
        cmt = "".join(re.findall(r"/\*.*?\*/", before, re.S))
        sel = re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.S)
        sel = re.sub(r"\s+", " ", sel).strip()
        body = re.sub(r"\s+", " ", m.group(2)).strip().rstrip(";")
        rules.append((sel, body, (pending + cmt).strip()))
        pending = ""
        pos = m.end()
    return rules


def owner_of(sel):
    for screen, prefixes in OWNER.items():
        for p in prefixes:
            if sel.startswith(p):
                return screen
    return None


def get_style(html):
    m = re.search(r"<style>(.*?)</style>", html, re.S)
    return m.group(1) if m else ""


def get_section(html, name):
    m = re.search(r'(<section[^>]*data-screen="%s".*?</section>)' % re.escape(name),
                  html, re.S)
    return m.group(1) if m else None


def main():
    use_property = "--from" in sys.argv and "property" in sys.argv
    src = open(SRC, encoding="utf-8").read()
    orig_rules = parse_css(get_style(src))
    orig_map = {sel: body for sel, body, _ in orig_rules}

    report = {"source": "property" if use_property else "merged",
              "screens": {}, "css_conflicts": [], "css_changed": [],
              "css_added": [], "missing_sections": [], "attr_loss": {}}

    sections, per_screen_css = {}, {}
    for name in SCREENS:
        fn = ("property_%s.html" % name) if use_property else ("%s.html" % name)
        path = os.path.join(ROOT, "outputs", name, fn)
        if not os.path.exists(path):
            report["missing_sections"].append(name)
            print("MISSING %s - falling back to the original screen" % name)
            sections[name] = get_section(src, name)
            continue
        out = open(path, encoding="utf-8").read()
        sec = get_section(out, name)
        if not sec:
            report["missing_sections"].append(name)
            print("NO SECTION in %s - falling back to the original screen" % name)
            sec = get_section(src, name)
        sections[name] = sec
        per_screen_css[name] = {s: b for s, b, _ in parse_css(get_style(out))}

        orig_sec = get_section(src, name)
        lost = {}
        for attr in ("data-action", "id", "data-screen", "data-bank", "data-v"):
            a = set(re.findall(r'%s="([^"]*)"' % attr, orig_sec))
            b = set(re.findall(r'%s="([^"]*)"' % attr, sec))
            if a - b:
                lost[attr] = sorted(a - b)
        report["screens"][name] = {"chars_in": len(orig_sec), "chars_out": len(sec)}
        if lost:
            report["attr_loss"][name] = lost

    # --- merge the stylesheet, declaration by declaration ---------------------
    # Two screens touching different properties of the same rule is not a
    # conflict - only the same property with different values is.
    def decls(body):
        out = {}
        for d in body.split(";"):
            if ":" in d:
                k, v = d.split(":", 1)
                out[k.strip()] = v.strip()
        return out

    merged = []
    for sel, body, cmt in orig_rules:
        base = decls(body)
        proposals = {}                       # prop -> {value: [screens]}
        for name, css in per_screen_css.items():
            if sel not in css:
                continue
            for k, v in decls(css[sel]).items():
                if base.get(k) != v:
                    proposals.setdefault(k, {}).setdefault(v, []).append(name)
        if not proposals:
            merged.append((sel, body, cmt))
            continue

        own = owner_of(sel)
        final = dict(base)
        order = list(base)
        for prop, variants in proposals.items():
            if len(variants) == 1:
                val = next(iter(variants))
                report["css_changed"].append({
                    "selector": sel, "property": prop, "by": variants[val],
                    "from": base.get(prop), "to": val})
            else:
                pick = next((v for v, s in variants.items() if own and own in s), None)
                val = pick if pick else next(iter(variants))
                report["css_conflicts"].append({
                    "selector": sel, "property": prop, "owner": own,
                    "kept": val, "kept_from": own if pick else "first",
                    "original": base.get(prop),
                    "variants": [{"screens": s, "value": v} for v, s in variants.items()]})
            final[prop] = val
            if prop not in order:
                order.append(prop)
        new = "; ".join("%s:%s" % (k, final[k]) for k in order if k in final)
        merged.append((sel, new, cmt))

    seen = set(orig_map)
    for name, css in per_screen_css.items():
        for sel, body in css.items():
            if sel not in seen:
                seen.add(sel)
                merged.append((sel, body, "/* added by %s */" % name))
                report["css_added"].append({"selector": sel, "by": name})

    css_text = "\n".join(
        ("  %s\n  %s{%s;}" % (c, s, b)) if c else ("  %s{%s;}" % (s, b))
        for s, b, c in merged)

    # --- rebuild the document -------------------------------------------------
    body_parts = []
    for name in SCREENS:
        sec = sections[name]
        cls = re.search(r'<section[^>]*\bclass="([^"]*)"', sec)
        names = set((cls.group(1) if cls else "").split())
        names.add("screen")
        names.discard("on")
        if name == "home":
            names |= {"on", "home"}          # home is the screen shown at load
        sec = re.sub(r'(<section[^>]*?)\bclass="[^"]*"', r"\1", sec, count=1)
        sec = re.sub(r"<section", '<section class="%s"' % " ".join(sorted(names)),
                     sec, count=1)
        body_parts.append("<!-- ============ %s ============ -->\n%s" % (name, sec))

    script = re.search(r"(<script>.*?</script>)", src, re.S).group(1)
    head = src[:src.index("<style>")]
    out = "%s<style>\n%s\n</style>\n</head>\n<body>\n<div id=\"phone\">\n\n%s\n\n</div>\n\n%s\n</body>\n</html>\n" % (
        head, css_text, "\n\n".join(body_parts), script)

    with open(DEST, "w", encoding="utf-8") as f:
        f.write(out)
    rp = os.path.join(ROOT, "outputs", "reassembly_report.json")
    with open(rp, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("wrote %s (%d chars)" % (DEST, len(out)))
    print("css: %d changed, %d conflicts, %d added"
          % (len(report["css_changed"]), len(report["css_conflicts"]),
             len(report["css_added"])))
    if report["attr_loss"]:
        print("ATTRIBUTE LOSS:", json.dumps(report["attr_loss"], ensure_ascii=False))
    if report["missing_sections"]:
        print("MISSING:", report["missing_sections"])
    print("report ->", rp)


main()
