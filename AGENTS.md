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

5. **`endFrame` is EXCLUSIVE.** Measured: `startFrame=0, endFrame=100` yields a
   100-frame clip. Writing `endFrame = round(t*fps) - 1` therefore drops one
   frame from every segment, and between two adjacent shots that shows as
   **one black frame in the pane**. George reported "the screen randomly goes
   black" and a full-rate scan found the top pane at 0 luminance on exactly
   frames 485, 1153, 2029, 2302, 3318 — precisely the five cut points. The
   source clip itself measured clean, so every black frame was self-inflicted.
   **Scan the render at full rate, not 10fps**: a one-frame drop is invisible
   to a 10fps sample and `blackdetect` misses it too, because only one PANE
   goes black while the rest of the frame is lit.

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

### Emulating the references — measured, clip 8 v6

| | ours | R1 receipts | R2 take |
|---|---|---|---|
| Duration | 67.2s | 80.3s | 20.2s |
| Cuts / min | **5.4** | 6.0 | 0 |
| Mean shot | **9.6s** | 8.9s | — |
| Speech coverage | 84% | 50% | 96% |
| Loudness | −12.50 LUFS | −11.79 | −14.26 |
| True peak | −0.75 dBTP | +1.25 | −0.44 |
| Loudness range | 5.00 LU | 13.70 | 1.30 |
| Seam | 0.42 | 0.418 | 0.4422 |

**The loudness range is NOT a mixing fault — do not try to fix it.** Measured
on mute-free spans the speech runs **LRA 0.5–0.8**, *flatter than R2's 1.30*.
Strip the silence from the whole clip and it reads 2.90. The 5.00 is the
digital-silence holes. This is why neither a `loudnorm` LRA target (11→2 moved
it 5.00→5.20) nor an `acompressor` at up to 6:1 changed anything: there is no
speech dynamic to compress. **On muted source, LRA measures the mutes.**

**Cut on a document change.** R1 ran seven exhibits through its lower pane.
`cuts.content_scenes()` diffs the content region at 2fps and returns the times
the on-screen document changes; those become MANDATORY cuts, because a shot
straddling the change reframes the wrong document for half its length. Clip 8
changes at 6.0s — he reads the Global Esports announcement tweet, then
switches to the roster board. Adding that cut took the clip from 5 cuts /
11.2s mean to **6 cuts / 9.6s mean**, which is R1's cadence.

**Frame an exhibit as an exhibit.** The tweet is a document, so the content
pane punches onto it (source x 600–1190, y 200–809) instead of showing the
whole desktop. **The rect must match the PANE's aspect** — 1080/1114 = 0.969 —
or `fill` crops it: a 590×780 rect scaled to 1080 wide becomes 1427 tall in a
1114 pane and loses 313px top and bottom, which ate the headline's first line.

### Dead air: 0 of 6 removals survived review

George asked for dead space to be cut. Six candidate removals (10.4s, taking
the clip to 56.7s) went to an independent judge each, then every one judged
safe went to an adversarial second opinion. **All four that passed the first
pass were refuted. Nothing was cut.**

The refutations measured the waveform rather than reading the transcript, and
found things the first pass could not:

- **Ten of eleven mutes resume into full-level speech** (−7 dBFS within 300ms
  of the gate opening) — he is mid-word when the audio returns, so the removed
  span holds speech.
- The one exception, at 6.49s, opens onto **room tone at −23.4 dBFS** — he had
  stopped and drawn breath inside it, so that gap held a completed thought.
- At 18.04s the word "kind" is **not audibly spoken** before the mute, so the
  proposed join was not the join that had been judged.

**On a DMCA-muted VOD, dead air is not dead — it is speech you cannot hear.**
Removing it is not tightening, it is splicing. The engine is in
`engine/tighten.py` with `joins()` reporting every splice for review; it stays
available for clips whose silence is genuinely empty.

### READ `docs/SKILLS.md` BEFORE EDITING ANYTHING

It is the inventory of what the four references actually DO — ten techniques
with measured parameters. The reference table at the top of this file is
durations, cut counts and LUFS; it is not a description of the style. Working
from it alone produces a bare two-pane layout, which is exactly what happened:
several turns of polishing structure while every title, banner and overlay in
the references stayed unbuilt.

Worse, **skill 9 says plainly that speed ramps and punch-ins are "not observed
in any reference" — all four are talking-head formats.** Zoom punches were
added to a talking head anyway. They were a gameplay technique imported where
nothing called for it, and they were correctly described as awful.

What went in once the inventory was read:

| skill | technique | status |
|---|---|---|
| 8 | **Hook title** (R1) — 2 lines ALL CAPS, coloured keyword, holds 1.5s, 0.5s dissolve | built, `engine/titles.hook` |
| 7 | **Persistent banner** (R2, R4) — answers "what am I watching" mid-scroll | built, `engine/titles.banner` |
| 3 | **Tilted card** (R4) — screenshot at 4–8°, shadow, ~60% frame width | built |
| 9 | Zoom punches | **removed — in no reference** |
| 10 | Audio target: talking head is **−14 LUFS**, not the −12 house default | fixed, measured −14.02 |

The tilted card does a second job here. Moving the in-point past the news to
fix the two-narrative problem also removed the viewer's answer to "why is he
talking about this"; the card restores it in three seconds of screen time
instead of nine seconds of audio.

Still unbuilt, and honest about why: **multicam speaker cutting** (needs
diarisation), **full-frame evidence replacement** and **meme cutouts** (need
an asset library). Three of the four gaps are editorial sourcing problems, not
rendering ones.

**ffmpeg notes.** This build has no `drawtext` (no libfreetype) — render text
to PNG with PIL and `overlay` it, which gives a real alpha dissolve anyway. A
single-frame PNG input has no advancing timestamps, so `fade` never
progresses: use `-loop 1 -framerate N -t D`. And an overlay's own timeline
starts at 0, so shift it with `setpts=PTS+T/TB` to meet the main one, or it
dies before its `enable` window closes.

### Nothing had an exit, which is why everything jolted out

George: "the remotion video effect animations need to slide out in a more
efficient way ... right now it's just kind of jolting out of the frame."

Literal, not a matter of taste. **Not one component referenced
`durationInFrames`** — every card sprang in, held, and the composition
ended at full opacity, so Resolve cut from a fully lit card to nothing in a
single frame. There was no exit to be smooth.

`src/motion.tsx` holds one exit for the whole set, applied in `Root.tsx` by
wrapping each composition rather than editing twelve components. Each card
already takes a `top` prop, which becomes the `transformOrigin` — without
it the scale happens about the CANVAS centre and a card at y 1000 drifts
upward as it shrinks, because the transform sits on a full-frame layer and
not on the card.

| | |
|---|---|
| Length | **18 frames (0.30s)**, against a ~20-frame entrance — a graphic takes longer to arrive, where the viewer is reading it, than to go |
| Shape | ease-out pull-back over the first 22%, then travel accelerating as `q^2.3` |
| Anticipation | **13px against the exit direction** |
| Travel | 118px, in the direction the card is anchored — down for lower-pane cards, sideways for a side chip, up for the line under the facecam |
| Opacity | holds to p 0.35, zero at p 0.95 |
| Also | scale to 0.94 and a 5px blur, both tied to the travel, not to p |

**A single `easeInBack` is the obvious implementation and it is wrong.**
That curve stays negative until `p = c1/(c1+1)`, so at c1 1.9 the card is
still moving BACKWARDS for the first 65% of its exit and does all its
travel in the last few frames — by which point the fade has it at 4%
coverage. Measured on the alpha: -13.8px at p 0.69, then +56px crammed into
four frames. It reads as a fade. Separating the pull-back from the travel
puts ~75px of movement on screen while the card is still visible.

**Measure an exit on the ALPHA CHANNEL**, not by watching it:
`alphaextract`, then per frame take coverage and the centroid. A real exit
has three signatures — coverage falling to zero, the centroid travelling,
and the centroid moving the WRONG WAY first. The third is the one that
separates a designed exit from a fade, and it is invisible at a glance.

**A clip Resolve trims short loses the end of its exit**, which is the jolt
the exit exists to remove. Two were already short (`rm_Bait` 1020 of 1060,
`rm_Tweet` 207 of 210) because the durations were typed into `EXHIBITS` by
hand. `resolve_lean` now reads the frame count out of each `rm_*.mov` —
gated to those, since `cap_kin.mov` is the whole caption track and
`dip.mov` is a measured 0.567s envelope.

### Facecam punches are CUTS, and the base shots come off V1

George: "also need more zooms on fns' player cam in general when there's
important bold moments."

There is no keyframe API for transforms on the Edit page, so a push that
MOVES cannot come from Resolve. What can is a cut to a tighter framing and
a cut back — the ordinary talking-head punch-in. `resolve_punch.py` splits
each V2 shot at the measured peaks and re-frames the punched piece at
**1.22x** over that shot's own inset. V1 and the audio are untouched, so
nothing is spliced and no caption timing moves.

**Read the base shots off V1, not V2.** Reading them off V2 looks
equivalent and is not: a second run then takes the already-split 22 pieces
as its base shots, hands them `framings(22, ...)` and punches the punches.
V1 carries the same keeps with the audio and is never touched by this pass.

**+3.0 dB is not a threshold on this clip.** The whole thing spans 5.4 dB
over his baseline, so +3.0 picks eleven moments and means nothing. At
+4.0 dB with 4.0s suppression it is eight, one every ~5.5s. Verified by
reading `ZoomX` back off every V2 item: the eight punched segments measure
base x 1.220 exactly, and the other fourteen hold the framing cycle.

### `cue_gain` targets RMS, which is wrong for a click

The shutter was set to the same RMS as the thunks and measured **6.4 dB
louder** in the master. Measured crest factors across the palette:

| newsding | thunk | paper | tick | shutter |
|---|---|---|---|---|
| 12.0 dB | 15.6 dB | 16.9 dB | 19.5 dB | **22.0 dB** |

A camera shutter is two 3ms clacks — almost all peak, almost no RMS — so
equal RMS puts its peak 6 dB over everything else, and a click's
audibility tracks its peak. `sfx.cue_gain_peak` solves for the peak
instead. The thunks measure -14.3 dBFS in the master, which is the level
already accepted; the shutter is now set to match it.

And measure the cue IN THE BED, not from the generator: predicted and
measured levels disagreed by 13 dB here, because `bed()` is not just gain
times waveform. The file is the one that ships.

### A line of white tweet text is as bright as a photograph

Two automated scans put the tweet card's bottom edge mid-paragraph. The
first counted bright pixels per row, the second took mean luma over a
6-row window — and a full-width line of bold white text on a dark tweet
satisfies both. The boundary was read off the frame in the end: author row
at source y 152, text ends 370, attached photo starts 378, panel x
596-1196. **Crop a tweet to where its TEXT ends** — the attached image
would have doubled the card's height, and half of one reads as "cut off"
exactly the way the missing author row did.

### Captions reach further down than their anchor says

`captions_video.kinetic` draws from `y` as the TOP of the glyph, so y 0.44
is 845px and an 88px card reaches 933 — an emphasised one, at 1.27x, 957.
A graphic at `top: 900` is therefore underneath them, which is what
George's "needs to be lower so it doesnt go under the subtitles" was. The
story cards sit at 975.

Their photos then cost the headline: at 42px instead of 50, with tighter
padding, the photos go 560 -> 650 and the card 1020 -> 1064 wide. The card
now ends around y 1740, which is inside the bottom 320px exclusion — that
band is a CAPTION gate in `gates.py`, not a graphics one, but it is where
platform UI sits and it is a deliberate trade for the size he asked for
twice.

### Render Remotion from a script, not a retyped command

`render_remotion.py`. It existed only as a shell command retyped each turn,
which is how a round once shipped four cards whose SOURCE had been edited
and whose .mov files had not. One trap of its own: **Remotion zero-pads the
PNG sequence to the sequence's width** — `element-000.png` for 210 frames,
`element-0000.png` past 1000 — so the ffmpeg pattern has to be derived from
the frame count, not hard-coded to `%d`.

### Effects must be MOTIVATED, and the footage decides how many

George: "the transitions and punches and flashes are so random same with the
shakes." He was reading it correctly. The first version put **22 effect events
into 51 seconds** — a punch and a flash on every cut regardless of content,
plus shakes on `emphasis[:14]`, literally the first fourteen caption cards,
seven of them inside the opening five seconds. Effects landed on STRUCTURE
(cuts) rather than on anything happening in the footage. That is the
definition of decoration the contract warns about.

**Measure the emphasis; do not guess it.** Per-window RMS against the
speaker's own baseline. On clip 8 the baseline is −23.3 dBFS and the peak
−18.3 — a **5 dB total range** — so there are exactly FOUR moments above
+3.5 dB. A clip this evenly delivered cannot carry more than a handful of
effects, and the measurement says so before any are placed.

Final: **4 effects, 4.7/min** (was 26/min), each tied to a measured peak or to
the payoff, each carrying its motivation in `clip08_effects.json`.
`juice.Beat` **raises** on an empty motivation, and `juice.check()` warns on
effects closer than 3s, on the WCAG 3/s flash rate, and on anything over
20/min.

Dropped deliberately: **flashes on cuts** (a cut is already an edit event, and
neither reference uses flashes at all) and **shake** (decoration on a speaker
this measured).

### The small grey source line IS the AI-ism

George pointed at one strip — `VCT ROSTER BOARD · ALL REGIONS`, small grey
letter-spaced caps under a card — and called it "an ai-ism design". Then,
separately: "remove vlr part - sources dont matter - same with the other
one."

He is identifying a tell, and it is a real one. A tracked-out micro-caps
attribution under every card is the house style of generated design: it
looks like provenance, it costs a line of screen space on every graphic,
and nobody watching a 47-second clip reads it. **Every source line is now
off** — the exhibit eyebrows, the counter notes, the chip notes, the news
card's outlet line.

**The sourcing did not go away, it went off-screen.** The photo manifest
still records every photo's id, account, licence and page URL, and this
file still records where each figure came from. A quote desk has to be able
to answer "where did that number come from"; it does not have to answer it
in 15px grey type on every card.

**Other things that read as generated, for the same reason:** a kicker over
every panel, a pill-shaped tag on every element, a two-line label where one
word would do, and an accent dash before a heading. If a line is there to
look like information rather than to BE information, it is this tell.

### Sound on the MOTION, not only on the arrival

George: "include natural sound effects to your motion designs."

Every cue so far fired once, on arrival, and the graphic then moved in
silence — a card tilting into place, a counter spinning through 274, and
nothing to hear. Two sounds now follow the movement itself:

| | |
|---|---|
| `sfx.paper` | a card settling on a desk — filtered noise rolled off four times plus a 120 Hz thud, 260ms. Under the tilted story card as it lands. NOT a whoosh: no sweep, that family was rejected |
| `sfx.tick` | 30ms, a pitched body under a noise edge. Nine of them across the counter roll, spaced on the same ease-out curve as the digits, so they thin as the number settles |

Levels, measured in the bed and referred to the master: ticks **-21.5
dBFS**, paper+ding **-15.0**, thunk **-14.2**, speech peaks -0.6. A sound
that accompanies motion sits below one that marks an event.

**Re-render the COMPOSITIONS, not just the stills.** Editing the `.tsx` and
checking `remotion still` proves the source changed; it does not change the
`.mov` files on the timeline. Four source lines were "removed" and still
shipped in the render because only the previews were regenerated. Any edit
to a component means re-rendering every composition that uses it.

### Where a card sits is a function of the captions

The tweet card sat at y 900 and occupied 913-1472. The captions sit at
y 845 and their glyphs reach about 960, so the card's top 45px ran under
them — George: "looks like youve cut off the story at the top". Moved to
y 1010 (occupies 1023-1582), which clears the captions and still ends
inside the 1600 safe-area line.

**The usable band for a lower-pane graphic is y 980-1600.** Above 980 the
captions own it; below 1600 is the platform's UI.

### "274 what?" — the pair rule applies to a COUNTER too

George, on the counter card: *"274 what? doesnt make sense."*

He is right and it breaks a rule written down in this very file: **a lone
figure can argue the opposite of the point, so a card shows a PAIR.** I
wrote that after three judges caught "32 OPEN SLOTS" alone, then shipped
"274 / NOT YET CONFIRMED" as a solo counter anyway.

The earlier reasoning was sound but incomplete. The board's own label has
no noun, and the verification pass was right that inventing one ("274
PLAYERS") asserts something the source does not say — staff and bench are
separate columns, and 139+32+82+78 does not equal 274, so the figure is not
a simple sum of the others. The mistake was concluding that the card
therefore had to stand alone.

**The subject comes from the CONTRAST, not from a noun.** `PairCounter`
shows **139 SIGNED** beside **274 NOT YET CONFIRMED**, both the board's own
labels, the second counting up against the static first. No noun invented,
and the question "274 what?" answers itself.

### A news card is cleaner without its chrome

Three notes in one, all right:

* **"remove the bar which is black and yellow, makes it cleaner."** The
  masthead slab was borrowed TV-news furniture sitting on a press card that
  did not need it. Attribution stays — a headline needs a source — but as a
  quiet grey `VLR.GG · 31 OCT` line inside the card.
* **"make sure it takes up more of the lower screen."** 880 -> 1000 wide,
  photos 250 -> 330 tall, headline 46 -> 54px, sitting at y 960. The lower
  pane is 1114px tall and the card was using half of it.
* **"remove credits we have full permissions."** Confirmed by George that
  his Riot photo permission covers video, so the per-photo credit line is
  gone. The licence is still read and logged per photo in the manifest —
  the record stays even though the overlay does not.

### Show the published HEADLINE, not a verb lifted out of it

George: *"i dont like this design it doesnt make sense 'parts ways with' ??
use an actual news story headline for both and just add images of the
players under the headline and make them both tilted."*

He diagnosed it exactly. The card had **JINGGG** across it with *"PARTS WAYS
AFTER FIVE YEARS"* under it in gold — VLR's verb cut out of its sentence and
set as a standalone label. No one writes that; it reads as a caption with no
author. The published headline *"Paper Rex parts ways with Jinggg after five
years"* is a sentence and works as one, carries its own subject, and is
safer, since the verification pass was strict about that verb in the first
place.

**So an outside story goes on screen as the outlet published it**: a
masthead (`VLR.GG` + a date stamp), the headline verbatim in sentence case,
the people it is about underneath, and the photo credit. `NewsStory` in
`vendor/remotion-clip08/src/NewsStory.tsx`.

**Tilted, per the R4 reference** — the tilted card at 4-8 degrees with a
shadow is already in `docs/SKILLS.md` as skill 3 and it was never used here.
The two run -3.4 and +3.1 degrees, opposite ways, so two stories in five
seconds do not read as one repeated element. The tilt animates in with the
spring rather than being baked, so the card settles into its angle.

A white card is also the point: every other graphic here is a dark glass
panel, so a press story arriving as **white paper** separates "what the
outlet published" from "what the board says" without a label explaining it.

**Two sounds, two meanings.** `sfx.thunk` (87ms, low, dry) says a FIGURE
landed. `sfx.newsding` says a STORY landed — two notes a fifth apart, G5
then D6, the second entering while the first rings, gone in 312ms. George
asked for "some kind of news ding"; the distinction is what stops a fifth
sound design being noise. It sits at **-16.9 dBFS** in the master, under the
thunk's -14.2.

**`PALETTE` is a dict literal, so a function defined after it cannot be
named inside it.** Appending `newsding` to the end of `sfx.py` and adding it
to the literal gives `NameError: name 'newsding' is not defined` at import.
Register it after the definition: `PALETTE["newsding"] = newsding`.

**Measure a cue in the BED, not the master.** Windowing the finished mp4
around a cue reported +2.0 dBFS, which is impossible in a file limited to
-0.65 dBTP — the window was catching speech, and AAC decode overshoot puts
float samples above 1.0. The bed is the only place a cue is isolated.

### Player photos: the Flickr client already exists, in the quote desk

George: "include images of players that go along with the graphics ... Use
the Flickr API that's seen in the Valorant Work channel."

**It is already built.** `~/valorant-quote-desk/worker/hermes_images` is a
working Flickr client for the four official accounts —
`valorantesports` (global), `vctamericas`, `vctemea`, `vctpacific` — with
per-photo licence reading, a 7-day cache, 1s rate limiting and retry
backoff. `ImageFinder(api_key, roster, stars).for_quote(handle)` returns
`Image(path, photo_id, subject, solo, account, uploaded, licence,
page_url)`. Reuse it; do not write a second client, or the licence handling
does not come along.

**The key lives in the environment, not in the code.** `DEFAULT_API_KEY` is
`os.environ.get("FLICKR_API_KEY", "")`, so running from another directory
gives an empty key and the finder reports "no photo found on any account" —
which looks like a search miss and is not. Export it from
`~/valorant-quote-desk/.env` first. (Both that file and
`~/quotes-pipeline/.env` carry one.)

**RIGHTS: these are All Rights Reserved.** The quote desk says so in its own
comment — "Riot's photos are All Rights Reserved. Used here with the
operator's own permission; the licence is still read and logged per photo
so nothing goes out on an assumption." Same operator, same material, and he
asked for them here, so that basis carries over — but a still quote card
and a distributed video clip are different uses, and every card now prints
`PHOTO: <account> / FLICKR · ALL RIGHTS RESERVED`. Worth his explicit
confirmation before anything ships publicly.

**Check what the photo actually shows.** The top-ranked Jinggg result was
the back of his head — identifiable only by the jersey name. The second
candidate was a clean face-forward shot. `for_quote` returns several;
look at them.

`PlayerCard` in `vendor/remotion-clip08/src/People.tsx`: portrait wiping in
from the side it sits on, a gradient into the panel so the photo has no
hard edge, the handle, the team, the one-line fact, and the credit.

### The clickbait line, and a reversal recorded as a reversal

George: "a line of text that says what the video is talking about, like FNS
talking about whatever it may be ... include an emoji at the end ... an
Apple emoji or like a shocking face ... It needs to be clickbaity ... and
that can be like slightly under his face cam."

**This reverses two earlier notes and that is fine — his call.** He
rejected "FNS ON JOB SECURITY IN VALORANT" as a banner that "doesn't make
sense", and later said "i dont need random text popping up". This is text I
write, and it stays: a clickbait hook line is a different object from a
neutral banner or a mid-clip title, and he asked for it directly.

Shipped: **"FNS ON VALORANT'S JOB SECURITY PROBLEM 😳"** at y 700 — inside
the facecam pane, under his face, clear of the captions at 845. It runs
0.8-17.8s, the stretch where a scroller decides, rather than the whole clip.

**The emoji is why it has to be Remotion.** PIL cannot render colour emoji
at all; Chrome on macOS has Apple Color Emoji and draws it natively. The
emoji also lands a beat after the line and gives one small scale-and-rotate
kick, so it reads as a reaction rather than a character.

### Verify a news fact INDEPENDENTLY before a name goes on screen

The fortnight's roster news was the timeliest material available and half
of it did not survive checking. Eight claims went to an independent pass
(search for corroboration elsewhere, do not just re-read the cited page);
**four held, four failed.**

Held, and shipped:

| stamp | card | source |
|---|---|---|
| 31 Oct | PRX PART WAYS WITH JINGGG / FIVE YEARS AT THE ORG | VLR.gg |
| 31 Oct | SENTINELS RELEASE JONAHP AND JERRWIN | VLR.gg |
| tomorrow | FREE AGENCY OPENS 2 NOV / WHEN MOST VCT CONTRACTS EXPIRE | Riot schedule |

**The one I was most excited about failed.** "KRU cut mwzera and heat" would
have closed the loop on the exhibit already in the clip — the board shows
those two unconfirmed and the marker circles them. It did not corroborate,
and shipping it would have named real people as released on one outlet's
word. This is why the names wait for the check and the figures do not.

**The checker's wording is the wording.** It was stricter than I would have
been and it was right every time:

* **"part ways with", never "cut"** — no org stated a reason, and Jinggg's
  contract ran to the end of 2026, so it may be a non-renewal;
* **"five years at the org", not "five-year starter"** — he was a reserve
  from Oct 2023 to Mar 2024;
* **keep PRX's slot retention on its own card**, because the sources say
  the departures are unrelated to league status, so the two must not share
  a sentence;
* **an absolute date, not "tomorrow", in the headline** — a relative word
  goes stale between render and post. (The stamp chip may say TOMORROW; the
  claim itself says 2 NOV.)

**Aggregate player counts from trackers do not survive.** "109 of 270 VCT
players unsigned" failed on six independent grounds — single-source, both
halves drifting between snapshots, the tracker's own page admitting an
overcount, "unsigned" conflating contract-expiry with having no team,
a denominator from a different season, and a figure that moves the day
free agency opens. Riot publishes expiry as a YEAR, so no tracker can
distinguish "out of contract" from "without a team". The corroborated
version of that story is the structural one: **40 -> 32 partner teams, 8
per region, down from 10.**

### Tooling worth adopting, and the licences worth avoiding

A survey of the motion-graphics ecosystem against this exact pipeline:

| verdict | what | why |
|---|---|---|
| **adopt** | `paper-design/shaders` (Apache-2.0) | deterministic shader backdrops — the usual blocker is that shaders are time-seeded and so not frame-reproducible; these can be mounted deterministically |
| **adopt** | `remotion-bits` (MIT) | a component set aimed squarely at "a popup every few seconds that looks designed" |
| **adopt** | Remotion first-party packages | all resolve at 4.0.390, so no upgrade needed |
| **adopt** | `@remotion/captions` | `createTikTokStyleCaptions` would replace the per-frame PIL caption pass |
| try | `airbnb/visx`, `anime.js v4`, `three-nebula`, `simple-icons`, `pysubs2` | charts without an animation engine; text splitting; frame-exact particles; source-line logos |

**Licence traps, flagged so they are not vendored by accident:**
`hylarucoder/remotion-bar-race` has **no licence file at all**;
`patriciogonzalezvivo/lygia` is **Prosperity** (non-commercial);
`DanteAlighieri13210914/pv-tools` is **non-commercial**. On an agency clip
these are unusable whatever they do. `motion-canvas` and `tsparticles` are
fine licences but the wrong shape — both would be a rewrite.

### Density: ten graphics, and where the figures come from

George: "I like the fact that we're kind of having pop-ups like every other
second. I think that keeps retention quite well." Five graphics became ten,
roughly one every four seconds, and the earlier "way too much" still holds
because that was about EFFECTS — sweeps, act cards, a vignette. Graphics
carrying a real figure are the opposite: they are the reason to watch.

The rule that makes density safe is the one from the turn before: **every
figure is read off the board or sourced, and nothing on screen is a phrase
I wrote.** Ten graphics with no invented text is fine; three with invented
text was not.

| at | graphic | figure |
|---|---|---|
| 1.20 | side chip | 34/40 Americas slots filled |
| 3.30 | the announcement screenshot | — |
| 7.60 | stat card | 10 -> 8 partner teams per region |
| 11.60 | counter | 274, counting up |
| 15.08 | the header strip | 32 open / 274 unconfirmed |
| 19.40 | ratio bar | 32 against 274 |
| 24.32 | NRG card | 5/5 |
| 28.80 | the Americas grid, populating | eight real counts |
| 33.20 | KRU card + marker | 1/5 |
| 38.40 | side chip | 1/5 again |

New component types in `vendor/remotion-clip08/src/Chips.tsx`: `StatChip`
(small, side-anchored, ~1.8s, one figure — the thing that makes a high
cadence possible), `CounterCard` (eases out so the last digits settle on
the beat), `RatioBar` (32 against 274 renders as a 10% sliver, which is the
point), and `RosterGrid` (all eight Americas teams landing in turn, so
KRU's 1/5 is SEEN against seven others instead of asserted).

The eight counts, read off the board: 100 Thieves 5/5, G2 5/5, **KRU 1/5**,
Leviatan 5/5, LOUD 5/5, MIBR 4/5, NRG 5/5, Sentinels 4/5 — 34 of 40.

### The news is where the clip gets its timeliness, and it moves fast

George: "the news needs to be a bit more timely." A research pass over the
fortnight to 1 Nov 2026 turned up far fresher material than the partnership
story, and one item lands directly on the graphic already built:

| days old | item |
|---|---|
| 0 | PRX cut Jinggg after five years |
| 1 | Sentinels released JonahP and Jerrwin |
| **3** | **KRU cut mwzera and heat** |
| 4 | NAVI released its entire roster and coach |
| 5 | Gentle Mates dropped all five players and two coaches |
| 7 | MIBR benched all five, aspas included |

**The KRU item closes the loop on the exhibit we already show**: the board
has mwzera and heat sitting unconfirmed, the marker circles them, and three
days later they were cut. Likewise MIBR is on the board at 4/5 with aspas
listed.

**Do not put a player's name on screen on one source.** Almost all of these
are single-source (VLR.gg), which is the standard roster-news outlet but
still one outlet, and naming a real person as released when they were not
is the worst error this pipeline can make. They go through an independent
verification pass first; until that clears, the figures stay and the names
do not.

### Outside graphics are built in REMOTION, not drawn in PIL

George: "when we are introducing graphics from outside of what we're doing
... we're doing it in a way that actually looks designed, like we're using
ReMotion ... because the ones that you're implementing just don't look good
at all."

The split he is pointing at is real. A **crop of his screen** looks fine
because it is a photograph of a designed thing. A **card I draw** has to be
designed, and PIL cannot do the things that make a card look designed: a
gradient fill, a layered shadow, an inner highlight, a clip-path reveal, a
type scale with real optical sizes. CSS does all of them in a line each.

So anything not cropped from the footage is now a Remotion composition in
`vendor/remotion-clip08/src/Graphics.tsx`, rendered with alpha and dropped
on a Resolve track like any other overlay.

What the rebuild actually gained, beyond "nicer":

* one **shared surface** token, so the stat card and the exhibit frames read
  as a set rather than as separate drawings;
* **staggered reveals** — eyebrow, figure, label, source each land ~0.15s
  apart, which is what makes a card feel composed instead of pasted;
* the superseded figure **dims and blurs as the new one arrives**, so
  "10 -> 8" is a transition rather than two numbers side by side;
* the marker is an **SVG stroke drawn on by `stroke-dashoffset`**, with a
  wobble and a 1.1-turn overshoot — smoother than redrawing an ellipse per
  frame in PIL, and it keeps the pen taper;
* the screenshot inside the frame **wipes up via `clip-path`** so the
  evidence arrives rather than appears.

**Remotion will not write alpha from the CLI here.** `--codec=prores
--prores-profile=4444` produces `yuv422p12le` — no alpha plane — and
passing `--pixel-format=yuva444p10le` errors out. The route that works is
`--sequence --image-format=png`, then encode the frames to `qtrle` with
ffmpeg. PNG keeps the alpha and the encode is ours to control.

Also: `npx remotion render --help` does not list the transparency flags, so
do not go looking for them there — check the output's `pix_fmt` instead.

### Exhibits, not text. And the motion is what makes an exhibit land

George: "i like the kru thing thats a good idea - we need more graphics and
motion like that but in a cooler style ... i dont need random text popping
up during the video makes no sense."

**The dividing line is authorship.** A crop of what is on his screen, or a
sourced outside fact, is EVIDENCE. A phrase I wrote is text popping up.
"WHAT IT MEANS FOR PLAYERS" and "THE TRADE-OFF" were mine; they are gone.
The hook stays because it is his own closing line, verbatim, at the head.

Five exhibits now, every one of them real:

| at | exhibit |
|---|---|
| 3.30 | the Global Esports announcement tweet |
| 7.60 | **10 -> 8 partner teams per region**, sourced |
| 15.08 | the board's 32 open slots / 274 not yet confirmed |
| 24.32 | **NRG 5/5** — a full roster, over the line about getting signed |
| 33.20 | **KRU 1/5** with the marker on the four unconfirmed |

NRG replaces a second showing of the same strip. A full 5/5 roster against
KRU's 1/5 is the contrast the argument is actually about.

**Check the news; the best fact is often not on his screen.** Riot is
cutting each VCT region from **10 partner teams to 8** for 2027-28, and
Global Esports, Cloud9 and FlyQuest were among those rejected. That also
explains the board: its "32 teams" IS the reduced field, 8 x 4 regions.
Riot has published no official list, so the card is attributed to the
outlets that reported it, not stated as fact.

**`overlays.exhibit_reveal` is the "cooler style".** A fade plus a 16px
settle is why the cards read flat. What changed:

* **scale 0.78 -> 1.0 on ease-out-back**, so it overshoots slightly and
  settles rather than simply appearing at size;
* it travels from `from_x`, the horizontal position of the region it was
  cropped from, so it reads as pulled out of that part of the board;
* it **resolves from a 9px blur**, which is what sells a scale as depth
  instead of as a size change;
* it drifts ~9px while held, so a 3.5s card is never a still frame.

Easing lives in `engine/overlays` (`ease_out_expo`, `ease_out_back`,
`ease_in_out_cubic`). No library needed: the Python motion frameworks
surveyed (movis, pymotion) are these curves plus a compositor we already
have, and the broadcast-graphics repos found are OBS live-production tools,
not file-based.

**Tungsten has no arrow glyph** — "10 -> 8" rendered as tofu. Draw the
arrow as a rectangle plus a triangle.

### The caption style George likes is IMPACT, and the edit sits at ~10 events

Two separate notes, one turn: "way too much in the edit there, and didnt
include the new text style that i liked."

**The text style was a real miss, and the cause was the font.** The style
he picked out came from the Remotion version, where the CSS stack was
`Impact, Haettenschweiler, "Arial Narrow"`. My "smaller, less bouncy"
rebuild used `titles._font()`, which resolves to **Tungsten-Bold** — so the
size and the damping changed but the letterforms did not, and it never
read as the thing he liked. `captions_video.kinetic` now takes
`font_path`, defaulting to `/System/Library/Fonts/Supplemental/Impact.ttf`.

House caption spec, settled:

| | |
|---|---|
| Face | **Impact**, tracking -1 (PIL has none; step per glyph) |
| Size | **88px**, emphasis **1.27x**; shrink to fit at `width - 70` |
| Stroke | 9.5% of size, hard black |
| Entrance | critically damped — 10px lift, 0.045 scale, 1.2 degrees on emphasis |

C's own numbers were 104/136px with a spring that overshoots; "a little
bit smaller and less bouncy" is 88/112 with the overshoot removed.

**Event budget: about 10 in 47s.** The loaded cut ran 23 — a sweep on all
ten splices, three act cards, four dips, four cards, two titles — and that
was too much. Removed: the sweeps, the act cards, the seam glow and the
vignette. Kept: four dips, four exhibit cards, two mid-clip titles, and the
colour arc, which is a GRADE and does not count as an event.

So the swing went nothing -> 23 -> 10. Ten is the number to work from.

**Do not punch the pane onto an exhibit AND show a card of it.** With both,
the same figures appear twice in one frame. Style A's punch and the cards
are alternatives, not layers.

**Clear the render queue before rendering.** `resolve_driver.render()`
appends a job every call and never deletes one; a stale job whose output
file already exists is the likely source of the overwrite dialog that
blocked the API at 3% CPU. `DeleteRenderJob` on every job in
`GetRenderJobList()` first — doing that recovered a wedged Resolve without
a restart.

### The reference rule became the thing blocking the work

George: "you're literally just changing the fucking subtitle ... no
transitions, no sounds, no background effects, no coloring ... no storyline
... there's literally nothing."

Accurate. Across four style versions the only real differences were caption
treatment, a banner, a lower third and one pane punch.

**The cause is a rule in this file.** "Only use what is measurable in the
references" was written to stop invented decoration, and it worked — but
R1 and R2 are both RESTRAINED talking-head clips, so measuring against them
caps the work at a two-pane layout with captions. Every rejection tightened
the filter until nothing could get through. The per-second sweep even found
R1 running 72 documents and 40 overlays in 80s and the filter still blocked
acting on it.

**The rule now has a limit: it governs whether a technique is HOUSE STYLE,
not whether it may be used at all.** When George asks for something the
references do not contain, build it. The earlier note that "a cut is already
an edit event, so no flashes on cuts" is overruled by his instruction.

What went into the loaded cut, all in Resolve:

| | |
|---|---|
| Transitions | a 0.20s light sweep on each of the 10 splices (`build_loaded.sweep`) |
| Colour arc | three CDLs by act — cool and flat, house, then warm. Measured R-B: **-3.3 -> +3.8 -> +25.4** |
| Storyline | three act cards: "GLOBAL ESPORTS IS OUT", "SO WHAT HAPPENS TO THE PLAYERS", "YOU CAN END UP WITH NOTHING" |
| Background | an accent rule and glow on the seam, plus a soft vignette |
| Captions | C's kinetic style at 78px with the bounce damped out — his note |
| Sound | a cue on each sweep, now a visible event, spaced >= 2.5s |

**`SetCDL` per CLIP is how you get an arc without keyframes.** The grade
cannot ramp, but the cut is already 11 segments, so it can STEP by act. That
is the one place Resolve's lack of keyframes does not bite.

**An act card and a caption cannot share a line.** Both sat at y~820 and
collided on all three. The caption track is baked, so the fix is to drop the
cards that fall inside an act window when rendering it (20 of 106 here),
not to move either element.

**Resolve wedged again**, this time at 3% CPU with the API blocked — not a
busy loop, so most likely a modal dialog. A `SIGALRM` watchdog does not
help (the hang is inside `fusionscript.so`). `render()` also appends a NEW
job every call without clearing the queue, which is a likely source of an
overwrite prompt; it should clear stale jobs first.

### What this project needs from George to go further

The source is one static roster board and one tweet. No amount of technique
makes b-roll, memes or imagery out of that. Asked directly, these are the
blockers, in order:

1. **Reference clips in the style he actually wants.** R1 and R2 are
   restrained, which is why every measurement says "do less". Two or three
   clips of the heavily-produced style would re-aim every number here.
2. **B-roll with a rights basis** — VCT broadcast, gameplay, press shots.
3. **Team and org logos**, licensed.
4. **A licensed SFX library.** Synthesised cues have been rejected four
   times; `finish-standard.md` says the same ("never synthesize effects in
   code").
5. **A music bed** he has the rights to.
6. **A meme / reaction pack**, if memes are wanted.

### Four style versions, four tools

George: "give me 4 different versions of the video edited using different
tools - i want new editing styles." All four run off one clean base —
`renders/styles/_base.mov`, the tightened 46.9s cut in L2 with the facecam
graded and NO graphics — so the styles differ by treatment, not by edit.

| | style | tool | what makes it that style |
|---|---|---|---|
| **A** | Receipts | **DaVinci Resolve** | the lower pane punches FULL-PANE onto each exhibit with a dip either side; no cards, no titles — the document carries the argument, which is R1's actual structure |
| **B** | Take | **ffmpeg** | R2's language: one framing, zero picture cuts, white-on-blue box captions at y 0.747, and a persistent banner carrying his CLAIM in his own words |
| **C** | Kinetic | **Remotion** (React) | type is the hero — each card springs in at 104-136px across the seam, emphasis in accent with a tilt, a running kicker |
| **D** | Broadcast news | **HTML + headless Chrome** | a red-spine lower third, stat chips and a source strip, all authored in CSS and screenshotted to alpha PNGs, composited in ffmpeg |

All four: 46.9-47.1s, -14.1 LUFS, under -1 dBTP, QC pass.

**`engine/captions_video.track()`** renders a whole caption track to ONE
alpha movie from a style dict. 106 cards as 106 ffmpeg inputs is not
workable and Resolve's Fusion route costs a 300-frame title per 5s window;
one clip restyled by a dict is simpler than both, and it is what let the
same captions become blue boxes in B and a news bar in D.

Four things worth keeping:

1. **Remotion cannot fetch its own headless shell here** — it dies with "No
   browser found for rendering frames". System Chrome works:
   `--browser-executable="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"`.
   A 2822-frame 1080x1920 render then takes a few minutes at concurrency 4.
2. **HyperFrames is unavailable**: `npx hyperframes usage --json` returns
   `{"status":"unknown","reason":"unsupported_auth"}` — it needs George's
   account. Plain HTML through headless Chrome does the same job for static
   furniture.
3. **Chrome screenshots the whole PAGE, not an element.** Four elements in
   one file gave four identical PNGs. One element per HTML file, then crop
   to the alpha bounding box.
4. **An exhibit rect far from the pane's aspect renders BLACK.** The pane is
   1080x1114 (0.969). Punching onto the 670x28 stat strip needs ~11x, which
   Resolve clamps, and the pane came back black. Rects near 0.969 work:
   (10,100,680,790) for the strip in context, (958,240,1417,715) for KRU.
   Check the aspect before the zoom.

### The four outside skills — what was taken and what was refused

George sent `scenario-auto-edit` (zip, installed to `~/.claude/skills/`),
remotion, motionvideo.xyz and videoeditskill.synteq.app, and asked for a
better video without "anything ridiculous". Most of the value is in one of
them; the rest are already here or are styling.

| source | what it is | verdict |
|---|---|---|
| **scenario-auto-edit** | talking-head auto-edit: word-level cutting, Apple Vision person matte, type behind the head, captions, ElevenLabs sound, Seedance world rebuild | the substance. Needs the Scenario MCP (not connected), so the paid cloud steps are unavailable; its **finish standard** is the useful part |
| **remotion** | React programmatic video | **already installed** here as `remotion` / `remotion-editor`. A different rendering stack, not a technique |
| **motionvideo.xyz** | library of AI motion videos + MCP + skill | a catalogue; no concrete parameters on the page |
| **videoeditskill.synteq.app** | "Style Studio" — picks a type family, casing and palette, emits a configured skill | a styling layer. We already have one (Tungsten + a single gold accent) |

**TAKEN, and only after measuring that this audio needed it.** Its voice
chain lists six moves; four of them measure as unnecessary here, and
applying all six on faith would have undone work:

| move | measured on our master | verdict |
|---|---|---|
| high-pass 85 Hz | rumble at **-5.1 dB** vs the speech body | **applied** -> now -14.4 dB |
| -2.5 dB @ 280 Hz | **+1.6 dB**, slightly boxy | **applied** -> now +0.4 dB |
| de-esser | sibilance already **-20.2 dB** | refused, nothing to tame |
| "a little air" | 10-14 kHz at -35.7 dB, and we CUT the top because it measured +10.7 dB hot vs R1/R2 | refused, it would undo a measured fix |
| +2 dB @ 3.6 kHz | we already do +4 dB @ 3 kHz from the same measurement | kept ours |
| 3:1 compression | speech runs LRA 0.5-0.8 on mute-free spans, flatter than R2 | refused, no dynamic to compress |

**TAKEN: re-transcribe the finished cut and diff it against the source.**
"Every word must survive." This is the check the 15 dead-space joins needed
and we did not have. Result: **174 source words, 177 heard, similarity
0.974**; the only differences are function words and whisper variance
("partnered" heard as "partner"), so no splice ate anything of substance.
Note `they're` sits exactly on a join and is worth a listen.

**Already satisfied: `segment_zoom`.** Its jump-cut cover — alternate the
base framing per segment so splices read as intentional — is what
`cuts.framings` and `cuts.content_framings` already do on V2 and V1. (The
older note here that "the lower pane never moves" is stale: it was true at
v6 and the current build moves both panes.)

**REFUSED, with reasons:**

* **Seedance world rebuild** — regenerating the room around the speaker.
  On a quote desk this is fabricating the record of a real person. No.
* **"Always lay a music bed"** — contradicts the measured references:
  neither R1 nor R2 has one. George's own references outrank a general
  house standard.
* **"Never synthesize effects in code"** — ours are synthesised precisely
  so the rights basis is clean and `gates.py` can check it. A real
  disagreement, recorded; ours stays.
* **Odometer counters, flicker words, lights-down spotlight, light burst,
  logo end card, character cards** — product-hook furniture. On a clip
  about players losing their jobs they are exactly the "ridiculous" being
  warned against.
* **24 fps** — ours is 60, and the references are 60 and 30.
* **A subtle vignette** — tried to verify it against R1/R2 and the test is
  confounded: in a two-pane layout the corners sit in the bright panes, so
  corner-vs-centre reads 1.8 on R2 and on ours. Inconclusive, so not added.

**Not yet tried: type behind the speaker from a person matte**, the one
genuinely strong technique left. The risk is specific — our facecam is a
464px-wide source region upscaled 3x into the top 42%, so a matte would be
cut from soft pixels, and there is little headroom above his head for type
to rise into. Worth a test, not worth assuming.

### The black dip, and what Resolve does to an alpha overlay

**Measured on R1 at 1:11, frame by frame, and all three assumptions were wrong:**

| | |
|---|---|
| What dips | the CONTENT PANE only — facecam holds 67-69 luma straight through |
| Depth | to ~6 luma from ~79. It never reaches black |
| Shape | down 0.13s, hold 0.40s, up 0.15s — asymmetric, 0.56s total |

It is the ONLY transition anywhere in the four references. No wipes, no
whooshes. `overlays.pane_dip`.

**RESOLVE COMPOSITES IN LINEAR LIGHT, and it moves the number 12x.** The
identical alpha clip over the identical frame measures a 0.189 luma ratio
in ffmpeg — exactly the 0.18 the alpha asks for — and **0.015 in Resolve**.
Two depths pin the transfer at `(1 - alpha) ** 2.4`: alpha 0.82 predicts
0.0156, measured 0.015. So an alpha intended to darken by a given amount on
screen has to be solved through that gamma. For R1's floor here,
`(1-a)**2.4 = 6/24` gives **a = 0.42**, which lands at 10.6 luma measured.
Anything composited in Resolve with an intended opacity needs this.

**It goes BELOW the captions.** In R1 the dip is the document going dark and
the editor's own overlays stay lit through it, so track order is now
`V1 content | V2 facecam | V3 dip | V4 cards | V5 titles | V6 captions`.
The 11 caption Text+ titles were lifted from V3 to V6 with `SetPosition`;
never clear V6, since rebuilding them means re-running the Fusion pass.

**One dip, because clip 8 earns exactly one.** R1 dips between exhibits and
has 72 of them; clip 8's pane shows one static document, so the single
handoff is the announcement tweet giving way to the board as the card
clears. Anywhere else it would punctuate nothing.

### No dead space on a talking head

George: "for talking head videos like these ensure there is NO dead space."

The earlier cut removed only DIGITAL ZERO (the Twitch mutes) and left
ordinary room tone, so **6.40s of pause survived into the delivered clip —
12.4% of it**, against R2's 96% speech coverage. `qc.quiet_runs` catches the
other kind, on a floor **relative to the speaker's own level** (75th
percentile of window RMS, minus 12 dB) rather than a fixed dBFS, because raw
VOD audio runs ~7 dB under target and a fixed threshold means something
different on every clip.

| | before | after |
|---|---|---|
| Duration | 51.5s | **46.9s** |
| Absent audio | 1.77s | **0.00s** |
| Quiet | 6.40s (12.4%) | 3.70s (7.9%) |
| Speech coverage | 87.6% | **92.1%** (R2: 96%) |
| Shots | 5 | 11 |

Two things this costs, both real:

* **12.8 cuts/min against R1's 6.0.** Each removal is a splice, and the
  facecam framing changes at every one so it reads as a cut rather than a
  jump — but the cadence is now twice the reference and that is a
  consequence of the instruction, not an editorial choice.
* **15 joins splice across unheard speech**, printed by `tighten.joins()`.
  The caveat from the adversarial review stands and has been overruled
  twice; it is not re-litigated, only recorded.

**Anchor overlays to SOURCE time, never to the finished cut.** Re-timing the
clip moved every output timestamp, and hard-coded overlay positions would
all have drifted silently. `build_overlays.at(src_t)` remaps a spoken-line
anchor through the same keeps `build_v7.py` uses, so the two agree by
construction.

**Trim the render to the PICTURE.** A caption title is a fixed 300 frames
and cannot be trimmed through the API, so the last one overhangs V1 by
whatever the keeps fall short of `round(out_dur * fps)` — 4 frames here,
which render black. And `-t` with `-c:v copy` cuts at a keyframe, so it
misses: use `-frames:v` on the delivery re-encode.

### Marker annotation and mid-clip titles (R1, 0:31)

Both came out of a per-second contact-sheet sweep of R1 that the earlier
once-over had missed, and both are now built.

**The marker DRAWS ON.** R1's annotation is a red/orange circle caught
mid-stroke — about 70% round, starting bottom-left and sweeping up and over.
That is the whole character of it: a circle that simply fades in reads as a
UI element, while one that draws reads as someone pointing. `titles.
marker_ellipse(…, progress)` renders one frame of the stroke;
`overlays.sequence_clip` pipes the frames to ffmpeg as raw RGBA so an
animated overlay needs no intermediate files.

Three details keep it off the vector-ellipse look, and all three matter:
the radius wanders on three slow harmonics (noise alone looks like noise,
not like a hand); the stroke thins toward the end as a real pen lifts; and
the arc **overshoots past 360°**, which is what a hand does closing a circle
in one motion.

On clip 8 it circles the four unconfirmed KRU players, replacing the clean
rectangle `panel(boxes=…)` was drawing. Its position is DERIVED from the
panel geometry — crop scale, card offset, pad and kicker height — not
eyeballed, so it stays correct if the card is resized.

**Mid-clip titles are the same treatment as the hook.** R1 re-titles as the
argument moves ("150K POV:" at 0:31): ALL CAPS, white fill, heavy hard black
outline, no box, no glow, condensed heavy grotesque, roughly a second, then
a dissolve out — and R1 lets that dissolve run on top of a shot change
rather than waiting for one. `titles.section` is `hook` with one line at a
smaller cap height, so the head of the clip keeps its weight.

Clip 8 gets two, and neither restates him — they frame the stretch that
follows, which is the job the removed banner was doing badly:
**"WHAT IT MEANS FOR PLAYERS"** at 6.1s (the pivot from news to argument)
and **"THE TRADE-OFF"** at 44.4s (the closing move).

**Titles get no sound.** Sound stays exclusively on fact cards, so a thunk
always means the same thing — a fact just arrived. Salting six events
instead of four is the wrong direction after two notes about level. The
marker gets none either: it starts 0.55s after its card's cue, well inside
the 3s spacing floor.

Seven overlays in 51.5s now, up from three.

### The overlays belong IN the Resolve timeline

George: "stop being lazy, edit this in davinci." He was right — the hook,
cards and sound were being composited in ffmpeg after Resolve rendered, so
none of them existed in the timeline and none could be nudged in the UI.

They are now clips on **V4/V5** and **A2**. Resolve composites and renders
them. `resolve_overlays.py` places them; `engine/overlays.py` prepares them.

**How, given there is no keyframe API.** `Opacity` IS a settable
TimelineItem property (verified: set 40, reads back 40) but holds one static
value. `AddTransition` does not exist. So each overlay's fade and settle are
baked into a full-frame **alpha movie clip**, and Resolve just composites
it.

Four things cost a render each:

1. **`hasattr` LIES on Resolve objects.** They are remote proxies, and
   `hasattr(tl, "ThisMethodDoesNotExistAtAll")` returns True. That is how
   `AddTransition` looked available. Call it: `TypeError: 'NoneType' object
   is not callable`. Never feature-detect with `hasattr` here.
2. **A still cannot be used as an overlay clip.** A PNG in the media pool
   reports `Frames == 1` and `AppendToTimeline` ignores `endFrame` for it —
   the clip lands at Resolve's default length (300 frames) no matter what
   you ask for. A movie clip honours `endFrame` exactly.
3. **`color=c=black@0.0` needs `,format=rgba` INSIDE the lavfi source.** The
   bare source emits an opaque format, so the `@0.0` has nothing to be
   carried in, and converting to rgba afterwards gives opaque black. Also
   `overlay=...:format=rgb` flattens alpha — use `format=auto`. Either
   mistake yields a clip that looks right as a still and composites in
   Resolve as a solid black rectangle.
4. **Use `qtrle`, not ProRes 4444.** Both are lossless with alpha, but these
   frames are almost entirely transparent and RLE collapses that: 56 MB for
   five overlays instead of ~1.2 GB. The ProRes attempt filled the disk and
   died with exit 228.

**Derive the length FROM the timeline.** Hard-coding 51.5s put the sound bed
5 frames past the picture, which permanently extended the timeline (deleting
the clip does not shrink it back) and left a black frame at 51.42s.

**What still cannot be in Resolve, and why:**

| | |
|---|---|
| Loudness | `NormalizeAudioLevel` applies gain without true-peak limiting. At -20.2 LUFS / -3.5 dBTP, the +6.2 dB to reach -14 would hit +2.7 dBTP |
| Animated shot pushes | no keyframe API for transforms (see the juice section) |

**Regression to be honest about:** the animated 5% shot pushes are GONE from
v22. They were an ffmpeg `zoompan` over the whole frame, and now that the
overlays are burned into the Resolve render, pushing would scale the cards
too. The per-shot *framings* remain (they are V2 insets in Resolve); only the
movement within a shot is lost. To get it back, bake the push into the
source clips BEFORE Resolve rather than after.

### More overlays, because the reference has far more

George: "we need more popups on the screen for things like news, references,
etc ... still looks basic." Measured, he is right by a wide margin.

Clip 8's own footage cannot supply variety: the content region is **pixel-
static for 61 of its 67 seconds** (frame delta median 0.13, one change at
5.5s when he switches from the tweet to the board). R1 by contrast changes
its lower pane constantly — in seconds 30-39 alone a per-second sweep found
the buy menu, gameplay, a scoreboard, the scoreboard with a context card,
the report dialog and gameplay again.

So variety has to come from moving around INSIDE the one document. Now five
overlays instead of three, each on the line it supports:

| at | overlay | over |
|---|---|---|
| 0.00 | hook title | — |
| 1.65 | the announcement tweet | the news |
| 17.45 | strip: 32 open slots / 274 not yet confirmed | "you don't have enough job security" |
| 30.80 | strip: 139 signed | "once you get SIGNED to an org" |
| 37.85 | KRU Esports: 1/5, four unconfirmed | "those people that get replaced" |

The KRU card is the strongest thing on the board: four empty roster slots,
one signed player, and saadhak / Dantedeu5 / mwzera / heat sitting in bench
/ options. Showing real pixels also preserves handle casing for free —
"KRU", "Dantedeu5" — which the whisper transcript garbles.

**Sentinels is unusable as an exhibit**: his facecam window sits over it in
the source frame. Check occlusion before choosing a region.

**Still to build, found by a per-second sweep of R1 and not yet in our
inventory** (`docs/SKILLS.md` skills 16-18):

- a **hand-drawn marker circle** over the exhibit (R1 at 0:31) — annotation,
  which is exactly the "references" idea;
- a **mid-clip section title** ("150K POV:" at 0:31), not only a hook;
- the content pane **dipping to full black between exhibits** (R1 at 1:11).

### SHOW the exhibit, do not redraw it

George on a card I designed: *"animations like that are useful and
informative but i dont like the design - looks vibe coded."*

He was right, and the fix came from looking at R1 again rather than
iterating on the design. **R1 does not design a stat panel.** The card at
0:08 — AIM 98.6 / RATING +2.4 / TIME TO DMG 447ms, twelve figures in a grid
— is a screenshot of a real stats page composited in, exactly like the tweet
card. Square corners, no shadow, no accent rule, the page's own light wide
sans. The reference shows the document.

My card had rounded corners, a drop shadow, a gold rule down one edge and
heavy condensed gold numerals. That combination is the generic-dashboard
signature, and no amount of restyling fixes the category error.

So `titles.exhibit` crops the **actual stat strip out of the source frame**,
magnifies it ~2x and puts an accent rule under the figures being pointed at.
It cannot be mis-transcribed, cannot drift from the source, and cannot look
like a component because nothing about it is drawn. Strip geometry is
measured by column variance and kept in `titles.STRIP_BLOCKS`.

**Crop a CONTIGUOUS run.** The two figures that matter are blocks 2 and 5,
not adjacent. Stitching them together would fabricate an adjacency the page
does not have — that is doctoring an exhibit. Show the run that contains
them and underline the two.

**A banner must be a CLAIM, not metadata.** George: *"the 'fns on job
security' bit doesnt really make sense."* R2's persistent banner says "IT'S
EITHER PRX OR G2" — the take, in the speaker's voice. Mine described the
video to itself. The banner is removed; if one returns, it asserts
something.

**Pick a sound by TARGET RMS, not peak gain.** Across the palette the RMS of
a peak-normalised waveform spans 9 dB, so the same `gain` makes a chirp far
louder than a tock — which is why levelling kept missing in both directions.
`sfx.cue_gain(name, target_rms_dbfs, master_gain_db)` solves for the gain,
and swapping sounds then keeps the level. Clip 8 sits at -30 dBFS RMS.

Sound, fourth attempt: rejected were a bell (547ms decay), a shorter bell
(216ms) and a woodblock (65ms) — all pitched chimes. `sfx.thunk` is the
other register: a down-swept low body plus a click, gone in 87ms.

### A card has to carry a FACT, and the exhibit is full of them

George, on the v19 chips: *"why are you adding a text of 'blown out of
proportion', makes no sense, stop making these random text cards - if you had
useful information to put on the screen like you did at the start it'd be
fine."*

He is pointing at the tweet card. **The test for an overlay is whether it
tells the viewer something the audio does not.** The v19 chips paraphrased
his own captions into a box — "BLOWN OUT OF PROPORTION" is literally the
caption one line earlier — so they carried nothing. Note this was already
written down here ("chips carry the argument, not the caption") and broken
anyway, because paraphrasing *feels* like adding something.

**Where the facts were: in the frame the whole time.** FNS reads from the VCT
Roster Board for all 51.5s, and its header strip is real data made illegible
by the crop to 1080x1920. Verified by three independent reads of a 2x crop,
all six figures agreeing exactly:

| 32 teams | 139 signed | 32 open slots | 82 bench / options | 78 staff | 274 not yet confirmed |

This is the same move R1 makes by running seven exhibits through its lower
pane. The content pane is a document viewer — read the document.

**A LONE FIGURE CAN ARGUE THE OPPOSITE OF THE POINT.** Three independent
judges caught this before it shipped: "32 OPEN SLOTS" on its own reads as 32
jobs going spare, which undercuts the scarcity he is arguing; it only means
scarcity beside the 274 chasing them. So a card shows a PAIR. Likewise "139
signed" alone implies rosters are nearly full.

**Copy the source's own labels and invent no nouns.** The board says "bench /
options", not "bench". It says "274 not yet confirmed" with no noun — writing
"274 PLAYERS" asserts something the source does not say, since staff and
bench are separate columns. An unsourced or re-worded number on a quote desk
is a liability, so the card carries its source line.

Shipped: **32 open slots / 274 not yet confirmed** over the job-security
thesis at 17.45s, and **139 signed / 82 bench / options** over the
replacement line at 37.85s. `engine/titles.stat`. Unanimously rejected by the
judges: "78 staff" (he never mentions staff) and dropping cards altogether.

### Sound belongs to a VISUAL event, not a vocal peak

Three designs were rejected in a row — ding-on-entrance, whoosh-on-cut,
impact-on-vocal-peak — and the third was the informative one, because by then
the placement was *correctly measured*. The three `impact` cues sat on real
RMS peaks of +5.0, +3.7 and +3.8 dB over the speaker's own baseline, and
George still called them "random sound effect out of place and useless".

**A measured peak is not a motivation the viewer can see.** The `motivation`
field was satisfied and the sound was still wrong, because nothing on screen
changed when it fired. A sound explains itself when the viewer watches the
thing that made it arrive.

So: **no sound without a visual event**. Current set is five cues, all of them
a popup landing — the tweet card plus four chips. Nothing fires on a peak, a
cut, or a word.

**Low means ~13 dB under the speech, and the arithmetic is worth keeping.**
The bed is mixed before `loudnorm`, so a cue's gain is not its level in the
master. Measured on clip 8: bed peak 0.099 (−20.1 dBFS), loudnorm applied
+6.2 dB (−20.2 → −14.0 LUFS), so the ding peaks at **−13.9 dBFS** against
speech at −0.75 dBTP. The rejected ding at gain 0.45–0.80 works out to −0.7 to
**+4.3** dBFS — louder than the speech it was punctuating, which is exactly
what "way too loud" meant. Compute the post-normalisation level before
choosing a gain.

**SUSTAIN is what makes a sound read as a ding.** Both sounds George rejected
turned out to be the two longest-decaying in the palette — `ding` rings for
547ms, `pop` for 216ms. Measured across seven candidates, everything under
~100ms lands as an event instead of a chime. The popup sound is now
`sfx.tock`, a dry woodblock: **65ms decay**, centroid 2020 Hz, no ring.
Gain 0.095 puts it at **-14.2 dBFS** in the master.

**Window the spectral centroid.** `_centroid` was taking a raw `rfft`, so
leakage from the hard start of a short burst smeared across the spectrum and
inflated every figure in the manifest — `tock` read 7173 Hz raw against 2020
Hz Hann-windowed, with a tonal body at 1565 Hz. Fixed; `ding` is 4107 Hz, not
the 5984 Hz quoted earlier here.

**Make a popup a different OBJECT from the banner.** First pass drew the chip
as a dark card with a gold outline — the same thing the persistent banner is —
and at 1180 vs 1500 they read as two banners rather than a popup over a
banner. Inverting the chip (solid accent, dark text, drop shadow) separates
them instantly. `titles.chip`.

**Pop motion is a MOVE, not a grow.** `scale` cannot animate for the same
reason `crop` cannot (below) — constant output dimensions. But `overlay`'s
`y` takes `t`, so the chip settles 14px over 0.16s under a 0.10s alpha fade.
Measured on the render: top edge at row 1186 at t+0.07, 1180 by t+0.17.

Chips carry the argument, not the caption — the captions already show the
words. On clip 8 the four are "BLOWN OUT OF PROPORTION", "NO JOB SECURITY",
"1-YEAR CONTRACTS", "REPLACED = NO JOB", each over the line it compresses,
each verified against the burned captions in the render rather than against a
reconstructed timeline. No chip on the payoff: the hook title already says
those words.

### `crop` CANNOT animate a zoom — it has to be zoompan

This cost two wrong renders and a wrong conclusion, so it is worth stating
flatly. A filter's output dimensions must be constant for the encoder, so
`crop` evaluates `w`/`h` ONCE at init; only `x`/`y` can move. That is why
ffmpeg 9 removed crop's `eval` option. A crop-based punch renders silently at
zoom 1.00 and looks plausible in a still — **measured against the source it
came back identical, residual 0.3.**

`zoompan` scales internally and emits a constant size, which is the entire
reason the filter exists. Its evaluator has **no `t`**; it offers `it` (input
timestamp) and errors with "Undefined constant" otherwise. `eq` later in the
chain does use `t`.

**Verify a transform by measuring it, not by looking at it.** Best-fit a
centre-crop of the ungraded source against the processed frame across a range
of zooms: expected 1.19 / 1.00 / 1.17 / 1.21, measured 1.19 / 1.00 / 1.14 /
1.17. Two earlier eyeball checks on stills had passed a filter that was doing
nothing.

### The juice layer lives in ffmpeg, not Resolve

Resolve's Edit page has **no keyframe API for transforms**. `SetProperty`
writes a static value, numeric Fusion inputs refuse keyframes, and the only
animation reachable from Python is a Fusion expression on a tool input. So
smooth motion cannot come from the Edit page: the structural edit is built in
Resolve, rendered, and `engine/juice.py` applies punches, flashes and shake as
a finishing pass alongside the loudness pass.

Three traps, each cost a bad render:

1. **CLAMP THE EXPONENT.** `exp(-k*(t-C))` gated by `gte(t,C)` looks correct
   and is not — ffmpeg does not short-circuit, so the exponential evaluates
   anyway. At t=0 with C=39.861 and k=26, `exp(1036)` is **+inf**, `inf*0` is
   **NaN**, and a NaN brightness crushed the first 12.5s of a 51s clip to
   black. Always `exp(-k*max(0, t-C))`.
2. **ffmpeg 9 removed `eval` from `crop`.** Its `w/h/x/y` are flagged `T`
   (runtime-tunable) and evaluate every frame already; passing `eval=frame`
   fails with "Option not found". `eq` still takes it.
3. **zoompan wants `it`, not `t`** — its evaluator has no `t` and errors with
   "Undefined constant". `crop` exposes `t` and is the better tool anyway.

Tuned values: punch **0.16** decaying at 5.5/s (0.085 was present but
unreadable in motion), flash **0.07** (0.22 lifted luma 57→112, a blowout),
shake 5px at 11Hz on an emphasised caption. Measured flash lift is +13 to +16
luma over ~0.2s at roughly 4.7 cuts/min — far inside the WCAG 3/s cap.

### Clip 8 v8 — the re-cut

George: "extremely boring… the first part isn't about the second part… the
deadspace should be fully cut." All three were right.

**It was two narratives.** The subject line said it: "Reaction to a team
missing the partnership cycle **and** what it means for player job security."
The first 9s is the Global Esports announcement; everything after is an
argument about job security. The in-point moved to **8.85s**, where the
argument starts — which also dropped 4.2s of mute that sat in those 9s.

**Dead space cut.** Four removals over the new range, 6.9s. He asked twice;
the integrity caveat was recorded and overruled, and `tighten.joins()` printed
every splice. Absent audio fell from **19% to 1%**.

| | v6 | v8 |
|---|---|---|
| Duration | 67.2s | **51.5s** |
| Narratives | 2 | **1** |
| Absent audio | 19% | **1%** |
| Loudness range | 5.00 LU | **2.40 LU** |
| Motion | static per shot | punch + flash + shake |

The loudness range falling 5.00 → 2.40 is the same finding from the other
side: the range WAS the silence, and cutting the silence collapsed it toward
R2's 1.30 without touching a compressor.

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
