r"""실제 응답 고정물(tests/fixtures/real_runs/)을 판정 입력의 새 길로 다시 판정한다.
`pytest -m browser` 로만 돈다.

gpt-6.1-sol (20261006-124055) 과 gpt-6-astra (20261006-124838) 의 첫 답을 루프와
같은 순서로 받는다 - 답 가르기 → 완료 칸 별칭 → 형식 검사 → 선택지 데이터 넣기
→ 저장(모델이 쓴 흐름 그대로) → 판정. 판정은 루프의 길(audit_call.run_audit)과
검사기 CLI 둘 다로 한다. 판정 입력을 한 함수(audit.inputs.judged_flow)로 모은
뒤에도 11-4 의 다시 확인(outputs/preflight_recheck)과 같은 판정이어야 한다.

  sol    통과
  astra  J fatal 1 - wrong-bank 의 되돌아가는 조작이 막힌다 (클릭 시간 초과)

astra 의 J 는 버튼을 30 초 기다리다 실패한다. 루프와 CLI 가 한 번씩 걸으므로
이 파일은 1분 넘게 걸린다.
"""
import asyncio
import io
import json
import os
import shutil
import sys

import pytest

import _api
import capture_baseline as C

pytestmark = pytest.mark.browser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL = os.path.join(ROOT, "tests", "fixtures", "real_runs")
OUT = os.path.join(ROOT, ".pytest-outputs", "real_runs")

reply = _api.reply_module
F = _api.flow_module


def build_like_the_loop(model):
    """첫 답을 루프의 check_reply 와 같은 순서로 받아 빌드 · 흐름 파일로 쓴다."""
    text = io.open(os.path.join(REAL, model, "attempt_1.response.txt"),
                   encoding="utf-8").read()
    html, flow, _ = _api.parse_reply(text)
    flow.setdefault("name", "auto")
    reply.accept_done_alias(flow)
    task = _api.load_task("transfer")
    data = json.load(io.open(os.path.join(REAL, model, "preserved.json"),
                             encoding="utf-8"))
    problems = (reply.validate_flow(flow, html, F.required_errors(), task["done_expect"])
                + _api.preserved_problems(html, data))
    build, _redeclared = _api.preserve_module.inject(html, data)
    d = os.path.join(OUT, model)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    html_path, flow_path = os.path.join(d, "attempt_1.html"), os.path.join(d, "attempt_1.flow.json")
    io.open(html_path, "w", encoding="utf-8", newline="\n").write(build)
    io.open(flow_path, "w", encoding="utf-8", newline="\n").write(
        json.dumps(flow, ensure_ascii=False, indent=2))
    rel = os.path.relpath(html_path, ROOT).replace(os.sep, "/")
    return problems, html_path, flow_path, "%s/%s" % (C.BASE_URL, rel)


@pytest.fixture(scope="module")
def verdicts(server):
    """두 모델의 첫 답을 루프의 길과 CLI 로 한 번씩 판정한다."""
    orig_html = io.open(os.path.join(ROOT, C.ORIGINAL_REL), encoding="utf-8").read()
    orig_url = "%s/%s" % (C.BASE_URL, C.ORIGINAL_REL)
    snap = asyncio.run(_api.drive(orig_url, _api.load_flow(None), errors=False))
    out = {}
    for model in ("sol", "astra"):
        problems, html_path, flow_path, url = build_like_the_loop(model)
        loop_report = _api.audit_call_module.run_audit(
            snap, orig_html, html_path, flow_path, url, None, "wireframe",
            original_url=orig_url, task="transfer")
        cli_out = os.path.join(OUT, model, "audit.cli.json")
        saved, sys.stdout = sys.stdout, io.StringIO()
        try:
            code = _api.audit_cli_main(["--build", url, "--build-file", html_path,
                                        "--flow", flow_path, "--out", cli_out,
                                        "--task", "transfer"])
        finally:
            sys.stdout = saved
        cli_report = json.load(io.open(cli_out, encoding="utf-8"))
        with io.open(os.path.join(OUT, model, "audit.loop.json"), "w",
                     encoding="utf-8", newline="\n") as f:
            json.dump(loop_report, f, ensure_ascii=False, indent=2)
        out[model] = {"problems": problems, "loop": loop_report, "cli": cli_report,
                      "code": code}
    return out


def strip(report):
    return {k: v for k, v in report.items() if k != "inputs"}


def test_both_first_replies_pass_the_format_check(verdicts):
    for model in ("sol", "astra"):
        assert verdicts[model]["problems"] == [], model


def test_sol_first_attempt_now_fails_only_on_the_entrances(verdicts):
    """sol 의 첫 답은 A~J 를 모두 지난다 - 그런데 이체 홈 · 받는 사람 · 완료 화면의
    다른 메뉴를 거의 다 지웠다. 11-7 에서 검사 K (과제 밖 입구 보존, 연구자 결정 (나))
    가 생긴 뒤로 그것 하나로 떨어진다. 전에는 통과했다."""
    v = verdicts["sol"]
    fatal = v["loop"]["fatal"]
    assert [f["check"] for f in fatal] == ["K"], fatal
    m = v["loop"]["metrics"]
    assert m["stage"] == "wireframe"
    assert (m["entrances_original"], m["entrances_kept"]) == (31, 2)
    assert v["code"] == 1


def test_astra_first_attempt_has_the_J_fatal_and_now_K(verdicts):
    v = verdicts["astra"]
    fatal = v["loop"]["fatal"]
    assert [(f["check"], f.get("error_path")) for f in fatal] == [("J", "wrong-bank"),
                                                                    ("K", None)], fatal
    assert "되돌아가는 조작이 막혔다" in fatal[0]["detail"]
    assert "TimeoutError" in fatal[0]["detail"]
    assert v["code"] == 1


def test_the_cli_gives_the_same_verdicts(verdicts):
    """같은 빌드 · 같은 흐름 파일을 CLI 로 다시 검사하면 같은 판정이다 (감사 B-03).
    CLI 에는 그 실행의 과제(--task transfer)만 주고 --stage 는 주지 않았다 -
    루프의 기본 단계와 같다."""
    for model in ("sol", "astra"):
        v = verdicts[model]
        assert strip(v["cli"]) == strip(v["loop"]), model
        assert v["cli"]["inputs"]["flow_author"] == "model"
