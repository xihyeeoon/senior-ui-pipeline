r"""In-page JavaScript probes used by senior_ui.audit.drive.

Kept separate from the driver so each probe can be read and tested on its own.
Every probe is scoped to the screen that is currently `.on`, except STATE_PAIRS
which inspects the stylesheet as a whole.

화면에 매인 probe 는 켜진 화면이 없으면 `[]` 가 아니라 `null` 을 돌려준다.
빈 목록은 "쟀고 아무것도 없었다" 이고 null 은 "잴 수 없었다" 다. 둘을 같은
값으로 돌려주면 아무것도 떠 있지 않은 빌드가 가장 깨끗한 빌드로 보인다 -
검사 A 가 그 null 을 fatal 로 잡는다.
"""

# --- 켜진 화면이 스스로 말하는 이름 ------------------------------------------
# window.__screen() 은 전환 스크립트의 기록이다. 기록이 바뀌었다는 것과 화면이
# 바뀌었다는 것은 다른 일이므로, 화면 쪽 이름을 따로 읽어 둘을 맞춰 본다.
# 켜진 화면이 없으면 null 이고, 그것은 "도착을 확인할 수 없다" 는 뜻이다.
DOM_SCREEN = r"""
() => {
  const s = document.querySelector('.screen.on');
  return s ? (s.dataset.screen || null) : null;
}
"""

# --- inventory: what the current screen contains -----------------------------
# `attr_text` 는 innerText 에 들어오지 않는, 그래도 눈에 닿는 글이다 -
# placeholder · 입력칸의 현재 값 · alt · aria-label · title. 마크업에서 영어를
# 찾는 쪽(checks/f_language.markup_words)도 이것들을 못 본다: 태그를 통째로
# 걷어내므로 속성값이 함께 사라진다. 문서 전체에서 걷되 보이는 요소에서만
# 걷는다 - 꺼진 화면의 입력칸은 사용자에게 닿지 않는다.
INVENTORY = r"""
() => {
  const s = document.querySelector('.screen.on') || document.body;
  const attr = (sel, a) => Array.from(s.querySelectorAll(sel))
                                .map(e => e.getAttribute(a));
  const visible = e => {
    const cs = getComputedStyle(e);
    if (cs.display === 'none' || cs.visibility === 'hidden') return false;
    if (+cs.opacity === 0) return false;
    const r = e.getBoundingClientRect();
    return r.width >= 1 && r.height >= 1;
  };
  const ATTRS = ['placeholder', 'alt', 'aria-label', 'title'];
  const texts = [];
  document.querySelectorAll('*').forEach(e => {
    if (!visible(e)) return;
    for (const a of ATTRS) {
      const v = e.getAttribute(a);
      if (v) texts.push(v);
    }
    const t = e.tagName.toLowerCase();
    if ((t === 'input' || t === 'textarea') && e.value) texts.push(e.value);
  });
  /* 켜진 화면 밖에 떠 있는 것 - 모달·토스트·오버레이. 사용자 눈에는 화면 위에
     덮여 있는데 켜진 화면의 innerText 에는 들어오지 않는다. 켜진 화면의 조상은
     지나쳐 안으로 들어간다 (찾는 것은 켜진 화면의 형제다). 켜진 화면이 없으면
     빈 값이다 - 그때 `text` 가 이미 body 전체를 담기 때문이다. */
  const lit = document.querySelector('.screen.on');
  const outside = [];
  const walkOutside = el => {
    for (const c of el.children) {
      if (c === lit) continue;
      if (c.contains(lit)) { walkOutside(c); continue; }
      if (!visible(c)) continue;
      const t = (c.innerText || '').trim();
      if (t) outside.push(t);
    }
  };
  if (lit) walkOutside(document.body);
  return {
    attr_text: texts.join('\n'),
    outside_text: outside.join('\n'),
    actions:  attr('[data-action]', 'data-action'),
    ids:      Array.from(s.querySelectorAll('[id]')).map(e => e.id),
    screens:  Array.from(document.querySelectorAll('[data-screen]'))
                   .map(e => e.dataset.screen),
    onclicks: Array.from(s.querySelectorAll('[onclick]'))
                   .map(e => e.tagName.toLowerCase() + '|' + e.getAttribute('onclick')),
    text:     s.innerText,
    height:   s.scrollHeight
  };
}
"""

# --- D: low-contrast text (WCAG 2.1 ratio) -----------------------------------
# Walks every element holding its own text, resolves the effective background by
# climbing ancestors until something is opaque, and flags anything under
# threshold - 3.0 for large text (>=24px, or >=18.66px bold), 4.5 otherwise.
#
# 재는 것은 선언된 색이 아니라 눈에 닿는 색이다. 글자색에 알파가 있으면 그
# 알파만큼만 배경 위에 얹히므로, 선언된 색 그대로 재면 rgba(17,17,17,.25) 가
# #111 로 읽혀 18.9:1 이 된다 - 실제로는 #c4c4c4 이고 1.75:1 이다.
CONTRAST = r"""
() => {
  const lum = c => {
    const f = v => { v /= 255; return v <= 0.03928 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4); };
    return 0.2126*f(c[0]) + 0.7152*f(c[1]) + 0.0722*f(c[2]);
  };
  /* 색 하나를 sRGB 숫자로 바꾼다.

     rgb()/rgba() 는 글자에서 바로 읽는다. 그 밖의 표기 - oklch() · lab() ·
     color(srgb …) · color-mix() - 는 getComputedStyle 이 rgb 로 바꾸지 않고
     적힌 모양 그대로 돌려주므로, canvas 에 1픽셀 찍어 읽는다. 브라우저가
     칠할 수 있는 색이면 무엇이든 같은 길로 숫자가 된다.

     흰 바탕과 검은 바탕에 각각 찍어 비교하면 알파까지 되돌릴 수 있다.
     w = C*a + 255*(1-a), b = C*a 이므로 a = 1 - (w-b)/255, C = b/a 다.
     한 바탕에만 찍고 getImageData 로 읽으면 알파를 곱해 저장한 값을 되돌리는
     과정에서 옅은 색의 자리수가 깎인다. */
  const cvs = document.createElement('canvas');
  cvs.width = cvs.height = 1;
  const cx = cvs.getContext('2d', { willReadFrequently: true });
  const paint = (s, backdrop) => {
    cx.fillStyle = backdrop; cx.fillRect(0, 0, 1, 1);
    cx.fillStyle = s;        cx.fillRect(0, 0, 1, 1);
    const d = cx.getImageData(0, 0, 1, 1).data;
    return [d[0], d[1], d[2]];
  };
  const rasterise = s => {
    /* 칠할 수 없는 값은 fillStyle 이 앞 값을 그대로 둔다. 서로 다른 두 값에서
       출발해 두 번 넣어 보면, 끝 값이 갈리는 것으로 걸러진다. */
    cx.fillStyle = '#000000'; cx.fillStyle = s; const one = cx.fillStyle;
    cx.fillStyle = '#ffffff'; cx.fillStyle = s;
    if (one !== cx.fillStyle) return null;
    const w = paint(s, '#ffffff'), b = paint(s, '#000000');
    let a = 0;
    for (let i = 0; i < 3; i++) a += 1 - (w[i] - b[i]) / 255;
    a = Math.min(1, Math.max(0, a / 3));
    if (a < 0.004) return { rgb: [0, 0, 0], a: 0 };
    return { rgb: b.map(v => Math.min(255, v / a)), a: a };
  };
  const parse = s => {
    const m = (s || '').match(/^rgba?\(([^)]+)\)$/);
    if (m) {
      const p = m[1].split(',').map(x => parseFloat(x.trim()));
      if (p.length >= 3 && !p.some(isNaN))
        return { rgb: [p[0], p[1], p[2]], a: p.length > 3 ? p[3] : 1 };
    }
    return rasterise(s);
  };
  /* 알파가 든 색을 배경 위에 얹었을 때 눈에 닿는 색. */
  const over = (rgb, a, bg) =>
    [0, 1, 2].map(i => rgb[i] * a + bg[i] * (1 - a));
  /* 글자 하나의 명암을 재려면 그 요소까지의 조상 사슬이 다 필요하다 - opacity
     는 뿌리에서 곱해 내려오고, 배경은 뿌리에서부터 섞어 올라온다. 한 번만
     걷고 두 가지에 함께 쓴다. 뿌리가 먼저 오는 순서로 돌려준다. */
  const chainOf = el => {
    const up = [];
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) up.push(n);
    up.reverse();
    let o = 1;
    return up.map(n => {
      const cs = getComputedStyle(n);
      const v = parseFloat(cs.opacity);
      o *= isNaN(v) ? 1 : v;
      return { el: n, cs: cs, opacity: o };
    });
  };
  const css = c => 'rgb(' + c.map(v => Math.round(v)).join(', ') + ')';
  /* 글자 뒤에 실제로 깔린 색. 반투명 층을 건너뛰지 않고 뿌리에서부터 차례로
     섞는다. 건너뛰고 "불투명한 조상" 을 찾으면 어두운 상자에 덮인 흰 베일이
     없는 것처럼 되어, 그 위의 흰 글자가 "어두운 바탕 위의 흰 글자" 로 읽힌다.
     바탕은 흰색이다 - 아무도 칠하지 않은 캔버스의 색.

     배경이 색 하나가 아닌 층(그라디언트·이미지)을 만나면 뒤에 무슨 색이
     깔렸는지 알 수 없다. 그때는 색을 돌려주지 않고 `unknown` 을 세운다 -
     통과도 저명암도 아닌 "판정 불가" 다. CSS 는 한 요소에서 배경색을 먼저
     칠하고 그 위에 이미지를 얹으므로, 이미지가 있으면 그 층의 색은 가려진다.
     반대로 불투명한 색을 칠한 층은 아래에 무엇이 있든 덮으므로 거기서 다시
     판정할 수 있게 된다. */
  const bgOf = chain => {
    let acc = [255, 255, 255], unknown = null;
    for (const n of chain) {
      const c = parse(n.cs.backgroundColor);
      if (c && c.a > 0) {
        const a = Math.min(1, c.a * n.opacity);
        if (a > 0.999) { acc = c.rgb; unknown = null; }   /* 아래를 덮었다 */
        else acc = over(c.rgb, a, acc);
      }
      const img = n.cs.backgroundImage;
      if (img && img !== 'none') {
        unknown = { background: img.slice(0, 80),
                    behind: n.el.tagName.toLowerCase()
                            + (n.el.getAttribute('class')
                               ? '.' + n.el.getAttribute('class').split(/\s+/)[0]
                               : '') };
      }
    }
    return { rgb: acc, unknown: unknown };
  };
  const ratio = (a, b) => {
    const l1 = lum(a), l2 = lum(b);
    return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
  };

  const out = [], undet = [];
  document.querySelectorAll('*').forEach(el => {
    /* only elements holding their own text */
    const own = Array.from(el.childNodes)
      .filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join(' ').trim();
    if (!own) return;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none') return;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return;

    const fg = parse(cs.color);
    /* 완전히 투명한 글자는 명암 결함이 아니라 안 보이는 글이다 - 다른 일이다. */
    if (!fg || fg.a < 0.05) return;
    const chain = chainOf(el);
    /* 사실상 보이지 않는 글은 명암 결함이 아니다 - 글자색 알파와 같은 규칙. */
    const op = chain[chain.length - 1].opacity;
    if (op < 0.05) return;
    const back = bgOf(chain);
    const size = parseFloat(cs.fontSize);
    const weight = parseInt(cs.fontWeight, 10) || 400;
    const large = size >= 24 || (size >= 18.66 && weight >= 700);
    const need = large ? 3.0 : 4.5;
    if (back.unknown) {
      undet.push({
        text: own.slice(0, 40),
        tag: el.tagName.toLowerCase(),
        cls: (el.getAttribute('class') || '').slice(0, 40),
        color: cs.color,
        fontSize: Math.round(size * 10) / 10, need,
        background: back.unknown.background, behind: back.unknown.behind
      });
      return;
    }
    const bg = back.rgb;
    const seen = over(fg.rgb, fg.a * op, bg);
    const cr = ratio(seen, bg);
    if (cr < need) {
      out.push({
        text: own.slice(0, 40),
        tag: el.tagName.toLowerCase(),
        cls: (el.getAttribute('class') || '').slice(0, 40),
        color: cs.color, seen: css(seen), bg: css(bg),
        opacity: Math.round(op * 1000) / 1000,
        fontSize: Math.round(size * 10) / 10,
        ratio: Math.round(cr * 100) / 100, need
      });
    }
  });
  /* 두 칸으로 나눠 돌려준다. 판정 불가를 빈 자리로 돌려주면 통과와 같아진다. */
  return { low: out, undetermined: undet };
}
"""

# --- D: elements whose colour is purely inherited -----------------------------
# The example1 / recipient failure mode: a repair adds a label with no colour of
# its own, it inherits something meant for a different context, and disappears.
INHERITED_COLOUR = r"""
() => {
  const s = document.querySelector('.screen.on');
  if (!s) return null;      /* 켜진 화면이 없다 - 잴 수 없었다는 뜻이다 */
  const out = [];
  s.querySelectorAll('*').forEach(el => {
    const own = Array.from(el.childNodes)
      .filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join(' ').trim();
    if (!own) return;
    const p = el.parentElement;
    if (!p) return;
    const cs = getComputedStyle(el), ps = getComputedStyle(p);
    const inline = el.getAttribute('style') || '';
    const declaresOwn = /(^|;)\s*color\s*:/i.test(inline);
    if (!declaresOwn && cs.color === ps.color) {
      out.push({
        text: own.slice(0, 40),
        tag: el.tagName.toLowerCase(),
        cls: el.getAttribute('class') || '',
        color: cs.color
      });
    }
  });
  return out;
}
"""

# --- E1: text-bearing elements that visually overlap --------------------------
OVERLAP = r"""
() => {
  const s = document.querySelector('.screen.on');
  if (!s) return null;      /* 켜진 화면이 없다 - 잴 수 없었다는 뜻이다 */
  const cand = Array.from(s.querySelectorAll('*')).filter(el => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return false;
    if (cs.position === 'absolute' || cs.position === 'fixed') return false;
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) return false;
    const own = Array.from(el.childNodes)
      .filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join('').trim();
    return own.length > 0;
  });
  const out = [];
  for (let i = 0; i < cand.length; i++) {
    for (let j = i + 1; j < cand.length; j++) {
      const a = cand[i], b = cand[j];
      if (a.contains(b) || b.contains(a)) continue;
      const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
      const w = Math.min(ra.right, rb.right) - Math.max(ra.left, rb.left);
      const h = Math.min(ra.bottom, rb.bottom) - Math.max(ra.top, rb.top);
      if (w <= 2 || h <= 2) continue;
      const share = (w * h) / Math.min(ra.width * ra.height, rb.width * rb.height);
      if (share > 0.25) {
        out.push({
          a: (a.textContent || '').trim().slice(0, 24),
          b: (b.textContent || '').trim().slice(0, 24),
          overlap_pct: Math.round(share * 100)
        });
      }
    }
  }
  return out.slice(0, 25);
}
"""

# --- E2: content taller than the box that is supposed to hold it --------------
# Scroll containers are legitimate, so anything with overflow auto/scroll on the
# relevant axis is skipped.
OVERFLOW = r"""
() => {
  const s = document.querySelector('.screen.on');
  if (!s) return null;      /* 켜진 화면이 없다 - 잴 수 없었다는 뜻이다 */
  const out = [];
  s.querySelectorAll('*').forEach(el => {
    const cs = getComputedStyle(el);
    if (cs.overflowY === 'auto' || cs.overflowY === 'scroll') return;
    if (cs.display === 'none' || cs.visibility === 'hidden') return;
    const r = el.getBoundingClientRect();
    if (r.height < 4 || !el.children.length) return;
    let bottom = -Infinity, top = Infinity;
    for (const c of el.children) {
      const cs2 = getComputedStyle(c);
      if (cs2.position === 'absolute' || cs2.position === 'fixed') continue;
      if (cs2.display === 'none') continue;
      const rc = c.getBoundingClientRect();
      if (rc.height < 1) continue;
      bottom = Math.max(bottom, rc.bottom);
      top = Math.min(top, rc.top);
    }
    if (bottom === -Infinity) return;
    const spill = Math.max(bottom - r.bottom, r.top - top);
    if (spill > 2) {
      out.push({
        tag: el.tagName.toLowerCase(),
        cls: el.getAttribute('class') || '',
        box_h: Math.round(r.height),
        spill_px: Math.round(spill),
        text: (el.textContent || '').trim().slice(0, 30)
      });
    }
  });
  return out.slice(0, 25);
}
"""

# --- E3: text that now wraps onto more lines than it used to ------------------
# The recipient navbar does not overlap by rect - it just wraps inside a bar of
# fixed height, which is what makes it unreadable.
#
# 줄 수는 글이 실제로 그려진 줄 상자를 세어 얻는다. 상자 높이를 줄 높이로 나누면
# 여백과 테두리가 그 높이에 들어 있으므로, 여백만 붙은 한 줄이 두 줄로 읽힌다 -
# 위아래 여백 12px 인 버튼은 전부 두 줄이 된다. Range 로 텍스트 노드를 감싸면
# getClientRects() 가 줄마다 사각형을 돌려주므로 그것을 센다.
WRAPPED = r"""
() => {
  const s = document.querySelector('.screen.on');
  if (!s) return null;      /* 켜진 화면이 없다 - 잴 수 없었다는 뜻이다 */
  /* 한 줄이 여러 조각으로 쪼개져 올 수 있으므로 윗변이 같은 것끼리 묶는다.
     자기 글만 센다 - 자식 요소의 줄은 그 자식의 줄이다. */
  const range = document.createRange();
  const lineCount = el => {
    const tops = [];
    for (const node of el.childNodes) {
      if (node.nodeType !== 3 || !node.textContent.trim()) continue;
      range.selectNodeContents(node);
      for (const r of range.getClientRects()) {
        if (r.width < 1 || r.height < 1) continue;
        if (!tops.some(t => Math.abs(t - r.top) < 2)) tops.push(r.top);
      }
    }
    return tops.length;
  };
  const out = [];
  s.querySelectorAll('*').forEach(el => {
    const own = Array.from(el.childNodes)
      .filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join(' ').trim();
    if (!own) return;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return;
    const lines = lineCount(el);
    if (lines >= 2) {
      out.push({
        text: own.slice(0, 30),
        tag: el.tagName.toLowerCase(),
        cls: el.getAttribute('class') || '',
        lines: lines
      });
    }
  });
  return out;
}
"""

# --- 스타일시트의 규칙을 하나하나 (중첩까지) -----------------------------------
# @media · @supports · @layer · @container 안의 규칙도 규칙이다. cssRules 를 한
# 겹만 돌면 그 블록들은 selectorText 가 없으므로 그냥 지나쳐지고, 그 안에서만
# 정의한 클래스는 "아무 스타일시트도 정의하지 않는다"(H) 가 되고 그 안에서만
# 적은 `.x.on` 은 상태 쌍으로 집히지 않는다(G). 그래서 재귀로 돈다.
#
# @keyframes 안의 규칙은 selectorText 가 아니라 keyText (`0%`) 이므로 들어가도
# 걸리는 것이 없다. 들어가지 않는 쪽이 뜻이 분명하므로 건너뛴다.
# @import 는 그 안에 또 하나의 스타일시트가 있다 - 같은 규칙으로 들어간다.
EACH_RULE = r"""
  const eachRule = (fn) => {
    const walk = (rules) => {
      for (const r of rules || []) {
        if (r.type === CSSRule.KEYFRAMES_RULE) continue;
        if (r.styleSheet) {                    /* @import */
          try { walk(r.styleSheet.cssRules); } catch (e) { /* 읽을 수 없다 */ }
          continue;
        }
        if (r.selectorText) fn(r);
        if (r.cssRules) walk(r.cssRules);
      }
    };
    for (const sheet of document.styleSheets) {
      let rs;
      try { rs = sheet.cssRules; } catch (e) { continue; }
      walk(rs);
    }
  };
"""


# --- H: classes the markup uses that no stylesheet defines --------------------
# example1 produced `bg-primary` / `text-primary`; this run produced `sr-only`.
# Both render as if the class were never written, which is how a "hidden" label
# ends up on screen.
UNDEFINED_CLASSES = "() => {" + EACH_RULE + r"""
  const defined = new Set();
  eachRule(r => {
    for (const m of r.selectorText.matchAll(/\.([A-Za-z0-9_-]+)/g)) defined.add(m[1]);
  });
  const used = new Map();
  document.querySelectorAll('[class]').forEach(el => {
    const screen = el.closest('[data-screen]');
    for (const c of el.classList) {
      if (defined.has(c)) continue;
      const key = c + '|' + (screen ? screen.dataset.screen : '?');
      if (!used.has(key)) {
        used.set(key, {
          cls: c,
          screen: screen ? screen.dataset.screen : null,
          count: 0,
          sample: (el.textContent || '').trim().slice(0, 30)
        });
      }
      used.get(key).count++;
    }
  });
  return Array.from(used.values());
}
"""


# --- G: does a state class still change how the element looks? ----------------
# Probes `.x` against `.x.on` with real elements so `#0046FF` and
# `var(--blue-deep)` compare equal, the way the eye sees them.
STATE_PAIRS = "() => {" + EACH_RULE + r"""
  const STATES = ['on', 'act', 'active', 'selected', 'checked', 'disabled'];
  const rules = [];
  eachRule(r => { if (r.style) rules.push(r); });
  const out = [];
  const seen = new Set();
  for (const r of rules) {
    for (const sel of r.selectorText.split(',').map(x => x.trim())) {
      const m = sel.match(/^(\.[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*)\.([A-Za-z-]+)$/);
      if (!m || !STATES.includes(m[2])) continue;
      const key = m[1] + '|' + m[2];
      if (seen.has(key)) continue;
      seen.add(key);
      const props = Array.from(r.style);
      if (!props.length) continue;

      const mk = cls => {
        const d = document.createElement('div');
        d.className = cls;
        d.style.position = 'absolute';
        d.style.left = '-9999px';
        d.textContent = 'x';
        document.body.appendChild(d);
        return d;
      };
      const baseCls = m[1].replace(/^\./, '').split('.').join(' ');
      const a = mk(baseCls), b = mk(baseCls + ' ' + m[2]);
      const ca = getComputedStyle(a), cb = getComputedStyle(b);
      const differing = props.filter(p =>
        ca.getPropertyValue(p) !== cb.getPropertyValue(p));
      out.push({
        base: m[1], state: m[2], props: props, differing: differing,
        base_values: props.map(p => p + '=' + ca.getPropertyValue(p))
      });
      a.remove();
      b.remove();
    }
  }
  return out;
}
"""


# --- 누를 수 있게 보이는가 (검사 K 의 입구 · 검사 I 의 보이는 선택지가 함께 쓴다) -------
# 그려져 있고(크기 >= 1x1), 자신이나 조상이 display · visibility · opacity 로 숨지 않았고,
# disabled 가 아니다. 브라우저의 checkVisibility() 를 쓴다 - 닫힌 <details> 안의 요소는
# display 도 크기도 멀쩡하지만(Chromium 은 그 안을 content-visibility 로 숨긴다) 보이지 않고,
# 조상의 opacity:0 도 요소 자신의 계산값에는 나타나지 않는다. 그 둘을 놓치면 접어 둔
# 입구가 펼치는 조작 없이 "보인다" 로 세였다 (11-8 - mock entrances-folded 가 reveal 없이도
# 통과했다). checkVisibility 가 없는 브라우저는 요소 자신의 계산값만 본다 (전의 규칙).
PRESSABLE = r"""
  const pressable = e => {
    if (e.disabled || e.getAttribute('aria-disabled') === 'true') return false;
    const r = e.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return false;
    if (typeof e.checkVisibility === 'function')
      return e.checkVisibility({checkOpacity: true, checkVisibilityCSS: true});
    const cs = getComputedStyle(e);
    return cs.display !== 'none' && cs.visibility !== 'hidden' && +cs.opacity !== 0;
  };
"""

# --- I: 반복 선택지의 식별값 --------------------------------------------------
# 같은 data-action 을 공유하는 요소가 둘 이상이면 그것은 "고르는 것들" 이다 -
# 은행 목록이든 숫자판이든 받는 사람 목록이든. 각 요소를 가리키는 값은
# data-action 이 아닌 다른 data-* 를 우선 쓰고, 없으면 보이는 글자를 쓴다.
# 스크립트가 만들어 넣는 목록도 있으므로 렌더링된 DOM 에서 모은다.
#
# 인자는 원본에서 무리였던 이름들이다 (checks/i_choices.original_groups). 무리는
# 원본이 정한다 - 그 이름의 요소는 생성물이 분류마다 하나씩 따로 놓았든 한곳에
# 모았든 형제 수와 상관없이 모두 센다. 원본을 걸을 때는 빈 목록이고, 목록에 없는
# 이름은 형제 둘 이상일 때만 무리다 (뒤로가기 같은 버튼이 무리가 되지 않게).
#
# CHOICE_SHOWN (11-8 2-3) 은 같은 무리 가운데 **지금 누를 수 있게 보이는** 요소의 값만
# 모은다 - 검사 K 의 입구와 같은 PRESSABLE (그려져 있고 크기 > 0, 자신이나 조상이 숨기지
# 않았고 - 닫힌 <details> 안 포함 - disabled 가 아니다). 무리를 정하는 규칙은 CHOICE_GROUPS 와 한 글자도 다르지 않게
# 같은 글에서 만든다 (아래 _CHOICES). 보이는 값이 하나뿐이어도 그 무리의 값이다. 검사 I 가
# "문서 안에만 있고 어느 상태에서도 보이지 않는 값" 을 이것으로 가른다.
_CHOICES = r"""
(known) => {
  const fixed = new Set(known || []);
  const groups = {};
  document.querySelectorAll('[data-action]').forEach(el => {
    const a = el.getAttribute('data-action');
    if (!a) return;
    (groups[a] = groups[a] || []).push(el);
  });
  const out = {};
  for (const action of Object.keys(groups)) {
    let els = [];
    if (fixed.has(action)) {
      // 원본에서 무리였던 이름 - 놓인 모양과 상관없이 모두 센다.
      els = groups[action];
    } else {
      // 같은 부모 아래 나란히 있는 것만 선택지다. 뒤로가기처럼 화면마다 하나씩
      // 놓인 같은 동작의 버튼은 "고르는 것들" 이 아니므로 제외한다.
      const byParent = new Map();
      groups[action].forEach(el => {
        const p = el.parentElement;
        if (!p) return;
        if (!byParent.has(p)) byParent.set(p, []);
        byParent.get(p).push(el);
      });
      // 같은 선택지가 여러 묶음에 나뉘어 있을 수 있다 - 원본은 은행 38개와
      // 증권사 29개를 탭으로 갈라 두었다. 둘 다 고를 수 있는 값이므로 합친다.
      byParent.forEach(sibs => { if (sibs.length >= 2) els = els.concat(sibs); });
      if (els.length < 2) continue;          // 형제가 둘 이상이어야 선택지다
    }
    __FILTER__
    const vals = [];
    els.forEach(el => {
      let v = null;
      for (const k in el.dataset) {
        if (k === 'action') continue;
        const x = (el.dataset[k] || '').trim();
        if (x) { v = x; break; }
      }
      if (!v) v = (el.textContent || '').trim();
      if (v && v.length <= 40) vals.push(v);
    });
    const uniq = Array.from(new Set(vals));
    // 원본의 무리는 값이 하나만 보여도 그 무리의 값이다.
    if (uniq.length >= __AT_LEAST__) out[action] = uniq;
  }
  return out;
}
"""
CHOICE_GROUPS = (_CHOICES.replace("    __FILTER__\n", "")
                 .replace("__AT_LEAST__", "(fixed.has(action) ? 1 : 2)"))
CHOICE_SHOWN = (_CHOICES.replace("__FILTER__", PRESSABLE.strip()
                                 + "\n    els = els.filter(pressable);")
                .replace("__AT_LEAST__", "1"))


# --- K: 과제 밖 입구 ------------------------------------------------------------
# 과제 밖 입구(과제 파일의 entrances)는 원본의 data-action 이름(oos-*)으로 찾는다.
# 이름마다 지금 누를 수 있게 보이는가(PRESSABLE - 아래)와, 기록용으로
# 그 요소의 글자 · aria-label 을 모은다 - 글자는 판정에 쓰지 않는다 (11-7b).
# 같은 이름이 여럿이면 보이는 것 하나를 고른다. 문서 전체를 보지만 숨은 화면 안의
# 요소는 크기가 0 이라 보이지 않는 것이 된다 - 그 화면에 도착한 걸음에서 보인다.
#
# 보이는 요소에는 `scroll_px` 도 잰다 (11-8, 기록만 - 검사 K 의 entrance_distance). 그
# 화면 맨 위에서(모든 스크롤을 0 으로 되돌린 자리에서) 요소 전체가 창 안에 들어오기까지
# 내려야 하는 거리다. 첫 화면 안이면 0. 실제로 스크롤하지 않는다 - 지금 위치에 조상들의
# scrollTop 을 더해 셈한다 (걷기가 버튼을 누르느라 내려가 있어도 같은 값). 고정(fixed ·
# sticky)된 것은 스크롤과 함께 움직이지 않으므로 0 이다. 세로만 잰다 - 옆으로 넘기는
# 띠 안의 위치와 덮개에 가려진 것은 재지 않는다. 같은 이름이 여럿 보이면 덜 내려도 되는
# 것을 고른다. 보이지 않는 요소는 null 이다.
ENTRANCE_PREFIX = "oos-"

ENTRANCES = r"""
() => {
  const out = {};
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  __PRESSABLE__
  const shown = pressable;
  const docY = () => (document.scrollingElement || document.documentElement).scrollTop;
  /* el 을 담은, 지금 스크롤할 수 있는 조상들 */
  const scrollers = el => {
    const got = [];
    for (let n = el.parentElement; n && n !== document.body
         && n !== document.documentElement; n = n.parentElement) {
      if (/(auto|scroll|overlay)/.test(getComputedStyle(n).overflowY)
          && n.scrollHeight > n.clientHeight + 1) got.push(n);
    }
    return got;
  };
  const pinned = el => {
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      if (/^(fixed|sticky)$/.test(getComputedStyle(n).position)) return true;
    }
    return false;
  };
  /* 모든 스크롤이 0 일 때의 세로 위치로 옮기는 값 */
  const shift = el => scrollers(el).reduce((s, n) => s + n.scrollTop, 0) + docY();
  const scrollPx = el => {
    if (pinned(el)) return 0;
    const r = el.getBoundingClientRect(), d = shift(el);
    const top = r.top + d, bottom = r.bottom + d;
    let viewTop = 0, viewBottom = window.innerHeight;
    for (const n of scrollers(el)) {
      const nr = n.getBoundingClientRect();
      const nt = nr.top + shift(n) + n.clientTop;
      viewTop = Math.max(viewTop, nt);
      viewBottom = Math.min(viewBottom, nt + n.clientHeight);
    }
    /* 아래 끝이 창 아래 끝에 닿을 때까지. 창보다 큰 요소는 위 끝이 창 위 끝에 올 때까지 */
    return Math.max(0, Math.round(Math.min(bottom - viewBottom, top - viewTop)));
  };
  document.querySelectorAll('[data-action^="__PREFIX__"]').forEach(el => {
    const a = el.getAttribute('data-action');
    const parts = [];
    const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) {
      const t = clean(n.nodeValue);
      if (t) parts.push(t);
    }
    const visible = shown(el);
    const row = {visible: visible, text: parts.join(' '),
                 aria: clean(el.getAttribute('aria-label')),
                 scroll_px: visible ? scrollPx(el) : null};
    const old = out[a];
    if (!old || (row.visible && !old.visible)
        || (row.visible && old.visible && row.scroll_px < old.scroll_px)) out[a] = row;
  });
  return out;
}
""".replace("__PREFIX__", ENTRANCE_PREFIX).replace("__PRESSABLE__", PRESSABLE.strip())
