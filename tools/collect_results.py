r"""Copy the evidence worth keeping out of the ignored trees into results/.

outputs/ and logs/ are git-ignored because they are large and mostly
regenerable. Two things in them are not cheaply regenerable:

  * logs/transfer/*.log - the only record of what the property stream actually
    suggested. The pipeline never writes its suggestion JSON to disk, so
    collect_citations.py reconstructs it from these prompts. Re-running costs
    roughly 40 minutes and a round of API spend.
  * the repaired build and its audit - what a later run has to be compared to.

This copies those into results/, which is tracked.

Usage: python tools/collect_results.py
"""
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(ROOT, "results")

# (source relative to ROOT, destination relative to results/)
FILES = [
    ("outputs/audit.json", "audit.json"),
    ("outputs/audit_selftest.json", "audit_selftest.json"),
    ("outputs/citations.json", "citations.json"),
    ("outputs/reassembly_report.json", "reassembly_report.json"),
    ("outputs/screen_extraction.json", "screen_extraction.json"),
    ("outputs/runtime_before.json", "runtime_before.json"),
    ("outputs/runtime_after.json", "runtime_after.json"),
    ("outputs/repaired_transfer.html", "repaired_transfer.html"),
]

# whole directories worth keeping, and what to take from them
TREES = [
    ("logs/transfer", "logs/transfer", (".log",)),
    ("outputs/shots", "shots", (".png",)),
]

# per-screen pipeline logs: the guideline counts that property.log records
SCREENS = ["home", "recipient", "bank", "account", "amount",
           "confirm", "password", "done"]


def copy(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)


def main():
    kept, missing = 0, []
    for rel, dest in FILES:
        s = os.path.join(ROOT, rel.replace("/", os.sep))
        if os.path.exists(s):
            copy(s, os.path.join(RESULTS, dest.replace("/", os.sep)))
            kept += 1
        else:
            missing.append(rel)

    for rel, dest, exts in TREES:
        s = os.path.join(ROOT, rel.replace("/", os.sep))
        if not os.path.isdir(s):
            missing.append(rel)
            continue
        for name in sorted(os.listdir(s)):
            if not name.lower().endswith(exts):
                continue
            copy(os.path.join(s, name),
                 os.path.join(RESULTS, dest.replace("/", os.sep), name))
            kept += 1

    for name in SCREENS:
        s = os.path.join(ROOT, "outputs", name, "property.log")
        if os.path.exists(s):
            copy(s, os.path.join(RESULTS, "property_logs", name + ".log"))
            kept += 1

    print("copied %d files into results/" % kept)
    if missing:
        print("not present (skipped): " + ", ".join(missing))


if __name__ == "__main__":
    main()
