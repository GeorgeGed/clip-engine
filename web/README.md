# Clip Factory — the pipeline as a website

    ./.venv/bin/python web/server.py      # http://127.0.0.1:8808

Paste a Twitch VOD, give it a rights basis, and it drives the existing
pipeline end to end:

    run.py   ingest / analyse / rank
    batch.py screen / prep / specs / build / report

## Why it is local, and why one job at a time

`build` drives DaVinci Resolve through a scripting API served on Resolve's
own GUI thread: one Resolve, one project, one timeline. Remotion's `public/`
is shared the same way. A single worker thread consumes the queue, which is
the honest model of that constraint rather than a limit imposed by the UI.

## What it does NOT hide

**The screen is the product.** Measured across this VOD's 50 candidate
windows, 10 are buildable — the rest are rejected mostly for DMCA muting at
20-55%. The site shows that as a table with a verdict and a reason per clip,
because a progress bar that emitted three clips out of fifty would be lying
about the yield.

**Rights are a required field.** `permission` is on every source and the
build refuses to start without one, so the form asks rather than defaults.

## Layout

    web/server.py          stdlib http.server — no framework, nothing to install
    web/static/index.html  one page
    web/static/app.js      polling, 1.5s
    web/static/app.css
    web/factory.db         SQLite job + stage state (gitignored)
    jobs/<job>/web/*.log   one log per stage, tee'd from the subprocess

Every stage is the same command a person would type. Nothing about the
editing is reimplemented here, so the site follows the pipeline for free.

## Not done yet

- No per-clip build picker: `build` currently builds everything `specs`
  kept. The screen table is read-only.
- No auth. It binds 127.0.0.1 and assumes the operator is at the machine.
- `cancel` terminates the running subprocess; Resolve may need a look after
  a cancelled `build`.
