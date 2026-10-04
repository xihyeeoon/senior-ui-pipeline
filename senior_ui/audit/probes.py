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
INVENTORY = r"""
() => {
  const s = document.querySelector('.screen.on') || document.body;
  const attr = (sel, a) => Array.from(s.querySelectorAll(sel))
                                .map(e => e.getAttribute(a));
  return {
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
  /* opacity 는 자손 전체에 곱해진다. 요소 자신의 것만 보면 opacity:.3 인 상자
     안의 #111 글자가 #111 그대로 읽힌다 - 눈에는 #b8b8b8 로 보인다. */
  const opacityOf = el => {
    let o = 1;
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      const v = parseFloat(getComputedStyle(n).opacity);
      if (!isNaN(v)) o *= v;
      if (o <= 0) return 0;
    }
    return o;
  };
  const css = c => 'rgb(' + c.map(v => Math.round(v)).join(', ') + ')';
  /* Climb until an ancestor paints something opaque; body/html default to white. */
  const bgOf = el => {
    let n = el;
    while (n && n.nodeType === 1) {
      const c = parse(getComputedStyle(n).backgroundColor);
      if (c && c.a > 0.95) return c.rgb;
      n = n.parentElement;
    }
    return [255, 255, 255];
  };
  const ratio = (a, b) => {
    const l1 = lum(a), l2 = lum(b);
    return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
  };

  const out = [];
  document.querySelectorAll('*').forEach(el => {
    /* only elements holding their own text */
    const own = Array.from(el.childNodes)
      .filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join(' ').trim();
    if (!own) return;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none') return;
    /* 사실상 보이지 않는 글은 명암 결함이 아니다 - 글자색 알파와 같은 규칙. */
    const op = opacityOf(el);
    if (op < 0.05) return;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return;

    const fg = parse(cs.color);
    /* 완전히 투명한 글자는 명암 결함이 아니라 안 보이는 글이다 - 다른 일이다. */
    if (!fg || fg.a < 0.05) return;
    const bg = bgOf(el);
    const seen = over(fg.rgb, fg.a * op, bg);
    const size = parseFloat(cs.fontSize);
    const weight = parseInt(cs.fontWeight, 10) || 400;
    const large = size >= 24 || (size >= 18.66 && weight >= 700);
    const need = large ? 3.0 : 4.5;
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
  return out;
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
WRAPPED = r"""
() => {
  const s = document.querySelector('.screen.on');
  if (!s) return null;      /* 켜진 화면이 없다 - 잴 수 없었다는 뜻이다 */
  const out = [];
  s.querySelectorAll('*').forEach(el => {
    const own = Array.from(el.childNodes)
      .filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join(' ').trim();
    if (!own) return;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return;
    let lh = parseFloat(cs.lineHeight);
    if (!lh || isNaN(lh)) lh = parseFloat(cs.fontSize) * 1.2;
    const lines = Math.round(el.getBoundingClientRect().height / lh);
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

# --- H: classes the markup uses that no stylesheet defines --------------------
# example1 produced `bg-primary` / `text-primary`; this run produced `sr-only`.
# Both render as if the class were never written, which is how a "hidden" label
# ends up on screen.
UNDEFINED_CLASSES = r"""
() => {
  const defined = new Set();
  for (const sheet of document.styleSheets) {
    let rs;
    try { rs = sheet.cssRules; } catch (e) { continue; }
    for (const r of rs) {
      if (!r.selectorText) continue;
      for (const m of r.selectorText.matchAll(/\.([A-Za-z0-9_-]+)/g)) defined.add(m[1]);
    }
  }
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
STATE_PAIRS = r"""
() => {
  const STATES = ['on', 'act', 'active', 'selected', 'checked', 'disabled'];
  const rules = [];
  for (const sheet of document.styleSheets) {
    let rs;
    try { rs = sheet.cssRules; } catch (e) { continue; }
    for (const r of rs) if (r.selectorText && r.style) rules.push(r);
  }
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


# --- I: 반복 선택지의 식별값 --------------------------------------------------
# 같은 data-action 을 공유하는 요소가 둘 이상이면 그것은 "고르는 것들" 이다 -
# 은행 목록이든 숫자판이든 받는 사람 목록이든. 각 요소를 가리키는 값은
# data-action 이 아닌 다른 data-* 를 우선 쓰고, 없으면 보이는 글자를 쓴다.
# 스크립트가 만들어 넣는 목록도 있으므로 렌더링된 DOM 에서 모은다.
CHOICE_GROUPS = r"""
() => {
  const groups = {};
  document.querySelectorAll('[data-action]').forEach(el => {
    const a = el.getAttribute('data-action');
    if (!a) return;
    (groups[a] = groups[a] || []).push(el);
  });
  const out = {};
  for (const action of Object.keys(groups)) {
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
    let els = [];
    byParent.forEach(sibs => { if (sibs.length >= 2) els = els.concat(sibs); });
    if (els.length < 2) continue;          // 형제가 둘 이상이어야 선택지다
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
    if (uniq.length >= 2) out[action] = uniq;
  }
  return out;
}
"""
