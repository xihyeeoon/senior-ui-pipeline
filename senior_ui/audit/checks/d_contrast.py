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

나머지는 비교가 아니다 - 그 화면만 보고 알 수 있다. 그래서 모든 화면에서 돈다.

    기준 미달    글자가 그 크기에 필요한 명암비를 넘는지. 새 설계에서만 돈다 -
                 수리본에서는 위의 개수 비교가 그 일을 하고, 원본이 이미 안고
                 있던 저명암을 생성물의 결함으로 적으면 고칠 수 없는 경고가
                 쌓인다. 비교가 물러난 자리를 메우는 판정이다.
    판정 불가    그라디언트나 이미지 위의 글자는 뒤에 깔린 색이 하나가 아니라
                 잴 수 없다. 통과로 세면 배경을 그림으로 깐 빌드가 가장 선명한
                 빌드가 되므로 저명암과 따로 센다. 경고는 아니다.
    상속 색      자기 색이 없는 글자. 수리본에서는 "원본에 없던 것" 을 가릴 수
                 있으므로 그것만 적는다. 새 설계에는 가릴 기준이 없고, 색을
                 상속받는 것 자체는 흔한 모양이다 (Run1 한 빌드에 102건). 그래서
                 읽히지 않는 것만 세고, 경고는 기준 미달 쪽 finding 에 "상속받은
                 색이다" 로 함께 담는다 - 결함 하나에 finding 하나.
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

    # 새 설계에는 "원본에 없던 것" 을 가릴 기준이 없다. 상속 자체는 흔한 모양
    # 이므로 (Run1 한 빌드에 102건 - 숫자판 버튼과 상태바까지 전부 상속이고 전부
    # 멀쩡하다) 그대로 적으면 경고가 노이즈로 찬다. 읽히지 않는 것만 세고, 경고는
    # _below_threshold 가 그 글자의 finding 하나에 함께 담는다 - 결함 하나에
    # finding 하나여야 하므로 같은 글자를 두 번 적지 않는다.
    metrics["new_inherited_colour"] = None
    metrics["inherited_colour_unreadable"] = len(_unreadable_inherited(ctx))


def _unreadable_inherited(ctx):
    """자기 색이 없는데 그 색으로는 읽히지 않는 글자. {(방문, tag, text)}.

    probes 의 두 목록은 class 를 자르는 길이가 달라 (tag, text) 로 맞춘다.
    한 화면 안에서 그 둘이면 같은 요소를 가리킨다.
    """
    out = set()
    for n in ctx.want:
        row = ctx.rep["screens"].get(n) or {}
        low = {(x["tag"], x["text"]) for x in row.get("contrast") or []}
        for x in row.get("inherited") or []:
            if (x["tag"], x["text"]) in low:
                out.add((n, x["tag"], x["text"]))
    return out


def _below_threshold(ctx):
    """기준에 못 미치는 글자를 하나씩. 새 설계에서만 돈다.

    수리본에서는 개수의 전후 비교가 그 일을 한다 - 원본이 이미 안고 있던 저명암을
    생성물의 결함으로 적으면 고칠 수 없는 경고가 쌓인다. 새 설계에는 그 전후가
    없으므로 비교가 물러나고(_counts), 그 자리에 아무 말도 남지 않으면 읽을 수
    없는 글이 조용히 통과한다. 그래서 비교 대신 기준으로 판정한다 - 비교가 아니라
    "이 글자가 읽히는가" 이므로 짝이 되는 원본 화면이 필요 없다.

    경계는 요소마다 다르다 (큰 글씨는 3.0:1, 나머지는 4.5:1). probes.CONTRAST 가
    요소별로 그 경계를 적어 두므로 여기서는 그 목록을 그대로 쓴다 - 목록에 있는
    것이 곧 기준 미달이다.

    판정 불가(그라디언트·이미지 위)는 이 목록에 없다. 경고가 아니라 따로 세는
    것이고 그것은 _undetermined 가 한다.
    """
    if ctx.derived:
        return
    rep, W = ctx.rep, ctx.warn
    inherited = _unreadable_inherited(ctx)
    seen = set()
    for n in ctx.want:
        for x in (rep["screens"].get(n) or {}).get("contrast") or []:
            k = (n, x["tag"], x["cls"], x["text"])
            if k in seen:
                continue
            seen.add(k)
            if len(seen) > 20:
                return
            where = x["tag"] + ("." + x["cls"] if x["cls"] else "")
            # 선언된 색과 눈에 닿는 색이 다르면 알파나 opacity 가 끼어 있다.
            # 그 둘을 다 적지 않으면 왜 걸렸는지 설명되지 않는다.
            lit = ("" if x.get("seen") in (None, x["color"])
                   else " (눈에 닿는 색 %s)" % x["seen"])
            own = (n, x["tag"], x["text"]) in inherited
            why = (" 이 글자에 색을 정해 주는 규칙이 없다 - 상속받은 색이다."
                   if own else "")
            W("D", n, "%r (%s) 의 명암비가 %.2f:1 이다 - %.1f:1 이 필요하다. "
              "글자색 %s%s, 배경 %s.%s"
              % (x["text"], where, x["ratio"], x["need"], x["color"], lit,
                 x["bg"], why),
              cls=x["cls"], tag=x["tag"], color=x["color"], seen=x.get("seen"),
              bg=x["bg"], ratio=x["ratio"], need=x["need"], inherited=own)


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
PARTS = [_counts, _inherited, _below_threshold, _undetermined, _gained_text]


def run(ctx):
    for part in PARTS:
        part(ctx)
