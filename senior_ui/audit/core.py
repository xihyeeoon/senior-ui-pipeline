r"""Machine-readable audit of a restructured build for the transfer prototype.

두 스냅샷(원본 · 생성물)과 두 HTML 을 받아 검사 A~I 를 돌리고
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
                                  somewhere in the build

The screens, how to reach them and what each must show live in a flow file
under flows/ (see flow.load_flow); the in-page JavaScript probes live in
probes.py.
"""
from .checks import (a_completion, b_display, c_dead_controls, d_contrast,
                     e_layout, f_language, g_state, h_undefined_class,
                     i_choices)
from .context import AuditContext

# 집계보다 앞서 도는 검사들. 순서가 곧 fatal/warning 목록과 metrics 키의
# 순서다 - 바꾸면 출력이 바뀐다.
CHECKS = (a_completion, b_display, c_dead_controls, d_contrast, e_layout,
          f_language, g_state, h_undefined_class)


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
    m["fatal_total"] = len(ctx.fatal)
    m["fatal_derived"] = len([f for f in ctx.fatal if f.get("derived_from")])
    m["fatal_root"] = m["fatal_total"] - m["fatal_derived"]
    m["stopped_at"] = ctx.stopped_at
    m["js_error_details"] = ctx.rep.get("js_error_details") or []
    m["flow_notes"] = ctx.rep.get("notes") or []


def audit(orig, rep, orig_html, rep_html, flow):
    # A restructured build is not a repair of the original document: its screens
    # are different screens. Anything that compares screen-to-screen is only
    # meaningful when the two share a structure, so those checks stand down and
    # say so rather than reporting noise.
    derived = bool(flow.get("derived_from_original", True))
    want = [s["screen"] for s in flow["steps"]]
    # A name match is not a screen match: both designs happen to contain a
    # "bank" and an "amount" that have nothing to do with each other. Only a
    # build derived from the original may be compared screen by name.
    shared = [n for n in want if n in orig["screens"] and n in rep["screens"]] \
        if derived else []
    ctx = AuditContext(orig=orig, rep=rep, orig_html=orig_html,
                       rep_html=rep_html, flow=flow, derived=derived,
                       want=want, shared=shared)
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

    finalize_counts(ctx)
    # TODO(버그): I 의 fatal 이 집계에서 빠진다. 정리 후 별도 커밋에서 I 를 집계 앞으로 옮긴다.
    i_choices.run(ctx)

    ctx.metrics["checks_stood_down"] = ctx.skipped
    return {"passed": not ctx.fatal, "fatal": ctx.fatal,
            "warning": ctx.warning, "metrics": ctx.metrics}
