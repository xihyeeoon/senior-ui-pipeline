r"""실행마다 달라지는 값 - 비교에서 뺄 것들과, 빼는 방법.

이 목록은 추측이 아니라 측정으로 만들었다. tests/capture_baseline.py 를 두 번
돌려 모든 출력 파일을 키 단위로 비교하고, 실제로 달라진 경로만 적었다. 왜
달라지는지는 tests/README.md 에 있다.

측정 결과 흔들리는 것은 원본 시제품의 비밀번호 숫자판 하나뿐이었다. audit() /
apply_stage() / validate_flow / retry_block / mock 실행 / session_report 의
출력은 두 실행이 바이트까지 같았다. 그래서 REPORT 는 비어 있다 - 리포트는
무시할 키 없이 그대로 비교한다.

경로는 점으로 끊은 키 목록이고 `*` 는 키 하나(또는 리스트 원소 하나)에
대응한다. scrub() 은 대응하는 딕셔너리 키를 지운 사본을 돌려준다.
"""
import copy
import json

# --------------------------------------------------------------------- #
# drive() 스냅샷
# --------------------------------------------------------------------- #
# 원본 시제품의 비밀번호 숫자판은 그릴 때마다 숫자를 섞는다
# (inputs/original_transfer.html: `[0..9].sort(()=>Math.random()-0.5)`).
# 섞인 순서가 그대로 들어가는 세 곳만 뺀다. 같은 구조의 다른 수집 결과
# (pick-bank 선택지 67개, 대비, 겹침, 넘침 등)는 두 실행이 똑같았으므로 그대로
# 비교한다 - 넓게 빼면 검사 I 가 보는 선택지 집합까지 비교에서 사라진다.
SNAPSHOT = [
    "screens.*.choices.pw",        # 숫자판 버튼 값의 DOM 순서
    "screens.password.text",       # 화면 텍스트에 숫자판 순서가 그대로 들어간다
    "screens.password.wrapped",    # 줄바꿈 수집 항목의 text 와 순서
]

# --------------------------------------------------------------------- #
# audit() / apply_stage() 리포트
# --------------------------------------------------------------------- #
# 측정 결과 흔들리는 키가 없다. 나중 단계에서 새로 흔들리는 것이 나오면 그때
# 측정해서 여기에 적는다. 비어 있다는 것 자체가 결론이다.
REPORT = []

IGNORE = SNAPSHOT + REPORT


def _match(path, pattern):
    if len(path) != len(pattern):
        return False
    return all(p == "*" or p == k for k, p in zip(path, pattern))


def scrub(obj, patterns):
    """patterns 에 걸리는 딕셔너리 키를 지운 사본을 돌려준다."""
    pats = [p.split(".") for p in patterns]

    def walk(node, path):
        if isinstance(node, dict):
            out = {}
            for k, v in node.items():
                here = path + [str(k)]
                if any(_match(here, p) for p in pats):
                    continue
                out[k] = walk(v, here)
            return out
        if isinstance(node, list):
            return [walk(v, path + [str(i)]) for i, v in enumerate(node)]
        return node

    return walk(copy.deepcopy(obj), [])


def normalise_snapshot(snapshot):
    """{"orig": ..., "rep": ...} 또는 한쪽 스냅샷 하나를 받는다."""
    if set(snapshot) == {"orig", "rep"}:
        return {k: scrub(v, SNAPSHOT) for k, v in snapshot.items()}
    return scrub(snapshot, SNAPSHOT)


def normalise_report(report):
    return scrub(report, REPORT)


def jround(obj):
    """JSON 으로 한 번 왕복시켜 비교 가능한 표현으로 맞춘다."""
    return json.loads(json.dumps(obj, ensure_ascii=False))
