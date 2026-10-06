r"""판정 입력 - 모델이 쓴 흐름 명세가 판정 기준을 바꾸지 못하는가 (감사 E-1 · E-2).

판정 기준은 과제에서만 온다 (원칙 P1). 모델이 흐름 명세에 정답(truth)을 적든,
완료 화면의 값을 비우든, 원본에서 파생된 빌드라고 적든, 판정은 과제의 정답 ·
과제의 완료 화면 값 · 새 설계 규칙으로 해야 한다. 그리고 같은 빌드는 루프
(audit_call.run_audit)와 검사기 CLI(python -m senior_ui.audit)에서 같은 판정을
받아야 한다.

브라우저도 모델도 부르지 않는다. 걷기(drive)는 손으로 만든 스냅샷을 돌려주는
가짜로 바꾸고, 판정(core.audit · apply_stage)은 진짜를 돌린다.
"""
import io
import json
import os

import pytest

import _api
from test_audit_bugs import row, snap
from test_restructure_bugs import (GOOD_FLOW, GOOD_HTML, fake_run_env,  # noqa: F401
                                   out_root, reply_text, run_loop)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

AC = _api.audit_call_module
loop = _api.loop_module
F = _api.flow_module

ORIGINAL_REL = "inputs/original_transfer.html"
ORIGINAL_HTML = io.open(os.path.join(ROOT, ORIGINAL_REL), encoding="utf-8").read()

# 이체 과제의 정답 (flows/original.json 의 truth)
TASK_AMOUNT_SHOWN = "32,000"

# 모델이 적은, 모양은 멀쩡한 정답. 금액이 과제와 다르다.
MODEL_TRUTH = {"ACCOUNT": "110234567890", "AMOUNT": "999", "BANK": "신한",
               "NAME": "김철수"}


def model_flow(**kw):
    """GOOD_FLOW 에 오류 경로가 없는 모델 흐름. kw 로 칸을 바꾼다."""
    f = json.loads(json.dumps(GOOD_FLOW))
    f.update(kw)
    return f


def build_snapshot(amount):
    """GOOD_FLOW 의 두 화면을 걸은 결과. 완료 화면의 #dn-amt 가 `amount` 를 보인다."""
    return snap({"start": row("start", actions=["go"], ids=["phone"]),
                 "done": row("done", ids=["dn-amt"], shown=[["#dn-amt", amount]],
                             text="보냈습니다 %s원" % amount)})


ORIGINAL_SNAPSHOT = snap({"home": row("home")})


def write_build(tmp_path, flow, html=GOOD_HTML):
    """빌드와 흐름 명세를 파일로. 루프가 attempt_N.html · .flow.json 으로 쓰는 것과
    같다. 흐름 명세는 모델이 쓴 그대로 둔다."""
    html_path = tmp_path / "attempt_1.html"
    html_path.write_text(html, encoding="utf-8")
    flow_path = tmp_path / "attempt_1.flow.json"
    flow_path.write_text(json.dumps(flow, ensure_ascii=False), encoding="utf-8")
    return str(html_path), str(flow_path)


def fake_drive(rep):
    """걷기의 대역. 원본 URL 이면 원본 스냅샷, 아니면 `rep`. 받은 흐름을 남긴다."""
    seen = []

    async def drive(url, flow, want_shots=None, **kw):
        seen.append(flow)
        return json.loads(json.dumps(ORIGINAL_SNAPSHOT if ORIGINAL_REL in url else rep))
    drive.seen = seen
    return drive


def loop_verdict(monkeypatch, tmp_path, flow, rep, stage="wireframe", task=None):
    """루프가 검사기를 부르는 길(audit_call.run_audit)로 판정한다. 흐름 명세는
    루프가 저장하는 모양 그대로다 (check_reply 가 derived_from_original 을 false 로
    적는다)."""
    html_path, flow_path = write_build(tmp_path, dict(flow, derived_from_original=False))
    drive = fake_drive(rep)
    monkeypatch.setattr(AC.A, "drive", drive)
    report = AC.run_audit(ORIGINAL_SNAPSHOT, ORIGINAL_HTML, html_path, flow_path,
                          "http://localhost:3003/outputs/attempt_1.html", None, stage,
                          original_url="http://localhost:3003/" + ORIGINAL_REL,
                          task=task)
    return report, drive.seen[-1]


# --------------------------------------------------------------------- #
# 1. 정답 - 모델이 truth 를 적어도 과제의 정답으로 판정한다 (B-06)
# --------------------------------------------------------------------- #
def test_the_loop_judges_with_the_tasks_truth_even_if_the_model_wrote_one(
        monkeypatch, tmp_path):
    """모델이 금액 999 를 정답으로 적고 완료 화면에 999 를 보였다. 과제의 금액은
    32,000 이므로 떨어져야 한다.

    지키는 줄: 모델 truth 를 과제 정답으로 덮는 곳. 그 줄이 없으면 모델의 정답
    (999)으로 판정해 통과한다 (감사 R-6: 그 줄을 지워도 기본 묶음이 모두 통과했다)."""
    flow = model_flow(truth=MODEL_TRUTH)
    report, judged = loop_verdict(monkeypatch, tmp_path, flow, build_snapshot("999"))
    assert judged["truth"]["AMOUNT"] == "32000"
    assert judged["truth"]["AMOUNT_SHOWN"] == TASK_AMOUNT_SHOWN
    assert report["passed"] is False
    b = [f for f in report["fatal"] if f["check"] == "B"]
    assert [(f["selector"], f["got"], f["expected"]) for f in b] == \
        [("#dn-amt", "999", TASK_AMOUNT_SHOWN)]


def test_the_same_build_showing_the_tasks_amount_has_no_display_fatal(
        monkeypatch, tmp_path):
    """같은 흐름(모델 truth 999)이라도 완료 화면이 과제의 금액을 보이면 검사 B 는
    말이 없다 - 위 테스트의 B fatal 이 금액 때문임을 보인다. (오류 경로가 없는
    흐름이라 J 는 떨어진다 - 여기서 보는 것이 아니다.)"""
    flow = model_flow(truth=MODEL_TRUTH)
    report, _judged = loop_verdict(monkeypatch, tmp_path, flow,
                                   build_snapshot(TASK_AMOUNT_SHOWN))
    assert [f for f in report["fatal"] if f["check"] in ("A", "B")] == []


# --------------------------------------------------------------------- #
# 2. 새 설계 - 모델 흐름은 늘 derived_from_original=False 로 판정한다 (B-24)
# --------------------------------------------------------------------- #
def spy_on_the_judge(env):
    """루프 안에서 진짜 run_audit 을 돌리고, 판정(core.audit)이 받은 흐름을 남긴다.

    fake_run_env 는 run_audit 을 통째로 바꿔 끼우므로 진짜로 되돌린다. 걷기는
    가짜 스냅샷, 판정은 통과 리포트다 - 여기서 보는 것은 판정의 입력이다."""
    seen = []

    def judge(orig, rep, orig_html, rep_html, flow):
        seen.append(json.loads(json.dumps(flow)))
        return {"passed": True, "fatal": [], "warning": [],
                "metrics": {"flow": flow.get("name"), "fatal_total": 0,
                            "fatal_root": 0, "fatal_derived": 0}}
    env.setattr(loop, "run_audit", AC.run_audit)
    env.setattr(AC.A, "load_flow", _api.load_flow)
    env.setattr(AC.A, "audit", judge)
    return seen


def test_the_loop_judges_a_model_flow_as_a_new_design(fake_run_env, out_root):  # noqa: F811
    """모델이 derived_from_original 을 true 로 적어도 판정은 새 설계로 한다.

    원본에서 파생된 빌드로 판정하면 원본의 화면 이름 · data-action · id 를 짝지어
    비교한다 - 화면이 다른 새 설계에는 뜻이 없는 비교이고, 모델이 그 칸을 골라
    판정 규칙을 바꿀 수 있게 된다."""
    seen = spy_on_the_judge(fake_run_env)
    flow = model_flow(derived_from_original=True, truth=MODEL_TRUTH)
    call = lambda *a, **kw: {"text": reply_text(GOOD_HTML, flow),  # noqa: E731
                             "finish_reason": "stop", "seconds": 0.0, "usage": None}
    code, summary = run_loop(fake_run_env, out_root, call, attempts=1)
    assert summary["attempts"][0]["stage"] == "audit", summary["attempts"]
    assert len(seen) == 1
    assert seen[0]["derived_from_original"] is False
    assert seen[0]["truth"] == F.task_truth("transfer")
    assert code == 0
