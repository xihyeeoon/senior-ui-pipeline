r"""과제에 묶이지 않는다 - 이체 말고 다른 과제(공과금)도 같은 파이프라인으로 돈다.

과제마다 다른 것은 과제 파일(tasks/<과제>.json)에 있다. 여기 있는 테스트는 그
파일을 읽어야 할 자리가 이체 값을 코드에서 바로 읽던 것(11번 단계에서 찾은 이체
전용 가정)의 재현이다. 브라우저도 모델도 부르지 않는다.

이체 쪽은 바뀌지 않아야 하므로, 과제를 주지 않은 호출이 전과 같은 값을 내는지도
함께 본다.
"""
import io
import json
import os

import pytest

import _api

F = _api.flow_module
T = _api.tasks_module

TRANSFER_TRUTH = {"ACCOUNT": "110234567890", "AMOUNT": "32000", "BANK": "신한",
                  "NAME": "김철수", "AMOUNT_SHOWN": "32,000",
                  "ACCOUNT_WRONG": "110234567891", "BANK_WRONG": "국민"}


@pytest.fixture
def demo_task(tmp_path, monkeypatch):
    """tasks/ 를 임시 폴더로 옮기고 과제 셋(이체 사본 · 공과금 사본 · demo)을
    둔다. demo 는 truth 에 AMOUNT · CODE 만 요구하는 과제다."""
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    for name in ("transfer", "bill"):
        (tasks / ("%s.json" % name)).write_text(
            io.open(T.task_path(name), encoding="utf-8").read(), encoding="utf-8")
    flow = tmp_path / "demo_flow.json"
    flow.write_text(json.dumps({
        "name": "demo", "task": "demo",
        "truth": {"AMOUNT": "500", "CODE": "77"},
        "steps": [{"screen": "home"}], "error_paths": []}), encoding="utf-8")
    (tasks / "demo.json").write_text(json.dumps({
        "id": "demo", "description": ["demo"], "original": "inputs/original_bill.html",
        "flow": str(flow).replace(os.sep, "/"),
        "done_expect": [["#dn-x", "{AMOUNT_SHOWN}"]],
        "required_truth": ["AMOUNT", "CODE"], "required_error_paths": []}),
        encoding="utf-8")
    monkeypatch.setattr(T, "TASKS_DIR", str(tasks))
    F._task_truth.clear()
    F._task_errors.clear()
    yield str(flow)
    F._task_truth.clear()
    F._task_errors.clear()


# --------------------------------------------------------------------- #
# 1. 정답 값 (flow.py)
# --------------------------------------------------------------------- #
def test_a_flow_needs_only_its_tasks_truth_keys(demo_task):
    """고치기 전: truth 에 ACCOUNT · BANK · NAME 이 없으면 어느 과제든 멈췄다."""
    flow = _api.load_flow(demo_task)
    assert flow["truth"]["CODE"] == "77"
    assert flow["truth"]["AMOUNT_SHOWN"] == "500"


def test_a_missing_key_of_the_task_still_stops(demo_task, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"name": "bad", "task": "demo",
                               "truth": {"AMOUNT": "500"}, "steps": []}),
                   encoding="utf-8")
    with pytest.raises(ValueError, match="CODE"):
        _api.load_flow(str(bad))


def test_the_default_flow_follows_the_task(demo_task):
    """고치기 전: load_flow(None) 은 과제와 상관없이 이체 흐름이었다."""
    assert _api.load_flow(None, task="demo")["name"] == "demo"
    assert _api.load_flow(None)["name"] == "original"


def test_a_flow_without_truth_uses_its_tasks_truth(demo_task):
    """고치기 전: truth 블록이 없는 흐름은 이체 정답({ACCOUNT}=110234567890)으로
    걸렸다."""
    assert F.truth_of({"task": "demo"})["CODE"] == "77"
    assert F.truth_of({"task": "bill"})["ENO"] == "1700000000"


def test_error_definitions_follow_the_task(demo_task):
    """고치기 전: 오류 정의는 늘 이체의 wrong-account · wrong-bank 였다."""
    assert F.error_defs({"task": "demo"}) == {}
    assert F.task_error_paths("bill") == []


def test_the_explicit_task_wins_over_the_flows_own(demo_task):
    flow = _api.load_flow(demo_task, task="demo")
    assert flow["task"] == "demo"


def test_transfer_is_unchanged_without_a_task():
    """과제를 주지 않은 호출은 전과 같은 값이다."""
    assert F.truth_of(None) == TRANSFER_TRUTH
    assert F.original_truth() == TRANSFER_TRUTH
    assert list(F.truth_of(None))[:5] == ["ACCOUNT", "AMOUNT", "BANK", "NAME",
                                          "AMOUNT_SHOWN"]
    assert [e["id"] for e in F.original_error_paths()] == ["wrong-account",
                                                            "wrong-bank"]
    flow = _api.load_flow(None)
    assert flow["done_amount"] == "#dn-amt"
    assert flow["task"] == "transfer"
