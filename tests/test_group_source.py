r"""선택지 무리는 원본이 정한다 (11-9b).

검사 I 의 선택지 수집(probes.CHOICE_GROUPS)은 같은 부모 아래 같은 data-action 형제가
둘 이상인 것만 무리로 센다 - 뒤로가기처럼 화면마다 하나씩 놓인 버튼을 무리로 세지
않으려는 규칙이다. 그런데 그 규칙을 생성물에도 쓰면, 재설계가 원본의 무리를 분류마다
나눠 놓았을 때 항목이 하나뿐인 분류의 값을 세지 못한다. 공과금 예비 실행의 세 답이
모두 그것으로 메뉴 항목 6개를 잃었다 (모델은 6개를 그렸다).

어떤 이름이 무리인지는 원본이 정한다. 생성물을 걸을 때는 원본에서 무리였던 이름을
넘기고(i_choices.original_groups - 과제가 선택지가 아니라고 선언한 이름은 뺀다), 그
이름의 요소는 형제 수와 상관없이 모두 센다. 원본에서 무리가 아니던 이름은 전과 같이
형제 둘 이상일 때만 무리다. 걸음마다 모으는 곳과 reveal 을 따로 걸으며 모으는 곳이
같은 목록을 쓴다. 생성물만 보는 규칙("생성물 어딘가에서 무리가 된 이름")으로 하지
않는다 - 판정 기준이 생성물에 따라 달라진다.

`-m browser` 의 묶음은 고정물 페이지(fixtures/pages/i_one_per_section)를 실제로 걷는다.
저장된 공과금 답 셋의 재판정은 test_choice_roles 의 마지막 묶음이다.
"""
import asyncio
import io
import json
import os

import pytest

import _api
import capture_baseline as C
from test_audit_bugs import flow, row, snap
from test_choice_roles import BILL_DECLARED

ROOT = _api.ROOT_DIR
I = _api.i_choices_module
PAGE = "tests/fixtures/pages/i_one_per_section"
ITEMS = ["계좌이체", "납부하기", "자동납부", "환전"]


# --------------------------------------------------------------------- #
# 1. 원본에서 무리였던 이름
# --------------------------------------------------------------------- #
def test_the_original_groups_are_what_check_I_counts():
    orig = snap({"home": row("home", choices={"menu-item": ["가", "나"], "pw": ["1", "2"]}),
                 "menu": row("menu", choices={"menu-item": ["다"], "menu-chip": ["a", "b"],
                                              "one": ["하나"]})})
    # 값이 하나뿐인 이름은 무리가 아니다 (검사 I 와 같은 기준)
    assert I.original_groups(orig, flow(["home"])) == ["menu-chip", "menu-item", "pw"]


def test_declared_not_choices_are_left_out():
    orig = snap({"menu": row("menu", choices={"menu-item": ["가", "나"],
                                              "menu-chip": ["a", "b"], "menu-tab": ["x", "y"]})})
    got = I.original_groups(orig, flow(["menu"], not_choices=BILL_DECLARED))
    assert got == ["menu-item"]


def test_the_build_is_never_asked():
    """기준은 원본 스냅샷과 과제의 선언뿐이다 - 생성물의 모양으로 바뀌지 않는다."""
    import inspect
    assert list(inspect.signature(I.original_groups).parameters) == ["orig_snapshot", "flow"]


# --------------------------------------------------------------------- #
# 2. 생성물을 걷는다 (pytest -m browser)
# --------------------------------------------------------------------- #
ORIG = snap({"menu": row("menu", choices={"menu-item": ITEMS}),
             "done": row("done")})


def page_flow():
    return _api.load_flow(os.path.join(ROOT, *(PAGE + ".json").split("/")))


def walk_page(groups):
    f = page_flow()
    rep = asyncio.run(_api.drive("%s/%s.html" % (C.BASE_URL, PAGE), f, errors=False,
                                 original_groups=groups))
    html = io.open(os.path.join(ROOT, *(PAGE + ".html").split("/")), encoding="utf-8").read()
    report = _api.audit(ORIG, rep, "", html, f)
    return rep, report


def i_fatal(report):
    return [(x["action"], x["missing"]) for x in report["fatal"] if x["check"] == "I"]


@pytest.fixture(scope="module")
def walked(server):
    return {"old": walk_page(()), "new": walk_page(I.original_groups(ORIG, page_flow()))}


@pytest.mark.browser
def test_old_rule_misses_values_placed_one_per_section(walked):
    """(가) 고치기 전과 같은 규칙(빈 목록) - 형제가 없어 하나도 세지 못한다."""
    rep, report = walked["old"]
    assert "menu-item" not in rep["screens"]["menu"]["choices"]
    assert "menu-item" not in rep["revealed"]["menu-item"]["choices"]
    assert i_fatal(report) == [("menu-item", ITEMS)]


@pytest.mark.browser
def test_original_groups_are_counted_however_the_build_places_them(walked):
    """(가) 원본의 무리 이름을 넘기면 걸음마다 둘, 펼친 뒤 넷 - 모두 센다."""
    rep, report = walked["new"]
    assert rep["screens"]["menu"]["choices"]["menu-item"] == ITEMS[:2]
    assert sorted(rep["revealed"]["menu-item"]["choices"]["menu-item"]) == sorted(ITEMS)
    assert i_fatal(report) == []
    m = report["metrics"]
    assert m["choice_values_kept"] == {"menu-item": 4}
    assert m["choice_values_selectable"] == {"menu-item": 4}


@pytest.mark.browser
def test_a_name_that_was_not_a_group_does_not_become_one(walked):
    """(나) 뒤로(back)는 두 화면에 하나씩 있다. 원본에서 무리가 아니었으므로 넘기는
    목록에 없고, 형제가 없어 무리가 되지 않는다."""
    for key in ("old", "new"):
        rep, _report = walked[key]
        for visit, r in rep["screens"].items():
            assert "back" not in r["choices"], (key, visit)
        assert "back" not in rep["revealed"]["menu-item"]["choices"], key
