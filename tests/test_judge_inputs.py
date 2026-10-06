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
import sys

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
        original = "/inputs/original_" in url
        return json.loads(json.dumps(ORIGINAL_SNAPSHOT if original else rep))
    drive.seen = seen
    return drive


def loop_verdict(monkeypatch, tmp_path, flow, rep, stage="wireframe", task=None):
    """루프가 검사기를 부르는 길(audit_call.run_audit)로 판정한다. 흐름 명세는
    루프가 저장하는 모양 그대로 - 모델이 쓴 그대로다."""
    html_path, flow_path = write_build(tmp_path, flow)
    drive = fake_drive(rep)
    monkeypatch.setattr(AC.A, "drive", drive)
    # 루프는 그 과제의 원본(과제 파일의 original)을 비교 기준으로 읽는다.
    original = _api.load_task(task)["original"]
    orig_html = io.open(os.path.join(ROOT, original), encoding="utf-8").read()
    report = AC.run_audit(ORIGINAL_SNAPSHOT, orig_html, html_path, flow_path,
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


# --------------------------------------------------------------------- #
# 3. 버려질 truth 는 검증하지 않는다 (B-02)
# --------------------------------------------------------------------- #
BAD_TRUTHS = [
    # 쉼표가 든 금액 - 원본 흐름이면 멈춰야 할 모양이다
    {"ACCOUNT": "110234567890", "AMOUNT": "32,000", "BANK": "신한", "NAME": "김철수"},
    # 필수 키가 빠졌다
    {"AMOUNT": "32000"},
]


@pytest.mark.parametrize("truth", BAD_TRUTHS, ids=["comma", "missing-keys"])
def test_a_badly_shaped_model_truth_does_not_stop_the_audit(monkeypatch, tmp_path,
                                                            truth):
    """고치기 전: run_audit 이 load_flow 로 모델의 truth 를 먼저 검증해 ValueError 가
    났다 - 어차피 과제의 정답으로 덮을 값이었다. 루프는 그것을 "검사기가 흐름
    명세를 실행하지 못했다" 로 받아 검사 예산을 하나 썼다 (감사 R-2)."""
    report, judged = loop_verdict(monkeypatch, tmp_path, model_flow(truth=truth),
                                  build_snapshot(TASK_AMOUNT_SHOWN))
    assert judged["truth"] == F.task_truth("transfer")
    assert [f for f in report["fatal"] if f["check"] in ("A", "B", None)] == []


def test_a_badly_shaped_model_truth_costs_no_retry(fake_run_env, out_root):  # noqa: F811
    """루프 전체로: 시도는 검사까지 가고, 검사 예산은 그대로이며, 모델이 truth 를
    적었다는 사실은 기록에 남는다."""
    seen = spy_on_the_judge(fake_run_env)
    flow = model_flow(truth=BAD_TRUTHS[0])
    call = lambda *a, **kw: {"text": reply_text(GOOD_HTML, flow),  # noqa: E731
                             "finish_reason": "stop", "seconds": 0.0, "usage": None}
    code, summary = run_loop(fake_run_env, out_root, call, attempts=1)
    entry = summary["attempts"][0]
    assert entry["stage"] == "audit" and entry["passed"], entry
    assert summary["budget"]["audit_used"] == 0
    assert entry["model_claims_dropped"] == ["truth"]
    assert seen[0]["truth"] == F.task_truth("transfer")
    assert code == 0


# --------------------------------------------------------------------- #
# 4. 판정 입력 함수 자체 - 입력과 출력
# --------------------------------------------------------------------- #
def test_judged_flow_takes_the_judging_fields_from_the_task():
    flow = model_flow(truth=MODEL_TRUTH, task="bill", stage="styled",
                      derived_from_original=True, error_paths_required=[],
                      choices_removed={"pick-bank": {"values": ["x"], "reason": "r"}})
    before = json.loads(json.dumps(flow))
    out = _api.judged_flow(flow, task="transfer", stage="wireframe",
                           allowed_removals={})
    assert flow == before                         # 받은 흐름은 그대로
    assert out["task"] == "transfer"
    assert out["truth"] == F.task_truth("transfer")
    assert out["derived_from_original"] is False
    assert out["choices_removed"] == {}
    assert out["error_paths_required"] == ["wrong-account", "wrong-bank"]
    assert out["stage"] == "wireframe"
    assert out["model_claims_dropped"] == ["truth", "choices_removed", "task", "stage",
                                           "error_paths_required",
                                           "derived_from_original"]
    # 걷는 법은 모델의 것 그대로
    assert out["steps"] == flow["steps"]
    assert out["required_ids"] == flow["required_ids"]


def test_judged_flow_defaults_are_the_loops_defaults():
    out = _api.judged_flow(model_flow())
    assert out["task"] == "transfer"
    assert out["stage"] == _api.config_module.DEFAULT_STAGE
    assert out["choices_removed"] == _api.load_allowed_removals("transfer")
    assert out["model_claims_dropped"] == []


def test_judged_flow_reads_the_bill_task():
    out = _api.judged_flow(model_flow(), task="bill")
    assert out["truth"] == F.task_truth("bill")
    assert out["error_paths_required"] == []


def test_judged_flow_passes_the_reveal_in_one_shape():
    """펼치기(11-5)도 판정 입력을 거친다. `do` 는 늘 목록이고, click 하나가 아닌
    동작은 걷는 쪽이 규칙 위반으로 적도록 그대로 둔다."""
    flow = model_flow(reveal={"pick-bank": {"at": "start", "do": {"click": "#all"}},
                              "pick-sec": {"at": "start",
                                           "do": [{"type": "x", "key": "#k"}]},
                              "odd": "start"})
    out = _api.judged_flow(flow)
    assert out["reveal"] == {"pick-bank": {"at": "start", "do": [{"click": "#all"}]},
                             "pick-sec": {"at": "start",
                                          "do": [{"type": "x", "key": "#k"}]},
                             "odd": {"at": None, "do": []}}
    assert "reveal" not in _api.judged_flow(model_flow())


def test_only_files_under_flows_are_researcher_flows(tmp_path):
    I = _api.inputs_module
    assert I.researcher_flow(None)
    assert I.researcher_flow(os.path.join(ROOT, "flows", "run2.json"))
    assert not I.researcher_flow(os.path.join(ROOT, "outputs", "x.flow.json"))
    assert not I.researcher_flow(str(tmp_path / "flows" / "run2.json"))


# --------------------------------------------------------------------- #
# 5. 완료 화면 값은 늘 과제의 done_expect 로 판정한다 (B-01)
# --------------------------------------------------------------------- #
@pytest.mark.parametrize("value", ["", "999", "{AMOUNT}"],
                         ids=["empty", "literal", "other-placeholder"])
def test_the_done_value_is_the_tasks_whatever_the_model_wrote(monkeypatch, tmp_path,
                                                              value):
    """완료 화면이 999 를 보인다. 과제가 넣은 금액은 32,000 이다.

    고치기 전: 검사 B 는 모델이 expect 에 적은 값과 비교했다. 빈 값이면 무조건
    통과였고(감사 R-1), 999 로 적으면 999 가 정답이 됐다. 형식 검사는 선택자만
    본다."""
    flow = model_flow(expect={"done": [["#dn-amt", value]]})
    report, judged = loop_verdict(monkeypatch, tmp_path, flow, build_snapshot("999"))
    assert judged["expect"]["done"] == [["#dn-amt", "{AMOUNT_SHOWN}"]]
    b = [f for f in report["fatal"] if f["check"] == "B"]
    assert [(f["selector"], f["got"], f["expected"]) for f in b] == \
        [("#dn-amt", "999", TASK_AMOUNT_SHOWN)]


def test_the_models_done_amount_cannot_move_the_done_check(monkeypatch, tmp_path):
    """모델이 done_amount 로 금액 자리를 맞는 값을 보이는 다른 요소로 옮기고,
    과제의 자리(#dn-amt)는 expect 에 적지 않았다.

    고치기 전: 검사 A 는 done_amount 가 가리키는 #fake(32,000)만 보고, #dn-amt 의
    999 는 아무도 보지 않아 통과했다."""
    flow = model_flow(expect={"done": []}, done_amount="#fake")
    rep = snap({"start": row("start", actions=["go"], ids=["phone"]),
                "done": row("done", ids=["dn-amt", "fake"],
                            shown=[["#dn-amt", "999"], ["#fake", TASK_AMOUNT_SHOWN]])})
    report, judged = loop_verdict(monkeypatch, tmp_path, flow, rep)
    assert judged["done_amount"] == "#dn-amt"
    fatal = [f for f in report["fatal"] if f["check"] in ("A", "B")]
    assert len(fatal) == 1, fatal
    assert "#dn-amt" in fatal[0]["detail"] and "999" in fatal[0]["detail"]


def test_the_models_other_done_pairs_are_kept(monkeypatch, tmp_path):
    """완료 화면에서 모델이 더 확인하겠다고 적은 짝은 그대로 둔다 - 걷는 법이고
    과제의 기준을 바꾸지 않는다. 과제의 짝은 모델이 적은 자리에 그 값으로 들어간다."""
    flow = model_flow(expect={"done": [["#note", "{NAME}"], ["#dn-amt", ""],
                                       ["#dn-amt", "1"]]})
    out = _api.judged_flow(flow)
    assert out["expect"]["done"] == [["#note", "{NAME}"],
                                     ["#dn-amt", "{AMOUNT_SHOWN}"]]
    assert "expect.done" in out["model_claims_dropped"]


def test_the_done_pairs_follow_the_last_screen_and_the_task():
    """완료 화면은 이름이 아니라 마지막 걸음의 화면이다. 공과금은 두 짝이다."""
    flow = model_flow(steps=[{"screen": "start"},
                             {"screen": "finish", "click": "[data-action='go']"}],
                      expect={})
    out = _api.judged_flow(flow, task="bill")
    assert out["expect"]["finish"] == _api.load_task("bill")["done_expect"]
    assert out["done_amount"] == "#dn-paid"


# --------------------------------------------------------------------- #
# 6. 같은 빌드는 루프와 검사기 CLI 에서 같은 판정을 받는다 (B-03 · B-24)
# --------------------------------------------------------------------- #
BUILD_URL = "http://localhost:3003/outputs/attempt_1.html"


def cli_verdict(monkeypatch, tmp_path, flow, rep, extra=()):
    """검사기 CLI(python -m senior_ui.audit)로 같은 빌드 · 같은 흐름 파일을 판정한다.
    걷기만 대역이고 흐름 읽기 · 판정 · 단계는 CLI 의 것 그대로다."""
    html_path, flow_path = write_build(tmp_path, flow)
    CLI = _api.audit_cli_module
    monkeypatch.setattr(CLI, "drive", fake_drive(rep))
    out = tmp_path / "audit.json"
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    code = _api.audit_cli_main(["--build", BUILD_URL, "--build-file", html_path,
                                "--flow", flow_path, "--out", str(out)] + list(extra))
    return code, json.load(io.open(str(out), encoding="utf-8"))


def without_inputs(report):
    return {k: v for k, v in report.items() if k != "inputs"}


PARITY = [
    ("good", model_flow(), build_snapshot(TASK_AMOUNT_SHOWN), None, None),
    ("model-truth-and-empty-done",
     model_flow(truth=MODEL_TRUTH, expect={"done": [["#dn-amt", ""]]}),
     build_snapshot("999"), None, None),
    ("model-says-derived", model_flow(derived_from_original=True),
     build_snapshot(TASK_AMOUNT_SHOWN), None, None),
    ("model-says-stage-and-task", model_flow(stage="styled", task="bill"),
     build_snapshot(TASK_AMOUNT_SHOWN), None, None),
    ("styled", model_flow(), build_snapshot(TASK_AMOUNT_SHOWN), "styled", None),
    ("bill", model_flow(), build_snapshot(TASK_AMOUNT_SHOWN), None, "bill"),
]


@pytest.mark.parametrize("flow,rep,stage,task", [c[1:] for c in PARITY],
                         ids=[c[0] for c in PARITY])
def test_the_cli_and_the_loop_judge_a_model_flow_alike(monkeypatch, tmp_path, flow, rep,
                                                       stage, task):
    """고치기 전: CLI 는 모델 흐름을 연구자 흐름처럼 읽었다 - 모델의 truth, 흐름의
    task · stage(없으면 styled), derived_from_original 기본값 true, 허용 목록 ·
    필수 오류 경로 없음 (감사 B-03 의 (a)~(e)). 루프는 그 다섯을 과제로 정했다.

    루프는 실행의 과제 · 단계로 부르고, CLI 는 --task · --stage 로 같은 것을 준다.
    둘 다 주지 않으면 양쪽 모두 기본값(이체 · config.DEFAULT_STAGE)이다."""
    (tmp_path / "loop").mkdir()
    (tmp_path / "cli").mkdir()
    loop_report, _ = loop_verdict(monkeypatch, tmp_path / "loop", flow, rep,
                                  stage=stage or _api.config_module.DEFAULT_STAGE,
                                  task=task)
    extra = (["--stage", stage] if stage else []) + (["--task", task] if task else [])
    code, cli_report = cli_verdict(monkeypatch, tmp_path / "cli", flow, rep, extra)
    assert without_inputs(cli_report) == without_inputs(loop_report)
    assert cli_report["inputs"]["stage"] == loop_report["inputs"]["stage"]
    assert code == (0 if loop_report["passed"] else 1)


def test_the_cli_still_trusts_a_researcher_flow(monkeypatch, tmp_path):
    """flows/ 아래의 흐름(옛 Run 흐름)은 연구자의 것이다. 자기 truth(옛 원본의
    정답) · 자기 단계(없으면 styled)로 판정한다 - 기준값 run1~3 이 그것이다."""
    CLI = _api.audit_cli_module
    drive = fake_drive(build_snapshot(TASK_AMOUNT_SHOWN))
    monkeypatch.setattr(CLI, "drive", drive)
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    out = tmp_path / "audit.json"
    path = os.path.join(ROOT, "flows", "restructured.json")
    _api.audit_cli_main(["--build", BUILD_URL, "--build-file",
                         os.path.join(ROOT, "results", "restructured_transfer.html"),
                         "--flow", path, "--out", str(out)])
    own = json.load(io.open(path, encoding="utf-8"))["truth"]
    built = drive.seen[-1]
    assert built["truth"]["AMOUNT"] == own["AMOUNT"] != F.task_truth()["AMOUNT"]
    assert "model_claims_dropped" not in built
    report = json.load(io.open(str(out), encoding="utf-8"))
    assert report["inputs"]["stage"] == "styled"
