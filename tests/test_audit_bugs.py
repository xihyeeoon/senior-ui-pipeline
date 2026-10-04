r"""집계 버그 재현 테스트. 브라우저 없이, 손으로 만든 스냅샷으로 돈다.

`test_baseline.py` 는 "지금 나오는 값" 을 그대로 못박는다 - 그래서 값이 틀렸을
때도 통과한다. 이 파일은 반대로 **무엇이 맞는 값인지** 를 적는다. 버그 하나에
테스트 하나이고, 각 테스트는 그 버그를 고치기 전에 실패한다.

입력은 `drive()` 가 돌려주는 모양을 손으로 만든 것이다 (`snap()` · `row()`).
실제 빌드를 쓰지 않는 이유는 두 가지다 - 브라우저가 필요 없어야 하고, 버그를
드러내는 상황(엉뚱한 화면에 도착, 주입된 alert 등)이 네 빌드에는 없다.
"""
import copy

import _api


# --------------------------------------------------------------------- #
# drive() 스냅샷 만들기 - 검사들이 읽는 키를 전부 빈 값으로 채운다
# --------------------------------------------------------------------- #
def row(name, **kw):
    """한 화면에 도착한 뒤 긁어 온 것. 기본값은 "아무 문제 없음" 이다."""
    r = {"landed_on": name, "screens": [name], "actions": [], "ids": [],
         "onclicks": [], "text": "", "height": 800, "choices": {},
         "contrast": [], "inherited": [], "overlap": [], "overflow": [],
         "wrapped": [], "shown": []}
    r.update(kw)
    return r


def snap(screens, **kw):
    d = {"screens": screens, "reached": [n for n, r in screens.items()
                                         if "error" not in r],
         "dialogs": [], "js_errors": [], "js_error_details": [],
         "missing_ids": [], "state_pairs": [], "undefined_classes": [],
         "notes": [], "load_failed": None, "flow": "t"}
    d.update(kw)
    return d


def flow(steps, expect=None, **kw):
    f = {"name": "t", "derived_from_original": False, "required_ids": [],
         "steps": [{"screen": s} for s in steps], "expect": expect or {},
         "done_amount": "#dn-amt"}
    f.update(kw)
    return f


# 완료 화면이 금액을 제대로 보여 주는 상태. 금액 왕복 검사를 건드리지 않으려는
# 테스트는 완료 화면을 이것으로 만든다.
def done_row(name="done", amount="10,000"):
    return row(name, shown=[["#dn-amt", amount]])


def checks_of(findings):
    return [f.get("check") for f in findings]


def details_of(findings):
    return [f.get("detail") or "" for f in findings]


# --------------------------------------------------------------------- #
# 1. 검사 I 의 fatal 이 집계에 들어간다
# --------------------------------------------------------------------- #
def one_missing_choice():
    """원본에 세 개짜리 선택지가 있고 빌드에는 하나만 있다 -> I fatal 1건."""
    orig = snap({"start": row("start", choices={"pick-bank": ["가은행", "나은행", "다은행"]})})
    rep = snap({"start": done_row("start")})
    return _api.audit(orig, rep, "", "<html>가은행</html>", flow(["start"]))


def test_check_I_fatal_is_counted():
    """I 는 fatal 검사다. 그 fatal 이 fatal_total · fatal_root 에 들어가야 한다.

    고치기 전: I 가 집계(finalize_counts) 뒤에 돌아서 fatal 목록에는 있고
    숫자에는 없었다 - fatal_total 0, fatal 1건.
    """
    report = one_missing_choice()
    assert checks_of(report["fatal"]) == ["I"]

    m = report["metrics"]
    assert m["fatal_total"] == len(report["fatal"]) == 1
    assert m["fatal_root"] == 1
    assert m["fatal_derived"] == 0


def test_every_fatal_is_counted():
    """계약: 집계는 마지막에 돈다. 어떤 검사가 낸 fatal 이든 숫자에 들어간다."""
    report = one_missing_choice()
    m = report["metrics"]
    assert m["fatal_total"] == len(report["fatal"])
    assert m["fatal_root"] + m["fatal_derived"] == m["fatal_total"]


def test_check_I_fatal_is_deduplicated():
    """같은 (검사·화면·내용) 은 한 번만 센다. I 도 그 규칙을 받아야 한다.

    흐름이 같은 화면을 두 번 지나가면(flows/run4.json 의 `account`) 화면을
    보는 검사는 같은 fatal 을 두 번 적는다. I 는 문서 전체를 보므로 스스로는
    중복을 만들지 않지만, 집계 앞에서 돌아야 그 규칙 안에 들어온다.
    """
    report = one_missing_choice()
    m = report["metrics"]
    assert m["fatal_duplicates_removed"] == 0
    assert len(report["fatal"]) == len(
        {(f.get("check"), f.get("screen"), f.get("detail"))
         for f in report["fatal"]})


# --------------------------------------------------------------------- #
# 2. apply_stage() 가 걸러낸 뒤 다시 센다
# --------------------------------------------------------------------- #
def staged_report(fatals):
    """core.audit() 이 낸 모양의 리포트. 숫자는 걸러내기 전의 것이다."""
    derived = len([f for f in fatals if f.get("derived_from")])
    return {"passed": not fatals, "fatal": copy.deepcopy(fatals), "warning": [],
            "metrics": {"fatal_duplicates_removed": 0,
                        "fatal_total": len(fatals), "fatal_derived": derived,
                        "fatal_root": len(fatals) - derived,
                        "checks_stood_down": []}}


# D 는 지금 warning 만 내지만, apply_stage 가 걸러내는 기준은 심각도가 아니라
# 검사 글자다. 걸러낼 수 있는 자리에 fatal 을 두어 계약을 직접 확인한다.
STAGE_FATALS = [
    {"check": "A", "screen": "amount", "detail": "navigation failed"},
    {"check": "A", "screen": "done", "detail": "never reached",
     "derived_from": "amount"},
    {"check": "D", "screen": "done", "detail": "대비가 낮다"},
]


def test_apply_stage_recounts_after_filtering():
    """걸러낸 뒤의 숫자는 걸러낸 뒤의 목록과 맞아야 한다.

    고치기 전: apply_stage 는 목록만 줄이고 fatal_total·fatal_derived·
    fatal_root 는 core.audit() 이 센 값을 그대로 두었다.
    """
    report = _api.apply_stage(staged_report(STAGE_FATALS), "wireframe")
    m = report["metrics"]
    assert len(report["fatal"]) == 2            # D 가 빠졌다
    assert m["fatal_total"] == 2
    assert m["fatal_derived"] == 1
    assert m["fatal_root"] == 1


def test_apply_stage_keeps_counts_when_nothing_is_dropped():
    """styled 는 A~I 를 다 보므로 걸러낼 것이 없고 숫자도 그대로다."""
    report = _api.apply_stage(staged_report(STAGE_FATALS), "styled")
    m = report["metrics"]
    assert len(report["fatal"]) == 3
    assert (m["fatal_total"], m["fatal_derived"], m["fatal_root"]) == (3, 1, 2)


def test_core_and_stage_share_one_counting_function():
    """계약: 집계는 한 곳에서만 정의한다. 두 곳이 따로 세면 규칙이 갈라진다."""
    assert _api.audit_stage_module.count_fatals         is _api.audit_core_module.count_fatals


def test_counts_match_the_list_at_every_stage():
    """실제 리포트로도 같은 계약을 본다 - 단계를 거쳐도 숫자는 목록과 맞는다."""
    report = one_missing_choice()
    for stage in ("styled", "wireframe"):
        staged = _api.apply_stage(copy.deepcopy(report), stage)
        m = staged["metrics"]
        assert m["fatal_total"] == len(staged["fatal"])
        assert m["fatal_root"] + m["fatal_derived"] == m["fatal_total"]


# --------------------------------------------------------------------- #
# 3-1. 마지막 화면에 못 갔으면 완료 금액 검사(A)를 건너뛴다
# --------------------------------------------------------------------- #
DONE_AMOUNT_MARK = "완료 화면의"


def amount_fatals(report):
    return [d for d in details_of(report["fatal"]) if DONE_AMOUNT_MARK in d]


def test_navigation_failure_does_not_also_fail_the_amount():
    """완료 화면으로 가다 멈췄으면 금액이 없는 것은 그 멈춤의 결과다.

    고치기 전: "navigation failed" 와 "완료 화면의 #dn-amt 가 None 을 보여
    준다" 가 같은 한 번의 실패로 fatal 두 건이 되었다.
    """
    rep = snap({"start": row("start"),
                "done": {"error": "TimeoutError: Locator.click: Timeout 30000ms"}})
    report = _api.audit(snap({"start": row("start")}), rep, "", "",
                        flow(["start", "done"]))
    assert amount_fatals(report) == []
    assert len(report["fatal"]) == 1
    assert "navigation failed" in report["fatal"][0]["detail"]
    # 지표는 그대로 남는다 - 검사를 건너뛰는 것이지 측정을 지우는 것이 아니다.
    assert report["metrics"]["done_screen"] == "done"
    assert report["metrics"]["done_amount"] is None


def test_landing_on_the_wrong_screen_does_not_also_fail_the_amount():
    """엉뚱한 화면에 서 있으면 완료 화면의 금액을 물을 수 없다."""
    rep = snap({"start": row("start"), "done": row("done", landed_on="amount")})
    report = _api.audit(snap({"start": row("start")}), rep, "", "",
                        flow(["start", "done"]))
    assert amount_fatals(report) == []
    assert details_of(report["fatal"]) == ["landed on 'amount' instead"]


def test_unreached_last_screen_does_not_also_fail_the_amount():
    rep = snap({"start": row("start")})
    report = _api.audit(snap({"start": row("start")}), rep, "", "",
                        flow(["start", "done"]))
    assert amount_fatals(report) == []
    assert len(report["fatal"]) == 1
    assert "never reached" in report["fatal"][0]["detail"]


def test_wrong_amount_on_a_screen_that_was_reached_is_still_fatal():
    """건너뛰는 것은 "못 갔을 때" 뿐이다. 제대로 도착했는데 금액이 틀리면 잡는다."""
    rep = snap({"start": row("start"), "done": done_row("done", "9,000")})
    report = _api.audit(snap({"start": row("start")}), rep, "", "",
                        flow(["start", "done"]))
    assert len(amount_fatals(report)) == 1
    assert report["metrics"]["done_amount"] == "9,000"


def test_missing_screen_hook_does_not_also_fail_the_amount():
    """__screen() 이 null 을 주면 어느 화면에 서 있는지 알 수 없다. 도달을 확인
    하지 못한 것이므로 금액도 묻지 않는다 - 훅이 없다는 fatal 이 이미 있다."""
    rep = snap({"start": row("start"),
                "done": done_row("done", "10,000")})
    rep["screens"]["done"]["landed_on"] = None
    report = _api.audit(snap({"start": row("start")}), rep, "", "",
                        flow(["start", "done"]))
    assert amount_fatals(report) == []
    assert len(report["fatal"]) == 1
    assert "__screen()" in report["fatal"][0]["detail"]
