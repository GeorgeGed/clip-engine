/* Clip Engine — drop a link, pick a clip, review it, download it.
 *
 * Three screens and nothing else. The screening table, the verdict chips and
 * the refused clips are gone on purpose: a clip that cannot be cut is not a
 * result, and showing twenty-three of them is showing the machine's working
 * instead of the work.
 *
 * THE GRID IS PATCHED, NEVER REBUILT. The previous version held a signature
 * of the whole list and did `grid.innerHTML = ''` whenever it changed — so
 * the moment ANY clip finished building, every playing <video> on the page
 * was destroyed and every half-typed field was wiped. That is the same
 * defect the job list had when it tore a row out from under a click, one
 * layer down, and the general rule is written here because it has now been
 * learned three times: DO NOT REPLACE A SUBTREE THAT HOLDS FOCUS, PLAYBACK
 * OR AN UNSAVED EDIT. Cards are created once, kept in `CARDS`, and updated
 * field by field.
 */
const $ = s => document.querySelector(s);
const pad = n => String(n).padStart(2, '0');
const mmss = s => `${Math.floor(s / 60)}:${pad(Math.round(s % 60))}`;

let JOB = null, TIMER = null, BUILDING = new Set();
let CANDS = [], CARDS = new Map(), EDITING = new Set(), LAST = null;

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
/* EVERY POLL FAILURE USED TO BE SWALLOWED — `catch { return; }` — so a
 * server that had restarted, crashed or lost its key left the page showing
 * whatever it last knew, forever, with nothing to say so. Stale data that
 * looks live is worse than an error. */
function trouble(msg) {
  const el = $('#oops');
  el.hidden = !msg;
  if (msg) el.textContent = msg;
}

/* ── screen 1: the link ─────────────────────────────────────────────── */
let looked = null, lookTimer = null;
$('#url').addEventListener('input', () => {
  clearTimeout(lookTimer); looked = null; gate();
  const u = $('#url').value.trim();
  // A TWITCH VOD **OR** A PATH ON THIS MAC. The server has always accepted
  // both, and this test was the reason only one of them could be used: a
  // path never matched, so the lookup never ran, so `looked` stayed null and
  // the Start button could not enable. An absolute path or a ~ is enough to
  // try — the server confirms the file is actually there and says how long
  // it is, which is what you want to know before an hour of work starts.
  const isPath = /^[~/]/.test(u);
  if (!isPath && !/\/videos?\/\d+/.test(u)) { $('#meta').textContent = ''; return; }
  $('#meta').textContent = isPath ? 'Checking that file…' : 'Looking it up…';
  lookTimer = setTimeout(async () => {
    try {
      const d = await api('/api/lookup?url=' + encodeURIComponent(u));
      looked = d;
      // A file has no channel, so do not render an empty bold span before a
      // separator — it reads as a missing value rather than an absent one.
      $('#meta').innerHTML = (d.channel ? `<b>${esc(d.channel)}</b> &middot; ` : '')
        + `${esc(d.title)} &middot; ${esc(d.duration)}`;
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
      url: $('#url').value.trim(), channel: looked.channel || '',
      rights: $('#rights').value, note: looked.title || '' }) });
    await listJobs();
    openJob(j.id);
  } catch (e) {
    $('#meta').innerHTML = `<span class="err">${esc(e.message)}</span>`;
    $('#start').disabled = false;
  }
});
$('#restart').addEventListener('click', () => {
  clearInterval(TIMER); JOB = null; trouble(''); show('drop');
});

/* ── the job picker ─────────────────────────────────────────────────── */
/* A SECOND VOD USED TO HIDE THE FIRST FOREVER. Boot opened `jobs[0]` and
 * nothing else was reachable — the older job, its specs and its finished
 * clips were all still served, and there was no way to ask for them. */
async function listJobs() {
  const sel = $('#jobs');
  try {
    const jobs = await api('/api/jobs');
    sel.hidden = jobs.length < 2;
    const sig = jobs.map(j => j.id + ':' + j.state).join(',');
    if (sel.dataset.sig !== sig) {
      sel.dataset.sig = sig;
      sel.innerHTML = jobs.map(j =>
        `<option value="${j.id}">${esc(j.note || j.name)}</option>`).join('');
    }
    if (JOB) sel.value = String(JOB);
    return jobs;
  } catch { sel.hidden = true; return null; }
}
$('#jobs').addEventListener('change', e => openJob(Number(e.target.value)));

/* ── screen 2: it works ─────────────────────────────────────────────── */
const SAY = {
  ingest: 'Fetching the stream', analyse: 'Listening to all of it',
  rank: 'Finding the moments', screen: 'Checking what can be cut',
  // `editorial` had no entry, so the rail printed the raw key at the user.
  editorial: 'Reading what each one is about',
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

/* WHAT THE BUILD IS DOING, said in words.
 *
 * George: *"there's just like an endless kind of loop ... they're just not
 * working"*. A clip takes minutes and the card showed a sliding bar and the
 * word "Cutting…" for all of it — no stage, no count, no change. Nothing was
 * stuck; there was no way to tell that from the page, and a progress bar
 * that never moves IS an endless loop as far as the person watching is
 * concerned. The server has reported the running stage's last log line all
 * along; this turns it into a sentence.
 */
function buildSay(p) {
  if (p && p.state === 'queued') return 'Waiting for a free lane…';
  if (!p || !p.line) return 'Starting…';
  const l = p.line;
  let m = /Rendered (\d+)\/(\d+)/.exec(l);
  if (m) return `Drawing the overlays — frame ${m[1]} of ${m[2]}`;
  if (/^Bundling|Copying public dir|Getting compositions/.test(l))
    return 'Loading the graphics';
  if (/native render|cut: \d+ keeps/.test(l)) return 'Rendering the video';
  if (/loudness|LUFS|dBTP/.test(l)) return 'Finishing the sound';
  if (/^\s*\[cut\]/.test(l)) return 'Finding the cut';
  if (/^\s*\[captions\]|cards ->/.test(l)) return 'Writing the captions';
  if (/^\s*\[chat\]|messages/.test(l)) return 'Reading the chat';
  if (/^\s*\[punch\]|boom|baseline/.test(l)) return 'Placing the booms';
  if (/PASS|FAIL|^\s*ok\s/.test(l)) return 'Checking the file';
  return l.replace(/^\s*/, '').slice(0, 60);
}

/* ── screen 3: the clips ────────────────────────────────────────────── */
function cardShell(j, c) {
  const el = document.createElement('article');
  el.className = 'clip';
  el.innerHTML =
    `<div class="vt raw"><span class="vs">${c.score}<small>VIRALITY</small></span>` +
      `<span class="len"></span></div>` +
    `<div class="bar2" hidden><i></i></div>` +
    `<p class="prog" hidden></p>` +
    `<div class="ci"><p class="ct"></p><p class="cq"></p>` +
      `<div class="act"></div>` +
      `<form class="askf" hidden>` +
        `<input class="askq" type="text" autocomplete="off" ` +
          `aria-label="Tell the editor what to change about this clip" ` +
          `placeholder="remove the booms · cut the end · chat off">` +
        `<button class="askb" type="submit">Ask</button>` +
      `</form>` +
      `<p class="askr" hidden role="status" aria-live="polite"></p>` +
      `<button class="link edit" type="button" aria-expanded="false">Edit the cut</button>` +
      `<div class="ed" hidden></div>` +
    `</div>`;
  el.querySelector('.edit').addEventListener('click', () => toggleEditor(j, c, el));
  el.querySelector('.askf').addEventListener('submit', e => {
    e.preventDefault();
    askFor(j, c, el);
  });
  return el;
}

/* ASK FOR A CHANGE IN WORDS.
 *
 * George: *"i can ask the ai 'remove the booms' or cut the end of the
 * video, etc, and then it will make the changes then and there and re-load
 * the video."* The server turns the sentence into a patch over the same
 * fields the drawer edits, validates it the same way, and queues the
 * rebuild. A refusal is a real answer and is shown as one — "make the
 * captions bigger" is not expressible and should say so rather than
 * rebuilding something nobody asked for.
 */
async function askFor(j, c, el) {
  const f = el.querySelector('.askf');
  const q = el.querySelector('.askq');
  const r = el.querySelector('.askr');
  const said = q.value.trim();
  if (!said) return;
  f.querySelector('.askb').disabled = true;
  q.disabled = true;
  r.hidden = false; r.className = 'askr'; r.textContent = 'Thinking…';
  try {
    const d = await api(`/api/jobs/${j.id}/ask/${c.n}`, {
      method: 'POST', body: JSON.stringify({ ask: said }) });
    if (d.refused) {
      r.className = 'askr warn';
      r.textContent = d.refused;
    } else {
      r.textContent = (d.why || 'Changed.')
        + (d.queued ? ' Re-cutting now.' : ' ' + (d.note || 'Saved.'));
      q.value = '';
      if (d.queued) { BUILDING.add(c.n); poll(); }
    }
  } catch (e) {
    r.className = 'askr warn';
    r.textContent = e.message;
  } finally {
    f.querySelector('.askb').disabled = false;
    q.disabled = false;
  }
}

/* The media tile. Swapping an <img> for a <video> is the one node change a
 * card ever makes, and it only happens when a clip is first built. */
function setMedia(el, j, c, done) {
  const vt = el.querySelector('.vt');
  const want = done ? 'video' : 'img';
  let have = vt.querySelector('video,img');
  if (have && have.tagName.toLowerCase() !== want) { have.remove(); have = null; }
  if (!have) {
    have = document.createElement(want);
    if (done) { have.controls = true; have.preload = 'metadata'; have.playsInline = true; }
    else { have.alt = ''; have.loading = 'lazy'; have.src = `/api/jobs/${j.id}/thumb/${c.n}`; }
    vt.insertBefore(have, vt.firstChild);
  }
  // A REBUILT CLIP IS A DIFFERENT VIDEO AT THE SAME URL. Asking for a
  // change and getting the old cut back is the feature failing silently, so
  // the src carries the render's own mtime and changes when it does. Only
  // then — resetting `src` on every repaint would restart playback twice a
  // second.
  if (done) {
    const v = String(done.modified || 0);
    if (have.dataset.v !== v) {
      have.dataset.v = v;
      have.src = `/api/jobs/${j.id}/clip/${c.n}?v=${encodeURIComponent(v)}`;
      if (have.load) have.load();
    }
  }
  vt.classList.toggle('raw', !done);
}

function setText(el, sel, s) {
  const n = el.querySelector(sel);
  if (n.textContent !== s) n.textContent = s;
}

// WHAT THE SERVER SAYS IS ALLOWED, fetched once. A colour list typed in
// here would be a second place deciding the same thing, and it would go
// stale the moment a colour was added or refused. `/api/options` is built
// from `engine.caption_colour`, which is the code that enforces the floor.
let OPTS = null;
async function loadOptions() {
  if (OPTS) return OPTS;
  try { OPTS = await api('/api/options'); } catch (e) { OPTS = {}; }
  return OPTS;
}

let PROG = null, PROG_N = null;
// index -> {state, line}: ONE ENTRY PER LANE, because clips now build at
// once. `PROG_N` was a single number, so with two lanes going one card
// showed the other lane's frame count. The server reports a list.
let LANES = new Map();

function paintCard(el, j, c, done, spec, busy) {
  const lane = LANES.get(c.n);
  const mine = lane ? true : (PROG_N === null ? true : PROG_N === c.n);
  setMedia(el, j, c, done);
  // THE BADGE IS THE CLIP'S LENGTH, NOT THE REGION'S. It read `c.secs`,
  // which is the candidate WINDOW — up to 54s longer than the cut, and
  // visibly wrong on screen as a 1:04 label over a 0:45 video. A built clip
  // is measured on the file; an unbuilt one has no length yet, so the spec's
  // own span is shown as an approximation and marked with a ~, and a clip
  // with no spec shows nothing rather than a number that means something
  // else.
  let len = '';
  if (done && done.seconds) len = mmss(done.seconds);
  else if (spec && spec.in_point != null) {
    // Most specs carry no out_point — only a reviewed clip sets one — and
    // without it the cut runs to the end of its region. So the planned span
    // is `(out_point ?? region) - in_point`: an upper bound, because the
    // dead-space pass has not run yet, which is what the ~ says.
    const end = spec.out_point != null ? spec.out_point : c.secs;
    if (end > spec.in_point) len = '~' + mmss(end - spec.in_point);
  }
  setText(el, '.len', len);

  el.querySelector('.bar2').hidden = !busy;
  const pr = el.querySelector('.prog');
  pr.hidden = !busy;
  if (busy) setText(el, '.prog', buildSay(lane || (mine ? PROG : null)));
  // The hook is the clip's NAME; `subject` is a sentence about it. Falling
  // back to `subject` only matters before the editorial pass has run.
  setText(el, '.ct', (spec && spec.hook) || c.title || c.subject);
  setText(el, '.cq', (c.title || (spec && spec.hook))
    ? c.subject : (c.claim || '').replace(/^"|"$/g, ''));

  const act = el.querySelector('.act');
  const want = done ? 'done' : (busy ? 'busy' : 'make');
  if (act.dataset.state !== want) {
    act.dataset.state = want;
    act.innerHTML = '';
    if (done) {
      const a = document.createElement('a');
      a.className = 'dl'; a.textContent = 'Download';
      a.href = `/api/jobs/${j.id}/clip/${c.n}?download=1`; a.download = '';
      const again = document.createElement('button');
      again.className = 'sec'; again.type = 'button'; again.textContent = 'Cut again';
      again.addEventListener('click', () => make(j.id, c.n, again));
      act.append(a, again);
    } else {
      const b = document.createElement('button');
      b.className = 'make'; b.type = 'button'; b.disabled = busy;
      b.textContent = busy ? 'Cutting…' : 'Make this clip';
      b.addEventListener('click', () => make(j.id, c.n, b));
      act.append(b);
    }
  } else if (!done) {
    const b = act.querySelector('.make');
    if (b) { b.disabled = busy; b.textContent = busy ? 'Cutting…' : 'Make this clip'; }
  }
  // The ask box is for changing a cut that EXISTS. There is nothing to
  // adjust about a clip that has not been made yet, and "cut the end" has
  // no end to point at.
  el.querySelector('.askf').hidden = !done || busy;

  // A QC verdict the gate produced but the page never showed, because the
  // manifest was parsed in a shape it has never been written in.
  // `classList.toggle(name, undefined)` IGNORES the second argument and
  // toggles — so an unbuilt clip, where `done` is undefined, flipped the
  // flag on every repaint and the grid filled with "QC FAILED" on clips
  // that had never been cut. The force parameter has to be a real boolean.
  el.classList.toggle('bad', !!(done && done.qc_ok === false));
}

async function paintClips(j) {
  if (!CANDS.length) {
    try { CANDS = await api(`/api/jobs/${j.id}/candidates`); }
    catch (e) { trouble(`Could not read this job's clips — ${e.message}`); return; }
  }
  const made = new Map((j.clips || []).map(c => [c.index, c]));
  const specs = new Map((j.specs || []).map(s => [s.index, s]));
  const list = CANDS.filter(c => c.verdict === 'build').sort((a, b) => b.score - a.score);

  $('#cT').textContent = `${list.length} clips worth cutting`;
  $('#cS').textContent = 'Ranked by how likely they are to carry. Pick one and it gets made.';
  // THE FOOTER STATED ONE REASON FOR ALL OF THEM and it is false for some —
  // a clip can be left out because the editorial pass read it as two
  // narratives, not because the audio is muted. The screen writes its own
  // reason per clip; this counts them instead of inventing a summary.
  // A clip carries SEVERAL reasons — "43% muted; 19 cuts/min; only 20s left"
  // — so the thing to count is reason KINDS across clips, not whole strings.
  // Grouping the strings put "32% muted" and "51% muted" in separate buckets
  // and reported three of each, which is the number dressed as a category.
  const KIND = [[/muted/, 'the audio is muted'],
                [/cuts\s*\/\s*min/, 'the cut would strobe'],
                [/left/, 'too little is left after tightening']];
  const why = new Map();
  CANDS.filter(c => c.verdict !== 'build').forEach(c => {
    new Set((c.block || '').split(';').map(s => {
      const hit = KIND.find(([re]) => re.test(s));
      return hit ? hit[1] : null;
    }).filter(Boolean)).forEach(k => why.set(k, (why.get(k) || 0) + 1));
  });
  const n = CANDS.length - list.length;
  $('#foot').textContent = n
    ? `${n} other moments were left out` + (why.size
        ? ' — ' + [...why].sort((a, b) => b[1] - a[1])
            .map(([k, v]) => `${v} because ${k}`).join(', ') + '.'
        : '.')
    : '';

  const grid = $('#grid');
  const seen = new Set();
  list.forEach(c => {
    seen.add(c.n);
    let el = CARDS.get(c.n);
    if (!el) { el = cardShell(j, c); CARDS.set(c.n, el); grid.appendChild(el); }
    paintCard(el, j, c, made.get(c.n), specs.get(c.n), BUILDING.has(c.n));
    if (EDITING.has(c.n)) fillEditor(el, specs.get(c.n), c, /* onlyIfClean */ true);
  });
  CARDS.forEach((el, n) => {
    if (!seen.has(n)) { el.remove(); CARDS.delete(n); }
  });
}

/* ── the editor: the fields a review ever changes ───────────────────── */
/* `in_point`, `out_point`, `booms`, `chat_mode` and `hook` are the whole of
 * it — every note across every round of review reduced to one of these —
 * and the server has routed `POST /api/jobs/:id/spec/:n` the entire time
 * with nothing in the page able to reach it. */
const FIELDS = [
  ['in_point', 'Starts at', 'seconds', 'text'],
  ['out_point', 'Ends at', 'seconds, or blank for the planned end', 'text'],
  ['hook', 'Title', 'the line burned on screen', 'text'],
];

// BOOMS ARE THREE ANSWERS, NOT A TEXT FIELD, and one text field could not
// express the middle one. `booms: []` means "no booms, decided"; `null`
// means "nobody has said, let the pipeline pick"; a list names the times.
//
// As a text box this round-tripped wrong in the one direction that matters:
// `spec.booms ? ... : ''` is TRUE for `[]` in JavaScript, `[].join()` is
// `''`, and the server maps `''` to `null` — so a clip whose booms George
// had removed got them back on the next save of ANY field, and "Save & cut"
// rebuilt it with them in. The spec's own notes went on saying they were
// removed. That is the `if keep:` defect again, one layer up, in the UI for
// the feature it was found in.
const BOOMS = [
  ['auto', 'Automatic', 'let the pipeline pick'],
  ['none', 'None', 'no booms on this clip'],
  ['these', 'These times', 'seconds, comma separated'],
];

function toggleEditor(j, c, el) {
  const open = EDITING.has(c.n);
  if (open) { EDITING.delete(c.n); }
  else { EDITING.add(c.n); }
  const box = el.querySelector('.ed');
  const btn = el.querySelector('.edit');
  box.hidden = open;
  btn.setAttribute('aria-expanded', String(!open));
  btn.textContent = open ? 'Edit the cut' : 'Close';
  if (!open) buildEditor(j, c, el);
}

/* WHERE THE SCORE CAME FROM.
 *
 * George: *"the virality score doesn't really make sense. I'm not really
 * too sure the logic on that."* It is a WEIGHTED OPINION, not a measurement
 * — `engine/virality.py` says so in its own docstring: *nothing here is
 * validated against real view counts yet*. 45% of it is a model's read of
 * the transcript. Printing a bare two-digit number next to a thumbnail
 * invites it to be read as a predicted view count, which it is not. The
 * parts have always been computed and stored; this shows them.
 */
const PART = { strength: 'reads well (45%)', crowd: 'viewers clipped it (25%)',
               reaction: 'he got loud (15%)', fit: 'length and subject (15%)' };

function scoreWhy(c) {
  const comp = c.components || {};
  const rows = Object.entries(PART)
    .filter(([k]) => comp[k] != null)
    .map(([k, label]) =>
      `<li><b>${Math.round(comp[k] * 100)}</b> ${esc(label)}</li>`).join('');
  if (!rows) return '';
  return `<div class="whyscore"><p>Score <b>${c.score}</b> — a stated weighting, `
       + `not a measured prediction:</p><ul>${rows}</ul>`
       + (c.flags && c.flags.length
          ? `<p class="fl">${c.flags.map(f => esc(f)).join(' · ')}</p>` : '')
       + (c.vetoed ? `<p class="fl">The editorial pass would drop this one`
            + (c.why ? ` — ${esc(c.why)}` : '') + `</p>` : '')
       + `</div>`;
}

function buildEditor(j, c, el) {
  const box = el.querySelector('.ed');
  // If the options have not arrived yet, draw now with the house entry and
  // redraw once they do — better than an empty drawer while a fetch runs.
  if (!OPTS) loadOptions().then(() => {
    if (EDITING.has(c.n)) buildEditor(j, c, el);
  });
  box.innerHTML = scoreWhy(c) +
    FIELDS.map(([k, label, hint]) =>
      `<label class="f"><span>${esc(label)}</span>` +
      `<input name="${k}" type="text" autocomplete="off" spellcheck="false" ` +
      `aria-label="${esc(label)} — ${esc(hint)}" placeholder="${esc(hint)}"></label>`).join('') +
    `<fieldset class="f bm"><legend>Booms</legend>` +
      BOOMS.map(([v, label, hint]) =>
        `<label class="r"><input type="radio" name="booms_mode" value="${v}" ` +
        `aria-label="${esc(label)} — ${esc(hint)}"><span>${esc(label)}</span></label>`
      ).join('') +
      `<input name="booms" type="text" autocomplete="off" spellcheck="false" ` +
      `aria-label="Boom times in seconds, comma separated" ` +
      `placeholder="seconds, comma separated" hidden></fieldset>` +
    `<label class="f"><span>Chat</span><select name="chat_mode" aria-label="Chat overlay mode">` +
      `<option value="">Decide automatically</option>` +
      `<option value="continuous">Always on</option>` +
      `<option value="reactive">Only on reactions</option>` +
      `<option value="off">Off</option></select></label>` +
    `<label class="f"><span>Subtitles</span>` +
      `<select name="caption_emph" aria-label="Emphasised subtitle colour">` +
      capOptions('emph') + `</select></label>` +
    `<label class="f"><span>Subtitle body</span>` +
      `<select name="caption_fill" aria-label="Subtitle body colour">` +
      capOptions('fill') + `</select></label>` +
    `<label class="f"><span>Story cards</span>` +
      `<select name="stories" aria-label="Story photo cards">` +
      `<option value="auto">When one fits</option>` +
      `<option value="off">Off</option></select></label>` +
    `<label class="f"><span>Why</span><input name="note" type="text" autocomplete="off" ` +
      `aria-label="Why you changed it — appended to the spec's notes" ` +
      `placeholder="appended to the clip's notes"></label>` +
    `<div class="eact"><button type="button" class="sec save">Save</button>` +
      `<button type="button" class="make saveb">Save &amp; cut</button>` +
      `<span class="emsg" role="status" aria-live="polite"></span></div>`;
  box.addEventListener('input', () => { box.dataset.dirty = '1'; });
  box.addEventListener('change', () => {
    const m = box.querySelector('[name="booms_mode"]:checked');
    box.querySelector('[name="booms"]').hidden = !m || m.value !== 'these';
  });
  fillEditor(el, (LAST && (LAST.specs || []).find(s => s.index === c.n)), c);
  box.querySelector('.save').addEventListener('click', () => saveSpec(j, c, el, false));
  box.querySelector('.saveb').addEventListener('click', () => saveSpec(j, c, el, true));
}

function capOptions(which) {
  const list = (OPTS && OPTS.caption_colours) || [];
  const def = (OPTS && OPTS.caption_default && OPTS.caption_default[which]) || '';
  if (!list.length) return `<option value="">House</option>`;
  // The measured ratio is shown, because it is the reason a colour is on
  // this list — and it is the number that refuses the obvious request.
  return `<option value="">House (${esc(def)})</option>` + list.map(x =>
    `<option value="${esc(x.name)}">${esc(x.name)} \u2014 ${x.ratio}:1</option>`
  ).join('');
}

function fillEditor(el, spec, c, onlyIfClean) {
  const box = el.querySelector('.ed');
  if (!box || box.hidden || !box.children.length) return;
  // Never overwrite what someone is in the middle of typing. A 2s poll with
  // a text field in it is how the job list's torn-row defect reappears.
  if (onlyIfClean && (box.contains(document.activeElement) || box.dataset.dirty)) return;
  const b = spec ? spec.booms : undefined;
  const v = {
    in_point: spec && spec.in_point != null ? spec.in_point : '',
    out_point: spec && spec.out_point != null ? spec.out_point : '',
    // `Array.isArray` and `.length`, never truthiness — see BOOMS above.
    booms: Array.isArray(b) && b.length ? b.join(', ') : '',
    hook: (spec && spec.hook) || c.title || '',
    chat_mode: (spec && spec.chat_mode) || '',
    caption_fill: (spec && spec.caption_fill) || '',
    caption_emph: (spec && spec.caption_emph) || '',
    stories: (spec && spec.stories) || 'auto',
  };
  Object.entries(v).forEach(([k, val]) => {
    const n = box.querySelector(`[name="${k}"]`);
    if (n && n !== document.activeElement) n.value = val;
  });
  const mode = !Array.isArray(b) ? 'auto' : (b.length ? 'these' : 'none');
  box.querySelectorAll('[name="booms_mode"]').forEach(r => {
    if (r !== document.activeElement) r.checked = r.value === mode;
  });
  box.querySelector('[name="booms"]').hidden = mode !== 'these';
}

async function saveSpec(j, c, el, thenBuild) {
  const box = el.querySelector('.ed');
  const msg = box.querySelector('.emsg');
  const get = k => box.querySelector(`[name="${k}"]`).value.trim();
  const spec = {};
  FIELDS.forEach(([k]) => { spec[k] = get(k); });
  // JSON TYPES, so each of the three answers survives the round trip.
  const bm = (box.querySelector('[name="booms_mode"]:checked') || {}).value;
  spec.booms = bm === 'none' ? [] : bm === 'these' ? get('booms') : null;
  if (bm === 'these' && !get('booms')) {
    msg.textContent = 'Name the boom times, or choose Automatic or None';
    msg.className = 'emsg err';
    return;
  }
  // ALWAYS SEND IT, EVEN EMPTY. `if (mode) spec.chat_mode = mode` omitted
  // the key when the select was on "Decide automatically", so that option
  // was inoperative: once a mode was set from this page there was no way to
  // unset it. `null` is what clears it, and the server already maps the
  // empty string to None.
  spec.chat_mode = get('chat_mode') || null;
  // Same rule as chat_mode: always send the key, so "House" can clear a
  // colour that was set. `null` is what the server maps to the default.
  spec.caption_fill = get('caption_fill') || null;
  spec.caption_emph = get('caption_emph') || null;
  spec.stories = get('stories') || 'auto';
  box.querySelectorAll('button').forEach(b => { b.disabled = true; });
  msg.textContent = 'Saving…'; msg.className = 'emsg';
  try {
    await api(`/api/jobs/${j.id}/spec/${c.n}`, {
      method: 'POST', body: JSON.stringify({ spec, note: get('note') }) });
    delete box.dataset.dirty;
    msg.textContent = 'Saved';
    if (thenBuild) { await make(j.id, c.n, null); msg.textContent = 'Saved — cutting'; }
  } catch (e) {
    msg.textContent = e.message; msg.className = 'emsg err';
  } finally {
    box.querySelectorAll('button').forEach(b => { b.disabled = false; });
  }
  poll();
}

/* ── making one ─────────────────────────────────────────────────────── */
async function make(id, n, btn) {
  // DISABLE SYNCHRONOUSLY. The button was only disabled on the next
  // repaint, so a double-click sent two POSTs, each spawning subprocesses
  // that write the clip's spec.
  if (btn) { btn.disabled = true; btn.textContent = 'Cutting…'; }
  if (BUILDING.has(n)) return;
  BUILDING.add(n);
  try { await api(`/api/jobs/${id}/build/${n}`, { method: 'POST' }); }
  catch (e) { BUILDING.delete(n); trouble(e.message); if (btn) btn.disabled = false; }
  poll();
}

/* ── the loop ───────────────────────────────────────────────────────── */
async function poll() {
  if (!JOB) return;
  let j;
  try { j = await api('/api/jobs/' + JOB); }
  catch (e) { trouble(`Lost contact with the factory — ${e.message}`); return; }
  LAST = j;
  const by = Object.fromEntries(j.stages.map(s => [s.key, s.state]));
  // A FAILED CUT LOOKED LIKE NOTHING HAPPENING. The card dropped out of
  // "Cutting…" and went back to offering "Make this clip", with no way to
  // tell a failure from a build that was never started — which is most of
  // what "the clips are basically just not cutting" describes. The stage
  // state has always said so; nothing read it.
  trouble(by.build === 'failed'
    ? 'The last cut failed. Its reason is at the end of the build log — '
      + `jobs/${j.name}/web/build.log`
    : '');
  const ready = by.screen === 'done';

  // THE SERVER'S BUILD STATE, NOT ONLY THIS TAB'S. `BUILDING` was purely
  // local, so a batch build started anywhere else — the CLI, another tab,
  // the whole-job chain — left every card offering "Make this clip" while
  // that clip was already being cut.
  PROG = (j.active_stage === 'build' && j.progress) ? j.progress : null;
  PROG_N = null;
  // THE LANES FIRST: the server names every clip it is building or holding,
  // with that clip's own log line. Falling back to `progress.clip` covers
  // the chain's own build stage, which walks the specs in one process.
  LANES = new Map(((j.progress && j.progress.clips) || [])
    .map(x => [x.n, x]));
  LANES.forEach((_v, n) => BUILDING.add(n));
  if (PROG && PROG.clip) {
    const m = /(\d+)$/.exec(PROG.clip);
    if (m) { PROG_N = Number(m[1]); BUILDING.add(PROG_N); }
  }
  // A CLIP THAT ALREADY EXISTS IS DONE — UNLESS IT IS THE ONE BEING CUT
  // RIGHT NOW. This dropped every clip with a render out of `BUILDING`,
  // which is right for a first build and exactly wrong for a RE-build: ask
  // for a change to a finished clip and the card showed no progress at all,
  // because the old render was still sitting there the whole time. That is
  // the ask feature's normal case, not an edge of it.
  (j.clips || []).forEach(c => {
    if (c.index !== PROG_N && !LANES.has(c.index)) BUILDING.delete(c.index);
  });
  if (!j.active && by.build !== 'running' && !LANES.size) BUILDING.clear();

  if (ready) { show('clips'); await paintClips(j); }
  else { show('work'); paintWork(j); }
}

function openJob(id) {
  JOB = id; CANDS = []; BUILDING.clear(); EDITING.clear();
  CARDS.forEach(el => el.remove()); CARDS.clear();
  $('#steps').dataset.h = ''; $('#jobs').value = String(id);
  trouble('');
  clearInterval(TIMER); poll(); TIMER = setInterval(poll, 2000);
}
function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"]/g,
    m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[m]));
}

/* Open the newest job if there is one, else ask for a link.
 *
 * A BOOT FAILURE USED TO RENDER THE "DROP A VOD" SCREEN, which reads as a
 * healthy empty install — so a server that could not answer looked exactly
 * like one with no work in it, and the honest response to each is opposite. */
(async () => {
  const jobs = await listJobs();
  if (jobs === null) {
    trouble('Could not reach the factory. It may be restarting — this page '
          + 'retries every few seconds.');
    show('drop');
    setTimeout(() => location.reload(), 8000);
    return;
  }
  if (jobs.length) return openJob(jobs[0].id);
  show('drop');
})();
