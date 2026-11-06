'use strict';
const D = window.__FACTORY__;
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const el = (t, c, x) => { const n = document.createElement(t);
  if (c) n.className = c; if (x !== undefined) n.textContent = x; return n; };
const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`;

const STOP = new Set(('about above after again against because before being below between '
  + 'could doing during each from further having into itself might more most other '
  + 'over same should some such than that their them then there these they this those '
  + 'through under until very were what when where which while will with would your'
  ).split(/\s+/));
// Emphasis is what the engine itself marks: content words of five letters or
// more taken from the clip's own claim. Not a guess made for this page.
function emphasisKeys(claim) {
  return new Set((claim || '').toLowerCase().match(/[a-z']+/g)?.filter(
    (w) => w.length >= 5 && !STOP.has(w)) || []);
}
const bare = (w) => (w || '').toLowerCase().replace(/[^a-z']/g, '');

let view = 'results', openN = null, verdictOf = {}, likes = {};
const STATE = {
  rendered: { tag: 'ok', label: 'Rendered' },
  cuttable: { tag: 'warn', label: 'Ready to cut' },
  blocked: { tag: 'no', label: 'Blocked' },
};
const clipOf = Object.fromEntries(D.clips.map((c) => [c.n, c]));
D.candidates.forEach((c) => {
  verdictOf[c.n] = clipOf[c.n] ? 'rendered'
    : c.verdict === 'build' ? 'cuttable' : 'blocked';
});

function toast(msg) {
  const t = $('#toast'); t.textContent = msg; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => { t.hidden = true; }, 2600);
}

function show(v) {
  view = v;
  $$('.view').forEach((s) => { s.hidden = s.id !== 'v-' + v; });
  $$('nav button').forEach((b) =>
    b.setAttribute('aria-current', String(b.dataset.go === v)));
  window.scrollTo({ top: 0, behavior: 'instant' });
}

/* ───────────────────────────── new project ─────────────────────────────── */
const STEPS = [
  ['Ingest', 'Pull it at 1080p60 and refuse anything softer'],
  ['Transcribe', 'Once, whole VOD — slicing it per region costs more audio'],
  ['Rank', 'Score every candidate window on strength, crowd and fit'],
  ['Screen', 'Decide which can be cut at all before anything renders'],
  ['Prep', 'Words, chat replay and the facecam rect, per clip'],
  ['Spec', 'Drop duplicate topics; one spec per surviving clip'],
  ['Build', 'Serial through Resolve — one GUI app, one timeline'],
  ['Gate', 'Measure the rendered file, not the plan'],
];
let stepAt = STEPS.length;
function steps() {
  const s = $('#steps'); s.textContent = '';
  STEPS.forEach(([k, d], i) => {
    const row = el('div', 'step ' + (i < stepAt ? 'done' : i === stepAt ? 'on' : ''));
    row.append(el('div', 'i', i < stepAt ? '' : String(i + 1)));
    const b = el('div'); b.append(el('div', 'k', k), el('div', 'd', d));
    row.append(b); s.append(row);
  });
}

/* ───────────────────────────── results ─────────────────────────────────── */
// USABLE IS THE DEFAULT, AND REFUSED IS ONE CLICK AWAY.
//
// George: "you gave it a 63 and yet it's blocked because it's 43% muted.
// Why are you even showing that to me if we can't even use it?" He is right
// — a high score on a clip that cannot be cut is a tease, and it was the
// first thing in the grid. The yield still matters, so the count stays in
// the tally and on the chip; what changes is that it no longer costs him
// the top of the page.
let filter = 'usable', sort = 'score';
const FILTERS = [
  ['usable', 'Usable'], ['rendered', 'Rendered'],
  ['cuttable', 'Ready to cut'], ['blocked', 'Refused'], ['all', 'Everything'],
];
const inFilter = (c, k) => k === 'all' ? true
  : k === 'usable' ? verdictOf[c.n] !== 'blocked'
  : verdictOf[c.n] === k;

function tally() {
  const n = (k) => D.candidates.filter((c) => verdictOf[c.n] === k).length;
  const t = $('#tally'); t.textContent = '';
  [[D.candidates.length, 'moments scored'], [n('rendered') + n('cuttable'), 'can be cut'],
   [D.clips.length, 'rendered'],
   [D.clips.reduce((a, c) => a + c.dur, 0).toFixed(0) + 's', 'delivered']]
    .forEach(([v, k]) => {
      const d = el('div'); d.append(el('b', 'num', String(v)), el('span', '', k));
      t.append(d);
    });
}

function filters() {
  const f = $('#filters'); f.textContent = '';
  FILTERS.forEach(([k, label]) => {
    const b = el('button', 'seg'); b.type = 'button';
    b.setAttribute('aria-pressed', String(k === filter));
    b.append(document.createTextNode(label));
    const n = D.candidates.filter((c) => inFilter(c, k)).length;
    b.append(el('span', 'c', String(n)));
    b.addEventListener('click', () => { filter = k; filters(); cards(); });
    f.append(b);
  });
}

function card(c) {
  const st = verdictOf[c.n], meta = STATE[st], built = clipOf[c.n];
  const d = el('div', 'c' + (likes[c.n] === -1 ? ' down' : ''));
  const top = el('div', 'top');
  if (built) {
    const img = document.createElement('img');
    img.src = built.poster; img.alt = ''; img.loading = 'lazy';
    // Preview on hover, like every clip grid does. preload="none" so forty
    // cards do not pull four videos before anyone asks.
    const v = document.createElement('video');
    v.className = 'prev'; v.src = `clips/${String(c.n).padStart(2, '0')}.mp4`;
    v.muted = true; v.loop = true; v.playsInline = true; v.preload = 'none';
    top.append(img, v, el('div', 'dur num', built.dur.toFixed(1) + 's'));
    top.addEventListener('pointerenter', () => {
      v.classList.add('on'); v.play().catch(() => {});
    });
    top.addEventListener('pointerleave', () => {
      v.classList.remove('on'); v.pause();
    });
  } else {
    // THE SOURCE FRAME, LETTERBOXED. It is 16:9 because nothing has reframed
    // it yet, and showing that is more use than a grey rectangle or a fake
    // vertical crop: the tile says at a glance which clips are cut.
    const b = el('div', 'blank');
    if (c.frame) {
      const im = document.createElement('img');
      im.src = c.frame; im.alt = ''; im.loading = 'lazy';
      im.className = 'raw';
      b.append(im);
    }
    b.append(el('div', 'at num', 'at ' + mmss(c.at)),
             el('div', 'st', st === 'cuttable'
               ? (c.window
                   ? `Cut to ${Math.round(c.window.in)}–${Math.round(c.window.out)}s`
                   : 'Cuttable — not reframed yet')
               : 'Not cut'));
    top.append(b, el('div', 'dur num', Math.round(c.secs) + 's'));
  }
  const sc = el('div', 'score');
  sc.append(el('b', 'num', String(c.score)));
  const m = el('span', 'm'); const i = el('i'); i.style.width = c.score + '%';
  m.append(i); sc.append(m);
  sc.title = `Score ${c.score} — strength ${c.strength}`;
  top.append(sc);

  const body = el('div', 'body');
  body.append(el('div', 'ttl', built && built.hook ? built.hook : c.subject));
  if (built && built.hook) body.append(el('div', 'sub', c.subject));
  else if (c.claim) body.append(el('div', 'sub', c.claim));
  const tags = el('div', 'tags');
  tags.append(el('span', 'tag ' + meta.tag, meta.label));
  if (c.genre) tags.append(el('span', 'tag', c.genre));
  if (c.muted != null) tags.append(el('span', 'tag', Math.round(c.muted * 100) + '% muted'));
  if (c.window) tags.append(el('span', 'tag', 'windowed'));
  body.append(tags);
  d.append(top, body);

  if (st === 'blocked' && c.block) d.append(el('div', 'blocked', 'Blocked — ' + c.block));

  const foot = el('div', 'foot');
  if (built) {
    const open = el('button', 'btn sm', 'Open'); open.type = 'button';
    open.addEventListener('click', () => editor(c.n));
    foot.append(open);
  } else {
    const q = el('button', 'btn quiet sm', st === 'cuttable' ? 'Cut it' : 'Why?');
    q.type = 'button';
    q.addEventListener('click', () => toast(st === 'cuttable'
      ? `Clip ${c.n} queued — one at a time, Resolve is a single app`
      : 'Blocked — ' + (c.block || 'nothing left after tightening')));
    foot.append(q);
  }
  foot.append(el('div', 'gap'));
  const up = el('button', 'lk', '▲'); up.type = 'button';
  const dn = el('button', 'lk dn', '▼'); dn.type = 'button';
  const sync = () => {
    up.setAttribute('aria-pressed', String(likes[c.n] === 1));
    dn.setAttribute('aria-pressed', String(likes[c.n] === -1));
  };
  up.addEventListener('click', () => {
    likes[c.n] = likes[c.n] === 1 ? 0 : 1; sync(); cards();
  });
  dn.addEventListener('click', () => {
    likes[c.n] = likes[c.n] === -1 ? 0 : -1; sync(); cards();
  });
  sync(); foot.append(up, dn);
  d.append(foot);
  return d;
}

function cards() {
  const g = $('#cards'); g.textContent = '';
  let rows = D.candidates.filter((c) => inFilter(c, filter));
  rows = sort === 'score'
    ? [...rows].sort((a, b) => b.score - a.score || a.n - b.n)
    : [...rows].sort((a, b) => a.at - b.at);
  rows.forEach((c) => g.append(card(c)));
}

/* ───────────────────────────── editor ──────────────────────────────────── */
const LAYOUTS = [
  ['L2', 'Split — facecam over content',
   'Seam at 0.42. Measured 0.418 and 0.4422 in the two references, and the house build independently had 0.44.'],
  ['L1', 'Blurred pillar',
   'Full 16:9 over a blurred copy. For broadcast footage, or when the killfeed carries meaning.'],
  ['L3', 'Crop to fill, HUD re-composited',
   'A 9:16 window keeps full height and crops sideways, so the killfeed is lost to the side and has to be overlaid back.'],
];
const CAPS = [
  ['Impact 88px', 'Word-level, 1–3 words, ~2.3 cards a second. Emphasis 1.27×, hard black stroke at 9.5% of size.'],
  ['Impact, no emphasis', 'Same face and cadence, one weight throughout.'],
  ['White on blue box', 'The R2 treatment, riding lower at y 0.747.'],
];

function paneTranscript(c) {
  const keys = emphasisKeys(c.claim);
  const booms = (c.booms || []).map((b) => b.t);
  const tx = $('#tx'); tx.textContent = '';
  c.words.forEach((w) => {
    const s = el('span', '', w.w + ' ');
    if (keys.has(bare(w.w))) s.classList.add('emph');
    if (booms.some((b) => Math.abs(b - w.t) < 0.45)) s.classList.add('boom');
    s.title = w.t.toFixed(2) + 's';
    s.addEventListener('click', () => {
      const v = $('#evid');
      if (v && v.src) { v.currentTime = Math.max(0, w.t - 0.15); v.play().catch(() => {}); }
      else toast(`In-point would move to ${w.t.toFixed(2)}s`);
    });
    tx.append(s);
  });
  const kv = $('#txkv'); kv.textContent = '';
  [['Words in the cut', c.words.length],
   ['Emphasised', [...new Set(c.words.filter((w) => keys.has(bare(w.w)))
     .map((w) => bare(w.w)))].length + ' from the claim'],
   ['Audio splices', c.shots], ['Runtime', c.dur.toFixed(2) + 's']]
    .forEach(([k, v]) => { kv.append(el('dt', '', k), el('dd', 'num', String(v))); });
}

function radios(host, name, items, pick, note) {
  host.textContent = '';
  const o = el('div', 'opt');
  items.forEach(([k, label, sub], i) => {
    const l = el('label');
    const r = document.createElement('input');
    r.type = 'radio'; r.name = name; r.checked = i === pick;
    r.id = `${name}-${i}`;
    const t = el('div');
    t.append(el('b', '', label));
    if (sub) t.append(el('em', '', sub));
    l.append(r, t); o.append(l);
  });
  host.append(o);
  if (note) host.append(el('p', 'sub', note));
}

function paneSound(c) {
  const p = $('#p3'); p.textContent = '';
  p.append(el('p', 'sub', 'One boom per ~22 seconds of runtime, and only on a '
    + 'moment the clip itself calls a point. Budget for this clip: '
    + c.budget + '.'));
  const kv = el('dl', 'kv');
  (c.booms.length ? c.booms : [{ t: null, db: null }]).forEach((b, i) => {
    kv.append(el('dt', '', b.t === null ? 'Booms' : `Boom ${i + 1}`),
      el('dd', 'num', b.t === null ? 'none — no qualifying moment'
        : `${b.t.toFixed(2)}s  ·  +${b.db} dB over his baseline`));
  });
  kv.append(el('dt', '', 'Level'), el('dd', 'num', '−16.8 dBFS RMS, cued 237 ms early'));
  p.append(kv);
  if (c.gated && c.gated.length) {
    p.append(el('p', 'sub',
      'Refused: ' + c.gated.map((g) => `“${g.word}” — “${g.by}” demotes the clause`)
        .join('; ') + '.'));
  }
}

function editor(n) {
  const c = clipOf[n]; if (!c) return;
  openN = n;
  $('#etitle').textContent = c.hook || c.subject || `Clip ${n}`;
  const vid = $('#evid');
  vid.poster = c.poster;
  vid.src = `clips/${String(n).padStart(2, '0')}.mp4`;
  vid.load();
  const strip = $('#strip'); strip.textContent = '';
  c.strip.forEach((src, i) => {
    const im = document.createElement('img');
    im.src = src; im.alt = ''; im.loading = 'lazy';
    if (i === 1) im.classList.add('on');
    im.addEventListener('click', () => {
      vid.currentTime = c.dur * (i + 0.5) / c.strip.length;
      strip.querySelectorAll('img').forEach((x) => x.classList.toggle('on', x === im));
    });
    strip.append(im);
  });
  $('#tl').textContent = '';
  const fill = el('i'); fill.style.width = '0%'; $('#tl').append(fill);
  vid.ontimeupdate = () => {
    fill.style.width = (vid.currentTime / c.dur * 100) + '%';
  };
  (c.booms || []).forEach((b) => {
    const mk = el('b'); mk.style.left = (b.t / c.dur * 100) + '%';
    mk.title = `boom ${b.t}s`; $('#tl').append(mk);
  });
  const m = $('#emeta'); m.textContent = '';
  [`1080×1920`, `${c.dur.toFixed(2)}s`, `${c.mb} MB`, `score ${c.score}`,
   `${c.shots} splices`].forEach((x) => m.append(el('span', '', x)));

  $('#guides').onclick = () => {
    const on = $('#canvas').classList.toggle('noguide');
    $('#guides').setAttribute('aria-pressed', String(!on));
  };
  paneTranscript(c);
  radios($('#p1'), 'lay', LAYOUTS, 0,
    'The lower pane is a document viewer, not a gameplay slot.');
  radios($('#p2'), 'cap', CAPS, 0,
    'Profanity is masked in the caption and left in the audio. A card whose span '
    + 'is more than half digital silence is dropped — whisper writes words over a '
    + 'mute at full confidence.');
  paneSound(c);
  show('editor');
}

/* ───────────────────────────── boot ────────────────────────────────────── */
function segs(host, onPick) {
  host.addEventListener('click', (e) => {
    const b = e.target.closest('.seg'); if (!b || !host.contains(b)) return;
    [...host.querySelectorAll('.seg')].forEach((x) =>
      x.setAttribute('aria-pressed', String(x === b)));
    onPick(b.textContent.trim(), b);
  });
}

function boot() {
  $('#projpill').textContent = `${D.job} · ${D.channel}`;
  $('#rtitle').textContent = D.vod_title.split('|')[0].trim() + ' — ' + D.vod_duration;
  const f = $('#found'); f.textContent = '';
  f.append(el('span', 'kb'), el('b', '', D.channel),
           el('span', 'num', D.vod_duration), el('span', 't', D.vod_title));

  steps(); tally(); filters(); cards();

  $$('nav button').forEach((b) => b.addEventListener('click', () => {
    if (b.dataset.go === 'editor' && !openN) { editor(D.clips[0].n); return; }
    if (b.dataset.go === 'editor') { editor(openN); return; }
    show(b.dataset.go);
  }));
  $('#back').addEventListener('click', () => show('results'));
  segs($('#sorts'), (t) => { sort = t === 'Score' ? 'score' : 'order'; cards(); });
  $$('.segs[data-seg="frame"],.segs[data-seg="len"]').forEach((h) => segs(h, () => {}));

  $('#upload').addEventListener('click', () =>
    toast('A VOD already on this machine is adopted in place — no upload'));
  $('#redo').addEventListener('click', () => {
    const q = $('#reprompt').value.trim();
    toast(q ? `Re-ranking against “${q}”` : 'Give it something to rank against');
  });
  $('#go').addEventListener('click', () => {
    if (stepAt < STEPS.length) return;
    stepAt = 0; steps(); $('#go').disabled = true;
    $('#gohint').textContent = 'Replaying — stage states, no invented timings.';
    const tick = () => {
      stepAt += 1; steps();
      if (stepAt < STEPS.length) setTimeout(tick, 480);
      else {
        $('#go').disabled = false;
        $('#gohint').textContent = "Replays this VOD's real run.";
        show('results');
      }
    };
    setTimeout(tick, 480);
  });

  $('#tabs').addEventListener('click', (e) => {
    const b = e.target.closest('button'); if (!b) return;
    const i = [...$('#tabs').children].indexOf(b);
    [...$('#tabs').children].forEach((x, k) =>
      x.setAttribute('aria-selected', String(k === i)));
    [0, 1, 2, 3].forEach((k) => { $('#p' + k).hidden = k !== i; });
  });
  $$('.exp [data-x]').forEach((b) => b.addEventListener('click', () => {
    const c = clipOf[openN] || {};
    toast({ mp4: `${c.dur ? c.dur.toFixed(2) + 's ' : ''}H.264 1080×1920, −14 LUFS`,
            xml: 'Timeline XML — the cut opens in Resolve with every decision intact',
            sched: 'Scheduling is not wired up in the prototype' }[b.dataset.x]);
  }));

  $('#theme').addEventListener('click', () => {
    const now = document.documentElement.getAttribute('data-theme');
    const dark = now ? now === 'dark'
      : matchMedia('(prefers-color-scheme: dark)').matches;
    document.documentElement.setAttribute('data-theme', dark ? 'light' : 'dark');
  });
}
boot();
