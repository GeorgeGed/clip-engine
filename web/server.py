#!/usr/bin/env python3
"""The clip factory, as a website: paste a Twitch VOD, get clips back.

    ./.venv/bin/python web/server.py          # http://127.0.0.1:8808

WHY THIS RUNS LOCALLY AND NOT IN THE CLOUD. The build stage drives DaVinci
Resolve through its scripting API, which is served on Resolve's GUI thread on
this machine. That is not a deployment choice we can revisit by renting a
bigger box: one Resolve, one project, one timeline at a time. Remotion's
`public/` directory is shared the same way. So the site is a local control
surface over the pipeline that already exists, not a service.

WHAT IT DRIVES, which is the real chain and not a reimplementation of it:

    run.py   ingest   <url> --job <name> --rights <basis>
    run.py   analyse  --job <name>
    run.py   rank     --job <name>
    batch.py <job> screen
    batch.py <job> prep
    batch.py <job> specs
    batch.py <job> build
    batch.py <job> report

Every stage is the same command a person would type, run as a subprocess with
its output tee'd to `jobs/<job>/web/<stage>.log`. Nothing about the editing is
duplicated here — if the pipeline changes, the site follows it for free, and
a stage that fails fails visibly instead of being papered over.

ONE JOB AT A TIME, deliberately. A single worker thread consumes the queue.
Resolve wedges on a modal dialog and cannot be driven concurrently; two VODs
transcribing at once would also fight over the GPU. The queue is the honest
model of the constraint rather than a limit imposed by the UI.

THE SCREEN IS THE PRODUCT, NOT A LOADING BAR. Measured across this VOD's 50
candidate clips, **10 are buildable** — the rest are rejected mostly for DMCA
muting at 20-55%. A site that hid that behind a spinner and emitted three
clips would be lying about the yield, so `screen` is shown as a table with a
verdict and a reason per clip, and the operator chooses what to build.

RIGHTS ARE A REQUIRED FIELD. `permission` is on every source in this pipeline
and the build refuses to start without it; the form asks for it rather than
defaulting, because a default here is how an unlicensed clip ships.
"""

from __future__ import annotations

import hmac
import io
import json
import mimetypes
import os
import queue
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.parse
import zipfile
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import runlock
import views

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
JOBS = ROOT / "jobs"
DB = ROOT / "web" / "factory.db"
VENV = ROOT / ".venv" / "bin" / "python"
PORT = int(os.environ.get("CLIP_FACTORY_PORT", "8808"))

# A PUBLIC URL NEEDS A KEY, because binding to 127.0.0.1 stops protecting
# anything the moment a tunnel is pointed at it: the tunnel's traffic arrives
# on the loopback socket exactly as a local browser's does, so the bind
# address cannot tell them apart. And this site is not a viewer — it queues
# jobs that drive Resolve on this Mac, writes editorial specs, and serves
# finished clips of material whose rights basis is George's own permission.
#
# Unset (the default) means local-only use and no gate, so `./start.sh` is
# unchanged. `--public` generates one.
TOKEN = os.environ.get("CLIP_FACTORY_TOKEN", "").strip()

RIGHTS = ("explicit", "affiliate", "client_owned")


# --------------------------------------------------------------- stages ----
@dataclass(frozen=True)
class Stage:
    key: str
    label: str
    blurb: str
    argv: tuple[str, ...]          # {job} and {url} and {rights} are filled in

    def cmd(self, job: str, url: str, rights: str,
            extra: tuple[str, ...] = ()) -> list[str]:
        return ([str(VENV)]
                + [a.format(job=job, url=url, rights=rights) for a in self.argv]
                + list(extra))


# The chain, in order. `build` is last because it is the only stage that
# needs Resolve, so everything that can fail cheaply fails before the
# expensive thing starts.
STAGES: tuple[Stage, ...] = (
    Stage("ingest", "Ingest",
          "Fetch the VOD at 1080p60 and record its rights basis.",
          ("run.py", "ingest", "{url}", "--job", "{job}", "--rights", "{rights}")),
    Stage("analyse", "Analyse",
          "Transcribe the whole VOD once, then run the detectors over it.",
          ("run.py", "analyse", "--job", "{job}")),
    Stage("rank", "Rank",
          "Score the candidate windows and write ranked.json.",
          ("run.py", "rank", "--job", "{job}")),
    Stage("screen", "Screen",
          "Which clips can be cut at all — muting, cadence, seconds left.",
          ("batch.py", "{job}", "screen")),
    Stage("prep", "Prep",
          "Words, chat and facecam for the survivors. Everything before Resolve.",
          ("batch.py", "{job}", "prep")),
    # EDITORIAL BEFORE SPECS, which is why every clip used to start too
    # early. `specs` takes each clip's in-point and hook out of
    # editorial.json, and this stage was never in the chain — so every spec
    # was written with in_point 0.0, i.e. the top of the candidate REGION,
    # which is an acoustic boundary and not where the argument starts.
    # 10 of 25 specs on this VOD still carry that 0.0.
    Stage("editorial", "Read",
          "Decides where each clip starts, what it is called, "
          "and whether it is one argument.",
          ("batch.py", "{job}", "editorial")),
    Stage("specs", "Specs",
          "Topic dedup, then one spec per clip.",
          ("batch.py", "{job}", "specs")),
)

BUILD = Stage("build", "Build",
              "Serial through Resolve, gated on the rendered file.",
              ("batch.py", "{job}", "build"))
REPORT = Stage("report", "Report",
               "The manifest: what shipped and why the rest did not.",
               ("batch.py", "{job}", "report"))

ALL_STAGES = STAGES + (BUILD, REPORT)
STAGE_BY_KEY = {s.key: s for s in ALL_STAGES}


# ----------------------------------------------------------- preflight ----
# RESOLVE IS CHECKED BEFORE THE BUILD, NOT DURING IT.
#
# `build` is the only stage that needs Resolve, and it is last — so a VOD
# dropped on a machine where Resolve is closed would ingest, transcribe,
# detect, screen and spec for the best part of an hour and then fail inside
# `make_clip` with whatever the scripting API raises. The chain is one action
# now, which makes that the normal way to lose an hour rather than an edge
# case.
#
# `doctor()` IMPORTS DaVinciResolveScript and connects, and this file already
# records that Resolve serves its API on the GUI thread — so it is cached.
# Polling it at the UI's 1.5s would be knocking on that thread 40 times a
# minute for a value that changes when someone opens an app.
_DOCTOR: dict = {"at": 0.0, "val": None}
DOCTOR_TTL = 10.0


def resolve_doctor(force: bool = False) -> dict:
    now = time.time()
    if not force and _DOCTOR["val"] is not None and now - _DOCTOR["at"] < DOCTOR_TTL:
        return _DOCTOR["val"]
    try:
        sys.path.insert(0, str(ROOT))
        from engine.resolve_driver import doctor           # noqa: PLC0415
        d = doctor()
        val = {"ok": d.ok(), "running": d.resolve_running,
               "studio": d.studio, "importable": d.module_importable,
               "notes": list(d.notes)[:4]}
    except Exception as exc:                               # noqa: BLE001
        val = {"ok": False, "running": False, "studio": None,
               "importable": False, "notes": [f"{type(exc).__name__}: {exc}"]}
    _DOCTOR.update(at=now, val=val)
    return val


# ------------------------------------------------------------------ db ----
def db() -> sqlite3.Connection:
    c = sqlite3.connect(DB, timeout=30, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init_db() -> None:
    DB.parent.mkdir(parents=True, exist_ok=True)
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS job (
          id        INTEGER PRIMARY KEY AUTOINCREMENT,
          name      TEXT NOT NULL UNIQUE,
          url       TEXT NOT NULL,
          rights    TEXT NOT NULL,
          note      TEXT NOT NULL DEFAULT '',
          state     TEXT NOT NULL DEFAULT 'queued',
          created   REAL NOT NULL,
          updated   REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS stage (
          job_id    INTEGER NOT NULL,
          key       TEXT NOT NULL,
          state     TEXT NOT NULL DEFAULT 'pending',
          started   REAL,
          ended     REAL,
          code      INTEGER,
          PRIMARY KEY (job_id, key)
        );
        """)


def set_job(job_id: int, **kw) -> None:
    kw["updated"] = time.time()
    cols = ", ".join(f"{k}=?" for k in kw)
    with db() as c:
        c.execute(f"UPDATE job SET {cols} WHERE id=?", (*kw.values(), job_id))


def set_stage(job_id: int, key: str, **kw) -> None:
    with db() as c:
        c.execute("INSERT OR IGNORE INTO stage (job_id, key) VALUES (?,?)",
                  (job_id, key))
        if kw:
            cols = ", ".join(f"{k}=?" for k in kw)
            c.execute(f"UPDATE stage SET {cols} WHERE job_id=? AND key=?",
                      (*kw.values(), job_id, key))


# -------------------------------------------------------------- worker ----
WORK: "queue.Queue[tuple[int, list[str]]]" = queue.Queue()
RUNNING: dict[str, object] = {"job_id": None, "stage": None, "proc": None}


def log_path(job_name: str, stage: str, *, create: bool = False) -> Path:
    """`create` ONLY where a stage is about to write.

    It used to mkdir unconditionally, so a GET that merely READ a log created
    directories — and since `stage` arrived raw off the query string, at a
    path of the caller's choosing.
    """
    p = JOBS / job_name / "web" / f"{stage}.log"
    if create:
        p.parent.mkdir(parents=True, exist_ok=True)
    return p


def run_stage(job_id: int, job_name: str, url: str, rights: str,
              stage: Stage, extra: tuple[str, ...] = ()) -> int:
    """One stage as a subprocess, output tee'd to its own log."""
    out = log_path(job_name, stage.key, create=True)
    set_stage(job_id, stage.key, state="running", started=time.time(),
              ended=None, code=None)
    RUNNING["stage"] = stage.key
    cmd = stage.cmd(job_name, url, rights, extra)
    with out.open("w") as fh:
        fh.write(f"$ {' '.join(cmd)}\n\n"); fh.flush()
        proc = subprocess.Popen(cmd, cwd=ROOT, stdout=fh,
                                stderr=subprocess.STDOUT)
        RUNNING["proc"] = proc
        code = proc.wait()
    RUNNING["proc"] = None
    set_stage(job_id, stage.key, state="done" if code == 0 else "failed",
              ended=time.time(), code=code)
    return code


def worker() -> None:
    while True:
        job_id, keys, extra = WORK.get()
        try:
            with db() as c:
                row = c.execute("SELECT * FROM job WHERE id=?",
                                (job_id,)).fetchone()
            if row is None:
                continue
            RUNNING["job_id"] = job_id
            set_job(job_id, state="running")
            failed = None
            for key in keys:
                if RUNNING.get("cancel") == job_id:
                    failed = f"{key} (cancelled)"
                    break
                if key == "build":
                    doc = resolve_doctor(force=True)
                    if not doc["ok"]:
                        why = ("DaVinci Resolve is not reachable — open it, "
                               "and set Preferences > System > General > "
                               "External scripting using to Local. "
                               + "; ".join(doc["notes"]))
                        log_path(row["name"], key,
                                 create=True).write_text(why + "\n")
                        set_stage(job_id, key, state="failed",
                                  ended=time.time(), code=1)
                        failed = f"{key} (Resolve not reachable)"
                        break
                code = run_stage(job_id, row["name"], row["url"],
                                 row["rights"], STAGE_BY_KEY[key], extra)
                if code != 0:
                    failed = key
                    break
            set_job(job_id, state=f"failed:{failed}" if failed else "done")
        except Exception as exc:                       # noqa: BLE001
            set_job(job_id, state=f"error:{exc}")
        finally:
            RUNNING.update({"job_id": None, "stage": None, "proc": None,
                            "cancel": None})
            WORK.task_done()


# ----------------------------------------------------------- job reading ---
def job_dir(name: str) -> Path:
    return JOBS / name


def _reason(v) -> str:
    """`screened.json` stores the reasons as a list; a web page should not
    show `['32% muted']`."""
    if isinstance(v, (list, tuple)):
        return "; ".join(str(x) for x in v)
    return str(v or "")


def read_screen(name: str) -> list[dict]:
    """The screen verdicts, which are the product of the first half."""
    p = job_dir(name) / "screened.json"
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text())
    except json.JSONDecodeError:
        return []
    rows = raw if isinstance(raw, list) else raw.get("clips", raw)
    if isinstance(rows, dict):
        rows = list(rows.values())
    out = []
    for i, r in enumerate(rows, 1):
        if not isinstance(r, dict):
            continue
        out.append({
            "index": r.get("index", r.get("i", i)),
            "verdict": str(r.get("verdict", "")),
            "reason": _reason(r.get("reason", r.get("why", ""))),
            "subject": str(r.get("subject", "")),
            "muted": r.get("muted_share", r.get("absent_share")),
            "seconds": r.get("seconds"),
            "cuts_min": r.get("cuts_min", r.get("cuts_per_min")),
        })
    return out


def read_clips(name: str) -> list[dict]:
    """Delivered clips: whatever renders/ holds for this job, plus its QC."""
    out = []
    man = job_dir(name) / "manifest.json"
    qc = {}
    if man.exists():
        try:
            m = json.loads(man.read_text())
            for row in (m if isinstance(m, list) else m.get("clips", [])):
                if isinstance(row, dict) and "index" in row:
                    qc[int(row["index"])] = row
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    for mp4 in sorted((ROOT / "renders").glob(f"{name}-*.mp4")):
        if mp4.name.endswith("_src.mov"):
            continue
        m = re.search(rf"{re.escape(name)}-(\d+)\.mp4$", mp4.name)
        if not m:
            continue
        idx = int(m.group(1))
        out.append({
            "index": idx,
            "file": mp4.name,
            "size_mb": round(mp4.stat().st_size / 1e6, 1),
            "modified": mp4.stat().st_mtime,
            "qc": qc.get(idx, {}),
        })
    return out


# ----------------------------------------------------------- the review ---
# THE SPEC IS WHERE THE REVIEW LIVES, and until now the site could not see it.
#
# Every note George has sent over six rounds reduced to editing one of these
# five fields and rebuilding that one clip: the in-point, the out-point, which
# booms survive, whether the chat overlay is forced on, and the hook line.
# Nothing else about a clip has ever been the thing he changed. That loop ran
# through chat, by hand, which is the actual bottleneck in "upload a VOD and
# get clips" — not the rendering.
#
# `batch.py specs` already refuses to overwrite a spec a human has edited, so
# these writes are safe against a re-run of the stage that proposed them.
REVIEWABLE = ("in_point", "out_point", "booms", "chat_mode", "hook")
CHAT_MODES = ("continuous", "reactive")


def spec_path(name: str, index: int) -> Path:
    """`clips/<channel>-NN.json`. The channel is the job name's first part."""
    return ROOT / "clips" / f"{name.split('-')[0]}-{index:02d}.json"


def read_specs(name: str) -> list[dict]:
    chan = name.split("-")[0]
    out = []
    for sp in sorted((ROOT / "clips").glob(f"{chan}-*.json")):
        m = re.search(r"-(\d+)\.json$", sp.name)
        if not m:
            continue
        try:
            d = json.loads(sp.read_text())
        except json.JSONDecodeError:
            continue
        c = d.get("clip", {})
        if str(c.get("job", "")) not in ("", name):
            continue                       # another VOD's clip, same channel
        out.append({
            "index": int(m.group(1)),
            "file": sp.name,
            **{k: c.get(k) for k in REVIEWABLE},
            "notes": c.get("notes", ""),
            "cards": len(c.get("cards") or []),
        })
    return out


def _clean(patch: dict) -> tuple[dict, str | None]:
    """Validate before writing. A bad value here costs a Resolve build, so it
    is refused with a reason rather than written and discovered at render."""
    out = {}
    for k, v in patch.items():
        if k not in REVIEWABLE:
            continue
        if v == "" or v is None:
            # in_point has no meaningful empty state; the others clear to None
            if k == "in_point":
                return {}, "in_point cannot be empty"
            out[k] = None
            continue
        if k in ("in_point", "out_point"):
            try:
                f = float(v)
            except (TypeError, ValueError):
                return {}, f"{k} must be a number of seconds"
            if f < 0:
                return {}, f"{k} cannot be negative"
            out[k] = round(f, 3)
        elif k == "booms":
            if isinstance(v, str):
                v = [x for x in re.split(r"[,\s]+", v.strip()) if x]
            try:
                xs = sorted(round(float(x), 2) for x in v)
            except (TypeError, ValueError):
                return {}, "booms must be times in seconds, comma separated"
            if any(x < 0 for x in xs):
                return {}, "a boom cannot sit at a negative time"
            out[k] = xs
        elif k == "chat_mode":
            if v not in CHAT_MODES:
                return {}, f"chat_mode must be one of {', '.join(CHAT_MODES)}"
            out[k] = v
        else:
            out[k] = str(v)
    if "in_point" in out and "out_point" in out and out["out_point"] is not None \
            and out["out_point"] <= out["in_point"]:
        return {}, "out_point must be after in_point"
    return out, None


def write_spec(name: str, index: int, patch: dict,
               note: str = "") -> tuple[dict | None, str | None]:
    """MERGE, never replace. The spec carries reasoning in `notes` that no UI
    collects, and this file's recurring defect is a routine write eating state
    a human put there."""
    sp = spec_path(name, index)
    if not sp.exists():
        return None, f"no spec at clips/{sp.name}"
    clean, err = _clean(patch)
    if err:
        return None, err
    d = json.loads(sp.read_text())
    # THE SAME GUARD `read_specs` ALREADY APPLIES. `spec_path` keys on the
    # CHANNEL (`name.split("-")[0]`), so every job from one streamer maps to
    # the same clips/<chan>-NN.json. Reading knows that and skips another
    # VOD's clip; writing did not — so a second FNS VOD overwrote the first
    # one's reviewed in_point, out_point and chat_mode. This needs no
    # attacker: pasting a second FNS link was enough. Same defect this repo
    # has recorded four times, one layer further out.
    owner = str((d.get("clip") or {}).get("job", ""))
    if owner and owner != name:
        return None, (f"clips/{sp.name} belongs to job {owner}, not {name} — "
                      f"refusing to overwrite another VOD's reviewed spec")
    c = d.setdefault("clip", {})
    changed = {k: (c.get(k), v) for k, v in clean.items() if c.get(k) != v}
    c.update(clean)
    if note.strip():
        c["notes"] = (str(c.get("notes", "")).rstrip() + " " + note.strip()).strip()
    sp.write_text(json.dumps(d, indent=1) + "\n")
    return {"file": sp.name, "changed": {k: {"was": a, "now": b}
                                         for k, (a, b) in changed.items()}}, None


# ------------------------------------------------------------ progress ----
# WHAT IS HAPPENING RIGHT NOW, from the stage's own log.
#
# A 103-minute VOD spends the best part of an hour in `analyse` and then a
# serial pass through Resolve, and until now the rail said "running" for all
# of it. A spinner that cannot distinguish "transcribing" from "wedged" is
# the thing AGENTS.md warns about in the other direction: Resolve CAN wedge,
# at 90-105% CPU, with no output at all. The last line it printed is the
# cheapest honest answer, and for `build` the clip count is countable.
BUILD_MARK = re.compile(r"^=== (\S+) ===", re.M)
BUILD_DONE = re.compile(r"^\[(\S+)\] -> ", re.M)


def progress(name: str, stage: str) -> dict:
    lp = log_path(name, stage)
    if not lp.exists():
        return {}
    try:
        tail = lp.read_text(errors="replace")[-8000:]
    except OSError:
        return {}
    lines = [ln.rstrip() for ln in tail.splitlines() if ln.strip()]
    out = {"line": lines[-1][:160] if lines else ""}
    if stage == "build":
        started = BUILD_MARK.findall(tail)
        out["done"] = len(BUILD_DONE.findall(tail))
        out["total"] = len(read_specs(name))
        if started:
            out["clip"] = started[-1]
    return out


# ------------------------------------------------------------- delivery ---
def clip_path(name: str, index: int) -> Path:
    return ROOT / "renders" / f"{name}-{index:02d}.mp4"


def job_json(row: sqlite3.Row) -> dict:
    with db() as c:
        st = {r["key"]: dict(r) for r in c.execute(
            "SELECT * FROM stage WHERE job_id=?", (row["id"],))}
    return {
        "id": row["id"], "name": row["name"], "url": row["url"],
        "rights": row["rights"], "note": row["note"], "state": row["state"],
        "created": row["created"], "updated": row["updated"],
        "stages": [{
            "key": s.key, "label": s.label, "blurb": s.blurb,
            "state": st.get(s.key, {}).get("state", "pending"),
            "code": st.get(s.key, {}).get("code"),
            "started": st.get(s.key, {}).get("started"),
            "ended": st.get(s.key, {}).get("ended"),
        } for s in ALL_STAGES],
        "screen": read_screen(row["name"]),
        "specs": read_specs(row["name"]),
        "clips": read_clips(row["name"]),
        "active": RUNNING.get("job_id") == row["id"],
        "active_stage": RUNNING.get("stage") if RUNNING.get("job_id") == row["id"] else None,
        "progress": (progress(row["name"], RUNNING["stage"])
                     if RUNNING.get("job_id") == row["id"] and RUNNING.get("stage")
                     else {}),
    }


def download_name(job: str, n: int) -> str:
    """`i-like-people-who-explain-things.mp4`, from the clip's own hook.

    Falls back to the render's filename when a clip has no spec or no hook
    yet — a neutral name beats an empty one.
    """
    chan = job.split("-")[0]
    sp = ROOT / "clips" / f"{chan}-{n:02d}.json"
    hook = ""
    if sp.exists():
        try:
            hook = (json.loads(sp.read_text()).get("clip", {}) or {}).get("hook") or ""
        except (json.JSONDecodeError, AttributeError):
            hook = ""
    hook = re.sub(rf"^{re.escape(chan)}\s*(?::|\bon\b)\s*", "", hook, flags=re.I)
    slug = re.sub(r"[^a-z0-9]+", "-", hook.lower())[:52].strip("-")
    return f"{chan}-{n:02d}-{slug}.mp4" if slug else f"{job}-{n:02d}.mp4"


def is_local_vod(s: str) -> bool:
    """A path on this machine, rather than a URL.

    `engine.ingest.fetch` already ADOPTS an existing path instead of calling
    yt-dlp, so a VOD that is already on disk needs no download — only this
    check stood in the way. A multipart upload is the wrong shape here: the
    source is a 6 GB 1080p60 file, the server is one stdlib thread, and the
    file is already on the same disk the pipeline reads from.
    """
    try:
        return bool(s) and Path(s).expanduser().is_file()
    except OSError:
        return False


def job_name_for(url: str, given: str) -> str:
    """`fns-2905408276` — the channel and the VOD id, which is what the
    pipeline's own directories are already named after."""
    given = re.sub(r"[^a-z0-9-]+", "-", given.strip().lower()).strip("-")
    vid = ""
    m = re.search(r"/videos?/(\d+)", url)
    if m:
        vid = m.group(1)
    elif is_local_vod(url):
        # a local file has no VOD id, so its own name is the next best thing —
        # less the channel prefix, or the job reads `fns-fnsstreamnov5`
        stem = re.sub(r"[^a-z0-9]+", "", Path(url).stem.lower())
        if given and stem.startswith(given.replace("-", "")):
            stem = stem[len(given.replace("-", "")):].lstrip("-_") or stem
        vid = stem[:24]
    if given and vid:
        return f"{given}-{vid}"
    return given or (f"vod-{vid}" if vid else f"job-{int(time.time())}")


KEY_PAGE = b"""<!doctype html><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Clip Factory</title>
<style>
 :root{color-scheme:dark}
 body{margin:0;min-height:100vh;display:grid;place-items:center;
      background:#0b0b0c;color:#f4f4f5;
      font:16px/1.5 ui-sans-serif,system-ui,-apple-system,sans-serif}
 form{width:min(92vw,340px);display:grid;gap:14px}
 h1{margin:0;font-size:19px;letter-spacing:-.01em}
 p{margin:0;color:#a1a1aa;font-size:14px}
 input{padding:11px 13px;background:#18181b;color:inherit;font:inherit;
       border:1px solid #2e2e33;border-radius:0;width:100%;box-sizing:border-box}
 input:focus{outline:none;border-color:#2E5CFF}
 button{padding:11px;background:#2E5CFF;color:#fff;font:inherit;font-weight:600;
        border:0;border-radius:0;cursor:pointer}
</style>
<form method=get action=/>
 <h1>Clip Factory</h1>
 <p>This link needs the key printed in the terminal.</p>
 <input name=k type=password autofocus autocomplete=current-password
        placeholder="key" spellcheck=false>
 <button>Open</button>
</form>
"""


# -------------------------------------------------------------- http ------
class Handler(BaseHTTPRequestHandler):
    server_version = "ClipFactory/1.0"
    # HTTP/1.1, SO A CONNECTION IS REUSED. At 1.0 every request needs its own
    # TCP connection, and a tunnel is where that stops being free: the grid
    # asks for ~16 thumbnails at once, cloudflared dials 16 times, and the
    # ones that do not fit the accept queue are RESET — which the browser
    # shows as a 502 from Cloudflare and the server never sees at all.
    # Safe here because every response path sets Content-Length: `_send`
    # always does, and `_file`'s 206 branch does too.
    protocol_version = "HTTP/1.1"
    # WITHOUT THIS A CONNECTION THAT NEVER FINISHES ITS REQUEST OWNS A THREAD
    # FOREVER. The key is checked in do_GET/do_POST, which the stdlib only
    # reaches after reading the whole request line and headers — so a caller
    # with no key at all can still park threads by sending headers slowly.
    # `timeout` is honoured by StreamRequestHandler and drops them.
    timeout = 20

    def log_message(self, fmt, *args):      # quieter than the default
        pass

    # -- helpers
    def _send(self, code: int, body: bytes, ctype: str,
              extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj).encode(), "application/json")

    # Every JSON endpoint here takes a handful of fields. A megabyte is
    # already absurd; the point is that there WAS no ceiling.
    MAX_BODY = 1 << 20

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        if n > self.MAX_BODY:
            # Do not read it. `rfile.read(n)` trusted a number the caller
            # chose, with no cap and no socket timeout, so one unauthenticated
            # POST could hold a thread and allocate as much as it liked.
            self.close_connection = True
            return {}
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return {}

    def _file(self, path: Path, download: str | None = None) -> None:
        if not path.is_file():
            return self._json({"error": "not found"}, 404)
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        # Range support, so a 45s mp4 scrubs in the browser instead of
        # downloading whole on every seek.
        size = path.stat().st_size
        rng = self.headers.get("Range")
        if rng and rng.startswith("bytes="):
            a, _, b = rng[6:].partition("-")
            start = int(a) if a else 0
            end = int(b) if b else size - 1
            end = min(end, size - 1)
            if start > end:
                return self._json({"error": "bad range"}, 416)
            with path.open("rb") as fh:
                fh.seek(start)
                chunk = fh.read(end - start + 1)
            self.send_response(206)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(chunk)))
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Accept-Ranges", "bytes")
            # THE ONE RESPONSE PATH THAT USED TO OMIT THIS. `_send` sets it on
            # everything else, and a 206 is exactly where it matters: a clip
            # is REBUILT at the same URL, so a cached byte range is the OLD
            # render, and a <video> that stitches fresh ranges onto stale ones
            # plays a clip that never existed. Cloudflare gives a 200/206 with
            # no Cache-Control a 120-minute edge TTL.
            #
            # Today these URLs happen to be extensionless (`/clip/12`, not
            # `/clip/12.mp4`) and Cloudflare's default cache picks by
            # EXTENSION, so nothing is cached in practice. That is luck, not
            # a design — one Cache Rule, or one route gaining a suffix, ends
            # it. Say what we mean instead.
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(chunk)
            return
        head = {"Accept-Ranges": "bytes"}
        if download:
            head["Content-Disposition"] = f'attachment; filename="{download}"'
        self._send(200, path.read_bytes(), ctype, head)

    # -- the key
    def _has_key(self, q: dict) -> bool:
        """`?k=`, the cookie it sets, or `X-Clip-Key` for a script.

        `compare_digest` rather than `==`, so a wrong key cannot be narrowed
        by timing it. No key configured means local-only and no gate.
        """
        if not TOKEN:
            return True
        given = (q.get("k") or [""])[0]
        if not given:
            given = self.headers.get("X-Clip-Key") or ""
        if not given:
            for part in (self.headers.get("Cookie") or "").split(";"):
                name, _, val = part.strip().partition("=")
                if name == "cf_key":
                    given = urllib.parse.unquote(val)
                    break
        # COMPARE BYTES. `hmac.compare_digest` raises TypeError on str with
        # any non-ASCII character, and `given` is attacker-controlled — so a
        # key of "é" took the handler down before it could answer at all.
        if not given:
            return False
        return hmac.compare_digest(given.encode("utf-8", "surrogateescape"),
                                   TOKEN.encode("utf-8"))

    def _gate(self, p: str, q: dict) -> bool:
        """True when the request may proceed; otherwise it has been answered.

        A good `?k=` is turned into a cookie and the key is dropped from the
        URL, so it stops riding in every later request and in the address
        bar. A page request with no key gets the form rather than a bare 403
        — the tunnel URL changes every run and the cookie does not follow it,
        so landing on a 403 with no way in is the common case, not the odd
        one. An API request gets 401, which the page reloads on.
        """
        if self._has_key(q):
            # ONLY UPGRADE A NAVIGATION. The branch exists to move the key
            # out of the address bar, which is a GET concern — firing it on a
            # POST turned every state-changing request carrying ?k= into a
            # 303 that did nothing, so one of the three documented ways in
            # never worked for build, spec or job creation.
            if (TOKEN and (q.get("k") or [""])[0]
                    and self.command in ("GET", "HEAD")):
                rest = {k: v for k, v in q.items() if k != "k"}
                dest = p + (("?" + urllib.parse.urlencode(rest, doseq=True))
                            if rest else "")
                # Not `Secure`: the same binary serves http on loopback and
                # https through the tunnel, and `Secure` would drop the
                # cookie on the local one.
                self._send(303, b"", "text/plain", extra={
                    "Location": dest,
                    "Set-Cookie": "cf_key=" + urllib.parse.quote(TOKEN)
                                  + "; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000"})
                return False
            return True
        if p.startswith("/api/"):
            self._json({"error": "key required"}, 401)
        else:
            self._send(401, KEY_PAGE, "text/html; charset=utf-8")
        return False

    # -- routes
    def _job(self, job_id: int):
        with db() as c:
            return c.execute("SELECT * FROM job WHERE id=?", (job_id,)).fetchone()

    def do_GET(self):                                   # noqa: N802
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        p = u.path

        if not self._gate(p, q):
            return None

        if p in ("/", "/index.html"):
            return self._file(WEB / "static" / "index.html")
        if re.fullmatch(r"/[A-Za-z0-9._-]+\.(js|css|svg|png|ico|woff2?)", p):
            return self._file(WEB / "static" / p.lstrip("/"))

        if p == "/api/doctor":
            return self._json(resolve_doctor())

        if p == "/api/lookup":
            # A PASTED VOD KNOWS ITS OWN CHANNEL, so do not ask for it.
            # Helix `Get Videos` returns user_login, title and duration; the
            # credentials are the ones `engine.detect_crowd` already reads.
            src = (q.get("url") or [""])[0]
            # A LOCAL FILE ANSWERS THE SAME QUESTION. The pipeline has
            # accepted a path on this machine since `ingest.fetch` was found
            # to adopt one rather than calling yt-dlp — but the UI could not
            # reach it: the field was `type="url"` so a browser refused a
            # path before submitting, and the Start button was gated on a
            # Twitch lookup that a path can never produce. The capability
            # existed and was unusable, which is worse than absent.
            #
            # A multipart upload stays out: the source is a 6 GB 1080p60
            # file, this is one stdlib thread, and the file is already on the
            # disk the pipeline reads from. What a browser cannot give is a
            # path, so the path is typed or pasted — and this confirms the
            # file is really there before an hour of work starts.
            if is_local_vod(src):
                f = Path(src).expanduser()
                dur = ""
                try:
                    r = subprocess.run(
                        ["ffprobe", "-v", "error", "-show_entries",
                         "format=duration", "-of", "csv=p=0", str(f)],
                        capture_output=True, text=True, timeout=30)
                    secs = float((r.stdout or "0").strip() or 0)
                    if secs:
                        dur = (f"{int(secs // 3600)}h{int(secs % 3600 // 60):02d}m"
                               f"{int(secs % 60):02d}s")
                except (OSError, ValueError, subprocess.SubprocessError):
                    pass
                gb = f.stat().st_size / 1e9
                return self._json({
                    "channel": "",          # a file has none; the stem names the job
                    "title": f.name,
                    "duration": dur or f"{gb:.1f} GB",
                    "created": "", "local": True})
            m = re.search(r"/videos?/(\d+)", src)
            if not m:
                return self._json(
                    {"error": "not a Twitch VOD URL, and no file at that path"},
                    400)
            try:
                sys.path.insert(0, str(ROOT))
                from engine.detect_crowd import Helix      # noqa: PLC0415
                d = (Helix().get("videos", id=m.group(1))
                     .get("data") or [{}])[0]
            except Exception as exc:                       # noqa: BLE001
                return self._json({"error": f"{type(exc).__name__}: {exc}"}, 502)
            if not d:
                return self._json({"error": "no such VOD"}, 404)
            return self._json({"channel": d.get("user_login", ""),
                               "title": d.get("title", ""),
                               "duration": d.get("duration", ""),
                               "created": d.get("created_at", "")})

        if p == "/api/jobs":
            with db() as c:
                rows = c.execute(
                    "SELECT * FROM job ORDER BY created DESC").fetchall()
            return self._json([job_json(r) for r in rows])

        m = re.fullmatch(r"/api/jobs/(\d+)", p)
        if m:
            with db() as c:
                row = c.execute("SELECT * FROM job WHERE id=?",
                                (int(m.group(1)),)).fetchone()
            return self._json(job_json(row) if row else {"error": "no such job"},
                              200 if row else 404)

        m = re.fullmatch(r"/api/jobs/(\d+)/log", p)
        if m:
            stage = (q.get("stage") or ["ingest"])[0]
            # `stage` REACHES A FILESYSTEM PATH, so it is not free text. Left
            # unchecked, ?stage=../../../../var/log/install read any *.log on
            # the Mac — including jobs/_service/site.out.log, which had the
            # site's own key printed in it. `do_POST` already validates the
            # same value against this table; the GET simply never did.
            if stage not in STAGE_BY_KEY:
                return self._json({"error": f"no such stage {stage!r}"}, 400)
            with db() as c:
                row = c.execute("SELECT * FROM job WHERE id=?",
                                (int(m.group(1)),)).fetchone()
            if not row:
                return self._json({"error": "no such job"}, 404)
            lp = log_path(row["name"], stage)
            text = lp.read_text()[-20000:] if lp.exists() else ""
            return self._json({"stage": stage, "text": text})

        m = re.fullmatch(r"/api/jobs/(\d+)/candidates", p)
        if m:
            row = self._job(int(m.group(1)))
            if not row:
                return self._json({"error": "no such job"}, 404)
            cands = views.candidates(row["name"])
            views.warm(row["name"], [c["n"] for c in cands])
            return self._json(cands)

        m = re.fullmatch(r"/api/jobs/(\d+)/detail/(\d+)", p)
        if m:
            row = self._job(int(m.group(1)))
            if not row:
                return self._json({"error": "no such job"}, 404)
            return self._json(views.clip_detail(row["name"], int(m.group(2))))

        m = re.fullmatch(r"/api/jobs/(\d+)/thumb/(\d+)", p)
        if m:
            row = self._job(int(m.group(1)))
            f = views.candidate_thumb(row["name"], int(m.group(2))) if row else None
            if not f:
                return self._json({"error": "no frame"}, 404)
            return self._file(f)

        m = re.fullmatch(r"/api/jobs/(\d+)/frame/(\d+)", p)
        if m:
            row = self._job(int(m.group(1)))
            at = float((q.get("t") or ["1"])[0] or 1)
            w = int((q.get("w") or ["250"])[0] or 250)
            f = views.clip_frame(row["name"], int(m.group(2)), at, w) if row else None
            if not f:
                return self._json({"error": "no frame"}, 404)
            return self._file(f)

        m = re.fullmatch(r"/api/jobs/(\d+)/clip/(\d+)", p)
        if m:
            with db() as c:
                row = c.execute("SELECT * FROM job WHERE id=?",
                                (int(m.group(1)),)).fetchone()
            if not row:
                return self._json({"error": "no such job"}, 404)
            fp = clip_path(row["name"], int(m.group(2)))
            if q.get("download"):
                # NAME THE DOWNLOAD BY ITS TITLE. `fns-2905408276-04.mp4`
                # tells whoever opens it nothing; `deliver/` has named its
                # copies by the hook since the titles landed, and a file
                # pulled from the UI should match.
                return self._file(fp, download=download_name(
                    row["name"], int(m.group(2))))
            return self._file(fp)

        m = re.fullmatch(r"/api/jobs/(\d+)/clips\.zip", p)
        if m:
            with db() as c:
                row = c.execute("SELECT * FROM job WHERE id=?",
                                (int(m.group(1)),)).fetchone()
            if not row:
                return self._json({"error": "no such job"}, 404)
            files = [clip_path(row["name"], c["index"])
                     for c in read_clips(row["name"])]
            files = [f for f in files if f.exists()]
            if not files:
                return self._json({"error": "no clips built yet"}, 404)
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
                # STORED, not DEFLATED: these are already H.264, so deflate
                # buys nothing and costs the whole file through a CPU.
                for f in files:
                    z.write(f, f.name)
            return self._send(200, buf.getvalue(), "application/zip",
                              extra={"Content-Disposition":
                                     f'attachment; filename="{row["name"]}-clips.zip"'})

        return self._json({"error": "not found"}, 404)

    def do_HEAD(self):                                  # noqa: N802
        self.do_GET()

    def do_POST(self):                                  # noqa: N802
        u = urllib.parse.urlparse(self.path)
        p = u.path
        if not self._gate(p, urllib.parse.parse_qs(u.query)):
            # DO NOT DRAIN IT — CLOSE. Draining was there so a keep-alive
            # connection did not start mid-JSON, but it meant an
            # unauthenticated POST could make the server read a body of any
            # size it declared. Closing solves the framing problem without
            # reading a byte.
            self.close_connection = True
            return None
        body = self._body()

        if p == "/api/jobs":
            url = str(body.get("url", "")).strip()
            rights = str(body.get("rights", "")).strip()
            channel = str(body.get("channel", "")).strip()
            note = str(body.get("note", "")).strip()
            # A TWITCH VOD OR A LOCAL FILE — NOT ANY URL. The only check was
            # a startswith on http(s), and this value goes straight to
            # yt-dlp as an argument, so the box could be pointed at anything
            # it could reach and the result read back through the stage log.
            # The pipeline only supports these two anyway.
            ok_url = (re.match(r"https?://(www\.)?twitch\.tv/videos?/\d+", url)
                      or re.match(r"https?://(www\.)?twitch\.tv/[\w-]+/v(ideo)?/\d+", url))
            if not ok_url and not is_local_vod(url):
                return self._json(
                    {"error": "give a Twitch VOD URL (twitch.tv/videos/…), or "
                              "the path to a VOD already on this machine"}, 400)
            if rights not in RIGHTS:
                return self._json(
                    {"error": f"rights must be one of {', '.join(RIGHTS)} — "
                              f"the build refuses to start without one"}, 400)
            name = job_name_for(url, channel)
            now = time.time()
            try:
                with db() as c:
                    cur = c.execute(
                        "INSERT INTO job (name,url,rights,note,state,created,"
                        "updated) VALUES (?,?,?,?,?,?,?)",
                        (name, url, rights, note, "queued", now, now))
                    job_id = cur.lastrowid
            except sqlite3.IntegrityError:
                return self._json(
                    {"error": f"job {name!r} already exists — open it instead"},
                    409)
            for s in ALL_STAGES:
                set_stage(job_id, s.key)
            # THE WHOLE CHAIN. The promise is 'drop a VOD, get\n            # clips'; stopping at `specs` delivered specs.\n            WORK.put((job_id, [s.key for s in ALL_STAGES], ()))
            return self._json({"id": job_id, "name": name}, 201)

        m = re.fullmatch(r"/api/jobs/(\d+)/run", p)
        if m:
            job_id = int(m.group(1))
            keys = [k for k in body.get("stages", []) if k in STAGE_BY_KEY]
            if not keys:
                return self._json({"error": "no known stages given"}, 400)
            for k in keys:
                set_stage(job_id, k, state="pending", code=None,
                          started=None, ended=None)
            set_job(job_id, state="queued")
            WORK.put((job_id, keys, ()))
            return self._json({"queued": keys})

        m = re.fullmatch(r"/api/jobs/(\d+)/spec/(\d+)", p)
        if m:
            with db() as c:
                row = c.execute("SELECT * FROM job WHERE id=?",
                                (int(m.group(1)),)).fetchone()
            if not row:
                return self._json({"error": "no such job"}, 404)
            res, err = write_spec(row["name"], int(m.group(2)),
                                  body.get("spec", {}) or {},
                                  str(body.get("note", "")))
            if not err:
                views.invalidate(row["name"], int(m.group(2)))
            return self._json({"error": err} if err else res, 400 if err else 200)

        m = re.fullmatch(r"/api/jobs/(\d+)/build/(\d+)", p)
        if m:
            job_id, n = int(m.group(1)), int(m.group(2))
            with db() as c:
                row = c.execute("SELECT * FROM job WHERE id=?",
                                (job_id,)).fetchone()
            if not row:
                return self._json({"error": "no such job"}, 404)
            # DECIDE, THEN SPEC, THEN BUILD — every time, not only when the
            # spec is missing.
            #
            # `editorial` is what says where a clip starts and what it is
            # called; `specs` only copies that across. The chain runs them in
            # that order, but this button is the main path in the product and
            # it ran NEITHER when a spec already existed — so a spec written
            # before the judging pass, carrying `in_point 0.0` (the top of
            # the candidate region, an acoustic boundary and not where the
            # argument starts), was handed straight to the build. That is
            # George's "the clip starts too early", reachable from the UI
            # after being fixed in the chain.
            #
            # Both are safe to re-run and that is the whole reason this can
            # be unconditional: `editorial` skips a clip it has already
            # judged, and `specs` FILLS a missing in-point or hook and never
            # changes one that is set. `--only` also bypasses the topic dedup
            # and the editorial veto, which is right here — somebody has
            # pointed at this clip and asked for it, not for a balanced
            # batch. Seconds of JSON plus at most one model call, so it runs
            # inline rather than taking a turn through the queue.
            for argv, why in (
                    (("editorial", "--only", str(n)), "judge"),
                    (("specs", "--only", str(n)), "spec")):
                r = subprocess.run(
                    [str(VENV), "batch.py", row["name"], *argv],
                    cwd=ROOT, capture_output=True, text=True, timeout=180)
                if r.returncode != 0:
                    tail = (r.stdout or r.stderr or "").strip().splitlines()
                    return self._json(
                        {"error": f"could not {why} that clip: "
                                  + (tail[-1] if tail else f"{argv[0]} failed")},
                        409)
            if not spec_path(row["name"], n).exists():
                return self._json(
                    {"error": "could not prepare that clip: no spec written"},
                    409)
            if RUNNING.get("job_id") is not None:
                return self._json(
                    {"error": "a job is already running — one at a time, "
                              "because Resolve is a single GUI app"}, 409)
            # --force, because a rebuild after a note is exactly the case the
            # "already built and passed, skipping" guard would swallow.
            set_stage(job_id, "build", state="pending", code=None,
                      started=None, ended=None)
            set_job(job_id, state="queued")
            WORK.put((job_id, ["build"], ("--only", str(n), "--force")))
            return self._json({"queued": "build", "clip": n})

        m = re.fullmatch(r"/api/jobs/(\d+)/cancel", p)
        if m:
            job_id = int(m.group(1))
            RUNNING["cancel"] = job_id
            proc = RUNNING.get("proc")
            if RUNNING.get("job_id") == job_id and proc is not None:
                try:
                    proc.terminate()                    # type: ignore[union-attr]
                except OSError:
                    pass
            return self._json({"cancelling": job_id})

        return self._json({"error": "not found"}, 404)


def main() -> None:
    init_db()
    if not VENV.exists():
        raise SystemExit(f"no interpreter at {VENV}")
    # ONE RUNNER PER MACHINE. If `worker/agent.py` already holds it, this
    # process still serves the UI — looking at a job is always safe — but it
    # does not start its own worker thread, because two runners on one
    # Resolve is the one thing the whole pipeline cannot survive.
    runner = None
    try:
        runner = runlock.take("web/server.py")
        threading.Thread(target=worker, daemon=True).start()
    except runlock.Held as other:
        print(f"  NOT running jobs — {other} holds the runner lock")
    # THE ACCEPT QUEUE IS 5 BY DEFAULT, inherited from socketserver, and that
    # is the number the first public run died on: cloudflared's own log said
    # `dial tcp 127.0.0.1:8808: connect: connection reset by peer`, which is
    # the kernel refusing a connection the backlog had no room for — not a
    # timeout, not a slow handler. Over loopback it never shows, because the
    # queue drains as fast as it fills.
    ThreadingHTTPServer.request_queue_size = 128
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"clip factory on http://127.0.0.1:{PORT}  (root {ROOT})")
    if TOKEN:
        # THE KEY IS NOT PRINTED. Under launchd stdout is a file inside the
        # tree this app serves from, so printing it put the master
        # credential into jobs/_service/site.out.log — readable through the
        # very API it protects, and accumulating every token ever used, so
        # rotating the key did not revoke anything.
        print("  a key is set; it is in web/.site-key")
    print(f"  {len(ALL_STAGES)} stages: "
          f"{' -> '.join(s.key for s in ALL_STAGES)}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if runner is not None:
            runner.close()


if __name__ == "__main__":
    main()
