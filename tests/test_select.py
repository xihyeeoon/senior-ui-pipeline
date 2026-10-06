r"""C 후보 고르기 (python -m senior_ui.select) - 가짜 실행 폴더로 본다.

가짜 실행 다섯 (통과 셋 · 실패 하나 · 도구가 고친 것 하나) 의 summary ·
audit · plan 을 루프가 쓰는 모양 그대로 만들어 두고, 순위와 제외 이유를 본다.
모델도 브라우저도 부르지 않는다 - 고르기 도구는 저장된 결과만 읽는다.

통과 셋의 값과 기본 규칙으로 기대하는 순서:

            warning  화면  data-action  변경  시도
    pass-a     2      9       30         7     1     대표성 0
    pass-b     2      8       25         5     2     대표성 1/4 + 5/15 + 2/5
    pass-c     1     12       40        10     3     대표성 3/4 + 10/15 + 3/5

    대표성 (후보 셋의 중앙값 9 · 30 · 7 에 가까운 순) 이 먼저다 -> pass-a,
    pass-b, pass-c. pass-c 는 warning 이 하나 적지만 가장 튀는 시안이다 - 이
    규칙은 여러 실행 중 전형적인 시안을 고르는 것이므로 warning 은 그다음이다.
"""
import io
import json
import os

import pytest

import _api

DEFAULT_RULE = json.load(io.open(_api.DEFAULT_SELECTION_RULE, encoding="utf-8"))

# 실행 당시의 절대 경로를 흉내 낸다. 이 자리에는 아무것도 없다 - 고르기 도구는
# 실행 폴더 안의 같은 이름을 찾아야 한다 (폴더를 옮겨도 읽히도록).
ELSEWHERE = "C:\\gone\\outputs\\restructure_auto\\%s\\%s"


def make_run(root, name, passed=True, warning=0, fatal=0, screens=9, actions=30,
             changes=7, attempts=1, redeclared=(), dirty=False, truncated=False,
             mock=None, model="gpt-6.1-sol", task="transfer", unaddressed_changes=0,
             effort="medium", brief=True):
    d = os.path.join(root, name)
    os.makedirs(d)
    n = attempts

    def p(fname):
        return ELSEWHERE % (name, fname)

    report = {"passed": passed,
              "fatal": [{"check": "A", "detail": "x"}] * fatal,
              "warning": [{"check": "D", "detail": "w"}] * warning,
              "metrics": {"data-screen_repaired": screens, "screens_reached": screens,
                          "data-action_repaired": actions,
                          "choice_groups_original": {"pick-bank": 67, "num": 11},
                          "choice_values_kept": {"pick-bank": 67, "num": 11},
                          "choice_values_selectable": {"pick-bank": 67, "num": 11},
                          "error_paths": {
                              "wrong-account": {"appeared": True, "recovered": True},
                              "wrong-bank": {"appeared": True, "recovered": passed}}}}
    plan = {"screens": [{"name": "s%d" % i} for i in range(screens)],
            "changes": [{"id": "C%d" % (i + 1),
                         "addresses": [] if i < unaddressed_changes else ["D1"]}
                        for i in range(changes)]}
    entries = []
    for i in range(1, n + 1):
        last = i == n
        e = {"n": i, "stage": "audit", "passed": passed and last,
             "fatal": fatal if last else 3, "warning": warning if last else 0,
             "finish_reason": "stop"}
        # truncated: "middle" = 첫 시도가 잘리고 마지막은 검사까지 갔다,
        #            "final"  = 마지막 시도가 잘렸다 (통과할 수 없다)
        if (truncated == "middle" and i == 1 and n > 1) or (truncated == "final" and last):
            e.update(stage="truncated", truncated=True, passed=False)
            e.pop("warning")
        entries.append(e)
    final = {"attempt": n, "html": p("attempt_%d.html" % n),
             "audit": p("attempt_%d.audit.json" % n), "plan": p("attempt_%d.plan.json" % n),
             "preserved": {"injected": {"BANKS": 38}, "redeclared": list(redeclared),
                           "read": ["BANKS"]}}
    if brief:
        final["brief"] = p("designer_brief.md")
    summary = {
        "run_dir": ELSEWHERE % (name, ""), "model": model, "mock": mock, "task": task,
        "model_call": {"reasoning_effort": effort},
        "passed": passed,
        "plan": {"diagnosis_count": 6, "changes": changes, "unaddressed": []},
        "attempts": entries, "final": final,
        "budget": {"format_used": 1 if truncated else 0,
                   "audit_used": n - (1 if passed else 0) - (1 if truncated else 0)},
        "stopped_reason": None if passed else "budget_exhausted",
        "git": {"commit": "abcdef1234567890", "branch": "main", "dirty": dirty,
                "dirty_files": ["x.py"] if dirty else []},
        "tokens": {"total": {"prompt": 30000 * n, "completion": 20000 * n,
                             "reasoning": 15000 * n}},
        "cost": {"total_usd": round(0.1 * n, 4)},
    }
    dump = lambda obj, f: json.dump(obj, io.open(os.path.join(d, f), "w", encoding="utf-8"))
    dump(summary, "summary.json")
    dump(report, "attempt_%d.audit.json" % n)
    dump(plan, "attempt_%d.plan.json" % n)
    io.open(os.path.join(d, "attempt_%d.html" % n), "w").write("<html></html>")
    if brief:
        io.open(os.path.join(d, "designer_brief.md"), "w", encoding="utf-8").write("# brief\n")
    return d


FIVE = [
    ("20261007-100000-pass-a", dict(warning=2, screens=9, actions=30, changes=7, attempts=1)),
    ("20261007-110000-pass-b", dict(warning=2, screens=8, actions=25, changes=5, attempts=2)),
    ("20261007-120000-pass-c", dict(warning=1, screens=12, actions=40, changes=10, attempts=3)),
    ("20261007-130000-fail", dict(passed=False, fatal=2, warning=0, screens=20, actions=90,
                                  changes=30, attempts=3)),
    ("20261007-140000-redeclared", dict(warning=0, redeclared=["BANKS"])),
]


@pytest.fixture
def five(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    for name, kw in FIVE:
        make_run(str(runs), name, **kw)
    return tmp_path


def select(tmp_path, *extra, runs=None):
    """명령을 돌리고 (종료 코드, 결과 JSON, md 글)."""
    out = str(tmp_path / "sel")
    argv = ["--task", "transfer", "--out", out]
    argv += ["--runs", runs or str(tmp_path / "runs" / "*")]
    before = set(os.listdir(out)) if os.path.isdir(out) else set()
    code = _api.select_main(argv + list(extra))
    # 같은 초에 두 번 돌면 이름 뒤에 -2 가 붙는다 - 이번에 생긴 것을 집는다
    js = [f for f in set(os.listdir(out)) - before if f.endswith(".json")][0]
    result = json.load(io.open(os.path.join(out, js), encoding="utf-8"))
    md = io.open(os.path.join(out, js[:-5] + ".md"), encoding="utf-8").read()
    return code, result, md


def order(result):
    return [r["name"] for r in result["ranking"] if r["rank"]]


def reasons(result):
    return {r["name"]: r["excluded_because"] for r in result["ranking"] if not r["rank"]}


def write_rule(tmp_path, **change):
    rule = json.loads(json.dumps(DEFAULT_RULE))
    for k, v in change.items():
        rule[k] = v
    path = tmp_path / "rule.json"
    path.write_text(json.dumps(rule, ensure_ascii=False), encoding="utf-8")
    return str(path)


# ===================================================================== #
# 1. 가짜 다섯 - 순위와 제외 이유
# ===================================================================== #
def test_five_runs_rank_and_exclusion_reasons(five):
    code, result, _md = select(five)
    assert code == 0
    assert order(result) == ["20261007-100000-pass-a", "20261007-110000-pass-b",
                             "20261007-120000-pass-c"]
    assert result["rank1"] == "20261007-100000-pass-a"
    why = reasons(result)
    assert why == {"20261007-130000-fail": ["통과하지 못함 (budget_exhausted)"],
                   "20261007-140000-redeclared": ["도구가 고침: redeclared BANKS"]}
    assert result["counts"] == {"runs": 5, "candidates": 3, "excluded": 2}


def test_representativeness_is_measured_among_candidates_only(five):
    """떨어진 실행(화면 20 · data-action 90 · 변경 30)이 중앙값을 끌면 안 된다."""
    _code, result, _md = select(five)
    stats = result["representative"]["stats"]
    assert stats["screens"] == {"median": 9, "min": 8, "max": 12}
    assert stats["data_actions"] == {"median": 30, "min": 25, "max": 40}
    assert stats["changes"] == {"median": 7, "min": 5, "max": 10}
    rows = {r["name"]: r for r in result["ranking"]}
    assert rows["20261007-100000-pass-a"]["representative"]["distance"] == 0
    assert rows["20261007-110000-pass-b"]["representative"]["distance"] == \
        pytest.approx(1 / 4 + 5 / 15 + 2 / 5)
    assert "representative" not in rows["20261007-130000-fail"]


def test_values_collected_from_summary_audit_and_plan(five):
    _code, result, _md = select(five)
    b = {r["name"]: r for r in result["ranking"]}["20261007-110000-pass-b"]
    assert (b["passed"], b["attempts"], b["format_failures"], b["audit_failures"]) == \
        (True, 2, 0, 1)
    assert (b["fatal"], b["warning"]) == (0, 2)
    assert (b["redeclared"], b["truncated"], b["truncated_middle"], b["dirty"]) ==         ([], False, 0, False)
    assert (b["model"], b["reasoning_effort"], b["commit"]) == \
        ("gpt-6.1-sol", "medium", "abcdef1234567890")
    assert (b["screens"], b["data_actions"]) == (8, 25)
    assert b["choice_groups"]["pick-bank"] == {"original": 67, "kept": 67, "selectable": 67}
    assert b["error_paths"]["wrong-bank"]["ok"] is True
    assert (b["input_tokens"], b["output_tokens"], b["reasoning_tokens"], b["cost_usd"]) == \
        (60000, 40000, 30000, 0.2)
    assert (b["diagnoses"], b["changes"], b["unmatched_changes"]) == (6, 5, 0)
    # summary 의 경로는 옛 자리(C:\gone\...)다 - 실행 폴더 안의 같은 이름을 찾는다
    assert b["brief"].endswith("designer_brief.md") and b["audit"] is not None


def test_changes_without_a_diagnosis_are_counted(tmp_path):
    make_run(str(tmp_path), "20261007-100000", changes=4, unaddressed_changes=3)
    row = _api.select_collect(str(tmp_path / "20261007-100000"))
    assert row["unmatched_changes"] == 3 and row["unmatched_change_ids"] == ["C1", "C2", "C3"]


# ===================================================================== #
# 2. 문지기 - 잘림 · dirty · mock · 모델
# ===================================================================== #
def test_every_gate_names_its_reason(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    make_run(str(runs), "20261007-100000-ok")
    make_run(str(runs), "20261007-100001-dirty", dirty=True)
    make_run(str(runs), "20261007-100003-mock-pass", mock="pass")
    make_run(str(runs), "20261007-100004-4o", model="gpt-4o")
    rule = write_rule(tmp_path, gates=dict(DEFAULT_RULE["gates"], model="gpt-6.1-sol"))
    code, result, _md = select(tmp_path, "--rule", rule)
    assert code == 0 and order(result) == ["20261007-100000-ok"]
    assert reasons(result) == {
        "20261007-100001-dirty": ["작업 트리가 깨끗하지 않음"],
        "20261007-100003-mock-pass": ["mock 실행 (pass)"],
        "20261007-100004-4o": ["모델이 gpt-6.1-sol 아님 (gpt-4o)"]}


def test_only_the_final_attempts_truncation_excludes(tmp_path):
    """중간 시도의 잘림은 최종 시안과 상관없다 - 열로만 보인다. 마지막 시도가
    잘렸을 때만 문지기가 뺀다."""
    runs = tmp_path / "runs"
    runs.mkdir()
    make_run(str(runs), "20261007-100000-middle", truncated="middle", attempts=2)
    make_run(str(runs), "20261007-100001-final", truncated="final", attempts=2,
             passed=False)
    rule = write_rule(tmp_path, gates=dict(DEFAULT_RULE["gates"], passed=False))
    code, result, md = select(tmp_path, "--rule", rule)
    assert code == 0 and order(result) == ["20261007-100000-middle"]
    assert reasons(result) == {
        "20261007-100001-final": ["마지막 시도의 답이 길이 제한에서 잘림"]}
    rows = {r["name"]: r for r in result["ranking"]}
    assert (rows["20261007-100000-middle"]["truncated"],
            rows["20261007-100000-middle"]["truncated_middle"]) == (False, 1)
    assert (rows["20261007-100001-final"]["truncated"],
            rows["20261007-100001-final"]["truncated_middle"]) == (True, 0)
    assert "중간 잘림" in md
    line = [l for l in md.splitlines() if l.startswith("| 1 | `20261007-100000-middle`")][0]
    cells = [c.strip() for c in line.strip("|").split("|")]
    header = [l for l in md.splitlines() if l.startswith("| 순위 |")][0]
    names = [c.strip() for c in header.strip("|").split("|")]
    assert cells[names.index("중간 잘림")] == "1"
    assert cells[names.index("잘림 (마지막)")] == "✗"


def test_model_gate_is_off_when_null(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    make_run(str(runs), "20261007-100004-4o", model="gpt-4o")
    _code, result, _md = select(tmp_path)
    assert order(result) == ["20261007-100004-4o"]


def test_unknown_dirty_state_is_not_clean(tmp_path):
    """git 기록이 없는 옛 실행은 깨끗했는지 모른다 - 깨끗한 것으로 치지 않는다."""
    runs = tmp_path / "runs"
    runs.mkdir()
    make_run(str(runs), "20261007-100000", dirty=None)
    code, result, _md = select(tmp_path)
    assert code == 1 and result["rank1"] is None
    assert reasons(result) == {"20261007-100000": ["작업 트리 기록 없음 (git.dirty)"]}


def test_folder_without_summary_is_listed_as_excluded(five):
    (five / "runs" / "20261007-150000").mkdir()
    _code, result, md = select(five)
    assert reasons(result)["20261007-150000"] == ["summary.json 없음"]
    assert "summary.json 없음" in md


def test_runs_of_another_task_are_left_out(five):
    make_run(str(five / "runs"), "20261007-160000-bill", task="bill")
    _code, result, md = select(five)
    assert "20261007-160000-bill" not in [r["name"] for r in result["ranking"]]
    assert result["runs_source"]["skipped_other_task"] == ["20261007-160000-bill"]
    assert "다른 과제의 실행 1개" in md


# ===================================================================== #
# 3. 규칙은 파일에 있다 - 순서 · 가중치를 파일에서 바꾼다
# ===================================================================== #
def test_ordering_comes_from_the_rule_file(five):
    rep = DEFAULT_RULE["ordering"][0]
    assert rep["by"] == "representative"
    rule = write_rule(five, ordering=[{"by": "warning", "order": "asc"}, rep])
    _code, result, _md = select(five, "--rule", rule)
    # warning 이 먼저면 pass-c(1) 가 1등, 그다음 대표성 pass-a(0) < pass-b(0.98)
    assert order(result) == ["20261007-120000-pass-c", "20261007-100000-pass-a",
                             "20261007-110000-pass-b"]


def test_weights_come_from_the_rule_file(five):
    """data-action 만 보게 하면 pass-a(30) 다음은 중앙값에서 5 떨어진 pass-b."""
    rule = write_rule(five, ordering=[{"by": "representative",
                                       "metrics": {"screens": 0, "data_actions": 1,
                                                   "changes": 0}}])
    _code, result, _md = select(five, "--rule", rule)
    assert order(result)[:2] == ["20261007-100000-pass-a", "20261007-110000-pass-b"]


def test_desc_order(five):
    rule = write_rule(five, ordering=[{"by": "attempts", "order": "desc"}])
    _code, result, _md = select(five, "--rule", rule)
    assert order(result) == ["20261007-120000-pass-c", "20261007-110000-pass-b",
                             "20261007-100000-pass-a"]


@pytest.mark.parametrize("change,needle", [
    ({"gates": {"passed": True, "no_redeclard": True}}, "모르는 문지기"),
    ({"ordering": [{"by": "warnings"}]}, "모르는 값"),
    ({"ordering": [{"by": "warning", "order": "down"}]}, "asc 나 desc"),
    ({"ordering": [{"by": "representative", "metrics": {"screen": 1}}]}, "모르는 값"),
    ({"ordering": []}, "비어 있지 않은 목록"),
    ({"gates": {"passed": "yes"}}, "true/false"),
])
def test_a_malformed_rule_stops_the_command(five, capsys, change, needle):
    rule = write_rule(five, **change)
    code = _api.select_main(["--task", "transfer", "--runs", str(five / "runs" / "*"),
                             "--rule", rule, "--out", str(five / "sel")])
    assert code == 2 and needle in capsys.readouterr().err
    assert not (five / "sel").exists()


# ===================================================================== #
# 4. 결과 - 규칙 전문과 커밋 · 연구자 결정 칸 · md
# ===================================================================== #
def test_result_keeps_the_rule_and_its_commit(five):
    _code, result, md = select(five)
    rule = result["rule"]
    assert rule["content"] == DEFAULT_RULE
    assert rule["path"] == "flows/selection_rule.json"
    assert len(rule["sha256"]) == 64 and rule["repo_commit"]
    assert "rule_file_commit" in rule and "rule_file_dirty" in rule
    assert rule["sha256"][:12] in md and '"ordering"' in md


def test_researcher_decision_is_left_blank(five):
    _code, result, md = select(five)
    assert result["researcher_decision"] == {"chosen": "", "same_as_rank1": None,
                                             "reason": ""}
    assert "## 연구자 결정" in md


def test_md_ranks_every_run_and_links_rank1_brief(five):
    _code, _result, md = select(five)
    table = [l for l in md.splitlines() if l.startswith("| ") and "`2026" in l]
    first = [l for l in table if "pass-a" in l][0]
    assert first.startswith("| 1 | `20261007-100000-pass-a`")
    assert any("redeclared" in l and "도구가 고침: redeclared BANKS" in l for l in table)
    assert "**1등: `20261007-100000-pass-a`**" in md
    assert "(../runs/20261007-100000-pass-a/designer_brief.md)" in md


def test_output_file_names(five):
    select(five)
    files = sorted(os.listdir(str(five / "sel")))
    assert len(files) == 2 and files[0].startswith("transfer_") \
        and files[0].endswith(".json") and files[1].endswith(".md")


# ===================================================================== #
# 5. 규칙을 바꾼 뒤 지난 결과와 나란히
# ===================================================================== #
def test_compare_with_an_earlier_selection(five):
    _code, before, _md = select(five)
    before_path = str(five / "sel" / sorted(os.listdir(str(five / "sel")))[0])
    rule = write_rule(five, ordering=[{"by": "warning", "order": "asc"}])
    _code, after, md = select(five, "--rule", rule, "--compare", before_path)
    c = after["compare"]
    assert c["rule_changed"] is True and c["ordering"]["changed"] is True
    assert c["rank1"] == {"before": "20261007-100000-pass-a",
                          "after": "20261007-120000-pass-c"}
    runs = {r["name"]: r for r in c["runs"]}
    assert runs["20261007-120000-pass-c"]["before"][0] == 3
    assert runs["20261007-120000-pass-c"]["after"][0] == 1
    assert runs["20261007-130000-fail"]["after"][0] is None
    assert "## 지난 고르기와 비교" in md


def test_an_earlier_result_replays_its_rule(five):
    rule = write_rule(five, ordering=[{"by": "attempts", "order": "desc"}])
    _code, first, _md = select(five, "--rule", rule)
    first_path = str(five / "sel" / sorted(os.listdir(str(five / "sel")))[0])
    os.remove(rule)                          # 규칙 파일이 없어져도 결과에서 되살린다
    _code, again, md = select(five, "--rule", first_path)
    assert again["rule"]["content"] == first["rule"]["content"]
    assert again["rule"]["sha256"] == first["rule"]["sha256"]
    assert order(again) == order(first)
    assert "지난 결과" in md


# ===================================================================== #
# 6. 어디서 실행을 찾나
# ===================================================================== #
def test_default_reads_outputs_restructure_auto(five, monkeypatch):
    monkeypatch.setenv("SENIOR_UI_OUTPUTS", str(five))
    os.rename(str(five / "runs"), str(five / "restructure_auto"))
    code = _api.select_main(["--task", "transfer"])
    assert code == 0
    files = os.listdir(str(five / "selection"))
    assert len(files) == 2
    result = json.load(io.open(str(five / "selection" / sorted(files)[0]), encoding="utf-8"))
    assert result["runs_source"]["default"] is True
    assert result["counts"]["runs"] == 5


def test_a_folder_of_runs_is_expanded(five):
    """results/runs 처럼 summary 가 없는 폴더를 주면 그 아래의 실행들."""
    _code, result, _md = select(five, runs=str(five / "runs"))
    assert result["counts"]["runs"] == 5


def test_no_runs_is_a_cannot_run(tmp_path, capsys):
    code = _api.select_main(["--task", "transfer", "--runs", str(tmp_path / "none*"),
                             "--out", str(tmp_path / "sel")])
    assert code == 2 and "실행 폴더가 없다" in capsys.readouterr().err


def test_the_select_command_never_imports_the_model_client():
    """저장된 결과만 읽는다 - 모델 호출 모듈을 끌어오지 않는다."""
    import subprocess
    import sys
    code = ("import sys; import senior_ui.select.__main__; "
            "bad = [m for m in sys.modules if m.startswith('openai') or "
            "m.startswith('senior_ui.restructure') or m.startswith('playwright')]; "
            "print(bad); sys.exit(1 if bad else 0)")
    p = subprocess.run([sys.executable, "-c", code], cwd=_api.ROOT_DIR,
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr


# ===================================================================== #
# 7. mock 실행으로 끝까지 (pytest -m browser)
# ===================================================================== #
MOCK_CASES = [
    ("transfer", ["--mock", "preserved-all", "--attempts", "1"], "preserved-all"),
    ("bill", ["--task", "bill", "--mock", "bill-identity", "--attempts", "1"],
     "bill-identity"),
]


@pytest.mark.browser
@pytest.mark.parametrize("task,args,mode", MOCK_CASES, ids=[c[2] for c in MOCK_CASES])
def test_select_runs_to_the_end_on_a_mock_run(tmp_path, task, args, mode):
    """실제 루프가 쓴 실행 폴더를 그대로 읽는다. 루프는 .mock-outputs/ 에 쓴다."""
    import capture_baseline as C
    C.ensure_mock_input()
    summary, run_code = C.run_mock(args)
    assert run_code == 0 and summary["passed"] is True
    run_dir, name = summary["run_dir"], os.path.basename(summary["run_dir"])
    out = str(tmp_path / "sel")

    def go(*extra):
        before = set(os.listdir(out)) if os.path.isdir(out) else set()
        code = _api.select_main(["--task", task, "--runs", run_dir, "--out", out]
                                + list(extra))
        js = [f for f in set(os.listdir(out)) - before if f.endswith(".json")][0]
        return code, json.load(io.open(os.path.join(out, js), encoding="utf-8"))

    # 기본 규칙 - mock 은 후보가 아니다. 결과는 쓰고 종료 1
    code, result = go()
    assert code == 1 and result["rank1"] is None
    assert "mock 실행 (%s)" % mode in result["ranking"][0]["excluded_because"]

    # mock · 작업 트리 문지기를 끈 규칙 - 그 실행이 1등이고 값이 모두 읽힌다
    rule = write_rule(tmp_path, gates=dict(DEFAULT_RULE["gates"], not_mock=False,
                                           clean_tree=False))
    code, result = go("--rule", rule)
    assert code == 0 and result["rank1"] == name
    row = result["ranking"][0]
    assert row["passed"] is True and row["attempts"] == 1
    assert row["fatal"] == 0 and isinstance(row["warning"], int)
    assert row["redeclared"] == [] and row["truncated"] is False
    assert row["screens"] and row["data_actions"] and row["changes"]
    assert row["choice_groups"] and all(
        g["kept"] == g["selectable"] for g in row["choice_groups"].values())
    assert row["brief"] and os.path.exists(os.path.join(_api.ROOT_DIR, row["brief"]))
    assert row["commit"] == summary["git"]["commit"]
    if task == "transfer":
        assert all(p["ok"] for p in row["error_paths"].values())
