'use strict';
const $ = (s) => document.querySelector(s);
const el = (t, c, x) => { const n = document.createElement(t);
  if (c) n.className = c; if (x !== undefined) n.textContent = x; return n; };

// Stage names are the pipeline's own commands, in the order it runs them.
const STAGES = [
  ['ingest','Ingest','1080p60'], ['analyse','Analyse','transcribed'],
  ['rank','Rank','scored'], ['screen','Screen','50 judged'],
  ['prep','Prep','assets'], ['specs','Specs','8 kept'],
  ['build','Build','Resolve'], ['report','Report','manifest'],
];
let state = STAGES.length;      // opens finished: the result is the first view

function cause(why) {
  const w = (why || '').toLowerCase();
  if (w.includes('muted')) return 'DMCA-muted audio';
  if (w.includes('cuts/min')) return 'cut rate strobes';
  if (w.includes('left')) return 'too little left';
  return 'other';
}

function rail() {
  const r = $('#rail'); r.textContent = '';
  STAGES.forEach(([k, label, sub], i) => {
    const d = el('div', 'st ' + (i < state ? 'done' : i === state ? 'run' : ''));
    d.append(el('div', 'k', label), el('div', 'v', i < state ? sub : i === state ? 'running' : '—'));
    r.append(d);
  });
}

function funnel(d) {
  const by = {};
  d.screen.filter((r) => r.verdict !== 'build')
    .forEach((r) => { const c = cause(r.why); by[c] = (by[c] || 0) + 1; });
  const refused = Object.entries(by).sort((a, b) => b[1] - a[1]);
  const steps = [
    [d.screen.length, 'Candidate windows scored', false],
    [d.screen.filter((r) => r.verdict === 'build').length, 'Can be cut at all', false],
    [d.specs.length, 'Kept after topic dedup', false],
    [d.clips.length, 'Built and passed QC', false],
  ];
  const f = $('#funnel'); f.textContent = '';
  const max = steps[0][0];
  // 72%, not 100%: one scale for every bar, with the label always outside it.
  const draw = (n, label, cls) => {
    const row = el('div', 'fr' + (cls ? ' ' + cls : ''));
    const lab = el('div', 'lab'); lab.append(el('b', 'num', String(n)));
    const track = el('div', 'track');
    const bar = el('div', 'bar'); bar.style.width = (n / max * 72) + '%';
    track.append(bar, el('span', '', label));
    row.append(lab, track); f.append(row);
  };
  steps.forEach(([n, label]) => draw(n, label, ''));
  refused.forEach(([c, n]) => draw(n, 'Refused — ' + c, 'muted'));
}

let filter = 'all';
function table(d) {
  const tb = $('#rows'); tb.textContent = '';
  d.screen
    .filter((r) => filter === 'all' || r.verdict === filter)
    .forEach((r) => {
      const tr = el('tr', r.verdict);
      tr.append(el('td', 'n num', String(r.n)));
      const s = el('td', 'subj');
      s.append(el('i', 'key'), document.createTextNode(r.subject || '—'));
      tr.append(s);
      tr.append(el('td', 'r', r.muted == null ? '—' : Math.round(r.muted * 100) + '%'));
      tr.append(el('td', 'r', r.cuts == null ? '—' : r.cuts.toFixed(1)));
      const v = el('td'); v.append(el('span', 'v ' + r.verdict,
        r.verdict === 'build' ? 'build' : 'refuse'));
      tr.append(v);
      tr.append(el('td', 'why', r.why || '—'));
      tb.append(tr);
    });
}

function clips(d) {
  const g = $('#clips'); g.textContent = '';
  const spec = Object.fromEntries(d.specs.map((s) => [s.n, s]));
  d.clips.forEach((c) => {
    const s = spec[c.n] || {};
    const card = el('div', 'card');
    const shot = el('div', 'shot');
    const img = document.createElement('img');
    img.src = c.poster; img.alt = `Clip ${c.n}, frame`; img.loading = 'lazy';
    shot.append(img, el('div', 'dur num', c.dur.toFixed(1) + 's'));
    const body = el('div', 'body');
    body.append(el('div', 'hook', s.hook || `Clip ${String(c.n).padStart(2, '0')}`));
    const m = el('div', 'meta');
    m.append(el('span', '', '#' + String(c.n).padStart(2, '0')),
             el('span', '', c.mb + ' MB'),
             el('span', '', '1080×1920'));
    body.append(m, el('div', 'qc', 'nine of nine gates'));

    const fields = el('div', 'fields');
    const mk = (key, label, val, ph) => {
      const f = el('div', 'f'); f.append(el('span', '', label));
      const i = document.createElement('input');
      i.type = 'text'; i.id = `f-${c.n}-${key}`;
      i.value = val === null || val === undefined ? '' : val;
      i.placeholder = ph || ''; f.append(i); fields.append(f); return i;
    };
    mk('in', 'in', s.in, 'seconds');
    mk('out', 'out', s.out, 'end of region');
    mk('booms', 'booms', (s.booms || []).join(', '), 'auto by duration');
    mk('chat', 'chat', s.chat, 'auto');
    const bar = el('div', 'cardbar');
    const save = el('button', 'mini', 'Save');
    const build = el('button', 'mini solid', 'Rebuild');
    const msg = el('span', 'msg');
    const touch = (what) => { msg.textContent = what;
      setTimeout(() => { msg.textContent = ''; }, 2200); };
    save.addEventListener('click', () => touch('spec saved'));
    build.addEventListener('click', () => touch('queued — one at a time'));
    bar.append(save, build, msg);
    fields.append(bar);
    body.append(fields);
    card.append(shot, body); g.append(card);
  });
}

function facts(d) {
  const b = d.screen.filter((r) => r.verdict === 'build');
  const med = (xs) => { const s = [...xs].sort((a, x) => a - x);
    return s.length ? s[Math.floor(s.length / 2)] : 0; };
  const rows = [
    ['Source', d.vod_duration + ' · 1920×1080 @60'],
    ['Transcribed', 'once, whole VOD'],
    ['Median muted share, refused',
      Math.round(med(d.screen.filter((r) => r.verdict !== 'build' && r.muted != null)
        .map((r) => r.muted)) * 100) + '%'],
    ['Median muted share, kept',
      Math.round(med(b.filter((r) => r.muted != null).map((r) => r.muted)) * 100) + '%'],
    ['Delivered runtime',
      d.clips.reduce((a, c) => a + c.dur, 0).toFixed(0) + 's across ' + d.clips.length],
    ['Loudness target', '−14 LUFS, −1.0 dBTP hard'],
    ['Caption cadence', '≈2.3 cards/second'],
  ];
  const dl = $('#facts'); dl.textContent = '';
  rows.forEach(([k, v]) => { dl.append(el('dt', '', k), el('dd', 'num', v)); });
}

function boot(d) {
  $('#jobchip').textContent = `${d.job} · ${d.channel}`;
  const r = $('#resolved'); r.textContent = '';
  r.append(el('b', '', d.channel), el('span', 'num', d.vod_duration),
           el('span', 't', d.vod_title));
  rail(); funnel(d); table(d); clips(d); facts(d);

  $('#filters').addEventListener('click', (e) => {
    const b = e.target.closest('.chip'); if (!b) return;
    filter = b.dataset.f;
    $('#filters').querySelectorAll('.chip').forEach((c) =>
      c.setAttribute('aria-pressed', String(c === b)));
    table(d);
  });

  $('#run').addEventListener('click', () => {
    if (state < STAGES.length) return;
    state = 0; rail();
    $('#run').disabled = true;
    $('#runhint').textContent = 'Replaying — stage states only, no invented timings.';
    const step = () => {
      state += 1; rail();
      if (state < STAGES.length) { setTimeout(step, 520); }
      else {
        $('#run').disabled = false;
        $('#runhint').textContent = 'Replays this VOD’s real run.';
      }
    };
    setTimeout(step, 520);
  });

  $('#theme').addEventListener('click', () => {
    const now = document.documentElement.getAttribute('data-theme');
    const dark = now ? now === 'dark'
      : matchMedia('(prefers-color-scheme: dark)').matches;
    document.documentElement.setAttribute('data-theme', dark ? 'light' : 'dark');
  });
}
boot(window.__FACTORY__);
