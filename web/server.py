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

import json
import mimetypes
import os
import queue
import re
import shutil
import sqlite3
import subprocess
import threading
import time
import urllib.parse
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
JOBS = ROOT / "jobs"
DB = ROOT / "web" / "factory.db"
VENV = ROOT / ".venv" / "bin" / "python"
PORT = int(os.environ.get("CLIP_FACTORY_PORT", "8808"))

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


def log_path(job_name: str, stage: str) -> Path:
    p = JOBS / job_name / "web" / f"{stage}.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def run_stage(job_id: int, job_name: str, url: str, rights: str,
              stage: Stage, extra: tuple[str, ...] = ()) -> int:
    """One stage as a subprocess, output tee'd to its own log."""
    out = log_path(job_name, stage.key)
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
    c = d.setdefault("clip", {})
    changed = {k: (c.get(k), v) for k, v in clean.items() if c.get(k) != v}
    c.update(clean)
    if note.strip():
        c["notes"] = (str(c.get("notes", "")).rstrip() + " " + note.strip()).strip()
    sp.write_text(json.dumps(d, indent=1) + "\n")
    return {"file": sp.name, "changed": {k: {"was": a, "now": b}
                                         for k, (a, b) in changed.items()}}, None


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
    }


def job_name_for(url: str, given: str) -> str:
    """`fns-2905408276` — the channel and the VOD id, which is what the
    pipeline's own directories are already named after."""
    given = re.sub(r"[^a-z0-9-]+", "-", given.strip().lower()).strip("-")
    vid = ""
    m = re.search(r"/videos?/(\d+)", url)
    if m:
        vid = m.group(1)
    if given and vid:
        return f"{given}-{vid}"
    return given or (f"vod-{vid}" if vid else f"job-{int(time.time())}")


# -------------------------------------------------------------- http ------
class Handler(BaseHTTPRequestHandler):
    server_version = "ClipFactory/1.0"

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

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return {}

    def _file(self, path: Path) -> None:
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
            self.end_headers()
            self.wfile.write(chunk)
            return
        self._send(200, path.read_bytes(), ctype, {"Accept-Ranges": "bytes"})

    # -- routes
    def do_GET(self):                                   # noqa: N802
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        p = u.path

        if p in ("/", "/index.html"):
            return self._file(WEB / "static" / "index.html")
        if p in ("/app.js", "/app.css"):
            return self._file(WEB / "static" / p.lstrip("/"))

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
            with db() as c:
                row = c.execute("SELECT * FROM job WHERE id=?",
                                (int(m.group(1)),)).fetchone()
            if not row:
                return self._json({"error": "no such job"}, 404)
            lp = log_path(row["name"], stage)
            text = lp.read_text()[-20000:] if lp.exists() else ""
            return self._json({"stage": stage, "text": text})

        m = re.fullmatch(r"/api/jobs/(\d+)/clip/(\d+)", p)
        if m:
            with db() as c:
                row = c.execute("SELECT * FROM job WHERE id=?",
                                (int(m.group(1)),)).fetchone()
            if not row:
                return self._json({"error": "no such job"}, 404)
            return self._file(ROOT / "renders" /
                              f"{row['name']}-{int(m.group(2)):02d}.mp4")

        return self._json({"error": "not found"}, 404)

    def do_HEAD(self):                                  # noqa: N802
        self.do_GET()

    def do_POST(self):                                  # noqa: N802
        p = urllib.parse.urlparse(self.path).path
        body = self._body()

        if p == "/api/jobs":
            url = str(body.get("url", "")).strip()
            rights = str(body.get("rights", "")).strip()
            channel = str(body.get("channel", "")).strip()
            note = str(body.get("note", "")).strip()
            if not url.startswith(("http://", "https://")):
                return self._json({"error": "a Twitch VOD URL is required"}, 400)
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
            WORK.put((job_id, [s.key for s in STAGES], ()))
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
            return self._json({"error": err} if err else res, 400 if err else 200)

        m = re.fullmatch(r"/api/jobs/(\d+)/build/(\d+)", p)
        if m:
            job_id, n = int(m.group(1)), int(m.group(2))
            with db() as c:
                row = c.execute("SELECT * FROM job WHERE id=?",
                                (job_id,)).fetchone()
            if not row:
                return self._json({"error": "no such job"}, 404)
            if not spec_path(row["name"], n).exists():
                return self._json({"error": f"no spec for clip {n:02d}"}, 404)
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
    threading.Thread(target=worker, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"clip factory on http://127.0.0.1:{PORT}  (root {ROOT})")
    print(f"  {len(ALL_STAGES)} stages: "
          f"{' -> '.join(s.key for s in ALL_STAGES)}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
