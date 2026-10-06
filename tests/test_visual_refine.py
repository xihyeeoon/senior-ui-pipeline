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
    """390x844 = 13 x 27 = 351 패치 x 1.2. sol 은 안내에 없어 같은 계열 값 - 추정."""
    tokens, how = model.image_tokens(390, 844, "gpt-6.1-sol")
    assert tokens == 422
    assert "patch" in how and "추정" in how


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
