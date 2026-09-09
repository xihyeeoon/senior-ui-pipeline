r"""Run run_local.py once per split screen, sequentially.

Sequential on purpose: this account's gpt-4o TPM budget is 30k and a single
property prompt is 10-15k tokens, so parallel screens would spend the whole run
in 429 backoff.

Usage: python tools/run_screens.py [screen ...]   # needs the repo served on :3003
"""
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
SCREENS = ["home", "recipient", "bank", "account", "amount",
           "confirm", "password", "done"]

targets = sys.argv[1:] or SCREENS
os.makedirs(os.path.join(ROOT, "logs", "transfer"), exist_ok=True)

for i, name in enumerate(targets, 1):
    env = dict(os.environ)
    env.update({
        # Upstream opens its logs and writes the repaired file with no encoding
        # argument, so Windows picks cp949 and dies on the first non-KS X 1001
        # glyph - this page has ⌂, ⌫, ☺, emoji. UTF-8 mode (PEP 540) changes
        # open()'s default to UTF-8 without patching the vendored source.
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "DESIGNREPAIR_MODEL": "gpt-4o",
        "DESIGNREPAIR_SYSTEM_KB": os.path.join(ROOT, "kb", "senior_kb.csv"),
        "DESIGNREPAIR_FILE_DIR": os.path.join(ROOT, "outputs", "screens"),
        "DESIGNREPAIR_FILE": name + ".html",
        "DESIGNREPAIR_URL": "http://localhost:3003/outputs/screens/%s.html" % name,
    })
    log = os.path.join(ROOT, "logs", "transfer", name + ".log")
    print("[%d/%d] %s -> %s" % (i, len(targets), name, log), flush=True)
    t0 = time.time()
    with open(log, "wb") as fh:
        rc = subprocess.call([PY, os.path.join(ROOT, "run_local.py")],
                             env=env, stdout=fh, stderr=subprocess.STDOUT)
    print("      rc=%d  %.0fs" % (rc, time.time() - t0), flush=True)

print("ALL DONE")
