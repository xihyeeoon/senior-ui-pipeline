r"""이 작업 트리를 127.0.0.1:3003 에 서빙하는 개발용 서버.

검사기는 페이지를 file:// 이 아니라 http:// 로 연다 - 원본 시제품이 fetch 를
쓰지 않더라도, 대시보드도 같은 포트로 서빙하므로 검사도 같은 조건에서 돈다.

루트 전체를 서빙하는 것은 검사기가 어떤 빌드 파일이든 열 수 있어야 해서
그대로 둔다. 대신 루프백에만 띄운다 - 그 루트에는 .envs 와 sessions/ 가 같이
들어 있어서, LAN 에 열면 검사기를 한 번 돌리는 동안 다 나간다.

ensure_server() 는 이미 떠 있는 서버를 재사용한다 - 그때는 None 을 돌려주고,
부른 쪽은 끝에서도 그 서버를 건드리지 않는다. 다만 재사용 전에 그것이 **이 작업
트리의 파일을** 서빙하는지 확인한다 (serves_this_tree). 아니면 멈춘다 - 남의
서버로 돌린 검사는 통과하든 떨어지든 뜻을 알 수 없다.

대시보드 서버(python -m senior_ui.experiment.server · 시작.bat)와는 다르다. 그쪽은
허용 목록만 서빙하므로 .mock-outputs/ · SENIOR_UI_OUTPUTS 의 빌드를 열지 못하고,
ensure_server 도 그것을 재사용하지 않는다.
"""
import io
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

from .config import PORT, ROOT


# 루프백만. http.server 는 아무것도 주지 않으면 0.0.0.0 에 띄우고, 그러면
# 검사기를 한 번 돌리는 동안 같은 Wi-Fi 의 누구나 프로젝트 루트 전체를
# 디렉터리 목록과 함께 받아 간다 - .envs(API 키)·.git/·sessions/ 까지.
HOST = "127.0.0.1"


def listening(port):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex((HOST, port)) == 0


# 떠 있는 서버가 이 작업 트리를 서빙하는지 확인할 때 대조하는 파일 (.gitignore).
#
# 전에는 원본 HTML 의 해시를 대조했다. 그것은 "같은 저장소의 파일" 이지 "이 작업
# 트리의 파일" 이 아니다 - 다른 worktree 나 사본도 원본이 바이트까지 같으므로 그
# 서버를 재사용했고, 검사기는 이쪽이 아니라 그쪽의 빌드 · 산출물을 열었다 (감사
# E-7 · B-25). 허용 목록만 서빙하는 대시보드 서버도 원본은 내보내므로 통과했다
# (B-13). 작업 트리마다 처음 쓸 때 무작위 값으로 만든다 - 추적하지 않으므로 체크아웃
# 마다 다르다.
TREE_ID_REL = ".devserver-id"


def tree_id(root=ROOT):
    """이 작업 트리의 확인 값. 파일이 없으면 만든다 (동시에 만들어도 하나만 남는다)."""
    path = os.path.join(root, TREE_ID_REL)
    for _ in range(2):
        try:
            with io.open(path, encoding="ascii") as f:
                value = f.read().strip()
            if value:
                return value
        except OSError:
            pass
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError:
            continue                    # 다른 프로세스가 막 만들었다 - 다시 읽는다
        with os.fdopen(fd, "w", encoding="ascii") as f:
            f.write(uuid.uuid4().hex + "\n")
    with io.open(path, encoding="ascii") as f:
        return f.read().strip()


def serves_this_tree(port, root=ROOT):
    """:port 가 이 작업 트리의 파일을 서빙하는가. 확인 파일의 값을 대조한다."""
    want = tree_id(root)
    url = "http://%s:%d/%s" % (HOST, port, TREE_ID_REL)
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            served = r.read().decode("ascii", "replace").strip()
    except (urllib.error.URLError, OSError):
        return False
    return served == want


def server_cmd(port, root=ROOT):
    """띄우는 명령. 루프백에만 묶는다 (HOST). 테스트와 기준값 캡처도 이것을 쓴다."""
    return [sys.executable, "-m", "http.server", str(port), "--bind", HOST,
            "--directory", root]


def ensure_server(log, port=PORT):
    """Return the Popen we started, or None if the port was already up (then we
    leave it alone at the end too).

    이미 떠 있으면 그것이 **이 작업 트리를** 서빙하는지 먼저 본다 (serves_this_tree).
    다른 폴더를 서빙하는 서버를 모르고 쓰면 검사는 돌긴 하지만 결과가 무엇을 뜻하는지
    알 수 없다. 빌드를 못 열어 전부 fatal 이 나거나, 더 나쁘게 같은 이름의 다른
    문서를 열어 통과한다.
    """
    if listening(port):
        if not serves_this_tree(port):
            raise RuntimeError(
                ":%d 에 이미 서버가 있지만 이 작업 트리(%s)의 파일을 서빙하지 않는다 "
                "(확인 파일 %s 가 없거나 값이 다르다). 다른 worktree · 다른 폴더를 서빙하는 "
                "서버이거나, 허용 목록만 서빙하는 대시보드 서버(시작.bat)일 수 있다. 그 "
                "서버를 끄고 다시 실행하라 (확인: netstat -ano | findstr :%d)."
                % (port, ROOT, TREE_ID_REL, port))
        log("server: :%d already listening (이 작업 트리를 서빙한다), reusing it" % port)
        return None
    tree_id()                           # 서버가 내보낼 확인 파일을 먼저 둔다
    proc = subprocess.Popen(server_cmd(port), stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    for _ in range(50):
        if listening(port):
            log("server: started http.server on %s:%d (pid %d)" % (HOST, port, proc.pid))
            return proc
        time.sleep(0.1)
    proc.kill()
    raise RuntimeError("could not start http.server on :%d" % port)

