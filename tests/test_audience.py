r"""모델에게 말하는 대상 문구를 과제 파일 한 칸으로 (11-8 4).

"60대 이상 고령 사용자" 가 과제 파일 description 둘과 다듬기 프롬프트에 따로 박혀 있었다.
과제 파일에 `audience` 칸을 두고(값은 지금 문구 그대로), 프롬프트는 그 자리를 `{{AUDIENCE}}`
로 쓴다. 대상을 바꾼 대조 실행과 모집 기준(65세 이상 여부)에 맞춘 문구 수정을 코드 수정 없이
하려는 것이다 - 값을 바꾸는 것은 연구자 결정이다.

값을 바꾸지 않았으므로 진단 · 계획 · 생성 · 반성 프롬프트는 글자 하나 다르지 않다 (스냅샷
기준값 tests/baseline/prompt · bill/prompt 가 그대로다 - test_baseline 이 본다). 다듬기
프롬프트만 "60대 이상 사용자가" 가 "60대 이상 고령 사용자가" 로 바뀐다 (다듬기는 꺼 두었다).

  .\.venv\Scripts\python.exe -m pytest tests/test_audience.py
"""
import io
import json
import os
import shutil

import pytest

import _api

T = _api.tasks_module
P = _api.prompt_module
ROOT = _api.ROOT_DIR
NOW = "60대 이상 고령 사용자"
TASKS = ("transfer", "bill")


# ===================================================================== #
# 1. 과제 파일의 칸
# ===================================================================== #
@pytest.mark.parametrize("task", TASKS)
def test_the_task_file_has_the_audience_as_it_was(task):
    raw = json.load(io.open(T.task_path(task), encoding="utf-8"))
    assert raw["audience"] == NOW
    # 설명에는 문구가 아니라 자리가 있다 - 문구는 한 칸에만 있다
    desc = "\n".join(raw["description"])
    assert "{{AUDIENCE}}" in desc and NOW not in desc
    # 읽으면 자리가 채워진다 - 설명을 쓰는 다른 곳(화면설계서 머리)도 전과 같은 글이다
    assert NOW + "가" in T.load_task(task)["description"]
    assert "{{AUDIENCE}}" not in T.load_task(task)["description"]


def test_a_task_without_the_audience_stops(tmp_path, monkeypatch):
    raw = json.load(io.open(T.task_path("transfer"), encoding="utf-8"))
    raw.pop("audience")
    (tmp_path / "transfer.json").write_text(json.dumps(raw, ensure_ascii=False),
                                            encoding="utf-8")
    monkeypatch.setattr(T, "TASKS_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="audience"):
        T.load_task("transfer")


def test_the_reason_is_written_next_to_the_field():
    text = io.open(os.path.join(ROOT, "senior_ui", "tasks.py"), encoding="utf-8").read()
    flat = " ".join(text.split())
    assert ("대상을 바꾼 대조 실행과 모집 기준(65세 이상 여부)에 맞춘 문구 수정을 코드 수정 없이 "
            "하려고") in flat.replace(" # ", " ")
    assert "값을 바꾸는 것은 연구자 결정이다" in flat


# ===================================================================== #
# 2. 프롬프트의 자리
# ===================================================================== #
@pytest.mark.parametrize("task", TASKS)
def test_every_prompt_carries_the_value_and_no_slot_is_left(task):
    for t in (P.load_plan_template(task), P.load_template(task),
              P.load_refine_template(task)):
        assert NOW + "가" in t and "{{AUDIENCE}}" not in t


@pytest.mark.parametrize("task", TASKS)
def test_the_refine_prompt_now_says_the_same_words(task):
    """다듬기 프롬프트의 대상 문구만 바뀐다 - "60대 이상 사용자가" 가 audience 값으로."""
    t = P.load_refine_template(task)
    assert NOW + "가 이 화면들을 처음 본다고 하자" in t
    assert "60대 이상 사용자가" not in t


def test_the_slot_is_written_in_the_prompt_file_and_the_task_files_only():
    doc = io.open(P.PROMPT_FILE, encoding="utf-8").read()
    for name in ("PLAN_PROMPT", "PROMPT", "REFINE_PROMPT", "CONTRACT", "REVEAL", "REFLECT"):
        assert NOW not in P.load_block(name, doc), name
        assert "60대" not in P.load_block(name, doc), name
    assert "{{AUDIENCE}}" in P.load_block("REFINE_PROMPT", doc)


# 받침이 있는 값이면 조사가 "이" 다 - 값을 바꿔도 프롬프트의 말이 틀리지 않게.
@pytest.mark.parametrize("value,want", [
    ("60대 이상 고령 사용자", "60대 이상 고령 사용자가"),
    ("65세 이상 고령자", "65세 이상 고령자가"),
    ("65세 이상 성인", "65세 이상 성인이"),
])
def test_the_particle_follows_the_value(value, want):
    assert T.fill_audience("{{AUDIENCE}}가 처음 본다", value) == want + " 처음 본다"
    assert T.fill_audience("{{AUDIENCE}}이 처음 본다", value) == want + " 처음 본다"


def test_a_value_not_ending_in_hangul_keeps_the_written_particle():
    assert T.fill_audience("{{AUDIENCE}}가 본다", "고령 사용자(65+)") == "고령 사용자(65+)가 본다"
    assert T.fill_audience("{{AUDIENCE}}이 본다", "고령 사용자(65+)") == "고령 사용자(65+)이 본다"


def test_a_copula_after_the_slot_is_not_a_particle():
    assert T.fill_audience("대상은 {{AUDIENCE}}이다", "고령자") == "대상은 고령자이다"


# ===================================================================== #
# 3. 값을 바꾼 과제 파일로 한 번 돌린다 - 진단 · 생성 · 다듬기 프롬프트 모두에 새 값
# ===================================================================== #
NEW = "65세 이상 고령자"


@pytest.fixture
def new_audience(tmp_path, monkeypatch):
    """이체 과제 파일을 복사해 audience 값만 바꾼 과제 폴더."""
    for name in TASKS:
        shutil.copy(T.task_path(name), str(tmp_path / ("%s.json" % name)))
    raw = json.load(io.open(str(tmp_path / "transfer.json"), encoding="utf-8"))
    raw["audience"] = NEW
    (tmp_path / "transfer.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2),
                                            encoding="utf-8")
    monkeypatch.setattr(T, "TASKS_DIR", str(tmp_path))
    return tmp_path


def test_a_changed_value_reaches_every_prompt_template(new_audience):
    for t in (P.load_plan_template("transfer"), P.load_template("transfer"),
              P.load_refine_template("transfer")):
        assert NEW + "가" in t
        assert "60대" not in t


from test_restructure_bugs import fake_run_env, make_args, out_root  # noqa: E402,F401
from test_visual_refine import (IMPROVE, audit_by_marker, images, is_refine,  # noqa: E402,F401
                                refine_answers, run_with)

loop = _api.loop_module


def test_a_run_with_a_changed_value_sends_it_everywhere(new_audience, audit_by_marker,
                                                       out_root, tmp_path):
    """진단·계획 · 생성 · 다듬기 프롬프트를 실제 템플릿으로 만든다 (모델 · 검사기만 가짜).
    다듬기를 한 번 켜서 그 프롬프트도 만든다. 기록(summary.json)에 값이 남는다."""
    env = audit_by_marker
    env.setattr(loop, "load_template", P.load_template)
    env.setattr(loop, "load_plan_template",
                lambda task=None: "PLAN_TEMPLATE " + P.load_plan_template(task))
    code, s, sent, d = run_with(env, out_root, refine_answers([IMPROVE]),
                                original_images=images(tmp_path, 1),
                                build_images=images(os.path.join(str(tmp_path), "b"), 1),
                                refine=1)
    assert code == 0 and s["audience"] == NEW
    files = {"plan": "attempt_1.plan_prompt.txt", "generate": "attempt_1.prompt.txt",
             "refine": "attempt_2.refine_prompt.txt"}
    for stage, name in files.items():
        text = io.open(os.path.join(d, name), encoding="utf-8").read()
        assert NEW + "가" in text, stage
        assert "60대" not in text, stage
    md = io.open(os.path.join(d, "designer_brief.md"), encoding="utf-8").read()
    assert NEW + "가 처음 볼 때" in md and "60대" not in md


def test_a_default_run_records_the_audience(fake_run_env, out_root):
    code, s, sent, d = run_with(fake_run_env, out_root,
                                refine_answers([IMPROVE]), refine=0)
    assert s["audience"] == NOW
