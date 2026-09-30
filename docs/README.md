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

### Flow files: two ways to enter text

A flow's `type` action works with either input style, and the selector says
which.

```json
{"type": "{ACCOUNT}", "key": "[data-action='acc-num'][data-v='%s']"}   // 숫자판
{"type": "{ACCOUNT}", "key": "#acc-input"}                             // 입력 칸
```

A `%s` means there is one button per digit, and the auditor clicks them in turn.
No `%s` means the selector addresses a field, and the auditor calls `fill()`
once. A design with a real `<input>` should use the second form.

Models often write the first form while building the second -
`"input[data-action='x'][data-v='%s']"` - because the example they read showed a
keypad. Dropping the `%s` attribute from that selector leaves a real element; if
it is an `<input>` or `<textarea>`, the auditor fills it and records what it did
in `metrics.flow_notes`. It does not silently accept the mismatch.

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

The JSON is for machines. `tools/audit_report.py` turns any number of those
files into one side-by-side Markdown table (overview, per-check A–H, the
metrics behind each check, what was stood down, and with `--details` every
finding):

```powershell
.\.venv\Scripts\python.exe tools\audit_report.py 규칙기반=results\audit.json `
   Run1=results\audit_restructured.json Run2=results\audit_run2.json Run3=results\audit_run3.json `
   --details --out results\audit-report.md
```

It reuses `tools/verify_flow.py` (required ids), `tools/check_contrast.py` (the
WCAG probe) and `tools/runtime_audit.py` (the flow definition); those three still
work standalone. The in-page JS lives in `tools/audit_probes.py`.

Known gaps, both real: it cannot tell that `☆` labelled "선택됨" is factually
inverted (that needs a declared class↔label mapping), and it has no
duplicate-text check, so `confirm`'s doubled "수수료 무료" passes.

## The pipeline, and what sits outside it

```
캡처 → LLM 재구성 → 검사기 → (스타일 이식) → 실험
```

The tool's output is a **wireframe-level structural proposal**; a designer fills
in the visual detail afterwards. That shapes everything below, including how the
auditing works.

| | |
|---|---|
| **파이프라인** | the chain above. Neither DesignRepair nor `senior_kb.csv` is in it. |
| **실험 조건** | 원본 vs 재구성본, two conditions, on real elderly participants. |
| **보관 자료** | DesignRepair results and `kb/senior_kb.csv`. Kept, not used. `vendor/designrepair/` stays too. |

**DesignRepair was dropped from the research on 2026-09-30.** It repairs the
visual quality of a finished screen, which is a different job from proposing a
structure, and the two branches could not be given the same input unit: feeding
DesignRepair the whole file needs 39,276 tokens against a 30,000 TPM account
limit. A fair comparison is therefore not available, so the two results are not
compared. `docs/comparison-validity.md` records how that was established and is
closed.

`kb/senior_kb.csv` stays for **사후 대조** - checking after the fact which rules a
design happens to satisfy. It is not fed to anything in the pipeline.

## Two audit stages

Because the tool now emits a wireframe first and a styled build later, the
checks split in two. `tools/audit_stage.py` wraps `tools/audit.py` without
modifying it.

| stage | checks | why |
|---|---|---|
| `wireframe` | A 과제 완주 · B 표시 정확성 · C 죽은 컨트롤 · F 언어 | contrast, layout, state colour and undefined classes are about detail nobody has filled in yet |
| `styled` | A~H | everything |

```powershell
.\.venv\Scripts\python.exe toolsudit_stage.py --flow toolslows
estructured.json `
   --repaired http://localhost:3003/outputs/restructured_transfer.html `
   --repaired-file outputs
estructured_transfer.html --stage wireframe
```

The stage can also live in the flow file as `"stage": "wireframe"`; the flag
wins. A flow with neither runs everything, so existing flows behave as before.
Dropped checks are recorded in `checks_stood_down` with the reason, the same
place `audit.py` already notes what it stood down.

## The viewer

`시작.bat` (or `python tools/session_server.py`) serves the project and opens
**`tools/viewers/dashboard.html`** - four pages for checking where things stand
while working:

| | |
|---|---|
| 대시보드 | one row per build: passed, fatal, warning, screens, low-contrast before→after, flow |
| 화면 비교 | 2-4 builds side by side at 390px, each with its own screen picker. Screen names differ between designs (original `account` vs Run 1 `accno`+`bank`), so nothing is auto-synced. A screenshot mode swaps the iframes for the png in `outputs/shots`, which needs no server and shows the state as captured. |
| 검사 결과 | audits side by side, folded per check A-H. Findings link to that screen's screenshot; stood-down checks say why; the metric table is folded away because a count is not a grade. |
| 변경 추적 | the changelog's changes with rule filters, and all 46 KB rules split by whether a table actually cites them |

It reads one file, `outputs/index.json`, written by **`tools/build_index.py`**.
Builds are discovered, not listed: each audit JSON records the URL of the build
it drove and the flow it used, so a new build with its own audit appears without
editing anything. Screenshots are matched by flow name, then build id, then the
older flat `before_`/`after_` convention.

```powershell
.\.venv\Scripts\python.exe toolsuild_index.py --print
```

The "다시 읽기" button asks the server to rebuild the index first, so editing a
file and pressing it is enough. `builds[].attempts` is reserved for the
generate-audit-regenerate loop and is empty until that lands.

Two numbers the viewer deliberately keeps apart: the changelog's tables cite
**26** of the 46 rules, while the document claims **33** are met. The extra 7 are
the author's own judgement with no table behind them, which the document itself
flags as optimistic.

## Older viewers

- `tools/viewers/kb_compare.html` — example1 under the base KB vs the senior KB. A different experiment; left alone.
- `outputs/compare/kb-compare.html` — the same comparison as one self-contained file (no server, no CDN). Rebuild with `node tools\compareuild.js`, then the tailwind CLI step and `tools\compare\make_standalone.py`.

`tools/viewers/transfer_compare.html`, `tools/dashboard.html` and
`tools/pipeline_state.py` were removed: the four pages above cover what they did.

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
