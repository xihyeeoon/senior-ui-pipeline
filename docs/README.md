# senior-ui-pipeline

Running [DesignRepair](https://github.com/UGAIForge/DesignRepair)
(arXiv:2411.01606) against a senior-usability knowledge base, and auditing what
comes out.

## Layout

| Path | What | Tracked |
|---|---|---|
| `vendor/designrepair/` | Pristine upstream clone, still its own git checkout. **Never modified.** | no — pull it yourself |
| `kb/senior_kb.csv` | The replacement system-level KB. 46 rows, rule ids in the `relation` column (`SDF-*` x41, `KS-*` x5). | yes |
| `inputs/` | What the pipeline reads: `original_transfer.html` (8-screen transfer prototype), `page/` and `page-bank/` (example1 precompiled to a static page). | yes |
| `tools/` | Everything written for this project — runners, probes, the auditor, the viewers. | yes |
| `run_local.py` | The runner. Upstream `backend/test.py` plus the fixes listed below. | yes |
| `outputs/` | Repaired code, split screens, screenshots, audit JSON. Regenerable. | no |
| `logs/` | Per-screen pipeline logs. | no |
| `results/` | The evidence worth keeping, copied out of `outputs/` and `logs/` by `tools/collect_results.py`. | **yes** |
| `.venv/`, `.envs` | Python 3.12 env; `.envs` holds `OPENAI_API_KEY`. | no |

`outputs/` and `logs/` are ignored because they are large and mostly
regenerable — but `logs/transfer/*.log` is *not* cheaply regenerable. The
pipeline never writes its suggestion JSON to disk, so those prompt dumps are the
only record of what the property stream actually suggested; recreating them
costs ~40 minutes and a round of API spend. That is why `results/` exists.

## Run

Serve the project root once and leave it up — every tool defaults to
`http://localhost:3003/…` paths under it:

```powershell
.\.venv\Scripts\python.exe -m http.server 3003 --directory .
```

Full pipeline over the 8-screen transfer prototype:

```powershell
.\.venv\Scripts\python.exe tools\split_screens.py     # inputs -> outputs/screens/
.\.venv\Scripts\python.exe tools\run_screens.py       # DesignRepair, one screen at a time
.\.venv\Scripts\python.exe tools\reassemble.py        # -> outputs/repaired_transfer.html
.\.venv\Scripts\python.exe tools\audit.py             # -> outputs/audit.json, exit 1 if fatal
```

`run_screens.py` sets `PYTHONUTF8=1` for the child process. It has to: upstream
opens its logs and writes the repaired file with no encoding argument, so
Windows picks cp949 and dies on the first character outside KS X 1001 — this
input has `⌂`, `⌫`, `☺` and emoji.

Single example1 run:

```powershell
$env:DESIGNREPAIR_MODEL = "gpt-4o"
$env:DESIGNREPAIR_SYSTEM_KB = "$PWD\kb\senior_kb.csv"
.\.venv\Scripts\python.exe run_local.py
```

Playwright-only checks, no API key needed: `tools\probe_stream_b.py`,
`tools\probe_screens.py`, `tools\check_contrast.py`, `tools\verify_flow.py`.

## The auditor

`tools/audit.py` drives the original and the repaired build through the same
8-screen task and diffs them. It prints machine-readable JSON and exits 0 only
when nothing fatal fired, so it can gate a regenerate-on-failure loop.

| | Check | Severity |
|---|---|---|
| A | 8 screens reached, amount round-trips, `data-action`/`id`/`data-screen` preserved | fatal |
| B | displayed values match what was entered; no injected `alert()`/`onclick`; no hardcoded numbers | fatal |
| C | `data-action` with no branch in the handler; `data-action` that disappeared | fatal |
| D | low-contrast count must not grow; new text must not rely on inherited colour; an already-low-contrast element must not gain readable text | warning |
| E | overlapping text, content spilling out of its box, newly wrapping text, screens much taller | warning |
| F | English words the original did not have (runtime and markup-only) | warning |
| G | `.x` and `.x.on` must still render differently | warning |
| H | classes the markup uses that no stylesheet defines | warning |

H is not in the original brief. It was added because it is the shared root cause
of two rendering failures: example1's `bg-primary`/`text-primary` and the
transfer run's `sr-only`. A class no stylesheet defines does nothing, so a label
meant to be hidden shows up and a colour meant to be applied never lands.

It reuses `tools/verify_flow.py` (required ids), `tools/check_contrast.py` (the
WCAG probe) and `tools/runtime_audit.py` (the flow definition); those three still
work standalone. The in-page JS lives in `tools/audit_probes.py`.

Known gaps, both real: it cannot tell that `☆` labelled "선택됨" is factually
inverted (that needs a declared class↔label mapping), and it has no
duplicate-text check, so `confirm`'s doubled "수수료 무료" passes.

## Viewers

Served from the project root:

- `tools/viewers/transfer_compare.html` — the 8 screens before/after, side by side, with per-screen findings.
- `tools/viewers/kb_compare.html` — example1 under the base KB vs the senior KB.
- `outputs/compare/kb-compare.html` — the same comparison as one self-contained file (no server, no CDN). Rebuild with `node tools\compare\build.js`, then the tailwind CLI step and `tools\compare\make_standalone.py` (order is in that file's docstring).

## Fixes layered on top of upstream

In `run_local.py`, so the clone stays pristine:

1. **KB filename** — upstream `test.py:102` opens `components_knowledge_base.json`; the file is `component_knowledge_base.json`. Otherwise `FileNotFoundError`.
2. **pydantic v2** — `root_directory: str = None` raises `ValidationError` on pydantic 2.x, and pydantic is not pinned in `pyproject.toml`. Fixed to `Optional[str]`.
3. **Model shutdown** — upstream uses `gpt-4-1106-preview` and `gpt-4-turbo-2024-04-09`; both shut down 2026-10-23. `DESIGNREPAIR_MODEL` overrides them.
4. **Rate limits** — 30k TPM against 10–15k-token property prompts, so consecutive calls trip 429. Retries with the delay the API asks for.
5. **Output location** — upstream writes into `backend/<name>/`; the runner chdirs to `outputs/`.
6. **Encoding** — `PYTHONUTF8=1` from `tools/run_screens.py`, see above.

Not on the execution path but worth knowing: `core/llm.py` still defines
`gpt-4-vision-preview`, removed from the API in Dec 2024.

## Findings so far

`docs/senior-kb-handoff.md` has the full write-up. In short: the senior KB makes
DesignRepair cite traceable rule ids (150 of 173 suggestions, 27 distinct rules
of 46) where the upstream KB cited none, and it does produce the intended
changes — bigger text, more contrast, lower density, plainer wording. It also
introduces conflicts the rules do not resolve among themselves: a contrast rule
repaints a deliberately-dimmed disabled button, an icon-labelling rule adds
English to a KB that forbids English, and a feedback rule injects
`alert('1원이 전송됩니다')` with the amount hardcoded.
