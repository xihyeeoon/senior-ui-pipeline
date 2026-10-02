r"""검사 H - 정의되지 않은 class. warning.

어떤 스타일시트도 정의하지 않은 class 를 찾는다. 원래 과제에는 없던 검사인데,
두 렌더링 실패 - example1 의 bg-primary/text-primary 와 이번 run 의 sr-only -
의 공통 원인이어서 넣었다. 정의가 없는 class 는 아무 일도 하지 않으므로,
숨기려던 라벨이 보이고 넣으려던 색이 들어가지 않는다.
"""


def run(ctx):
    metrics, W = ctx.metrics, ctx.warn

    before_undef = {x["cls"] for x in ctx.orig.get("undefined_classes", [])}
    new_undef = [x for x in ctx.rep.get("undefined_classes", [])
                 if x["cls"] not in before_undef]
    metrics["undefined_classes_new"] = sorted({x["cls"] for x in new_undef})
    for x in new_undef:
        W("H", x["screen"], "class %r is used %dx but no stylesheet defines it - "
          "it has no effect (e.g. %r)" % (x["cls"], x["count"], x["sample"]),
          cls=x["cls"], count=x["count"])
