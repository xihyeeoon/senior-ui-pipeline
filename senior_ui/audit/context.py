r"""검사들이 함께 보는 입력과 함께 쓰는 출력 한 덩어리.

A~I 는 모두 같은 것을 본다 - 두 스냅샷, 두 HTML, 흐름 파일 - 그리고 모두 같은
곳에 적는다 - fatal · warning · metrics. 그 전부를 AuditContext 하나에 담아
각 검사의 run(ctx) 에 넘긴다. 여러 검사가 같이 쓰는 union() 도 여기 있다.
"""
from dataclasses import dataclass, field


def union(snapshot, key):
    out = set()
    for row in snapshot["screens"].values():
        out |= {v for v in row.get(key, []) or [] if v}
    return out


@dataclass
class AuditContext:
    """한 번의 검사가 보는 것과 쌓는 것.

    `derived` · `want` · `shared` 는 core.audit() 이 흐름 파일에서 미리 구해 둔
    것이다. `stopped_at` 은 검사 A 가 채우고 집계가 읽는다.
    """
    orig: dict
    rep: dict
    orig_html: str
    rep_html: str
    flow: dict
    derived: bool
    want: list
    shared: list
    fatal: list = field(default_factory=list)
    warning: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    skipped: list = field(default_factory=list)
    stopped_at: str = None

    def fatal_(self, check, screen, detail, **kw):
        self.fatal.append(dict(check=check, screen=screen, detail=detail, **kw))

    def warn(self, check, screen, detail, **kw):
        self.warning.append(dict(check=check, screen=screen, detail=detail, **kw))
