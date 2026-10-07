import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def pytest_addoption(parser):
    import _api
    parser.addoption(
        "--port", type=int, default=_api.config_module.AUTO_PORT,
        help="브라우저 테스트가 쓸 서버 포트. 주지 않으면 빈 포트에 이 테스트 실행만의 서버를 "
             "띄운다 (config.AUTO_PORT) - 같은 포트를 명시하지 않으면 다른 실행과 동시에 "
             "돌려도 된다. 주면 그 포트에 떠 있는 서버를 이 작업 트리를 서빙할 때만 재사용한다")


@pytest.fixture(scope="session")
def server(pytestconfig):
    """브라우저 테스트가 함께 쓰는 서버 하나. 기본은 빈 포트에 새로 띄운다.

    재구성 루프와 같은 판단(devserver.ensure_server)을 쓴다. --port 를 주면 그 포트에
    떠 있는 서버가 **이 작업 트리를** 서빙하는지 확인 파일로 보고 재사용하고, 아니면
    이유와 함께 멈춘다. 끝에서는 내가 띄운 것만 끈다. 테스트가 여는 주소
    (capture_baseline.BASE_URL)는 여기서 실제 포트로 맞춘다.

    전에는 :3003 하나를 썼다 - 다른 테스트 실행 · 재구성 루프와 같이 돌면 먼저 끝난 쪽이
    다른 쪽이 쓰던 서버를 껐다 (11-9). 그 전에는 테스트 파일마다 서버가 따로 있었고
    무엇이 떠 있든 재사용했다 (감사 B-25)."""
    import _api
    import capture_baseline as C
    port = pytestconfig.getoption("--port")
    lines = []
    try:
        proc = _api.ensure_server(lines.append, port=port)
    except RuntimeError as e:
        pytest.fail(str(e))
    C.use_port(getattr(proc, "port", None) or port)
    try:
        yield proc
    finally:
        if proc is not None:
            proc.terminate()
            proc.wait()
