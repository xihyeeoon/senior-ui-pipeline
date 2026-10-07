r"""storyboard.json 하나로 설계서(index.html)를 그린다. 그림 말고는 다른 것을 읽지 않는다.

한 장 = 가로 A4. 맨 앞장(과제 · 화면 순서 · 변경 목록 · 진단 요약 · 실행 정보) 다음에
화면마다 한 장 - 왼쪽은 와이어프레임 그림 위에 영역 테두리와 번호(굵게)와 요소
번호(가늘게), 오른쪽은 화면 ID · 화면 목적 · 영역 표 · 조건별 화면 링크. 조건별
화면은 그 화면 뒤에 같은 모양으로 온다.

스크롤되는 화면은 그림이 길다. 한 장에 들도록 그림을 여러 단으로 잘라 나란히 놓는다
(layout - 가장 크게 보이는 단 수를 고른다). 영역 테두리는 단마다 잘려 그려지고 번호는
테두리가 시작하는 단에만 붙는다.

칸마다 출처를 붙인다: 동작은 "도구 확인"(도구가 실제로 눌러 본 결과), 영역 이름 · 설명은
"모델 설명" (mock 이면 "mock", 모델이 빠뜨려 도구가 모은 "기타" 는 "도구 묶음").

PDF 는 이 페이지를 Chromium 으로 인쇄한 것이다 (print_pdf).
"""
import asyncio
import html as _html
import math
import re

# 가로 A4 (297 x 210mm) - 여백 8mm. CSS 픽셀(1/96 인치)로 쓴 그림 칸.
PIC_W, PIC_H = 560, 680
SLICE_GAP = 10
MAX_SLICES = 6

SOURCE_LABEL = {"tool": "도구 확인", "model": "모델 설명", "mock": "mock",
                "tool_group": "도구 묶음"}


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


def result_text(it, link=True, sheet_ids=None):
    """항목의 동작 - 도구가 눌러 본 결과."""
    r = it.get("result") or {}
    kind = r.get("kind")
    if kind == "screen":
        to = r.get("to_id") or "scr-%s" % r.get("to")
        ref = ('<a href="#%s">[%s]</a>' % (esc(to), esc(to))
               if link and (sheet_ids is None or to in sheet_ids) else "[%s]" % to)
        text = "선택 시 %s 로 이동" % ref
    elif kind == "same":
        text = "선택 시 같은 화면에서 바뀜 — %s" % (esc(r.get("detail")) if link
                                                 else r.get("detail"))
    elif kind == "none":
        text = "선택해도 바뀌는 것 없음"
    elif kind == "disabled":
        text = "꺼져 있음 (이 상태에서는 누를 수 없음)"
    elif kind == "left":
        text = "페이지를 떠남 — %s" % (esc(r.get("detail")) if link else r.get("detail"))
    else:
        d = r.get("detail") or "결과 없음"
        text = "확인 못 함 — %s" % (esc(d) if link else d)
    if it["kind"] == "group":
        text = "%d개 중 하나 선택 (대표 '%s' 를 눌러 봄: %s)" % (
            it["group"]["count"], esc(it.get("value")) if link else it.get("value"), text)
    if it.get("entrance"):
        text += " · 과제 밖 입구"
    if r.get("js_errors"):
        text += " · 자바스크립트 오류 %d건" % len(r["js_errors"])
    return text


# --------------------------------------------------------------------------- #
CSS = r"""
@page { size: A4 landscape; margin: 8mm; }
:root { --ink:#1f1f1f; --muted:#666; --line:#cfcfcf; --reg:#d9480f; --el:#1864ab;
        --soft:#f4f4f2; }
* { box-sizing: border-box; }
html, body { margin: 0; background: #e9e9e6; color: var(--ink);
  font: 11px/1.45 "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans KR", sans-serif; }
.sheet { width: 281mm; min-height: 194mm; margin: 10mm auto; padding: 0; background: #fff;
  box-shadow: 0 1px 4px rgba(0,0,0,.18); position: relative; }
.sheet.screen { display: grid; grid-template-columns: 560px 1fr; column-gap: 16px;
  padding: 0; }
.sheet.cover { padding: 6mm 8mm; }
@media print {
  html, body { background: #fff; }
  .sheet { margin: 0; box-shadow: none; page-break-after: always; break-after: page; }
  a { color: inherit; text-decoration: none; }
}
h1 { font-size: 20px; margin: 0 0 2px; }
h2 { font-size: 13px; margin: 14px 0 6px; padding-bottom: 3px; border-bottom: 1.5px solid var(--ink); }
.sub { color: var(--muted); margin-bottom: 8px; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid var(--line); padding: 3px 5px; vertical-align: top; text-align: left; }
th { background: var(--soft); font-weight: 600; white-space: nowrap; }
.kv th { width: 120px; }
.mono { font-family: Consolas, "D2Coding", monospace; font-size: 10px; }
.src { display: inline-block; font-size: 9px; font-weight: 600; padding: 0 4px; border-radius: 3px;
  border: 1px solid currentColor; margin-left: 4px; white-space: nowrap; vertical-align: 1px; }
.src.tool { color: #1864ab; } .src.model { color: #862e9c; } .src.mock { color: #5c5f66; }
.src.tool_group { color: #a61e4d; }
.flow { margin: 0; padding-left: 18px; }
.flow li { margin: 2px 0; }
.how { color: var(--muted); }
.pic { padding: 8px 0 0 8px; }
.pic-head { font-weight: 700; font-size: 12px; margin-bottom: 4px; }
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
.spec { padding: 8px 8px 8px 0; }
.sid { font: 700 18px/1.2 Consolas, monospace; }
.sid .of { font: 400 11px sans-serif; color: var(--muted); margin-left: 6px; }
.purpose { margin: 4px 0 6px; }
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
"""


def _src(source):
    key = source if source in SOURCE_LABEL else "tool"
    return '<span class="src %s">%s</span>' % (key, SOURCE_LABEL[key])


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
           "검사를 통과한 HTML 에서 뽑았다. 색 · 모양은 디자이너의 몫이라 그림은 회색 "
           "와이어프레임이다.</div>" % (esc(run.get("id")), esc(run.get("final_label")),
                                     esc(run.get("final_attempt")))]
    out.append("<h2>과제</h2><p>%s</p>"
               % markdown_bold(esc(task.get("description"))).replace("\n", " "))

    out.append("<h2>화면 순서 (흐름 명세의 정답 경로)</h2><ol class=\"flow\">")
    sheets = {s["id"]: s for s in data["sheets"]}
    for st in data["flow"]["steps"]:
        sh = sheets.get(st.get("sheet")) or {}
        how = _how(st.get("how"), ids)
        out.append("<li>%s %s%s</li>" % (
            _link(st.get("sheet"), ids), esc(sh.get("purpose") or ""),
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
        ("영역 묶기", "%s%s · 비용 %s%s" % (
            "mock (%s)" % esc(call.get("mock")) if call.get("mock") else esc(call.get("model")),
            " · reasoning_effort %s" % esc(call["reasoning_effort"])
            if call.get("reasoning_effort") else "",
            "$%.4f" % call["cost_usd"] if call.get("cost_usd") is not None else "-",
            ' · <span class="warn">%s</span>' % esc(call["error"]) if call.get("error") else
            (' · <span class="warn">어긋나 "기타" 로 묶은 장 %d</span>' % len(call["fallback"])
             if call.get("fallback") else ""))),
        ("설계서", "장 %d (화면 %d) · 항목 %d · 누르기 %d번 · 그림 %s초 · 누르기 %s초 · %s"
         % (data["counts"]["sheets"], data["counts"]["main_sheets"], data["counts"]["items"],
            data["counts"]["clicks"], esc((gen.get("seconds") or {}).get("pictures")),
            esc((gen.get("seconds") or {}).get("clicks")), esc(gen.get("at")))),
    ]
    out += ["<tr><th>%s</th><td>%s</td></tr>" % r for r in rows]
    out.append("</table>")

    out.append("<h2>칸마다 어디서 왔나</h2><table class=\"legend\">"
               "<tr><th>칸</th><th>출처</th><th>어떻게</th></tr>"
               "<tr><td>그림</td><td>%s</td><td>최종 HTML 의 회색 덮개 사본을 흐름 명세대로 걸어 "
               "찍었다</td></tr>"
               "<tr><td>요소 번호 · 글자 · 위치</td><td>%s</td><td>그 상태에서 보이는 "
               "data-action 요소를 모았다</td></tr>"
               "<tr><td>동작</td><td>%s</td><td>요소마다 새 페이지에서 그 상태까지 다시 걸은 뒤 "
               "눌러 보았다. 선택지 무리는 대표 하나</td></tr>"
               "<tr><td>영역 이름 · 설명</td><td>%s %s %s</td><td>모델이 그림과 요소 목록으로 "
               "묶었다 (mock 은 정해진 답, 모델이 빠뜨린 요소는 도구가 \"기타\" 로)</td></tr>"
               "<tr><td>화면 목적 · 변경 · 진단</td><td>계획 · 진단 (모델)</td><td>재구성 "
               "실행의 계획 파일을 그대로 옮겼다</td></tr>"
               "<tr><td>조건</td><td>흐름 명세 · 과제</td><td>error_paths · reveal · 과제의 "
               "오류 조건</td></tr></table>" % (
                   _src("tool"), _src("tool"), _src("tool"), _src("model"), _src("mock"),
                   _src("tool_group")))

    out.append("<h2>장 목록</h2><ul class=\"flow\">")
    for s in data["sheets"]:
        out.append("<li>%s%s</li>" % (_link(s["id"], ids),
                                      " — %s" % esc(s["condition"]) if s.get("condition")
                                      else " — %s" % esc(s.get("purpose") or "")))
    out.append("</ul></section>")
    return "\n".join(out)


def render_picture(sh):
    if not sh.get("picture") or not sh.get("size"):
        return ('<div class="pic"><div class="pic-head">%s</div><p class="warn">그림 없음 - %s'
                "</p></div>" % (esc(sh["id"]), esc(sh.get("error") or "걷지 못했다")))
    w, h = sh["size"]
    k, s, slice_h = layout(w, h)
    out = ['<div class="pic"><div class="pic-head">%s</div><div class="slices">' % esc(sh["id"])]
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


def render_sheet(sh, ids, sheets_by_id):
    items = {it["no"]: it for it in sh["items"]}
    out = ['<section class="sheet screen" id="%s">' % esc(sh["id"]), render_picture(sh),
           '<div class="spec">']
    of = (' <span class="of">조건별 화면 · 본 화면 %s</span>' % _link(sh["of"], ids)
          if sh.get("of") else "")
    out.append('<div class="sid">%s%s</div>' % (esc(sh["id"]), of))
    if sh.get("condition"):
        out.append('<div class="cond">조건: %s</div>' % esc(sh["condition"]))
    out.append('<div class="purpose"><b>화면 목적</b> %s%s</div>' % (
        esc(sh.get("purpose") or "계획에 없음"),
        " · <b>원본 화면</b> %s" % esc(", ".join(sh["from_original"]))
        if sh.get("from_original") else ""))
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
                lis.append('<li><span class="e">%s</span>%s — %s</li>' % (
                    esc(e), esc(item_label(it)), result_text(it, True, ids)))
            out.append('<tr><td class="no">%d</td><td class="nm"><b>%s</b>'
                       '<span class="desc">%s</span> %s</td><td>%s<ul>%s</ul></td></tr>' % (
                           r["no"], esc(r["name"]), esc(r.get("description")),
                           _src(src_key), _src("tool"), "".join(lis)))
        out.append("</table>")
    else:
        out.append("<p>이 상태에서 보이는 data-action 요소가 없다.</p>")
    if sh.get("conditions"):
        out.append('<div class="conds"><b>조건별 화면</b><ul>')
        for cid in sh["conditions"]:
            c = sheets_by_id.get(cid) or {}
            out.append("<li>%s — %s</li>" % (_link(cid, ids), esc(c.get("condition") or "")))
        out.append("</ul></div>")
    out.append("</div></section>")
    return "\n".join(out)


def render(data):
    ids = {s["id"] for s in data["sheets"]}
    by_id = {s["id"]: s for s in data["sheets"]}
    title = "화면설계서 · %s · %s" % (data["task"].get("label"), data["run"].get("id"))
    body = [render_cover(data, ids)] + [render_sheet(s, ids, by_id) for s in data["sheets"]]
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
