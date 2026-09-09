r"""DesignRepair local runner.

Layout (everything under C:\Users\xihye\designrepair\):
    vendor\designrepair\   pristine upstream clone (never modified)
    .venv\          python 3.12 env
    inputs\page\    rendered page served at PAGEURL
    outputs\        repaired code + logs land here (NOT inside the clone)
    tools\          probe / mock-server helpers

Fixes applied on top of upstream test.py:
    1. KB filename   -> library/component_knowledge_base.json
                        (upstream test.py says "components_..." -> FileNotFoundError)
    2. pydantic v2   -> root_directory must be Optional[str], not str = None
    3. model remap   -> DESIGNREPAIR_MODEL env var; upstream's gpt-4-1106-preview and
                        gpt-4-turbo-2024-04-09 are both shut down 2026-10-23
    4. outputs       -> written to outputs\, keeping the clone clean

Usage (PowerShell), with page\ served at http://localhost:3000 :
    $env:OPENAI_API_KEY = "sk-..."
    $env:DESIGNREPAIR_MODEL = "gpt-4o"      # optional; omit for paper-faithful models
    C:\Users\xihye\designrepair\.venv\Scripts\python.exe C:\Users\xihye\designrepair\run_local.py
"""
import os, sys, json, csv, asyncio
from typing import Optional

ROOT     = os.path.dirname(os.path.abspath(__file__))
REPO     = os.path.join(ROOT, "vendor", "designrepair")
BACKEND  = os.path.join(REPO, "backend")
LIBRARY  = os.path.join(REPO, "library")
OUTPUTS  = os.path.join(ROOT, "outputs")

sys.path.insert(0, BACKEND)
os.makedirs(OUTPUTS, exist_ok=True)
os.chdir(OUTPUTS)                      # fix 4: repo-relative writes land in outputs\

from pydantic import BaseModel
from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".envs"))

# --- fix 3 (model remap) + fix 5 (429 backoff) ------------------------------
# This account's gpt-4o TPM limit is 30k and a single property prompt is ~10-15k
# tokens, so consecutive calls trip 429. Retry with the delay the API asks for.
_OVERRIDE = os.environ.get("DESIGNREPAIR_MODEL")
_RETRIES  = int(os.environ.get("DESIGNREPAIR_RETRIES", "6"))

import asyncio as _asyncio, re as _re, time as _time
import core.llm as _llm
_orig = _llm.stream_openai_response

async def _patched(*a, **kw):
    if _OVERRIDE:
        kw["model"] = _OVERRIDE
    last = None
    for attempt in range(_RETRIES):
        try:
            return await _orig(*a, **kw)
        except Exception as e:
            if type(e).__name__ not in ("RateLimitError", "APIConnectionError", "APITimeoutError"):
                raise
            last = e
            m = _re.search(r"try again in ([0-9.]+)s", str(e))
            wait = float(m.group(1)) + 1.5 if m else min(60, 5 * 2 ** attempt)
            print(f"[run_local] {type(e).__name__}, retry {attempt+1}/{_RETRIES} in {wait:.1f}s")
            await _asyncio.sleep(wait)
    raise last

_llm.stream_openai_response = _patched
import core.analysis_groups as _g, core.analysis_utils as _u
_g.stream_openai_response = _patched
_u.stream_openai_response = _patched
print(f"[run_local] model override -> {_OVERRIDE or '(none, paper default)'} | retries={_RETRIES}")

from core.analysis_components import analysis_components
from core.analysis_groups import analysis_groups
from core.analysis_utils import repair_to_full_code


class FileContext(BaseModel):
    file_name: str
    file_dir: str
    file_content: str
    root_directory: Optional[str] = None        # fix 2
    example_content: Optional[str] = None


def process_file(file_dir, file_name):
    with open(os.path.join(file_dir, file_name), "r", encoding="utf-8") as f:
        return FileContext(file_name=file_name, file_dir=file_dir, file_content=f.read())


def load_component_guidelines(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def load_system_level_guidelines(p):
    out = {}
    with open(p, "r", newline="", encoding="utf-8") as fh:
        for row in csv.reader(fh):
            if not row or row[0] == "material_design_section" or len(row) != 6:
                continue
            if row[1] not in ["Structure","Flow","Layout","Implement","Label","Text",
                              "Color","Typography","Shape","Icon","Elevation"]:
                continue
            if row[2] not in ["Group","Clickable","Spacing","Platform","Label","Text",
                              "Color","all elements","Icon"]:
                continue
            if row[3] not in ["soft","hard"]:
                continue
            out.setdefault(row[2], {"soft": [], "hard": []})[row[3]].append(row)
    return out


if __name__ == "__main__":
    FILE_DIR  = os.environ.get("DESIGNREPAIR_FILE_DIR", os.path.join(REPO, "examples"))
    FILE_NAME = os.environ.get("DESIGNREPAIR_FILE", "example1.tsx")
    PAGEURL   = os.environ.get("DESIGNREPAIR_URL", "http://localhost:3000/")

    COMP_KB   = os.path.join(LIBRARY, "component_knowledge_base.json")      # fix 1
    SYSTEM_KB = os.environ.get("DESIGNREPAIR_SYSTEM_KB",
                               os.path.join(LIBRARY, "system_design_knowledge_base.csv"))

    print(f"[run_local] file    : {os.path.join(FILE_DIR, FILE_NAME)}")
    print(f"[run_local] page    : {PAGEURL}")
    print(f"[run_local] outputs : {OUTPUTS}")
    print(f"[run_local] system KB: {SYSTEM_KB}")

    ctx = process_file(FILE_DIR, FILE_NAME)
    folder = ctx.file_name.split(".")[0]
    os.makedirs(folder, exist_ok=True)

    print("== A. component stream ==")
    comp = asyncio.run(analysis_components(ctx, load_component_guidelines(COMP_KB)))
    asyncio.run(repair_to_full_code(ctx, comp, "", folder, "comp_"))

    print("== B. property stream (playwright) ==")
    prop = asyncio.run(analysis_groups(ctx, load_system_level_guidelines(SYSTEM_KB), PAGEURL))
    asyncio.run(repair_to_full_code(ctx, "", prop, folder, "property_"))

    print("== C. merged repair ==")
    asyncio.run(repair_to_full_code(ctx, comp, prop, folder, ""))
    print("done ->", os.path.join(OUTPUTS, folder))
