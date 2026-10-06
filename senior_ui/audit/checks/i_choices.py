r"""검사 I - 선택지 보존. fatal.

원본에서 "고를 수 있던" 값이 생성물에 없으면 잡는다. 한 화면에 다 보일 필요는
없으므로 화면 하나가 아니라 빌드 전체에서 찾는다. 보는 곳은 둘이다.

    원문   재설계 HTML 의 글자. **도구가 넣은 데이터 블록은 뺀다.**
    DOM    걸음마다 렌더링된 DOM 에서 모은 선택지 값 (drive 의 CHOICE_GROUPS)

데이터 블록을 빼는 이유가 이 검사의 핵심이다. 도구는 입력이 가진 선택지 데이터를
재설계 HTML 에 `<script id="preserved-data">` 로 넣어 준다 (senior_ui/preserved.py,
senior_ui/restructure/preserve.py). 그러면 모든 값이 원문에 생기므로, 빼지 않으면
모델이 하나도 그리지 않아도 통과한다 - 데이터를 지키려고 만든 장치가 그 데이터를
지켰는지 보는 검사를 꺼 버린다.

DOM 을 더 보는 이유는 그 반대다. 블록을 빼면 "블록을 참조해 그린" 빌드는 원문에
값이 한 글자도 없다 - 값은 런타임에 생긴다. 그 빌드를 떨어뜨리면 하라고 한 일을
한 답이 떨어진다.

찾는 단위는 낱말이다. 글자가 들어 있는지로만 보면 짧은 값이 다른 글자 속에서
우연히 맞는다. 경계는 값의 글자 종류마다 다르다 (boundary() 참고).

지표는 둘로 나뉜다. `choice_values_kept` 는 위 두 곳 어디에든 있는 값의 수이고
판정 기준이다. `choice_values_selectable` 는 그중 DOM 에서 실제로 고를 수 있던
값의 수다. 둘이 다르면 경고 하나를 남긴다 - fatal 이 아니다. "전체 보기" 뒤나
검색 결과로만 목록이 나오는 설계는 검사기가 그 버튼을 누르지 않으면 DOM 에
나타나지 않으므로, fatal 로 하면 정상 설계가 떨어진다. 판정은 느슨한 쪽으로
하고 차이는 사람이 보게 남긴다.

"전체 보기" 를 눌러야 목록이 만들어지는 설계는 흐름 명세의 `reveal` 에 그 조작을
적는다. drive 가 그 조작을 따로 걸으며 모은 값(`rep["revealed"]`)도 DOM 에서 고를
수 있던 값으로 센다. 펼친 뒤에도 값이 data-action 요소로 있어야 한다는 기준은
같다 - 같은 CHOICE_GROUPS 로 모은다.

흐름 파일이 "일부러 뺐다" 를 선언할 수 있다. 안전을 위해 뺀 선택지까지 누락으로
세면 고칠 수 없는 fatal 이 재생성 루프에 계속 남는다 (declared() 참고).
"""
import re

from senior_ui.preserved import strip_data_block


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


def dom_values(rep):
    """빌드를 걷는 동안 렌더링된 DOM 에서 모은 선택지 값. 한 덩어리 글로.

    probe(CHOICE_GROUPS)는 걸음마다 **문서 전체** 의 `[data-action]` 을 보므로,
    걸음들을 합치면 "선택 화면이 열린 단계" 의 목록이 그 안에 들어 있다. 켜지지
    않은 화면 안의 선택지도 들어온다 - 그래서 숨김·접힘은 괜찮다는 규칙이
    그대로 지켜진다. 반대로 클릭해야 비로소 만들어지는 목록은 그 클릭이 흐름에
    없으면 들어오지 않는다. 그것이 kept 와 selectable 이 갈리는 자리다.

    글로 이어 붙이는 이유는 경계 규칙을 원문과 똑같이 쓰기 위해서다 - 값끼리
    집합으로 맞추면 원본의 "국민" 과 빌드의 "국민은행" 이 다른 값이 된다.
    """
    seen = set()
    for row in (rep.get("screens") or {}).values():
        for vals in (row.get("choices") or {}).values():
            seen.update(v for v in (vals or []) if v)
    # 펼치기 조작(reveal)을 따로 걸으며 모은 것. 흐름 명세가 적은 조작만이다.
    for res in (rep.get("revealed") or {}).values():
        for vals in ((res or {}).get("choices") or {}).values():
            seen.update(v for v in (vals or []) if v)
    return "\n".join(sorted(seen))


def reveal_failures(rep):
    """펼치기 조작이 실패한 것. `{action: "단계: 내용"}`."""
    out = {}
    for action, res in (rep.get("revealed") or {}).items():
        err = (res or {}).get("error")
        if err:
            out[action] = "%s: %s" % (err.get("phase"), (err.get("detail") or "")[:200])
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
    # 스크립트 안의 배열로 들고 있어도 된다. 보는 곳은 둘이다 - 원문에서 도구가
    # 넣은 데이터 블록을 뺀 것과, 걷는 동안 렌더링된 DOM 에서 모은 선택지 값.
    # 블록을 빼는 이유와 DOM 을 더 보는 이유는 이 파일 머리말에 있다.
    text = strip_data_block(ctx.rep_html)
    dom = dom_values(ctx.rep)

    decl = declared(ctx.flow)
    missing_by_action, kept, selectable, unreachable, by_design = {}, {}, {}, {}, {}
    for action, vals in orig_choices.items():
        if len(vals) < 2:
            continue
        gone = sorted(v for v in vals
                      if not present(v, text) and not present(v, dom))
        # 남은 개수는 실제로 찾을 수 있는 값의 수다. 일부러 뺀 값은 "남아 있다"
        # 가 아니라 "뺐다" 이므로 여기에 넣지 않는다.
        kept[action] = len(vals) - len(gone)
        # 그중 DOM 에서 고를 수 있던 것. 판정에는 쓰지 않는다.
        selectable[action] = sum(1 for v in vals if present(v, dom))
        hidden = sorted(v for v in vals
                        if present(v, text) and not present(v, dom))
        if hidden:
            unreachable[action] = hidden
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
    # 판정과 따로 내보내는 숫자. kept 는 "문서 어디에든 있다" 이고 이것은 "걷는
    # 동안 DOM 에서 고를 수 있었다" 다. 둘을 한 숫자로 합치면 "숨겨 두었지만
    # 고를 수 있다" 와 "글자로만 있고 길이 없다" 가 구분되지 않는다.
    metrics["choice_values_selectable"] = selectable
    metrics["choice_values_missing"] = {a: d["missing"]
                                        for a, d in missing_by_action.items()}
    # 흐름 명세의 펼치기 조작과 그 결과. 없으면 키가 없다 (옛 흐름 그대로).
    revealed = ctx.rep.get("revealed") or {}
    if revealed:
        metrics["reveal"] = {a: {"at": (r or {}).get("at"),
                                 "values": sum(len(v) for v in ((r or {}).get("choices")
                                                                or {}).values()),
                                 "error": ((r or {}).get("error") or {}).get("phase")}
                             for a, r in revealed.items()}
    failed = reveal_failures(ctx.rep)
    # 차이는 경고다. fatal 로 하면 "전체 보기" 뒤나 검색 결과로만 목록을 내놓는
    # 설계가 떨어진다 - 검사기가 그 버튼을 누르지 않으면 DOM 에 나타나지 않고,
    # 그것은 설계의 결함이 아니라 흐름 명세가 그 길을 걷지 않은 것이다. 그래서
    # 판정은 느슨한 쪽으로 하고, 사람이 볼 줄 하나를 남긴다.
    for action, hidden in sorted(unreachable.items()):
        sample = ", ".join(hidden[:5]) + (" …" if len(hidden) > 5 else "")
        ctx.warn("I", None,
                 "원본의 %s 선택지 %d개 중 %d개는 생성물 문서 안에는 있지만 "
                 "검사기가 걷는 동안 DOM 에서는 고를 수 없었다 (예: %s). "
                 '"전체 보기" 뒤나 검색 결과로만 나오는 목록이면 정상이다 - '
                 "판정에는 넣지 않는다. 그 길을 걷게 하려면 흐름 명세의 reveal "
                 "에 펼치는 조작을 적어라."
                 % (action, len(orig_choices[action]), len(hidden), sample),
                 action=action, not_selectable=hidden)
    for action, d in sorted(missing_by_action.items()):
        sample = ", ".join(d["missing"][:5]) + (" …" if len(d["missing"]) > 5 else "")
        F("I", None,
          "원본의 %s 선택지 %d개 중 %d개가 생성물에 없다 (예: %s). 화면에 모두 "
          "보일 필요는 없지만 값 자체는 모두 접근 가능해야 한다. 검색이나 단계적 "
          "선택으로 찾을 수 있게 포함하라.%s"
          % (action, d["total"], len(d["missing"]), sample,
             "".join(" 흐름 명세의 reveal.%s 조작이 실패했다 (%s)." % (a, why)
                     for a, why in sorted(failed.items()))),
          action=action, missing=d["missing"])
