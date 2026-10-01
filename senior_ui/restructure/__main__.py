r"""Restructure-and-audit loop: ask an LLM for a redesigned transfer prototype,
audit it with senior_ui.audit, feed the fatal findings back, up to N attempts.

What used to be three manual steps - paste a prompt into a chat, save the HTML
it returns, run audit.py, read the JSON, ask again - is one command:

  1. serve the project root on :3003 (only if nothing is listening already)
  2. up to --attempts times:
       a. build the prompt from docs/restructure-prompt.md (+ the previous
          attempt's fatal list on a retry), call the model
       b. split the reply into HTML + flow JSON, save both under outputs/
       c. audit it - senior_ui.audit is imported and called, never edited
       d. stop on pass; otherwise carry the fatal list into the next prompt
  3. stop the server if this script started it
  4. copy the final build to outputs/restructured_auto.html (+ .flow.json,
     audit_auto.json) and write summary.json next to the per-attempt files

Everything from a run lands in outputs/restructure_auto/<timestamp>/:
  attempt_N.prompt.txt   the exact prompt sent
  attempt_N.response.txt the raw reply
  attempt_N.html / attempt_N.flow.json
  attempt_N.audit.json   audit.py's report (or the parse/validation failure)
  shots/attempt_N/       one screenshot per screen reached
  run.log, summary.json

Usage:
  python -m senior_ui.restructure                 # real model, 3 attempts
  python -m senior_ui.restructure --attempts 2 --model gpt-4o
  python -m senior_ui.restructure --mock pass     # no API: replays Run 1
  python -m senior_ui.restructure --mock fail     # no API: a broken flow, every attempt fails

The key comes from .envs (OPENAI_API_KEY=...) or the environment. The model
comes from --model, then RESTRUCTURE_MODEL, then DESIGNREPAIR_MODEL, then gpt-4o.
Exit: 0 = a build passed, 1 = every attempt failed, 2 = could not run.
"""
import argparse
import asyncio
import datetime
import io
import json
import os
import re
import shutil
import sys
import time

from senior_ui import audit as A
from senior_ui.audit import stage as S
from senior_ui.config import (FLOWS_DIR, ORIGINAL_FILE, ORIGINAL_URL,
                              OUTPUTS_DIR, PORT, ROOT, url_for)
# listening 은 여기서 쓰지 않는다. 기준값 캡처(tests/_api.py)가 이 이름을
# run_restructure 에서 가져다 쓰던 것을 그대로 유지하기 위한 재수출이다.
from senior_ui.devserver import ensure_server, listening    # noqa: F401

PROMPT_FILE = os.path.join(ROOT, "docs", "restructure-prompt.md")
RUNS_DIR = os.path.join(OUTPUTS_DIR, "restructure_auto")


# --------------------------------------------------------------------------- #
# setup
# --------------------------------------------------------------------------- #
def load_env():
    """OPENAI_API_KEY from .envs if the environment does not have it. The file
    is KEY=value lines, quotes optional, '#' comments."""
    if os.environ.get("OPENAI_API_KEY"):
        return
    path = os.path.join(ROOT, ".envs")
    if not os.path.exists(path):
        return
    for line in io.open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_template():
    text = io.open(PROMPT_FILE, encoding="utf-8").read()
    m = re.search(r"<!-- PROMPT -->\n(.*?)<!-- /PROMPT -->", text, re.S)
    if not m:
        raise RuntimeError("no <!-- PROMPT --> block in " + PROMPT_FILE)
    return m.group(1)


def build_prompt(template, original_html, retry_block, choices=""):
    return (template.replace("{{ORIGINAL_HTML}}", original_html)
                    .replace("{{RETRY_BLOCK}}", retry_block)
                    .replace("{{CHOICES}}", choices))


ARRAY_DECL = re.compile(r"(?:const|let|var)\s+([A-Za-z_]\w*)\s*=\s*\[([^\]]*)\]")


def choices_block(orig_snapshot, original_html):
    """원본이 가진 반복 선택지를 요약한다.

    검사 I 가 렌더링된 DOM 에서 수집하는 바로 그 집합을 쓴다. 모델이 보는 것과
    검사가 세는 것이 어긋나면 안 되기 때문이다. 원본은 은행 67개를 스크립트
    배열로만 들고 있어서, 프롬프트에 원본 파일을 그대로 넣으면 마크업에는
    템플릿 조각 하나만 보인다 - 모델이 스크립트를 읽어야만 발견한다.

    마크업에 직접 쓰인 것(숫자판 등)과 스크립트가 그리는 것(은행 목록 등)을
    가른다. 전자는 그대로 두면 되고, 후자만 "배열을 참조해 그려라" 가 된다.
    은행이나 금융에 묶이지 않은 일반 규칙이다."""
    groups = {}
    for row in (orig_snapshot.get("screens") or {}).values():
        for action, vals in (row.get("choices") or {}).items():
            groups.setdefault(action, set()).update(vals)
    if not groups:
        return ""

    script = "\n".join(re.findall(r"<script[^>]*>(.*?)</script>", original_html, re.S))
    arrays = [(name, [v.strip().strip("'\"") for v in body.split(",") if v.strip()])
              for name, body in ARRAY_DECL.findall(script)]

    generated, inline = [], []
    for action, vals in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        in_markup = len(re.findall(r'data-action="%s"' % re.escape(action), original_html))
        # 그 선택지 값을 담고 있는 스크립트 배열을 찾는다
        src = [(n, len(items)) for n, items in arrays
               if items and len(set(items) & vals) >= max(2, len(items) // 2)]
        if in_markup < len(vals):
            where = (" (%s)" % " + ".join("%s %d" % (n, c) for n, c in src)) if src else ""
            generated.append("  %s — %d개%s" % (action, len(vals), where))
        else:
            inline.append("  %s — %d개" % (action, len(vals)))

    out = ["## 원본이 가진 선택지", ""]
    if generated:
        out += ["원본의 반복 선택지 (스크립트가 런타임에 그린다):", *generated, "",
                "이 배열들은 원본 그대로 두고, 화면은 그 배열을 참조해 그려라.",
                "목록 항목을 마크업에 직접 쓰지 마라. 몇 개를 보일지는 네가 정한다 —",
                "전부 보여도 되고, 검색이나 추정으로 좁혀도 된다. 다만 값은 하나도",
                "빠뜨리지 마라.", ""]
    if inline:
        out += ["마크업에 직접 있는 것 (그대로 두면 된다):", *inline, ""]
    return "\n".join(out)


def one_line(s):
    """Playwright errors carry a multi-line call log; keep it on one line so
    the log and the retry list stay one finding per line."""
    return re.sub(r"\s*\n\s*", " / ", str(s)).strip()


# Playwright 의 실패 로그는 1,100자쯤 되지만 쓸모 있는 것은 셋뿐이다:
# 어느 선택자를 기다렸는지, 그것이 어떤 요소로 풀렸는지, 왜 실패했는지.
WAITING_FOR = re.compile(r'waiting for locator\("([^"]+)"\)')
RESOLVED_TO = re.compile(r"locator resolved to (<[^>]+>)")
WHY = [(re.compile(r"element is not visible"), "화면에 보이지 않음"),
       (re.compile(r"element is not enabled"), "disabled 라 누를 수 없음"),
       (re.compile(r"element is not stable"), "움직이는 중"),
       (re.compile(r"resolved to \d+ elements"), "선택자가 여러 요소에 걸림")]
# stack 의 끝에 붙는 파일:줄:칸
STACK_LINE = re.compile(r":(\d+):\d+\)?\s*$", re.M)


def brief_failure(detail):
    """긴 Playwright 로그를 한 줄로. 남길 것은 선택자·요소·이유뿐이다.

    audit 이 " || " 뒤에 붙인 힌트(요소가 어느 화면에 있는지)가 있으면 그것이
    가장 중요한 정보다. 로그를 줄이면서 그 한 줄을 버리면 안 된다."""
    detail, _, hint = detail.partition(" || ")
    sel = WAITING_FOR.search(detail)
    el = RESOLVED_TO.search(detail)
    why = next((msg for pat, msg in WHY if pat.search(detail)), None)
    if not sel and not el:
        return one_line(detail)[:200]
    bits = []
    if sel:
        bits.append(sel.group(1))
        if not el:
            why = why or "그런 요소가 없음"
    if el:
        bits.append(el.group(1))
        if "disabled" in el.group(1):
            why = "disabled 가 풀리지 않음" + (" (%s)" % why if why else "")
    if why:
        bits.append(why)
    out = "  ".join(bits)
    if hint:
        out += "\n      → " + hint.strip()
    return out


def js_cause(report, prev_html):
    """JS 오류가 있으면 (설명 줄들) 을 만든다. 없으면 None.

    메시지만으로는 어디를 고칠지 알 수 없으므로 stack 에서 줄 번호를 뽑아
    그 줄의 코드를 함께 보여 준다."""
    details = (report.get("metrics") or {}).get("js_error_details") or []
    if not details:
        return None
    counts, first = {}, {}
    for d in details:
        key = "%s: %s" % (d.get("name") or "Error", d.get("message") or "")
        counts[key] = counts.get(key, 0) + 1
        first.setdefault(key, d)

    src = (prev_html or "").splitlines()
    out = []
    for key, n in counts.items():
        out.append("  %s  (%d회)" % (key, n))
        stack = first[key].get("stack") or ""
        m = STACK_LINE.search(stack)
        if m and src:
            ln = int(m.group(1))
            lo, hi = max(1, ln - 1), min(len(src), ln + 1)
            out.append("  발생 위치 — %d번째 줄 근처:" % ln)
            for i in range(lo, hi + 1):
                mark = ">" if i == ln else " "
                out.append("    %s %4d | %s" % (mark, i, src[i - 1].rstrip()[:100]))
    return out


def retry_block(report, prev_html, prev_flow_text):
    """The slot the template leaves for a retry.

    Listing every fatal buries the one that matters. A task that stops early
    fails every screen after it, a flow that revisits a screen records the same
    failure twice, and a JavaScript error takes the handler down so that
    *everything else is a symptom of it*. Handing the model nine items, with the
    real cause ninth and three copies of an 1,100-character Playwright log above
    it, is how the last run went - and it changed nothing across the retry.

    So: the cause first, the stall point next, and the consequences in one line
    that says not to fix them.
    """
    fatals = report.get("fatal") or []
    derived = [f for f in fatals if f.get("derived_from")]
    root = [f for f in fatals if not f.get("derived_from")]
    js = [f for f in root if "JavaScript errors" in (f.get("detail") or "")]
    other = [f for f in root if f not in js]

    parts = ["## 이전 시도의 실패", ""]
    cause = js_cause(report, prev_html)

    if cause:
        # 규칙 1: JS 오류가 있으면 그것이 유일한 원인이다.
        parts += ["[원인]",
                  "JavaScript 오류가 클릭 처리기를 중단시켰다. 이것만 고치면 된다.",
                  *cause,
                  "  → 선언하지 않은 이름을 쓴 것으로 보인다. 그 이름을 정의하거나 "
                  "쓰는 쪽을 고쳐라.",
                  "  선언하지 않은 전역 이름을 쓰는 실수가 반복되고 있다. "
                  "출력하기 전에, 코드에서 쓰는 모든 이름이 선언되어 있는지 확인하라.", ""]
        if other:
            parts += ["[막힌 지점]"]
            for f in other:
                where = (f.get("screen") + ": ") if f.get("screen") else ""
                parts.append("  " + where + brief_failure(f.get("detail", "")))
            parts.append("")
    else:
        # 규칙 4: JS 오류가 없으면 근본 fatal 만 나열한다.
        if other:
            parts += ["[고칠 것]"]
            for f in other:
                where = (f.get("screen") + ": ") if f.get("screen") else ""
                parts.append("  " + where + brief_failure(f.get("detail", "")))
            parts.append("")
        elif not derived:
            parts += ["(fatal 목록이 비어 있지만 통과하지 못했다)", ""]

    # 규칙 3: 파생은 한 줄로 묶는다.
    if derived:
        names = " · ".join(f.get("screen") or "?" for f in derived)
        head = "[아래는 위 원인의 결과다. 따로 고치지 마라]" if (cause or other) \
            else "[도달하지 못한 화면]"
        parts += [head, "  %s — 도달 못 함" % names, ""]

    parts += ["직전 출력을 고쳐라. 설계를 처음부터 새로 하지 마라.", ""]
    if prev_flow_text:
        parts += ["### 직전 흐름 명세", "", "```json", prev_flow_text.strip(), "```", ""]
    if prev_html:
        parts += ["### 직전 HTML", "", "```html", prev_html.strip(), "```", ""]
    return "\n".join(parts)


# --------------------------------------------------------------------------- #
# the model
# --------------------------------------------------------------------------- #
class RateLimited(Exception):
    """백오프를 다 쓰고도 429 가 계속된 경우. 설계 실패가 아니라 인프라 한도다."""


def call_model(model, prompt, max_tokens, log=None, backoff=(20, 45, 90, 180)):
    """시도마다 직전 HTML 전체를 다시 보내므로 프롬프트가 크다. 이 계정은 전에
    TPM 30,000 한도에 걸린 적이 있으므로 429 를 지수적으로 기다렸다 다시 친다.
    그래도 안 되면 RateLimited 를 올려 설계 실패와 섞이지 않게 한다."""
    from openai import OpenAI
    from openai import RateLimitError
    client = OpenAI()
    t0 = time.time()
    for i, wait in enumerate((0,) + tuple(backoff)):
        if wait:
            if log:
                log("429 — %d초 기다렸다 다시 시도 (%d/%d)" % (wait, i, len(backoff)))
            time.sleep(wait)
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=max_tokens,
            )
            break
        except RateLimitError as e:
            last = e
    else:
        raise RateLimited(str(last))
    choice = resp.choices[0]
    usage = getattr(resp, "usage", None)
    return {
        "text": choice.message.content or "",
        "finish_reason": choice.finish_reason,
        "seconds": round(time.time() - t0, 1),
        "usage": {"prompt": getattr(usage, "prompt_tokens", None),
                  "completion": getattr(usage, "completion_tokens", None)} if usage else None,
    }


def mock_reply(mode):
    """No API: replay Run 1. 'fail' hands back a flow whose second step clicks
    a selector that does not exist, so every attempt dies on screen 2."""
    html = io.open(os.path.join(OUTPUTS_DIR, "restructured_transfer.html"),
                   encoding="utf-8").read()
    flow = json.load(io.open(os.path.join(FLOWS_DIR, "restructured.json"),
                             encoding="utf-8"))
    flow["name"] = "auto"
    if mode == "fail":
        flow["steps"][1]["click"] = "[data-action='does-not-exist']"
    text = "```html\n%s\n```\n\n```json\n%s\n```\n" % (
        html, json.dumps(flow, ensure_ascii=False, indent=2))
    return {"text": text, "finish_reason": "stop", "seconds": 0.0, "usage": None}


FENCE = re.compile(r"```(html|json)[ \t]*\r?\n(.*?)\r?\n[ \t]*```", re.S)


def parse_reply(text):
    """Last ```html``` block and last ```json``` block. Raises ValueError with
    a message meant to go straight into the next prompt."""
    blocks = {}
    for kind, body in FENCE.findall(text):
        blocks[kind] = body
    if "html" not in blocks:
        raise ValueError("답에 ```html 코드 블록이 없다")
    if "json" not in blocks:
        raise ValueError("답에 ```json 흐름 명세 블록이 없다")
    html = blocks["html"]
    if "<html" not in html.lower() or "</html>" not in html.lower():
        raise ValueError("html 블록이 완전한 문서가 아니다 (<html> … </html> 필요)")
    try:
        flow = json.loads(blocks["json"])
    except json.JSONDecodeError as e:
        raise ValueError("흐름 명세가 JSON 으로 읽히지 않는다: %s" % e)
    return html, flow, blocks["json"]


def validate_flow(flow, html):
    """Shape checks audit.py would otherwise crash on, phrased for the model."""
    problems = []
    if not isinstance(flow, dict):
        return ["흐름 명세가 객체가 아니다"]
    steps = flow.get("steps")
    if not isinstance(steps, list) or not steps:
        problems.append("steps 가 비어 있다")
        steps = []
    # literal names only - a template literal like data-screen="${x}" in the
    # script is not a screen
    screens = set(re.findall(r'data-screen="([a-z0-9_-]+)"', html))
    if steps and isinstance(steps[0], dict) and ("click" in steps[0] or "do" in steps[0]):
        problems.append("steps[0] 은 시작 화면이므로 동작(click/do)이 없어야 한다. 각 step 의 "
                        "screen 은 그 동작을 한 *뒤에* 도착해 있는 화면이다 — 동작이 일어나는 "
                        "화면이 아니다. 목록 전체를 한 칸씩 다시 맞춰라")
    # audit.py reads the handler with exactly this pattern; a switch/case or a
    # differently named variable makes every data-action look dead to it.
    handled = set(re.findall(r"a\s*===\s*'([a-z-]+)'", html))
    actions = set(re.findall(r'data-action="([^"]+)"', html))
    if not handled:
        problems.append("클릭 처리기에 `a==='이름'` 분기가 하나도 없다. switch/case 나 다른 변수 "
                        "이름은 검사기가 읽지 못한다. `const a = el.dataset.action;` 뒤에 "
                        "`if(a==='이름'){…} else if(a==='이름'){…}` 형식으로 써라")
    else:
        dead = sorted(actions - handled)
        if dead:
            problems.append("data-action 이 있지만 `a==='…'` 분기가 없는 것: " + ", ".join(dead))
    for i, st in enumerate(steps):
        if not isinstance(st, dict) or "screen" not in st:
            problems.append("steps[%d] 에 screen 이 없다" % i)
            continue
        if st["screen"] not in screens:
            problems.append("steps[%d].screen=%r 은 HTML 의 data-screen 에 없다 (있는 것: %s)"
                            % (i, st["screen"], ", ".join(sorted(screens))))
        if i > 0 and "click" not in st and "do" not in st:
            problems.append("steps[%d] (%s) 에 click 도 do 도 없다" % (i, st["screen"]))

    # 화면을 넘기는 것은 클릭뿐이다. 타이핑으로 끝나는 단계는 다음 화면에 도달할
    # 수단이 없고, 검사기는 아직 켜지지 않은 화면 안의 요소를 찾다 멈춘다. 이것은
    # 브라우저를 띄우지 않고도 흐름 명세만 보면 알 수 있다.
    def has_click(item):
        return isinstance(item, dict) and "click" in item

    for i, st in enumerate(steps[:-1]):          # 마지막 화면은 넘어갈 곳이 없다
        if not isinstance(st, dict) or "screen" not in st:
            continue
        nxt = steps[i + 1].get("screen") if isinstance(steps[i + 1], dict) else "?"
        here = st["screen"]
        if "do" not in st:
            continue                              # click 하나짜리 단계는 문제없다
        do = st["do"] if isinstance(st["do"], list) else [st["do"]]
        if not do:
            continue
        if not any(has_click(x) for x in do):
            problems.append(
                "흐름 명세: %r 의 do 에 클릭이 하나도 없다. 타이핑과 대기만으로는 "
                "화면이 바뀌지 않으므로 %r 로 갈 수 없다. %s 에서 %s 로 넘어가는 "
                "클릭 단계를 추가하라." % (here, nxt, here, nxt))
        elif not has_click(do[-1]):
            kind = "type" if "type" in do[-1] else list(do[-1])[0] if do[-1] else "?"
            problems.append(
                "흐름 명세: %r 의 마지막 동작이 %s 이다. 타이핑은 화면을 넘기지 "
                "않으므로 %r 로 갈 수 없다. %s 에서 %s 로 넘어가는 클릭 단계를 "
                "추가하라." % (here, kind, nxt, here, nxt))
    # 값싼 조기 탐지. "나머지는 생략" 하고 끝낸 목록은 검사기 I 가 잡지만,
    # 브라우저를 띄우기 전에 걸러내면 한 번 덜 돈다. I 의 대체가 아니라 차단이다.
    OMIT = r"(\.\.\.|…|\betc\b|\bother\b|생략|나머지)"
    for m in re.finditer(r"<(ul|ol|select|tbody)\b[^>]*>(.*?)</\1>", html, re.S | re.I):
        tail = m.group(2)[-400:]
        if re.search(r"<!--[^-]*?%s.*?-->" % OMIT, tail, re.I | re.S) \
                or re.search(r">\s*%s\s*<" % OMIT, tail, re.I):
            problems.append(
                '목록이 "생략" 표시로 끝난다 (… / etc / other / 생략). 원본에 있던 '
                "선택지는 하나도 빠뜨리면 안 된다. 화면에 몇 개를 보일지는 네가 정하되 "
                "값은 전부 포함하라.")
            break

    ids = set(re.findall(r'\bid="([^"]+)"', html))
    req = flow.get("required_ids")
    if not isinstance(req, list):
        problems.append("required_ids 가 목록이 아니다")
        req = []
    for must in ("phone", "dn-amt"):
        if must not in req:
            problems.append("required_ids 에 %r 이 없다" % must)
        if must not in ids:
            problems.append("HTML 에 id=%r 요소가 없다" % must)
    missing = [i for i in req if i not in ids]
    if missing:
        problems.append("required_ids 중 HTML 에 없는 id: " + ", ".join(missing))
    expect = flow.get("expect")
    if not isinstance(expect, dict):
        problems.append("expect 가 객체가 아니다")
    else:
        done = expect.get("done") or []
        if not any(isinstance(p, list) and len(p) == 2 and p[0] == "#dn-amt" for p in done):
            problems.append('expect.done 에 ["#dn-amt", "{AMOUNT_SHOWN}"] 이 없다')
    if flow.get("derived_from_original", False):
        problems.append("derived_from_original 은 false 여야 한다")
    unseen = screens - {st.get("screen") for st in steps if isinstance(st, dict)}
    if unseen:
        problems.append("steps 가 지나가지 않는 화면: " + ", ".join(sorted(unseen)))
    return problems


def failure_report(kind, detail):
    """An audit-shaped report for a reply that never reached the audit, so the
    retry block and summary treat it like any other fatal."""
    return {"passed": False,
            "fatal": [{"check": kind, "screen": None, "detail": detail}],
            "warning": [], "metrics": {"flow": "auto", "not_audited": True}}


# --------------------------------------------------------------------------- #
# audit (senior_ui.audit, called as a library)
# --------------------------------------------------------------------------- #
def run_audit(orig_snapshot, orig_html, html_path, flow_path, url, shots, stage):
    """senior_ui.audit 로 검사한 뒤 단계 밖 검사를 걷어낸다. 와이어프레임 단계에서는
    대비·레이아웃·상태 색·미정의 클래스를 보지 않는다 - 아직 채우지 않은
    디테일이기 때문이다. 걸러낸 이유는 checks_stood_down 에 남는다."""
    flow = A.load_flow(flow_path)
    rep_html = io.open(html_path, encoding="utf-8").read()
    rep = asyncio.run(A.drive(url, flow, want_shots=shots))
    report = A.audit(orig_snapshot, rep, orig_html, rep_html, flow)
    report = S.apply_stage(report, stage)
    report["inputs"] = {"original": ORIGINAL_URL, "repaired": url, "flow": flow_path,
                        "stage": stage}
    return report


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--attempts", type=int, default=3,
                    help="두 예산의 기본값")
    ap.add_argument("--format-attempts", type=int, default=None,
                    help="흐름 명세 형식 오류에 쓸 재시도 횟수 (기본: --attempts)")
    ap.add_argument("--audit-attempts", type=int, default=None,
                    help="검사 fatal 에 쓸 재시도 횟수 (기본: --attempts)")
    ap.add_argument("--model", default=None)
    ap.add_argument("--max-tokens", type=int, default=16000,
                    help="completion cap; the HTML alone is ~12k tokens")
    ap.add_argument("--mock", choices=["pass", "fail"], default=None,
                    help="skip the API and replay Run 1 (fail: with a broken flow)")
    ap.add_argument("--original", default=ORIGINAL_FILE)
    ap.add_argument("--stage", choices=sorted(S.STAGES), default="styled",
                    help="검사 단계. wireframe 은 A·B·C·F 만 본다")
    ap.add_argument("--delay", type=float, default=15.0,
                    help="시도 사이 대기(초). 프롬프트가 커서 TPM 한도에 걸리기 쉽다")
    args = ap.parse_args()

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = os.path.join(RUNS_DIR, stamp + ("-mock-" + args.mock if args.mock else ""))
    os.makedirs(run_dir, exist_ok=True)
    log_path = os.path.join(run_dir, "run.log")

    def log(msg):
        line = "%s %s" % (datetime.datetime.now().strftime("%H:%M:%S"), msg)
        print(line, flush=True)
        with io.open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    load_env()
    model = args.model or os.environ.get("RESTRUCTURE_MODEL") \
        or os.environ.get("DESIGNREPAIR_MODEL") or "gpt-4o"
    if not args.mock and not os.environ.get("OPENAI_API_KEY"):
        print("no OPENAI_API_KEY in the environment or .envs", file=sys.stderr)
        return 2

    try:
        template = load_template()
        original_html = io.open(args.original, encoding="utf-8").read()
    except (OSError, RuntimeError) as e:
        print("cannot start: %s" % e, file=sys.stderr)
        return 2

    log("run: %s | model=%s | attempts=%d | stage=%s | mock=%s"
        % (run_dir, model, args.attempts, args.stage, args.mock))
    server = None
    summary = {"run_dir": run_dir, "model": model, "mock": args.mock,
               "stage": args.stage, "attempts": [], "passed": False, "final": None,
               "budget": {}, "stopped_reason": None, "trend": []}
    try:
        server = ensure_server(log)
        base_flow = A.load_flow(None)
        log("audit: driving the original once (baseline for contrast / language)")
        orig_snapshot = asyncio.run(A.drive(ORIGINAL_URL, base_flow))
        choices = choices_block(orig_snapshot, original_html)
        if choices:
            log("선택지: %s" % " / ".join(
                l.strip() for l in choices.splitlines() if l.startswith("  ")))

        prev = {"report": None, "html": None, "flow_text": None}
        # 예산을 둘로 나눈다. 형식 오류(흐름 명세가 규격에 안 맞음)와 검사 fatal
        # (설계가 과제를 통과 못 함)은 다른 종류의 실패이고, 한쪽이 예산을 다 쓰면
        # 다른 쪽은 재시도를 한 번도 못 받는 일이 생긴다 - Run 2 가 그랬다.
        fmt_budget = args.format_attempts if args.format_attempts is not None else args.attempts
        aud_budget = args.audit_attempts if args.audit_attempts is not None else args.attempts
        fmt_used = aud_used = 0
        n = 0
        while True:
            n += 1
            if n > 1 and args.delay and not args.mock:
                time.sleep(args.delay)
            log("---- attempt %d (형식 %d/%d · 검사 %d/%d)"
                % (n, fmt_used, fmt_budget, aud_used, aud_budget))
            block = retry_block(prev["report"], prev["html"], prev["flow_text"]) \
                if prev["report"] else ""
            prompt = build_prompt(template, original_html, block, choices)
            p = os.path.join(run_dir, "attempt_%d" % n)
            io.open(p + ".prompt.txt", "w", encoding="utf-8", newline="\n").write(prompt)
            log("prompt: %d chars%s" % (len(prompt), " (with retry block)" if block else ""))

            if args.mock:
                reply = mock_reply(args.mock)
            else:
                try:
                    reply = call_model(model, prompt, args.max_tokens, log)
                except RateLimited as e:
                    # 설계 실패가 아니다. 예산을 깎지 않고 여기서 멈춘다.
                    log("중단: 인프라 한도 — 백오프를 다 쓰고도 429 (%s)" % e)
                    summary["stopped_reason"] = "rate_limit"
                    report = failure_report("INFRA", "인프라 한도로 중단: %s" % e)
                    json.dump(report, io.open(p + ".audit.json", "w", encoding="utf-8"),
                              ensure_ascii=False, indent=2)
                    summary["attempts"].append({"n": n, "stage": "rate_limit",
                                                "passed": False, "error": str(e)})
                    break
                except Exception as e:                       # network, auth
                    log("model: call failed: %s" % e)
                    report = failure_report("LLM", "모델 호출 실패: %s" % e)
                    json.dump(report, io.open(p + ".audit.json", "w", encoding="utf-8"),
                              ensure_ascii=False, indent=2)
                    summary["attempts"].append({"n": n, "stage": "call", "passed": False,
                                                "error": str(e)})
                    prev = {"report": report, "html": prev["html"], "flow_text": prev["flow_text"]}
                    continue
            io.open(p + ".response.txt", "w", encoding="utf-8", newline="\n").write(reply["text"])
            log("model: %s chars, finish=%s, %ss, usage=%s"
                % (len(reply["text"]), reply["finish_reason"], reply["seconds"], reply["usage"]))

            entry = {"n": n, "finish_reason": reply["finish_reason"], "usage": reply["usage"],
                     "seconds": reply["seconds"]}
            try:
                if reply["finish_reason"] == "length":
                    raise ValueError("답이 길이 제한에서 잘렸다 (finish_reason=length). "
                                     "코드 블록 두 개만, 군더더기 없이 출력하라")
                html, flow, flow_text = parse_reply(reply["text"])
                flow.setdefault("name", "auto")
                flow["derived_from_original"] = False
                problems = validate_flow(flow, html)
            except ValueError as e:
                log("parse: %s" % e)
                report = failure_report("PARSE", str(e))
                entry.update(stage="parse", passed=False, fatal=1)
                json.dump(report, io.open(p + ".audit.json", "w", encoding="utf-8"),
                          ensure_ascii=False, indent=2)
                summary["attempts"].append(entry)
                prev = {"report": report, "html": prev["html"], "flow_text": prev["flow_text"]}
                fmt_used += 1
                if fmt_used >= fmt_budget:
                    log("형식 재시도 예산 소진 (%d회)" % fmt_used)
                    break
                continue

            html_path, flow_path = p + ".html", p + ".flow.json"
            io.open(html_path, "w", encoding="utf-8", newline="\n").write(html)
            io.open(flow_path, "w", encoding="utf-8", newline="\n").write(
                json.dumps(flow, ensure_ascii=False, indent=2))
            entry["html"], entry["flow"] = html_path, flow_path

            if problems:
                log("flow: %d problem(s): %s" % (len(problems), " | ".join(problems)[:300]))
                report = {"passed": False, "warning": [], "metrics": {"flow": "auto", "not_audited": True},
                          "fatal": [{"check": "FLOW", "screen": None, "detail": d} for d in problems]}
                entry.update(stage="flow", passed=False, fatal=len(problems))
                fmt_used += 1
            else:
                rel = os.path.relpath(html_path, ROOT).replace(os.sep, "/")
                url = url_for(rel)
                shots = os.path.join(run_dir, "shots", "attempt_%d" % n)
                os.makedirs(shots, exist_ok=True)
                try:
                    report = run_audit(orig_snapshot, original_html, html_path,
                                       flow_path, url, shots, args.stage)
                except Exception as e:                       # a flow audit.py cannot drive
                    log("audit: crashed: %s: %s" % (type(e).__name__, e))
                    report = failure_report("AUDIT", "검사기가 흐름 명세를 실행하지 못했다: %s: %s"
                                            % (type(e).__name__, e))
                entry.update(stage="audit", passed=bool(report.get("passed")),
                             fatal=len(report.get("fatal", [])),
                             warning=len(report.get("warning", [])))
                if not report.get("passed"):
                    aud_used += 1
                m = report.get("metrics", {})
                summary["trend"].append({
                    "attempt": n, "fatal_total": m.get("fatal_total"),
                    "fatal_root": m.get("fatal_root"), "fatal_derived": m.get("fatal_derived"),
                    "screens": "%s/%s" % (m.get("screens_reached"), m.get("screens_expected")),
                    "stopped_at": m.get("stopped_at")})
                log("audit: passed=%s fatal=%d (근본 %s) warning=%d screens=%s/%s"
                    % (report.get("passed"), len(report.get("fatal", [])), m.get("fatal_root"),
                       len(report.get("warning", [])), m.get("screens_reached"),
                       m.get("screens_expected")))
                for f in report.get("fatal", [])[:8]:
                    log("  F [%s] %s%s" % (f.get("check"), ("%s: " % f["screen"]) if f.get("screen") else "",
                                          one_line(f.get("detail", ""))[:160]))

            json.dump(report, io.open(p + ".audit.json", "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
            summary["attempts"].append(entry)
            summary["final"] = {"attempt": n, "html": html_path, "flow": flow_path,
                                "audit": p + ".audit.json"}
            if report.get("passed"):
                summary["passed"] = True
                log("PASSED on attempt %d" % n)
                break
            prev = {"report": report, "html": html, "flow_text": flow_text}
            if fmt_used >= fmt_budget and aud_used >= aud_budget:
                log("양쪽 예산 모두 소진 — 형식 %d회 / 검사 %d회" % (fmt_used, aud_used))
                break
            if entry.get("stage") == "flow" and fmt_used >= fmt_budget:
                log("형식 재시도 예산 소진 (%d회) — 검사까지 가지 못했다" % fmt_used)
                break
            if entry.get("stage") == "audit" and aud_used >= aud_budget:
                log("검사 재시도 예산 소진 (%d회)" % aud_used)
                break
        if not summary["passed"]:
            log("통과 없음 — 형식 재시도 %d회 / 검사 재시도 %d회" % (fmt_used, aud_used))
            if summary["stopped_reason"] is None:
                summary["stopped_reason"] = "budget_exhausted"
        if summary["trend"]:
            log("")
            log("fatal_root 추이")
            log("  시도 | fatal | 근본 | 파생 | 화면    | 멈춘 곳")
            for t in summary["trend"]:
                log("  %4s | %5s | %4s | %4s | %-7s | %s"
                    % (t["attempt"], t["fatal_total"], t["fatal_root"],
                       t["fatal_derived"], t["screens"], t["stopped_at"] or "-"))
        summary["budget"] = {"format_used": fmt_used, "format_budget": fmt_budget,
                             "audit_used": aud_used, "audit_budget": aud_budget}
    finally:
        if server:
            server.terminate()
            log("server: stopped (pid %d)" % server.pid)

    # the last build that got as far as a file, passed or not
    if summary["final"]:
        f = summary["final"]
        shutil.copy2(f["html"], os.path.join(OUTPUTS_DIR, "restructured_auto.html"))
        shutil.copy2(f["flow"], os.path.join(OUTPUTS_DIR, "restructured_auto.flow.json"))
        shutil.copy2(f["audit"], os.path.join(OUTPUTS_DIR, "audit_auto.json"))
        log("final: attempt %d -> outputs/restructured_auto.html (+ .flow.json, audit_auto.json)"
            % f["attempt"])
    json.dump(summary, io.open(os.path.join(run_dir, "summary.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    log("summary: %s" % os.path.join(run_dir, "summary.json"))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
