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
    li.append(el('div', 's', bits.join(' · ')));
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

  // clips
  const wrap = $('#d-clips');
  $('#d-clipcount').textContent = j.clips.length ? `${j.clips.length} delivered` : '';
  const sig = j.clips.map((c) => `${c.index}:${c.modified}`).join(',');
  if (wrap.dataset.sig !== sig) {      // only rebuild when it changed, so a
    wrap.dataset.sig = sig;            // playing <video> is not torn out
    wrap.textContent = '';
    if (!j.clips.length) {
      wrap.append(el('p', 'empty', 'No clips built yet.'));
    }
    for (const c of j.clips) {
      const d = el('div', 'clip');
      const v = document.createElement('video');
      v.controls = true;
      v.preload = 'metadata';
      v.src = `/api/jobs/${j.id}/clip/${String(c.index).padStart(2, '0')}`;
      d.append(v);
      const m = el('div', 'meta');
      const b = el('b', '', `#${c.index}`);
      m.append(b, document.createTextNode(` · ${c.size_mb} MB · ${ago(c.modified)}`));
      const qc = c.qc || {};
      if (qc.verdict || qc.status) {
        const ok = /pass/i.test(qc.verdict || qc.status);
        m.append(el('div', `qc ${ok ? 'pass' : 'fail'}`,
          `QC ${qc.verdict || qc.status}${qc.reason ? ' — ' + qc.reason : ''}`));
      }
      d.append(m);
      wrap.append(d);
    }
  }
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
setInterval(refresh, POLL_MS);
