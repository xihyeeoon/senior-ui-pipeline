r"""프로젝트 루트를 :3003 에 서빙하는 개발용 서버.

검사기는 페이지를 file:// 이 아니라 http:// 로 연다. 원본 시제품이 fetch 를
쓰지 않더라도, 실험 서버와 뷰어가 같은 루트를 같은 포트로 서빙하므로 검사도
같은 조건에서 돌아야 하기 때문이다.

ensure_server() 는 이미 떠 있는 서버를 재사용한다 - 그때는 None 을 돌려주고,
부른 쪽은 끝에서도 그 서버를 건드리지 않는다.
"""
import socket
import subprocess
import sys
import time

from .config import PORT, ROOT


def listening(port):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def ensure_server(log):
    """Return the Popen we started, or None if :3003 was already up (then we
    leave it alone at the end too)."""
    if listening(PORT):
        log("server: :%d already listening, reusing it" % PORT)
        return None
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(PORT), "--directory", ROOT],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        if listening(PORT):
            log("server: started http.server on :%d (pid %d)" % (PORT, proc.pid))
            return proc
        time.sleep(0.1)
    proc.kill()
    raise RuntimeError("could not start http.server on :%d" % PORT)
