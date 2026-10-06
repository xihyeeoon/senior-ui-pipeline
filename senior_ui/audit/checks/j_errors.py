r"""검사 J - 오류 경로. fatal (알림 글은 warning).

정답 경로만 걸으면 재설계에서 오류 처리가 통째로 빠져도 보이지 않는다. 실험
참가자는 실제로 계좌번호를 틀리므로, 오류를 알리고 되돌아가게 하는 동작은
사용자가 할 수 있는 일의 일부다. 그래서 흐름의 `error_paths` 를 하나씩 걸어
본 결과(drive.walk_error_path)를 여기서 판정한다.

**어떻게** 알릴지는 설계가 정한다 - 팝업이 아니어도 되고, 두 오류를 한 화면에
보여도 되고, 입력하는 즉시 알리거나 [다음] 을 끄고 이유를 보여도 된다. 지키는
것은 셋이다.

  나타남   잘못된 입력 뒤에 `expect_screen` 에 있고, 거기에 새로 나타난 글이
           있다 (fatal). 같은 화면에 머무르는 설계도 새 글이 있으면 오류
           상태로 인정한다. 다른 화면으로 갔어도 새 글이 없으면 - 정답
           경로에서 그 화면이 보이던 그대로라면 - 오류를 알린 것이 아니다.
  알아챔   새 글에 과제가 정한 단어(`notice_any`)가 하나라도 있다 (warning).
           단어는 원본 흐름에서 읽는다. 모델이 적은 `expect_text_any` 로
           판정하면 자기가 띄운 글을 그대로 적어 경고를 끌 수 있다.
  돌아감   `recover` 뒤에 `back_to` 에 있다 (fatal). `back_to` 는 정답
           경로에 있는 화면이고 완료 화면이 아니어야 한다 (back_to_ok).
           오류가 나타난 화면보다 뒤여도 된다 - 계좌 화면에서 은행이
           틀렸다고 알리고 뒤의 은행 고르기 화면으로 보내는 것은 고칠
           곳으로 보내는 설계다. 실제로 거기 닿는지는 위의 걷기가 본다.

"새로 나타난 글" 은 잘못된 입력의 마지막 동작 바로 앞에 보이던 글, 그리고 같은
화면이 정답 경로에서 보이던 글에 없던 줄이다. 줄을 견주기 전에 숫자와 정답
값을 걷어낸다 (normalize) - 눌러 넣은 계좌번호나 고른 은행 이름이 화면에
되비친 것은 알림이 아니다.

흐름에 오류 경로가 없으면 물러난다. 옛 흐름(Run 1~4)은 정답 경로만 적었고,
그 판정은 바뀌지 않아야 한다. 반대로 과제가 정한 오류 경로를 반드시 걸어야
하는 곳(재구성 루프)은 `error_paths_required` 로 id 를 넘기고, 빠진 것은
fatal 이다.
"""
import re

from ..flow import error_defs, truth_of, visit_keys

# 숫자 덩어리(쉼표·점·하이픈·공백 포함)와 바로 뒤의 "원". 금액·계좌번호·
# 자릿수 표시를 한꺼번에 걷어낸다.
NUMBERS = re.compile(r"[\d][\d,.\-\s]*원?")
LETTER = re.compile(r"[A-Za-z가-힣]")


def normalize(line, truth):
    """견주기 위한 줄. 정답 값(틀린 값 포함)과 숫자를 걷어내고 공백을 없앤다.
    글자(한글·영문)가 둘 미만이면 빈 문자열 - 알림이 될 수 없는 줄이다."""
    s = line
    for v in sorted((v for v in truth.values() if v), key=len, reverse=True):
        s = s.replace(v, "")
    s = re.sub(r"\s+", "", NUMBERS.sub("", s))
    return s if len(LETTER.findall(s)) >= 2 else ""


def new_lines(after, before, happy, truth):
    """after 에 있고 before · happy 에 없던 줄 (원래 모양 그대로, 순서대로)."""
    seen = {normalize(l, truth) for t in (before, happy)
            for l in (t or "").splitlines()}
    out, kept = [], set()
    for l in (after or "").splitlines():
        n = normalize(l, truth)
        if n and n not in seen and n not in kept:
            kept.add(n)
            out.append(l.strip())
    return out


def step_screens(steps):
    """정답 경로의 화면 이름들, 처음 지나는 순서로."""
    out = []
    for st in steps:
        if isinstance(st, dict) and st.get("screen") not in out:
            out.append(st.get("screen"))
    return out


def back_to_ok(screens, back_to, error_screen, done_screen):
    """`back_to` 가 사용자가 고칠 수 있는 곳인가 - 정답 경로에 있는 화면이고
    완료 화면이 아니다. 오류가 나타난 화면 자신(그 자리에서 고치는 설계)도
    된다.

    전에는 "오류가 나타난 화면이거나 그보다 앞" 이었다. gpt-6.1-sol 의 첫 시도
    (20261006-124055)는 계좌 화면에서 은행 오류를 알리고 은행 고르기 화면으로
    보냈는데, 은행 화면이 순서상 뒤라서 떨어졌다. 규칙의 목적은 고칠 수 있는
    곳으로 돌아가는 것이고 순서가 아니다. 완료 화면으로 보내는 것만은 고칠
    기회가 없으므로 막는다.
    """
    if back_to == done_screen:
        return False
    # 오류 화면 자신은 steps 밖(팝업)이어도 둔다 - 원본 팝업 동작과 같고 J 가 걸어서 확인한다 (11-4 결정).
    return back_to == error_screen or back_to in screens


def done_screen(steps):
    """완료 화면 - 정답 경로의 마지막 단계의 화면."""
    last = steps[-1] if steps else None
    return last.get("screen") if isinstance(last, dict) else None


def _happy_text(ctx, screen):
    """그 화면이 정답 경로에서 처음 보였을 때의 글."""
    for visit in visit_keys(ctx.flow.get("steps") or []):
        if ctx.screen(visit) == screen:
            row = ctx.rep["screens"].get(visit) or {}
            return "\n".join(t for t in (row.get("text"), row.get("outside_text"))
                             if t)
    return ""


def _after_text(row):
    """오류 상태에서 사용자가 본 글 - 화면의 글과, 잘못된 입력 뒤 오류 상태가
    나타날 때까지 뜬 대화상자의 글. 대화상자로만 알린 설계도 사용자는 그 글을
    읽었으므로 "나타남" 으로 인정한다. 막는 대화상자라는 결함은 검사 B 가 센다
    (결함 하나 = fatal 하나)."""
    dialogs = row.get("dialogs") or []
    start, end = row.get("dialogs_at_trigger"), row.get("dialogs_at_after")
    if start is None or end is None:
        said = []
    else:
        said = [d.get("message") or "" for d in dialogs[start:end]]
    return "\n".join([row.get("after_text") or ""] + said)


def _brief(detail):
    return re.sub(r"\s*\n\s*", " / ", str(detail or "")).strip()[:300]


def _judge(ctx, ep, row, defs, result):
    F, W = ctx.fatal_, ctx.warn
    eid = ep["id"]
    exp, back = ep.get("expect_screen"), ep.get("back_to")
    err = row.get("error")
    if err and err.get("phase") in ("load", "replay"):
        # 정답 걸음이 막힌 것은 검사 A 가 이미 적었다. 그 결과로 오류 경로를
        # 걷지 못한 것은 파생이다.
        if ctx.stopped_at:
            F("J", exp, "오류 경로 %s: 정답 경로가 %r 에서 멈춰 갈라지는 곳(%s)까지 "
              "가지 못했다" % (eid, ctx.stopped_at, ep.get("from_step")),
              derived_from=ctx.stopped_at, error_path=eid)
        else:
            F("J", exp, "오류 경로 %s: 갈라지는 곳(%s)까지 정답대로 가다가 막혔다: %s"
              % (eid, ep.get("from_step"), _brief(err.get("detail"))), error_path=eid)
        return
    if err and err.get("phase") == "inputs":
        F("J", exp, "오류 경로 %s: 잘못된 입력을 넣다가 막혔다: %s"
          % (eid, _brief(err.get("detail"))), error_path=eid)
        return

    after = row.get("after") or {}
    landed = after.get("dom_screen")
    hook = after.get("landed_on")
    trigger = (row.get("trigger") or {}).get("dom_screen")
    notice = new_lines(_after_text(row), row.get("before_text"),
                       _happy_text(ctx, exp), truth_of(ctx.flow))
    result.update(trigger_screen=trigger, landed_on=landed, notice=notice)
    if landed != exp or (hook is not None and hook != exp):
        F("J", exp, "오류 경로 %s: 잘못된 입력(%s) 뒤에 오류 상태가 나타나지 않았다 - "
          "%r 에 있어야 하는데 켜진 화면은 %r 이다. 틀린 값으로 다음 단계에 넘어가면 "
          "사용자는 틀린 줄 모른다."
          % (eid, ", ".join(defs.get("uses") or []) or "?", exp, landed),
          error_path=eid)
        return
    if not notice:
        F("J", exp, "오류 경로 %s: %r 에 머물렀지만 새로 나타난 글이 없다. 잘못된 "
          "입력을 넣기 전과 보이는 글이 같으면 사용자는 무엇이 틀렸는지 알 수 없다."
          % (eid, exp), error_path=eid)
        return
    result["appeared"] = True

    words = defs.get("notice_any") or []
    if words and not any(w in l for w in words for l in notice):
        W("J", exp, "오류 경로 %s: 새로 나타난 글에 %s 중 어느 단어도 없다 - 무엇이 "
          "틀렸는지 알아채기 어렵다. 나타난 글: %s"
          % (eid, " · ".join(words), " / ".join(notice)[:200]), error_path=eid)

    if err and err.get("phase") == "recover":
        F("J", exp, "오류 경로 %s: 되돌아가는 조작이 막혔다: %s"
          % (eid, _brief(err.get("detail"))), error_path=eid)
        return
    rec = (row.get("recover") or {}).get("dom_screen")
    result["recovered_to"] = rec
    if rec != back:
        F("J", exp, "오류 경로 %s: 되돌아가지 못했다 - %r 로 가야 하는데 켜진 화면은 "
          "%r 이다." % (eid, back, rec), error_path=eid)
        return
    steps = ctx.flow.get("steps") or []
    done = done_screen(steps)
    if not back_to_ok(step_screens(steps), back, exp, done):
        F("J", exp, "오류 경로 %s: 돌아가는 화면 %r 은 %s. 고치려면 정답 경로에서 "
          "완료 화면이 아닌 곳으로 돌아가야 한다."
          % (eid, back, "완료 화면이다" if back == done else "정답 경로에 없다"),
          error_path=eid)
        return
    result["recovered"] = True


def run(ctx):
    flow = ctx.flow
    paths = [e for e in flow.get("error_paths") or []
             if isinstance(e, dict) and e.get("id")]
    required = list(flow.get("error_paths_required") or [])
    if not paths and not required:
        ctx.skipped.append("J/흐름에 오류 경로가 없다 - 정답 경로만 걸었다")
        return

    defs = error_defs(flow)
    have = {e["id"] for e in paths}
    for rid in required:
        if rid not in have:
            d = defs.get(rid) or {}
            ctx.fatal_("J", None, "오류 경로 %s 가 흐름에 없다 (%s). 이 오류를 어떻게 "
                       "알리고 어디로 되돌아가는지 흐름 명세의 error_paths 에 적어라."
                       % (rid, d.get("about") or d.get("condition") or "?"),
                       error_path=rid)

    walked = ctx.rep.get("error_paths") or {}
    results = {}
    for ep in paths:
        res = results[ep["id"]] = {"appeared": False, "recovered": False}
        row = walked.get(ep["id"])
        if row is None:
            ctx.fatal_("J", ep.get("expect_screen"), "오류 경로 %s 를 걷지 않았다"
                       % ep["id"], error_path=ep["id"])
            continue
        _judge(ctx, ep, row, defs.get(ep["id"]) or {}, res)
        if row.get("js_errors"):
            ctx.fatal_("J", ep.get("expect_screen"),
                       "오류 경로 %s 를 걷는 중 JavaScript 오류: %s"
                       % (ep["id"], " | ".join(row["js_errors"][:3])),
                       error_path=ep["id"])
    ctx.metrics["error_paths"] = results
