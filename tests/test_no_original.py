r"""검사기는 원본 없이 통과를 내지 않는다 (11-9b).

11-9 의 동시 실행 확인에서 검사기 CLI 가 `--original` 없이 기본 원본 URL(:3003, 아무도
듣지 않음)을 열고도 멈추지 않았다. 원본 스냅샷이 비어 있으니 원본과 견주는 검사(입구 K
등)가 할 말이 없어졌고, 입구 31개를 모두 지운 sol 의 첫 답이 "통과" 로 나왔다 - 같은
빌드를 루프는 K fatal 로 떨어뜨렸다.

원본 페이지를 열지 못했거나(load_failed) 원본에서 화면을 하나도 읽지 못했으면
(`window.__screen()` 도 `.screen.on` 도 없는 페이지 - 서버의 404 같은) 검사하지 않고
멈춘다. CLI 는 종료 코드 2 (cannot_run), 재구성 루프는 실행 시작에서 cannot_start
(종료 2) - 루프의 시도마다의 판정은 시작에 걸은 그 원본 스냅샷을 쓰므로 같은 보호를 받는다.
"""
import io
import json
import os
import socket

import pytest

import _api
import capture_baseline as C
from test_restructure_bugs import (always_reply, fake_run_env, out_root,  # noqa: F401
                                   passing_report, run_loop)

ROOT = _api.ROOT_DIR
CLI = _api.audit_cli_module
drive_module = _api.drive_module
loop = _api.loop_module

DEAD = {"screens": {}, "reached": [], "dialogs": [], "js_errors": [],
        "load_failed": "Error: net::ERR_CONNECTION_REFUSED at http://localhost:1/x.html"}
# 서버가 404 를 돌려준 페이지 - 열리기는 했지만 화면이 없다
EMPTY = {"screens": {"home": {"landed_on": None, "dom_screen": None, "choices": {}},
                     "menu": {"error": "TimeoutError: locator('#go') ..."}},
         "reached": [None], "dialogs": [], "js_errors": [], "load_failed": None}
READ = {"screens": {"home": {"landed_on": "home", "dom_screen": "home", "choices": {}}},
        "reached": ["home"], "dialogs": [], "js_errors": [], "load_failed": None}


# --------------------------------------------------------------------- #
# 1. 무엇을 "읽지 못했다" 로 보는가
# --------------------------------------------------------------------- #
def test_what_counts_as_nothing_read():
    assert "열지 못했다" in drive_module.nothing_read(DEAD)
    assert "ERR_CONNECTION_REFUSED" in drive_module.nothing_read(DEAD)
    assert "화면을 하나도 읽지 못했다" in drive_module.nothing_read(EMPTY)
    assert drive_module.nothing_read(READ) is None
    # 켜진 화면만 있고 기록(__screen)이 없어도 화면은 읽은 것이다
    lit = {"screens": {"home": {"landed_on": None, "dom_screen": "home"}}, "load_failed": None}
    assert drive_module.nothing_read(lit) is None


# --------------------------------------------------------------------- #
# 2. 검사기 CLI
# --------------------------------------------------------------------- #
def cli_with_original(monkeypatch, tmp_path, orig_snapshot):
    """원본 걷기는 `orig_snapshot` 을, 빌드 걷기는 READ 를 돌려준다. 판정은 늘 통과다 -
    원본을 읽지 못했는데도 그 판정까지 가는지를 본다."""
    seen = []

    async def fake_drive(url, flow, want_shots=None, errors=True, **_kw):
        seen.append(url)
        return json.loads(json.dumps(orig_snapshot if len(seen) == 1 else READ))
    monkeypatch.setattr(CLI, "drive", fake_drive)
    monkeypatch.setattr(CLI, "audit", lambda *a: {"passed": True, "fatal": [],
                                                  "warning": [], "metrics": {}})
    monkeypatch.setattr(CLI, "apply_stage", lambda r, s: r)
    out = tmp_path / "audit.json"
    stdout = io.StringIO()
    monkeypatch.setattr("sys.stdout", stdout)
    code = _api.audit_cli_main(["--build", "http://localhost:1/b.html",
                                "--build-file", os.path.join(ROOT, "inputs",
                                                             "original_transfer.html"),
                                "--original", "http://localhost:1/inputs/original_transfer.html",
                                "--out", str(out)])
    return code, json.load(io.open(str(out), encoding="utf-8")), seen


@pytest.mark.parametrize("orig", [DEAD, EMPTY], ids=["load_failed", "no_screen"])
def test_the_cli_stops_without_an_original(monkeypatch, tmp_path, orig):
    """고치기 전: 종료 0 - 원본 없이 "통과"."""
    code, report, seen = cli_with_original(monkeypatch, tmp_path, orig)
    assert code == 2
    assert report["passed"] is False
    detail = report["fatal"][0]["detail"]
    assert "원본" in detail and "http://localhost:1/inputs/original_transfer.html" in detail
    assert len(seen) == 1                       # 빌드는 걷지 않는다


def test_the_cli_still_judges_with_a_readable_original(monkeypatch, tmp_path):
    code, report, seen = cli_with_original(monkeypatch, tmp_path, READ)
    assert code == 0 and report["passed"] is True and len(seen) == 2


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.browser
def test_the_cli_stops_on_an_original_nobody_serves(server, tmp_path):
    """실제로 걷는다 - 원본 URL 의 포트에 아무도 없다. 빌드는 이 테스트의 서버에 있다."""
    import sys
    rel = "inputs/original_transfer.html"
    out = tmp_path / "audit.json"
    saved, sys.stdout = sys.stdout, io.StringIO()
    try:
        code = _api.audit_cli_main(["--build", "%s/%s" % (C.BASE_URL, rel),
                                    "--build-file", os.path.join(ROOT, rel),
                                    "--original", "http://127.0.0.1:%d/%s" % (free_port(), rel),
                                    "--out", str(out)])
    finally:
        sys.stdout = saved
    assert code == 2
    report = json.load(io.open(str(out), encoding="utf-8"))
    assert report["passed"] is False and "원본" in report["fatal"][0]["detail"]


# --------------------------------------------------------------------- #
# 3. 재구성 루프 - 실행 시작의 원본 걷기
# --------------------------------------------------------------------- #
@pytest.mark.parametrize("orig", [DEAD, EMPTY], ids=["load_failed", "no_screen"])
def test_the_loop_does_not_start_without_an_original(fake_run_env, out_root, orig):
    """고치기 전: 빈 원본 스냅샷으로 시작해 (가짜 판정이) 통과했다 - 종료 0. 루프의
    시도마다의 판정(run_audit)은 이 스냅샷을 쓴다."""
    async def drive(url, flow, want_shots=None, **_kw):
        return json.loads(json.dumps(orig))
    fake_run_env.setattr(loop.A, "drive", drive)
    asked = []
    fake_run_env.setattr(loop, "run_audit", lambda *a, **kw: asked.append(1) or passing_report())
    code, summary = run_loop(fake_run_env, out_root, always_reply, attempts=1)
    assert code == 2
    assert summary["stopped_reason"] == "cannot_start"
    assert "원본" in summary["error"]
    assert asked == []
