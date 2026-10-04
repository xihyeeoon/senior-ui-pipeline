r"""검사 I - 선택지 보존. fatal.

원본에서 "고를 수 있던" 값이 생성물 문서 어디에도 없으면 잡는다. 한 화면에 다
보일 필요는 없고 스크립트 안의 배열로 들고 있어도 되므로, 화면이 아니라 문서
전체에서 찾는다. 그래서 값은 파일에 있지만 사용자가 거기까지 갈 길이 없는
경우는 보지 못한다.

찾는 단위는 낱말이다. 글자가 들어 있는지로만 보면 짧은 값이 다른 글자 속에서
우연히 맞는다. 경계는 값의 글자 종류마다 다르다 (boundary() 참고).

흐름 파일이 "일부러 뺐다" 를 선언할 수 있다. 안전을 위해 뺀 선택지까지 누락으로
세면 고칠 수 없는 fatal 이 재생성 루프에 계속 남는다 (declared() 참고).
"""
import re


# 값이 "있다" 를 어떻게 볼 것인가.
#
# `v in html` 로 보면 짧은 값이 다른 글자 속에서 우연히 맞는다 - 'all' 이
# 'small' 안에서, '10000' 이 '110000' 안에서. 그러면 빌드에 없는 선택지가 남아
# 있는 것으로 읽힌다. 그래서 경계를 본다.
#
# 경계는 글자 종류마다 다르다. 같은 규칙을 모두에 쓰면 한쪽이 틀린다.
HANGUL = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ]")
LATIN = re.compile(r"[A-Za-z]")
DIGIT = re.compile(r"[0-9]")

# 한글: 앞쪽 경계만 본다. 뒤에는 말이 붙어 늘어나고, 늘어난 것도 같은 선택지다 -
# 원본의 "국민" 을 빌드가 "국민은행" 으로 쓰는 것은 그 은행을 뺀 것이 아니다.
HANGUL_RULE = r"(?<!\w)%s"
# 영문: 앞뒤 모두 낱말 경계. 'all' 이 'small' 안에서 맞으면 안 된다.
LATIN_RULE = r"(?<!\w)%s(?!\w)"
# 숫자: 앞뒤에 숫자가 붙으면 안 된다 - '10000' 이 '110000' 안에서 맞으면 안
# 된다. 한글 단위는 붙어도 된다 ("10000원" 은 같은 값이다). 영문 글자가 붙은
# 것은 숫자가 아닌 다른 토막이므로 막는다 - '#6B5B00' 의 00 은 색이지 숫자판의
# 00 키가 아니고, 막지 않으면 세 빌드에서 빠진 00 키가 그 색 안에서 맞는다.
DIGIT_RULE = r"(?<![0-9A-Za-z])%s(?![0-9A-Za-z])"


def boundary(value):
    """값의 글자 종류에 맞는 경계 규칙으로 찾을 정규식을 돌려준다.

    한글이 섞인 값은 한글 규칙을 쓴다 ("BNK투자증권" 도 뒤에 말이 붙을 수
    있다). 글자가 하나도 없는 값 - 기호뿐인 값 - 은 가장 좁은 낱말 경계로
    본다.
    """
    v = re.escape(value)
    if HANGUL.search(value):
        return HANGUL_RULE % v
    if LATIN.search(value):
        return LATIN_RULE % v
    if DIGIT.search(value):
        return DIGIT_RULE % v
    return LATIN_RULE % v


def present(value, html):
    """`value` 를 빌드 문서에서 하나의 값으로 찾을 수 있는가.

    경계 규칙은 boundary() 가 정한다. 속성값과 배열 원소는 어느 규칙으로든
    저절로 걸린다 - 따옴표는 낱말 글자도 숫자도 아니므로 `data-v="all"` 과
    `['70000']` 둘 다 경계가 맞는다. 화면에 보일 필요는 없다는 규칙은
    그대로다.
    """
    if not value:
        return False
    return bool(re.search(boundary(value), html))


def declared(flow):
    """흐름 파일이 "일부러 뺐다" 고 선언한 선택지. {action: (값 집합, 이유)}.

    모양은 이렇다.

        "choices_removed": {"quick": {"values": ["all"], "reason": "..."}}

    선언한 값만 빠진다. 선언하지 않은 값은 그대로 fatal 이다 - 선언이 검사를
    끄는 장치가 되어서는 안 된다.
    """
    spec = flow.get("choices_removed")
    out = {}
    if not isinstance(spec, dict):
        return out
    for action, d in spec.items():
        if not isinstance(d, dict):
            continue
        vals = d.get("values")
        out[action] = (set(vals if isinstance(vals, list) else []),
                       d.get("reason") or "")
    return out


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
    decl = declared(ctx.flow)
    missing_by_action, kept, by_design = {}, {}, {}
    for action, vals in orig_choices.items():
        if len(vals) < 2:
            continue
        gone = sorted(v for v in vals if not present(v, ctx.rep_html))
        # 남은 개수는 실제로 찾을 수 있는 값의 수다. 일부러 뺀 값은 "남아 있다"
        # 가 아니라 "뺐다" 이므로 여기에 넣지 않는다.
        kept[action] = len(vals) - len(gone)
        allowed, reason = decl.get(action, (set(), ""))
        on_purpose = [v for v in gone if v in allowed]
        missing = [v for v in gone if v not in allowed]
        if on_purpose:
            by_design[action] = {"values": on_purpose, "reason": reason}
        if missing:
            missing_by_action[action] = {"total": len(vals), "missing": missing}

    metrics["choice_groups_original"] = {a: len(v) for a, v in orig_choices.items()
                                         if len(v) >= 2}
    # 일부러 뺀 것은 fatal 로 세지 않는 대신 이유와 함께 남긴다. 조용히
    # 사라지면 "검사가 통과했다" 와 "검사를 내려놓았다" 를 구분할 수 없다.
    metrics["choice_values_removed_by_design"] = by_design
    for action, d in sorted(by_design.items()):
        ctx.skipped.append(
            "I/%s 선택지 %s - 흐름 파일이 일부러 뺀 것으로 선언했다: %s"
            % (action, ", ".join(d["values"]),
               d["reason"] or "이유가 적혀 있지 않다"))
    # 남은 개수도 내보낸다. 없는 값만 보면 "67개 중 58개 없음" 과 "3개 중 2개
    # 없음" 이 리포트에서 같은 모양이 된다 - 둘은 전혀 다른 상태다.
    metrics["choice_values_kept"] = kept
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
