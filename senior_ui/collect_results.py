r"""Copy the evidence worth keeping out of the ignored trees into results/.

outputs/ is git-ignored because it is large and mostly regenerable. The
restructured builds are not: they come out of an LLM run, so re-making them
costs API spend and never reproduces byte for byte. This copies them, their
audit JSON and their screenshots into results/, which is tracked.

Usage: python -m senior_ui.collect_results
"""
import os
import shutil

from senior_ui.config import RESULTS_DIR as RESULTS
from senior_ui.config import ROOT

# (source relative to ROOT, destination relative to results/)
FILES = [
    # The restructured build is LLM-written: outputs/ is ignored, so without
    # this copy it lives nowhere git can restore it.
    ("outputs/restructured_transfer.html", "restructured_transfer.html"),
    ("outputs/audit_restructured.json", "audit_restructured.json"),
    # Runs 2 and 3 of the same restructuring brief; see docs/restructure-runs.md
    ("outputs/restructured_run2.html", "restructured_run2.html"),
    ("outputs/audit_run2.json", "audit_run2.json"),
    ("outputs/restructured_run3.html", "restructured_run3.html"),
    ("outputs/audit_run3.json", "audit_run3.json"),
    # Run 4 는 자동 파이프라인이 낸 것이어서 승격 전 이름이 다르다. 통과한
    # 시도(attempt_3)가 run2·run3 과 같은 자리에 오도록 이름을 바꿔 둔다.
    ("outputs/restructure_auto/20261001-125247/attempt_3.html",
     "restructured_run4.html"),
    ("outputs/restructure_auto/20261001-125247/attempt_3.audit.json",
     "audit_run4.json"),
]

# whole directories worth keeping, and what to take from them
TREES = [
    ("outputs/shots/restructured", "shots/restructured", (".png",)),
    ("outputs/shots/run2", "shots/run2", (".png",)),
    ("outputs/shots/run3", "shots/run3", (".png",)),
    ("outputs/restructure_auto/20261001-125247/shots/attempt_3",
     "shots/run4", (".png",)),
]


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

    print("copied %d files into results/" % kept)
    if missing:
        print("not present (skipped): " + ", ".join(missing))


if __name__ == "__main__":
    main()
