r"""연구자가 직접 돌리는 확인 명령 둘. 돈이 거의 들지 않는다.

  python -m senior_ui.restructure --list-models
      이 키로 쓸 수 있는 모델 이름 (models.list - 요금 없음). gpt- 로 시작하는
      것만 이름 순서로 보이고, 도구가 그 모델을 어떻게 부를지(model.profile_for)를
      옆에 적는다.

  python -m senior_ui.restructure --probe <모델>
      아주 짧은 요청 하나(출력 PROBE_MAX_TOKENS 토큰)를 실제 실행과 **같은
      방식으로** 보낸다 (model.call_model). 응답 헤더의 분당 토큰 한도 · 요청
      한도, API 가 답한 실제 모델 이름, 지원하지 않는 인자 오류가 있었는지를
      보인다. 그런 오류가 나면 그 인자를 빼고 한 번 더 보낸다 - 400 은 요금이
      없으므로 요금이 드는 요청은 여전히 하나다.

둘 다 실행 폴더를 만들지 않는다. 결과는 화면과 outputs/model-probe.log 에 쓴다
(로그는 덧붙인다 - 날짜를 바꿔 다시 돌린 결과를 나란히 볼 수 있다).

종료 코드: 0 = 확인했다, 2 = 확인하지 못했다 (키 없음 · API 거절 · 연결 실패).
"""
import datetime
import io
import json
import os
import re

from senior_ui import config

from . import model as M

LOG_NAME = "model-probe.log"

# 짧게 답할 질문. 답의 내용은 보지 않는다 - 헤더와 응답 모델 이름이 목적이다.
PROBE_PROMPT = "Reply with exactly one word: OK"
# Responses API 의 max_output_tokens 는 16 이상이어야 한다. 추론형은 이 16 토큰을
# 생각에 다 쓰고 보이는 답 없이 잘려 올 수 있다 - 확인 명령에서는 그래도 된다.
PROBE_MAX_TOKENS = 16


class Out:
    """화면과 로그 파일에 같은 줄을 쓴다. 로그는 끝날 때 한 번에 덧붙인다."""

    def __init__(self, title):
        self.lines = []
        self.say("== %s (%s)" % (title, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    def say(self, line=""):
        print(line, flush=True)
        self.lines.append(line)

    def close(self):
        out = config.outputs_dir()
        os.makedirs(out, exist_ok=True)
        path = os.path.join(out, LOG_NAME)
        with io.open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(self.lines) + "\n\n")
        print("(기록: %s)" % path)


def _key_or_explain(out):
    """키를 지금처럼 읽는다 (.envs 또는 환경). 없으면 False."""
    try:
        M.load_env()
    except RuntimeError as e:
        out.say("확인하지 못했다: %s" % e)
        return False
    if not os.environ.get("OPENAI_API_KEY"):
        out.say("확인하지 못했다: OPENAI_API_KEY 가 환경에도 .envs 에도 없다")
        return False
    return True


def natural(name):
    """gpt-5.2 가 gpt-5.10 보다 앞에 오게 숫자를 숫자로 비교한다."""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", name)]


def list_models():
    out = Out("list-models")
    try:
        if not _key_or_explain(out):
            return 2
        from openai import OpenAI, OpenAIError
        try:
            ids = [m.id for m in OpenAI().models.list()]
        except OpenAIError as e:
            out.say("확인하지 못했다: %s: %s" % (type(e).__name__, e))
            return 2
        gpt = sorted((i for i in ids if i.startswith("gpt-")), key=natural)
        out.say("이 키로 쓸 수 있는 gpt- 모델 %d개 (도구가 부르는 방식):" % len(gpt))
        width = max([len(i) for i in gpt] + [10])
        for name in gpt:
            p = M.profile_for(name)
            how = ("%s · %s" % (p["api"], "추론형" if p["reasoning"] else "추론형 아님")
                   if p["known"] else "모름 → gpt-4o 처럼 부른다")
            out.say("  %-*s  %s" % (width, name, how))
        out.say("gpt- 로 시작하지 않는 %d개는 뺐다 (o3 · o4-mini 같은 o 계열 추론형도 "
                "여기 든다)." % (len(ids) - len(gpt)))
        return 0
    finally:
        out.close()


def probe(name, temperature=M.TEMPERATURE, seed=M.SEED, reasoning_effort=None,
          api=None):
    out = Out("probe %s" % name)
    try:
        if not _key_or_explain(out):
            return 2
        p = M.profile_for(name, api)
        out.say("도구가 부르는 방식: %s%s" % (
            M.describe(p), "" if p["known"] else
            " — 표에 없는 모델이라 gpt-4o 처럼 부른다 (model.FAMILIES)"))
        notes = []
        try:
            reply = M.call_model(name, PROBE_PROMPT, PROBE_MAX_TOKENS, log=notes.append,
                                 backoff=(), temperature=temperature, seed=seed,
                                 reasoning_effort=reasoning_effort, api=api)
        except M.ModelError as e:
            for n in notes:
                out.say("  " + n)
            out.say("확인하지 못했다 (%s): %s" % (type(e).__name__, e))
            return 2
        for n in notes:
            out.say("  " + n)
        out.say("보낸 인자: %s" % json.dumps(reply["sent"], ensure_ascii=False))
        if reply["dropped"]:
            out.say("지원하지 않는 인자 오류: 있음 — %s (빼고 다시 보냈다). 실제 실행도 "
                    "같은 인자를 빼고 보낸다. 표를 고칠 일인지 본다 (model.FAMILIES)"
                    % ", ".join(reply["dropped"]))
        else:
            out.say("지원하지 않는 인자 오류: 없음")
        out.say("실제 모델: %s" % reply["model"])
        out.say("분당 한도: %s" % M.describe_ratelimit(reply["ratelimit"]))
        usage = reply["usage"] or {}
        out.say("끝난 모양: %s · 출력 %s 토큰 (그중 생각 %s) · 답 %r"
                % (reply["finish_reason"], usage.get("completion"),
                   "-" if usage.get("reasoning") is None else usage["reasoning"],
                   reply["text"][:40]))
        if reply["finish_reason"] == "length" and p["reasoning"]:
            out.say("  (추론형은 출력 %d 토큰을 생각에 다 쓰고 잘릴 수 있다 - 확인 "
                    "명령에서는 정상이다)" % PROBE_MAX_TOKENS)
        return 0
    finally:
        out.close()
