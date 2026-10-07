r"""오류 경로를 브라우저로 실제로 걷는다. `pytest -m browser` 로만 돈다.

  원본 대 원본      원본의 두 오류 경로(계좌번호 틀림 · 은행 틀림)가 나타나고
                    되돌아가는가
  미리 막는 설계    틀린 계좌번호를 넣는 즉시 같은 화면에 이유를 보이고 [다음]
                    을 끈다 - 같은 화면 + 새 글로 오류 상태가 인정되는가
  처리 없는 설계    같은 화면이 확인하지 않고 그대로 넘어간다 - J 가 잡는가

  .\.venv\Scripts\python.exe -m pytest -m browser tests/test_error_paths_browser.py
"""
import asyncio
import io
import os

import pytest

import _api
import capture_baseline as C
from test_error_paths import ORIGINAL_TRIGGERS

pytestmark = pytest.mark.browser

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIXTURE = "tests/fixtures/error_paths/inline.html"


def run(rel, flow, base_flow=None, query=""):
    base_flow = base_flow or flow
    orig = asyncio.run(_api.drive("%s/%s" % (C.BASE_URL, C.ORIGINAL_REL),
                                  base_flow, errors=base_flow is flow))
    rep = asyncio.run(_api.drive("%s/%s%s" % (C.BASE_URL, rel, query), flow,
                                 original_groups=C.original_groups(orig, flow)))
    oh = io.open(os.path.join(ROOT, C.ORIGINAL_REL), encoding="utf-8").read()
    rh = io.open(os.path.join(ROOT, rel), encoding="utf-8").read()
    return rep, _api.audit(orig, rep, oh, rh, flow)


def test_original_vs_original_walks_both_error_paths(server):
    flow = _api.load_flow(None)
    rep, report = run(C.ORIGINAL_REL, flow)
    assert report["passed"]
    assert [f for f in report["fatal"] if f["check"] == "J"] == []
    res = report["metrics"]["error_paths"]
    assert set(res) == {"wrong-account", "wrong-bank"}
    for eid, r in res.items():
        assert r["appeared"] and r["recovered"], eid
        # 판정 테스트(test_error_paths.py)가 쓰는 trigger 와 같은 화면이다.
        assert r["trigger_screen"] == ORIGINAL_TRIGGERS[eid]
    assert any("계좌번호가 올바르지 않습니다" in l
               for l in res["wrong-account"]["notice"])
    # 원본의 은행 오류 문구는 은행을 말하지 않는다 ("과목코드 오류") - warning.
    jw = [w for w in report["warning"] if w["check"] == "J"]
    assert [w["error_path"] for w in jw] == ["wrong-bank"]
    # 계좌 화면은 두 번 찍힌다 - 들어온 모습(키패드 닫힘)과 입력란을 누른 뒤(열림,
    # account#2). 숨은 요소는 innerText 에 들어오지 않는다 (11-11, test_account_keypad).
    assert rep["screens"]["account"]["landed_on"] == "account"
    assert rep["screens"]["account#2"]["landed_on"] == "account"
    assert "⌫" not in rep["screens"]["account"]["text"]
    assert "⌫" in rep["screens"]["account#2"]["text"]
    # 키패드가 숨어 있어도 acc-num 버튼은 DOM 에 있다 - 원본 선택지는 그대로 10
    assert report["metrics"]["choice_groups_original"]["acc-num"] == 10


def inline_flow(inputs):
    flow = {"name": "inline", "derived_from_original": False,
            "required_ids": ["phone"],
            "steps": [{"screen": "start"},
                      {"screen": "account", "click": "[data-action='go']"},
                      {"screen": "amount", "do": [
                          {"type": "{ACCOUNT}",
                           "key": "[data-action='num'][data-v='%s']"},
                          {"click": "#next"}]}],
            "expect": {}, "done_amount": "#dn-amt",
            "error_paths": [{"id": "wrong-account", "from_step": "account",
                             "inputs": inputs, "expect_screen": "account",
                             "recover": [{"click": "#clear"}],
                             "back_to": "account"}]}
    flow["truth"] = _api.flow_module.truth_of(None)
    return flow


TYPE_WRONG = {"type": "{ACCOUNT_WRONG}", "key": "[data-action='num'][data-v='%s']"}


def test_preventive_design_counts_as_an_error_state(server):
    """[다음] 이 꺼진 설계 - 흐름은 꺼진 버튼을 누르지 않는다. 틀린 값을 넣는
    즉시 같은 화면에 이유가 보이므로 오류 상태로 인정된다."""
    flow = inline_flow([TYPE_WRONG])
    rep, report = run(FIXTURE, flow, base_flow=_api.load_flow(None))
    assert [f for f in report["fatal"] if f["check"] == "J"] == []
    r = report["metrics"]["error_paths"]["wrong-account"]
    assert r["appeared"] and r["recovered"]
    assert r["notice"] == ["없는 계좌번호예요. 계좌번호를 다시 확인해 주세요"]
    assert [w for w in report["warning"] if w["check"] == "J"] == []


def test_an_alert_on_the_error_path_is_judged_once(server):
    """같은 설계가 화면에 쓰지 않고 alert(변수) 로만 알린다 (?alert).

    고치기 전: 오류 경로에서 뜬 대화상자는 기록만 되고 판정되지 않았고(감사
    B-12), J 는 화면에 새 글이 없다고 떨어뜨렸다. 이제 막는 대화상자는 B 의 fatal
    하나이고, 사용자가 읽은 그 글로 J 의 "나타남" 은 인정된다."""
    flow = inline_flow([TYPE_WRONG])
    rep, report = run(FIXTURE, flow, base_flow=_api.load_flow(None), query="?alert")
    row = rep["error_paths"]["wrong-account"]
    assert row["dialogs_at_trigger"] == 0
    assert [d["message"] for d in row["dialogs"]] == \
        ["없는 계좌번호예요. 계좌번호를 다시 확인해 주세요"]
    # 작은 설계라 완료 화면 · 선택지 검사(A · I)는 떨어진다 - 여기서 보는 것은 B 와 J 다.
    assert [(f["check"], f.get("error_path")) for f in report["fatal"]
            if f["check"] in ("B", "J")] == [("B", "wrong-account")], report["fatal"]
    r = report["metrics"]["error_paths"]["wrong-account"]
    assert r["appeared"] and r["recovered"]


def test_design_without_error_handling_is_caught(server):
    """같은 설계에서 확인을 끈 것 (?none). 흐름은 [다음] 까지 누르고, 틀린
    계좌번호로 금액 화면에 넘어간다 - J fatal."""
    flow = inline_flow([TYPE_WRONG, {"click": "#next"}])
    rep, report = run(FIXTURE, flow, base_flow=_api.load_flow(None),
                      query="?none")
    j = [f for f in report["fatal"] if f["check"] == "J"]
    assert len(j) == 1 and "나타나지 않았다" in j[0]["detail"]
    assert "'amount'" in j[0]["detail"]
