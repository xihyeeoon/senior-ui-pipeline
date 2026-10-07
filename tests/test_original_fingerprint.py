r"""원본 지문 - 재구성 실행이 어느 원본으로 만들어졌는가 (11-11).

원본 HTML 은 고쳐진다 (11-11: 이체 계좌 화면의 키패드). 고치기 전 원본으로 만든 실행을
고친 뒤의 실행과 함께 고르면 "같은 조건의 반복" 이 아니다. 그래서 실행마다 원본 HTML
파일의 sha256 을 남긴다 - summary.json 의 original_sha256 과 run.log 첫 줄. 고르기 규칙의
문지기 original: "current" 가 그것을 지금 inputs 의 원본과 견준다 (test_select).

지문은 줄끝을 LF 로 맞춘 내용의 sha256 이다 (tasks.fingerprint - 설계서의 원본 지문과
같은 함수). Windows 작업 트리는 CRLF 로 체크아웃되므로 그대로 재면 PC 마다 다르다.

모델도 서버도 브라우저도 부르지 않는다 (test_restructure_bugs 의 fake_run_env).
"""
import io
import json
import os

import _api
from test_restructure_bugs import (GOOD_REPLY, always_reply, fake_run_env,  # noqa: F401
                                   make_args, out_root, run_dirs)

loop = _api.loop_module
T = _api.tasks_module
ROOT = _api.ROOT


def last_run(out_root):
    d = run_dirs(out_root)[-1]
    summary = json.load(io.open(os.path.join(d, "summary.json"), encoding="utf-8"))
    log = io.open(os.path.join(d, "run.log"), encoding="utf-8").read().splitlines()
    return summary, log


def test_the_run_records_the_original_it_used(fake_run_env, out_root):
    fake_run_env.setattr(loop, "call_model", always_reply(GOOD_REPLY))
    loop.run(make_args(out_root))
    summary, log = last_run(out_root)
    want = T.original_sha256("transfer")
    assert len(want) == 64
    assert summary["original_sha256"] == want
    assert summary["original"] == "inputs/original_transfer.html"
    # 첫 줄 - 모델 다음으로 결과를 가르는 조건이다
    assert "original_sha256=%s (inputs/original_transfer.html)" % want in log[0].split(" ", 1)[1]


def test_a_given_original_is_the_one_fingerprinted(fake_run_env, out_root):
    """--original 로 다른 파일을 주면 그 파일의 지문이다 - 과제의 원본이 아니다."""
    other = os.path.join(ROOT, "results", "restructured_transfer.html")
    fake_run_env.setattr(loop, "call_model", always_reply(GOOD_REPLY))
    loop.run(make_args(out_root, original=other))
    summary, log = last_run(out_root)
    assert summary["original_sha256"] == T.file_sha256(other)
    assert summary["original_sha256"] != T.original_sha256("transfer")
    assert summary["original"] == "results/restructured_transfer.html"
    assert "(results/restructured_transfer.html)" in log[0]


def test_a_run_that_cannot_start_still_names_its_original(fake_run_env, out_root):
    """시작하지 못한 실행의 summary 에도 남긴다 - 고르기는 그런 실행을 어차피 빼지만,
    무엇으로 돌리려 했는지는 기록이다."""
    fake_run_env.delenv("OPENAI_API_KEY")
    fake_run_env.setattr(loop, "load_env", lambda: None)
    code = loop.run(make_args(out_root))
    summary, log = last_run(out_root)
    assert code == 2 and summary["stopped_reason"] == "cannot_start"
    assert summary["original_sha256"] == T.original_sha256("transfer")
    assert "original_sha256=%s" % T.original_sha256("transfer") in log[0]


def test_the_bill_task_fingerprints_its_own_original(fake_run_env, out_root):
    """원본 파일은 과제 파일이 정한다 (tasks/bill.json 의 original)."""
    fake_run_env.setattr(loop, "call_model", always_reply(GOOD_REPLY))
    loop.run(make_args(out_root, task="bill", original=None))
    summary, log = last_run(out_root)
    assert summary["original_sha256"] == T.original_sha256("bill")
    assert summary["original"] == "inputs/original_bill.html"
    assert "(inputs/original_bill.html)" in log[0]
