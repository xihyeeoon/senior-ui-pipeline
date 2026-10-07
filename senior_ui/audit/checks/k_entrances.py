r"""검사 K - 과제 밖 입구 보존. fatal.

과제 경로 위 화면에는 이 과제에는 쓰지 않는 메뉴 · 버튼이 있다 (이체 홈의 메시지 ·
쿠폰 · 하단 탭, 완료 화면의 추가이체 · 공유 …). 그것도 사용자가 쓸 수 있는 기능이다.
재설계가 그것을 지우면 과제는 더 쉬워 보이지만 그것은 기능을 빼서 이긴 것이고, 같은
기능을 다 가진 A1 · A2 와의 비교가 공정하지 않다. 연구 원칙은 "보여 주는 방식은
자유, 사용자가 할 수 있는 일은 줄이지 않는다" 다 (연구자 결정 (나), 2026-10-06 -
예비 실행 20261006-215902 의 모델이 이체 홈의 다른 메뉴를 모두 지우고 "돈 보내기"
하나만 남겼다).

무엇이 입구인지는 과제 파일의 `entrances` 가 정한다 - 더미앱 A1 에서 누를 수 있고
OutOfScope 로 처리되는 탭 대상, 연구자가 확정한 목록이다. 원본 HTML 의 그 요소에는
`data-action="oos-…"` 가 붙어 있다. 선택지 데이터(메뉴 항목 · 은행 목록)는 검사 I 가 센다.

판정 (연구자 결정 2026-10-07):

    이름     원본의 data-action 이름(oos-*)을 그대로 가진 요소가 빌드에 있다 (기술
             계약이 이름을 원본 그대로 두라고 한다)
    보임     그 요소가 걷는 동안 - 정답 경로의 어느 걸음에서든, 흐름 명세의 reveal 로
             펼친 뒤에든 - 누를 수 있게 보인다 (그려져 있고 disabled 가 아니다. 자신이나
             조상이 숨기지 않았다 - 닫힌 <details> 안은 보이지 않는다, probes.PRESSABLE). 같은
             화면이 아니어도 된다. 늘 숨어 있는 요소는 사용자가 쓸 수 없다
    무엇만   원본을 걷는 동안 누를 수 있게 보인 입구만 센다 - 검사 I 가 원본의 선택지만
             세는 것과 같다. 원본에서 보이지 않은 입구는 지표에만 남긴다

글자 · aria-label 은 판정에 쓰지 않고 기록만 한다 (`entrances_shown_as`). 전에는 글자로
맞췄는데, 다른 요소의 글자가 그 입구로 읽혔다 - 배너의 "금융자산" 이 하단 탭 "금융" 으로,
메뉴 항목 "이체결과 조회" 가 홈의 [이체] 로 (outputs/11-7_entrance_collisions.txt).

입구를 눌렀을 때 무슨 일이 일어나는지는 보지 않는다 - 원본도 아무 일도 하지 않는다.

입구까지의 거리 (11-8, 기록만 - 판정 · 고르기 문지기에 쓰지 않는다).
남아 있는 것과 찾을 수 있는 것은 다르다 (Findlater, McGrenere 2007).
그래서 입구마다 원본과 생성물에서 각각 처음 누를 수 있게 보인 방문, 그 입구를 보려고 누른
펼치기(reveal) 횟수, 그 화면 맨 위에서 입구가 창 안에 들어오기까지의 스크롤 거리를 지표
`entrance_distance` 로 남긴다 (distance()).
위의 판정이 걷는 걸음과 reveal 에서 잰 것이다 - 새 걷기는 없다. 기준선 · 합격선은 정하지
않는다 - 정하면 그것이 또 규칙이 된다.
"""
from ... import tasks as T
from ..flow import task_of


def entrances(flow):
    """그 흐름 과제의 입구 목록. 과제 파일에 없으면 빈 목록."""
    try:
        task = T.load_task(task_of(flow))
    except ValueError:
        return []
    group = task.get("entrances") or {}
    return [e for e in group.get("items") or [] if isinstance(e, dict) and e.get("id")]


def seen(snapshot):
    """그 스냅샷의 입구 상태 `{action: {visible, text, aria}}` - 정답 경로 + 펼치기.
    한 번이라도 보였으면 보인 것이다 (drive.merge_entrances 와 같은 규칙)."""
    out = {}
    rows = [snapshot.get("entrances_seen") or {}] + [
        (res or {}).get("entrances_seen") or {}
        for res in (snapshot.get("revealed") or {}).values()]
    for got in rows:
        for action, row in got.items():
            old = out.get(action)
            if old is None or (row.get("visible") and not old.get("visible")):
                out[action] = row
    return out


def shown(state, action):
    return bool((state.get(action) or {}).get("visible"))


def first_seen(snapshot, action, visits=()):
    """그 입구가 처음 누를 수 있게 보인 자리 `{visit, reveal, scroll_px}` (+ 펼치기로 보였으면
    `via` = 그 reveal 의 이름). 한 번도 보이지 않았으면 None. 기록만 한다.

    정답 걸음에서 보였으면 그것이다 - 바로 보이므로 펼치기는 0 이고, 방문은 처음 보인
    걸음이다 (drive.merge_entrances 가 처음 것을 남긴다). 정답 걸음에서는 보이지 않고
    펼치기 뒤에만 보였으면, 누른 횟수가 가장 적은 reveal 의 것이다 (같으면 흐름에서 앞선
    방문, 그다음 이름순). 수집이 이 칸들을 남기기 전의 스냅샷이면 칸은 null 이다."""
    main = (snapshot.get("entrances_seen") or {}).get(action) or {}
    if main.get("visible"):
        return {"visit": main.get("visit"), "reveal": 0, "scroll_px": main.get("scroll_px")}
    order = list(visits)
    best = None
    for key, res in sorted((snapshot.get("revealed") or {}).items()):
        got = ((res or {}).get("entrances_seen") or {}).get(action) or {}
        if not got.get("visible"):
            continue
        visit = got.get("visit") or (res or {}).get("at")
        clicks = got.get("reveal")
        rank = (clicks if isinstance(clicks, int) else float("inf"),
                order.index(visit) if visit in order else len(order), key)
        if best is None or rank < best[0]:
            best = (rank, {"visit": visit, "reveal": clicks, "via": key,
                           "scroll_px": got.get("scroll_px")})
    return best[1] if best else None


def distance(items, orig, rep, visits=()):
    """입구마다 원본과 생성물에서 처음 보인 자리 (first_seen), 과제 파일의 순서대로."""
    return [{"id": e["id"], "label": e.get("label"), "action": e["action"],
             "original": first_seen(orig, e["action"]),
             "build": first_seen(rep, e["action"], visits)}
            for e in items]


def run(ctx):
    items = entrances(ctx.flow)
    if not items:
        return
    if "entrances_seen" not in ctx.orig or "entrances_seen" not in ctx.rep:
        ctx.skipped.append(
            "K/과제 밖 입구 - 스냅샷에 입구 수집(entrances_seen)이 없다 (수집이 생기기 "
            "전의 스냅샷이거나 손으로 만든 것). 판정하지 않았다.")
        return
    orig, rep = seen(ctx.orig), seen(ctx.rep)
    in_orig = [e for e in items if shown(orig, e["action"])]
    missing = [e for e in in_orig if not shown(rep, e["action"])]
    hidden = [e["id"] for e in missing if e["action"] in rep]
    not_in_orig = [e["id"] for e in items if e not in in_orig]

    m = ctx.metrics
    m["entrances_original"] = len(in_orig)
    m["entrances_kept"] = len(in_orig) - len(missing)
    m["entrances_missing"] = [e["id"] for e in missing]
    # 이름은 있지만 걷는 동안 한 번도 누를 수 있게 보이지 않은 것 (missing 의 일부)
    m["entrances_hidden"] = hidden
    m["entrances_not_in_original"] = not_in_orig
    # 기록만 한다 - 남은 입구가 빌드에서 어떤 글자 · aria-label 로 보였나
    m["entrances_shown_as"] = {e["id"]: {"text": rep[e["action"]].get("text") or "",
                                         "aria": rep[e["action"]].get("aria") or ""}
                               for e in in_orig if e not in missing}
    # 기록만 한다 - 처음 보인 방문 · 펼치기 횟수 · 스크롤 거리, 원본과 나란히 (distance())
    m["entrance_distance"] = distance(items, ctx.orig, ctx.rep, ctx.want)
    if not_in_orig and in_orig:
        # 원본이 이 과제의 원본인데 목록의 일부가 보이지 않았다 - 목록이나 원본이
        # 바뀌었다. 판정에서는 빼고 사람이 볼 줄을 남긴다.
        ctx.skipped.append("K/과제 밖 입구 - 원본을 걷는 동안 보이지 않은 입구 %d개는 세지 "
                           "않았다: %s" % (len(not_in_orig), ", ".join(not_in_orig)))
    if missing:
        ctx.fatal_(
            "K", None,
            "원본의 과제 밖 입구 %d개 중 %d개가 생성물에서 누를 수 있게 보이지 않는다: %s.%s "
            "원본의 다른 메뉴와 버튼도 사용자가 쓸 수 있는 기능이다. 배치 · 묶음 · 크기는 "
            "바꿔도 되지만 없애지 마라. 검사기는 원본의 data-action 이름(oos-…)을 그대로 가진 "
            "요소가 걷는 동안 누를 수 있게 보이는지 본다. 눌러야 보이는 요소라면 그 조작을 "
            "흐름 명세의 reveal 에 적어라."
            % (len(in_orig), len(missing),
               ", ".join("%s(%s)" % (e["label"], e["action"]) for e in missing),
               " 그중 %s 는 문서에는 있지만 한 번도 보이지 않았다." % ", ".join(
                   by["action"] for by in missing if by["id"] in hidden) if hidden else ""),
            missing=[e["id"] for e in missing])
