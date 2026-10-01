r"""Machine-readable audit of a restructured build for the transfer prototype.

두 스냅샷(원본 · 생성물)과 두 HTML 을 받아 검사 A~I 를 돌리고
{"passed", "fatal", "warning", "metrics"} 를 돌려준다. 브라우저도 파일도 건드리지
않는 순수 함수다 - 걷기는 drive.py, 단계별 걸러내기는 stage.py, CLI 는
__main__.py 가 한다.

Checks
  A  task completion      fatal   8 screens reached, amount round-trips,
                                  data-action / id / data-screen preserved
  B  display accuracy     fatal   shown values match what was entered;
                                  no injected alert()/confirm()/onclick;
                                  no hardcoded numbers in injected handlers
  C  dead controls        fatal   data-action with no branch in the handler;
                                  data-action present in the original but gone
  D  contrast             warning low-contrast count must not grow; new
                                  elements must not rely on inherited colour
  E  layout               warning overlapping text, content spilling out of its
                                  box, screens much taller than before
  F  language             warning English words that were not in the original
  G  state distinction    warning `.x` and `.x.on` must still look different
  I  choice preservation  fatal   values the original offered must still exist
                                  somewhere in the build

The screens, how to reach them and what each must show live in a flow file
under flows/ (see flow.load_flow); the in-page JavaScript probes live in
probes.py.
"""
import re

from .flow import ACCOUNT, AMOUNT, AMOUNT_SHOWN, NAME, fill

HEIGHT_GROWTH_LIMIT = 1.5      # screen scrollHeight vs the original
ENGLISH = re.compile(r"[A-Za-z][A-Za-z'’]{1,}")


def union(snapshot, key):
    out = set()
    for row in snapshot["screens"].values():
        out |= {v for v in row.get(key, []) or [] if v}
    return out


def audit(orig, rep, orig_html, rep_html, flow):
    fatal, warning, metrics = [], [], {}
    # A restructured build is not a repair of the original document: its screens
    # are different screens. Anything that compares screen-to-screen is only
    # meaningful when the two share a structure, so those checks stand down and
    # say so rather than reporting noise.
    derived = bool(flow.get("derived_from_original", True))
    metrics["flow"] = flow["name"]
    metrics["derived_from_original"] = derived
    skipped = []

    def F(check, screen, detail, **kw):
        fatal.append(dict(check=check, screen=screen, detail=detail, **kw))

    def W(check, screen, detail, **kw):
        warning.append(dict(check=check, screen=screen, detail=detail, **kw))

    want = [s["screen"] for s in flow["steps"]]
    # A name match is not a screen match: both designs happen to contain a
    # "bank" and an "amount" that have nothing to do with each other. Only a
    # build derived from the original may be compared screen by name.
    shared = [n for n in want if n in orig["screens"] and n in rep["screens"]] \
        if derived else []
    metrics["screens_in_flow"] = want
    metrics["screens_comparable_to_original"] = shared

    # ---------------------------------------------------------------- A ----
    if rep["load_failed"]:
        F("A", None, "page failed to load: " + rep["load_failed"])
        return {"passed": False, "fatal": fatal, "warning": warning,
                "metrics": metrics}

    metrics["screens_expected"] = len(want)
    metrics["screens_reached"] = len(rep["reached"])
    # 과제가 한 번 멈추면 그 뒤의 모든 화면이 "도달 못 함" 으로 걸린다. 그것들은
    # 독립된 결함이 아니라 한 원인의 결과다. 나누지 않으면 일찍 멈춘 실행일수록
    # fatal 이 부풀려져 run 끼리 숫자를 비교할 수 없다.
    stopped_at = None
    for i, name in enumerate(want):
        row = rep["screens"].get(name)
        if row is None:
            if stopped_at:
                F("A", name, "never reached - consequence of stopping at %r"
                  % stopped_at, derived_from=stopped_at)
            else:
                F("A", name, "never reached (task stopped after %d of %d screens)"
                  % (len(rep["reached"]), len(want)))
                stopped_at = name
        elif "error" in row:
            F("A", name, "navigation failed: " + row["error"])
            if not stopped_at:
                stopped_at = name
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
    done_sel = flow.get("done_amount") or "#dn-amt"
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
        if not derived:
            continue
        lost = sorted(a - b)
        if lost:
            F("A", None, "%s values lost: %s" % (label, ", ".join(lost)), lost=lost)
    if not derived:
        skipped.append("A/preservation (new design, nothing to preserve)")

    per_screen_loss = {}
    for n in (want if derived else []):
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
    if not derived:
        skipped.append("A/per-screen attribute loss")

    if rep["js_errors"]:
        F("A", None, "JavaScript errors during the task: "
          + " | ".join(rep["js_errors"][:3]))

    # ---------------------------------------------------------------- B ----
    for name, pairs in flow["expect"].items():
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
    def calls(html, fn):
        return set(re.findall(r"%s\(\s*(['\"])(.*?)\1" % fn, html))

    for fn in ("alert", "confirm", "prompt"):
        new = calls(rep_html, fn) - calls(orig_html, fn)
        for _q, msg in sorted(new):
            digits = re.findall(r"\d[\d,]*", msg)
            F("B", None, "%s() injected that the original never had: %r"
              % (fn, msg), injected=msg, numbers=digits)
            if digits:
                F("B", None,
                  "injected %s() hardcodes %s - the value is dynamic, so it will "
                  "be wrong for any other amount" % (fn, ", ".join(digits)),
                  injected=msg, numbers=digits)
    metrics["injected_dialog_calls"] = sum(
        len(calls(rep_html, f) - calls(orig_html, f))
        for f in ("alert", "confirm", "prompt"))

    orig_onclick = union(orig, "onclicks")
    rep_onclick = union(rep, "onclicks")
    added = sorted(rep_onclick - orig_onclick)
    metrics["onclick_added"] = len(added)
    for h in added:
        F("B", None, "onclick attribute added that the original did not have: "
          + h[:120], handler=h)

    # dialogs actually raised while driving the task
    metrics["dialogs_during_task"] = len(rep["dialogs"])
    for d in rep["dialogs"]:
        nums = [n for n in re.findall(r"\d[\d,]*", d["message"])
                if n not in (AMOUNT_SHOWN, AMOUNT, ACCOUNT)]
        F("B", d["screen"], "blocking %s during the task: %r"
          % (d["type"], d["message"]))
        if nums:
            F("B", d["screen"],
              "dialog states %s while the task used %s"
              % (", ".join(nums), AMOUNT_SHOWN), numbers=nums)

    # ---------------------------------------------------------------- C ----
    # The handler chain lives in the build under test. For a repair that is the
    # original script copied over; for a new design it is that design's own.
    handled = set(re.findall(r"a\s*===\s*'([a-z-]+)'", rep_html)) \
        or set(re.findall(r"a\s*===\s*'([a-z-]+)'", orig_html))
    metrics["handled_actions"] = len(handled)
    orig_actions, rep_actions = union(orig, "actions"), union(rep, "actions")
    pre_existing_dead = (orig_actions - handled) if derived else set()
    new_dead = sorted((rep_actions - handled) - pre_existing_dead)
    metrics["dead_controls_new"] = len(new_dead)
    metrics["dead_controls_pre_existing"] = sorted(pre_existing_dead)
    for a in new_dead:
        F("C", None, "data-action=%r has no branch in the handler - the control "
          "looks tappable and does nothing" % a, action=a)
    removed = sorted(orig_actions - rep_actions) if derived else []
    for a in removed:
        F("C", None, "data-action=%r existed in the original and is gone" % a,
          action=a)

    # ---------------------------------------------------------------- D ----
    lc_before = {n: len(r.get("contrast", []))
                 for n, r in orig["screens"].items()}
    lc_after = {n: len(r.get("contrast", []))
                for n, r in rep["screens"].items()}
    metrics["low_contrast_before"] = sum(lc_before.values())
    metrics["low_contrast_after"] = sum(lc_after.values())
    metrics["low_contrast_by_screen"] = {
        n: {"before": lc_before.get(n), "after": lc_after.get(n)}
        for n in (want if derived else shared)}
    if metrics["low_contrast_after"] > metrics["low_contrast_before"]:
        W("D", None, "low-contrast text grew from %d to %d"
          % (metrics["low_contrast_before"], metrics["low_contrast_after"]))
    for n in shared:
        b, a = lc_before.get(n), lc_after.get(n)
        if b is not None and a is not None and a > b:
            W("D", n, "low-contrast text grew from %d to %d" % (b, a))

    new_inherited = []
    for n in (want if derived else shared):
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
    WORDY = re.compile(r"[0-9A-Za-z가-힣]")
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

    # ---------------------------------------------------------------- E ----
    ov_new, of_new, tall = [], [], []
    for n in want:
        # overlap and overflow are defects on their own terms, so they run on
        # every screen; a missing baseline just means nothing is subtracted.
        # Wrapping and height growth are comparisons, so they only run where a
        # matching original screen exists.
        o = orig["screens"].get(n, {}) if (derived or n in shared) else {}
        r = rep["screens"].get(n, {})
        ob = {(x["a"], x["b"]) for x in o.get("overlap", [])}
        for x in r.get("overlap", []):
            if (x["a"], x["b"]) not in ob:
                ov_new.append(dict(x, screen=n))
        of = {(x["cls"], x["text"]) for x in o.get("overflow", [])}
        for x in r.get("overflow", []):
            if (x["cls"], x["text"]) not in of:
                of_new.append(dict(x, screen=n))
        if o.get("height") and r.get("height") and (derived or n in shared):
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
    for n in (want if derived else shared):
        def key(items):
            out = {}
            for x in items or []:
                out[(x["tag"], x["cls"])] = out.get((x["tag"], x["cls"]), 0) + 1
            return out
        ob = key(orig["screens"].get(n, {}).get("wrapped"))
        for x in rep["screens"].get(n, {}).get("wrapped", []) or []:
            k = (x["tag"], x["cls"])
            if ob.get(k, 0) > 0:
                ob[k] -= 1
            else:
                wrap_new.append(dict(x, screen=n))
    metrics["newly_wrapped_text"] = len(wrap_new)
    if not derived and not shared:
        skipped.append("E/newly-wrapped text and height growth (no shared screens)")
    for x in wrap_new[:20]:
        W("E", x["screen"], "%r now wraps onto %d lines (.%s) - it did not before"
          % (x["text"], x["lines"], x["cls"] or x["tag"]), lines=x["lines"])

    # ---------------------------------------------------------------- F ----
    def words(snapshot):
        seen = set()
        for row in snapshot["screens"].values():
            seen |= set(ENGLISH.findall(row.get("text") or ""))
        return seen

    new_en = sorted(words(rep) - words(orig))
    metrics["new_english_words"] = new_en
    for n in want:
        t = (rep["screens"].get(n) or {}).get("text") or ""
        hits = sorted({w for w in new_en if w in t})
        if hits:
            W("F", n, "English text not present in the original: "
              + ", ".join(hits), words=hits, source="runtime")

    # Markup the script overwrites at runtime never reaches the eye, but it is
    # still in the file - password's 재배열 -> "Shuffle" only shows up here.
    def markup_words(html):
        body = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S | re.I)
        return set(ENGLISH.findall(re.sub(r"<[^>]+>", " ", body)))

    # Anything appearing anywhere in the original file - including inside its
    # script, where the 37 bank and 29 securities names live - is not new
    # English. The reassembly merely bakes those into markup.
    static_only = sorted(markup_words(rep_html)
                         - set(ENGLISH.findall(orig_html))
                         - words(orig) - set(new_en))
    metrics["new_english_words_markup_only"] = static_only
    if static_only:
        W("F", None, "English added to the markup but overwritten before it "
          "renders: " + ", ".join(static_only), words=static_only, source="markup")

    # ---------------------------------------------------------------- G ----
    def collapsed(snapshot):
        return {(x["base"], x["state"]) for x in snapshot["state_pairs"]
                if not x["differing"]}

    before_bad = collapsed(orig)
    now_bad = sorted(collapsed(rep) - before_bad)
    metrics["state_pairs_checked"] = len(rep["state_pairs"])
    metrics["state_pairs_collapsed"] = len(now_bad)
    detail = {(x["base"], x["state"]): x for x in rep["state_pairs"]}
    for base, state in now_bad:
        x = detail[(base, state)]
        W("G", None, "%s and %s%s now render identically (%s) - the state is no "
          "longer visible" % (base, base, "." + state, ", ".join(x["props"])),
          base=base, state=state, properties=x["props"],
          base_values=x["base_values"])

    # ---------------------------------------------------------------- H ----
    # Not in the original brief, added because it is the shared root cause of
    # two rendering failures: example1's bg-primary/text-primary and this run's
    # sr-only. A class no stylesheet defines does nothing, so a label meant to
    # be hidden shows up and a colour meant to be applied never lands.
    before_undef = {x["cls"] for x in orig.get("undefined_classes", [])}
    new_undef = [x for x in rep.get("undefined_classes", [])
                 if x["cls"] not in before_undef]
    metrics["undefined_classes_new"] = sorted({x["cls"] for x in new_undef})
    for x in new_undef:
        W("H", x["screen"], "class %r is used %dx but no stylesheet defines it - "
          "it has no effect (e.g. %r)" % (x["cls"], x["count"], x["sample"]),
          cls=x["cls"], count=x["count"])

    # 흐름이 같은 화면을 여러 번 지나가면 같은 실패가 그 횟수만큼 기록된다.
    # 결함은 하나인데 숫자만 커지므로, 같은 (검사·화면·내용) 은 한 번만 센다.
    seen, deduped, dups = set(), [], 0
    for f in fatal:
        k = (f.get("check"), f.get("screen"), f.get("detail"))
        if k in seen:
            dups += 1
            continue
        seen.add(k)
        deduped.append(f)
    fatal[:] = deduped
    metrics["fatal_duplicates_removed"] = dups

    metrics["fatal_total"] = len(fatal)
    metrics["fatal_derived"] = len([f for f in fatal if f.get("derived_from")])
    metrics["fatal_root"] = metrics["fatal_total"] - metrics["fatal_derived"]
    metrics["stopped_at"] = stopped_at
    metrics["js_error_details"] = rep.get("js_error_details") or []
    metrics["flow_notes"] = rep.get("notes") or []
    # ------------------------------------------------------------ I ----
    # 원본에서 "고를 수 있던 것" 이 생성물에서 사라지면, 과제는 통과해도
    # 그 선택지를 쓰려던 사람은 막힌다. 검사 과제가 쓰는 값 하나만 남기고
    # 나머지를 지우는 식의 최소 구현을 잡는다. 앱 종류와 무관한 규칙이다 -
    # 같은 data-action 을 공유하는 반복 요소면 무엇이든 선택지로 본다.
    orig_choices = {}
    for row in orig["screens"].values():
        for action, vals in (row.get("choices") or {}).items():
            orig_choices.setdefault(action, set()).update(vals)

    # 생성물에서는 "어디에든 있는가" 만 본다. 한 화면에 다 보일 필요는 없고,
    # 스크립트 안의 배열로 들고 있어도 된다. 그래서 문서 전체에서 찾는다.
    missing_by_action, kept = {}, {}
    for action, vals in orig_choices.items():
        if len(vals) < 2:
            continue
        gone = sorted(v for v in vals if v not in rep_html)
        kept[action] = len(vals) - len(gone)
        if gone:
            missing_by_action[action] = {"total": len(vals), "missing": gone}

    metrics["choice_groups_original"] = {a: len(v) for a, v in orig_choices.items()
                                         if len(v) >= 2}
    metrics["choice_values_missing"] = {a: d["missing"] for a, d in missing_by_action.items()}
    for action, d in sorted(missing_by_action.items()):
        sample = ", ".join(d["missing"][:5]) + (" …" if len(d["missing"]) > 5 else "")
        F("I", None,
          "원본의 %s 선택지 %d개 중 %d개가 생성물에 없다 (예: %s). 화면에 모두 "
          "보일 필요는 없지만 값 자체는 모두 접근 가능해야 한다. 검색이나 단계적 "
          "선택으로 찾을 수 있게 포함하라."
          % (action, d["total"], len(d["missing"]), sample),
          action=action, missing=d["missing"])

    metrics["checks_stood_down"] = skipped
    return {"passed": not fatal, "fatal": fatal, "warning": warning,
            "metrics": metrics}
