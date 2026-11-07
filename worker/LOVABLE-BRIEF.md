# The control plane, as a brief

Paste the **Build this** section into Lovable. The rest is why, and the
things that will bite.

The split is forced, not chosen: the render drives DaVinci Resolve's
scripting API, which lives on a GUI thread on one Mac. Everything else can
be hosted. The Mac already runs an agent (`worker/agent.py`) that **only
ever dials outward** — eight POSTs and a signed PUT — so there is no tunnel,
no domain and no DNS anywhere in this design.

**The contract below is not a proposal. It has been run.**
`worker/mock_control_plane.py` implements it and the real agent completed a
real job against it: 1 claim, 2 stage transitions, 1 heartbeat, 2 uploads,
1 clip row, 1 finish, 24 spec artifacts, and 24 specs byte-identical after
a round trip. Run it yourself before trusting any of this:

    ./.venv/bin/python -u worker/mock_control_plane.py --port 8906 &
    CLIP_WORKER_URL=http://127.0.0.1:8906 CLIP_WORKER_TOKEN=test \
        ./.venv/bin/python worker/agent.py --once

---

## Build this

A private web app for one person (later a handful) that queues video jobs
and reviews the clips a Mac renders for them. Postgres + object storage +
email sign-in. No public sign-up.

**Tables:** exactly as in `worker/schema.sql` — run it as the migration.
`job`, `stage`, `clip`, `artifact`, `worker`, and the `claim_job` function.

**Eight endpoints**, all `POST`, all requiring `Authorization: Bearer
<WORKER_TOKEN>` except where noted. They are machine-to-machine: the caller
is a Python script, not a browser, so they must not require a user session.

| endpoint | body | returns |
|---|---|---|
| `/claim` | `{worker, caps}` | `{job: {id, name, url, rights, stages[], note, extra[], specs{}} \| null}` |
| `/stage` | `{job, stage, state, code}` | `{}` |
| `/heartbeat` | `{job, stage, progress}` | `{cancelled: bool}` |
| `/artifact` | `{job, kind, idx, data, url}` | `{}` |
| `/upload-url` | `{job, clip, name, type}` | `{url, headers?, public}` |
| `/clip` | `{job, clip, url, meta}` | `{}` |
| `/finish` | `{job, state, manifest}` | `{}` |
| `/health` | `{worker, health}` | `{}` |

- `/claim` calls `claim_job(worker, caps.resolve)` and returns one job or
  null. It must also return every spec row for that job, keyed by clip
  number as a string: `{"12": {...}, "16": {...}}`.
- `/upload-url` returns a **signed PUT URL**. The agent PUTs the bytes
  straight to storage — never through the app. A clip is 20–40 MB.
- `/clip` writes **one row per clip**, not per file. A delivery is an mp4
  plus a sidecar json; the sidecar's URL goes in `meta.sidecar_url`.
- `/heartbeat` returning `{"cancelled": true}` makes the agent stop and
  terminate the running stage. That is how a cancel button works.

**Three screens:**

1. **Projects** — a list of jobs with state and progress, and a form to add
   one: a Twitch VOD URL, and a **rights basis** which is a required choice
   of `explicit | affiliate | client_owned` with no default.
2. **Clips** — a grid from `artifact kind='candidates'`: one card per
   candidate with its thumbnail (`kind='thumb'`), score, duration, and the
   screen's verdict and reason. Filters: usable / rendered / refused / all.
   Default to **usable** — a blocked clip shown first is a clip you cannot
   have.
3. **Editor** — one clip: the mp4 in a `<video>`, the transcript from
   `artifact kind='detail'`, and a form over the five spec fields
   (`in_point`, `out_point`, `booms`, `chat_mode`, `hook`). Saving writes
   the `spec` row. A **Rebuild** button inserts a job with
   `stages_remaining = ['build']` and `extra = ['--only','<n>','--force']`.

**Saving a spec MERGES, never replaces.** The spec carries reasoning no form
collects. Patch the five fields and leave every other key alone.

---

## Four things that will bite

**1. Range works at the origin — the CDN is the part still untested.**
The editor plays 20–40 MB mp4s by scrubbing, which needs 206 partial
responses, and no Supabase *documentation* page mentions Range at all. The
source settles it: `src/storage/range.ts` has a full `parseRangeHeader`
handling `bytes=N-M` and suffix ranges, `renderer.ts` sets `Accept-Ranges:
bytes` and `Content-Range` and takes its status from the backend's
`httpStatusCode`, and the adapter interface carries `range`, `contentRange`
and `httpStatusCode` through. So the origin is not a guess any more.

What is NOT settled is the CDN in front of a public URL, which is the layer
most likely to surprise. One command, the moment a real URL exists:

    ./worker/check-range.sh "<public-or-signed-url>"

It checks the 206, the `Content-Range`, that the body is the range and not
the whole file, that a mid-file slice is byte-identical to the same slice of
the whole download, and what the caching headers say. If it fails, serve the
clips from R2 or S3 instead — both do Range.

**A redirect is not a failure.** The first run of that script hit our own
key gate and got a 303; calling that "Range broken" would have been wrong in
the other direction, so it now says so explicitly.

**2. The free tier is too small to be the answer.** 1 GB storage is about
30 clips, the upload cap is 50 MB against clips of 20–40, and **a free
project pauses after a week of inactivity** — which for a tool used in
bursts is a silent outage. Budget for Pro.

**3. One job at a time, and it is not a UI limit.** Resolve is one GUI app
with one timeline. `claim_job` uses `for update skip locked` so two agents
cannot take the same row, and the lease (`lease_until`) is what returns a
job when a Mac crashes, sleeps or loses power — a flag in memory survives
none of those.

**4. A worker without Resolve must not claim a job that builds.** `caps.resolve`
is false when Resolve is closed. The original `claim_job` had
`(needs_resolve or true)` in its WHERE, which is true for every row — the
parameter did nothing, and a Mac with Resolve closed would claim a job,
spend the best part of an hour transcribing, and fail at the last stage.

---

## What this does NOT fix

The Mac still has to be awake, logged in, with Resolve open. Automatic login
is off and macOS updates reboot on their own schedule, so the agent stops
until someone logs in. `./service/status.sh` reports it; `service/README.md`
has the three ways out.
