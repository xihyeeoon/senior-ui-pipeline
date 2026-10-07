r"""검사 I - 선택지 보존. fatal.

원본에서 "고를 수 있던" 값이 생성물에 없으면 잡는다. 한 화면에 다 보일 필요는
없으므로 화면 하나가 아니라 빌드 전체에서 찾는다. 보는 곳은 둘이다.

    원문   재설계 HTML 의 글자. **도구가 넣은 데이터 블록은 뺀다.**
    DOM    걸음마다 렌더링된 DOM 에서 모은 선택지 값 (drive 의 CHOICE_GROUPS)

무리는 원본이 정하고, 생성물에서는 놓인 모양과 상관없이 센다 (original_groups).

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

지표는 둘로 나뉜다. `choice_values_kept` 는 위 두 곳 어디에든 있는 값의 수다 -
"남아 있다". `choice_values_selectable` 는 그중 걷는 동안 어느 상태에서 **누를 수 있게
보인** 값의 수다 - "고를 수 있다" (11-8 2-3, 아래).

"전체 보기" 를 눌러야 목록이 만들어지거나 보이는 설계는 흐름 명세의 `reveal` 에 그
조작을 적는다. drive 가 그 조작을 따로 걸으며 모은 값(`rep["revealed"]`)도 센다. 펼친
뒤에도 값이 data-action 요소로 있어야 한다는 기준은 같다 - 같은 CHOICE_GROUPS 로 모은다.

펼친 뒤 실제로 보이는가 (11-8 2-3, 2026-10-07 20:38). 공과금 실행 20261007-201603-bill 의
전체메뉴에서 분야 칸이 열린 모양인데 속이 비어 보였다 - 그 안에는 닫힌 분류 제목뿐이고
항목은 분류를 한 번 더 눌러야 보였다. 이 검사는 메뉴 289개가 문서 안에 있는지만 세서
통과했다 ("숨김 · 접힘은 괜찮다"). 이제 원본 선택지 값마다, 정답 걸음이나 reveal 뒤 어느
상태에서 누를 수 있게 보였는지(그려져 있고 크기 > 0, display / visibility / opacity 로
숨지 않았고 disabled 가 아니다 - probes.CHOICE_SHOWN, 스냅샷의 `choices_shown`)를 센다.
문서 안에만 있고 어느 상태에서도 보이지 않은 값은 fatal 이다 (`not_selectable`).

다만 **원본을 걷는 동안 원본에서 보인 값만** 그렇게 센다 - 검사 K 가 원본을 걷는 동안
보인 입구만 세는 것과 같은 규칙이다 (연구자 결정 2026-10-07). 원본 흐름이 걷지 않는 상태
에만 있는 값(이체 원본의 증권사 29개 - 은행 시트의 [증권사] 탭 뒤)은 원본에서도 보이지
않았으므로 생성물에도 "보여야 한다" 를 요구하지 않고, 전처럼 남아 있기만 하면 되며 보이지
않으면 경고다. 그 값까지 요구하려면 원본 흐름에 그 탭을 여는 reveal 을 적는다.

`choices_shown` 이 없는 스냅샷(수집이 생기기 전의 것 · 손으로 만든 것)은 전처럼 DOM 에
있으면 고를 수 있다고 보고, 보이는지는 판정하지 않았다고 남긴다.

흐름 파일이 "일부러 뺐다" 를 선언할 수 있다. 안전을 위해 뺀 선택지까지 누락으로
세면 고칠 수 없는 fatal 이 재생성 루프에 계속 남는다 (declared() 참고).

과제는 "이 무리는 선택지가 아니다" 를 선언할 수 있다 (not_choices() 참고). 같은
data-action 의 형제 무리면 무엇이든 선택지로 세는 규칙은, 누르면 스크롤만 하는
표지판 · 탭(공과금의 menu-chip · menu-tab)도 선택지로 센다. 선언된 무리는 판정에서
빼고 지표 `choice_groups_not_choices` 에 이유와 함께 남긴다.
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


def original_choices(orig_snapshot):
    """원본을 걷는 동안 모은 선택지 값. `{action: {값들}}` - 화면마다 모은 것을 합친다."""
    out = {}
    for row in (orig_snapshot.get("screens") or {}).values():
        for action, vals in (row.get("choices") or {}).items():
            out.setdefault(action, set()).update(vals)
    return out


def original_groups(orig_snapshot, flow):
    """원본에서 선택지 무리였던 이름들 (정렬). 생성물을 걸을 때 drive(original_groups=…)
    로 넘긴다 - probes.CHOICE_GROUPS 는 그 이름의 요소를 형제 수와 상관없이 모두 센다.

    어떤 data-action 이 선택지 무리인지는 원본이 정한다. 재설계가 그 값들을 분류마다
    나눠 놓든 한곳에 모으든 그것은 보여 주는 방식이다. 공과금 예비 실행의 세 답은
    항목이 하나뿐인 분류 여섯 곳의 메뉴 항목을 그렸는데, 형제가 없어 세지 못했다.

    기준은 이 검사가 세는 무리와 같다 - 원본에서 값이 둘 이상이고, 과제가 선택지가
    아니라고 선언하지 않은 이름 (not_choices). 생성물은 보지 않는다 - "생성물 어딘가에서
    무리가 된 이름" 으로 하면 판정 기준이 생성물에 따라 달라진다."""
    skip = not_choices(flow)
    return sorted(a for a, vals in original_choices(orig_snapshot).items()
                  if len(vals) >= 2 and a not in skip)


def not_choices(flow):
    """과제가 선택지가 아니라고 선언한 무리. `{action: 이유}`.

    판정 입력(audit.inputs.judged_flow · flow.load_flow)이 과제 파일의 not_choices 를
    흐름에 붙인다 - 모델이 흐름 명세에 적은 것은 거기서 버려진다. 무리 전체를 뺀다는
    점이 declared() 와 다르다: 그쪽은 선택지인데 일부러 뺀 **값** 이고, 이쪽은 처음부터
    고르는 대상이 아닌 **무리** 다.
    """
    spec = flow.get("not_choices")
    if not isinstance(spec, dict):
        return {}
    return {a: str(why or "") for a, why in spec.items()}


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


def shown_values(snapshot):
    """걷는 동안 누를 수 있게 보인 선택지 값 (`choices_shown` - 걸음마다 + reveal 뒤). 한
    덩어리 글로 - dom_values 와 같은 이유 (경계 규칙을 똑같이 쓴다)."""
    seen = set()
    for row in (snapshot.get("screens") or {}).values():
        for vals in (row.get("choices_shown") or {}).values():
            seen.update(v for v in (vals or []) if v)
    for res in (snapshot.get("revealed") or {}).values():
        for vals in ((res or {}).get("choices_shown") or {}).values():
            seen.update(v for v in (vals or []) if v)
    return "\n".join(sorted(seen))


def measured(snapshot):
    """그 스냅샷에 보이는 값의 수집(`choices_shown`)이 있는가. 없으면 수집이 생기기 전의
    스냅샷이거나 손으로 만든 것이다."""
    return any("choices_shown" in row for row in (snapshot.get("screens") or {}).values())


def reveal_violations(rep):
    """펼치기 조작이 규칙(그 화면에 보이는 data-action 요소를 click, 같은 화면에
    머문다)을 어긴 것. `[(action, 내용)]`."""
    return [(action, v) for action, res in sorted((rep.get("revealed") or {}).items())
            for v in (res or {}).get("violations") or []]


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
    orig_choices = original_choices(ctx.orig)

    # 생성물에서는 "어디에든 있는가" 만 본다. 한 화면에 다 보일 필요는 없고,
    # 스크립트 안의 배열로 들고 있어도 된다. 보는 곳은 둘이다 - 원문에서 도구가
    # 넣은 데이터 블록을 뺀 것과, 걷는 동안 렌더링된 DOM 에서 모은 선택지 값.
    # 블록을 빼는 이유와 DOM 을 더 보는 이유는 이 파일 머리말에 있다.
    text = strip_data_block(ctx.rep_html)
    dom = dom_values(ctx.rep)
    # 걷는 동안 누를 수 있게 보인 값 (11-8 2-3). 원본 · 생성물 둘 다 수집이 있어야 본다 -
    # 없으면 전처럼 DOM 에 있으면 고를 수 있다고 보고 그 사실을 남긴다.
    seeing = measured(ctx.orig) and measured(ctx.rep)
    shown = shown_values(ctx.rep) if seeing else dom
    orig_shown = shown_values(ctx.orig) if seeing else None
    if not seeing:
        ctx.skipped.append(
            "I/보임 - 스냅샷에 보이는 값의 수집(choices_shown)이 없다 (수집이 생기기 전의 "
            "스냅샷이거나 손으로 만든 것). 문서(DOM)에 있으면 고를 수 있다고 보았다 - "
            "누를 수 있게 보였는지는 판정하지 않았다.")

    decl = declared(ctx.flow)
    skip = not_choices(ctx.flow)
    missing_by_action, kept, selectable, unreachable, by_design = {}, {}, {}, {}, {}
    not_choice, not_selectable, in_original = {}, {}, {}
    for action, vals in orig_choices.items():
        if len(vals) < 2:
            continue
        if action in skip:
            # 고르는 대상이 아니다 - 남았는지 세지 않는다. 원본에 있던 무리만 남긴다.
            not_choice[action] = {"values": len(vals), "reason": skip[action]}
            continue
        gone = sorted(v for v in vals
                      if not present(v, text) and not present(v, dom))
        # 남은 개수는 실제로 찾을 수 있는 값의 수다. 일부러 뺀 값은 "남아 있다"
        # 가 아니라 "뺐다" 이므로 여기에 넣지 않는다.
        kept[action] = len(vals) - len(gone)
        # 그중 걷는 동안 누를 수 있게 보인 것 (수집이 없는 옛 스냅샷은 DOM 에 있던 것)
        selectable[action] = sum(1 for v in vals if present(v, shown))
        allowed, reason = decl.get(action, (set(), ""))
        # 남아 있지만 한 번도 보이지 않은 값. 일부러 빼도 된다고 한 값은 숨겨도 된다.
        hidden = sorted(v for v in vals if v not in gone and v not in allowed
                        and not present(v, shown))
        if seeing:
            # 원본을 걷는 동안 원본에서 보인 값만 "보여야 한다" 로 센다 (머리말)
            required = {v for v in vals if present(v, orig_shown)}
            in_original[action] = len(required)
            must = [v for v in hidden if v in required]
            if must:
                not_selectable[action] = must
            hidden = [v for v in hidden if v not in required]
        if hidden:
            unreachable[action] = hidden
        on_purpose = [v for v in gone if v in allowed]
        missing = [v for v in gone if v not in allowed]
        if on_purpose:
            by_design[action] = {"values": on_purpose, "reason": reason}
        if missing:
            missing_by_action[action] = {"total": len(vals), "missing": missing}

    metrics["choice_groups_original"] = {a: len(v) for a, v in orig_choices.items()
                                         if len(v) >= 2 and a not in skip}
    # 선택지가 아니라고 선언한 무리 - 판정에서 뺐다는 사실을 이유와 함께 남긴다.
    # 사라지게 두면 "원본에 그 무리가 없었다" 와 "있었지만 세지 않았다" 를 가를 수 없다.
    metrics["choice_groups_not_choices"] = not_choice
    for action, d in sorted(not_choice.items()):
        ctx.skipped.append("I/%s 선택지 무리 %d개 - 과제가 선택지가 아니라고 선언했다: %s"
                           % (action, d["values"], d["reason"] or "이유가 적혀 있지 않다"))
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
    # kept 는 "문서 어디에든 있다" 이고 이것은 "걷는 동안 어느 상태에서 누를 수 있게
    # 보였다" 다 (11-8 2-3). 둘을 한 숫자로 합치면 "숨겨 두었지만 펼칠 수 있다" 와 "글자로만
    # 있고 길이 없다" 가 구분되지 않는다.
    metrics["choice_values_selectable"] = selectable
    if seeing:
        # 원본을 걷는 동안 원본에서 보인 값의 수 - "보여야 한다" 로 센 값들
        metrics["choice_values_shown_in_original"] = in_original
        # 그중 생성물에서 한 번도 누를 수 있게 보이지 않은 값 - fatal
        metrics["choice_values_not_selectable"] = not_selectable
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
    # 펼치기 규칙을 어긴 조작. 그 조작으로 모은 값은 이미 버려졌다 (drive 가 거기서
    # 멈춘다). fatal 로 남기고, 재구성 루프는 이 fatal 을 형식 문제로 센다.
    for action, why in reveal_violations(ctx.rep):
        F("I", None, "흐름 명세의 reveal.%s 가 펼치기 규칙을 어겼다: %s. 펼치기는 그 화면에 "
          "보이는 data-action 버튼을 click 하는 것만이고, 누른 뒤에도 같은 화면이어야 "
          "한다." % (action, why), action=action, reveal_violation=True)
    # 문서 안에만 있고 걷는 동안 어느 상태에서도 누를 수 있게 보이지 않은 값 - fatal
    # (11-8 2-3). 숨기거나 접어 둔 값은 펼치는 조작이 흐름 명세의 reveal 에 있어야
    # 검사기가 볼 수 있다. 걷기가 일찍 멈췄으면 그 뒤 화면의 값은 보지 못한 것이므로
    # 멈춘 탓으로 적는다 (derived_from - 검사 J 와 같다).
    for action, hidden in sorted(not_selectable.items()):
        sample = ", ".join(hidden[:5]) + (" …" if len(hidden) > 5 else "")
        extra = {"derived_from": ctx.stopped_at} if ctx.stopped_at else {}
        F("I", None,
          "원본의 %s 선택지 %d개 중 %d개가 생성물 문서 안에는 있지만 걷는 동안 어느 상태에서도 "
          "누를 수 있게 보이지 않았다 (예: %s). 원본에서는 걷는 동안 보이던 값이다. 숨기거나 "
          "접어 둔 값은 사용자가 고를 수 없다 - 눌러야 보이는 목록이면 그 조작을 흐름 명세의 "
          "reveal 에 적어라 (검사기는 정답 걸음과 reveal 뒤에 보이는 값만 센다).%s"
          % (action, len(orig_choices[action]), len(hidden), sample,
             " 걷기가 %s 에서 멈춰 그 뒤 화면을 보지 못했다." % ctx.stopped_at
             if ctx.stopped_at else ""),
          action=action, not_selectable=hidden, **extra)
    # 원본에서도 걷는 동안 보이지 않은 값(seeing), 또는 보이는 값의 수집이 없는 옛
    # 스냅샷의 차이는 경고다 - 판정에는 넣지 않고 사람이 볼 줄 하나를 남긴다.
    for action, hidden in sorted(unreachable.items()):
        sample = ", ".join(hidden[:5]) + (" …" if len(hidden) > 5 else "")
        why = ("원본도 걷는 동안 보이지 않은 값이라 판정에는 넣지 않는다 - 원본 흐름이 그 값이 "
               "보이는 상태를 걷지 않는다." if seeing else
               '"전체 보기" 뒤나 검색 결과로만 나오는 목록이면 정상이다 - 판정에는 넣지 '
               "않는다. 그 길을 걷게 하려면 흐름 명세의 reveal 에 펼치는 조작을 적어라.")
        ctx.warn("I", None,
                 "원본의 %s 선택지 %d개 중 %d개는 생성물 문서 안에는 있지만 "
                 "검사기가 걷는 동안 %s (예: %s). %s"
                 % (action, len(orig_choices[action]), len(hidden),
                    "누를 수 있게 보이지 않았다" if seeing else "DOM 에서는 고를 수 없었다",
                    sample, why),
                 action=action, not_selectable=hidden)
    for action, d in sorted(missing_by_action.items()):
        sample = ", ".join(d["missing"][:5]) + (" …" if len(d["missing"]) > 5 else "")
        F("I", None,
          "원본의 %s 선택지 %d개 중 %d개가 생성물에 없다 (예: %s). 화면에 모두 "
          "보일 필요는 없지만 값 자체는 모두 접근 가능해야 한다. 모든 값을 고를 수 "
          "있게 포함하라.%s"
          % (action, d["total"], len(d["missing"]), sample,
             "".join(" 흐름 명세의 reveal.%s 조작이 실패했다 (%s)." % (a, why)
                     for a, why in sorted(failed.items()))),
          action=action, missing=d["missing"])
