r"""검사 I - 펼친 뒤 실제로 보이는가 (11-8 2-3, 2026-10-07 20:38 추가).

배경: 공과금 실행(20261007-201603-bill)의 전체메뉴 · 메뉴 검색에서 분야 칸이 열린 모양인데
속이 비어 보였다. 검사 I 는 메뉴 289개가 문서 안에 있는지만 세서 통과했다 ("숨김 · 접힘은
괜찮다"). 재현해 보니 분야 칸을 누르면 그 안에는 닫힌 분류 제목만 있고, 항목은 분류를 한 번
더 눌러야 보였다 - 콘솔 오류는 없었다 (outputs/11-8_repro_menu/).

규칙: 원본 선택지 값마다, 흐름이 머무는 걸음이나 reveal 뒤 어느 상태에서 누를 수 있게
보이면(그려져 있고 크기 > 0, display / visibility / opacity 로 숨지 않았고, disabled 가
아니다) "고를 수 있음" 이다. 문서 안에만 있고 어느 상태에서도 보이지 않는 값은 fatal 이다
(전에는 kept 와 selectable 이 다르면 경고였다).

단, 원본을 걷는 동안 원본에서 보인 값만 그렇게 센다 (검사 K 와 같은 규칙, 연구자 결정
2026-10-07). 이체 원본은 은행 시트의 [증권사] 탭 뒤 29개를 원본 흐름이 걷는 동안 한 번도
보이지 않는다 - 그 값까지 요구하면 원본 대 원본도 떨어진다. 그 값은 전처럼 남아 있기만
하면 되고, 보이지 않으면 경고다.

걷는 동안 걸음마다 보이는 값을 `choices_shown` 으로 모은다 (probes.CHOICE_SHOWN - 무리는
CHOICE_GROUPS 와 같은 규칙으로 정하고, 그 가운데 보이는 요소의 값만). 그 칸이 없는 옛
스냅샷은 전처럼 판정하고 그 사실을 남긴다.

  .\.venv\Scripts\python.exe -m pytest tests/test_choices_shown.py
  .\.venv\Scripts\python.exe -m pytest tests/test_choices_shown.py -m browser
"""
import asyncio
import io
import os

import pytest

import _api
from test_audit_bugs import done_row, flow, row, snap

ROOT = _api.ROOT_DIR
BANKS = ["국민", "신한", "우리", "하나", "농협"]


def judge(rep_rows, revealed=None, rep_html="<html></html>", orig_banks=BANKS):
    """원본은 은행 다섯이 고를 수 있게 보인다. `rep_rows` 는 생성물의 bank 화면 칸."""
    f = flow(["start", "bank", "done"])
    orig = snap({"start": row("start"),
                 "bank": row("bank", choices={"pick-bank": list(orig_banks)},
                             choices_shown={"pick-bank": list(orig_banks)}),
                 "done": done_row()})
    rep = snap({"start": row("start"), "bank": row("bank", **rep_rows), "done": done_row()})
    if revealed is not None:
        rep["revealed"] = revealed
    return _api.audit(orig, rep, "<html></html>", rep_html, f)


def i_fatals(report):
    return [x for x in report["fatal"] if x.get("check") == "I"]


def test_values_shown_on_a_step_are_selectable():
    report = judge({"choices": {"pick-bank": BANKS},
                    "choices_shown": {"pick-bank": BANKS}})
    assert i_fatals(report) == []
    m = report["metrics"]
    assert m["choice_values_kept"] == {"pick-bank": 5}
    assert m["choice_values_selectable"] == {"pick-bank": 5}


def test_values_only_in_the_document_are_fatal():
    """문서 안에는 다섯이 다 있지만(숨김 · 접힘) 보인 것은 둘뿐 - 셋이 fatal."""
    report = judge({"choices": {"pick-bank": BANKS},
                    "choices_shown": {"pick-bank": BANKS[:2]}})
    fs = i_fatals(report)
    assert report["passed"] is False and len(fs) == 1, report["fatal"]
    assert fs[0]["action"] == "pick-bank"
    assert fs[0]["not_selectable"] == sorted(BANKS[2:])
    assert "어느 상태에서도 누를 수 있게 보이지 않았다" in fs[0]["detail"]
    assert "reveal" in fs[0]["detail"]
    m = report["metrics"]
    assert m["choice_values_kept"] == {"pick-bank": 5}
    assert m["choice_values_selectable"] == {"pick-bank": 2}
    assert m["choice_values_not_selectable"] == {"pick-bank": sorted(BANKS[2:])}
    # 경고로도 한 번 더 남기지 않는다 - fatal 하나다
    assert [w for w in report["warning"] if w.get("check") == "I"] == []


def test_values_in_the_script_only_are_fatal_too():
    """원문(스크립트 배열)에만 있고 DOM 에도, 보이는 곳에도 없다 - 전에는 경고였다."""
    html = "<script>const B=%r;</script>" % BANKS
    report = judge({"choices": {"pick-bank": BANKS[:1]},
                    "choices_shown": {"pick-bank": BANKS[:1]}}, rep_html=html)
    fs = i_fatals(report)
    assert len(fs) == 1 and fs[0]["not_selectable"] == sorted(BANKS[1:])


def test_values_shown_after_a_reveal_count():
    report = judge({"choices": {"pick-bank": BANKS},
                    "choices_shown": {"pick-bank": BANKS[:2]}},
                   revealed={"pick-bank": {"at": "bank", "error": None, "violations": [],
                                           "choices": {"pick-bank": BANKS},
                                           "choices_shown": {"pick-bank": BANKS}}})
    assert i_fatals(report) == []
    assert report["metrics"]["choice_values_selectable"] == {"pick-bank": 5}


def test_a_value_the_original_did_not_show_either_is_only_a_warning():
    """원본도 걷는 동안 보이지 않은 값(증권사 탭 뒤 같은) - 보여야 한다고 요구하지 않는다."""
    f = flow(["start", "bank", "done"])
    orig = snap({"start": row("start"),
                 "bank": row("bank", choices={"pick-bank": BANKS},
                             choices_shown={"pick-bank": BANKS[:3]}),
                 "done": done_row()})
    rep = snap({"start": row("start"),
                "bank": row("bank", choices={"pick-bank": BANKS},
                            choices_shown={"pick-bank": BANKS[:3]}),
                "done": done_row()})
    report = _api.audit(orig, rep, "<html></html>", "<html></html>", f)
    assert i_fatals(report) == []
    m = report["metrics"]
    assert m["choice_values_shown_in_original"] == {"pick-bank": 3}
    assert m["choice_values_selectable"] == {"pick-bank": 3}
    assert m["choice_values_not_selectable"] == {}
    ws = [w for w in report["warning"] if w.get("check") == "I"]
    assert len(ws) == 1 and ws[0]["not_selectable"] == sorted(BANKS[3:])
    assert "원본도 걷는 동안 보이지 않은 값" in ws[0]["detail"]


def test_a_walk_that_stopped_early_marks_the_hidden_values_as_derived():
    """걷기가 bank 앞에서 멈췄다 - 그 화면의 값을 보지 못한 것은 멈춘 탓이다."""
    f = flow(["start", "bank", "done"])
    orig = snap({"start": row("start"),
                 "bank": row("bank", choices={"pick-bank": BANKS},
                             choices_shown={"pick-bank": BANKS}),
                 "done": done_row()})
    rep = snap({"start": row("start", choices={"pick-bank": BANKS},
                             choices_shown={}),
                "bank": {"error": "TimeoutError: 선택자가 없다"}})
    report = _api.audit(orig, rep, "<html></html>", "<html></html>", f)
    fs = [x for x in i_fatals(report) if x.get("not_selectable")]
    assert len(fs) == 1 and fs[0]["derived_from"] == report["metrics"]["stopped_at"]
    assert "멈춰" in fs[0]["detail"]


def test_missing_values_are_still_their_own_fatal():
    report = judge({"choices": {"pick-bank": BANKS[:4]},
                    "choices_shown": {"pick-bank": BANKS[:4]}})
    fs = i_fatals(report)
    assert len(fs) == 1 and fs[0]["missing"] == ["농협"]
    assert "not_selectable" not in fs[0]


def test_an_old_snapshot_without_choices_shown_is_judged_as_before():
    """수집이 choices_shown 을 남기기 전의 스냅샷 - 문서(DOM)에 있으면 고를 수 있다고 보고,
    보이는지는 판정하지 않았다고 남긴다."""
    html = "<script>const B=%r;</script>" % BANKS
    report = judge({"choices": {"pick-bank": BANKS[:2]}}, rep_html=html)
    assert i_fatals(report) == []
    assert report["metrics"]["choice_values_selectable"] == {"pick-bank": 2}
    assert any(w.get("check") == "I" and w.get("not_selectable") for w in report["warning"])
    assert any(s.startswith("I/보임") for s in report["metrics"]["checks_stood_down"])


def test_the_not_selectable_fatal_has_its_own_count_for_the_stuck_check():
    """막힘(같은 실패의 되풀이) 비교는 (검사, 대상, 개수) 다 - 보이지 않는 값의 수가 개수다."""
    f = {"check": "I", "action": "pick-bank", "not_selectable": ["a", "b", "c"]}
    assert _api.loop_module.fatal_key(f) == ("I", "pick-bank", 3)


def test_the_brief_says_the_gap_is_now_a_failure():
    brief = _api.brief_module
    plan = {"screens": [{"name": "home", "purpose": "p", "from": ["home"]}], "changes": []}
    report = {"passed": True, "fatal": [], "warning": [],
              "metrics": {"choice_values_kept": {"pick-bank": 67},
                          "choice_values_selectable": {"pick-bank": 67}}}
    md = brief.render_brief("r", 1, plan, [], report, ["home"], ".", ".")
    assert "### 선택지: 문서에 있는 것과 누를 수 있게 보인 것" in md
    assert "생성물에서 어느 상태에서도 보이지 않으면 검사 I 의 fatal 이다" in md


# 기술 계약(생성 · 재시도 · 다듬기가 함께 쓴다)이 검사 I 의 판정과 같은 말을 한다 (11-8b 3).
# 전에는 "(숨김·접힘은 괜찮다)" 까지만 말해, 접어 둔 목록을 펼치는 조작을 reveal 에 적으라는
# 것은 떨어진 시도의 재시도 블록에서야 알았다.
FOLDED = ("(숨김·접힘은 괜찮다). 다만 접거나 숨긴 값도 흐름 명세의 걸음이나 `reveal` 을 따라가면 "
          "어느 상태에서든 실제로 누를 수 있게 보여야 한다 — 접은 묶음마다(값이 하나뿐인 묶음도) "
          "펼치는 조작을 `reveal` 에 적어라.")


@pytest.mark.parametrize("task", ["transfer", "bill"])
def test_the_contract_says_folded_values_must_be_shown(task):
    p = _api.prompt_module
    for t in (p.load_template(task), p.load_refine_template(task)):
        assert " ".join(t.split()).count(FOLDED) == 1


# ===================================================================== #
# 실제로 걷는다 (pytest -m browser)
# ===================================================================== #
# 같은 data-action 형제 여덟. 보이는 것은 v1 · v2 둘이다.
#   v3 display:none        v4 visibility:hidden    v5 조상이 opacity:0
#   v6 크기 0 (높이 0, 넘침 숨김 조상 안)           v7 disabled
#   v8 닫힌 <details> 안
PAGE = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>
.screen{display:none}.screen.on{display:block}
.z{height:0;overflow:hidden}
</style></head><body><div id="phone">
<section class="screen on" data-screen="home">
<div class="list">
<button data-action="pick" data-v="v1">1</button>
<button data-action="pick" data-v="v2">2</button>
<button data-action="pick" data-v="v3" style="display:none">3</button>
<button data-action="pick" data-v="v4" style="visibility:hidden">4</button>
<span style="opacity:0"><button data-action="pick" data-v="v5">5</button></span>
<div style="height:0;width:0;overflow:hidden;display:inline-block"><button data-action="pick" data-v="v6" style="width:0;height:0;padding:0;border:0">6</button></div>
<button data-action="pick" data-v="v7" disabled>7</button>
<details><summary>더</summary><button data-action="pick" data-v="v8">8</button></details>
</div></section></div>
<script>window.__screen = () => 'home';</script></body></html>"""


@pytest.mark.browser
def test_the_probe_keeps_only_pressable_visible_values(server):
    import capture_baseline as C
    rel = ".pytest-outputs/choices_shown_probe.html"
    os.makedirs(os.path.join(ROOT, ".pytest-outputs"), exist_ok=True)
    io.open(os.path.join(ROOT, rel), "w", encoding="utf-8").write(PAGE)
    f = {"name": "probe", "derived_from_original": False, "required_ids": [],
         "steps": [{"screen": "home"}], "expect": {}}
    try:
        # 원본에서 무리였던 이름으로 준다 - 놓인 부모가 달라도 모두 센다 (생성물을 걸을 때와 같다)
        got = asyncio.run(_api.drive("%s/%s" % (C.BASE_URL, rel), f, errors=False,
                                     original_groups=["pick"]))
    finally:
        os.remove(os.path.join(ROOT, rel))
    home = got["screens"]["home"]
    assert sorted(home["choices"]["pick"]) == ["v%d" % i for i in range(1, 9)]
    assert sorted(home["choices_shown"]["pick"]) == ["v1", "v2"]


# 원본을 걷는 동안 보이지 않는 원본의 선택지 값 (11-8 측정). 이체 원본의 은행 시트는 [은행]
# 탭이 열린 채로 걷고 [증권사] 탭(29개)은 누르지 않는다. 공과금 원본은 모두 보인다.
HIDDEN_ON_THE_ORIGINALS_WALK = {"transfer": {"pick-bank": 29}, "bill": {}}


@pytest.mark.browser
@pytest.mark.parametrize("task", ["transfer", "bill"])
def test_what_the_originals_walk_shows(server, task):
    import capture_baseline as C
    t = _api.load_task(task)
    fl = _api.load_flow(None, task=task)
    snapshot = asyncio.run(_api.drive("%s/%s" % (C.BASE_URL, t["original"]), fl,
                                      errors=False))
    I = _api.i_choices_module
    groups = I.original_groups(snapshot, fl)
    shown = I.shown_values(snapshot)
    hidden = {a: sorted(v for v in vals if not I.present(v, shown))
              for a, vals in I.original_choices(snapshot).items() if a in groups}
    assert {a: len(v) for a, v in hidden.items() if v} == HIDDEN_ON_THE_ORIGINALS_WALK[task]
    if task == "transfer":
        assert all(v.endswith("증권") or "투자" in v or v in ("KB증권",) or "증권" in v
                   for v in hidden["pick-bank"]), hidden


@pytest.mark.browser
def test_an_original_judged_against_itself_still_passes_i(server):
    """원본 대 원본 - 원본에서 보이던 값은 원본에서도 보인다."""
    import capture_baseline as C
    t = _api.load_task("transfer")
    fl = _api.load_flow(None, task="transfer")
    url = "%s/%s" % (C.BASE_URL, t["original"])
    orig = asyncio.run(_api.drive(url, fl, errors=False))
    rep = asyncio.run(_api.drive(url, fl, errors=False,
                                 original_groups=_api.i_choices_module.original_groups(
                                     orig, fl)))
    html = io.open(os.path.join(ROOT, t["original"]), encoding="utf-8").read()
    report = _api.audit(orig, rep, html, html, fl)
    assert i_fatals(report) == []
    assert report["metrics"]["choice_values_shown_in_original"]["pick-bank"] == 38


# 모델 답(mock)의 흐름 명세 - Run 1 빌드는 은행 목록을 [다른 은행이에요] 뒤에만 보인다.
def test_the_mock_answers_declare_the_bank_list_reveal():
    model = _api.model_module
    for mode in model.MODES:
        if model.MOCK_TASK.get(mode) != "transfer":
            continue
        reveal = model.mock_base(mode)[1].get("reveal") or {}
        if mode == "reveal-undeclared":
            assert reveal == {}, mode            # 일부러 적지 않는 모드
        elif mode == "reveal":
            assert reveal == model.MOCK_REVEAL
        else:
            assert reveal["pick-bank"] == model.MOCK_BANK_REVEAL["pick-bank"], mode


@pytest.mark.browser
@pytest.mark.parametrize("mode,passed", [("pass", True), ("reveal", True),
                                         ("reveal-undeclared", False)])
def test_the_mock_runs_are_judged_on_what_they_show(server, mode, passed):
    import capture_baseline as C
    import json
    C.ensure_mock_input()
    summary, code = C.run_mock(["--mock", mode, "--attempts", "1"])
    assert summary["passed"] is passed
    report = json.load(io.open(os.path.join(
        summary["run_dir"], "attempt_%d.audit.json" % summary["attempts"][-1]["n"]),
        encoding="utf-8"))
    m = report["metrics"]
    if passed:
        assert m["choice_values_selectable"]["pick-bank"] == 67
        assert m["choice_values_not_selectable"] == {}
