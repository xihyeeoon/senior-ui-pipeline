r"""모델에 보낼 프롬프트를 만든다.

docs/restructure-prompt.md 에 블록이 셋 있다.

    <!-- TASK -->         과제 설명. 아래 두 프롬프트가 같은 글을 쓴다
    <!-- PLAN_PROMPT -->  진단·계획 (호출 1)
    <!-- PROMPT -->       생성 (호출 2, 그리고 재시도)

과제 설명을 한 곳에 두는 이유는 과제를 바꾸는 날 한 곳만 고치게 하려는 것이다 -
두 프롬프트에 따로 적으면 한쪽만 바뀐 채로 돈다.

생성 프롬프트의 슬롯은 다섯이다 - 원본 HTML · 재시도 블록 · 선택지 요약 · 오류
조건 · 계획.
재시도 블록은 직전 검사 결과를 모델이 읽을 수 있는 몇 줄로 줄이는 일이고, 그
줄이기가 이 파일의 대부분이다.

여기서는 파일을 읽는 것 말고는 아무것도 하지 않는다 - 모델 호출은 model.py,
답 해석은 reply.py 다.
"""
import io
import os
import re

from senior_ui.audit.flow import original_error_paths
from senior_ui.config import ROOT
from senior_ui.preserved import GLOBAL_NAME

from .preserve import preserved_data, split_groups

PROMPT_FILE = os.path.join(ROOT, "docs", "restructure-prompt.md")


def load_block(name, text=None):
    """`<!-- name -->` 와 `<!-- /name -->` 사이."""
    if text is None:
        text = io.open(PROMPT_FILE, encoding="utf-8").read()
    m = re.search(r"<!-- %s -->\n(.*?)<!-- /%s -->" % (name, name), text, re.S)
    if not m:
        raise RuntimeError("no <!-- %s --> block in %s" % (name, PROMPT_FILE))
    return m.group(1)


def _with_task(name):
    text = io.open(PROMPT_FILE, encoding="utf-8").read()
    return load_block(name, text).replace("{{TASK}}",
                                          load_block("TASK", text).strip())


def load_template():
    """생성 프롬프트. 과제 설명은 TASK 블록에서 채운 뒤다."""
    return _with_task("PROMPT")


def load_plan_template():
    """진단·계획 프롬프트. 과제 설명은 생성 프롬프트와 같은 TASK 블록이다."""
    return _with_task("PLAN_PROMPT")


def build_prompt(template, original_html, retry_block, choices="", plan="",
                 errors=None):
    """`errors` 를 주지 않으면 원본 흐름의 오류 조건으로 채운다 (errors_block)."""
    if errors is None:
        errors = errors_block(original_error_paths())
    return (template.replace("{{ORIGINAL_HTML}}", original_html)
                    .replace("{{RETRY_BLOCK}}", retry_block)
                    .replace("{{CHOICES}}", choices)
                    .replace("{{ERRORS}}", errors)
                    .replace("{{PLAN}}", plan))


def build_plan_prompt(template, original_html, choices, original_screens,
                      retry="", errors=None):
    if errors is None:
        errors = errors_block(original_error_paths())
    return (template.replace("{{ORIGINAL_HTML}}", original_html)
                    .replace("{{RETRY_BLOCK}}", retry)
                    .replace("{{CHOICES}}", choices)
                    .replace("{{ERRORS}}", errors)
                    .replace("{{ORIGINAL_SCREENS}}", ", ".join(original_screens)))


def errors_block(paths):
    """원본의 오류 조건을 모델이 읽을 글로. 원본 흐름의 error_paths 에서 만든다.

    넣는 것은 id · 무엇이 틀렸나(about) · 원본은 어떻게 하나(condition) · 잘못된
    값의 **자리표시자 이름** 뿐이다. 실제 값은 넣지 않는다 - 모델이 그 값을 알면
    "그 값일 때만 오류를 띄우는" HTML 로 검사 J 를 지날 수 있다. 정답이 아닌
    모든 값에서 같은 오류가 나야 한다는 것을 대신 말한다.

    과제에 묶이지 않는다 - 오류의 수도 이름도 글도 흐름 파일에서 나온다.
    """
    paths = [e for e in paths or [] if isinstance(e, dict) and e.get("id")]
    if not paths:
        return ""
    out = ["## 원본의 오류 조건", "",
           "사용자는 실제로 잘못 입력한다. 잘못된 입력을 알리고 고치게 하는 것도 "
           "과업의 일부다.", "원본에는 오류가 %d개 있다." % len(paths), ""]
    for e in paths:
        out.append("- `%s` — %s" % (e["id"], e.get("about") or ""))
        if e.get("condition"):
            out.append("  %s" % e["condition"])
        if e.get("uses"):
            out.append("  검사기가 넣는 잘못된 값: %s"
                       % ", ".join("`{%s}`" % k for k in e["uses"]))
    out += ["",
            "보여 주는 방식은 자유다. 팝업이 아니어도 되고, 넣는 즉시 같은 화면에서 "
            "알려도 되고,",
            "[다음] 을 끄고 이유를 보여도 되고, 오류 코드는 쉬운 말로 바꿔도 되고, "
            "여러 오류를 한",
            "화면으로 보여도 된다. 지킬 것은 셋이다.", "",
            "1. 그 잘못된 입력에서 오류 상태가 나타난다 — 틀린 값으로 다음 단계에 "
            "넘어가지 않는다.",
            "2. 무엇이 틀렸는지 알아챌 수 있는 글이 새로 보인다.",
            "3. 고칠 수 있는 화면 — 오류가 나타난 화면이나 그 앞 — 으로 되돌아갈 수 "
            "있다.", "",
            "잘못된 값이 무엇인지는 알려 주지 않는다. 정답이 아닌 모든 값에서 같은 "
            "오류가 나야 한다.", ""]
    return "\n".join(out)


def reflection_request():
    """재시도 프롬프트의 맨 앞에 붙는 반성 요청 (REFLECT 블록)."""
    return load_block("REFLECT")


def with_reflection(block):
    """재시도 블록 앞에 반성 요청을 붙인다. 코드보다 반성을 먼저 쓰게 하려는
    것이므로 실패 목록보다 앞이다. 빈 블록(첫 시도)은 그대로다."""
    return reflection_request() + "\n" + block if block else block


def plan_retry_block(problems):
    """진단·계획 답을 쓸 수 없었을 때의 재시도 블록. 이 단계에는 검사 결과가
    없으므로 무엇이 틀렸는지만 적는다."""
    if not problems:
        return ""
    return "\n".join(["## 직전 답의 문제", "",
                      "직전 답을 아래 이유로 쓸 수 없었다. 고쳐서 JSON 블록 하나로 "
                      "다시 출력하라.", ""]
                     + ["- " + one_line(x) for x in problems] + [""])


def choices_block(orig_snapshot, original_html):
    """원본이 가진 반복 선택지를 요약하고, 데이터를 어디서 읽는지 알린다.

    검사 I 가 렌더링된 DOM 에서 수집하는 바로 그 집합을 쓴다 (preserve.py 의
    choice_groups). 모델이 보는 것과 검사가 세는 것이 어긋나면 안 되기 때문이다.

    마크업에 직접 쓰인 것(숫자판 등)과 스크립트가 그리는 것(은행 목록 등)을
    가른다. 전자는 그대로 두면 되고, 후자는 **도구가 들고 있다** - 모델은 목록을
    다시 타이핑하지 않고 `window.PRESERVED.<이름>` 을 참조해 그린다.

    전에는 이 자리에 "배열은 원본 그대로 두고 참조해 그려라, 값은 하나도
    빠뜨리지 마라" 가 있었다. Run 5 는 그 문장을 받고도 9번 시도 모두 4개만
    썼다 (docs/variance-notes.md). 말로 지시하는 방법은 효과가 없었으므로 이제
    데이터는 도구가 넣고, 이 블록은 "어디서 읽는가" 와 "검사가 무엇을 보는가" 를
    알리는 글이 되었다.

    은행이나 금융에 묶이지 않은 일반 규칙이다 - 이름도 개수도 입력에서 나온다.
    """
    generated, inline = split_groups(orig_snapshot, original_html)
    if not generated and not inline:
        return ""
    data = preserved_data(orig_snapshot, original_html)

    out = ["## 원본이 가진 선택지", ""]
    if generated:
        out.append("원본의 반복 선택지 (스크립트가 런타임에 그린다):")
        for action, count, src in generated:
            where = (" (%s)" % " + ".join("%s %d" % (n, c) for n, c in src))                 if src else ""
            out.append("  %s — %d개%s" % (action, count, where))
        out.append("")
    if data:
        keys = " · ".join("window.%s.%s (%d개)" % (GLOBAL_NAME, n, len(v))
                          for n, v in data.items())
        out += ["이 데이터는 도구가 다음 이름으로 넣어 준다:", "  " + keys, "",
                "목록을 직접 쓰지 마라. 이것을 참조해 그려라. 몇 개를 어떻게 "
                "보일지는 네가",
                "정한다 (검색, 자주 쓰는 것 먼저, 탭, 가나다 묶음 등). 다만 모든 "
                "값을 고를",
                "수 있어야 한다. 위 이름을 하나도 빠뜨리지 말고 참조하라 - 읽지 "
                "않은 이름이",
                "있으면 형식 오류로 돌아온다.", "",
                "검사가 보는 것은 렌더링된 화면이다. 선택 화면이 열렸을 때 모든 "
                "값이 DOM",
                "안에 있어야 한다 (숨김·접힘은 괜찮다). 검색창을 두더라도 검색어가 "
                "비었을",
                "때는 전체 목록이 DOM 에 있어야 한다. 도구가 넣어 준 데이터 "
                "블록은 증거로",
                "세지 않는다 - 그 데이터를 읽어 **그린** 것만 센다.", ""]
    if inline:
        out.append("마크업에 직접 있는 것 (그대로 두면 된다):")
        for action, count, _src in inline:
            out.append("  %s — %d개" % (action, count))
        out.append("")
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
    details = ((report or {}).get("metrics") or {}).get("js_error_details") or []
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


def truncated_part(n):
    """답이 길이 제한에서 잘렸다는 것만 따로 알린다.

    잘린 답은 형식 오류와 겉모양이 같다 - 코드 블록이 닫히지 않았으니 "블록이
    없다" 로 보인다. 그래서 "군더더기 없이 쓰라" 는 말만 전달되고, 같은 길이의
    답이 다시 와서 같은 자리에서 또 잘린다. 잘렸다는 사실과 몇 번째인지를
    적는 이유가 그것이다 - 둘째 번부터는 짧게 쓰는 것 말고 할 일이 없다.
    """
    head = "직전 답이 길이 제한에서 잘렸다 (finish_reason=length)."
    if n >= 2:
        head += " 이번까지 %d번 연속으로 잘렸다." % n
    return ["[잘린 답]", "  " + head,
            "  답의 끝이 사라진 것이지 내용이 틀린 것이 아니다. 같은 분량으로 다시 "
            "쓰면 같은 자리에서 또 잘린다.",
            "  설명·주석·빈 줄을 모두 빼고, 코드 블록 두 개만 출력하라. 그래도 "
            "길면 화면 수를 줄여서라도 문서를 끝까지 닫아라.", ""]


def error_part(error, has_build):
    """이번 답의 형식 오류. 검사 결과와 같은 자리에 섞이면 안 된다.

    파싱이 실패한 시도는 검사를 받은 적이 없다. 그런데 재시도 프롬프트에는
    실패 목록이 하나뿐이라, 이 오류를 거기 넣으면 그 전 시도에서 실제로 검사받은
    실패가 사라진다. 둘은 다른 것이므로 따로 적고, 아래 목록이 어느 빌드의
    것인지도 한 줄로 밝힌다.
    """
    items = error if isinstance(error, (list, tuple)) else [error]
    out = ["[이번 답의 형식 오류]"] + ["  " + one_line(x) for x in items]
    if has_build:
        out.append("  아래 [고칠 것] 과 직전 HTML·흐름 명세는 그 전에 검사까지 간 "
                   "빌드의 것이다. 그 빌드를 고쳐서, 이번에는 형식에 맞게 출력하라.")
    out.append("")
    return out


def retry_block(report, prev_html, prev_flow_text, error=None, truncated=0):
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
    report = report or {}
    fatals = report.get("fatal") or []
    derived = [f for f in fatals if f.get("derived_from")]
    root = [f for f in fatals if not f.get("derived_from")]
    js = [f for f in root if "JavaScript errors" in (f.get("detail") or "")]
    other = [f for f in root if f not in js]

    parts = ["## 이전 시도의 실패", ""]
    # 규칙 0: 답이 아예 쓸 수 없는 모양이면 그것부터. 검사 결과는 그보다 앞
    # 시도의 것이므로 덮지 않고 아래에 그대로 둔다.
    if truncated:
        parts += truncated_part(truncated)
    if error:
        parts += error_part(error, bool(fatals or prev_html))
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
        elif not derived and not (error or truncated):
            parts += ["(fatal 목록이 비어 있지만 통과하지 못했다)", ""]

    # 규칙 3: 파생은 한 줄로 묶는다.
    if derived:
        names = " · ".join(f.get("screen") or "?" for f in derived)
        head = "[아래는 위 원인의 결과다. 따로 고치지 마라]" if (cause or other) \
            else "[도달하지 못한 화면]"
        parts += [head, "  %s — 도달 못 함" % names, ""]

    if prev_html or prev_flow_text:
        parts += ["직전 출력을 고쳐라. 설계를 처음부터 새로 하지 마라.", ""]
    if prev_flow_text:
        parts += ["### 직전 흐름 명세", "", "```json", prev_flow_text.strip(), "```", ""]
    if prev_html:
        parts += ["### 직전 HTML", "", "```html", prev_html.strip(), "```", ""]
    return "\n".join(parts)
