r"""Machine-readable audit of a restructured build for the transfer prototype.

두 스냅샷(원본 · 생성물)과 두 HTML 을 받아 검사 A~J 를 돌리고
{"passed", "fatal", "warning", "metrics"} 를 돌려준다. 브라우저도 파일도 건드리지
않는 순수 함수다 - 걷기는 drive.py, 단계별 걸러내기는 stage.py, CLI 는
__main__.py 가 한다.

판정 자체는 하지 않는다. 검사 하나가 모듈 하나이고 (checks/), 이 파일은 순서를
정하고 집계만 한다. 검사가 함께 보는 입력과 함께 쓰는 출력은 context.py 의
AuditContext 다.

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
  H  undefined class      warning a class no stylesheet defines does nothing
  I  choice preservation  fatal   values the original offered must still exist
                                  somewhere in the build - the tool's injected
                                  data block does not count; warns when a value
                                  is in the document but was never selectable
  J  error paths          fatal   a wrong input must bring up an error state
                                  with new text, and `recover` must lead back
                                  to the screen where it can be fixed; warns
                                  when the text has none of the task's words.
                                  Stands down for flows without error_paths

The screens, how to reach them and what each must show live in a flow file
under flows/ (see flow.load_flow); the in-page JavaScript probes live in
probes.py.
"""
from .checks import (a_completion, b_display, c_dead_controls, d_contrast,
                     e_layout, f_language, g_state, h_undefined_class,
                     i_choices, j_errors)
from .context import AuditContext
from .flow import visit_keys

# 집계보다 앞서 도는 검사들. 순서가 곧 fatal/warning 목록과 metrics 키의
# 순서다 - 바꾸면 출력이 바뀐다. I 도 fatal 검사이므로 여기 들어 있어야 한다.
# 집계 뒤에 돌리면 fatal 목록에는 들어가고 숫자에는 빠진다.
CHECKS = (a_completion, b_display, c_dead_controls, d_contrast, e_layout,
          f_language, g_state, h_undefined_class, i_choices, j_errors)


def count_fatals(fatal):
    """fatal 목록 하나에서 집계 세 값을 낸다.

    여기서만 정의한다. 집계하는 곳이 두 곳이기 때문이다 - finalize_counts() 가
    검사 직후에 세고, stage.apply_stage() 가 단계 밖 결과를 걷어낸 뒤 다시
    센다. 두 곳이 각자 세면 규칙이 갈라지고, 걸러낸 리포트의 숫자가 그 리포트의
    목록과 맞지 않게 된다.

    파생(`derived_from`)은 한 번 멈춘 탓에 줄줄이 따라온 결함이다. 독립된 결함
    (`fatal_root`)과 나누지 않으면 일찍 멈춘 실행일수록 숫자가 부풀려져 run
    끼리 비교할 수 없다.
    """
    total = len(fatal)
    derived = len([f for f in fatal if f.get("derived_from")])
    return {"fatal_total": total, "fatal_derived": derived,
            "fatal_root": total - derived}


def finalize_counts(ctx):
    """중복 fatal 을 걷어내고 fatal 개수를 센다.

    흐름이 같은 화면을 여러 번 지나가면 같은 실패가 그 횟수만큼 기록된다.
    결함은 하나인데 숫자만 커지므로, 같은 (검사·화면·내용) 은 한 번만 센다.
    """
    seen, deduped, dups = set(), [], 0
    for f in ctx.fatal:
        k = (f.get("check"), f.get("screen"), f.get("detail"))
        if k in seen:
            dups += 1
            continue
        seen.add(k)
        deduped.append(f)
    ctx.fatal[:] = deduped
    m = ctx.metrics
    m["fatal_duplicates_removed"] = dups
    m.update(count_fatals(ctx.fatal))
    m["stopped_at"] = ctx.stopped_at
    m["js_error_details"] = ctx.rep.get("js_error_details") or []
    m["flow_notes"] = ctx.rep.get("notes") or []


def audit(orig, rep, orig_html, rep_html, flow):
    # A restructured build is not a repair of the original document: its screens
    # are different screens. Anything that compares screen-to-screen is only
    # meaningful when the two share a structure, so those checks stand down and
    # say so rather than reporting noise.
    derived = bool(flow.get("derived_from_original", True))
    # 걸음마다 하나씩, 같은 화면을 두 번 지나면 두 번째는 "review#2" 다
    # (flow.visit_keys 참고). 스냅샷의 screens 키도 같은 이름이다.
    want = visit_keys(flow["steps"])
    # A name match is not a screen match: both designs happen to contain a
    # "bank" and an "amount" that have nothing to do with each other. Only a
    # build derived from the original may be compared screen by name.
    shared = [n for n in want if n in orig["screens"] and n in rep["screens"]] \
        if derived else []
    ctx = AuditContext(orig=orig, rep=rep, orig_html=orig_html,
                       rep_html=rep_html, flow=flow, derived=derived,
                       want=want, shared=shared,
                       screen_of=dict(zip(want, (s["screen"]
                                                 for s in flow["steps"]))))
    ctx.metrics["flow"] = flow["name"]
    ctx.metrics["derived_from_original"] = derived
    ctx.metrics["screens_in_flow"] = want
    ctx.metrics["screens_comparable_to_original"] = shared

    # 페이지가 뜨지 않았으면 긁어 온 것이 없다. 나머지 검사는 전부 빈 입력을
    # 보게 되므로 돌리지 않고, 그 하나만 적어 바로 돌려준다.
    if rep["load_failed"]:
        ctx.fatal_("A", None, "page failed to load: " + rep["load_failed"])
        return {"passed": False, "fatal": ctx.fatal, "warning": ctx.warning,
                "metrics": ctx.metrics}

    for check in CHECKS:
        check.run(ctx)

    # 집계는 마지막이다. 모든 검사가 fatal 을 다 적은 뒤에 세고 중복을 걷어낸다.
    finalize_counts(ctx)

    ctx.metrics["checks_stood_down"] = ctx.skipped
    return {"passed": not ctx.fatal, "fatal": ctx.fatal,
            "warning": ctx.warning, "metrics": ctx.metrics}
