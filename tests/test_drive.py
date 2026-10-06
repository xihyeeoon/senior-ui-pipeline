r"""브라우저를 띄워 실제로 다시 걷는 비교. `pytest -m browser` 로만 실행된다.

test_baseline.py 는 저장된 스냅샷을 입력으로 쓰므로 "검사 로직이 그대로인가" 만
확인한다. 이 파일은 그 앞단 - drive() 가 페이지에서 같은 것을 긁어 오는가 - 까지
확인한다. 느리고(브라우저 8회 + mock 2회), 실행마다 흔들리는 값이 있으므로
tests/ignore.py 의 IGNORE 를 빼고 비교한다. 흔들리는 이유는 tests/README.md 에
적혀 있다.

  .\.venv\Scripts\python.exe -m pytest -m browser
"""
import asyncio
import copy
import io
import json
import os

import pytest

import _api
import capture_baseline as C
import ignore

pytestmark = pytest.mark.browser

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BASE = os.path.join(HERE, "baseline")
IDS = [c[0] for c in C.CASES]


def load(*parts):
    with io.open(os.path.join(BASE, *parts), encoding="utf-8") as f:
        return json.load(f)


def jround(obj):
    return json.loads(json.dumps(obj, ensure_ascii=False))


# 서버는 tests/conftest.py 의 `server` 하나를 모든 브라우저 테스트가 함께 쓴다
# (devserver.ensure_server 와 같은 판단 - 이 작업 트리를 서빙하는지 확인 파일로 본다).


@pytest.fixture(scope="module")
def baseline_dir():
    if not os.path.isdir(BASE):
        pytest.skip("기준값이 없습니다. tests/capture_baseline.py 를 먼저 실행하세요.")
    return BASE


# --------------------------------------------------------------------- #
# a~d 를 실제로 다시 drive 한다
# --------------------------------------------------------------------- #
def drive_case(rel, flow_name):
    """capture_baseline 과 같은 순서: 원본 drive -> 빌드 drive -> audit()."""
    flow_path = C.flow_path_of(flow_name)
    flow = _api.load_flow(flow_path)
    base_flow = _api.load_flow(None) \
        if not flow.get("derived_from_original", True) else flow
    orig_html = io.open(os.path.join(ROOT, C.ORIGINAL_REL), encoding="utf-8").read()
    rep_html = io.open(os.path.join(ROOT, rel), encoding="utf-8").read()

    orig = asyncio.run(_api.drive("%s/%s" % (C.BASE_URL, C.ORIGINAL_REL), base_flow,
                                  errors=base_flow is flow))
    rep = asyncio.run(_api.drive("%s/%s" % (C.BASE_URL, rel), flow))
    report = _api.audit(orig, rep, orig_html, rep_html, flow)
    return {"orig": orig, "rep": rep}, report


@pytest.fixture(scope="module")
def driven(server, baseline_dir):
    """브라우저 실행은 비싸다. 경우마다 한 번만 걷고 모든 검사가 나눠 쓴다."""
    out = {}
    for name, rel, flow_name in C.CASES:
        out[name] = drive_case(rel, flow_name)
    return out


@pytest.mark.parametrize("name,rel,flow_name", C.CASES, ids=IDS)
def test_snapshot_matches_baseline(driven, name, rel, flow_name):
    snaps, _ = driven[name]
    want = ignore.normalise_snapshot(load(name, "snapshots.json"))
    got = ignore.normalise_snapshot(jround(snaps))
    for side in ("orig", "rep"):
        assert got[side]["reached"] == want[side]["reached"]
        assert got[side]["missing_ids"] == want[side]["missing_ids"]
        assert got[side]["js_errors"] == want[side]["js_errors"]
        assert got[side]["load_failed"] == want[side]["load_failed"]
        assert got[side] == want[side]


@pytest.mark.parametrize("name,rel,flow_name", C.CASES, ids=IDS)
def test_audit_matches_baseline(driven, name, rel, flow_name):
    _, report = driven[name]
    want = ignore.normalise_report(load(name, "audit.json"))
    got = ignore.normalise_report(jround(report))
    assert got["passed"] == want["passed"]
    assert got["fatal"] == want["fatal"]
    assert got["warning"] == want["warning"]
    assert got["metrics"] == want["metrics"]
    assert got == want


@pytest.mark.parametrize("stage", ["styled", "wireframe"])
@pytest.mark.parametrize("name,rel,flow_name", C.CASES, ids=IDS)
def test_apply_stage_matches_baseline(driven, name, rel, flow_name, stage):
    _, report = driven[name]
    want = ignore.normalise_report(load(name, "audit.%s.json" % stage))
    got = ignore.normalise_report(
        jround(_api.apply_stage(copy.deepcopy(report), stage)))
    assert got["fatal"] == want["fatal"]
    assert got["warning"] == want["warning"]
    assert got == want


# --------------------------------------------------------------------- #
# mock 실행
# --------------------------------------------------------------------- #
@pytest.mark.parametrize("name,args", C.MOCK_RUNS, ids=[m[0] for m in C.MOCK_RUNS])
def test_mock_run_matches_baseline(server, baseline_dir, name, args):
    C.ensure_mock_input()
    summary, _code = C.run_mock(args)
    got = jround(C.strip_volatile(summary))
    want = load("%s.json" % name)
    assert got["passed"] == want["passed"]
    assert got["stopped_reason"] == want["stopped_reason"]
    assert got["budget"] == want["budget"]
    assert got["trend"] == want["trend"]
    assert got["attempts"] == want["attempts"]
    assert got == want


# --------------------------------------------------------------------- #
# 공과금 과제 (baseline/bill/) - 실제로 다시 걷는다
# --------------------------------------------------------------------- #
def drive_bill(rel, flow_name):
    """capture_baseline.capture_bill 과 같은 순서."""
    flow = _api.load_flow(C.flow_path_of(flow_name))
    orig_html = io.open(os.path.join(ROOT, C.BILL_ORIGINAL_REL), encoding="utf-8").read()
    rep_html = io.open(os.path.join(ROOT, rel), encoding="utf-8").read()
    orig = asyncio.run(_api.drive("%s/%s" % (C.BASE_URL, C.BILL_ORIGINAL_REL), flow))
    rep = asyncio.run(_api.drive("%s/%s" % (C.BASE_URL, rel), flow))
    return {"orig": orig, "rep": rep}, _api.audit(orig, rep, orig_html, rep_html, flow)


@pytest.mark.parametrize("name,rel,flow_name", C.BILL_CASES,
                         ids=[c[0] for c in C.BILL_CASES])
def test_bill_drive_matches_baseline(server, baseline_dir, name, rel, flow_name):
    snaps, report = drive_bill(rel, flow_name)
    want = ignore.normalise_snapshot(load(C.BILL, name, "snapshots.json"))
    assert ignore.normalise_snapshot(jround(snaps)) == want
    assert ignore.normalise_report(jround(report)) == \
        ignore.normalise_report(load(C.BILL, name, "audit.json"))


@pytest.mark.parametrize("name,args", C.BILL_MOCK_RUNS,
                         ids=[m[0] for m in C.BILL_MOCK_RUNS])
def test_bill_mock_run_matches_baseline(server, baseline_dir, name, args):
    """공과금 루프를 처음부터 끝까지 - 기준값 걷기 · 데이터 보존 · 형식 검사 ·
    검사기 A~J · 설명서. 통과해야 한다."""
    summary, code = C.run_mock(args)
    got = jround(C.strip_volatile(summary))
    want = load(C.BILL, "%s.json" % name)
    assert got["passed"] is True and code == 0
    assert got["task"] == "bill"
    assert got == want
