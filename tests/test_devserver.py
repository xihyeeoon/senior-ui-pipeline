r"""검사기·재구성 루프가 띄우는 개발용 서버의 회귀 테스트.

검사기는 페이지를 file:// 이 아니라 http:// 로 열어야 하므로, 재구성 루프가
`python -m http.server` 로 프로젝트 루트를 띄운다. 루트 전체를 서빙하는 것은
검사기가 어떤 빌드 파일이든 열 수 있어야 해서 그대로 둔다 - 다만 그 루트가
LAN 에 나가서는 안 된다. .envs(API 키)·.git/·sessions/ 가 다 그 안에 있다.

서버는 빈 포트에 띄우고 try/finally 로 내가 띄운 것만 끈다.
`.envs` 와 `sessions/` 는 읽지도 쓰지도 않는다.

  .\.venv\Scripts\python.exe -m pytest tests/test_devserver.py
"""
import contextlib
import io
import os
import socket
import urllib.request

import pytest

import _api


def lan_ip():
    """이 PC 의 LAN 주소. 연결되는 망이 없어도 된다."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def reachable(host, port):
    with socket.socket() as s:
        s.settimeout(1.0)
        return s.connect_ex((host, port)) == 0


@contextlib.contextmanager
def dev_server():
    """ensure_server() 가 띄우는 그대로. 포트만 비어 있는 것을 쓴다."""
    port = free_port()
    lines = []
    proc = _api.ensure_server(lines.append, port=port)
    assert proc is not None, "빈 포트인데 이미 떠 있다고 했다: %r" % lines
    try:
        yield port
    finally:
        proc.kill()
        proc.wait(timeout=10)


# --------------------------------------------------------------------- #
# LAN 에 열리지 않는다
# --------------------------------------------------------------------- #
# `python -m http.server` 는 아무것도 주지 않으면 0.0.0.0 에 띄운다. 그러면
# 검사기나 재구성 루프를 한 번 돌리는 동안, 같은 Wi-Fi 의 누구나 .envs 를
# 포함한 프로젝트 루트 전체를 디렉터리 목록과 함께 받아 갈 수 있다.
def test_개발용_서버는_LAN_에_열리지_않는다():
    ip = lan_ip()
    if ip == "127.0.0.1":
        pytest.skip("LAN 주소가 없는 PC")
    with dev_server() as port:
        assert reachable("127.0.0.1", port), "루프백으로는 열려 있어야 한다"
        assert not reachable(ip, port), "LAN 주소로 들어올 수 있다 - %s:%d" % (ip, port)


# 막는 것이 검사기를 막아서는 안 된다. 검사기는 어떤 빌드 파일이든 이 루트에서
# http:// 로 열 수 있어야 한다.
def test_루프백으로는_프로젝트_루트가_그대로_나간다():
    rel = "inputs/original_transfer.html"
    want = io.open(os.path.join(_api.ROOT_DIR, rel), "rb").read()
    with dev_server() as port:
        with urllib.request.urlopen("http://127.0.0.1:%d/%s" % (port, rel),
                                    timeout=5) as r:
            assert r.status == 200
            assert r.read() == want


# 띄운 것만 끈다는 약속. 이미 떠 있으면 None 을 돌려주고, 부른 쪽은 끝에서도
# 그 서버를 건드리지 않는다.
def test_이미_떠_있으면_새로_띄우지_않는다():
    with dev_server() as port:
        lines = []
        assert _api.ensure_server(lines.append, port=port) is None
        assert any("reusing" in x for x in lines), lines


# --------------------------------------------------------------------- #
# 테스트가 띄우는 서버도 LAN 에 열리지 않는다
# --------------------------------------------------------------------- #
# 기준값 캡처 · 브라우저 테스트가 띄우는 http.server 도 같은 약속을 지켜야 한다.
# 고치기 전: capture_baseline · test_drive · test_audit_accuracy 가 --bind 없이
# 띄워 0.0.0.0 에 열렸다.
def test_테스트가_띄우는_http_server_는_모두_루프백에만_묶인다():
    import glob
    import re
    here = os.path.dirname(os.path.abspath(__file__))
    bad = []
    for path in sorted(glob.glob(os.path.join(here, "*.py"))):
        src = io.open(path, encoding="utf-8").read()
        for m in re.finditer(r'"http\.server"', src):
            call = src[m.start(): src.find("]", m.start()) + 1]   # 명령 목록 끝까지
            if '"--bind", "127.0.0.1"' not in call and "server_cmd" not in src[m.start() - 200: m.start()]:
                bad.append("%s:%d" % (os.path.basename(path), src.count("\n", 0, m.start()) + 1))
    assert bad == [], "http.server 를 --bind 127.0.0.1 없이 띄운다: %s" % ", ".join(bad)


def test_기준값_캡처의_서버는_LAN_에_열리지_않는다():
    import subprocess
    import sys
    import time
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import capture_baseline as C
    ip = lan_ip()
    if ip == "127.0.0.1":
        pytest.skip("LAN 주소가 없는 PC")
    port = free_port()
    proc = subprocess.Popen(C.server_cmd(port), stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            if reachable("127.0.0.1", port):
                break
            time.sleep(0.1)
        assert reachable("127.0.0.1", port)
        assert not reachable(ip, port), "LAN 주소로 들어올 수 있다 - %s:%d" % (ip, port)
    finally:
        proc.kill()
        proc.wait(timeout=10)
