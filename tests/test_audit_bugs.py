r"""집계 버그 재현 테스트. 브라우저 없이, 손으로 만든 스냅샷으로 돈다.

`test_baseline.py` 는 "지금 나오는 값" 을 그대로 못박는다 - 그래서 값이 틀렸을
때도 통과한다. 이 파일은 반대로 **무엇이 맞는 값인지** 를 적는다. 버그 하나에
테스트 하나이고, 각 테스트는 그 버그를 고치기 전에 실패한다.

입력은 `drive()` 가 돌려주는 모양을 손으로 만든 것이다 (`snap()` · `row()`).
실제 빌드를 쓰지 않는 이유는 두 가지다 - 브라우저가 필요 없어야 하고, 버그를
드러내는 상황(엉뚱한 화면에 도착, 주입된 alert 등)이 네 빌드에는 없다.
"""
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
