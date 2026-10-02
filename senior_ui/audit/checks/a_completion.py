r"""검사 A - 과제 완수. fatal.

흐름이 적은 화면에 모두 도달했는지, 금액이 완료 화면까지 왕복했는지,
data-screen · data-action · id 가 사라지지 않았는지를 본다. 멈춘 뒤의 "도달 못
함" 은 파생 결함으로 표시해 한 원인을 여러 번 세지 않는다. 화면 이름으로 짝을
맞추는 부분은 원본에서 파생된 빌드에서만 돈다 - 새 설계에는 지킬 원본이 없다.
"""
from ..context import union
from ..flow import AMOUNT_SHOWN


def run(ctx):
    rep, orig, want = ctx.rep, ctx.orig, ctx.want
    metrics, F = ctx.metrics, ctx.fatal_

    metrics["screens_expected"] = len(want)
    metrics["screens_reached"] = len(rep["reached"])
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
        elif row["landed_on"] is None:
            # __screen() 이 없거나 null 을 돌려준 것이다. "landed on None" 만으로는
            # 어디를 고쳐야 할지 알 수 없으므로 무엇이 깨졌는지 적는다.
            F("A", name, "화면 전환 후 window.__screen() 이 null 을 반환했다. "
                         "기록 훅 __screen() 은 현재 화면의 id 를 반환해야 한다. "
                         "원본 HTML 의 __screen() · __startTask() · __dump() 를 유지하라.")
        elif row["landed_on"] != name:
            F("A", name, "landed on %r instead" % row["landed_on"])

    if rep["missing_ids"]:
        F("A", None, "ids the transition script needs are gone: "
          + ", ".join(rep["missing_ids"]), lost=rep["missing_ids"])

    # 완료 화면은 흐름의 마지막 단계이고, 금액을 담은 선택자는 흐름이 알려 준다.
    # 화면 이름을 "done" 으로 못박으면 다른 이름을 쓴 설계를 검사할 수 없다.
    last_screen = want[-1] if want else None
    done_sel = ctx.flow.get("done_amount") or "#dn-amt"
    done = (rep["screens"].get(last_screen) or {}) if last_screen else {}
    shown_done = dict(done.get("shown") or []).get(done_sel)
    metrics["done_screen"] = last_screen
    metrics["done_amount"] = shown_done
    if done and shown_done != AMOUNT_SHOWN:
        F("A", last_screen, "완료 화면의 %s 가 %r 을 보여 준다. 과제가 넣은 값은 %r 이다."
          % (done_sel, shown_done, AMOUNT_SHOWN))

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

    if rep["js_errors"]:
        F("A", None, "JavaScript errors during the task: "
          + " | ".join(rep["js_errors"][:3]))
