r"""검사 B - 표시 정확도. fatal.

각 화면이 과제가 넣은 값을 그대로 보여 주는지, 원본에 없던
alert/confirm/prompt 나 onclick 이 끼어들었는지를 본다. 값은 숫자 경계로 본다 -
라벨은 함께 있어도 되지만 숫자가 더 붙어 있으면 다른 값이다 (shows() 참고).

끼어든 쪽이 숫자를 박아 넣었는지는 그 주입 finding 의 속성(`numbers`)으로
남긴다 - 결함 하나가 두 번 세지지 않게.

흐름 파일의 expect 에 적힌 선택자만 본다 - 적히지 않은 곳이 무엇을 보여 주는지는
보지 않는다.
"""
import re

from ..context import union
from ..flow import ACCOUNT, AMOUNT, AMOUNT_SHOWN, NAME, fill

# 숫자 사이의 하이픈과 공백은 끊어 읽히게 하는 장식이다 (3333-0000-0000-0,
# 3333 0000 0000 0). 숫자 사이가 아닌 것은 걷어내지 않는다 - "카카오뱅크
# 3333000000000" 의 공백은 라벨과 값을 가르는 것이지 숫자의 장식이 아니다.
DIGIT_GAP = re.compile(r"(?<=\d)[\s-]+(?=\d)")


def joined(text):
    """숫자 사이의 하이픈·공백만 걷어낸다. 그 밖의 글자는 그대로 둔다."""
    return DIGIT_GAP.sub("", text or "")


def shows(got, expected):
    """그 선택자가 과제가 넣은 값을 보여 주는가.

    기대값이 앞뒤에 다른 숫자가 붙지 않은 채로 들어 있으면 통과다. 값이 아닌
    다른 글자는 함께 있어도 된다 - 한 요소가 라벨과 값을 같이 담는 것은 흔한
    모양이고, 그것은 결함이 아니다.

        "카카오뱅크 3333000000000"   계좌 옆에 은행 이름        -> 통과
        "10,000원만 원"              금액 아래 한글 읽기(<small>) -> 통과
        "3333-0000-0000-0"           끊어 읽는 계좌             -> 통과

    "포함" 으로 보면 안 되는 쪽은 숫자다. 110,000원 은 10,000 을 품고
    33330000000009 는 3333000000000 을 품으므로, 열한 배 금액과 한 자리 더 긴
    계좌가 전부 통과한다 - 검사 B 가 잡아야 하는 바로 그 결함이다. 그래서
    앞이나 뒤에 숫자가 더 붙은 자리는 세지 않는다.
    """
    want, have = joined(expected), joined(got)
    if not want:
        return True
    return bool(re.search(r"(?<!\d)%s(?!\d)" % re.escape(want), have))


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
            elif not shows(got, expected):
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
