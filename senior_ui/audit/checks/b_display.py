r"""검사 B - 표시 정확도. fatal.

각 화면이 과제가 넣은 값을 그대로 보여 주는지, 원본에 없던
alert/confirm/prompt 나 onclick 이 끼어들었는지를 본다. 끼어든 쪽이 숫자를 박아
넣었는지는 그 주입 finding 의 속성(`numbers`)으로 남긴다 - 결함 하나가 두 번
세지지 않게. 흐름 파일의 expect 에 적힌 선택자만 본다 - 적히지 않은 곳이
무엇을 보여 주는지는 보지 않는다.
"""
import re

from ..context import union
from ..flow import ACCOUNT, AMOUNT, AMOUNT_SHOWN, NAME, fill


def calls(html, fn):
    return set(re.findall(r"%s\(\s*(['\"])(.*?)\1" % fn, html))


def run(ctx):
    rep, orig = ctx.rep, ctx.orig
    metrics, F, W = ctx.metrics, ctx.fatal_, ctx.warn

    for name, pairs in ctx.flow["expect"].items():
        pairs = [(fill(sel), fill(val)) for sel, val in pairs]
        row = rep["screens"].get(name)
        if not row or row.get("shown") is None:
            continue
        shown = dict(row.get("shown") or [])
        for sel, expected in pairs:
            got = shown.get(sel)
            if got is None:
                F("B", name, "%s is missing, cannot show %r" % (sel, expected))
            elif expected not in got:
                F("B", name, "%s shows %r but the task used %r"
                  % (sel, got, expected), selector=sel, expected=expected, got=got)
        # Only a name the original actually showed here can go missing.
        orig_text = (orig["screens"].get(name) or {}).get("text") or ""
        if NAME in orig_text and NAME not in (row.get("text") or ""):
            W("B", name, "recipient name %r no longer appears on this screen" % NAME)

    # injected dialogs / handlers, by diffing the two documents
    #
    # 박아 넣은 숫자는 그 주입의 성질이지 별개의 결함이 아니다. 따로 적으면
    # alert 한 개가 fatal 두 건이 되어, 결함 수가 결함 수를 세지 않게 된다.
    # 숫자는 finding 의 `numbers` 속성으로 남고 내용에도 한 줄 덧붙는다.
    for fn in ("alert", "confirm", "prompt"):
        new = calls(ctx.rep_html, fn) - calls(ctx.orig_html, fn)
        for _q, msg in sorted(new):
            digits = re.findall(r"\d[\d,]*", msg)
            hard = ""
            if digits:
                hard = (" - it also hardcodes %s, and the value is dynamic, so "
                        "it will be wrong for any other amount"
                        % ", ".join(digits))
            F("B", None, "%s() injected that the original never had: %r%s"
              % (fn, msg, hard), injected=msg, numbers=digits)
    metrics["injected_dialog_calls"] = sum(
        len(calls(ctx.rep_html, f) - calls(ctx.orig_html, f))
        for f in ("alert", "confirm", "prompt"))

    orig_onclick = union(orig, "onclicks")
    rep_onclick = union(rep, "onclicks")
    added = sorted(rep_onclick - orig_onclick)
    metrics["onclick_added"] = len(added)
    for h in added:
        F("B", None, "onclick attribute added that the original did not have: "
          + h[:120], handler=h)

    # dialogs actually raised while driving the task
    #
    # 주입된 alert 와 같은 규칙이다 (위 참고): 막은 대화상자 하나가 결함
    # 하나고, 그것이 과제가 쓰지 않은 숫자를 말한다는 것은 그 대화상자의
    # 성질이므로 finding 의 `numbers` 속성으로 둔다. 따로 적으면 대화상자
    # 한 개가 fatal 두 건이 된다.
    metrics["dialogs_during_task"] = len(rep["dialogs"])
    for d in rep["dialogs"]:
        nums = [n for n in re.findall(r"\d[\d,]*", d["message"])
                if n not in (AMOUNT_SHOWN, AMOUNT, ACCOUNT)]
        wrong = ""
        if nums:
            wrong = (" - it states %s while the task used %s"
                     % (", ".join(nums), AMOUNT_SHOWN))
        F("B", d["screen"], "blocking %s during the task: %r%s"
          % (d["type"], d["message"], wrong), numbers=nums)
