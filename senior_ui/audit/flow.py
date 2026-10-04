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

