r"""검사 A - 과제 완수. fatal.

흐름이 적은 화면에 모두 도달했는지, 금액이 완료 화면까지 왕복했는지,
data-screen · data-action · id 가 사라지지 않았는지를 본다.

도달은 두 가지가 같아야 인정한다 - 전환 스크립트의 기록(window.__screen())과
켜진 화면이 스스로 말하는 이름(`.screen.on` 의 data-screen). 기록만 바꾸고
on 클래스를 옮기지 않으면 사용자는 앞 화면에 그대로 서 있으므로, 기록 하나만
믿으면 그 빌드가 과제를 완주한 것으로 보인다.

멈춘 뒤의 "도달 못 함" 은 파생 결함으로 표시해 한 원인을 여러 번 세지 않는다. 금액 왕복도 같은
규칙을 따른다 - 도달하지 못한 화면에는 묻지 않고, 흐름의 expect 에 적혀 검사 B
가 이미 보는 선택자는 다시 보지 않는다. 화면 이름으로 짝을 맞추는 부분은
원본에서 파생된 빌드에서만 돈다 - 새 설계에는 지킬 원본이 없다.
"""
from ..context import union
from ..flow import fill, truth_of

# 켜진 화면 안에서만 잴 수 있는 것들. probes.py 가 켜진 화면이 없을 때 이
# 값들을 [] 가 아니라 null 로 돌려주므로, null 하나로 "아무것도 떠 있지
# 않았다" 를 알 수 있다 (probes.py 머리말 참고).
SCREEN_SCOPED = ("inherited", "overlap", "overflow", "wrapped", "shown")


def _unlit(row):
    """켜진 화면이 하나도 없었는가.

    키가 있으면서 값이 null 인 것만 본다. 키가 아예 없는 것은 옛 스냅샷이거나
    아직 긁지 않은 것이고, 그것은 "꺼져 있었다" 와 다른 일이다.
    """
    return any(k in row and row[k] is None for k in SCREEN_SCOPED)


def _screens_reached(ctx):
    """흐름이 적은 화면에 다 도달했는지. 한 번 멈추면 그 뒤는 전부 파생이다."""
    rep, want = ctx.rep, ctx.want
    metrics, F = ctx.metrics, ctx.fatal_

    metrics["screens_expected"] = len(want)
    metrics["screens_reached"] = len(rep["reached"])
    metrics["screens_unlit"] = [n for n in want
                                if _unlit(rep["screens"].get(n) or {})]
    metrics["screens_landed_on"] = {
        n: {"hook": (rep["screens"].get(n) or {}).get("landed_on"),
            "dom": (rep["screens"].get(n) or {}).get("dom_screen")}
        for n in want if n in rep["screens"]}
    # 과제가 한 번 멈추면 그 뒤의 모든 화면이 "도달 못 함" 으로 걸린다. 그것들은
    # 독립된 결함이 아니라 한 원인의 결과다. 나누지 않으면 일찍 멈춘 실행일수록
    # fatal 이 부풀려져 run 끼리 숫자를 비교할 수 없다.
    for name in want:
        row = rep["screens"].get(name)
        if row is None:
            if ctx.stopped_at:
                F("A", name, "never reached - consequence of stopping at %r"
                  % ctx.stopped_at, derived_from=ctx.stopped_at)
            else:
                F("A", name, "never reached (task stopped after %d of %d screens)"
                  % (len(rep["reached"]), len(want)))
                ctx.stopped_at = name
        elif "error" in row:
            F("A", name, "navigation failed: " + row["error"])
            if not ctx.stopped_at:
                ctx.stopped_at = name
        elif _unlit(row):
            # 켜진 화면이 없다. 화면에 매인 probe 가 전부 null 로 돌아왔다는
            # 뜻이고, 그 상태로는 무엇이 보이는지 하나도 잴 수 없다. 빈 목록을
            # 통과로 읽으면 아무것도 떠 있지 않은 빌드가 가장 깨끗해 보인다.
            F("A", name, "켜진 화면이 없다 - `.screen.on` 인 요소가 문서에 "
                         "하나도 없다. window.__screen() 은 %r 을 돌려주지만 "
                         "사용자에게는 아무것도 떠 있지 않으므로, 이 화면에서 "
                         "재야 할 것을 하나도 잴 수 없다. 화면을 넘길 때 on "
                         "클래스를 다음 화면으로 옮겨라."
              % row.get("landed_on"), dom_screen=None)
            if not ctx.stopped_at:
                ctx.stopped_at = name
        elif row["landed_on"] is None:
            # __screen() 이 없거나 null 을 돌려준 것이다. "landed on None" 만으로는
            # 어디를 고쳐야 할지 알 수 없으므로 무엇이 깨졌는지 적는다.
            F("A", name, "화면 전환 후 window.__screen() 이 null 을 반환했다. "
                         "기록 훅 __screen() 은 현재 화면의 id 를 반환해야 한다. "
                         "원본 HTML 의 __screen() · __startTask() · __dump() 를 유지하라.")
        elif row["landed_on"] != ctx.screen(name):
            # 예외는 나지 않았지만 과제는 여기서 더 나아가지 못했다. 뒤의 화면
            # 들은 그 결과이므로, 멈춘 곳으로 적어 파생으로 묶이게 한다.
            # 적지 않으면 첫 "도달 못 함" 이 stopped_at 을 자기 이름으로 채워,
            # 멈춤의 결과가 원인으로 기록된다.
            F("A", name, "landed on %r instead" % row["landed_on"])
            if not ctx.stopped_at:
                ctx.stopped_at = name
        elif row.get("dom_screen") != ctx.screen(name):
            # 기록은 넘어갔는데 화면은 넘어가지 않았다. 예외도 나지 않고
            # __screen() 도 맞는 이름을 돌려주므로, 기록 하나만 보면 완주한
            # 것으로 보인다 - 사용자는 앞 화면에 그대로 서 있다. 엉뚱한 화면에
            # 도착한 것과 같은 멈춤이므로 뒤의 화면들은 파생으로 묶인다.
            F("A", name, "window.__screen() 은 %r 을 돌려주는데 켜진 화면"
                         "(`.screen.on`)의 data-screen 은 %r 이다. 기록만 "
                         "바뀌고 화면은 넘어가지 않았으므로 사용자는 아직 %r "
                         "을 보고 있다. 화면을 넘길 때 on 클래스를 함께 옮겨라."
              % (ctx.screen(name), row.get("dom_screen"),
                 row.get("dom_screen")),
              dom_screen=row.get("dom_screen"))
            if not ctx.stopped_at:
                ctx.stopped_at = name


def _transition_ids(ctx):
    """전환 스크립트가 이름으로 찾는 id 가 사라졌는지."""
    rep, F = ctx.rep, ctx.fatal_
    if rep["missing_ids"]:
        F("A", None, "ids the transition script needs are gone: "
          + ", ".join(rep["missing_ids"]), lost=rep["missing_ids"])


def _arrived(row, screen):
    """그 화면에 실제로 도착했는지. 도착하지 못한 화면에 무엇이 보이는지는
    물을 수 없다 - 물으면 한 번의 실패가 두 건이 된다.

    기록과 화면이 둘 다 그 이름이어야 도착이다. _screens_reached 의 판정과
    같은 규칙이어야 하므로 여기도 같이 본다."""
    return (bool(row) and "error" not in row
            and row.get("landed_on") == screen
            and row.get("dom_screen") == screen)


def _amount_round_trip(ctx):
    """과제가 넣은 금액이 완료 화면까지 그대로 왕복했는지."""
    rep, want = ctx.rep, ctx.want
    metrics, F = ctx.metrics, ctx.fatal_

    # 완료 화면은 흐름의 마지막 단계이고, 금액을 담은 선택자는 흐름이 알려 준다.
    # 화면 이름을 "done" 으로 못박으면 다른 이름을 쓴 설계를 검사할 수 없다.
    last_screen = want[-1] if want else None
    done_sel = ctx.flow.get("done_amount") or "#dn-amt"
    done = (rep["screens"].get(last_screen) or {}) if last_screen else {}
    shown_done = dict(done.get("shown") or []).get(done_sel)
    metrics["done_screen"] = last_screen
    metrics["done_amount"] = shown_done
    # 도착하지 못했으면(멈춤·오류·엉뚱한 화면) 금액은 애초에 볼 수 없다.
    # _screens_reached 가 그 도착 실패를 이미 fatal 로 적었으므로, 여기서 또
    # 적으면 결함 하나가 두 번 세진다. 지표(done_amount)는 그대로 남긴다.
    if not _arrived(done, ctx.screen(last_screen)):
        return
    # 흐름의 expect 에 같은 선택자가 적혀 있으면 검사 B 가 같은 값을 같은 기준
    # 으로 이미 본다. 결함은 하나이므로 거기에 맡기고 여기서는 지표만 남긴다.
    # (네 흐름 파일 모두 완료 화면의 금액을 expect 에 적고 있다.) expect 에
    # 없으면 B 는 그 선택자를 보지 않으므로 A 가 유일한 검사다.
    truth = truth_of(ctx.flow)
    covered = any(fill(sel, truth) == done_sel
                  for sel, _ in (ctx.flow["expect"].get(last_screen) or []))
    if shown_done != truth["AMOUNT_SHOWN"] and not covered:
        F("A", last_screen, "완료 화면의 %s 가 %r 을 보여 준다. 과제가 넣은 값은 %r 이다."
          % (done_sel, shown_done, truth["AMOUNT_SHOWN"]))


def _preserved_attrs(ctx):
    """data-screen · data-action · id 가 문서 전체에서 사라졌는지. 짝을 맞추는
    비교이므로 원본에서 파생된 빌드에서만 돈다 - 새 설계에는 지킬 원본이 없다."""
    rep, orig = ctx.rep, ctx.orig
    metrics, F = ctx.metrics, ctx.fatal_

    for key, label in [("screens", "data-screen"), ("actions", "data-action"),
                       ("ids", "id")]:
        a, b = union(orig, key), union(rep, key)
        metrics["%s_original" % label] = len(a)
        metrics["%s_repaired" % label] = len(b)
        if not ctx.derived:
            continue
        lost = sorted(a - b)
        if lost:
            F("A", None, "%s values lost: %s" % (label, ", ".join(lost)), lost=lost)
    if not ctx.derived:
        ctx.skipped.append("A/preservation (new design, nothing to preserve)")


def _per_screen_loss(ctx):
    """같은 이름의 화면에서 data-action 이나 id 가 빠졌는지."""
    rep, orig, want = ctx.rep, ctx.orig, ctx.want
    metrics, F = ctx.metrics, ctx.fatal_

    per_screen_loss = {}
    for n in (want if ctx.derived else []):
        o = orig["screens"].get(n) or {}
        r = rep["screens"].get(n) or {}
        if not o or not r or "error" in r:
            continue
        lost = {}
        for key, label in [("actions", "data-action"), ("ids", "id")]:
            gone = sorted({v for v in o.get(key) or [] if v}
                          - {v for v in r.get(key) or [] if v})
            if gone:
                lost[label] = gone
        if lost:
            per_screen_loss[n] = lost
            for label, gone in lost.items():
                F("A", n, "%s removed from this screen: %s"
                  % (label, ", ".join(gone)), lost=gone)
    metrics["per_screen_attr_loss"] = per_screen_loss
    if not ctx.derived:
        ctx.skipped.append("A/per-screen attribute loss")


def _js_errors(ctx):
    """클릭 처리기를 멈추게 한 JS 오류. 셋까지만 적는다 - 나머지는 사본이다."""
    rep = ctx.rep
    if rep["js_errors"]:
        ctx.fatal_("A", None, "JavaScript errors during the task: "
                   + " | ".join(rep["js_errors"][:3]))


# 이 순서가 fatal 목록과 metrics 키의 순서다 - 바꾸면 출력이 바뀐다.
PARTS = [_screens_reached, _transition_ids, _amount_round_trip,
         _preserved_attrs, _per_screen_loss, _js_errors]


def run(ctx):
    for part in PARTS:
        part(ctx)
