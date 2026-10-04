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
import io
import json
import os
import re
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
    kw = {"sessions_dir": None, "tasks": [], "allow_session": False}
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

# --------------------------------------------------------------------- #
# 정적 파일: 허용 목록만
# --------------------------------------------------------------------- #
# 프로젝트 루트 전체를 서빙하던 동안 밖으로 나갈 수 있던 것들. 하나라도
# 200 이면 그 구멍이 다시 열린 것이다. 테스트는 이 파일들을 직접 열지 않고
# 서버가 무엇을 돌려주는지만 본다.
LEAKS = [
    "/.envs",                      # OPENAI_API_KEY
    "/.git/config",
    "/.gitignore",
    "/sessions/",                  # 피험자 기록
    "/inputs/1.png",               # 실제 SOL 캡처 - 실명이 보인다
    "/inputs/KakaoTalk_20260915_153359065.png",
    "/requirements.txt",
    "/pytest.ini",
    "/senior_ui/config.py",
    "/web/session.html",           # HTML 실험 장치는 쓰지 않는다
]


@pytest.mark.parametrize("path", LEAKS)
def test_허용_목록_밖은_404(path):
    with serving(**handler_kw()) as port:
        status, _, _ = req(port, path)
    assert status == 404


# 디렉터리 목록이 켜져 있으면 폴더 이름만으로 나머지를 다 찾아낼 수 있다.
@pytest.mark.parametrize("path", ["/", "/web/", "/inputs/", "/outputs/",
                                 "/results/", "/sessions/", "/.git/"])
def test_디렉터리_목록은_나가지_않는다(path):
    with serving(**handler_kw()) as port:
        status, body, _ = req(port, path)
    assert status == 404
    assert b"Directory listing" not in body


# 경로를 거슬러 올라가는 요청. 허용 목록은 바로잡은 경로로 본다.
@pytest.mark.parametrize("path", [
    "/web/../.envs",
    "/web/dashboard.html/../../.envs",
    "/outputs/../.envs",
    "/..%2f.envs",
    "/web/%2e%2e/.envs",
    "/outputs/shots/../../.envs",
])
def test_거슬러_올라가도_404(path):
    with serving(**handler_kw()) as port:
        status, _, _ = req(port, path)
    assert status == 404


# --------------------------------------------------------------------- #
# 대시보드가 읽는 것은 다 나가야 한다
# --------------------------------------------------------------------- #
ALLOWED = [
    "/web/dashboard.html",
    "/web/dashboard.css",
    "/web/dashboard.js",
    "/outputs/index.json",
    "/inputs/original_transfer.html",       # 화면 비교의 기준 빌드
    "/results/restructured_run4.html",
    "/results/shots/run4/audit_account.png",
    "/outputs/shots/before_home.png",
]


@pytest.mark.parametrize("path", ALLOWED)
def test_대시보드가_읽는_것은_200(path):
    if not os.path.exists(os.path.join(_api.ROOT_DIR, path.lstrip("/"))):
        pytest.skip("이 PC 에 없는 파일: %s" % path)
    with serving(**handler_kw()) as port:
        status, body, _ = req(port, path)
    assert status == 200
    assert body


def test_index_가_가리키는_빌드와_스크린샷이_다_나간다():
    """'화면 비교' 탭이 iframe 과 img 로 여는 경로. outputs/ 는 PC 마다
    내용이 달라서 index.json 에 적힌 것을 그대로 따라간다."""
    ix_path = os.path.join(_api.ROOT_DIR, "outputs", "index.json")
    if not os.path.exists(ix_path):
        pytest.skip("outputs/index.json 이 없다 - build_index 를 먼저 돌린다")
    with io.open(ix_path, encoding="utf-8") as f:
        ix = json.load(f)

    builds = ([ix["baseline"]] if ix.get("baseline") else []) + (ix.get("builds") or [])
    paths = []
    for b in builds:
        if b.get("html"):
            paths.append(b["html"])
        shots = sorted((b.get("shots") or {}).values())
        paths.extend(shots[:1])
    paths = [p for p in paths if os.path.exists(os.path.join(_api.ROOT_DIR, p))]
    assert paths, "index.json 이 가리키는 파일이 이 PC 에 하나도 없다"

    bad = []
    with serving(**handler_kw()) as port:
        for rel in paths:
            status, _, _ = req(port, "/" + rel)
            if status != 200:
                bad.append((rel, status))
    assert not bad, "대시보드가 읽는데 서버가 막는다: %r" % (bad,)

# --------------------------------------------------------------------- #
# /api/session: 기본으로 꺼져 있다
# --------------------------------------------------------------------- #
# 본실험은 Flutter 더미앱으로 한다. HTML 실험 장치는 쓰지 않으므로 세션을
# 받아 쓰는 길도 기본으로 닫는다. --session 을 줄 때만 열리고, 그때도
# 127.0.0.1 에서 온 요청만 받는다.
#
# 저장 테스트는 tmp_path 에만 쓴다 - 레포의 sessions/ 는 건드리지 않는다.
PAYLOAD = {"participant": 1, "condition": "original", "order_index": 0,
           "completed": True, "elapsed_ms": 1234,
           "metrics": {"seconds": 12.3, "taps": 9, "misses": 0, "backs": 1},
           "events": []}


def post_session(port, payload=None):
    body = json.dumps(payload if payload is not None else PAYLOAD).encode("utf-8")
    return req(port, "/api/session", method="POST", body=body)


def test_기본으로는_세션을_받지_않는다(tmp_path):
    sess = tmp_path / "sessions"
    with serving(**handler_kw(sessions_dir=str(sess))) as port:
        status, _, _ = post_session(port)
    assert status == 404
    assert not sess.exists(), "꺼져 있는데 폴더를 만들었다"


@pytest.mark.parametrize("path", ["/api/config", "/api/sessions"])
def test_실험_장치_전용_엔드포인트도_기본으로_꺼져_있다(path):
    with serving(**handler_kw()) as port:
        status, _, _ = req(port, path)
    assert status == 404


def test_session_옵션을_주면_저장된다(tmp_path):
    sess = tmp_path / "sessions"
    with serving(**handler_kw(sessions_dir=str(sess), allow_session=True)) as port:
        status, body, _ = post_session(port)
    assert status == 200, body
    assert json.loads(body)["ok"] is True
    assert [f.name for f in sess.iterdir()] == ["P01_1_original.json"]


@pytest.mark.parametrize("path", ["/api/config", "/api/sessions", "/web/session.html"])
def test_session_옵션을_주면_실험_장치도_나간다(path, tmp_path):
    kw = handler_kw(sessions_dir=str(tmp_path), allow_session=True)
    with serving(**kw) as port:
        status, body, _ = req(port, path)
    assert status == 200, body


# 루프백에만 바인드하므로 밖에서는 닿지 않지만, 받는 쪽에서도 한 번 더 본다.
@pytest.mark.parametrize("addr,ok", [
    ("127.0.0.1", True),
    ("::1", True),
    ("::ffff:127.0.0.1", True),
    ("192.168.0.5", False),
    ("10.11.140.123", False),
    ("0.0.0.0", False),
    ("", False),
])
def test_루프백_판정(addr, ok):
    assert _api.srv_is_local(addr) is ok


def test_session_을_켜도_밖에서_온_요청은_거절한다(tmp_path, monkeypatch):
    sess = tmp_path / "sessions"
    monkeypatch.setattr(_api.srv_module, "is_local", lambda addr: False)
    with serving(**handler_kw(sessions_dir=str(sess), allow_session=True)) as port:
        status, _, _ = post_session(port)
    assert status == 403
    assert not sess.exists()

# --------------------------------------------------------------------- #
# /api/reindex: POST 로만
# --------------------------------------------------------------------- #
# '다시 읽기' 는 outputs/index.json 을 새로 쓴다. GET 으로 받으면 주소창에
# 한 번 넣는 것으로도, 브라우저의 선읽기로도 돌아간다. 여기서는 실제로
# 색인을 다시 만들지 않고 불렸는지만 본다 - outputs/ 를 건드리지 않는다.
@pytest.fixture
def reindex_calls(monkeypatch):
    calls = []

    def fake():
        calls.append(1)
        return {"ok": True, "builds": 0, "changes": 0, "generated": "2026-10-04T00:00:00"}

    monkeypatch.setattr(_api.srv_module, "reindex", fake)
    return calls


def test_reindex_는_GET_으로는_돌지_않는다(reindex_calls):
    with serving(**handler_kw()) as port:
        status, _, headers = req(port, "/api/reindex")
    assert status == 405
    assert headers.get("Allow") == "POST"
    assert reindex_calls == [], "GET 으로 색인을 다시 만들었다"


def test_reindex_는_POST_로_돈다(reindex_calls):
    with serving(**handler_kw()) as port:
        status, body, _ = req(port, "/api/reindex", method="POST")
    assert status == 200, body
    assert json.loads(body)["ok"] is True
    assert reindex_calls == [1]


def test_대시보드의_다시_읽기는_POST_로_보낸다():
    js = io.open(os.path.join(_api.ROOT_DIR, "web", "dashboard.js"),
                 encoding="utf-8").read()
    i = js.index("/api/reindex")
    call = js[i:i + 120]
    assert "POST" in call, "dashboard.js 가 아직 GET 으로 부른다: %r" % call

# --------------------------------------------------------------------- #
# 안내 문구: 폰 주소와 방화벽 안내는 없다
# --------------------------------------------------------------------- #
# 폰에서 여는 주소를 띄우고 방화벽을 열라고 안내하던 것은 LAN 에 서빙할
# 때의 안내다. 그 주소와 안내가 남아 있으면, 서버를 고쳐도 사람이 다시
# 구멍을 낸다.
BAD = ["New-NetFirewallRule", "방화벽", "폰에서", "같은 Wi-Fi", "session.html"]


def test_서버_안내에는_대시보드_주소만_있다():
    out = _api.srv_banner(3003, "sessions", [], allow_session=False)
    assert "http://localhost:3003/web/dashboard.html" in out
    for bad in BAD:
        assert bad not in out, "안내에 아직 %r 가 있다" % bad
    assert not re.search(r"(?:\d{1,3}\.){3}\d{1,3}",
                         out.replace("127.0.0.1", "")), "LAN 주소가 보인다"


def test_시작bat_은_대시보드만_안내한다():
    bat = io.open(os.path.join(_api.ROOT_DIR, "시작.bat"), encoding="utf-8").read()
    assert "http://localhost:3003/web/dashboard.html" in bat
    for bad in BAD:
        assert bad not in bat, "시작.bat 에 아직 %r 가 있다" % bad


# 설명문은 전에 어떤 구멍이 있었는지를 적고 있으므로 단어로 걸러서는 안 된다.
# 코드로 남아 있으면 안 되는 것만 본다 - LAN 주소를 구하는 함수와 방화벽 명령.
def test_서버_모듈에_LAN_주소를_구하는_코드가_없다():
    src = io.open(_api.srv_module.__file__, encoding="utf-8").read()
    assert "local_ip" not in src
    assert "New-NetFirewallRule" not in src
    assert '"0.0.0.0"' not in src
