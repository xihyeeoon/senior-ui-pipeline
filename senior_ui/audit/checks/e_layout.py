r"""검사 E - 배치. warning.

겹침과 넘침은 그 자체로 결함이므로 모든 화면에서 본다. 줄바꿈과 높이 증가는
전후 비교이므로 짝이 되는 원본 화면이 있을 때만 돌고, 없으면 물러난다.
사람 눈에 어떻게 보이는지는 보지 않는다 - 사각형 좌표와 높이 숫자만 본다.
"""
HEIGHT_GROWTH_LIMIT = 1.5      # screen scrollHeight vs the original


def tally(items):
    out = {}
    for x in items or []:
        out[(x["tag"], x["cls"])] = out.get((x["tag"], x["cls"]), 0) + 1
    return out


def run(ctx):
    orig, rep, want, shared = ctx.orig, ctx.rep, ctx.want, ctx.shared
    metrics, W = ctx.metrics, ctx.warn

    ov_new, of_new, tall = [], [], []
    for n in want:
        # overlap and overflow are defects on their own terms, so they run on
        # every screen; a missing baseline just means nothing is subtracted.
        # Wrapping and height growth are comparisons, so they only run where a
        # matching original screen exists.
        o = orig["screens"].get(n, {}) if (ctx.derived or n in shared) else {}
        r = rep["screens"].get(n, {})
        ob = {(x["a"], x["b"]) for x in o.get("overlap") or []}
        for x in r.get("overlap") or []:
            if (x["a"], x["b"]) not in ob:
                ov_new.append(dict(x, screen=n))
        of = {(x["cls"], x["text"]) for x in o.get("overflow") or []}
        for x in r.get("overflow") or []:
            if (x["cls"], x["text"]) not in of:
                of_new.append(dict(x, screen=n))
        # 짝이 되는 원본 화면이 없으면 o 는 위에서 이미 {} 다 - 높이가 있다는
        # 것 자체가 짝이 있다는 뜻이므로 조건을 또 걸지 않는다.
        if o.get("height") and r.get("height"):
            ratio = r["height"] / float(o["height"])
            if ratio > HEIGHT_GROWTH_LIMIT:
                tall.append({"screen": n, "before": o["height"],
                             "after": r["height"], "ratio": round(ratio, 2)})
    metrics["overlaps_new"] = len(ov_new)
    metrics["overflows_new"] = len(of_new)
    metrics["screens_much_taller"] = len(tall)
    for x in ov_new[:20]:
        W("E", x["screen"], "%r and %r overlap by %d%%"
          % (x["a"], x["b"], x["overlap_pct"]))
    for x in of_new[:20]:
        W("E", x["screen"], "content spills %dpx out of a %dpx box (.%s): %r"
          % (x["spill_px"], x["box_h"], x["cls"] or x["tag"], x["text"]))
    for x in tall:
        W("E", x["screen"], "screen is %.2fx taller than the original (%d -> %dpx)"
          % (x["ratio"], x["before"], x["after"]))

    # E3 - text that did not wrap before and wraps now. The recipient navbar
    # breaks this way rather than by rect overlap.
    wrap_new = []
    for n in (want if ctx.derived else shared):
        ob = tally(orig["screens"].get(n, {}).get("wrapped"))
        for x in rep["screens"].get(n, {}).get("wrapped") or []:
            k = (x["tag"], x["cls"])
            if ob.get(k, 0) > 0:
                ob[k] -= 1
            else:
                wrap_new.append(dict(x, screen=n))
    metrics["newly_wrapped_text"] = len(wrap_new)
    # derived 가 거짓이면 shared 는 늘 비어 있다 (core.audit 이 그렇게 만든다).
    if not ctx.derived:
        ctx.skipped.append(
            "E/newly-wrapped text and height growth (no shared screens)")
    for x in wrap_new[:20]:
        W("E", x["screen"], "%r now wraps onto %d lines (.%s) - it did not before"
          % (x["text"], x["lines"], x["cls"] or x["tag"]), lines=x["lines"])
