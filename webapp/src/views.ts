import type { Clip, Job, JobEvent } from "./env";
import { clock, twitchTimestamp } from "./util";

export function esc(value: unknown): string {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!,
  );
}

function fileUrl(key: string): string {
  return "/files/" + key.split("/").map(encodeURIComponent).join("/");
}

const FAVICON =
  "data:image/svg+xml," +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="8" fill="#7c5cff"/><path d="M11 9l12 7-12 7z" fill="#fff"/></svg>',
  );

const CSS = `
:root{color-scheme:dark;--bg:#0d0e12;--card:#16181f;--card2:#1d2029;--line:#262a35;--text:#e8e9ee;--muted:#8b90a0;--accent:#7c5cff;--accent2:#9a80ff;--ok:#2fbf71;--run:#3d8bfd;--bad:#ef4f5f;--radius:14px}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;padding-bottom:env(safe-area-inset-bottom)}
a{color:var(--accent2);text-decoration:none}
main{max-width:980px;margin:0 auto;padding:0 14px 40px}
.top{position:sticky;top:0;z-index:5;display:flex;align-items:center;justify-content:space-between;padding:12px 14px;padding-top:max(12px,env(safe-area-inset-top));background:rgba(13,14,18,.92);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);border-bottom:1px solid var(--line);margin-bottom:16px}
.brand{color:var(--text);font-weight:700;font-size:17px;display:flex;align-items:center;gap:8px}
.brand i{display:inline-block;width:22px;height:22px;border-radius:6px;background:var(--accent);position:relative}
.brand i:after{content:"";position:absolute;left:8px;top:6px;border-left:8px solid #fff;border-top:5px solid transparent;border-bottom:5px solid transparent}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);padding:14px}
h1{font-size:20px;margin:6px 0 4px;line-height:1.25;word-break:break-word}
h2{font-size:15px;margin:22px 2px 10px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.06em}
.muted{color:var(--muted)}
.small{font-size:13px}
.row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.spacer{flex:1}
label{display:block;font-size:13px;color:var(--muted);margin:0 0 6px}
input{width:100%;font:inherit;font-size:16px;color:var(--text);background:var(--card2);border:1px solid var(--line);border-radius:10px;padding:12px}
input:focus{outline:2px solid var(--accent);outline-offset:-1px}
.fields{display:grid;grid-template-columns:1fr 92px;gap:10px;margin-bottom:12px}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;min-height:42px;padding:0 14px;border-radius:10px;border:1px solid var(--line);background:var(--card2);color:var(--text);font:inherit;font-weight:600;cursor:pointer;text-align:center}
.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.btn.danger{color:var(--bad)}
.btn.block{width:100%}
.btn:disabled{opacity:.6}
.link{background:none;border:0;color:var(--muted);font:inherit;cursor:pointer;padding:6px}
.error{color:var(--bad);font-size:14px;min-height:0;margin:8px 0 0}
.error:empty{display:none}
.errbox{background:rgba(239,79,95,.1);border:1px solid rgba(239,79,95,.35);color:#ffb3bb;border-radius:10px;padding:10px 12px;font-size:14px;margin-top:10px;white-space:pre-wrap;word-break:break-word}
.badge{display:inline-block;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;padding:3px 8px;border-radius:999px;background:var(--card2);color:var(--muted)}
.s-running{background:rgba(61,139,253,.15);color:#7fb0ff}
.s-done{background:rgba(47,191,113,.15);color:#5fdc98}
.s-failed{background:rgba(239,79,95,.15);color:#ff8792}
.bar{height:6px;border-radius:6px;background:var(--card2);overflow:hidden;margin-top:10px}
.bar>span{display:block;height:100%;background:linear-gradient(90deg,var(--accent),var(--accent2));border-radius:6px;transition:width .4s}
.bar.indet>span{width:35%;animation:indet 1.4s ease-in-out infinite}
@keyframes indet{0%{transform:translateX(-100%)}100%{transform:translateX(300%)}}
.jobs{display:grid;gap:10px}
.job{display:block;color:var(--text)}
.job:active{background:var(--card2)}
.job-title{font-weight:600;margin:8px 0 2px;word-break:break-word}
.stage{margin:10px 0 0;font-size:14px;word-break:break-word}
.actions{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap}
.clips{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
@media(min-width:640px){.clips{grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:14px}.fields{grid-template-columns:1fr 110px}}
.clip{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);overflow:hidden;display:flex;flex-direction:column}
.clip video{display:block;width:100%;aspect-ratio:9/16;background:#000;object-fit:cover}
.clip-body{padding:10px;display:flex;flex-direction:column;gap:6px;flex:1}
.clip h3{font-size:14px;margin:0;line-height:1.3;word-break:break-word}
.clip .meta{font-size:12px;color:var(--muted);margin:0}
.clip .btn{min-height:38px;font-size:13px;padding:0 8px;width:100%}
.clip-actions{display:grid;gap:6px;margin-top:auto}
.empty{color:var(--muted);text-align:center;padding:28px 10px;border:1px dashed var(--line);border-radius:var(--radius)}
details{margin-top:22px}
details summary{cursor:pointer;color:var(--muted);font-weight:600;font-size:14px;padding:6px 2px}
.log{list-style:none;margin:6px 0 0;padding:0;font-size:13px;border-left:2px solid var(--line)}
.log li{padding:4px 0 4px 12px;word-break:break-word}
.log time{color:var(--muted);margin-right:6px;font-variant-numeric:tabular-nums}
.login{max-width:360px;margin:12vh auto 0}
.login h1{text-align:center;margin-bottom:18px}
`;

const CLIENT_COMMON = `
function localizeTimes(root){root.querySelectorAll('time[datetime]').forEach(function(t){var d=new Date(t.getAttribute('datetime'));if(!isNaN(d))t.textContent=t.hasAttribute('data-short')?d.toLocaleTimeString([],{hour:'numeric',minute:'2-digit',second:'2-digit'}):d.toLocaleString([],{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'});});}
localizeTimes(document);
async function fetchPage(){var r=await fetch(location.href,{headers:{accept:'text/html'},cache:'no-store'});if(r.redirected||!r.ok)return null;return new DOMParser().parseFromString(await r.text(),'text/html');}
function poll(isActive,apply){if(!isActive())return;setTimeout(async function tick(){try{var doc=await fetchPage();if(doc){apply(doc);localizeTimes(document);}}catch(e){}if(isActive())setTimeout(tick,5000);},5000);}
`;

function layout(title: string, body: string, script = "", header = true): string {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#0d0e12">
<meta name="robots" content="noindex">
<title>${esc(title)}</title>
<link rel="icon" href="${FAVICON}">
<style>${CSS}</style>
</head>
<body>
${
  header
    ? `<header class="top"><a class="brand" href="/"><i></i>Clip Engine</a><form method="post" action="/logout"><button class="link" type="submit">Log out</button></form></header>`
    : ""
}
<main>${body}</main>
${script ? `<script>${CLIENT_COMMON}${script}</script>` : ""}
</body>
</html>`;
}

export function loginPage(error: string | null, next: string): string {
  return layout(
    "Log in · Clip Engine",
    `<form class="login card" method="post" action="/login">
  <h1>Clip Engine</h1>
  <input type="hidden" name="next" value="${esc(next)}">
  <label for="password">Password</label>
  <input id="password" name="password" type="password" autocomplete="current-password" required autofocus>
  <p class="error">${esc(error)}</p>
  <button class="btn primary block" type="submit" style="margin-top:14px">Log in</button>
</form>`,
    "",
    false,
  );
}

function statusBadge(status: string): string {
  return `<span class="badge s-${esc(status)}">${esc(status)}</span>`;
}

function progressBar(job: Job): string {
  if (job.status === "done") return `<div class="bar"><span style="width:100%"></span></div>`;
  if (job.status === "failed") return "";
  if (job.progress == null)
    return job.status === "running" ? `<div class="bar indet"><span></span></div>` : "";
  const pct = Math.round(Math.min(1, Math.max(0, job.progress)) * 100);
  return `<div class="bar" role="progressbar" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100"><span style="width:${pct}%"></span></div>`;
}

function stageLine(job: Job): string {
  const parts = [job.stage && `<b>${esc(job.stage)}</b>`, job.message && esc(job.message)].filter(Boolean);
  return parts.join(" — ");
}

function vodLabel(job: Job): string {
  return job.vod_title || `Twitch VOD ${job.vod_url.split("/").pop()}`;
}

const active = (job: Job) => job.status === "queued" || job.status === "running";

export function jobList(jobs: Job[]): string {
  if (!jobs.length) return `<p class="empty">No jobs yet. Paste a Twitch VOD link above to start.</p>`;
  return jobs
    .map(
      (job) => `<a class="job card" href="/jobs/${esc(job.id)}"${active(job) ? " data-active" : ""}>
  <div class="row">${statusBadge(job.status)}<span class="muted small">${job.clip_count ?? 0}/${job.clips_wanted} clips</span><span class="spacer"></span><time class="muted small" datetime="${esc(job.created_at)}">${esc(job.created_at.slice(0, 16).replace("T", " "))}</time></div>
  <div class="job-title">${esc(vodLabel(job))}${job.channel ? ` <span class="muted">· ${esc(job.channel)}</span>` : ""}</div>
  ${job.status === "failed" && job.error ? `<div class="small" style="color:#ff8792">${esc(job.error.slice(0, 160))}</div>` : `<div class="muted small">${stageLine(job)}</div>`}
  ${progressBar(job)}
</a>`,
    )
    .join("\n");
}

export function homePage(jobs: Job[]): string {
  return layout(
    "Clip Engine",
    `<form id="new-job" class="card" method="post" action="/api/jobs">
  <div class="fields">
    <div><label for="vod_url">Twitch VOD link</label><input id="vod_url" name="vod_url" type="url" inputmode="url" placeholder="https://www.twitch.tv/videos/…" autocomplete="off" required></div>
    <div><label for="clips">Clips</label><input id="clips" name="clips" type="number" inputmode="numeric" min="1" max="30" value="10" required></div>
  </div>
  <button class="btn primary block" type="submit">Make clips</button>
  <p id="form-error" class="error"></p>
</form>
<h2>Jobs</h2>
<div id="jobs" class="jobs">${jobList(jobs)}</div>`,
    `
var form=document.getElementById('new-job');
form.addEventListener('submit',async function(e){e.preventDefault();var btn=form.querySelector('button'),err=document.getElementById('form-error');btn.disabled=true;err.textContent='';
try{var r=await fetch('/api/jobs',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({vod_url:form.vod_url.value,clips:Number(form.clips.value)})});var d=await r.json();if(!r.ok)throw new Error(d.error||'Request failed');location.href='/jobs/'+d.id;}catch(x){err.textContent=x.message;btn.disabled=false;}});
poll(function(){return !!document.querySelector('#jobs [data-active]');},function(doc){var n=doc.getElementById('jobs');if(n)document.getElementById('jobs').innerHTML=n.innerHTML;});
`,
  );
}

function clipCard(job: Job, clip: Clip): string {
  const key = [clip.n, clip.video_key, clip.preview_key, clip.thumb_key, clip.title].join("|");
  const meta = [
    `#${clip.n}`,
    clip.duration != null && clock(clip.duration),
    clip.score != null && `score ${clip.score.toFixed(clip.score < 10 ? 2 : 0)}`,
  ].filter(Boolean);
  return `<article class="clip" data-key="${esc(key)}">
  <video controls playsinline preload="metadata"${clip.thumb_key ? ` poster="${esc(fileUrl(clip.thumb_key))}"` : ""} src="${esc(fileUrl(clip.preview_key || clip.video_key))}"></video>
  <div class="clip-body">
    <h3>${clip.emoji ? `${esc(clip.emoji)} ` : ""}${esc(clip.title || `Clip ${clip.n}`)}</h3>
    <p class="meta">${meta.join(" · ")}</p>
    <div class="clip-actions">
      <a class="btn primary" href="${esc(fileUrl(clip.video_key))}?download=1" download>Download</a>
      ${clip.vod_start != null ? `<a class="btn" href="${esc(job.vod_url)}?t=${twitchTimestamp(clip.vod_start)}" target="_blank" rel="noopener">Twitch @ ${clock(clip.vod_start)}</a>` : ""}
    </div>
  </div>
</article>`;
}

function jobSummary(job: Job, clipCount: number): string {
  return `<div class="row">${statusBadge(job.status)}<span class="muted small">${clipCount}/${job.clips_wanted} clips</span></div>
  <h1>${esc(vodLabel(job))}</h1>
  <div class="muted small">${job.channel ? `${esc(job.channel)} · ` : ""}<a href="${esc(job.vod_url)}" target="_blank" rel="noopener">${esc(job.vod_url.replace(/^https:\/\/www\./, ""))}</a> · <time datetime="${esc(job.created_at)}">${esc(job.created_at.slice(0, 16).replace("T", " "))}</time></div>
  ${progressBar(job)}
  ${job.status !== "failed" && stageLine(job) ? `<p class="stage">${stageLine(job)}</p>` : ""}
  ${job.error ? `<div class="errbox">${esc(job.error)}</div>` : ""}
  <div class="actions">
    ${job.status === "failed" ? `<button class="btn primary" type="button" data-action="retry">Retry</button>` : ""}
    <button class="btn danger" type="button" data-action="delete">Delete</button>
  </div>`;
}

function eventLog(events: JobEvent[]): string {
  return `<summary>Activity (${events.length})</summary>
<ol class="log">${events
    .map(
      (e) =>
        `<li><time data-short datetime="${esc(e.at)}">${esc(e.at.slice(11, 19))}</time>${e.stage ? `<b>${esc(e.stage)}</b> ` : ""}${esc(e.message)}</li>`,
    )
    .join("")}</ol>`;
}

export function jobPage(job: Job, clips: Clip[], events: JobEvent[]): string {
  return layout(
    `${vodLabel(job)} · Clip Engine`,
    `<section id="summary" class="card" data-id="${esc(job.id)}"${active(job) ? " data-active" : ""}>${jobSummary(job, clips.length)}</section>
<div id="clips-head"><h2>Clips</h2>${clips.length ? "" : `<p class="empty">${active(job) ? "Clips appear here as they finish rendering." : "No clips."}</p>`}</div>
<div id="clips" class="clips">${clips.map((c) => clipCard(job, c)).join("\n")}</div>
<details id="events">${eventLog(events)}</details>`,
    `
var summary=document.getElementById('summary'),id=summary.dataset.id;
document.addEventListener('click',async function(e){var b=e.target.closest('[data-action]');if(!b)return;var a=b.dataset.action;
if(a==='delete'&&!confirm('Delete this job and all its clips?'))return;b.disabled=true;
var r=await fetch('/api/jobs/'+id+(a==='retry'?'/retry':''),{method:a==='retry'?'POST':'DELETE'});
if(!r.ok){var d=await r.json().catch(function(){return{}});alert(d.error||'Request failed');b.disabled=false;return;}
location.href=a==='retry'?location.pathname:'/';});
function mergeClips(doc){var grid=document.getElementById('clips');var fresh=Array.prototype.slice.call(doc.querySelectorAll('#clips > .clip'));var cur={};grid.querySelectorAll(':scope > .clip').forEach(function(c){cur[c.dataset.key]=c;});
if(fresh.length===grid.children.length&&fresh.every(function(c){return cur[c.dataset.key];}))return;
grid.replaceChildren.apply(grid,fresh.map(function(c){return cur[c.dataset.key]||document.importNode(c,true);}));}
poll(function(){return document.getElementById('summary').hasAttribute('data-active');},function(doc){
var s=doc.getElementById('summary');if(!s)return;var cur=document.getElementById('summary');cur.innerHTML=s.innerHTML;if(s.hasAttribute('data-active'))cur.setAttribute('data-active','');else cur.removeAttribute('data-active');
document.getElementById('clips-head').innerHTML=doc.getElementById('clips-head').innerHTML;document.getElementById('events').innerHTML=doc.getElementById('events').innerHTML;mergeClips(doc);});
`,
  );
}

export function notFoundPage(): string {
  return layout("Not found · Clip Engine", `<p class="empty">Not found. <a href="/">Back to jobs</a></p>`);
}
