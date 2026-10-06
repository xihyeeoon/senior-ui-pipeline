r"""과제 밖 입구 보존 (검사 K) - 연구자 결정 (나), 2026-10-06.

연구 원칙은 "보여 주는 방식은 자유, 사용자가 할 수 있는 일은 줄이지 않는다" 다.
예비 실행(20261006-215902)의 모델은 이체 홈의 다른 메뉴를 모두 지우고 "돈 보내기"
하나만 남겼다 - 그러면 C 는 기능을 빼서 이긴 것이 되어 A1 · A2 와의 비교가 공정하지
않다.

입구 목록은 과제 파일의 `entrances` 다 (더미앱 A1 의 OutOfScope 탭 대상, 연구자 확정).
판정 규칙:

  - 원본에서 찾은 입구만 센다 (검사 I 가 원본의 선택지만 세는 것과 같다)
  - 걷는 동안(reveal 포함) DOM 의 data-action 요소의 글자 또는 aria-label 이
    [원본 글자, 더미 라벨] 중 하나와 맞으면 있다 - 경계 규칙은 검사 I 와 같다
  - 같은 화면이 아니어도, 접혀 있어도 된다. 빠지면 fatal

브라우저도 모델도 부르지 않는다 (손으로 만든 스냅샷). 실제로 걷는 것은
test_drive.py 의 mock 실행 기준값 (entrances-none · entrances-reveal) 이 본다.
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


def names(e):
    return [n for n in (e.get("text"), e.get("label")) if n]


# ===================================================================== #
# 1. 목록 - 과제 파일에 있고, 원본이 그것을 누를 수 있는 요소로 갖는다
# ===================================================================== #
WANT = {
    # 이체: T1-T28 + R1 · R3 · R4 (R2 의 [이체] 는 이체 과제의 경로다)
    "transfer": ["T%d" % i for i in range(1, 29)] + ["R1", "R3", "R4"],
    # 공과금: B1-B30 + R2 · R3 · R4 (R1 의 ⌕ 는 공과금 과제의 경로 go-menu 다)
    "bill": ["B%d" % i for i in range(1, 31)] + ["R2", "R3", "R4"],
}


@pytest.mark.parametrize("task", ["transfer", "bill"])
def test_the_task_file_lists_the_confirmed_entrances(task):
    group = T.load_task(task)["entrances"]
    assert "00834ca" in group["source"]
    ids = [e["id"] for e in group["items"]]
    assert sorted(ids) == sorted(WANT[task]) and len(ids) == len(set(ids))
    for e in group["items"]:
        assert e["dummy"] and e["screen"] and e["label"], e
        # data-action 이름은 ASCII 다 - 분기를 읽는 규칙(audit/handlers.py)이 ASCII
        # 이름만 읽는다. 한글 이름이면 검사 C 와 형식 검사가 "분기 없음" 으로 잡는다.
        assert re.fullmatch(r"oos-[a-z0-9-]+", e["action"]), e


@pytest.mark.parametrize("task", ["transfer", "bill"])
def test_the_original_marks_every_entrance(task):
    """원본 HTML 보강: 입구마다 data-action 과 aria-label (더미 라벨). 아이콘만 있는
    입구의 이름을 모델이 알 수 있게 하려는 것이다."""
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


# ===================================================================== #
# 2. 판정 (손으로 만든 스냅샷)
# ===================================================================== #
def texts_for(task, keep=None, drop=()):
    """그 과제의 입구 이름들을 data-action 글자로 가진 스냅샷 글 목록."""
    out = []
    for e in items(task):
        if e["id"] in drop:
            continue
        if keep and e["id"] not in keep:
            continue
        out.append(e["label"])
    return out


def judge(rep_texts, orig_texts=None, revealed=None, task="transfer"):
    f = flow(["start", "done"], task=task)
    if task != "transfer":
        f.pop("truth")          # 손 스냅샷의 옛 이체 정답 대신 그 과제의 정답
    orig = snap({"start": row("start"), "done": done_row()},
                action_texts=texts_for(task) if orig_texts is None else orig_texts)
    rep = snap({"start": row("start"), "done": done_row()}, action_texts=rep_texts)
    if revealed is not None:
        rep["revealed"] = revealed
    return _api.audit(orig, rep, "<html></html>", "<html></html>", f)


def k_fatals(report):
    return [x for x in report["fatal"] if x.get("check") == "K"]


def test_a_build_without_the_entrances_fails():
    """예비 실행처럼 다른 메뉴를 모두 지운 빌드. 고치기 전에는 통과했다."""
    report = judge(["돈 보내기"])
    ks = k_fatals(report)
    assert report["passed"] is False and len(ks) == 1, report["fatal"]
    assert report["metrics"]["entrances_original"] == len(WANT["transfer"])
    assert report["metrics"]["entrances_kept"] == 0
    assert "메시지" in ks[0]["detail"] and "없애지 마라" in ks[0]["detail"]


def test_a_build_that_keeps_every_entrance_passes():
    report = judge(texts_for("transfer"))
    assert k_fatals(report) == [] and report["metrics"]["entrances_kept"] == 31


def test_one_missing_entrance_is_named():
    report = judge(texts_for("transfer", drop=("T28",)))
    ks = k_fatals(report)
    assert len(ks) == 1 and ks[0]["missing"] == ["T28"]
    assert "공유" in ks[0]["detail"]


def test_entrances_found_only_after_a_reveal_count():
    """눌러야 만들어지는 입구 - 흐름 명세의 reveal 로 걸어 모은 글자도 센다."""
    report = judge(["돈 보내기"], revealed={"oos-message": {
        "at": "start", "choices": {}, "action_texts": texts_for("transfer")}})
    assert k_fatals(report) == [], report["fatal"]


def test_the_original_glyph_or_the_dummy_label_both_count():
    """아이콘만 있는 입구: 원본 글자(☺) 그대로 두어도, 이름(메시지)을 붙여도 된다."""
    full = texts_for("transfer", drop=("T1", "T2"))
    assert k_fatals(judge(full + ["☺", "지갑"])) == []
    assert k_fatals(judge(full + ["☺"]))[0]["missing"] == ["T2"]


def test_matching_uses_the_check_I_boundary():
    """검사 I 와 같은 경계 - 한글은 앞쪽 경계만 본다. '주식' 은 '보유주식' 안에서
    맞지 않고, '주식 현재가' 에서는 맞는다."""
    full = texts_for("transfer", drop=("T18",))
    assert k_fatals(judge(full + ["보유주식"]))[0]["missing"] == ["T18"]
    assert k_fatals(judge(full + ["주식 현재가"])) == []


def test_an_entrance_the_original_does_not_have_is_not_counted():
    """원본에서 찾지 못한 입구는 세지 않는다 (검사 I 와 같다) - 원본이 다른 흐름
    파일(fixture 페이지 등)이면 입구 목록은 아무것도 요구하지 않는다."""
    report = judge(["x"], orig_texts=["x"])
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
    report = judge(["x"], task="bill", orig_texts=texts_for("bill"))
    assert report["metrics"]["entrances_original"] == len(WANT["bill"])
    assert len(k_fatals(report)) == 1


# ===================================================================== #
# 3. 프롬프트 - 그 수준으로만 알린다 (어디에 어떻게 두라는 말은 하지 않는다)
# ===================================================================== #
SENTENCE = ("원본의 다른 메뉴와 버튼도 사용자가 쓸 수 있는 기능이다. 배치 · 묶음 · 크기는 "
            "바꿔도 되지만 없애지 마라")


@pytest.mark.parametrize("task", ["transfer", "bill"])
def test_the_prompts_say_it_once_and_only_that(task):
    p = _api.prompt_module
    for t in (p.load_plan_template(task), p.load_template(task),
              p.load_refine_template(task)):
        flat = " ".join(t.split())
        assert flat.count(SENTENCE) == 1
        assert "oos-" not in flat and "entrances" not in flat


# ===================================================================== #
# 4. mock 실행으로 실제로 걷는다 (pytest -m browser)
# ===================================================================== #
def final_audit(summary):
    path = summary["attempts"][-1].get("audit") or os.path.join(
        summary["run_dir"], "attempt_%d.audit.json" % summary["attempts"][-1]["n"])
    return json.load(io.open(path, encoding="utf-8"))


@pytest.mark.browser
@pytest.mark.parametrize("mode,passed", [
    ("entrances-none", False),       # 입구를 다 지운 빌드 -> fatal
    ("entrances-reveal", True),      # [다른 메뉴] 를 눌러야 그리는 빌드 + reveal -> 통과
    ("pass", True),                  # 첫 화면의 접힌 블록 (<details>) -> 통과
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
