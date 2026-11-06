'use strict';

// Polling rather than websockets: a stage runs for minutes, the server is on
// localhost, and 1.5s of lag on a progress bar costs nothing. One fewer
// moving part between the operator and a build that must not be interrupted.
const POLL_MS = 1500;

const $ = (s) => document.querySelector(s);
const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
};

let openId = null;       // job being shown in the detail panel
let logStage = null;     // which stage's log the operator is reading
let pinnedLog = false;   // true once they pick one, so polling stops moving it

async function api(path, opts) {
  const r = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.error || `${r.status} ${r.statusText}`);
  return body;
}

const ago = (t) => {
  if (!t) return '';
  const s = Math.max(0, (Date.now() / 1000) - t);
  if (s < 60) return `${s | 0}s ago`;
  if (s < 3600) return `${(s / 60) | 0}m ago`;
  if (s < 86400) return `${(s / 3600) | 0}h ago`;
  return `${(s / 86400) | 0}d ago`;
};

const took = (st) => (st.started && st.ended)
  ? `${Math.round(st.ended - st.started)}s` : '';

const stateClass = (s) => s.startsWith('failed') || s.startsWith('error')
  ? 'failed' : s;

// A PASTED VOD KNOWS ITS OWN CHANNEL. Asking for it again is asking the
// operator to retype something the URL already contains, and getting it
// wrong renames the job directory.
let lookedUp = '';
async function lookupVod() {
  const el0 = $('#job-form [name=url]');
  const url = el0.value.trim();
  const out = $('#vod-about');
  if (!/\/videos?\/\d+/.test(url) || url === lookedUp) return;
  lookedUp = url;
  out.className = 'note'; out.textContent = 'looking up…';
  try {
    const d = await api(`/api/lookup?url=${encodeURIComponent(url)}`);
    const ch = $('#job-form [name=channel]');
    if (d.channel && !ch.value.trim()) ch.value = d.channel;
    out.className = 'note ok-note';
    out.textContent = `${d.channel} · ${d.duration} · ${d.title}`;
  } catch (e) {
    out.className = 'note';
    out.textContent = `could not look that up (${e.message}) — fill the channel in yourself`;
  }
}
$('#job-form [name=url]').addEventListener('change', lookupVod);
$('#job-form [name=url]').addEventListener('paste', () => setTimeout(lookupVod, 50));

// Resolve is needed by exactly one stage, and it is the last one. Saying so
// on the form is cheaper than finding out an hour in.
async function showDoctor() {
  const el0 = $('#doctor');
  try {
    const d = await api('/api/doctor');
    el0.className = `doctor ${d.ok ? 'ok' : 'bad'}`;
    el0.textContent = d.ok
      ? `Resolve ready${d.studio ? ' (Studio)' : ''} — the build stage can run`
      : `Resolve not reachable — everything up to Specs will still run. ${(d.notes || []).join(' ')}`;
  } catch { el0.textContent = ''; }
}

// ------------------------------------------------------------- new job ---
$('#job-form').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const f = new FormData(ev.target);
  const msg = $('#form-msg');
  msg.className = 'msg';
  msg.textContent = 'starting…';
  try {
    const out = await api('/api/jobs', {
      method: 'POST',
      body: JSON.stringify({
        url: f.get('url'), channel: f.get('channel'),
        rights: f.get('rights'), note: f.get('note'),
      }),
    });
    msg.className = 'msg ok';
    msg.textContent = `queued as ${out.name}`;
    ev.target.reset();
    openId = out.id;
    refresh();
  } catch (e) {
    msg.className = 'msg bad';
    msg.textContent = e.message;
  }
});

$('#d-close').addEventListener('click', () => {
  openId = null; pinnedLog = false; logStage = null;
  $('#detail').hidden = true;
});

$('#d-cancel').addEventListener('click', async () => {
  if (openId == null) return;
  await api(`/api/jobs/${openId}/cancel`, { method: 'POST' }).catch(() => {});
  refresh();
});

$('#d-stage-pick').addEventListener('change', (ev) => {
  logStage = ev.target.value;
  pinnedLog = true;
  loadLog();
});

// ------------------------------------------------------------- render ----
function renderJobs(jobs) {
  const ul = $('#jobs');
  // Only rebuild when something actually changed. Polling every 1.5s and
  // replacing the list each time tears the row out from under a click —
  // which it did, and the click landed on nothing.
  const sig = jobs.map((j) =>
    `${j.id}:${j.state}:${j.active_stage}:${j.clips.length}`).join('|');
  if (ul.dataset.sig === sig) return;
  ul.dataset.sig = sig;
  ul.textContent = '';
  if (!jobs.length) {
    ul.append(el('li', 'empty', 'Nothing yet.'));
    return;
  }
  for (const j of jobs) {
    const li = el('li');
    li.append(el('span', 'nm', j.name));
    li.append(el('span', 'hint', j.rights));
    li.append(el('span', 'sp'));
    const built = j.clips.length;
    if (built) li.append(el('span', 'hint', `${built} clip${built > 1 ? 's' : ''}`));
    li.append(el('span', 'hint', ago(j.updated)));
    li.append(el('span', `badge ${stateClass(j.state)}`,
      j.active ? `running · ${j.active_stage}` : j.state));
    li.addEventListener('click', () => {
      openId = j.id; pinnedLog = false; logStage = null; refresh();
    });
    ul.append(li);
  }
}

function renderDetail(j) {
  $('#detail').hidden = false;
  $('#d-name').textContent = j.name;
  $('#d-meta').textContent =
    `${j.url} · rights: ${j.rights}${j.note ? ' · ' + j.note : ''} · ${j.state}`;
  $('#d-cancel').disabled = !j.active;

  // stage rail
  const ol = $('#d-stages');
  ol.textContent = '';
  for (const s of j.stages) {
    const li = el('li', s.state);
    li.title = s.blurb;
    li.append(el('div', 'k', s.label));
    const bits = [s.state];
    const t = took(s);
    if (t) bits.push(t);
    if (s.code) bits.push(`exit ${s.code}`);
    if (s.state === 'running' && j.progress && j.progress.total) {
      bits.push(`${j.progress.done}/${j.progress.total}`);
    }
    li.append(el('div', 's', bits.join(' · ')));
    if (s.state === 'running' && j.progress && j.progress.line) {
      // what it is actually doing. A spinner cannot tell "transcribing"
      // from "wedged", and Resolve does wedge.
      li.append(el('div', 'now', j.progress.line));
    }
    li.addEventListener('click', () => {
      logStage = s.key; pinnedLog = true;
      $('#d-stage-pick').value = s.key;
      loadLog();
    });
    ol.append(li);
  }

  // screen table
  const tb = $('#d-screen').querySelector('tbody');
  tb.textContent = '';
  const rows = j.screen;
  const buildable = rows.filter((r) => /^build|^ok|^pass/i.test(r.verdict));
  $('#d-yield').textContent = rows.length
    ? `${buildable.length} buildable of ${rows.length}` : '';
  if (!rows.length) {
    const tr = el('tr');
    const td = el('td', 'sub', 'Nothing screened yet.');
    td.colSpan = 4;
    tr.append(td);
    tb.append(tr);
  }
  for (const r of rows) {
    const good = /^build|^ok|^pass/i.test(r.verdict);
    const tr = el('tr');
    tr.append(el('td', '', String(r.index)));
    tr.append(el('td', good ? 'v-build' : 'v-reject', r.verdict || '—'));
    tr.append(el('td', 'sub', (r.subject || '').slice(0, 78)));
    tr.append(el('td', 'sub', r.reason || ''));
    tb.append(tr);
  }

  // log picker — keep the operator's choice, default to whatever is running
  const pick = $('#d-stage-pick');
  const want = j.stages.map((s) => s.key).join(',');
  if (pick.dataset.keys !== want) {
    pick.textContent = '';
    for (const s of j.stages) {
      const o = el('option', '', `${s.label} (${s.state})`);
      o.value = s.key;
      pick.append(o);
    }
    pick.dataset.keys = want;
  } else {
    [...pick.options].forEach((o, i) => {
      o.textContent = `${j.stages[i].label} (${j.stages[i].state})`;
    });
  }
  if (!pinnedLog) {
    const run = j.stages.find((s) => s.state === 'running');
    const lastDone = [...j.stages].reverse()
      .find((s) => s.state === 'done' || s.state === 'failed');
    logStage = (run || lastDone || j.stages[0]).key;
  }
  pick.value = logStage;

  // clips — driven by the SPECS, not by renders/. The spec IS the clip; the
  // mp4 is its current render, which may be missing or stale.
  const wrap = $('#d-clips');
  const byIdx = Object.fromEntries(j.clips.map((c) => [c.index, c]));
  const specs = j.specs.length
    ? j.specs
    : j.clips.map((c) => ({ index: c.index, unspecced: true }));
  $('#d-clipcount').textContent = specs.length
    ? `${j.clips.length} built of ${specs.length} specced` : '';
  const dl = $('#d-dlall');
  dl.hidden = !j.clips.length;
  dl.href = `/api/jobs/${j.id}/clips.zip`;

  // Rebuild only when something actually changed AND nothing here has focus.
  // The grid holds text inputs now, so a 1.5s poll that replaced it would
  // wipe what the operator is typing — the same defect as the job list
  // tearing a row out from under a click, one layer down.
  const sig = specs.map((s) => [s.index, s.in_point, s.out_point,
    JSON.stringify(s.booms), s.chat_mode, s.hook,
    byIdx[s.index]?.modified].join(':')).join('|');
  const typing = wrap.contains(document.activeElement);
  if (wrap.dataset.sig !== sig && !typing) {
    wrap.dataset.sig = sig;
    wrap.textContent = '';
    if (!specs.length) wrap.append(el('p', 'empty', 'No clips specced yet.'));
    for (const s of specs) {
      wrap.append(clipCard(j, s, byIdx[s.index]));
    }
  }
}

// One clip: its render, and the five fields every round of review has
// actually changed. Everything else about a clip is house style and lives
// in code, by the same split `engine/clipspec.py` already draws.
function clipCard(job, spec, built) {
  const d = el('div', 'clip');
  if (built) {
    const v = document.createElement('video');
    v.controls = true;
    v.preload = 'metadata';
    v.src = `/api/jobs/${job.id}/clip/${String(spec.index).padStart(2, '0')}`;
    d.append(v);
  } else {
    d.append(el('div', 'noclip', 'not built yet'));
  }
  const m = el('div', 'meta');
  m.append(el('b', '', `#${spec.index}`));
  if (built) {
    m.append(document.createTextNode(` · ${built.size_mb} MB · ${ago(built.modified)} · `));
    const a = el('a', 'dl', 'download');
    a.href = `/api/jobs/${job.id}/clip/${String(spec.index).padStart(2, '0')}?download=1`;
    m.append(a);
    const qc = built.qc || {};
    if (qc.verdict || qc.status) {
      const ok = /pass/i.test(qc.verdict || qc.status);
      m.append(el('div', `qc ${ok ? 'pass' : 'fail'}`,
        `QC ${qc.verdict || qc.status}${qc.reason ? ' — ' + qc.reason : ''}`));
    }
  }
  d.append(m);
  if (spec.unspecced) return d;

  const f = el('div', 'review');
  const field = (key, label, value, ph) => {
    const l = el('label', 'f');
    l.append(el('span', '', label));
    const i = document.createElement(key === 'chat_mode' ? 'select' : 'input');
    if (key === 'chat_mode') {
      for (const [v2, t2] of [['', 'auto (topicality gate)'],
                              ['continuous', 'continuous'],
                              ['reactive', 'reactive']]) {
        const o = el('option', '', t2); o.value = v2; i.append(o);
      }
      i.value = value || '';
    } else {
      i.type = 'text';
      i.value = value === null || value === undefined ? '' : value;
      i.placeholder = ph || '';
    }
    i.dataset.key = key;
    l.append(i);
    f.append(l);
    return i;
  };
  field('in_point', 'in', spec.in_point, 'seconds');
  field('out_point', 'out', spec.out_point, 'end of region');
  field('booms', 'booms', (spec.booms || []).join(', '), 'auto by duration');
  field('chat_mode', 'chat', spec.chat_mode);
  field('hook', 'hook', spec.hook, 'clickbait line');

  const note = el('label', 'f wide');
  note.append(el('span', '', 'why'));
  const ni = document.createElement('input');
  ni.type = 'text';
  ni.placeholder = 'appended to the spec notes — what the change is for';
  note.append(ni);
  f.append(note);

  const bar = el('div', 'rbar');
  const save = el('button', 'ghost', 'Save');
  const build = el('button', '', 'Save & rebuild');
  const msg = el('span', 'msg');
  bar.append(save, build, msg);
  f.append(bar);

  const collect = () => {
    const out = {};
    f.querySelectorAll('[data-key]').forEach((i) => { out[i.dataset.key] = i.value; });
    return out;
  };
  const put = async (then) => {
    msg.className = 'msg'; msg.textContent = 'saving…';
    try {
      const r = await api(`/api/jobs/${job.id}/spec/${spec.index}`, {
        method: 'POST',
        body: JSON.stringify({ spec: collect(), note: ni.value }),
      });
      const n = Object.keys(r.changed || {}).length;
      msg.className = 'msg ok';
      msg.textContent = n ? `saved ${n} change${n > 1 ? 's' : ''}` : 'no change';
      ni.value = '';
      if (then) await then();
    } catch (e) {
      msg.className = 'msg bad';
      msg.textContent = e.message;
    }
  };
  save.addEventListener('click', () => put());
  build.addEventListener('click', () => put(async () => {
    try {
      await api(`/api/jobs/${job.id}/build/${spec.index}`, { method: 'POST' });
      msg.className = 'msg ok';
      msg.textContent = 'saved, rebuild queued';
      refresh();
    } catch (e) {
      msg.className = 'msg bad';
      msg.textContent = e.message;
    }
  }));
  d.append(f);
  return d;
}

async function loadLog() {
  if (openId == null || !logStage) return;
  try {
    const out = await api(`/api/jobs/${openId}/log?stage=${logStage}`);
    const pre = $('#d-log');
    const atBottom = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 30;
    pre.textContent = out.text || '— nothing yet —';
    if (atBottom) pre.scrollTop = pre.scrollHeight;
  } catch { /* the job may have gone */ }
}

async function refresh() {
  let jobs;
  try {
    jobs = await api('/api/jobs');
  } catch {
    return;                                   // server restarting; try again
  }
  renderJobs(jobs);
  const running = jobs.find((j) => j.active);
  $('#queue-note').textContent = running
    ? `one at a time — ${running.name} is on ${running.active_stage}`
    : 'one at a time: Resolve is a single GUI app';
  if (openId != null) {
    const j = jobs.find((x) => x.id === openId);
    if (j) { renderDetail(j); loadLog(); } else { $('#detail').hidden = true; }
  }
}

refresh();
showDoctor();
setInterval(refresh, POLL_MS);
setInterval(showDoctor, 15000);
