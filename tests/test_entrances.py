r"""과제 밖 입구 보존 (검사 K) - 연구자 결정 (나), 2026-10-06.

연구 원칙은 "보여 주는 방식은 자유, 사용자가 할 수 있는 일은 줄이지 않는다" 다.
예비 실행(20261006-215902)의 모델은 이체 홈의 다른 메뉴를 모두 지우고 "돈 보내기"
하나만 남겼다 - 그러면 C 는 기능을 빼서 이긴 것이 되어 A1 · A2 와의 비교가 공정하지
않다.

입구 목록은 과제 파일의 `entrances` 다 (더미앱 A1 의 OutOfScope 탭 대상, 연구자 확정).
판정 규칙 (연구자 결정 2026-10-07, 11-7b):

  - 원본의 data-action 이름(oos-*)을 그대로 가진 요소가, 걷는 동안(reveal 포함)
    누를 수 있게 보이면 그 입구가 있다 - 그려져 보이고 disabled 가 아니다
  - 같은 화면이 아니어도 된다. 접어 두었으면 펼치는 조작을 reveal 에 적는다
  - 원본을 걷는 동안 누를 수 있게 보인 입구만 센다. 빠지면 fatal
  - 글자 · aria-label 은 판정에 쓰지 않고 기록만 한다 (전에는 그것으로 맞췄는데,
    배너의 "금융자산" 이 하단 탭 "금융" 으로 읽히는 식으로 다른 요소에 맞았다 -
    outputs/11-7_entrance_collisions.txt)

손으로 만든 스냅샷으로 판정만 본다. 실제로 걷는 것은 아래 4절(-m browser)이다.
"""
import copy
import io
import json
import os
import re

import pytest

import _api
from test_audit_bugs import done_row, flow, row, snap

ROOT = _api.ROOT_DIR
T = _api.tasks_module


def items(task):
    return T.load_task(task)["entrances"]["items"]


def by_id(task):
    return {e["id"]: e for e in items(task)}


# ===================================================================== #
# 1. 목록 - 과제 파일에 있고, 원본이 그것을 누를 수 있는 요소로 갖는다
# ===================================================================== #
WANT = {
    # 이체: T1-T28 + R1 · R3 · R4 (R2 의 [이체] 는 이체 과제의 경로다)
    "transfer": ["T%d" % i for i in range(1, 29)] + ["R1", "R3", "R4"],
    # 공과금: B1-B30 + R2 · R3 · R4 (R1 의 ⌕ 는 공과금 과제의 경로 go-menu 다).
    # B23(AI에게 물어보기)은 뺐다 - 검색 결과 뒤에만 그려지고, 정답 경로는 검색어를
    # 넣은 그 걸음에서 바로 결과를 누르므로 원본을 걷는 동안 한 번도 보이지 않는다
    # (확정 규칙 5: 원본에서 걷기 · reveal 로 나타나지 않는 입구는 뺀다).
    "bill": ["B%d" % i for i in range(1, 31) if i != 23] + ["R2", "R3", "R4"],
}


@pytest.mark.parametrize("task", ["transfer", "bill"])
def test_the_task_file_lists_the_confirmed_entrances(task):
    group = T.load_task(task)["entrances"]
    assert "00834ca" in group["source"]
    ids = [e["id"] for e in group["items"]]
    assert sorted(ids) == sorted(WANT[task]) and len(ids) == len(set(ids))
    # 탭 대상 하나가 입구 하나다 - 이름(data-action)도 하나씩이다. 같은 이름을 나눠 쓰면
    # 한 화면의 것만 남겨도 다른 화면의 것까지 있는 것으로 센다 (공과금 메인 · 납부정보
    # 의 ⌂ 가 oos-home 하나였다).
    actions = [e["action"] for e in group["items"]]
    assert len(actions) == len(set(actions))
    for e in group["items"]:
        assert e["dummy"] and e["screen"] and e["label"], e
        # data-action 이름은 ASCII 다 - 분기를 읽는 규칙(audit/handlers.py)이 ASCII
        # 이름만 읽는다. 한글 이름이면 검사 C 와 형식 검사가 "분기 없음" 으로 잡는다.
        assert re.fullmatch(r"oos-[a-z0-9-]+", e["action"]), e


@pytest.mark.parametrize("task", ["transfer", "bill"])
def test_the_original_marks_every_entrance(task):
    """원본 HTML 보강: 입구마다 data-action 과 aria-label (더미 라벨)."""
    html = io.open(T.abs_path(T.load_task(task)["original"]), encoding="utf-8").read()
    for e in items(task):
        assert ('data-action="%s" aria-label="%s"' % (e["action"], e["label"])) in html, e


@pytest.mark.parametrize("task", ["transfer", "bill"])
def test_pressing_an_entrance_in_the_original_still_does_nothing(task):
    """눌러도 아무 일도 없다 (더미앱 A1 과 같다). 분기는 하나 두지만 몸통이 비어 있다 -
    없으면 원본 자신이 "처리되지 않는 data-action" 이 되어, 원본을 그대로 돌려주는
    mock(bill-identity)도 형식 검사와 검사 C 에서 떨어진다."""
    html = io.open(T.abs_path(T.load_task(task)["original"]), encoding="utf-8").read()
    handled = _api.handlers_module.handled_actions(html)
    actions = {e["action"] for e in items(task)}
    assert actions <= handled
    body = re.search(r"else if\((a==='oos-[^{]+)\)\{([^}]*)\}", html)
    assert body and "a==='" not in body.group(2) and "show(" not in body.group(2)


def test_the_probe_and_the_list_use_the_same_prefix():
    assert all(e["action"].startswith(_api.probes_module.ENTRANCE_PREFIX)
               for t in ("transfer", "bill") for e in items(t))


# ===================================================================== #
# 2. 판정 (손으로 만든 스냅샷)
# ===================================================================== #
def seen(task, drop=(), hidden=(), extra=None):
    """그 과제의 입구를 `{action: {visible, text, aria}}` 로. drop 은 없고, hidden 은
    문서에는 있지만 보이지 않는다. extra 는 그 밖의 oos-* 요소."""
    out = {}
    for e in items(task):
        if e["id"] in drop:
            continue
        out[e["action"]] = {"visible": e["id"] not in hidden, "text": e["label"],
                            "aria": e["label"]}
    out.update(extra or {})
    return out


def judge(rep_seen, orig_seen=None, revealed=None, task="transfer"):
    f = flow(["start", "done"], task=task)
    if task != "transfer":
        f.pop("truth")          # 손 스냅샷의 옛 이체 정답 대신 그 과제의 정답
    orig = snap({"start": row("start"), "done": done_row()},
                entrances_seen=seen(task) if orig_seen is None else orig_seen)
    rep = snap({"start": row("start"), "done": done_row()}, entrances_seen=rep_seen)
    if revealed is not None:
        rep["revealed"] = revealed
    return _api.audit(orig, rep, "<html></html>", "<html></html>", f)


def k_fatals(report):
    return [x for x in report["fatal"] if x.get("check") == "K"]


def missing(report):
    ks = k_fatals(report)
    return ks[0]["missing"] if ks else []


def test_a_build_without_the_entrances_fails():
    """예비 실행처럼 다른 메뉴를 모두 지운 빌드."""
    report = judge({})
    ks = k_fatals(report)
    assert report["passed"] is False and len(ks) == 1, report["fatal"]
    assert report["metrics"]["entrances_original"] == len(WANT["transfer"])
    assert report["metrics"]["entrances_kept"] == 0
    assert "메시지" in ks[0]["detail"] and "없애지 마라" in ks[0]["detail"]
    assert "oos-message" in ks[0]["detail"]


def test_a_build_that_keeps_every_entrance_passes():
    report = judge(seen("transfer"))
    assert k_fatals(report) == [] and report["metrics"]["entrances_kept"] == 31


def test_one_missing_entrance_is_named():
    report = judge(seen("transfer", drop=("T28",)))
    assert missing(report) == ["T28"]
    assert "공유" in k_fatals(report)[0]["detail"]


def test_an_entrance_that_is_never_visible_does_not_count():
    """문서에는 있지만 걷는 동안 한 번도 누를 수 있게 보이지 않았다 - 늘 숨어 있는
    요소는 사용자가 쓸 수 없다. 접어 두었으면 펼치는 조작을 reveal 에 적는다."""
    report = judge(seen("transfer", hidden=("T26", "T27")))
    assert missing(report) == ["T26", "T27"]
    assert report["metrics"]["entrances_hidden"] == ["T26", "T27"]
    assert "reveal" in k_fatals(report)[0]["detail"]


def test_an_entrance_shown_after_a_reveal_counts():
    """눌러야 보이는 입구 - 흐름 명세의 reveal 로 걸어 본 것도 센다."""
    report = judge(seen("transfer", hidden=[e["id"] for e in items("transfer")]),
                   revealed={"oos-message": {"at": "start", "choices": {},
                                             "entrances_seen": seen("transfer")}})
    assert k_fatals(report) == [], report["fatal"]


def test_the_text_and_label_are_recorded_not_judged():
    """글자 · aria-label 을 바꿔도 이름(data-action)만 원본 그대로면 있다. 그 글자는
    지표에 기록만 한다."""
    rep = seen("transfer")
    rep["oos-message"] = {"visible": True, "text": "알림함", "aria": ""}
    report = judge(rep)
    assert k_fatals(report) == []
    assert report["metrics"]["entrances_shown_as"]["T1"] == {"text": "알림함", "aria": ""}


def test_a_renamed_action_does_not_count_even_with_the_same_text():
    """글자가 같아도 data-action 이름이 다르면 그 입구가 아니다 (기술 계약: oos-* 는
    이름을 원본 그대로 둔다)."""
    rep = seen("transfer", drop=("T1",), extra={
        "oos-messages": {"visible": True, "text": "메시지", "aria": "메시지"}})
    assert missing(judge(rep)) == ["T1"]


# 겹침 사례 (outputs/11-7_entrance_collisions.txt) - 글자로 맞추던 판정에서는 다른 요소의
# 글자가 그 입구로 읽혀 통과했다. 이름으로 보는 판정에서는 떨어진다. 실제 원본에서 그
# 요소를 지운 빌드로도 본다 (4절, -m browser).
COLLISIONS = [
    # (과제, 지운 입구, 남는 같은 낱말 - 다른 요소의 글자)
    ("transfer", "T15", "금융자산"),        # 홈 탭 "금융" 을 지우고 배너만 남김
    ("transfer", "T7", "이벤트 바로가기"),  # 땡겨요 "이벤트" 를 지우고 배너만 남김
    ("transfer", "R4", "홈화면 설정"),      # 하단 탭 "홈" 을 지우고 하단 링크만 남김
    ("bill", "R2", "이체결과 조회"),        # 홈의 [이체] 를 지우고 메뉴 항목만 남김
    ("bill", "B18", "주식 현재가"),         # 홈 탭 "주식" 을 지우고 메뉴 항목만 남김
    ("bill", "B20", "설정/인증"),           # 메뉴의 ⚙ 를 지우고 메뉴 항목만 남김
    ("bill", "B25", "고객센터 홈"),         # 공과금 메인의 ⌂ 를 지우고 메뉴 항목만 남김
]
COLLISION_IDS = ["%s-%s" % (c[0], c[1]) for c in COLLISIONS]


@pytest.mark.parametrize("task,gone,word", COLLISIONS, ids=COLLISION_IDS)
def test_another_element_with_the_same_word_no_longer_passes(task, gone, word):
    rep = seen(task, drop=(gone,))
    # 같은 낱말은 다른 요소의 글자로 남아 있다 - 판정은 글자를 보지 않는다
    other = sorted(rep)[0]
    rep[other] = dict(rep[other], text=word)
    assert missing(judge(rep, task=task)) == [gone]


def test_an_entrance_the_original_does_not_show_is_not_counted():
    """원본에서 누를 수 있게 보이지 않은 입구는 세지 않는다 (검사 I 가 원본의 선택지만
    세는 것과 같다) - 원본이 다른 흐름 파일(fixture 페이지 등)이면 입구 목록은
    아무것도 요구하지 않는다."""
    report = judge({}, orig_seen={})
    assert k_fatals(report) == []
    assert report["metrics"]["entrances_original"] == 0
    assert len(report["metrics"]["entrances_not_in_original"]) == 31


def test_a_snapshot_from_before_the_collection_stands_down():
    f = flow(["start", "done"])
    s = snap({"start": row("start"), "done": done_row()})
    report = _api.audit(s, copy.deepcopy(s), "<html></html>", "<html></html>", f)
    assert k_fatals(report) == []
    assert any(x.startswith("K/") for x in report["metrics"]["checks_stood_down"])


def test_K_is_judged_at_the_wireframe_stage():
    """구조 문제다 - 시각 디테일이 아니다."""
    assert "K" in _api.audit_stage_module.STAGES["wireframe"]["checks"]
    assert "K" in _api.audit_stage_module.STAGES["styled"]["checks"]


def test_the_bill_task_counts_its_own_entrances():
    report = judge({}, task="bill", orig_seen=seen("bill"))
    assert report["metrics"]["entrances_original"] == len(WANT["bill"])
    assert len(k_fatals(report)) == 1


# ===================================================================== #
# 3. 프롬프트 - 그 수준으로만 알린다 (어디에 어떻게 두라는 말은 하지 않는다)
# ===================================================================== #
SENTENCE = ("원본의 다른 메뉴와 버튼도 사용자가 쓸 수 있는 기능이다. 배치 · 묶음 · 크기는 "
            "바꿔도 되지만 없애지 마라")
CONTRACT_LINE = ("원본의 과제 밖 입구(data-action 이 oos- 로 시작하는 요소)는 data-action "
                 "이름을 원본 그대로 둔다. 글자 · 배치 · 묶음은 바꿔도 된다.")


@pytest.mark.parametrize("task", ["transfer", "bill"])
def test_the_prompts_say_it_once_and_only_that(task):
    p = _api.prompt_module
    for t in (p.load_plan_template(task), p.load_template(task),
              p.load_refine_template(task)):
        flat = " ".join(t.split())
        assert flat.count(SENTENCE) == 1
        assert "entrances" not in flat
    # 기술 계약(생성 · 재시도 · 다듬기가 함께 쓴다)에 이름을 지키라는 한 줄
    for t in (p.load_template(task), p.load_refine_template(task)):
        flat = " ".join(t.split())
        assert flat.count(CONTRACT_LINE) == 1 and flat.count("oos-") == 1
    assert "oos-" not in p.load_plan_template(task)


# ===================================================================== #
# 4. 실제로 걷는다 (pytest -m browser)
# ===================================================================== #
def final_audit(summary):
    path = os.path.join(summary["run_dir"],
                        "attempt_%d.audit.json" % summary["attempts"][-1]["n"])
    return json.load(io.open(path, encoding="utf-8"))


@pytest.mark.browser
@pytest.mark.parametrize("mode,passed", [
    ("entrances-none", False),       # 입구를 다 지운 빌드 -> fatal
    ("entrances-reveal", True),      # [다른 메뉴] 를 눌러야 그리는 빌드 + reveal -> 통과
    ("entrances-folded", True),      # 접힌 <details> + 펼치는 조작을 reveal 에 -> 통과
    ("pass", True),                  # 첫 화면에 보이게 둔 블록 -> 통과
])
def test_a_mock_build_is_judged_on_its_entrances(server, mode, passed):
    import capture_baseline as C
    C.ensure_mock_input()
    summary, code = C.run_mock(["--mock", mode, "--attempts", "1", "--refine", "0"])
    report = final_audit(summary)
    m = report["metrics"]
    assert summary["passed"] is passed and code == (0 if passed else 1)
    assert m["entrances_original"] == 31 and m["entrances_not_in_original"] == []
    if passed:
        assert m["entrances_kept"] == 31 and k_fatals(report) == []
    else:
        assert [f["check"] for f in report["fatal"]] == ["K"]
        assert m["entrances_kept"] == 0 and len(m["entrances_missing"]) == 31


@pytest.mark.browser
@pytest.mark.parametrize("task", ["transfer", "bill"])
def test_the_original_shows_every_listed_entrance_on_its_walk(server, task):
    """확정 규칙 5 - 목록의 입구는 모두 원본을 걷는 동안 누를 수 있게 보인다."""
    import asyncio
    import capture_baseline as C
    t = T.load_task(task)
    snapshot = asyncio.run(_api.drive("%s/%s" % (C.BASE_URL, t["original"]),
                                      _api.load_flow(None, task=task)))
    shown = {a for a, v in snapshot["entrances_seen"].items() if v["visible"]}
    assert [e["id"] for e in items(task) if e["action"] not in shown] == []


ELEMENT = r'<(\w+)\b[^>]*\bdata-action="%s"[^>]*>.*?</\1>'


def without(html, action):
    """원본에서 그 data-action 을 가진 요소 하나를 통째로 지운다."""
    pat = re.compile(ELEMENT % re.escape(action), re.S)
    assert pat.search(html), action
    return pat.sub("", html, count=1)


@pytest.mark.browser
@pytest.mark.parametrize("task,gone,word", COLLISIONS, ids=COLLISION_IDS)
def test_an_original_without_that_entrance_fails_even_if_the_word_remains(
        server, task, gone, word):
    """실제 원본에서 그 입구 요소만 지운 빌드. 같은 낱말을 가진 다른 요소(배너 · 하단
    링크 · 메뉴 항목)는 그대로 있다 - 글자로 맞추던 판정에서는 통과했다."""
    import asyncio
    import capture_baseline as C
    t = T.load_task(task)
    orig_html = io.open(T.abs_path(t["original"]), encoding="utf-8").read()
    build = without(orig_html, by_id(task)[gone]["action"])
    if task == "transfer":
        assert word in build                     # 마크업에 있는 낱말
    rel = ".pytest-outputs/entrances_%s_%s.html" % (task, gone)
    os.makedirs(os.path.join(ROOT, ".pytest-outputs"), exist_ok=True)
    io.open(os.path.join(ROOT, rel), "w", encoding="utf-8").write(build)
    try:
        f = _api.load_flow(None, task=task)
        orig = asyncio.run(_api.drive("%s/%s" % (C.BASE_URL, t["original"]), f))
        nf = dict(f, derived_from_original=False)   # 화면 대 화면 비교(A · C)는 빼고 K 만
        rep = asyncio.run(_api.drive("%s/%s" % (C.BASE_URL, rel), nf,
                                     original_groups=C.original_groups(orig, nf)))
        report = _api.audit(orig, rep, orig_html, build, nf)
    finally:
        os.remove(os.path.join(ROOT, rel))
    assert missing(report) == [gone], report["fatal"]
    assert [x["check"] for x in report["fatal"]] == ["K"], report["fatal"]
