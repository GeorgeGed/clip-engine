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
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="9" fill="#1c1c1c"/><path d="M12.5 9.5l10 6.5-10 6.5z" fill="#fff"/></svg>',
  );

const ICONS = {
  home: '<path d="M4 10.5 12 4l8 6.5V19a1 1 0 0 1-1 1h-4.5v-6h-5v6H5a1 1 0 0 1-1-1z"/>',
  film: '<rect x="4" y="3.5" width="16" height="17" rx="2"/><path d="M8 3.5v17M16 3.5v17M4 8h4M4 12h4M4 16h4M16 8h4M16 12h4M16 16h4"/>',
  download: '<path d="M12 4v11m0 0-4.5-4.5M12 15l4.5-4.5M5 19.5h14"/>',
  external: '<path d="M14 5h5v5m0-5-8 8M10 5H6a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-4"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
  play: '<path d="M8 5.5v13l10.5-6.5z" fill="currentColor" stroke="none"/>',
  logout: '<path d="M15 4h3a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-3M10 8l-4 4 4 4M6 12h10"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
  sound: '<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4zM16 9a4 4 0 0 1 0 6M18.5 6.5a7.5 7.5 0 0 1 0 11"/>',
  trash: '<path d="M5 7h14M10 7V5h4v2M7 7l1 12h8l1-12"/>',
  retry: '<path d="M5 12a7 7 0 1 0 2-5M5 4v4h4"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4 4"/>',
  calendar: '<rect x="4" y="5.5" width="16" height="14" rx="2"/><path d="M4 10h16M8.5 3.5v4M15.5 3.5v4"/>',
  clock: '<circle cx="12" cy="12" r="8"/><path d="M12 8v4.5l3 1.5"/>',
  clips: '<rect x="7" y="3.5" width="10" height="17" rx="2"/><path d="M4 6.5v11M20 6.5v11"/>',
  arrow: '<path d="M5 12h14m0 0-5-5m5 5-5 5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  chevron: '<path d="m9 6 6 6-6 6"/>',
  star: '<path d="m12 4.5 2.3 4.7 5.2.8-3.8 3.6.9 5.1-4.6-2.4-4.6 2.4.9-5.1-3.8-3.6 5.2-.8z"/>',
};

function icon(name: keyof typeof ICONS): string {
  return '<svg class="ico" viewBox="0 0 24 24" aria-hidden="true">' + ICONS[name] + "</svg>";
}

const CSS = `
:root{color-scheme:light;--bg:#fff;--canvas:#f5f4ef;--line:#e6e4de;--line2:#d6d3cb;--text:#1b1b1a;--muted:#6d6b66;--faint:#a3a19a;--ink:#1c1c1c;--ink2:#2b2b2a;--soft:#f1f0eb;--run:#2f6fdb;--ok:#2e8b57;--bad:#d64545;--r:14px}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 Inter,-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",Roboto,Helvetica,Arial,sans-serif;-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}
button{font:inherit;color:inherit}
.ico{width:18px;height:18px;flex:none;fill:none;stroke:currentColor;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round}
.shell{display:grid;grid-template-columns:248px minmax(0,1fr);min-height:100vh}
.side{position:sticky;top:0;height:100vh;display:flex;flex-direction:column;padding:28px 18px 20px;border-right:1px solid var(--line);background:var(--bg)}
.brand{display:flex;align-items:center;gap:10px;font-size:18px;font-weight:650;letter-spacing:-.02em;padding:0 10px;margin-bottom:34px}
.mark{display:grid;place-items:center;width:26px;height:26px;border-radius:8px;background:var(--ink);color:#fff}
.mark .ico{width:12px;height:12px}
.nav{display:flex;flex-direction:column;gap:2px}
.nav a{display:flex;align-items:center;gap:12px;padding:9px 10px;border-radius:9px;font-size:15px;color:var(--text)}
.nav a:hover{background:var(--soft)}
.nav a.on{background:var(--soft);font-weight:550}
.nav .n{margin-left:auto;font-size:12px;min-width:22px;height:22px;display:grid;place-items:center;border-radius:50%;background:var(--soft);color:var(--muted)}
.nav a.on .n{background:var(--bg)}
.side h4{font-size:13px;font-weight:450;color:var(--faint);margin:32px 10px 10px}
.recent a{display:flex;align-items:center;gap:10px;padding:7px 10px;border-radius:9px;font-size:14px;min-width:0}
.recent a:hover{background:var(--soft)}
.recent a.on{background:var(--soft)}
.recent .t{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dot{width:7px;height:7px;border-radius:50%;flex:none;background:var(--faint)}
.dot.running,.dot.queued{background:var(--run)}.dot.done{background:var(--ok)}.dot.failed{background:var(--bad)}
.side-foot{margin-top:auto;padding:12px 10px 0;border-top:1px solid var(--line);display:flex;align-items:center;gap:10px;font-size:14px;color:var(--muted)}
.side-foot .spacer{flex:1}
.iconbtn{display:inline-grid;place-items:center;width:36px;height:36px;border-radius:10px;border:0;background:transparent;color:var(--muted);cursor:pointer}
.iconbtn:hover{background:var(--soft);color:var(--text)}
.mtop{display:none}
.spacer{flex:1}
.muted{color:var(--muted)}
.content{min-width:0}
.topbar{display:flex;align-items:center;gap:8px;padding:22px 40px;background:var(--canvas)}
.search{display:flex;align-items:center;gap:12px;flex:1;min-width:0;color:var(--muted)}
.search input{flex:1;min-width:0;border:0;background:transparent;font:inherit;font-size:15px;color:var(--text);outline:0;padding:8px 0}
.search input::placeholder{color:var(--faint)}
.tlink{display:inline-flex;align-items:center;gap:8px;padding:8px 12px;border-radius:10px;font-size:15px;color:var(--text);background:none;border:0;cursor:pointer;white-space:nowrap}
.tlink:hover{background:rgba(0,0,0,.04)}
.tlink.danger{color:var(--bad)}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:44px;padding:0 18px;border-radius:12px;border:1px solid var(--line2);background:var(--bg);color:var(--text);font-weight:500;font-size:15px;cursor:pointer;white-space:nowrap}
.btn:hover{border-color:var(--faint)}
.btn.dark{background:var(--ink);border-color:var(--ink);color:#fff}
.btn.dark:hover{background:var(--ink2)}
.btn.sm{min-height:34px;padding:0 12px;font-size:13px;border-radius:9px}
.btn:disabled{opacity:.5;cursor:default}
.band{background:var(--canvas);padding:8px 40px 34px;border-bottom:1px solid var(--line)}
.composer{display:flex;gap:10px;align-items:stretch;margin-bottom:30px}
.url{flex:1;min-width:0;display:flex;align-items:center;gap:10px;background:var(--bg);border:1px solid var(--line);border-radius:12px;padding:0 14px;color:var(--faint)}
.url:focus-within{border-color:var(--ink)}
.url input{flex:1;min-width:0;height:48px;border:0;background:transparent;color:var(--text);font:inherit;font-size:15px;outline:0}
.url input::placeholder{color:var(--faint)}
.count{display:flex;align-items:center;background:var(--bg);border:1px solid var(--line);border-radius:12px;padding:3px}
.count span{font-size:13px;color:var(--muted);padding:0 4px 0 10px}
.count button{width:34px;height:40px;border:0;border-radius:9px;background:transparent;font-size:18px;color:var(--text);cursor:pointer}
.count button:hover{background:var(--soft)}
.count input{width:30px;border:0;background:transparent;font:inherit;font-size:15px;font-weight:550;text-align:center;color:var(--text);outline:0;-moz-appearance:textfield}
.count input::-webkit-inner-spin-button,.count input::-webkit-outer-spin-button{-webkit-appearance:none;margin:0}
.error{color:var(--bad);font-size:13px;margin:-20px 0 18px}
.error:empty{display:none}
.stats{display:grid;grid-template-columns:minmax(260px,1.3fr) minmax(220px,1fr) .8fr .8fr;gap:32px;align-items:end}
.stat-title{font-size:16px;font-weight:500;margin:0 0 14px}
.chart{display:grid;grid-template-columns:22px 1fr;gap:6px;height:150px}
.yax{display:flex;flex-direction:column;justify-content:space-between;font-size:11px;color:var(--text);padding-bottom:22px}
.bars{display:grid;grid-template-columns:repeat(7,1fr);gap:14px;align-items:end;min-width:0}
.bar-col{display:flex;flex-direction:column;align-items:center;gap:6px;height:100%;justify-content:flex-end;min-width:0}
.bar-col i{display:block;width:100%;max-width:22px;background:var(--ink);border-radius:1px}
.bar-col i.zero{height:6px!important;background:repeating-linear-gradient(135deg,var(--line2) 0 2px,transparent 2px 5px)}
.bar-col i.ghost{background:repeating-linear-gradient(135deg,var(--faint) 0 1.5px,transparent 1.5px 4.5px)}
.bar-col span{font-size:11px;color:var(--text);height:16px}
.gauge{display:flex;flex-direction:column;align-items:center;position:relative}
.gauge svg{width:100%;max-width:280px;height:auto;display:block}
.gauge .gv{position:absolute;left:0;right:0;bottom:4px;text-align:center}
.gauge .gv b{display:block;font-size:30px;font-weight:500;letter-spacing:-.02em;line-height:1.1}
.gauge .gv span{font-size:13px;color:var(--text)}
.num{display:flex;flex-direction:column;justify-content:space-between;height:130px;padding-bottom:6px}
.num b{font-size:34px;font-weight:500;letter-spacing:-.02em;line-height:1}
.num .lab{display:flex;align-items:flex-end;justify-content:space-between;gap:8px;font-size:13px;color:var(--text);line-height:1.35}
.num .lab .ico{width:20px;height:20px}
.page{padding:32px 40px 60px}
.board{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:24px;align-items:start}
.col-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:18px}
.col-head h2{font-size:21px;font-weight:450;letter-spacing:-.01em;margin:0}
.chip{display:inline-flex;align-items:center;gap:6px;height:32px;padding:0 10px;border:1px solid var(--line2);border-radius:9px;font-size:14px;background:var(--bg);color:var(--text);white-space:nowrap}
.col-list{display:flex;flex-direction:column;gap:14px}
.card{display:block;background:var(--bg);border:1px solid var(--line2);border-radius:var(--r);padding:20px 20px 16px;transition:box-shadow .15s,border-color .15s}
a.card:hover{box-shadow:0 6px 24px rgba(0,0,0,.06);border-color:var(--faint)}
.card h3{font-size:17px;font-weight:500;line-height:1.3;margin:0 0 10px;letter-spacing:-.01em;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;word-break:break-word}
.card p{font-size:14px;line-height:1.4;margin:0 0 16px;color:var(--text);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;word-break:break-word}
.card .foot{display:flex;align-items:center;gap:10px}
.mini{display:inline-flex;align-items:center;gap:6px;height:30px;padding:0 9px;border:1px solid var(--line2);border-radius:8px;font-size:12px;white-space:nowrap}
.mini .ico{width:15px;height:15px}
.cnt{display:inline-flex;align-items:center;gap:4px;font-size:13px}
.cnt .ico{width:16px;height:16px}
.thumbs{display:flex;gap:6px;margin:0 0 16px}
.thumbs img{width:40px;height:71px;object-fit:cover;border-radius:6px;background:var(--soft)}
.card.dark{background:var(--ink);border-color:var(--ink);color:#fff}
.card.dark p{color:rgba(255,255,255,.88)}
.card.dark .mini{border-color:rgba(255,255,255,.25)}
.card.dark .meta-line{color:rgba(255,255,255,.8)}
.meta-line{display:flex;align-items:center;gap:8px;font-size:13px;margin:-4px 0 14px;min-width:0}
.meta-line span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.meta-line .ico{width:16px;height:16px}
.pbar{height:3px;border-radius:3px;background:rgba(255,255,255,.18);overflow:hidden;margin:0 0 16px}
.pbar span{display:block;height:100%;background:#fff;transition:width .5s}
.pbar.indet span{width:35%;animation:indet 1.3s ease-in-out infinite}
@keyframes indet{0%{transform:translateX(-100%)}100%{transform:translateX(300%)}}
.card.failed{border-color:rgba(214,69,69,.35)}
.card .err{color:var(--bad)}
.empty-col{border:1px dashed var(--line2);border-radius:var(--r);padding:22px;text-align:center;color:var(--faint);font-size:13px}
.empty{color:var(--muted);text-align:center;padding:40px 16px;border:1px dashed var(--line2);border-radius:var(--r);margin:0}

/* job page */
.crumbs{display:flex;align-items:center;gap:6px;flex:1;min-width:0;font-size:15px;color:var(--muted)}
.crumbs a:hover{color:var(--text)}
.crumbs .ico{width:14px;height:14px;color:var(--faint)}
.crumbs b{font-weight:500;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.jstats{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(220px,1fr) .7fr .7fr;gap:32px;align-items:end;padding-top:20px}
.jhead .pill{margin-bottom:12px}
.jhead h1{font-size:28px;font-weight:500;line-height:1.2;letter-spacing:-.02em;margin:0 0 10px;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;word-break:break-word}
.jsub{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:14px;color:var(--muted)}
.jsub a{display:inline-flex;align-items:center;gap:5px;color:var(--text)}
.jsub a:hover{text-decoration:underline}
.jsub .ico{width:15px;height:15px}
.pill{display:inline-flex;align-items:center;gap:7px;height:28px;padding:0 10px;border:1px solid var(--line2);border-radius:8px;font-size:13px;background:var(--bg);white-space:nowrap}
.steps{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;list-style:none;margin:30px 0 0;padding:0}
.steps li{display:flex;flex-direction:column;gap:8px;font-size:13px;color:var(--faint)}
.steps li:before{content:"";height:4px;border-radius:2px;background:var(--line)}
.steps li.done{color:var(--muted)}
.steps li.done:before{background:var(--ink)}
.steps li.now{color:var(--text);font-weight:500}
.steps li.now:before{background:repeating-linear-gradient(135deg,var(--ink) 0 3px,var(--line2) 3px 6px);background-size:8.5px 8.5px;animation:march .6s linear infinite}
@keyframes march{to{background-position:8.5px 0}}
.stage-msg{margin:12px 0 0;font-size:14px;color:var(--muted)}
.run{margin-top:28px;display:grid;grid-template-columns:minmax(0,1.6fr) minmax(240px,1fr);gap:24px;background:var(--bg);border:1px solid var(--line2);border-radius:var(--r);padding:20px 22px}
.run h3{font-size:16px;font-weight:500;margin:0 0 14px}
.tl{list-style:none;margin:0;padding:0}
.tl li{display:grid;grid-template-columns:14px minmax(0,1fr) auto;gap:12px;align-items:start;padding:9px 0;border-bottom:1px solid var(--line);font-size:14px}
.tl li:last-child{border-bottom:0}
.tl i{width:10px;height:10px;border-radius:50%;margin-top:5px;background:var(--ink)}
.tl li.now i{background:var(--run);box-shadow:0 0 0 4px rgba(47,111,219,.15);animation:pulse 1.4s ease-in-out infinite}
@keyframes pulse{50%{box-shadow:0 0 0 7px rgba(47,111,219,.05)}}
.tl li.failed i{background:var(--bad)}
.tl li.failed b{color:var(--bad)}
.tl b{font-weight:500}
.tl small{display:block;color:var(--muted);font-size:13px;margin-top:2px;word-break:break-word}
.tl .d{font-variant-numeric:tabular-nums;color:var(--muted);white-space:nowrap}
.tl li.now .d{color:var(--text);font-weight:500}
.kv{margin:0;display:grid;grid-template-columns:auto minmax(0,1fr);gap:10px 16px;font-size:14px;align-content:start}
.kv dt{color:var(--muted)}
.kv dd{margin:0;min-width:0;word-break:break-all;font-variant-numeric:tabular-nums}
.kv code{font:13px ui-monospace,SFMono-Regular,Menlo,monospace}
.kv a{text-decoration:underline}
.failbox{margin-top:24px;background:var(--bg);border:1px solid rgba(214,69,69,.35);border-radius:var(--r);padding:18px 20px}
.failbox h3{margin:0 0 8px;font-size:16px;font-weight:500;color:var(--bad)}
.errtext{font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--text);white-space:pre-wrap;word-break:break-word;margin:0 0 14px;max-height:200px;overflow:auto}
.section-head{display:flex;align-items:center;justify-content:space-between;margin:0 0 18px}
.section-head h2{font-size:21px;font-weight:450;letter-spacing:-.01em;margin:0}
.clips{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:20px}
.clip{display:flex;flex-direction:column;background:var(--bg);border:1px solid var(--line2);border-radius:var(--r);padding:12px 12px 14px;min-width:0;transition:box-shadow .15s}
.clip:hover{box-shadow:0 6px 24px rgba(0,0,0,.06)}
.thumb{position:relative;display:block;width:100%;aspect-ratio:9/16;border:0;padding:0;border-radius:10px;overflow:hidden;background:var(--soft);cursor:pointer}
.thumb img,.thumb video{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.thumb .rank{position:absolute;top:8px;left:8px;z-index:1;height:26px;min-width:26px;padding:0 8px;display:grid;place-items:center;border-radius:7px;background:var(--bg);color:var(--text);font-size:12px;font-weight:550}
.thumb .rank.top{background:var(--ink);color:#fff}
.thumb .playi{position:absolute;left:50%;top:50%;width:48px;height:48px;margin:-24px 0 0 -24px;display:grid;place-items:center;border-radius:50%;background:rgba(255,255,255,.92);color:var(--ink);opacity:0;transform:scale(.9);transition:.2s}
.thumb .playi .ico{width:20px;height:20px;margin-left:3px}
.thumb:hover .playi{opacity:1;transform:none}
@media(hover:none){.thumb .playi{opacity:1;transform:none;width:42px;height:42px;margin:-21px 0 0 -21px}}
.clip h3{font-size:16px;font-weight:500;line-height:1.3;letter-spacing:-.01em;margin:14px 4px 12px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;word-break:break-word}
.clip .foot{display:flex;align-items:center;gap:8px;margin:0 4px 12px;flex-wrap:wrap}
.clip .actions{display:flex;gap:8px;margin:auto 4px 0}
.clip .actions .btn{flex:1}
.clip .actions .btn.icon{flex:none;width:40px;padding:0}
details{margin-top:40px;border-top:1px solid var(--line);padding-top:12px}
details summary{cursor:pointer;color:var(--muted);font-size:14px;padding:8px 0;list-style:none}
details summary::-webkit-details-marker{display:none}
details summary:after{content:" +"}
details[open] summary:after{content:" −"}
.log{list-style:none;margin:6px 0 0;padding:0;font-size:13px}
.log li{display:flex;gap:14px;padding:7px 0;border-bottom:1px solid var(--line);word-break:break-word}
.log time{color:var(--faint);font-variant-numeric:tabular-nums;flex:none;min-width:80px}
.log b{font-weight:500;margin-right:6px}

/* player */
.player{position:fixed;inset:0;z-index:50;background:#000;display:flex;justify-content:center;color:#fff}
.player[hidden]{display:none}
.feed{position:relative;height:100%;width:100%;max-width:calc(100dvh*9/16);overflow-y:scroll;scroll-snap-type:y mandatory;overscroll-behavior:contain;scrollbar-width:none}
.feed::-webkit-scrollbar{display:none}
.slide{position:relative;height:100dvh;scroll-snap-align:start;scroll-snap-stop:always;display:flex;align-items:center;justify-content:center;background:#000}
.slide video{width:100%;height:100%;object-fit:contain;background:#000}
.slide .shade{position:absolute;left:0;right:0;bottom:0;padding:90px 16px calc(18px + env(safe-area-inset-bottom));background:linear-gradient(transparent,rgba(0,0,0,.72) 40%,rgba(0,0,0,.94));pointer-events:none}
.slide .shade>*{pointer-events:auto}
.slide h3{font-size:17px;font-weight:550;line-height:1.3;margin:0 0 4px}
.slide .meta{font-size:13px;color:rgba(255,255,255,.7);margin:0 0 12px}
.slide .acts{display:flex;gap:8px}
.slide .acts .btn{flex:1;border-color:transparent}
.slide .acts .btn.primary{background:#fff;color:var(--ink)}
.slide .acts .btn:not(.primary){background:rgba(255,255,255,.14);color:#fff}
.slide .paused{position:absolute;left:50%;top:50%;width:68px;height:68px;margin:-34px 0 0 -34px;display:none;place-items:center;border-radius:50%;background:rgba(0,0,0,.5);pointer-events:none}
.slide .paused .ico{width:30px;height:30px;margin-left:4px}
.slide.is-paused .paused{display:grid}
.slide .prog{position:absolute;left:0;right:0;bottom:0;height:3px;background:rgba(255,255,255,.15)}
.slide .prog span{display:block;height:100%;width:0;background:#fff}
.ptop{position:fixed;z-index:51;top:0;left:0;right:0;display:flex;align-items:center;gap:8px;padding:12px;padding-top:max(12px,env(safe-area-inset-top));pointer-events:none}
.ptop>*{pointer-events:auto}
.ptop .iconbtn{background:rgba(0,0,0,.45);color:#fff}
.ptop .ctr{font-size:13px;font-weight:550;padding:6px 10px;border-radius:999px;background:rgba(0,0,0,.45);font-variant-numeric:tabular-nums}
.unmute{display:none!important}
.player.muted .unmute{display:inline-flex!important}
body.locked{overflow:hidden}

/* login */
.login-wrap{min-height:100dvh;display:grid;place-items:center;padding:24px;background:var(--canvas)}
.login{width:100%;max-width:380px;background:var(--bg);border:1px solid var(--line2);border-radius:18px;padding:36px 28px 28px}
.login .brand{padding:0;margin:0 0 26px}
.login h1{font-size:24px;font-weight:500;letter-spacing:-.02em;margin:0 0 6px}
.login p.muted{margin:0 0 24px}
.login label{display:block;font-size:13px;color:var(--muted);margin-bottom:6px}
.login input{width:100%;height:48px;padding:0 14px;font:inherit;font-size:15px;color:var(--text);background:var(--bg);border:1px solid var(--line2);border-radius:12px;outline:0}
.login input:focus{border-color:var(--ink)}
.login .error{margin:10px 0 0}
.login .btn{width:100%;margin-top:16px;min-height:48px}

@media(max-width:1180px){.stats{grid-template-columns:1fr 1fr}.board{grid-template-columns:repeat(2,minmax(0,1fr))}.jstats{grid-template-columns:1fr 1fr}.jhead{grid-column:1/-1}}
@media(max-width:860px){
.run{grid-template-columns:minmax(0,1fr);padding:16px}
.shell{display:block}
.side{display:none}
.mtop{display:flex;align-items:center;gap:10px;padding:14px 16px;padding-top:max(14px,env(safe-area-inset-top));background:var(--bg);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:10}
.mtop .brand{margin:0;padding:0;font-size:17px}
.topbar{padding:14px 16px}
.band{padding:4px 16px 24px}
.page{padding:24px 16px 48px}
.composer{flex-wrap:wrap;margin-bottom:24px}
.url{flex-basis:100%}
.composer .btn{flex:1}
.stats{grid-template-columns:1fr 1fr;gap:22px 16px}
.stats .chart-box{grid-column:1/-1}
.stats .gauge{grid-column:1/-1}
.num{height:auto;gap:12px}
.num b{font-size:28px}
.board{grid-template-columns:minmax(0,1fr);gap:28px}
.col.is-empty{display:none}
.jstats{grid-template-columns:1fr 1fr;gap:22px 16px}
.jstats .gauge{grid-column:1/-1}
.jhead h1{font-size:22px}
.steps{gap:6px}.steps li{font-size:11px}
.clips{grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.clip{padding:8px 8px 10px}
.clip h3{font-size:14px;margin:10px 2px 8px}
.clip .foot{margin:0 2px 10px;gap:6px}
.clip .foot .mini:nth-child(n+3){display:none}
.clip .actions{margin:auto 2px 0}
.clip .actions .btn{min-height:38px;font-size:13px;padding:0 8px}
.clip .actions .btn.icon{width:38px}
.mini{height:26px;font-size:11px;padding:0 7px}
.topbar .tlink .lbl{display:none}
}
`;

const CLIENT_COMMON = `
function localizeTimes(root){root.querySelectorAll('time[datetime]').forEach(function(t){var d=new Date(t.getAttribute('datetime'));if(isNaN(d))return;if(t.hasAttribute('data-short')){t.textContent=d.toLocaleTimeString([],{hour:'numeric',minute:'2-digit',second:'2-digit'});return;}if(t.hasAttribute('data-day')){t.textContent=d.toLocaleDateString([],{day:'2-digit',month:'short'});return;}t.textContent=d.toLocaleString([],{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'});});}
localizeTimes(document);
async function fetchPage(){var r=await fetch(location.href,{headers:{accept:'text/html'},cache:'no-store'});if(r.redirected||!r.ok)return null;return new DOMParser().parseFromString(await r.text(),'text/html');}
function poll(isActive,apply){if(!isActive())return;setTimeout(async function tick(){try{var doc=await fetchPage();if(doc){apply(doc);localizeTimes(document);}}catch(e){}if(isActive())setTimeout(tick,4000);},4000);}
`;

const active = (job: Job) => job.status === "queued" || job.status === "running";

function vodLabel(job: Job): string {
  return job.vod_title || `Twitch VOD ${job.vod_url.split("/").pop()}`;
}

function sidebar(recent: Job[], current: string | null): string {
  const running = recent.filter(active).length;
  return `<aside class="side">
  <a class="brand" href="/"><span class="mark">${icon("play")}</span>Clip Engine</a>
  <nav class="nav">
    <a href="/" class="${current ? "" : "on"}">${icon("home")}Dashboard${running ? `<span class="n">${running}</span>` : ""}</a>
  </nav>
  ${
    recent.length
      ? `<h4>Recent VODs</h4><nav class="recent">${recent
          .slice(0, 8)
          .map(
            (j) =>
              `<a href="/jobs/${esc(j.id)}" class="${j.id === current ? "on" : ""}" title="${esc(vodLabel(j))}"><span class="dot ${esc(j.status)}"></span><span class="t">${esc(vodLabel(j))}</span></a>`,
          )
          .join("")}</nav>`
      : ""
  }
  <div class="side-foot"><span class="mark" style="width:30px;height:30px;border-radius:50%;background:var(--soft);color:var(--muted)">${icon("film")}</span><span>Signed in</span><span class="spacer"></span><form method="post" action="/logout"><button class="iconbtn" type="submit" title="Log out" aria-label="Log out">${icon("logout")}</button></form></div>
</aside>`;
}

function layout(title: string, body: string, script = "", shell: { recent: Job[]; current: string | null } | null = null): string {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#ffffff">
<meta name="robots" content="noindex">
<title>${esc(title)}</title>
<link rel="icon" href="${FAVICON}">
<style>${CSS}</style>
</head>
<body>
${
  shell
    ? `<div class="shell">${sidebar(shell.recent, shell.current)}<div class="content"><header class="mtop"><a class="brand" href="/"><span class="mark">${icon("play")}</span>Clip Engine</a><span class="spacer"></span><form method="post" action="/logout"><button class="iconbtn" type="submit" aria-label="Log out">${icon("logout")}</button></form></header>${body}</div></div>`
    : body
}
${script ? `<script>${CLIENT_COMMON}${script}</script>` : ""}
</body>
</html>`;
}

export function loginPage(error: string | null, next: string): string {
  return layout(
    "Log in · Clip Engine",
    `<div class="login-wrap"><form class="login" method="post" action="/login">
  <div class="brand"><span class="mark">${icon("play")}</span>Clip Engine</div>
  <h1>Welcome back</h1>
  <p class="muted">Sign in to turn Twitch VODs into vertical clips.</p>
  <input type="hidden" name="next" value="${esc(next)}">
  <label for="password">Password</label>
  <input id="password" name="password" type="password" autocomplete="current-password" required autofocus>
  <p class="error">${esc(error)}</p>
  <button class="btn dark" type="submit">Log in</button>
</form></div>`,
  );
}

const STATUS_LABEL: Record<string, string> = { queued: "Queued", running: "In progress", done: "Ready", failed: "Failed" };

function pill(status: string): string {
  return `<span class="pill"><span class="dot ${esc(status)}"></span>${esc(STATUS_LABEL[status] ?? status)}</span>`;
}

function pct(job: Job): number | null {
  if (job.status === "done") return 100;
  if (job.progress == null) return null;
  return Math.round(Math.min(1, Math.max(0, job.progress)) * 100);
}

function gauge(value: number, label: string, shown = `${value}%`): string {
  const n = 44;
  const lit = Math.round((Math.min(100, Math.max(0, value)) / 100) * n);
  const ticks = Array.from({ length: n }, (_, i) => {
    const a = Math.PI - (Math.PI * i) / (n - 1);
    const c = Math.cos(a), s = Math.sin(a);
    return `<line x1="${(140 + 96 * c).toFixed(1)}" y1="${(132 - 96 * s).toFixed(1)}" x2="${(140 + 126 * c).toFixed(1)}" y2="${(132 - 126 * s).toFixed(1)}" stroke="${i < lit ? "#1c1c1c" : "#d6d3cb"}" stroke-width="2" stroke-linecap="round"/>`;
  }).join("");
  return `<div class="gauge"><svg viewBox="0 0 280 136" aria-hidden="true">${ticks}</svg><div class="gv"><b>${shown}</b><span>${esc(label)}</span></div></div>`;
}

const DAY = 86_400_000;

function clipsChart(jobs: Job[]): string {
  const today = Math.floor(Date.now() / DAY);
  const days = Array.from({ length: 7 }, (_, i) => today - 6 + i);
  const made = days.map(() => 0);
  const pending = days.map(() => 0);
  for (const j of jobs) {
    const i = Math.floor(Date.parse(j.created_at) / DAY) - days[0];
    if (i < 0 || i > 6) continue;
    made[i] += j.clip_count ?? 0;
    if (active(j)) pending[i] += Math.max(0, j.clips_wanted - (j.clip_count ?? 0));
  }
  const top = Math.max(4, ...made.map((m, i) => m + pending[i]));
  const max = Math.ceil(top / 2) * 2;
  const name = (d: number) => new Date(d * DAY).toLocaleDateString("en-US", { weekday: "short", timeZone: "UTC" });
  return `<div class="chart-box"><h3 class="stat-title">Clips this week</h3><div class="chart"><div class="yax"><span>${max}</span><span>${max / 2}</span><span>0</span></div><div class="bars">${days
    .map((d, i) => {
      const h = (v: number) => ((v / max) * 112).toFixed(1);
      const bars = made[i] || pending[i]
        ? `${pending[i] ? `<i class="ghost" style="height:${h(pending[i])}px" title="${pending[i]} on the way"></i>` : ""}${made[i] ? `<i style="height:${h(made[i])}px" title="${made[i]} clips"></i>` : ""}`
        : `<i class="zero"></i>`;
      return `<div class="bar-col" style="gap:0">${bars}<span style="margin-top:6px">${name(d)}</span></div>`;
    })
    .join("")}</div></div></div>`;
}

function numStat(value: string | number, label: string, href?: string): string {
  return `<div class="num"><b>${value}</b><div class="lab"><span>${label}</span>${href ? `<a href="${href}" aria-label="${esc(label.replace(/<[^>]+>/g, " "))}">${icon("arrow")}</a>` : ""}</div></div>`;
}

function homeStats(jobs: Job[]): string {
  const finished = jobs.filter((j) => j.status === "done" || j.status === "failed");
  const ok = finished.filter((j) => j.status === "done").length;
  const rate = finished.length ? Math.round((ok / finished.length) * 100) : 0;
  const clips = jobs.reduce((n, j) => n + (j.clip_count ?? 0), 0);
  return `${clipsChart(jobs)}
${gauge(rate, "Successful jobs", finished.length ? `${rate}%` : "–")}
${numStat(jobs.filter(active).length, "Jobs<br>in progress")}
${numStat(clips, "Clips ready<br>to download")}`;
}

function jobCard(job: Job): string {
  const count = job.clip_count ?? 0;
  const thumbs = (job.covers ?? "").split("|").filter(Boolean).slice(0, 3);
  const running = job.status === "running";
  const p = pct(job);
  const desc =
    job.status === "failed"
      ? `<p class="err">${esc((job.error ?? "Failed").split("\n")[0].slice(0, 160))}</p>`
      : active(job)
        ? `<p>${esc(job.message || (job.status === "queued" ? "Waiting for Modal to pick it up" : "Starting"))}</p>`
        : `<p>${count} vertical clip${count === 1 ? "" : "s"} ready to download.</p>`;
  return `<a class="card ${running ? "dark" : ""} ${job.status === "failed" ? "failed" : ""}" href="/jobs/${esc(job.id)}" data-search="${esc((vodLabel(job) + " " + (job.channel ?? "")).toLowerCase())}"${active(job) ? " data-active" : ""}>
  <h3>${esc(vodLabel(job))}</h3>
  ${job.channel ? `<div class="meta-line">${icon("film")}<span>${esc(job.channel)}</span></div>` : ""}
  ${desc}
  ${running ? `<div class="pbar${p == null ? " indet" : ""}"><span style="width:${p ?? 0}%"></span></div>` : ""}
  ${thumbs.length ? `<div class="thumbs">${thumbs.map((k) => `<img src="${esc(fileUrl(k))}" alt="" loading="lazy">`).join("")}</div>` : ""}
  <div class="foot"><span class="mini">${icon("calendar")}<time data-day datetime="${esc(job.created_at)}">${esc(job.created_at.slice(0, 10))}</time></span><span class="spacer"></span><span class="cnt" title="Clips">${icon("clips")}${count}/${job.clips_wanted}</span>${running && p != null ? `<span class="cnt">${p}%</span>` : ""}</div>
</a>`;
}

const COLUMNS: [string, string][] = [
  ["queued", "Queued"],
  ["running", "In progress"],
  ["done", "Ready"],
  ["failed", "Failed"],
];

export function jobList(jobs: Job[]): string {
  if (!jobs.length) return `<p class="empty" style="grid-column:1/-1">No VODs yet. Paste a Twitch VOD link above and the clips land here.</p>`;
  return COLUMNS.map(([status, label]) => {
    const list = jobs.filter((j) => j.status === status);
    return `<section class="col${list.length ? "" : " is-empty"}"><div class="col-head"><h2>${label}</h2><span class="chip">${list.length}</span></div><div class="col-list">${
      list.length ? list.map(jobCard).join("\n") : `<div class="empty-col">Nothing here</div>`
    }</div></section>`;
  }).join("\n");
}

export function homePage(jobs: Job[]): string {
  return layout(
    "Clip Engine",
    `<div class="topbar"><label class="search">${icon("search")}<input id="q" type="search" placeholder="Search VODs…" aria-label="Search VODs" autocomplete="off"></label></div>
<section class="band">
  <form id="new-job" class="composer" method="post" action="/api/jobs">
    <label class="url">${icon("link")}<input id="vod_url" name="vod_url" type="url" inputmode="url" placeholder="Paste a Twitch VOD link, like twitch.tv/videos/…" aria-label="Twitch VOD link" autocomplete="off" required></label>
    <div class="count"><span>Clips</span><button type="button" data-step="-1" aria-label="Fewer">−</button><input id="clips" name="clips" type="number" inputmode="numeric" min="1" max="30" value="10" aria-label="Number of clips" required><button type="button" data-step="1" aria-label="More">+</button></div>
    <button class="btn dark" type="submit">${icon("plus")}Make clips</button>
  </form>
  <p id="form-error" class="error"></p>
  <div id="stats" class="stats">${homeStats(jobs)}</div>
</section>
<main class="page"><div id="jobs" class="board">${jobList(jobs)}</div></main>`,
    `
var form=document.getElementById('new-job'),q=document.getElementById('q');
form.querySelectorAll('[data-step]').forEach(function(b){b.addEventListener('click',function(){var n=Number(form.clips.value)||10;form.clips.value=Math.min(30,Math.max(1,n+Number(b.dataset.step)));});});
form.addEventListener('submit',async function(e){e.preventDefault();var btn=form.querySelector('[type=submit]'),err=document.getElementById('form-error');btn.disabled=true;err.textContent='';
try{var r=await fetch('/api/jobs',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({vod_url:form.vod_url.value,clips:Number(form.clips.value)})});var d=await r.json();if(!r.ok)throw new Error(d.error||'Request failed');location.href='/jobs/'+d.id;}catch(x){err.textContent=x.message;btn.disabled=false;}});
function filter(){var v=q.value.trim().toLowerCase();document.querySelectorAll('#jobs .card').forEach(function(c){c.hidden=!!v&&c.dataset.search.indexOf(v)<0;});}
q.addEventListener('input',filter);
poll(function(){return !!document.querySelector('#jobs [data-active]');},function(doc){['jobs','stats'].forEach(function(id){var n=doc.getElementById(id);if(n)document.getElementById(id).innerHTML=n.innerHTML;});filter();});
`,
    { recent: jobs, current: null },
  );
}

const STEPS: [string, string][] = [
  ["download", "Download"],
  ["transcribe", "Transcribe"],
  ["rank", "Find clips"],
  ["title", "Titles"],
  ["render", "Render"],
];

function stepper(job: Job): string {
  const at = Math.max(0, STEPS.findIndex(([s]) => s === job.stage));
  return `<ol class="steps">${STEPS.map(([, label], i) => `<li class="${i < at ? "done" : i === at ? "now" : ""}">${label}</li>`).join("")}</ol>`;
}

function clipTitle(clip: Clip): string {
  return (clip.emoji ? clip.emoji + " " : "") + (clip.title || `Clip ${clip.n}`);
}

function clipCard(job: Job, clip: Clip): string {
  const key = [clip.n, clip.video_key, clip.preview_key, clip.thumb_key, clip.title].join("|");
  const download = fileUrl(clip.video_key) + "?download=1";
  const twitch = clip.vod_start != null ? `${job.vod_url}?t=${twitchTimestamp(clip.vod_start)}` : "";
  const meta = [
    clip.duration != null && clock(clip.duration),
    clip.vod_start != null && `at ${clock(clip.vod_start)}`,
    clip.score != null && `score ${clip.score.toFixed(clip.score < 10 ? 2 : 0)}`,
  ].filter(Boolean);
  return `<article class="clip" data-key="${esc(key)}" data-src="${esc(fileUrl(clip.preview_key || clip.video_key))}" data-poster="${clip.thumb_key ? esc(fileUrl(clip.thumb_key)) : ""}" data-title="${esc(clipTitle(clip))}" data-meta="${esc(meta.join(" · "))}" data-download="${esc(download)}" data-twitch="${esc(twitch)}">
  <button class="thumb" type="button" data-open aria-label="Play ${esc(clipTitle(clip))}">
    ${clip.thumb_key ? `<img src="${esc(fileUrl(clip.thumb_key))}" alt="" loading="lazy">` : `<video src="${esc(fileUrl(clip.preview_key || clip.video_key))}#t=1" preload="metadata" muted playsinline></video>`}
    <span class="rank${clip.n === 1 ? " top" : ""}">#${clip.n}</span>
    <span class="playi">${icon("play")}</span>
  </button>
  <h3>${esc(clipTitle(clip))}</h3>
  <div class="foot">
    ${clip.duration != null ? `<span class="mini">${icon("clock")}${clock(clip.duration)}</span>` : ""}
    ${clip.vod_start != null ? `<span class="mini" title="Position in the VOD">${icon("film")}${clock(clip.vod_start)}</span>` : ""}
  </div>
  <div class="actions">
    <a class="btn dark sm" href="${esc(download)}" download>${icon("download")}Download</a>
    ${twitch ? `<a class="btn sm icon" href="${esc(twitch)}" target="_blank" rel="noopener" title="Open on Twitch at ${clock(clip.vod_start!)}" aria-label="Open on Twitch">${icon("external")}</a>` : ""}
  </div>
</article>`;
}

function jobSummary(job: Job, clips: Clip[], events: JobEvent[], modalUrl: string | null): string {
  const p = pct(job);
  const runtime = clips.reduce((t, c) => t + (c.duration ?? 0), 0);
  return `<div class="jstats">
  <div class="jhead">
    ${pill(job.status)}
    <h1>${esc(vodLabel(job))}</h1>
    <div class="jsub">${job.channel ? `<span>${esc(job.channel)}</span>` : ""}<time datetime="${esc(job.created_at)}">${esc(job.created_at.slice(0, 16).replace("T", " "))}</time><a href="${esc(job.vod_url)}" target="_blank" rel="noopener">${icon("external")}Open VOD</a></div>
  </div>
  ${
    job.status === "failed"
      ? gauge(p ?? 0, "Stopped", "–")
      : gauge(p ?? 0, job.status === "done" ? "Complete" : job.status === "queued" ? "Queued" : "Progress", p == null ? "…" : `${p}%`)
  }
  ${numStat(`${clips.length}<span class="muted" style="font-size:20px">/${job.clips_wanted}</span>`, "Clips<br>ready")}
  ${numStat(runtime ? clock(runtime) : "–", "Total<br>runtime")}
</div>
${active(job) ? `${stepper(job)}<p class="stage-msg">${esc(job.message || (job.status === "queued" ? "Waiting for Modal to pick this up" : "Starting"))}</p>` : ""}
${
  job.status === "failed"
    ? `<div class="failbox"><h3>This job failed${job.stage && job.stage !== "failed" ? ` during ${esc(job.stage)}` : ""}</h3><pre class="errtext">${esc(job.error || job.message || "Unknown error")}</pre><button class="btn dark sm" type="button" data-action="retry">${icon("retry")}Retry</button></div>`
    : ""
}
${runPanel(job, events, modalUrl)}`;
}

const STAGE_LABEL: Record<string, string> = {
  queued: "Queued",
  start: "Starting",
  download: "Download VOD",
  transcribe: "Transcribe",
  rank: "Find & rank clips",
  title: "Write titles",
  render: "Render & upload",
  done: "Finished",
  failed: "Failed",
};

function dur(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000));
  if (s < 60) return s + "s";
  const m = Math.floor(s / 60);
  if (m < 60) return m + "m " + String(s % 60).padStart(2, "0") + "s";
  return Math.floor(m / 60) + "h " + String(m % 60).padStart(2, "0") + "m";
}

function runPanel(job: Job, events: JobEvent[], modalUrl: string | null): string {
  const retry = events.findLastIndex((e) => e.stage === "queued" && e.message === "Retry requested");
  const earlier = retry > 0 ? events.slice(0, retry).filter((e) => e.stage === "failed").length : 0;
  const attempt = retry > 0 ? events.slice(retry) : events;
  const rows: { stage: string; at: string; message: string | null }[] = [];
  for (const e of attempt) {
    const last = rows.at(-1);
    const stage = e.stage ?? last?.stage ?? "queued";
    if (last && last.stage === stage) last.message = e.message ?? last.message;
    else rows.push({ stage, at: e.at, message: e.message });
  }
  const live = active(job);
  const items = rows
    .map((row, i) => {
      const next = rows[i + 1];
      const state = row.stage === "failed" ? "failed" : !next && live ? "now" : "";
      const d = next
        ? dur(Date.parse(next.at) - Date.parse(row.at))
        : live
          ? `<span data-since="${esc(row.at)}">${dur(Date.now() - Date.parse(row.at))}</span>`
          : "";
      return `<li class="${state}"><i></i><div><b>${esc(STAGE_LABEL[row.stage] ?? row.stage)}</b>${row.message ? `<small>${esc(row.message.length > 180 ? row.message.slice(0, 179) + "…" : row.message)}</small>` : ""}</div><span class="d">${d}</span></li>`;
    })
    .join("");
  const started = attempt[0]?.at ?? job.created_at;
  const total = job.finished_at
    ? dur(Date.parse(job.finished_at) - Date.parse(started))
    : `<span data-since="${esc(started)}">${dur(Date.now() - Date.parse(started))}</span>`;
  const stamp = (t: string) => `<time datetime="${esc(t)}">${esc(t.slice(0, 16).replace("T", " "))}</time>`;
  return `<div class="run">
  <div><h3>Run timeline</h3><ol class="tl">${items}</ol>${earlier ? `<p class="stage-msg">${earlier} earlier attempt${earlier === 1 ? "" : "s"} failed. The full history is in the activity log below.</p>` : ""}</div>
  <div><h3>Run details</h3><dl class="kv">
    <dt>Run ID</dt><dd><code>${esc(job.id)}</code></dd>
    ${earlier ? `<dt>Attempt</dt><dd>${earlier + 1}</dd>` : ""}
    <dt>Modal call</dt><dd>${job.modal_call_id ? `<code>${esc(job.modal_call_id)}</code>` : "–"}${modalUrl ? `<br><a href="${esc(modalUrl)}" target="_blank" rel="noopener">Open in Modal</a>` : ""}</dd>
    <dt>Started</dt><dd>${stamp(started)}</dd>
    <dt>${job.finished_at ? "Finished" : "Status"}</dt><dd>${job.finished_at ? stamp(job.finished_at) : esc(STATUS_LABEL[job.status] ?? job.status)}</dd>
    <dt>${job.finished_at ? "Total time" : "Elapsed"}</dt><dd>${total}</dd>
    <dt>Clips</dt><dd>${job.clip_count ?? 0} of ${job.clips_wanted}</dd>
  </dl></div>
</div>`;
}

function eventLog(events: JobEvent[]): string {
  return `<summary>Activity log (${events.length})</summary>
<ol class="log">${events
    .map(
      (e) =>
        `<li><time data-short datetime="${esc(e.at)}">${esc(e.at.slice(11, 19))}</time><span>${e.stage ? `<b>${esc(e.stage)}</b>` : ""}${esc(e.message)}</span></li>`,
    )
    .join("")}</ol>`;
}

function clipsHead(job: Job, clips: Clip[]): string {
  if (!clips.length)
    return job.status === "failed"
      ? ""
      : `<p class="empty">${active(job) ? "Clips show up here one by one as they finish rendering." : "No clips."}</p>`;
  return `<div class="section-head"><h2>Clips</h2><span class="chip">${clips.length}</span></div>`;
}

export function jobPage(
  job: Job,
  clips: Clip[],
  events: JobEvent[],
  recent: Job[] = [],
  modalUrl: string | null = null,
): string {
  return layout(
    `${vodLabel(job)} · Clip Engine`,
    `<div class="topbar"><nav class="crumbs"><a href="/">Dashboard</a>${icon("chevron")}<b>${esc(vodLabel(job))}</b></nav><a class="tlink" href="${esc(job.vod_url)}" target="_blank" rel="noopener">${icon("external")}<span class="lbl">Twitch</span></a><button class="tlink danger" type="button" data-action="delete">${icon("trash")}<span class="lbl">Delete</span></button></div>
<section class="band"><div id="summary" data-id="${esc(job.id)}"${active(job) ? " data-active" : ""}>${jobSummary(job, clips, events, modalUrl)}</div></section>
<main class="page">
<div id="clips-head">${clipsHead(job, clips)}</div>
<div id="clips" class="clips">${clips.map((c) => clipCard(job, c)).join("\n")}</div>
<details id="events">${eventLog(events)}</details>
</main>
<div id="player" class="player" hidden><div class="ptop"><button class="iconbtn" type="button" data-close aria-label="Close">${icon("close")}</button><span class="ctr"></span><span class="spacer"></span><button class="btn sm unmute" type="button" data-unmute>${icon("sound")}Tap for sound</button></div><div class="feed"></div></div>
<template id="slide-tpl"><section class="slide"><video playsinline loop preload="metadata"></video><span class="paused">${icon("play")}</span><div class="shade"><h3></h3><p class="meta"></p><div class="acts"><a class="btn primary" data-dl download>${icon("download")}Download</a><a class="btn" data-tw target="_blank" rel="noopener">${icon("external")}On Twitch</a></div></div><div class="prog"><span></span></div></section></template>`,
    `
var summary=document.getElementById('summary'),id=summary.dataset.id;
function dur(ms){var s=Math.max(0,Math.round(ms/1000));if(s<60)return s+'s';var m=Math.floor(s/60);if(m<60)return m+'m '+String(s%60).padStart(2,'0')+'s';return Math.floor(m/60)+'h '+String(m%60).padStart(2,'0')+'m';}
setInterval(function(){document.querySelectorAll('[data-since]').forEach(function(n){n.textContent=dur(Date.now()-Date.parse(n.dataset.since));});},1000);
document.addEventListener('click',async function(e){var b=e.target.closest('[data-action]');if(!b)return;var a=b.dataset.action;
if(a==='delete'&&!confirm('Delete this job and all its clips?'))return;b.disabled=true;
var r=await fetch('/api/jobs/'+id+(a==='retry'?'/retry':''),{method:a==='retry'?'POST':'DELETE'});
if(!r.ok){var d=await r.json().catch(function(){return{}});alert(d.error||'Request failed');b.disabled=false;return;}
location.href=a==='retry'?location.pathname:'/';});

var player=document.getElementById('player'),feed=player.querySelector('.feed'),ctr=player.querySelector('.ctr'),tpl=document.getElementById('slide-tpl'),wantSound=true,obs=null;
function slides(){return Array.prototype.slice.call(feed.children);}
function playSlide(s){slides().forEach(function(o){if(o!==s){var v=o.querySelector('video');v.pause();}});var v=s.querySelector('video');if(!v.getAttribute('src'))v.src=s.dataset.src;v.muted=!wantSound;s.classList.remove('is-paused');
var p=v.play();if(p)p.catch(function(){v.muted=true;wantSound=false;player.classList.add('muted');v.play().catch(function(){s.classList.add('is-paused');});});
ctr.textContent=(slides().indexOf(s)+1)+' / '+slides().length;}
function openPlayer(start){var cards=document.querySelectorAll('#clips > .clip');feed.replaceChildren();
cards.forEach(function(c){var s=tpl.content.firstElementChild.cloneNode(true);s.dataset.src=c.dataset.src;var v=s.querySelector('video');if(c.dataset.poster)v.poster=c.dataset.poster;
s.querySelector('h3').textContent=c.dataset.title;s.querySelector('.meta').textContent=c.dataset.meta;s.querySelector('[data-dl]').href=c.dataset.download;var tw=s.querySelector('[data-tw]');if(c.dataset.twitch)tw.href=c.dataset.twitch;else tw.remove();
v.addEventListener('timeupdate',function(){if(v.duration)s.querySelector('.prog span').style.width=(100*v.currentTime/v.duration)+'%';});
v.addEventListener('click',function(){if(v.paused){v.play();s.classList.remove('is-paused');}else{v.pause();s.classList.add('is-paused');}});
feed.appendChild(s);});
player.hidden=false;document.body.classList.add('locked');var target=feed.children[start]||feed.firstElementChild;feed.scrollTop=target.offsetTop;
obs=new IntersectionObserver(function(es){es.forEach(function(en){if(en.isIntersecting&&en.intersectionRatio>.6)playSlide(en.target);});},{root:feed,threshold:[.6]});slides().forEach(function(s){obs.observe(s);});
playSlide(target);if(!history.state||!history.state.player)history.pushState({player:1},'');}
function closePlayer(){if(player.hidden)return;if(obs)obs.disconnect();slides().forEach(function(s){var v=s.querySelector('video');v.pause();v.removeAttribute('src');v.load();});feed.replaceChildren();player.hidden=true;document.body.classList.remove('locked');}
document.getElementById('clips').addEventListener('click',function(e){var b=e.target.closest('[data-open]');if(!b)return;var cards=Array.prototype.slice.call(document.querySelectorAll('#clips > .clip'));openPlayer(cards.indexOf(b.closest('.clip')));});
player.querySelector('[data-close]').addEventListener('click',function(){if(history.state&&history.state.player)history.back();else closePlayer();});
player.querySelector('[data-unmute]').addEventListener('click',function(){wantSound=true;player.classList.remove('muted');slides().forEach(function(s){var v=s.querySelector('video');v.muted=false;});});
window.addEventListener('popstate',closePlayer);
document.addEventListener('keydown',function(e){if(player.hidden)return;if(e.key==='Escape')player.querySelector('[data-close]').click();if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();feed.scrollBy({top:(e.key==='ArrowDown'?1:-1)*feed.clientHeight,behavior:'smooth'});}});

function mergeClips(doc){var grid=document.getElementById('clips');var fresh=Array.prototype.slice.call(doc.querySelectorAll('#clips > .clip'));var cur={};grid.querySelectorAll(':scope > .clip').forEach(function(c){cur[c.dataset.key]=c;});
if(fresh.length===grid.children.length&&fresh.every(function(c){return cur[c.dataset.key];}))return;
grid.replaceChildren.apply(grid,fresh.map(function(c){return cur[c.dataset.key]||document.importNode(c,true);}));}
poll(function(){return document.getElementById('summary').hasAttribute('data-active');},function(doc){
var s=doc.getElementById('summary');if(!s)return;var cur=document.getElementById('summary');cur.innerHTML=s.innerHTML;if(s.hasAttribute('data-active'))cur.setAttribute('data-active','');else cur.removeAttribute('data-active');
document.getElementById('clips-head').innerHTML=doc.getElementById('clips-head').innerHTML;document.getElementById('events').innerHTML=doc.getElementById('events').innerHTML;mergeClips(doc);});
`,
    { recent, current: job.id },
  );
}

export function notFoundPage(): string {
  return layout("Not found · Clip Engine", `<div class="login-wrap"><p class="empty" style="background:#fff">Not found. <a href="/" style="text-decoration:underline">Back to the dashboard</a></p></div>`);
}
