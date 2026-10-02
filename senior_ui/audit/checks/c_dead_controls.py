r"""검사 C - 죽은 조작부. fatal.

핸들러에 분기가 없는 data-action - 눌러도 아무 일도 없는 것 - 과, 원본에
있었는데 사라진 data-action 을 본다. 핸들러 사슬은 검사 대상 문서에서 찾는다:
수리본이면 원본 스크립트를 복사해 온 것이고, 새 설계면 그 설계의 것이다.
원본에서 이미 죽어 있던 것은 새 결함으로 세지 않는다.
"""
import re

from ..context import union


def run(ctx):
    metrics, F = ctx.metrics, ctx.fatal_

    handled = set(re.findall(r"a\s*===\s*'([a-z-]+)'", ctx.rep_html)) \
        or set(re.findall(r"a\s*===\s*'([a-z-]+)'", ctx.orig_html))
    metrics["handled_actions"] = len(handled)
    orig_actions = union(ctx.orig, "actions")
    rep_actions = union(ctx.rep, "actions")
    pre_existing_dead = (orig_actions - handled) if ctx.derived else set()
    new_dead = sorted((rep_actions - handled) - pre_existing_dead)
    metrics["dead_controls_new"] = len(new_dead)
    metrics["dead_controls_pre_existing"] = sorted(pre_existing_dead)
    for a in new_dead:
        F("C", None, "data-action=%r has no branch in the handler - the control "
          "looks tappable and does nothing" % a, action=a)
    removed = sorted(orig_actions - rep_actions) if ctx.derived else []
    for a in removed:
        F("C", None, "data-action=%r existed in the original and is gone" % a,
          action=a)
