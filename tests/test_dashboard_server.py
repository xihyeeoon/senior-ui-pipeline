r"""대시보드 서버(`senior_ui/experiment/server.py`)의 회귀 테스트.

이 서버는 대시보드를 보는 용도로만 쓴다. 본실험은 Flutter 더미앱으로 하므로
HTML 실험 장치(`web/session.html` · `/api/session`)는 기본으로 꺼져 있다.

여기서 확인하는 것은 "무엇이 나가지 않는가" 다. 서버가 프로젝트 루트 전체를
서빙하던 동안에는 같은 Wi-Fi 의 누구나 `.envs`(API 키)·`.git/`·`sessions/` 를
받아 갈 수 있었다. 그 구멍이 다시 열리면 아래 404 테스트가 먼저 깨진다.

서버는 127.0.0.1 의 빈 포트(0)에 띄우고, 띄운 것만 try/finally 로 끈다.
`sessions/` 와 `.envs` 는 읽지도 쓰지도 않는다 - 세션 저장을 켜는 테스트는
tmp_path 에만 쓴다.

  .\.venv\Scripts\python.exe -m pytest tests/test_dashboard_server.py
"""
import contextlib
import http.client
import socket
import threading

import pytest

import _api


# --------------------------------------------------------------------- #
# 서버를 띄우고 끄는 것
# --------------------------------------------------------------------- #
@contextlib.contextmanager
def serving(**kw):
    """빈 포트(0)에 서버를 하나 띄우고 포트를 넘긴다. 바인드 주소는 테스트가
    고르지 않는다 - 서버가 쓰는 make_server() 를 그대로 거친다."""
    handler = _api.srv_make_handler(**kw)
    srv = _api.srv_make_server(0, handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield srv.server_address[1]
    finally:
        srv.shutdown()
        srv.server_close()
        t.join(timeout=5)


def req(port, path, method="GET", body=None):
    """(상태코드, 본문, 헤더dict). 연결이 끊기면 예외가 그대로 올라온다."""
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        c.request(method, path, body=body)
        r = c.getresponse()
        return r.status, r.read(), dict(r.getheaders())
    finally:
        c.close()


def handler_kw(**over):
    kw = {"sessions_dir": None, "tasks": []}
    kw.update(over)
    return kw


# --------------------------------------------------------------------- #
# log_message: args[0] 이 문자열이 아닐 때
# --------------------------------------------------------------------- #
# send_error() 는 log_error("code %d, message %s", code, message) 를 부르고,
# 그 code 는 int 가 아니라 HTTPStatus 다. 문자열인지 보지 않고 `in` 을 쓰면
# TypeError 가 나면서 헤더를 쓰기도 전에 연결이 끊어진다. 그래서 모든 404 가
# 빈 응답이 되고, /favicon.ico 요청마다 핸들러 스레드가 죽었다.
def test_404_가_빈_응답이_아니라_404_로_온다():
    with serving(**handler_kw()) as port:
        status, body, _ = req(port, "/favicon.ico")
    assert status == 404
    assert body, "본문이 비어 있다 - 응답을 쓰기 전에 끊어졌다는 뜻이다"


def test_404_뒤에도_서버가_계속_받는다():
    with serving(**handler_kw()) as port:
        req(port, "/favicon.ico")
        status, _, _ = req(port, "/web/dashboard.html")
    assert status == 200

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


def reachable(host, port):
    with socket.socket() as s:
        s.settimeout(1.0)
        return s.connect_ex((host, port)) == 0


# --------------------------------------------------------------------- #
# 바인드 주소: 루프백만
# --------------------------------------------------------------------- #
# 0.0.0.0 에 띄우면 같은 Wi-Fi 의 누구나 들어올 수 있다. 이 서버는 이 PC 의
# 대시보드를 보는 용도뿐이므로 루프백 밖으로는 나가지 않는다.
def test_서버는_루프백에만_바인드한다():
    srv = _api.srv_make_server(0, _api.srv_make_handler(**handler_kw()))
    try:
        assert srv.server_address[0] == "127.0.0.1"
    finally:
        srv.server_close()


def test_LAN_주소로는_접속되지_않는다():
    ip = lan_ip()
    if ip == "127.0.0.1":
        pytest.skip("LAN 주소가 없는 PC")
    with serving(**handler_kw()) as port:
        assert reachable("127.0.0.1", port), "루프백으로는 열려 있어야 한다"
        assert not reachable(ip, port), "LAN 주소로 들어올 수 있다 - %s:%d" % (ip, port)


def test_LAN_에_여는_옵션은_없다():
    dests = {a.dest for a in _api.srv_parser()._actions}
    assert not dests & {"host", "bind", "lan", "address", "addr"}
