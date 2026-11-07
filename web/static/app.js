/* Clip Engine — drop a link, pick a clip, download it.
 *
 * Three screens and nothing else. The screening table, the verdict chips and
 * the refused clips are gone on purpose: a clip that cannot be cut is not a
 * result, and showing twenty-three of them is showing the machine's working
 * instead of the work.
 */
const $ = s => document.querySelector(s);
const pad = n => String(n).padStart(2, '0');
const mmss = s => `${Math.floor(s / 60)}:${pad(Math.round(s % 60))}`;

let JOB = null, TIMER = null, BUILDING = new Set();

async function api(path, opts) {
  const r = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...opts });
  if (r.status === 401) { location.href = '/'; throw new Error('key required'); }
  const b = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(b.error || `${r.status} ${r.statusText}`);
  return b;
}
function show(which) {
  ['drop', 'work', 'clips'].forEach(k => { $('#s-' + k).hidden = k !== which; });
  $('#restart').hidden = which === 'drop';
}

/* ── screen 1: the link ─────────────────────────────────────────────── */
let looked = null, lookTimer = null;
$('#url').addEventListener('input', () => {
  clearTimeout(lookTimer); looked = null; gate();
  const u = $('#url').value.trim();
  if (!/\/videos?\/\d+/.test(u)) { $('#meta').textContent = ''; return; }
  $('#meta').textContent = 'Looking it up…';
  lookTimer = setTimeout(async () => {
    try {
      const d = await api('/api/lookup?url=' + encodeURIComponent(u));
      looked = d;
      $('#meta').innerHTML = `<b>${esc(d.channel)}</b> &middot; ${esc(d.title)} &middot; ${esc(d.duration)}`;
    } catch (e) { looked = null; $('#meta').innerHTML = `<span class="err">${esc(e.message)}</span>`; }
    gate();
  }, 450);
});
$('#rights').addEventListener('change', gate);
function gate() {
  $('#start').disabled = !(looked && $('#rights').value);
}
$('#start').addEventListener('click', async () => {
  $('#start').disabled = true;
  try {
    const j = await api('/api/jobs', { method: 'POST', body: JSON.stringify({
      url: $('#url').value.trim(), channel: looked.channel,
      rights: $('#rights').value, note: looked.title || '' }) });
    open(j.id);
  } catch (e) {
    $('#meta').innerHTML = `<span class="err">${esc(e.message)}</span>`;
    $('#start').disabled = false;
  }
});
$('#restart').addEventListener('click', () => {
  clearInterval(TIMER); JOB = null; show('drop');
});

/* ── screen 2: it works ─────────────────────────────────────────────── */
const SAY = {
  ingest: 'Fetching the stream', analyse: 'Listening to all of it',
  rank: 'Finding the moments', screen: 'Checking what can be cut',
  prep: 'Reading the words', specs: 'Planning the edits',
  build: 'Cutting', report: 'Finishing',
};
function paintWork(j) {
  $('#wS').textContent = j.note || j.name;
  const box = $('#steps');
  const html = j.stages.map(s => {
    const cls = s.state === 'running' ? 'run' : s.state === 'done' ? 'done'
              : s.state === 'failed' ? 'fail' : '';
    const n = s.state === 'running' ? (j.progress && j.progress.line || '') : '';
    return `<div class="step ${cls}"><span class="dot"></span>` +
           `<span class="t">${esc(SAY[s.key] || s.key)}</span>` +
           `<span class="n">${esc(n.slice(0, 70))}</span></div>`;
  }).join('');
  if (box.dataset.h !== html) { box.innerHTML = html; box.dataset.h = html; }
}

/* ── screen 3: the clips ────────────────────────────────────────────── */
let CANDS = [];
async function paintClips(j) {
  if (!CANDS.length) {
    try { CANDS = await api(`/api/jobs/${j.id}/candidates`); } catch { return; }
  }
  const made = new Map((j.clips || []).map(c => [c.index, c]));
  const list = CANDS.filter(c => c.verdict === 'build').sort((a, b) => b.score - a.score);
  const skipped = CANDS.length - list.length;

  $('#cT').textContent = `${list.length} clips worth cutting`;
  $('#cS').textContent = 'Ranked by how likely they are to carry. Pick one and it gets made.';
  $('#foot').textContent = skipped
    ? `${skipped} other moments were left out — the audio is muted or the cut would strobe.`
    : '';

  const grid = $('#grid');
  const sig = JSON.stringify([list.map(c => c.n), [...made.keys()], [...BUILDING]]);
  if (grid.dataset.sig === sig) return;
  grid.dataset.sig = sig;
  grid.innerHTML = '';

  list.forEach(c => {
    const done = made.get(c.n), busy = BUILDING.has(c.n);
    const el = document.createElement('article');
    el.className = 'clip';
    const secs = done ? (done.seconds || c.secs) : c.secs;
    el.innerHTML =
      `<div class="vt${done ? '' : ' raw'}">` +
        (done
          ? `<video src="/api/jobs/${j.id}/clip/${c.n}" controls preload="metadata" playsinline></video>`
          : `<img alt="" loading="lazy" src="/api/jobs/${j.id}/thumb/${c.n}">`) +
        `<span class="vs">${c.score}<small>VIRALITY</small></span>` +
        `<span class="len">${mmss(secs)}</span>` +
      `</div>` +
      (busy ? `<div class="bar2"><i></i></div>` : '') +
      `<div class="ci">` +
        `<p class="ct"></p><p class="cq"></p>` +
        `<div class="act"></div>` +
      `</div>`;
    el.querySelector('.ct').textContent = c.subject;
    el.querySelector('.cq').textContent = (c.claim || '').replace(/^"|"$/g, '');
    const act = el.querySelector('.act');
    if (done) {
      const a = document.createElement('a');
      a.className = 'dl'; a.textContent = 'Download';
      a.href = `/api/jobs/${j.id}/clip/${c.n}?download=1`; a.download = '';
      const again = document.createElement('button');
      again.className = 'sec'; again.textContent = 'Cut again';
      again.addEventListener('click', () => make(j.id, c.n));
      act.append(a, again);
    } else {
      const b = document.createElement('button');
      b.className = 'make'; b.disabled = busy;
      b.textContent = busy ? 'Cutting…' : 'Make this clip';
      b.addEventListener('click', () => make(j.id, c.n));
      act.append(b);
    }
    grid.appendChild(el);
  });
}

async function make(id, n) {
  BUILDING.add(n);
  $('#grid').dataset.sig = '';
  try { await api(`/api/jobs/${id}/build/${n}`, { method: 'POST' }); }
  catch (e) { BUILDING.delete(n); alert(e.message); }
  poll();
}

/* ── the loop ───────────────────────────────────────────────────────── */
async function poll() {
  if (!JOB) return;
  let j; try { j = await api('/api/jobs/' + JOB); } catch { return; }
  const by = Object.fromEntries(j.stages.map(s => [s.key, s.state]));
  const ready = by.screen === 'done';
  (j.clips || []).forEach(c => BUILDING.delete(c.index));
  if (!j.active && !BUILDING.size && by.build !== 'running') BUILDING.clear();

  if (ready) { show('clips'); await paintClips(j); }
  else { show('work'); paintWork(j); }
}
function open(id) {
  JOB = id; CANDS = []; BUILDING.clear();
  $('#grid').dataset.sig = ''; $('#steps').dataset.h = '';
  clearInterval(TIMER); poll(); TIMER = setInterval(poll, 2000);
}
function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"]/g,
    m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[m]));
}

/* Open the newest job if there is one, else ask for a link. */
(async () => {
  try {
    const jobs = await api('/api/jobs');
    if (jobs.length) return open(jobs[0].id);
  } catch {}
  show('drop');
})();
