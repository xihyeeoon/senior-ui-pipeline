r"""storyboard.json 하나로 설계서(index.html)를 그린다. 그림 말고는 다른 것을 읽지 않는다.

한 장 = 가로 A4. 차례:

  맨 앞장       과제 · 화면 순서 · 오류 경로 · 변경 목록 · 진단 요약 · 실행 정보
  와이어플로    모든 장을 작은 그림으로 늘어놓고 정답 경로를 번호 붙은 화살표로, 오류
                경로를 점선 갈래와 되돌아가는 화살표로, 펼치기를 점선으로 잇는다 (넘치면
                띠마다 장을 나눈다). 화살표는 흐름 명세의 걸음 · 오류 경로 · 펼치기에서만
                만든다.
  기능-화면 표  줄은 기능(과제 단계 · 선택지 무리 · 입력 수단 · 오류 회복 · 과제 밖 입구),
                칸은 화면. "기능은 줄이지 않는다" 의 확인표 (features.py)
  화면마다      맨 위에 정보칸 한 줄(화면 ID · 화면 이름 · 경로 · 원본 화면 · 조건), 왼쪽은
                와이어프레임 그림 위에 영역 테두리와 번호(굵게)와 요소 번호(가늘게), 오른쪽은
                화면 목적 · 영역 표 · 조건별 화면 링크. 조건별 화면은 그 화면 뒤에 같은
                모양으로 오고, 장 제목에 [오류] · [펼침] · [다시 지남] 꼬리표가 붙는다.
                예외는 영역 표에 - 꺼진 버튼은 "예외: 비활성" (도구 확인), 빈 상태 안내는
                영역 묶기 답이 표시한 것만 "예외: 빈 화면" (글자로 판정하지 않는다).

스크롤되는 화면은 그림이 길다. 한 장에 들도록 그림을 여러 단으로 잘라 나란히 놓는다
(layout - 가장 크게 보이는 단 수를 고른다). 영역 테두리는 단마다 잘려 그려지고 번호는
테두리가 시작하는 단에만 붙는다.

칸마다 출처를 붙인다: 동작은 "도구 확인"(도구가 실제로 눌러 본 결과), 영역 이름 · 설명은
"모델 설명" (mock 이면 "mock", 모델이 빠뜨려 도구가 모은 "기타" 는 "도구 묶음").
동작 칸은 실무 주석 꼴로 적는다 ("클릭 시 → [scr-amount] 이동").

PDF 는 이 페이지를 Chromium 으로 인쇄한 것이다 (print_pdf).
"""
import asyncio
import html as _html
import math
import re

from .features import DIRECT, ORIGINAL_FROM, REVEALED, SECTION_LABEL, SECTIONS

# 가로 A4 (297 x 210mm) - 여백 8mm. CSS 픽셀(1/96 인치)로 쓴 그림 칸.
# 그림 칸의 높이는 장 맨 위의 정보칸 만큼 줄였다.
PIC_W, PIC_H = 560, 620
SLICE_GAP = 10
MAX_SLICES = 6

SOURCE_LABEL = {"tool": "도구 확인", "model": "모델 설명", "mock": "mock",
                "tool_group": "도구 묶음"}
TAG = {"error": "오류", "reveal": "펼침", "visit": "다시 지남"}


def esc(s):
    return _html.escape("" if s is None else str(s), quote=True)


def layout(w, h, area_w=PIC_W, area_h=PIC_H, gap=SLICE_GAP, kmax=MAX_SLICES):
    """그림(w x h, CSS 픽셀)을 몇 단으로 자를지. `(단 수, 배율, 한 단의 높이)`.
    배율은 1 을 넘지 않는다."""
    best = None
    for k in range(1, kmax + 1):
        sh = int(math.ceil(h / float(k)))
        s = min(1.0, (area_w - (k - 1) * gap) / float(k * w), area_h / float(sh))
        if best is None or s > best[1] + 1e-9:
            best = (k, s, sh)
    return best


def markdown_bold(s):
    """과제 글의 **굵게** 를 <b> 로 (과제 파일은 프롬프트용 마크다운이다)."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s, flags=re.S)


def item_label(it):
    if it["kind"] == "group":
        vals = it["group"]["values"]
        return "%s 무리 %d개 (%s%s)" % (it["action"], it["group"]["count"],
                                      " · ".join(vals[:3]), " …" if len(vals) > 3 else "")
    t = it.get("text") or it.get("aria") or it["action"]
    return "'%s'" % t


def sheet_tag(sh):
    """장 제목의 꼬리표 - 오류 · 펼침 · 다시 지남. 본 장(정답 경로)은 없다."""
    if sh.get("kind") == "visit":
        return None if sh.get("main") else TAG["visit"]
    return TAG.get(sh.get("kind"))


# --------------------------------------------------------------------------- #
# 동작 칸 - 실무 주석 꼴
# --------------------------------------------------------------------------- #
# 같은 화면에서 바뀐 것(walk.describe_change 의 detail)을 주석 꼴로. detail 은 " · " 로
# 이은 조각들이다 - 조각마다 머리말이 정해져 있다.
SAME_PREFIX = (("새로 보임: ", "같은 화면에서 %s 나타남"),
               ("사라짐: ", "같은 화면에서 %s 사라짐"),
               ("입력 칸 값이 바뀜: ", "입력 칸에 %s"),
               ("알림창 ", "알림창 %s 뜸"))
SAME_FIXED = {"입력 칸 값이 바뀜": "입력 칸 값이 바뀜",
              "보이는 글의 순서가 바뀜": "같은 화면에서 글의 순서가 바뀜",
              "표시 상태가 바뀜 (보이는 글은 그대로)": "같은 화면에서 표시 상태가 바뀜 (글은 그대로)",
              "스크롤 위치가 바뀜": "같은 화면에서 스크롤 위치가 바뀜"}


def _split_parts(detail):
    """detail 을 " · " 로 나눈다 - 따옴표 안의 " · " 는 나누지 않는다."""
    parts, cur, quoted, i = [], [], False, 0
    while i < len(detail):
        if detail[i] == "'":
            quoted = not quoted
        if not quoted and detail.startswith(" · ", i):
            parts.append("".join(cur))
            cur, i = [], i + 3
            continue
        cur.append(detail[i])
        i += 1
    parts.append("".join(cur))
    return [p for p in parts if p]


def same_phrase(detail):
    out = []
    for part in _split_parts(detail or ""):
        if part in SAME_FIXED:
            out.append(SAME_FIXED[part])
            continue
        for head, form in SAME_PREFIX:
            if part.startswith(head):
                out.append(form % part[len(head):])
                break
        else:
            out.append("같은 화면에서 바뀜 — %s" % part)
    return " · ".join(out) or "같은 화면에서 바뀜"


def result_text(it, link=True, sheet_ids=None):
    """항목의 동작 - 도구가 눌러 본 결과를 실무 주석 꼴로.

      클릭 시 → [scr-amount] 이동
      클릭 시 → 같은 화면에서 '…' 나타남
      클릭해도 변화 없음
      비활성 (이 상태에서는 누를 수 없음)
      38개 중 하나 선택 → [scr-account] 이동 (눌러 본 대표: '경남')
    """
    e = esc if link else (lambda x: "" if x is None else str(x))
    r = it.get("result") or {}
    kind = r.get("kind")
    effect = None
    if kind == "screen":
        to = r.get("to_id") or "scr-%s" % r.get("to")
        ref = ('<a href="#%s">[%s]</a>' % (esc(to), esc(to))
               if link and (sheet_ids is None or to in sheet_ids)
               else "[%s]" % (esc(to) if link else to))
        effect = "%s 이동" % ref
    elif kind == "same":
        effect = e(same_phrase(r.get("detail")))
    elif kind == "none":
        effect = "변화 없음"
    elif kind == "left":
        effect = "페이지를 떠남 — %s" % e(r.get("detail"))
    unsure = "확인 못 함 — %s" % e(r.get("detail") or "결과 없음")
    if it["kind"] == "group":
        n = it["group"]["count"]
        if kind == "disabled":
            text = "%d개 모두 비활성 (이 상태에서는 누를 수 없음)" % n
        else:
            text = "%d개 중 하나 선택 → %s (눌러 본 대표: '%s')" % (
                n, effect or unsure, e(it.get("value")))
    elif kind == "disabled":
        text = "비활성 (이 상태에서는 누를 수 없음)"
    elif kind == "none":
        text = "클릭해도 변화 없음"
    else:
        text = "클릭 시 → %s" % effect if effect else unsure
    if it.get("entrance"):
        text += " · 과제 밖 입구"
    if r.get("js_errors"):
        text += " · 자바스크립트 오류 %d건" % len(r["js_errors"])
    return text


# --------------------------------------------------------------------------- #
CSS = r"""
@page { size: A4 landscape; margin: 8mm; }
:root { --ink:#1f1f1f; --muted:#666; --line:#cfcfcf; --reg:#d9480f; --el:#1864ab;
        --soft:#f4f4f2; --err:#c92a2a; }
* { box-sizing: border-box; }
html, body { margin: 0; background: #e9e9e6; color: var(--ink);
  font: 11px/1.45 "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans KR", sans-serif; }
.sheet { width: 281mm; min-height: 194mm; margin: 10mm auto; padding: 0; background: #fff;
  box-shadow: 0 1px 4px rgba(0,0,0,.18); position: relative; }
.sheet.screen { display: grid; grid-template-columns: 560px 1fr; grid-template-rows: auto 1fr;
  column-gap: 16px; padding: 0; }
.sheet.cover { padding: 6mm 8mm; }
.sheet.flowmap { height: 194mm; overflow: hidden; }
@media print {
  html, body { background: #fff; }
  .sheet { margin: 0; box-shadow: none; page-break-after: always; break-after: page; }
  a { color: inherit; text-decoration: none; }
}
h1 { font-size: 20px; margin: 0 0 2px; }
h2 { font-size: 13px; margin: 14px 0 6px; padding-bottom: 3px; border-bottom: 1.5px solid var(--ink); }
.sub { color: var(--muted); margin-bottom: 8px; }
.lead { margin: 4px 0 4px; font-weight: 600; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid var(--line); padding: 3px 5px; vertical-align: top; text-align: left; }
th { background: var(--soft); font-weight: 600; white-space: nowrap; }
.kv th { width: 120px; }
.mono { font-family: Consolas, "D2Coding", monospace; font-size: 10px; }
.src { display: inline-block; font-size: 9px; font-weight: 600; padding: 0 4px; border-radius: 3px;
  border: 1px solid currentColor; margin-left: 4px; white-space: nowrap; vertical-align: 1px; }
.src.tool { color: #1864ab; } .src.model { color: #862e9c; } .src.mock { color: #5c5f66; }
.src.tool_group { color: #a61e4d; }
.tag { display: inline-block; font: 700 10px/1.3 sans-serif; padding: 0 4px; margin-left: 4px;
  border: 1px solid currentColor; border-radius: 2px; vertical-align: 2px; white-space: nowrap; }
.tag.error { color: var(--err); } .tag.reveal { color: #5f3dc4; } .tag.visit { color: #495057; }
.ex { display: inline-block; font-size: 9px; font-weight: 700; padding: 0 3px; margin-right: 3px;
  background: #fff4e6; color: #a6420e; border: 1px solid #f0b37e; white-space: nowrap; }
.flow { margin: 0; padding-left: 18px; }
.flow li { margin: 2px 0; }
.how { color: var(--muted); }
.info { grid-column: 1 / -1; margin: 0; width: 100%; }
.info th { font-size: 9.5px; padding: 2px 5px; }
.info td { font-size: 10.5px; padding: 3px 5px; }
.info .sid { font: 700 14px/1.25 Consolas, monospace; white-space: nowrap; }
.info .path a { color: inherit; }
.info .path b { font-weight: 700; }
.src.plain { color: var(--muted); font-weight: 400; }
.pic { padding: 6px 0 0 8px; }
.slices { display: flex; gap: 10px; align-items: flex-start; }
.slice { position: relative; overflow: hidden; outline: 1px solid #bbb; background: #fff; }
.slice img { position: absolute; left: 0; display: block; }
.reg { position: absolute; border: 2px solid var(--reg); }
.reg .badge { position: absolute; left: -2px; top: -2px; background: var(--reg); color: #fff;
  font: 700 11px/15px sans-serif; min-width: 15px; text-align: center; padding: 0 3px; }
.el { position: absolute; border: 1px dashed var(--el); }
.el span { position: absolute; right: 0; top: 0; background: rgba(255,255,255,.85); color: var(--el);
  font: 600 7px/8px sans-serif; padding: 0 1px; }
.pic-note { color: var(--muted); font-size: 9.5px; margin-top: 4px; }
.spec { padding: 6px 8px 8px 0; }
.purpose { margin: 0 0 6px; }
.cond { background: #fff4e6; border-left: 3px solid var(--reg); padding: 3px 6px; margin: 4px 0 6px; }
.regs td.no { width: 26px; text-align: center; font-weight: 700; color: var(--reg); }
.regs td.nm { width: 34%; }
.regs .nm b { display: block; }
.regs .desc { color: #333; }
.regs ul { margin: 0; padding-left: 0; list-style: none; }
.regs li { margin: 1px 0; }
.regs li .e { font-weight: 700; color: var(--el); margin-right: 3px; }
.conds { margin-top: 8px; }
.conds li { margin: 2px 0; }
.legend td, .legend th { font-size: 10.5px; }
.warn { color: #a61e4d; }
/* 와이어플로 */
.fm-head { position: absolute; left: 12px; right: 12px; top: 8px; }
.fm-head h1 { font-size: 16px; }
.fm-head .sub { margin: 0; font-size: 9.5px; }
.fm-key { display: inline-flex; align-items: center; gap: 3px; margin-right: 10px; }
.node { position: absolute; display: block; color: inherit; text-decoration: none; }
.node .nt { height: 28px; overflow: hidden; font: 600 9px/1.25 sans-serif; display: flex;
  align-items: flex-end; gap: 3px; padding-bottom: 2px; }
.node .nt span.nm { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden; }
.node .num { flex: none; display: inline-block; min-width: 15px; height: 15px; border-radius: 8px;
  background: var(--ink); color: #fff; font: 700 9px/15px sans-serif; text-align: center; }
.node .tag { margin: 0; flex: none; }
.node .thumb { position: relative; overflow: hidden; outline: 1px solid #999; background: #fff; }
.node .thumb img { position: absolute; left: 0; top: 0; display: block; }
.node .thumb .more { position: absolute; left: 0; right: 0; bottom: 0; font: 7px/10px sans-serif;
  text-align: center; background: rgba(255,255,255,.9); color: var(--muted); }
.node .nc { font: 7.5px/13px Consolas, monospace; color: var(--muted); white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; }
.node.branch .thumb { outline-style: dashed; }
.node.error .thumb { outline-color: var(--err); }
.edge-label { position: absolute; font: 7.5px/9px sans-serif; color: #333; overflow: hidden;
  background: rgba(255,255,255,.88); }
/* 기능-화면 표 */
.fm { table-layout: fixed; }
.fm th, .fm td { padding: 2px 4px; font-size: 9.5px; }
.fm th.f { width: 300px; } .fm th.o { width: 120px; }
.fm th.v { height: 92px; vertical-align: bottom; text-align: center; padding: 3px 0; }
.fm th.v div { writing-mode: vertical-rl; transform: rotate(180deg); margin: 0 auto;
  font: 600 9px Consolas, monospace; white-space: nowrap; }
.fm th.v a { color: inherit; }
.fm td.m { text-align: center; font-size: 11px; }
.fm td.m small { font-size: 7.5px; color: var(--muted); }
.fm tr.sec td { background: var(--soft); font-weight: 700; }
.fm tr.sec td .how { font-weight: 400; }
.fm tr.miss td.f { color: #a61e4d; }
.edge-label.c { text-align: center; }
.edge-label.b { display: flex; flex-direction: column; justify-content: flex-end; }
.edge-label.r { text-align: right; }
.edge-label.err { color: var(--err); }
.edge-label.rev { color: #5f3dc4; }
.flowsvg { position: absolute; left: 0; top: 0; overflow: visible; }
.badge-n { font: 700 8px sans-serif; fill: #fff; }
"""


def _src(source):
    key = source if source in SOURCE_LABEL else "tool"
    return '<span class="src %s">%s</span>' % (key, SOURCE_LABEL[key])


def _tag(sh, short=False):
    """장 제목의 꼬리표. short 는 와이어플로의 작은 그림 위 - [다시 지남] 을 [다시] 로."""
    t = sheet_tag(sh)
    if t and short:
        t = t.split()[0]
    return ('<span class="tag %s">[%s]</span>' % (esc(sh["kind"]), esc(t))) if t else ""


def _how_text(a):
    if a.get("type") == "type":
        return "%s 입력" % a.get("value")
    if a.get("item"):
        return "%s '%s'%s" % (a["item"], a.get("text"),
                              " ×%d" % a["repeat"] if a.get("repeat") else "")
    return "%s 누름" % a.get("selector")


def _how(how, flow_sheet_ids):
    parts = []
    for a in how or []:
        if a.get("type") == "type":
            parts.append("%s 입력" % esc(a.get("value")))
        elif a.get("item"):
            parts.append("%s '%s' 누름%s" % (esc(a["item"]), esc(a.get("text")),
                                           " ×%d" % a["repeat"] if a.get("repeat") else ""))
        else:
            parts.append("<span class=\"mono\">%s</span> 누름" % esc(a.get("selector")))
    return " → ".join(parts)


def short_how(how, keep=2, chars=16):
    """화살표 옆에 적는 누른 것 - 조작이 많으면 처음과 끝만, 조각마다 chars 자에서 자른다."""
    parts = [_clip(_how_text(a), chars) for a in how or []]
    if len(parts) > keep:
        parts = parts[:1] + ["…"] + parts[-(keep - 1):]
    return " → ".join(parts)


def _clip(s, n):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n - 1] + "…"


def _link(sid, ids):
    if not sid:
        return "-"
    return '<a href="#%s">[%s]</a>' % (esc(sid), esc(sid)) if sid in ids else "[%s]" % esc(sid)


def render_cover(data, ids):
    run, task = data["run"], data["task"]
    orig = run.get("original") or {}
    call = data.get("regions_call") or {}
    gen = data.get("generated") or {}
    out = ['<section class="sheet cover" id="cover">',
           "<h1>화면설계서 · %s</h1>" % esc(task.get("label")),
           '<div class="sub">실행 <span class="mono">%s</span> · 최종 %s (시도 %s) · '
           "검사를 통과한 HTML 에서 뽑았다. 색 · 모양은 디자이너의 몫이라 그림은 로우파이 "
           "와이어프레임(회색 상자와 글자)이다. 다음 장이 와이어플로, 그다음이 기능-화면 "
           "표다.</div>" % (esc(run.get("id")), esc(run.get("final_label")),
                                     esc(run.get("final_attempt")))]
    out.append("<h2>과제</h2><p>%s</p>"
               % markdown_bold(esc(task.get("description"))).replace("\n", " "))

    out.append("<h2>화면 순서 (흐름 명세의 정답 경로)</h2><ol class=\"flow\">")
    sheets = {s["id"]: s for s in data["sheets"]}
    for st in data["flow"]["steps"]:
        sh = sheets.get(st.get("sheet")) or {}
        how = _how(st.get("how"), ids)
        out.append("<li>%s %s%s</li>" % (
            _link(st.get("sheet"), ids), esc(sh.get("name") or sh.get("purpose") or ""),
            ' <span class="how">← 앞 화면에서 %s</span>' % how if how else ""))
    out.append("</ol>")
    if data["flow"]["errors"]:
        out.append("<h2>오류 경로 (흐름 명세 error_paths · 과제의 오류 조건)</h2><table>"
                   "<tr><th>오류</th><th>조건 (과제)</th><th>어디서 무엇을 넣으면</th>"
                   "<th>나오는 화면</th><th>되돌아가기</th></tr>")
        for e in data["flow"]["errors"]:
            out.append("<tr><td class=\"mono\">%s</td><td>%s</td><td>%s 에서 %s</td>"
                       "<td>%s</td><td>%s → %s</td></tr>" % (
                           esc(e["id"]), esc(e.get("about") or e.get("condition")),
                           _link(e.get("from_sheet"), ids), _how(e.get("inputs"), ids),
                           _link(e.get("sheet"), ids), _how(e.get("recover"), ids),
                           _link(e.get("back_to_sheet"), ids)))
        out.append("</table>")
    if data["flow"]["reveals"]:
        out.append("<h2>펼치기 (흐름 명세 reveal)</h2><ul>")
        for r in data["flow"]["reveals"]:
            out.append("<li><span class=\"mono\">%s</span>: %s 에서 %s → %s</li>" % (
                esc(r["action"]), _link(r.get("at_sheet"), ids), _how(r.get("how"), ids),
                _link(r.get("sheet"), ids)))
        out.append("</ul>")

    out.append("<h2>계획의 변경 목록</h2>")
    if data["changes"]:
        out.append("<table><tr><th>#</th><th>무엇을</th><th>왜</th><th>대응 진단</th></tr>")
        for c in data["changes"]:
            diag = "<br>".join("<b>%s</b> %s" % (esc(a["id"]), esc(a.get("problem") or ""))
                               for a in c["addresses"]) or "-"
            out.append("<tr><td class=\"mono\">%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
                       % (esc(c["id"]), esc(c["what"]), esc(c["why"]), diag))
        out.append("</table>")
    else:
        out.append("<p>계획이 없다.</p>")

    d = data["diagnosis"]
    out.append("<h2>진단 요약</h2><p>진단 %d건 · 근거: %s · 화면별: %s</p>" % (
        d["count"],
        " · ".join("%s %d" % (esc(k), v) for k, v in sorted(d["evidence_kinds"].items())) or "-",
        " · ".join("%s %d" % (esc(k), v) for k, v in d["by_screen"].items()) or "-"))
    if d["items"]:
        out.append("<table><tr><th>#</th><th>화면</th><th>요소</th><th>문제</th></tr>")
        for x in d["items"]:
            out.append("<tr><td class=\"mono\">%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
                       % (esc(x["id"]), esc(x["screen"]), esc(x["element"]),
                          esc(x["problem"])))
        out.append("</table>")

    out.append("<h2>실행 정보</h2><table class=\"kv\">")
    reused = call.get("reused")
    if reused:
        regions_row = ("저장된 영역 답을 다시 씀 - <span class=\"mono\">%s</span> (그때 %s · "
                       "실행 %s · %s · 그때 비용 %s) · 이번에는 모델을 부르지 않음" % (
                           esc(reused.get("path")),
                           "mock (%s)" % esc(call.get("mock")) if call.get("mock")
                           else esc(call.get("model")),
                           esc(reused.get("run")), esc(reused.get("at")),
                           "$%.4f" % reused["cost_usd"] if reused.get("cost_usd") is not None
                           else "-"))
    else:
        regions_row = "%s%s · 비용 %s%s" % (
            "mock (%s)" % esc(call.get("mock")) if call.get("mock") else esc(call.get("model")),
            " · reasoning_effort %s" % esc(call["reasoning_effort"])
            if call.get("reasoning_effort") else "",
            "$%.4f" % call["cost_usd"] if call.get("cost_usd") is not None else "-",
            ' · <span class="warn">%s</span>' % esc(call["error"]) if call.get("error") else
            (' · <span class="warn">어긋나 "기타" 로 묶은 장 %d</span>' % len(call["fallback"])
             if call.get("fallback") else ""))
    rows = [
        ("실행 id", '<span class="mono">%s</span>' % esc(run.get("id"))),
        ("과제", "%s (%s)" % (esc(task.get("label")), esc(task.get("id")))),
        ("생성 모델", "%s%s" % (esc(run.get("model")),
                             " · mock %s" % esc(run["mock"]) if run.get("mock") else "")),
        ("최종 빌드", "%s · 시도 %s · 검사 단계 %s" % (esc(run.get("final_label")),
                                                esc(run.get("final_attempt")),
                                                esc(run.get("stage")))),
        ("원본 지문", '<span class="mono">%s</span> sha256 <span class="mono">%s</span> (%s)'
         % (esc(orig.get("path")), esc((orig.get("sha256") or "")[:16]),
            "실행 커밋의 파일" + ("" if orig.get("same_as_now") else
                             " - <span class=\"warn\">지금 파일과 다르다</span>")
            if orig.get("source") == "commit" else "지금 파일")),
        ("커밋", '<span class="mono">%s</span>%s' % (
            esc((run.get("commit") or "")[:12]),
            ' <span class="warn">(커밋하지 않은 수정이 있었다)</span>' if run.get("dirty")
            else "")),
        ("생성 비용", "$%.4f" % run["cost_usd"] if run.get("cost_usd") is not None else "-"),
        ("영역 묶기", regions_row),
        ("원본 걷기", "%s - 걸음 %d%s" % (
            esc((data.get("original") or {}).get("html")),
            len((data.get("original") or {}).get("steps") or []),
            ' · <span class="warn">%s</span>' % esc(data["original"]["error"])
            if (data.get("original") or {}).get("error") else " (끝까지)")),
        ("설계서", "장 %d (화면 %d) · 항목 %d · 누르기 %d번 · 그림 %s초 · 누르기 %s초 · %s"
         % (data["counts"]["sheets"], data["counts"]["main_sheets"], data["counts"]["items"],
            data["counts"]["clicks"], esc((gen.get("seconds") or {}).get("pictures")),
            esc((gen.get("seconds") or {}).get("clicks")), esc(gen.get("at")))),
    ]
    out += ["<tr><th>%s</th><td>%s</td></tr>" % r for r in rows]
    out.append("</table>")

    out.append("<h2>칸마다 어디서 왔나</h2><table class=\"legend\">"
               "<tr><th>칸</th><th>출처</th><th>어떻게</th></tr>"
               "<tr><td>그림</td><td>%(tool)s</td><td>최종 HTML 의 로우파이 덮개 사본을 흐름 "
               "명세대로 걸어 찍었다 (위치 · 크기 · 글자 크기 · 굵기는 그대로)</td></tr>"
               "<tr><td>요소 번호 · 글자 · 위치</td><td>%(tool)s</td><td>그 상태에서 보이는 "
               "data-action 요소를 모았다</td></tr>"
               "<tr><td>동작 (클릭 시 → …)</td><td>%(tool)s</td><td>요소마다 새 페이지에서 그 "
               "상태까지 다시 걸은 뒤 눌러 보았다. 선택지 무리는 대표 하나</td></tr>"
               "<tr><td>예외: 비활성</td><td>%(tool)s</td><td>눌러 보려 했을 때 꺼져 있던 "
               "요소</td></tr>"
               "<tr><td>영역 이름 · 설명 · 화면 이름 · 예외: 빈 화면</td><td>%(model)s "
               "%(mock)s %(group)s</td><td>모델이 그림과 요소 목록으로 묶었다 (mock 은 정해진 "
               "답, 모델이 빠뜨린 요소는 도구가 \"기타\" 로). 화면 이름이 없으면 계획의 화면 "
               "목적 앞부분. 빈 화면은 모델이 표시한 것만 (글자로 판정하지 않는다)</td></tr>"
               "<tr><td>와이어플로의 화살표 · 경로</td><td>흐름 명세 · %(tool)s</td><td>정답 "
               "경로의 걸음 · 오류 경로 · 펼치기만. 이어지는 장은 도구가 그 상태까지 걸어 "
               "확인한 화면</td></tr>"
               "<tr><td>기능-화면 표의 표시</td><td>%(tool)s</td><td>장마다 보인 data-action "
               "요소와 흐름 명세의 걸음 · 오류 경로. 원본 화면 칸은 줄마다 출처가 다르다 (그 "
               "장에 적었다)</td></tr>"
               "<tr><td>화면 목적 · 원본 화면 · 변경 · 진단</td><td>계획 · 진단 (모델)</td>"
               "<td>재구성 실행의 계획 파일을 그대로 옮겼다</td></tr>"
               "<tr><td>조건</td><td>흐름 명세 · 과제</td><td>error_paths · reveal · 과제의 "
               "오류 조건</td></tr></table>" % {
                   "tool": _src("tool"), "model": _src("model"), "mock": _src("mock"),
                   "group": _src("tool_group")})

    out.append("<h2>장 목록</h2><ul class=\"flow\">")
    for s in data["sheets"]:
        out.append("<li>%s%s %s — %s</li>" % (
            _link(s["id"], ids), _tag(s), esc(s.get("name") or ""),
            esc(s["condition"]) if s.get("condition") else esc(s.get("purpose") or "")))
    out.append("</ul></section>")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# 와이어플로
# --------------------------------------------------------------------------- #
# 가로 A4 한 장의 CSS 픽셀 (281 x 194mm). 장 안에 그 크기의 캔버스를 두고 그림 · 화살표를
# 절대 위치로 놓는다.
FLOW_W, FLOW_H = 1062, 733
FLOW_PAD = 12
FLOW_TOP = 84                   # 제목 · 설명 · 범례
FLOW_COLS = 8                   # 한 줄의 걸음 수 (넘으면 다음 줄로 - 띠)
FLOW_MIN_GAP = 44               # 그림 사이 (화살표 · 누른 것)
FLOW_MAX_GAP = 90
FLOW_VGAP = 66                  # 걸음 줄과 갈래 줄 사이 (오류 · 되돌아가기 · 펼침 글)
FLOW_LANE_GAP = 16              # 갈래 줄이 둘 이상일 때 그 사이
FLOW_BGAP = 34                  # 띠 사이 (다음 줄로 이어지는 화살표)
NODE_TITLE, NODE_CAP = 28, 13
THUMB_MAX_W = 132
THUMB_MIN_W = 60                # 이보다 작아지면 띠마다 장을 나눈다
PHONE_RATIO = 844 / 390.0       # 작은 그림은 폰 화면 한 개 비율로 위쪽만 보인다
ERR, REV, INK = "#c92a2a", "#5f3dc4", "#333"


def flow_graph(data):
    """와이어플로의 마디와 잇기 - 흐름 명세(data["flow"])에서만.

    마디: 걸음(정답 경로의 방문마다 그 장) · 갈래(오류 장 · 펼친 뒤 장).
    잇기: step (걸음 i → i+1) · error (그 걸음의 장 → 오류 장) · return (오류 장 →
    되돌아가는 장) · reveal (그 걸음의 장 → 펼친 뒤 장)."""
    ids = {s["id"] for s in data["sheets"]}
    flow = data["flow"]
    steps = [st for st in flow.get("steps") or [] if st.get("sheet") in ids]
    branches = []
    for e in flow.get("errors") or []:
        if e.get("sheet") in ids:
            branches.append({"kind": "error", "sheet": e["sheet"], "from": e.get("from_sheet"),
                             "how": e.get("inputs") or [], "id": e["id"],
                             "back": e.get("back_to_sheet"), "recover": e.get("recover") or []})
    for r in flow.get("reveals") or []:
        if r.get("sheet") in ids:
            branches.append({"kind": "reveal", "sheet": r["sheet"], "from": r.get("at_sheet"),
                             "how": r.get("how") or [], "id": r["action"]})
    return steps, branches


def _bands(steps, branches, cols):
    """걸음을 cols 개씩 띠로 나누고, 갈래를 그 출발 걸음의 띠 아래 갈래 줄에 놓는다.
    `[{"steps": [(칸, 걸음)], "lanes": [[(칸, 갈래)]]}]`."""
    pos = {}
    for i, st in enumerate(steps):
        pos.setdefault(st["sheet"], i)
    bands = [{"steps": [(j, st) for j, st in enumerate(steps[i:i + cols])], "lanes": []}
             for i in range(0, max(len(steps), 1), cols)]
    order = sorted(range(len(branches)), key=lambda k: (pos.get(branches[k]["from"], 10 ** 6), k))
    for k in order:
        br = branches[k]
        p = pos.get(br["from"])
        b, c = divmod(p, cols) if p is not None else (len(bands) - 1, 0)
        lanes = bands[b]["lanes"]
        for lane in lanes:
            slot = max(c, lane[-1][0] + 1)
            if slot < cols:
                lane.append((slot, br))
                break
        else:
            lanes.append([(min(c, cols - 1), br)])
    return bands


def _band_height(band, h):
    rows = 1 + len(band["lanes"])
    node = NODE_TITLE + h + NODE_CAP
    gaps = (FLOW_VGAP + FLOW_LANE_GAP * (len(band["lanes"]) - 1)) if band["lanes"] else 0
    return rows * node + gaps


def flow_pages(data):
    """띠들을 장으로 나누고 그림 크기를 정한다. `[(띠들, 그림 폭)]`."""
    steps, branches = flow_graph(data)
    cols = max(1, min(len(steps), FLOW_COLS))
    bands = _bands(steps, branches, cols)
    width = FLOW_W - 2 * FLOW_PAD
    room = FLOW_H - FLOW_TOP - FLOW_PAD
    w_cols = min(THUMB_MAX_W, (width - (cols - 1) * FLOW_MIN_GAP) / float(cols))

    def fit(group):
        rows = sum(1 + len(b["lanes"]) for b in group)
        fixed = sum(_band_height(b, 0) for b in group) + FLOW_BGAP * (len(group) - 1)
        h = (room - fixed) / float(rows)
        return min(w_cols, h / PHONE_RATIO)

    w = fit(bands)
    if w >= THUMB_MIN_W or len(bands) == 1:
        return cols, [(bands, w)]
    return cols, [([b], fit([b])) for b in bands]


def _thumb(sh, w, h):
    box = '<div class="thumb" style="width:%.1fpx;height:%.1fpx">%%s</div>' % (w, h)
    if not sh.get("picture") or not sh.get("size"):
        return box % '<span class="more">그림 없음</span>'
    more = ('<span class="more">↓ 길이 %dpx</span>' % sh["size"][1]
            if sh["size"][1] > 844 * 1.02 else "")
    return box % ('<img src="%s" alt="" style="width:%.1fpx">%s'
                  % (esc(sh["picture"]), w, more))


def _node(sh, x, y, w, h, title, cls=""):
    return ('<a class="node %s" href="#%s" style="left:%.1fpx;top:%.1fpx;width:%.1fpx">'
            '<div class="nt">%s</div>%s<div class="nc">%s</div></a>'
            % (cls, esc(sh["id"]), x, y, w, title, _thumb(sh, w, h), esc(sh["id"])))


def _label(x, y, w, hgt, text, cls=""):
    """화살표 옆 글. 칸(cls 의 b)이 있으면 그 높이의 아래쪽에 붙인다."""
    return ('<div class="edge-label %s" style="left:%.1fpx;top:%.1fpx;width:%.1fpx;'
            '%s:%.1fpx">%s</div>' % (cls, x, y, max(w, 10),
                                      "height" if "b" in cls.split() else "max-height",
                                      max(hgt, 9), text))


def _badge(x, y, n):
    return ('<circle cx="%.1f" cy="%.1f" r="7" fill="%s"/><text x="%.1f" y="%.1f" '
            'class="badge-n" text-anchor="middle">%d</text>' % (x, y, INK, x, y + 3, n))


def _path(d, color, dash=None, head=True):
    return ('<path d="%s" fill="none" stroke="%s" stroke-width="1.3"%s%s/>'
            % (d, color, ' stroke-dasharray="%s"' % dash if dash else "",
               ' marker-end="url(#ah-%s)"' % color.lstrip("#") if head else ""))


def render_flow_page(data, bands, cols, w, page_no, pages, by_id):
    h = w * PHONE_RATIO
    width = FLOW_W - 2 * FLOW_PAD
    gap = min(FLOW_MAX_GAP, (width - cols * w) / float(cols - 1)) if cols > 1 else 0
    x0 = FLOW_PAD + (width - (cols * w + (cols - 1) * gap)) / 2.0
    colx = lambda c: x0 + c * (w + gap)
    html, svg = [], []
    where = {}                                  # 장 id → (띠 번호, 칸, 마디 위)
    y = FLOW_TOP
    tops = []
    for bi, band in enumerate(bands):
        tops.append(y)
        for c, st in band["steps"]:
            where.setdefault(st["sheet"], (bi, c, y))
        y += NODE_TITLE + h + NODE_CAP
        if band["lanes"]:
            y += FLOW_VGAP
            for li, lane in enumerate(band["lanes"]):
                for c, br in lane:
                    where.setdefault(br["sheet"], (bi, c, y))
                y += NODE_TITLE + h + NODE_CAP + (FLOW_LANE_GAP if li < len(band["lanes"]) - 1
                                                  else 0)
        y += FLOW_BGAP

    steps, _ = flow_graph(data)
    first_step = bands[0]["steps"][0][1]["step"] if bands and bands[0]["steps"] else None
    for band in bands:
        for c, st in band["steps"]:
            sh = by_id[st["sheet"]]
            _, _, top = where[st["sheet"]]
            title = ('<span class="num">%d</span>%s<span class="nm">%s</span>'
                     % (st["step"], _tag(sh, True), esc(sh.get("name") or sh["id"])))
            html.append(_node(sh, colx(c), top, w, h, title))
        for lane in band["lanes"]:
            for c, br in lane:
                sh = by_id[br["sheet"]]
                _, _, top = where[br["sheet"]]
                title = "%s<span class=\"nm\">%s</span>" % (_tag(sh, True),
                                                            esc(sh.get("name") or ""))
                html.append(_node(sh, colx(c), top, w, h, title,
                                  "branch %s" % br["kind"]))

    # 걸음 → 다음 걸음 (정답 경로)
    for i in range(len(steps) - 1):
        a, b = steps[i], steps[i + 1]
        wa, wb = where.get(a["sheet"]), where.get(b["sheet"])
        label = esc(short_how(b.get("how"))) or "(조작 없음)"
        if wa and wb and wa[0] == wb[0] and wb[1] == wa[1] + 1:
            ya = wa[2] + NODE_TITLE + h * 0.42
            x1, x2 = colx(wa[1]) + w + 2, colx(wb[1]) - 3
            svg.append(_path("M%.1f %.1fH%.1f" % (x1, ya, x2), INK))
            svg.append(_badge((x1 + x2) / 2.0, ya, b["step"]))
            html.append(_label(x1 - 2, wa[2] + NODE_TITLE + 2, x2 - x1 + 4,
                               h * 0.42 - 13, label, "c b"))
        elif wa and wb and wb[0] == wa[0] + 1:
            # 다음 띠로 - 오른쪽으로 나가 띠 사이로 돌아 들어온다
            ya = wa[2] + NODE_TITLE + h * 0.42
            xr = colx(wa[1]) + w + 7
            yb = tops[wb[0]] - FLOW_BGAP / 2.0
            xb = colx(wb[1]) + w / 2.0
            svg.append(_path("M%.1f %.1fH%.1fV%.1fH%.1fV%.1f"
                             % (colx(wa[1]) + w + 2, ya, xr, yb, xb, wb[2] + 1), INK))
            svg.append(_badge(xb - 14, yb, b["step"]))
            html.append(_label(xb - 6, yb - 12, 3 * (w + gap), 10,
                               "← " + label, ""))
        elif wa and not wb:
            html.append(_label(colx(wa[1]), wa[2] + NODE_TITLE + h + NODE_CAP, w + gap, 20,
                               "→ 다음 장 %d (%s)" % (b["step"], label), ""))
        elif wb and not wa and b["step"] == first_step:
            html.append(_label(colx(wb[1]), wb[2] - 12, 3 * (w + gap), 11,
                               "앞 장 %d 에서 → %d (%s)" % (a["step"], b["step"], label), ""))

    # 갈래 - 오류 · 펼침, 되돌아가기
    into = {}
    for bi, band in enumerate(bands):
        for lane in band["lanes"]:
            for c, br in lane:
                src = where.get(br["from"])
                _, _, top = where[br["sheet"]]
                color = ERR if br["kind"] == "error" else REV
                dash = "5 3" if br["kind"] == "error" else "1.5 2.5"
                label = (("오류 %s · " % esc(br["id"])) if br["kind"] == "error"
                         else "펼침 · ") + esc(short_how(br["how"]))
                cls = "r err" if br["kind"] == "error" else "r rev"
                xe = colx(c) + w / 2.0 - 8
                if src and src[0] == bi:
                    ys = src[2] + NODE_TITLE + h + NODE_CAP + 1
                    xs = colx(src[1]) + w / 2.0 - 8
                    if src[1] == c:
                        svg.append(_path("M%.1f %.1fV%.1f" % (xs, ys, top - 1), color, dash))
                        html.append(_label(xe - (w / 2.0 + gap / 2.0) + 2, ys + 2,
                                           w / 2.0 + gap / 2.0 - 6, top - ys - 6, label, cls))
                    else:
                        ym = top - FLOW_VGAP / 2.0 + 6
                        svg.append(_path("M%.1f %.1fV%.1fH%.1fV%.1f" % (xs, ys, ym, xe, top - 1),
                                         color, dash))
                        html.append(_label(xe - (w / 2.0 + gap / 2.0) + 2, ym + 3,
                                           w / 2.0 + gap / 2.0 - 6, top - ym - 6, label, cls))
                if br["kind"] != "error":
                    continue
                back = where.get(br.get("back"))
                rlabel = "↩ " + esc(short_how(br.get("recover")) or "되돌아가기")
                xr = colx(c) + w / 2.0 + 8
                if back and back[0] == bi:
                    k = into.get(br["back"], 0)
                    into[br["back"]] = k + 1
                    yt = back[2] + NODE_TITLE + h + NODE_CAP + 1
                    xt = colx(back[1]) + w / 2.0 + 8 + 6 * k
                    if back[1] == c and not k:
                        svg.append(_path("M%.1f %.1fV%.1f" % (xr, top - 1, yt), ERR, "5 3"))
                    else:
                        ym = top - FLOW_VGAP / 2.0 - 6
                        svg.append(_path("M%.1f %.1fV%.1fH%.1fV%.1f" % (xr, top - 1, ym, xt, yt),
                                         ERR, "5 3"))
                    html.append(_label(xr + 4, top - FLOW_VGAP / 2.0 + 3,
                                       w / 2.0 + gap / 2.0 - 6, FLOW_VGAP / 2.0 - 6, rlabel,
                                       "err"))
                else:
                    html.append(_label(colx(c), top + NODE_TITLE + h + NODE_CAP, w + gap, 20,
                                       "%s → [%s]" % (rlabel, esc(br.get("back") or "-")),
                                       "err"))

    n_err = sum(1 for b in bands for l in b["lanes"] for _, br in l if br["kind"] == "error")
    n_rev = sum(1 for b in bands for l in b["lanes"] for _, br in l if br["kind"] == "reveal")
    key = ('<span class="fm-key"><svg width="26" height="8"><path d="M1 4H24" stroke="%s" '
           'stroke-width="1.3"%s/></svg>%s</span>')
    head = ('<div class="fm-head"><h1>와이어플로%s</h1><div class="sub">정답 경로 %s · 오류 '
            "갈래 %d · 펼치기 %d — 화살표는 흐름 명세의 걸음 · 오류 경로 · 펼치기에서만 만들고, "
            "화살표 옆은 앞 화면에서 누른 것, 이어지는 장은 도구가 그 상태까지 걸어 확인한 "
            "화면이다. 작은 그림은 화면 위쪽(폰 한 화면)만 보인다.</div>"
            "<div class=\"sub\">%s%s%s%s</div></div>" % (
                " (%d/%d)" % (page_no, pages) if pages > 1 else "",
                "①→%s" % (steps[-1]["step"] if steps else "-"), n_err, n_rev,
                key % (INK, "", "정답 경로"), key % (ERR, ' stroke-dasharray="5 3"', "오류 갈래 · ↩ 되돌아가기"),
                key % (REV, ' stroke-dasharray="1.5 2.5"', "펼침"),
                '<span class="fm-key">점선 테두리 그림 = 조건별 장</span>'))
    marker = ('<marker id="ah-%s" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
              'markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" '
              'fill="%s"/></marker>')
    defs = "<defs>%s</defs>" % "".join(marker % (c.lstrip("#"), c) for c in (INK, ERR, REV))
    return ('<section class="sheet flowmap" id="%s">%s<svg class="flowsvg" width="%d" '
            'height="%d" viewBox="0 0 %d %d">%s%s</svg>%s</section>'
            % ("wireflow" if page_no == 1 else "wireflow-%d" % page_no, head, FLOW_W, FLOW_H,
               FLOW_W, FLOW_H, defs, "".join(svg), "".join(html)))


def render_wireflow(data):
    by_id = {s["id"]: s for s in data["sheets"]}
    steps, _ = flow_graph(data)
    if not steps:
        return ('<section class="sheet cover" id="wireflow"><h1>와이어플로</h1><p class="warn">'
                "정답 경로의 장이 없어 그리지 못했다.</p></section>")
    cols, pages = flow_pages(data)
    return "\n".join(render_flow_page(data, bands, cols, w, i + 1, len(pages), by_id)
                     for i, (bands, w) in enumerate(pages))


# --------------------------------------------------------------------------- #
# 기능-화면 표
# --------------------------------------------------------------------------- #
def _feature_label(row, by_id):
    sec = row["section"]
    if sec == "steps":
        sh = by_id.get(row.get("sheet")) or {}
        how = short_how(row.get("how"))
        return "%d. %s%s" % (row["step"], esc(sh.get("name") or row.get("sheet")),
                             ' <span class="how">← %s</span>' % esc(how) if how else "")
    if sec == "choices":
        return '<span class="mono">%s</span> · 원본 %s개' % (
            esc(row["action"]), esc(row.get("count_original") or "?"))
    if sec == "inputs" and row.get("kind") == "keypad":
        return '숫자판 <span class="mono">%s</span> · 키 %d개 (원본 %s개)' % (
            esc(row["action"]), row.get("keys") or 0, esc(row.get("count_original") or "?"))
    if sec == "inputs":
        return '입력 칸 <span class="mono">%s</span>%s' % (
            esc(row["action"]), " '%s'" % esc(row.get("text") or row.get("aria"))
            if row.get("text") or row.get("aria") else "")
    if sec == "errors":
        rec = short_how(row.get("recover"))
        return ('<span class="mono">%s</span> %s%s' % (
            esc(row["id"]), esc(_clip(row.get("about") or "", 30)),
            ' <span class="how">— 회복 %s → [%s]</span>' % (esc(rec), esc(row.get("back_to_sheet")))
            if rec else ""))
    return '%s <span class="mono">%s</span>' % (esc(row.get("label") or "-"), esc(row["action"]))


def render_features(data, ids):
    table = data.get("features") or {}
    by_id = {s["id"]: s for s in data["sheets"]}
    cols = table.get("columns") or []
    rows = table.get("rows") or []
    missing = table.get("missing") or []
    out = ['<section class="sheet cover" id="features">', "<h1>기능-화면 표</h1>",
           '<p class="lead">이 표는 "기능은 줄이지 않는다" 의 확인표다 — 줄마다 그 기능이 '
           "어느 화면에 있는지 표시하고, 표시가 하나도 없는 줄은 설계서의 어느 장에서도 보지 "
           "못한 기능이다.</p>",
           '<div class="sub">%s 바로 보임 (본 장 · 다시 지나는 장 · 오류 장) · %s 펼쳐야 보임 '
           "(펼친 뒤 장에만) · 작은 수는 그 화면에 보인 개수. 표시는 모두 %s - 장마다 보인 "
           "data-action 요소와 흐름 명세의 걸음 · 오류 경로. 원본 화면 칸의 출처는 무리마다 "
           "적었다.%s</div>" % (
               DIRECT, REVEALED, _src("tool"),
               ' <span class="warn">표시가 없는 줄 %d</span>' % len(missing) if missing else
               " 표시가 없는 줄은 없다.")]
    out.append('<table class="fm"><thead><tr><th class="f">기능</th><th class="o">원본 화면'
               "</th>%s</tr></thead><tbody>" % "".join(
                   '<th class="v"><div>%s</div></th>' % _link(c, ids) for c in cols))
    for sec in SECTIONS:
        group = [r for r in rows if r["section"] == sec]
        if not group:
            continue
        srcs = sorted({ORIGINAL_FROM.get(r.get("original_from"), r.get("original_from"))
                       for r in group})
        out.append('<tr class="sec"><td colspan="%d">%s %d <span class="how">— 원본 화면: '
                   "%s</span></td></tr>" % (2 + len(cols), SECTION_LABEL[sec], len(group),
                                            esc(" · ".join(srcs))))
        for r in group:
            miss = not r["cells"]
            orig = ", ".join(r.get("original") or []) or "-"
            if r["section"] == "errors" and r.get("original_back_to"):
                orig += " → %s" % r["original_back_to"]
            cells = []
            for c in cols:
                cell = r["cells"].get(c)
                if not cell:
                    cells.append('<td class="m"></td>')
                    continue
                count = cell.get("count")
                cells.append('<td class="m" title="%s">%s%s</td>' % (
                    esc(", ".join(cell.get("sheets") or [])), cell["mark"],
                    "<small>%d</small>" % count if count and count > 1 else ""))
            out.append('<tr class="%s"><td class="f">%s%s</td><td>%s</td>%s</tr>' % (
                "miss" if miss else "", _feature_label(r, by_id),
                " · 장에서 보지 못함" if miss else "", esc(orig), "".join(cells)))
    out.append("</tbody></table></section>")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# 화면마다 한 장
# --------------------------------------------------------------------------- #
def render_picture(sh):
    if not sh.get("picture") or not sh.get("size"):
        return ('<div class="pic"><p class="warn">그림 없음 - %s</p></div>'
                % esc(sh.get("error") or "걷지 못했다"))
    w, h = sh["size"]
    k, s, slice_h = layout(w, h)
    out = ['<div class="pic"><div class="slices">']
    for i in range(k):
        y0, y1 = i * slice_h, min(h, (i + 1) * slice_h)
        out.append('<div class="slice" style="width:%.1fpx;height:%.1fpx">'
                   % (w * s, (y1 - y0) * s))
        out.append('<img src="%s" alt="%s 와이어프레임" style="width:%.1fpx;top:%.1fpx">'
                   % (esc(sh["picture"]), esc(sh["id"]), w * s, -y0 * s))
        for it in sh["items"]:
            x, y, bw, bh = it["box"]
            if y + bh <= y0 or y >= y1:
                continue
            out.append('<div class="el" style="left:%.1fpx;top:%.1fpx;width:%.1fpx;'
                       'height:%.1fpx"><span>%s</span></div>'
                       % (x * s, (y - y0) * s, bw * s, bh * s, esc(it["no"])))
        for r in sh.get("regions") or []:
            x, y, bw, bh = r["box"]
            pad = 3
            if y + bh + pad <= y0 or y - pad >= y1:
                continue
            badge = ('<span class="badge">%d</span>' % r["no"]) if y0 <= y - pad < y1 or \
                (i == 0 and y - pad < 0) else ""
            out.append('<div class="reg" style="left:%.1fpx;top:%.1fpx;width:%.1fpx;'
                       'height:%.1fpx">%s</div>'
                       % ((x - pad) * s, (y - pad - y0) * s, (bw + 2 * pad) * s,
                          (bh + 2 * pad) * s, badge))
        out.append("</div>")
    notes = ["%d × %dpx" % (w, h)]
    if sh.get("grown"):
        notes.append("스크롤되는 화면 - #phone 을 내용 높이로 %dpx 늘려 한 장으로 찍음"
                     % sh["grown"])
    if k > 1:
        notes.append("%d단으로 나눠 놓음" % k)
    if sh.get("clipped"):
        notes.append('<span class="warn">아래 %dpx 는 다 찍지 못함</span>' % sh["clipped"])
    if sh.get("covered"):
        notes.append("덮개 아래에 깔린 요소 %d개는 뺌" % sh["covered"])
    out.append('</div><div class="pic-note">%s</div></div>' % " · ".join(notes))
    return "".join(out)


NAME_SOURCE = {"model": None, "plan": "계획의 화면 목적 앞부분", "screen": "화면 이름"}
# 경로 칸에 적는 화면 이름의 길이 (넘으면 자른다 - 전체 이름은 그 장에 있다)
PATH_CHARS = 12


def render_info(sh, ids, by_id):
    """장 맨 위의 정보칸 한 줄 - 화면 ID · 화면 이름 · 경로 · 바탕이 된 원본 화면 · 조건."""
    src = sh.get("name_source")
    name = "%s%s" % (esc(sh.get("name") or ""), _src("model") if src == "model" else
                     ' <span class="src plain">%s</span>' % NAME_SOURCE[src]
                     if NAME_SOURCE.get(src) else "")
    path = []
    trail = sh.get("path") or []
    for i, sid in enumerate(trail):
        s = by_id.get(sid) or {}
        label = esc(_clip(s.get("name") or sid, PATH_CHARS))
        if i == len(trail) - 1:
            path.append("<b>%s</b>%s" % (label, _tag(s)))
        else:
            path.append('<a href="#%s">%s</a>' % (esc(sid), label))
    head = ["화면 ID", "화면 이름", "경로 (흐름 명세)", "바탕이 된 원본 화면"]
    cells = ['<td class="sid">%s%s</td>' % (esc(sh["id"]), _tag(sh)),
             "<td>%s</td>" % name,
             '<td class="path">%s</td>' % (" &gt; ".join(path) or "-"),
             "<td>%s%s</td>" % (esc(", ".join(sh.get("from_original") or [])) or "-",
                                ' <span class="src plain">계획</span>'
                                if sh.get("from_original") else "")]
    if sh.get("condition"):
        head.append("조건")
        cells.append("<td>%s</td>" % esc(sh["condition"]))
    widths = ["", ' style="width:150px"', "", ' style="width:110px"', ' style="width:270px"']
    return ('<table class="info"><tr>%s</tr><tr>%s</tr></table>'
            % ("".join("<th%s>%s</th>" % (widths[i], t) for i, t in enumerate(head)),
               "".join(cells)))


def render_sheet(sh, ids, sheets_by_id):
    items = {it["no"]: it for it in sh["items"]}
    out = ['<section class="sheet screen" id="%s">' % esc(sh["id"]),
           render_info(sh, ids, sheets_by_id), render_picture(sh), '<div class="spec">']
    if sh.get("of"):
        out.append('<div class="purpose"><b>조건별 화면</b> · 본 화면 %s</div>'
                   % _link(sh["of"], ids))
    out.append('<div class="purpose"><b>화면 목적</b> %s</div>'
               % esc(sh.get("purpose") or "계획에 없음"))
    if sh.get("dialogs"):
        out.append('<div class="cond">이 상태에 오는 동안 뜬 알림창: %s</div>' % " · ".join(
            "'%s'" % esc(d.get("message")) for d in sh["dialogs"]))
    if sh["items"]:
        out.append('<table class="regs"><tr><th>영역</th><th>이름 · 설명</th>'
                   "<th>요소와 동작</th></tr>")
        for r in sh.get("regions") or []:
            src_key = r.get("source")
            lis = []
            for e in r["elements"]:
                it = items.get(e)
                if not it:
                    continue
                ex = ('<span class="ex">예외: 비활성</span>'
                      if (it.get("result") or {}).get("kind") == "disabled" else "")
                lis.append('<li><span class="e">%s</span>%s — %s%s</li>' % (
                    esc(e), esc(item_label(it)), ex, result_text(it, True, ids)))
            empty = '<span class="ex">예외: 빈 화면</span>' if r.get("empty") else ""
            out.append('<tr><td class="no">%d</td><td class="nm">%s<b>%s</b>'
                       '<span class="desc">%s</span> %s</td><td>%s<ul>%s</ul></td></tr>' % (
                           r["no"], empty, esc(r["name"]), esc(r.get("description")),
                           _src(src_key), _src("tool"), "".join(lis)))
        out.append("</table>")
    else:
        out.append("<p>이 상태에서 보이는 data-action 요소가 없다.</p>")
    if sh.get("conditions"):
        out.append('<div class="conds"><b>조건별 화면</b><ul>')
        for cid in sh["conditions"]:
            c = sheets_by_id.get(cid) or {}
            out.append("<li>%s%s — %s</li>" % (_link(cid, ids), _tag(c),
                                              esc(c.get("condition") or "")))
        out.append("</ul></div>")
    out.append("</div></section>")
    return "\n".join(out)


def render(data):
    ids = {s["id"] for s in data["sheets"]}
    by_id = {s["id"]: s for s in data["sheets"]}
    title = "화면설계서 · %s · %s" % (data["task"].get("label"), data["run"].get("id"))
    body = ([render_cover(data, ids), render_wireflow(data), render_features(data, ids)]
            + [render_sheet(s, ids, by_id) for s in data["sheets"]])
    return ("<!doctype html>\n<html lang=\"ko\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            "<title>%s</title>\n<style>%s</style>\n</head>\n<body>\n%s\n</body>\n</html>\n"
            % (esc(title), CSS, "\n".join(body)))


async def _print(url, path):
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle")
            await page.emulate_media(media="print")
            await page.pdf(path=path, prefer_css_page_size=True, print_background=True)
        finally:
            await browser.close()


def print_pdf(url, path):
    """index.html 을 Chromium 으로 인쇄한다 (가로 A4 - CSS 의 @page)."""
    asyncio.run(_print(url, path))
