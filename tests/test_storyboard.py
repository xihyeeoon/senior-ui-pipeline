r"""화면설계서 (python -m senior_ui.storyboard, 11-12).

설계서는 검사를 통과한 HTML 에서 뽑는다. "누르면 어디로 가는가" 는 도구가 실제로 눌러
본 것만 적고, 모델은 영역 묶기와 설명 문장만 쓴다. 실행 폴더는 읽기만 한다.

  1. 항목 - 보이는 요소를 번호 매긴 항목으로, 선택지 무리는 하나로 (대표 하나만 누른다)
  2. 누르기 결과 - 다른 화면으로 감 / 같은 화면에서 바뀜 / 아무 일 없음 (순수 함수)
  3. 영역 묶기 - 검사 · 한 번 다시 묻기 · "기타" · mock 의 정해진 답 · 키를 읽지 않는 mock ·
     모델 호출 기록 (가짜 호출)
  4. 그리기 - 단 나누기 · 동작 문구 · storyboard.json 만으로 다시 그리기
  5. 실행 폴더 - 통과하지 못한 실행은 만들지 않는다 (종료 2) · 원본 지문
  6. (-m browser) 작은 HTML 로 동작 확인 - 다른 화면 · 같은 화면 · 아무 일 없음 · 무리 ·
     꺼짐 · 과제 밖 입구 · 가려진 요소 · 늦게 넘어가는 화면 · 스크롤 화면 한 장 · 오류 · 펼침
  7. (-m browser) 끝까지 - mock pass 실행 · 저장된 이체 답(refine_102041) · 저장된 공과금
     답(bill_sol 시도 4)의 storyboard.json 을 기준값(baseline/storyboard/)과 견준다. 그림은
     기준값으로 두지 않는다. 실행 폴더의 원래 파일은 바이트까지 그대로여야 한다.
"""
import asyncio
import hashlib
import io
import json
import os
import re
import shutil

import pytest

import _api
import capture_baseline as C

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "storyboard")
B = _api.storyboard_build
W = _api.storyboard_walk
R = _api.storyboard_regions
RD = _api.storyboard_render
RUN = _api.storyboard_run
M = _api.model_module


def raw(index, action, box, value=None, text=None, disabled=False):
    return {"index": index, "action": action, "id": None, "tag": "button",
            "value": value if value is not None else (text or action),
            "text": text or action, "aria": None, "disabled": disabled, "box": list(box)}


# --------------------------------------------------------------------- #
# 1. 항목
# --------------------------------------------------------------------- #
def test_items_are_numbered_top_to_bottom_then_left_to_right():
    items = B.itemize([raw(0, "b", (200, 100, 50, 30)), raw(1, "a", (10, 102, 50, 30)),
                       raw(2, "c", (10, 10, 50, 30))], groups=[])
    assert [(it["no"], it["action"]) for it in items] == [("e1", "c"), ("e2", "a"),
                                                          ("e3", "b")]


def test_a_choice_group_becomes_one_item_with_the_first_member_in_reading_order():
    """검사 I 가 세는 무리(원본의 이름)는 둘 이상 보이면 하나로 묶는다. 대표는 읽는
    순서의 첫 것 - 값 순서로 고르면 금액 숫자판의 대표가 '0' 이 되어 빈 칸에서는 눌러도
    아무 일이 없다 (11-12 의 첫 시험에서 그랬다)."""
    keys = [raw(10 + i, "num", (10 + 60 * (i % 3), 300 + 60 * (i // 3), 50, 50), value=v)
            for i, v in enumerate(["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"])]
    items = B.itemize(keys + [raw(1, "next", (10, 600, 300, 50))], groups=["num"])
    assert [it["kind"] for it in items] == ["group", "element"]
    g = items[0]
    assert g["group"] == {"count": 10, "values": sorted("1234567890")}
    assert g["value"] == "1" and g["_index"] == 10
    assert g["box"] == [10, 300, 170, 230]
    assert B.target_of(g) == {"index": 10, "action": "num", "value": "1", "by_value": True}


def test_a_lone_member_of_a_group_is_an_ordinary_element():
    items = B.itemize([raw(3, "pick-bank", (0, 0, 10, 10), value="신한")], groups=["pick-bank"])
    assert items[0]["kind"] == "element"
    assert B.target_of(items[0])["by_value"] is False


def test_out_of_scope_entrances_are_marked():
    items = B.itemize([raw(0, "oos-menu", (0, 0, 10, 10)), raw(1, "go", (0, 50, 10, 10))], [])
    assert [it["entrance"] for it in items] == [True, False]


# --------------------------------------------------------------------- #
# 2. 누르기 결과
# --------------------------------------------------------------------- #
def seen(screen="a", lines=(), values=(), sig=1, scroll=(), doc=0):
    return {"dom_screen": screen, "landed_on": screen, "lines": list(lines),
            "values": list(values), "sig": sig, "scroll": list(scroll), "doc_scroll": doc}


def test_change_another_screen():
    assert W.describe_change(seen("a"), seen("b"), []) == {"kind": "screen", "to": "b"}


def test_change_same_screen_says_what_appeared():
    r = W.describe_change(seen(lines=["제목"]), seen(lines=["제목", "메모가 보입니다", "둘째"]), [])
    assert r == {"kind": "same", "detail": "새로 보임: '메모가 보입니다' 외 1줄"}


def test_change_nothing():
    assert W.describe_change(seen(lines=["x"]), seen(lines=["x"]), []) == {"kind": "none"}


@pytest.mark.parametrize("before,after,dialogs,detail", [
    (seen(lines=["a", "b"]), seen(lines=["a"]), [], "사라짐: 'b'"),
    (seen(values=[""]), seen(values=["12"]), [], "입력 칸 값이 바뀜: '12'"),
    (seen(), seen(), [{"message": "확인하세요"}], "알림창 '확인하세요'"),
    (seen(lines=["1", "2"]), seen(lines=["2", "1"]), [], "보이는 글의 순서가 바뀜"),
    (seen(sig=1), seen(sig=2), [], "표시 상태가 바뀜 (보이는 글은 그대로)"),
    (seen(scroll=[]), seen(scroll=[120]), [], "스크롤 위치가 바뀜"),
])
def test_change_same_screen_kinds(before, after, dialogs, detail):
    assert W.describe_change(before, after, dialogs) == {"kind": "same", "detail": detail}


# --------------------------------------------------------------------- #
# 3. 영역 묶기
# --------------------------------------------------------------------- #
def sheet(sid="scr-a", n=3, gap=False):
    items = []
    for i in range(n):
        y = 10 + i * 40 + (200 if gap and i == n - 1 else 0)
        items.append({"no": "e%d" % (i + 1), "kind": "element", "action": "x%d" % i,
                      "text": "버튼 %d" % i, "aria": None, "value": "", "box": [0, y, 100, 30],
                      "entrance": False, "result": {"kind": "none"}})
    return {"id": sid, "items": items, "purpose": "목적", "condition": None,
            "marked": "shots/%s.marked.png" % sid}


PNG = os.path.join(ROOT, "results", "shots", "run4", "audit_start.png")


def shots(tmp_path, *sheets):
    """번호 그림 자리에 진짜 PNG 를 둔다 (그림 토큰 어림이 PNG 머리를 읽는다)."""
    (tmp_path / "shots").mkdir(exist_ok=True)
    for sh in sheets:
        shutil.copy2(PNG, str(tmp_path / sh["marked"]))
    return list(sheets)


def test_check_accepts_an_answer_that_puts_every_element_in_exactly_one_region():
    sh = [sheet()]
    ans = {"sheets": [{"id": "scr-a", "regions": [
        {"no": 1, "name": "위", "elements": ["e1", "e2"], "description": "d"},
        {"no": 2, "name": "아래", "elements": ["e3"], "description": "d"}]}]}
    assert R.check(ans, sh) == []


@pytest.mark.parametrize("regions,needle", [
    ([{"no": 1, "name": "a", "elements": ["e1", "e2"]}], "e3 가 어느 영역에도 없다"),
    ([{"no": 1, "name": "a", "elements": ["e1", "e2", "e3", "e9"]}], "없는 요소 e9"),
    ([{"no": 1, "name": "a", "elements": ["e1", "e2", "e3"]},
      {"no": 2, "name": "b", "elements": ["e3"]}], "e3 가 영역 1 와 2 에 둘 다"),
    ([{"no": 1, "name": "", "elements": ["e1", "e2", "e3"]}], "이름이 없다"),
])
def test_check_finds_what_is_wrong(regions, needle):
    problems = R.check({"sheets": [{"id": "scr-a", "regions": regions}]}, [sheet()])
    assert any(needle in p for p in problems), problems


def test_check_finds_missing_and_unknown_sheets():
    problems = R.check({"sheets": [{"id": "scr-z", "regions": []}]}, [sheet()])
    assert "없는 장 scr-z 를 적었다" in problems and "scr-a 장이 없다" in problems
    assert R.check(None, [sheet()]) == ["답에서 JSON 을 읽지 못했다"]


def test_settle_puts_the_leftovers_into_other_and_records_it():
    """어긋난 답의 맞는 부분은 쓰고, 남은 요소는 "기타" 로 (출처: 도구 묶음)."""
    ans = {"sheets": [{"id": "scr-a", "regions": [
        {"no": 1, "name": "위", "elements": ["e1", "e999", "e1"], "description": "d"}]}]}
    out, fb = R.settle_regions(ans, [sheet()], "model")
    regs = out["scr-a"]
    assert [(r["name"], r["elements"], r["source"]) for r in regs] == [
        ("위", ["e1"], "model"), (R.OTHER_NAME, ["e2", "e3"], "tool_group")]
    assert fb == {"scr-a": {"other": ["e2", "e3"], "dropped": ["e999", "e1"]}}
    assert regs[1]["box"] == [0, 50, 100, 70]


def test_mock_answer_splits_on_vertical_gaps():
    ans = R.mock_answer([sheet(n=4, gap=True)])
    regs = ans["sheets"][0]["regions"]
    assert [r["elements"] for r in regs] == [["e1", "e2", "e3"], ["e4"]]
    assert R.check(ans, [sheet(n=4, gap=True)]) == []


def test_group_mock_writes_the_record_and_the_answer(tmp_path):
    shs = shots(tmp_path, sheet(), sheet("scr-b", n=0))
    rec = R.group(shs, mock="regions", out_dir=str(tmp_path), log=lambda m: None)
    assert rec["mock"] == "regions" and rec["model"] is None and rec["cost_usd"] == 0.0
    assert [c["phase"] for c in rec["calls"]] == ["first"]
    assert rec["fallback"] == {} and rec["problems"] == []
    assert shs[0]["regions"][0]["source"] == "mock" and shs[1]["regions"] == []
    assert (tmp_path / R.PROMPT_FILE).exists() and (tmp_path / R.RESPONSE_FILE).exists()


def test_group_asks_once_more_when_the_answer_is_wrong(tmp_path):
    shs = shots(tmp_path, sheet())
    rec = R.group(shs, mock="bad-then-good", out_dir=str(tmp_path), log=lambda m: None)
    assert [c["phase"] for c in rec["calls"]] == ["first", "retry"]
    assert rec["calls"][0]["problems"] and rec["calls"][1]["problems"] == []
    assert rec["fallback"] == {}
    retry = (tmp_path / R.RETRY_PROMPT_FILE).read_text(encoding="utf-8")
    assert "e999" in retry and "전체 답을 다시" in retry


def test_group_falls_back_to_other_after_the_second_wrong_answer(tmp_path):
    shs = shots(tmp_path, sheet())
    rec = R.group(shs, mock="bad", out_dir=str(tmp_path), log=lambda m: None)
    assert len(rec["calls"]) == 2 and rec["problems"]
    assert rec["fallback"]["scr-a"]["other"] == ["e3"]
    assert shs[0]["regions"][-1]["name"] == R.OTHER_NAME


def test_mock_never_reads_the_key(tmp_path, monkeypatch):
    """--mock 은 .envs 도 읽지 않는다."""
    def boom():
        raise AssertionError("mock 이 키를 읽었다")
    monkeypatch.setattr(M, "load_env", boom)
    monkeypatch.setattr(M, "call_model", lambda *a, **k: boom())
    R.group(shots(tmp_path, sheet()), mock="regions", out_dir=str(tmp_path),
            log=lambda m: None)


def test_the_model_call_is_recorded(tmp_path, monkeypatch):
    """모델 호출 - 그림 · 토큰 · 비용 · 응답 원문이 남는다. 실제 API 는 부르지 않는다
    (call_model 을 바꿔 끼우고, 키 읽기도 막는다)."""
    shs = shots(tmp_path, sheet())
    answer = json.dumps({"sheets": [{"id": "scr-a", "regions": [
        {"no": 1, "name": "버튼들", "elements": ["e1", "e2", "e3"], "description": "버튼 셋"}]}]},
        ensure_ascii=False)
    sent = []

    def fake_call(model, prompt, max_tokens, log=None, reasoning_effort=None, images=None,
                  **kw):
        sent.append({"model": model, "prompt": prompt, "max_tokens": max_tokens,
                     "effort": reasoning_effort, "images": images})
        return {"text": "```json\n%s\n```" % answer, "usage": {"prompt": 3000, "completion": 500,
                                                             "reasoning": 100},
                "finish_reason": "stop", "seconds": 2.0, "model": "gpt-6.1-sol-2026",
                "max_tokens": max_tokens}
    monkeypatch.setattr(M, "load_env", lambda: None)
    monkeypatch.setattr(M, "call_model", fake_call)
    rec = R.group(shs, model="gpt-6.1-sol", out_dir=str(tmp_path), log=lambda m: None)
    assert len(sent) == 1
    assert sent[0]["max_tokens"] == R.MAX_TOKENS["reasoning"] and sent[0]["effort"] == "medium"
    assert [i["path"] for i in sent[0]["images"]] == [
        os.path.join(str(tmp_path), "shots", "scr-a.marked.png")]
    call = rec["calls"][0]
    assert call["tokens"] == {"prompt": 3000, "completion": 500, "reasoning": 100}
    assert call["cost_usd"] == pytest.approx((3000 * 2.0 + 500 * 10.0) / 1e6)
    assert rec["cost_usd"] == pytest.approx(0.011)
    assert shs[0]["regions"][0]["source"] == "model"
    assert (tmp_path / R.RESPONSE_FILE).read_text(encoding="utf-8").startswith("```json")


def test_a_model_error_leaves_other_regions_and_is_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "load_env", lambda: None)

    def fail(*a, **k):
        raise M.ApiRejected("AuthenticationError: no key")
    monkeypatch.setattr(M, "call_model", fail)
    shs = shots(tmp_path, sheet())
    rec = R.group(shs, model="gpt-6.1-sol", out_dir=str(tmp_path), log=lambda m: None)
    assert rec["error"].startswith("ApiRejected")
    assert [r["name"] for r in shs[0]["regions"]] == [R.OTHER_NAME]


def test_the_prompt_asks_for_descriptions_only():
    """넣는 것: 그림 · 요소 목록(번호 · 글자 · 도구가 확인한 동작) · 화면 목적. 평가나
    고령자 UX 규칙은 넣지 않고, 동작은 쓰지 말라고 한다."""
    p = R.build_prompt([sheet()])
    assert "누르면 어디로 가는지는 쓰지 마세요" in p
    assert "평가 · 문제 지적 · 개선 제안은 쓰지 않습니다" in p
    assert "화면 목적 (계획): 목적" in p
    assert "e1 · y 10 · \"버튼 0\" · 도구 확인: 클릭해도 변화 없음" in p
    for word in ("고령", "글자 크기", "대비", "WCAG", "규칙 목록"):
        assert word not in p
    assert M.IMAGE_MARK in p


# --------------------------------------------------------------------- #
# 4. 그리기
# --------------------------------------------------------------------- #
def test_layout_keeps_a_phone_screen_in_one_column():
    k, s, h = RD.layout(390, 844)
    assert k == 1 and s == pytest.approx(RD.PIC_H / 844.0)


def test_layout_splits_a_long_screen_into_columns():
    """그림 칸(PIC_H)은 장 맨 위의 정보칸 만큼 낮다 (11-12b) - 2,909px 화면은 세 단."""
    assert RD.PIC_H == 620
    k, s, h = RD.layout(390, 2909)
    assert k == 3 and h == 970
    assert RD.layout(390, 1800)[0] == 2
    assert RD.layout(390, 8000)[0] >= 3


@pytest.mark.parametrize("item,text", [
    ({"kind": "element", "result": {"kind": "screen", "to": "amount", "to_id": "scr-amount"}},
     "클릭 시 → [scr-amount] 이동"),
    ({"kind": "element", "result": {"kind": "same", "detail": "새로 보임: 'x'"}},
     "클릭 시 → 같은 화면에서 'x' 나타남"),
    ({"kind": "element", "result": {"kind": "none"}, "entrance": True},
     "클릭해도 변화 없음 · 과제 밖 입구"),
    ({"kind": "element", "result": {"kind": "disabled"}}, "비활성 (이 상태에서는 누를 수 없음)"),
    ({"kind": "element", "result": {"kind": "failed", "detail": "누르지 못했다 - 가려짐"}},
     "확인 못 함 — 누르지 못했다 - 가려짐"),
    ({"kind": "group", "value": "신한", "group": {"count": 38, "values": []},
      "result": {"kind": "screen", "to": "account", "to_id": "scr-account"}},
     "38개 중 하나 선택 → [scr-account] 이동 (눌러 본 대표: '신한')"),
    ({"kind": "group", "value": "1", "group": {"count": 11, "values": []},
      "result": {"kind": "same", "detail": "새로 보임: '1원' 외 1줄"}},
     "11개 중 하나 선택 → 같은 화면에서 '1원' 외 1줄 나타남 (눌러 본 대표: '1')"),
    ({"kind": "group", "value": "1", "group": {"count": 4, "values": []},
      "result": {"kind": "disabled"}}, "4개 모두 비활성 (이 상태에서는 누를 수 없음)"),
])
def test_result_text(item, text):
    """동작 칸은 실무 주석 꼴이다 (11-12b) - 출처는 그대로 도구가 눌러 본 결과."""
    assert RD.result_text(item, link=False) == text


@pytest.mark.parametrize("detail,phrase", [
    ("새로 보임: '메모가 보입니다' 외 1줄", "같은 화면에서 '메모가 보입니다' 외 1줄 나타남"),
    ("사라짐: 'b'", "같은 화면에서 'b' 사라짐"),
    ("입력 칸 값이 바뀜: '12'", "입력 칸에 '12'"),
    ("입력 칸 값이 바뀜", "입력 칸 값이 바뀜"),
    ("알림창 '확인하세요'", "알림창 '확인하세요' 뜸"),
    ("보이는 글의 순서가 바뀜", "같은 화면에서 글의 순서가 바뀜"),
    ("표시 상태가 바뀜 (보이는 글은 그대로)", "같은 화면에서 표시 상태가 바뀜 (글은 그대로)"),
    ("스크롤 위치가 바뀜", "같은 화면에서 스크롤 위치가 바뀜"),
    ("새로 보임: '1원' · 입력 칸 값이 바뀜: '1'", "같은 화면에서 '1원' 나타남 · 입력 칸에 '1'"),
    # 따옴표 안의 " · " 는 나누지 않는다
    ("새로 보임: '수수료 · 0원'", "같은 화면에서 '수수료 · 0원' 나타남"),
])
def test_same_screen_changes_read_as_annotations(detail, phrase):
    """walk.describe_change 가 남긴 detail 의 조각마다 주석 꼴로 (기준값의 결과는 그대로)."""
    assert RD.same_phrase(detail) == phrase


def rsheet(sid="scr-a", kind="visit", main=True, of=None, items=None, regions=None,
           **kw):
    """그리기 시험용 장 하나 (그림 없음)."""
    items = items if items is not None else []
    regions = regions if regions is not None else (
        [{"no": 1, "name": "영역", "description": "", "box": [0, 0, 10, 10], "source": "mock",
          "elements": [it["no"] for it in items]}] if items else [])
    sh = {"id": sid, "screen": sid[4:].split("--")[0], "kind": kind, "main": main, "of": of,
          "items": items, "regions": regions, "picture": None, "size": None,
          "purpose": "목적입니다. 둘째 문장", "from_original": ["home"], "dialogs": [],
          "conditions": [], "condition": None if main else "조건 글", "error": None}
    sh.update(kw)
    return sh


def ritem(no, text, result, **kw):
    it = {"no": no, "kind": "element", "action": "a-%s" % no, "text": text, "aria": None,
          "value": text, "tag": "button", "box": [0, 0, 10, 10], "disabled": False,
          "entrance": False, "result": result}
    it.update(kw)
    return it


@pytest.mark.parametrize("kind,main,tag", [
    ("error", False, "[오류]"), ("reveal", False, "[펼침]"), ("visit", False, "[다시 지남]"),
    ("error", True, "[오류]"), ("visit", True, None)])
def test_the_sheet_title_carries_the_condition_tag(kind, main, tag):
    """조건별 화면(오류 상태 · 펼친 뒤)은 그대로 두고 장 제목에 꼬리표를 붙인다 (11-12b)."""
    sid = "scr-a" if main else "scr-a--x"
    sh = rsheet(sid, kind=kind, main=main, of=None if main else "scr-a")
    page = RD.render_sheet(sh, {sid, "scr-a"}, {sid: sh})
    assert RD.sheet_tag(sh) == (tag.strip("[]") if tag else None)
    for t in ("[오류]", "[펼침]", "[다시 지남]"):
        assert (t in page) == (t == tag), t


def test_a_disabled_control_is_marked_as_an_exception():
    """꺼진 버튼은 도구가 확인한 예외다 - "예외: 비활성"."""
    sh = rsheet(items=[ritem("e1", "다음", {"kind": "disabled"}, disabled=True),
                       ritem("e2", "이전", {"kind": "none"})])
    page = RD.render_sheet(sh, {"scr-a"}, {"scr-a": sh})
    assert page.count("예외: 비활성") == 1
    li = [l for l in page.split("<li>") if "예외: 비활성" in l][0]
    assert "&#x27;다음&#x27;" in li and "비활성 (이 상태에서는 누를 수 없음)" in li


def test_an_empty_state_is_marked_only_when_the_region_answer_says_so():
    """빈 상태는 글자로 판정하지 않는다 - 영역 묶기 답의 표시(empty_state)가 있을 때만
    "예외: 빈 화면"."""
    items = [ritem("e1", "등록된 계좌가 없습니다", {"kind": "none"})]
    plain = rsheet(items=items)
    assert "예외: 빈 화면" not in RD.render_sheet(plain, {"scr-a"}, {"scr-a": plain})
    flagged = rsheet(items=items, regions=[
        {"no": 1, "name": "빈 목록", "description": "", "box": [0, 0, 10, 10],
         "source": "model", "elements": ["e1"], "empty": True}])
    page = RD.render_sheet(flagged, {"scr-a"}, {"scr-a": flagged})
    assert page.count("예외: 빈 화면") == 1 and "모델 설명" in page


def test_the_region_answer_may_flag_an_empty_state():
    sh = [sheet()]
    ans = {"sheets": [{"id": "scr-a", "regions": [
        {"no": 1, "name": "목록", "elements": ["e1", "e2"], "description": "d",
         "empty_state": True},
        {"no": 2, "name": "아래", "elements": ["e3"], "description": "d", "empty_state": "yes"}]}]}
    assert R.check(ans, sh) == []
    out, _ = R.settle_regions(ans, sh, "model")
    assert out["scr-a"][0]["empty"] is True and "empty" not in out["scr-a"][1]
    assert "empty_state" in R.build_prompt(sh)


@pytest.mark.parametrize("purpose,head", [
    ("출금 계좌를 확인하고 이체를 시작한다. 기존의 다른 기능도 이용한다.",
     "출금 계좌를 확인하고 이체를 시작한다"),
    ("새 계좌로 보내기 또는 자주 쓰는 계좌·내 계좌·최근 계좌에서 받는 대상을 정한다.",
     "새 계좌로 보내기 또는 자주 쓰는…"),
    ("금액을 넣는다", "금액을 넣는다"), (None, None), ("", None)])
def test_the_purpose_head_is_the_first_sentence_clipped(purpose, head):
    assert B.purpose_head(purpose) == head
    assert head is None or len(head) <= B.NAME_CHARS


def test_screen_names_come_from_the_region_answer_then_the_plan():
    """화면 이름: 영역 묶기의 화면 이름(그 장, 없으면 본 장의 것) → 계획의 화면 목적
    앞부분 → 화면 이름 (11-12b)."""
    shs = [rsheet("scr-a", title="받는 사람 고르기"),
           rsheet("scr-a--error-x", kind="error", main=False, of="scr-a", title=None),
           rsheet("scr-b", title=None, purpose="금액을 넣는다. 빠른 금액도 있다."),
           rsheet("scr-c", title=None, purpose=None)]
    B.name_sheets(shs)
    assert [(s["name"], s["name_source"]) for s in shs] == [
        ("받는 사람 고르기", "model"), ("받는 사람 고르기", "model"),
        ("금액을 넣는다", "plan"), ("c", "screen")]


def test_the_region_answer_may_name_each_sheet(tmp_path, monkeypatch):
    """답의 장마다 name 은 없어도 맞는 답이다. 글이 아니거나 너무 길면 버린다."""
    shs = shots(tmp_path, sheet(), sheet("scr-b"), sheet("scr-c"))
    regs = [{"no": 1, "name": "버튼", "elements": ["e1", "e2", "e3"], "description": "d"}]
    answer = json.dumps({"sheets": [
        {"id": "scr-a", "name": " 받는 사람  고르기 ", "regions": regs},
        {"id": "scr-b", "name": "가" * (R.TITLE_CHARS + 1), "regions": regs},
        {"id": "scr-c", "name": 3, "regions": regs}]}, ensure_ascii=False)
    monkeypatch.setattr(M, "load_env", lambda: None)
    monkeypatch.setattr(M, "call_model", lambda *a, **k: {
        "text": answer, "usage": None, "finish_reason": "stop", "seconds": 1.0})
    rec = R.group(shs, model="gpt-6.1-sol", out_dir=str(tmp_path), log=lambda m: None)
    assert rec["problems"] == []
    assert [s["title"] for s in shs] == ["받는 사람 고르기", None, None]
    assert "화면 이름(name)" in R.build_prompt(shs)
    mock = shots(tmp_path, sheet())
    R.group(mock, mock="regions", out_dir=str(tmp_path), log=lambda m: None)
    assert mock[0]["title"] is None                    # mock 은 화면 이름을 쓰지 않는다


def test_the_path_to_each_sheet_follows_the_flow():
    """경로 = 흐름 명세의 정답 걸음을 그 상태의 방문까지, 조건별 장은 끝에 제 장."""
    flow = json.load(io.open(os.path.join(FIX, "actions.flow.json"), encoding="utf-8"))
    states = W.states_of(flow)
    screen = {"visit:a": "a", "visit:b": "b", "error:bad": "b", "reveal:pick": "a"}
    walked = {"states": {k: {"items": [], "dom_screen": v} for k, v in screen.items()},
              "clicks": {}}
    run = {"task": "transfer", "plan_data": {"screens": [
        {"name": "a", "purpose": "첫 화면.", "from": ["home"]},
        {"name": "b", "purpose": "둘째 화면.", "from": ["amount"]}]}}
    sheets, _ = B.assemble(run, flow, states, walked, [])
    assert {s["id"]: s["path"] for s in sheets} == {
        "scr-a": ["scr-a"], "scr-a--reveal-pick": ["scr-a", "scr-a--reveal-pick"],
        "scr-b": ["scr-a", "scr-b"], "scr-b--error-bad": ["scr-a", "scr-b", "scr-b--error-bad"]}


def test_each_sheet_starts_with_an_info_row():
    """장 맨 위의 정보칸 한 줄 - 화면 ID · 화면 이름 · 경로 · 원본 화면 · 조건(조건별
    화면일 때만)."""
    a = rsheet("scr-a", name="받는 사람", name_source="model", path=["scr-a"])
    b = rsheet("scr-b", name="금액을 넣는다", name_source="plan", path=["scr-a", "scr-b"],
               from_original=["amount", "err-amount"])
    e = rsheet("scr-b--error-x", kind="error", main=False, of="scr-b", name="금액을 넣는다",
               name_source="plan", path=["scr-a", "scr-b", "scr-b--error-x"],
               condition="오류 경로 'x' 조건 글", from_original=["amount", "err-amount"])
    by_id = {s["id"]: s for s in (a, b, e)}
    info = RD.render_info(e, set(by_id), by_id)
    head = info.split("</tr>")[0]
    for th in ("화면 ID", "화면 이름", "경로", "바탕이 된 원본 화면", "조건"):
        assert th in head
    assert 'scr-b--error-x<span class="tag error">[오류]</span>' in info
    assert ('<a href="#scr-a">받는 사람</a> &gt; <a href="#scr-b">금액을 넣는다</a> &gt; '
            '<b>금액을 넣는다</b>') in info
    assert "amount, err-amount" in info and "오류 경로 &#x27;x&#x27; 조건 글" in info
    assert "계획의 화면 목적 앞부분" in info
    main = RD.render_info(a, set(by_id), by_id)
    assert "조건" not in main.split("</tr>")[0] and "모델 설명" in main
    page = RD.render_sheet(e, set(by_id), by_id)
    assert page.index('<table class="info">') < page.index('<div class="pic">')


def test_result_text_links_to_the_sheet():
    it = {"kind": "element", "result": {"kind": "screen", "to": "b", "to_id": "scr-b"}}
    assert RD.result_text(it, True, {"scr-b"}) == '클릭 시 → <a href="#scr-b">[scr-b]</a> 이동'
    assert RD.result_text(it, True, set()) == "클릭 시 → [scr-b] 이동"


# --------------------------------------------------------------------- #
# 5. 실행 폴더
# --------------------------------------------------------------------- #
def fake_run(tmp_path, passed=True, stopped=None, audit_passed=True, html=True):
    d = tmp_path / "20261007-000000"
    d.mkdir()
    if html:
        (d / "attempt_1.html").write_text("<html></html>", encoding="utf-8")
    (d / "attempt_1.flow.json").write_text("{}", encoding="utf-8")
    (d / "attempt_1.audit.json").write_text(json.dumps({"passed": audit_passed, "fatal": []}),
                                            encoding="utf-8")
    summary = {"passed": passed, "stopped_reason": stopped, "task": "transfer",
               "final": {"attempt": 1, "html": "C:/elsewhere/attempt_1.html",
                         "flow": "C:/elsewhere/attempt_1.flow.json",
                         "audit": "C:/elsewhere/attempt_1.audit.json"}}
    (d / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    return str(d)


def test_a_passed_run_is_read_from_its_own_folder(tmp_path):
    """summary 의 절대 경로가 다른 PC 의 것이어도 실행 폴더 안의 같은 이름을 쓴다."""
    run = RUN.load_run(fake_run(tmp_path))
    assert run["html"].endswith(os.path.join("20261007-000000", "attempt_1.html"))
    assert run["task"] == "transfer" and run["plan_data"] is None


@pytest.mark.parametrize("kw,needle", [
    ({"passed": False, "stopped": "budget_exhausted"}, "통과하지 못한 실행이다"),
    ({"passed": False, "stopped": "stuck"}, "같은 실패가 되풀이되어 멈춘 실행"),
    ({"audit_passed": False}, "검사 결과(attempt_1.audit.json)가 통과가 아니다"),
    ({"html": False}, "최종 빌드의 html 파일이 실행 폴더에 없다"),
])
def test_a_run_that_did_not_pass_gets_no_storyboard(tmp_path, kw, needle):
    with pytest.raises(RUN.NotReady) as e:
        RUN.load_run(fake_run(tmp_path, **kw))
    assert needle in str(e.value)


def test_the_cli_exits_2_with_the_reason_and_writes_nothing(tmp_path, capsys):
    d = fake_run(tmp_path, passed=False, stopped="budget_exhausted")
    assert _api.storyboard_main([d, "--mock"]) == 2
    err = capsys.readouterr().err
    assert "만들지 않았다" in err and "통과하지 못한 실행이다" in err
    assert not os.path.exists(os.path.join(d, B.OUT_DIR))


def test_the_cli_refuses_a_folder_without_summary(tmp_path, capsys):
    assert _api.storyboard_main([str(tmp_path), "--mock"]) == 2
    assert "summary.json 이 없다" in capsys.readouterr().err


def test_model_and_mock_cannot_both_be_given():
    with pytest.raises(SystemExit):
        _api.storyboard_cli_parser().parse_args(["x", "--model", "m", "--mock"])


def test_the_original_fingerprint_ignores_line_endings():
    """Windows 작업 트리의 CRLF 와 저장소의 LF 가 같은 원본으로 잰다."""
    assert RUN.fingerprint(b"a\r\nb\r\n") == RUN.fingerprint(b"a\nb\n")
    fp = RUN.original_fingerprint(_api.load_task("transfer"), RUN.head_commit())
    assert fp["source"] == "commit" and fp["path"] == "inputs/original_transfer.html"


def test_the_wire_copy_only_adds_the_cover():
    html = io.open(os.path.join(FIX, "actions.html"), encoding="utf-8").read()
    wired = W.wire_copy(html)
    assert W.WIRE_MARK in wired and "filter:grayscale(1)" in wired
    start = wired.index(W.WIRE_MARK)
    end = wired.index("</script>", start) + len("</script>\n")
    assert wired[:start] + wired[end:] == html


# 배치를 바꾸는 속성 - 로우파이 덮개는 이것을 하나도 쓰지 않는다 (11-12b)
LAYOUT_PROPS = re.compile(
    r"(?:^|[;{])\s*(font|font-size|font-weight|font-family|line-height|letter-spacing|"
    r"width|height|min-width|min-height|max-width|max-height|margin[a-z-]*|padding[a-z-]*|"
    r"display|position|top|left|right|bottom|border|border-width|border-style|"
    r"border-(?:top|right|bottom|left)(?:-width|-style)?|flex[a-z-]*|grid[a-z-]*|"
    r"transform|zoom|box-sizing|white-space|word-break)\s*:")


def test_the_lofi_cover_strips_decoration_but_keeps_layout():
    """실무 와이어프레임 관례 - 배경 · 채우기 · 그림자 · 그라데이션 · 둥근 모서리를 없애고
    글자는 진회색 하나, 누를 수 있는 요소와 묶음 상자는 1px 회색 테두리, 꺼진 버튼은 점선.
    위치 · 크기 · 글자 크기 · 굵기는 설계 결정이므로 남긴다 - 배치를 바꾸는 속성은 쓰지
    않고, 테두리는 두께를 둔 채 색만 지운다 (상자는 outline)."""
    css = W.WIRE_CSS
    bad = LAYOUT_PROPS.search(css)
    assert bad is None, bad.group(0)
    for want in ("background-color:transparent", "background-image:none", "box-shadow:none",
                 "text-shadow:none", "border-radius:0", "border-color:transparent",
                 "color:#333", "-webkit-text-fill-color:#333", "outline:1px solid #999",
                 "outline-style:dashed", "[data-sb-box]", "[data-sb-fill=solid]"):
        assert want in css, want
    for sel in ("[data-action]:disabled", '[data-action][aria-disabled="true"]',
                "fieldset:disabled [data-action]"):
        assert "html.sb-wire " + sel in css


def test_the_lofi_cover_is_off_while_walking():
    """덮개의 규칙은 모두 html.sb-wire 아래에 있고, 그 클래스는 그림을 찍기 직전에
    __sbWire() 가 켠다 - 걷는 동안의 페이지는 원래 스타일 그대로다 (문서가 열릴 때
    켜지 않는다)."""
    for sel in re.findall(r"([^{}]+)\{[^{}]*\}", W.WIRE_CSS):
        for part in sel.split(","):
            assert part.strip().startswith("html.%s" % W.WIRE_CLASS), part
    assert "DOMContentLoaded" not in W.WIRE_JS
    assert "classList.add('%s')" % W.WIRE_CLASS in W.WIRE_JS


def test_states_come_from_the_flow():
    flow = json.load(io.open(os.path.join(FIX, "actions.flow.json"), encoding="utf-8"))
    states = W.states_of(flow)
    assert [(s["key"], s["kind"], s["upto"]) for s in states] == [
        ("visit:a", "visit", 0), ("visit:b", "visit", 1), ("error:bad", "error", 1),
        ("reveal:pick", "reveal", 0)]
    assert states[2]["settle"] == "b" and states[2]["back_to"] == "a"


# --------------------------------------------------------------------- #
# 6. 작은 HTML 로 동작 확인 (pytest -m browser)
# --------------------------------------------------------------------- #
UNIT_OUT = os.path.join(ROOT, ".pytest-outputs", "storyboard_unit")


@pytest.fixture(scope="module")
def unit(server):
    shutil.rmtree(UNIT_OUT, ignore_errors=True)
    os.makedirs(UNIT_OUT)
    src = os.path.join(FIX, "actions.html")
    before = hashlib.sha256(open(src, "rb").read()).hexdigest()
    wire = os.path.join(UNIT_OUT, "wireframe.html")
    io.open(wire, "w", encoding="utf-8", newline="\n").write(
        W.wire_copy(io.open(src, encoding="utf-8").read()))
    rel = lambda p: os.path.relpath(p, ROOT).replace(os.sep, "/")
    flow = json.load(io.open(os.path.join(FIX, "actions.flow.json"), encoding="utf-8"))
    states, walked = B.inspect("%s/%s" % (C.BASE_URL, rel(src)),
                               "%s/%s" % (C.BASE_URL, rel(wire)), flow, ["pick"],
                               os.path.join(UNIT_OUT, "shots"), log=lambda m: None)
    after = hashlib.sha256(open(src, "rb").read()).hexdigest()
    by_state = {}
    for st in states:
        got = walked["states"][st["key"]]
        items = B.itemize(got.get("items") or [], ["pick"])
        res = walked["clicks"].get(st["key"]) or {}
        by_state[st["key"]] = {"got": got, "items": {it["action"]: dict(it, result=res[it["no"]])
                                                     for it in items}}
    return {"states": by_state, "walked": walked, "same_file": before == after}


def result(unit, action, state="visit:a"):
    return unit["states"][state]["items"][action]["result"]


@pytest.mark.browser
def test_unit_another_screen(unit):
    assert result(unit, "go-b") == {"kind": "screen", "to": "b"}


@pytest.mark.browser
def test_unit_same_screen_change(unit):
    assert result(unit, "show-note") == {"kind": "same", "detail": "새로 보임: '메모가 보입니다'"}


@pytest.mark.browser
def test_unit_nothing_happens(unit):
    assert result(unit, "noop") == {"kind": "none"}


@pytest.mark.browser
def test_unit_a_choice_group_is_one_item_and_one_click(unit):
    """무리 넷 중 대표 하나만 눌렀다 - 읽는 순서의 첫 것 (data-v=3)."""
    it = unit["states"]["visit:a"]["items"]["pick"]
    assert it["kind"] == "group" and it["group"]["count"] == 4
    assert it["value"] == "3"
    assert it["result"] == {"kind": "same", "detail": "새로 보임: '고른 값: 3'"}
    items = unit["states"]["visit:a"]["items"]
    clicked = unit["walked"]["clicks"]["visit:a"]
    assert len(clicked) == len(items)


@pytest.mark.browser
def test_unit_a_disabled_control_is_not_pressed(unit):
    assert result(unit, "next") == {"kind": "disabled"}


@pytest.mark.browser
def test_unit_out_of_scope_entrance_keeps_its_result(unit):
    it = unit["states"]["visit:a"]["items"]["oos-help"]
    assert it["entrance"] is True and it["aria"] == "도움말"
    assert it["result"] == {"kind": "none"}


@pytest.mark.browser
def test_unit_a_covered_control_is_left_out(unit):
    got = unit["states"]["visit:a"]["got"]
    assert "under" not in unit["states"]["visit:a"]["items"]
    assert got["covered"] == 1


@pytest.mark.browser
def test_unit_a_late_transition_is_still_another_screen(unit):
    """700ms 뒤에 넘어가는 버튼 - 조회를 흉내 내는 설계 (AFTER_CLICK_MS 안)."""
    assert result(unit, "later") == {"kind": "screen", "to": "b"}


@pytest.mark.browser
def test_unit_a_scrolling_screen_is_one_tall_picture(unit):
    got = unit["states"]["visit:a"]["got"]
    assert got["size"][0] == 390 and got["size"][1] > 844 and got["grown"] > 0
    bottom = unit["states"]["visit:a"]["items"]["bottom"]
    later = unit["states"]["visit:a"]["items"]["later"]
    assert bottom["box"][1] > 844 - 72
    assert later["box"][1] > bottom["box"][1]          # 아래 막대는 늘린 화면의 맨 아래
    assert os.path.exists(got["picture"]) and os.path.exists(got["marked"])


@pytest.mark.browser
def test_unit_error_and_reveal_states(unit):
    err = unit["states"]["error:bad"]
    assert err["got"]["dom_screen"] == "b"
    assert err["items"]["err"]["result"] == {"kind": "none"}       # 이미 보이는 오류 글
    assert err["items"]["back-a"]["result"] == {"kind": "screen", "to": "a"}
    rev = unit["states"]["reveal:pick"]
    assert rev["items"]["show-note"]["result"] == {"kind": "none"}  # 이미 펼쳤다


@pytest.mark.browser
def test_unit_the_original_file_is_untouched(unit):
    assert unit["same_file"]


LOOK = r"""(sels) => sels.map(sel => {
  const el = document.querySelector(sel);
  const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
  return {sel: sel, box: [r.left, r.top, r.width, r.height], size: cs.fontSize,
          weight: cs.fontWeight, bg: cs.backgroundColor, bgi: cs.backgroundImage,
          color: cs.color, shadow: cs.boxShadow, radius: cs.borderTopLeftRadius,
          outline: cs.outlineStyle + ' ' + cs.outlineWidth,
          pic: el.hasAttribute('data-sb-pic'), box_mark: el.hasAttribute('data-sb-box')};
})"""
LOOKED = ["#go-b", "[data-action='next']", "[data-action='pick']", ".card", ".plain", "img",
          ".pic", "#phone", ".bar"]


async def _look_before_and_after(url):
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page(viewport=dict(W.VIEWPORT))
            await page.goto(url, wait_until="networkidle")
            before = await page.evaluate(LOOK, LOOKED)
            off = await page.evaluate("() => document.documentElement.className")
            marks = await page.evaluate("() => window.__sbWire()")
            after = await page.evaluate(LOOK, LOOKED)
            return before, after, off, marks
        finally:
            await browser.close()


@pytest.mark.browser
def test_unit_the_lofi_cover(unit):
    """그림용 사본에서 덮개를 켜기 전후 - 위치 · 크기 · 글자 크기 · 굵기는 그대로이고,
    채우기 · 그림자 · 둥근 모서리는 없어지고, 누를 것 · 묶음 상자는 1px 회색 테두리,
    꺼진 버튼은 점선, 그림 자리는 X 상자."""
    url = "%s/%s" % (C.BASE_URL, os.path.relpath(os.path.join(UNIT_OUT, "wireframe.html"),
                                                ROOT).replace(os.sep, "/"))
    before, after, off, marks = asyncio.run(_look_before_and_after(url))
    assert W.WIRE_CLASS not in off                      # 걷는 동안에는 꺼져 있다
    for b, a in zip(before, after):
        assert (a["box"], a["size"], a["weight"]) == (b["box"], b["size"], b["weight"]), a["sel"]
    look = {a["sel"]: a for a in after}
    gray, white = "rgb(51, 51, 51)", "rgb(255, 255, 255)"
    for sel in ("#go-b", "[data-action='pick']", "[data-action='next']", ".card", ".plain"):
        assert look[sel]["color"] == gray and look[sel]["shadow"] == "none", sel
        assert look[sel]["radius"] == "0px", sel
    # 원래 채워진 것은 흰 종이 (뒤를 가린다), 바탕 없던 것은 그대로 비어 있다
    assert look["#go-b"]["bg"] == white and look[".card"]["bg"] == white
    assert look[".plain"]["bg"] == "rgba(0, 0, 0, 0)"
    assert look["#go-b"]["outline"] == "solid 1px"
    assert look["[data-action='next']"]["outline"] == "dashed 1px"      # 꺼진 버튼
    assert look[".card"]["box_mark"] and look[".card"]["outline"] == "solid 1px"
    assert not look[".plain"]["box_mark"] and look[".plain"]["outline"].startswith("none")
    assert not look["#phone"]["box_mark"]
    assert look[".bar"]["outline"].startswith("none")       # 한 변 테두리는 상자가 아니다
    assert look[".pic"]["pic"] and "linear-gradient" in look[".pic"]["bgi"]
    assert "linear-gradient" in look["img"]["bgi"]
    assert marks["pic"] == 1 and marks["box"] >= 1
    # 원래 디자인은 달랐다 - 시험이 헛돌지 않는다
    assert before[0]["bg"] != white and before[3]["shadow"] != "none"
    assert before[3]["radius"] == "12px"


# --------------------------------------------------------------------- #
# 7. 끝까지 - 기준값 (pytest -m browser)
# --------------------------------------------------------------------- #
def tree_hashes(d):
    out = {}
    for base, dirs, files in os.walk(d):
        if os.path.basename(base) == B.OUT_DIR or B.OUT_DIR in os.path.relpath(base, d).split(
                os.sep):
            continue
        for f in files:
            p = os.path.join(base, f)
            out[os.path.relpath(p, d)] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    return out


def make_and_compare(run_dir, name):
    before = tree_hashes(run_dir)
    code = _api.storyboard_main([run_dir, "--mock"])
    assert code == 0
    assert tree_hashes(run_dir) == before                 # 원래 파일은 그대로
    out = os.path.join(run_dir, B.OUT_DIR)
    data = json.load(io.open(os.path.join(out, B.JSON_NAME), encoding="utf-8"))
    for f in ("index.html", "storyboard.pdf", "wireframe.html", "storyboard.log",
              R.PROMPT_FILE, R.RESPONSE_FILE):
        assert os.path.exists(os.path.join(out, f)), f
    assert open(os.path.join(out, "storyboard.pdf"), "rb").read(5) == b"%PDF-"
    for sh in data["sheets"]:
        assert os.path.exists(os.path.join(out, sh["picture"])), sh["id"]
    # storyboard.json 만으로 같은 설계서를 다시 그린다
    page = io.open(os.path.join(out, "index.html"), encoding="utf-8").read()
    assert RD.render(data) == page
    want = json.load(io.open(os.path.join(C.HERE, "baseline", "storyboard", "%s.json" % name),
                             encoding="utf-8"))
    got = C.strip_storyboard(data)
    assert got["counts"] == want["counts"]
    assert got["flow"] == want["flow"]
    for g, w in zip(got["sheets"], want["sheets"]):
        assert g["id"] == w["id"]
        assert [(i["no"], i["action"], i["result"]) for i in g["items"]] == \
            [(i["no"], i["action"], i["result"]) for i in w["items"]], g["id"]
    assert got == want
    return data


@pytest.mark.browser
def test_storyboard_of_the_mock_pass_run(server):
    C.ensure_mock_input()
    summary, code = C.run_mock(C.STORYBOARD_MOCK_ARGS)
    assert code == 0
    data = make_and_compare(summary["run_dir"], "mock_pass")
    assert data["regions_call"]["mock"] == "regions"


@pytest.mark.browser
@pytest.mark.parametrize("name", sorted(C.STORYBOARD_SAVED))
def test_storyboard_of_a_saved_reply(server, name):
    import storyboard_fixture as SF
    d = SF.make_saved_run(name, C.BASE_URL)
    data = make_and_compare(d, name)
    # 모든 항목이 정확히 한 영역에 들어 있다
    for sh in data["sheets"]:
        nos = [e for r in sh["regions"] for e in r["elements"]]
        assert sorted(nos) == sorted(it["no"] for it in sh["items"]), sh["id"]
