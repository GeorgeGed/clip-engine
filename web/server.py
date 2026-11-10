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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import caption_colour                                # noqa: E402
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

# ONE CLIP AT A TIME WAS A CODE DEFECT, NOT A POLICY.
#
# George: *"why doesnt it let me clip multiple clips at once? needs to allow
# this possibility"*. The 409 said it was "because Remotion's public/
# directory is shared between clips", which was true and was fixable: the
# per-clip data now goes out as `--props` instead of being `import`ed from
# that shared tree, and the PNG sequence directory is a temp dir per call
# rather than one named after the composition. Both of those collided
# SILENTLY — a clean render of the wrong clip's material.
#
# What is left is memory, which `batch.lanes_for()` measures (~1.9 GB a
# lane against free+inactive pages). So this is a QUEUE with lanes, not a
# refusal: clicking six clips enqueues six and they come out in order, which
# is the half of the ask that matters most for bulk.
CLIPQ: "queue.Queue[tuple[int, int]]" = queue.Queue()
# keyed by (job_id, clip index) -> {"proc", "started"}
BUILDING: dict[tuple[int, int], dict] = {}
QUEUED: set[tuple[int, int]] = set()
_BLOCK = threading.Lock()


def clip_lanes() -> int:
    """How many clip builds may run at once. Measured, not assumed."""
    try:
        sys.path.insert(0, str(ROOT))
        import batch                                          # noqa: PLC0415
        return batch.lanes_for()
    except Exception:                                          # noqa: BLE001
        return 1


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


def clip_log_path(job_name: str, index: int) -> Path:
    """ONE LOG PER CLIP, because lanes interleave.

    `batch.clip_log` writes the same path; this reads it. Two make_clip
    processes writing line-interleaved into one file is unreadable, and the
    page needs to say which clip is on which frame.
    """
    return JOBS / job_name / "web" / f"build-{index:02d}.log"


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


def clip_worker() -> None:
    """Build ONE clip, as its own subprocess, in its own lane.

    Deliberately NOT the chain's worker: the chain's stages must run in
    order and a job's `ingest` cannot overlap its `analyse`, while two
    different clips of the same job are independent by construction — that
    is the whole premise of `batch.py`. Keeping them separate also means a
    clip build cannot be starved behind an hour of transcription.
    """
    while True:
        job_id, n = CLIPQ.get()
        key = (job_id, n)
        try:
            with db() as c:
                row = c.execute("SELECT * FROM job WHERE id=?",
                                (job_id,)).fetchone()
            if row is None:
                continue
            with _BLOCK:
                QUEUED.discard(key)
                BUILDING[key] = {"proc": None, "started": time.time()}
            set_job(job_id, state="running")
            out = log_path(row["name"], "build", create=True)
            cmd = [str(VENV), "batch.py", row["name"], "build",
                   "--only", str(n), "--force"]
            # Append, not truncate: with lanes, several clips write their
            # headlines into this one file and the last to start must not
            # erase the others'. Each clip's detail is in its own log.
            with out.open("a") as fh:
                fh.write(f"\n$ {' '.join(cmd)}\n")
                fh.flush()
                proc = subprocess.Popen(cmd, cwd=ROOT, stdout=fh,
                                        stderr=subprocess.STDOUT)
                with _BLOCK:
                    BUILDING[key]["proc"] = proc
                code = proc.wait()
            with _BLOCK:
                BUILDING.pop(key, None)
                busy = any(k[0] == job_id for k in BUILDING) \
                    or any(k[0] == job_id for k in QUEUED) \
                    or RUNNING.get("job_id") == job_id
            if not busy:
                set_job(job_id, state="done" if code == 0
                        else f"failed:build {n:02d}")
            set_stage(job_id, "build",
                      state="done" if code == 0 else "failed",
                      ended=time.time(), code=code)
        except Exception as exc:                               # noqa: BLE001
            with _BLOCK:
                BUILDING.pop(key, None)
            set_job(job_id, state=f"error:{exc}")
        finally:
            CLIPQ.task_done()


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
                # THE RESOLVE GATE IS GONE. `build` used to be blocked here
                # unless DaVinci Resolve was open and answering, because the
                # build drove its scripting API — and since build is LAST,
                # a job dropped with Resolve closed would transcribe and
                # screen for the best part of an hour before dying. The
                # native renderer composites with ffmpeg and is the default,
                # so there is nothing left to be open. `/api/doctor` still
                # reports Resolve's state, because the GUI path is still
                # there for format work and it is worth seeing.
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


# A render's duration, memoised on its own mtime and size. The grid polls
# every two seconds and ffprobe is a process, so this cannot run per request
# — and a rebuild changes both, so the memo cannot go stale.
_DUR: dict[tuple, float] = {}


def clip_seconds(mp4: Path) -> float:
    st = mp4.stat()
    key = (str(mp4), st.st_mtime_ns, st.st_size)
    if key not in _DUR:
        _DUR[key] = views._duration(mp4)
    return _DUR[key]


def read_clips(name: str) -> list[dict]:
    """Delivered clips: whatever renders/ holds for this job, plus its QC."""
    out = []
    man = job_dir(name) / "manifest.json"
    qc = {}
    if man.exists():
        try:
            m = json.loads(man.read_text())
            # THE MANIFEST IS A DICT KEYED BY SPEC STEM — `{"fns-12": {...}}`
            # — and the index is in the KEY, not the row. This looked for a
            # list of rows carrying `"index"`, a shape `batch.py` has never
            # written, so `qc` came back empty for every clip and the grid
            # offered each render for download with no verdict attached.
            rows = (m.items() if isinstance(m, dict)
                    else [(str(r.get("index", "")), r) for r in m])
            for key, row in rows:
                k = re.search(r"(\d+)$", str(key))
                if k and isinstance(row, dict):
                    qc[int(k.group(1))] = row
        except (json.JSONDecodeError, ValueError, TypeError, AttributeError):
            pass
    for mp4 in sorted((ROOT / "renders").glob(f"{name}-*.mp4")):
        if mp4.name.endswith("_src.mov"):
            continue
        m = re.search(rf"{re.escape(name)}-(\d+)\.mp4$", mp4.name)
        if not m:
            continue
        idx = int(m.group(1))
        row = qc.get(idx, {})
        out.append({
            "index": idx,
            "file": mp4.name,
            "size_mb": round(mp4.stat().st_size / 1e6, 1),
            "modified": mp4.stat().st_mtime,
            # THE CLIP'S OWN LENGTH, measured on the file. There was no such
            # field, so the grid fell through to the CANDIDATE REGION's
            # length and every badge was wrong — a 1:04 label over a 0:45
            # video, up to 54s out. Do NOT reach for the manifest's
            # `seconds`: that is how long the BUILD took (323 for a 45s
            # clip), which is the same trap one field over.
            "seconds": round(clip_seconds(mp4), 1),
            "qc_ok": row.get("qc_ok"),
            "qc": row,
        })
    return out


# ----------------------------------------------------------- the review ---
# THE SPEC IS WHERE THE REVIEW LIVES, and until now the site could not see it.
#
# Every note George has sent over six rounds reduced to editing one of these
# a handful of spec fields and rebuilding that one clip: the in-point, the out-point, which
# booms survive, whether the chat overlay is forced on, and the hook line.
# Nothing else about a clip has ever been the thing he changed. That loop ran
# through chat, by hand, which is the actual bottleneck in "upload a VOD and
# get clips" — not the rendering.
#
# `batch.py specs` already refuses to overwrite a spec a human has edited, so
# these writes are safe against a re-run of the stage that proposed them.
REVIEWABLE = ("in_point", "out_point", "booms", "chat_mode", "hook",
              "caption_fill", "caption_emph", "stories")
# "off" IS THE DOCUMENTED OPT-OUT and was not accepted here, so the site
# could not express the one setting `make_clip` tells the operator to use —
# its own log says *set chat_mode "off" on this clip's spec if the room is
# talking about something else*, and saving that from the page was refused.
CHAT_MODES = ("continuous", "reactive", "off")
STORY_MODES = ("auto", "off")


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
            # `float()` ACCEPTS "nan" AND "inf". Either one round-trips
            # through `round()` and `json.dumps` writes a bare NaN/Infinity
            # token, which is not JSON — so a reviewed spec would be saved
            # in a state that `json.loads` refuses and every later read of
            # that clip fails. `f < 0` does not catch nan, because every
            # comparison with nan is False.
            if f != f or f in (float("inf"), float("-inf")):
                return {}, f"{k} must be a real number of seconds"
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
            if any(x != x or x in (float("inf"), float("-inf")) for x in xs):
                return {}, "a boom must be a real time in seconds"
            if any(x < 0 for x in xs):
                return {}, "a boom cannot sit at a negative time"
            out[k] = xs
        elif k == "chat_mode":
            if v not in CHAT_MODES:
                return {}, f"chat_mode must be one of {', '.join(CHAT_MODES)}"
            out[k] = v
        elif k == "stories":
            if v not in STORY_MODES:
                return {}, f"stories must be one of {', '.join(STORY_MODES)}"
            out[k] = v
        elif k in ("caption_fill", "caption_emph"):
            # THE PALETTE REFUSES, NOT THIS. `caption_colour.rgba` measures
            # the colour against the caption's own hard black stroke at a
            # 4.5:1 floor — so "use our brand blue" (#2E5CFF, 4.09:1) comes
            # back refused BY NAME with the lifted alternative, which is
            # better than a validator here that would have to repeat the
            # measurement and could come to disagree with it.
            try:
                caption_colour.rgba(v)
            except ValueError as exc:
                return {}, str(exc)
            out[k] = str(v).strip().lower()
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
        # WHICH CLIP, FROM THE WHOLE LOG — NOT THE TAIL. The marker is one
        # line per clip (`=== fns-11 ===`) and Remotion writes one line per
        # FRAME, so a 1180-frame overlay buries it: measured, the marker sat
        # 23k characters back in a 8k window. `progress.clip` then vanished,
        # so the page knew a build was running and not which card it was,
        # and the card it belonged to showed nothing. The tail is still what
        # reports the current LINE; only the marker needs the whole file.
        try:
            whole = lp.read_text(errors="replace")
        except OSError:
            whole = tail
        started = BUILD_MARK.findall(whole)
        out["done"] = len(BUILD_DONE.findall(whole))
        out["total"] = len(read_specs(name))
        if started:
            out["clip"] = started[-1]
        # AND ONE ENTRY PER LANE. With clips building at once there is no
        # single "which clip is it on" — each lane writes its own log and
        # the page matches by index, so a card shows its OWN frame count
        # instead of whichever lane happened to write last.
        out["clips"] = clips_in_flight(name)
    return out


def clips_in_flight(name: str) -> list[dict]:
    """What each lane is doing, read from the lane's own log."""
    rows = []
    with _BLOCK:
        live = sorted(n for (jid, n) in BUILDING
                      if JOBS_BY_ID.get(jid) == name)
        waiting = sorted(n for (jid, n) in QUEUED
                         if JOBS_BY_ID.get(jid) == name)
    for n in live:
        lp = clip_log_path(name, n)
        line = ""
        if lp.exists():
            try:
                tail = lp.read_text(errors="replace")[-4000:]
                ls = [x.rstrip() for x in tail.splitlines() if x.strip()]
                line = ls[-1][:160] if ls else ""
            except OSError:
                pass
        rows.append({"n": n, "state": "building", "line": line})
    rows += [{"n": n, "state": "queued", "line": ""} for n in waiting]
    return rows


# job_id -> name, so `clips_in_flight` need not hit the database on a 2s poll
JOBS_BY_ID: dict[int, str] = {}


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
        **_activity(row),
    }


def _activity(row: sqlite3.Row) -> dict:
    """Is anything happening on this job, and what.

    TWO RUNNERS NOW, and this only knew about one. The chain holds
    `RUNNING`; a per-clip build holds a LANE, and `RUNNING["job_id"]` stays
    None for it — so after the lanes landed, a clip could be building with
    the page reporting the job idle and the card showing nothing. That is
    the exact symptom George already reported once ("the clips are basically
    just not cutting"), and it would have been reintroduced by the fix for
    it.
    """
    jid, name = row["id"], row["name"]
    JOBS_BY_ID[jid] = name
    chain = RUNNING.get("job_id") == jid
    with _BLOCK:
        lanes = [n for (j, n) in BUILDING if j == jid]
        waiting = [n for (j, n) in QUEUED if j == jid]
    if chain:
        return {"active": True, "active_stage": RUNNING.get("stage"),
                "progress": (progress(name, RUNNING["stage"])
                             if RUNNING.get("stage") else {})}
    if lanes or waiting:
        # `active_stage` is what the page keys its build UI off, so a lane
        # has to report "build" even though no chain stage is running.
        return {"active": True, "active_stage": "build",
                "progress": progress(name, "build")}
    return {"active": False, "active_stage": None, "progress": {}}


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
    # IT MUST BE A VIDEO, NOT MERELY A FILE. This was `is_file()`, which
    # accepts /etc/passwd, ~/.ssh/id_rsa or any other readable path on the
    # machine — and the site SERVES its own stage logs, so a path that fails
    # downstream can surface the file's contents in the error it prints. An
    # audit queued `vod-passwd -> /etc/passwd` and the form took it.
    #
    # The suffix is not the test either, because a file named .mp4 need not
    # be one. ffprobe reading a video stream out of it IS the definition of
    # the thing being accepted, so that is the test; it parses a header and
    # costs milliseconds, and the `/api/lookup` route already ffprobes the
    # same path for its duration.
    try:
        f = Path(s).expanduser()
        if not s or not f.is_file():
            return False
    except OSError:
        return False
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(f)],
            capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0 and r.stdout.strip() == "video"


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

    # BUT THE SAME TIMEOUT IS ON THE SOCKET WHILE THE RESPONSE IS WRITTEN,
    # AND THAT SILENTLY TRUNCATED EVERY SLOW DOWNLOAD. A clip is 24-30 MB and
    # the whole body goes out in one `wfile.write`, which blocks until the
    # kernel has taken it all; past 20 seconds the socket raises and the
    # client has a 200, a correct Content-Length and a short file. Measured
    # on clip 12 at `--limit-rate 300k`: 7,825,704 bytes of 26,584,815 — 29%
    # — after 25.2s, curl exit 18. Anything under roughly 1 MB/s loses its
    # download, which through a tunnel is most of them, and the 139 MiB zip
    # would need 7 MB/s sustained.
    #
    # The timeout belongs on READING a request, where a dribbling client is
    # the hazard, not on writing a body the client asked for. So the body
    # write gets a budget scaled to its own size, with a floor: a reader
    # slower than this is not a reader.
    MIN_SEND_RATE = 20_000          # bytes/s — 26 MB gets 22 minutes

    def _write_body(self, body: bytes) -> None:
        """Write a response body with a timeout proportional to its size."""
        try:
            self.connection.settimeout(
                max(self.timeout, len(body) / self.MIN_SEND_RATE))
        except OSError:
            pass
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # A <video> SEEKING IS NOT AN ERROR. The player asks for a range,
            # gets what it needs and closes the socket, and the stdlib then
            # logs a full traceback per abandoned request. The service log
            # filled with them — and a real failure hid in that noise for a
            # whole diagnosis, which is the actual cost of logging something
            # normal as an exception.
            self.close_connection = True
        finally:
            try:
                self.connection.settimeout(self.timeout)
            except OSError:
                pass

    def log_message(self, fmt, *args):      # quieter than the default
        pass

    # -- helpers
    def _send(self, code: int, body: bytes, ctype: str,
              extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # The page is served from the same origin as the clips and the JSON,
        # and `_file` guesses a content type from a filename. Costs nothing
        # and closes the sniffing class outright.
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self._write_body(body)

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
            if self.command != "HEAD":
                # A HEAD with a Range used to send the body anyway, which
                # desynchronises a keep-alive connection: the next response
                # on that socket is read as the tail of this one.
                self._write_body(chunk)
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

        if p == "/api/options":
            # WHAT THE PAGE MAY OFFER, from the code that enforces it. A
            # colour list typed into the JavaScript is two places deciding
            # the same thing — this repo's most-repeated defect — and it
            # would go stale the moment a colour was added or refused.
            # Every ratio here is measured, so the page can show it.
            return self._json({
                "caption_colours": [
                    {"name": n, "hex": h,
                     "ratio": round(caption_colour.ratio(
                         [int(h.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]), 2)}
                    for n, h in sorted(caption_colour.PALETTE.items())],
                "caption_refused": [
                    {"name": n, "hex": h, "why": w}
                    for n, (h, w) in sorted(caption_colour.REFUSED.items())],
                "caption_default": {"fill": caption_colour.DEFAULT_FILL,
                                    "emph": caption_colour.DEFAULT_EMPH},
                "chat_modes": list(CHAT_MODES),
                "story_modes": list(STORY_MODES),
                "lanes": clip_lanes(),
            })

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
            # NAME THEM BY THEIR TITLE, AND BRING THE SIDECAR. The single
            # download has used `download_name` since the titles landed, and
            # this zip did not — so one click gave you
            # `fns-2905408276-04.mp4`, which this project's own note calls a
            # name that "tells whoever posts it nothing". The two paths
            # answer the same question and must answer it the same way.
            #
            # The `.json` beside each delivery carries the title, the source
            # timestamps and the rights basis, and `batch.py` says plainly
            # why: that is the difference between a render and something you
            # can actually publish. A zip of bare mp4s throws it away at the
            # last step, which is the defect the agent's upload had.
            want = []
            for c in read_clips(row["name"]):
                f = clip_path(row["name"], c["index"])
                if not f.exists():
                    continue
                name = download_name(row["name"], c["index"]) or f.name
                want.append((f, name))
                side = (ROOT / "deliver" / name).with_suffix(".json")
                if side.exists():
                    want.append((side, side.name))
            if not want:
                return self._json({"error": "no clips built yet"}, 404)
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
                # STORED, not DEFLATED: these are already H.264, so deflate
                # buys nothing and costs the whole file through a CPU.
                for f, arcname in want:
                    z.write(f, arcname)
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
            # `re.match` ANCHORS ONLY AT THE START, so every one of these
            # passed: .../videos/123/../../evil, .../videos/123@evil.com,
            # .../videos/123?x=../../. The value is handed to yt-dlp as an
            # argument, so the tail is not inert. `fullmatch`, with the query
            # string the only thing allowed after the id — Twitch's own
            # timestamp links are `?t=1h2m3s`.
            ok_url = (re.fullmatch(r"https?://(www\.)?twitch\.tv/videos?/\d+/?(\?[^#]*)?", url)
                      or re.fullmatch(r"https?://(www\.)?twitch\.tv/[\w-]+/v(ideo)?/\d+/?(\?[^#]*)?", url))
            if not ok_url and not is_local_vod(url):
                return self._json(
                    {"error": "give a Twitch VOD URL (twitch.tv/videos/…), or "
                              "the path to a VOD already on this machine"}, 400)
            if rights not in RIGHTS:
                return self._json(
                    {"error": f"rights must be one of {', '.join(RIGHTS)} — "
                              f"the build refuses to start without one"}, 400)
            name = job_name_for(url, channel)
            # THE RIGHTS BASIS IS DECLARED HERE, SO IT IS WRITTEN HERE.
            #
            # `batch.py` refuses to build a channel whose spec has no
            # `permission` — correctly, because never shipping a source
            # without a rights basis is the oldest rule in this project. But
            # the only place a human declares one is this form, and nothing
            # carried it into the channel spec. So a new streamer's VOD
            # would ingest, transcribe, screen and spec for the best part of
            # an hour and then stop at the build on a file the operator did
            # not know they had to write.
            #
            # Only ever CREATED, never overwritten: a channel already on
            # file carries a permission someone wrote deliberately, often
            # with a note narrower than the four words this form offers, and
            # a routine write eating hand-set state is the defect this repo
            # has recorded more than any other.
            chan_file = ROOT / "channels" / f"{name.split('-')[0]}.json"
            if not chan_file.exists():
                try:
                    sys.path.insert(0, str(ROOT))
                    import batch as _b                      # noqa: PLC0415
                    spec = _b._channel(name)                # house defaults
                    spec["permission"] = rights
                    spec["permission_note"] = (
                        f"Declared on the site when job {name!r} was created. "
                        f"A viewer's chat message is their words on screen — "
                        f"confirm before a wide release.")
                    chan_file.write_text(
                        json.dumps(spec, indent=1) + "\n", encoding="utf-8")
                except Exception as exc:                    # noqa: BLE001
                    return self._json(
                        {"error": f"could not create the channel spec for "
                                  f"{name.split('-')[0]!r}: "
                                  f"{type(exc).__name__}: {exc}"}, 500)
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
            # THE WHOLE CHAIN. The promise is "drop a VOD, get clips";
            # stopping at `specs` delivered specs.
            #
            # THIS LINE WAS INSIDE A COMMENT. An edit collapsed the comment
            # and the call onto ONE line with literal "\n" in the text, so
            # `WORK.put` was commented out and creating a job inserted a row,
            # wrote nine pending stages, set the state to "queued" — and
            # queued nothing. Every status the UI showed wastrue of the
            # database and false of the machine. It parses, it lints, it
            # returns 201, and the product does not work.
            WORK.put((job_id, [s.key for s in ALL_STAGES], ()))
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

        # ── ask the AI to change this clip ────────────────────────────
        #
        # "remove the booms", "cut the end", "turn the chat off". The model
        # returns a PATCH over the same five reviewable fields the editor
        # drawer exposes, and that patch goes through `_clean` and
        # `write_spec` exactly as a typed edit does. The model never touches
        # the file, so the worst a bad reply can do is be refused — and
        # everything the house style owns stays in code, unreachable from
        # here by design.
        m = re.fullmatch(r"/api/jobs/(\d+)/ask/(\d+)", p)
        if m:
            job_id, n = int(m.group(1)), int(m.group(2))
            with db() as c:
                row = c.execute("SELECT * FROM job WHERE id=?",
                                (job_id,)).fetchone()
            if not row:
                return self._json({"error": "no such job"}, 404)
            said = str(body.get("ask", "")).strip()
            if not said:
                return self._json({"error": "say what you want changed"}, 400)
            if len(said) > 600:
                return self._json({"error": "that is too long to be an edit"}, 400)
            sp = spec_path(row["name"], n)
            if not sp.exists():
                return self._json({"error": f"no spec at {sp.name}"}, 404)
            try:
                spec = (json.loads(sp.read_text(encoding="utf-8"))
                        .get("clip") or {})
                detail = views.clip_detail(row["name"], n)
                words = [(w["t"], w.get("s", w["t"]), w.get("e", w["t"]), w["w"])
                         for w in (detail.get("words") or [])]
                from engine import ask as ask_mod             # noqa: PLC0415
                ans = ask_mod.interpret(said, spec=spec, detail=detail,
                                        words=words)
            except Exception as exc:                          # noqa: BLE001
                return self._json(
                    {"error": f"{type(exc).__name__}: {exc}"[:300]}, 502)
            if ans.refused:
                # NOT AN ERROR, AND NOT A BUILD. Saying no to "make the
                # captions bigger" is the right answer; rebuilding anyway
                # because something must happen is not.
                return self._json({"refused": ans.refused, "why": ans.why})
            res, err = write_spec(row["name"], n, ans.patch,
                                  f"asked: {said}"
                                  + (f" — {ans.why}" if ans.why else ""))
            if err:
                return self._json({"error": err, "patch": ans.patch}, 400)
            views.invalidate(row["name"], n)
            if RUNNING.get("job_id") is not None:
                return self._json({"patch": ans.patch, "why": ans.why,
                                   "saved": True, "queued": False,
                                   "note": "saved — a job is already running, "
                                           "so the rebuild has to wait"})
            set_stage(job_id, "build", state="pending", code=None,
                      started=None, ended=None)
            set_job(job_id, state="queued")
            WORK.put((job_id, ["build"], ("--only", str(n), "--force")))
            return self._json({"patch": ans.patch, "why": ans.why,
                               "saved": True, "queued": True})

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
            # ENQUEUE, DO NOT REFUSE. This used to 409 with "one at a
            # time, because Remotion's public/ directory is shared between
            # clips" — which was true and is now fixed (the per-clip data
            # goes out as `--props`, and the PNG sequence directory is a
            # temp dir per call). What is left is memory, and a lane limit
            # is a queue, not a rejection: clicking six clips enqueues six.
            #
            # The ONE thing still refused is overlapping the CHAIN's own
            # build stage on the same job, which walks every spec itself —
            # two writers on one clip's artifacts, which is the collision
            # class this whole round exists to remove.
            key = (job_id, n)
            with _BLOCK:
                if RUNNING.get("job_id") == job_id \
                        and RUNNING.get("stage") == "build":
                    return self._json(
                        {"error": "this job's own build stage is running and "
                                  "walks every clip — wait for it, or cancel "
                                  "it, then ask for this one"}, 409)
                if key in BUILDING or key in QUEUED:
                    return self._json(
                        {"error": f"clip {n:02d} is already being cut"}, 409)
                QUEUED.add(key)
                JOBS_BY_ID[job_id] = row["name"]
                waiting = sum(1 for k in QUEUED if k[0] == job_id)
                live = sum(1 for k in BUILDING if k[0] == job_id)
            # --force, because a rebuild after a note is exactly the case the
            # "already built and passed, skipping" guard would swallow.
            set_stage(job_id, "build", state="running", code=None,
                      started=time.time(), ended=None)
            set_job(job_id, state="running")
            CLIPQ.put(key)
            return self._json({"queued": "build", "clip": n,
                               "lanes": clip_lanes(),
                               "building": live, "waiting": waiting})

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
    # does not start its own worker thread.
    #
    # THE REASON CHANGED AND THE RULE DID NOT. It used to be Resolve: one
    # GUI app, one scripting API on its GUI thread, and two runners would
    # fight over it. The native renderer took Resolve out of the build, and
    # it is tempting to call that the mass-production unlock — it is not,
    # yet. Remotion renders every overlay through a SHARED `public/`
    # directory, so two clips building at once still corrupt each other.
    # Dropping Resolve removed one of the two causes of serialisation; the
    # overlay renderer is the other, and it is also 85% of the wall clock.
    runner = None
    try:
        runner = runlock.take("web/server.py")
        threading.Thread(target=worker, daemon=True).start()
        # ONE THREAD PER LANE. `clip_lanes()` measures free memory against
        # ~1.9 GB a lane, so the number is the machine's, not a guess — and
        # the threads only wait on a queue, so starting a couple costs
        # nothing when nothing is building.
        lanes = clip_lanes()
        for _ in range(lanes):
            threading.Thread(target=clip_worker, daemon=True).start()
        print(f"  {lanes} clip-build lane(s)")
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
