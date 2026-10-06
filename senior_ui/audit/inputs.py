r"""판정 입력 - 모델이 쓴 흐름 명세를 판정에 쓰는 흐름으로 바꾼다.

재구성 루프에서는 흐름 명세를 모델이 쓴다. 흐름 명세에는 성격이 다른 두 가지
칸이 섞여 있다.

  걷는 법     steps · error_paths 의 걸음 · reveal · required_ids · expect 의
              선택자. 설계마다 다르므로 설계를 만든 모델이 적는다.
  판정 기준   정답(truth) · 빼도 되는 선택지 · 걸어야 할 오류 경로 · 검사 단계 ·
              원본에서 파생됐는가. 과제와 연구자가 정한다.

판정 기준을 모델의 말로 정하면 모델이 자기 빌드의 채점 기준을 고르게 된다
(원칙 P1). 그래서 judged_flow 하나가 모델 흐름의 판정 기준 칸을 버리고 과제의
것으로 채운다. 루프(restructure/audit_call)와 검사기 CLI(__main__)가 둘 다
이것을 부른다. 한쪽에만 있으면 같은 빌드가 두 판정을 받는다 (감사 B-03).

버리는 칸은 읽지도 검증하지도 않는다. 전에는 버려질 truth 를 먼저 검증하다가
모양이 틀리면 ValueError 로 검사가 터졌고, 루프는 그것을 설계 실패로 세어 검사
예산을 썼다 (감사 B-02).

연구자가 쓴 흐름(flows/ 아래 - 과제의 원본 흐름과 옛 Run 흐름)은 여기를 거치지
않는다. 그 흐름의 정답은 연구자의 말이고, 옛 빌드는 옛 정답으로 다시 검사할 수
있어야 한다 (flow.load_flow). 어느 쪽인지는 researcher_flow 가 파일 위치로
가른다 - 모델이 흐름 명세 안에 무엇을 적어도 바뀌지 않는 기준이다.
"""
import copy
import io
import json
import os

from .. import config
from ..config import FLOWS_DIR
from ..tasks import DEFAULT_TASK, load_task
from .flow import done_selector, task_truth, visit_keys
from .stage import STAGES

# 허용하는 제거를 적는 파일. 연구자가 손으로 관리하는 것이고, 이것 말고는
# 어디에서도 읽지 않는다.
#
# 검사 I 는 흐름의 choices_removed 를 읽어 그 값을 누락으로 세지 않는다. 그
# 선언은 "연구자가 안전을 이유로 뺐다" 는 뜻인데, 재구성 루프에서는 흐름 명세를
# **모델이** 쓴다 - 모델이 스스로 그것을 적으면 검사를 끄는 장치가 된다. 그래서
# 선언을 읽는 곳을 모델이 쓸 수 없는 파일 하나로 옮긴다.
#
# 과제별로 적는다. 한 과제에서 안전한 제거가 다른 과제에서도 안전하다는 보장은
# 없다.
ALLOWED_REMOVALS = os.path.join(FLOWS_DIR, "allowed_removals.json")


def load_allowed_removals(task=DEFAULT_TASK, path=ALLOWED_REMOVALS):
    """그 과제에서 빼도 되는 선택지. {action: {"values": [...], "reason": "..."}}.

    파일이 없으면 빈 선언이다 - 그때 검사 I 는 모든 누락을 fatal 로 센다.
    모양이 틀린 파일은 빈 선언으로 넘어가지 않고 멈춘다. 허용 목록을 적어
    두었는데 조용히 무시되면, 연구자는 적었다고 믿고 결과는 다르게 나온다.
    """
    if not os.path.exists(path):
        return {}
    try:
        data = json.load(io.open(path, encoding="utf-8-sig"))
    except ValueError as e:
        raise RuntimeError("%s 를 JSON 으로 읽지 못했다: %s" % (path, e))
    if not isinstance(data, dict):
        raise RuntimeError("%s 의 최상위는 과제 이름을 키로 하는 객체여야 한다" % path)
    allowed = data.get(task, {})
    if not isinstance(allowed, dict):
        raise RuntimeError("%s 의 %r 이 객체가 아니다" % (path, task))
    for action, d in allowed.items():
        if not isinstance(d, dict) or not isinstance(d.get("values"), list):
            raise RuntimeError('%s 의 %r/%r 은 {"values": [...], "reason": "..."} '
                               "여야 한다" % (path, task, action))
    return allowed


def researcher_flow(path):
    """그 흐름 파일이 연구자의 것인가 - flows/ 아래에 있다.

    경로가 없으면 과제의 원본 흐름을 읽는 것이므로 연구자의 것이다. 모델이 쓴
    흐름 명세는 실행 폴더(outputs/ · .mock-outputs/)에 저장된다. 모델 흐름을
    flows/ 로 옮기는 것은 연구자가 그 흐름을 자기 것으로 받아들이는 일이다."""
    if not path:
        return True
    here = os.path.normcase(os.path.abspath(path))
    return here.startswith(os.path.normcase(os.path.abspath(FLOWS_DIR)) + os.sep)


def read_flow(path):
    """흐름 파일을 그대로 읽는다. 아무 칸도 채우거나 검증하지 않는다."""
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


def _done_visit(flow):
    """완료 화면의 방문 이름 - 흐름의 마지막 걸음. 걸음이 없으면 None."""
    steps = flow.get("steps")
    visits = visit_keys(steps) if isinstance(steps, list) else []
    return visits[-1] if visits else None


def _done_expect(pairs, task_pairs):
    """완료 화면에서 확인할 짝들. 과제의 짝(done_expect)은 과제의 값으로 들어간다.

    모델이 과제의 선택자를 적은 자리에 과제의 값을 넣고(두 번 적었으면 한 번만),
    모델이 적지 않은 과제의 짝은 뒤에 더한다. 과제의 선택자가 아닌 짝은 모델이
    더 확인하겠다고 적은 것이므로 그대로 둔다."""
    want = dict((sel, val) for sel, val in task_pairs)
    out, placed = [], set()
    for p in pairs if isinstance(pairs, list) else []:
        sel = p[0] if isinstance(p, list) and p else None
        if sel in want:
            if sel not in placed:
                out.append([sel, want[sel]])
                placed.add(sel)
            continue
        out.append(p)
    out += [[sel, val] for sel, val in task_pairs if sel not in placed]
    return out


def model_claims(flow, task=DEFAULT_TASK):
    """모델이 적었지만 judged_flow 가 버리는 판정 기준 칸의 이름들.

    버린다는 사실을 남기기 위한 것이다 - 남기지 않으면 "모델이 적지 않았다" 와
    "적었는데 버렸다" 를 구분할 수 없고, 모델이 판정 기준을 적으려 했다는 것
    자체가 결과다."""
    if not isinstance(flow, dict):
        return []
    out = []
    if "truth" in flow:
        out.append("truth")
    if flow.get("choices_removed"):
        out.append("choices_removed")
    if "task" in flow and flow["task"] != task:
        out.append("task")
    if "stage" in flow:
        out.append("stage")
    if "error_paths_required" in flow:
        out.append("error_paths_required")
    if flow.get("derived_from_original"):
        out.append("derived_from_original")
    if "done_amount" in flow and flow["done_amount"] != done_selector(task):
        out.append("done_amount")
    last, expect = _done_visit(flow), flow.get("expect")
    if last and isinstance(expect, dict):
        want = dict(load_task(task)["done_expect"])
        mine = [p for p in expect.get(last) or []
                if isinstance(p, list) and p and p[0] in want]
        if any(len(p) != 2 or p[1] != want[p[0]] for p in mine) \
                or len(mine) != len({p[0] for p in mine}):
            out.append("expect.%s" % last)
    return out


def _reveal_of(flow):
    """펼치기 조작(reveal) - 걷는 법이므로 모델의 것을 쓰되, 걷는 쪽
    (drive.walk_reveal)이 읽는 한 가지 모양으로 맞춘다: {action: {"at", "do": [...]}}.

    `do` 의 동작 하나하나는 고치지 않는다. click 하나가 아닌 동작은 걷는 쪽이
    규칙 위반으로 적어야 하므로(루프는 그것을 형식 문제로 센다) 그대로 넘긴다.
    객체가 아닌 항목은 "펼칠 곳이 없는 조작" 으로 남긴다 - 빼 버리면 그 선택지는
    펼쳐 보지도 않은 채 누락으로 세진다."""
    reveal = flow.get("reveal")
    if not isinstance(reveal, dict) or not reveal:
        return None
    out = {}
    for action, spec in reveal.items():
        if not isinstance(spec, dict):
            out[action] = {"at": None, "do": []}
            continue
        do = spec.get("do")
        out[action] = {"at": spec.get("at"),
                       "do": do if isinstance(do, list) else ([do] if do else [])}
    return out


def judged_flow(flow, task=None, stage=None, allowed_removals=None):
    """모델 흐름 + 과제 → 판정에 쓰는 흐름. 받은 흐름은 바꾸지 않는다.

      task                   부르는 쪽이 정한 과제 (모델이 적은 task 는 듣지 않는다)
      truth                  과제의 정답 (과제의 원본 흐름). 모델 것은 검증 없이 버린다
      derived_from_original  늘 false - 모델의 설계는 새 설계다
      choices_removed        연구자 파일(flows/allowed_removals.json)의 그 과제 칸
      error_paths_required   과제 파일의 required_error_paths
      stage                  부르는 쪽이 정한 단계, 없으면 config.DEFAULT_STAGE
      done_amount            과제의 완료 화면 금액 자리 (done_expect 첫 짝)
      expect[완료 화면]      과제의 done_expect 짝은 과제의 값으로 (_done_expect).
                             모델이 비우거나 다른 값을 적어도 과제의 값으로 본다
      reveal                 모델의 펼치기 조작, 한 가지 모양으로 (_reveal_of)
      model_claims_dropped   위 칸 중 모델이 적었다가 버려진 것 (model_claims)

    `allowed_removals` 를 주면 파일 대신 그것을 쓴다 - 루프는 실행을 시작할 때
    한 번 읽어 둔 것을 넘긴다."""
    if not isinstance(flow, dict):
        raise ValueError("흐름 명세가 객체가 아니다 (%s)" % type(flow).__name__)
    task = task or DEFAULT_TASK
    stage = stage or config.DEFAULT_STAGE
    if stage not in STAGES:
        raise ValueError("알 수 없는 단계: %s (가능: %s)"
                         % (stage, ", ".join(sorted(STAGES))))
    spec = load_task(task)
    out = copy.deepcopy(flow)
    out.setdefault("name", "auto")
    out["task"] = task
    out["truth"] = task_truth(task)
    out["derived_from_original"] = False
    out["choices_removed"] = dict(load_allowed_removals(task)
                                  if allowed_removals is None else allowed_removals)
    out["error_paths_required"] = list(spec["required_error_paths"])
    out["stage"] = stage
    out.setdefault("expect", {})
    if not isinstance(out["expect"], dict):
        raise ValueError("expect 가 객체가 아니다 (%s)" % type(out["expect"]).__name__)
    out.setdefault("error_paths", [])
    # 완료 화면의 값은 과제가 정한다 (감사 B-01). 모델이 적은 값으로 보면 빈 값은
    # 무조건 통과이고, 틀린 값을 적으면 틀린 값이 정답이 된다. 금액 자리를 옮기는
    # done_amount 도 같은 구멍이다 - 검사 A 가 그 자리만 본다.
    out["done_amount"] = done_selector(task)
    last = _done_visit(out)
    if last:
        out["expect"][last] = _done_expect(out["expect"].get(last),
                                           spec["done_expect"])
    reveal = _reveal_of(flow)
    if reveal is None:
        out.pop("reveal", None)
    else:
        out["reveal"] = reveal
    out["model_claims_dropped"] = model_claims(flow, task)
    return out
