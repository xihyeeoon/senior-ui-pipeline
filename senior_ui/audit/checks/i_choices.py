r"""검사 I - 선택지 보존. fatal.

원본에서 "고를 수 있던" 값이 생성물 문서 어디에도 없으면 잡는다. 한 화면에 다
보일 필요는 없고 스크립트 안의 배열로 들고 있어도 되므로, 화면이 아니라 문서
전체에서 찾는다. 그래서 값은 파일에 있지만 사용자가 거기까지 갈 길이 없는
경우는 보지 못한다.
"""


def run(ctx):
    metrics, F = ctx.metrics, ctx.fatal_

    # 원본에서 "고를 수 있던 것" 이 생성물에서 사라지면, 과제는 통과해도
    # 그 선택지를 쓰려던 사람은 막힌다. 검사 과제가 쓰는 값 하나만 남기고
    # 나머지를 지우는 식의 최소 구현을 잡는다. 앱 종류와 무관한 규칙이다 -
    # 같은 data-action 을 공유하는 반복 요소면 무엇이든 선택지로 본다.
    orig_choices = {}
    for row in ctx.orig["screens"].values():
        for action, vals in (row.get("choices") or {}).items():
            orig_choices.setdefault(action, set()).update(vals)

    # 생성물에서는 "어디에든 있는가" 만 본다. 한 화면에 다 보일 필요는 없고,
    # 스크립트 안의 배열로 들고 있어도 된다. 그래서 문서 전체에서 찾는다.
    missing_by_action, kept = {}, {}
    for action, vals in orig_choices.items():
        if len(vals) < 2:
            continue
        gone = sorted(v for v in vals if v not in ctx.rep_html)
        kept[action] = len(vals) - len(gone)
        if gone:
            missing_by_action[action] = {"total": len(vals), "missing": gone}

    metrics["choice_groups_original"] = {a: len(v) for a, v in orig_choices.items()
                                         if len(v) >= 2}
    metrics["choice_values_missing"] = {a: d["missing"]
                                        for a, d in missing_by_action.items()}
    for action, d in sorted(missing_by_action.items()):
        sample = ", ".join(d["missing"][:5]) + (" …" if len(d["missing"]) > 5 else "")
        F("I", None,
          "원본의 %s 선택지 %d개 중 %d개가 생성물에 없다 (예: %s). 화면에 모두 "
          "보일 필요는 없지만 값 자체는 모두 접근 가능해야 한다. 검색이나 단계적 "
          "선택으로 찾을 수 있게 포함하라."
          % (action, d["total"], len(d["missing"]), sample),
          action=action, missing=d["missing"])
