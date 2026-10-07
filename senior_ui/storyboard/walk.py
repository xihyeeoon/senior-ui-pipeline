r"""설계서의 브라우저 쪽 - 상태마다 다시 걷고, 그림을 찍고, 요소를 모으고, 눌러 본다.

상태(state)는 설계서의 그림 한 장이다. 흐름 명세에서 나온다.

  visit   정답 경로(steps)의 방문. 같은 화면을 두 번 지나면 두 번째는 따로 센다
  error   오류 경로(error_paths) - from_step 까지 정답대로 간 뒤 inputs 를 넣은 상태
  reveal  펼치기(reveal) - at 까지 간 뒤 do 의 조작을 한 상태

상태마다 "다시 걷는 법"(recipe)이 있다. 그림도 누르기 확인도 **새 페이지에서 그
recipe 를 처음부터 다시 걸어** 그 상태를 만든다. 걸음은 검사기와 같은 함수
(audit.drive.run_actions · settle)로 밟는다 - 검사기가 통과시킨 그 걸음이다.

두 페이지가 다르다.

  그림 페이지   로우파이 덮개 사본(storyboard/wireframe.html)을 연다. 그림을 찍기 직전에
                덮개를 켠다 - 회색 상자와 글자만, 사진 · 아이콘 자리는 X 표시
                상자로 (WIRE_CSS · __sbWire). 스크롤되는 화면은
                #phone 을 내용 높이만큼 늘려 한 장으로 찍는다 (EXPAND).
  확인 페이지   실행 폴더의 최종 HTML 그대로를 연다. 요소마다 새 페이지에서 그 상태까지
                다시 걸은 뒤 누르고, 무엇이 바뀌었는지 본다 (verify_one).

두 페이지는 같은 문서다 - 덮개는 스타일만 바꾸고 data-action 요소를 더하거나 빼지
않는다. 그래서 그림 페이지에서 모은 요소의 순번(문서 안의 [data-action] 순서)으로
확인 페이지의 같은 요소를 찾는다.

판정은 하지 않는다. 결과는 "다른 화면으로 감 / 같은 화면에서 바뀜 / 아무 일 없음"
(+ 누르지 못함 · 꺼져 있음) 이고, 무엇이 바뀌었는지는 짧게 적는다.
"""
import asyncio
import os
import re
import time

from playwright.async_api import async_playwright

from senior_ui.audit.drive import run_actions, settle
from senior_ui.audit.flow import truth_of, visit_keys, fill
from senior_ui.audit.probes import ENTRANCE_PREFIX

VIEWPORT = {"width": 390, "height": 844}
# 그림은 2배 해상도로 찍는다 - PDF 를 확대해 읽을 수 있게. 폭은 390px 화면 그대로다.
# 모델에게 보내는 번호 그림은 CSS 픽셀(1배)로 찍는다 (그림 토큰).
PICTURE_SCALE = 2
# 늘린 #phone 의 상한. 넘는 높이는 잘린 채 찍고 clipped_px 로 남긴다.
MAX_PHONE_HEIGHT = 8000

# 걸음 하나가 기다리는 상한. 검사를 통과한 빌드의 걸음이라 막히면 도구 쪽 문제다 -
# Playwright 기본 30초를 다 기다리지 않는다.
STEP_TIMEOUT_MS = 8000
# 누르기 하나의 상한. 가려진 요소는 Playwright 가 이만큼 기다린 뒤 실패한다.
CLICK_TIMEOUT_MS = 3000
# 누른 뒤 다른 화면이 켜지기를 기다리는 시간. 그동안 켜지지 않으면 같은 화면에서
# 무엇이 바뀌었는지 본다 (조회를 흉내 내느라 늦게 넘어가는 설계가 있다).
AFTER_CLICK_MS = 1200
POLL_MS = 100
# 동시에 여는 확인 페이지 수.
CONCURRENCY = 8

# 같은 화면에서 바뀐 것을 적을 때 줄마다 · 전체 몇 줄까지.
CHANGE_LINE_CHARS = 28
CHANGE_LINES = 1


# --------------------------------------------------------------------------- #
# 로우파이 덮개 - 그림용 사본에만 넣는다
# --------------------------------------------------------------------------- #
# 실무 와이어프레임 관례를 따른다: 회색 상자와 글자만. 색 · 모양은 디자이너의 몫이라
# 배경 · 채우기 · 그림자 · 그라데이션 · 둥근 모서리를 없애고 글자는 진회색 하나로 한다.
# 누를 수 있는 요소(data-action)와 입력 칸, 원래 디자인에서 상자로 보이던 묶음(카드 ·
# 띠 · 패널)은 1px 회색 테두리 상자로, 꺼진 버튼은 점선 테두리로 그린다. 사진 · 아이콘 ·
# 로고 자리는 X 가 그어진 회색 상자다.
#
# 위치 · 크기 · 글자 크기 · 굵기는 그대로 둔다 - 위계와 크기는 설계 결정이므로 남긴다.
# 그래서 이 덮개는 배치를 바꾸는 속성(크기 · 여백 · 테두리 두께 · 글꼴)을 하나도 쓰지
# 않는다. 테두리는 두께를 둔 채 색만 지우고, 상자는 outline 으로 그린다 (outline 은
# 배치에 들지 않는다).
#
# 덮개의 스타일은 모두 `html.sb-wire` 아래에 있다. 걷는 동안에는 꺼져 있고, 그림을
# 찍기 직전에 __sbWire() 가 원래 스타일을 읽어 표시(data-sb-*)를 붙인 뒤 그 클래스를
# 켠다 - 무엇이 상자였는지는 지우기 전의 배경 · 그림자 · 테두리로만 알 수 있다.
# 표시는 data-action 이 아니므로 요소 순번은 그대로다.
#
#   data-sb-pic   배경 그림(url) · 가면 그림(mask url)을 쓴 요소 → X 상자
#   data-sb-fill  solid = 불투명 바탕 → 흰 종이 (뒤에 깔린 것을 가린다)
#                 veil  = 화면을 덮는 반투명 막(모달 뒤) → 옅은 흰 막
#   data-sb-box   원래 디자인에서 상자로 보이던 묶음 → 1px 회색 테두리
WIRE_CLASS = "sb-wire"
_W = "html.%s " % WIRE_CLASS
X_BOX = ("background-color:#eeeeee!important;"
         "background-image:"
         "linear-gradient(to top right,transparent calc(50% - 1px),#999 calc(50% - 1px),"
         "#999 calc(50% + 1px),transparent calc(50% + 1px)),"
         "linear-gradient(to bottom right,transparent calc(50% - 1px),#999 calc(50% - 1px),"
         "#999 calc(50% + 1px),transparent calc(50% + 1px))!important;"
         "background-size:100% 100%!important;background-repeat:no-repeat!important;"
         "-webkit-mask:none!important;mask:none!important;"
         "outline:1px solid #999!important;outline-offset:-1px!important")
PICTURE_SELECTOR = ('img,video,picture,canvas,iframe,object,embed,svg,[role="img"],'
                    '[data-sb-pic]')
INK = "#333"
LINE = "1px solid #999"
PRESSABLE = "[data-action],input,textarea,select"
DISABLED = ("[data-action]:disabled,[data-action][aria-disabled=\"true\"],"
            "fieldset:disabled [data-action]")
WIRE_CSS = (
    "html.%s{filter:grayscale(1)!important;background:#fff!important}" % WIRE_CLASS
    + _W + "body{background:#fff!important}"
    + _W + "*," + _W + "*::before," + _W + "*::after{"
    "background-color:transparent!important;background-image:none!important;"
    "box-shadow:none!important;text-shadow:none!important;border-radius:0!important;"
    "border-color:transparent!important;border-image:none!important;"
    "outline:none!important;filter:none!important;backdrop-filter:none!important;"
    "-webkit-backdrop-filter:none!important;mix-blend-mode:normal!important;"
    "color:%s!important;-webkit-text-fill-color:%s!important;" % (INK, INK)
    + "text-decoration-color:%s!important;transition:none!important}" % INK
    + _W + "::placeholder{color:%s!important;-webkit-text-fill-color:%s!important;" % (INK, INK)
    + "opacity:1!important}"
    + _W + "[data-sb-fill=solid]{background-color:#fff!important}"
    + _W + "[data-sb-fill=veil]{background-color:rgba(255,255,255,.8)!important}"
    + ",".join(_W + s for s in (PRESSABLE + ",[data-sb-box]").split(","))
    + "{outline:%s!important;outline-offset:-1px!important}" % LINE
    + ",".join(_W + s for s in DISABLED.split(","))
    + "{outline-style:dashed!important}"
    + ",".join(_W + s for s in PICTURE_SELECTOR.split(",")) + "{" + X_BOX + "}"
    + _W + "img," + _W + "video{object-position:-99999px -99999px!important}"
    + _W + "svg *{visibility:hidden!important}"
    + _W + '[role="img"]{color:transparent!important;'
    "-webkit-text-fill-color:transparent!important}")
WIRE_JS = r"""window.__sbWire = function () {
  var root = document.documentElement;
  root.classList.remove('%(cls)s');
  ['data-sb-pic', 'data-sb-fill', 'data-sb-box'].forEach(function (a) {
    document.querySelectorAll('[' + a + ']').forEach(function (e) { e.removeAttribute(a); });
  });
  var phone = document.getElementById('phone');
  var pr = phone ? phone.getBoundingClientRect()
                 : {width: innerWidth, height: innerHeight};
  var outer = [root, document.body];
  for (var p = phone; p; p = p.parentElement) outer.push(p);
  var rgba = function (c) {
    var m = /rgba?\(([^)]*)\)/.exec(c || '');
    if (!m) return null;
    var v = m[1].split(/[\s,\/]+/).filter(Boolean).map(parseFloat);
    return {rgb: v.slice(0, 3).join(','), a: v.length > 3 ? v[3] : 1};
  };
  // 원래 스타일로 본 바탕: solid (불투명) · tint (반투명) · grad (그라데이션) · null
  var paint = new Map();
  var paintOf = function (el) {
    if (paint.has(el)) return paint.get(el);
    var cs = getComputedStyle(el), c = rgba(cs.backgroundColor);
    var out = null;
    if ((cs.backgroundImage || '').indexOf('gradient(') >= 0) out = {kind: 'grad', rgb: 'grad'};
    else if (c && c.a >= 0.9) out = {kind: 'solid', rgb: c.rgb};
    else if (c && c.a > 0) out = {kind: 'tint', rgb: c.rgb};
    paint.set(el, out);
    return out;
  };
  var under = function (el) {          // 그 요소 뒤에 보이는 바탕 (가장 가까운 불투명 조상)
    for (var q = el.parentElement; q; q = q.parentElement) {
      var b = paintOf(q);
      if (b && b.kind !== 'tint') return b.rgb;
    }
    return '255,255,255';
  };
  var lined = function (cs) {          // 네 변이 모두 보이는 테두리
    return ['Top', 'Right', 'Bottom', 'Left'].every(function (s) {
      var c = rgba(cs['border' + s + 'Color']);
      return parseFloat(cs['border' + s + 'Width']) > 0 && c && c.a > 0
        && ['none', 'hidden'].indexOf(cs['border' + s + 'Style']) < 0;
    });
  };
  var skip = 'input,textarea,select,.screen,%(pics)s';
  var n = {pic: 0, fill: 0, veil: 0, box: 0};
  document.querySelectorAll('body *').forEach(function (el) {
    var cs = getComputedStyle(el);
    var bgi = cs.backgroundImage || '', mask = cs.webkitMaskImage || cs.maskImage || '';
    if (bgi.indexOf('url(') >= 0 || mask.indexOf('url(') >= 0) {
      el.setAttribute('data-sb-pic', ''); n.pic++; return;
    }
    var r = el.getBoundingClientRect();
    var big = r.width >= pr.width - 2 && r.height >= pr.height * 0.5;
    var b = paintOf(el);
    if (b && b.kind === 'tint' && big) { el.setAttribute('data-sb-fill', 'veil'); n.veil++; }
    else if (b && b.kind !== 'tint') { el.setAttribute('data-sb-fill', 'solid'); n.fill++; }
    if (outer.indexOf(el) >= 0 || el.hasAttribute('data-action') || el.matches(skip)) return;
    if (r.width < 4 || r.height < 4 || big) return;
    var boxed = (cs.boxShadow && cs.boxShadow !== 'none') || lined(cs)
      || (b && b.kind === 'tint')
      || (b && (b.kind === 'grad' || b.rgb !== under(el)));
    if (boxed) { el.setAttribute('data-sb-box', ''); n.box++; }
  });
  root.classList.add('%(cls)s');
  return n;
};""" % {"cls": WIRE_CLASS, "pics": PICTURE_SELECTOR.replace("'", "\\'")}
WIRE_MARK = "<!-- storyboard: 로우파이 덮개 (그림용 사본) -->"


def wire_copy(html):
    """최종 HTML 의 그림용 사본. 덮개 스타일과 스크립트를 </head> 앞에 넣는다 (없으면
    문서 맨 앞). 다른 것은 한 글자도 바꾸지 않는다."""
    block = "%s\n<style id=\"sb-wire\">%s</style>\n<script id=\"sb-wire-js\">%s</script>\n" \
        % (WIRE_MARK, WIRE_CSS, WIRE_JS)
    m = re.search(r"</head\s*>", html, re.I)
    if m:
        return html[:m.start()] + block + html[m.start():]
    return block + html


# --------------------------------------------------------------------------- #
# 페이지 안에서 도는 조각
# --------------------------------------------------------------------------- #
# 스크롤되는 화면을 한 장으로. 켜진 화면 안의 스크롤 요소가 넘치는 만큼 #phone 을
# 늘린다 (화면 · 몸통이 #phone 에 맞춰 늘어나는 설계 - 대부분). 늘려도 줄지 않는
# 스크롤 요소(높이를 못박은 목록)는 그 요소의 높이 제한을 푼다. 아래에 고정된 버튼은
# 늘어난 화면의 맨 아래에 온다.
EXPAND = r"""(maxH) => {
  const phone = document.getElementById('phone');
  if (!phone) return {phone: false};
  const lit = () => document.querySelector('.screen.on') || document.body;
  const scrollers = () => {
    const out = [];
    const root = lit();
    [root, ...root.querySelectorAll('*')].forEach(el => {
      const cs = getComputedStyle(el);
      if (!/(auto|scroll)/.test(cs.overflowY)) return;
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) return;
      el.scrollTop = 0;
      const extra = el.scrollHeight - el.clientHeight;
      if (extra > 1) out.push([el, extra]);
    });
    return out;
  };
  const setH = h => {
    phone.style.setProperty('height', h + 'px', 'important');
    phone.style.setProperty('max-height', 'none', 'important');
  };
  let clipped = 0;
  const h0 = phone.getBoundingClientRect().height;
  for (let round = 0; round < 6; round++) {
    const list = scrollers();
    if (!list.length) break;
    const extra = Math.max(...list.map(x => x[1]));
    const h = phone.getBoundingClientRect().height;
    if (h + extra > maxH) { setH(maxH); clipped = h + extra - maxH; break; }
    setH(h + extra);
    // 늘린 뒤에도 같은 만큼 넘치는 요소는 #phone 을 따라 늘지 않는 요소다
    scrollers().forEach(([el, e]) => {
      const before = list.find(x => x[0] === el);
      if (before && e >= before[1] - 1) {
        el.style.setProperty('max-height', 'none', 'important');
        el.style.setProperty('height', 'auto', 'important');
        el.style.setProperty('overflow-y', 'visible', 'important');
      }
    });
  }
  const left = scrollers();
  if (left.length && !clipped) clipped = Math.max(...left.map(x => x[1]));
  const r = phone.getBoundingClientRect();
  return {phone: true, x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height,
          clipped: Math.round(clipped), grown: Math.round(r.height - h0)};
}"""

PHONE_RECT = r"""() => {
  const p = document.getElementById('phone');
  const r = p ? p.getBoundingClientRect()
              : {left: 0, top: 0, width: innerWidth, height: innerHeight};
  return {x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height};
}"""

# 보이는 data-action 요소. 순번(index)은 문서 안의 [data-action] 순서다 - 확인 페이지가
# 같은 순번으로 같은 요소를 찾는다. 보인다 = 그려져 있고(display · visibility · 조상의
# opacity) #phone 과 겹치고, 가운데를 찍었을 때 그 요소(또는 그 안)가 맞는다 - 덮개
# 아래에 깔린 것은 그 상태에서 누를 수 없으므로 빼고 수만 센다.
ELEMENTS = r"""() => {
  const phone = document.getElementById('phone');
  const pr = phone ? phone.getBoundingClientRect()
                   : {left: 0, top: 0, right: innerWidth, bottom: innerHeight};
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  const hidden = el => {
    for (let p = el; p; p = p.parentElement) {
      const cs = getComputedStyle(p);
      if (+cs.opacity === 0) return true;
      if (p === el && (cs.display === 'none' || cs.visibility === 'hidden')) return true;
    }
    return false;
  };
  const valueOf = el => {
    for (const k in el.dataset) {
      if (k === 'action') continue;
      const x = (el.dataset[k] || '').trim();
      if (x) return x;
    }
    return clean(el.textContent);
  };
  const out = [], covered = [];
  document.querySelectorAll('[data-action]').forEach((el, i) => {
    const action = el.getAttribute('data-action');
    if (!action || hidden(el)) return;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return;
    if (r.right <= pr.left || r.left >= pr.right || r.bottom <= pr.top || r.top >= pr.bottom) return;
    const cx = Math.min(Math.max(r.left + r.width / 2, pr.left + 1), pr.right - 1);
    const cy = Math.min(Math.max(r.top + r.height / 2, pr.top + 1), pr.bottom - 1);
    const hit = document.elementFromPoint(cx, cy);
    if (!(hit && (hit === el || el.contains(hit)))) { covered.push(i); return; }
    const tag = el.tagName.toLowerCase();
    let text = clean(el.innerText);
    if (!text && (tag === 'input' || tag === 'textarea'))
      text = clean(el.value || el.getAttribute('placeholder'));
    out.push({index: i, action: action, id: el.id || null, tag: tag,
              value: valueOf(el).slice(0, 40), text: text.slice(0, 80),
              aria: clean(el.getAttribute('aria-label')) || null,
              disabled: !!(el.disabled || el.getAttribute('aria-disabled') === 'true'
                           || el.closest('fieldset[disabled]')),
              box: [Math.round(r.left - pr.left), Math.round(r.top - pr.top),
                    Math.round(r.width), Math.round(r.height)]});
  });
  const on = document.querySelector('.screen.on');
  return {items: out, covered: covered.length,
          dom_screen: on ? (on.dataset.screen || null) : null,
          landed_on: (window.__screen && window.__screen()) || null};
}"""

# 흐름 명세의 선택자가 가리키는 data-action 요소의 순번 (화면 순서 · 되돌아가기를
# 요소 번호로 적으려고). 선택자의 요소가 data-action 이 아니면 가장 가까운 조상.
SELECTOR_INDEX = r"""(sels) => {
  const all = Array.from(document.querySelectorAll('[data-action]'));
  return sels.map(sel => {
    let el = null;
    try { el = document.querySelector(sel); } catch (e) { return null; }
    if (!el) return null;
    const a = el.hasAttribute('data-action') ? el : el.closest('[data-action]');
    return a ? all.indexOf(a) : null;
  });
}"""

# 모델에게 보낼 번호 그림 - 요소 상자와 이름표를 #phone 위에 잠깐 얹는다.
MARK_ON = r"""(items) => {
  const phone = document.getElementById('phone') || document.body;
  const layer = document.createElement('div');
  layer.id = 'sb-mark-layer';
  layer.style.cssText = 'position:absolute;left:0;top:0;right:0;bottom:0;'
    + 'pointer-events:none;z-index:2147483647';
  if (getComputedStyle(phone).position === 'static') phone.style.position = 'relative';
  items.forEach(it => {
    const [x, y, w, h] = it.box;
    const b = document.createElement('div');
    b.style.cssText = 'position:absolute;box-sizing:border-box;border:2px solid #000;'
      + 'left:' + x + 'px;top:' + y + 'px;width:' + w + 'px;height:' + h + 'px';
    const t = document.createElement('div');
    t.textContent = it.no;
    t.style.cssText = 'position:absolute;left:-2px;top:-2px;background:#000;color:#fff;'
      + 'font:bold 11px/13px sans-serif;padding:0 3px';
    b.appendChild(t);
    layer.appendChild(b);
  });
  phone.appendChild(layer);
}"""
MARK_OFF = "() => { const l = document.getElementById('sb-mark-layer'); if (l) l.remove(); }"

# 누르기 전후에 보는 것. 켜진 화면 · 기록 · 보이는 글(켜진 화면 + 그 밖에 떠 있는 것) ·
# 입력 칸 값 · 표시 상태(클래스와 aria 상태)의 지문 · 스크롤 위치.
SEEN = r"""() => {
  const on = document.querySelector('.screen.on');
  const root = on || document.body;
  const visible = e => {
    const cs = getComputedStyle(e);
    if (cs.display === 'none' || cs.visibility === 'hidden' || +cs.opacity === 0) return false;
    const r = e.getBoundingClientRect();
    return r.width >= 1 && r.height >= 1;
  };
  const lines = [];
  const add = t => (t || '').split('\n').forEach(l => {
    l = l.replace(/\s+/g, ' ').trim(); if (l) lines.push(l); });
  add(root.innerText);
  if (on) {
    const walk = el => {
      for (const c of el.children) {
        if (c === on) continue;
        if (c.contains(on)) { walk(c); continue; }
        if (visible(c)) add(c.innerText);
      }
    };
    walk(document.body);
  }
  const values = [];
  document.querySelectorAll('input, textarea, select').forEach(e => {
    if (visible(e)) values.push(e.value || '');
  });
  let sig = 0;
  const feed = s => { for (let i = 0; i < s.length; i++) sig = (sig * 31 + s.charCodeAt(i)) | 0; };
  document.querySelectorAll('body *').forEach(e => {
    if (!visible(e)) return;
    feed(e.tagName + '|' + (typeof e.className === 'string' ? e.className : '') + '|'
         + (e.getAttribute('aria-pressed') || '') + (e.getAttribute('aria-selected') || '')
         + (e.getAttribute('aria-expanded') || '') + (e.checked ? 'c' : '')
         + (e.disabled ? 'd' : '') + ';');
  });
  const scroll = [];
  [root, ...root.querySelectorAll('*')].forEach(e => {
    if (e.scrollTop) scroll.push(Math.round(e.scrollTop));
  });
  const doc = document.scrollingElement;
  return {dom_screen: on ? (on.dataset.screen || null) : null,
          landed_on: (window.__screen && window.__screen()) || null,
          lines: lines, values: values, sig: sig, scroll: scroll,
          doc_scroll: doc ? Math.round(doc.scrollTop) : 0};
}"""

# 확인 페이지에서 누를 요소를 찾는다. 순번의 요소가 같은 data-action 이면 그것,
# 아니면(목록이 달리 그려졌다) 같은 data-action 의 보이는 것 중 같은 값 · 같은 차례.
# 찾은 요소에 data-sb-target 을 붙인다 - Playwright 가 그것으로 누른다.
LOCATE = r"""(want) => {
  document.querySelectorAll('[data-sb-target]').forEach(e => e.removeAttribute('data-sb-target'));
  const all = Array.from(document.querySelectorAll('[data-action]'));
  const shown = e => { const r = e.getBoundingClientRect(); return r.width >= 1 && r.height >= 1; };
  const valueOf = el => {
    for (const k in el.dataset) {
      if (k === 'action') continue;
      const x = (el.dataset[k] || '').trim();
      if (x) return x;
    }
    return (el.textContent || '').replace(/\s+/g, ' ').trim();
  };
  let el = null, how = 'index';
  if (!want.by_value) {
    const c = all[want.index];
    if (c && c.getAttribute('data-action') === want.action) el = c;
  }
  if (!el) {
    const same = all.filter(e => e.getAttribute('data-action') === want.action && shown(e));
    el = same.find(e => valueOf(e).slice(0, 40) === want.value) || null;
    how = 'value';
    if (!el && same.length) { el = same[0]; how = 'first'; }
  }
  if (!el) return {found: false};
  el.setAttribute('data-sb-target', '1');
  return {found: true, how: how,
          disabled: !!(el.disabled || el.getAttribute('aria-disabled') === 'true'
                       || el.closest('fieldset[disabled]'))};
}"""


# --------------------------------------------------------------------------- #
# 상태와 다시 걷는 법
# --------------------------------------------------------------------------- #
def states_of(flow):
    """흐름 명세의 상태들, 걷는 순서대로. 하나는 `{"key", "kind", "visit", "screen",
    "upto", "extra", "settle", ...}`.

      upto    정답 걸음을 몇 번째(0부터) 방문까지 밟는가
      extra   그 뒤에 할 조작 (오류 경로의 inputs · 펼치기의 do)
      settle  extra 뒤에 켜지기를 기다릴 화면 (오류 경로의 expect_screen)
      screen  흐름 명세가 이 상태에서 있다고 적은 화면 - 실제로 켜진 화면은 걸어서 잰다
    """
    steps = flow.get("steps") or []
    visits = visit_keys(steps)
    out = []
    for i, (step, visit) in enumerate(zip(steps, visits)):
        n = visits[:i + 1].count(visit) if "#" not in visit else int(visit.split("#")[1])
        out.append({"key": "visit:%s" % visit, "kind": "visit", "visit": visit,
                    "screen": step.get("screen"), "upto": i, "extra": [], "settle": None,
                    "nth": n})
    for ep in flow.get("error_paths") or []:
        if not isinstance(ep, dict) or ep.get("from_step") not in visits:
            continue
        inputs = ep.get("inputs") or []
        out.append({"key": "error:%s" % ep.get("id"), "kind": "error", "id": ep.get("id"),
                    "visit": ep["from_step"], "screen": ep.get("expect_screen"),
                    "upto": visits.index(ep["from_step"]),
                    "extra": inputs if isinstance(inputs, list) else [inputs],
                    "settle": ep.get("expect_screen"),
                    "recover": ep.get("recover") or [], "back_to": ep.get("back_to")})
    reveal = flow.get("reveal")
    for action, spec in (reveal.items() if isinstance(reveal, dict) else []):
        if not isinstance(spec, dict) or spec.get("at") not in visits:
            continue
        i = visits.index(spec["at"])
        do = spec.get("do") or []
        out.append({"key": "reveal:%s" % action, "kind": "reveal", "action": action,
                    "visit": spec["at"], "screen": steps[i].get("screen"), "upto": i,
                    "extra": do if isinstance(do, list) else [do], "settle": None})
    return out


class ReplayFailed(Exception):
    """그 상태까지 다시 걷지 못했다."""


async def replay(page, flow, state, url):
    """새 페이지에서 그 상태까지 걷는다. 검사기의 걸음 함수를 그대로 쓴다."""
    truth = truth_of(flow)
    await page.goto(url, wait_until="networkidle")
    steps = flow["steps"]
    for step in steps[:state["upto"] + 1]:
        try:
            if "do" in step:
                await run_actions(page, step["do"], None, truth)
            elif "click" in step:
                await run_actions(page, {"click": step["click"]}, None, truth)
        except Exception as e:
            raise ReplayFailed("%s 걸음: %s" % (step.get("screen"), _short(e)))
        if not await settle(page, step.get("screen")):
            raise ReplayFailed("%s 화면이 켜지지 않았다" % step.get("screen"))
    for act in state["extra"]:
        try:
            await run_actions(page, [act], None, truth)
        except Exception as e:
            raise ReplayFailed("%s 의 조작 %s: %s" % (state["key"], act, _short(e)))
        if state["kind"] == "reveal":
            await page.wait_for_timeout(100)
    if state.get("settle") and not await settle(page, state["settle"]):
        raise ReplayFailed("%s 뒤에 %s 화면이 켜지지 않았다" % (state["key"], state["settle"]))


def _short(e):
    s = "%s: %s" % (type(e).__name__, e) if isinstance(e, Exception) else str(e)
    return " ".join(s.split())[:200]


def attach_dialogs(page, seen):
    """뜨는 알림창을 모으고 닫는다 (검사기와 같이 dismiss)."""
    async def on_dialog(d):
        seen.append({"type": d.type, "message": d.message})
        try:
            await d.dismiss()
        except Exception:
            pass
    page.on("dialog", lambda d: asyncio.ensure_future(on_dialog(d)))


# 설계서의 페이지는 시각과 난수를 고정한다. 상태 표시줄의 시계가 누르는 사이에 분을
# 넘기면 "아무 일 없음" 이 "새로 보임: '1:40'" 으로 적힌다. 비밀번호 숫자판처럼 그릴
# 때마다 섞는 목록은 그림 페이지와 확인 페이지에서 같은 순서가 된다. 타이머는 그대로
# 돈다 (set_fixed_time 은 Date 만 고정한다) - 늦게 넘어가는 화면 전환은 그대로 본다.
FIXED_TIME = "2026-10-01T09:41:00"
SEEDED_RANDOM = r"""(() => {
  let s = 20260101 >>> 0;
  Math.random = function () {
    s = (s + 0x6D2B79F5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
})();"""


async def new_page(browser, scale=1):
    ctx = await browser.new_context(viewport=dict(VIEWPORT), device_scale_factor=scale)
    await ctx.add_init_script(SEEDED_RANDOM)
    await ctx.clock.set_fixed_time(FIXED_TIME)
    page = await ctx.new_page()
    page.set_default_timeout(STEP_TIMEOUT_MS)
    return ctx, page


# --------------------------------------------------------------------------- #
# 그림 페이지 - 상태 하나
# --------------------------------------------------------------------------- #
async def picture_state(browser, wire_url, flow, state, shots_dir, file_id, number,
                        selectors=()):
    """로우파이 덮개 사본에서 그 상태까지 걷고, 덮개를 켜고, #phone 을 늘려 찍는다.

    `number(items) -> [(no, box)]` 는 모은 요소에 번호를 매기는 함수다 (build.number_items).
    번호를 안 뒤에 같은 페이지에서 번호 그림(모델에게 보낼 것)을 찍는다.
    `selectors` 는 이 상태에서 요소 순번을 알아낼 흐름 명세의 선택자들이다.

    돌려주는 것: {"items", "covered", "dom_screen", "landed_on", "size", "clipped",
    "picture", "marked", "selector_index", "dialogs", "error"}."""
    out = {"error": None, "dialogs": []}
    ctx, page = await new_page(browser, PICTURE_SCALE)
    attach_dialogs(page, out["dialogs"])
    try:
        try:
            await replay(page, flow, state, wire_url)
        except ReplayFailed as e:
            out["error"] = str(e)
            return out
        await page.evaluate("() => window.__sbWire && window.__sbWire()")
        ex = await page.evaluate(EXPAND, MAX_PHONE_HEIGHT)
        if ex.get("phone"):
            # 창을 늘린 #phone 이 다 들어가게 키운다. 창 높이에 맞춰 놓이는 설계(가운데
            # 정렬)가 있으므로 키운 뒤 다시 잰다.
            for _ in range(3):
                need = int(ex["y"] + ex["h"] + 1)
                await page.set_viewport_size({"width": max(VIEWPORT["width"],
                                                           int(ex["x"] + ex["w"] + 0.5)),
                                              "height": max(VIEWPORT["height"], need)})
                again = await page.evaluate(PHONE_RECT)
                if abs(again["y"] + again["h"] - (ex["y"] + ex["h"])) < 1:
                    break
                ex.update(again)
            ex.update(await page.evaluate(PHONE_RECT))
        else:
            ex.update(await page.evaluate(PHONE_RECT), clipped=0)
        got = await page.evaluate(ELEMENTS)
        out.update(items=got["items"], covered=got["covered"],
                   dom_screen=got["dom_screen"], landed_on=got["landed_on"],
                   size=[int(round(ex["w"])), int(round(ex["h"]))],
                   clipped=ex.get("clipped") or 0, grown=ex.get("grown") or 0,
                   phone=bool(ex.get("phone")))
        if selectors:
            out["selector_index"] = dict(zip(
                selectors, await page.evaluate(SELECTOR_INDEX, list(selectors))))
        clip = {"x": ex["x"], "y": ex["y"], "width": ex["w"], "height": ex["h"]}
        pic = os.path.join(shots_dir, "%s.png" % file_id)
        await page.screenshot(path=pic, clip=clip, scale="device")
        out["picture"] = pic
        marks = number(out["items"])
        await page.evaluate(MARK_ON, [{"no": no, "box": box} for no, box in marks])
        marked = os.path.join(shots_dir, "%s.marked.png" % file_id)
        await page.screenshot(path=marked, clip=clip, scale="css")
        await page.evaluate(MARK_OFF)
        out["marked"] = marked
        return out
    finally:
        await ctx.close()


# --------------------------------------------------------------------------- #
# 확인 페이지 - 요소 하나를 눌러 본다
# --------------------------------------------------------------------------- #
def describe_change(before, after, dialogs):
    """누르기 전후의 SEEN 둘을 결과 하나로. `{"kind", "to"?, "detail"?}`.

      screen    켜진 화면이 바뀌었다 - to 는 새 화면 이름
      same      같은 화면에서 무엇이 바뀌었다 - detail 은 짧은 설명
      none      보이는 것이 그대로다
    """
    b_screen = before.get("dom_screen") or before.get("landed_on")
    a_screen = after.get("dom_screen") or after.get("landed_on")
    if a_screen != b_screen and a_screen:
        return {"kind": "screen", "to": a_screen}
    parts = []
    new = _new_lines(before["lines"], after["lines"])
    gone = _new_lines(after["lines"], before["lines"])
    if new:
        parts.append("새로 보임: " + _quote_lines(new))
    elif gone:
        parts.append("사라짐: " + _quote_lines(gone))
    if before.get("values") != after.get("values"):
        changed = [v for v in after.get("values") or [] if v not in (before.get("values") or [])]
        parts.append("입력 칸 값이 바뀜" + (": " + _quote_lines(changed) if changed else ""))
    for d in dialogs:
        parts.append("알림창 '%s'" % _clip(d.get("message") or ""))
    if not parts and before["lines"] != after["lines"]:
        parts.append("보이는 글의 순서가 바뀜")
    if not parts and before.get("sig") != after.get("sig"):
        parts.append("표시 상태가 바뀜 (보이는 글은 그대로)")
    if not parts and (before.get("scroll") != after.get("scroll")
                      or before.get("doc_scroll") != after.get("doc_scroll")):
        parts.append("스크롤 위치가 바뀜")
    if not parts:
        return {"kind": "none"}
    return {"kind": "same", "detail": " · ".join(parts)}


def _new_lines(old, new):
    """new 에만 있는 줄 (같은 줄이 늘어난 것도 센다), 나온 순서대로."""
    left = {}
    for l in old:
        left[l] = left.get(l, 0) + 1
    out = []
    for l in new:
        if left.get(l):
            left[l] -= 1
        else:
            out.append(l)
    return out


def _clip(s, n=CHANGE_LINE_CHARS):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n - 1] + "…"


def _quote_lines(lines):
    shown = ["'%s'" % _clip(l) for l in lines[:CHANGE_LINES]]
    more = len(lines) - CHANGE_LINES
    return " ".join(shown) + (" 외 %d줄" % more if more > 0 else "")


async def verify_one(browser, url, flow, state, target):
    """새 페이지에서 그 상태까지 다시 걸은 뒤 target 을 누르고 결과를 돌려준다.

    target 은 `{"index", "action", "value", "by_value"}`. 결과는 describe_change 의
    것에 더해, 누르지 못했으면 `{"kind": "failed", "detail"}`, 꺼져 있어 누르지 않았으면
    `{"kind": "disabled"}`. 자바스크립트 오류가 났으면 js_errors."""
    ctx, page = await new_page(browser)
    dialogs, errors = [], []
    attach_dialogs(page, dialogs)
    page.on("pageerror", lambda e: errors.append(_short(str(e))))
    try:
        try:
            await replay(page, flow, state, url)
        except ReplayFailed as e:
            return {"kind": "failed", "detail": "그 상태까지 다시 걷지 못했다 - %s" % e}
        except Exception as e:
            return {"kind": "failed", "detail": "그 상태까지 다시 걷지 못했다 - %s" % _short(e)}
        await page.wait_for_timeout(50)
        found = await page.evaluate(LOCATE, target)
        if not found.get("found"):
            return {"kind": "failed", "detail": "다시 걸었을 때 그 요소를 찾지 못했다"}
        if found.get("disabled"):
            return {"kind": "disabled"}
        before = await page.evaluate(SEEN)
        n_dialogs, n_errors, url0 = len(dialogs), len(errors), page.url
        try:
            await page.locator("[data-sb-target='1']").first.click(timeout=CLICK_TIMEOUT_MS)
        except Exception as e:
            msg = _short(e)
            why = ("다른 요소에 가려져 있다" if "intercepts pointer events" in msg
                   else "누를 수 있게 되지 않았다" if "Timeout" in msg else msg)
            return {"kind": "failed", "detail": "누르지 못했다 - %s" % why}
        b_screen = before.get("dom_screen") or before.get("landed_on")
        waited, after = 0, None
        while waited < AFTER_CLICK_MS:
            await page.wait_for_timeout(POLL_MS)
            waited += POLL_MS
            if page.url.split("#")[0] != url0.split("#")[0]:
                return {"kind": "left", "detail": "페이지를 떠났다 (%s)" % page.url}
            now = await page.evaluate(SEEN)
            if (now.get("dom_screen") or now.get("landed_on")) != b_screen:
                await page.wait_for_timeout(150)
                after = await page.evaluate(SEEN)
                break
        if after is None:
            after = await page.evaluate(SEEN)
        await asyncio.sleep(0)
        res = describe_change(before, after, dialogs[n_dialogs:])
        if errors[n_errors:]:
            res["js_errors"] = errors[n_errors:]
        # 순번으로 찾을 것을 다른 길로 찾았으면 남긴다 (무리는 늘 값으로 찾는다)
        if found.get("how") != ("value" if target.get("by_value") else "index"):
            res["located_by"] = found["how"]
        return res
    finally:
        await ctx.close()


# --------------------------------------------------------------------------- #
# 전부
# --------------------------------------------------------------------------- #
async def _walk(build_url, wire_url, flow, states, shots_dir, number, selectors_for,
                targets_for, log, concurrency):
    out = {"states": {}, "seconds": {}}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            t0 = time.time()
            for i, st in enumerate(states):
                got = await picture_state(browser, wire_url, flow, st, shots_dir,
                                          st["file_id"], number,
                                          selectors_for(st))
                out["states"][st["key"]] = got
                log("그림 %d/%d %s - %s" % (i + 1, len(states), st["key"],
                                           got.get("error") or "요소 %d개 · %dx%d"
                                           % (len(got.get("items") or []),
                                              *(got.get("size") or [0, 0]))))
            out["seconds"]["pictures"] = round(time.time() - t0, 1)

            t1 = time.time()
            sem = asyncio.Semaphore(concurrency)
            jobs = []
            for st in states:
                for tid, target in targets_for(st, out["states"][st["key"]]):
                    jobs.append((st, tid, target))
            done = [0]

            async def one(st, tid, target):
                async with sem:
                    res = await verify_one(browser, build_url, flow, st, target)
                done[0] += 1
                if done[0] % 20 == 0 or done[0] == len(jobs):
                    log("누르기 %d/%d" % (done[0], len(jobs)))
                return st["key"], tid, res

            results = await asyncio.gather(*(one(*j) for j in jobs))
            out["clicks"] = {}
            for key, tid, res in results:
                out["clicks"].setdefault(key, {})[tid] = res
            out["seconds"]["clicks"] = round(time.time() - t1, 1)
            out["click_count"] = len(jobs)
        finally:
            await browser.close()
    return out


def walk(build_url, wire_url, flow, states, shots_dir, number, selectors_for, targets_for,
         log=print, concurrency=CONCURRENCY):
    """그림 페이지로 상태마다 찍고 요소를 모은 뒤, 확인 페이지로 요소마다 눌러 본다.

    number(items)            -> [(no, box)]          번호 매기기 (번호 그림에 쓴다)
    selectors_for(state)     -> [선택자]              그 상태에서 순번을 알아낼 선택자
    targets_for(state, got)  -> [(id, target)]        그 상태에서 눌러 볼 것"""
    os.makedirs(shots_dir, exist_ok=True)
    return asyncio.run(_walk(build_url, wire_url, flow, states, shots_dir, number,
                             selectors_for, targets_for, log, concurrency))


def is_entrance(action):
    """과제 밖 입구 - 원본의 data-action 이름이 oos- 로 시작한다 (검사 K 와 같은 규칙)."""
    return str(action or "").startswith(ENTRANCE_PREFIX)


def filled(selector, flow):
    """흐름 명세 선택자의 자리표시자를 정답으로."""
    return fill(selector, truth_of(flow))
