r"""Collect the property-stream suggestions and the rules they cite, per screen.

The pipeline never writes its suggestion JSON to disk, but repair_to_full_code()
prints the whole prompt (analysis_utils.py:113), and the stream-B prompt embeds
str(property_suggestions). So the run's real suggestions are recoverable from
the log - no extra API calls, and no risk of sampling a different answer than
the one that actually shaped the output.

Log order per screen: [0] component repair, [1] property repair, [2] merged.

Usage: python tools/collect_citations.py
Output: outputs/citations.json  + a per-screen and overall summary
"""
import ast
import csv
import json
import os
import re
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS = os.path.join(ROOT, "logs", "transfer")
KB = os.path.join(ROOT, "kb", "senior_kb.csv")
SCREENS = ["home", "recipient", "bank", "account", "amount",
           "confirm", "password", "done"]

RULE_ID = re.compile(r"\b(SDF-[A-Za-z0-9]+-\d+|KS-\d+)\b")


def kb_rules():
    """rule id -> (property, content) for every row the loader accepts."""
    out = {}
    with open(KB, encoding="utf-8", newline="") as fh:
        for i, row in enumerate(csv.reader(fh), 1):
            if i == 1 or len(row) != 6:
                continue
            out[row[4]] = (row[2], row[5])
    return out


def prompts(path):
    """Every printed regenerate prompt in a run log, parsed back to messages.

    httpx/httpcore teardown chatter goes to stderr and lands mid-line, with no
    newline in front of it, so a prompt line often carries trailing garbage.
    Retry from the last plausible end of the list backwards.
    """
    found = []
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.rstrip("\n")
        if not line.startswith("[{'role': 'system'"):
            continue
        parsed = None
        for end in reversed([m.end() for m in re.finditer(r"'\}\]", line)]):
            try:
                parsed = ast.literal_eval(line[:end])
                break
            except Exception:
                continue
        found.append(parsed)
    return found


def suggestions(msgs):
    """The suggestion blob is the 2nd ''' quoted section of the user message."""
    parts = msgs[-1]["content"].split("'''")
    if len(parts) < 4:
        return []
    try:
        return ast.literal_eval(parts[3])
    except Exception:
        return []


def main():
    rules = kb_rules()
    result, all_ids = {}, Counter()
    by_prop_total = defaultdict(int)

    for name in SCREENS:
        path = os.path.join(LOGS, name + ".log")
        if not os.path.exists(path):
            print("%-10s (no log)" % name)
            continue
        ps = prompts(path)
        if len(ps) < 2 or ps[1] is None:
            print("%-10s (property prompt not recoverable)" % name)
            continue
        data = suggestions(ps[1])

        screen = {"total": 0, "cited": 0, "by_property": {}, "ids": []}
        for group in data:
            for key, items in group.items():
                prop = key.replace("bad_", "").replace("_property_design", "")
                ids = []
                for it in items:
                    m = RULE_ID.search(it.get("detailed_reference_from_guidelines", ""))
                    ids.append(m.group(1) if m else None)
                screen["by_property"][prop] = {
                    "n": len(items),
                    "cited": sum(1 for i in ids if i),
                    "ids": sorted({i for i in ids if i}),
                }
                screen["total"] += len(items)
                screen["cited"] += sum(1 for i in ids if i)
                screen["ids"] += [i for i in ids if i]
                by_prop_total[prop] += len(items)
        all_ids.update(screen["ids"])
        screen["distinct"] = sorted(set(screen["ids"]))
        result[name] = screen
        print("%-10s suggestions=%-3d cited=%-3d distinct=%d  %s"
              % (name, screen["total"], screen["cited"],
                 len(screen["distinct"]), screen["distinct"]))

    total = sum(s["total"] for s in result.values())
    cited = sum(s["cited"] for s in result.values())
    distinct = sorted(all_ids)
    unused = sorted(set(rules) - set(distinct))

    print("\nTOTAL suggestions=%d  with rule id=%d (%.0f%%)"
          % (total, cited, 100.0 * cited / total if total else 0))
    print("distinct rules cited: %d / %d" % (len(distinct), len(rules)))
    print("  most cited:", ", ".join("%s x%d" % (i, n)
                                     for i, n in all_ids.most_common(6)))
    print("never cited (%d): %s" % (len(unused), ", ".join(unused)))
    print("\nby property (suggestion counts):")
    for p, n in sorted(by_prop_total.items(), key=lambda x: -x[1]):
        print("  %-10s %d" % (p, n))

    dest = os.path.join(ROOT, "outputs", "citations.json")
    with open(dest, "w", encoding="utf-8") as f:
        json.dump({"screens": result, "distinct": distinct, "unused": unused,
                   "total": total, "cited": cited,
                   "counts": dict(all_ids)}, f, ensure_ascii=False, indent=2)
    print("\nsaved ->", dest)


main()
