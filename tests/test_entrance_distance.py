r"""과제 밖 입구까지의 거리 (11-8 2) - 기록만 한다.

검사 K 는 입구가 걷는 동안 누를 수 있게 **남아 있는가** 를 본다. 남아 있는 것과 찾을 수
있는 것은 다르다 (Findlater, McGrenere 2007) - 그래서 입구마다 원본과 생성물에서 각각

    visit      처음 누를 수 있게 보인 방문(흐름의 걸음 이름)
    reveal     그 입구를 보려고 누른 펼치기(흐름 명세의 reveal) 횟수. 바로 보이면 0
    scroll_px  그 화면 맨 위에서 입구 전체가 창 안에 들어오기까지 내려야 하는 거리.
               첫 화면 안이면 0

을 남긴다 (summary.json 의 entrance_distance, 설명서의 "과제 밖 입구" 표). 검사 K 가 이미
걷는 걸음과 reveal 에서 잰다 - 새 걷기는 없다. 판정 · 고르기 문지기에는 쓰지 않고, 기준선
· 합격선도 정하지 않는다 (정하면 그것이 또 규칙이 된다).

  .\.venv\Scripts\python.exe -m pytest tests/test_entrance_distance.py
  .\.venv\Scripts\python.exe -m pytest tests/test_entrance_distance.py -m browser
"""
import asyncio
import io
import json
import os

import pytest

import _api
from senior_ui.audit.checks import k_entrances as K
from test_audit_bugs import done_row, flow, row, snap
from test_entrances import WANT, items, k_fatals

ROOT = _api.ROOT_DIR


def seen_at(task, visit="start", scroll=0, drop=(), hidden=(), rows=None):
    """`{action: {visible, text, aria, visit, reveal, scroll_px}}` - drive 가 이제 남기는 모양.
    보인 입구에만 visit · reveal · scroll_px 가 붙는다 (drive.mark_entrances)."""
    out = {}
    for e in items(task):
        if e["id"] in drop:
            continue
        r = {"visible": e["id"] not in hidden, "text": e["label"], "aria": e["label"],
             "scroll_px": scroll if e["id"] not in hidden else None}
        if r["visible"]:
            r.update(visit=visit, reveal=0)
        out[e["action"]] = r
    for action, extra in (rows or {}).items():
        out[action] = dict(out.get(action) or {}, **extra)
    return out


def judge(rep_seen, orig_seen=None, revealed=None, steps=("start", "middle", "done")):
    f = flow(list(steps))
    screens = {s: row(s) for s in steps[:-1]}
    screens[steps[-1]] = done_row(steps[-1])
    orig = snap(dict(screens), entrances_seen=seen_at("transfer") if orig_seen is None
                else orig_seen)
    rep = snap(dict(screens), entrances_seen=rep_seen)
    if revealed is not None:
        rep["revealed"] = revealed
    return _api.audit(orig, rep, "<html></html>", "<html></html>", f)


def distance(report, eid):
    return {d["id"]: d for d in report["metrics"]["entrance_distance"]}[eid]


# ===================================================================== #
# 1. 기록의 모양 (손으로 만든 스냅샷)
# ===================================================================== #
def test_every_listed_entrance_gets_a_row_in_task_order():
    report = judge(seen_at("transfer"))
    rows = report["metrics"]["entrance_distance"]
    assert [d["id"] for d in rows] == [e["id"] for e in items("transfer")]
    first = rows[0]
    assert (first["label"], first["action"]) == ("메시지", "oos-message")
    assert first["original"] == {"visit": "start", "reveal": 0, "scroll_px": 0}
    assert first["build"] == {"visit": "start", "reveal": 0, "scroll_px": 0}


def test_the_first_visit_and_the_scroll_distance_are_kept_side_by_side():
    orig = seen_at("transfer", rows={"oos-share": {"visit": "done", "scroll_px": 0}})
    rep = seen_at("transfer", rows={"oos-share": {"visit": "middle", "scroll_px": 1206}})
    d = distance(judge(rep, orig_seen=orig), "T28")
    assert d["original"] == {"visit": "done", "reveal": 0, "scroll_px": 0}
    assert d["build"] == {"visit": "middle", "reveal": 0, "scroll_px": 1206}


def test_an_entrance_seen_only_after_a_reveal_counts_its_clicks():
    """정답 걸음에서는 숨어 있고, reveal.oos-more 를 두 번 눌러야 보인다."""
    rep = seen_at("transfer", hidden=("T1",))
    after = seen_at("transfer", visit="middle", rows={"oos-message": {"reveal": 2}})
    report = judge(rep, revealed={"oos-more": {"at": "middle", "choices": {},
                                               "entrances_seen": after}})
    assert k_fatals(report) == []
    assert distance(report, "T1")["build"] == {"visit": "middle", "reveal": 2,
                                                "via": "oos-more", "scroll_px": 0}


def test_of_two_reveals_the_one_with_fewer_clicks_is_written():
    rep = seen_at("transfer", hidden=("T1",))
    two = seen_at("transfer", visit="start", rows={"oos-message": {"reveal": 2}})
    one = seen_at("transfer", visit="middle", rows={"oos-message": {"reveal": 1}})
    report = judge(rep, revealed={
        "a-two": {"at": "start", "choices": {}, "entrances_seen": two},
        "b-one": {"at": "middle", "choices": {}, "entrances_seen": one}})
    assert distance(report, "T1")["build"]["via"] == "b-one"


def test_a_missing_entrance_has_no_build_value_and_one_the_original_did_not_show_none():
    orig = seen_at("transfer", hidden=("T27",))
    rep = seen_at("transfer", drop=("T28",))
    report = judge(rep, orig_seen=orig)
    assert distance(report, "T28")["build"] is None
    assert distance(report, "T27")["original"] is None


def test_an_old_snapshot_without_the_new_fields_still_gives_rows():
    """수집이 visit · scroll_px 를 남기기 전의 스냅샷 - 칸은 null 이고 멈추지 않는다."""
    old = {e["action"]: {"visible": True, "text": e["label"], "aria": e["label"]}
           for e in items("transfer")}
    d = distance(judge(old, orig_seen=old), "T1")
    assert d["original"] == {"visit": None, "reveal": 0, "scroll_px": None}


# ===================================================================== #
# 2. 기록만 한다 - 판정 · 고르기에 쓰지 않는다
# ===================================================================== #
def test_the_distance_does_not_change_the_judgement():
    near = judge(seen_at("transfer"))
    far = judge(seen_at("transfer", visit="done", scroll=9999))
    assert near["passed"] is far["passed"] is True
    assert near["fatal"] == far["fatal"] and near["warning"] == far["warning"]


def test_no_gate_or_ordering_reads_the_distance():
    rule = io.open(_api.DEFAULT_SELECTION_RULE, encoding="utf-8").read()
    assert "entrance_distance" not in rule and "scroll_px" not in rule
    for mod in ("collect", "rule", "report"):
        path = os.path.join(ROOT, "senior_ui", "select", mod + ".py")
        assert "entrance_distance" not in io.open(path, encoding="utf-8").read(), mod


def test_the_reason_is_written_next_to_the_code():
    text = io.open(K.__file__, encoding="utf-8").read()
    assert "남아 있는 것과 찾을 수 있는 것은 다르다 (Findlater, McGrenere 2007)" in text


# ===================================================================== #
# 3. summary.json 과 설명서
# ===================================================================== #
from test_restructure_bugs import fake_run_env, make_args, out_root, passing_report  # noqa
from test_visual_refine import PLAN_THEN_GOOD, run_with  # noqa

ROWS = [{"id": "T1", "label": "메시지", "action": "oos-message",
         "original": {"visit": "home", "reveal": 0, "scroll_px": 0},
         "build": {"visit": "home", "reveal": 1, "via": "oos-more", "scroll_px": 312}},
        {"id": "T28", "label": "공유", "action": "oos-share",
         "original": {"visit": "done", "reveal": 0, "scroll_px": 40},
         "build": None},
        {"id": "T27", "label": "추가이체", "action": "oos-again",
         "original": None, "build": {"visit": "done", "reveal": 0, "scroll_px": 0}}]


def report_with_rows():
    r = passing_report()
    r["metrics"]["entrance_distance"] = ROWS
    return r


def test_the_summary_keeps_the_final_builds_distance(fake_run_env, out_root):
    fake_run_env.setattr(_api.loop_module, "run_audit", lambda *a, **kw: report_with_rows())
    code, s, sent, d = run_with(fake_run_env, out_root, PLAN_THEN_GOOD)
    assert code == 0 and s["entrance_distance"] == ROWS
    on_disk = json.load(io.open(os.path.join(d, "summary.json"), encoding="utf-8"))
    assert on_disk["entrance_distance"] == ROWS


def test_a_summary_without_a_judged_build_has_null_distance(fake_run_env, out_root):
    """검사 K 가 물러난 리포트(손 스냅샷 · 옛 스냅샷)에는 칸이 없다 - null 로 남긴다."""
    code, s, sent, d = run_with(fake_run_env, out_root, PLAN_THEN_GOOD)
    assert s["entrance_distance"] is None


def test_the_brief_has_the_entrance_table_next_to_the_original():
    brief = _api.brief_module
    plan = {"screens": [{"name": "home", "purpose": "p", "from": ["home"]}], "changes": []}
    md = brief.render_brief("r", 1, plan, [], report_with_rows(), ["home"], ".", ".")
    assert "## 과제 밖 입구" in md
    assert "남아 있는 것과 찾을 수 있는 것은 다르다 (Findlater, McGrenere 2007)" in md
    assert "기준선 · 합격선은 정하지 않았다" in md
    assert ("| 입구 | 원본 화면 | 원본 펼치기 | 원본 스크롤 px | 재설계 화면 | 재설계 펼치기 "
            "| 재설계 스크롤 px |") in md
    assert ("| T1 메시지 (`oos-message`) | `home` | 0 | 0 | `home` | 1 (reveal "
            "`oos-more`) | 312 |") in md
    assert "| T28 공유 (`oos-share`) | `done` | 0 | 40 | 보이지 않음 | - | - |" in md
    assert "| T27 추가이체 (`oos-again`) | 원본에서 보이지 않음 | - | - | `done` | 0 | 0 |" in md


def test_a_brief_without_the_rows_has_no_entrance_table():
    brief = _api.brief_module
    plan = {"screens": [{"name": "home", "purpose": "p", "from": ["home"]}], "changes": []}
    md = brief.render_brief("r", 1, plan, [], passing_report(), ["home"], ".", ".")
    assert "## 과제 밖 입구" not in md


# ===================================================================== #
# 4. 실제로 잰다 (pytest -m browser)
# ===================================================================== #
# 스크롤 거리를 아는 페이지. 화면 안의 .body 가 스크롤되고(창 높이 844), 입구 셋:
#   oos-top    첫 화면 안                                -> 0
#   oos-deep   .body 안 위에서 2000px, 높이 50           -> 2050 - 844 = 1206
#   oos-fixed  창 아래에 고정된 탭 (position: fixed)     -> 0
# 걷기가 .body 를 500px 내린 뒤에 재도 같은 값이어야 한다 - 화면 맨 위가 기준이다.
PAGE = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>
html,body{margin:0}
.screen{display:none;position:absolute;inset:0}
.screen.on{display:block}
.body{position:absolute;top:0;left:0;right:0;height:844px;overflow-y:auto}
.gap{height:2000px}
button{display:block;height:50px;margin:0;border:0;padding:0}
.tab{position:fixed;bottom:0;left:0;height:60px}
</style></head><body><div id="phone">
<section class="screen on" data-screen="home"><div class="body" id="b">
<button data-action="oos-top">위</button><div class="gap" style="height:1950px"></div>
<button data-action="oos-deep">아래</button><div class="gap"></div>
<button data-action="go" onclick="">다음</button>
</div><button class="tab" data-action="oos-fixed">탭</button></section>
<section class="screen" data-screen="next"><p>다음 화면</p></section>
</div><script>
let s = 'home';
window.__screen = () => s;
document.getElementById('b').scrollTop = 500;
document.getElementById('phone').addEventListener('click', e => {
  const el = e.target.closest('[data-action]'); if (!el) return;
  if (el.dataset.action === 'go') {
    s = 'next';
    document.querySelectorAll('.screen').forEach(x => x.classList.toggle('on', x.dataset.screen === s));
  }
});
</script></body></html>"""


@pytest.mark.browser
def test_the_probe_measures_from_the_top_of_the_screen(server):
    import capture_baseline as C
    rel = ".pytest-outputs/entrance_distance_probe.html"
    os.makedirs(os.path.join(ROOT, ".pytest-outputs"), exist_ok=True)
    io.open(os.path.join(ROOT, rel), "w", encoding="utf-8").write(PAGE)
    f = {"name": "probe", "derived_from_original": False, "required_ids": [],
         "steps": [{"screen": "home"}, {"screen": "next", "click": "[data-action='go']"}],
         "expect": {}}
    try:
        got = asyncio.run(_api.drive("%s/%s" % (C.BASE_URL, rel), f, errors=False))
    finally:
        os.remove(os.path.join(ROOT, rel))
    e = got["entrances_seen"]
    assert (e["oos-top"]["visit"], e["oos-top"]["scroll_px"]) == ("home", 0)
    assert (e["oos-deep"]["visit"], e["oos-deep"]["scroll_px"]) == ("home", 1206)
    assert (e["oos-fixed"]["visit"], e["oos-fixed"]["scroll_px"]) == ("home", 0)
    assert all(r["reveal"] == 0 for r in e.values())


def final_audit(summary):
    path = os.path.join(summary["run_dir"],
                        "attempt_%d.audit.json" % summary["attempts"][-1]["n"])
    return json.load(io.open(path, encoding="utf-8"))


@pytest.mark.browser
@pytest.mark.parametrize("mode,reveal", [("pass", 0), ("entrances-reveal", 1),
                                         ("entrances-folded", 1)])
def test_a_mock_run_writes_the_distance_table(server, mode, reveal):
    """mock 의 입구 블록은 첫 화면에 바로(pass), [다른 메뉴] 를 눌러야(reveal), 접힌
    <details> 를 펼쳐야(folded) 보인다. 원본은 모두 바로 보인다."""
    import capture_baseline as C
    C.ensure_mock_input()
    summary, code = C.run_mock(["--mock", mode, "--attempts", "1"])
    assert code == 0 and summary["passed"] is True
    rows = summary["entrance_distance"]
    assert rows == final_audit(summary)["metrics"]["entrance_distance"]
    assert [d["id"] for d in rows] == [e["id"] for e in items("transfer")]
    assert all(d["original"]["reveal"] == 0 and d["original"]["visit"]
               and isinstance(d["original"]["scroll_px"], int) for d in rows)
    assert {d["build"]["reveal"] for d in rows} == {reveal}
    brief = io.open(os.path.join(summary["run_dir"], "designer_brief.md"),
                    encoding="utf-8").read()
    assert "## 과제 밖 입구" in brief and brief.count("(`oos-") == len(rows)


@pytest.mark.browser
def test_the_bill_mock_run_writes_its_32_rows(server):
    import capture_baseline as C
    summary, code = C.run_mock(["--task", "bill", "--mock", "bill-identity",
                                "--attempts", "1"])
    assert code == 0
    rows = summary["entrance_distance"]
    assert len(rows) == len(WANT["bill"]) == 32
    # 원본을 그대로 돌려주는 mock - 원본과 생성물의 값이 같다
    assert all(d["original"] == d["build"] for d in rows)
