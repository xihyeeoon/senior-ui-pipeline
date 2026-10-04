r"""검사 C - 죽은 조작부. fatal.

핸들러에 분기가 없는 data-action - 눌러도 아무 일도 없는 것 - 과, 원본에
있었는데 사라진 data-action 을 본다. 핸들러 사슬은 검사 대상 문서에서만 찾는다:
수리본이면 원본 스크립트를 복사해 온 것이고, 새 설계면 그 설계의 것이다.
원본에서 이미 죽어 있던 것은 새 결함으로 세지 않는다.

분기를 읽는 규칙은 handlers.py 에 있다 - 재구성 쪽의 흐름 명세 검사와 같은
함수를 쓴다.

빌드에 data-action 이 있는데 분기를 하나도 못 찾으면 그것 자체가 fatal 이다.
원본 목록으로 대신하면 이름이 겹치는 만큼 "처리된다" 고 읽혀, 처리기가 아예
없는 - 모든 조작부가 죽은 - 빌드가 가장 깨끗한 빌드로 통과한다. 조작부도 없고
처리기도 없는 문서는 죽을 것이 없으므로 아무 말도 하지 않는다.
"""
from ..context import union
from ..handlers import handled_actions


def run(ctx):
    metrics, F = ctx.metrics, ctx.fatal_

    handled = handled_actions(ctx.rep_html)
    metrics["handled_actions"] = len(handled)
    orig_actions = union(ctx.orig, "actions")
    rep_actions = union(ctx.rep, "actions")

    if handled:
        metrics["dead_controls_unverifiable"] = []
        pre_existing_dead = (orig_actions - handled) if ctx.derived else set()
        new_dead = sorted((rep_actions - handled) - pre_existing_dead)
        metrics["dead_controls_new"] = len(new_dead)
        metrics["dead_controls_pre_existing"] = sorted(pre_existing_dead)
        for a in new_dead:
            F("C", None, "data-action=%r has no branch in the handler - the "
              "control looks tappable and does nothing" % a, action=a)
    elif rep_actions:
        # 빌드 자신의 처리기를 하나도 못 찾았다. 조작부 하나하나를 죽었다고
        # 적지는 않는다 - 원인이 하나인데 fatal 이 조작부 수만큼 부풀려지고,
        # 그것은 이 레포가 집계에서 지키는 규칙(결함 하나 = fatal 하나)에
        # 어긋난다. 확인할 수 없었던 이름은 지표로 남긴다.
        F("C", None, "이 빌드에서 클릭 처리기의 분기를 하나도 찾지 못했다. "
                     "`a === '이름'` 도 `switch(a){case '이름':}` 도 없으므로 "
                     "data-action 이 붙은 조작부 %d개가 전부 눌러도 아무 일도 "
                     "하지 않는다 (%s). `const a = el.dataset.action;` 뒤에 그 "
                     "두 모양 중 하나로 분기를 써라."
          % (len(rep_actions), ", ".join(sorted(rep_actions)) or "없음"),
          actions=sorted(rep_actions))
        metrics["dead_controls_unverifiable"] = sorted(rep_actions)
        # 어느 조작부가 죽었는지는 가릴 기준이 없다. 0 으로 적으면 "죽은 것이
        # 없다" 가 되므로 null 로 둔다 - 리포트는 그것을 "–" 로 찍는다.
        metrics["dead_controls_new"] = None
        metrics["dead_controls_pre_existing"] = []
        ctx.skipped.append(
            "C/죽은 조작부 대조 - 빌드에 분기가 하나도 없어 어느 조작부가 "
            "죽었는지 가릴 기준이 없다. 그 사실 자체를 fatal 로 적었다.")
    else:
        # 처리기도 없고 data-action 도 없다. 죽을 조작부가 없으므로 이 검사는
        # 할 말이 없다 - 조작부가 사라진 것 자체는 검사 A 가 본다. 여기서
        # fatal 을 내면 조작부 없는 문서가 "죽은 조작부" 로 걸린다.
        metrics["dead_controls_unverifiable"] = []
        metrics["dead_controls_new"] = 0
        metrics["dead_controls_pre_existing"] = []
    removed = sorted(orig_actions - rep_actions) if ctx.derived else []
    for a in removed:
        F("C", None, "data-action=%r existed in the original and is gone" % a,
          action=a)
