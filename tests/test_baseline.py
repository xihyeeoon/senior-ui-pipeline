r"""브라우저 없이 빠르게: 저장된 스냅샷으로 기준값을 다시 계산해 비교한다.

tests/capture_baseline.py 가 저장한 drive() 스냅샷을 입력으로 쓰므로 브라우저가
필요 없고, 입력이 고정되어 있으므로 출력도 고정되어야 한다. 즉 여기서는 무시할
키가 없다 - 한 글자라도 다르면 실패다. fatal/warning 은 순서까지 같아야 한다.

브라우저를 띄워 실제로 다시 걷는 비교는 tests/test_drive.py (`pytest -m browser`).

  .\.venv\Scripts\python.exe -m pytest
"""
import copy
import hashlib
import io
import json
import os
import sys

import pytest

import _api
import capture_baseline as C

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BASE = os.path.join(HERE, "baseline")
FIXTURES = os.path.join(HERE, "fixtures", "sessions")

pytestmark = pytest.mark.skipif(
    not os.path.isdir(BASE),
    reason="기준값이 없습니다. tests/capture_baseline.py 를 먼저 실행하세요.")


# --------------------------------------------------------------------- #
# 읽기 도우미
# --------------------------------------------------------------------- #
def load(*parts):
    with io.open(os.path.join(BASE, *parts), encoding="utf-8") as f:
        return json.load(f)


def load_text(*parts):
    with io.open(os.path.join(BASE, *parts), encoding="utf-8") as f:
        return f.read()


def jround(obj):
    """튜플/집합이 아닌 순수 JSON 모양으로 맞춘다. 기준값은 JSON 으로 저장되어
    있으므로 비교 전에 같은 표현으로 만들어야 한다."""
    return json.loads(json.dumps(obj, ensure_ascii=False))


def case_inputs(name, rel, flow_name):
    flow_path = C.flow_path_of(flow_name)
    return (io.open(os.path.join(ROOT, C.ORIGINAL_REL), encoding="utf-8").read(),
            io.open(os.path.join(ROOT, rel), encoding="utf-8").read(),
            _api.load_flow(flow_path), flow_path)


def recompute(name, rel, flow_name):
    """저장된 스냅샷으로 audit() 을 다시 계산한다."""
    snaps = load(name, "snapshots.json")
    orig_html, rep_html, flow, _ = case_inputs(name, rel, flow_name)
    return _api.audit(snaps["orig"], snaps["rep"], orig_html, rep_html, flow)


IDS = [c[0] for c in C.CASES]
WITH_FLOW = [c for c in C.CASES if c[2]]


# --------------------------------------------------------------------- #
# audit()
# --------------------------------------------------------------------- #
@pytest.mark.parametrize("name,rel,flow_name", C.CASES, ids=IDS)
def test_audit_matches_baseline(name, rel, flow_name):
    want = load(name, "audit.json")
    got = jround(recompute(name, rel, flow_name))

    # 목록은 순서까지 같아야 한다. 먼저 따로 비교해 실패 메시지를 읽을 수 있게 한다.
    assert got["fatal"] == want["fatal"]
    assert got["warning"] == want["warning"]
    assert got["metrics"] == want["metrics"]
    assert got == want


@pytest.mark.parametrize("stage", ["styled", "wireframe"])
@pytest.mark.parametrize("name,rel,flow_name", C.CASES, ids=IDS)
def test_apply_stage_matches_baseline(name, rel, flow_name, stage):
    want = load(name, "audit.%s.json" % stage)
    report = recompute(name, rel, flow_name)
    # apply_stage 는 리포트를 제자리에서 바꾼다. 사본을 넘긴다.
    got = jround(_api.apply_stage(copy.deepcopy(report), stage))

    assert got["fatal"] == want["fatal"]
    assert got["warning"] == want["warning"]
    assert got["passed"] == want["passed"]
    assert got == want


def test_wireframe_drops_only_visual_checks():
    """apply_stage 의 계약: 와이어프레임에서 빠지는 것은 D·E·G·H 뿐이고
    A·B·C·F·I 는 그대로 남는다. 기준값 비교와 별도로 이 규칙을 못박는다."""
    assert set(_api.STAGES["wireframe"]["checks"]) == {"A", "B", "C", "F", "I"}
    dropped = set(_api.STAGES["styled"]["checks"]) - set(
        _api.STAGES["wireframe"]["checks"])
    assert dropped == {"D", "E", "G", "H"}


# --------------------------------------------------------------------- #
# validate_flow
# --------------------------------------------------------------------- #
@pytest.mark.parametrize("name,rel,flow_name", WITH_FLOW,
                         ids=[c[0] for c in WITH_FLOW])
def test_validate_flow_matches_baseline(name, rel, flow_name):
    want = load(name, "validate_flow.json")
    _, rep_html, flow, _ = case_inputs(name, rel, flow_name)
    got = jround(_api.validate_flow(copy.deepcopy(flow), rep_html))
    assert got == want


# --------------------------------------------------------------------- #
# retry_block / brief_failure
# --------------------------------------------------------------------- #
@pytest.mark.parametrize("name,rel,flow_name", WITH_FLOW,
                         ids=[c[0] for c in WITH_FLOW])
def test_retry_block_matches_baseline(name, rel, flow_name):
    want = load_text("retry_block", "%s.txt" % name)
    report = load(name, "audit.json")
    _, rep_html, _, flow_path = case_inputs(name, rel, flow_name)
    flow_text = io.open(flow_path, encoding="utf-8").read()
    got = _api.retry_block(report, rep_html, flow_text)
    assert got == want


def test_retry_block_synthetic_matches_baseline():
    """파생 fatal · stack 이 붙은 JS 오류 · Playwright 로그를 한자리에 넣은
    합성 리포트. 실제 실행 세 개로는 이 세 갈래가 다 밟히지 않는다."""
    want = load_text("retry_block", "synthetic.txt")
    got = _api.retry_block(copy.deepcopy(C.SYNTH_REPORT), C.SYNTH_HTML,
                           C.SYNTH_FLOW_TEXT)
    assert got == want


def test_brief_failure_matches_baseline():
    want = load_text("brief_failure.txt")
    assert _api.brief_failure(C.PLAYWRIGHT_DETAIL) + "\n" == want


# --------------------------------------------------------------------- #
# parse_reply / mock_reply
# --------------------------------------------------------------------- #
@pytest.mark.parametrize("mode", ["pass", "fail"])
def test_parse_reply_matches_baseline(mode):
    want = load("parse_reply.json")[mode]
    reply = _api.mock_reply(mode)
    html, flow, flow_text = _api.parse_reply(reply["text"])

    def sha(s):
        return hashlib.sha256(s.encode("utf-8")).hexdigest()

    assert reply["finish_reason"] == want["reply_finish_reason"]
    assert sha(reply["text"]) == want["reply_text_sha256"]
    assert len(html) == want["html_len"]
    assert sha(html) == want["html_sha256"]
    assert jround(flow) == want["flow"]
    assert sha(flow_text) == want["flow_text_sha256"]


# --------------------------------------------------------------------- #
# session_report
# --------------------------------------------------------------------- #
def run_session_report(out_dir):
    md = os.path.join(out_dir, "session_report.md")
    csv = os.path.join(out_dir, "session_report.csv")
    argv, stdout = sys.argv, sys.stdout
    sys.argv = ["session_report.py", "--sessions", FIXTURES, "--out", md,
                "--csv", csv]
    sys.stdout = io.StringIO()
    try:
        code = _api.sr_main()
    finally:
        sys.argv, sys.stdout = argv, stdout
    assert code == 0
    return (io.open(md, encoding="utf-8").read(),
            io.open(csv, encoding="utf-8-sig", newline="").read())


def test_session_report_matches_baseline(tmp_path):
    assert os.path.isdir(FIXTURES), \
        "세션 고정물이 없습니다. tests/capture_baseline.py 를 먼저 실행하세요."
    md, csv = run_session_report(str(tmp_path))
    assert md == load_text("session_report.md")
    assert csv == io.open(os.path.join(BASE, "session_report.csv"),
                          encoding="utf-8-sig", newline="").read()


def test_session_report_aggregations_match_baseline():
    """집계 함수를 하나씩 직접 불러 본다. md 전체 비교만 하면 어느 집계가
    달라졌는지 알 수 없다. 각 표는 md 에 그대로 들어가므로 부분 문자열이다."""
    md = load_text("session_report.md")
    rows = _api.sr_load(FIXTURES)
    assert len(rows) == 4
    conditions = sorted({r["condition"] for r in rows})

    for label, produced in [
        ("1. 진행 현황", _api.sr_progress(rows, conditions)),
        ("2. 피험자별", _api.sr_per_session(rows)),
        ("3. 조건 비교", _api.sr_compare(rows, conditions, False)),
        ("4. 화면별 체류", _api.sr_dwell(rows, conditions)),
        ("5. 막힌 지점", _api.sr_trouble(rows, conditions)),
    ]:
        assert produced in md, "%s 의 표가 기준값 md 와 다릅니다" % label

    # summarise 는 표에 숫자로만 나타난다. 중앙값/평균/범위/개수를 직접 못박는다.
    secs = [(r.get("metrics") or {}).get("seconds") for r in rows]
    med, mean, lo, hi, n = _api.sr_summarise(secs)
    assert (round(med, 3), round(mean, 3), lo, hi, n) == (85.65, 104.275, 61.3, 184.5, 4)
