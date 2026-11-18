# Setting up the clip service on a new owner's accounts

**This file is written for Claude** (or any engineer) deploying the service onto the
client's own Cloudflare and Modal accounts. Follow it top to bottom. Every step says
how to check it worked. When you finish, the client owns everything and the person
who ran the setup has no remaining access.

## What gets deployed

| Piece | Where | What it does |
|---|---|---|
| Web app | Cloudflare Worker + D1 database (`webapp/`) | The client pastes VOD links, watches progress, and plays or downloads clips. Password login. |
| Clip storage | Cloudflare R2 bucket | Every rendered clip, its phone-size preview and its thumbnail |
| Pipeline | Modal app (`modal_app.py`) | Downloads the VOD, transcribes it on a GPU, ranks moments with Claude, writes titles, renders clips in parallel, uploads them to R2, and reports to the Worker |
| Notifications | Optional Hark webhook | The Worker pushes to the client's iPhone when a VOD is submitted, when Modal starts on it, when the clips are ready, and on failure |

```
phone/browser -> Worker (D1, R2) --POST /start--> Modal: run_job
                    ^                               |- transcribe (L4 GPU)
                    '-- /api/pipeline/* callbacks --'- build_clip x N (CPU) -> R2
```

The client pays for all of it: Cloudflare (Workers, D1 and R2; R2 has no egress fees),
Modal (per-second GPU and CPU), and Anthropic (about $1 of Claude per VOD).

## 0. What to ask the client for

Collect these before starting. Never paste them into chat logs, commits or files in
the repository. Pass them only as environment variables or through each CLI's secret
prompt.

1. **Cloudflare account ID.** Dashboard → any domain or Workers page → right sidebar.
2. **A Cloudflare API token for the setup.** Dashboard → My Profile → API Tokens →
   Create Token → "Edit Cloudflare Workers" template, then add **Account → D1 → Edit**
   and **Account → Workers R2 Storage → Edit**. Scope it to the client's account.
   You will delete it at the end.
3. **R2 S3 credentials for the pipeline.** Dashboard → R2 → Manage R2 API Tokens →
   Create API token → **Object Read & Write**, limited to the `clip-engine-clips` bucket.
   Create the bucket first (step 2). This gives an Access Key ID and a Secret Access
   Key. Those keys are the pipeline's long-term storage credentials and stay.
4. **A Modal token.** The client signs in at modal.com (a paid plan with GPU access),
   then goes to Settings → API Tokens → New Token. This gives a token ID and a token
   secret. You will revoke it at the end. The deployed app keeps running without it.
5. **An Anthropic API key** from console.anthropic.com. The pipeline keeps it.
6. **A password for the web app**, chosen by the client.
7. *(Optional)* **The Hark webhook URL** (`https://hark.fyi/hooks/whk_…`) for push
   notifications, with the Hark app signed in on the client's iPhone.
8. **The channels they have permission to clip.** For each: the Twitch login (the
   name in `twitch.tv/<login>`), how they hold the rights (`own` for their own
   channel, `explicit` for written permission, `license` or `partner`), and a
   one-line note on that permission.

## 1. Machine prerequisites

```bash
git clone <this repo> clip-engine && cd clip-engine
python3 -m pip install modal fastapi      # to deploy the Modal app
cd webapp && npm ci && cd ..              # wrangler is a dev dependency
# webapp/README.md is the reference for the web app's routes, secrets and API contract
export CLOUDFLARE_ACCOUNT_ID=...          # step 0.1
export CLOUDFLARE_API_TOKEN=...           # step 0.2
```

Check: `npx --prefix webapp wrangler whoami` names the client's account.

## 2. Storage and database (Cloudflare)

```bash
cd webapp
npx wrangler r2 bucket create clip-engine-clips
npx wrangler d1 create clip-engine          # prints a database_id
```

Put the `database_id` into `webapp/wrangler.toml` in place of
`REPLACE_WITH_D1_DATABASE_ID`. The bucket name there is already `clip-engine-clips`. Then create the tables:

```bash
npx wrangler d1 migrations apply clip-engine --remote
```

Now create the R2 API token from step 0.3, scoped to the `clip-engine-clips` bucket.

## 3. Channel files

Any public Twitch VOD can be submitted. A channel with no file in `channels/` uses
`channels/_default.json` (the house layout) with permission `operator`, meaning the
person who submits the link is responsible for having the right to clip it. A channel
file is only needed to give a streamer their own handle, facecam fallback or grade.
For each channel from step 0.8, create or edit `channels/<name>.json`. Use
`channels/fns.json` as the template. The fields that matter:

```json
{
 "name": "fns",                 // job folder prefix
 "twitch": ["gofns"],           // Twitch login(s) whose VODs this covers
 "handle": "FNS",               // how titles refer to the streamer
 "permission": "explicit",      // own | explicit | license | partner
 "permission_note": "Written permission from FNS, 2026-11-20",
 "cam": [1456, 818, 1920, 1080], // fallback facecam box if no face is detected
 "seam": 0.4, "chrome": 92, "fps": 60, "grade": { ... }, "arc": null
}
```

Commit the channel files. Modal deploys the code that is on disk.

## 4. The pipeline (Modal)

```bash
modal token set --token-id <id> --token-secret <secret>     # step 0.4
openssl rand -hex 32                                       # -> PIPELINE_TOKEN, keep it for step 5
modal secret create clip-engine \
  ANTHROPIC_API_KEY=... PIPELINE_TOKEN=... \
  R2_ACCOUNT_ID=$CLOUDFLARE_ACCOUNT_ID R2_ACCESS_KEY_ID=... \
  R2_SECRET_ACCESS_KEY=... R2_BUCKET=clip-engine-clips
modal deploy modal_app.py
```

`modal deploy` prints the URL of the `start` endpoint
(`https://<workspace>--clip-engine-start.modal.run`). That is `MODAL_START_URL`.

Check it refuses a bad token. This must print 401:

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST <MODAL_START_URL> \
  -H 'content-type: application/json' -d '{}'
```

The first deploy builds the image (CUDA, ffmpeg, Python packages), which takes several
minutes. The first transcription also downloads the Whisper large-v3 model, about
3 GB, into the `clip-engine-data` volume. Later jobs reuse it.

## 5. The web app (Cloudflare)

```bash
cd webapp
npx wrangler secret put APP_PASSWORD        # step 0.6
npx wrangler secret put SESSION_SECRET      # openssl rand -hex 32
npx wrangler secret put PIPELINE_TOKEN      # the SAME value as in step 4
npx wrangler secret put NOTIFY_WEBHOOK_URL  # optional, step 0.7 (the Hark webhook URL)
npx wrangler deploy                          # prints https://clip-engine.<subdomain>.workers.dev
```

Before deploying, edit `[vars]` in `webapp/wrangler.toml`: set `MODAL_START_URL` to the URL from step 4, and set `PUBLIC_URL` to the Worker's URL. The first `wrangler deploy` prints the `*.workers.dev` URL, so if you don't know it yet, deploy once, set `PUBLIC_URL`, and deploy again. A custom domain added under Workers → Settings → Domains works the same way.
The pipeline uses `PUBLIC_URL` to call back. If it is wrong, jobs run but never show
progress.

**Recommended:** put Cloudflare Access (Zero Trust → Access → Applications) in front of
the domain with the client's email, as a second lock on top of the password.

## 6. Smoke test

1. Open `PUBLIC_URL`, log in, submit a VOD from an allowlisted channel with 2 clips.
2. The job moves through download → transcribe → rank → title → render. For a 3-hour
   VOD expect about 10 minutes to download, 5–10 minutes to transcribe on the L4, about
   10 minutes to rank, then a few minutes per clip, run in parallel.
3. Both clips appear with previews. The download button returns a 1080×1920 mp4.
4. If a notification webhook is set, it receives `{"event":"job.done",...}`.
5. Submit a VOD from a channel that is *not* allowlisted. The job must fail with
   "not on the allowlist".

If something fails, the full log is in the Modal dashboard → Apps → clip-engine →
`run_job` / `build_clip`. Every intermediate file is on the `clip-engine-data`
volume under `jobs/<channel>-<vod>/`, including `specs/NN.log` for each clip's build.
Resubmitting the same VOD resumes from what is already there.

## 7. Hand-off: remove your own access

Do all of these, then tell the client which ones you did.

1. **Delete the setup Cloudflare API token** from step 0.2 (My Profile → API Tokens).
   The Worker does not need it.
2. **Revoke the Modal token** from step 0.4 (Modal → Settings → API Tokens), and delete
   `~/.modal.toml` on this machine. The deployed app keeps running.
3. Remove any Cloudflare or Modal membership or invite you were given.
4. Run `unset CLOUDFLARE_API_TOKEN CLOUDFLARE_ACCOUNT_ID` and `npx wrangler logout`.
   Clear shell history if any secret was typed on the command line.
5. Give the client the web app password, and suggest they change it with
   `wrangler secret put APP_PASSWORD`. Rotating `PIPELINE_TOKEN` means updating it in
   both places: the Modal secret and the Worker secret.
6. Keep nothing: no copies of the R2 keys, the Anthropic key or the pipeline token.

## Operating notes

- **Cost controls.** Each job renders `clips` clips, 10 by default, at most 30.
  Modal → Settings → Usage lets the client set a spending limit.
- **What each clip looks like.** The house style is clip 08 of `fns-2905408276`:
  a 0.40 split with the facecam on top, pop captions, a TikTok-style opening title
  with one coloured keyword and an emoji, and big-facecam stretches. Chat and story
  cards are off. `pipeline/core.py` `STYLE` sets it.
- **Titles** come from `engine/titler.py`. It writes five options per clip and the
  pipeline uses the one it rates best. All five are kept in `jobs/<job>/titles.json`
  on the volume.
- **Rights.** Only allowlisted channels get processed. Clips can show real viewers'
  messages only if chat is turned on. It's off by default.
