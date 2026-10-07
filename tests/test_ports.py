r"""자동 실행의 포트 (11-9).

재구성 루프 · 테스트 · 기준값 캡처는 빈 포트(port 0)를 잡아 쓴다. 전에는 셋 다 :3003
하나를 썼다 - 이미 떠 있으면 재사용하고, 띄운 쪽이 끝에서 끈다. 그래서 둘을 같이 돌리면
먼저 끝난 쪽이 다른 쪽이 쓰던 서버를 끄고, 남은 쪽은 걷다가 연결이 끊긴다. 같은 포트를
명시하지 않으면 이제 동시에 돌려도 된다.

`--port` 를 주었을 때만 그 포트를 쓰고, 그때는 전처럼 그 포트의 서버가 이 작업 트리를
서빙하는지 확인 파일로 본다 (devserver.serves_this_tree). 사람이 직접 띄우는 devserver
CLI 와 대시보드 서버는 3003 그대로다.

서버는 띄우지만 브라우저도 모델도 부르지 않는다.
"""
import io
import os

import pytest

import _api
from test_devserver import lan_ip, reachable
from test_restructure_bugs import (FAKE_SNAPSHOT, always_reply,  # noqa: F401
                                   fake_run_env, out_root, passing_report, run_loop)

config = _api.config_module
devserver = _api.devserver_module
loop = _api.loop_module
ROOT = _api.ROOT_DIR


def stop(proc):
    if proc is not None and proc.poll() is None:
        proc.terminate()
        proc.wait(timeout=10)


# --------------------------------------------------------------------- #
# 1. 값
# --------------------------------------------------------------------- #
def test_automatic_runs_take_a_free_port_and_people_keep_3003():
    assert config.AUTO_PORT == 0
    assert config.PORT == 3003                      # devserver CLI · 대시보드
    assert devserver.build_parser().parse_args([]).port == 3003


def test_the_restructure_cli_takes_a_port_only_when_given():
    from senior_ui.restructure.__main__ import build_parser
    assert build_parser().parse_args([]).port is None
    assert build_parser().parse_args(["--port", "3010"]).port == 3010


def test_pytest_takes_a_free_port_unless_told(pytestconfig):
    assert pytestconfig.getoption("--port") == 0


def test_url_for_follows_the_port():
    assert config.url_for("inputs/a.html") == "http://localhost:3003/inputs/a.html"
    assert config.url_for("inputs/a.html", 45678) == "http://localhost:45678/inputs/a.html"


# --------------------------------------------------------------------- #
# 2. 빈 포트의 서버
# --------------------------------------------------------------------- #
def test_two_automatic_servers_do_not_share_one():
    """고치기 전: 둘째가 첫째의 :3003 을 재사용했고(None), 첫째가 끝에서 끄면 둘째의
    서버가 사라졌다."""
    lines = []
    a = devserver.ensure_server(lines.append, port=config.AUTO_PORT)
    b = None
    try:
        b = devserver.ensure_server(lines.append, port=config.AUTO_PORT)
        assert a is not None and b is not None, lines
        assert a.port != b.port and 0 not in (a.port, b.port)
        assert devserver.serves_this_tree(a.port) and devserver.serves_this_tree(b.port)
        stop(a)
        assert devserver.serves_this_tree(b.port)     # 한쪽을 꺼도 다른 쪽은 그대로
        assert any("빈 포트" in x for x in lines), lines
    finally:
        stop(a)
        stop(b)


def test_a_free_port_server_is_loopback_only():
    ip = lan_ip()
    if ip == "127.0.0.1":
        pytest.skip("LAN 주소가 없는 PC")
    proc = devserver.ensure_server(lambda m: None, port=config.AUTO_PORT)
    try:
        assert reachable("127.0.0.1", proc.port)
        assert not reachable(ip, proc.port)
    finally:
        stop(proc)


def test_an_explicit_port_still_checks_the_tree(tmp_path):
    """--port 를 주면 전과 같다 - 떠 있는 서버가 이 작업 트리가 아니면 멈춘다."""
    other = devserver.ensure_server(lambda m: None, port=config.AUTO_PORT, root=str(tmp_path))
    try:
        with pytest.raises(RuntimeError) as e:
            devserver.ensure_server(lambda m: None, port=other.port)
        assert ":%d" % other.port in str(e.value)
    finally:
        stop(other)


# --------------------------------------------------------------------- #
# 3. 재구성 루프
# --------------------------------------------------------------------- #
class FakeServer:
    pid = 4242

    def __init__(self, port):
        self.port = port
        self.stopped = False

    def terminate(self):
        self.stopped = True


@pytest.fixture
def loop_ports(fake_run_env):
    """루프가 서버를 어느 포트로 띄워 달라고 했는지, 원본과 빌드를 어느 URL 로 열었는지."""
    seen = {"asked": [], "driven": [], "audited": [], "server": None}

    def ensure(log, port=None):
        seen["asked"].append(port)
        if port == 0:
            seen["server"] = FakeServer(45678)
            return seen["server"]
        return None                                  # 이미 떠 있는 것을 재사용

    async def drive(url, flow, want_shots=None, **_kw):
        seen["driven"].append(url)
        return dict(FAKE_SNAPSHOT)

    def audit(orig, orig_html, html_path, flow_path, url, shots, stage,
              original_url=None, **kw):
        seen["audited"].append((url, original_url))
        return passing_report()

    fake_run_env.setattr(loop, "ensure_server", ensure)
    fake_run_env.setattr(loop.A, "drive", drive)
    fake_run_env.setattr(loop, "run_audit", audit)
    return seen


def test_the_loop_takes_a_free_port_by_default(loop_ports, fake_run_env, out_root):
    code, _summary = run_loop(fake_run_env, out_root, always_reply, attempts=1)
    assert code == 0
    assert loop_ports["asked"] == [0]
    assert loop_ports["driven"] == ["http://localhost:45678/inputs/original_transfer.html"]
    build_url, orig_url = loop_ports["audited"][0]
    assert build_url.startswith("http://localhost:45678/.pytest-outputs/")
    assert orig_url == "http://localhost:45678/inputs/original_transfer.html"
    assert loop_ports["server"].stopped


def test_the_loop_uses_the_given_port(loop_ports, fake_run_env, out_root):
    _code, _summary = run_loop(fake_run_env, out_root, always_reply, attempts=1, port=3010)
    assert loop_ports["asked"] == [3010]
    assert loop_ports["driven"] == ["http://localhost:3010/inputs/original_transfer.html"]
    assert loop_ports["audited"][0][1] == "http://localhost:3010/inputs/original_transfer.html"


# --------------------------------------------------------------------- #
# 4. 기준값 캡처 · 문서
# --------------------------------------------------------------------- #
def test_the_baseline_capture_takes_a_free_port_by_default():
    import inspect
    import capture_baseline as C
    assert inspect.signature(C.start_server).parameters["port"].default == config.AUTO_PORT


def test_the_docs_allow_parallel_runs_unless_the_same_port_is_given():
    rule = "같은 포트를 명시하지 않으면 동시에 돌려도 된다"
    for rel in ("docs/README.md", "tests/README.md"):
        text = io.open(os.path.join(ROOT, rel), encoding="utf-8").read()
        assert rule in text, rel
