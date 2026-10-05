r"""오류 경로 - 흐름 명세의 error_paths 와 검사 J.

원본에는 잘못된 입력에서 뜨는 오류가 있다 (계좌번호가 틀림, 은행이 틀림).
검사기가 정답 경로만 걸으면 재설계에서 오류 처리가 통째로 빠져도 잡지 못한다.
여기 있는 테스트는 브라우저 없이 도는 것들이다 - 걷기까지 하는 것은
test_error_paths_browser.py 에 있다.
"""
import io
import json

import _api

F = _api.flow_module


def test_truth_keeps_extra_placeholders():
    """truth 블록의 필수 키 밖의 값(틀린 계좌번호 등)도 자리표시자로 남는다.

    전에는 make_truth 가 필수 키 넷만 골라 담아서, 오류 경로가 쓰는
    {ACCOUNT_WRONG} 이 채워지지 않고 글자 그대로 눌렸다."""
    t = F.make_truth({"BANK": "신한", "ACCOUNT": "1", "AMOUNT": "2", "NAME": "n",
                      "ACCOUNT_WRONG": "9", "BANK_WRONG": "국민"})
    assert t["ACCOUNT_WRONG"] == "9"
    assert t["BANK_WRONG"] == "국민"
    assert F.fill("{ACCOUNT_WRONG}/{ACCOUNT}/{BANK_WRONG}", t) == "9/1/국민"


# --------------------------------------------------------------------- #
# 원본 흐름의 오류 경로
# --------------------------------------------------------------------- #
J = _api.j_errors


def original():
    return _api.load_flow(None)


def dumps(x):
    return json.dumps(x, ensure_ascii=False)


def test_original_declares_two_error_paths_with_wrong_values_in_truth():
    flow = original()
    assert [e["id"] for e in flow["error_paths"]] == ["wrong-account", "wrong-bank"]
    for e in flow["error_paths"]:
        for key in e["uses"]:
            assert key in flow["truth"], key
            # 틀린 값은 자리표시자로만 눌린다 - 글자 그대로 적지 않는다.
            assert flow["truth"][key] not in dumps(e["inputs"])
            assert "{%s}" % key in dumps(e["inputs"])
    assert flow["truth"]["ACCOUNT_WRONG"] != flow["truth"]["ACCOUNT"]
    assert flow["truth"]["BANK_WRONG"] != flow["truth"]["BANK"]


# 원본의 두 경로가 걷기에서 실제로 지나는 곳. trigger 는 잘못된 입력의 마지막
# 동작(계좌 [다음] / 확인 [보내기])을 누른 화면이다. 브라우저 테스트
# (test_error_paths_browser.py) 가 걷기에서 같은 값을 얻는지 본다.
ORIGINAL_TRIGGERS = {"wrong-account": "account", "wrong-bank": "confirm"}


def test_original_error_paths_pass_the_back_to_rule():
    """back_to 는 오류가 나타난 화면이거나 그보다 앞이어야 한다.

    갈라진 지점(from_step)과는 견주지 않는다 - wrong-bank 는 bank 에서 갈라져
    confirm 으로 돌아가는데, confirm 은 bank 보다 뒤지만 오류(보내기)가 나타난
    곳이므로 맞다."""
    flow = original()
    screens = J.step_screens(flow["steps"])
    for e in flow["error_paths"]:
        assert J.back_to_ok(screens, e["back_to"], e["expect_screen"],
                            ORIGINAL_TRIGGERS[e["id"]]), e["id"]
    wb = [e for e in flow["error_paths"] if e["id"] == "wrong-bank"][0]
    assert screens.index(wb["back_to"]) > screens.index(wb["from_step"])


def test_back_to_rule_rejects_screens_after_the_error():
    screens = J.step_screens(original()["steps"])
    # 오류는 confirm 에서 났다 - password · done 은 그보다 뒤다.
    assert not J.back_to_ok(screens, "password", "err-bank", "confirm")
    assert not J.back_to_ok(screens, "done", "err-bank", "confirm")
    # 앞의 화면은 된다.
    assert J.back_to_ok(screens, "account", "err-bank", "confirm")
    # 같은 화면 안에서 알리는 설계는 그 화면이 기준이다.
    assert J.back_to_ok(screens, "account", "account", "account")
    assert not J.back_to_ok(screens, "amount", "account", "account")
    # 정답 경로에 없는 화면으로는 돌아갈 수 없다 (오류 화면 자신만 예외).
    assert not J.back_to_ok(screens, "somewhere", "err-bank", "confirm")


# --------------------------------------------------------------------- #
# 판정 - 손으로 만든 걷기 결과로
# --------------------------------------------------------------------- #
STEPS = [{"screen": "start"},
         {"screen": "account", "click": "[data-action='go']"},
         {"screen": "amount", "click": "#next"}]
HAPPY_ACCOUNT = "계좌번호를 넣어 주세요\n다음"
HAPPY_AMOUNT = "얼마를 보낼까요?\n다음"


def flow_with(paths, **kw):
    f = {"name": "t", "derived_from_original": False, "steps": STEPS,
         "expect": {}, "error_paths": paths, "truth": F.truth_of(None)}
    f.update(kw)
    return f


def ep(**kw):
    e = {"id": "wrong-account", "from_step": "account",
         "inputs": [{"type": "{ACCOUNT_WRONG}", "key": "#acc"}, {"click": "#next"}],
         "expect_screen": "account",
         "recover": [{"click": "#clear"}], "back_to": "account"}
    e.update(kw)
    return e


def walked(after="account", after_text="", recover="account", error=None):
    return {"error": error,
            "trigger": {"landed_on": "account", "dom_screen": "account"},
            "before_text": HAPPY_ACCOUNT,
            "after": {"landed_on": after, "dom_screen": after},
            "after_text": after_text,
            "recover": {"landed_on": recover, "dom_screen": recover},
            "js_errors": [], "dialogs": []}


def judge(flow, rows, stopped_at=None):
    rep = {"screens": {"start": {"text": "시작"},
                       "account": {"text": HAPPY_ACCOUNT},
                       "amount": {"text": HAPPY_AMOUNT}},
           "error_paths": rows}
    ctx = _api.AuditContext(orig={"screens": {}}, rep=rep, orig_html="",
                            rep_html="", flow=flow, derived=False,
                            want=["start", "account", "amount"], shared=[])
    ctx.stopped_at = stopped_at
    J.run(ctx)
    return ctx


def test_inline_notice_on_the_same_screen_counts_as_an_error_state():
    """입력하는 즉시 알리는 설계 - 같은 화면에 머무르지만 새 글이 나타났다.
    이것도 오류 상태로 인정한다."""
    after = HAPPY_ACCOUNT + "\n110-234-567891\n계좌번호가 맞지 않아요. 다시 확인해 주세요"
    ctx = judge(flow_with([ep()]), {"wrong-account": walked(after_text=after)})
    assert ctx.fatal == [] and ctx.warning == []
    res = ctx.metrics["error_paths"]["wrong-account"]
    assert res["appeared"] and res["recovered"]
    assert res["notice"] == ["계좌번호가 맞지 않아요. 다시 확인해 주세요"]


def test_disabled_next_with_a_reason_counts_when_the_flow_does_not_press_it():
    """[다음] 이 꺼진 설계는 꺼진 버튼을 누르지 않는다 - 흐름의 마지막 입력이
    타이핑이다. 이유 글이 새로 보이면 통과한다."""
    e = ep(inputs=[{"type": "{ACCOUNT_WRONG}", "key": "#acc"}])
    after = HAPPY_ACCOUNT + "\n110234567891\n없는 계좌번호예요. [다음]을 누를 수 없어요"
    ctx = judge(flow_with([e]), {"wrong-account": walked(after_text=after)})
    assert ctx.fatal == []
    assert ctx.metrics["error_paths"]["wrong-account"]["appeared"]


def test_only_the_echo_of_the_typed_value_is_not_an_error_state():
    """같은 화면에 새로 보인 것이 눌러 넣은 계좌번호와 자릿수뿐이면 알린 것이
    아니다."""
    after = HAPPY_ACCOUNT + "\n110-234-567891\n12"
    ctx = judge(flow_with([ep()]), {"wrong-account": walked(after_text=after)})
    assert [f["check"] for f in ctx.fatal] == ["J"]
    assert "새로 나타난 글이 없다" in ctx.fatal[0]["detail"]


def test_moving_on_with_the_wrong_value_is_not_an_error_state():
    """틀린 값으로 다음 화면에 넘어갔다 - 오류 처리가 없는 설계."""
    ctx = judge(flow_with([ep()]),
                {"wrong-account": walked(after="amount", after_text=HAPPY_AMOUNT)})
    assert [f["check"] for f in ctx.fatal] == ["J"]
    assert "나타나지 않았다" in ctx.fatal[0]["detail"]


def test_claiming_the_next_happy_screen_as_the_error_screen_needs_new_text():
    """흐름이 오류 화면을 정답 경로의 다음 화면이라고 적어도, 그 화면이 정답
    경로에서 보이던 그대로라면 알린 것이 아니다."""
    e = ep(expect_screen="amount")
    ctx = judge(flow_with([e]), {"wrong-account": walked(
        after="amount", after_text=HAPPY_AMOUNT + "\n110234567891")})
    assert [f["check"] for f in ctx.fatal] == ["J"]


def test_not_getting_back_is_fatal():
    after = HAPPY_ACCOUNT + "\n계좌번호가 맞지 않아요"
    ctx = judge(flow_with([ep()]),
                {"wrong-account": walked(after_text=after, recover="start")})
    assert [f["check"] for f in ctx.fatal] == ["J"]
    assert "되돌아가지 못했다" in ctx.fatal[0]["detail"]


def test_back_to_after_the_error_is_fatal():
    after = HAPPY_ACCOUNT + "\n계좌번호가 맞지 않아요"
    ctx = judge(flow_with([ep(back_to="amount")]),
                {"wrong-account": walked(after_text=after, recover="amount")})
    assert [f["check"] for f in ctx.fatal] == ["J"]
    assert "뒤다" in ctx.fatal[0]["detail"]


def test_notice_without_the_task_words_is_a_warning_only():
    """알림 단어는 원본 흐름의 notice_any 에서 읽는다 (wrong-account: 계좌).
    모델이 적은 expect_text_any 는 판정에 쓰지 않는다."""
    e = ep(expect_text_any=["다시"])
    ctx = judge(flow_with([e]), {"wrong-account": walked(
        after_text=HAPPY_ACCOUNT + "\n다시 넣어 주세요")})
    assert ctx.fatal == []
    assert [w["check"] for w in ctx.warning] == ["J"]
    assert "계좌" in ctx.warning[0]["detail"]


def test_flow_without_error_paths_stands_down():
    """옛 흐름(Run 1~4)은 오류 경로가 없다. 판정이 바뀌지 않아야 한다."""
    ctx = judge(flow_with([]), {})
    assert ctx.fatal == [] and ctx.warning == []
    assert any(s.startswith("J/") for s in ctx.skipped)
    assert "error_paths" not in ctx.metrics


def test_required_error_path_missing_is_fatal():
    ctx = judge(flow_with([], error_paths_required=["wrong-account", "wrong-bank"]),
                {})
    assert sorted(f["error_path"] for f in ctx.fatal) == ["wrong-account",
                                                          "wrong-bank"]


def test_stall_before_the_branch_is_derived_when_check_a_already_stopped():
    ctx = judge(flow_with([ep()]),
                {"wrong-account": walked(error={"phase": "replay",
                                                "detail": "막힘"})},
                stopped_at="account")
    assert ctx.fatal[0]["derived_from"] == "account"


# --------------------------------------------------------------------- #
# 형식 검사 (reply.validate_flow) - 브라우저 없이
# --------------------------------------------------------------------- #
HTML = """<html><body><div id="phone">
<section class="screen on" data-screen="start"><button data-action="go">x</button></section>
<section class="screen" data-screen="account"><button id="next" data-action="next">x</button>
<button id="clear" data-action="clear">x</button></section>
<section class="screen" data-screen="oops"><button id="ok" data-action="ok">x</button></section>
<section class="screen" data-screen="amount"><b id="dn-amt"></b></section>
</div><script>
document.getElementById('phone').addEventListener('click', e => {
  const el = e.target.closest('[data-action]'); const a = el.dataset.action;
  if (a === 'go') {} else if (a === 'next') {} else if (a === 'clear') {}
  else if (a === 'ok') {}
});
</script></body></html>"""


def model_flow(paths):
    return {"name": "auto", "derived_from_original": False,
            "required_ids": ["phone", "dn-amt"], "steps": STEPS,
            "expect": {"done": [["#dn-amt", "{AMOUNT_SHOWN}"]]},
            "error_paths": paths}


def popup_ep(**kw):
    e = ep(expect_screen="oops", recover=[{"click": "#ok"}], back_to="account")
    e.update(kw)
    return e


REQUIRED = [{"id": "wrong-account", "about": "계좌번호가 틀렸다",
             "uses": ["ACCOUNT_WRONG"]},
            {"id": "wrong-bank", "about": "은행이 틀렸다", "uses": ["BANK_WRONG"]}]


def test_screen_reached_only_by_an_error_path_is_covered():
    """오류 화면(oops)은 정답 경로가 지나가지 않는다. 오류 경로가 지나가면
    덮인 것이다 - 전에는 억지 우회 경로를 넣어야 통과했다."""
    assert _api.validate_flow(model_flow([popup_ep()]), HTML) == []
    bare = _api.validate_flow(model_flow([]), HTML)
    assert any("지나가지 않는 화면" in p and "oops" in p for p in bare)


def test_old_flows_get_the_same_problems_without_required_errors():
    """필수 오류 경로를 넘기지 않으면(옛 흐름의 재검사) 빠진 오류 경로를
    문제로 세지 않는다."""
    probs = _api.validate_flow(model_flow([popup_ep()]), HTML)
    assert probs == []


def test_required_error_paths_must_be_declared():
    probs = _api.validate_flow(model_flow([popup_ep()]), HTML, REQUIRED)
    assert len(probs) == 1
    assert "wrong-bank" in probs[0] and "은행이 틀렸다" in probs[0]
    # 틀린 값은 문제 글에도 나오지 않는다 - 자리표시자 이름만.
    assert "국민" not in probs[0]


def test_error_path_must_use_the_wrong_value_placeholder():
    e = popup_ep(inputs=[{"type": "{ACCOUNT}", "key": "#acc"}, {"click": "#next"}])
    probs = _api.validate_flow(model_flow([e]), HTML, REQUIRED[:1])
    assert any("{ACCOUNT_WRONG}" in p for p in probs)


def test_error_path_names_must_exist():
    e = popup_ep(from_step="nowhere", expect_screen="ghost", back_to="ghost2")
    probs = _api.validate_flow(model_flow([e]), HTML)
    text = " | ".join(probs)
    assert "from_step" in text and "expect_screen" in text and "back_to" in text


def test_back_to_after_an_on_path_error_screen_is_a_format_problem():
    """오류가 정답 경로 위의 화면(account)에 나타나면, 그보다 뒤(amount)로
    돌아가는 것은 흐름만 보고도 틀렸다."""
    e = ep(back_to="amount")
    probs = _api.validate_flow(model_flow([e, popup_ep(id="x")]), HTML)
    assert any("back_to" in p and "amount" in p for p in probs)


def test_error_paths_of_the_wrong_type_are_a_shape_problem():
    probs = _api.validate_flow(model_flow({"id": "x"}), HTML)
    assert any("error_paths" in p for p in probs)


# --------------------------------------------------------------------- #
# 진단·계획 - plan.errors
# --------------------------------------------------------------------- #
P = _api.plan_module
ORIG_SCREENS = ["home", "account", "confirm", "err-account", "err-bank"]
DIAG = [{"id": "D1", "screen": "err-account", "element": "오류 팝업",
         "problem": "코드만 보인다", "evidence": "ELB00016"}]


def plan_with(errors, screens=("start", "account", "review")):
    p = {"screens": [{"name": n, "purpose": "p", "from": []} for n in screens],
         "changes": [{"id": "C1", "what": "w", "why": "y", "addresses": ["D1"],
                      "from_screens": ["err-account"], "to_screens": ["account"]}]}
    if errors is not None:
        p["errors"] = errors
    return p


ERRS = [{"id": "wrong-account", "screen": "account", "how": "같은 화면에 빨간 글",
         "back_to": "account"},
        {"id": "wrong-bank", "screen": "review", "how": "확인 화면 위에 안내",
         "back_to": "account"}]
IDS = ["wrong-account", "wrong-bank"]


def test_plan_must_say_how_each_error_is_shown():
    assert P.plan_problems(DIAG, plan_with(ERRS), ORIG_SCREENS, error_ids=IDS) == []
    probs = P.plan_problems(DIAG, plan_with(None), ORIG_SCREENS, error_ids=IDS)
    assert any("plan.errors" in p for p in probs)
    probs = P.plan_problems(DIAG, plan_with(ERRS[:1]), ORIG_SCREENS, error_ids=IDS)
    assert any("wrong-bank" in p for p in probs)


def test_plan_error_screens_must_be_planned_screens():
    bad = [dict(ERRS[0], screen="popup"), dict(ERRS[1], back_to="nowhere")]
    probs = P.plan_problems(DIAG, plan_with(bad), ORIG_SCREENS, error_ids=IDS)
    text = " | ".join(probs)
    assert "popup" in text and "nowhere" in text


def test_plan_without_error_ids_is_checked_as_before():
    """오류 정의를 넘기지 않으면(옛 계획) plan.errors 를 요구하지 않는다."""
    assert P.plan_problems(DIAG, plan_with(None), ORIG_SCREENS) == []


def test_reflection_can_change_how_an_error_is_shown():
    new, probs = P.apply_changes(
        plan_with(ERRS), DIAG,
        [{"op": "change", "target": "error:wrong-bank",
          "new": {"screen": "account", "how": "계좌 화면에서 알린다"}}],
        ORIG_SCREENS)
    assert probs == []
    assert [e for e in new["errors"] if e["id"] == "wrong-bank"][0]["screen"] == "account"


def test_reflection_cannot_drop_a_screen_an_error_uses():
    _new, probs = P.apply_changes(
        plan_with(ERRS), DIAG, [{"op": "remove", "target": "screen:review"}],
        ORIG_SCREENS)
    assert any("review" in p for p in probs)


# --------------------------------------------------------------------- #
# 프롬프트 - 조건과 자리표시자 이름만, 실제 값은 없다
# --------------------------------------------------------------------- #
import glob  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "baseline")


def wrong_values():
    t = original()["truth"]
    return {k: t[k] for e in original()["error_paths"] for k in e["uses"]}


def errors_section(text):
    m = re.search(r"## 원본의 오류 조건\n(.*?)(?=\n## |\Z)", text, re.S)
    assert m, "프롬프트에 오류 조건 절이 없다"
    return m.group(1)


def test_errors_block_names_placeholders_but_never_the_values():
    block = _api.prompt_module.errors_block(original()["error_paths"])
    for key, value in wrong_values().items():
        assert "{%s}" % key in block
        assert value not in block, key
    assert "wrong-account" in block and "wrong-bank" in block


def prompts():
    html = io.open(os.path.join(_api.ROOT_DIR, "inputs", "original_transfer.html"),
                   encoding="utf-8").read()
    yield "plan", _api.build_plan_prompt(_api.load_plan_template(), html, "",
                                         P.screens_in(html))
    yield "generate", _api.build_prompt(_api.load_template(), html, "", "", "{}")


def test_built_prompts_carry_the_conditions_without_the_values():
    for name, text in prompts():
        sec = errors_section(text)
        for key, value in wrong_values().items():
            assert "{%s}" % key in sec, (name, key)
            assert value not in sec, (name, key)
        # 계좌번호는 원본 어디에도 없는 값이다 - 프롬프트 전체에 없어야 한다.
        assert wrong_values()["ACCOUNT_WRONG"] not in text, name


def test_prompt_baselines_do_not_leak_the_wrong_values():
    files = glob.glob(os.path.join(BASE, "prompt", "*.txt"))
    assert files
    for path in files:
        text = io.open(path, encoding="utf-8").read()
        assert wrong_values()["ACCOUNT_WRONG"] not in text, path
        if "## 원본의 오류 조건" in text:
            assert wrong_values()["BANK_WRONG"] not in errors_section(text), path


# --------------------------------------------------------------------- #
# mock 일곱 모드 - 형식 검사까지 (브라우저 없이)
# --------------------------------------------------------------------- #
M = _api.model_module


def test_mock_modes_split_on_error_paths_at_the_format_check():
    """errors-undeclared 만 오류 경로가 없어 형식에서 떨어진다. 나머지는 오류
    경로를 적었다 (errors-unhandled 는 HTML 에 처리가 없어 검사 J 에서
    떨어진다 - 브라우저 테스트 test_drive.test_mock_run_matches_baseline)."""
    required = _api.flow_module.original_error_paths()
    for mode in M.MODES:
        html, flow, _ = _api.parse_reply(M.mock_reply(mode)["text"])
        flow["derived_from_original"] = False
        errs = [p for p in _api.validate_flow(flow, html, required)
                if "오류 경로" in p or "error_paths" in p]
        if mode == "errors-undeclared":
            assert len(errs) == 2, errs
        else:
            assert errs == [], (mode, errs)
        handled = "mock-acc-err" in html
        assert handled == (M.MOCKS[mode][3] == "handled"), mode
