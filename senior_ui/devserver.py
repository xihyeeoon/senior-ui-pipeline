r"""이 작업 트리를 127.0.0.1 에 서빙하는 개발용 서버 - 사람이 띄우면 :3003, 자동 실행은 빈 포트.

검사기는 페이지를 file:// 이 아니라 http:// 로 연다 - 원본 시제품이 fetch 를
쓰지 않더라도, 대시보드도 같은 포트로 서빙하므로 검사도 같은 조건에서 돈다.

루트 전체를 서빙하는 것은 검사기가 어떤 빌드 파일이든 열 수 있어야 해서
그대로 둔다. 대신 루프백에만 띄운다 - 그 루트에는 .envs 와 sessions/ 가 같이
들어 있어서, LAN 에 열면 검사기를 한 번 돌리는 동안 다 나간다.

자동 실행(재구성 루프 · pytest · 기준값 캡처)은 ensure_server(port=0) 으로 빈 포트에
제 서버를 띄우고 끝에서 제 것만 끈다 (config.AUTO_PORT). 그래서 같은 포트를 명시하지
않으면 둘을 동시에 돌려도 된다. 전에는 모두 :3003 하나를 썼다 - 뒤에 시작한 쪽이 앞의
서버를 재사용하고, 앞의 쪽이 끝나며 그 서버를 끄면 뒤의 쪽은 걷다가 끊겼다.

포트를 명시하면 ensure_server() 는 이미 떠 있는 서버를 재사용한다 - 그때는 None 을
돌려주고, 부른 쪽은 끝에서도 그 서버를 건드리지 않는다. 다만 재사용 전에 그것이
**이 작업 트리의 파일을** 서빙하는지 확인한다 (serves_this_tree). 아니면 멈춘다 -
남의 서버로 돌린 검사는 통과하든 떨어지든 뜻을 알 수 없다.

서버를 따로 띄워 두려면 (뷰어로 빌드를 열어 보거나 검사기 CLI 를 여러 번 돌릴 때):

  python -m senior_ui.devserver            (127.0.0.1:3003, Ctrl+C 로 끈다)
  python -m senior_ui.devserver --port 3010

`python -m http.server 3003 --directory .` 로 띄우지 마라 - --bind 가 없으면 0.0.0.0
에 열려 .envs · sessions/ 가 같은 망에 나간다 (감사 B-27).

대시보드 서버(python -m senior_ui.experiment.server · 시작.bat)와는 다르다. 그쪽은
허용 목록만 서빙하므로 .mock-outputs/ · SENIOR_UI_OUTPUTS 의 빌드를 열지 못하고,
ensure_server 도 그것을 재사용하지 않는다.
"""
import argparse
import functools
import io
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from ._cli import setup_stdout
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
    """띄우는 명령. 루프백에만 묶는다 (HOST). 테스트와 기준값 캡처도 이것을 쓴다.
    `-u` 는 빈 포트로 띄웠을 때 잡힌 포트를 알리는 첫 줄을 곧바로 내보내게 한다."""
    return [sys.executable, "-u", "-m", "http.server", str(port), "--bind", HOST,
            "--directory", root]


# http.server 가 띄운 직후 찍는 줄. 빈 포트(0)로 띄우면 여기서 잡힌 포트를 읽는다.
SERVING = re.compile(r"Serving HTTP on \S+ port (\d+)")


def start_on_free_port(log, root=ROOT):
    """빈 포트에 이 작업 트리의 서버를 띄운다. 돌려주는 Popen 의 `port` 가 잡힌 포트다.

    포트를 먼저 골라 두고 띄우면 그 사이에 다른 실행이 같은 포트를 잡을 수 있다.
    http.server 에 0 을 주면 운영체제가 bind 할 때 고르므로 그런 틈이 없다."""
    tree_id(root)                       # 서버가 내보낼 확인 파일을 먼저 둔다
    proc = subprocess.Popen(server_cmd(0, root), stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, encoding="ascii",
                            errors="replace")
    first = []
    reader = threading.Thread(target=lambda: first.append(proc.stdout.readline()),
                              daemon=True)
    reader.start()
    reader.join(10)
    m = SERVING.search(first[0]) if first else None
    if not m:
        proc.kill()
        proc.wait()
        raise RuntimeError("could not start http.server on a free port (첫 줄: %r)"
                           % (first[0] if first else None))
    proc.port = int(m.group(1))
    log("server: started http.server on %s:%d (빈 포트, pid %d)" % (HOST, proc.port, proc.pid))
    return proc


def ensure_server(log, port=PORT, root=ROOT):
    """Return the Popen we started, or None if the port was already up (then we
    leave it alone at the end too). 띄운 Popen 의 `port` 가 그 서버의 포트다.

    port 가 0 이면 빈 포트에 새로 띄운다 (start_on_free_port) - 재사용할 것이 없다.

    이미 떠 있으면 그것이 **이 작업 트리를** 서빙하는지 먼저 본다 (serves_this_tree).
    다른 폴더를 서빙하는 서버를 모르고 쓰면 검사는 돌긴 하지만 결과가 무엇을 뜻하는지
    알 수 없다. 빌드를 못 열어 전부 fatal 이 나거나, 더 나쁘게 같은 이름의 다른
    문서를 열어 통과한다.
    """
    if not port:
        return start_on_free_port(log, root)
    if listening(port):
        if not serves_this_tree(port, root):
            raise RuntimeError(
                ":%d 에 이미 서버가 있지만 이 작업 트리(%s)의 파일을 서빙하지 않는다 "
                "(확인 파일 %s 가 없거나 값이 다르다). 다른 worktree · 다른 폴더를 서빙하는 "
                "서버이거나, 허용 목록만 서빙하는 대시보드 서버(시작.bat)일 수 있다. 그 "
                "서버를 끄고 다시 실행하라 (확인: netstat -ano | findstr :%d)."
                % (port, root, TREE_ID_REL, port))
        log("server: :%d already listening (이 작업 트리를 서빙한다), reusing it" % port)
        return None
    tree_id(root)                       # 서버가 내보낼 확인 파일을 먼저 둔다
    proc = subprocess.Popen(server_cmd(port, root), stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    for _ in range(50):
        if listening(port):
            log("server: started http.server on %s:%d (pid %d)" % (HOST, port, proc.pid))
            proc.port = port
            return proc
        time.sleep(0.1)
    proc.kill()
    raise RuntimeError("could not start http.server on :%d" % port)


def build_parser():
    """사람이 띄우는 서버의 인자. 포트는 :3003 그대로다 (config.PORT) - 뷰어 · 문서의
    주소가 그것을 가정한다. 자동 실행의 빈 포트와는 다르다."""
    ap = argparse.ArgumentParser(prog="python -m senior_ui.devserver")
    ap.add_argument("--port", type=int, default=PORT)
    return ap


def main(argv=None):
    """`python -m senior_ui.devserver` - 이 작업 트리를 루프백에 띄워 두고 기다린다.

    ensure_server 와 같은 판단을 하되, 서버는 이 프로세스 안에서 돈다 (자식 프로세스를
    띄우지 않는다). 그래야 이 창을 닫거나 프로세스를 끝내면 서버도 함께 끝난다 -
    Windows 에서는 부모를 끝내도 자식 http.server 가 포트를 쥔 채 남는다."""
    setup_stdout()
    args = build_parser().parse_args(argv)
    if listening(args.port):
        if not serves_this_tree(args.port):
            print("cannot start: :%d 에 이미 서버가 있지만 이 작업 트리(%s)를 서빙하지 "
                  "않는다. 그 서버를 끄고 다시 실행하라." % (args.port, ROOT), file=sys.stderr)
            return 2
        print("이미 이 작업 트리를 서빙하는 서버가 :%d 에 있다 - 그대로 쓴다." % args.port)
        return 0
    tree_id()
    handler = functools.partial(SimpleHTTPRequestHandler, directory=ROOT)
    srv = ThreadingHTTPServer((HOST, args.port), handler)
    print("http://localhost:%d/ - %s 를 루프백(%s)에만 서빙한다. 끄려면 Ctrl+C."
          % (args.port, ROOT, HOST), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
