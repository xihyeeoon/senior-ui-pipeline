r"""11-5 화면 보여 주기 - 브라우저도 실제 API 도 부르지 않는다.

  그림 요청      그림을 넣은 요청의 모양 (Chat · Responses), 그림 토큰 어림,
                 기록에 남는 프롬프트, 호출마다 그림 수와 40장 경고
  진단           원본 그림이 진단·계획 호출에만 들어간다 · evidence_kind 세기
  보고 다듬기    통과 뒤 다듬기 · 멈춤 · 실패하면 한 번 고치고 그래도 안 되면
                 직전 통과 빌드로 되돌림 · 예산을 따로 셈 · 기록
  펼치기         흐름 명세의 reveal 모양 검사 · 검사 I 가 펼친 값을 센다
  설명서 · 고르기 규칙

  .\.venv\Scripts\python.exe -m pytest tests/test_visual_refine.py
"""
import json
import os
import struct
import zlib

import pytest

import _api
import fake_openai as F

model = _api.model_module
config = _api.config_module


def make_png(path, w=390, h=844):
    """흰 PNG 한 장 (Pillow 없이). 크기만 맞으면 된다."""
    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff))
    raw = b"".join(b"\x00" + b"\xff" * w for _ in range(h))
    body = (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(body)
    return path


def images(tmp_path, n=2, w=390, h=844):
    return [{"label": "화면 s%d" % i,
             "path": make_png(os.path.join(str(tmp_path), "s%d.png" % i), w, h)}
            for i in range(1, n + 1)]


# --------------------------------------------------------------------------- #
# 그림 토큰 어림
# --------------------------------------------------------------------------- #
def test_png_size_is_read_from_the_header(tmp_path):
    p = make_png(os.path.join(str(tmp_path), "a.png"), 390, 1600)
    assert model.png_size(p) == (390, 1600)


def test_a_phone_screen_on_gpt_6_1_sol_is_about_422_tokens():
    """390x844 = 13 x 27 = 351 패치 x 1.2. sol 은 안내에 없지만 2026-10-07 probe 의
    실측(430)이 어림과 2% 안에서 같아 배수는 그대로 두고 추정 표시를 지웠다."""
    tokens, how = model.image_tokens(390, 844, "gpt-6.1-sol")
    assert tokens == 422
    assert "patch" in how and "추정" not in how
    assert "estimated" not in config.IMAGE_TOKENS["gpt-6.1-sol"]


def test_gpt_6_astra_uses_the_documented_patch_rule():
    tokens, how = model.image_tokens(390, 844, "gpt-6-astra")
    assert tokens == 422 and "추정" not in how


def test_gpt_4o_counts_tiles():
    """작은 그림은 키우지 않는다: 1 x 2 타일 → 85 + 2 x 170."""
    assert model.image_tokens(390, 844, "gpt-4o")[0] == 425


def test_a_huge_image_is_shrunk_to_the_patch_budget():
    tokens, _how = model.image_tokens(390, 20112, "gpt-6-astra")
    assert tokens <= int(2500 * 1.2) + 1


def test_an_unknown_model_says_it_used_the_default_rule():
    _t, how = model.image_tokens(390, 844, "gpt-unknown-9")
    assert "기본 규칙" in how


# --------------------------------------------------------------------------- #
# 요청 모양
# --------------------------------------------------------------------------- #
PROMPT = "앞 글\n" + "{mark}" + "\n뒤 글"


def prompt_with_mark():
    return PROMPT.format(mark=model.IMAGE_MARK)


def test_chat_request_puts_each_image_after_its_label(tmp_path):
    imgs = images(tmp_path)
    kw = model.request_kwargs("gpt-6.1-sol", prompt_with_mark(), 100,
                              model.profile_for("gpt-6.1-sol"), images=imgs)
    content = kw["messages"][0]["content"]
    kinds = [p["type"] for p in content]
    assert kinds == ["text", "text", "image_url", "text", "image_url", "text"]
    assert content[0]["text"] == "앞 글\n" and content[-1]["text"] == "\n뒤 글"
    assert content[1]["text"] == "[그림 1/2] 화면 s1"
    url = content[2]["image_url"]
    assert url["url"].startswith("data:image/png;base64,")
    assert url["detail"] == config.IMAGE_DETAIL == "high"


def test_responses_request_uses_input_image(tmp_path):
    imgs = images(tmp_path, 1)
    kw = model.request_kwargs("gpt-6.1-sol", prompt_with_mark(), 100,
                              model.profile_for("gpt-6.1-sol", "responses"), images=imgs)
    content = kw["input"][0]["content"]
    assert [p["type"] for p in content] == ["input_text", "input_text", "input_image",
                                            "input_text"]
    assert content[2]["detail"] == "high"
    assert content[2]["image_url"].startswith("data:image/png;base64,")


def test_without_images_the_request_is_one_string_as_before():
    kw = model.request_kwargs("gpt-4o", prompt_with_mark(), 100,
                              model.profile_for("gpt-4o"))
    assert kw["messages"] == [{"role": "user", "content": "앞 글\n\n뒤 글"}]
    kw = model.request_kwargs("gpt-4o", "그냥 글", 100, model.profile_for("gpt-4o"))
    assert kw["messages"] == [{"role": "user", "content": "그냥 글"}]


def test_the_fake_client_receives_the_images(monkeypatch, tmp_path):
    client = F.install(monkeypatch)
    imgs = images(tmp_path, 3)
    reply = model.call_model("gpt-6.1-sol", prompt_with_mark(), 100, images=imgs,
                             reasoning_effort="medium")
    api, kw = client.sent[-1]
    assert api == "chat"
    assert len(F.images_in(kw)) == 3
    assert reply["images"] == 3


def test_the_record_names_each_image_instead_of_its_bytes(tmp_path):
    imgs = images(tmp_path, 2)
    text = model.prompt_record(prompt_with_mark(), imgs, "gpt-6.1-sol",
                               base=str(tmp_path))
    assert model.IMAGE_MARK not in text
    assert "[그림 1/2] 화면 s1  <그림: s1.png 390x844 · 예상 422토큰>" in text
    assert "base64" not in text


# --------------------------------------------------------------------------- #
# (가) 원본 그림은 진단·계획 호출에만
# --------------------------------------------------------------------------- #
from test_restructure_bugs import (GOOD_DIAGNOSIS, GOOD_PLAN, GOOD_REPLY,  # noqa: E402
                                   fake_run_env, is_plan_prompt, make_args,  # noqa: F401
                                   out_root, run_dirs)

loop = _api.loop_module

SNAPSHOT = {"screens": {}, "reached": [], "dialogs": [], "js_errors": [],
            "js_error_details": [], "missing_ids": [], "state_pairs": [],
            "undefined_classes": [], "notes": [], "load_failed": None}


def plan_reply(diagnosis=None, plan=None):
    return "```json\n%s\n```\n" % json.dumps(
        {"diagnosis": diagnosis or GOOD_DIAGNOSIS, "plan": plan or GOOD_PLAN},
        ensure_ascii=False)


def reply(text, usage=None):
    return {"text": text, "finish_reason": "stop", "seconds": 0.0, "usage": usage}


def recording_model(sent, answers):
    """call_model 의 대역. 부를 때마다 (프롬프트, 그림) 을 sent 에 쌓고, answers
    에서 (조건, 답) 의 첫 맞는 답을 돌려준다. 답이 목록이면 차례로 꺼낸다."""
    def fake(model_, prompt, *a, **k):
        sent.append({"prompt": prompt, "images": list(k.get("images") or [])})
        for test, text in answers:
            if test(prompt):
                if isinstance(text, list):
                    text = text.pop(0) if len(text) > 1 else text[0]
                return reply(text)
        raise AssertionError("답이 정해지지 않은 프롬프트: %s" % prompt[:80])
    return fake


def summary_of(out_root):
    last = run_dirs(out_root)[-1]
    return json.load(open(os.path.join(last, "summary.json"), encoding="utf-8")), last


def run_with(monkeypatch, out_root, answers, original_images=(), build_images=(),
             **kw):
    sent = []
    monkeypatch.setattr(loop, "call_model", recording_model(sent, answers))
    monkeypatch.setattr(loop, "see_images",
                        lambda shots, labels, ids=(): list(
                            original_images if labels is loop.ORIGINAL_LABELS
                            else build_images))
    kw.setdefault("refine", 0)
    code = loop.run(make_args(out_root, **kw))
    summary, last = summary_of(out_root)
    return code, summary, sent, last


PLAN_THEN_GOOD = [(is_plan_prompt, plan_reply()), (lambda p: True, GOOD_REPLY)]


def test_the_plan_call_gets_the_original_screens_and_generation_does_not(
        fake_run_env, out_root, tmp_path):
    imgs = images(tmp_path, 3)
    code, summary, sent, _d = run_with(fake_run_env, out_root, PLAN_THEN_GOOD, imgs)
    assert code == 0
    assert [len(c["images"]) for c in sent] == [3, 0]
    assert summary["see"] == {"on": True, "source": "기본값 (켜짐)", "original_images": 3}
    plan, gen = summary["attempts"][0]["calls"]
    per = model.image_tokens(390, 844, "test-model")[0]
    assert plan["images"] == 3 and plan["estimated_images"] == 3 * per
    assert gen["images"] == 0 and gen["estimated_images"] == 0
    assert summary["tokens"]["by_stage"]["plan"]["images"] == 3


def test_the_saved_plan_prompt_names_the_images(fake_run_env, out_root, tmp_path):
    imgs = images(tmp_path, 2)
    _c, _s, sent, d = run_with(fake_run_env, out_root, PLAN_THEN_GOOD, imgs)
    saved = open(os.path.join(d, "attempt_1.plan_prompt.txt"), encoding="utf-8").read()
    assert model.IMAGE_MARK not in saved
    assert "[그림 1/2] 화면 s1  <그림: " in saved


def test_the_plan_template_has_a_slot_for_the_screens():
    text = _api.load_plan_template()
    assert "{{ORIGINAL_SHOTS}}" in text
    assert "{{ORIGINAL_SHOTS}}" not in _api.load_template()
    shots = _api.prompt_module.shots_section([{"label": "x", "path": "x.png"}])
    assert shots.startswith("## 원본 화면\n\n") and model.IMAGE_MARK in shots
    assert _api.prompt_module.shots_section([]) == ""


def test_see_off_sends_no_images(fake_run_env, out_root):
    seen = []

    async def fake_drive(url, flow, want_shots=None, **kw):
        seen.append(dict(kw, want_shots=want_shots))
        return dict(SNAPSHOT)
    fake_run_env.setattr(loop.A, "drive", fake_drive)
    sent = []
    fake_run_env.setattr(loop, "call_model", recording_model(sent, PLAN_THEN_GOOD))
    loop.run(make_args(out_root, see="off", refine=0))
    assert [len(c["images"]) for c in sent] == [0, 0]
    assert seen[0] == {"errors": False, "see": False, "want_shots": None}
    summary, _d = summary_of(out_root)
    assert summary["see"]["on"] is False and summary["see"]["source"] == "--see"


def test_the_original_walk_takes_screens_and_error_states_when_see_is_on(
        fake_run_env, out_root):
    seen = []

    async def fake_drive(url, flow, want_shots=None, **kw):
        seen.append(dict(kw, want_shots=want_shots))
        return dict(SNAPSHOT)
    fake_run_env.setattr(loop.A, "drive", fake_drive)
    fake_run_env.setattr(loop, "call_model", recording_model([], PLAN_THEN_GOOD))
    loop.run(make_args(out_root, refine=0))
    assert seen[0]["errors"] is True and seen[0]["see"] is True
    assert seen[0]["want_shots"].endswith(os.path.join("shots", "original"))


def test_the_original_error_walk_is_kept_out_of_the_baseline(fake_run_env, out_root):
    """원본의 오류 경로는 그림을 찍으려고 걷는다. 비교 기준(orig_snapshot)에는
    넣지 않는다 - 검사가 보는 원본은 전과 같아야 한다."""
    got = {}

    async def fake_drive(url, flow, want_shots=None, **kw):
        return dict(SNAPSHOT, error_paths={"x": {}})

    def fake_audit(orig, *a, **kw):
        got["orig"] = orig
        return {"passed": True, "fatal": [], "warning": [], "metrics": {}}
    fake_run_env.setattr(loop.A, "drive", fake_drive)
    fake_run_env.setattr(loop, "run_audit", fake_audit)
    fake_run_env.setattr(loop, "call_model", recording_model([], PLAN_THEN_GOOD))
    loop.run(make_args(out_root, refine=0))
    assert "error_paths" not in got["orig"]


def test_more_than_40_images_in_one_call_is_warned(fake_run_env, out_root, tmp_path):
    imgs = images(tmp_path, 1) * 41
    _c, summary, _s, d = run_with(fake_run_env, out_root, PLAN_THEN_GOOD, imgs)
    log = open(os.path.join(d, "run.log"), encoding="utf-8").read()
    assert "경고: plan 호출에 그림이 41장이다 (config.IMAGE_WARN_COUNT 40 초과)" in log
    assert summary["attempts"][0]["calls"][0]["images"] == 41


def test_40_images_is_not_warned(fake_run_env, out_root, tmp_path):
    imgs = images(tmp_path, 1) * 40
    _c, _s, _sent, d = run_with(fake_run_env, out_root, PLAN_THEN_GOOD, imgs)
    assert "IMAGE_WARN_COUNT" not in open(os.path.join(d, "run.log"),
                                          encoding="utf-8").read()


def test_see_images_labels_scroll_parts_and_error_states(tmp_path):
    shots = str(tmp_path)
    for f in ("bank.1.png", "bank.2.png", "home.1.png"):
        make_png(os.path.join(shots, "see", f))
    make_png(os.path.join(shots, "audit_error_wrong-bank.png"))
    index = [{"visit": "home", "file": "home.1.png", "part": 1, "parts": 1,
              "offset": 0, "more_px": 0},
             {"visit": "bank", "file": "bank.1.png", "part": 1, "parts": 2,
              "offset": 0, "more_px": 0},
             {"visit": "bank", "file": "bank.2.png", "part": 2, "parts": 2,
              "offset": 674, "more_px": 120}]
    with open(os.path.join(shots, "see", "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f)
    got = [i["label"] for i in loop.see_images(shots, loop.ORIGINAL_LABELS,
                                               ["wrong-account", "wrong-bank"])]
    assert got == ["원본 화면 home",
                   "원본 화면 bank — 스크롤 1/2 (맨 위)",
                   "원본 화면 bank — 스크롤 2/2 (674px 내린 모습) · 아래로 120px 더 "
                   "있음 (찍지 않음)",
                   "원본 오류 상태 wrong-bank — 잘못된 값을 넣은 직후"]


# --------------------------------------------------------------------------- #
# evidence_kind
# --------------------------------------------------------------------------- #
def test_evidence_kinds_are_counted_and_missing_is_not_a_failure(fake_run_env, out_root):
    diag = [dict(GOOD_DIAGNOSIS[0], id="D1", evidence_kind="screen"),
            dict(GOOD_DIAGNOSIS[0], id="D2", evidence_kind="both"),
            dict(GOOD_DIAGNOSIS[0], id="D3", evidence_kind="code"),
            dict(GOOD_DIAGNOSIS[0], id="D4"),
            dict(GOOD_DIAGNOSIS[0], id="D5", evidence_kind="화면")]
    code, summary, sent, d = run_with(
        fake_run_env, out_root, [(is_plan_prompt, plan_reply(diag)),
                                 (lambda p: True, GOOD_REPLY)])
    assert code == 0 and len(sent) == 2       # 다시 묻지 않았다
    assert summary["plan"]["evidence_kinds"] == {"screen": 1, "code": 1, "both": 1,
                                                 "missing": 2}
    assert "plan: 근거 화면 1 · 코드 1 · 둘 다 1 · 미표시 2" in open(
        os.path.join(d, "run.log"), encoding="utf-8").read()


def test_the_plan_prompt_asks_for_screen_evidence_first():
    text = _api.load_plan_template()
    assert '"evidence_kind": "<screen | code | both>"' in text
    assert "화면에서 보이는 것을 먼저 적는다" in text
    assert "코드는 화면으로 알 수 없는 동작" in text


# --------------------------------------------------------------------------- #
# 3. 프롬프트 정리
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("task", ["transfer", "bill"])
def test_the_task_no_longer_calls_itself_a_prototype(task):
    """예비 실행에서 두 모델 모두 "연습용 본인 확인입니다" · "모의 이체 완료" 를
    화면에 넣었다. 과제 설명이 "시제품이다" 로 시작하고 규칙마다 "시제품이므로"
    가 붙어 있었다."""
    t = _api.tasks_module.load_task(task)
    text = " ".join(t["description"]) + json.dumps(t["prompt"], ensure_ascii=False)
    assert "시제품" not in text


@pytest.mark.parametrize("task", ["transfer", "bill"])
def test_the_contract_says_to_write_like_a_real_app(task):
    text = _api.load_template(task)
    assert "화면의 글은 실제 앱처럼 쓴다" in text
    assert "{{CONTRACT}}" not in text


def test_the_contract_is_one_block_shared_by_generation_and_refinement():
    contract = _api.prompt_module.load_block("CONTRACT")
    assert contract.startswith("- 파일 하나.")
    before, _slot, after = contract.partition("{{TASK_RULES}}")
    text = _api.load_template()
    assert before in text and after.rstrip("\n") in text


def test_the_recover_button_may_appear_only_in_the_error_state():
    text = _api.load_template("transfer")
    assert "되돌아가는 버튼은 오류 상태에서만 보여도 된다" in text


# --------------------------------------------------------------------------- #
# 4. 펼치기 (reveal)
# --------------------------------------------------------------------------- #
from senior_ui.audit.checks import i_choices  # noqa: E402
from senior_ui.audit.context import AuditContext  # noqa: E402

reply_mod = _api.reply_module
REVEAL_HTML = """<html><body>
<section data-screen="start"><button data-action="go" id="phone">시작</button></section>
<section data-screen="bank"><div id="list"></div>
<button data-action="show-all" id="show-all">전체 보기</button></section>
<section data-screen="done"><span id="dn-amt">10,000</span></section>
<script>
const L = ['a','b','c'];
document.getElementById('list').innerHTML =
  L.slice(0,1).map(n => '<button data-action="pick-bank" data-v="'+n+'">'+n+'</button>').join('');
function onClick(el){ const a = el.dataset.action;
  if (a === 'go') {} else if (a === 'show-all') {} else if (a === 'pick-bank') {} }
</script></body></html>"""


def reveal_flow(reveal):
    flow = {"name": "auto", "required_ids": ["phone", "dn-amt"],
            "steps": [{"screen": "start"}, {"screen": "bank", "click": "#phone"},
                      {"screen": "done", "click": "[data-action='pick-bank']"}],
            "expect": {"done": [["#dn-amt", "{AMOUNT_SHOWN}"]]}}
    if reveal is not None:
        flow["reveal"] = reveal
    return flow


GOOD_REVEAL = {"pick-bank": {"at": "bank", "do": [{"click": "#show-all"}]}}


def test_a_good_reveal_has_no_problems():
    assert reply_mod.validate_flow(reveal_flow(GOOD_REVEAL), REVEAL_HTML, [], []) == []


@pytest.mark.parametrize("reveal,needle", [
    ([{"click": "#show-all"}], "reveal 이 객체가 아니다"),
    ({"pick-bank": [{"click": "#show-all"}]}, "reveal.pick-bank 가 객체가 아니다"),
    ({"pick-bank": {"do": [{"click": "#show-all"}]}}, "reveal.pick-bank.at 이 문자열이"),
    ({"pick-bank": {"at": "bank", "do": "click"}}, "reveal.pick-bank.do 가 목록도"),
    ({"pick-bank": {"at": "nowhere", "do": [{"click": "#x"}]}},
     "reveal.pick-bank.at='nowhere' 은 steps 의 화면이 아니다"),
    ({"pick-bank": {"at": "bank", "do": []}}, "reveal.pick-bank.do 가 비어 있다"),
    ({"pick-x": {"at": "bank", "do": [{"click": "#x"}]}}, "'pick-x' 은 HTML 의 data-action"),
])
def test_a_bad_reveal_says_what_is_wrong(reveal, needle):
    flow = reveal_flow(reveal)
    shape = reply_mod.shape_problems(flow)
    problems = shape or reply_mod.validate_flow(flow, REVEAL_HTML, [], [])
    assert any(needle in p for p in problems), problems


def i_ctx(revealed=None):
    orig = {"screens": {"bank": {"choices": {"pick-bank": ["a", "b", "c"]}}}}
    rep = {"screens": {"bank": {"choices": {"pick-bank": ["a"]}}}}
    if revealed is not None:
        rep["revealed"] = revealed
    return AuditContext(orig=orig, rep=rep, orig_html="", rep_html="<html></html>",
                        flow={"choices_removed": {}}, derived=False, want=[], shared=[])


def test_without_reveal_values_drawn_only_after_a_click_are_missing():
    ctx = i_ctx()
    i_choices.run(ctx)
    assert [f["missing"] for f in ctx.fatal] == [["b", "c"]]
    assert "reveal" not in ctx.metrics


def test_check_i_counts_what_the_reveal_walk_collected():
    ctx = i_ctx({"pick-bank": {"at": "bank", "error": None,
                               "choices": {"pick-bank": ["a", "b", "c"]}}})
    i_choices.run(ctx)
    assert ctx.fatal == []
    assert ctx.metrics["choice_values_selectable"] == {"pick-bank": 3}
    assert ctx.metrics["reveal"] == {"pick-bank": {"at": "bank", "values": 3,
                                                   "error": None}}


def test_a_failed_reveal_is_named_in_the_missing_choices_fatal():
    ctx = i_ctx({"pick-bank": {"at": "bank", "choices": {"pick-bank": ["a"]},
                               "error": {"phase": "do", "detail": "no #show-all"}}})
    i_choices.run(ctx)
    assert len(ctx.fatal) == 1
    assert "흐름 명세의 reveal.pick-bank 조작이 실패했다 (do: no #show-all)" \
        in ctx.fatal[0]["detail"]


def test_the_prompts_tell_the_model_about_reveal():
    gen = _api.load_template()
    assert '"do": [{"click": "<선택자>"}]' in gen
    assert "`do` 의 항목은 `{\"click\": 선택자}` 하나뿐이다" in gen
    flat = " ".join(gen.split())
    assert "눌러야 목록이 만들어지는 설계라면 그 조작을 흐름 명세의 `reveal` 에 적는다" in flat


def test_the_reveal_mocks_differ_only_in_the_flow():
    pick = model.mock_reply("reveal")["text"]
    undecl = model.mock_reply("reveal-undeclared")["text"]
    h1, f1, _ = reply_mod.parse_reply(pick)
    h2, f2, _ = reply_mod.parse_reply(undecl)
    assert h1 == h2 and "show-all-banks" in h1
    assert f1["reveal"] == model.MOCK_REVEAL and "reveal" not in f2
    assert reply_mod.validate_flow(f1, h1, _api.flow_module.required_errors("transfer")) == []


# --------------------------------------------------------------------------- #
# (나) 보고 다듬기
# --------------------------------------------------------------------------- #
from test_restructure_bugs import GOOD_FLOW, GOOD_HTML, passing_report, reply_text  # noqa

IMPROVED_HTML = GOOD_HTML.replace("<body>", "<body><style>#phone{font-size:22px}</style>")
BROKEN_HTML = GOOD_HTML.replace("<body>", "<body><!-- BROKEN -->")


def critique_block(c):
    return "```json\n%s\n```\n\n" % json.dumps(c, ensure_ascii=False)


DONE = critique_block(model.MOCK_CRITIQUE_DONE)
IMPROVE = critique_block(model.MOCK_CRITIQUE) + reply_text(IMPROVED_HTML, GOOD_FLOW)
BREAK = critique_block(model.MOCK_CRITIQUE_BREAK) + reply_text(BROKEN_HTML, GOOD_FLOW)
REFLECTION = critique_block({"cause": "다듬다 깨뜨렸다", "plan_changes": [], "keep": []})
FIX_GOOD = REFLECTION + reply_text(IMPROVED_HTML, GOOD_FLOW)
FIX_BROKEN = REFLECTION + reply_text(BROKEN_HTML, GOOD_FLOW)


def is_refine(p):
    return "## 지금 HTML" in p


def is_fix(p):
    return "## 반성 먼저" in p


def refine_answers(refine, fix=(FIX_GOOD,)):
    return [(is_plan_prompt, plan_reply()), (is_refine, list(refine)),
            (is_fix, list(fix)), (lambda p: True, GOOD_REPLY)]


def failing_report():
    return {"passed": False, "warning": [],
            "fatal": [{"check": "A", "screen": "done", "detail": "never reached"}],
            "metrics": {"fatal_total": 1, "fatal_root": 1, "fatal_derived": 0}}


@pytest.fixture
def audit_by_marker(fake_run_env):
    """BROKEN 표시가 있는 빌드는 검사에서 떨어진다."""
    def fake(orig, orig_html, html_path, *a, **kw):
        html = open(html_path, encoding="utf-8").read()
        return failing_report() if "BROKEN" in html else passing_report()
    fake_run_env.setattr(loop, "run_audit", fake)
    return fake_run_env


def run_refine(env, out_root, tmp_path, refine_replies, fix=(FIX_GOOD,), n=2, **kw):
    return run_with(env, out_root, refine_answers(refine_replies, fix),
                    original_images=images(tmp_path, 1),
                    build_images=images(os.path.join(str(tmp_path), "b"), 2),
                    refine=n, **kw)


def read(path):
    return open(path, encoding="utf-8").read()


def test_a_done_critique_stops_refining_and_keeps_the_build(audit_by_marker, out_root,
                                                            tmp_path):
    code, s, sent, d = run_refine(audit_by_marker, out_root, tmp_path, [DONE])
    assert code == 0 and s["passed"]
    rf = s["refine"]
    assert rf["budget"] == 2 and rf["source"] == "--refine"
    assert len(rf["rounds"]) == 1
    r1 = rf["rounds"][0]
    assert r1["stopped"] == "done" and r1["issues"] == 0 and r1["done"] is True
    assert s["final"]["attempt"] == 1
    assert rf["final_from"] == "generate" and rf["final_label"] == "생성"
    assert os.path.exists(os.path.join(d, "attempt_2.critique.json"))
    # 빌드가 없는 회차는 시도 목록에 없다
    assert [a["n"] for a in s["attempts"]] == [1]
    assert s["tokens"]["by_stage"]["refine"]["calls"] == 1


def test_an_improvement_that_passes_becomes_the_final_build(audit_by_marker, out_root,
                                                            tmp_path):
    code, s, sent, d = run_refine(audit_by_marker, out_root, tmp_path, [IMPROVE, DONE])
    rf = s["refine"]
    assert [x["round"] for x in rf["rounds"]] == [1, 2]
    r1, r2 = rf["rounds"]
    assert r1["passed"] and r1["became_final"] and r1["issues"] == 2 and r1["done"] is False
    assert r2["stopped"] == "done" and r2["from_attempt"] == 2
    assert s["final"]["attempt"] == 2
    assert rf["final_from"] == "refine" and rf["final_label"] == "다듬기 1회차"
    assert "#phone{font-size:22px}" in read(s["final"]["html"])
    # 승격된 산출물도 다듬은 빌드다
    assert "#phone{font-size:22px}" in read(os.path.join(out_root, "restructured_auto.html"))
    critique = json.load(open(r1["critique"], encoding="utf-8"))
    assert critique == model.MOCK_CRITIQUE
    # 회차마다 토큰 · 금액 칸이 있다 (mock 이라 금액은 모른다)
    assert r1["tokens"]["calls"] == 1 and "usd" in r1


def test_the_refine_call_sees_the_build_not_the_original(audit_by_marker, out_root,
                                                         tmp_path):
    code, s, sent, d = run_refine(audit_by_marker, out_root, tmp_path, [DONE])
    plan_call, gen_call, refine_call = sent
    assert len(plan_call["images"]) == 1          # 원본
    assert len(gen_call["images"]) == 0
    assert len(refine_call["images"]) == 2        # 빌드
    prompt = refine_call["prompt"]
    assert GOOD_HTML.strip() in prompt
    assert "## 원본\n" not in prompt
    assert '"name": "auto"' in prompt              # 지금 흐름 명세
    assert '"screens"' in prompt                   # 계획
    saved = read(os.path.join(d, "attempt_2.refine_prompt.txt"))
    assert "## 지금 화면" in saved and "[그림 1/2] 화면 s1  <그림: " in saved
    assert s["refine"]["rounds"][0]["images"] == 2


def test_a_broken_refinement_gets_one_ordinary_retry(audit_by_marker, out_root, tmp_path):
    code, s, sent, d = run_refine(audit_by_marker, out_root, tmp_path, [BREAK, DONE],
                                  fix=(FIX_GOOD,))
    r1 = s["refine"]["rounds"][0]
    assert r1["passed"] is False and r1["fix_attempt"] == 3 and r1["fix_passed"] is True
    assert r1["became_final"] and s["final"]["attempt"] == 3
    assert s["refine"]["reverted"] is None
    # 고치기는 보통 재시도 블록이다 - 반성 요청과 실패 목록
    fix_prompt = [c["prompt"] for c in sent if is_fix(c["prompt"])][0]
    assert "## 이전 시도의 실패" in fix_prompt and "never reached" in fix_prompt
    stages = [c["stage"] for a in s["attempts"] for c in a["calls"]]
    assert "refine_fix" in stages
    assert s["refine"]["final_label"] == "다듬기 1회차"


def test_when_the_fix_also_fails_the_last_passing_build_is_kept(audit_by_marker, out_root,
                                                                tmp_path):
    code, s, sent, d = run_refine(audit_by_marker, out_root, tmp_path, [BREAK],
                                  fix=(FIX_BROKEN,))
    assert code == 0 and s["passed"]
    rf = s["refine"]
    assert len(rf["rounds"]) == 1 and rf["rounds"][0]["stopped"] == "reverted"
    assert rf["reverted"]["to_attempt"] == 1 and rf["reverted"]["failed_attempts"] == [2, 3]
    assert s["final"]["attempt"] == 1
    assert rf["final_label"] == "생성 (다듬기 1회차가 실패해 되돌림)"
    assert "BROKEN" not in read(s["final"]["html"])
    assert "BROKEN" not in read(os.path.join(out_root, "restructured_auto.html"))
    log = read(os.path.join(d, "run.log"))
    assert "직전에 통과한 시도 1 를 최종으로 되돌린다" in log


def test_a_revert_after_an_earlier_round_passed_keeps_that_round(audit_by_marker,
                                                                  out_root, tmp_path):
    code, s, sent, d = run_refine(audit_by_marker, out_root, tmp_path, [IMPROVE, BREAK],
                                  fix=(FIX_BROKEN,))
    rf = s["refine"]
    assert s["final"]["attempt"] == 2
    assert rf["final_from"] == "refine"
    assert rf["final_label"] == "다듬기 1회차 (다듬기 2회차가 실패해 되돌림)"


def test_refine_failures_do_not_spend_the_generation_budget(audit_by_marker, out_root,
                                                             tmp_path):
    code, s, sent, d = run_refine(audit_by_marker, out_root, tmp_path, [BREAK],
                                  fix=(FIX_BROKEN,))
    assert s["budget"]["audit_used"] == 0 and s["budget"]["format_used"] == 0


def test_refine_zero_turns_it_off(audit_by_marker, out_root, tmp_path):
    code, s, sent, d = run_refine(audit_by_marker, out_root, tmp_path, [IMPROVE], n=0)
    assert len(sent) == 2
    assert s["refine"]["rounds"] == [] and s["refine"]["final_label"] == "생성"


def test_the_default_refine_count_is_two():
    assert config.DEFAULT_REFINE == 2
    assert loop.refine_choice(make_args("x", refine=None)) == (2, "config.DEFAULT_REFINE")
    assert loop.refine_choice(make_args("x", refine=1)) == (1, "--refine")


def test_a_failed_run_is_not_refined(fake_run_env, out_root, tmp_path):
    fake_run_env.setattr(loop, "run_audit", lambda *a, **kw: failing_report())
    code, s, sent, d = run_with(fake_run_env, out_root, refine_answers([IMPROVE]),
                                refine=2, attempts=1)
    assert not s["passed"]
    assert not any(is_refine(c["prompt"]) for c in sent)


def test_the_refine_prompt_asks_an_open_question_not_a_checklist():
    text = _api.prompt_module.load_refine_template()
    assert "60대 이상 사용자가 이 화면들을 처음 본다고 하자" in text
    assert "어디서 멈추는가. 무엇을 못 읽는가. 무엇을 잘못 누르는가." in text
    assert "코드에서 짐작한 것이 아니라 그림에서 본 것으로 판단하라" in text
    # 비평 칸은 빈칸 틀이다
    assert '"problem": "<고령 사용자가 어디서 왜 막히는가>"' in text
    assert '"seen": "<어느 그림의 어디에서 무엇을 보고>"' in text
    # 체크리스트 말이 없다 (글자 크기 · 터치 크기 같은 규칙) - 기술 계약(3절) 앞까지
    head = text.split("## 3.")[0]
    for word in ("18px", "44px", "글자 크기를", "터치 영역", "대비를"):
        assert word not in head, word
    assert "{{" not in text.replace("{{CURRENT_HTML}}", "").replace(
        "{{CURRENT_FLOW}}", "").replace("{{PLAN}}", "").replace("{{CHOICES}}", "").replace(
        "{{ERRORS}}", "").replace("{{BUILD_SHOTS}}", "")


def test_parse_critique_reads_the_first_json_block():
    c, problems = _api.plan_module.parse_critique(IMPROVE)
    assert c == model.MOCK_CRITIQUE and problems == []
    c, problems = _api.plan_module.parse_critique(GOOD_REPLY)
    assert c is None
    c, problems = _api.plan_module.parse_critique(
        critique_block({"issues": [{"screen": "x"}], "done": "yes"}))
    assert any("issues[0] 에 problem, seen, fix 가 없다" in p for p in problems)
    assert any("done 이 true/false 가 아니다" in p for p in problems)


@pytest.mark.parametrize("rmode,round_no,blocks", [
    ("done", 1, 1), ("improve", 1, 3), ("improve", 2, 1), ("break", 1, 3)])
def test_the_mock_critiques_have_the_answer_shape(rmode, round_no, blocks):
    text = model.mock_refine_reply(rmode, "pass", round_no)["text"]
    assert text.count("```") == blocks * 2
    c, problems = _api.plan_module.parse_critique(text)
    assert problems == [] and isinstance(c["done"], bool)


# --------------------------------------------------------------------------- #
# 5. 설명서
# --------------------------------------------------------------------------- #
brief = _api.brief_module


@pytest.mark.parametrize("refine,attempt,want", [
    ({"final_label": "다듬기 1회차"}, 3, "최종: 다듬기 1회차 (시도 3)"),
    ({"final_label": "생성 (다듬기 2회차가 실패해 되돌림)"}, 1,
     "최종: 생성 (다듬기 2회차가 실패해 되돌림) · 시도 1"),
    ({"final_label": "생성"}, 2, "최종: 생성 (시도 2)"),
    (None, 2, "최종: 생성 (시도 2)"),
])
def test_the_brief_starts_with_where_the_final_build_came_from(refine, attempt, want):
    assert brief.final_line(refine, attempt) == want


def test_a_refined_run_writes_its_final_line_and_refine_section(audit_by_marker, out_root,
                                                                tmp_path):
    code, s, sent, d = run_refine(audit_by_marker, out_root, tmp_path, [IMPROVE, DONE])
    md = read(os.path.join(d, "designer_brief.md"))
    assert md.splitlines()[2] == "최종: 다듬기 1회차 (시도 2)"
    assert "## 보고 다듬기" in md
    assert "### 1회차 — 시도 1 의 빌드를 다듬음 (시도 2)" in md
    assert "결과: 통과 — 새 최종 (시도 2). 비평 2건 · keep 1건 · done=false" in md
    assert "### 2회차 — 시도 2 의 빌드를 다듬음 (시도 3)" in md
    assert "고칠 것이 없다고 답했다" in md
    assert model.MOCK_CRITIQUE["issues"][0]["seen"].split(" ")[0] in md
    # 승격된 사본도 같은 첫 줄
    promoted = read(os.path.join(out_root, "restructured_auto.designer_brief.md"))
    assert "최종: 다듬기 1회차 (시도 2)" in promoted


def test_a_reverted_run_says_so_at_the_top(audit_by_marker, out_root, tmp_path):
    code, s, sent, d = run_refine(audit_by_marker, out_root, tmp_path, [BREAK],
                                  fix=(FIX_BROKEN,))
    md = read(os.path.join(d, "designer_brief.md"))
    assert "최종: 생성 (다듬기 1회차가 실패해 되돌림) · 시도 1" in md
    assert "**되돌림**: 다듬기 1회차의 빌드(시도 2)와 고친 빌드(시도 3)가 모두" in md


def test_the_diagnosis_list_shows_the_evidence_kind(tmp_path):
    diag = [{"id": "D1", "screen": "home", "element": "e", "problem": "p",
             "evidence": "ev", "evidence_kind": "screen"},
            {"id": "D2", "screen": "home", "element": "e", "problem": "p",
             "evidence": "ev", "evidence_kind": "both"},
            {"id": "D3", "screen": "home", "element": "e", "problem": "p",
             "evidence": "ev"}]
    plan = {"screens": [{"name": "start", "purpose": "시작", "from": ["home"]}],
            "changes": []}
    md = brief.render_brief("r", 1, plan, diag, {}, ["home"], str(tmp_path),
                            str(tmp_path))
    assert "(근거[화면]: ev)" in md and "(근거[화면+코드]: ev)" in md
    assert "(근거[미표시]: ev)" in md


def test_the_refine_section_links_before_and_after_and_marks_changes(tmp_path):
    def shots(name, files):
        folder = os.path.join(str(tmp_path), name, "see")
        index = []
        for visit, size in files:
            make_png(os.path.join(folder, "%s.1.png" % visit), 390, size)
            index.append({"visit": visit, "file": "%s.1.png" % visit, "part": 1,
                          "parts": 1, "offset": 0, "more_px": 0})
        with open(os.path.join(folder, "index.json"), "w", encoding="utf-8") as f:
            json.dump(index, f)
        return folder
    before = shots("a1", [("home", 844), ("bank", 844)])
    after = shots("a2", [("home", 844), ("bank", 800)])
    crit = os.path.join(str(tmp_path), "c.json")
    with open(crit, "w", encoding="utf-8") as f:
        json.dump(model.MOCK_CRITIQUE, f, ensure_ascii=False)
    refine = {"rounds": [{"round": 1, "attempt": 2, "from_attempt": 1, "images": 2,
                          "before_shots": before, "after_shots": after,
                          "critique": crit, "issues": 2, "keep": 1, "done": False,
                          "passed": True, "became_final": True, "stopped": None}]}
    md = "\n".join(brief.refine_section(refine, str(tmp_path)))
    assert "| `home` | [전](a1/see/home.1.png) | [후](a2/see/home.1.png) | 그대로 |" in md
    assert "| `bank` | [전](a1/see/bank.1.png) | [후](a2/see/bank.1.png) | 바뀜 |" in md
    assert "| 화면 | 어디서 왜 막히나 | 그림에서 본 것 | 고친 것 |" in md
    assert "그대로 둔 것:" in md


# --------------------------------------------------------------------------- #
# 6. 고르기 규칙 - 검사 J 의 알림 글 경고
# --------------------------------------------------------------------------- #
import test_select as TS  # noqa: E402


def add_j_warning(run_dir, n=1, error_path="wrong-bank"):
    path = os.path.join(run_dir, "attempt_%d.audit.json" % n)
    report = json.load(open(path, encoding="utf-8"))
    report["warning"].append({"check": "J", "screen": "accno", "error_path": error_path,
                              "detail": "오류 경로 %s: 새로 나타난 글에 은행 중 어느 단어도 "
                                        "없다" % error_path})
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False)


def test_the_default_rule_drops_runs_with_a_j_notice_warning(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    TS.make_run(str(runs), "20261007-100000-ok")
    bad = TS.make_run(str(runs), "20261007-100001-astra-like")
    add_j_warning(bad)
    assert TS.DEFAULT_RULE["gates"]["no_warning_checks"] == ["J"]
    code, result, _md = TS.select(tmp_path)
    assert code == 0 and TS.order(result) == ["20261007-100000-ok"]
    assert TS.reasons(result) == {
        "20261007-100001-astra-like": ["검사 J 경고 1건 (오류 경로 wrong-bank: 새로 나타난 "
                                       "글에 은행 중 어느 단어도 없다)"]}


def test_the_j_gate_can_be_turned_off(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    add_j_warning(TS.make_run(str(runs), "20261007-100001-astra-like"))
    rule = TS.write_rule(tmp_path, gates=dict(TS.DEFAULT_RULE["gates"],
                                              no_warning_checks=[]))
    code, result, _md = TS.select(tmp_path, "--rule", rule)
    assert TS.order(result) == ["20261007-100001-astra-like"]


def test_other_warnings_do_not_trip_the_j_gate(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    TS.make_run(str(runs), "20261007-100000-ok", warning=3)
    code, result, _md = TS.select(tmp_path)
    assert TS.order(result) == ["20261007-100000-ok"]


def test_refine_attempts_are_not_counted_as_design_attempts(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    d = TS.make_run(str(runs), "20261007-100000-ok", attempts=1)
    path = os.path.join(d, "summary.json")
    s = json.load(open(path, encoding="utf-8"))
    s["attempts"].append({"n": 2, "stage": "audit", "phase": "refine", "passed": True})
    s["refine"] = {"final_label": "다듬기 1회차"}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False)
    row = _api.select_collect(d)
    assert row["attempts"] == 1 and row["final_from"] == "다듬기 1회차"


# --------------------------------------------------------------------------- #
# --probe <모델> --image
# --------------------------------------------------------------------------- #
from test_model_upgrade import probe_env, probe_log, run_cli  # noqa: E402,F401


def test_probe_image_measures_one_image(probe_env, out_root, capsys):
    """글만 보낸 요청과 그림 한 장을 더한 요청의 입력 차이가 그림 한 장이다.
    가짜 답: 100 → 522 (= 351 패치 x 1.2 ≈ 422)."""
    client = F.install(probe_env, [F.Reply(prompt=100), F.Reply(prompt=522)])
    assert run_cli(probe_env, "--probe", "gpt-6.1-sol", "--image") == 0
    out = capsys.readouterr().out
    assert len(client.sent) == 2
    assert F.images_in(client.sent[0][1]) == []
    imgs = F.images_in(client.sent[1][1])
    assert len(imgs) == 1 and imgs[0]["image_url"]["detail"] == "high"
    assert "그림 한 장의 실측: 입력 522 − 글만 보낸 입력 100 = 422 토큰 (390x844, 패치 351개)" \
        in out
    assert "배수 = 422 / 351 = 1.202" in out
    assert '"gpt-6.1-sol": {"method": "patch", "multiplier": 1.2, "budget": 2500},' in out
    assert "estimated 표시만 지우면 된다" in out
    assert "그림 한 장의 실측" in probe_log(out_root)


def test_probe_image_suggests_a_new_multiplier_when_the_estimate_is_off(
        probe_env, out_root, capsys):
    F.install(probe_env, [F.Reply(prompt=100), F.Reply(prompt=100 + 702)])
    assert run_cli(probe_env, "--probe", "gpt-6.1-sol", "--image") == 0
    out = capsys.readouterr().out
    assert "배수 = 702 / 351 = 2.000" in out
    assert '"multiplier": 2.0' in out
    assert "estimated 표시만" not in out


def test_probe_image_on_a_model_without_images_exits_2(probe_env, out_root, capsys):
    F.install(probe_env, ["ok", F.no_images()])
    assert run_cli(probe_env, "--probe", "gpt-4o", "--image") == 2
    out = capsys.readouterr().out
    assert "그림을 넣은 요청이 실패했다" in out and "--see off" in out


def test_probe_without_image_sends_one_request(probe_env, out_root, capsys):
    client = F.install(probe_env, ["ok"])
    assert run_cli(probe_env, "--probe", "gpt-6.1-sol") == 0
    assert len(client.sent) == 1


# --------------------------------------------------------------------------- #
# 감사 1. 원본의 주석은 모델 입력에서 뺀다
# --------------------------------------------------------------------------- #
strip = _api.prompt_module.model_input_html


def test_markup_comments_are_removed_with_their_lines():
    html = ("<body>\n  <!-- 탭 기록 장치 -->\n<p>남는다</p><!-- 줄 끝 주석 -->\n"
            "<!-- 여러\n줄 -->\n<p>둘</p>\n</body>")
    assert strip(html) == "<body>\n<p>남는다</p>\n<p>둘</p>\n</body>"


def test_block_comments_are_removed_only_inside_style_and_script():
    html = ("<style>\n  /* 제목 */\n  a{color:#000;} /* 끝 */\n</style>\n"
            "<p>/* 화면의 글 */</p>\n"
            "<script>\n/* ==== 상태 ==== */\nconst x = 1; /* 메모 */\n</script>")
    assert strip(html) == ("<style>\n  a{color:#000;}\n</style>\n"
                           "<p>/* 화면의 글 */</p>\n"
                           "<script>\nconst x = 1;\n</script>")


def test_one_comment_never_swallows_the_code_up_to_the_next():
    html = "<!-- a --> <p>x</p> <!-- b -->\n<script>/* a */ go(); /* b */</script>"
    assert strip(html) == " <p>x</p> \n<script> go();</script>"


ORIGINALS = ["inputs/original_transfer.html", "inputs/original_bill.html"]

# 화면으로 알 수 없는 실험 장치 코드 (11-7b, 연구자 결정 11번 (나)). 탭 기록 장치 ·
# 쓰지 않는 .tempnote CSS · 기록 배열과 그것을 내보내는 훅. 검사기가 쓰는 것은
# window.__screen() 과 그것이 읽는 window.__task 뿐이다.
EXPERIMENT_CODE = ["log('tap'", ".tempnote", "__log", "__dump", "__startTask",
                   "const LOG", "function log(", "log('"]


@pytest.mark.parametrize("path", ORIGINALS)
def test_the_originals_lose_their_comments_and_experiment_code(path):
    html = open(os.path.join(config.ROOT, path), encoding="utf-8").read()
    out = strip(html)
    assert "<!--" not in out and "/*" not in out
    assert _api.plan_module.screens_in(out) == _api.plan_module.screens_in(html)
    assert "기록 장치" in html and "기록 장치" not in out
    assert [c for c in EXPERIMENT_CODE if c in out] == []
    # 검사기가 쓰는 훅은 남는다
    assert "window.__screen = " in out and "window.__task" in out


@pytest.mark.parametrize("path", ORIGINALS)
def test_the_original_file_keeps_its_experiment_code(path):
    """원본 파일과 검사기가 보는 원본은 바꾸지 않는다 - 모델 입력에서만 뺀다."""
    html = open(os.path.join(config.ROOT, path), encoding="utf-8").read()
    assert "log('tap'" in html and "window.__dump" in html and "window.__startTask" in html


def test_the_contract_no_longer_asks_for_the_log_hooks():
    contract = _api.prompt_module.load_block("CONTRACT")
    assert "__screen()" in contract
    assert [h for h in ("__log", "__dump", "__startTask", "screen_enter")
            if h in contract] == []


def test_the_unreachable_screen_message_names_only_the_hook_the_auditor_reads():
    src = open(os.path.join(config.ROOT, "senior_ui", "audit", "checks", "a_completion.py"),
               encoding="utf-8").read()
    assert "__startTask" not in src and "__dump" not in src


@pytest.mark.browser
@pytest.mark.parametrize("task", ["transfer", "bill"])
def test_the_model_input_still_walks_the_task(server, task):
    """모델에게 보내는 원본(주석 · 실험 장치 코드를 뺀 것)도 그대로 과제가 끝까지 걸린다 -
    지운 코드가 화면 동작에 닿지 않았다는 확인."""
    import asyncio
    import io
    t = _api.tasks_module.load_task(task)
    html = io.open(_api.tasks_module.abs_path(t["original"]), encoding="utf-8").read()
    rel = ".pytest-outputs/model_input_%s.html" % task
    os.makedirs(os.path.join(config.ROOT, ".pytest-outputs"), exist_ok=True)
    io.open(os.path.join(config.ROOT, rel), "w", encoding="utf-8").write(strip(html))
    try:
        f = _api.load_flow(None, task=task)
        import capture_baseline as C
        base = C.BASE_URL                    # server fixture 가 띄운 포트
        orig = asyncio.run(_api.drive("%s/%s" % (base, t["original"]), f))
        rep = asyncio.run(_api.drive("%s/%s" % (base, rel), f))
        report = _api.audit(orig, rep, html, strip(html), f)
    finally:
        os.remove(os.path.join(config.ROOT, rel))
    assert rep["js_errors"] == [] and rep["reached"] == orig["reached"]
    assert report["fatal"] == [], report["fatal"]


def test_the_prompts_carry_the_stripped_original_and_the_audit_the_full_one(
        fake_run_env, out_root):
    got = {}

    def fake_audit(orig, orig_html, *a, **kw):
        got["orig_html"] = orig_html
        return passing_report()
    fake_run_env.setattr(loop, "run_audit", fake_audit)
    _c, _s, sent, d = run_with(fake_run_env, out_root, PLAN_THEN_GOOD)
    for c in sent:
        assert "<!--" not in c["prompt"] and "기록 장치" not in c["prompt"]
    for name in ("attempt_1.plan_prompt.txt", "attempt_1.prompt.txt"):
        assert "<!--" not in read(os.path.join(d, name))
    assert "<!--" in got["orig_html"]


# --------------------------------------------------------------------------- #
# 감사 2. 그림을 넣은 요청이 거절되면 멈춘다 - 그림을 빼고 다시 보내지 않는다
# --------------------------------------------------------------------------- #
def run_with_fake_client(env, out_root, outcomes, original_images=(), build_images=(),
                         **kw):
    """call_model 은 그대로 두고 openai.OpenAI 만 대역으로 바꾼다."""
    client = F.install(env, outcomes)
    env.setattr(loop, "see_images",
                lambda shots, labels, ids=(): list(
                    original_images if labels is loop.ORIGINAL_LABELS else build_images))
    kw.setdefault("refine", 0)
    code = loop.run(make_args(out_root, model="gpt-6.1-sol", **kw))
    summary, last = summary_of(out_root)
    return code, summary, client, last


def test_a_rejected_image_request_stops_and_is_not_resent_without_images(
        fake_run_env, out_root, tmp_path):
    code, s, client, d = run_with_fake_client(
        fake_run_env, out_root, [F.no_images()], original_images=images(tmp_path, 3))
    assert code == 2 and s["stopped_reason"] == "api_rejected"
    assert len(client.sent) == 1                       # 다시 보내지 않았다
    assert len(F.images_in(client.sent[0][1])) == 3
    log = read(os.path.join(d, "run.log"))
    assert "중단: 그림 3장을 넣은 plan 요청이었다 — 그림을 빼고 다시 보내지 않는다" in log
    assert s["attempts"][-1]["stage"] == "api_rejected"
    assert s["attempts"][-1]["calls"][0]["images"] == 3


def test_a_rejected_refine_request_keeps_the_passed_build(audit_by_marker, out_root,
                                                          tmp_path):
    ok = F.Reply(text=plan_reply())
    gen = F.Reply(text=GOOD_REPLY)
    code, s, client, d = run_with_fake_client(
        audit_by_marker, out_root, [ok, gen, F.no_images()], refine=2,
        build_images=images(tmp_path, 2))
    assert code == 0 and s["passed"] and s["final"]["attempt"] == 1
    assert len(client.sent) == 3
    r1 = s["refine"]["rounds"][0]
    assert r1["stopped"] == "call_failed" and len(s["refine"]["rounds"]) == 1
    assert "중단: 그림 2장을 넣은 refine 요청이었다" in read(os.path.join(d, "run.log"))


# --------------------------------------------------------------------------- #
# 감사 3. reveal 의 do 는 click 만 · 보이는 data-action · 같은 화면
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("act", [
    {"type": "신한", "key": "#search"}, {"wait": 1}, {"repeat": 2, "click": "#x"},
    {"click": "#x", "wait": 0.5}, "click"])
def test_reveal_allows_only_plain_clicks(act):
    flow = reveal_flow({"pick-bank": {"at": "bank", "do": [{"click": "#show-all"}, act]}})
    problems = reply_mod.validate_flow(flow, REVEAL_HTML, [], [])
    assert any("reveal.pick-bank.do[1] 는 click 만 쓸 수 있다" in p for p in problems), \
        problems


def test_a_reveal_violation_is_a_check_i_fatal():
    ctx = i_ctx({"pick-bank": {"at": "bank", "error": None, "choices": {},
                               "violations": ["do[0] #go: 누른 뒤 화면이 바뀌었다 "
                                              "(bank → done)"]}})
    i_choices.run(ctx)
    v = [f for f in ctx.fatal if f.get("reveal_violation")]
    assert len(v) == 1
    assert "reveal.pick-bank 가 펼치기 규칙을 어겼다: do[0] #go: 누른 뒤 화면이 바뀌었다" \
        in v[0]["detail"]


def test_the_loop_counts_a_reveal_violation_as_a_format_failure(fake_run_env, out_root):
    violated = {"passed": False, "warning": [], "metrics": {},
                "fatal": [{"check": "I", "screen": None, "reveal_violation": True,
                           "detail": "흐름 명세의 reveal.pick-bank 가 펼치기 규칙을 "
                                     "어겼다: do[0] #x: 화면에 보이지 않는다"},
                          {"check": "I", "screen": None, "detail": "선택지 없음"}]}
    fake_run_env.setattr(loop, "run_audit", lambda *a, **kw: violated)
    code, s, sent, d = run_with(fake_run_env, out_root, PLAN_THEN_GOOD, attempts=1)
    a = s["attempts"][0]
    assert a["stage"] == "flow" and a["fatal"] == 1
    assert s["budget"]["format_used"] == 1 and s["budget"]["audit_used"] == 0
    report = json.load(open(os.path.join(d, "attempt_1.audit.json"), encoding="utf-8"))
    assert [f["check"] for f in report["fatal"]] == ["FLOW"]
    assert "화면에 보이지 않는다" in report["fatal"][0]["detail"]


# --------------------------------------------------------------------------- #
# 감사 4. 되돌린 뒤 final.attempt · 다듬기 실패는 따로 센다
# --------------------------------------------------------------------------- #
def test_after_a_revert_select_reads_the_real_final_build(audit_by_marker, out_root,
                                                           tmp_path):
    code, s, sent, d = run_refine(audit_by_marker, out_root, tmp_path, [BREAK],
                                  fix=(FIX_BROKEN,))
    assert s["final"]["attempt"] == 1
    row = _api.select_collect(d)
    assert row["final_attempt"] == 1
    assert row["passed"] and row["fatal"] == 0          # 시도 1 의 기록이다
    assert row["truncated"] is False
    # 생성 단계는 실패가 없고, 다듬기의 검사 실패 둘(다듬은 빌드 · 고친 빌드)은 따로
    assert (row["format_failures"], row["audit_failures"]) == (0, 0)
    assert (row["refine_format_failures"], row["refine_audit_failures"]) == (0, 2)
    assert row["attempts"] == 1
    assert s["refine"]["audit_failures"] == 2
    assert s["refine"]["rounds"][0]["audit_failures"] == 2


def test_a_truncated_refine_answer_is_not_the_final_truncation(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    d = TS.make_run(str(runs), "20261007-100000-ok", attempts=1)
    path = os.path.join(d, "summary.json")
    s = json.load(open(path, encoding="utf-8"))
    s["attempts"].append({"n": 2, "phase": "refine", "stage": "truncated",
                          "truncated": True, "passed": False})
    s["refine"] = {"final_label": "생성 (다듬기 1회차가 실패해 되돌림)",
                   "format_failures": 1, "audit_failures": 0}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False)
    row = _api.select_collect(d)
    assert row["truncated"] is False and row["truncated_middle"] == 0
    assert row["refine_format_failures"] == 1 and row["format_failures"] == 0


def test_a_run_from_before_refine_has_no_refine_counts(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    row = _api.select_collect(TS.make_run(str(runs), "20261007-100000-old",
                                          refine_budget=None))
    assert row["refine_format_failures"] is None and row["refine_audit_failures"] is None


# --------------------------------------------------------------------------- #
# 감사 6. 다듬기의 고치기는 계획을 바꾸지 않는다
# --------------------------------------------------------------------------- #
PLAN_CHANGE_FIX = critique_block(
    {"cause": "다듬다 깨뜨렸다", "keep": [],
     "plan_changes": [{"op": "add", "target": "screen", "after": "start",
                       "new": {"name": "extra", "purpose": "더", "from": []},
                       "why": "화면을 하나 더"}]}) + reply_text(IMPROVED_HTML, GOOD_FLOW)


def test_the_refine_fix_does_not_apply_plan_changes(audit_by_marker, out_root, tmp_path):
    code, s, sent, d = run_refine(audit_by_marker, out_root, tmp_path, [BREAK, DONE],
                                  fix=(PLAN_CHANGE_FIX,))
    fix = [a for a in s["attempts"] if a.get("phase") == "refine_fix"][0]
    assert fix["plan_changes"] == 0 and fix["plan_changes_ignored"] == 1
    assert fix["passed"] and s["final"]["attempt"] == 3
    plan = json.load(open(os.path.join(d, "attempt_3.plan.json"), encoding="utf-8"))
    assert [sc["name"] for sc in plan["screens"]] == ["start", "done"]
    assert s["plan"]["screens"] == ["start", "done"]
    assert "계획 변경 1건을 적용하지 않았다 (화면 구성 고정)" in read(
        os.path.join(d, "run.log"))


def test_the_refine_fix_prompt_says_the_screens_stay(audit_by_marker, out_root, tmp_path):
    code, s, sent, d = run_refine(audit_by_marker, out_root, tmp_path, [BREAK, DONE])
    fix_prompt = [c["prompt"] for c in sent if is_fix(c["prompt"])][0]
    assert _api.prompt_module.REFINE_FIX_NOTE in fix_prompt
    # 생성 루프의 재시도에는 붙지 않는다
    normal = [c["prompt"] for c in sent if not is_fix(c["prompt"])]
    assert not any(_api.prompt_module.REFINE_FIX_NOTE in p for p in normal)


def test_the_refine_answer_has_no_plan_changes_slot():
    text = _api.prompt_module.load_refine_template()
    assert "plan_changes" not in text



def test_no_warning_checks_is_a_general_rule(tmp_path):
    """검사 이름 목록이다 - J 말고 다른 검사의 경고로도 뺄 수 있다."""
    runs = tmp_path / "runs"
    runs.mkdir()
    TS.make_run(str(runs), "20261007-100000-d-warn", warning=2)      # 검사 D 경고 둘
    add_j_warning(TS.make_run(str(runs), "20261007-100001-j-warn"))
    rule = TS.write_rule(tmp_path, gates=dict(TS.DEFAULT_RULE["gates"],
                                              no_warning_checks=["D"]))
    code, result, _md = TS.select(tmp_path, "--rule", rule)
    assert TS.order(result) == ["20261007-100001-j-warn"]
    assert TS.reasons(result) == {"20261007-100000-d-warn": ["검사 D 경고 2건 (w)"]}
    rows = {r["name"]: r for r in result["ranking"]}
    assert rows["20261007-100001-j-warn"]["warning_by_check"]["J"]["count"] == 1


@pytest.mark.parametrize("bad", [True, "J", [1], [""]])
def test_no_warning_checks_must_be_a_list_of_names(tmp_path, bad):
    rule = dict(TS.DEFAULT_RULE, gates=dict(TS.DEFAULT_RULE["gates"],
                                            no_warning_checks=bad))
    with pytest.raises(_api.select_rule_module.RuleError):
        _api.select_rule_module.validate(rule)
