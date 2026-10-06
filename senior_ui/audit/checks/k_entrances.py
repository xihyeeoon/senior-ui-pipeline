r"""검사 K - 과제 밖 입구 보존. fatal.

과제 경로 위 화면에는 이 과제에는 쓰지 않는 메뉴 · 버튼이 있다 (이체 홈의 메시지 ·
쿠폰 · 하단 탭, 완료 화면의 추가이체 · 공유 …). 그것도 사용자가 쓸 수 있는 기능이다.
재설계가 그것을 지우면 과제는 더 쉬워 보이지만 그것은 기능을 빼서 이긴 것이고, 같은
기능을 다 가진 A1 · A2 와의 비교가 공정하지 않다. 연구 원칙은 "보여 주는 방식은
자유, 사용자가 할 수 있는 일은 줄이지 않는다" 다 (연구자 결정 (나), 2026-10-06 -
예비 실행 20261006-215902 의 모델이 이체 홈의 다른 메뉴를 모두 지우고 "돈 보내기"
하나만 남겼다).

무엇이 입구인지는 과제 파일의 `entrances` 가 정한다 - 더미앱 A1 에서 누를 수 있고
OutOfScope 로 처리되는 탭 대상, 연구자가 확정한 목록이다. 선택지 데이터(메뉴 항목 ·
은행 목록)는 검사 I 가 센다.

세는 방식은 검사 I 와 같다.

    어디서   걷는 동안(reveal 포함) DOM 에 있는 data-action 요소 - 문서 전체다. 같은
             화면이 아니어도, 접혀 있어도 된다. 눌러야 만들어지는 요소는 흐름 명세의
             reveal 로 걸어 모은 것도 센다 (drive.ACTION_TEXTS)
    무엇을   그 요소의 보이는 글자나 aria-label 이 입구의 [원본 글자, 더미 라벨] 중
             하나와 맞는가. 경계 규칙은 검사 I 의 present() 다
    무엇만   **원본을 걷는 동안 찾은 입구만** 센다 - 검사 I 가 원본의 선택지만 세는
             것과 같다. 원본에서 찾지 못한 입구는 지표에만 남긴다

원본에서 찾은 입구만 세는 이유는 둘이다. 목록이 원본과 어긋나면(원본을 바꿨는데 목록을
안 고쳤다) 고칠 수 없는 fatal 이 생기지 않고 지표로 드러난다. 그리고 원본이 이 과제의
원본이 아닌 검사(fixture 페이지)에서는 아무것도 요구하지 않는다.

입구를 눌렀을 때 무슨 일이 일어나는지는 보지 않는다 - 원본도 아무 일도 하지 않는다.
"""
from ... import tasks as T
from ..flow import task_of
from .i_choices import present


def entrances(flow):
    """그 흐름 과제의 입구 목록. 과제 파일에 없으면 빈 목록."""
    try:
        task = T.load_task(task_of(flow))
    except ValueError:
        return []
    group = task.get("entrances") or {}
    return [e for e in group.get("items") or [] if isinstance(e, dict) and e.get("id")]


def names(entrance):
    """그 입구로 인정하는 이름 - [원본 글자, 더미 라벨] 중 비지 않은 것."""
    return [n for n in (entrance.get("text"), entrance.get("label")) if n]


def shown(entrance):
    """사람과 모델이 읽는 이름. 원본 글자가 아이콘처럼 짧고 라벨과 다르면 괄호로 함께
    적는다 (메시지(☺)) - 긴 문장(배너 글)까지 붙이면 목록이 읽히지 않는다."""
    label, text = entrance.get("label"), entrance.get("text")
    return "%s(%s)" % (label, text) if text and text != label and len(text) <= 2 else label


def texts(snapshot):
    """그 스냅샷의 data-action 요소 이름 전부 - 정답 경로 + 펼치기. 한 덩어리 글로
    (검사 I 의 dom_values 와 같은 이유 - 경계 규칙을 원문과 똑같이 쓴다)."""
    seen = set(snapshot.get("action_texts") or [])
    for res in (snapshot.get("revealed") or {}).values():
        seen.update((res or {}).get("action_texts") or [])
    return "\n".join(sorted(seen))


def found(entrance, text):
    return any(present(n, text) for n in names(entrance))


def run(ctx):
    items = entrances(ctx.flow)
    if not items:
        return
    if "action_texts" not in ctx.orig or "action_texts" not in ctx.rep:
        ctx.skipped.append(
            "K/과제 밖 입구 - 스냅샷에 data-action 요소의 이름(action_texts)이 없다 "
            "(수집이 생기기 전의 스냅샷이거나 손으로 만든 것). 판정하지 않았다.")
        return
    orig_text, rep_text = texts(ctx.orig), texts(ctx.rep)
    in_orig = [e for e in items if found(e, orig_text)]
    missing = [e for e in in_orig if not found(e, rep_text)]
    not_in_orig = [e["id"] for e in items if e not in in_orig]

    m = ctx.metrics
    m["entrances_original"] = len(in_orig)
    m["entrances_kept"] = len(in_orig) - len(missing)
    m["entrances_missing"] = [e["id"] for e in missing]
    m["entrances_not_in_original"] = not_in_orig
    if not_in_orig and in_orig:
        # 원본이 이 과제의 원본인데 목록의 일부를 찾지 못했다 - 목록이나 원본이
        # 바뀌었다. 판정에서는 빼고 사람이 볼 줄을 남긴다.
        ctx.skipped.append("K/과제 밖 입구 - 원본에서 찾지 못한 입구 %d개는 세지 않았다: %s"
                           % (len(not_in_orig), ", ".join(not_in_orig)))
    if missing:
        ctx.fatal_(
            "K", None,
            "원본의 과제 밖 입구 %d개 중 %d개가 생성물에 없다: %s. 원본의 다른 메뉴와 버튼도 "
            "사용자가 쓸 수 있는 기능이다. 배치 · 묶음 · 크기는 바꿔도 되지만 없애지 마라. "
            "검사기는 걷는 동안 DOM 에 있는 data-action 요소의 글자나 aria-label 에서 이 "
            "이름을 찾는다. 눌러야 만들어지는 요소라면 그 조작을 흐름 명세의 reveal 에 적어라."
            % (len(in_orig), len(missing), ", ".join(shown(e) for e in missing)),
            missing=[e["id"] for e in missing])
