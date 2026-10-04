r"""집계 버그 재현 테스트. 브라우저 없이, 손으로 만든 스냅샷으로 돈다.

`test_baseline.py` 는 "지금 나오는 값" 을 그대로 못박는다 - 그래서 값이 틀렸을
때도 통과한다. 이 파일은 반대로 **무엇이 맞는 값인지** 를 적는다. 버그 하나에
테스트 하나이고, 각 테스트는 그 버그를 고치기 전에 실패한다.

입력은 `drive()` 가 돌려주는 모양을 손으로 만든 것이다 (`snap()` · `row()`).
실제 빌드를 쓰지 않는 이유는 두 가지다 - 브라우저가 필요 없어야 하고, 버그를
드러내는 상황(엉뚱한 화면에 도착, 주입된 alert 등)이 네 빌드에는 없다.
"""
import copy
import io
import json
import os
import sys

import _api

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


# --------------------------------------------------------------------- #
# 3-2. 완료 금액이 틀릴 때 A 와 B 가 같은 값을 두 번 잡지 않는다
# --------------------------------------------------------------------- #
DONE_EXPECT = {"done": [["#dn-amt", "{AMOUNT_SHOWN}"]]}


def wrong_done_amount(expect):
    rep = snap({"start": row("start"), "done": done_row("done", "9,000")})
    return _api.audit(snap({"start": row("start")}), rep, "", "",
                      flow(["start", "done"], expect=expect))


def test_wrong_done_amount_is_one_finding_not_two():
    """흐름의 expect 에 #dn-amt 가 적혀 있으면 B 가 그 값을 본다. A 의 금액
    왕복 검사는 같은 선택자의 같은 값을 다시 본다.

    고치기 전: fatal 2건 (A "완료 화면의 #dn-amt 가 '9,000' …" + B "#dn-amt
    shows '9,000' but the task used '10,000'"). 네 흐름 파일 모두 완료 화면의
    #dn-amt 를 expect 에 적고 있으므로 늘 두 번 세졌다.
    """
    report = wrong_done_amount(DONE_EXPECT)
    assert len(report["fatal"]) == 1
    assert report["fatal"][0]["check"] == "B"
    assert "#dn-amt" in report["fatal"][0]["detail"]
    assert report["metrics"]["fatal_total"] == 1
    # 지표는 여전히 A 가 남긴다.
    assert report["metrics"]["done_amount"] == "9,000"


def test_a_still_checks_the_amount_when_the_flow_does_not():
    """expect 에 적히지 않은 흐름에서는 A 가 유일한 검사다. 줄이는 것은 겹치는
    경우뿐이고, 검사가 사라지는 경우는 없어야 한다."""
    report = wrong_done_amount({})
    assert len(report["fatal"]) == 1
    assert report["fatal"][0]["check"] == "A"
    assert DONE_AMOUNT_MARK in report["fatal"][0]["detail"]


# --------------------------------------------------------------------- #
# 3-3. 주입된 alert() 의 "숫자 하드코딩" 은 속성이지 별도 fatal 이 아니다
# --------------------------------------------------------------------- #
def injected_alert(msg):
    plain = snap({"start": done_row("start")})
    return _api.audit(plain, snap({"start": done_row("start")}),
                      "<html></html>",
                      "<html><script>alert('%s')</script></html>" % msg,
                      flow(["start"]))


def test_injected_dialog_with_a_number_is_one_fatal():
    """주입된 alert 하나는 결함 하나다.

    고치기 전: "alert() injected …" 와 "injected alert() hardcodes 10,000 …"
    가 따로 나서 alert 한 개가 fatal 2건이 되었다. 숫자를 박아 넣은 것은 그
    alert 의 성질이지 별개의 결함이 아니다.
    """
    report = injected_alert("10,000원을 보냈습니다")
    assert len(report["fatal"]) == 1
    f = report["fatal"][0]
    assert f["check"] == "B"
    assert f["numbers"] == ["10,000"]            # 속성으로 남는다
    assert "hardcode" in f["detail"]             # 내용에도 적힌다
    assert report["metrics"]["injected_dialog_calls"] == 1
    assert report["metrics"]["fatal_total"] == 1


def test_injected_dialog_without_a_number_is_still_one_fatal():
    report = injected_alert("보냈습니다")
    assert len(report["fatal"]) == 1
    assert report["fatal"][0]["numbers"] == []
    assert "hardcode" not in report["fatal"][0]["detail"]


# --------------------------------------------------------------------- #
# 3-4. 엉뚱한 화면에 도착한 것도 "멈춤" 이다
# --------------------------------------------------------------------- #
def landed_wrong():
    """두 번째 화면에서 엉뚱한 곳에 도착하고, 세 번째는 아예 못 간 경우.
    예외는 나지 않았다 - 클릭은 됐고 화면만 바뀌지 않았다."""
    rep = snap({"start": row("start"), "middle": row("middle", landed_on="start")})
    return _api.audit(snap({"start": row("start")}), rep, "", "",
                      flow(["start", "middle", "done"]))


def test_landing_on_the_wrong_screen_records_where_it_stopped():
    """고치기 전: stopped_at 이 비어 있어서, 뒤따르는 "도달 못 함" 이 파생이
    아니라 독립된 결함으로 세졌다. 게다가 그 "도달 못 함" 이 stopped_at 을
    자기 이름(done)으로 채워, 실제로 멈춘 곳(middle)이 아니라 멈춤의 결과가
    원인으로 기록되었다."""
    report = landed_wrong()
    assert report["metrics"]["stopped_at"] == "middle"


def test_screens_after_a_wrong_landing_are_derived():
    report = landed_wrong()
    m = report["metrics"]
    assert len(report["fatal"]) == 2
    assert m["fatal_total"] == 2
    assert m["fatal_root"] == 1              # 엉뚱한 화면 하나만 독립 결함이다
    assert m["fatal_derived"] == 1
    after = [f for f in report["fatal"] if f.get("screen") == "done"]
    assert after and after[0]["derived_from"] == "middle"


# --------------------------------------------------------------------- #
# 4. 검사기 자체가 죽으면 종료 코드 2 와 리포트 모양 JSON
# --------------------------------------------------------------------- #
# 빌드 불합격(fatal 있음)은 1 이다. 검사기가 돌지 못한 것과 빌드가 떨어진 것은
# 재생성 루프에게 전혀 다른 사건이므로 종료 코드가 같아서는 안 된다.
CLI_ARGS = [
    "--build", "http://localhost:3003/results/restructured_transfer.html",
    "--build-file", os.path.join(ROOT, "results", "restructured_transfer.html"),
    "--original-file", os.path.join(ROOT, "inputs", "original_transfer.html"),
    "--flow", os.path.join(ROOT, "flows", "restructured.json"),
]


def run_cli(monkeypatch, argv, encoding="ascii"):
    """CLI 를 부르고 (종료 코드, stdout 에 찍힌 글) 을 돌려준다.

    stdout 은 일부러 한글을 못 쓰는 인코딩으로 둔다. 검사기가 스스로 UTF-8 로
    맞추지 않으면 JSON 을 찍다가 UnicodeEncodeError 로 죽는다 - cp949 콘솔에서
    실제로 그렇게 죽는다."""
    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout",
                        io.TextIOWrapper(raw, encoding=encoding, errors="strict"))
    code = _api.audit_cli_main(argv)
    sys.stdout.flush()
    return code, raw.getvalue().decode("utf-8")


def test_cli_exits_2_when_the_auditor_itself_dies(monkeypatch, tmp_path):
    """고치기 전: drive() 가 던지면 역추적이 그대로 올라가 종료 코드 1 이 됐다 -
    "빌드 불합격" 과 구분되지 않았다."""
    def boom(*a, **kw):
        raise RuntimeError("브라우저를 띄울 수 없다")
    monkeypatch.setattr(_api.audit_cli_module, "drive", boom)

    code, out = run_cli(monkeypatch, CLI_ARGS
                        + ["--out", str(tmp_path / "audit.json")])
    assert code == 2
    report = json.loads(out)
    assert report["passed"] is False
    assert report["warning"] == [] and report["metrics"] == {}
    assert len(report["fatal"]) == 1
    f = report["fatal"][0]
    assert f["check"] is None and f["screen"] is None
    assert "RuntimeError" in f["detail"] and "브라우저" in f["detail"]


def test_cli_exits_2_when_an_input_cannot_be_read(monkeypatch, tmp_path):
    """읽기 실패는 전부터 2 였다. 한글이 든 JSON 이 cp949 stdout 에서도
    찍히는지를 함께 본다 (stdout 을 UTF-8 로 맞추는 것이 main 의 첫 일이다)."""
    argv = list(CLI_ARGS)
    argv[argv.index("--build-file") + 1] = str(tmp_path / "없는-빌드.html")
    code, out = run_cli(monkeypatch, argv)
    assert code == 2
    report = json.loads(out)
    assert "없는-빌드.html" in report["fatal"][0]["detail"]


# --------------------------------------------------------------------- #
# 5. 리포트: 개요의 fatal 행 · 핵심 지표의 I 행
# --------------------------------------------------------------------- #
def report_build(label="Run1", **metrics):
    m = {"fatal_total": 3, "fatal_derived": 2, "fatal_root": 1,
         "choice_values_missing": {"pick-bank": ["가은행", "나은행", "다은행"]},
         "choice_values_kept": {"pick-bank": 9}}
    m.update(metrics)
    return (label, {"passed": False,
                    "fatal": [{"check": "I", "screen": None, "detail": "선택지 누락"},
                              {"check": "A", "screen": "amount",
                               "detail": "navigation failed"},
                              {"check": "A", "screen": "done",
                               "detail": "never reached",
                               "derived_from": "amount"}],
                    "warning": [], "metrics": m, "inputs": {"repaired": "x"}})


def md_section(md, title):
    """리포트의 한 절만 떼어 온다. 검사 글자는 '검사 항목별' 표와 '핵심 지표'
    표 양쪽에 나오므로, 절을 가르지 않으면 엉뚱한 행을 본다."""
    out, on = [], False
    for line in md.splitlines():
        if line.startswith("## "):
            on = line[3:].strip() == title
            continue
        if on:
            out.append(line)
    assert out, "'%s' 절이 리포트에 없습니다" % title
    return out


def md_row(md, label, section="개요"):
    hits = [l for l in md_section(md, section)
            if l.startswith("| %s |" % label)]
    assert hits, "'%s' 행이 %s 절에 없습니다" % (label, section)
    return hits[0]


def test_overview_fatal_row_shows_root_and_derived():
    """고치기 전: 개요의 fatal 행은 총 개수 하나였다. run 끼리 비교할 때 봐야
    하는 것은 독립 결함(fatal_root) 인데 그 값이 표에 없었다."""
    md = _api.ar_render([report_build()], False, 10, "t")
    row = md_row(md, "fatal")
    assert "3" in row and "독립 1" in row and "파생 2" in row


def test_overview_fatal_row_without_the_metrics():
    """옛 audit JSON 에는 그 두 값이 없을 수 있다. 그때도 죽지 않는다."""
    _, rep = report_build()
    for k in ("fatal_total", "fatal_derived", "fatal_root"):
        rep["metrics"].pop(k)
    md = _api.ar_render([("Old", rep)], False, 10, "t")
    assert md_row(md, "fatal")


def test_key_metrics_has_a_row_for_check_I():
    """고치기 전: 핵심 지표 표는 A~H 만 있었다. I 는 fatal 검사인데 그 숫자를
    표에서 볼 수 없었다."""
    md = _api.ar_render([report_build()], False, 10, "t")
    row = md_row(md, "I", "핵심 지표")
    assert "choice" not in row              # 지표 이름이 아니라 사람 말로
    assert "pick-bank" in row and "3" in row


def test_key_metrics_I_row_with_nothing_missing():
    md = _api.ar_render([report_build(choice_values_missing={})], False, 10, "t")
    assert md_row(md, "I", "핵심 지표").endswith("| 0 |")
