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
    # 방문 이름 -> 그 방문이 가리키는 화면 이름. 같은 화면을 두 번 지나는 흐름
    # 에서 둘이 갈라진다 ("review#2" -> "review"). 페이지가 스스로 말하는 이름과
    # 견줄 때는 화면 이름을 써야 한다 - 페이지는 방문 횟수를 모른다.
    screen_of: dict = field(default_factory=dict)
    fatal: list = field(default_factory=list)
    warning: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    skipped: list = field(default_factory=list)
    stopped_at: str = None

    def screen(self, visit):
        """방문 이름이 가리키는 화면 이름. 모르는 이름은 그대로 돌려준다 -
        손으로 만든 스냅샷으로 도는 테스트가 그렇다."""
        return self.screen_of.get(visit, visit)

    def fatal_(self, check, screen, detail, **kw):
        self.fatal.append(dict(check=check, screen=screen, detail=detail, **kw))

    def warn(self, check, screen, detail, **kw):
        self.warning.append(dict(check=check, screen=screen, detail=detail, **kw))
