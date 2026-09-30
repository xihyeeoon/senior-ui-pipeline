r"""Run DesignRepair once over the WHOLE original file, not screen by screen.

Why this exists: the earlier rule-based run fed DesignRepair one screen at a
time and withheld the transition script (tools/split_screens.py), so the model
could not see that there were other screens at all - let alone decide to split
one. The LLM restructuring got the whole file. Comparing the two and concluding
"rules cannot change structure" was therefore unsound; see
docs/comparison-validity.md.

This run changes exactly one variable: the input unit.

  same as before   model gpt-4o, kb/senior_kb.csv (46 rules), no task description
  different        the whole 597-line file in one call, script included

Deliberately NOT given: what the user is trying to do. The restructuring prompt
described the transfer task, but "structure only changes when the model knows
the task" is a separate hypothesis and would confound this one.

Output goes to outputs/original_transfer/ (upstream names the folder after the
file), which does not collide with the per-screen folders from the earlier run.
Nothing existing is overwritten.

Usage: python tools/run_whole.py      # needs the repo served on :3003
"""
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")

env = dict(os.environ)
env.update({
    # Upstream writes with no encoding argument; this page has ⌂ ⌫ ☺ and emoji.
    "PYTHONUTF8": "1",
    "PYTHONIOENCODING": "utf-8",
    # Same model and same KB as the per-screen run, so the only difference is
    # that the model now sees the whole document.
    "DESIGNREPAIR_MODEL": "gpt-4o",
    "DESIGNREPAIR_SYSTEM_KB": os.path.join(ROOT, "kb", "senior_kb.csv"),
    "DESIGNREPAIR_FILE_DIR": os.path.join(ROOT, "inputs"),
    "DESIGNREPAIR_FILE": "original_transfer.html",
    "DESIGNREPAIR_URL": "http://localhost:3003/inputs/original_transfer.html",
})

log_dir = os.path.join(ROOT, "logs", "whole")
os.makedirs(log_dir, exist_ok=True)
log = os.path.join(log_dir, "original_transfer.log")

print("전체 파일 1회 실행 -> %s" % log, flush=True)
print("  입력 : inputs/original_transfer.html (597줄, 쪼개지 않음)", flush=True)
print("  모델 : gpt-4o    KB : kb/senior_kb.csv (46개)", flush=True)
print("  출력 : outputs/original_transfer/", flush=True)
t0 = time.time()
with open(log, "wb") as fh:
    rc = subprocess.call([PY, os.path.join(ROOT, "run_local.py")],
                         env=env, stdout=fh, stderr=subprocess.STDOUT)
print("rc=%d  %.0f초" % (rc, time.time() - t0), flush=True)
sys.exit(rc)
