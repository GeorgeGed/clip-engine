#!/usr/bin/env python3
"""The render agent: the piece that has to live on a Mac next to Resolve.

    ./.venv/bin/python worker/agent.py                 # local SQLite queue
    CLIP_WORKER_URL=https://… CLIP_WORKER_TOKEN=… \\
        ./.venv/bin/python worker/agent.py             # a cloud control plane

WHY THIS EXISTS. `web/server.py` already queues jobs and runs stages, but
only from its own HTTP POST, on this machine, while someone has it open. A
website needs work queued from anywhere, picked up by whichever Mac is
awake, and results pushed back. That is this program, and it is deliberately
the ONLY part that has to run here: everything else — auth, the project
list, the clip grid, storage — can be hosted anywhere.

IT RUNS THE REAL COMMANDS. Every stage is the same subprocess a person would
type, with its output tee'd to `jobs/<job>/web/<stage>.log`. Nothing about
the editing is reimplemented, so when the pipeline changes the agent follows
it for free, and a stage that fails fails visibly.

FOUR THINGS IT REFUSES TO GET WRONG
-----------------------------------

**One job at a time.** Resolve serves its scripting API on its own GUI
thread and Remotion's `public/` is shared. Two jobs at once is not slower,
it is wrong. The agent is single-threaded by construction and the claim is a
single conditional UPDATE, so two agents on one machine cannot take the same
job.

**It checks Resolve before the hour, not during it.** `build` is the only
stage that needs Resolve and it is last, so an agent that claims a job with
Resolve closed would ingest, transcribe, detect, screen and spec for the
best part of an hour before failing. It reports its capabilities when
claiming and re-checks immediately before the build stage.

**It resumes instead of restarting.** If the agent dies mid-job, the stages
that finished stay finished: the backend records them and the next claim
asks only for what is left. The pipeline is already idempotent — `batch.py
build` skips a clip that is built and passed unless `--force` — so a retry
costs minutes, not an hour of transcription.

**It publishes the artifact, not the plan.** Only clips that `batch.py
build` wrote into `deliver/` are uploaded. That directory is what
`engine.deliver_qc` gates: a clip that failed the gate is in the manifest
with its reason and is not delivered. A cue count is a claim about the plan;
the file is the thing that ships.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

sys.path.insert(0, str(ROOT / "web"))

import runlock                                          # noqa: E402
from worker.backend import Cancelled, Job, from_env      # noqa: E402

VENV = ROOT / ".venv" / "bin" / "python"
POLL_IDLE = 5.0          # seconds between claims when there is no work
HEARTBEAT = 10.0         # seconds between progress reports while a stage runs

# The chain, as commands. {job}/{url}/{rights} are filled in.
STAGE_ARGV = {
    "ingest":  ("run.py", "ingest", "{url}", "--job", "{job}", "--rights", "{rights}"),
    "analyse": ("run.py", "analyse", "--job", "{job}"),
    "rank":    ("run.py", "rank", "--job", "{job}"),
    "screen":  ("batch.py", "{job}", "screen"),
    "prep":    ("batch.py", "{job}", "prep"),
    "specs":   ("batch.py", "{job}", "specs"),
    "build":   ("batch.py", "{job}", "build"),
    "report":  ("batch.py", "{job}", "report"),
}
NEEDS_RESOLVE = {"build"}

STOP = False


def _stop(*_a):
    global STOP
    STOP = True
    print("\n[agent] finishing the current stage, then stopping", flush=True)


def log(msg: str) -> None:
    print(f"[agent] {msg}", flush=True)


# ------------------------------------------------------------- capability --
def resolve_ok() -> tuple[bool, list[str]]:
    """Is Resolve reachable right now? Imports and connects, so it is called
    on a schedule rather than in a loop — the API is on Resolve's GUI thread
    and this project has watched that thread wedge."""
    try:
        from engine.resolve_driver import doctor          # noqa: PLC0415
        d = doctor()
        return d.ok(), list(d.notes)[:3]
    except Exception as exc:                              # noqa: BLE001
        return False, [f"{type(exc).__name__}: {exc}"]


def capabilities() -> dict:
    ok, notes = resolve_ok()
    return {"resolve": ok, "notes": notes, "host": socket.gethostname(),
            "platform": platform.platform(), "python": platform.python_version()}


# ------------------------------------------------------------- progress ----
def progress(path: Path, stage: str, specs: int) -> dict:
    """The last line the stage printed, and for `build` how many clips are
    done. Derived from the log the stage already writes, so it cannot drift
    from what is happening."""
    if not path.exists():
        return {}
    try:
        tail = path.read_text(errors="replace")[-8000:]
    except OSError:
        return {}
    lines = [ln.rstrip() for ln in tail.splitlines() if ln.strip()]
    out = {"line": lines[-1][:200] if lines else ""}
    if stage == "build":
        out["done"] = tail.count("] -> ")
        out["total"] = specs
    return out


def spec_count(job_name: str) -> int:
    chan = job_name.split("-")[0]
    return len(list((ROOT / "clips").glob(f"{chan}-*.json")))


# ------------------------------------------------------------ one stage ----
def run_stage(be, job: Job, stage: str) -> int:
    argv = STAGE_ARGV[stage]
    cmd = [str(VENV)] + [a.format(job=job.name, url=job.url, rights=job.rights)
                         for a in argv]
    if stage == "build":
        cmd += list(job.extra)
    lp = be.log_path(job, stage)
    be.stage_state(job, stage, "running")
    log(f"{job.name} · {stage}: {' '.join(cmd[1:])}")
    with lp.open("w") as fh:
        fh.write(f"$ {' '.join(cmd)}\n\n")
        fh.flush()
        proc = subprocess.Popen(cmd, cwd=ROOT, stdout=fh,
                                stderr=subprocess.STDOUT)
        n = spec_count(job.name)
        last = 0.0
        while proc.poll() is None:
            time.sleep(0.5)
            if time.time() - last >= HEARTBEAT:
                last = time.time()
                if not be.heartbeat(job, stage, progress(lp, stage, n)):
                    proc.terminate()
                    try:
                        proc.wait(timeout=20)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    raise Cancelled(stage)
        code = proc.returncode
    be.stage_state(job, stage, "done" if code == 0 else "failed", code)
    return code


# -------------------------------------------------------------- publish ----
def publish_clips(be, job: Job) -> list[dict]:
    """Upload what `deliver/` holds, which is what passed the gate.

    `batch.py build` writes a clip there only after `engine.deliver_qc`
    passes it; a clip that failed is in the manifest with its reason and
    never reaches this directory. So this function needs no quality opinion
    of its own, which is the point.

    THE SIDECAR GOES TOO. `batch.py` writes `<name>.json` beside every
    delivery, and its own comment says why: *"fns-2905408276-06.mp4" tells
    whoever posts it nothing, and they also need the title, the source
    timestamps and the rights basis in one place — that is the difference
    between a render and something you can actually publish.* Uploading the
    mp4 alone would throw that away at the last step.
    """
    man_p = ROOT / "jobs" / job.name / "manifest.json"
    man = json.loads(man_p.read_text()) if man_p.exists() else {}
    out = []
    deliver = ROOT / "deliver"
    if not deliver.is_dir():
        return out
    chan = job.name.split("-")[0]
    # `<channel>-<index>-<slug>.mp4` — the index is the SECOND field, not the
    # last; the slug that follows it has hyphens of its own.
    pat = re.compile(rf"^{re.escape(chan)}-(\d+)-")
    for mp4 in sorted(deliver.glob(f"{chan}-*.mp4")):
        m = pat.match(mp4.stem)
        if not m:
            continue
        index = int(m.group(1))
        meta = dict(man.get(f"{chan}-{index:02d}", {}))   # keyed by spec stem
        if meta.get("qc_ok") is False:
            continue                       # held back by the gate; say nothing
        side = mp4.with_suffix(".json")
        if side.exists():
            try:
                meta["sidecar"] = json.loads(side.read_text())
            except json.JSONDecodeError:
                pass
        meta["bytes"] = mp4.stat().st_size
        # BOTH FILES UP FIRST, THEN ONE ROW. A delivery is an mp4 and its
        # sidecar, and recording each of them as a clip wrote two rows on
        # one (job_id, idx) primary key — the second upserting the mp4's URL
        # away and leaving the clip unplayable.
        url = be.upload(job, index, mp4, meta)
        rec = {"index": index, "url": url, "name": mp4.name}
        if side.exists():
            meta["sidecar_url"] = be.upload(
                job, index, side, {"kind": "sidecar", "of": mp4.name})
            rec["sidecar"] = meta["sidecar_url"]
        be.record(job, index, url, meta)
        out.append(rec)
        log(f"  published {mp4.name} -> {url}")
    return out


# ----------------------------------------------------------- artifacts -----
def write_specs(job: Job) -> int:
    """The control plane's specs win over whatever is on this disk.

    George's every note reduces to editing one of five fields, and the one
    time `batch.py specs` regenerated over a reviewed spec it silently ate
    four rounds of review. With a cloud front end the reviewed spec lives
    there, so it is written down BEFORE any stage runs.
    """
    if not job.specs:
        return 0
    chan = job.name.split("-")[0]
    (ROOT / "clips").mkdir(exist_ok=True)
    n = 0
    for idx, spec in job.specs.items():
        p = ROOT / "clips" / f"{chan}-{int(idx):02d}.json"
        # ONLY WRITE A REAL CHANGE. Rewriting an identical spec in our own
        # formatting still moves its mtime, and `views.clip_detail` caches
        # against that mtime — so an unconditional write quietly re-derives
        # every clip's plan through `_plan_only` for nothing. Caught by
        # diffing clips/ against a backup after a round trip that could not
        # have changed any content: two files differed, both only in
        # whitespace.
        try:
            if p.exists() and json.loads(p.read_text()) == spec:
                continue
        except (json.JSONDecodeError, OSError):
            pass                       # unreadable on disk: the sent one wins
        p.write_text(json.dumps(spec, indent=1))
        n += 1
    return n


# What the UI needs, and when it becomes true on disk.
AFTER = {"screen": ("candidates",), "specs": ("spec",),
         "prep": ("thumb",), "build": ("detail",)}


def push_artifacts(be, job: Job, stage: str) -> None:
    """Send the UI's data up after the stage that creates it.

    A cloud front end cannot derive any of this — it is computed here from
    files that never leave the Mac. Failures are logged, never fatal: a
    missing thumbnail is a blank tile, not a lost build.
    """
    kinds = AFTER.get(stage)
    if not kinds or be.name == "local":
        return
    sys.path.insert(0, str(ROOT / "web"))
    try:
        import views                                   # noqa: PLC0415
    except Exception as exc:                           # noqa: BLE001
        log(f"  artifacts: cannot import views ({exc})")
        return
    chan = job.name.split("-")[0]
    try:
        if "candidates" in kinds:
            c = views.candidates(job.name)
            be.artifact(job, "candidates", None, data=c)
            log(f"  pushed {len(c)} candidates")
        if "spec" in kinds:
            n = 0
            for sp in sorted((ROOT / "clips").glob(f"{chan}-*.json")):
                idx = int(sp.stem.rsplit("-", 1)[-1])
                be.artifact(job, "spec", idx,
                            data=json.loads(sp.read_text()))
                n += 1
            log(f"  pushed {n} spec(s)")
        if "thumb" in kinds:
            n = 0
            for c in views.candidates(job.name):
                f = views.candidate_thumb(job.name, c["n"])
                if not f:
                    continue
                url = be.upload(job, c["n"], f, {"kind": "thumb"})
                be.artifact(job, "thumb", c["n"], url=url)
                n += 1
            log(f"  pushed {n} thumbnail(s)")
        if "detail" in kinds:
            n = 0
            for sp in sorted((ROOT / "clips").glob(f"{chan}-*.json")):
                idx = int(sp.stem.rsplit("-", 1)[-1])
                d = views.clip_detail(job.name, idx)
                if d:
                    be.artifact(job, "detail", idx, data=d)
                    n += 1
            log(f"  pushed {n} clip detail(s)")
    except Exception as exc:                           # noqa: BLE001
        log(f"  artifacts after {stage} failed: {type(exc).__name__}: {exc}")


# ------------------------------------------------------------- one job -----
def run_job(be, job: Job) -> str:
    log(f"claimed {job.name}  ({job.rights})  stages: {', '.join(job.stages)}")
    wrote = write_specs(job)
    if wrote:
        log(f"  wrote {wrote} spec(s) from the control plane")
    for stage in job.stages:
        if STOP:
            return "paused"
        if stage in NEEDS_RESOLVE:
            ok, notes = resolve_ok()
            if not ok:
                why = ("DaVinci Resolve is not reachable — open it, and set "
                       "Preferences > System > General > External scripting "
                       "using to Local. " + "; ".join(notes))
                be.log_path(job, stage).write_text(why + "\n")
                be.stage_state(job, stage, "failed", 1)
                log(f"  {stage}: {why}")
                return f"failed:{stage} (Resolve not reachable)"
        try:
            code = run_stage(be, job, stage)
        except Cancelled:
            log(f"  {stage}: cancelled by the control plane")
            return "cancelled"
        if code != 0:
            log(f"  {stage}: exit {code}")
            return f"failed:{stage}"
        push_artifacts(be, job, stage)
    clips = publish_clips(be, job)
    man_p = ROOT / "jobs" / job.name / "manifest.json"
    manifest = json.loads(man_p.read_text()) if man_p.exists() else {}
    be.finish(job, "done", {"clips": clips, "manifest": manifest})
    log(f"done {job.name} — {len(clips)} clip(s) published")
    return "done"


# ---------------------------------------------------------------- loop -----
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--once", action="store_true",
                    help="take at most one job, then exit")
    ap.add_argument("--name", default=os.environ.get(
        "CLIP_WORKER_NAME", socket.gethostname()))
    ap.add_argument("--poll", type=float, default=POLL_IDLE)
    a = ap.parse_args()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    be = from_env()
    # ONE RUNNER PER MACHINE. Against the local SQLite the site is a runner
    # too — it queues a job AND leaves the row at `state='queued'`, which is
    # what this claims — so running both would drive one Resolve from two
    # processes. A cloud control plane is a different queue, so the lock is
    # only for the local backend.
    runner = None
    if be.name == "local":
        try:
            runner = runlock.take("worker/agent.py")
        except runlock.Held as other:
            log(f"{other} is already the runner on this machine — "
                "nothing for this agent to do")
            return 0
    caps = capabilities()
    log(f"{a.name} · backend {be.name} · Resolve "
        + ("ready" if caps["resolve"] else "NOT reachable — "
           + "; ".join(caps["notes"])))
    be.health(a.name, caps)

    idle_since = time.time()
    # Not 0.0: the loop's own `> 60` test would then fire immediately and
    # send a second identical health report before any work had happened.
    last_health = time.time()
    while not STOP:
        if time.time() - last_health > 60:
            last_health = time.time()
            caps = capabilities()
            be.health(a.name, caps)
        try:
            job = be.claim(a.name, caps)
        except Exception as exc:                          # noqa: BLE001
            log(f"claim failed ({type(exc).__name__}: {exc}) — retrying")
            time.sleep(min(30.0, a.poll * 4))
            continue
        if job is None:
            if a.once:
                # --once means "at most one job, then exit", and that has to
                # include finding none. Polling forever here is what makes it
                # useless in cron, and it is what two agents racing for one
                # job look like from the loser's side.
                log("nothing queued")
                break
            if time.time() - idle_since > 300:
                idle_since = time.time()
                log("idle")
            time.sleep(a.poll)
            continue
        idle_since = time.time()
        try:
            state = run_job(be, job)
        except Exception as exc:                          # noqa: BLE001
            import traceback
            log(f"job {job.name} blew up: {exc}\n{traceback.format_exc()}")
            state = f"error:{type(exc).__name__}"
        if state not in ("done",):
            be.finish(job, state, {})
        if a.once:
            break
    log("stopped")
    if runner is not None:
        runner.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
