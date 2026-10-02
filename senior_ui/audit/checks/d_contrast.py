r"""검사 D - 명암비. warning.

저명암 텍스트 개수가 늘지 않았는지, 새 텍스트가 색을 상속만으로 받는지, 이미
저명암이던 요소에 읽을 글이 들어왔는지를 본다. 개수 비교만으로는 마지막 경우를
놓친다 - 개수는 그대로인데 읽어야 할 글이 늘기 때문이다. 명암비 계산 자체는
probes.CONTRAST 가 페이지 안에서 한다.
"""
import re

# 더해진 글이 장식이 아니라 실제로 읽히는 글인지 가리는 데 쓴다.
WORDY = re.compile(r"[0-9A-Za-z가-힣]")


def run(ctx):
    orig, rep, want, shared = ctx.orig, ctx.rep, ctx.want, ctx.shared
    metrics, W = ctx.metrics, ctx.warn

    lc_before = {n: len(r.get("contrast", []))
                 for n, r in orig["screens"].items()}
    lc_after = {n: len(r.get("contrast", []))
                for n, r in rep["screens"].items()}
    metrics["low_contrast_before"] = sum(lc_before.values())
    metrics["low_contrast_after"] = sum(lc_after.values())
    metrics["low_contrast_by_screen"] = {
        n: {"before": lc_before.get(n), "after": lc_after.get(n)}
        for n in (want if ctx.derived else shared)}
    if metrics["low_contrast_after"] > metrics["low_contrast_before"]:
        W("D", None, "low-contrast text grew from %d to %d"
          % (metrics["low_contrast_before"], metrics["low_contrast_after"]))
    for n in shared:
        b, a = lc_before.get(n), lc_after.get(n)
        if b is not None and a is not None and a > b:
            W("D", n, "low-contrast text grew from %d to %d" % (b, a))

    new_inherited = []
    for n in (want if ctx.derived else shared):
        o = {(x["text"], x["cls"]) for x in orig["screens"].get(n, {}).get("inherited", [])}
        for x in rep["screens"].get(n, {}).get("inherited", []):
            if (x["text"], x["cls"]) not in o:
                new_inherited.append(dict(x, screen=n))
    metrics["new_inherited_colour"] = len(new_inherited)
    for x in new_inherited[:20]:
        W("D", x["screen"], "new text %r takes its colour purely by inheritance "
          "(%s) - nothing sets a colour for it" % (x["text"], x["color"]),
          cls=x["cls"], tag=x["tag"])

    # An element that was already below threshold does not change the count when
    # a repair puts words into it, and it is not inheriting either - its class
    # supplies the colour. `.st` was a decorative ☆ at 1.44:1; it now carries
    # "선택됨", which a reader is expected to read at the same 1.44:1.
    burdened = []
    for n in want:
        by_key = {}
        for x in orig["screens"].get(n, {}).get("contrast", []) or []:
            by_key.setdefault((x["tag"], x["cls"]), set()).add(x["text"])
        for x in rep["screens"].get(n, {}).get("contrast", []) or []:
            k = (x["tag"], x["cls"])
            was = by_key.get(k)
            if not was or x["text"] in was:
                continue
            # only when text was added, and the addition is actually readable
            if len(x["text"]) > max(len(t) for t in was) and WORDY.search(x["text"]):
                burdened.append(dict(x, screen=n, before=sorted(was)[0]))
    metrics["low_contrast_gained_text"] = len(burdened)
    seen_b = set()
    for x in burdened:
        k = (x["screen"], x["cls"], x["text"])
        if k in seen_b:
            continue
        seen_b.add(k)
        W("D", x["screen"], "already low-contrast element (.%s, %.2f:1) gained "
          "readable text: %r -> %r - the count is unchanged, so this passes the "
          "before/after comparison" % (x["cls"], x["ratio"], x["before"], x["text"]),
          cls=x["cls"], ratio=x["ratio"], need=x["need"],
          color=x["color"], bg=x["bg"])
