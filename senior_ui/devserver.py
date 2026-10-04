r"""프로젝트 루트를 127.0.0.1:3003 에 서빙하는 개발용 서버.

검사기는 페이지를 file:// 이 아니라 http:// 로 연다. 원본 시제품이 fetch 를
쓰지 않더라도, 실험 서버와 뷰어가 같은 루트를 같은 포트로 서빙하므로 검사도
같은 조건에서 돌아야 하기 때문이다.

루트 전체를 서빙하는 것은 검사기가 어떤 빌드 파일이든 열 수 있어야 해서
그대로 둔다. 대신 루프백에만 띄운다 - 그 루트에는 .envs 와 sessions/ 가 같이
들어 있어서, LAN 에 열면 검사기를 한 번 돌리는 동안 다 나간다.

ensure_server() 는 이미 떠 있는 서버를 재사용한다 - 그때는 None 을 돌려주고,
부른 쪽은 끝에서도 그 서버를 건드리지 않는다.
"""
import socket
import subprocess
import sys
import time

from .config import PORT, ROOT


# 루프백만. http.server 는 아무것도 주지 않으면 0.0.0.0 에 띄우고, 그러면
# 검사기를 한 번 돌리는 동안 같은 Wi-Fi 의 누구나 프로젝트 루트 전체를
# 디렉터리 목록과 함께 받아 간다 - .envs(API 키)·.git/·sessions/ 까지.
HOST = "127.0.0.1"


def listening(port):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex((HOST, port)) == 0


def ensure_server(log, port=PORT):
    """Return the Popen we started, or None if the port was already up (then we
    leave it alone at the end too)."""
    if listening(port):
        log("server: :%d already listening, reusing it" % port)
        return None
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port),
         "--bind", HOST, "--directory", ROOT],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        if listening(port):
            log("server: started http.server on :%d (pid %d)" % (port, proc.pid))
            return proc
        time.sleep(0.1)
    proc.kill()
    raise RuntimeError("could not start http.server on :%d" % port)
