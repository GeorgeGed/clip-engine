# The site

    ./start.sh              http://127.0.0.1:8808
    ./start.sh --public     the same site on a public https URL

`start.sh` runs two things: the site and the render agent. Ctrl-C stops both.

## Why the site and the renderer are the same machine

Resolve serves its scripting API on its own GUI thread, on this Mac, and
Remotion's `public/` is shared. Nothing can render anywhere else. **So
hosting a front end apart from the renderer buys nothing** — it would be a
page that says "worker offline" whenever this machine is asleep, which is
exactly when the product cannot work anyway.

A tunnel is therefore the whole of hosting, not a shortcut past it:

    brew install cloudflared     # once
    ./start.sh --public

That prints a `https://….trycloudflare.com` URL. No account, no deploy, no
environment variables. The URL changes each run; a named tunnel on a domain
you own is the same tool with one config file, when it is worth it.

When the pipeline does grow a cloud control plane, `worker/agent.py` already
speaks to one — see `worker/README.md`. The site here keeps working either
way, because both read the same `jobs/` directory.

## The three screens

**New project** — paste a Twitch VOD or the path of one already on this Mac
(`engine.ingest.fetch` adopts a local file instead of downloading it). A
Twitch link fills in its own channel, duration and title from Helix. A
rights basis is required; the build refuses to start without one.

**Clips** — every scored candidate, defaulting to the ones that can be cut.
Each card carries the score, the state (Rendered / Ready to cut / Refused)
and, when the screen had to cut into the region to make it buildable, the
window it chose. Refused clips are one chip away with their reason, because
a high score on a clip you cannot use is a tease.

**Editor** — the rendered clip plays, the transcript sits beside it with the
claim's own emphasis marked, and clicking a word jumps the video there. The
five fields review actually changes — in, out, booms, chat, hook — write
back to the spec, which `batch.py specs` will not overwrite.

## What is derived and cached

`web/views.py` makes the thumbnails, the per-clip transcript in cut time and
the candidate list, caching all of it under `jobs/<job>/ui/`. Nothing there
decides anything: the scores come from `ranked.json`, the verdicts from
`screened.json`, the words from the transcript the pipeline already wrote.
If a number on the page disagrees with the pipeline, this layer is wrong.

Thumbnails are warmed on a daemon thread the first time a project is opened.
Fifty frames is fifty ffmpeg calls, and generating them inside the requests
left the grid blank while they queued.

## One job at a time

A single worker thread, and the same rule in `worker/agent.py`. Resolve
cannot be driven concurrently and two VODs transcribing at once would fight
over the GPU. The queue is the constraint stated honestly rather than a
limit imposed by the interface.
