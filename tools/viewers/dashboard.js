/* 내부 확인용 대시보드.
   데이터는 outputs/index.json 하나뿐이고, tools/build_index.py 가 만든다.
   이 파일은 읽기만 한다 - 파이프라인을 실행하거나 고치지 않는다. */
'use strict';

const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
const esc = s => String(s == null ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

let IX = null;            // index.json
let PAGE = 'home';

/* 원본을 포함한 전체 목록. 원본은 검사 대상이 아니라 비교 기준이다. */
function allBuilds(){
  return (IX.baseline ? [IX.baseline] : []).concat(IX.builds || []);
}
function buildById(id){ return allBuilds().find(b => b.id === id); }

/* ------------------------------------------------------------------ */
/* 1. 대시보드                                                          */
/* ------------------------------------------------------------------ */
function drawHome(){
  const rows = [];
  const base = IX.baseline;
  if (base){
    rows.push('<tr class="click" data-goto="' + base.id + '">' +
      '<td><b>' + esc(base.name) + '</b> <span class="tag t-dim">기준</span></td>' +
      '<td class="c-dim">–</td><td class="num c-dim">·</td><td class="num c-dim">·</td>' +
      '<td class="num">' + base.screens.length + '</td>' +
      '<td class="num c-dim">·</td>' +
      '<td class="mono">' + esc((base.flow || {}).name || '') + '</td>' +
      '<td class="mono">' + esc(base.when || '') + '</td></tr>');
  }
  (IX.builds || []).forEach(b => {
    const a = b.audit, m = a.metrics || {};
    const lc = (m.low_contrast_before != null && m.low_contrast_after != null)
      ? m.low_contrast_before + ' → ' + m.low_contrast_after : '·';
    rows.push('<tr class="click" data-goto="' + b.id + '">' +
      '<td><b>' + esc(b.name) + '</b></td>' +
      '<td>' + (a.passed ? '<span class="tag t-ok">통과</span>'
                         : '<span class="tag t-fatal">미통과</span>') + '</td>' +
      '<td class="num ' + (a.fatal ? 'c-fatal' : 'c-dim') + '">' + (a.fatal || '·') + '</td>' +
      '<td class="num ' + (a.warning ? 'c-warn' : 'c-dim') + '">' + (a.warning || '·') + '</td>' +
      '<td class="num">' + b.screens.length + '</td>' +
      '<td class="num">' + lc + '</td>' +
      '<td class="mono">' + esc((b.flow || {}).name || '') + '</td>' +
      '<td class="mono">' + esc(b.when || '') + '</td></tr>');
  });

  $('#home').innerHTML =
    '<h2>빌드</h2>' +
    '<p class="hint">행을 누르면 그 빌드의 검사 결과로 갑니다. ' +
    'fatal 이 있다는 것은 고장났다는 뜻이 아니라 검사기가 그 항목을 붙잡았다는 뜻입니다 — ' +
    '규칙 기반의 7건은 이 연구의 관측 결과입니다.</p>' +
    '<table><thead><tr><th>이름</th><th>통과</th><th class="num">fatal</th>' +
    '<th class="num">warning</th><th class="num">화면</th><th class="num">저대비(원본→빌드)</th>' +
    '<th>흐름</th><th>수정</th></tr></thead><tbody>' + rows.join('') + '</tbody></table>' +
    attemptsSlot() +
    '<h2 style="margin-top:24px">스크린샷</h2>' +
    '<p class="hint">' + Object.keys(IX.shot_dirs || {}).length + '개 폴더에 흩어져 있던 것을 ' +
    '빌드별로 묶었습니다. 화면 비교 탭에서 스크린샷 모드로 보면 서버 없이도 열립니다.</p>' +
    '<table><thead><tr><th>빌드</th><th class="num">화면</th><th class="num">스크린샷</th>' +
    '<th>출처 폴더</th></tr></thead><tbody>' +
    allBuilds().map(b => {
      const dirs = Array.from(new Set(Object.values(b.shots || {})
        .map(p => p.replace(/\/[^/]+$/, ''))));
      return '<tr><td>' + esc(b.name) + '</td><td class="num">' + b.screens.length + '</td>' +
        '<td class="num ' + (Object.keys(b.shots || {}).length ? '' : 'c-dim') + '">' +
        (Object.keys(b.shots || {}).length || '없음') + '</td>' +
        '<td class="mono">' + (dirs.join('<br>') || '–') + '</td></tr>';
    }).join('') + '</tbody></table>';

  $$('#home tr.click').forEach(tr => tr.onclick = () => {
    go('audit'); $('#audit-pick-' + tr.dataset.goto) &&
      ($('#audit-pick-' + tr.dataset.goto).checked = true);
    drawAudit();
  });
}

/* 자동 루프가 시도 이력을 채울 자리. 지금은 비어 있다는 사실만 알린다. */
function attemptsSlot(){
  const any = (IX.builds || []).some(b => (b.attempts || []).length);
  if (any) return '';
  return '<div class="box attempts"><b>시도 이력</b> — 생성-검사-재생성 루프가 돌면 ' +
    '여기에 빌드별로 "1차 실패 → 2차 통과" 가 쌓입니다. ' +
    'index.json 의 <span class="mono">builds[].attempts</span> 가 그 자리이며 지금은 비어 있습니다.</div>';
}

/* ------------------------------------------------------------------ */
/* 2. 화면 비교                                                         */
/* ------------------------------------------------------------------ */
let CMP = { mode: 'live', picks: [] };

function drawCompare(){
  const bs = allBuilds();
  if (!CMP.picks.length)
    CMP.picks = bs.slice(0, Math.min(2, bs.length)).map(b => b.id);

  const chips = bs.map(b =>
    '<span class="chip' + (CMP.picks.includes(b.id) ? ' on' : '') + '" data-pick="' + b.id + '">' +
    esc(b.name) + '</span>').join('');

  $('#compare').innerHTML =
    '<h2>화면 비교</h2>' +
    '<p class="hint">빌드를 2~4개 고르세요. 화면 이름이 빌드마다 달라(원본 account ↔ Run 1 accno+bank) ' +
    '자동으로 맞추지 않습니다. 각 칸에서 따로 고르는 편이 정확합니다.</p>' +
    '<div class="bar">' + chips +
      '<span style="margin-left:auto"></span>' +
      '<span class="chip' + (CMP.mode === 'live' ? ' on' : '') + '" data-mode="live">실행</span>' +
      '<span class="chip' + (CMP.mode === 'shot' ? ' on' : '') + '" data-mode="shot">스크린샷</span>' +
    '</div>' +
    (CMP.mode === 'shot'
      ? '<div class="box">스크린샷 모드는 outputs/shots 의 png 를 보여줍니다. ' +
        '서버가 없어도 열리고, 지금 파일이 아니라 <b>그때 찍힌 상태</b>를 봅니다.</div>' : '') +
    '<div class="cols" id="cols"></div>';

  $$('#compare [data-pick]').forEach(el => el.onclick = () => {
    const id = el.dataset.pick, i = CMP.picks.indexOf(id);
    if (i >= 0){ if (CMP.picks.length > 1) CMP.picks.splice(i, 1); }
    else if (CMP.picks.length < 4) CMP.picks.push(id);
    drawCompare();
  });
  $$('#compare [data-mode]').forEach(el => el.onclick = () => {
    CMP.mode = el.dataset.mode; drawCompare();
  });
  drawCols();
}

function drawCols(){
  const host = $('#cols');
  host.innerHTML = CMP.picks.map(id => {
    const b = buildById(id); if (!b) return '';
    const opts = b.screens.map(s =>
      '<option value="' + esc(s) + '">' + esc(s) + '</option>').join('');
    return '<div class="col" data-col="' + id + '">' +
      '<h3>' + esc(b.name) + '</h3>' +
      '<div class="ctl"><select data-sel="' + id + '">' + opts + '</select>' +
        (CMP.mode === 'live'
          ? '<a href="/' + b.html + '" target="_blank" class="chip">새 창</a>' : '') +
      '</div>' +
      '<div data-slot="' + id + '"></div>' +
    '</div>';
  }).join('');

  CMP.picks.forEach(id => {
    const sel = host.querySelector('[data-sel="' + id + '"]');
    if (!sel) return;
    sel.onchange = () => paintCol(id, sel.value);
    paintCol(id, sel.value);
  });
}

/* 실행 모드는 iframe 을 띄우고 그 안에서 해당 화면으로 보낸다.
   시제품은 show() 를 전역에 두지 않으므로, data-screen 클래스를 직접 바꾼다.
   프로토타입 코드를 고치지 않고 화면만 갈아끼우는 가장 단순한 방법이다. */
function paintCol(id, screen){
  const b = buildById(id);
  const slot = $('#cols [data-slot="' + id + '"]');
  if (!b || !slot) return;

  if (CMP.mode === 'shot'){
    const p = (b.shots || {})[screen];
    slot.innerHTML = p
      ? '<img src="/' + p + '" alt="' + esc(b.name + ' ' + screen) + '">' +
        '<div class="mono" style="margin-top:6px">' + esc(p) + '</div>'
      : '<div class="none">이 화면의 스크린샷이 없습니다<br><span class="mono">' +
        esc(screen) + '</span></div>';
    return;
  }
  let fr = slot.querySelector('iframe');
  if (!fr){
    slot.innerHTML = '<iframe></iframe>';
    fr = slot.querySelector('iframe');
    fr.addEventListener('load', () => showScreen(fr, slot.dataset.want || screen));
    fr.src = '/' + b.html;
  }
  slot.dataset.want = screen;
  showScreen(fr, screen);
}

function showScreen(fr, screen){
  try {
    const d = fr.contentDocument;
    if (!d || !d.querySelector('.screen')) return;
    d.querySelectorAll('[data-screen]').forEach(s =>
      s.classList.toggle('on', s.dataset.screen === screen));
    if (fr.contentWindow.__task) fr.contentWindow.__task.screen = screen;
  } catch (e) { /* 아직 로드 전 */ }
}

/* ------------------------------------------------------------------ */
/* 3. 검사 결과                                                         */
/* ------------------------------------------------------------------ */
let AUD = { picks: null, open: {} };

function drawAudit(){
  const withAudit = (IX.builds || []).filter(b => b.audit);
  if (!AUD.picks) AUD.picks = withAudit.length ? [withAudit[0].id] : [];

  const chips = withAudit.map(b =>
    '<span class="chip' + (AUD.picks.includes(b.id) ? ' on' : '') + '" data-apick="' + b.id + '">' +
    esc(b.name) + '</span>').join('');

  const picked = withAudit.filter(b => AUD.picks.includes(b.id));
  const letters = Object.keys(IX.check_names);

  let body = '';
  letters.forEach(c => {
    const per = picked.map(b => ({
      b, n: (b.audit.by_check || {})[c] || { fatal: 0, warning: 0 },
      down: (b.audit.stood_down || {})[c] || []
    }));
    const tf = per.reduce((s, x) => s + x.n.fatal, 0);
    const tw = per.reduce((s, x) => s + x.n.warning, 0);
    const alldown = per.length && per.every(x => x.down.length);
    const open = AUD.open[c];

    let counts = '';
    per.forEach(x => {
      counts += '<span class="tag ' + (x.n.fatal ? 't-fatal' : (x.n.warning ? 't-warn' : 't-dim')) +
        '" title="' + esc(x.b.name) + '">' +
        (picked.length > 1 ? esc(shortName(x.b.name)) + ' ' : '') +
        (x.n.fatal ? x.n.fatal + 'F' : '') + (x.n.fatal && x.n.warning ? ' ' : '') +
        (x.n.warning ? x.n.warning + 'W' : '') +
        (!x.n.fatal && !x.n.warning ? '0' : '') + '</span>';
    });

    // findings, 심각도 순
    let rows = '';
    picked.forEach(b => {
      ['fatal', 'warning'].forEach(sev => {
        (b.audit.findings[sev] || []).filter(f => (f.check || '?') === c).forEach(f => {
          const shot = (b.shots || {})[f.screen];
          rows += '<div class="f-row" data-shot="' + esc(shot || '') + '"' +
            ' data-cap="' + esc(b.name + ' · ' + (f.screen || '')) + '">' +
            '<span class="sev ' + (sev === 'fatal' ? 'f' : 'w') + '">' +
            (sev === 'fatal' ? '■' : '▲') + '</span>' +
            '<span class="scr">' + esc(f.screen || '—') + '</span>' +
            '<span class="tx">' + esc(f.detail) + '</span>' +
            (picked.length > 1 ? '<span class="build">' + esc(shortName(b.name)) + '</span>' : '') +
            '</div>';
        });
      });
    });
    per.forEach(x => x.down.forEach(d => {
      rows += '<div class="f-row"><span class="sev">·</span><span class="scr c-dim">생략</span>' +
        '<span class="tx c-dim">' + esc(d) + '</span>' +
        (picked.length > 1 ? '<span class="build">' + esc(shortName(x.b.name)) + '</span>' : '') +
        '</div>';
    }));
    if (!rows) rows = '<div class="f-row"><span class="sev">·</span>' +
      '<span class="tx c-dim">발견 없음</span></div>';

    body += '<div class="chk' + (open ? ' open' : '') + (alldown ? ' down' : '') + '" data-chk="' + c + '">' +
      '<div class="chk-h"><span class="id">' + c + '</span>' +
      '<span class="nm">' + esc(IX.check_names[c]) +
        (alldown ? ' <span class="c-dim">· 생략됨</span>' : '') + '</span>' +
      '<span class="counts">' + counts + '</span>' +
      '<span class="c-dim">' + (open ? '▾' : '▸') + '</span></div>' +
      '<div class="chk-b">' + rows + '</div></div>';
  });

  $('#audit').innerHTML =
    '<h2>검사 결과</h2>' +
    '<p class="hint">빌드를 여러 개 고르면 항목별로 나란히 셉니다. ' +
    'finding 을 누르면 그 화면 스크린샷이 오른쪽 아래에 뜹니다.</p>' +
    '<div class="bar">' + chips + '</div>' +
    '<div class="checks">' + body + '</div>' +
    metricsBlock(picked);

  $$('#audit [data-apick]').forEach(el => el.onclick = () => {
    const id = el.dataset.apick, i = AUD.picks.indexOf(id);
    if (i >= 0){ if (AUD.picks.length > 1) AUD.picks.splice(i, 1); }
    else AUD.picks.push(id);
    drawAudit();
  });
  $$('#audit .chk-h').forEach(h => h.onclick = () => {
    const c = h.parentElement.dataset.chk;
    AUD.open[c] = !AUD.open[c]; drawAudit();
  });
  $$('#audit .f-row[data-shot]').forEach(r => r.onclick = () => {
    if (r.dataset.shot) showShot(r.dataset.shot, r.dataset.cap);
  });
}

function shortName(n){
  return n.replace('재구성 ', '').replace('규칙 기반 ', '규칙 ').replace('수리본', '수리');
}

/* 지표는 접어 둔다 - 개수는 좋고 나쁨이 아니다. */
function metricsBlock(picked){
  if (!picked.length) return '';
  const keys = [];
  picked.forEach(b => Object.keys(b.audit.metrics || {}).forEach(k => {
    const v = b.audit.metrics[k];
    if ((typeof v === 'number' || typeof v === 'string') && !keys.includes(k)) keys.push(k);
  }));
  const rows = keys.map(k =>
    '<tr><td class="mono">' + esc(k) + '</td>' +
    picked.map(b => '<td class="num">' + esc(b.audit.metrics[k] != null ? b.audit.metrics[k] : '·') +
      '</td>').join('') + '</tr>').join('');
  return '<details class="metrics"><summary>지표 ' + keys.length + '개 — 개수는 좋고 나쁨이 아닙니다</summary>' +
    '<table><thead><tr><th>지표</th>' +
    picked.map(b => '<th class="num">' + esc(shortName(b.name)) + '</th>').join('') +
    '</tr></thead><tbody>' + rows + '</tbody></table></details>';
}

function showShot(path, cap){
  const p = $('#shotpane');
  p.innerHTML = '<div class="cap"><span>' + esc(cap) + '</span>' +
    '<button id="shot-x">✕</button></div><img src="/' + path + '">' +
    '<div class="mono" style="margin-top:6px">' + esc(path) + '</div>';
  p.classList.add('on');
  $('#shot-x').onclick = () => p.classList.remove('on');
}

/* ------------------------------------------------------------------ */
/* 4. 변경 추적                                                         */
/* ------------------------------------------------------------------ */
let CHG = { rule: '', only: '' };

function drawChanges(){
  const changes = IX.changes || [], rules = IX.rules || [];
  let list = changes.slice();
  if (CHG.only === 'uncovered') list = list.filter(c => c.uncovered || c.partial);
  if (CHG.rule) list = list.filter(c => c.rules.includes(CHG.rule));

  const ruleOpts = ['<option value="">규칙 전체</option>'].concat(
    Array.from(new Set(changes.flatMap(c => c.rules))).sort().map(r =>
      '<option value="' + esc(r) + '"' + (CHG.rule === r ? ' selected' : '') + '>' +
      esc(r) + '</option>')).join('');

  const rows = list.map(c =>
    '<tr><td class="num c-dim">' + (c.n == null ? '—' : c.n) + '</td>' +
    '<td>' + esc(c.before) + '</td><td>' + esc(c.after) + '</td>' +
    '<td class="c-dim">' + esc(c.why) + '</td>' +
    '<td class="rules">' + (c.rules.length
      ? c.rules.map(r => '<span class="rid">' + esc(r) + '</span>').join('')
      : '<span class="rid none">규칙 없음</span>') +
      (c.partial ? '<span class="rid none">부분</span>' : '') + '</td></tr>').join('');

  const cited = rules.filter(r => r.cited_by.length);
  const claimed = rules.filter(r => r.claimed_met && !r.cited_by.length);
  const shortfall = rules.filter(r => r.shortfall);
  const never = rules.filter(r => !r.cited_by.length && !r.claimed_met && !r.shortfall);

  $('#changes').innerHTML =
    '<h2>변경 추적</h2>' +
    '<p class="hint">docs/restructure-changelog.md 의 표를 그대로 읽은 것입니다. ' +
    '규칙 ID 는 사후에 붙인 것이라 "어떤 규칙이 이 변경을 만들었다"가 아니라 ' +
    '"결과적으로 이 규칙에 해당한다"는 뜻입니다.</p>' +
    '<div class="bar">' +
      '<select id="chg-rule">' + ruleOpts + '</select>' +
      '<span class="chip' + (CHG.only === 'uncovered' ? ' on' : '') + '" id="chg-unc">' +
      '규칙 없음·부분만</span>' +
      '<span class="c-dim">' + list.length + ' / ' + changes.length + '건</span>' +
    '</div>' +
    '<table><thead><tr><th class="num">#</th><th>원본</th><th>바꾼 내용</th><th>이유</th>' +
    '<th>규칙</th></tr></thead><tbody>' + rows + '</tbody></table>' +
    '<p class="hint" style="margin-top:8px">번호 없는 항목(—)은 용어 변경 절로, 원문에 번호가 없습니다.</p>' +

    '<h2 style="margin-top:26px">규칙 46개는 어떻게 됐나</h2>' +
    '<div class="box">표에서 실제로 인용된 것은 <b>' + cited.length + '개</b>입니다. ' +
    'changelog 는 스스로 <b>' + (cited.length + claimed.length) + '개</b>가 충족됐다고 적는데, ' +
    '그 차이인 ' + claimed.length + '개는 표에 근거 없이 저자가 판단한 것입니다. ' +
    '문서 자체가 "내가 내 결과물을 채점한 것이라 낙관 쪽으로 기운다"고 밝히고 있습니다.</div>' +
    '<div class="bar">' +
      '<span class="tag t-ok">표에서 인용 ' + cited.length + '</span>' +
      '<span class="tag t-acc">저자 판단만 ' + claimed.length + '</span>' +
      '<span class="tag t-warn">미충족·부분 ' + shortfall.length + '</span>' +
      '<span class="tag t-dim">언급 없음 ' + never.length + '</span>' +
    '</div>' +
    '<div class="kb-grid">' + rules.map(r => {
      const cls = r.cited_by.length ? 'cited' : (r.claimed_met ? 'claimed'
              : (r.shortfall ? 'short' : 'never'));
      const note = r.cited_by.length
        ? ('변경 ' + r.cited_by.filter(n => n != null).join(', ') + (r.cited_partially ? ' (부분)' : ''))
        : (r.claimed_met ? '저자 판단'
        : (r.shortfall ? esc(r.shortfall.state) : '언급 없음'));
      return '<div class="kb ' + cls + '"><div class="id">' + esc(r.id) +
        ' <span class="c-dim" style="font-weight:400">' + note + '</span></div>' +
        '<div class="txt">' + esc(r.content) + '</div></div>';
    }).join('') + '</div>';

  $('#chg-rule').onchange = e => { CHG.rule = e.target.value; drawChanges(); };
  $('#chg-unc').onclick = () => {
    CHG.only = CHG.only === 'uncovered' ? '' : 'uncovered'; drawChanges();
  };
}

/* ------------------------------------------------------------------ */
function go(page){
  PAGE = page;
  $$('.page').forEach(p => p.classList.toggle('on', p.id === page));
  $$('nav button').forEach(b => b.classList.toggle('on', b.dataset.page === page));
  if (page === 'home') drawHome();
  if (page === 'compare') drawCompare();
  if (page === 'audit') drawAudit();
  if (page === 'changes') drawChanges();
  location.hash = page;
}

async function load(){
  const r = await fetch('/outputs/index.json?t=' + Date.now());
  if (!r.ok) throw new Error('index.json 을 읽지 못했습니다 (' + r.status + '). ' +
    'python tools/build_index.py 를 먼저 돌리세요.');
  IX = await r.json();
  $('#when').textContent = IX.generated.replace('T', ' ');
  go(location.hash.replace('#', '') || 'home');
}

$$('nav button').forEach(b => b.onclick = () => go(b.dataset.page));
/* 파일을 고친 뒤 이 버튼만 누르면 되도록, 서버에 인덱스 재생성을 먼저 부탁한다.
   서버가 없으면(정적으로 연 경우) 그냥 index.json 을 다시 읽는다. */
$('#reload').onclick = async () => {
  const btn = $('#reload'), was = btn.textContent;
  btn.textContent = '읽는 중…'; btn.disabled = true;
  try { await fetch('/api/reindex'); } catch (e) { /* 정적으로 열었을 때 */ }
  try { await load(); } catch (e) { showErr(e); }
  btn.textContent = was; btn.disabled = false;
};
function showErr(e){
  $('#home').innerHTML = '<div class="box" style="border-color:var(--fatal)">' +
    esc(e.message) + '</div>';
  $('#home').classList.add('on');
}
load().catch(showErr);
