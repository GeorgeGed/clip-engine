# Getting Resolve into the loop

Run the diagnostic before anything else. It names what is missing instead of
dying on an import error:

```bash
PYTHONPATH=. ./.venv/bin/python -m engine.resolve_driver doctor
```

Current state on this machine: **Resolve is not installed.** Everything else in
the engine runs without it.

## What actually needs Studio, and what doesn't

| Job | Needs Studio? | How |
|---|---|---|
| Build a timeline from an edit | **No** | `engine/fcpxml.py` → File > Import > Timeline |
| Cut, retime, caption, render a deliverable | **No** | `engine/render_ffmpeg.py` |
| Drive Resolve from Claude / a script | **Yes** | `engine/resolve_driver.py`, or the MCP |
| Automated grading, Fusion titles, render queue | **Yes** | same |

Blackmagic moved the Python scripting API behind Studio in 21.1 — their release
notes say the free API was being used to unlock Studio features — and external
control was always Studio-only. Studio is a one-time $295.

So the FCPXML path is not a workaround you settle for. It is the path that does
not care which edition you own, and it keeps the edit reviewable as a file
before a timeline exists.

## Install order

1. **DaVinci Resolve** (Free is enough to import timelines) from
   blackmagicdesign.com. Studio if you want Claude driving it.
2. Open Resolve → **Preferences > System > General** → set
   **"External scripting using"** to **Local**. Nothing connects until this is set.
3. Re-run `doctor`. It should report the app, the API folder and the library.
4. Only then, the MCP server.

## The MCP server

`.mcp.json` in this repo points at one. Claude Code picks it up when the session
is rooted here, and will ask you to approve the server on first use.

Two community servers are worth knowing about. Both sit on the same Studio-only
scripting API, and both self-report their tool counts:

- `samuelgursky/davinci-resolve-mcp` — editing, media pool, render setup,
  markers, grading, Fusion, Fairlight. Tested against Resolve 20.x. This is
  what `.mcp.json` is wired to.
- `lordhoell/davinci-resolve-mcp` — claims full API coverage, 440+ tools,
  59 of them timeline editing.

Resolve Studio 21.1 also ships its own native MCP integration. If you are on
21.1 Studio, prefer that over a community server and drop `.mcp.json`.

## Where the MCP belongs in the pipeline

Not in timeline construction. The engine writes `edit.json`, gates it, and emits
either a rendered file or an FCPXML. The MCP's job starts after that:

- import the FCPXML and confirm it landed frame-accurate
- apply a grade or LUT across the timeline
- build Fusion titles for a client's brand treatment
- queue and run the render, then report back

That keeps a GUI app off the critical path for volume work, and uses it for the
things it is genuinely better at than ffmpeg.
