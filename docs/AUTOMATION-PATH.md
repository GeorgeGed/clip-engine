# From one good edit to mass production

The question this answers: once a clip is built by hand in Resolve and it looks
right, how does that become forty clips a stream?

**Short answer: it does, but the Resolve timeline is not the thing you reuse.**
What you reuse is the set of numbers that timeline is made of. The hand edit's
job is to be a *measurement*, not a production line.

That's why `edit.json` exists. The hand edit tells us what the numbers should
be; the contract carries them; the renderers execute them. Nothing about the
look has to live inside a `.drp`.

---

## Why Resolve can't be the volume path

Not a licensing complaint — a throughput fact.

| | ffmpeg | Resolve |
|---|---|---|
| Processes | as many as the box allows | one instance |
| Driven by | a file | a GUI, scripted |
| Renders | parallel | serial queue |
| Headless | yes | no |
| Fails | with an exit code | with a dialog |

Forty clips a stream, daily, is a render-farm shape of problem. Resolve is a
one-at-a-time tool with a window open. Even with the Studio API driving it, the
queue is still one machine doing one job.

So the division is:

- **Resolve designs the look** and finishes hero clips.
- **ffmpeg produces the volume.**
- **FCPXML is the bridge** for anything a human will take over.

All three read the same `edit.json`. That's the whole trick.

---

## The three backends, and what each is actually for

**`engine/render_ffmpeg.py`** — the volume path. Reads `edit.json`, shells out,
writes an mp4. Headless, parallel, deterministic, no licence. This is what runs
on forty clips.

**`engine/fcpxml.py`** — emits an FCPXML timeline from the same `edit.json`.
Resolve imports it **in the Free edition**, no scripting API. Use it for client
deliverables and anything an editor will keep working on. Frame-exact rationals,
not decimal seconds. **Still unvalidated against a live install** — the first
thing worth doing once Resolve is up is importing one and eyeballing the cuts.

**`engine/resolve_driver.py`** — the scripting API. **Studio only.** Needed for
renders, grades and Fusion, never to build a timeline. Any Resolve MCP server is
a wrapper over this same API, so it inherits the same requirement: Studio, app
running, External Scripting set to Local.

Start with `python -m engine.resolve_driver doctor`. It reports what's missing
instead of dying on an import error.

---

## What to capture from the first hand edit

This is the part that determines whether automation is possible at all. Three
things transfer, two don't.

### Transfers: geometry

Read these straight off the Inspector and write them down.

- [ ] Facecam pane — zoom, X/Y position, crop, and what fraction of the frame it ends up as
- [ ] Content pane — same four
- [ ] **Seam y** — where the two panes meet, as a fraction of 1920
- [ ] Whether the facecam is sharpened, and by how much
- [ ] For L3: the crop anchor, and the source/destination rects of every HUD element put back

→ becomes `layout.split_ratio`, `layout.facecam_source`, `layout.hud_recomposite`

The seam is the one number three independent sources already agree on (0.418,
0.4422, and 0.44 in clip-autopilot's config). If the hand edit lands somewhere
else, that's interesting and worth keeping — don't round it to 0.42 to be tidy.

### Transfers: caption style

- [ ] Font file, exact weight
- [ ] Size in px at 1080×1920
- [ ] Fill colour, stroke colour, stroke width, shadow offset/blur/opacity
- [ ] Position y
- [ ] Words per card, and how long a card holds (~0.5s in both references)
- [ ] The one emphasis colour, and what triggers it

→ becomes `captions.*`. A caption style is eight numbers and a font. It does
not need Resolve to reproduce.

### Transfers: the effect stack

For every piece of visual punctuation:

- [ ] Which `effects[]` type it is — `shake`, `flash`, `glow`, `whip_pan`, `zoom_punch`, `rgb_split`
- [ ] Timestamp, duration, intensity, ease
- [ ] **What in the footage it punctuates** — the `motivation`. An effect with no motivation is decoration and the gate warns on it.

Flashes stay under 3/second and intensity 0.8. The gate rejects, not warns.
That's the WCAG threshold, and a juice layer is exactly where a
photosensitivity problem gets introduced by accident.

### Does not transfer: per-clip keyframing

A punch-in hand-keyframed to follow one specific movement can't be generated.
Two options, pick deliberately:

- Parameterise it — `punch` → `punch_to` with an `ease` is already in the
  contract, and covers a linear or eased push.
- Accept it as a hero-clip move and leave it out of the volume path.

What's fatal is doing it by hand, liking it, and then expecting the automatic
clips to have it.

### Does not transfer: Fusion macros with no ffmpeg equivalent

If the look depends on a Fusion comp, the volume path cannot match it. Either
build the ffmpeg equivalent, or route that genre through FCPXML and accept it's
not a volume format. Worth knowing *before* the look is signed off.

---

## The sequence

1. Install Resolve. Decide Free vs Studio — Free is enough for everything up to
   step 6.
2. `python -m engine.resolve_driver doctor`
3. Build one clip by hand. Take the time; this is the specification.
4. Fill in the checklist above.
5. Write those numbers into an `edit.json`, render it with ffmpeg, and **put the
   two side by side**. The gap between them is the real backlog.
6. Close the gap, then generate `edit.json` per clip from the detection output.
7. Studio only if renders or grades need driving from here.

Step 5 is the one that can't be skipped. Everything before it is opinion.

---

## Honest state

- ffmpeg renderer: built, 417 lines, never run against a hand-built reference.
- FCPXML emitter: built, never imported into Resolve.
- Resolve driver: built, never connected.
- `edit.json` schema and gates: 53 tests passing, exercised only on synthetic
  and reference-derived data.

Nothing here has rendered a clip George has approved. That's what step 5 fixes.
