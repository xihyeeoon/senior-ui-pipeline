r"""저장소 맨 위 README.md - 처음 보는 사람용 (11-8 5).

README 는 코드와 따로 늙는다. 여기서는 코드에서 읽을 수 있는 것만 맞춰 본다 - 링크가
있는 파일을 가리키는가, 검사 A~K 표의 "와이어프레임 단계" 표시가 검사기의 단계 정의와
같은가, 과제 파일의 칸이 모두 표에 있는가, 절이 다 있는가.

  .\.venv\Scripts\python.exe -m pytest tests/test_readme.py
"""
import io
import json
import os
import re

import pytest

import _api

ROOT = _api.ROOT_DIR
TEXT = io.open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()


def section(title):
    m = re.search(r"^## %s\n(.*?)(?=^## |\Z)" % re.escape(title), TEXT, re.S | re.M)
    assert m, title
    return m.group(1)


@pytest.mark.parametrize("title", [
    "무엇에 쓰나", "원칙", "보존 대상", "한 번 실행의 흐름", "검사 A~K",
    "과제 파일의 칸 (`tasks/<과제>.json`)", "설치", "명령", "출력 폴더", "비용 어림",
    "C 후보 고르기", "시험", "한계", "문서"])
def test_the_readme_has_every_section(title):
    assert section(title).strip()


def test_every_relative_link_points_to_a_file():
    links = re.findall(r"\]\(([^)#\s]+)\)", TEXT)
    local = [l for l in links if not re.match(r"[a-z]+://", l)]
    assert local
    missing = [l for l in local if not os.path.exists(os.path.join(ROOT, *l.split("/")))]
    assert missing == []


def test_the_check_table_marks_the_wireframe_stage_as_the_auditor_does():
    rows = re.findall(r"^\| ([A-K]) \| (.*) \| (fatal|warning) \| ?(✓?) ?\|$",
                      section("검사 A~K"), re.M)
    assert [r[0] for r in rows] == list("ABCDEFGHIJK")
    marked = [r[0] for r in rows if r[3]]
    assert marked == _api.STAGES["wireframe"]["checks"]


def test_every_field_of_the_task_file_is_in_the_table():
    table = section("과제 파일의 칸 (`tasks/<과제>.json`)")
    for name in ("transfer", "bill"):
        raw = json.load(io.open(_api.tasks_module.task_path(name), encoding="utf-8"))
        for key in raw:
            assert "`%s`" % key in table, (name, key)


def test_the_selection_rule_version_and_refine_budget_match_the_file():
    rule = json.load(io.open(_api.DEFAULT_SELECTION_RULE, encoding="utf-8"))
    body = section("C 후보 고르기")
    assert "version\n%d" % rule["version"] in body or "version %d" % rule["version"] in body
    assert "다듬기 %d" % rule["gates"]["budget"]["refine"] in body
