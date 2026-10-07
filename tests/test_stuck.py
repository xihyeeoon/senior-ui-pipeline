r"""같은 실패가 되풀이되면 멈춘다 - 막힘(stuck) (11-9).

공과금 예비 실행(outputs/restructure_auto/20261007-103023-bill)은 시도 3 · 4 가 같은
fatal(검사 I 의 menu-chip 60 · menu-item 6)로 떨어졌고, 시도 5 를 보내다 멈췄다. 같은
실패 목록을 같은 재시도 블록으로 다시 보내면 같은 답이 올 공산이 크다 - 예산만 쓴다.

검사 단계에서 fatal 의 (검사 · 대상 · 개수)가 직전 시도와 같으면 실행을 "막힘"
(stopped_reason = stuck)으로 끝낸다. 남은 예산은 쓰지 않는다. 고르기 도구는 그 실행을
통과하지 못한 실행으로 본다.

모델도 브라우저도 부르지 않는다. mock 으로 끝까지 도는 것은 `-m browser` 의
test_drive 가 본다 (기준값 mock_stuck.json).
"""
import io
import os

import _api
from test_restructure_bugs import (GOOD_REPLY, BAD_REPLY, always_reply,  # noqa: F401
                                   failing_report, fake_run_env, out_root, replies,
                                   run_dirs, run_loop)
from test_select import make_run, reasons, select

loop = _api.loop_module


def report_with(*fatal):
    r = failing_report()
    r["fatal"] = [dict(f) for f in fatal]
    return r


I_ITEMS = {"check": "I", "screen": None, "detail": "메뉴 항목 6개가 없다",
           "action": "menu-item", "missing": ["가", "나", "다", "라", "마", "바"]}
I_CHIPS = {"check": "I", "screen": None, "detail": "칩 60개가 없다",
           "action": "menu-chip", "missing": ["x"] * 60}


def run_with(env, out_root, reports, attempts=5, call=always_reply):
    seq = list(reports)
    env.setattr(loop, "run_audit", lambda *a, **kw: seq.pop(0) if len(seq) > 1 else seq[0])
    return run_loop(env, out_root, call, attempts=attempts)


def run_log(out_root):
    return io.open(os.path.join(run_dirs(out_root)[-1], "run.log"), encoding="utf-8").read()


# --------------------------------------------------------------------- #
# 1. (검사 · 대상 · 개수)
# --------------------------------------------------------------------- #
def test_the_key_of_a_fatal_is_check_target_and_count():
    key = loop.fatal_key
    assert key(I_ITEMS) == ("I", "menu-item", 6)
    assert key({"check": "J", "screen": "acc", "error_path": "wrong-bank",
                "detail": "x"}) == ("J", "wrong-bank", 1)
    assert key({"check": "K", "screen": None, "missing": ["T1", "T2"],
                "detail": "x"}) == ("K", "", 2)
    assert key({"check": "A", "screen": "done", "detail": "x"}) == ("A", "done", 1)
    assert key({"check": "A", "screen": None, "lost": ["a", "b", "c"],
                "detail": "x"}) == ("A", "", 3)


def test_the_order_of_fatals_does_not_matter():
    a = report_with(I_CHIPS, I_ITEMS)
    b = report_with(I_ITEMS, I_CHIPS)
    assert loop.fatal_keys(a) == loop.fatal_keys(b)


# --------------------------------------------------------------------- #
# 2. 루프 - 같은 실패 두 번이면 멈춘다
# --------------------------------------------------------------------- #
def test_the_same_audit_failure_twice_stops_the_run(fake_run_env, out_root):
    """고치기 전: 예산 5 를 다 쓰고 budget_exhausted 로 끝났다 - 시도 5 번."""
    code, summary = run_with(fake_run_env, out_root, [report_with(I_CHIPS, I_ITEMS)])
    assert [a["n"] for a in summary["attempts"]] == [1, 2]
    assert summary["stopped_reason"] == "stuck"
    assert summary["stuck"] == {"attempt": 2, "same_as": 1,
                                "fatal": [["I", "menu-chip", 60], ["I", "menu-item", 6]]}
    assert summary["passed"] is False
    assert summary["budget"]["audit_used"] == 2 and summary["budget"]["audit_budget"] == 5
    assert code == 1                         # 떨어진 실행 - "돌지 못했다"(2)가 아니다
    log = run_log(out_root)
    assert "막힘(stuck): 시도 2 의 fatal (검사 · 대상 · 개수)가 직전 시도 1 과 같다" in log
    assert "I/menu-chip 60 · I/menu-item 6" in log
    assert "---- attempt 3" not in log


def test_a_changed_failure_keeps_going(fake_run_env, out_root):
    """공과금 예비 실행의 시도 2 → 3 처럼 fatal 하나가 사라졌으면 같은 실패가 아니다."""
    _code, summary = run_with(fake_run_env, out_root,
                              [report_with(I_CHIPS, I_ITEMS, dict(I_ITEMS, action="menu-tab",
                                                                  missing=["증권"])),
                               report_with(I_CHIPS, I_ITEMS),
                               report_with(I_CHIPS, I_ITEMS)])
    assert [a["n"] for a in summary["attempts"]] == [1, 2, 3]
    assert summary["stuck"]["attempt"] == 3 and summary["stuck"]["same_as"] == 2


def test_the_same_check_with_another_count_is_not_the_same_failure(fake_run_env, out_root):
    fewer = dict(I_ITEMS, missing=I_ITEMS["missing"][:5])
    _code, summary = run_with(fake_run_env, out_root,
                              [report_with(I_ITEMS), report_with(fewer)], attempts=2)
    assert summary["stopped_reason"] == "budget_exhausted"
    assert "stuck" not in summary


def test_a_format_failure_in_between_is_not_the_previous_audit(fake_run_env, out_root):
    """직전 시도가 검사까지 가지 못했으면 견줄 것이 없다 - 시도 3 은 시도 1 과 같은
    실패지만 바로 앞(시도 2)이 답 가르기에서 떨어졌다. 시도 4 는 시도 3 과 같다."""
    _code, summary = run_with(fake_run_env, out_root, [report_with(I_ITEMS)], attempts=3,
                              call=replies(GOOD_REPLY, BAD_REPLY, GOOD_REPLY))
    assert [a["stage"] for a in summary["attempts"]] == ["audit", "parse", "audit", "audit"]
    assert (summary["stuck"]["attempt"], summary["stuck"]["same_as"]) == (4, 3)


def test_a_passing_run_is_never_stuck(fake_run_env, out_root):
    code, summary = run_with(fake_run_env, out_root, [report_with(I_ITEMS),
                                                      {"passed": True, "fatal": [],
                                                       "warning": [], "metrics": {}}])
    assert summary["passed"] is True and summary["stopped_reason"] is None
    assert code == 0


# --------------------------------------------------------------------- #
# 3. 고르기 - stuck 은 통과하지 못한 실행이다
# --------------------------------------------------------------------- #
def test_select_treats_a_stuck_run_as_not_passed(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    make_run(str(runs), "20261007-100000-pass")
    make_run(str(runs), "20261007-110000-stuck", passed=False, attempts=2,
             stopped_reason="stuck")
    # 모순된 기록(통과 + stuck)이어도 통과로 세지 않는다
    make_run(str(runs), "20261007-120000-odd", stopped_reason="stuck")
    _code, result, _md = select(tmp_path)
    why = reasons(result)
    assert why["20261007-110000-stuck"] == ["통과하지 못함 (stuck)"]
    assert why["20261007-120000-odd"] == ["통과하지 못함 (stuck)"]
    assert result["rank1"] == "20261007-100000-pass"
