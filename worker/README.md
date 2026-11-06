# The render agent

The one piece that has to run on a Mac, because DaVinci Resolve does.

    ./.venv/bin/python worker/agent.py            # local queue, no account needed
    ./.venv/bin/python worker/agent.py --once     # take one job and exit

Point it at a control plane with two environment variables:

    CLIP_WORKER_URL=https://your-app/api/worker
    CLIP_WORKER_TOKEN=…

## Why the work splits here and not somewhere else

Everything except rendering can be hosted anywhere: auth, the project list,
the clip grid, storage, scheduling. Rendering cannot — Resolve serves its
scripting API on its own GUI thread on one machine, and Remotion's `public/`
is shared. That is not a deployment choice to revisit by renting a bigger
box, so the architecture is forced:

    browser → web app + database + storage → queue → AGENT on a Mac → clips back

The agent is single-threaded by construction, runs the same commands a
person would type, and tee's each stage to `jobs/<job>/web/<stage>.log`.
Nothing about the editing is reimplemented, so the agent follows the
pipeline for free.

## What it refuses to get wrong

* **One job at a time.** The local claim is a single conditional `UPDATE`;
  the Postgres one is `for update skip locked`. Two agents cannot take the
  same job, and one agent cannot take two.
* **Resolve is checked before the hour, not during it.** `build` is last and
  is the only stage that needs Resolve, so an agent that claimed with
  Resolve closed would transcribe and screen for the best part of an hour
  before failing. Capabilities go up with the claim, and the check runs
  again immediately before the build stage.
* **It resumes.** Finished stages stay finished; the next claim asks only
  for what is left. `batch.py build` already skips a clip that is built and
  passed, so a retry costs minutes rather than an hour of transcription.
* **It publishes the artifact, not the plan.** Only what `batch.py build`
  wrote into `deliver/` is uploaded, and a clip only lands there after
  `engine.deliver_qc` passes it.

## The control-plane contract

Six calls, one bearer token. `worker/backend.py` is the client and the
authority on the shapes.

| | |
|---|---|
| `POST /claim` | `{worker, caps}` → a job or null |
| `POST /heartbeat` | `{job, stage, progress}` → `{cancelled}` |
| `POST /log` | `{job, stage, text}` |
| `POST /upload-url` | `{job, clip, name, type}` → `{url, headers?, public}` |
| `POST /clip` | `{job, clip, url, meta}` |
| `POST /finish` | `{job, state, manifest}` |

**Uploads go straight to storage, not through the control plane.** A clip is
about 20 MB and a serverless function is the wrong place to put 20 MB. Both
Supabase Storage and S3/R2 hand out a signed PUT for exactly this, so
`upload-url` returns somewhere to PUT and `clip` records that it landed.

`schema.sql` is the Postgres side, including a `claim_job` function and the
**lease**: a worker that dies mid-job must not strand it, and a thread flag
cannot survive a crash, a power cut or a Mac going to sleep. All three
happen.

## Keeping it alive

On macOS, a LaunchAgent restarts it and survives logout:

    cp worker/com.clipfactory.agent.plist ~/Library/LaunchAgents/
    launchctl load ~/Library/LaunchAgents/com.clipfactory.agent.plist

Resolve must be running and logged in for the build stage, which means the
Mac cannot be at the login screen. `caffeinate -s` keeps it awake.
