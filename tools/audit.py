r"""Machine-readable audit of a DesignRepair result for the transfer prototype.

Runs the original and the repaired build through the same 8-screen task, then
compares them. Written for a regenerate-on-failure loop: the JSON on stdout (and
at --out) is the verdict, and the exit code is 0 only when nothing fatal fired.

Checks
  A  task completion      fatal   8 screens reached, amount round-trips,
                                  data-action / id / data-screen preserved
  B  display accuracy     fatal   shown values match what was entered;
                                  no injected alert()/confirm()/onclick;
                                  no hardcoded numbers in injected handlers
  C  dead controls        fatal   data-action with no branch in the handler;
                                  data-action present in the original but gone
  D  contrast             warning low-contrast count must not grow; new
                                  elements must not rely on inherited colour
  E  layout               warning overlapping text, content spilling out of its
                                  box, screens much taller than before
  F  language             warning English words that were not in the original
  G  state distinction    warning `.x` and `.x.on` must still look different

Reuses tools/verify_flow.py (required ids), tools/check_contrast.py (the WCAG
probe) and tools/runtime_audit.py (the flow definition) rather than restating
them; those three keep working standalone.

Usage:
  python tools/audit.py \
      --original http://localhost:3003/inputs/original_transfer.html \
      --repaired http://localhost:3003/outputs/repaired_transfer.html \
      --original-file inputs/original_transfer.html \
      --repaired-file outputs/repaired_transfer.html \
      --out outputs/audit.json
Exit: 0 = passed, 1 = fatal findings, 2 = the audit itself could not run.
"""
import argparse
import asyncio
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from playwright.async_api import async_playwright          # noqa: E402

import audit_probes as P                                   # noqa: E402
from check_contrast import JS as CONTRAST_JS               # noqa: E402
from runtime_audit import STEPS as _DEFAULT_STEPS          # noqa: E402
from verify_flow import REQUIRED_IDS as _DEFAULT_IDS        # noqa: E402

# Ground truth for the drive; every displayed value is checked against these.
ACCOUNT = "3333000000000"
AMOUNT = "10000"
AMOUNT_SHOWN = "10,000"
BANK = "카카오뱅크"
NAME = "김시현"

# What each screen must be showing once the task reaches it.
EXPECT_TEXT = {
    # no "account" entry: that screen is snapshotted on arrival, before the
    # bank modal has been opened, so #picked-bank is still the placeholder.
    # The bank choice is verified downstream, on confirm.
    "amount": [("#amt-acc", ACCOUNT)],
    "confirm": [("#cf-acc", ACCOUNT), ("#cf-amt", AMOUNT_SHOWN)],
    "done": [("#dn-amt", AMOUNT_SHOWN)],
}

HEIGHT_GROWTH_LIMIT = 1.5      # screen scrollHeight vs the original
ENGLISH = re.compile(r"[A-Za-z][A-Za-z'’]{1,}")

SUBST = {"{ACCOUNT}": ACCOUNT, "{AMOUNT}": AMOUNT, "{AMOUNT_SHOWN}": AMOUNT_SHOWN,
         "{BANK}": BANK, "{NAME}": NAME}


def fill(s):
    for k, v in SUBST.items():
        s = s.replace(k, v)
    return s


def load_flow(path):
    """A flow file describes the screens, how to reach each one, and what each
    must be showing. Keeping it out of the code is what lets a restructured
    design - different screens, different order - be audited at all."""
    if not path:
        # The shipped original flow is the default baseline. The in-code
        # fallback below only lists screen names, with no way to reach them, so
        # it must never be used to drive a real page.
        default = os.path.join(ROOT, "tools", "flows", "original.json")
        if os.path.exists(default):
            path = default
        else:
            return {"name": "original(names only)", "derived_from_original": True,
                    "required_ids": list(_DEFAULT_IDS),
                    "steps": [{"screen": n} for n, _ in _DEFAULT_STEPS],
                    "expect": {}, "done_amount": "#dn-amt", "_builtin": True}
    with open(path, encoding="utf-8") as f:
        flow = json.load(f)
    flow.setdefault("derived_from_original", True)
    flow.setdefault("expect", {})
    flow.setdefault("done_amount", "#dn-amt")
    return flow


# --------------------------------------------------------------------------- #
# driving
# --------------------------------------------------------------------------- #
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


async def drive(url, flow, want_shots=None):
    """Walk the task once and collect everything the checks need."""
    data = {"screens": {}, "dialogs": [], "js_errors": [], "reached": [],
            "missing_ids": [], "state_pairs": [], "load_failed": None,
            "notes": [], "flow": flow["name"]}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={"width": 390, "height": 844})
        page.on("pageerror", lambda e: data["js_errors"].append(str(e)))

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
                data["screens"][name] = {"error": "%s: %s" % (type(e).__name__, e)}
                break
            await asyncio.sleep(0.45)

            at = await page.evaluate("() => window.__screen && window.__screen()")
            data["reached"].append(at)
            row = {"landed_on": at}
            row.update(await page.evaluate(P.INVENTORY))
            row["contrast"] = await page.evaluate(CONTRAST_JS)
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


# --------------------------------------------------------------------------- #
# checks
# --------------------------------------------------------------------------- #
def union(snapshot, key):
    out = set()
    for row in snapshot["screens"].values():
        out |= {v for v in row.get(key, []) or [] if v}
    return out


def audit(orig, rep, orig_html, rep_html, flow):
    fatal, warning, metrics = [], [], {}
    # A restructured build is not a repair of the original document: its screens
    # are different screens. Anything that compares screen-to-screen is only
    # meaningful when the two share a structure, so those checks stand down and
    # say so rather than reporting noise.
    derived = bool(flow.get("derived_from_original", True))
    metrics["flow"] = flow["name"]
    metrics["derived_from_original"] = derived
    skipped = []

    def F(check, screen, detail, **kw):
        fatal.append(dict(check=check, screen=screen, detail=detail, **kw))

    def W(check, screen, detail, **kw):
        warning.append(dict(check=check, screen=screen, detail=detail, **kw))

    want = [s["screen"] for s in flow["steps"]]
    # A name match is not a screen match: both designs happen to contain a
    # "bank" and an "amount" that have nothing to do with each other. Only a
    # build derived from the original may be compared screen by name.
    shared = [n for n in want if n in orig["screens"] and n in rep["screens"]] \
        if derived else []
    metrics["screens_in_flow"] = want
    metrics["screens_comparable_to_original"] = shared

    # ---------------------------------------------------------------- A ----
    if rep["load_failed"]:
        F("A", None, "page failed to load: " + rep["load_failed"])
        return {"passed": False, "fatal": fatal, "warning": warning,
                "metrics": metrics}

    metrics["screens_expected"] = len(want)
    metrics["screens_reached"] = len(rep["reached"])
    for i, name in enumerate(want):
        row = rep["screens"].get(name)
        if row is None:
            F("A", name, "never reached (task stopped after %d of %d screens)"
              % (len(rep["reached"]), len(want)))
        elif "error" in row:
            F("A", name, "navigation failed: " + row["error"])
        elif row["landed_on"] != name:
            F("A", name, "landed on %r instead" % row["landed_on"])

    if rep["missing_ids"]:
        F("A", None, "ids the transition script needs are gone: "
          + ", ".join(rep["missing_ids"]), lost=rep["missing_ids"])

    done = rep["screens"].get("done", {})
    shown_done = dict(done.get("shown", []) or {}).get("#dn-amt") \
        if isinstance(done.get("shown"), dict) else \
        dict(done.get("shown") or []).get("#dn-amt")
    metrics["done_amount"] = shown_done
    if done and shown_done != AMOUNT_SHOWN:
        F("A", "done", "completion screen shows %r, entered %r"
          % (shown_done, AMOUNT_SHOWN))

    for key, label in [("screens", "data-screen"), ("actions", "data-action"),
                       ("ids", "id")]:
        a, b = union(orig, key), union(rep, key)
        metrics["%s_original" % label] = len(a)
        metrics["%s_repaired" % label] = len(b)
        if not derived:
            continue
        lost = sorted(a - b)
        if lost:
            F("A", None, "%s values lost: %s" % (label, ", ".join(lost)), lost=lost)
    if not derived:
        skipped.append("A/preservation (new design, nothing to preserve)")

    per_screen_loss = {}
    for n in (want if derived else []):
        o = orig["screens"].get(n) or {}
        r = rep["screens"].get(n) or {}
        if not o or not r or "error" in r:
            continue
        lost = {}
        for key, label in [("actions", "data-action"), ("ids", "id")]:
            gone = sorted({v for v in o.get(key) or [] if v}
                          - {v for v in r.get(key) or [] if v})
            if gone:
                lost[label] = gone
        if lost:
            per_screen_loss[n] = lost
            for label, gone in lost.items():
                F("A", n, "%s removed from this screen: %s"
                  % (label, ", ".join(gone)), lost=gone)
    metrics["per_screen_attr_loss"] = per_screen_loss
    if not derived:
        skipped.append("A/per-screen attribute loss")

    if rep["js_errors"]:
        F("A", None, "JavaScript errors during the task: "
          + " | ".join(rep["js_errors"][:3]))

    # ---------------------------------------------------------------- B ----
    for name, pairs in flow["expect"].items():
        pairs = [(fill(sel), fill(val)) for sel, val in pairs]
        row = rep["screens"].get(name)
        if not row or row.get("shown") is None:
            continue
        shown = dict(row.get("shown") or [])
        for sel, expected in pairs:
            got = shown.get(sel)
            if got is None:
                F("B", name, "%s is missing, cannot show %r" % (sel, expected))
            elif expected not in got:
                F("B", name, "%s shows %r but the task used %r"
                  % (sel, got, expected), selector=sel, expected=expected, got=got)
        # Only a name the original actually showed here can go missing.
        orig_text = (orig["screens"].get(name) or {}).get("text") or ""
        if NAME in orig_text and NAME not in (row.get("text") or ""):
            W("B", name, "recipient name %r no longer appears on this screen" % NAME)

    # injected dialogs / handlers, by diffing the two documents
    def calls(html, fn):
        return set(re.findall(r"%s\(\s*(['\"])(.*?)\1" % fn, html))

    for fn in ("alert", "confirm", "prompt"):
        new = calls(rep_html, fn) - calls(orig_html, fn)
        for _q, msg in sorted(new):
            digits = re.findall(r"\d[\d,]*", msg)
            F("B", None, "%s() injected that the original never had: %r"
              % (fn, msg), injected=msg, numbers=digits)
            if digits:
                F("B", None,
                  "injected %s() hardcodes %s - the value is dynamic, so it will "
                  "be wrong for any other amount" % (fn, ", ".join(digits)),
                  injected=msg, numbers=digits)
    metrics["injected_dialog_calls"] = sum(
        len(calls(rep_html, f) - calls(orig_html, f))
        for f in ("alert", "confirm", "prompt"))

    orig_onclick = union(orig, "onclicks")
    rep_onclick = union(rep, "onclicks")
    added = sorted(rep_onclick - orig_onclick)
    metrics["onclick_added"] = len(added)
    for h in added:
        F("B", None, "onclick attribute added that the original did not have: "
          + h[:120], handler=h)

    # dialogs actually raised while driving the task
    metrics["dialogs_during_task"] = len(rep["dialogs"])
    for d in rep["dialogs"]:
        nums = [n for n in re.findall(r"\d[\d,]*", d["message"])
                if n not in (AMOUNT_SHOWN, AMOUNT, ACCOUNT)]
        F("B", d["screen"], "blocking %s during the task: %r"
          % (d["type"], d["message"]))
        if nums:
            F("B", d["screen"],
              "dialog states %s while the task used %s"
              % (", ".join(nums), AMOUNT_SHOWN), numbers=nums)

    # ---------------------------------------------------------------- C ----
    # The handler chain lives in the build under test. For a repair that is the
    # original script copied over; for a new design it is that design's own.
    handled = set(re.findall(r"a\s*===\s*'([a-z-]+)'", rep_html)) \
        or set(re.findall(r"a\s*===\s*'([a-z-]+)'", orig_html))
    metrics["handled_actions"] = len(handled)
    orig_actions, rep_actions = union(orig, "actions"), union(rep, "actions")
    pre_existing_dead = (orig_actions - handled) if derived else set()
    new_dead = sorted((rep_actions - handled) - pre_existing_dead)
    metrics["dead_controls_new"] = len(new_dead)
    metrics["dead_controls_pre_existing"] = sorted(pre_existing_dead)
    for a in new_dead:
        F("C", None, "data-action=%r has no branch in the handler - the control "
          "looks tappable and does nothing" % a, action=a)
    removed = sorted(orig_actions - rep_actions) if derived else []
    for a in removed:
        F("C", None, "data-action=%r existed in the original and is gone" % a,
          action=a)

    # ---------------------------------------------------------------- D ----
    lc_before = {n: len(r.get("contrast", []))
                 for n, r in orig["screens"].items()}
    lc_after = {n: len(r.get("contrast", []))
                for n, r in rep["screens"].items()}
    metrics["low_contrast_before"] = sum(lc_before.values())
    metrics["low_contrast_after"] = sum(lc_after.values())
    metrics["low_contrast_by_screen"] = {
        n: {"before": lc_before.get(n), "after": lc_after.get(n)}
        for n in (want if derived else shared)}
    if metrics["low_contrast_after"] > metrics["low_contrast_before"]:
        W("D", None, "low-contrast text grew from %d to %d"
          % (metrics["low_contrast_before"], metrics["low_contrast_after"]))
    for n in shared:
        b, a = lc_before.get(n), lc_after.get(n)
        if b is not None and a is not None and a > b:
            W("D", n, "low-contrast text grew from %d to %d" % (b, a))

    new_inherited = []
    for n in (want if derived else shared):
        o = {(x["text"], x["cls"]) for x in orig["screens"].get(n, {}).get("inherited", [])}
        for x in rep["screens"].get(n, {}).get("inherited", []):
            if (x["text"], x["cls"]) not in o:
                new_inherited.append(dict(x, screen=n))
    metrics["new_inherited_colour"] = len(new_inherited)
    for x in new_inherited[:20]:
        W("D", x["screen"], "new text %r takes its colour purely by inheritance "
          "(%s) - nothing sets a colour for it" % (x["text"], x["color"]),
          cls=x["cls"], tag=x["tag"])

    # An element that was already below threshold does not change the count when
    # a repair puts words into it, and it is not inheriting either - its class
    # supplies the colour. `.st` was a decorative ☆ at 1.44:1; it now carries
    # "선택됨", which a reader is expected to read at the same 1.44:1.
    WORDY = re.compile(r"[0-9A-Za-z가-힣]")
    burdened = []
    for n in want:
        by_key = {}
        for x in orig["screens"].get(n, {}).get("contrast", []) or []:
            by_key.setdefault((x["tag"], x["cls"]), set()).add(x["text"])
        for x in rep["screens"].get(n, {}).get("contrast", []) or []:
            k = (x["tag"], x["cls"])
            was = by_key.get(k)
            if not was or x["text"] in was:
                continue
            # only when text was added, and the addition is actually readable
            if len(x["text"]) > max(len(t) for t in was) and WORDY.search(x["text"]):
                burdened.append(dict(x, screen=n, before=sorted(was)[0]))
    metrics["low_contrast_gained_text"] = len(burdened)
    seen_b = set()
    for x in burdened:
        k = (x["screen"], x["cls"], x["text"])
        if k in seen_b:
            continue
        seen_b.add(k)
        W("D", x["screen"], "already low-contrast element (.%s, %.2f:1) gained "
          "readable text: %r -> %r - the count is unchanged, so this passes the "
          "before/after comparison" % (x["cls"], x["ratio"], x["before"], x["text"]),
          cls=x["cls"], ratio=x["ratio"], need=x["need"],
          color=x["color"], bg=x["bg"])

    # ---------------------------------------------------------------- E ----
    ov_new, of_new, tall = [], [], []
    for n in want:
        # overlap and overflow are defects on their own terms, so they run on
        # every screen; a missing baseline just means nothing is subtracted.
        # Wrapping and height growth are comparisons, so they only run where a
        # matching original screen exists.
        o = orig["screens"].get(n, {}) if (derived or n in shared) else {}
        r = rep["screens"].get(n, {})
        ob = {(x["a"], x["b"]) for x in o.get("overlap", [])}
        for x in r.get("overlap", []):
            if (x["a"], x["b"]) not in ob:
                ov_new.append(dict(x, screen=n))
        of = {(x["cls"], x["text"]) for x in o.get("overflow", [])}
        for x in r.get("overflow", []):
            if (x["cls"], x["text"]) not in of:
                of_new.append(dict(x, screen=n))
        if o.get("height") and r.get("height") and (derived or n in shared):
            ratio = r["height"] / float(o["height"])
            if ratio > HEIGHT_GROWTH_LIMIT:
                tall.append({"screen": n, "before": o["height"],
                             "after": r["height"], "ratio": round(ratio, 2)})
    metrics["overlaps_new"] = len(ov_new)
    metrics["overflows_new"] = len(of_new)
    metrics["screens_much_taller"] = len(tall)
    for x in ov_new[:20]:
        W("E", x["screen"], "%r and %r overlap by %d%%"
          % (x["a"], x["b"], x["overlap_pct"]))
    for x in of_new[:20]:
        W("E", x["screen"], "content spills %dpx out of a %dpx box (.%s): %r"
          % (x["spill_px"], x["box_h"], x["cls"] or x["tag"], x["text"]))
    for x in tall:
        W("E", x["screen"], "screen is %.2fx taller than the original (%d -> %dpx)"
          % (x["ratio"], x["before"], x["after"]))

    # E3 - text that did not wrap before and wraps now. The recipient navbar
    # breaks this way rather than by rect overlap.
    wrap_new = []
    for n in (want if derived else shared):
        def key(items):
            out = {}
            for x in items or []:
                out[(x["tag"], x["cls"])] = out.get((x["tag"], x["cls"]), 0) + 1
            return out
        ob = key(orig["screens"].get(n, {}).get("wrapped"))
        for x in rep["screens"].get(n, {}).get("wrapped", []) or []:
            k = (x["tag"], x["cls"])
            if ob.get(k, 0) > 0:
                ob[k] -= 1
            else:
                wrap_new.append(dict(x, screen=n))
    metrics["newly_wrapped_text"] = len(wrap_new)
    if not derived and not shared:
        skipped.append("E/newly-wrapped text and height growth (no shared screens)")
    for x in wrap_new[:20]:
        W("E", x["screen"], "%r now wraps onto %d lines (.%s) - it did not before"
          % (x["text"], x["lines"], x["cls"] or x["tag"]), lines=x["lines"])

    # ---------------------------------------------------------------- F ----
    def words(snapshot):
        seen = set()
        for row in snapshot["screens"].values():
            seen |= set(ENGLISH.findall(row.get("text") or ""))
        return seen

    new_en = sorted(words(rep) - words(orig))
    metrics["new_english_words"] = new_en
    for n in want:
        t = (rep["screens"].get(n) or {}).get("text") or ""
        hits = sorted({w for w in new_en if w in t})
        if hits:
            W("F", n, "English text not present in the original: "
              + ", ".join(hits), words=hits, source="runtime")

    # Markup the script overwrites at runtime never reaches the eye, but it is
    # still in the file - password's 재배열 -> "Shuffle" only shows up here.
    def markup_words(html):
        body = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S | re.I)
        return set(ENGLISH.findall(re.sub(r"<[^>]+>", " ", body)))

    # Anything appearing anywhere in the original file - including inside its
    # script, where the 37 bank and 29 securities names live - is not new
    # English. The reassembly merely bakes those into markup.
    static_only = sorted(markup_words(rep_html)
                         - set(ENGLISH.findall(orig_html))
                         - words(orig) - set(new_en))
    metrics["new_english_words_markup_only"] = static_only
    if static_only:
        W("F", None, "English added to the markup but overwritten before it "
          "renders: " + ", ".join(static_only), words=static_only, source="markup")

    # ---------------------------------------------------------------- G ----
    def collapsed(snapshot):
        return {(x["base"], x["state"]) for x in snapshot["state_pairs"]
                if not x["differing"]}

    before_bad = collapsed(orig)
    now_bad = sorted(collapsed(rep) - before_bad)
    metrics["state_pairs_checked"] = len(rep["state_pairs"])
    metrics["state_pairs_collapsed"] = len(now_bad)
    detail = {(x["base"], x["state"]): x for x in rep["state_pairs"]}
    for base, state in now_bad:
        x = detail[(base, state)]
        W("G", None, "%s and %s%s now render identically (%s) - the state is no "
          "longer visible" % (base, base, "." + state, ", ".join(x["props"])),
          base=base, state=state, properties=x["props"],
          base_values=x["base_values"])

    # ---------------------------------------------------------------- H ----
    # Not in the original brief, added because it is the shared root cause of
    # two rendering failures: example1's bg-primary/text-primary and this run's
    # sr-only. A class no stylesheet defines does nothing, so a label meant to
    # be hidden shows up and a colour meant to be applied never lands.
    before_undef = {x["cls"] for x in orig.get("undefined_classes", [])}
    new_undef = [x for x in rep.get("undefined_classes", [])
                 if x["cls"] not in before_undef]
    metrics["undefined_classes_new"] = sorted({x["cls"] for x in new_undef})
    for x in new_undef:
        W("H", x["screen"], "class %r is used %dx but no stylesheet defines it - "
          "it has no effect (e.g. %r)" % (x["cls"], x["count"], x["sample"]),
          cls=x["cls"], count=x["count"])

    metrics["flow_notes"] = rep.get("notes") or []
    metrics["checks_stood_down"] = skipped
    return {"passed": not fatal, "fatal": fatal, "warning": warning,
            "metrics": metrics}


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--original",
                    default="http://localhost:3003/inputs/original_transfer.html")
    ap.add_argument("--repaired",
                    default="http://localhost:3003/outputs/repaired_transfer.html")
    ap.add_argument("--original-file",
                    default=os.path.join(ROOT, "inputs", "original_transfer.html"))
    ap.add_argument("--repaired-file",
                    default=os.path.join(ROOT, "outputs", "repaired_transfer.html"))
    ap.add_argument("--out", default=os.path.join(ROOT, "outputs", "audit.json"))
    ap.add_argument("--flow", default=None,
                    help="flow file describing the screens and how to reach them")
    ap.add_argument("--shots", default=None, help="directory to save screenshots in")
    args = ap.parse_args()

    try:
        orig_html = open(args.original_file, encoding="utf-8").read()
        rep_html = open(args.repaired_file, encoding="utf-8").read()
    except OSError as e:
        json.dump({"passed": False, "fatal": [{"check": None, "screen": None,
                   "detail": "cannot read inputs: %s" % e}], "warning": [],
                   "metrics": {}}, sys.stdout, ensure_ascii=False, indent=2)
        return 2

    if args.shots:
        os.makedirs(args.shots, exist_ok=True)
    flow = load_flow(args.flow)
    base_flow = load_flow(None) if not flow.get("derived_from_original", True) \
        else flow
    orig = asyncio.run(drive(args.original, base_flow))
    rep = asyncio.run(drive(args.repaired, flow, want_shots=args.shots))
    report = audit(orig, rep, orig_html, rep_html, flow)
    report["inputs"] = {"original": args.original, "repaired": args.repaired,
                        "flow": args.flow or "(builtin original)"}

    if args.out:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
