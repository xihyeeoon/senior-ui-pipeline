r"""선택지 아님 선언 - 과제 파일의 not_choices (11-9, 연구자 결정 2026-10-07).

공과금 예비 실행(outputs/restructure_auto/20261007-103023-bill)에서 검사 I 가
menu-chip(60) · menu-tab(7) 을 선택지로 세어 시도 2 · 3 · 4 가 같은 이유로 떨어졌다.
원본(inputs/original_bill.html)에서 이 둘은 누르면 scrollMenuTo 로 스크롤만 한다 -
메뉴 항목(menu-item 289)을 찾아가는 수단이지 고르는 대상이 아니다. 연구자는 이 둘을
"선택지 아님" 으로 선언했다.

  과제 파일   tasks/bill.json 의 not_choices = {data-action: 이유}
  판정 입력   judged_flow · load_flow 가 그 선언을 판정 흐름에 붙인다 (모델이 적은
              not_choices 는 버린다)
  검사 I      선언된 무리를 판정에서 빼고 지표 choice_groups_not_choices 로 남긴다
  프롬프트    선언된 무리만 받치는 배열(MENU_TABS)은 넣어 주되 "빠뜨리지 말고
              참조하라" 에서 뺀다
  설명서      "선택지가 아니라고 선언한 무리와 이유" 표

allowed_removals(flows/allowed_removals.json - 일부러 뺀 값)와는 뜻이 다르다. 그쪽은
"선택지인데 빼도 된다" 이고 이쪽은 "처음부터 선택지가 아니다" 다.

`-m browser` 의 마지막 묶음은 저장된 공과금 답 셋(tests/fixtures/real_runs/bill_sol)을
바뀐 검사기로 다시 판정한다. 모델은 부르지 않는다.
"""
import asyncio
import io
import json
import os

import pytest

import _api
import capture_baseline as C
from test_audit_bugs import done_row, flow, row, snap
from test_judge_inputs import model_flow

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T = _api.tasks_module
F = _api.flow_module
reply = _api.reply_module
preserve = _api.preserve_module

BILL_DECLARED = {"menu-chip": "분류로 스크롤하는 표지판 — 찾아가는 수단",
                 "menu-tab": "분야로 스크롤하는 탭 — 찾아가는 수단"}


# --------------------------------------------------------------------- #
# 1. 과제 파일
# --------------------------------------------------------------------- #
def test_the_bill_task_declares_the_two_navigation_groups():
    assert _api.load_task("bill")["not_choices"] == BILL_DECLARED


def test_the_transfer_task_declares_nothing():
    """tab-bank · tab-sec 는 이름이 달라 한 무리가 아니다 - 선언할 것이 없다."""
    assert _api.load_task("transfer")["not_choices"] == {}


def test_not_choices_is_not_the_allowed_removals():
    """두 선언은 다른 파일 · 다른 칸이다. 섞이면 "빼도 되는 값" 이 "선택지가 아닌
    무리" 로 읽히거나 그 반대가 된다."""
    for task in ("bill", "transfer"):
        assert "not_choices" not in _api.load_allowed_removals(task)
        assert "allowed_removals" not in _api.load_task(task)


@pytest.mark.parametrize("bad", [["menu-chip"], {"menu-chip": ""},
                                 {"menu-chip": {"reason": "x"}}])
def test_a_malformed_declaration_stops(monkeypatch, tmp_path, bad):
    """이유 없는 선언은 받지 않는다 - 무리 하나를 검사에서 빼는 일이다."""
    task = json.load(io.open(T.task_path("bill"), encoding="utf-8"))
    task["not_choices"] = bad
    (tmp_path / "bill.json").write_text(json.dumps(task, ensure_ascii=False),
                                        encoding="utf-8")
    monkeypatch.setattr(T, "TASKS_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="not_choices"):
        T.load_task("bill")


# --------------------------------------------------------------------- #
# 2. 판정 입력 - 과제의 선언이 흐름에 붙는다
# --------------------------------------------------------------------- #
def test_judged_flow_attaches_the_tasks_declaration():
    out = _api.judged_flow(model_flow(), task="bill")
    assert out["not_choices"] == BILL_DECLARED
    assert out["model_claims_dropped"] == []
    assert _api.judged_flow(model_flow(), task="transfer")["not_choices"] == {}


def test_a_models_own_declaration_is_dropped():
    """모델이 흐름 명세에 not_choices 를 적으면 검사 I 를 끄는 장치가 된다."""
    mine = {"menu-item": "찾아가는 수단", "pick-bill": "x"}
    out = _api.judged_flow(model_flow(not_choices=mine), task="bill")
    assert out["not_choices"] == BILL_DECLARED
    assert "not_choices" in out["model_claims_dropped"]
    out = _api.judged_flow(model_flow(not_choices=mine), task="transfer")
    assert out["not_choices"] == {}


def test_the_researchers_flow_carries_the_declaration_too():
    """원본 대 원본(flows/original_bill.json)도 같은 과제의 같은 선언으로 판정한다."""
    assert _api.load_flow(None, task="bill")["not_choices"] == BILL_DECLARED
    assert _api.load_flow(None, task="transfer")["not_choices"] == {}


# --------------------------------------------------------------------- #
# 3. 검사 I - 선언된 무리를 판정에서 뺀다
# --------------------------------------------------------------------- #
NAV_ORIG = snap({"start": row("start", choices={
    "menu-chip": ["은행::이체", "은행::조회"], "menu-tab": ["은행", "카드"],
    "menu-item": ["계좌이체", "납부하기", "자동납부"]})})


def nav_audit(html, **kw):
    return _api.audit(NAV_ORIG, snap({"start": done_row("start")}), "", html,
                      flow(["start"], **kw))


def test_declared_groups_are_not_judged():
    """빌드에 칩도 탭도 없다. 선언하면 fatal 이 아니고, 지표에 이유와 남는다."""
    report = nav_audit("<html>계좌이체 납부하기 자동납부</html>",
                       not_choices=BILL_DECLARED)
    assert report["fatal"] == []
    m = report["metrics"]
    assert m["choice_groups_original"] == {"menu-item": 3}
    assert m["choice_values_kept"] == {"menu-item": 3}
    assert m["choice_values_selectable"] == {"menu-item": 0}
    assert m["choice_values_missing"] == {}
    assert m["choice_groups_not_choices"] == {
        "menu-chip": {"values": 2, "reason": BILL_DECLARED["menu-chip"]},
        "menu-tab": {"values": 2, "reason": BILL_DECLARED["menu-tab"]}}
    stood = m["checks_stood_down"]
    assert any(s.startswith("I/menu-chip ") and BILL_DECLARED["menu-chip"] in s
               for s in stood), stood


def test_without_the_declaration_the_same_build_fails():
    """고치기 전과 같다 - 칩 · 탭이 선택지로 세어져 fatal 둘."""
    report = nav_audit("<html>계좌이체 납부하기 자동납부</html>")
    assert sorted(f["action"] for f in report["fatal"]) == ["menu-chip", "menu-tab"]
    assert report["metrics"]["choice_groups_not_choices"] == {}


def test_the_declaration_does_not_cover_other_groups():
    report = nav_audit("<html>계좌이체 납부하기</html>", not_choices=BILL_DECLARED)
    assert [(f["check"], f["action"], f["missing"]) for f in report["fatal"]] == \
        [("I", "menu-item", ["자동납부"])]


def test_a_declared_name_the_original_does_not_have_is_ignored():
    """선언은 원본에 그 무리가 있을 때만 지표에 남는다 - 없는 이름을 남기면 원본에
    없던 무리가 있었던 것처럼 읽힌다."""
    report = nav_audit("<html>계좌이체 납부하기 자동납부 은행 카드 은행::이체 은행::조회"
                       "</html>", not_choices={"menu-tab": "x", "tab-bank": "y"})
    assert set(report["metrics"]["choice_groups_not_choices"]) == {"menu-tab"}


# --------------------------------------------------------------------- #
# 4. 프롬프트 - 선언된 무리만 받치는 배열은 참조를 요구하지 않는다
# --------------------------------------------------------------------- #
def bill_snapshot():
    path = os.path.join(ROOT, "tests", "baseline", "bill", "original_vs_original",
                        "snapshots.json")
    return json.load(io.open(path, encoding="utf-8"))["orig"]


def bill_html():
    return io.open(os.path.join(ROOT, "inputs", "original_bill.html"), encoding="utf-8").read()


def test_only_menu_tabs_backs_nothing_but_declared_groups():
    snap_, html = bill_snapshot(), bill_html()
    data = preserve.preserved_data(snap_, html)
    assert "MENU_TABS" in data                   # 블록에는 그대로 들어간다
    assert preserve.optional_names(snap_, html, BILL_DECLARED) == ["MENU_TABS"]
    assert preserve.optional_names(snap_, html, {}) == []


def test_the_bill_choices_block_separates_the_declared_groups():
    block = _api.choices_block(bill_snapshot(), bill_html(), not_choices=BILL_DECLARED)
    head, _, declared = block.partition("선택지가 아니라고 과제가 정한 반복 요소")
    assert "menu-chip" not in head and "menu-tab" not in head
    required = [l for l in head.splitlines() if "window.PRESERVED.MENU_BANK" in l][0]
    assert "MENU_TABS" not in required
    assert "위 이름을 하나도 빠뜨리지 말고 참조하라" in head
    assert "menu-chip — 60개: " + BILL_DECLARED["menu-chip"] in declared
    assert "menu-tab — 7개 (MENU_TABS 7): " + BILL_DECLARED["menu-tab"] in declared
    assert "window.PRESERVED.MENU_TABS (7개)" in declared


def test_without_a_declaration_the_block_is_as_before():
    snap_, html = bill_snapshot(), bill_html()
    assert _api.choices_block(snap_, html) == _api.choices_block(snap_, html,
                                                                 not_choices={})
    assert "선택지가 아니라고" not in _api.choices_block(snap_, html)


def test_an_unread_optional_name_is_not_a_format_problem():
    data = {"MENU_BANK": ["가", "나"], "MENU_TABS": ["은행", "카드"]}
    html = "<script>const P = window.PRESERVED; P.MENU_BANK.map(draw);</script>"
    assert reply.preserved_problems(html, data, optional=["MENU_TABS"]) == []
    problems = reply.preserved_problems(html, data)
    assert len(problems) == 1 and "MENU_TABS" in problems[0]
    # 선택지를 받치는 이름은 여전히 읽어야 한다
    html = "<script>const P = window.PRESERVED; P.MENU_TABS.map(draw);</script>"
    problems = reply.preserved_problems(html, data, optional=["MENU_TABS"])
    assert len(problems) == 1 and "MENU_BANK" in problems[0]


# --------------------------------------------------------------------- #
# 5. 설명서 - 선택지 절의 표
# --------------------------------------------------------------------- #
from test_agent_stages import BRIEF_REPORT, render, section  # noqa: E402


def test_the_brief_lists_the_declared_groups_with_reasons(tmp_path):
    report = json.loads(json.dumps(BRIEF_REPORT))
    report["metrics"]["choice_groups_not_choices"] = {
        "menu-chip": {"values": 60, "reason": BILL_DECLARED["menu-chip"]},
        "menu-tab": {"values": 7, "reason": BILL_DECLARED["menu-tab"]}}
    md = section(render(tmp_path, report=report), "사람이 확인할 것")
    part = md[md.index("### 선택지가 아니라고 선언한 무리"):]
    assert "| `menu-chip` | 60 | 분류로 스크롤하는 표지판 — 찾아가는 수단 |" in part
    assert "| `menu-tab` | 7 | 분야로 스크롤하는 탭 — 찾아가는 수단 |" in part


def test_the_brief_says_none_when_nothing_is_declared(tmp_path):
    md = section(render(tmp_path), "사람이 확인할 것")
    part = md[md.index("### 선택지가 아니라고 선언한 무리"):]
    assert part.split("\n\n")[1].strip().endswith("없음")


# --------------------------------------------------------------------- #
# 6. 저장된 공과금 답 셋을 바뀐 검사기로 (pytest -m browser)
# --------------------------------------------------------------------- #
REAL = os.path.join(ROOT, "tests", "fixtures", "real_runs", "bill_sol")
OUT = os.path.join(ROOT, ".pytest-outputs", "real_runs", "bill_sol")

# 세 답 모두 메뉴 항목 6개가 남는다. 모델은 6개를 그렸다 - 항목이 하나뿐인 분류의
# 항목이라 분류마다 따로 만든 목록 안에서 같은 data-action 형제가 없고, 걷기의 선택지
# 수집(probes.CHOICE_GROUPS)은 형제가 둘 이상인 것만 센다. 글자 경계 규칙과는 무관하다.
SINGLE_ITEM_SECTIONS = ["나의 금융 이용현황", "보험상담신청", "보험상품안내",
                        "신한 슈퍼SOL 사용팁", "증권재발행", "진행중인 이벤트"]


def build_like_the_loop(n, base_url):
    import shutil
    text = io.open(os.path.join(REAL, "attempt_%d.response.txt" % n),
                   encoding="utf-8").read()
    html, flow_, _ = _api.parse_reply(text)
    flow_.setdefault("name", "auto")
    reply.accept_done_alias(flow_)
    task = _api.load_task("bill")
    data = json.load(io.open(os.path.join(REAL, "preserved.json"), encoding="utf-8"))
    problems = (reply.validate_flow(flow_, html, F.required_errors("bill"),
                                    task["done_expect"])
                + reply.preserved_problems(html, data, optional=["MENU_TABS"]))
    build, _ = preserve.inject(html, data)
    d = os.path.join(OUT, "attempt_%d" % n)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    html_path, flow_path = os.path.join(d, "attempt.html"), os.path.join(d, "attempt.flow.json")
    io.open(html_path, "w", encoding="utf-8", newline="\n").write(build)
    io.open(flow_path, "w", encoding="utf-8", newline="\n").write(
        json.dumps(flow_, ensure_ascii=False, indent=2))
    rel = os.path.relpath(html_path, ROOT).replace(os.sep, "/")
    return problems, html_path, flow_path, "%s/%s" % (base_url, rel)


@pytest.fixture(scope="module")
def bill_verdicts(server):
    orig_html = bill_html()
    orig_url = "%s/%s" % (C.BASE_URL, C.BILL_ORIGINAL_REL)
    snap_ = asyncio.run(_api.drive(orig_url, _api.load_flow(None, task="bill"),
                                   errors=False))
    out = {}
    for n in (2, 3, 4):
        problems, html_path, flow_path, url = build_like_the_loop(n, C.BASE_URL)
        report = _api.audit_call_module.run_audit(
            snap_, orig_html, html_path, flow_path, url, None, "wireframe",
            original_url=orig_url, task="bill")
        out[n] = {"problems": problems, "report": report}
    return out


@pytest.mark.browser
@pytest.mark.parametrize("n", [2, 3, 4])
def test_saved_bill_replies_fail_only_on_the_single_item_sections(bill_verdicts, n):
    """고치기 전: 시도 2 는 I 셋(menu-chip 60 · menu-item 6 · menu-tab 1), 시도 3 · 4 는
    I 둘(menu-chip 60 · menu-item 6) 이었다."""
    v = bill_verdicts[n]
    assert v["problems"] == []
    report = v["report"]
    assert [(f["check"], f.get("action"), f.get("missing")) for f in report["fatal"]] == \
        [("I", "menu-item", SINGLE_ITEM_SECTIONS)]
    m = report["metrics"]
    assert set(m["choice_groups_original"]) == {"menu-item", "pick-bill", "pw"}
    assert m["choice_groups_not_choices"] == {
        "menu-chip": {"values": 60, "reason": BILL_DECLARED["menu-chip"]},
        "menu-tab": {"values": 7, "reason": BILL_DECLARED["menu-tab"]}}
    assert m["choice_values_kept"]["menu-item"] == 283
    assert not [w for w in report["warning"] if "menu-tab" in w["detail"]]
