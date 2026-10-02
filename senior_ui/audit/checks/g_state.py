r"""검사 G - 상태 구분. warning.

`.x` 와 `.x.on` 이 아직 다르게 보이는지 본다. 원본에서 이미 구분이 없던 짝은
새 결함으로 세지 않는다. 비교하는 속성은 probes.STATE_PAIRS 가 정한 것뿐이므로,
그 밖의 방식으로 상태를 드러내는 설계는 구분이 있어도 걸릴 수 있다.
"""


def collapsed(snapshot):
    return {(x["base"], x["state"]) for x in snapshot["state_pairs"]
            if not x["differing"]}


def run(ctx):
    metrics, W = ctx.metrics, ctx.warn

    before_bad = collapsed(ctx.orig)
    now_bad = sorted(collapsed(ctx.rep) - before_bad)
    metrics["state_pairs_checked"] = len(ctx.rep["state_pairs"])
    metrics["state_pairs_collapsed"] = len(now_bad)
    detail = {(x["base"], x["state"]): x for x in ctx.rep["state_pairs"]}
    for base, state in now_bad:
        x = detail[(base, state)]
        W("G", None, "%s and %s%s now render identically (%s) - the state is no "
          "longer visible" % (base, base, "." + state, ", ".join(x["props"])),
          base=base, state=state, properties=x["props"],
          base_values=x["base_values"])
