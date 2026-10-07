r"""다듬기의 reveal 형식 (11-9).

예비 실행 두 번(outputs/restructure_auto/20261006-215902 · 20261007-102041)에서 다듬기
답이 모두 흐름 명세에 `"reveal": []` 을 적어 형식 검사에서 떨어졌다 ("reveal 이 객체가
아니다 (지금은 배열)"). 그 회차는 고치기 호출을 한 번 더 썼다. 다듬기 프롬프트의 흐름
명세 설명은 "형식은 같다 (`steps` · `expect` · `error_paths` · `reveal`)" 뿐이었고, 생성
프롬프트에 있는 reveal 의 모양({"at", "do"} 객체)이 없었다.

  프롬프트    reveal 모양을 한 블록(<!-- REVEAL -->)에 두고 생성 · 다듬기가 함께 쓴다
  형식 검사   배열로 온 reveal 은 원소마다 action 이 있으면 {action: {at, do}} 로 한 번
              바꿔 받고, 바꾼 사실을 남긴다 (summary 의 시도 기록 · run.log)

모델도 브라우저도 부르지 않는다. 두 다듬기 답은 tests/fixtures/real_runs/refine_* 에 그대로
복사해 두었다.
"""
import io
import json
import os

import pytest

import _api
from test_restructure_bugs import GOOD_FLOW, GOOD_HTML, reply_text
from test_visual_refine import (DONE, audit_by_marker, critique_block,  # noqa: F401
                                fake_run_env, model, out_root, run_refine)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL = os.path.join(ROOT, "tests", "fixtures", "real_runs")
reply = _api.reply_module
prompt = _api.prompt_module

SHAPE = ('"reveal": {"<선택지의 data-action>": {"at": "<steps 의 화면 이름>", '
         '"do": [{"click": "<선택자>"}]}}')


# --------------------------------------------------------------------- #
# 1. 프롬프트 - 같은 모양을 한 블록에서
# --------------------------------------------------------------------- #
@pytest.mark.parametrize("task", ["transfer", "bill"])
def test_the_refine_prompt_shows_the_same_reveal_shape(task):
    """고치기 전: 다듬기 프롬프트에는 reveal 의 모양이 없었다."""
    block = prompt.load_block("REVEAL").rstrip("\n")
    assert SHAPE in block
    assert block in _api.load_template(task)
    assert block in prompt.load_refine_template(task)


# --------------------------------------------------------------------- #
# 2. 형식 검사 - 배열을 한 번 객체로 바꿔 받는다
# --------------------------------------------------------------------- #
def parsed(reveal):
    flow = dict(GOOD_FLOW, reveal=reveal)
    accepted = {}
    _html, out, _text = reply.parse_reply(reply_text(GOOD_HTML, flow), accepted)
    return out, accepted


def test_a_list_with_actions_becomes_the_object():
    out, accepted = parsed([{"action": "pick-bank", "at": "start",
                             "do": [{"click": "#all"}]}])
    assert out["reveal"] == {"pick-bank": {"at": "start", "do": [{"click": "#all"}]}}
    assert accepted == {"reveal_from_list": ["pick-bank"]}


def test_an_empty_list_becomes_an_empty_object():
    """두 예비 실행의 다듬기 답이 이 모양이었다."""
    out, accepted = parsed([])
    assert out["reveal"] == {}
    assert accepted == {"reveal_from_list": []}


def test_an_object_is_taken_as_it_is():
    out, accepted = parsed({"pick-bank": {"at": "start", "do": [{"click": "#all"}]}})
    assert accepted == {}
    assert out["reveal"] == {"pick-bank": {"at": "start", "do": [{"click": "#all"}]}}


@pytest.mark.parametrize("bad", [
    [{"at": "start", "do": [{"click": "#all"}]}],                       # action 없음
    [{"action": "pick-bank", "at": "start", "do": []}, "pick-sec"],     # 객체가 아님
    [{"action": "pick-bank", "at": "a", "do": []},
     {"action": "pick-bank", "at": "b", "do": []}],                     # 같은 이름 둘
    [{"action": ["pick-bank"], "at": "start", "do": []}],               # 이름이 글이 아님
])
def test_a_list_that_cannot_be_read_as_the_object_is_still_a_problem(bad):
    with pytest.raises(reply.FlowShape) as e:
        parsed(bad)
    assert "reveal 이 객체가 아니다 (지금은 배열)" in str(e.value)


def test_parse_reply_without_the_record_still_converts():
    """기록을 받지 않는 부르는 쪽(테스트 · 기준값)도 같은 흐름을 받는다."""
    _html, out, _text = reply.parse_reply(reply_text(GOOD_HTML, dict(GOOD_FLOW, reveal=[])))
    assert out["reveal"] == {}


# --------------------------------------------------------------------- #
# 3. 예비 실행 두 번의 다듬기 답 - 저장된 응답으로
# --------------------------------------------------------------------- #
@pytest.mark.parametrize("run", ["refine_215902", "refine_102041"])
def test_the_saved_refine_replies_now_pass_the_format_check(run):
    """루프의 check_reply 와 같은 순서 - 답 가르기 → 완료 칸 별칭 → 흐름 명세 →
    계획과 화면 → 선택지 데이터 참조. 고치기 전: 첫 단계에서 FlowShape."""
    d = os.path.join(REAL, run)
    text = io.open(os.path.join(d, "refine.response.txt"), encoding="utf-8").read()
    accepted = {}
    html, flow, _ = reply.parse_reply(text, accepted)
    assert accepted == {"reveal_from_list": []}
    flow.setdefault("name", "auto")
    reply.accept_done_alias(flow)
    task = _api.load_task("transfer")
    plan = json.load(io.open(os.path.join(d, "plan.json"), encoding="utf-8"))
    data = json.load(io.open(os.path.join(d, "preserved.json"), encoding="utf-8"))
    problems = (reply.validate_flow(flow, html, _api.flow_module.required_errors("transfer"),
                                    task["done_expect"])
                + _api.plan_module.match_problems(plan, html)
                + reply.preserved_problems(html, data))
    assert problems == []


# --------------------------------------------------------------------- #
# 4. 루프 - 바꾼 사실이 남는다
# --------------------------------------------------------------------- #
def test_the_loop_records_the_conversion(audit_by_marker, out_root, tmp_path):
    """고치기 전: 다듬은 빌드가 형식에서 떨어져 고치기 호출을 한 번 더 썼다."""
    improved = GOOD_HTML.replace("<body>", "<body><style>#phone{font-size:22px}</style>")
    refine = (critique_block(model.MOCK_CRITIQUE)
              + reply_text(improved, dict(GOOD_FLOW, reveal=[])))
    code, s, _sent, d = run_refine(audit_by_marker, out_root, tmp_path, [refine, DONE])
    r1 = s["refine"]["rounds"][0]
    assert r1["passed"] is True and r1["fix_attempt"] is None
    entry = [a for a in s["attempts"] if a["n"] == 2][0]
    assert entry["reveal_from_list"] == []
    log = io.open(os.path.join(d, "run.log"), encoding="utf-8").read()
    assert "flow: reveal 이 배열로 왔다 - 원소의 action 을 키로 한 객체로 받았다 (빈 배열 → 빈 객체)" \
        in log
    assert code == 0
