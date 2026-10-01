r"""검사기. 생성물이 과제를 통과하는지, 원본이 주던 것을 잃지 않았는지 본다.

    flow.py    정답 값 · 흐름 파일 읽기
    drive.py   흐름대로 한 번 걷고 필요한 것을 긁어 온다
    probes.py  페이지 안에서 도는 JavaScript 조각
    core.py    긁어 온 것으로 A~I 를 판정한다
    stage.py   단계(와이어프레임 / 스타일 이식본) 밖의 결과를 걷어낸다
    report.py  리포트 여러 개를 나란히 놓고 표로 만든다
    __main__.py  CLI

네 이름만 밖으로 낸다. 나머지는 모듈 경로로 직접 쓴다.
"""
from .core import audit
from .drive import drive
from .flow import load_flow
from .stage import apply_stage

__all__ = ["audit", "drive", "load_flow", "apply_stage"]
