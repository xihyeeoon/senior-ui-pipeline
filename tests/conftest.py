import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


@pytest.fixture(scope="session")
def server():
    """브라우저 테스트가 함께 쓰는 :3003 서버 하나.

    재구성 루프와 같은 판단(devserver.ensure_server)을 쓴다 - 떠 있으면 그것이 **이
    작업 트리를** 서빙하는지 확인 파일로 보고 재사용하고, 아니면 이유와 함께 멈춘다.
    비어 있으면 띄우고 끝에서 끈다 (내가 띄운 것만 끈다).

    전에는 테스트 파일마다 셋이 따로 있었다 - test_drive 는 원본 HTML 을 대조했고,
    test_audit_accuracy 는 무엇이 떠 있든 확인 없이 재사용했다 (감사 B-25). 그래서
    다른 세션 · 다른 worktree 의 서버로 테스트가 돌 수 있었다."""
    import _api
    lines = []
    try:
        proc = _api.ensure_server(lines.append)
    except RuntimeError as e:
        pytest.fail(str(e))
    try:
        yield proc
    finally:
        if proc is not None:
            proc.terminate()
            proc.wait()
