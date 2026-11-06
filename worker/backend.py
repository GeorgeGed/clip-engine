"""Where the worker gets its jobs, and where it puts the clips.

TWO IMPLEMENTATIONS BEHIND ONE INTERFACE, and the local one is not a toy.

* `LocalBackend` reads `web/factory.db`, the SQLite the site already uses.
  It works today, on this machine, with no account anywhere — which means
  the agent can be run and watched before any cloud exists.
* `HttpBackend` speaks to a control plane over HTTPS with a bearer token.
  The contract is six calls, written out in this file, so the website can be
  built against it without reading the agent.

The split is not architecture for its own sake. The agent is the piece that
has to live on a Mac next to Resolve; everything else can live anywhere, and
the only honest way to keep that true is to make the agent talk through a
seam rather than reach into a database.

WHY A WORKER AT ALL. `web/server.py` already queues jobs and runs stages,
but it only takes work from its own HTTP POST, on this machine, while
someone has it open. A website needs the opposite: work queued from
anywhere, picked up by whichever Mac is awake, with results pushed back.
"""

from __future__ import annotations

import json
import mimetypes
import os
import sqlite3
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Job:
    id: str
    name: str                    # jobs/<name>, which every path is keyed on
    url: str                     # the VOD, or a path on this machine
    rights: str                  # explicit | affiliate | client_owned
    stages: list[str]
    note: str = ""
    extra: list[str] = field(default_factory=list)   # e.g. --only 16 --force


class Cancelled(Exception):
    """The control plane withdrew the job mid-run."""


# ---------------------------------------------------------------- local ----
class LocalBackend:
    """The site's own SQLite. Same tables, so the two cannot disagree."""

    name = "local"

    def __init__(self, db: Path | None = None):
        self.db = Path(db or ROOT / "web" / "factory.db")

    def _c(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA busy_timeout=30000")
        return c

    def claim(self, worker: str, caps: dict) -> Job | None:
        """One UPDATE, so two agents on one machine cannot take the same job.

        `state='queued' AND ...` in the WHERE is the whole lock: SQLite
        serialises the write, so exactly one of them changes a row.
        """
        with self._c() as c:
            row = c.execute(
                "SELECT * FROM job WHERE state='queued' ORDER BY created LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            n = c.execute(
                "UPDATE job SET state=?, updated=? WHERE id=? AND state='queued'",
                (f"running:{worker}", time.time(), row["id"])).rowcount
            if not n:
                return None
            done = {r["key"] for r in c.execute(
                "SELECT key FROM stage WHERE job_id=? AND state='done'",
                (row["id"],))}
        from web import server as site                    # noqa: PLC0415
        stages = [s.key for s in site.ALL_STAGES if s.key not in done]
        return Job(id=str(row["id"]), name=row["name"], url=row["url"],
                   rights=row["rights"], note=row["note"] or "", stages=stages)

    def heartbeat(self, job: Job, stage: str, progress: dict) -> bool:
        with self._c() as c:
            row = c.execute("SELECT state FROM job WHERE id=?",
                            (int(job.id),)).fetchone()
        return bool(row) and not str(row["state"]).startswith("cancel")

    def stage_state(self, job: Job, stage: str, state: str, code=None) -> None:
        now = time.time()
        with self._c() as c:
            c.execute("INSERT INTO stage (job_id,key,state,started,ended,code) "
                      "VALUES (?,?,?,?,?,?) ON CONFLICT(job_id,key) DO UPDATE SET "
                      "state=excluded.state, ended=excluded.ended, code=excluded.code",
                      (int(job.id), stage, state,
                       now if state == "running" else None,
                       None if state == "running" else now, code))

    def log_path(self, job: Job, stage: str) -> Path:
        p = ROOT / "jobs" / job.name / "web"
        p.mkdir(parents=True, exist_ok=True)
        return p / f"{stage}.log"

    def publish(self, job: Job, index: int, path: Path, meta: dict) -> str:
        """Locally there is nowhere to upload to; the file is already where
        the site serves it from. Returning the path keeps the contract."""
        return str(path.relative_to(ROOT))

    def finish(self, job: Job, state: str, manifest: dict) -> None:
        with self._c() as c:
            c.execute("UPDATE job SET state=?, updated=? WHERE id=?",
                      (state, time.time(), int(job.id)))

    def health(self, worker: str, h: dict) -> None:
        (ROOT / "web" / "worker-health.json").write_text(
            json.dumps({"worker": worker, "at": time.time(), **h}, indent=1))


# ----------------------------------------------------------------- http ----
class HttpBackend:
    """A control plane over HTTPS. Six calls, one bearer token.

        POST {base}/claim      {worker, caps}            -> job | null
        POST {base}/heartbeat  {job, stage, progress}    -> {cancelled: bool}
        POST {base}/log        {job, stage, text}        -> {}
        POST {base}/upload-url {job, clip, name, type}   -> {url, headers?, public}
        POST {base}/clip       {job, clip, url, meta}    -> {}
        POST {base}/finish     {job, state, manifest}    -> {}
        POST {base}/health     {worker, health}          -> {}

    UPLOADS GO STRAIGHT TO STORAGE, not through the control plane. A clip is
    20 MB and a serverless function is the wrong place to put 20 MB; both
    Supabase Storage and S3/R2 hand out a signed PUT for exactly this. So
    `upload-url` returns somewhere to PUT, the agent PUTs the bytes, and
    `clip` records that it landed.
    """

    name = "http"

    def __init__(self, base: str, token: str, timeout: float = 30.0):
        self.base = base.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _post(self, path: str, body: dict) -> dict:
        req = urllib.request.Request(
            f"{self.base}/{path.lstrip('/')}",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.token}"},
            method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read() or b"{}")

    def claim(self, worker: str, caps: dict) -> Job | None:
        d = self._post("claim", {"worker": worker, "caps": caps})
        j = d.get("job")
        if not j:
            return None
        return Job(id=str(j["id"]), name=j["name"], url=j["url"],
                   rights=j["rights"], note=j.get("note", ""),
                   stages=j.get("stages") or [], extra=j.get("extra") or [])

    def heartbeat(self, job: Job, stage: str, progress: dict) -> bool:
        try:
            d = self._post("heartbeat", {"job": job.id, "stage": stage,
                                         "progress": progress})
        except urllib.error.URLError:
            # A dropped heartbeat is the network, not a cancellation. Keep
            # working — the lease is what decides, and the control plane can
            # reissue the job if this one really has died.
            return True
        return not d.get("cancelled")

    def stage_state(self, job: Job, stage: str, state: str, code=None) -> None:
        self._post("heartbeat", {"job": job.id, "stage": stage,
                                 "state": state, "code": code})

    def log_path(self, job: Job, stage: str) -> Path:
        p = ROOT / "jobs" / job.name / "web"
        p.mkdir(parents=True, exist_ok=True)
        return p / f"{stage}.log"

    def publish(self, job: Job, index: int, path: Path, meta: dict) -> str:
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        d = self._post("upload-url", {"job": job.id, "clip": index,
                                      "name": path.name, "type": ctype})
        req = urllib.request.Request(
            d["url"], data=path.read_bytes(), method="PUT",
            headers={"Content-Type": ctype, **(d.get("headers") or {})})
        with urllib.request.urlopen(req, timeout=max(self.timeout, 600)):
            pass
        url = d.get("public") or d["url"].split("?", 1)[0]
        self._post("clip", {"job": job.id, "clip": index, "url": url,
                            "meta": meta})
        return url

    def finish(self, job: Job, state: str, manifest: dict) -> None:
        self._post("finish", {"job": job.id, "state": state,
                              "manifest": manifest})

    def health(self, worker: str, h: dict) -> None:
        try:
            self._post("health", {"worker": worker, "health": h})
        except urllib.error.URLError:
            pass


def from_env():
    """`CLIP_WORKER_URL` + `CLIP_WORKER_TOKEN`, else the local SQLite."""
    base, tok = os.environ.get("CLIP_WORKER_URL"), os.environ.get("CLIP_WORKER_TOKEN")
    if base and tok:
        return HttpBackend(base, tok)
    return LocalBackend()
