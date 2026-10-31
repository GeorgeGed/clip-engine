# Clip Engine — what we've learned so far

**These are observations, not laws.** Most come from two reference clips George
supplied. Where something is measured, the number is given. Where it's one
creator's habit, it says so. Confidence grows as references accumulate — it does
not start high.

Only a small set of things are enforced in `engine/gates.py`, and those are
genuine defects (clipping audio, cuts inside a word, captions under the platform
UI, missing rights), never matters of taste. Tagged **[checked]** below.

## What you produce

One `edit.json` validated against `schema/edit.schema.json`. A renderer executes
it. You decide the edit; you don't push pixels.

That split exists so the edit is reviewable before a frame renders, diffable,
and portable between ffmpeg and Resolve.

## Never

- Never render before running `engine.gates.check` and reading the result.
- Never ship after rendering without running `engine.qc.check` on the file.
  Gates judge the plan; QC judges the artifact. Passing one says nothing
  about the other.
- Never invent a timestamp. Every in/out traces to a detector output or a word
  timestamp.
- Never build a claim from non-contiguous speech. **[checked]**
- Never guess a speaker. Uncertain attribution holds. **[checked]**
- Never identify a person from appearance alone. **[checked]**
- Never ship a source without a rights basis. **[checked]**
- Never silently sanitise a master. Mask the caption track; leave the audio.
- Never claim a clip was exported without reading the file back. `engine.qc.check` is how you read it back. **[checked]**

---

## The references

| | **R1** | **R2** |
|---|---|---|
| | CS2, renyan, "cheater banned" | VALORANT, Polymarket bracket |
| Duration | **80.3s** | **20.2s** |
| Cuts | 8 (6.0/min, mean shot 8.9s) | **0** |
| Speech coverage | **50%** | **96%** |
| Speech rate | 119 wpm | **256 wpm** |
| Loudness | **−11.79 LUFS**, +1.25 dBTP | **−14.26 LUFS**, −0.44 dBTP |
| Loudness range | 13.70 LU | **1.30 LU** |
| Seam | **0.418** | **0.4422** |
| Captions | white + heavy stroke, y≈0.44 | white on blue box, y≈0.747 |

Both are vertical, both are facecam-over-content, both use word-level captions.
Almost everything else differs — which tells you which choices are structural
and which are taste.

---

## Three genres

**frag** — tension → release. Few cuts, speech only when it matters.
**take** — a claim delivered fast. R2: no cuts at all, 96% speech, flat audio.
**receipts** — a case argued with evidence. R1: half the runtime is deliberate
silence while the exhibit plays.

The receipts clip is the one my earlier drafts missed entirely, and it's the
format most of George's material fits.

### Receipts clips, specifically
R1 held **seven silent stretches of 3.2–9.1s**. That silence is the chat log,
the scoreboard, the Steam profile, the Match Cancelled banner. **Trimming it
destroys the format.** Any "remove dead air" instinct is wrong here. **[checked
— a receipts clip over 85% speech warns]**

Act shape that worked: hook → accusation → exhibit → escalation → exhibit →
attempt → **failure** → despair → turn → payoff → one-line button. The failure
act does the real work; without it the payoff means nothing.

---

## One clip = one narrative

**The rule George gave after reviewing the first 29 clips, and the one that
matters most.** A clip is about ONE thing, titleable in one line. When the
speaker pivots from one subject to another, that pivot is a **boundary**, not
something to clip across.

A region usually holds two or three separate topics. Return them as separate
clips, each with its own in-point and out-point. Never one clip spanning a
topic change, however good both halves are — a viewer who came for the first
subject leaves when it becomes the second.

**The case that taught it.** Clip 3 of the first delivery ran 0:36:17–0:37:11:

```
0:36:17  "Sentinels has reached an agreement..."        <- a transfer story
0:36:23  "...tech issues we'll probably see             <- PIVOT
          in the new circuit"
0:36:34  "these open qualifiers are gonna be an         <- the actual clip
          absolute shit show" ... ping, cheaters,
          no Riot tech support, delays, controversy
```

Six seconds of one story, then a rant about something else. With the rule
applied, Tier 3 returns the rant alone at 0:36:34–0:37:11, 37s instead of 54s,
and drops the transfer fragment because six seconds cannot carry a clip.

**The test:** if describing the clip needs the words "and then he talks about",
it is two clips.

Note this is NOT the same problem as over-long clips. Measured on the first 29:
clips over 100s had *higher* mean strength (0.57) than clips under 70s (0.50).
Length and multi-narrative are separate defects and need separate fixes.

## The out-point off-by-one — SOLVED, and it was mechanical

**This was misdiagnosed for several turns as an editorial problem. It was a
bug.** Read this before trusting anything below about rule 1.

Out-points were snapped to utterance **starts**, so every clip stopped just
*before* the line it named. Measured on the reviewed top 10: **all ten**
out-points landed exactly on an utterance start, so all ten dropped their final
line. Usually survivable — George accepted 7 of them. On clip 8 the dropped
line was *"You sacrifice a lot of time and you could just end up with
nothing"*, the whole point of the clip, and his note was "clip ended too
early".

**Clip 3 proves it was the model's intent, not its mistake.** Clip 3's stated
`consequence` is *"They've had a very successful year... you can't just
leave"* — quoting verbatim the line the cut excluded. The model meant to
include it. The pipeline threw it away.

The root cause is that the prompt asked for something the data could not
express: it said "the out-point lands where a sentence ENDS" while the
transcript carried only `start` timestamps. There was no end to name.

Fixed in `engine/tier3.py`:
- transcript lines render as `[start-end]`, and the contract says in_point is
  the START of the first included utterance, out_point the END of the last;
- `_ends()` reports whether ends are **real** (from `transcribe.py`) or
  **derived** (the next start);
- `_snap_out()` snaps to ends. With real ends the value is unambiguous. With
  derived ends a start and the preceding end are the same instant, so policy
  breaks the tie toward **including** the named line — over-including by one
  line is recoverable, losing the payoff is not.

**Use `transcribe.py` for future VODs**, which keeps real word-level ends. The
`small`-model run that produced `jobs/fns-2905408276` stored only starts, which
is why that job needs the tie-break. 14 tests in `tests/test_tier3.py`.

**Correction to what follows.** I argued repeatedly that clip 3's abrupt ending
was *prosodic* — that it read as a complete sentence in text and so could not
be detected. That was wrong. It was this off-by-one, and it is fully mechanical.
Rule 1 did not need a model to enforce it; it needed an end timestamp.

### Applying it to all 50

| | |
|---|---|
| Extended to keep the named line | **37 clips, +95.4s of speech recovered** |
| Trimmed back to where audio stops | 10 clips, −11.4s |
| Unchanged | 3 clips |
| QC rejects | **7 of 50**, down from 13 |

Three cases, and the third only became visible after the second was wrong:

1. **No mute in the span** → extend to the next utterance start. Recovers the line.
2. **Mute starts inside the span** → clamp to 0.15s before it. Keeps the audible
   part. Cutting exactly on the boundary leaves a few frames of mute in the tail.
3. **The named line sits inside a mute** → it has no audio to recover, so pull
   the out-point BACK to where audible speech stops. Leaving it put ends the
   clip on a mute boundary, which reads as absent audio.

**Test mute overlap, not containment.** The first version only looked for mutes
*starting* after the out-point. Clip 7's began 0.12s earlier, so it was skipped
and the clip gained 11.7s of absent audio in the middle of the line it was
supposed to recover. Five clips were affected; the overlap test fixed all five.

Known limit: `muted_regions.json` keeps runs ≥1.0s, so sub-second mutes are
invisible to the clamp — clip 21 ended on a 0.9s one. Measuring the cut file
with `qc.dead_audio(min_run=0.3)` catches what the map misses, which is the
right habit: **the map is a planning aid, the file is the truth.**

Of the 7 remaining rejects, **6 open on absent audio** — the in-point mute
problem, which is separate and still unsolved.

### Fixing an opening that sits on a mute

Six clips opened on absent audio. Moving the in-point is safe here in a way the
earlier blind walk was not: the span skipped is *known absent*, so nothing
audible is lost. (The earlier attempt trusted `silencedetect` and would have
stepped over a mute onto the answer, cutting the question off the front.)

**Landing on the mute's edge is not enough.** In all six the shape was: mute
ends, then **3–8s of ordinary quiet**, then speech. Stopping at the mute's edge
only trades absent audio for silence. The in-point goes to the first
transcribed utterance at or after the absent span, less the natural 0.3s
pre-roll.

**Measure the clip, not the map.** `muted_regions.json` keeps runs ≥1.0s, so
clip 29's 0.6s opening run was invisible to it. Re-measuring the file with
`qc.dead_audio(min_run=0.3)` caught it.

Result: 5 moved, 1 already fixed, **45.0s of dead opening removed, all 5 pass
QC**.

**But passing QC is not the same as being watchable.** What a mute eats is
whatever was SAID inside it, and if that was the clip's setup then the clip now
opens mid-thought. That is rule 3, and no measurement settles it — so every
move prints its first words for review. On these six:

| clip | opens with | verdict |
|---|---|---|
| 04 | "K drill is the only one that I watched for League of Legends…" | matches its subject |
| 37 | "We're all everyone that is on my team currently streams" | matches its subject |
| 25 | "All free food problem is a lot of these people are grown ass men" | gist lands, whisper garbled |
| 29 | "I got to start figuring out what… things other teams…" | **drifted** — the announcement its subject names was inside the mute |
| 13 | "Yeah, wait" / "human is seamless" / "Say it ain't so mummy" | **incoherent — drop it** |

Clip 13 is the clean illustration that a mechanical in-point fix cannot rescue
a clip whose setup was muted. It measures fine and is unwatchable.

## Three rules from review

**Status: rule 1 is now enforced (above). Rules 2 and 3 remain unenforced.**
Three approaches were tried against the three clips George flagged, and all
three failed — but note that the clip-3 case they kept failing on was a bug,
not an editorial judgement, which is part of why they failed:

| approach | result |
|---|---|
| put the rules in the Tier 3 prompt | applied 1 of 3 |
| text heuristics (punctuation, question detection) | caught 0 of 3 — whisper punctuates only 38% of utterances, and a "prompt" is often a statement, not a question |
| pause length after the out-point | does not separate good from bad: a correct out-point had a 0.46s pause, a flagged one 0.60s |

So these are editorial standards a human still has to check. Do not report a
clip as boundary-clean on the strength of `engine/boundaries.py` — it returns
"inconclusive" far more often than it returns an answer, by design.

Next thing to try: a narrow VERIFICATION pass — show the model one finished
clip's transcript and ask the single question "does this end mid-sentence?"
rather than carrying the rule through generation alongside everything else.

From George reviewing the v2 top 10. Each one came from a specific broken clip.

**1. Finish the sentence.** The out-point lands where a sentence ends, never
mid-clause. *Clip 3 ended on "...you can't just" and stopped.* An abrupt stop
reads as a broken file, not a stylistic choice.

**2. Include the prompt.** When the clip is a response, start at the question,
not the answer. *Clip 6 opened mid-rant; the co-host line that triggered it sat
one utterance earlier at 0:36:23.* A question and its answer are ONE narrative.

This refines the one-narrative rule: **the pivot sentence belongs to the NEW
topic.** When a speaker turns from one subject to another mid-sentence, that
line is the next clip's setup, not the previous clip's tail.

**3. The clip must explain itself.** Every person or team referenced has to be
identifiable from inside the clip. *Clip 5 opened mid-comparison on a name the
viewer had never been introduced to — George's note was "not really too sure
what it's referring to, no real substance".* The test: could someone who joined
at the in-point follow it? If not, move the in-point back or drop the clip.

## Finding the in-point

Anchor on the LAST event and walk backwards to the first irreversible
commitment. Never a fixed offset — that imports dead air and buries the hook.

| Moment | In-point |
|---|---|
| ace | first kill of the streak − 1.5s |
| 4k / 3k / 2k | first kill − 1.2 / 1.0 / 1.0s |
| 1vX clutch | the frame the player becomes last alive |
| flick | the shot − 1.2s |
| take | the first word of the SETUP, never the claim |
| receipts | the first word of the accusation |

If the clip runs long, trim from the FRONT. The payoff is at the end.

**Leading silence: natural pre-roll is 0.24–0.63s.** Measured across 50 clips —
30 open on speech at 0.00s, 14 cluster at 0.24–0.63s (median **0.42s**, the
breath before a first word), then a **1.24s gap**, then 6 at 1.87s and above,
which is dead air. The threshold is that gap: `LEAD_SILENCE_DEFECT_S = 1.0`.
An earlier 0.35s guess flagged 13 clips and was wrong about 7 of them.
**[checked]**

`boundaries.walk_in_point_to_speech` moves an in-point forward past dead air,
leaving 0.3s before speech. It only ever moves FORWARD, so it cannot pull in a
new topic at the front. **Always cross-check with `boundaries.speech_near`**:
`silencedetect` fires on any audio above the floor, so without it an in-point
lands on a keyboard clack — or, as happened on all 6 flagged clips here, on the
far side of a muted region, which would have cut the prompt off the front and
broken rule 2.

**Duration is set by the content, not the clock.** The references are 20s and
80s. The gate warns outside a genre's typical window and rejects only beyond
5–180s. **[checked]**

---

## Cutting

R1 cut **once per 8.9s**, and every cut landed a median **0.36s** from a
sentence boundary. R2 never cut at all.

**Cut when the point changes, not to a beat.** No jump cuts to kill pauses, no
cutting on music. If you're cutting mid-sentence you're following a rhythm the
format doesn't have.

For frag clips specifically: first-person footage is spatially continuous, so a
hard cut costs more than the dead air it removes. Cover removals with a speed
ramp or punch-in. **[checked]** One slow-mo per clip, on the payoff. **[checked]**

Take/receipts cuts land on word boundaries from the transcript. **[checked]**

---

## Framing

VALORANT and CS2 HUDs live at the frame edges — minimap top-left, timer
top-centre, **killfeed top-right**, abilities bottom-left.

- **L1 blurred pillar** — full 16:9 over a blurred copy. Use when the killfeed
  or minimap carries meaning, and for broadcast footage.
- **L2 split** — facecam above, content below. **Seam at 0.42 (measured 0.418
  and 0.4422 in the two references; George's clip-autopilot independently had
  0.44).** This is the most solid number we have. No facecam → falls back to
  L1. **[checked]** A "face" under 2% of frame is a HUD portrait. **[checked]**
- **L3 crop-to-fill + HUD re-composite** — crop 9:16, then overlay the killfeed
  and spike timer back. A 9:16 window out of 16:9 keeps full height and crops
  horizontally, so the killfeed is lost to the *side*; a vertical anchor does
  nothing unless you also punch in.

**The lower pane is not a gameplay slot.** R1 ran gameplay, a scoreboard, a
Steam profile, a stats card, a chat log, the report dialog and a banner through
it. R2 held one static bracket for the whole clip. It's a document viewer.

Safe area at 1080×1920: top 150px, bottom 320px. **[checked]**

---

## Driving Resolve

Studio, running, External Scripting = Local. `python -m engine.resolve_driver
doctor` reports exactly what is missing. No MCP server is needed — any such
server wraps this same Python API, so it inherits the same requirements.

**Four conventions, every one measured after a wrong-looking frame.** They are
in `engine/resolve_layout.py`; the reasoning is here so it is not re-derived.

1. **`recordFrame` is absolute.** A timeline starts at 01:00:00:00 = **216000**
   at 60fps. `AppendToTimeline(..., recordFrame=0)` puts the clip an hour
   before the start. `GetItemListInTrack` still lists it, so the failure is
   silent — the tell is `GetStartFrame() == GetEndFrame()` and a black render.
   Pass `timeline.GetStartFrame()`.
2. **Crop is in fitted-display pixels, not source pixels.** A 1920×1080 source
   in a 1080×1920 timeline fits to 1080×607.5 and crop clamps there: set
   `CropLeft=1456` and it reads back `1080`. Multiply by the fit factor.
3. **Zoom is relative to the fitted size and scales about the CANVAS centre**,
   not the image centre.
4. **Pan and Tilt do not share a scale.** Measured: Pan moves **1.000** canvas
   px per unit; Tilt moves **0.3164**, which is `fitted_h / canvas_h`, and the
   Tilt rate is **independent of zoom** (300 units moved 95px at both zoom 1
   and zoom 2, linear to 600). A vertical move needs a ×3.1605 conversion a
   horizontal one does not. Get it wrong and the panes come out the right size
   in the wrong place, which looks like a sign error and is not.
   **+Pan is right, +Tilt is up.**

`AppendToTimeline` also ignores `trackIndex` across separate calls — pass every
entry in ONE call. Give the second copy `mediaType: 1` (video only) or the
audio doubles.

**Verify with a still, not with the maths.** `timeline.GrabStill()` then
`album.ExportStills(...)` writes a PNG of the actual program output. Measure it
— `ffmpeg -vf scale=216:384 -pix_fmt gray -f rawvideo -` and scan for the
non-black box gives position to 5px with no numpy. Two grabs pinned convention
4 after the arithmetic had looked right three times. After rebuilding a
timeline, `SetCurrentTimecode` lands on the timeline END the first time; call
it twice.

### Captions in Resolve

**The subtitle track and Auto Captions cannot be styled from Python. At all.**
Font, size, colour, stroke and position are unreachable — confirmed by three
independent passes over the 3525-line API stub plus a direct grep: there is no
text-style property anywhere, and `TimelineItemProperties` is transform/crop
only. You can create a subtitle track, put per-word timed text on it with
`SetTranscription`, and burn it in at render — and it will look like Resolve's
default subtitle. That is not the house style, so captions go through Fusion.

**Fusion Text+ is the only styled path, and these four facts make it work:**

1. **`StyledText` does not keyframe.** Three writes at three times leave one
   static value, the last one. Numeric inputs (`Size`) do not keyframe either.
2. **`StyledText` DOES accept a Fusion expression**, evaluated per frame. This
   is the whole trick: `tool.StyledText.SetExpression('iif(time >= 0 and time
   < 30, "WORD", …)')`. Verified switching on exact frame boundaries.
3. **A title is 300 frames and there is no `SetDuration`.** So one Text+ per
   300-frame window, chained — 14 for a 67s clip at 60fps, ~10 cards each.
4. **`InsertFusionTitleIntoTimeline` always lands on V1 and RIPPLES every
   unlocked track**, shoving existing clips right by 300. Locking V1 to stop
   that makes the insert fail outright and return None.

So the build order is **captions first, video second**: insert each title
while V1 is still empty, with V3 LOCKED across the insert (otherwise each new
title shoves the already-placed ones right — the first run left 1 title of 14,
sitting at frame 3900), then `SetPosition({'trackIndex': 3, 'startFrame': …})`
and unlock. Append the video to V1/V2 afterwards.

Other traps:
- **Shading element 2 is the outline, and its inputs are `None` until
  `Enabled2 = 1`.** Only then do Red2/Green2/Blue2/Thickness2/ElementShape2
  exist. Element 1 is the fill, named "White Solid Fill"; element 2 is named
  "Red Outline" and is off by default.
- **Fusion's `Center` y is measured from the BOTTOM.** A caption at y 0.44
  from the top is `Center = {1: 0.5, 2: 0.56, 3: 0.0}`.
- **Stroke 0.14, not 0.30.** At 0.30 the outline merges into a solid slab and
  the letterforms disappear. 0.14 follows the glyphs and still reads over
  anything.
- `timelinePlaybackFrameRate` is **not settable from Python** — not as a
  string, a float, at project or timeline level, nor on a fresh empty project.
  A 60fps timeline left at the default 24 plays at 0.4x in the viewer. It is a
  monitoring setting and does not affect the render, but it must be fixed by
  hand in Project Settings before anyone reviews the edit.

**Measured on clip 8:** 196 words → **117 cards**, median 0.46s, **1.74
cards/second** — the reference cadence is "roughly twice a second", so the
grouping rule (≤3 words, ≤0.55s, break on a 0.6s gap) lands in the right place
without tuning.

**Fonts.** The repo's `fonts/LuckiestGuy-Regular.ttf` is NOT installed, so
Fusion cannot address it by name. George's machine already has **Tungsten
Black/Bold**, Proxima Nova Extrabold and Compacta — Tungsten is a broadcast
sports face and is what the reference build uses. Install a font to
`~/Library/Fonts` before naming it in `Style.font`.

### Cuts on a take clip, and why clip 8 gets PICTURE cuts only

**Every long pause in clip 8 is a Twitch mute sitting mid-sentence.** Six
inter-word gaps exceed 0.8s and all six coincide with absent audio, splitting
a sentence each time: *"was never kind"* [1.25s gone] *"to job stability"*,
*"it's"* [1.31s] *"hard as"*, *"but"* [2.24s] *"the thing is"*. Removing any of
them joins speech across content nobody can hear — exactly what the
non-contiguous speech gate rejects. **This clip has no safe audio cuts.**

So the audio runs unbroken and only the FRAME cuts: shots change on a pause,
the viewer reads it as cutting, and nothing is spliced. Because no time is
removed, caption timings need no remapping either.

`engine/cuts.py` picks cut points as the midpoints of the widest inter-word
gaps, spaced at least `MIN_SHOT` apart. Measured on clip 8:

| min shot | cuts | shots | mean shot | cuts/min |
|---|---|---|---|---|
| 4.0s | **5** | 6 | 11.2s | 4.5 |
| 5.0s | 4 | 5 | 13.4s | 3.6 |

R1 ran 8.9s mean and 6.0 cuts/min, so even the loosest setting is slower than
the frag reference — the material is 175 wpm with almost no real pauses. Note
R2, the *take* reference, cut **zero** times. Five picture cuts is already
more aggressive than the closest reference, not less.

**Watch out: whisper's VAD merges utterances.** Clip 8 came back as 12
utterances each ending exactly where the next starts, so utterance boundaries
are useless for finding pauses. Use WORD gaps.

**Built and verified.** 5 cuts at 8.09 / 19.23 / 33.84 / 38.39 / 55.31s, six
shots, each with its own framing from the inset cycle `(0.0, 0.10, 0.04, 0.14,
0.06)` — biased upward (`dy*0.6` top, `dy*1.4` bottom) because the face sits
above the box centre. Sampling one frame per shot out of the RENDER confirms
six visibly different framings.

The facecam copies are `mediaType: 1` (video only) and the audio rides the
unbroken content clip, so the picture cuts cost nothing in contiguity.

**The lower pane never moves.** All the motion is in the top 42% of frame;
the document pane holds one framing for the whole clip. That is the next lever
if it still reads static, and it is a deliberate choice rather than an
oversight — punching a text document around is usually worse than holding it.

### Resolve can wedge

Two probes hung with no output at all, and `ps` showed Resolve at 90–105% CPU
in state R — busy, not deadlocked. The scripting API is served on the GUI
thread, so a long operation blocks every call, and a `SIGALRM` watchdog does
NOT help: the hang is inside `fusionscript.so`, a C extension that never
yields to Python signals. Budget a real subprocess timeout instead, leave the
app on the Edit page rather than Color when scripting, and avoid invalid
timecodes (`01:00:60:00` is not a time and appeared to start the trouble).

### Grading and loudness

**`TimelineItem.SetCDL` is the grading API**, and it works:
`{'NodeIndex': '1', 'Slope': 'r g b', 'Offset': 'r g b', 'Power': 'r g b',
'Saturation': 's'}` — ASC CDL, `out = (in * Slope + Offset) ^ Power`. Values
are space-separated strings, not floats. The house lift for flat Twitch H.264
is Slope 1.06, Offset −0.012, Power 1.06, Saturation 1.18. **Grade the facecam
only** — the lower pane is a document, and lifting contrast there costs text
legibility for no gain.

**Numeric Fusion inputs take expressions too.** Only keyframes are refused. So
`Red1`/`Green1`/`Blue1` can carry the same per-card `iif` chain as
`StyledText`, which is how one Text+ gives some cards the accent colour and
leaves the rest white — "one emphasis colour per card", driven from data.

**Emphasis is keyed off the model's own `claim` and `consequence`**, not a
hand-written list: content words ≥5 chars, minus stopwords. On clip 8 that
marked **16 of 117 cards (14%)** and they were the right ones — "WORSE FOR THE
SCENE", "ARE BLOWING IT / OUT OF PROPORTION", "EXCEPTIONAL", "UP WITH
NOTHING". It needs no tuning per clip because the claim is already the point
of the clip.

**Loudness is finished AFTER the render, in ffmpeg, not in Resolve.**
`Timeline.NormalizeAudioLevel` exists and offers ITU-R BS.1770-4 and EBU R128,
but it only applies gain — it does not limit. Clip 8 sat at −20.12 LUFS with a
−6.37 dBTP peak, so the +8 dB to reach −12 would have hit **+1.6 dBTP** and
clipped straight through the hard ceiling. Two-pass `loudnorm`
(`render_ffmpeg._finish_audio`) applies gain AND true-peak limiting in one
pass: measured result **−12.50 LUFS, −0.74 dBTP**, 5 seconds for a 67s clip.

### The clip 8 reference build

Project `fns-clip08-reference`, timeline `clip08-L2`, 1080×1920 @ 60.

| | |
|---|---|
| Facecam in source | **x 1456–1920, y 818–1080** (464×262, 16:9, 5.9% of frame) |
| Seam | **0.42 → 806.4px** |
| Facecam pane | zoom 5.472, pan −2240.7, tilt +5738.3 |
| Content pane | zoom 2.004, pan 0, tilt −1110.4, chrome cropped 92px |

**Crop the browser chrome.** 92 source px removes the tab and address bars,
which otherwise sit right under the seam and read as a mistake.

The facecam is a 3× upscale of a 464px-wide region, so it is soft. That is what
the source gives; a bigger facecam on stream would be the only fix.

## Captions

Word-level, 1–3 words, in both references. Changing roughly twice a second.

**Placement has no fixed value.** R1 rides the seam at ~0.44; R2 sits at 0.747,
in the gap between bracket columns. Both are L2, both are correct. The rule is
**put the caption where the content isn't** — the gate checks the safe area and
the killfeed, and otherwise leaves your placement alone. **[checked]**

Phrase-level is for when the written sentence is the product (quote cards).
Word-level is for when the voice carries the claim and the captions carry
rhythm. I argued the opposite before seeing R2; R2 was right.

One emphasis colour per card. R1 used white with yellow/red/orange accents;
R2 used white on a blue box. Pick one system and keep it.

Preserve handle casing, acronyms, map names. **Leviatán, not Leviathan.**
Whisper garbles these constantly — "paper X" for PRX, "Hanz" for Hent.

Profanity: mask the caption (`F***ING`), leave the audio.

---

## Audio

| | |
|---|---|
| Loudness | **−12 LUFS** house default (references: −14.26 and −11.79) |
| True peak | **−1.0 dBTP**, hard. R1 clips at +1.25 — do not copy that **[checked]** |
| Duck under speech | 7 dB, 120ms attack, 400ms release |
| Music | **neither reference has a bed.** Don't add one by default |

Dynamics are a genre choice: R1 swings 13.7 LU between mutter and shout; R2 is
flat at 1.3 LU because it never stops talking. Match the dial to the format.

Use two-pass loudnorm. Single-pass lands a dB off.

**Raw VOD audio is ~7 dB under target.** Measured across 50 clips from FNS VOD
2905408276: median −19.45 LUFS, and **0 of 50** inside the −16 to −10.5 band.
Median true peak was −6.30 dBTP, so the lift to −12 has headroom and will not
clip. Normalisation is not optional polish; without it every clip ships quiet.

**Check the source audio is actually there.** Measured on FNS VOD
2905408276: **35.8% of the audio is absent** — not quiet, *absent* — across
**552 runs**. Present at identical timestamps in independently fetched 720p and
1080p renditions, so it is in the VOD on Twitch's side, not a download
artifact. `engine.qc.dead_audio` detects it. **[checked]**

The test is a **dB floor (−90 dBFS), not equality with zero.** After AAC the
absent region decodes to about −122 dBFS while speech in the same file peaks at
−4.1 dBFS, so the separation is enormous — but an exact-zero test finds nothing
and reports a clean file. Only the WAV extraction, quantised to 16-bit, has
literal zeros.

What it does and does not explain:

- It explains the transcript's gaps (up to 29.5s), and it caps Tier 1 recall:
  a muted region reads as "not loud" and is never flagged.
- It explains the clips that open or end on nothing — 49 of 50 contain some
  absent audio, 31 of 50 over 25%.
- **It does not explain clip 3's abrupt ending.** That clip measures 0% absent.
  The prosodic conclusion stands; do not re-attribute it to this.
- It is not automatically fatal. George accepted clips 1, 4 and 8, which
  measure 37%, 14% and 19% absent. The mutes mostly land where nobody is
  talking. Treat it as a warning with a number, not a reject, except at a
  clip's edges.

**Pull 1080p source and verify you got it.** The first FNS run used an ad-hoc
`yt-dlp` call that landed 720p60, and all 50 clips were cut from it before
anyone measured the files. A 1080×1920 master built from 720p is upscaled, and
the cost is invisible until the look has already been tuned against soft
footage. `ingest.fetch` now refuses source under `MIN_SOURCE_HEIGHT` (1080),
with a `min_height=None` opt-out for a Twitch clip or old VOD that genuinely
has nothing better. **[checked]**

VOD 2905408276 re-pulled at 1920×1080@60 — 6.28 GB for 103 minutes. Twitch
offers 1080p60 as `Source`; `--list-formats` shows what exists before you
commit to a download.

---

## Visual punctuation (the "juice" layer)

Added after studying Pause (pausevfx), an AI editing product whose feature list
is a good checklist. Expressed as `effects[]` in the edit contract:
`shake`, `flash`, `glow`, `whip_pan`, `zoom_punch`, `rgb_split`.

- **Every effect needs a `motivation`** — what in the footage it punctuates. An
  effect that punctuates nothing is decoration, and the gate warns on it.
- **Flashes: max 3 per second, intensity ≤ 0.8.** **[checked — rejects]** This
  is the WCAG general flash threshold. A juice layer is exactly where
  photosensitivity problems get introduced by accident.
- Effect assets need a rights basis like any other. **[checked]**
- Punch-ins can animate (`punch` → `punch_to`) with an `ease`, and overlays
  carry `in`/`out` timing.

**Pause's headline feature is "cut the dead air" — do not apply that globally.**
It is right for reaction content and it would destroy a receipts clip, where
the silence is the evidence. Genre decides.

## Selection

Detect cheap, understand expensive.

- **Tier 0** Twitch top clips — the crowd already chose.
- **Tier 1** `detect_audio.py` — vocal RMS plus spectral centroid. A reaction is
  loud *and* bright; a gunfight is loud and dull. Plus the transcript.
- **Tier 2** `detect_killfeed.py` — rows by the local player's highlight colour,
  grouped into rounds.
- **Tier 3** `engine/tier3.py` — a model reads the region transcript and
  locates the clip. Only on a window a lower tier flagged; it costs per call.

### Why Tier 3 is not optional
Measured on FNS VOD 2905408276. The reveal line sits at 0:47:16:

| method | in-point | error |
|---|---|---|
| loudness peak | 0:48:27 | +71s |
| regex topic-shift markers | no marker found in 9 of 12 regions | — |
| crowd (clips) | 0:47:33 | +17s, starts mid-tease |
| **Tier 3** | **0:47:17** | **+1s** |

**A region is a POINTER, not a boundary.** Regions come from acoustic
clustering and cut topics in half. Unpadded, the model saw a truncated reveal
and correctly trimmed before it — a defensible clip of the wrong moment.
`judge()` pads ±60s and is told it may start outside the flagged window.

**Transcribe the whole VOD once, then slice.** Padded regions overlap heavily;
transcribing them individually costs several times more audio than the VOD.

Killfeed detection triggers on the **count of highlighted rows**, not OCR text.
OCR reads the feed in a minority of frames, and rows differ by a character or
two so fuzzy matching merges distinct kills. Gating on the player's own-row
highlight is what prevents kills and deaths being counted together.

**Calibrate before trusting it** — `detect_killfeed.py calibrate` on real
footage. The ROI in `config/killfeed.yaml` is a guess until you do.

---

## Rights

Client-owned footage is the clean agency model. Reposting a permitted
streamer's clip to your own channel is one posture; selling edits of
third-party footage is a riskier one. Keep `permission` on every source.

## Reporting

Exact counts, what was skipped, what wasn't verified. A high score is not a good
clip, and a server that connects is not a working render.

---

See `STYLE-BASELINE.md` for the full reference measurements and
`docs/RESOLVE-BUILD.md` for how to build this in Resolve.
