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
import re

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
        "required_truth": ["AMOUNT", "CODE"], "required_error_paths": [],
        "keep_on_screen": {"CODE": "code"},
        "dialog_ok_values": ["AMOUNT_SHOWN", "AMOUNT", "CODE"]}),
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


# --------------------------------------------------------------------- #
# 2. 검사 B - 화면에서 사라지면 안 되는 값, 대화상자 속 숫자
# --------------------------------------------------------------------- #
def run_b(flow, orig_text, rep_text, dialogs=()):
    orig = {"screens": {"done": {"text": orig_text}}, "truth": F.truth_of(flow)}
    rep = {"screens": {"done": {"text": rep_text, "shown": []}},
           "dialogs": list(dialogs)}
    flow = dict(flow, expect={"done": []})
    ctx = _api.AuditContext(orig=orig, rep=rep, orig_html="", rep_html="",
                            flow=flow, derived=True, want=["done"], shared=[])
    _api.b_display.run(ctx)
    return ctx


def test_b_watches_the_tasks_own_value(demo_task):
    """고치기 전: truth 에 NAME 이 없는 과제는 검사 B 가 KeyError 로 멈췄다."""
    flow = {"task": "demo"}
    ctx = run_b(flow, "코드 77", "코드 없음")
    assert [w["detail"] for w in ctx.warning] == \
        ["code '77' no longer appears on this screen"]
    assert run_b(flow, "코드 77", "코드 77").warning == []


def test_b_dialog_numbers_follow_the_task(demo_task):
    """고치기 전: 대화상자 속 숫자를 늘 ACCOUNT 와 견줬다 (공과금에는 없다)."""
    ctx = run_b({"task": "demo"}, "", "",
                dialogs=[{"type": "alert", "message": "77 / 500 / 9", "screen": "done"}])
    assert ctx.fatal[0]["numbers"] == ["9"]


def test_b_is_unchanged_for_transfer():
    flow = {}
    ctx = run_b(flow, "받는 분 김철수", "받는 분")
    assert [w["detail"] for w in ctx.warning] == \
        ["recipient name '김철수' no longer appears on this screen"]
    ctx = run_b(flow, "", "", dialogs=[
        {"type": "alert", "message": "32,000 110234567890 5", "screen": "done"}])
    assert ctx.fatal[0]["numbers"] == ["5"]


# --------------------------------------------------------------------- #
# 3. 재구성 루프 - 기준값 걷기 · 형식 검사 · 프롬프트의 오류 조건
# --------------------------------------------------------------------- #
from test_restructure_bugs import (GOOD_FLOW, GOOD_HTML, GOOD_PLAN_REPLY,  # noqa: E402
                                   always_reply, fake_run_env, out_root,  # noqa: F401
                                   reply_text, run_loop)

loop = _api.loop_module
FLOW_REAL = _api.flow_module

BILL_HTML = GOOD_HTML.replace(
    '<span id="dn-amt">10,000</span>',
    '<span id="dn-paid">2,160</span><span id="dn-eno">1700000000</span>')
BILL_FLOW = {"name": "auto", "required_ids": ["phone", "dn-paid", "dn-eno"],
             "steps": GOOD_FLOW["steps"],
             "expect": {"done": [["#dn-paid", "{AMOUNT_SHOWN}"], ["#dn-eno", "{ENO}"]]},
             "done_amount": "#dn-paid", "error_paths": []}


def bill_reply(*a, **kw):
    return {"text": reply_text(BILL_HTML, BILL_FLOW), "finish_reason": "stop",
            "seconds": 0.0, "usage": None}


def bill_run(env, out_root, call=bill_reply, **kw):  # noqa: F811
    """공과금 과제로 루프를 돌린다. 가짜 환경은 오류 정의를 비워 두는데, 여기서는
    과제의 것(공과금은 빈 목록)이 쓰여야 하므로 진짜를 되돌려 둔다."""
    env.setattr(loop, "required_errors", FLOW_REAL.required_errors)
    return run_loop(env, out_root, call, attempts=1, task="bill", original=None, **kw)


def test_the_loop_walks_the_original_with_the_tasks_flow(fake_run_env, out_root):  # noqa: F811
    """고치기 전: 기준값 걷기가 load_flow(None) - 과제와 상관없이 이체 흐름 -
    이어서 공과금 원본은 home 에서 멈췄다."""
    seen = []

    def fake_load(path, task=None):
        seen.append((path, task))
        return {"name": "original", "steps": []}
    fake_run_env.setattr(loop.A, "load_flow", fake_load)
    bill_run(fake_run_env, out_root)
    assert seen[0] == (None, "bill")


def test_a_bill_reply_passes_the_format_check(fake_run_env, out_root):  # noqa: F811
    """고치기 전: 이체의 오류 경로 둘(wrong-account · wrong-bank)과 #dn-amt 가
    없다는 형식 오류로 떨어졌다. 계획도 plan.errors 에 이체 오류가 없다고
    떨어졌다."""
    code, summary = bill_run(fake_run_env, out_root)
    assert summary["attempts"][-1]["stage"] == "audit", summary["attempts"]
    assert code == 0


def test_a_bill_reply_still_needs_the_bill_done_ids(fake_run_env, out_root):  # noqa: F811
    code, summary = bill_run(fake_run_env, out_root, call=always_reply)
    report = json.load(io.open(summary["attempts"][-1]["html"].replace(
        ".html", ".audit.json"), encoding="utf-8"))
    details = [f["detail"] for f in report["fatal"]]
    assert "required_ids 에 'dn-paid' 이 없다" in details
    assert 'expect.done 에 ["#dn-eno", "{ENO}"] 이 없다' in details


def test_the_bill_prompts_carry_the_bill_task_and_no_transfer_errors(
        fake_run_env, out_root):  # noqa: F811
    """고치기 전: 오류 조건 절이 늘 이체의 두 오류였다."""
    fake_run_env.setattr(loop, "load_template", _api.load_template)
    # 가짜 모델은 이 머리말로 진단·계획 호출을 알아본다 (is_plan_prompt).
    fake_run_env.setattr(loop, "load_plan_template",
                         lambda task=None: "PLAN_TEMPLATE " + _api.load_plan_template(task))
    bill_run(fake_run_env, out_root)
    run_dir = sorted(os.listdir(os.path.join(out_root, "restructure_auto")))[-1]
    p = os.path.join(out_root, "restructure_auto", run_dir, "attempt_1")
    for suffix in (".prompt.txt", ".plan_prompt.txt"):
        text = io.open(p + suffix, encoding="utf-8").read()
        assert _api.load_task("bill")["description"] in text
        assert "## 원본의 오류 조건" not in text
        assert "wrong-account" not in text


def test_validate_flow_reads_the_done_values_from_the_task():
    assert _api.validate_flow(dict(BILL_FLOW), BILL_HTML, [],
                              _api.load_task("bill")["done_expect"]) == []
    # 과제를 주지 않으면 이체 - 문구도 전과 같다
    got = _api.validate_flow(dict(BILL_FLOW), BILL_HTML)
    assert "required_ids 에 'dn-amt' 이 없다" in got
    assert 'expect.done 에 ["#dn-amt", "{AMOUNT_SHOWN}"] 이 없다' in got


def test_required_errors_follow_the_task():
    assert FLOW_REAL.required_errors("bill") == []
    assert [e["id"] for e in FLOW_REAL.required_errors()] == ["wrong-account",
                                                               "wrong-bank"]


# --------------------------------------------------------------------- #
# 4. 검사기 호출 (audit_call) - 정답 · 필수 오류 경로 · 허용 제거
# --------------------------------------------------------------------- #
def test_run_audit_uses_the_tasks_truth_and_errors(monkeypatch, tmp_path):
    """고치기 전: 모델의 흐름을 늘 이체 정답과 이체 오류 경로로 걸었다."""
    AC = _api.audit_call_module
    seen = {}

    async def fake_drive(url, flow, want_shots=None, **kw):
        seen["flow"] = flow
        return {}
    monkeypatch.setattr(AC.A, "drive", fake_drive)
    monkeypatch.setattr(AC.A, "audit", lambda *a: {"passed": True})
    monkeypatch.setattr(AC.S, "apply_stage", lambda r, s: r)
    flow_path = tmp_path / "f.json"
    flow_path.write_text(json.dumps(BILL_FLOW), encoding="utf-8")
    html_path = tmp_path / "b.html"
    html_path.write_text(BILL_HTML, encoding="utf-8")
    AC.run_audit({}, "", str(html_path), str(flow_path), "u", None, "styled",
                 task="bill")
    assert seen["flow"]["truth"]["ENO"] == "1700000000"
    assert seen["flow"]["error_paths_required"] == []
    assert seen["flow"]["task"] == "bill"
    AC.run_audit({}, "", str(html_path), str(flow_path), "u", None, "styled")
    assert seen["flow"]["truth"] == TRANSFER_TRUTH
    assert seen["flow"]["error_paths_required"] == ["wrong-account", "wrong-bank"]


def test_allowed_removals_are_read_for_the_task(fake_run_env, out_root):  # noqa: F811
    seen = []
    fake_run_env.setattr(loop, "load_allowed_removals",
                         lambda task="transfer": seen.append(task) or {})
    bill_run(fake_run_env, out_root)
    assert seen == ["bill"]


# --------------------------------------------------------------------- #
# 5. 프롬프트 - 과제마다 다른 문단
# --------------------------------------------------------------------- #
TRANSFER_ONLY = ["다른 사람의 계좌로 돈을 보낸다", "dn-amt", "32,000", "110234567890",
                 "{ACCOUNT}", "{NAME}", "계좌번호를 넣는 화면", "예금주",
                 "처음 보내는 계좌", "acc-num"]


@pytest.mark.parametrize("load", ["load_template", "load_plan_template"])
def test_the_bill_prompt_has_no_transfer_text(load):
    """고치기 전: 과제 설명 말고도 기술 계약 · 흐름 명세 규칙 · 예시에 이체
    문구가 박혀 있었다 (완료 화면 dn-amt 에 32,000, 치환 문자열, 계좌 입력 화면)."""
    text = getattr(_api, load)("bill")
    left = [w for w in TRANSFER_ONLY if w in text]
    assert left == []
    assert "{{" not in text.replace("{{ORIGINAL_HTML}}", "").replace(
        "{{RETRY_BLOCK}}", "").replace("{{CHOICES}}", "").replace(
        "{{ERRORS}}", "").replace("{{PLAN}}", "").replace("{{ORIGINAL_SCREENS}}", "")


def test_the_bill_prompt_names_the_bill_done_values():
    text = _api.load_template("bill")
    assert '"#dn-paid", "{AMOUNT_SHOWN}"' in text
    assert '"#dn-eno", "{ENO}"' in text


def placeholder_pairs(text):
    """프롬프트의 "치환 문자열" 항목에 적힌 (키, 값)."""
    m = re.search(r"^- 치환 문자열: (.*?)(?=\n- |\n  [^`\s])", text, re.S | re.M)
    body = " ".join(m.group(1).split())
    return re.findall(r"`\{(\w+)\}` = (.*?)(?=,\s*`\{|[.,]?\s*$|\.\s)", body)


@pytest.mark.parametrize("name", ["transfer", "bill"])
def test_the_placeholder_line_agrees_with_the_truth(name):
    """프롬프트에 손으로 적은 치환 값이 흐름의 truth 와 어긋나지 않는다."""
    pairs = placeholder_pairs(_api.load_template(name))
    assert len(pairs) >= 4
    truth = F.task_truth(name)
    for key, val in pairs:
        assert truth[key] == val, (key, val)
    # 틀린 값(*_WRONG)은 모델에게 보이지 않는다
    assert not [k for k, _ in pairs if k.endswith("_WRONG")]
