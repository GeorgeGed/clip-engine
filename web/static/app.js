'use strict';
/* The site, on live data. The prototype's three screens, reading the same
   pipeline the agent runs — no inlined fixtures anywhere. */

const POLL = 2000;
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const el = (t, c, x) => { const n = document.createElement(t);
  if (c) n.className = c; if (x !== undefined) n.textContent = x; return n; };
const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`;
const pad = (n) => String(n).padStart(2, '0');

const S = { jobs: [], jobId: null, job: null, cands: [], detail: null,
            view: 'results', filter: 'usable', sort: 'score', likes: {} };

async function api(path, opts) {
  const r = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...opts });
  const b = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(b.error || `${r.status} ${r.statusText}`);
  return b;
}
function toast(m) {
  const t = $('#toast'); t.textContent = m; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => { t.hidden = true; }, 2800);
}
function show(v) {
  S.view = v;
  $$('.view').forEach((s) => { s.hidden = s.id !== 'v-' + v; });
  $$('nav button').forEach((b) => b.setAttribute('aria-current', String(b.dataset.go === v)));
  window.scrollTo({ top: 0, behavior: 'instant' });
}

/* ─────────────────────────────── state ─────────────────────────────────── */
const built = () => new Set((S.job?.clips || []).map((c) => c.index));
function stateOf(c) {
  if (built().has(c.n)) return 'rendered';
  return c.verdict === 'build' ? 'cuttable' : 'blocked';
}
const STATE = { rendered: ['ok', 'Rendered'], cuttable: ['warn', 'Ready to cut'],
                blocked: ['no', 'Refused'] };
const FILTERS = [['usable', 'Usable'], ['rendered', 'Rendered'],
                 ['cuttable', 'Ready to cut'], ['blocked', 'Refused'],
                 ['all', 'Everything']];
const inFilter = (c, k) => k === 'all' ? true
  : k === 'usable' ? stateOf(c) !== 'blocked' : stateOf(c) === k;

/* ─────────────────────────────── the rail ──────────────────────────────── */
function rail(host) {
  if (!host || !S.job) return;
  const sig = S.job.stages.map((s) => `${s.key}:${s.state}:${s.code}`).join(',')
    + '|' + JSON.stringify(S.job.progress || {});
  if (host.dataset.sig === sig) return;
  host.dataset.sig = sig;
  host.textContent = '';
  S.job.stages.forEach((s) => {
    const d = el('div', 'step ' + (s.state === 'done' ? 'done'
      : s.state === 'running' ? 'on' : s.state === 'failed' ? 'bad' : ''));
    d.append(el('div', 'i', s.state === 'done' ? '' : ''));
    const b = el('div');
    b.append(el('div', 'k', s.label));
    const p = S.job.progress || {};
    const sub = s.state === 'running'
      ? (p.total ? `${p.done}/${p.total} · ${p.line || ''}` : (p.line || 'running'))
      : s.state === 'failed' ? `failed (exit ${s.code})` : s.state;
    b.append(el('div', 'd', String(sub).slice(0, 110)));
    d.append(b); host.append(d);
  });
}

/* ─────────────────────────────── results ───────────────────────────────── */
function tally() {
  const n = (f) => S.cands.filter((c) => inFilter(c, f)).length;
  const secs = (S.job?.clips || []).length;
  const t = $('#tally'); t.textContent = '';
  [[S.cands.length, 'moments scored'], [n('usable'), 'can be cut'],
   [n('rendered'), 'rendered'], [secs ? `${secs}` : '0', 'delivered']]
    .forEach(([v, k]) => {
      const d = el('div'); d.append(el('b', 'num', String(v)), el('span', '', k));
      t.append(d);
    });
  $('#foot-yield').textContent = S.cands.length
    ? `${n('usable')} of ${S.cands.length} candidates can be cut · ${n('rendered')} rendered`
    : '';
}

function filters() {
  const f = $('#filters'); f.textContent = '';
  FILTERS.forEach(([k, label]) => {
    const b = el('button', 'seg'); b.type = 'button';
    b.setAttribute('aria-pressed', String(k === S.filter));
    b.append(document.createTextNode(label),
             el('span', 'c', String(S.cands.filter((c) => inFilter(c, k)).length)));
    b.addEventListener('click', () => { S.filter = k; filters(); cards(); });
    f.append(b);
  });
}

function card(c) {
  const st = stateOf(c), [tag, label] = STATE[st];
  const isBuilt = st === 'rendered';
  const d = el('div', 'c');
  const top = el('div', 'top');
  if (isBuilt) {
    const img = document.createElement('img');
    img.src = `/api/jobs/${S.jobId}/frame/${pad(c.n)}?t=2&w=250`;
    img.alt = ''; img.loading = 'lazy';
    const v = document.createElement('video');
    v.className = 'prev'; v.src = `/api/jobs/${S.jobId}/clip/${pad(c.n)}`;
    v.muted = true; v.loop = true; v.playsInline = true; v.preload = 'none';
    top.append(img, v);
    top.addEventListener('pointerenter', () => { v.classList.add('on'); v.play().catch(() => {}); });
    top.addEventListener('pointerleave', () => { v.classList.remove('on'); v.pause(); });
  } else {
    // The raw region, 16:9, because nothing has reframed it yet — the tile
    // says at a glance which clips are actually cut.
    const b = el('div', 'blank');
    const img = document.createElement('img');
    img.className = 'raw'; img.loading = 'lazy';
    img.src = `/api/jobs/${S.jobId}/thumb/${pad(c.n)}`;
    img.addEventListener('error', () => img.remove());
    b.append(img, el('div', 'at num', 'at ' + mmss(c.at)),
             el('div', 'st', st === 'cuttable'
               ? (c.window ? `Cut to ${Math.round(c.window.in)}–${Math.round(c.window.out)}s`
                           : 'Cuttable — not reframed yet')
               : 'Not cut'));
    top.append(b);
  }
  top.append(el('div', 'dur num', Math.round(c.secs) + 's'));
  const sc = el('div', 'score');
  sc.append(el('b', 'num', String(c.score)));
  const m = el('span', 'm'); const i = el('i'); i.style.width = c.score + '%';
  m.append(i); sc.append(m);
  sc.title = `Score ${c.score} · strength ${c.strength}`;
  top.append(sc);

  const body = el('div', 'body');
  body.append(el('div', 'ttl', c.subject || `Clip ${c.n}`));
  if (c.claim) body.append(el('div', 'sub', c.claim));
  const tags = el('div', 'tags');
  tags.append(el('span', 'tag ' + tag, label));
  if (c.genre) tags.append(el('span', 'tag', c.genre));
  if (c.muted != null) tags.append(el('span', 'tag', Math.round(c.muted * 100) + '% muted'));
  if (c.window) tags.append(el('span', 'tag', 'windowed'));
  body.append(tags);
  d.append(top, body);
  if (st === 'blocked' && c.block) d.append(el('div', 'blocked', c.block));

  const foot = el('div', 'foot');
  if (isBuilt) {
    const o = el('button', 'btn sm', 'Open'); o.type = 'button';
    o.addEventListener('click', () => editor(c.n));
    const a = el('a', 'chip', 'Download');
    a.href = `/api/jobs/${S.jobId}/clip/${pad(c.n)}?download=1`;
    foot.append(o, a);
  } else if (st === 'cuttable') {
    const q = el('button', 'btn quiet sm', 'Cut it'); q.type = 'button';
    q.addEventListener('click', async () => {
      q.disabled = true;
      try { await api(`/api/jobs/${S.jobId}/build/${c.n}`, { method: 'POST' });
            toast(`Clip ${c.n} queued — one at a time, Resolve is a single app`); }
      catch (e) { toast(e.message); q.disabled = false; }
      refresh();
    });
    foot.append(q);
  } else {
    const q = el('button', 'btn quiet sm', 'Why?'); q.type = 'button';
    q.addEventListener('click', () => toast(c.block || 'nothing left after tightening'));
    foot.append(q);
  }
  d.append(foot);
  return d;
}

function cards() {
  const g = $('#cards');
  let rows = S.cands.filter((c) => inFilter(c, S.filter));
  rows = S.sort === 'score'
    ? rows.sort((a, b) => b.score - a.score || a.n - b.n)
    : rows.sort((a, b) => a.at - b.at);
  // REBUILD ONLY WHEN SOMETHING CHANGED. The page polls every two seconds,
  // and replacing the grid each tick tears the card out from under a click
  // and stops a hover preview mid-play. Same defect as the job list losing
  // a click, one layer up — and it only shows when something is running.
  const sig = [S.filter, S.sort,
    rows.map((c) => `${c.n}:${stateOf(c)}:${c.score}`).join(',')].join('|');
  if (g.dataset.sig === sig) return;
  g.dataset.sig = sig;
  g.textContent = '';
  if (!rows.length) g.append(el('p', 'sub', 'Nothing here yet.'));
  rows.forEach((c) => g.append(card(c)));
  const dl = $('#dlall');
  dl.hidden = !(S.job?.clips || []).length;
  dl.href = `/api/jobs/${S.jobId}/clips.zip`;
}

/* ─────────────────────────────── editor ────────────────────────────────── */
const STOP = new Set(('about above after again against because before being below between could '
  + 'doing during each from further having into itself might more most other over same should '
  + 'some such than that their them then there these they this those through under until very '
  + 'were what when where which while will with would your').split(/\s+/));
const bare = (w) => (w || '').toLowerCase().replace(/[^a-z']/g, '');
const keysOf = (claim) => new Set((claim || '').toLowerCase().match(/[a-z']+/g)
  ?.filter((w) => w.length >= 5 && !STOP.has(w)) || []);

async function editor(n) {
  show('editor');
  $('#etitle').textContent = 'loading…';
  let d;
  try { d = await api(`/api/jobs/${S.jobId}/detail/${pad(n)}`); }
  catch (e) { $('#etitle').textContent = 'could not open clip ' + n; toast(e.message); return; }
  if (d.error) { $('#etitle').textContent = `clip ${n}`; toast(d.error); return; }
  S.detail = d;
  $('#etitle').textContent = d.hook || d.subject || `Clip ${n}`;
  const vid = $('#evid');
  vid.poster = `/api/jobs/${S.jobId}/frame/${pad(n)}?t=2&w=540`;
  vid.src = d.built ? `/api/jobs/${S.jobId}/clip/${pad(n)}` : '';
  $('#dl1').href = `/api/jobs/${S.jobId}/clip/${pad(n)}?download=1`;

  const strip = $('#strip'); strip.textContent = '';
  (d.strip || []).forEach((t, i) => {
    const im = document.createElement('img');
    im.src = `/api/jobs/${S.jobId}/frame/${pad(n)}?t=${t}&w=84`;
    im.alt = ''; im.loading = 'lazy';
    im.addEventListener('click', () => {
      vid.currentTime = t;
      strip.querySelectorAll('img').forEach((x) => x.classList.toggle('on', x === im));
    });
    strip.append(im);
  });
  const tl = $('#tl'); tl.textContent = '';
  const fill = el('i'); tl.append(fill);
  vid.ontimeupdate = () => { fill.style.width = (vid.currentTime / d.dur * 100) + '%'; };
  (d.booms || []).forEach((b) => {
    const mk = el('b'); mk.style.left = (b.t / d.dur * 100) + '%';
    mk.title = `boom ${b.t}s`; tl.append(mk);
  });
  const m = $('#emeta'); m.textContent = '';
  ['1080×1920', `${d.dur}s`, d.mb ? `${d.mb} MB` : 'not built',
   `${d.splices} splices`].forEach((x) => m.append(el('span', '', x)));

  // transcript
  const keys = keysOf(d.claim), booms = (d.booms || []).map((b) => b.t);
  const tx = $('#tx'); tx.textContent = '';
  (d.words || []).forEach((w) => {
    const s = el('span', '', w.w + ' ');
    if (keys.has(bare(w.w))) s.classList.add('emph');
    if (booms.some((b) => Math.abs(b - w.t) < 0.45)) s.classList.add('boom');
    s.title = w.t.toFixed(2) + 's';
    s.addEventListener('click', () => {
      if (vid.src) { vid.currentTime = Math.max(0, w.t - 0.15); vid.play().catch(() => {}); }
    });
    tx.append(s);
  });
  const kv = $('#txkv'); kv.textContent = '';
  [['Words in the cut', (d.words || []).length],
   ['Audio splices', d.splices], ['Runtime', d.dur + 's']]
    .forEach(([k, v]) => kv.append(el('dt', '', k), el('dd', 'num', String(v))));

  // the cut — the five fields review actually changes
  const p1 = $('#p1'); p1.textContent = '';
  p1.append(el('p', 'sub', 'These are the fields every round of review has changed. '
    + 'Everything else is house style and lives in code.'));
  const mk = (key, label, val, ph) => {
    const f = el('div', 'f'); f.append(el('span', '', label));
    const i = document.createElement('input');
    i.type = 'text'; i.id = `f-${key}`; i.dataset.key = key;
    i.value = val === null || val === undefined ? '' : val;
    i.placeholder = ph || ''; f.append(i); p1.append(f); return i;
  };
  mk('in_point', 'in', d.in, 'seconds');
  mk('out_point', 'out', d.out, 'end of region');
  mk('booms', 'booms', (d.specBooms || []).join(', '),
     (d.booms || []).map((b) => b.t).join(', ') || 'auto');
  mk('chat_mode', 'chat', d.chat, 'auto');
  mk('hook', 'hook', d.hook, 'clickbait line');
  const note = el('div', 'f'); note.append(el('span', '', 'why'));
  const ni = document.createElement('input');
  ni.type = 'text'; ni.id = 'f-note';
  ni.placeholder = 'appended to the spec notes';
  note.append(ni); p1.append(note);

  // sound
  const p2 = $('#p2'); p2.textContent = '';
  p2.append(el('p', 'sub', `One boom per ~22 seconds of runtime, and only on a moment `
    + `the clip itself calls a point. Budget here: ${d.budget}.`));
  const sk = el('dl', 'kv');
  ((d.booms || []).length ? d.booms : [null]).forEach((b, i) => {
    sk.append(el('dt', '', b ? `Boom ${i + 1}` : 'Booms'),
      el('dd', 'num', b ? `${b.t.toFixed(2)}s · +${b.db} dB over his baseline`
                        : 'none — no qualifying moment'));
  });
  p2.append(sk);
  if ((d.gated || []).length) {
    p2.append(el('p', 'sub', 'Refused: ' + d.gated
      .map((g) => `“${g.word}” — “${g.by}” demotes the clause`).join('; ') + '.'));
  }

  $('#rebuild').onclick = async () => {
    const spec = {};
    p1.querySelectorAll('[data-key]').forEach((i) => { spec[i.dataset.key] = i.value; });
    const msg = $('#emsg'); msg.textContent = 'saving…';
    try {
      await api(`/api/jobs/${S.jobId}/spec/${n}`, { method: 'POST',
        body: JSON.stringify({ spec, note: ni.value }) });
      await api(`/api/jobs/${S.jobId}/build/${n}`, { method: 'POST' });
      msg.textContent = 'saved, rebuild queued';
      refresh();
    } catch (e) { msg.textContent = e.message; }
  };
  $('#guides').onclick = () => {
    const off = $('#canvas').classList.toggle('noguide');
    $('#guides').setAttribute('aria-pressed', String(!off));
    $('#guides').textContent = off ? 'Show guides' : 'Hide guides';
  };
}

/* ─────────────────────────────── polling ───────────────────────────────── */
async function loadCands() {
  if (S.jobId == null) { S.cands = []; return; }
  try { S.cands = await api(`/api/jobs/${S.jobId}/candidates`); }
  catch { S.cands = []; }
}

async function refresh() {
  let jobs;
  try { jobs = await api('/api/jobs'); } catch { return; }
  S.jobs = jobs;
  if (S.jobId == null && jobs.length) S.jobId = jobs[0].id;
  S.job = jobs.find((j) => j.id === S.jobId) || null;

  const pick = $('#projpick');
  const sig = jobs.map((j) => `${j.id}:${j.name}:${j.state}`).join('|');
  if (pick.dataset.sig !== sig) {
    pick.dataset.sig = sig; pick.textContent = '';
    jobs.forEach((j) => {
      const o = el('option', '', `${j.name} · ${j.state}`); o.value = j.id; pick.append(o);
    });
    if (!jobs.length) pick.append(el('option', '', 'no projects yet'));
  }
  if (S.jobId != null) pick.value = S.jobId;

  if (S.job) {
    $('#rtitle').textContent = S.job.name;
    $('#rstate').textContent = S.job.active
      ? `running · ${S.job.active_stage}` : S.job.state;
    const n = S.cands.length;
    if (!n || S.cands._for !== S.jobId) { await loadCands(); S.cands._for = S.jobId; }
    tally(); rail($('#steps2')); rail($('#steps'));
    // Leave the grid alone while the editor is open or a field has focus.
    if (S.view !== 'editor' && !$('#cards').contains(document.activeElement)) {
      filters(); cards();
    }
  }
  try {
    const d = await api('/api/doctor');
    $('#agent').textContent = d.ok ? 'Resolve ready' : 'Resolve offline';
    $('#agent').style.color = d.ok ? 'var(--good)' : 'var(--warn)';
    $('#foot-agent').textContent = d.ok
      ? 'Renders on this Mac · one job at a time'
      : 'Resolve is not reachable — everything up to Specs will still run';
  } catch { /* server restarting */ }
}

/* ─────────────────────────────── boot ──────────────────────────────────── */
let lookedUp = '';
async function lookup() {
  const v = $('#src').value.trim(); const out = $('#found');
  if (!/\/videos?\/\d+/.test(v) || v === lookedUp) return;
  lookedUp = v; out.hidden = false; out.textContent = 'looking up…';
  try {
    const d = await api(`/api/lookup?url=${encodeURIComponent(v)}`);
    if (d.channel && !$('#chan').value.trim()) $('#chan').value = d.channel;
    out.textContent = '';
    out.append(el('span', 'kb'), el('b', '', d.channel),
               el('span', 'num', d.duration), el('span', 't', d.title));
  } catch (e) { out.textContent = `could not look that up — ${e.message}`; }
}

function boot() {
  $$('nav button').forEach((b) => b.addEventListener('click', () => {
    if (b.dataset.go !== 'editor') return show(b.dataset.go);
    const first = (S.job?.clips || [])[0];
    if (first) editor(first.index); else toast('Nothing built yet');
  }));
  $('#back').addEventListener('click', () => show('results'));
  $('#projpick').addEventListener('change', async (e) => {
    S.jobId = Number(e.target.value); S.cands = []; await refresh();
  });
  $('#sorts').addEventListener('click', (e) => {
    const b = e.target.closest('.seg'); if (!b) return;
    $$('#sorts .seg').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    S.sort = b.textContent.trim() === 'Score' ? 'score' : 'order'; cards();
  });
  $('#src').addEventListener('change', lookup);
  $('#src').addEventListener('paste', () => setTimeout(lookup, 60));
  $('#upload').addEventListener('click', () =>
    toast('Paste its path — a VOD already on this Mac is adopted in place, not uploaded'));
  $('#go').addEventListener('click', async () => {
    const body = { url: $('#src').value.trim(), channel: $('#chan').value.trim(),
                   rights: $('#rights').value, note: $('#note').value.trim() };
    $('#go').disabled = true; $('#gohint').textContent = 'starting…';
    try {
      const out = await api('/api/jobs', { method: 'POST', body: JSON.stringify(body) });
      S.jobId = out.id; S.cands = [];
      $('#gohint').textContent = `queued as ${out.name}`;
      await refresh(); show('results');
    } catch (e) { $('#gohint').textContent = e.message; }
    $('#go').disabled = false;
  });
  $('#tabs').addEventListener('click', (e) => {
    const b = e.target.closest('button'); if (!b) return;
    const i = [...$('#tabs').children].indexOf(b);
    [...$('#tabs').children].forEach((x, k) => x.setAttribute('aria-selected', String(k === i)));
    [0, 1, 2].forEach((k) => { $('#p' + k).hidden = k !== i; });
  });
  $('#theme').addEventListener('click', () => {
    const now = document.documentElement.getAttribute('data-theme');
    const dark = now ? now === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
    document.documentElement.setAttribute('data-theme', dark ? 'light' : 'dark');
  });
  refresh();
  setInterval(refresh, POLL);
}
boot();
