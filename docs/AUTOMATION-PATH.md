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

## How you keep it right every time

Resolve cannot be the answer to this. It is a GUI; consistency comes from
measurement, and there are four layers of it. Three are mechanical. The fourth
isn't, and pretending otherwise is how a pipeline ships forty broken clips.

### 1. Gate the plan — `engine/gates.check`
Reads `edit.json` before a frame renders. Rejects genuine defects (a cut inside
a word, no rights basis, a flash rate above the WCAG threshold), warns on
taste. 53 tests. **Built.**

### 2. Measure the artifact — `engine/qc.check`
Reads the rendered mp4. This is the one that was missing, and it closes the
project's own rule: *never claim a clip was exported without reading the file
back.* A clip can pass the gate and still be broken, because nothing in an
`edit.json` guarantees ffmpeg did what it was told.

Measures canvas, fps, codecs, duration against the plan, integrated loudness,
true peak, loudness range, leading/trailing silence, black frames. 18 tests.
**Built this turn.**

Rejects a missing audio track, a wrong canvas, a clipping master, a render that
drifted from its plan. Warns on loudness outside the house band and on a clip
that opens on silence.

### 3. Regression against a golden master
Once the first hand edit is approved, keep it. Re-render its `edit.json` after
every renderer change and compare frames and audio against the approved
output. This is what stops clip 500 drifting from clip 1 — a renderer change
that quietly shifts the seam by 20px is invisible per-clip and obvious against
a golden master. **Not built — needs the hand edit first.**

### 4. Sampled human review
The editorial faults are not mechanisable. Measured, not assumed: five
approaches at detecting George's three boundary rules reached 4 of 6 twice,
with *different* errors each time. "Ends abruptly" is prosodic — it reads as a
complete sentence in text. So a fixed sample gets watched, and the review
produces rules, not vibes. Every rule in `AGENTS.md` came out of exactly that.

**What this buys you:** every clip is technically clean and on-style, and the
editorial faults are flagged advisory and caught by sampling. Not "perfect each
time" — that is not purchasable. "Never broken, and measurably close to the
reference" is, and it is the honest target.

---

## What the first QC run found

All 50 raw clips from FNS VOD 2905408276, measured. None rejected — they are
raw cuts, so only the container and audio checks apply.

| | 720p set | re-cut from 1080p |
|---|---|---|
| Resolution | 1280×720 | **1920×1080** |
| Integrated loudness | median −19.45 LUFS | unchanged (same audio) |
| In the house band (−16 to −10.5) | 0 of 50 | **0 of 50** |
| True peak | median −6.30 dBTP | unchanged |
| Loudness range | 1.50 to 14.00 LU | unchanged |
| Opens on ≥0.35s of silence | 13 of 50 | **13 of 50** |
| Over 100s | 13 of 50, max 166.4s | **13 of 50** |

**The source was 720p.** Fixed: the VOD was re-pulled at 1920×1080@60 (6.28 GB,
103 min) and all 50 re-cut. The two sets pair exactly — max duration delta
0.000s, max loudness delta 0.01 LU — so resolution is the only thing that
changed, and `ingest.fetch` now refuses sub-1080p source so it cannot recur.

**Everything is ~7 dB quiet.** Raw Twitch VOD audio sits around −19.5 LUFS
against a −12 house target. Every clip George has reviewed so far he reviewed
quiet. The headroom is there — median true peak −6.30 dBTP means a +7.5 dB lift
does not clip — so this is a normalisation step that simply isn't applied yet,
not a problem with the material.

**13 of 50 open on silence**, and the tail is worse than it first looked:

| clip | dead air at the open | length |
|---|---|---|
| 39 — SR missing out on Riot partnership | **17.63s** | 50.2s |
| 37 — teasing his own team's roster | 7.22s | — |
| 25 — rant against players complaining about unpaid money | 4.70s | — |
| 09 — joke outrage at LOUD signing Lev | 4.36s | — |

Clip 39 spends **35% of its runtime silent before anyone speaks.** Verified
directly against the file, not inferred: `silence_start: 0.04`,
`silence_end: 17.67`.

Worth separating from the boundary-rule work. This is *mechanically* detectable
from the audio, which is why five text-based attempts never saw it — they were
all reading the transcript, where dead air leaves no trace. It is not the same
fault as rule 2 ("include the prompt"); a clip can open on speech and still be
missing its prompt. But dead air at the in-point is its own defect, it is
larger than any of the three faults George caught by hand, and it now gets
caught deterministically.

**13 of 50 run over 100s.** The known out-point problem, now with a number on
it. Still no rule from George on where to stop.

---

## The source audio is 34% missing

Found while fixing in-points, and it outranks everything else here.

**35.8% of FNS VOD 2905408276's audio is absent** — not quiet, absent — across
**552 runs** totalling 2213s. Present at identical timestamps in independently
fetched 720p and 1080p renditions, so it is in the VOD on Twitch's side rather
than an artifact of either download.

Across the 50 clips cut from it:

| | |
|---|---|
| Median absent audio per clip | **31.9%** |
| Worst clip | **62.1%** (#37, 28.2s of 45.5s) |
| Over 25% absent | **35 of 50** |
| Over 10% absent | 45 of 50 |
| Entirely clean | **1 of 50** (#3) |
| QC rejects, all on absent audio at a clip edge | **13 of 50** |

**The detector nearly missed it.** An exact-zero test found nothing and
reported clean files, because after AAC the absent region decodes to about
−122 dBFS rather than literal zeros. Only the 16-bit WAV extraction has true
zeros. The working test is a dB floor at −90 dBFS, where the absent region is
100% below and speech — peaking at −4.1 dBFS in the same file — is 0.1% below.
That is the kind of bug that makes a QC pass worse than none: it would have
issued a confident all-clear.

**What it does not explain.** Clip 3 measures 0% absent, so its abrupt ending
is still prosodic. And it is not automatically fatal: clips 1, 4 and 8 measure
37%, 14% and 19% absent and George accepted all three, because the mutes mostly
land where nobody is talking. So it warns with a number and rejects only at a
clip's edge.

**Consequences for selection.** A muted region reads as "not loud" to Tier 1,
so it is never flagged — this caps recall, invisibly. It is also why the
transcript has gaps up to 29.5s, which is what Tier 3 reads.

### Why the in-point fix held on all 6

The job was to walk 13 in-points forward past dead air. Two corrections came
out of it:

The 0.35s threshold was a guess and it was wrong. Measured, leading silence
splits cleanly — 30 clips open on speech, 14 cluster at 0.24–0.63s (median
0.42s, the breath before a first word), then a **1.24s gap**, then 6 at 1.87s
and up. The gap is the threshold. Only 6 clips were ever defects; the other 7
had normal pre-roll.

Then the walk refused all 6, because the transcript cross-check found no
utterance at any target. That was right, for a reason I had not anticipated:
the silence is a mute, not a pause. Walking clip 39's in-point forward 17.33s
would have landed on the far side of a muted region, cutting the question off
the front and breaking rule 2 — the rule George gave explicitly. The
cross-check exists because `silencedetect` fires on any audio above the floor;
it was added to stop an in-point landing on a keyboard clack, and it caught
something worse.

The real fix for a clip spanning a mute is a segment cut through the middle,
keeping the speech either side. That is an edit, not a boundary move.

---

## Honest state

- ffmpeg renderer: built, 417 lines, never run against a hand-built reference.
- Render QC: built, 31 tests, run against 50 real clips.
- In-point walk: built, 20 tests; held on all 6 real candidates.
- FCPXML emitter: built, never imported into Resolve.
- Resolve driver: built, never connected.
- `edit.json` schema and gates: 53 tests passing, exercised only on synthetic
  and reference-derived data.

Nothing here has rendered a clip George has approved. That's what step 5 fixes.
