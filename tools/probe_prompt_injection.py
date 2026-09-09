"""Dump the exact prompt DesignRepair sends for a property group.
No API call, no key needed beyond a dummy (module-level OpenAI client)."""
import sys, os, json
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "vendor", "designrepair", "backend"))
sys.path.insert(0, ROOT)
os.environ.setdefault("OPENAI_API_KEY", "sk-dummy")

from run_local import load_system_level_guidelines
from core.analysis_groups import assemble_analysis_property_prompt

PROP = sys.argv[1] if len(sys.argv) > 1 else "Text"
KB   = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "kb", "system_design_knowledge_base_senior.csv")

file_content = open(os.path.join(ROOT, "vendor", "designrepair", "examples", "example1.tsx"), encoding="utf-8").read()
extracted = json.load(open(os.path.join(ROOT, "outputs", "stream_b_properties.json"), encoding="utf-8"))
props = extracted.get(PROP, [])

g = load_system_level_guidelines(KB)
prompt, functions = assemble_analysis_property_prompt(file_content, g[PROP], PROP, props)

user_msg = [m for m in prompt if m["role"] == "user"][0]["content"]
out = os.path.join(ROOT, "outputs", f"prompt_{PROP}_{os.path.basename(KB).split('.')[0][-6:]}.txt")
with open(out, "w", encoding="utf-8") as f:
    f.write(user_msg)
print(f"property={PROP}  kb={os.path.basename(KB)}")
print(f"  hard rules injected : {len(g[PROP]['hard'])}")
print(f"  soft rules loaded   : {len(g[PROP]['soft'])}  <- check if they appear below")
print(f"  prompt chars        : {len(user_msg):,}")
print(f"  saved -> {out}")
