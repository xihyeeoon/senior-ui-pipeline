r"""In-page JavaScript probes used by tools/audit.py.

Kept separate from the driver so each probe can be read and tested on its own.
Every probe is scoped to the screen that is currently `.on`, except STATE_PAIRS
which inspects the stylesheet as a whole.
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

# --- D: elements whose colour is purely inherited -----------------------------
# The example1 / recipient failure mode: a repair adds a label with no colour of
# its own, it inherits something meant for a different context, and disappears.
INHERITED_COLOUR = r"""
() => {
  const s = document.querySelector('.screen.on');
  if (!s) return [];
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
  if (!s) return [];
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
  if (!s) return [];
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
  if (!s) return [];
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
