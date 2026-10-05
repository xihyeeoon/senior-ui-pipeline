r"""흐름 파일대로 페이지를 한 번 걷고, 검사가 필요한 것을 전부 긁어 온다.

판정은 하지 않는다 - 판정은 core.py 의 audit() 이 이 결과를 보고 한다. 페이지
안에서 실행되는 JavaScript 조각은 probes.py 에 있다.
"""
import asyncio
import os
import re

from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright

from . import probes as P
from .flow import fill, truth_of, visit_keys

# 방문 이름의 `#` 는 파일 이름에서는 쓰지 않는다 (URL 에서 조각 구분자다).
SHOT_SAFE = re.compile(r"[^0-9A-Za-z_.-]")

# A `%s`-bearing attribute selector, e.g. the [data-v='%s'] in
# "[data-action='acc-num'][data-v='%s']". Dropping it leaves the selector that
# addresses the field itself.
PER_CHAR_ATTR = re.compile(r"\[[^\]]*%s[^\]]*\]")

TAG_OF = """sel => { const e = document.querySelector(sel);
                     return e ? e.tagName.toLowerCase() : null; }"""


async def run_actions(page, spec, notes=None, truth=None):
    """One step of a flow file: click / type / repeat / wait, in order.

    `type` covers both ways a design can take text:

      keypad   "[data-action='acc-num'][data-v='%s']"  - one click per character
      field    "#acc-input"                            - one fill()

    The selector says which: a `%s` means there is a button per digit. A design
    that uses a real <input> has no such buttons, so it writes the field's own
    selector instead.

    Models often write both at once - "input[data-action='x'][data-v='%s']" -
    having read the keypad example but built a field. The element is an input,
    there are no per-digit buttons, and driving it as a keypad stalls on a
    selector that matches nothing. So when the `%s` selector points at an
    input/textarea once the `%s` attribute is dropped, fill it and record that
    in `notes`; the report surfaces it rather than silently accepting it.

    `truth` 는 자리표시자({ACCOUNT} 등)에 넣을 정답 값이다. 없으면 원본
    흐름의 것 (flow.truth_of).
    """
    truth = truth or truth_of(None)
    for item in (spec if isinstance(spec, list) else [spec]):
        if "wait" in item and "click" not in item and "repeat" not in item:
            await asyncio.sleep(float(item["wait"]))
            continue
        if "type" in item:
            key, value = item["key"], fill(item["type"], truth)
            if "%s" not in key:
                await page.fill(key, value)
                continue
            base = PER_CHAR_ATTR.sub("", key)
            tag = await page.evaluate(TAG_OF, base) if base != key else None
            if tag in ("input", "textarea"):
                await page.fill(base, value)
                if notes is not None:
                    notes.append(
                        "flow: type key %r has %%s but addresses an <%s>; filled "
                        "%r via %r instead of clicking per character"
                        % (key, tag, value, base))
                continue
            for ch in value:
                await page.click(key % ch)
            continue
        if "repeat" in item:
            for _ in range(int(item["repeat"])):
                await page.click(fill(item["click"], truth))
                await asyncio.sleep(float(item.get("wait", 0.1)))
            continue
        if "click" in item:
            await page.click(fill(item["click"], truth))
            if item.get("wait"):
                await asyncio.sleep(float(item["wait"]))


# 한 걸음 뒤 기대 화면이 켜지기를 기다리는 최대 시간.
#
# 전에는 걸음마다 0.45초를 고정으로 쉬었다. 그 수는 두 가지를 한꺼번에 틀린다 -
# 전환이 그보다 느린 설계(조회를 기다리거나 전환을 천천히 보여 주는 것)에서는
# 아직 앞 화면에 서 있는 것을 긁어 "엉뚱한 화면에 도착했다" 는 거짓 경보가 나고,
# 전환이 즉시 끝나는 설계에서는 화면 수만큼 그냥 기다린다.
#
# 이제 기대 화면이 켜지는 것을 보고 넘어간다. 이 값은 그러므로 "이만큼 기다려도
# 안 켜지면 안 켜지는 것이다" 이고, 다 되면 그대로 긁는다 - 못 켜진 것은 검사 A
# 가 적을 일이고, 여기서 예외를 내면 "검사하지 못했다" 가 되어 결함을 감춘다.
SETTLE_TIMEOUT_MS = 3000

# 기록(window.__screen())과 화면(`.screen.on`)이 둘 다 그 이름이어야 켜진 것이다.
# 화면만 보고 넘어가면 기록이 늦게 따라오는 설계에서 옛 이름을 긁는다. 기록 훅이
# 아예 없는 빌드는 화면만 본다 - 훅이 없다는 것 자체는 검사 A 가 적는다.
SCREEN_IS = """name => {
  const s = document.querySelector('.screen.on');
  if (!s || (s.dataset.screen || null) !== name) return false;
  if (typeof window.__screen !== 'function') return true;
  return window.__screen() === name;
}"""


async def settle(page, name, timeout_ms=SETTLE_TIMEOUT_MS):
    """기대 화면이 켜질 때까지 기다린다. 켜졌으면 True, 시간이 다 되면 False."""
    try:
        await page.wait_for_function(SCREEN_IS, arg=name, timeout=timeout_ms)
        return True
    except PlaywrightTimeout:
        return False


SELECTOR_IN_ERROR = re.compile(r'waiting for locator\("([^"]+)"\)')

WHERE_IS = """sel => {
  let el = null;
  try { el = document.querySelector(sel); } catch (e) { return null; }
  const on = document.querySelector('.screen.on');
  const current = on ? on.dataset.screen : null;
  if (!el) return {found: false, current: current};
  const sec = el.closest('[data-screen]');
  return {found: true, owner: sec ? sec.dataset.screen : null, current: current};
}"""


async def where_is(page, error_text):
    """실패한 선택자가 어느 화면 안에 있는지 알아낸다.

    "보이지 않음" 만으로는 요소를 고쳐야 하는지 화면 전환을 고쳐야 하는지 알 수
    없다. 요소가 다른 화면 안에 멀쩡히 있다면 문제는 요소가 아니라 거기까지
    가지 못한 것이다."""
    m = SELECTOR_IN_ERROR.search(error_text or "")
    if not m:
        return None
    try:
        info = await page.evaluate(WHERE_IS, m.group(1))
    except Exception:
        return None
    if not info:
        return None
    sel = m.group(1)
    if not info.get("found"):
        return "%s 는 문서 어디에도 없다 (지금 화면: %s)" % (sel, info.get("current"))
    owner, current = info.get("owner"), info.get("current")
    if owner and current and owner != current:
        return ("%s 는 %r 화면에 있는데 지금 켜진 화면은 %r 이다. "
                "요소가 아니라 화면 전환을 확인하라." % (sel, owner, current))
    return None


# 검사 B 가 읽는 값. 켜진 화면 안에서, 보이는 요소에서만 읽는다.
#
# document.querySelector 로 문서 전체에서 집으면 사용자가 볼 수 없는 값이
# 잡힌다 - 꺼진 화면에 남아 있는 옛 값이나 display:none 으로 숨긴 요소가
# 문서 순서에서 먼저 나오면 그것이 집히고, 화면에는 틀린 값이 떠 있는데도
# 검사 B 는 통과한다. 켜진 화면이 없으면 읽을 곳이 없으므로 null 이고,
# 검사 B 는 그때 물러난다 (도착하지 못한 것은 검사 A 가 적는다).
SHOWN = """sels => {
  const s = document.querySelector('.screen.on');
  if (!s) return null;
  const visible = (e) => {
    const cs = getComputedStyle(e);
    if (cs.display === 'none' || cs.visibility === 'hidden') return false;
    if (+cs.opacity === 0) return false;
    const r = e.getBoundingClientRect();
    return r.width >= 1 && r.height >= 1;
  };
  return sels.map(sel => {
    let hit = null;
    try {
      for (const e of s.querySelectorAll(sel)) {
        if (visible(e)) { hit = e; break; }
      }
    } catch (err) { return [sel, null]; }
    return [sel, hit ? hit.textContent.trim() : null];
  });
}"""


# 걷기를 끝낸 뒤 늦게 뜨는 dialog 에게 주는 틈.
#
# 걷는 중에 뜨는 dialog 는 저절로 잡힌다 - dialog 가 뜨면 페이지의 JS 가 멈추
# 므로 다음 evaluate 가 끝나지 않고, 그 사이에 처리기가 돈다. 노출된 자리는
# 마지막 화면을 긁은 뒤부터 브라우저를 닫기까지의 틈이고, 재어 보면 20ms 쯤이다.
# 닫는 동안에는 타이머가 돌지 않으므로 그 뒤에 예정된 alert 은 아예 뜨지 못한다.
# 보내기 결과를 뒤늦게 알리는 설계의 alert 이 바로 거기서 사라진다.
#
# 걸음마다 쉬던 0.45초가 전에는 이 틈을 우연히 덮고 있었다. 그 sleep 을 걷어낸
# 자리에, 끝에서 한 번만 주는 이 틈을 둔다 - 기다리는 대상이 화면이 아니라
# dialog 이므로 기대 화면을 보고 넘어가는 방식으로는 대신할 수 없다.
DIALOG_GRACE_MS = 400


def attach_listeners(page, data):
    """JS 오류와 dialog 를 `data` 에 모은다. 둘 다 언제 올지 모르므로, 걷기를
    시작하기 전에 붙여 둔다.

    dialog 처리기는 코루틴이므로 task 가 된다. 그 task 들을 돌려준다 - 붙잡지
    않으면 아무도 기다리지 않는 task 가 되어, 브라우저를 닫는 순간 기록도 되지
    않고 예외도 아무도 읽지 않는다 (drain_dialogs 참고).
    """
    def on_pageerror(e):
        # 메시지만 남기면 "S is not defined" 뿐이라 어디를 고칠지 알 수 없다.
        # stack 에 파일과 줄 번호가 들어 있으므로 함께 보관한다.
        data["js_errors"].append(str(e))
        data["js_error_details"].append({
            "name": getattr(e, "name", None),
            "message": str(e),
            "stack": getattr(e, "stack", None),
        })
    page.on("pageerror", on_pageerror)

    tasks = []

    async def on_dialog(d):
        data["dialogs"].append({"screen": data["reached"][-1] if data["reached"]
                                else "?", "type": d.type, "message": d.message})
        await d.dismiss()
    page.on("dialog", lambda d: tasks.append(asyncio.ensure_future(on_dialog(d))))
    return tasks


async def drain_dialogs(tasks, grace_ms=DIALOG_GRACE_MS):
    """브라우저를 닫기 전에 남은 dialog 를 처리한다.

    먼저 늦게 뜰 dialog 에게 틈을 준다 (DIALOG_GRACE_MS 의 설명 참고). 그다음
    만들어진 처리기 task 가 전부 끝나기를 기다린다 - 처리 중에 또 뜰 수 있으므로
    새 task 가 없을 때까지 돈다. 다섯 바퀴로 끊는다: 끝없이 대화상자를 띄우는
    페이지에서 영원히 머무르지 않게 한다.
    """
    await asyncio.sleep(grace_ms / 1000.0)
    for _ in range(5):
        pending = [t for t in tasks if not t.done()]
        if not pending:
            break
        await asyncio.gather(*pending, return_exceptions=True)


async def collect_screen(page, flow, visit, reached=None):
    """한 화면에 도착한 뒤의 상태를 전부 긁어 하나의 row 로 돌려준다.

    `reached` 를 주면 __screen() 의 답을 긁기 직전에 거기에 먼저 적는다. 걷는
    중에 뜬 dialog 는 `reached` 의 마지막 이름으로 기록되므로, 이 순서가 dialog
    가 어느 화면에 붙는지를 정한다.

    화면에 매인 값들(`inherited` · `overlap` · `overflow` · `wrapped` ·
    `shown`)은 켜진 화면이 없으면 null 이다 - 빈 목록이 아니다. probes.py 의
    머리말과 검사 A 의 _unlit() 참고.
    """
    at = await page.evaluate("() => window.__screen && window.__screen()")
    if reached is not None:
        reached.append(at)
    # 기록(__screen)과 화면(.screen.on)을 따로 적는다. 둘이 어긋나면 기록만
    # 넘어가고 사용자는 앞 화면에 서 있는 것이므로, 검사 A 가 둘을 맞춰 본다.
    row = {"landed_on": at,
           "dom_screen": await page.evaluate(P.DOM_SCREEN)}
    row.update(await page.evaluate(P.INVENTORY))
    row["choices"] = await page.evaluate(P.CHOICE_GROUPS)
    # CONTRAST 는 두 칸으로 돌려준다 - 잰 것과 잴 수 없었던 것. 한 칸으로
    # 합치면 그라디언트 위의 글자가 "저명암 아님" 과 구분되지 않는다.
    contrast = await page.evaluate(P.CONTRAST)
    row["contrast"] = contrast["low"]
    row["contrast_undetermined"] = contrast["undetermined"]
    row["inherited"] = await page.evaluate(P.INHERITED_COLOUR)
    row["overlap"] = await page.evaluate(P.OVERLAP)
    row["overflow"] = await page.evaluate(P.OVERFLOW)
    row["wrapped"] = await page.evaluate(P.WRAPPED)
    # expect 는 방문 이름으로 적는다 - 화면 이름만 적으면 첫 방문이다
    # (flow.visit_keys 참고).
    row["shown"] = await page.evaluate(
        SHOWN, [fill(s, truth_of(flow))
                for s, _ in flow["expect"].get(visit, [])])
    return row


async def drive(url, flow, want_shots=None, errors=True):
    """Walk the task once and collect everything the checks need.

    흐름에 오류 경로(`error_paths`)가 있으면 정답 경로를 걸은 뒤 경로마다 새
    페이지를 열어 한 번씩 더 걷는다 (walk_error_path). 결과는 `error_paths`
    에 따로 담는다 - `screens` 에 섞으면 A~I 가 보는 입력이 바뀐다. 흐름에
    오류 경로가 없거나 `errors=False` 면 그 키 자체가 없다. 비교 기준으로만
    걷는 원본(새 설계의 검사에서)은 오류 경로를 걸을 필요가 없다."""
    data = {"screens": {}, "dialogs": [], "js_errors": [], "reached": [],
            "missing_ids": [], "state_pairs": [], "load_failed": None,
            "notes": [], "js_error_details": [], "flow": flow["name"],
            # 이 걸음에 눌러 넣은 정답. 검사 B 가 원본 화면에 있던 받는 사람
            # 이름을 찾을 때 원본의 정답을 써야 한다 - 빌드의 정답과 다를 수 있다.
            "truth": truth_of(flow)}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        # 띄운 브라우저는 무슨 일이 있어도 닫는다. 걷는 중에 예외가 나면 전에는
        # 닫히지 않은 chromium 이 그대로 남았다.
        try:
            page = await browser.new_page(viewport={"width": 390, "height": 844})
            tasks = attach_listeners(page, data)
            await walk(page, flow, data, want_shots, url)
            await drain_dialogs(tasks)
            paths = [e for e in flow.get("error_paths") or []
                     if isinstance(e, dict) and e.get("id")] if errors else []
            if paths:
                data["error_paths"] = {}
                for ep in paths:
                    data["error_paths"][ep["id"]] = (
                        _not_walked(data, ep)
                        or await walk_error_path(browser, url, flow, ep,
                                                 want_shots))
        finally:
            await browser.close()
    return data


async def walk(page, flow, data, want_shots, url):
    """한 페이지를 흐름대로 걷는다. 브라우저의 생명은 drive() 가 쥐고 있다."""
    try:
        await page.goto(url, wait_until="networkidle")
    except Exception as e:
        data["load_failed"] = "%s: %s" % (type(e).__name__, e)
        return

    data["missing_ids"] = await page.evaluate(
        "ids => ids.filter(i => !document.getElementById(i))",
        flow["required_ids"])
    data["state_pairs"] = await page.evaluate(P.STATE_PAIRS)
    data["undefined_classes"] = await page.evaluate(P.UNDEFINED_CLASSES)

    for step, visit in zip(flow["steps"], visit_keys(flow["steps"])):
        name = step["screen"]
        try:
            if "do" in step:
                await run_actions(page, step["do"], data["notes"],
                                  truth_of(flow))
            elif "click" in step:
                await run_actions(page, {"click": step["click"]}, data["notes"],
                                  truth_of(flow))
        except Exception as e:
            msg = "%s: %s" % (type(e).__name__, e)
            hint = await where_is(page, msg)
            if hint:
                msg += " || " + hint
            data["screens"][visit] = {"error": msg}
            break
        if not await settle(page, name):
            data["notes"].append(
                "flow: %r 화면이 %dms 안에 켜지지 않았다. 그 상태로 긁는다 - "
                "무엇이 켜져 있었는지는 검사 A 가 적는다."
                % (name, SETTLE_TIMEOUT_MS))

        data["screens"][visit] = await collect_screen(
            page, flow, visit, data["reached"])
        if want_shots:
            await page.screenshot(path=os.path.join(
                want_shots, "audit_%s.png" % SHOT_SAFE.sub("_", visit)))


def _not_walked(data, ep):
    """정답 경로가 갈라지는 곳(from_step)에 닿기 전에 멈췄으면 오류 경로를 걷지
    않는다. 다시 걸어도 같은 자리에서 막히고, 막힌 선택자마다 클릭 제한 시간
    (30초)을 다 기다린다. 판정은 같다 - 검사 J 가 파생으로 적는다."""
    row = data["screens"].get(ep.get("from_step"))
    if ep.get("from_step") in data["screens"] and "error" not in row:
        return None
    return {"from_step": ep.get("from_step"), "expect_screen": ep.get("expect_screen"),
            "back_to": ep.get("back_to"), "js_errors": [], "dialogs": [],
            "error": {"phase": "replay",
                      "detail": "정답 경로가 %r 에 닿기 전에 멈췄다 - 오류 경로를 "
                                "걷지 않았다" % ep.get("from_step")}}


# 오류 경로에서 "보이는 글" 을 긁는다. 켜진 화면의 글과 켜진 화면 밖에 떠 있는
# 것(모달·토스트)을 함께 본다 - 오류를 어떻게 보일지는 설계가 정하므로, 화면
# 하나로 보이든 덮개로 보이든 사용자 눈에 닿는 글이면 된다.
async def _visible_text(page):
    inv = await page.evaluate(P.INVENTORY)
    return "\n".join(t for t in (inv.get("text"), inv.get("outside_text")) if t)


async def _where(page):
    return {"landed_on": await page.evaluate(
                "() => window.__screen && window.__screen()"),
            "dom_screen": await page.evaluate(P.DOM_SCREEN)}


async def walk_error_path(browser, url, flow, ep, want_shots=None):
    """오류 경로 하나를 새 페이지에서 걷는다. 판정은 하지 않는다 (검사 J).

      1. 정답 걸음을 `from_step` (방문 이름) 에 도착할 때까지 밟는다.
      2. `inputs` 를 실행한다. 마지막 동작 바로 앞에서 켜진 화면과 보이는 글을
         적어 둔다 - 마지막 동작이 오류를 일으키는 동작이고, 그 앞의 글이
         "새로 나타난 글" 을 가르는 기준이다. 틀린 값을 넣는 즉시 알리는
         설계라면 마지막 동작이 타이핑이고, 그때도 같은 규칙이다.
      3. `expect_screen` 이 켜지기를 기다리고 보이는 글을 긁는다.
      4. `recover` 를 실행하고 `back_to` 가 켜지기를 기다린다. 3 에서
         `expect_screen` 이 켜지지 않았으면 하지 않는다.

    단계마다 실패하면 거기서 멈추고 `error` 에 어느 단계였는지 적는다.
    """
    truth = truth_of(flow)
    row = {"from_step": ep.get("from_step"), "expect_screen": ep.get("expect_screen"),
           "back_to": ep.get("back_to"), "error": None}
    ed = {"js_errors": [], "js_error_details": [], "dialogs": [], "reached": []}
    page = await browser.new_page(viewport={"width": 390, "height": 844})
    tasks = attach_listeners(page, ed)

    async def failed(phase, e):
        msg = "%s: %s" % (type(e).__name__, e) if isinstance(e, Exception) else e
        hint = await where_is(page, msg) if isinstance(e, Exception) else None
        row["error"] = {"phase": phase, "detail": msg + (" || " + hint if hint else "")}

    try:
        try:
            await page.goto(url, wait_until="networkidle")
        except Exception as e:
            await failed("load", e)
            return row
        visits = visit_keys(flow["steps"])
        if ep.get("from_step") not in visits:
            await failed("replay", "from_step %r 은 steps 의 방문 이름이 아니다 (%s)"
                         % (ep.get("from_step"), ", ".join(visits)))
            return row
        for step, visit in zip(flow["steps"], visits):
            try:
                if "do" in step:
                    await run_actions(page, step["do"], None, truth)
                elif "click" in step:
                    await run_actions(page, {"click": step["click"]}, None, truth)
            except Exception as e:
                await failed("replay", e)
                return row
            if not await settle(page, step["screen"]):
                await failed("replay", "정답 걸음 %r 화면이 켜지지 않았다" % visit)
                return row
            if visit == ep.get("from_step"):
                break

        inputs = ep.get("inputs") or []
        inputs = inputs if isinstance(inputs, list) else [inputs]
        try:
            if inputs[:-1]:
                await run_actions(page, inputs[:-1], None, truth)
            row["trigger"] = await _where(page)
            row["before_text"] = await _visible_text(page)
            if inputs:
                await run_actions(page, inputs[-1:], None, truth)
        except Exception as e:
            await failed("inputs", e)
            return row
        row["settled"] = await settle(page, ep.get("expect_screen"))
        row["after"] = await _where(page)
        row["after_text"] = await _visible_text(page)
        if want_shots:
            # 오류 상태의 모습. 디자이너용 설명서의 오류 경로 표가 가리킨다.
            await page.screenshot(path=os.path.join(
                want_shots, "audit_error_%s.png" % SHOT_SAFE.sub("_", ep["id"])))
        if not row["settled"]:
            # 오류 상태가 나타나지 않았다. 되돌아가는 조작은 그 상태에서 누를
            # 것이므로 눌러 보지 않는다 - 없는 버튼마다 30초를 기다리게 된다.
            # 판정(검사 J)은 여기서 이미 정해진다.
            return row

        try:
            await run_actions(page, ep.get("recover") or [], None, truth)
        except Exception as e:
            await failed("recover", e)
            return row
        row["recovered"] = await settle(page, ep.get("back_to"))
        row["recover"] = await _where(page)
        return row
    finally:
        await drain_dialogs(tasks)
        row["js_errors"] = ed["js_errors"]
        row["dialogs"] = ed["dialogs"]
        await page.close()
