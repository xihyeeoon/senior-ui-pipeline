r"""과제가 쓰는 정답 값과 흐름 파일 읽기.

검사가 "보여 주는 값이 맞는가" 를 판정할 기준이 되는 값들(흐름 파일의 truth
블록), 흐름 파일의 {ACCOUNT} 같은 자리표시자를 그 값으로 바꾸는 fill(), 그리고
흐름 파일을 읽는 load_flow() 가 여기 있다.

흐름 파일은 화면이 무엇이고 어디를 눌러 거기까지 가는지, 각 화면이 무엇을 보여
주어야 하는지를 적은 JSON 이다. 코드 밖에 두는 것이 재구성된 설계 - 화면도
순서도 다른 것 - 를 검사할 수 있게 하는 유일한 장치다.
"""
import json
import os

from ..config import FLOWS_DIR

# 과제의 정답 값은 흐름 파일의 "truth" 블록에 있다. 원본이 바뀌면 정답도 바뀌고,
# 옛 원본으로 만든 옛 빌드는 옛 정답으로 다시 검사할 수 있어야 하기 때문이다 -
# 값을 코드에 두면 한 번에 하나의 원본만 검사할 수 있다.
#
#   "truth": {"BANK": "신한", "ACCOUNT": "110234567890",
#             "AMOUNT": "32000", "NAME": "김철수"}
#
# AMOUNT_SHOWN (화면에 보이는 금액, 32,000) 은 AMOUNT 에서 만든다. 블록이 없는
# 흐름 - 재구성 루프에서 모델이 쓴 흐름 명세, 테스트가 손으로 만든 흐름 - 은
# 원본 흐름(flows/original.json)의 정답을 쓴다. 과제는 원본의 과제다.
TRUTH_KEYS = ("ACCOUNT", "AMOUNT", "BANK", "NAME")

_original_truth = None
_original_errors = None


def make_truth(block, where="truth"):
    """흐름 파일의 truth 블록을 자리표시자 값으로. 빠진 키가 있으면 멈춘다 -
    조용히 넘어가면 `{BANK}` 같은 글자가 그대로 눌려 엉뚱한 곳에서 멈춘다."""
    if not isinstance(block, dict):
        raise ValueError("%s 는 객체여야 한다" % where)
    missing = [k for k in TRUTH_KEYS if not str(block.get(k) or "")]
    if missing:
        raise ValueError("%s 에 %s 가 없다" % (where, ", ".join(missing)))
    amount = str(block["AMOUNT"])
    if not amount.isdigit():
        raise ValueError("%s.AMOUNT 는 쉼표 없는 숫자여야 한다: %r" % (where, amount))
    truth = {k: str(block[k]) for k in TRUTH_KEYS}
    truth["AMOUNT_SHOWN"] = "{:,}".format(int(amount))
    # 필수 키 밖의 값도 자리표시자로 남긴다 - 오류 경로가 눌러 넣는 틀린 값
    # ({ACCOUNT_WRONG} 등) 이 여기 있다. 이름은 과제가 정하므로 코드가 고르지
    # 않는다.
    for k, v in block.items():
        if k not in truth and isinstance(v, (str, int)) and str(v):
            truth[k] = str(v)
    return truth


def original_truth():
    """원본 흐름(flows/original.json)의 정답. 한 번 읽고 들고 있는다."""
    global _original_truth
    if _original_truth is None:
        path = os.path.join(FLOWS_DIR, "original.json")
        with open(path, encoding="utf-8") as f:
            _original_truth = make_truth(json.load(f).get("truth"),
                                         "flows/original.json 의 truth")
    return _original_truth


def original_error_paths():
    """원본 흐름이 정한 오류 경로들. 한 번 읽고 들고 있는다.

    무엇이 오류인지(about · condition · 쓰는 틀린 값 `uses` · 알림 글로 인정할
    단어 `notice_any`)는 과제가 정한다. 재구성 루프에서는 흐름 명세를 모델이
    쓰므로, 판정에 쓰는 이 칸들은 모델의 흐름이 아니라 여기서 읽는다 - 정답
    값을 truth 에서만 읽는 것과 같은 이유다."""
    global _original_errors
    if _original_errors is None:
        path = os.path.join(FLOWS_DIR, "original.json")
        with open(path, encoding="utf-8") as f:
            _original_errors = list(json.load(f).get("error_paths") or [])
    return _original_errors


def error_defs(flow=None):
    """오류 경로 id -> 과제가 정한 정의. 원본 흐름의 것이 기준이다.

    흐름 자신이 원본에서 파생된 것(원본 대 원본)이면 그 흐름의 정의를 쓴다 -
    옛 원본으로 만든 흐름은 옛 정의로 검사할 수 있어야 한다."""
    own = (flow or {}).get("error_paths") or []
    if (flow or {}).get("derived_from_original") and             any("notice_any" in e or "uses" in e for e in own if isinstance(e, dict)):
        return {e["id"]: e for e in own if isinstance(e, dict) and "id" in e}
    return {e["id"]: e for e in original_error_paths() if "id" in e}


def truth_of(flow):
    """그 흐름이 쓰는 정답. 블록이 없으면 원본 흐름의 것.

    load_flow 를 거치지 않고 손으로 만든 흐름(테스트)도 같은 모양의 블록을 쓸 수
    있게, 여기서도 make_truth 로 한 번 더 맞춘다.
    """
    block = (flow or {}).get("truth")
    return make_truth(block) if block else original_truth()


def fill(s, truth):
    for k, v in truth.items():
        s = s.replace("{%s}" % k, v)
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
    if "truth" in flow:
        flow["truth"] = make_truth(flow["truth"], "%s 의 truth" % os.path.basename(path))
    else:
        flow["truth"] = original_truth()
    flow.setdefault("derived_from_original", True)
    flow.setdefault("expect", {})
    flow.setdefault("done_amount", "#dn-amt")
    # 일부러 뺀 선택지의 선언 (checks/i_choices.declared 참고). 없으면 빈
    # 선언이고, 그때 검사 I 는 모든 누락을 fatal 로 센다.
    flow.setdefault("choices_removed", {})
    # 잘못된 입력에서 오류를 보이고 되돌아가는 경로 (checks/j_errors.py).
    # 없으면 정답 경로만 걷고, 검사 J 는 물러난다 - 옛 흐름이 그렇다.
    flow.setdefault("error_paths", [])
    return flow

