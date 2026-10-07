r"""저장된 실제 답(fixtures/real_runs/)으로 실행 폴더 하나를 꾸민다 - 설계서 시험용.

모델은 부르지 않는다. 루프의 check_reply 와 같은 순서로 답을 받고(답 가르기 → 완료
칸 별칭 → 형식 검사 → 선택지 데이터 넣기), 검사기를 루프와 같은 길(audit_call.run_audit)
로 돌려 attempt_1.audit.json 을 쓰고, 루프가 쓰는 모양의 summary.json 을 남긴다.
검사를 통과하지 못하면 summary 의 passed 도 false 다 - 설계서 도구가 거절해야 한다.

  SAVED = {이름: (고정물 폴더, 답 파일, 과제)}

실행 폴더는 .pytest-outputs/storyboard/<이름>/ 이다 (서버가 서빙하는 저장소 안).
"""
import asyncio
import io
import json
import os
import shutil

import _api

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL = os.path.join(ROOT, "tests", "fixtures", "real_runs")
OUT = os.path.join(ROOT, ".pytest-outputs", "storyboard")

# 설계서 기준값에 쓰는 저장된 답. 셋 다 지금 검사기로 통과한다 (refine_102041 = 실행
# 20261007-102041 의 다듬기 답 - 입구 31/31, bill_sol 시도 4 = 20261007-103023-bill).
SAVED = {
    "refine_102041": ("refine_102041", "refine.response.txt", "transfer"),
    "bill_sol_4": ("bill_sol", "attempt_4.response.txt", "bill"),
}
OPTIONAL = {"transfer": [], "bill": ["MENU_TABS"]}


def _write(path, text):
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def make_saved_run(name, base_url, out_root=OUT):
    """저장된 답 하나로 실행 폴더를 만들고 그 경로를 돌려준다."""
    folder, reply_file, task = SAVED[name]
    src = os.path.join(REAL, folder)
    text = io.open(os.path.join(src, reply_file), encoding="utf-8").read()
    html, flow, _ = _api.parse_reply(text, {})
    flow.setdefault("name", "auto")
    _api.reply_module.accept_done_alias(flow)
    tdef = _api.load_task(task)
    data = json.load(io.open(os.path.join(src, "preserved.json"), encoding="utf-8"))
    problems = (_api.reply_module.validate_flow(flow, html, _api.flow_module.required_errors(task),
                                                tdef["done_expect"])
                + _api.reply_module.preserved_problems(html, data, optional=OPTIONAL[task]))
    build, redeclared = _api.preserve_module.inject(html, data)

    d = os.path.join(out_root, name)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    p = lambda f: os.path.join(d, f)
    _write(p("attempt_1.response.txt"), text)
    _write(p("attempt_1.model.html"), html)
    _write(p("attempt_1.html"), build)
    _write(p("attempt_1.flow.json"), json.dumps(flow, ensure_ascii=False, indent=2))
    for f, out in (("plan.json", "attempt_1.plan.json"),
                   ("diagnosis.json", "attempt_1.diagnosis.json")):
        if os.path.exists(os.path.join(src, f)):
            shutil.copy2(os.path.join(src, f), p(out))

    orig_rel = tdef["original"]
    orig_html = io.open(os.path.join(ROOT, orig_rel), encoding="utf-8").read()
    orig_url = "%s/%s" % (base_url, orig_rel)
    snap = asyncio.run(_api.drive(orig_url, _api.load_flow(None, task=task), errors=False))
    rel = os.path.relpath(p("attempt_1.html"), ROOT).replace(os.sep, "/")
    report = _api.audit_call_module.run_audit(
        snap, orig_html, p("attempt_1.html"), p("attempt_1.flow.json"),
        "%s/%s" % (base_url, rel), None, "wireframe", original_url=orig_url, task=task)
    _write(p("attempt_1.audit.json"), json.dumps(report, ensure_ascii=False, indent=2))
    passed = bool(report.get("passed")) and not problems
    summary = {
        "run_dir": d, "model": "saved:%s" % name, "model_source": "fixture",
        "mock": None, "task": task, "stage": "wireframe",
        "attempts": [{"n": 1, "stage": "audit", "passed": passed,
                      "problems": problems, "redeclared": redeclared}],
        "passed": passed, "stopped_reason": None if passed else "budget_exhausted",
        "final": {"attempt": 1, "html": p("attempt_1.html"), "flow": p("attempt_1.flow.json"),
                  "audit": p("attempt_1.audit.json"),
                  "plan": p("attempt_1.plan.json") if os.path.exists(p("attempt_1.plan.json"))
                  else None,
                  "diagnosis": p("attempt_1.diagnosis.json")
                  if os.path.exists(p("attempt_1.diagnosis.json")) else None,
                  "model_html": p("attempt_1.model.html")},
        "git": {"commit": None, "branch": None, "dirty": None, "dirty_files": []},
        "refine": {"final_from": "generate", "final_label": "저장된 답 (%s)" % reply_file},
        "cost": None,
    }
    _write(p("summary.json"), json.dumps(summary, ensure_ascii=False, indent=2))
    return d
