r"""과제가 쓰는 정답 값과 흐름 파일 읽기.

검사가 "보여 주는 값이 맞는가" 를 판정할 기준이 되는 값들, 흐름 파일의
{ACCOUNT} 같은 자리표시자를 그 값으로 바꾸는 fill(), 그리고 흐름 파일을 읽는
load_flow() 가 여기 있다.

흐름 파일은 화면이 무엇이고 어디를 눌러 거기까지 가는지, 각 화면이 무엇을 보여
주어야 하는지를 적은 JSON 이다. 코드 밖에 두는 것이 재구성된 설계 - 화면도
순서도 다른 것 - 를 검사할 수 있게 하는 유일한 장치다.
"""
import json
import os

from ..config import FLOWS_DIR

# Ground truth for the drive; every displayed value is checked against these.
ACCOUNT = "3333000000000"
AMOUNT = "10000"
AMOUNT_SHOWN = "10,000"
BANK = "카카오뱅크"
NAME = "김시현"

SUBST = {"{ACCOUNT}": ACCOUNT, "{AMOUNT}": AMOUNT, "{AMOUNT_SHOWN}": AMOUNT_SHOWN,
         "{BANK}": BANK, "{NAME}": NAME}


def fill(s):
    for k, v in SUBST.items():
        s = s.replace(k, v)
    return s


def visit_keys(steps):
    """흐름의 걸음마다 그 방문을 가리키는 이름.

    흐름이 같은 화면을 두 번 지날 수 있다 (run4 의 흐름이 `account` 를 두 번
    지난다). 방문을 화면 이름 하나로만 기록하면 두 번째 방문이 첫 번째를
    덮어쓰므로, 첫 방문에 보인 틀린 값은 아무도 보지 못한 일이 된다 - 사용자가
    실제로 그것을 보고 지나갔는데도.

    첫 방문은 화면 이름 그대로이고 그다음부터 `#2`, `#3` 이 붙는다. 첫 방문의
    이름을 바꾸지 않는 이유는 같은 화면을 두 번 지나지 않는 흐름 - 지금의 다섯
    흐름 중 네 개 - 의 출력이 한 글자도 달라지지 않게 하기 위해서다.

    흐름 파일의 `expect` 는 이 방문 이름으로 적는다. 화면 이름만 적으면 첫
    방문에 걸린다 (`account`), 두 번째 방문은 `account#2` 다. 방문마다 보여야
    하는 것이 다를 수 있으므로 모든 방문에 함께 걸지 않는다.
    """
    seen, out = {}, []
    for step in steps:
        name = step["screen"]
        seen[name] = seen.get(name, 0) + 1
        out.append(name if seen[name] == 1 else "%s#%d" % (name, seen[name]))
    return out


def load_flow(path):
    """A flow file describes the screens, how to reach each one, and what each
    must be showing. Keeping it out of the code is what lets a restructured
    design - different screens, different order - be audited at all."""
    if not path:
        # The shipped original flow is the default baseline. There is no in-code
        # fallback: a flow that cannot drive a page is worse than no flow.
        #
        # 라이브러리 함수이므로 SystemExit 를 내지 않는다. 종료 코드를 정하는
        # 것은 CLI 의 일이다 (읽기 실패 = 2).
        path = os.path.join(FLOWS_DIR, "original.json")
        if not os.path.exists(path):
            raise FileNotFoundError("audit: the default flow is missing: %s" % path)
    with open(path, encoding="utf-8") as f:
        flow = json.load(f)
    flow.setdefault("derived_from_original", True)
    flow.setdefault("expect", {})
    flow.setdefault("done_amount", "#dn-amt")
    # 일부러 뺀 선택지의 선언 (checks/i_choices.declared 참고). 없으면 빈
    # 선언이고, 그때 검사 I 는 모든 누락을 fatal 로 센다.
    flow.setdefault("choices_removed", {})
    return flow

