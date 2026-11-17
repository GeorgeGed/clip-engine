# Clip Engine web app (Cloudflare Worker)

The web half of the clip service. A client pastes Twitch VOD links, the Worker
records a job in D1 and asks the Modal pipeline to start it. The pipeline
downloads the VOD, picks the best moments, renders vertical 1080×1920 clips,
uploads them straight into R2, and reports progress, clips and completion back
to this Worker over HTTP. The app shows jobs with live progress and a grid of
finished clips that play inline and download at full resolution. When a job
finishes or fails, the Worker POSTs to an optional notification webhook.

Everything is one Worker: server-rendered HTML plus a little vanilla JS, a D1
database (`DB`) and an R2 bucket (`CLIPS`). No framework, no Pages project, no
runtime dependencies.

```
src/index.ts    router, job API, pipeline callbacks, notifications
src/auth.ts     signed session cookie
src/files.ts    R2 streaming with Range support and friendly download names
src/views.ts    HTML, CSS and the small client script
src/util.ts     VOD URL validation, ids, constant-time compare, formatting
migrations/     D1 schema
test/           vitest suite running inside the Workers runtime
```

## Configuration

| Name | Kind | Required | Purpose |
|---|---|---|---|
| `APP_PASSWORD` | secret | yes | The single shared password for the web app. |
| `SESSION_SECRET` | secret | yes | HMAC key for the session cookie. Any long random string. Changing it logs everyone out. |
| `PIPELINE_TOKEN` | secret | yes | Shared bearer token between the Worker and Modal, used in both directions. |
| `MODAL_START_URL` | var (or secret) | yes | The Modal web endpoint that starts a job. |
| `PUBLIC_URL` | var | yes | The app's base URL without a trailing slash, e.g. `https://clip-engine-webapp.acme.workers.dev`. Sent to Modal as `callback_base` and used in notification links. Falls back to the request's origin if unset. |
| `NOTIFY_WEBHOOK_URL` | secret | no | If set, receives a POST when a job finishes or fails. |
| `DB` | D1 binding | yes | Jobs, clips and the activity log. |
| `CLIPS` | R2 binding | yes | Rendered clips, previews and thumbnails, written by the pipeline. |

Vars live in `wrangler.toml`; secrets are set with `wrangler secret put`. A secret
with the same name as a var overrides it, so `MODAL_START_URL` can be either.

## Auth

`GET /login` shows a password form; `POST /login` checks `APP_PASSWORD` with a
constant-time compare and sets `ce_session`, an HMAC-SHA256 signed cookie
(`HttpOnly; Secure; SameSite=Lax`, 30 days). Every page, `/api/*` route and
`/files/*` requires it, except `/login` and `/api/pipeline/*`. Without a
session, pages redirect to `/login?next=…` and API routes return `401`.
`POST /logout` clears the cookie.

Pipeline callbacks instead require `Authorization: Bearer <PIPELINE_TOKEN>`
(constant-time compare); anything else gets `401 {"error":"Unauthorized"}`.

## API contract

All bodies are JSON. Errors are `{"error": "<message>"}` with a 4xx/5xx status.

### Job object

```json
{
  "id": "a3nkthur7u",
  "vod_url": "https://www.twitch.tv/videos/2905408276",
  "clips_wanted": 10,
  "status": "queued | running | done | failed",
  "stage": "render",
  "message": "Rendering clip 4 of 10",
  "progress": 0.62,
  "vod_title": "Ranked grind to Radiant, day 41",
  "channel": "tarik",
  "error": null,
  "created_at": "2026-11-17T14:45:08.064Z",
  "updated_at": "2026-11-17T14:47:10.120Z",
  "finished_at": null,
  "clip_count": 0
}
```

`id` is 10 random base32 characters (`a-z2-7`). `progress` is 0–1 or null.
Timestamps are ISO 8601 UTC.

### Browser API (session cookie)

**`POST /api/jobs`** `{"vod_url": string, "clips": number}`

- `vod_url` must be a Twitch VOD: `https://www.twitch.tv/videos/<digits>`, also
  without scheme or `www.`, on `m.twitch.tv`, with a trailing slash, or with a
  query string. It is stored and sent to Modal normalised to
  `https://www.twitch.tv/videos/<digits>`.
- `clips` is a whole number 1–30, default 10.
- Inserts the job, then POSTs to `MODAL_START_URL`:
  ```
  Authorization: Bearer <PIPELINE_TOKEN>
  Content-Type: application/json

  {"job_id": "a3nkthur7u", "vod_url": "https://www.twitch.tv/videos/2905408276", "clips": 10, "callback_base": "<PUBLIC_URL>"}
  ```
  Any 2xx counts as accepted. A non-2xx, a network error or a 20 s timeout
  marks the job `failed` with the reason in `error`.
- Returns `201` with the job object (in either state). A form-encoded post
  (no-JS fallback) gets a `303` to `/jobs/<id>` instead.

**`GET /api/jobs`** → `{"jobs": [Job, …]}`, newest first, 100 at most.

**`GET /api/jobs/:id`** → `{"job": Job, "clips": [Clip, …], "events": [Event, …]}`.
Clips are ordered by `n`; events are the last 50, oldest first.

**`POST /api/jobs/:id/retry`** re-dispatches a `failed` job: status back to
`queued`, error cleared, then the same Modal call as above. Returns the job;
`409` if the job is not failed.

**`DELETE /api/jobs/:id`** deletes the job, its clips, its events and every R2
object under `jobs/<id>/`. Returns `{"deleted": "<id>"}`.

**`GET /files/<key>`** streams an R2 object. Content type comes from the
object's metadata, else from the extension (`.mp4` → `video/mp4`, `.jpg`,
`.png`, `.webp` …). Single `Range: bytes=…` requests (`a-b`, `a-`, `-n`) get
`206` with `Content-Range`, unsatisfiable ones `416`, which is what iOS Safari
needs to play and seek video. `?download=1` adds
`Content-Disposition: attachment; filename="<title-slug>.mp4"`, using the
title of the clip that owns the key. `HEAD` is supported.

### Pipeline callbacks (`Authorization: Bearer <PIPELINE_TOKEN>`)

All return `{"ok": true}`, `404` for an unknown `job_id`, `400` for invalid fields.

**`POST /api/pipeline/progress`**

```json
{"job_id": "a3nkthur7u", "status": "running", "stage": "download", "message": "Downloading VOD", "progress": 0.1, "vod_title": "…", "channel": "…"}
```

Everything except `job_id` is optional. Omitted fields keep their value (send
`"progress": null` to clear the bar). Without `status`, a `queued` job becomes
`running`. A `stage` or `message` is also appended to the job's activity log.

**`POST /api/pipeline/clip`**

```json
{"job_id": "a3nkthur7u", "n": 3, "title": "He called the ace", "emoji": "🎯", "keyword": "ace", "subject": "…",
 "score": 0.81, "duration": 24.6, "vod_start": 7012.8,
 "video_key": "jobs/a3nkthur7u/03-he-called-the-ace.mp4",
 "preview_key": "jobs/a3nkthur7u/03-he-called-the-ace.preview.mp4",
 "thumb_key": "jobs/a3nkthur7u/03-he-called-the-ace.jpg"}
```

Upserts on `(job_id, n)`, so a retried callback replaces the clip instead of
duplicating it. `n` (integer) and `video_key` are required. Keys are R2 object
keys the pipeline has already uploaded; keep them under `jobs/<job_id>/` so
deleting a job removes them. `vod_start` is seconds into the VOD and becomes
the "Twitch @ h:mm:ss" link (`<vod_url>?t=1h2m3s`). The page plays
`preview_key` if set, else `video_key`, with `thumb_key` as the poster;
Download always serves `video_key`.

**`POST /api/pipeline/done`**

```json
{"job_id": "a3nkthur7u", "status": "done"}
{"job_id": "a3nkthur7u", "status": "failed", "error": "VOD is subscriber-only"}
```

Sets the final status, `finished_at` and (for `done`) progress 1. If
`NOTIFY_WEBHOOK_URL` is set and the status actually changed (a repeated
callback does not notify twice), it POSTs in the background:

```json
{"event": "job.done", "job_id": "a3nkthur7u", "vod_url": "https://www.twitch.tv/videos/2905408276",
 "vod_title": "…", "clips": 3, "url": "<PUBLIC_URL>/jobs/a3nkthur7u"}
```

`event` is `job.failed` on failure, with an `error` field added. Webhook
failures are logged and never fail the callback.

## Local development

```bash
cd webapp
npm install
cp .dev.vars.example .dev.vars        # set APP_PASSWORD, SESSION_SECRET, PIPELINE_TOKEN
npx wrangler d1 migrations apply clip-engine --local
npx wrangler dev                      # http://localhost:8787
```

Local D1 and R2 live in `.wrangler/state`. To point the app at a local Modal
stub, add `MODAL_START_URL=http://127.0.0.1:8799/start` and
`PUBLIC_URL=http://localhost:8787` to `.dev.vars`. To fake a pipeline run:

```bash
T='authorization: Bearer <PIPELINE_TOKEN>'; J='content-type: application/json'
npx wrangler r2 object put clip-engine-clips/jobs/<id>/01-test.mp4 --local --file test.mp4 --content-type video/mp4
curl -X POST localhost:8787/api/pipeline/progress -H "$T" -H "$J" -d '{"job_id":"<id>","stage":"render","message":"Rendering","progress":0.5}'
curl -X POST localhost:8787/api/pipeline/clip -H "$T" -H "$J" -d '{"job_id":"<id>","n":1,"title":"Test","emoji":"🔥","score":0.9,"duration":6,"vod_start":3723,"video_key":"jobs/<id>/01-test.mp4"}'
curl -X POST localhost:8787/api/pipeline/done -H "$T" -H "$J" -d '{"job_id":"<id>","status":"done"}'
```

Checks:

```bash
npm test                              # vitest inside workerd (Miniflare)
npx tsc --noEmit
npx wrangler deploy --dry-run
```

## Deploying to a fresh Cloudflare account

```bash
cd webapp
npm install
npx wrangler login

# 1. Create the database and paste the printed database_id into wrangler.toml
npx wrangler d1 create clip-engine

# 2. Create the bucket (name must match bucket_name in wrangler.toml)
npx wrangler r2 bucket create clip-engine-clips

# 3. Apply the schema
npx wrangler d1 migrations apply clip-engine --remote

# 4. Set secrets (each prompts for the value)
npx wrangler secret put APP_PASSWORD
npx wrangler secret put SESSION_SECRET      # e.g. openssl rand -hex 32
npx wrangler secret put PIPELINE_TOKEN      # same value goes into the Modal app
npx wrangler secret put NOTIFY_WEBHOOK_URL  # optional

# 5. Edit [vars] in wrangler.toml: PUBLIC_URL and MODAL_START_URL, then deploy
npx wrangler deploy
```

The first deploy prints the `*.workers.dev` URL. If you did not know it in
step 5, set `PUBLIC_URL` to it and deploy again. Using a custom domain instead
works the same way: add it in the dashboard (or a `routes` entry) and set
`PUBLIC_URL` to it.

The Modal side needs `PIPELINE_TOKEN` and must upload clips into the same R2
bucket (an R2 API token with write access to `clip-engine-clips`, using the S3
endpoint `https://<account_id>.r2.cloudflarestorage.com`).

Later schema changes: add a new file in `migrations/` and run
`wrangler d1 migrations apply clip-engine --remote` before `wrangler deploy`.
