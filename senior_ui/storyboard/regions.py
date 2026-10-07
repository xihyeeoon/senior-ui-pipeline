r"""영역 묶기 - 실행마다 모델 호출 한 번 (어긋나면 한 번 더).

넣는 것은 셋뿐이다: 와이어프레임 그림(요소 번호를 얹은 것), 장마다 요소 목록(번호 ·
글자 · 도구가 확인한 동작), 계획의 화면 목적. 고령자 UX 규칙이나 평가는 넣지 않는다 -
이 호출은 설명만 쓴다. 받는 것은 장마다 영역 목록 `{no, name, elements, description}`.
누르면 어디로 가는지는 쓰지 말라고 한다 - 설계서의 동작 칸은 도구가 확인한 것이다.

검사: 장마다 모든 요소가 정확히 한 영역에 들어갔는가, 없는 번호를 쓰지 않았는가,
없는 장 · 이름 없는 영역은 없는가. 어긋나면 문제를 적어 한 번 다시 묻는다 (그림은
다시 보내지 않는다). 그래도 어긋나면 맞는 부분은 쓰고, 남은 요소를 "기타" 영역으로
묶고, 그 사실을 남긴다 (`fallback`).

답에는 장마다 화면 이름(name)과, 영역이 빈 상태 안내이면 그 표시(empty_state)를 더
쓸 수 있다 - 둘 다 없어도 맞는 답이다. 설계서는 화면 이름이 없으면 계획의 화면 목적
앞부분을 쓰고, 빈 상태는 모델이 표시한 것만 "예외: 빈 화면" 으로 적는다 (글자로
판정하지 않는다).

`--mock` 은 정해진 답을 쓴다 (mock_answer) - 요소를 위에서 아래로 보며 세로로 크게
벌어지는 곳에서 나눈다. 시험용 모드 둘이 더 있다: bad-then-good (첫 답이 어긋나고
다시 물으면 맞는다), bad (두 번 다 어긋난다 → "기타").
"""
import io
import json
import os
import re
import time

from senior_ui import config
from senior_ui.restructure import model as M

MOCK_MODES = ("regions", "bad-then-good", "bad")
DEFAULT_MOCK = "regions"

# 출력 상한. 추론형은 생각 토큰도 이 안에서 쓴다.
MAX_TOKENS = {"reasoning": 16000, "default": 6000}

# mock 의 정해진 답 - 앞 요소의 아래 끝과 다음 요소의 위 끝이 이만큼 벌어지면 나눈다.
MOCK_GAP = 24

OTHER_NAME = "기타"
OTHER_DESC = "모델이 어느 영역에도 넣지 않은 요소 - 도구가 모았다"

PROMPT_FILE = "regions.prompt.txt"
RESPONSE_FILE = "regions.response.txt"
RETRY_PROMPT_FILE = "regions.retry.prompt.txt"
RETRY_RESPONSE_FILE = "regions.retry.response.txt"


class CannotRun(Exception):
    """설계서를 만들 수 없다 - 실행이 아니라 도구 쪽 사정 (서버 · 폴더)."""


# 모델이 쓴 화면 이름의 상한 (넘으면 버리고 계획의 화면 목적을 쓴다)
TITLE_CHARS = 40


# --------------------------------------------------------------------------- #
# 프롬프트
# --------------------------------------------------------------------------- #
INTRO = """이것은 은행 앱 화면설계서의 "영역" 을 나누는 일입니다. 디자이너가 화면을 읽을 때 쓰는 묶음입니다.

- 아래 장마다 와이어프레임 그림과 요소 목록이 있습니다. 그림 속 e1, e2 … 이름표가 목록의 번호입니다.
- 장마다 요소를 영역으로 묶고, 영역마다 이름과 한두 줄 설명을 쓰세요.
- 설명은 그 영역에 무엇이 있고 무엇을 하는 자리인지만 씁니다. 평가 · 문제 지적 · 개선 제안은 쓰지 않습니다.
- 누르면 어디로 가는지는 쓰지 마세요. 설계서의 동작 칸에는 도구가 직접 눌러 확인한 결과가 들어갑니다.
- 모든 요소는 정확히 한 영역에 들어가야 합니다. 목록에 없는 번호를 쓰지 마세요. 요소가 없는 장은 regions 를 빈 목록으로 둡니다.
- 영역 번호(no)는 장마다 1부터, 위에서 아래 순서로 매깁니다.
- 장마다 화면 이름(name)을 짧게 씁니다 (예: "받는 사람 고르기"). 장 id 를 그대로 옮기지 마세요.
- 영역이 빈 상태 안내(목록이 비어 있다는 글 같은 것)이면 그 영역에 "empty_state": true 를 붙입니다. 아니면 쓰지 않습니다.

답은 JSON 한 덩어리만 씁니다:
{"sheets": [{"id": "<장 id>", "name": "<화면 이름>", "regions": [{"no": 1, "name": "<영역 이름>", "elements": ["e1", "e2"], "description": "<한두 줄>"}]}]}
"""

RETRY_INTRO = """앞의 답에 문제가 있습니다. 아래 문제를 고쳐 **전체 답을 다시** JSON 한 덩어리로 쓰세요. 다른 규칙은 처음과 같습니다 — 모든 요소가 정확히 한 영역에, 목록에 없는 번호는 쓰지 않고, 누르면 어디로 가는지는 쓰지 않습니다.

## 문제
"""


def action_text(it):
    """요소 목록 한 줄의 "도구 확인" 부분 - render 와 같은 말."""
    from .render import result_text
    return result_text(it, link=False)


def sheet_block(sh):
    lines = ["### %s%s" % (sh["id"], " (조건별 화면 - %s)" % sh["condition"]
                           if sh.get("condition") else "")]
    if sh.get("purpose"):
        lines.append("화면 목적 (계획): %s" % sh["purpose"])
    if not sh["items"]:
        lines.append("(요소 없음)")
    for it in sh["items"]:
        text = it.get("text") or ""
        if it["kind"] == "group":
            text = "선택지 무리 %s · %d개 (예: %s)" % (
                it["action"], it["group"]["count"], ", ".join(it["group"]["values"][:4]))
        lines.append("%s · y %d · \"%s\"%s · 도구 확인: %s"
                     % (it["no"], it["box"][1], text,
                        " · aria \"%s\"" % it["aria"] if it.get("aria") else "",
                        action_text(it)))
    return "\n".join(lines)


def build_prompt(sheets):
    blocks = [sheet_block(sh) for sh in sheets]
    return (INTRO + "\n## 장\n\n" + "\n\n".join(blocks)
            + "\n\n## 그림 (장마다 한 장, 요소 번호를 얹었다)\n" + M.IMAGE_MARK + "\n")


def images_of(sheets, out_dir):
    return [{"label": "%s 와이어프레임" % sh["id"],
             "path": os.path.normpath(os.path.join(out_dir, sh["marked"]))}
            for sh in sheets if sh.get("marked") and sh["items"]]


# --------------------------------------------------------------------------- #
# 답 읽기 · 검사
# --------------------------------------------------------------------------- #
def parse_answer(text):
    """답 글에서 JSON 객체 하나. 코드 울타리를 벗긴다. 못 읽으면 None."""
    if not text:
        return None
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    body = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    try:
        data = json.loads(body)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def check(answer, sheets):
    """`[문제]`. 비면 맞는 답이다."""
    if answer is None:
        return ["답에서 JSON 을 읽지 못했다"]
    rows = answer.get("sheets")
    if not isinstance(rows, list):
        return ["맨 위에 sheets 목록이 없다"]
    problems = []
    got = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            problems.append("id 가 없는 장이 있다")
            continue
        if row["id"] in got:
            problems.append("%s 장을 두 번 적었다" % row["id"])
        got[row["id"]] = row
    known = {sh["id"] for sh in sheets}
    for sid in got:
        if sid not in known:
            problems.append("없는 장 %s 를 적었다" % sid)
    for sh in sheets:
        row = got.get(sh["id"])
        nos = [it["no"] for it in sh["items"]]
        if row is None:
            if nos:
                problems.append("%s 장이 없다" % sh["id"])
            continue
        regs = row.get("regions")
        if not isinstance(regs, list):
            problems.append("%s 의 regions 가 목록이 아니다" % sh["id"])
            continue
        seen = {}
        for i, reg in enumerate(regs):
            if not isinstance(reg, dict):
                problems.append("%s 의 영역 %d 가 객체가 아니다" % (sh["id"], i + 1))
                continue
            if not str(reg.get("name") or "").strip():
                problems.append("%s 의 영역 %s 에 이름이 없다" % (sh["id"], reg.get("no", i + 1)))
            els = reg.get("elements")
            if not isinstance(els, list):
                problems.append("%s 의 영역 %s 의 elements 가 목록이 아니다"
                                % (sh["id"], reg.get("no", i + 1)))
                continue
            for e in els:
                if e not in nos:
                    problems.append("%s 에 없는 요소 %s 를 썼다" % (sh["id"], e))
                elif e in seen:
                    problems.append("%s 의 %s 가 영역 %s 와 %s 에 둘 다 들어갔다"
                                    % (sh["id"], e, seen[e], reg.get("no", i + 1)))
                else:
                    seen[e] = reg.get("no", i + 1)
        left = [n for n in nos if n not in seen]
        if left:
            problems.append("%s 의 %s 가 어느 영역에도 없다" % (sh["id"], ", ".join(left)))
    return problems


def settle_regions(answer, sheets, source):
    """검사한 답을 장마다 영역으로. 맞지 않는 부분은 버리고 남은 요소는 "기타" 로.

    돌려주는 것: `({장 id: [영역]}, fallback)` - fallback 은 장마다 기타로 모은 요소와
    버린 것 (없으면 빈 dict)."""
    rows = {}
    for row in (answer or {}).get("sheets") or []:
        if isinstance(row, dict) and isinstance(row.get("id"), str) \
                and row["id"] not in rows:
            rows[row["id"]] = row
    out, fallback = {}, {}
    for sh in sheets:
        nos = [it["no"] for it in sh["items"]]
        boxes = {it["no"]: it["box"] for it in sh["items"]}
        taken, regs, dropped = set(), [], []
        for reg in (rows.get(sh["id"]) or {}).get("regions") or []:
            if not isinstance(reg, dict) or not isinstance(reg.get("elements"), list):
                dropped.append("모양이 틀린 영역")
                continue
            els = []
            for e in reg["elements"]:
                if e in nos and e not in taken:
                    els.append(e)
                    taken.add(e)
                else:
                    dropped.append(str(e))
            if not els:
                continue
            regs.append({"name": str(reg.get("name") or "").strip() or "이름 없음",
                         "description": str(reg.get("description") or "").strip(),
                         "elements": sorted(els, key=nos.index), "source": source,
                         "empty": reg.get("empty_state") is True})
        left = [n for n in nos if n not in taken]
        if left:
            regs.append({"name": OTHER_NAME, "description": OTHER_DESC, "elements": left,
                         "source": "tool_group"})
            fallback[sh["id"]] = {"other": left, "dropped": dropped}
        elif dropped:
            fallback[sh["id"]] = {"other": [], "dropped": dropped}
        # 번호는 위에서 아래 - 영역의 맨 위 요소 기준으로 다시 매긴다
        regs.sort(key=lambda r: min((boxes[e][1], boxes[e][0]) for e in r["elements"]))
        for i, r in enumerate(regs, 1):
            r["no"] = i
            r["box"] = _union([boxes[e] for e in r["elements"]])
        out[sh["id"]] = [dict({"no": r["no"], "name": r["name"],
                               "description": r["description"], "elements": r["elements"],
                               "box": r["box"], "source": r["source"]},
                              **({"empty": True} if r.get("empty") else {}))
                         for r in regs]
    return out, fallback


def titles_of(answer):
    """답에서 장마다 화면 이름 `{장 id: 이름}`. 없거나 글이 아니거나 길면 뺀다."""
    out = {}
    for row in (answer or {}).get("sheets") or []:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            continue
        name = row.get("name")
        if isinstance(name, str) and name.strip() and len(name.strip()) <= TITLE_CHARS \
                and row["id"] not in out:
            out[row["id"]] = " ".join(name.split())
    return out


def _union(boxes):
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[0] + b[2] for b in boxes)
    y1 = max(b[1] + b[3] for b in boxes)
    return [x0, y0, x1 - x0, y1 - y0]


# --------------------------------------------------------------------------- #
# mock - 정해진 답
# --------------------------------------------------------------------------- #
def mock_answer(sheets, mode=DEFAULT_MOCK, round_no=1):
    """요소를 위에서 아래로 보며, 앞 요소들의 아래 끝과 다음 요소의 위 끝 사이가
    MOCK_GAP 보다 벌어지면 새 영역을 연다. 이름은 "영역 n", 설명은 묶은 번호.

    bad 모드(와 bad-then-good 의 첫 답)는 장마다 마지막 요소를 빼고 없는 번호 e999 를
    넣는다 - 검사가 잡아야 한다."""
    rows = []
    for sh in sheets:
        items = sorted(sh["items"], key=lambda it: (it["box"][1], it["box"][0]))
        regs, cur, bottom = [], [], None
        for it in items:
            top = it["box"][1]
            if cur and top - bottom > MOCK_GAP:
                regs.append(cur)
                cur = []
            cur.append(it)
            bottom = max(bottom if cur[:-1] else top, top + it["box"][3])
        if cur:
            regs.append(cur)
        out = [{"no": i, "name": "영역 %d" % i,
                "elements": [it["no"] for it in reg],
                "description": "(mock) 요소 %s" % ", ".join(it["no"] for it in reg)}
               for i, reg in enumerate(regs, 1)]
        broken = mode == "bad" or (mode == "bad-then-good" and round_no == 1)
        if broken and out:
            last = out[-1]
            last["elements"] = last["elements"][:-1] + ["e999"]
        rows.append({"id": sh["id"], "regions": out})
    return {"sheets": rows}


# --------------------------------------------------------------------------- #
# 부르기
# --------------------------------------------------------------------------- #
def _write(out_dir, name, text):
    with io.open(os.path.join(out_dir, name), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _call(model, prompt, images, max_tokens, effort, log):
    r = M.call_model(model, prompt, max_tokens, log=log, reasoning_effort=effort,
                     images=images)
    price = M.price_for(model)
    return r, M.cost_usd(r.get("usage"), price)


def group(sheets, model=None, mock=None, out_dir=".", log=print, reasoning_effort=None):
    """장마다 영역을 정해 sheets 의 "regions" 에 넣고, 호출 기록을 돌려준다.

    기록: {"model", "mock", "calls": [{"phase", "images", "estimated_images",
    "max_tokens", "tokens", "cost_usd", "seconds", "finish_reason", "problems",
    "prompt", "response"}], "problems", "fallback", "cost_usd", "error"}"""
    todo = [sh for sh in sheets if sh["items"]]
    model = model or config.DEFAULT_MODEL
    rec = {"model": None if mock else model, "mock": mock or None, "calls": [],
           "problems": [], "fallback": {}, "cost_usd": None, "error": None,
           "reasoning_effort": None}
    if not todo:
        for sh in sheets:
            sh["regions"] = []
            sh["title"] = None
        return rec
    prompt = build_prompt(todo)
    images = images_of(todo, out_dir)
    _write(out_dir, PROMPT_FILE, M.prompt_record(prompt, images, model, base=out_dir))
    answer, problems = None, None
    if mock:
        for round_no, (pname, rname) in enumerate(
                [(PROMPT_FILE, RESPONSE_FILE), (RETRY_PROMPT_FILE, RETRY_RESPONSE_FILE)], 1):
            if round_no == 2:
                _write(out_dir, pname, retry_prompt(todo, text, problems))
            text = json.dumps(mock_answer(todo, mock, round_no), ensure_ascii=False, indent=1)
            _write(out_dir, rname, text)
            answer = parse_answer(text)
            problems = check(answer, todo)
            rec["calls"].append({"phase": "first" if round_no == 1 else "retry",
                                 "images": len(images) if round_no == 1 else 0,
                                 "tokens": None, "cost_usd": 0.0, "seconds": 0.0,
                                 "finish_reason": "mock", "problems": problems,
                                 "prompt": pname, "response": rname})
            log("영역 묶기 (mock %s) %s: 문제 %d건" % (mock, "첫 답" if round_no == 1
                                                     else "다시 물은 답", len(problems)))
            if not problems:
                break
        rec["cost_usd"] = 0.0
    else:
        profile = M.profile_for(model)
        effort = reasoning_effort or (config.DEFAULT_REASONING_EFFORT
                                      if profile["reasoning"] else None)
        rec["reasoning_effort"] = effort
        cap = MAX_TOKENS["reasoning" if profile["reasoning"] else "default"]
        M.load_env()
        total = 0.0
        text = ""
        for round_no in (1, 2):
            p = prompt if round_no == 1 else retry_prompt(todo, text, problems)
            imgs = images if round_no == 1 else []
            pname = PROMPT_FILE if round_no == 1 else RETRY_PROMPT_FILE
            rname = RESPONSE_FILE if round_no == 1 else RETRY_RESPONSE_FILE
            if round_no == 2:
                _write(out_dir, pname, p)
            est = M.describe_images(imgs, model)
            text_tokens, _how = M.estimate_tokens(M.model_text(p, imgs), model)
            log("영역 묶기 %s: %s 에 보낸다 (그림 %d장 · 그림 토큰 어림 %d · 글 토큰 어림 %d)"
                % ("첫 호출" if round_no == 1 else "다시 묻기", model, len(imgs),
                   est["estimated"], text_tokens))
            t0 = time.time()
            try:
                r, usd = _call(model, p, imgs, cap, effort, log)
            except M.ModelError as e:
                rec["error"] = "%s: %s" % (type(e).__name__, " ".join(str(e).split())[:300])
                log("영역 묶기: 모델을 부르지 못했다 - %s" % rec["error"])
                break
            text = r.get("text") or ""
            _write(out_dir, rname, text)
            answer = parse_answer(text)
            problems = check(answer, todo)
            total += usd or 0.0
            rec["calls"].append({"phase": "first" if round_no == 1 else "retry",
                                 "images": len(imgs), "estimated_images": est["estimated"],
                                 "estimated_text": text_tokens,
                                 "max_tokens": r.get("max_tokens"), "tokens": r.get("usage"),
                                 "cost_usd": usd, "seconds": r.get("seconds")
                                 if r.get("seconds") is not None else round(time.time() - t0, 1),
                                 "finish_reason": r.get("finish_reason"),
                                 "response_model": r.get("model"),
                                 "problems": problems, "prompt": pname, "response": rname})
            log("영역 묶기 %s: 토큰 %s · 예상 $%s · 문제 %d건"
                % ("첫 답" if round_no == 1 else "다시 물은 답", r.get("usage"),
                   "%.4f" % usd if usd is not None else "?", len(problems)))
            if not problems:
                break
        rec["cost_usd"] = round(total, 6) if rec["calls"] else None
    rec["problems"] = problems or []
    if rec["error"]:
        answer = None
    source = "mock" if mock else "model"
    settled, fallback = settle_regions(answer, todo, source)
    rec["fallback"] = fallback
    if fallback:
        log("영역 묶기: 어긋난 채 끝났다 - %s 의 남은 요소를 '%s' 로 묶었다"
            % (", ".join(sorted(fallback)), OTHER_NAME))
    titles = titles_of(answer)
    for sh in sheets:
        sh["regions"] = settled.get(sh["id"], [])
        sh["title"] = titles.get(sh["id"])
    return rec


def retry_prompt(sheets, previous, problems):
    return (RETRY_INTRO + "\n".join("- %s" % p for p in problems[:40])
            + ("\n- (외 %d건)" % (len(problems) - 40) if len(problems) > 40 else "")
            + "\n\n## 앞의 답\n" + (previous or "(없음)")
            + "\n\n## 장 (처음과 같다)\n\n" + "\n\n".join(sheet_block(sh) for sh in sheets)
            + "\n")
