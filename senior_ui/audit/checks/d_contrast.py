r"""검사 D - 명암비. warning.

명암비 계산 자체는 probes.CONTRAST 가 페이지 안에서 한다. 이 파일은 그 결과로
무엇을 결함이라 부를지 정한다.

세 가지는 전후 비교다 - 짝이 되는 원본 화면이 있어야 뜻이 있다.

    저명암 개수의 증가        합계와 화면별
    gained-text              이미 저명암이던 요소에 읽을 글이 들어왔는지
                             (개수는 그대로이므로 개수 비교로는 못 잡는다)

새 설계(`derived_from_original: false`)에는 그 짝이 없다. 화면 이름이 같다고
같은 화면이 아니다 - 원본과 재구성본 둘 다 `bank`, `amount` 가 있고 전혀 다른
화면이다. 그 비교를 그대로 돌리면 화면 수와 구성이 다른 것을 결함으로 읽으므로,
돌리지 않고 `checks_stood_down` 에 이유를 적는다.

두 가지는 비교가 아니다 - 그 화면만 보고 알 수 있다. 그래서 모든 화면에서 돈다.

    판정 불가    그라디언트나 이미지 위의 글자는 뒤에 깔린 색이 하나가 아니라
                 잴 수 없다. 통과로 세면 배경을 그림으로 깐 빌드가 가장 선명한
                 빌드가 되므로 저명암과 따로 센다.
    상속 색      자기 색이 없는 글자. 수리본에서는 "원본에 없던 것" 을 가릴 수
                 있으므로 그것만 적는다. 새 설계에는 가릴 기준이 없고, 색을
                 상속받는 것 자체는 흔한 모양이다 (Run1 한 빌드에 102건). 그래서
                 상속받은 색이 실제로 읽히지 않는 것 - 이 검사가 잡으려는 "색이
                 없어서 사라진 라벨" - 만 적는다.
"""
import re

# 더해진 글이 장식이 아니라 실제로 읽히는 글인지 가리는 데 쓴다.
WORDY = re.compile(r"[0-9A-Za-z가-힣]")

NO_PAIR = ("새 설계라 짝이 되는 원본 화면이 없다. 화면 이름이 같다고 같은 "
           "화면이 아니므로, 견주면 두 설계가 다른 것을 결함으로 읽는다.")


def _counts(ctx):
    """저명암 개수의 전후 비교. 짝이 되는 원본 화면이 있을 때만 돈다."""
    orig, rep, want, shared = ctx.orig, ctx.rep, ctx.want, ctx.shared
    metrics, W = ctx.metrics, ctx.warn

    lc_before = {n: len(r.get("contrast") or [])
                 for n, r in orig["screens"].items()}
    lc_after = {n: len(r.get("contrast") or [])
                for n, r in rep["screens"].items()}
    metrics["low_contrast_after"] = sum(lc_after.values())
    if not ctx.derived:
        # 견줄 수 없는 수를 적어 두면 리포트가 그것을 "전 -> 후" 로 찍는다.
        # 그 화살표가 비교이고, 하지 않기로 한 것이 바로 그 비교다.
        metrics["low_contrast_before"] = None
        metrics["low_contrast_by_screen"] = {
            n: {"before": None, "after": lc_after.get(n)} for n in want}
        ctx.skipped.append("D/저명암 개수 전후 비교 (합계·화면별) - " + NO_PAIR)
        return
    metrics["low_contrast_before"] = sum(lc_before.values())
    metrics["low_contrast_by_screen"] = {
        n: {"before": lc_before.get(n), "after": lc_after.get(n)} for n in want}
    if metrics["low_contrast_after"] > metrics["low_contrast_before"]:
        W("D", None, "low-contrast text grew from %d to %d"
          % (metrics["low_contrast_before"], metrics["low_contrast_after"]))
    for n in shared:
        b, a = lc_before.get(n), lc_after.get(n)
        if b is not None and a is not None and a > b:
            W("D", n, "low-contrast text grew from %d to %d" % (b, a))


def _undetermined(ctx):
    """뒤에 깔린 색이 하나가 아니어서 잴 수 없었던 글자. 비교가 아니다."""
    rep, metrics, W = ctx.rep, ctx.metrics, ctx.warn

    undet = []
    for n in ctx.want:
        for x in (rep["screens"].get(n) or {}).get("contrast_undetermined") or []:
            undet.append(dict(x, screen=n))
    metrics["contrast_undetermined"] = len(undet)
    metrics["contrast_undetermined_before"] = sum(
        len(r.get("contrast_undetermined") or [])
        for r in ctx.orig["screens"].values())
    seen = set()
    for x in undet:
        k = (x["screen"], x["cls"], x["text"])
        if k in seen:
            continue
        seen.add(k)
        if len(seen) > 20:
            break
        W("D", x["screen"], "%r 뒤에 깔린 색이 하나가 아니라 명암비를 판정할 수 "
          "없다 (%s 의 %s). 통과로 세지 않는다 - 글자색은 %s 다."
          % (x["text"], x["behind"], x["background"], x["color"]),
          cls=x["cls"], tag=x["tag"], color=x["color"],
          background=x["background"], behind=x["behind"], need=x["need"])


def _inherited(ctx):
    """자기 색이 없는 글자. 모든 화면에서 돈다 - 비교가 아니다.

    수리본에서는 "원본에 없던 것" 을 가릴 수 있으므로 그것만 적는다. 새 설계
    에서는 가릴 기준이 없으므로, 상속받은 색이 실제로 읽히지 않는 것만 적는다.
    """
    orig, rep, metrics, W = ctx.orig, ctx.rep, ctx.metrics, ctx.warn

    if ctx.derived:
        new_inherited = []
        for n in ctx.want:
            o = {(x["text"], x["cls"])
                 for x in (orig["screens"].get(n) or {}).get("inherited") or []}
            for x in (rep["screens"].get(n) or {}).get("inherited") or []:
                if (x["text"], x["cls"]) not in o:
                    new_inherited.append(dict(x, screen=n))
        metrics["new_inherited_colour"] = len(new_inherited)
        for x in new_inherited[:20]:
            W("D", x["screen"], "new text %r takes its colour purely by "
              "inheritance (%s) - nothing sets a colour for it"
              % (x["text"], x["color"]), cls=x["cls"], tag=x["tag"])
        return

    metrics["new_inherited_colour"] = None
    unreadable = []
    for n in ctx.want:
        row = rep["screens"].get(n) or {}
        # probes 의 두 목록은 class 를 자르는 길이가 달라 (tag, text) 로 맞춘다.
        # 한 화면 안에서 그 둘이면 같은 요소를 가리킨다.
        low = {(x["tag"], x["text"]): x for x in row.get("contrast") or []}
        for x in row.get("inherited") or []:
            hit = low.get((x["tag"], x["text"]))
            if hit:
                unreadable.append(dict(x, screen=n, ratio=hit["ratio"],
                                       need=hit["need"], bg=hit["bg"]))
    metrics["inherited_colour_unreadable"] = len(unreadable)
    for x in unreadable[:20]:
        W("D", x["screen"], "%r 은 자기 색이 없는데 상속받은 색(%s)이 배경(%s)에서 "
          "%.2f:1 이라 읽히지 않는다 (%.1f:1 이 필요하다). 이 글자에 색을 정해 "
          "주는 규칙이 없다." % (x["text"], x["color"], x["bg"], x["ratio"],
                                 x["need"]),
          cls=x["cls"], tag=x["tag"], color=x["color"], ratio=x["ratio"],
          need=x["need"], bg=x["bg"])


def _gained_text(ctx):
    """이미 저명암이던 요소에 읽을 글이 들어왔는지.

    개수는 그대로인데 읽어야 할 글이 늘기 때문에 개수 비교로는 잡히지 않는다.
    원본의 그 요소와 빌드의 그 요소가 같은 요소여야 뜻이 있는 비교이므로, 짝이
    되는 원본 화면에서만 돈다.
    """
    orig, rep, metrics, W = ctx.orig, ctx.rep, ctx.metrics, ctx.warn

    burdened = []
    for n in ctx.shared:
        by_key = {}
        for x in (orig["screens"].get(n) or {}).get("contrast") or []:
            by_key.setdefault((x["tag"], x["cls"]), set()).add(x["text"])
        for x in (rep["screens"].get(n) or {}).get("contrast") or []:
            k = (x["tag"], x["cls"])
            was = by_key.get(k)
            if not was or x["text"] in was:
                continue
            # only when text was added, and the addition is actually readable
            if len(x["text"]) > max(len(t) for t in was) and WORDY.search(x["text"]):
                burdened.append(dict(x, screen=n, before=sorted(was)[0]))
    metrics["low_contrast_gained_text"] = len(burdened)
    if not ctx.derived:
        ctx.skipped.append("D/gained-text (저대비 요소에 글이 늘었는지) - "
                           + NO_PAIR)
    seen = set()
    for x in burdened:
        k = (x["screen"], x["cls"], x["text"])
        if k in seen:
            continue
        seen.add(k)
        W("D", x["screen"], "already low-contrast element (.%s, %.2f:1) gained "
          "readable text: %r -> %r - the count is unchanged, so this passes the "
          "before/after comparison" % (x["cls"], x["ratio"], x["before"], x["text"]),
          cls=x["cls"], ratio=x["ratio"], need=x["need"],
          color=x["color"], bg=x["bg"])


# 이 순서가 warning 목록과 metrics 키의 순서다 - 바꾸면 출력이 바뀐다.
PARTS = [_counts, _inherited, _undetermined, _gained_text]


def run(ctx):
    for part in PARTS:
        part(ctx)
