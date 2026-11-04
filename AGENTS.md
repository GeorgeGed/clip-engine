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

### The exit over-corrected in four ways, and every one is reversed

The section above found the real defect. The fix then went too far in four
places, and each is measured rather than argued:

| | shipped in v42 | now | why |
|---|---|---|---|
| Anticipation | 13px against the exit | **none** | Across every published exit curve in five systems — Material `(0.3,0,1,1)` and `(0.3,0,0.8,0.15)`, Carbon `(0.2,0,1,0.9)` and `(0.4,0.14,1,1)`, Atlassian `(0.6,0,0.8,0.6)`, Fluent `(0.9,0.1,1,0.2)` and `(1,0,1,1)` — **not one has a negative control point.** It spent 4 of 18 frames moving the wrong way, and its own first frame jumped **5.74px out of a dead-still hold (344 px/s)**: the jolt, relocated to the other end |
| Travel | 118px, shared | **half each card's own entrance**, 9–28px | 118px on a 1080 frame is a card physically leaving the canvas, which is literally what "jolting out of the frame" described. Atlassian pairs `SlideInTop8px` with `SlideOutTop4px` and `SlideIn50PercentLeft` with `SlideOut15PercentLeft` — every published exit travels half its entrance or less |
| Length | 18f for everything | **6 / 12 / 15f** | 18f (300ms) is longer than ANY published exit: Atlassian's ceiling is 200ms, Carbon's 240ms. Chip 100ms, card 200ms, paper 250ms, each against an entrance 1.5–2x its own exit |
| Scale + blur | 0.94 and 5px | **off** | The scale ran about `transformOrigin: 50% <top>` — the card's top EDGE — so on a 728px story card the centre drifted **21.8px UP while the exit travelled down** and the two partly cancelled. The 5px blur was isotropic, so it blurred across the travel axis too, and at ~6.5px/frame an honest motion blur is ~3px — *less* than what was there |

**A DARK CARD MUST NOT FADE.** Measured in `clip08_v42.mp4`: a fixed box
inside the KRU card goes 17.4 → 17.0 → 18.4 → 22.8 luma across the whole
0.3s exit — a change of 5.4 — because at 40–60% opacity the board's own team
rows read *through* the panel while the card's crop and marker still overlap
them. It did not leave, it dematerialised into mud for six frames. So a
chassis card stays **fully opaque** and a clip plane sweeps across it in the
exit direction, the exact inverse of the wipe its evidence arrives on. Paper
and stroked type still fade: a 15.6:1 card at 50% is unambiguously a card.

Opacity, where it is used, is **linear**. Material's fade pattern puts
opacity on `motionEasingLinear` and reserves the accelerate curve for
displacement; v42 shaped the fade as `(p−0.35)/0.60` raised to 1.3, which is
the one thing Google explicitly does not do.

---

### The dark glass panel had no surface — 1.08:1 — and that was the AI-ism

George: "the design is still very like AI looking in terms of the remotion …
I just think we could perhaps change the palette a little bit … I'd like this
to be something that we continue working towards as like a foundation."

**Measured against the real board pixels of the lower pane** (a 1080×600 crop
of `_base.mov` at t=34, per-pixel WCAG):

| surface | vs board, median | % of footprint ≥1.6:1 | % under 1.25:1 |
|---|---|---|---|
| old panel `#1A1E28` | **1.08:1** | 4.2 | **95.1** |
| new chassis `#413D36` | **1.67:1** | **94.1** | 1.1 |
| accent `#F4512A` | 5.21:1 | 98.2 | 1.0 |
| paper `#F4F1EB` | 16.02:1 | 99.2 | 0.5 |

The panel could not be seen, so four devices were bolted on to compensate: a
1px 9%-white hairline, a 28/64px shadow bloom, a 2px inset highlight and a
gold rule. **Stacked compensation is the signature; the panel was the
symptom.** With a surface that has an edge, all four are deleted — along with
the 4px radius, which was only ever softening a rectangle nobody could see.

**Two rules carry the palette, and together they dissolve "vibe coded":**

1. **Nothing coloured is ever a number.** The accent is a key bar, a marker
   stroke or a bar segment — structure, never data. Before, gold marked the
   eyebrow dash, the date chip, a chip border, the bar fill, the highlighted
   row, the sub-line, the status line *and* the emphasised caption — and its
   meaning **inverted between adjacent cards**: `PairCounter` made 274 gold,
   `RatioBar` made 32 gold, the same two numbers eight seconds apart. An
   accent on everything marks nothing. White figures also read *louder*:
   10.79:1 on the chassis.
2. **The accent never touches a photograph or paper.** Across the eight VCT
   press photos, 35.2% of pixels are saturated and **56.0% of those sit in
   the 0–15° band where `#F4512A` lives** (gold's 40–60° band: 2.8%). VCT
   stage lighting is red-magenta and Riot's own brand red is `#FF4655`, so
   this is structural, not an artifact of eight files.

Every ratio quoted here reproduces to two decimals against an independent
WCAG implementation. Two that are worth keeping next to the tokens:
`accent` and `accent2` are **1.06:1 — isoluminant**, which is acceptable on
`RatioBar` only because the hues are 206° apart on the blue/yellow axis and
bar LENGTH is the primary encoding. **Any pair encoded by colour alone must
separate by 15–20% in luminance.** And a slab moved above the seam is
fragile: 13.9% of facecam pixels sit within 1.25:1 of the chassis.

**A theme-only edit would have been WORSE than either palette** — a warm
chassis still wearing gold halos, a cool white press card, the marker in the
old orange and cool-grey chrome text. 50 colour literals were spread across
six component files with `theme.tsx` imported once per file for `ACCENT`
alone; every secondary grey was formula-derived `(n, n+8, n+24)` with no two
values reused, and `rgba(170,178,194,0.92)` in one file against
`rgba(170,178,194,0.95)` in the token is that defect in miniature. The grep
now returns **two** literals in the whole component set: a transparent
gradient stop and the marker's pen shadow.

### Type by ROLE, and Impact is the voice face — captions only

Everything ≥28px was Impact and everything ≤25px was Helvetica Neue:
**eighteen distinct Impact sizes**, nine of them (28/30/31/32/34/38/40/42/44)
doing one job, three of those within 2px of each other in three files. And a
44px Impact label carried the same optical weight as the figure above it.

**A sourced figure set in Impact looks like a meme caption**, which is why
the cards and the captions read as the same object. Figures and labels are
now **Archivo** (OFL-1.1, vendored with its licence in
`public/fonts/Archivo-OFL.txt`), which has `wght 100-900` **and**
`wdth 62-125`, so figure / label / context separate by weight and width
instead of by colour — and that is what frees the accent to mean one thing.
Four sizes: figure 150 solo / 96 paired, label 40, context 30, headline 52.
Tracking +0.4px on labels and nothing else; Riot's own production CSS has a
0.64px ceiling, against the micro-caps' 0.2–0.3em.

**`fontVariantNumeric: 'tabular-nums'` was a no-op on Impact.** Verified on
the file: Impact's GSUB carries only `locl` — there is no `tnum` — and its
digit advances span **780–1109/2048 upm**, so the counters visibly reflowed.
Archivo measures **575–577/1000, a 0.35% spread**, with a real `tnum`.
Checked and rejected: Oswald (no `tnum`, 378–517 spread), Anton (single
weight, no axes), Big Shoulders (no width axis). **Tungsten cannot ship** —
Hoefler&Co, licensed to one machine, not redistributable, no `tnum` (251–407,
a 62% spread), video-distribution terms unchecked.

The press headline is **Source Serif 4** (OFL-1.1, digits 500–500). It was
Helvetica Neue 800 at 42px with `letterSpacing: -0.8` — the most generic
headline setting on macOS, and the only lowercase text in the system, sharing
its family with every micro-label. Nothing else in the clip is a serif, so
one appearing reads as a publication rather than an overlay.

### MEASURE THE PNG, not the coordinate map

`rm_ExStrip` was going to be magnified 1.41x on the contiguous run holding
both its figures, with the run computed from `titles.STRIP_BLOCKS` and the
`BOARD_REGIONS["strip"]` crop. The first render showed the wrong two blocks
underlined.

Reading the ink columns straight off `crop_strip.png` instead: it holds
**four** blocks, not six — `32 open slots | 82 bench / options | 78 staff |
274 not yet confirmed` — and the two that matter are the **first and the
last**, at png x 19–178 and 729–988 of 1010. So the contiguous run containing
both is the *entire strip*, no magnification is possible without dropping
one, and stitching them would fabricate an adjacency the page does not have.

**So the card is deleted.** At 1.00x its tallest ink band measures 21px
against 88px captions — 4.2x smaller than the subtitle over it. A graphic
that holds the frame for 3.5s and cannot be read is decoration that looks
like evidence. `rm_Ratio` carries the identical pair 4.3s later as two solid
bars. Re-cropping from the source gains 4%: the strip is 670 source px wide
and that is the ceiling. `rm_Pair` lengthens 3.45s → 4.80s to take up the
slack, so the remaining ten graphics stay roughly one every 4.4s and **no
card moves off the spoken line it was anchored to.**

### The worst entrance in the clip was two numbers in a Python list

`rm_ExKru` ran `(33.20, 4.50)`, ending 37.70, against `rm_StoryPrx` at 37.60
— **six frames of overlap on V4, and those six frames were ExKru's exit.**
Resolve resolves the collision by trimming the LATER clip's head, so the
biggest graphic in the clip slammed on in one frame at ~70% opacity: luma
23.6 at t=37.683, 165.0 at 37.700, 227 by 37.750. `rm_Pair` against
`rm_ExStrip` was the same bug, one frame, masked by the dip at 14.80.

A card that animates out over 12–15 frames cannot have those frames trimmed
away by the schedule, so `check_schedule()` now asserts
`prev_start*60 + prev_FILE_frames + 6 <= next_start*60` for every adjacent
pair before `AppendToTimeline`, and raises naming both clips. It uses the
ffprobe count `add()` already fetches, not the scheduled duration — those are
the two numbers that drifted apart, and the file is the one Resolve places.

### An odometer ticks per DIGIT TURN, so the times invert the count curve

Four of nine ticks were firing **after the number had stopped**. The tick
loop was `0.14 + 0.80*(1-(1-p)**2)` against `PairCounter`'s `1-(1-p)**3`,
offset by 0.04s: the digits reached 274 at 0.783s and ticks 5–8 landed at
0.828, 0.890, 0.928 and 0.940s — the last two 12ms apart, which is a buzz,
on a frozen frame.

Ticks are a digit turning, so they are evenly spaced in VALUE, not in time:
`p = 1 − (1−k/8)^(1/3)`. Measured gaps **33, 37, 41, 47, 56, 70, 99 then
384ms** — they *spread* as the number settles, which is what "thinning as it
eases out" always meant, the last one lands exactly on the final digit, and
the whole run tracks the card automatically if it is re-timed.

**A side tab gets no cue.** `rm_ChipAmer` at 1.20 took the thunk and the
2.4s dedup then swallowed `rm_Tweet` at 3.30 — so the clip's first real
exhibit arrived silent while a 1.8s chip announced itself.

### 73% of graphic screen time was a frozen frame

Frames between entrance settle and exit start, per card: ChipAmer 63, Tweet
161, StatCard 160, Pair 140, ExStrip 160, Ratio 148, ExNrg 175, Grid 165,
ExKru 184, StoryPrx 206, StorySen 191 — **29.2s of 39.8s dead still**, with
the identical rhythm eleven times: in, ~2.8s frozen, out. A PNG held for
three seconds is what a viewer reads as a template.

`motion.useHold()` returns 0→1 across that span. Chassis panels drift
`translateY` **+6px linear** (2px/s — below the threshold where movement is
noticed, above the one where a frame looks dead); evidence crops push to
**scale 1.012** with y −7, a slow move into the document; chips and the hook
line get **zero**, being too short and sitting over a moving face. This was
specified once already — `overlays.exhibit_reveal` drifted ~9px while held
"so a 3.5s card is never a still frame" — and the React rebuild dropped it.

### Every graphic also ENTERED the same way

Measured across all seven spring configs: zeta 1.061–1.344, **peak exactly
1.0000 in all seven**, f50 7–8 frames, f90 15–17, settle 29–32. Not one
overshoots, and the "different" configs (damping 15/mass 0.5 vs 16/0.48 vs
16/0.46 vs 17/0.4) are within 2 frames of each other at every checkpoint —
the same curve with decorative variation. Travel 34/30/26/26/28/28/26/30/38/
38px. Eleven graphics that all arrived by rising about 30px.

Four classes now, keyed to what the object **is**, not which file it is in:

| class | who | entrance |
|---|---|---|
| **EVIDENCE** | `ExhibitFrame`, `TweetCard` | no rise. scale 0.78→1.00 over 22f on ease-out-back, **blur 9→0px**, travel from `fromX` (the horizontal position of the region it was cropped from), `clip-path` wipe at 2–18f. All four were in `overlays.exhibit_reveal` and all four were dropped in the React rebuild |
| **FIGURE** | `StatCard`, `PairCounter`, `RatioBar` | panel `translateY` 18→0 ease-out-quint 12f, then the figure lands **separately** at f8 on `{stiffness:160, damping:12, mass:0.34}` — zeta 0.813, the only overshoot |
| **PAPER** | `NewsStory`, `TweetCard` tilt | rotation on `{stiffness:120, damping:11, mass:0.7}` — zeta 0.600, peak 1.0947 — so −3.4° arrives via −4.4° and settles |
| **CHIP** | `StatChip` | `translateX` 56→0 over 9f ease-out-expo, **no opacity fade at all** — a tab slides, it does not materialise |

`Easing.quint` **does not exist in Remotion** — the class has
`poly(n)`, `quad`, `cubic`, `sin`, `circle`, `exp`, `elastic`, `back`,
`bounce`, `bezier` and the `in`/`out`/`inOut` wrappers. Passing it gives
`TypeError: easing is not a function` at render, not at build. Use
`Easing.out(Easing.poly(5))`.

### The card geometry was drift, not intent

Six radii (1/2/3/4/5/999), three near-miss shadow stacks (30 vs 28px blur,
0.92 vs 0.85 alpha — one decision typed twice, plus a third at 66px), eleven
padding shorthands with eight horizontal insets, nine left edges, seven tops
and eleven widths across eleven graphics with four tops inside 40px of each
other. 864 vs 884 vs 814 is one width typed three times.

`theme.tsx` now carries `WIDTHS = {full: 1008, mid: 816, narrow: 624}` on a
36px margin, `SLOT = {top: 1000, bottom: 1600, centre: 1300}`, `PAD = {card:
28, tight: 20, chip: 14}` and `RADIUS = 0`. **Every card centres on y 1300**,
verified off the alpha bounding box of its own render rather than estimated.

**`NewsStory` was 103px past the platform-UI line and then exited into it.**
At `top: 975` with 650px photos it bottomed out at 1703. The tilt allowance
had never been computed either: a 1008-wide card at 3.4° lifts its raised
corner `w·sin(tilt)` = 60px above its stated top, which is how `top: 975`
rendered at 944 and how the captions clipped it. Measured body now 1002–1596.
It exits **up**, never down.

**Measure the card BODY at alpha > 250, not alpha > 8.** The paper shadow
spreads 56px, so a plain bounding box reported the story card as 629px tall
and overflowing when the card itself was 566 and fine.

### Licences — three corrections to what this file already says

* **`av/remotion-bits` is in the tooling adopt column of this file and must not be.** It has
  **no LICENSE file of any name** on its default branch (`master`, not
  `main`) and none in the 0.2.1 tarball's 294 files, despite an MIT field in
  `package.json`. Move it beside `remotion-bar-race`, `lygia` and
  `pv-tools` — and note its component vocabulary (glitch-cycle, matrix-rain,
  counter-confetti, ken-burns, typewriter, particle fountains) *is* the tell
  catalogue.
* **`@remotion/transitions` declares `"license": "UNLICENSED"`** in both npm
  and the source repo — an explicit reservation of all rights, worse than a
  missing field. It transitively disqualifies 31 of Remocn's 286 registry
  items. `@remotion/animation-utils` has **no `license` key at all**. The
  first-party packages that genuinely are MIT: `captions`, `paths`, `shapes`,
  `fonts`, `media-utils`, `noise`, `layout-utils`. **Check the field per
  package** — everything else is `SEE LICENSE IN LICENSE.md`,
  `Remotion License` or `UNLICENSED`.
* **Adobe Leonardo is Apache-2.0 but hard-depends on `apca-w3`**, whose
  licence reads "All Rights Reserved… Patent(s) pending" and grants use "for
  web-delivered and web-based content only". A 1080×1920 clip composited in
  Resolve is not web-delivered content. A check that stops at the repo's own
  LICENSE waves this straight through.

**Go to the npm package or the generated token file, never the marketing
site.** Reading `atlassian.design` is how an earlier pass recorded Atlassian
as having no licence when the package ships Apache-2.0.

### Two commercial gates, and neither is a code problem

1. **Remotion's licence is seat-gated.** `LICENSE.md` read in full: the Free
   Licence covers an individual, a for-profit organisation with **up to 3
   employees**, a non-profit, or evaluation. Above that a Company Licence is
   required, and the gate covers `cli`, `renderer`, `bundler`, `player`,
   `media-parser` and `webcodecs` — the entire render route. Commercial video
   *output* is permitted within the free tier. **This is a headcount
   question and it needs an answer before the next delivery.** Pin 4.0.390;
   the file says the terms change at 5.0.
2. **Riot's community-use licence is noncommercial for business entities.**
   §2: "You may not create commercial Projects, including any Project that
   involves a business or legal entity… without a written license agreement
   from us." §5 on logos and marks: "No… Unless you have a written license
   agreement with us." The written photo permission recorded above covers the
   Flickr photos; **confirm in writing whether it extends to the VCT roster
   board, broadcast frames and marks in paid client deliverables.** This also
   closes the team-logo blocker as unobtainable by default.

### Still open, with what would settle each

* ~~The pane dip has to be re-solved against the new chassis.~~ **SETTLED:
  the dip is removed** — it punctuates nothing, and the pixel test that
  looked decisive does not discriminate. See above.
* ~~The three-act CDL arc was tuned against dark overlays.~~ **SETTLED:
  re-solved against a white in his own room; the white-point swing across
  the clip goes 48.0 → 5.9 points.** See above.
* **Warm paper vs cool.** Both real documents in the clip measure cool — the
  board at hue 218, the tweet's brightest 15% at hue 220 — so `#EFF1F5` may
  have been right. Render one `StoryPrx` at each over the real t=37.6 frame
  and look; the card stays 9.57:1 from the chassis either way.
* **Type behind the speaker from a person matte.** Still the one genuinely
  strong untried technique, and still risky for the same specific reason: the
  facecam is a 464px-wide region upscaled 3x, so the matte comes off soft
  pixels and there is little headroom above his head.

### The captions are half the palette, and they were built by hand

The first v43 render shipped warm graphite cards with vermilion accents and
**gold captions**, because `cap_kin.mov` had no build script — it was a shell
command typed in an earlier turn, so the palette change could not reach it.
A card set and a caption set that disagree about their accent read as two
videos stacked on each other, which is the hybrid this work existed to avoid.

`build_captions.py` now renders it, with `ACCENT = (244, 81, 42)` matching
`theme.tsx` — one value, two renderers. **The style is untouched**: Impact,
88px, emphasis 1.27x, 9.5% hard black stroke, critically damped, white fill,
riding the seam at y 0.44. George picked that after four style versions and
only the accent moves.

The emphasis has to survive its own stroke over both backgrounds, and that
is the test the newsprint palette failed at 3.15:1. Measured: `#F4512A` is
**6.06:1 against hard black**, against gold's 14.08:1 — lower, and well over
the 4.5:1 floor, on 16 of 117 cards set at 1.27x.

Verified on the delivered file by sampling a frame every 0.17s: **685
gold-family pixels in 36.4 million, no frame holding more than 40** (what is
left is G2's own brand tab on the board), against 360,861 accent pixels in
199 of 281 sampled frames.

### What v43 measured

| | v42 | v43 |
|---|---|---|
| Peak frame-to-frame change at the out-points, mean | 17.11 | **8.24** (−52%) |
| …excluding the ExKru collision | 8.14 | **7.01** (−14%) |
| Share of an out-point's change in its single worst frame | 12.3% | 14.5% |
| Black frames, per-frame YMAX, both panes | — | **none** (top min 241, bottom 152) |
| Colour literals outside `theme.tsx` | 50 | **2** |
| Graphics | 11 | 10 |
| Loudness | −14.13 LUFS / −0.56 dBTP | −14.13 LUFS / −0.74 dBTP |

**Be honest about the second and third rows.** Most of the −52% is the
scheduling collision; the exits themselves are a further −14% on a v42 that
had already fixed the big problem. And the *concentration* went slightly UP,
because the exits are now 12–15 frames where v42 used 18 — the same change
spread over fewer frames. Shorter exits with a lower peak is the trade the
published durations ask for, and both numbers belong in the record.

**Measure the pane with `signalstats`, not `scale=1:1`.** A 1×1 downscale
point-samples under the default bicubic flags: it reported the content pane
at mean 3 where the real frame measures 22.2, and it invented 270 "black"
frames that do not exist. `signalstats` YMAX per frame is the honest read,
and `crop` first so one pane going dark is not hidden by the other.

**The odometer, verified in the bed:** gaps of 33, 37, 41, 47, 56, 70, 100
then 383ms, spreading as the number settles. Cue peaks referred to the
master: seven thunks at −14.3 dBFS, two shutters at −15.2.

### R5: the chat-overlay reference, and what the test found

George sent a Short — AloneVal's "Is NRG Ethan THE GOAT of VCT? FNS
Explains" — and asked for a test: find that part of the stream, overlay the
streamer's chat so you can see the reaction, animate it in the lower half.
**This is also the first reference in the heavily-produced style the file
has been asking for since the "what this project needs from George" list.**

| | **R5** |
|---|---|
| Duration | 32.2s, 1080×1920 @60 |
| Seam | **0.485 (y 932)** — a taller facecam than R1/R2's 0.42 |
| Lower pane | the streamer's own Twitch chat, replayed |
| Chat card | x 212-865 (654 wide), top ~1055 to the frame bottom; near-black, ~64px top radius, over a **cyan plate with square corners** so two triangles of colour show at the shoulders |
| Type | ~54px geometric sans; line pitch **68px**, message gap **43px**, so a one-line message occupies 111px |
| Rate | ~75 messages/min |
| Captions | in the band between the seam and the card, same white-on-heavy-stroke treatment |

**THE CHAT DOES NOT SCROLL, AND THAT IS THE WHOLE POINT.** Correlating
successive frames of the chat column, the stack moves in exactly ONE frame
per message, by a whole message height — measured jumps of 110, 178, 206,
220 and 240px, with a post-shift residual of 2.0-2.9, i.e. the new state is
already fully formed. Ten jumps in eight seconds, no intermediate frames
anywhere, no fade on the arriving message. That is how Twitch's own chat
renders, and it is why the reference reads as chat rather than as a
graphic. **An eased scroll would be the tell.** Build it instant.

#### 1. Finding the moment — the method works, this VOD is gone

The Short was uploaded **11 July 2026** by a clips channel. FNS's oldest
surviving VOD is **4 September**, exactly **59 days old** on 2 November. So
the archive is a rolling ~60-day window and the source stream fell out of it
around 9 September. **It cannot be found, and neither can its chat.**

**CHAT REPLAY IS PERISHABLE — it dies with the VOD.** That is the binding
constraint on this whole feature, not the API. A chat overlay has to be
built within ~60 days of the stream, or from chat captured live at the time.
Worth saying to George directly: if he wants chat on clips, the chat has to
be pulled while the VOD is still up, as part of ingest, not at edit time.

What does work, for anything inside the window:
- **Helix `Get Videos`** lists what still exists (28 VODs, 4 Sep onward).
- **Clip DENSITY beats clip titles.** Viewer-written titles are useless
  ("davai", "something goat", "how."). Bucketing `vod_offset` into 120s
  bins and ranking by count + views found the real crowd moments —
  17 clips in one 2-minute bucket.
- **Chat is the cheap search index.** One GQL call covers ~75s, against
  transcribing 5-hour VODs. Searching chat text for a reaction burst is
  roughly 100x cheaper than searching audio for the line that caused it.

#### 2. Chat replay — reachable, and the old note here was wrong

See `engine/twitch_chat.py`. The 2026-10-29 note said VOD chat was not
reachable; it had tested one abandoned package with a rotated persisted
hash. The endpoint returns text, offsets, user colours, badges and emotes.
**Address pages by OFFSET, never by cursor** — the cursor follow-up returns
`IntegrityCheckFailed`, which looks exactly like a rotated hash and is not.

Badges come from Helix (`Get Global Chat Badges` + the channel's own); this
window needed 14 of the 434 sets.

#### 3. The overlay — built, and the measurement that says when to use it

`src/Chat.tsx`, `build_chat.py`. Two things it gets right:

**Anchor to SOURCE time.** A message happened at a VOD second; the cut
removed 15 dead spans, so output seconds are not source seconds.
`build_overlays.at()` remaps through the same keeps `build_v7.py` used.
Messages landing inside a removed span are **dropped, not nudged** — a
reaction on the wrong line is worse than a missing one. On clip 8: 41 of 48
mapped, 7 dropped.

**Open mid-flow.** Messages from before the in-point get negative times so
the card is already half full at frame 0. A chat panel that starts empty
and fills up reads as a graphic booting, not as a stream you joined.

**AND THE FINDING THAT MATTERS MOST: measure whether the chat is actually
REACTING.** Clip 8's window runs 43 messages/min against the reference's 75,
and only **24% mention the clip's subject at all**. Reading them, they are a
Q&A queue — "are nrg partnered??", "who would you bring in?", "will u watch
nations world cup?" — people asking FNS questions during a casual stream,
not reacting to his job-security argument. R5's chat is the opposite
("ethan does everything ngl guy shoots, guy calls", "nrg have to watch out
for loverscock and lacock"): it is responding to the thing being said.

So a chat overlay is **not a treatment you apply to a clip, it is a property
of the window.** `build_chat.py` prints the on-topic share before anything
renders, and that number belongs in clip selection: a window with reacting
chat is a better clip than one without, and the same measurement says
whether the overlay is worth building at all. Clip 8 scores badly and is a
poor candidate — which the test demonstrates rather than hides.

**One thing our source cannot do.** R5's facecam fills 1080×932, an aspect
of 1.16:1 — a near-square crop of the streamer's webcam. Ours is a 464×262
region of the VOD frame, already a 3x upscale to fill 1080×806; cropping to
1.16:1 would mean taking 304×262 and blowing it up 3.55x. The seam stays at
0.42 and the chat card goes below the captions instead.

## The thirteen tools George sent — licence first, then against a REAL gap

Every licence read from the repo's own LICENSE file, because this file has
recorded three traps where the GitHub field or the marketing page was wrong.

| tool | licence | verdict |
|---|---|---|
| **rembg** | MIT | **ADOPT** — the person matte |
| **Real-ESRGAN** | BSD-3 | **ADOPT** — the soft facecam |
| **librosa** | ISC | **ADOPT** — onset detection |
| **PySceneDetect** | BSD-3 | **ADOPT** — content-change cuts |
| **HyperFrames** | Apache-2.0 | **CORRECTION — it is not unavailable** |
| auto-editor | Unlicense | read it; do NOT adopt its policy |
| demucs | MIT, **ARCHIVED** | no current need |
| RIFE | MIT | no current need |
| vid.stab | LGPL-2.1+ | not needed — a webcam does not shake |
| color-matcher | **GPL-3.0** | care: copyleft |
| OpenMontage | **AGPL-3.0** | read, never copy |
| FFmpeg | LGPL-2.1+ | in use |
| yt-dlp | Unlicense | in use |

**THREE OF THEM LAND ON GAPS THIS FILE HAS ALREADY WRITTEN DOWN**, which is
the only reason to take them:

* **`rembg` (MIT) -> the person matte.** "Type behind the speaker from a
  person matte" has sat in *Still open* as "the one genuinely strong untried
  technique" across many versions, unbuilt because it needed a matte. The
  recorded risk stands and is now testable rather than theoretical: the
  facecam is a 464px-wide region upscaled 3x, so the matte comes off soft
  pixels, and there is little headroom above his head.
* **`Real-ESRGAN` (BSD-3) -> that same softness.** This file says of the
  facecam: *"The facecam is a 3x upscale of a 464px-wide region, so it is
  soft. That is what the source gives; a bigger facecam on stream would be
  the only fix."* **That conclusion is now wrong** — a super-resolution pass
  on a 464x262 crop before it reaches Resolve is exactly the other fix, and
  it would improve every clip from this channel. Worth a measured A/B on one
  shot before it goes near the house build.
* **`librosa` (ISC) -> onset detection, which was hand-rolled TODAY.**
  `_snap_in_point` is a 5ms RMS envelope, a sustained-trough search and an
  onset test, written from scratch and debugged through two wrong versions
  (a transient inside a word; a too-loud onset threshold). `librosa.onset`
  is the maintained version of exactly that. Not urgent — ours is measured
  and works — but the next audio-timing problem should start there.

**HYPERFRAMES: THE RECORDED FINDING IS WRONG AND SHOULD BE STRUCK.** This
file says *"HyperFrames is unavailable: `npx hyperframes usage --json`
returns `unsupported_auth` — it needs George's account."* That tested the
HOSTED USAGE endpoint, not the renderer. The repo is **Apache-2.0, 78k
stars, pushed today**, and its own README says *"Render locally or in
Docker. The renderer seeks each frame in headless Chrome and encodes the
result with FFmpeg"* — which is the same architecture as our Remotion route
and has **no seat gate**, unlike Remotion's headcount licence. Its skills
are already installed in this session. **Same mistake as the Twitch chat
note: a dead client is not a dead capability.** Whether to move off Remotion
is a real question now, not a blocked one.

**The two copyleft ones, stated precisely because the distinction decides
them.** `color-matcher` is GPL-3.0 and `OpenMontage` is AGPL-3.0. Copyleft
attaches to the SOFTWARE, not to a rendered mp4, so running either locally
to produce clips is fine and always was. What they reach is this repo if
their code is imported, and for AGPL also any service clients interact with
over a network — which is the exact shape "agency as a service" would take.
So: run them, read them, never paste from them.

**`auto-editor` is the one to read and not adopt.** It cuts silence
automatically, which is the headline feature this file has refused twice:
on a DMCA-muted VOD *dead air is not dead, it is speech you cannot hear*,
and 35.8% of this VOD's audio is absent. Its silence DETECTION is worth
reading against ours; its default POLICY would splice across unheard speech
on almost every clip in this job.

## ONE CLIP SHIPPED WITH ANOTHER CLIP'S CHAT ON IT

George, on clip 12: *"the chat kind of dies at the end for some reason."*

Clip 12 has **no chat overlay** — the topicality gate measured its chat at
13% on-topic and refused it, and `overlays_12/` contains no `rm_Chat.mov`.
The delivered file carried a chat box anyway, for 0-38.25s, and then it
stopped.

**It was CLIP 6's chat.** `overlays_06/rm_Chat.mov` is 2298 frames = 38.3s,
which is exactly where it died.

`stage_assemble` built its lookup as `{c.GetName(): c for c in
mp.GetRootFolder().GetClipList()}` — **keyed by FILE NAME**. Every clip
writes `rm_Chat.mov`, `cap_kin.mov` and `sfx.wav` into its own directory and
they all land in one shared Resolve media pool, so at the time of the build
the pool held **five `rm_Chat.mov` entries and seven `cap_kin.mov`**, and
the dict kept whichever was added last. Clip 12 added no chat of its own, so
the lookup silently handed it clip 6's.

What shipped was real viewers' messages from a different part of the
stream, timed to lines they were not written about. Nothing failed, nothing
warned, and every gate passed — the delivery QC checks black frames,
loudness, captions and dead space, and none of those notice that the
overlay belongs to another clip.

**Match the pool by RESOLVED FILE PATH, never by name.** `GetClipProperty
("File Path")` on each item, compared against the paths actually added.
Missing now raises rather than falling through.

The captions were right ONLY BY LUCK: clip 12 did render its own
`cap_kin.mov`, so it was added last and won the same collision.

**This is the third defect in two rounds that a single clip could never
have exposed**, after the MarkIn offset and the stale `_cut.wav`. Building
one clip well says nothing about building the second.

## George's three notes on clip 12

### "A bit too long ... make it compact" — the lever is CONTENT, not pauses

Dead space was already at 1.9%; there was nothing left to tighten. The clip
ran 59.4s with its claim arriving at **15.7s**, behind a long anecdote about
taking five modes of transport to a LAN. `in_point` moves to **23.30**,
which is the word "you" in *"you guys have it good now man"* — the setup —
so the claim lands at once. **59.4s -> 46.8s.**

`Clip.out_point` is added for the same job at the other end. It is used
less, because the payoff is normally last (clip 12's is the final line), but
without it the only lever on length was the front.

### THE SNAP MOVED PAST A CORRECT IN-POINT, and the distance is the tell

`_snap_in_point` only ever moves FORWARD, so when the requested point is
already a real word START it marches past that word to the trough on its
far side. Asked for 23.30 it returned **23.835** — "you" ends at 23.82, so
it ate the word the line opens on.

A word TAIL is short and a whole word is not:

| | requested | nearest trough | distance | right answer |
|---|---|---|---|---|
| clip 6 | 2.02, inside the /s/ of "this" | 2.215 | **0.195s** | snap |
| clip 12 | 23.30, the start of "you" | 23.825 | **0.525s** | leave it |

`SNAP_MAX = 0.35`. Beyond it the requested point is treated as deliberate.
Clip 8 (0.03s) and clip 6 (0.205s) are unaffected.

### THE VINE BOOM, and why it is set by RMS

George supplied the file and asked for it *"on a zoom for dramatic effect"*.
**This is the first real sample in the palette** — every other cue is
synthesised, and "a licensed SFX library" has been an open blocker here for
many versions. Rights: a meme sound of uncertain provenance, chosen by him,
and not a licensed library.

Measured, because it behaves like nothing else in the palette:

| | duration | crest | centroid | energy <200 Hz |
|---|---|---|---|---|
| shutter | 82ms | 22.0 dB | 11460 Hz | — |
| paper | 260ms | 16.9 dB | 2007 Hz | — |
| **vine_boom** | **1185ms** | **7.7 dB** | 880 Hz | **50%** |

**The crest decides the method.** This file's rule is that a CLICK is set by
PEAK, because a click is almost all peak and no RMS — that is why
`cue_gain_peak` exists. The Vine Boom is the exact mirror: dense, low and
sustained at a 7.7 dB crest, the lowest in the palette by 4 dB. Setting it
by peak beside the shutter would put its RMS far above everything else.

So it is set by RMS — and then **checked against the other cues' peaks**,
which is what caught the first value. -26 dBFS RMS put its peak at **-18.3
in the master**: quieter in peak than every cue this project has accepted
(shutter -10.4, thunk -14.3) and 17.5 dB under the speech, where 13 dB is
the recorded figure for "low". A sub-heavy hit also needs more level than a
mid one to read as equally loud. **-21.0 RMS lands the peak at -13.3**:
above the thunk, below the shutter, under the speech.

**PUNCH NOW RUNS BEFORE ASSEMBLE.** A cue on a zoom needs the zoom's time,
and the punch plan only exists once that stage has run. The two touch
different tracks — punch rebuilds V2, assemble clears V3+ and A2 — so the
order was free. Verified on the delivered file: the facecam pane's
frame-to-frame delta at each boom is 37-51 against a median of 0.25, so all
three land on a real cut.

**And the same partial-run bug appeared a second time.** `punch_starts`
lived only in memory, so `--only assemble,render` produced `cues: 0` and
three silent booms. It reads `punches.json` off disk when the stage did not
run, exactly as the chat windows now do. Worth generalising: **any value one
stage computes and another consumes has to survive on disk**, because a
partial run is the normal way this pipeline is driven and `cues: 0` is not
loud enough to notice.

## THE PRODUCTION LINE: `batch.py`, and what the yield actually is

George: *"the main thing is essentially making these en masse, build the
full pipeline for developing this."*

    batch.py <job> screen   # which clips can be cut at all
    batch.py <job> prep     # words, chat, facecam — everything before Resolve
    batch.py <job> specs    # topic dedup, then one spec per clip
    batch.py <job> build    # serial, gated on the artifact, resumable
    batch.py <job> report   # the manifest

Four things shape it, and none of them is throughput:

**1. THE YIELD IS 10 OF 50, AND THE SCREEN IS THE POINT.** Measured across
every clip of this VOD: forty are rejected, almost all for DMCA muting at
20-55%. Ranking by virality picks clips the pipeline cannot cut, so nothing
downstream runs until `screen` has had its say.

**2. FIVE OF THE TEN SURVIVORS ARE THE SAME TOPIC** — clips 06, 15, 23, 30
and 42 all argue open qualifiers against franchising. Shipping them is
shipping one idea five times, which is worse for a channel than shipping
two clips. `specs` groups by topic and keeps the strongest of each group.

**3. RESOLVE IS ONE GUI APP, SO BUILDS ARE SERIAL.** Its API is served on
the GUI thread and Remotion's `public/` is shared, so two clips cannot
render at once. Everything cheap — transcription, chat, facecam — runs in
`prep` ahead of time, and each build is independent so a failure costs one
clip, not the run.

**4. EVERY CLIP IS GATED ON THE ARTIFACT**, by `engine/deliver_qc`, and a
clip that fails goes in the manifest with the reason instead of the
delivery folder. The channel also has to carry a `permission` or the build
refuses to start.

**The gate caught itself being useless, which is the reason to test a
gate.** Its first version reported `PASS ... black_top 0 frames` — because
`metadata=print` writes at INFO level and `-v error` silences it, so the
regex matched nothing and a check that measured NOTHING read as a pass. It
also read duration from the wrong key and reported `9e7 cards/s` as a
warning rather than noticing it had been handed nothing. Both now raise.

### THE ONE-NARRATIVE RULE APPLIES TO EVERY CHANNEL, NOT JUST THE AUDIO

**The worst thing found this round, and it was in a clip already
delivered.** An adversarial pass on clip 6's editorial decision reported
that the editor "checked the TRANSCRIPT and never checked the LOWER PANE".

Measured on the delivered file: of the 52 chat messages visible in the cut,
**4% are about open qualifiers and 29% are about an unrelated
Sentinels/Oxy roster transfer**. In the first 19 seconds it is **0 on
subject against 11 on the other story** — a viewer reads *"who is SEN
kicking?"* and *"oxy is out the jail"* while he rants about qualifier tech
problems. The content pane behind the chat is a Reddit thread headlined
"Sentinels Set to Add OXY", the same other story.

So the audio was the only channel telling the clip's narrative, and the
in-point work that made the audio one narrative had no effect on the other
two. A clip now carries three narrative channels — what he SAYS, what is on
his SCREEN, and what CHAT is saying — and the rule has only ever been
enforced on the first.

**AND THIS FILE ALREADY KNEW, AGAIN.** It records "a chat overlay is not a
treatment you apply to a clip, it is a property of the window", measured on
clip 8 at 24% on-topic. Nothing gated on it, so clip 6 shipped at 4%. Same
shape as the hallucinated captions: **a note is not a gate.** That is now
twice in two rounds, and the lesson is to write the check, not the
paragraph.

`chat_reaction.chat_is_safe()` derives keywords from the clip's own subject
and claim, so it cannot drift from what the clip is about. The floor is 15%,
set between the two measured points — clip 8 at 21-24% shipped and was
accepted repeatedly, clip 6 at 9% is wrong. Across the ten buildable clips:

| chat OK | no chat |
|---|---|
| 30 (41%), 42 (24%), 08 (21%), 04 (16%), 23 (16%) | 15 (14%), 12 (13%), 06 (9%), 43 (8%), 16 (6%) |

**Half the clips cannot carry the chat overlay.** That is a real constraint
on the format, not a bug: the overlay only works where the room is talking
about the thing he is talking about.

Still unchecked: the LOWER PANE's own narrative. Clip 6's Reddit headline
is legible behind the chat for the whole clip. Nothing measures what the
content pane says, and on a clip whose source is a browser that is a third
channel that can contradict the other two.

### OpenMontage (AGPL-3.0) — read it, do not copy from it

George sent `calesthio/OpenMontage`, 75k stars, a 2209-file agentic video
system. **Licence read from the LICENSE file, not the GitHub field: it is
AGPL-3.0**, and that is the first thing about it.

* **Using it to MAKE videos is fine.** Copyleft attaches to the software,
  not to a rendered mp4 — the same way a compiler's licence does not reach
  its output.
* **Copying code from it into this repo is not.** AGPL would reach this
  pipeline, and on an agency tool that is a decision about the whole
  business, not a dependency choice. So this is read for TECHNIQUE —
  measurements and ideas are not copyrightable — and nothing is pasted.
* **Running it as a service clients touch triggers the network clause**,
  which is the specific thing AGPL adds over GPL and the specific shape an
  "agency as a service" would take.

What is worth taking, all of it independent of its code:

* **`clip-factory` is our exact problem** — "takes long-form content and
  produces multiple short clips, N independent deliverables from a single
  source", with quality gates on "clip selection, batch consistency, and
  hook placement". Its structure (serial stages, quality gate after each,
  bounded send-backs) is what `batch.py` arrived at independently.
* **A BATCH NEEDS A MIX OF CLIP TYPES, not just distinct topics.** Its idea
  director names five families — hook, insight, story, proof, opinion — and
  says "a good batch mixes clip types instead of extracting the same energy
  repeatedly". Our topic dedup catches five clips arguing one subject; it
  would NOT catch ten clips that are all `opinion`, which is roughly what
  this VOD is. Worth adding to `specs`.
* **Its yield guidance matches ours.** "60+ min: 8-15 strong clips if the
  source quality supports it" against our 103-minute VOD yielding 10
  buildable. A useful outside check that the yield is not pathological.
* **"Each clip must make sense alone. No 'as I was saying' openings."** —
  our rule 3, independently arrived at, which is mild corroboration that
  the rule is real and not a local habit.

## AN IN-POINT ON A WHISPER WORD BOUNDARY LANDS INSIDE THE PREVIOUS WORD

George, on clip 6: *"it needs to start a tiny bit later because we hear a
little fragment of his former word."*

Whisper's word timings are CONTIGUOUS — the median inter-word gap on this
clip measures **0.000s** — so every boundary it reports is a guess placed
somewhere inside the join, not an onset. Setting `in_point` to one is
therefore a coin flip on whether the previous word's tail comes with it,
and a FRICATIVE is the worst case because it sustains.

Measured at 5ms resolution around clip 6's `i've @ 2.02`:

| | |
|---|---|
| 1.935-2.025 | the vowel of "this", peaking **-11 dB** |
| **2.025-2.210** | sustained **-20 to -25 dB** — the /s/ of "this" |
| 2.210-2.470 | the real gap, down to **-39 dB** |
| 2.475+ | "I've", softly |

So 2.02 opened the clip on **0.19s of a trailing fricative**, which is
exactly what he heard. Confirmed by transcribing both candidates: cutting at
2.02 and at 2.42 BOTH return *"I've said this on every single stream"*, so
the span dropped is entirely tail and costs no speech.

`make_clip._snap_in_point()` advances any in-point to the next real trough.
Two things it took two attempts to get right:

1. **THE TROUGH MUST BE SUSTAINED.** Taking the first sample under the
   threshold caught a 10ms dip *between the vowel and the fricative of the
   same word* and snapped to 2.025 — still inside "this". A real word gap
   holds; a transient inside a word does not. 60ms of hold separates them.
2. **SNAP TO THE TROUGH, NOT TO THE NEXT ONSET.** Hunting the onset needs a
   loudness threshold, and the word after a pause is often quiet: a 5x-floor
   test skipped the softly-spoken "I've" (peak 0.024 against a 0.004 floor)
   and landed on "said" 0.14s later — cutting the word the clip was meant to
   open on. The trough IS the boundary and is unambiguous. The pause in
   front of the next word is then the dead-space pass's job, which already
   trims it to a beat.

Clip 6: 2.02 -> 2.225, moved 0.205s. Clip 8: 8.85 -> 8.88, moved 0.03s — its
in-point was already clean, which is the check that this does not disturb a
good one.

## WHISPER HALLUCINATES OVER A MUTE, AT p = 1.000 — AND WE BURNED IT ON SCREEN

**The worst defect this project has shipped, and it was found by accident.**
An adversarial pass asked whether FNS was answering a chat message kept
reporting that the line it turned on does not exist.

Measured on clip 6's source with `qc.dead_audio(min_run=0.1)`: digital zero
at **36.086-36.773 (0.687s)** and **37.437-38.146 (0.709s)**, about -113
dBFS against speech at -19. Whisper placed **"agree" at 36.240-37.000 and
"we" at 37.000-38.020 across them, with confidence 1.000 and 0.999.** So
1.40s of the 2.80s it renders as *"i agree we agree on this"* is silence —
and the delivered clip burned those words on screen as captions.

A caption is read as a verbatim quote. This breaks the oldest rule in this
file (nothing on screen is a phrase nobody said) and it is worse than an
invented card, because an invented card at least announces itself as a
graphic.

**WHISPER'S CONFIDENCE IS WORTHLESS HERE.** It is *highest* exactly where
there is nothing to transcribe. The audio is the check, not the model.

`make_clip._drop_hallucinated()` removes any caption card whose own span is
more than 50% digital zero. Measured:

| | cards | dropped | the clip |
|---|---|---|---|
| clip 6 | 99 | **3** — AGREE (70% silence), WE (62%), IT (67%) | 7% absent |
| clip 8 (v51, SHIPPED) | 117 | **8** — I, LIKE, KIND, IT'S, BUT, THEN, SO, YOU | 22% absent |

**AND THIS FILE ALREADY KNEW.** The dead-air review recorded, turns ago:
*"At 18.04s the word 'kind' is not audibly spoken before the mute."* The
gate independently rediscovers exactly that card. A finding was written
down, nothing acted on it, and it shipped in every version since — which is
the argument for a GATE over a note.

**It also poisoned everything downstream.** Clip 6's tier3 risk note
"multiple speakers in the last few lines" traces to this same
hallucination: "i agree we agree on this" reads like a second voice because
it is half absent. Four independent judges had to measure pitch (median f0
131 Hz, consistent across the whole clip), mouth motion against the audio
envelope, and the facecam itself to establish there is no co-host and FNS
is alone throughout. **A hallucinated transcript becomes a false fact in
the clip's metadata**, and then that fact gets reasoned from.

Clip 8 is still on the old bespoke scripts and has NOT had the gate
applied; its eight cards are still in the shipped file.

## THE "UHH" WAS A SOUND EFFECT, AND A CUE IS NOT HEARD WHERE ITS FILE STARTS

George: *"should remove the 'uhh' and the booms are still very slightly late,
fix add to the logic, last boom is pretty irrelevant - remember there should
be logic to it - also video ends a bit too early now - fix."*

### The "uhh" is the chat's own entrance cue

There is no "uhh" in the speech — the source between the in-point and "guys"
is digital zero. Measured on the delivered file, **the first 0.24 s is exactly
the `paper` envelope**, −27.1 dB decaying to −56.2 over 260 ms, and no speech
starts until 0.26 s. A soft low noise burst with a 120 Hz thud in it, alone at
the top of a clip, reads as a voice clearing its throat.

It also marks nothing. The standing rule is **no sound without a VISIBLE
event**, and at frame 0 every element arrives at once — the chat is not
settling in, the clip is starting. `CUE_SILENT_HEAD = 0.25`: a window opening
at or before that gets no entrance cue. The clip now opens on 0.06 s of
silence and then speech.

`LEAD_IN_ABSENT = 0.10` goes with it. Room tone reads as the clip breathing
before he speaks; a mute's tail reads as nothing happening, so it buys less —
0.24 s of it was a quarter-second of dead start once the cue was gone.

### A CUE IS NOT HEARD WHERE ITS FILE STARTS

"Still very slightly late" after the anchor was already on the stressed
syllable's attack, so the remaining lateness is in the SOUND. Measured on
`vine_boom.wav`:

| | |
|---|---|
| 10% of total energy by | **107.8 ms** |
| 25% / 50% | 280.9 / 510.1 ms |
| broadband 20 ms envelope peak | **600 ms** |

It is a heavily back-loaded sub hit, so putting the FILE on the word puts the
thing a listener hears about a tenth of a second behind it. `sfx.perceptual_lead`
is the 10%-energy point and every cue is now fired early by its own:

| vine_boom | paper | shutter | thunk | tock |
|---|---|---|---|---|
| **107.8 ms** | 5.6 | 0.4 | 1.2 | 0.7 |

One rule, no table — a click reaches 10% immediately and is unaffected. **An
earlier pass concluded no lead was warranted by measuring the ONSET** (−6 dB
in 15 ms, which is true) — and the onset is not where a back-loaded sound is
heard.

### "Last boom is pretty irrelevant": no acoustic metric separates it

The third boom sat on *"you HAVE the freedom to choose your own teammates"* —
a calm explanatory line — against *"I don't want to HEAR no complaints"* and
*"that's IT"*. Measured at their own peaks:

| moment | level over baseline | rise |
|---|---|---|
| 3.36 "HEAR" | +2.72 | +0.87 |
| 12.78 "IT" | +1.28 | **+5.00** |
| 28.55 "HAVE the freedom" | **+2.74** | +1.79 |

**Level ranks the rejected one FIRST and rise ranks it second.** Capping at
two keeps it under either metric. What separates them is not how it sounds but
where the word comes from: `claim` and `consequence` are separate fields, the
two he kept are claim words and the one he rejected is a consequence word. A
boom punctuates what he is ASSERTING, not the resolution he offers.

**Mark with both, anchor on the claim.** Marking the cards with the claim
alone also changes WHICH cards are emphasised (16 → 12) and moved every
anchor, costing a boom he had accepted. The caption styling must not move —
that is what he signed off — so only the anchor subset narrows.

**And the anchor window spans onset→peak, not onset ± a margin.** A card may
sit anywhere inside the rise it belongs to. Clip 12's opening card is at 2.865,
0.065 s AFTER its own peak at 2.80 and so obviously right, but 0.665 s ahead
of the walked-back onset at 2.20 — outside `ANCHOR_FWD`, and that moment
vanished until the window was measured to the peak instead.

### The ending

86.34 ended on *"salary"* and read short. Transcribed with the tail padded,
86.50 gives *"...of salary."*, **86.70 and 86.80 both give *"...of salary all
day."*** — the complete sentence. 86.80 sits where "day" has decayed to −65 dB,
before the 87.00 mute and well before "tragic" at 87.36. 45.10 → **45.30s**.

Whisper calls 86.80 the middle of *"tragic"* (it times that word 0.8 s early,
across the mute); `_in_trough` lets the audio win, as it did at 86.34.

### Where this is still soft, stated plainly

The attack search can land on a neighbouring syllable rather than the card's
own word — delivered, the three booms sit on *"here"*, *"it"* and *"for"*,
and only the middle one is the word anyone would name. The energy peak inside
a 0.22 s window is not the same thing as the stressed word, and tightening the
window to keep it on the card (0.12 s) just moves it onto a different function
word. On a sub-bass hit under continuous speech the beat matters more than the
syllable, so this ships — but **if he flags the words again, the fix is a
stress model, not another constant.**

## TIGHTENING: the card was the right phrase and the wrong instant

George: *"second boom was slightly too late same with the third one -
tighten, also ends when he says tragic for some reason when it should be
'salary' - tighten."*

Read the two rounds together: last time he said **"random"** (selection) AND
**"too late"** (timing); this time only "slightly too late". **The selection
is settled and only the anchor was still wrong**, which is what decided the
fork below.

### A card begins on whichever word whisper grouped first

Anchoring to the emphasised card put the moment in the right PHRASE and still
fired late inside it. Measured on clip 12, **12 of the 16 emphasised cards sit
LATE of their own speech run's onset, median +59 ms**; the two he flagged were
the card "THE FREEDOM" at **+220 ms** — the boom landed on *"the"*, not on the
stressed *"have"* — and a card whose stressed syllable (*"that's IT"*) was
240 ms earlier.

So the anchor is refined once more: the loudest 40 ms in
`[t − STRESS_BACK, t + 0.10]`, then its ATTACK, walking back to 6 dB under
that syllable's own peak. **`STRESS_BACK = 0.22` is bracketed on both sides**:

| | |
|---|---|
| 0.30 | drags clip 6's second punch 305 ms back onto *"which"*, mid-previous-phrase |
| 0.18 | leaves clip 12's second boom at +15 ms — does not answer the note |
| **0.22** | clip 12 → *"hear" / "it" / "have"* (−180 / −240 / −185 ms); clip 6's "ping issues cheaters" punch moves −35 ms |

Delivered: **3.36 / 12.78 / 28.55**, measuring 3.7x / 3.9x / 3.6x the low-band
baseline, on *"don't want to **HEAR** no complaints"*, *"that's **IT**"* and
*"you **HAVE** the freedom"*.

### Two bugs the refinement exposed, both of the "plan ≠ build" family

1. **THE MOMENTS ARE THEIR OWN PHRASE STARTS.** `split`'s `open_at` snaps to
   the latest entry in `phrase_starts` at or before the moment. Once a moment
   moves off its card onto the stressed syllable it is no longer IN that list,
   so it snapped back to the PREVIOUS card — clip 12's middle boom went from
   12.78 to 9.35 and merged away. Pass the moments themselves.
2. **A MOMENT NEAR THE END OF ITS SEGMENT VANISHED SILENTLY.** 12.78 sits
   0.18 s before a picture cut, so the window was 0.23 s, fell under the 0.5 s
   minimum, and was skipped — **the plan printed three punches and the build
   delivered two, and the sfx bed followed the build.** A plan that prints what
   it cannot build is the same defect as a gate that measures nothing. The
   punch now opens earlier to fit (bounded by its segment and by
   `PUNCH_BACKOFF = 0.45`), and **the boom stays on the MOMENT, not on the
   piece** — a zoom already in when the word lands is the normal shape.

### Ending on "salary": whisper's boundary and the audio disagree

He wanted the clip to end on *"salary"*, not *"tragic"*. Transcribing
candidates with the tail padded:

| cut at | returns |
|---|---|
| 86.15 | *"...a couple months of **salad**."* — the word is clipped |
| 86.22 | *"...of **salary**."* — the earliest clean cut |
| **86.34** | *"...of **salary**."* — and it is the acoustic trough |

86.34 measures **−36 dB against a −19 dB speech baseline**, a 17 dB dip.
Whisper calls it the middle of *"all"* (86.15–86.41), so `_snap_out_point`
pushed the cut forward to 86.41 and put *"all"* back in. **`_in_trough()`
now lets the audio win**: whisper's word timings here are contiguous guesses,
and a trough is not a guess. 45.90s → **45.10s**.

### THE LEAD-IN WAS DIGITAL ZERO AND A SOUND EFFECT HID IT FROM THE GATE

Found by the adversarial pass, and it reproduces exactly. `_lead_in` had only
an UPPER bound, so a Twitch mute — under any quiet threshold — sailed through
it: all **0.255 s** of clip 12's lead-in measures **−180.0 dBFS, 100% digital
zero**, against clip 6's accepted lead-in at **−38.3 dBFS, 1% zero**.

**And `deliver_qc` cannot see it.** The chat's `paper` cue fires at 0.020 s
inside that silence, so `qc.dead_audio` on the delivered file reports **0 runs**.
A cue filled the hole the gate exists to find — the gate blinded, which is
worse than the hole. It is now measured on the CUT, where no bed exists, and
the build log names it.

**The behaviour is kept deliberately.** Scanning the source there is no room
tone to take — one 5 ms sample in twelve seconds — so the choice is 255 ms of
silence under the chat cue, or opening on the word's attack at full level,
which is the defect this lead-in was added to fix. The cue covers it and the
clip opens soft. What was wrong was that nothing said so.

### The adversarial pass rewrote the selector, and it was not taken

Its settle agents edited `resolve_punch.py` directly and replaced the whole
selector with a RISE metric snapped to caption-card starts. It is well
evidenced — on rise, clip 6's "CHEATERS" is the **#2 moment in the clip at
+4.66 dB**, where the emphasised-card rule scores it at the 57.7th percentile
— and **it is probably the better metric.** It was reverted anyway, for a
reason that is about the review loop and not about the measurement:

* its picks on clip 12 (6.92 "the", 13.72 "it", 24.49 "going", 30.99 "there",
  42.03 "i") land on function words and **move the second boom LATER**, which
  is the opposite of the note;
* it drops the semantic filter entirely, so a boom no longer has to sit on one
  of the clip's own thesis words;
* George has just accepted this selection. Swapping the metric underneath a
  note that only asks for tightening would re-open a question he has closed.

**Worth revisiting when the selection is next in question**, with the rise
distribution it measured (clip 6 p50 −0.05 / p99 +3.94 / max +5.91; clip 12
p50 +0.04 / p99 +4.16 / max +6.44) — it is in `$TMPDIR/wf_resolve_punch.py`
for that round, and the reasoning is above.

## "IT'S RANDOM" WAS LITERALLY TRUE, AND THE CAUSE WAS A SMOOTHING WINDOW

George, on clip 12: *"start of the video is still a bit wrong - try again -
also the boom effect was too late the first time and the second one was also
a bit too late - it's random, but we need to add some kind of logic to it -
also ends midway though tragic."*

Three notes, and the second one had two halves with ONE cause.

### The booms were on time to the frame and still late

First measurement, because the obvious hypothesis was wrong: cross-correlating
the boom template against the delivered low band put the three hits at
14.267 / 20.263 / 33.617 against planned cuts at 14.28 / 20.28 / 33.63 —
**13 to 17 ms EARLY, inside one frame.** The cue is not mislaid.

What is late is the MOMENT. Per-word levels around each one:

| boom | the emphatic word | boom fired | late by |
|---|---|---|---|
| 14.28 | "**want**" 13.45, +5.5 dB | 14.28 | **0.83s** |
| 20.28 | "**just**" 18.63, +3.7 dB | 20.28 | **1.65s** |
| 33.63 | "**are**" 31.56, +7.1 dB | 33.63 | **2.07s** |

**A 0.30s RMS window is a smoother, so its maximum sits after the syllable
that caused it.** On clip 6 the phrase snap hid this, because whisper gave it
an utterance boundary to snap to. On clip 12 it did not: two of the three
punches landed at exactly `peak - PUNCH_LEAD`, which is the signature of the
snap finding nothing — whisper's VAD had merged the utterances, and this file
already records the median inter-word gap on this VOD as 0.000s. **The snap
was sound and it was starved of targets.**

And "random" is the same starvation. Measured against the two seconds before
them, the three moments changed the level by **+1.5, +0.3 and −0.2 dB** — the
last one is QUIETER than what preceded it. In a clip whose whole range is
3.9 dB, ranking the loudest windows is ranking near-ties.

### Two simpler rules were tried first and the regression killed both

The test that matters is clip 6, where George named the moment himself: *"ping
issues, cheaters there should be zooms because it's when he's loud."*

| rule | where it puts clip 6's "cheaters" |
|---|---|
| per-WORD rise over the preceding 1.2s | **6th among content words** (+2.02), outside the top 10 overall |
| pause-before × rise ("setup then hit") | **31st of 138** — and on clip 12 its top pick is a 10.3s Twitch mute |
| **emphasised caption card + rise** | **4th of 21**, and it is picked |

Both of the first two are plausible and both are wrong, and the reason is the
same: **whisper's word timings here are contiguous, so per-word acoustics and
inter-word gaps are both built on guesses placed inside joins.** Nearly every
"gap before a word" on this clip measures 0.000s.

### The anchor is the emphasised caption card

Those come from `emphasis_keys(claim, consequence)` — the clip's own thesis,
written by the model that selected it — and this file already records that
they "marked the right ones" on clip 8. They are also the only candidate that
satisfies the standing rule **no sound without a VISIBLE event**: the card is
drawn in accent colour at that instant, so the boom marks something on screen
rather than a vocal peak.

So `bold_moments(..., anchors=…)`: a candidate peak is walked back to its
onset (the first crossing of halfway between baseline and peak), and must find
an emphasised card in `[onset − 1.10, onset + 0.30]`. **No card, no punch and
no boom** — a clip with no loud moment on one of its own thesis words gets
none, which is the honest answer for a flat read.

**`DB_FRAC` came down 0.70 → 0.55, because it was doing the anchor's job and
stacking with it.** At 0.70 clip 12 got exactly ONE punch: the floor admitted
three candidate peaks and the anchor filter dropped two. Swept with anchors on,
the plan is IDENTICAL at 0.55, 0.45, 0.35 and 0.25 on both clips — **a plateau
where the old threshold was a knife edge.** 0.55 is the top of it, and the
point is that the exact number no longer matters.

| | picks |
|---|---|
| clip 12 | 3.54 (+2.7), 13.02 (+4.3), 28.73 (+2.7) |
| clip 6 | **9.30 = "CHEATERS"**, 26.64, 34.80 |

Verified in the delivered file: 3.6x / 3.9x / 4.1x the low-band baseline, on
*"I don't want to hear **no complaints**"*, *"I **just** don't want to hear
it"* and *"you **have the** freedom to choose your own teammates"* — the
claim, the claim again, and the consequence.

### The opening: no pre-roll exists on this material, and the first word had no caption

Measured across the clips George has ACCEPTED:

| clip | lead-in | frame 0 |
|---|---|---|
| 06 | 270 ms | −47.6 dBFS |
| 08 | 100–200 ms | −41.5 dBFS |
| **12** | **0 ms** | **−11.9 dBFS** (its own peak is −10.4) |

**Pre-roll cannot be FOUND here.** Scanning source 20–32s, every word is
preceded either by the previous word still sounding — he talks continuously —
or by digital zero. **Exactly one word in twelve seconds has real room tone in
front of it.**

And the first word was not one to open on anyway: `in_point 23.225` sat on
"you", whose span is **55.4% digital zero**, so `_drop_hallucinated` had
already refused its caption. The viewer heard a word the caption track would
not show, and the captions started on the next one. **The audio and the
captions disagreed at frame 0.** `_open_on_captionable()` applies the same
test to the in-point: a word we will not quote is not a word to open on. On
clip 6 the opening word "i've" is 0.0% silent, so the rule is a no-op there
and the earlier backward snap stands.

`_lead_in()` then backs into whatever quiet precedes the new first word, up to
0.24s, crossing only audio under −34 dB so it cannot pull in the previous
word's tail. Clip 12 opens on **"guys have it good now, man"** with 255 ms of
lead-in; clip 6 moves 20 ms.

**Whisper will tell you the word is still there, and it is lying.** The
delivered clip transcribes as "You guys have it good now, man" — but the
source between the in-point and "guys" is digital zero at −180 dBFS, so there
is no "you" in the file. It is a language-model completion. Same lesson as the
hallucination gate: **the audio is the check, not the model.**

### "Ends midway though tragic" was THREE defects in a row

1. **The source window itself was short.** The clip file ran 87.70s and
   "tragic" ends at 87.71 — the word's release was the last frames of the
   file, so any frame lost anywhere ate it. **The VOD is still up**, so the
   region was re-fetched and 2.3s of tail spliced on. `--force-keyframes-at-cuts`
   put a whole-region re-fetch **1.078s out**, which would have invalidated
   every word timestamp, chat offset and punch — so the tail was taken from a
   separately verified fetch and concatenated, then checked: **offset +0.0 ms,
   corr 1.000** in an early and a late window. *Verify an alignment on
   ENVELOPES, not raw samples* — the raw-waveform correlation read 0.027 and
   was useless, while the 1 kHz envelope read 0.406 against a 0.016 median.
2. **The out-point was not frame-aligned.** 87.71 made the last keep 0.390s =
   23.4 frames, so the picture held 23 and the word needed 24. 87.72 makes it
   exactly 0.400s = 24 frames, and `"Thank you to the tier one man"` starts at
   87.72 so none of it is included.
3. **`-frames:v` BOUNDS THE AUDIO.** It stops ffmpeg reading once the video
   stream ends, so the audio is cut to the picture however long the release
   is. Measured: the Resolve render ended the word cleanly at **−53 dB** and
   the delivery step handed it over at **−14 dB**, 67 ms short. The note that
   put `-frames:v` there was about `-t` cutting at a KEYFRAME, which is true
   of `-c:v copy` and not of a step that re-encodes. Now `-t` with three
   frames of slack; `black_top`/`black_bottom` would catch it if that cost
   anything, and they report none.

**AND A TRAP IN VERIFYING IT:** whisper drops a trailing word when the file
ends on one. The delivered tail transcribed as *"...of salary all day."* with
no "tragic" until the clip was padded with 0.6s of silence, at which point it
returns *"a couple months of salary all day. Tragic."* **Pad before
transcribing a tail.**

### Replacing a source file under Resolve delivers a silent clip

The extended source was first written to the SAME path. Resolve had that path
in its media pool from the previous build, did not re-conform it, and rendered
**the sfx bed alone** — 44.09s of absent audio in a 45.8s clip, every speech
frame gone, and the loudness gate caught it at −12.76 LUFS. Giving the file a
new name fixed it. Same family as the media-pool-by-name collision already
recorded here: **Resolve's pool caches by path as well as by name, so a
changed file needs a changed path.**

### What clip 12 measures now

| | |
|---|---|
| Duration | **45.90s** |
| Opening | 255 ms of lead-in, then "guys have it good now, man" |
| Ending | "...salary all day. **Tragic.**", decaying to −58.6 dB |
| Booms | 3, each on an emphasised card, **3.6–4.1x** the low-band baseline |
| Chat | 29 of 29 frames |
| Captions | 104 cards, 2.27/s, 0 hallucinated |
| Audio | −14.06 LUFS, −1.19 dBTP, 0.00s dead space, 0.00s absent |

## THE BOOM WAS IN THE BED AND NOT IN THE FILE, TWICE OVER

George: *"no keep the twitch chat why did you remove it? it was good, also
remove the "uhh" - also the end "tragic" is cut off, also there's no booms?"*

Four notes, four separate defects, and **every one of them was a guard or a
constant that was correct once and had stopped being correct.** The build log
said `cues: 3` on a clip with no booms in it, which is the whole argument for
measuring the artifact: *a cue count is a claim about the plan.*

### 1. No audio track, and then a high-pass that ate what was left

The first cause was that `make_clip` only ever called `tl.AddTrack("video")`,
so the bed was appended to an A2 that did not exist and vanished silently.
**No clip this pipeline ever built had a sound effect in it.**

With the track added, the booms were still not audible, and the second cause
is an own-goal:

| | |
|---|---|
| Vine Boom energy **under 85 Hz** | **52.8%** |
| What `HOUSE_EQ` costs it | **7.09 dB RMS** (−7.67 → −14.76), only 1.83 dB peak |
| Clip 12's own sub-85 content | **−35.1 dBFS against a 200–4000 Hz body of −23.4** |

`highpass=f=85` was set because ONE clip's master measured rumble at −5.1 dB
against the speech body, and it then applied to every clip — and to the bed,
because Resolve mixes A2 into the master before `_finish_audio` sees it. On
clip 12 there is no rumble to remove (12 dB down is already masked) and the
filter was removing nothing except the one cue whose entire point is low end.
It does not quieten the boom, it **hollows it out**: 7 dB of RMS for 1.8 dB of
peak.

`render_ffmpeg.house_eq(src)` measures instead, with the floor at −10 dB, and
the decision prints in the build log. **Measure it on the SPEECH, not the
master** — `raw` already has the bed in it, and a Vine Boom reads as rumble, so
measuring there keeps the high-pass on *because* the boom is there and then
cuts the boom.

Measured in the delivered file, 40–120 Hz against its own baseline:

| | before | after |
|---|---|---|
| boom 1 | 1.2x — **absent** | **3.8x** |
| boom 2 | — | **3.6x** |
| boom 3 | 2.6x | **4.2x** |

### 2. A boom is an EVENT cue, so it sits at the shutter's level

`BOOM_RMS = -21.0` was chosen on arithmetic as "near −12.8" and **measured
−14.57** — the thunk's level. Wrong tier: a thunk means "a fact arrived" and
rides under the speech, while this is a punchline on the clip's loudest
moment, which is where the shutter sits (−10.4, "a photo card lands"). This
file's own rule is that a sound accompanying motion sits below one marking an
event. **−16.8 measures −10.47 dBFS peak.** Both numbers are measured in the
master, because the prediction was out by 1.8 dB — again.

**ASK FOR −1.5 dBTP TO DELIVER −1.0.** Raising the boom took true peak to
−0.41 and `deliver_qc` rejected the render, correctly. loudnorm hits its
target on the PCM it limits, but the delivery is AAC and AAC decode
overshoots — the same −1.0 request had measured −0.64 and −0.77 on earlier
versions of this clip. The overshoot belongs to the codec, so the request
carries the headroom instead of the cue being backed off to hide it. Now
−1.11 dBTP.

### 3. THE SLIVER GUARD WAS WRONG AT BOTH ENDS, AND IT RESTORED DEAD AIR

The same `min_first/min_last = 0.40` guard sat in `_clamp_in_point` and
`_clamp_out_point`. It was written when every keep got its own framing, so a
0.1s keep was a six-frame flash and merging it into its neighbour was the
lesser evil. **Since `_shot_index` decoupled shots from keeps it is pure
damage, because merging two keeps does not shorten anything — it puts the
removal between them BACK.**

| end | what it did |
|---|---|
| in-point | swallowed a 1.0s removal, delivering a clipped "you" then **1.0s of −77 dB silence** at the top — George's "uhh" |
| out-point | the last keep held the one-word button "Tragic." and ran **0.38s**, 0.02s under the limit, so the 0.59s removal came back as **0.75s of quiet with 0.35s of digital zero in it, immediately before the payoff word** |

Both gone. `dead_space` 1.6% → **0.0%**, `absent_audio` 0.35s → **0.00s**.

A keep is not a shot. That is the second time this round the same sentence
settled a bug, at opposite ends of the same clip.

### 4. An in-point can land INSIDE a word, and then the only fix is backwards

`_snap_in_point` had two cases: the point sits on a word TAIL (a trough is
close — snap forward, which is clip 6's fricative) or it is a real word START
(no trough close — leave it). Clip 12 was neither.

`in_point 23.30` landed **inside the word "you"**, audible 23.228–23.52 and
then decaying into a 0.73s Twitch mute. The forward snap refused, correctly —
the next trough was 0.535s away, past `SNAP_MAX`. So the clip opened on the
*second half of a word*, which is what an "uhh" is.

**THE REFUSAL IS THE SIGNAL.** When the forward trough is beyond `SNAP_MAX`
and the audio is CONTINUOUS across the requested point, the point is mid-word
and the only safe direction is back to that word's own onset. The test for
"continuous" is that the 60ms before the point is within 10 dB of the 60ms
after; at a genuine word start the before is 20+ dB down and nothing moves.
`SNAP_BACK = 0.20` — enough to recover an onset, not enough to pull in the
previous word.

Clip 12: 23.30 → **23.225** (−0.075s). Clip 6 still returns **+0.205s**, and a
real word start still does not move. Worth noting for accuracy: the forward
path can already return a value up to 0.05s EARLIER than its input, because
its analysis window starts at `in_point − 0.05` — so "it only ever moves
FORWARD" was never quite true, by up to 50ms into silence.

### 5. "tragic" was real, and whisper reported it 0.8 seconds early

`out_point 86.50` sat inside the word "day" (86.410–86.590), so the clip
stopped mid-word. But the interesting part is why the fix was not mechanical.

Measured at 20ms on the source: audible speech stops at **86.80**, then
**digital zero 87.00–87.34**, then a fresh onset at 87.36 running to the end
of the window. Whisper places "tragic" at **86.59–87.43** — stretched 0.8s
backwards across the silence, because its word timings are contiguous and the
gap has to be filled by something. Transcribing the spans separately settles
it: 86.30–86.82 is `"all day."` and 87.34–end is `"tragic"`.

So the button is real, it is audible, and it is 0.9s later than the transcript
says. `out_point 87.70` (the source end) recovers it; the 0.34s mute between
is then ordinary dead space and the cut leaves a beat.

`_snap_out_point()` now moves an out-point off the middle of a word onto that
word's END, forward, on the tie-break this file already records — over-
including by one word is recoverable, losing the payoff is not. **Be honest
about what it would have done here: 86.50 → 86.59, finishing "day" and still
dropping "tragic".** The guard stops a mid-word cut; it cannot know a one-word
button was the point. That took George's ear, which is what rules 1–3 have
always said.

It also reports when the word it lands on straddles a mute, because that is
the case where the snap cannot help.

### 6. Two planners, one of which was already stale

`_plan_only` was a second copy of `stage_cut`'s planning block, and within
this one round they diverged: the out-point snap went into `stage_cut` only,
so `--only render` planned a different cut than the full build had rendered.
`stage_cut` now calls `_plan_only`. Same shape as the punch plan being
measured from the overwritten delivery, and as `_cut.wav` being cached —
**two numbers that are supposed to be the same number, derived twice.**

### What clip 12 measures

| | |
|---|---|
| Duration | **45.95s** |
| Opening | `"You guys have it good now man"` from 0.00s, whole word |
| Ending | `"...salary all day. Tragic."`, the word completes |
| Booms | 3, on the zooms, **3.6–4.2x** the low-band baseline |
| Chat | Twitch's own black, chatters' own colours, **29 of 29 frames** |
| Captions | 105 cards, 2.29/s, **0 hallucinated** |
| Audio | −14.07 LUFS, −1.11 dBTP, **0.00s dead space, 0.00s absent** |

**One thing to say to George rather than bury.** The chat he liked was clip
6's, composited onto clip 12 by the media-pool bug. This is clip 12's OWN
chat, and it measures **13% on-topic against the 15% floor** — `chat_is_safe`
refuses it and it is on because he asked for it. An explicit `chat_mode` in a
spec is now the override: the floor is a default for clips nobody has watched,
and once he has watched one his call settles it. The measurement stays in the
log as a caveat rather than a veto.

## A SHOT IS NOT A KEEP — which is how to cut ALL the dead space

George, for the third time: *"remember i said cut ALL dead space too"*, on a
clip 6 that measured **21.6% quiet** at a 0.20s floor (clip 8: 14.3%).

He has asked this three times and each time the answer has been "yes, but it
costs picture cadence". **That trade was an artefact of the code, not a
fact about editing.** `framings(len(keeps))` gave every keep its own
framing, so an audio splice and a picture cut were the same event, and the
only way to remove more pauses was to cut the picture faster — which is
exactly the complaint recorded at v47 and at "12.8 cuts/min against R1's
6.0".

They are different things:

* a **keep** is an AUDIO SPLICE — where a pause was removed;
* a **shot** is a PICTURE CUT — where the framing changes.

`make_clip._shot_index()` groups consecutive keeps until `MIN_SHOT` (3.5s)
accumulates, and the framing changes per SHOT. Measured on clip 6:

| | MIN_DEAD 0.35 / BEAT 0.12 | **0.20 / 0.08** |
|---|---|---|
| duration | 41.5s | **38.6s** |
| audio splices | 5 | **14** (20.3/min) |
| picture cuts | 5 (5.8/min) | **7 (9.3/min)** |
| quiet at the 0.20 floor | 21.6% | **12.8%** |
| quiet at the 0.35 floor | 12.9% | **4.3%** |

So 8.5s of dead air comes out and the picture cuts SLOWER than clip 8 ships
at. What the small splices become inside a shot is an ordinary jump cut on
a talking head, which is the native language of the format.

## Clip 6's three notes, and what each one measured

George: *"clip starts off weirdly - feels like it's too late - also ping
issues, cheaters there should be zooms because it's when he's loud ... also
where's the story images?"*

### The opening was a dangling fragment

The clip opened on *"in the new circuit i already said this i've said this
on every single stream..."* — a prepositional phrase with no sentence, then
a repetition of itself, and the claim ("an absolute shit show") did not
land until **9.5s**. `in_point` moves to **2.02**, which drops the fragment
and opens on a complete clause: *"I've said this on every single stream
since we found out that franchise is ending — I said these open qualifiers
are going to be an absolute shit show."*

**A clamped in-point can leave a SLIVER first shot.** 2.02 sits 0.10s before
a removal, so the first keep became a six-frame stub with its own framing —
a flash before the clip proper. `_clamp_in_point()` now swallows that
removal instead: a natural breath at the head costs nothing, a six-frame
shot is a glitch.

### The punch floor was clip 8's number, and it was knife-edge

George is right that he is loud on "ping issues, cheaters", and there WAS a
peak there — **3.9946 dB over baseline**, rejected by `if d < 4.0` while the
printout rounded it to "+4.0". The same knife-edge class that was fixed in
the SELECTOR last version and left sitting in the floor.

And 4.0 was never general: it was read off clip 8, whose range is 5.5 dB
over baseline. **Clip 6's entire range is 4.55 dB**, so an absolute 4.0
keeps only the top 12% of its dynamic and throws away the moment the clip is
named after. A speaker's emphasis is relative to their own delivery in that
clip, so the floor is: `max(2.5, 0.70 x range)`.

| | range | floor | picked |
|---|---|---|---|
| clip 8 | 5.50 dB | 3.85 | 13.10 +4.5, 23.80 +5.5, 36.90 +4.9 — **unchanged** |
| clip 6 | 4.55 dB | 3.19 | 12.00 +4.0 (**"cheaters"**), 18.60, 26.40, 33.90, 39.80 |

**`SKIP_HEAD = 9.0` was a false attribution.** It was set to clear clip 8's
8.97s opening shot, but swept across 9.0 / 4.0 / 2.5 / 1.0 clip 8 returns
the IDENTICAL plan every time — its loud moments all sit past 13s. What
actually stopped its opening being chopped was `MAX_PER_SHOT`. 9.0 was a
coincidence doing nothing, and on a shorter clip it would silently eat a
real moment near the head. Now 2.5.

### A PUNCH OPENS ON THE PHRASE, NOT ON THE RMS PEAK

The peak is mid-phrase. "ping issues, cheaters" begins at output 8.78s and
the loudest 0.3s window sits at **10.10** — four words later — so opening
`PUNCH_LEAD` before the PEAK opened the zoom after the words it was meant to
mark. The start now snaps back to the phrase containing the peak.

**And the phrase boundary is the UTTERANCE list, not an inter-word gap.**
Whisper's VAD gives contiguous word timings: measured on clip 6 the median
inter-word gap is **0.000s and only 1 of 150 reaches 0.25s**, so a
gap-based detector found one boundary in the whole clip and the snap did
nothing. This file already records the inverse trap for finding pauses
("whisper's VAD merges utterances ... use WORD gaps"); for finding phrase
STARTS the utterance list is the only usable signal.

### Stories: this clip has none that belong on it

George: *"where's the story images? we should always include some stories
sometimes where appropriate - but perhaps this one is fine."*

Checked rather than skipped. The two verified stories in the system are
roster departures — PRX/Jinggg and Sentinels/JonahP+Jerrwin — and clip 6 is
about open-qualifier tech chaos. Neither is on topic, and the one genuinely
relevant item (the 10 -> 8 partner-team reduction) has no verified published
headline with photos; it shipped on clip 8 as a figure card, not a story.
**A story card goes on a clip when a verified, on-topic published story
exists — it is not a default slot to fill**, and inventing one to fill it
would be the "random text cards" defect under a nicer name.

## THE QUESTION CARD: built, and lexical overlap is the WRONG retrieval

George: *"ideally we should have something where fns has seen the twitch
chatter's question and we have an animation of it shown on screen while he
answers it - then the twitch chat should come in like normal."*

**This reframes the "chat is not reacting" finding.** Clip 8's chat measured
43 msg/min with 24% on-topic and was recorded as a poor overlay candidate
because it is a Q&A queue. It is the opposite: a chat that ASKS is the
material for this card. Reacting chat wants the burst overlay; asking chat
wants the question card.

`src/Question.tsx` is built — Twitch's own `#18181B` and the chatter's own
colour, like the chat box, because a viewer must read it as a message from
chat; what separates it is SCALE AND POSITION (full width, centred,
untilted, 1.5x the type) rather than a second visual language. A third tilt
in one clip would read as one repeated gesture.

**THE CARD ASSERTS AN INTERACTION BETWEEN TWO REAL PEOPLE** — the only
claim of that kind anything here makes — so nothing reaches it on a score.

**Six candidates ranked by shared words were put to independent judges and
ALL SIX WERE REFUTED.** The judges read the raw chat themselves and found
what a similarity score cannot:

* the overlap runs the WRONG WAY — chat was paraphrasing the streamer, who
  says in the clip he has made this argument "on every single stream". Three
  chatters reached for "ping / issues / tech" inside a 16-second span while
  he independently ran a prepared talking point;
* **Ferruxx asks the same question again 105 seconds later**, which is proof
  nobody answered it — a check no lexical method would ever make;
* Zehi's single shared token was "out", in an idiom ("out of jail") against
  a phrasal verb ("locking players out"), from a chatter-to-chatter joke
  about an unrelated story.

**So high overlap is evidence AGAINST a response, not for it** — in a chat
and a streamer locked on one subject, shared vocabulary is the null
hypothesis. And the one pair that looks genuine has **zero words in
common**:

    Perrysuxker_17 +30.2s : "so how can you say the format is good"
    spoken         +33.84s: "i agree we agree on this i know that the open
                             qualifier system is going to have its own issues
                             ... it is still better than locking players out
                             of franchise forever"

A question and its answer use DIFFERENT words — that is what makes it an
answer rather than an echo. `chat_reaction.answering()` now retrieves every
QUESTION within the lookback, ranked by RECENCY, and reports overlap only as
evidence for the judge. The question test also matches a question word in
the first few tokens rather than at position 0, because chat opens with a
discourse marker constantly — anchoring to the start missed this exact
message.

## Four more bugs, all of them stale or empty state

* **`_cut.wav` was cached and never invalidated.** It is derived from the
  keeps, so moving the in-point or the dead-space floor changes it — but a
  stale 43.14s copy put the punch plan's last moment at **39.80s on a 38.57s
  clip**, measured against a cut that no longer existed.
* **The continuous chat window came back EMPTY on any clip with a non-zero
  in-point.** It was derived as `remap(0.0)`, and 0.0 is before the first
  keep when the in-point is not 0, so the whole window list was `[]` — the
  chat left the screen entirely and took its entrance cue with it.
  "Continuous" means the whole clip by definition; there is nothing to look
  up.
* **`punches.json` is written to one shared path**, so reading it back after
  a second clip's build returns the FIRST clip's plan. It now lands in the
  clip's own overlays directory.
* **The one-punch-per-shot cap counted segments.** Once dead-space removal
  was decoupled from framing, one shot spans several segments and the rule
  silently became one-punch-per-SPLICE.

## MASS PRODUCTION: the spec, the screen, and what is actually in the way

George, locking clip 8 in: *"all of this logic ... I want us to develop
this into other clips ... I want to mass produce these clips for different
channels. So figure out how you can kind of do that from here."*

Clip 8's pipeline was eight top-level scripts with its constants at the top
of each — the VOD id in four, the facecam rect in two, the in-point in two,
the duration typed into `Root.tsx`. `engine/clipspec.py` splits those into
a **`Channel`** (seam, chrome, grade, fps — measured once per streamer) and
a **`Clip`** (which cut, where it starts, what the chat did, what goes in
the pane). `make_clip.py` runs the whole pipeline off them in six skippable
stages. The house style — captions, exits, punch geometry, sound, palette —
stays in CODE, because it is the same on every clip for every channel by
definition. If a value differs per channel it goes in `Channel`; per clip,
in `Clip`; if it is a decision we made once about how our clips look, it is
not a spec field at all.

**Proved by building a second clip end to end from a spec**: `fns-06`, "open
qualifiers are going to be a shit show", 43.1s, **7.0 cuts/min** against
clip 8's 12.8 and R1's 6.0, −14.09 LUFS, −0.87 dBTP, no black frame in
either pane.

### THE BOTTLENECK IS CHOOSING, NOT RENDERING — 4 of 12 are buildable

Ranking by virality picks clips the pipeline cannot cut. Measured across
the top twelve of this VOD:

| | |
|---|---|
| buildable | **4 of 12** (files 04, 06, 08, 12) |
| rejected for muting | 7, at **32–44% absent audio** |
| rejected for cadence | 4 of those also exceeded 15 cuts/min |
| rejected as too short | 1 (19s left after tightening) |

**The second clip chosen by virality had to be abandoned.** File 07 ranked
#6 and has the best chat burst in the entire set (x4.83) — and it is 44.4%
muted, cutting to 36.2s in 13 shots at **19.9 cuts/min**. Clip 8 at 12.8
was already recorded here as twice the reference; 19.9 is a strobe.

`screen_clips.py` gates on what decides buildability — muting share,
cuts/min after tightening, seconds left, the chat profile, the facecam
confidence — and prints a verdict and a reason per clip. **Run it before
picking anything.** The editorial call (is this one narrative, does it
explain itself) is still a human reading the subject line; this only
removes the clips that cannot be cut at all.

Clip 8 was not a lucky pick: at 20.8% absent it is the least-muted long
clip in the top ten. The highest-strength clip in the set (file 12, 0.70,
"telling complaining players they have it easy") is buildable and unbuilt.

### THE FACECAM RECT IS NOT A CHANNEL CONSTANT — and assuming it was shipped a broken clip

The most useful thing the generalisation pass found. Clip 8 (VOD 1:39:38)
has FNS bottom-right at (1456, 818, 1920, 1080); clip 6 (VOD 0:36:34), the
**same streamer on the same stream**, has him at (1436, 344, 1920, 616) —
higher and a different size. Reusing clip 8's rect rendered clip 6's top
pane as a corner of a browser sidebar with no face in it. A streamer moves
their own layout between scenes.

`engine/facecam.py` detects it per clip by MOTION, which needs no face
model, no download and no per-game tuning, and still works when the
streamer is turned away. Two measurements got it right, and the first
version of each was wrong:

1. **ADJACENT FRAMES IN SHORT BURSTS, not variance across the clip.** The
   first version took the per-pixel standard deviation of 24 frames spread
   over the whole clip — which measures "did this change over a minute".
   On clip 8 the PAGE scored a higher median (5.52) than the facecam
   (3.99), because he switches document once and a one-off change of the
   whole page dwarfs a webcam. Consecutive frames separate them completely.
2. **THE THRESHOLD IS LOW AND ABSOLUTE.** Measured at the analysis scale,
   inside the facecam the adjacent-frame delta runs median 0.125; outside
   it median **0.000**, 99th percentile 0.050. At a floor of 0.15 the cam
   is 46.3% lit and the page 0.1%. A HIGH threshold finds only the
   streamer's FACE — the room behind him is as still as the page — which is
   how clip 8 first came back as a 128x72 box on his hands.

Validated against known ground truth: on clip 8 it lands **within 6px on
every corner** of the hand-measured rect. Confidence is motion inside the
rect over motion outside it — clip 8 50x, clip 6 391x — and the failure
mode it catches is a page PLAYING VIDEO (a watch party, a VOD review),
which moves too and drags the ratio toward 1.

### WHEN the chat belongs on screen, and the gameplay case

George: *"if it's a gameplay video ... after the streamer has like got a 3K
or 3 kills, then we can see the Twitch chat's reaction ... we have to pick
the right moments for when the Twitch chat is on the screen."*

**The frag does not have to be detected.** A 3K produces a burst of chat,
and the burst is the signal. Reading the chat is ~100x cheaper than reading
the footage, it needs no per-game detector, and it generalises to anything
a crowd reacts to — a frag, a fail, a reveal, a guest. Detecting the kill
would say a kill happened; measuring the burst says the crowd CARED, which
is what the overlay is for. `engine/chat_reaction.py`.

Two modes, and a clip is one or the other:

* **continuous** — no burst. The chat is the lower pane's resting state and
  stays up. Clip 8 and clip 6 are both this.
* **reactive** — the chat spikes, so the box goes up ON the spikes and is
  away otherwise, and its arrival means "look what they said".

**BASELINE FROM OUTSIDE THE CLIP.** A 20s ace clip is hype end to end and
reads as flat against its own mean, so the resting rate comes from ±180s of
context around the clip.

Measured across the top seven windows of this VOD: the stream's resting
rate is **72–87 messages/min** (R5's reference is ~75), bursts run **x2.09
to x4.83** over it, and two of the seven have no burst at all. So the
signal is real and it discriminates.

**THE HONEST LIMIT: this VOD cannot demonstrate the reactive mode.** Every
clip in it is `take` genre — a talking-head stream with no gameplay — and
the clips that DO have bursts are the ones the muting destroys (file 01
with three bursts is 43% muted; file 07 with the x4.83 burst is 44%). The
reactive path is built, measured and unexercised, and it stays that way
until a gameplay VOD arrives. Worth saying plainly rather than claiming it
works.

Also worth knowing: **clip 8's chat is the least reactive in the set** — 43
messages/min against the stream's 78, with 24% on-topic — and it got the
most chat screen time (100%). It earned that on a different basis: there
was nothing else to put in the pane.

### Four bugs the second clip found, which one clip could never have

* **`MarkIn` RENDERS ONE FRAME BEFORE THE MARK.** Measured: marking
  [216000..218586] gave 2587 frames whose frame 0 was pure black (timeline
  215999, where nothing is); marking [216001..218587] gave a frame 0 of
  real picture. Every clip rendered with marks opens on a black frame until
  it is compensated.
* **The timeline is as long as its LONGEST track**, so an overlay sized
  from `round(out_dur * fps)` outran V1 by 2 frames and those rendered
  black at the tail. The overlays are now cut to what V1 holds — the
  picture is V1, by definition.
* **A chat message's offset is a VOD second; the keeps are in CLIP-FILE
  time.** Passing the raw offset to the remap matched no keep and silently
  dropped every message inside the clip — 60 of 116, with the 56 survivors
  all pre-roll, which looks like a thin window rather than a bug.
* **`finish_audio.py` ran `print(qc.check(...))` on a hardcoded v27 render
  at module scope**, so importing its EQ string re-QC'd an unrelated old
  file mid-build. The chain moved to `engine.render_ffmpeg.HOUSE_EQ`.

### What mass production still needs from George

Not code. In order:

1. **A gameplay VOD**, so the reactive chat mode can be exercised and the
   "after a 3K" case proved rather than asserted.
2. **Chat is perishable — pull it at INGEST.** Replay dies with the VOD and
   FNS's archive is a rolling ~60-day window. Any clip built more than two
   months after the stream has no chat overlay available at all. This
   should be part of fetching a VOD, not part of editing it.
3. **The rights basis per channel.** `permission` is required on every
   source, and a viewer's chat message is their words on screen.
4. **Headcount, for the Remotion licence.** The free tier covers an
   organisation of up to 3 employees and the gate covers the entire render
   route.
5. **Cards are editorial and stay that way.** A sourced exhibit or a
   verified news story needs a human deciding what the clip argues and an
   independent check on any name that goes on screen. A clip with
   `cards: []` is fully automatic, and that is what clip 6 is.

### The blue mount is gone, and my test for "can you see the box" was wrong

George: *"twitch chat does not need a blue border."*

He is right, and the measurement I used to justify the plate was testing the
wrong property. **A contrast ratio along a panel's outline tells you whether
you can see the RECTANGLE. It does not tell you whether you can see the
BOX.** Measured on the bare version composited over the real board: the
outline is legible along 6.3% of its perimeter against the board outside it,
13.1% against the board content it covers, 14.3% either way — and the box
reads immediately and unmistakably anyway.

What actually carries it is the contents. Local texture (mean
`|pixel - 9x9 mean|`) inside the chat box measures **26.27 against the
board's 4.35** — the box is 36px white type at 17:1 on its own fill, sitting
on a board whose own type is small and dim. **A panel is legible when what
is IN it is louder than what is AROUND it**, and the perimeter test cannot
see that at all. The old 1.08:1 dark-glass panel failed because it was a
near-empty surface with nothing in it to be louder, not because its edge
was invisible — the two cases look identical to a contrast ratio and are
nothing alike.

So the chat is Twitch's own `#18181B`, square corners like Twitch's own
column, no border, no plate, no shadow. The 52px top radius goes with the
plate: it only ever existed to cut the blue into R5's shoulder triangles,
and without it that is a sixth radius in a system whose geometry is
`RADIUS = 0`.

### The chat arrives once and stays, and the cycle was an artefact

George: *"why does it randomly disappear and come back at the start of the
video? ... keep the twitch chat in place but make sure there's a sound
effect as it pops in."*

**"Randomly" is the accurate word.** The cycle was an arbitrary clock with no
relation to anything on screen, and it could not have had one: the content
pane's frame-to-frame delta is median 0.0005 with zero frames above 0.5
across all 2822, so there is nothing in that pane for it to punctuate. The
first thing a viewer saw was the box vanishing at 8.75s for no nameable
reason.

It only existed because the chat used to live in the GAPS between cards, and
with ten cards gone there were no gaps left — **a scheduling rule that
outlived the thing it was scheduling around.** Worth generalising: when the
element a rule was dodging is deleted, delete the rule, do not re-tune it.
Two versions were spent tuning ON/OFF on a cycle that should not have
existed.

**It does not need to dodge the two cards either.** Measured off their own
alpha, `rm_StoryPrx` and `rm_StorySen` each cover **100% of the chat box
footprint at alpha > 250** — 1008 wide at top 1029 against a 580-wide box at
1090 — so a card lands on the chat and lifts off it.

| | windows | chat on screen | state changes |
|---|---|---|---|
| v49 | 4 | 29.9s (64%) | 7 |
| v50 | 4 | 34.6s (74%) | 7 |
| **v51** | **1** | **46.8s (100%)** | **1** |

**THE CUE IS `paper`, PICKED ON THE ENVELOPE.** The box's entrance runs
0.34s — a 34px lift, a 0.90->1.00 scale, the tilt springing in. Effective
durations across the palette: tock 65ms, shutter 82ms, thunk 88ms, pop
220ms, **paper 260ms**, newsding 420ms, ding 550ms. `paper` is the only one
whose envelope matches a 340ms settle, and an 87ms thunk would fire and be
gone while the box was still moving — the "sound on the MOTION, not only on
the arrival" note. It is also what `paper` was built for (a card settling on
a desk) and it was free, because the stories take the shutter and only the
shutter.

So the whole sound design is **two sounds with one meaning each**: `paper`
= the chat panel settles in (once), `shutter` = a photo card lands (twice).
Measured in the bed: paper **-13.91 dBFS** in the master against the
shutters' -10.42, so the resting state arriving sits 3.5 dB under an event
landing, and lands where the thunks used to at -14.3.

### THE PUNCH PLAN WAS MEASURED FROM THE LAST DELIVERY, WHICH GETS OVERWRITTEN

A real bug, not a verification wrinkle, and it had been there since the
punches were built. `resolve_punch.py` read `renders/clip08_FINAL.mp4` —
the file `render_and_finish.py` overwrites every version. So each run
measured whatever shipped last.

**v49 and v50 hold identical speech and returned different plans:**
`[10.5, 20.8, 26.2, 31.9, 39.6]` and `[10.5, 22.6, 28.2, 36.7]`.

Two causes, both fixed:

1. **The source.** Now `renders/styles/_base.mov` — the tightened cut with
   PCM audio, no graphics and no sfx bed, which does not change between
   versions. It is also the speaker's own delivery rather than our mix: the
   EQ's +4dB at 3kHz re-weights which windows read loudest, and his emphasis
   is a property of his speech, not of our tone shaping.
2. **The selector was knife-edge.** Every candidate sits +4.0 to +5.5 dB
   inside a 5.5 dB total range, so a hard threshold at +4.0 chooses between
   near-ties — a fraction of a dB flips which qualify — and suppression ran
   in TIME order, so one flip cascaded through every later pick and a weaker
   early peak could suppress a stronger later one. Now: **rank by dB,
   suppress in rank order, take the top `MAX_PUNCHES`**, with `MIN_DB` kept
   only as a floor. That is invariant to any global level shift. Verified
   across every delivered version v42-v50: all now return the same plan.

**And the clip has THREE bold moments, not five or eight.** Ranked on the
clean cut: 23.80s +5.5, 36.90s +4.9, 13.10s +4.5, then a clear step down to
29.20s +3.5 and 44.60s +3.5. The break is real and the floor lands on it.
Three punches, 10.7s and 13.1s apart, none before 9.0s, each 1.136x held
2.20s. Verified by reading `ZoomX` off all 17 V2 items: every piece at its
shot's base or exactly 1.1364x, max one per shot, shot 0 unpunched.

### The chat goes back to Twitch's own black, and it is MOUNTED

George: *"no the twitch chat needs to stay black with the normal colours of
the twitch chatters."*

The blue panel with white usernames was a graphic that QUOTED chat. This is
chat: Twitch's own `#18181B` and the chatters' own colours.

**WHICH COSTS IT ITS EDGE, and the number is the one this file already
knows.** Measured per-pixel against the real board under the box footprint:

| panel | vs board, median | outline visible (>=1.6:1) |
|---|---|---|
| `#18181B` (Twitch's own) | 1.03:1 | — |
| pure black | 1.16:1 | **7.2% of its own perimeter** |
| `#070C11` (the first chat box) | 1.09:1 | 7.0% |
| `C.blue` | 3.41:1 | **97.5%** |

A box whose outline is distinguishable along 7% of its length is not a box.
The panel disappears into the roster rows and the tilt George liked goes
with it — the identical 1.08:1 defect the palette pass deleted four devices
for.

**So the black card sits on a BLUE PLATE**, square corners against the
card's 52px top radius, so the blue reads as a rule down the sides and as
two triangles at the shoulders. **That is R5's own construction** — its
near-black chat card sits on a cyan plate with square corners — in the
Polymarket palette. One element carrying the edge, not a hairline plus a
bloom plus an inset highlight plus a rule stacked on a panel nobody can see.
The drop shadow went with the blue: a rgba(0,0,0,0.55) bloom does nothing
over board pixels at Y' 22.

**THE USER COLOURS ARE LIFTED, AND THAT IS MORE FAITHFUL, NOT LESS.** Twitch
ships **"Readable Colors" ON by default**, so a dark user colour is already
lifted on the viewer's own screen — rendering raw hex would show something
no Twitch viewer ever saw. Measured against `#18181B`, **17 of the window's
41 names (41%) sit under the 4.5:1 floor** and four are unreadable: `#0000FF`
2.06:1, `#000000` 1.19:1, `#B22222` 2.65:1, `#8A2BE2` 2.97:1. The lift holds
HUE AND SATURATION and bisects lightness to the floor — the identical move
`theme.tsx` makes for `blueLight`, so the project has one rule for this and
not two. Most moves are invisible (`#FF0000` -> `#FF1010`, `#2E8B57` ->
`#30915B`); the four that matter become `#6E6EFF`, `#808080`, `#DD4F4F`,
`#A55DE9`. `chat.json` keeps the raw value in `colour` and the drawn one in
`display`, so the record stays true.

Verified on the delivered file: **67,704 coloured username pixels across 8
sampled frames, spanning every 30-degree hue band** — the names are not
white. The card interior reads modal (8,8,11) against the board's (17,26,39);
the limited-range encode darkens `#18181B`'s (24,24,27) uniformly, which
RAISES the text contrast, so the lift floor is conservative.

Two defects caught by compositing over the real board before shipping, both
invisible in the component preview:

* **the plate and the card rotated about different points.** `50% 60%` of
  the plate is 9.6px below `50% 60%` of the card, and at -2.4deg that sheared
  them — the mount rendered visibly thicker top-left than bottom-right.
* **a pasted link is one unbreakable token** and at 580px ran through the
  padding to be clipped mid-word by the panel edge, which reads as a broken
  render rather than as chat. `overflowWrap: anywhere`.

### The punches were chopping the opening shot, not punching it

George: *"some of the zooms on the player cams are a bit quick and harsh
toward the start of the video."* Three measurements, all agreeing with him:

1. **SHOT 0 RUNS 0.00-8.97s, ONE CONTINUOUS SHOT** — the longest in the
   clip's first half — and BOTH head punches landed inside it, at 2.90 and
   7.00. That split one shot into five pieces (2.78 / 1.50 / 2.60 / 1.50 /
   0.58) with four cuts between them, every one the same framing jumping in,
   back, in and back, before a single real cut had happened.
2. **THE JUMP WAS 97px.** At 0.18 inset (1.220x) a feature at the pane edge
   moves 97 canvas px in ONE frame.
3. **1.50s IS A FLICK.** The base shots around it run 2.6-3.3s, so the
   punched piece was conspicuously the shortest thing on V2 every time.

| | v49 | v50 |
|---|---|---|
| inset / zoom | 0.18 / 1.220x | **0.12 / 1.136x** |
| edge jump in one frame | 97px | **65px** |
| hold | 1.50s | **2.20s** |
| `skip_head` / `MIN_SEP` | 2.5 / 4.0 | **9.0 / 5.0** |
| punches | 8 | **5** |
| punches in the first 9s | 2 | **0** |
| V2 pieces | 22 | **16** |

**ONE PUNCH PER BASE SHOT, which is the structural half of the fix.** A
punch tightens a shot; two of them restructure it. Where a shot holds more
than one candidate the LOUDEST wins and the rest are dropped, never nudged —
a punch moved off its peak marks nothing.

**All eight old peaks measured +4.1 to +4.5 dB — a 0.4 dB spread.** The
threshold was not picking BOLDER moments, it was picking the eight loudest
windows of a flat read. Five is what `resolve_punch`'s own docstring always
claimed ("one every ~9s reads as a device rather than a tic"); eight was
drift.

Verified by reading `ZoomX` back off all 16 V2 items: every piece sits at
its shot's own base framing or at **exactly 1.1364x**, max one punch per
shot, and shot 0 is a single unpunched piece.

**A GOTCHA THAT INVALIDATED THE FIRST VERIFICATION.** `resolve_punch.py`
measures its peaks from `renders/clip08_FINAL.mp4`, and `render_and_finish.py`
OVERWRITES that same file. So after a render, re-deriving the plan measures a
different file than the build did, and zipping the fresh plan against the
timeline items misaligns them — which looked like four punches at wrong
ratios and was nothing of the kind. Verify against the `punches.json` the
build wrote, not against a re-measurement.

### No dead space between chat windows, and the lever is window LENGTH

George: *"the twitch chat needs to come back quicker make sure there's no
dead space maybe at the end its fine but we're getting there."*

He is right about what an OFF gap is here. The content pane's frame-to-frame
delta over this cut measures **median 0.0005, max 0.27, zero frames above 0.5
across all 2822** — one motionless roster board start to finish. While the
chat is away the lower pane is a frozen frame, and 2.5s of that three times
is 7.5s of nothing happening.

**CUTTING `OFF` ALONE WOULD HAVE REPEATED v47.** The cycle count is
`round((span + OFF) / (ON + OFF))`, so dropping OFF to 0.9 on its own takes n
from 4 to 5 and adds two state changes — exactly the "going way too quickly"
that removing two cards was meant to solve. Raising `ON` by the same amount
holds n at 4, so the switching rate is IDENTICAL and only the dead air moves:

| | ON | OFF | windows | each | gaps | chat | state changes |
|---|---|---|---|---|---|---|---|
| v49 | 7.0 | 2.5 | 4 | 7.48s | 7.5s | 29.9s (64%) | 7 |
| **v50** | **9.0** | **0.9** | 4 | **8.68s** | **2.7s** | **34.7s (74%)** | **7** |

4.8s of frozen pane becomes 4.8s of chat for no extra cut. 0.9s is still a
beat and not a blink — 54 frames against a 0.34s entrance — and **0 messages
now fall into a gap**, where the 2.5s version lost a handful to it.

Measured off the delivered file rather than the plan, by counting the blue
mount per frame: **4 windows at 8.63s, gaps 0.93 / 0.95 / 0.95s, 34.55s of
46.87s (74%), 2.83s of dead space.** The end is left as it is on his note:
the 0.25s between the two story cards and the 0.77s after the last one are
both under `MIN_GAP`, so no window is attempted in either.

### POLYMARKET: #2E5CFF and white, and what each colour can carry

George sent the logo: *"let's use polymarket blue colours and their design
typography for this - blue and white text for example - blue and white for
animations etc"*.

**Sampled off the file he sent rather than guessed.** The mark is exactly
two colours: **#2E5CFF over 96.1% of the image and #FFFFFF over 3.0%.**
Everything else in it is antialiasing.

| | ratio | |
|---|---|---|
| white on `#2E5CFF` | **5.13:1** | the chat box. Clears the 4.5 body floor |
| `#2E5CFF` vs the real roster board | **3.52:1 median**, 98.2% of footprint ≥1.6 | the blue needs no keyline — it has its own edge |
| the graphite chassis it replaces | 1.67:1 | for comparison |
| `#2E5CFF` on white paper | 5.13:1 | the press card's outlet rule |
| `#2E5CFF` vs a hard black caption stroke | **4.09:1** | **under the 4.5 floor** |

**So there are two blues, and the second one is not decoration.** The brand
blue fails as caption emphasis against the captions' own hard black stroke.
`C.blueLight` **#5C80FF** is the same hue (227°) and the same saturation
(1.00) lifted from L 0.59 to 0.68, and reads **5.99:1** — which matches the
6.06:1 of the vermilion it replaces almost exactly. Rule: **`blue` on white
and as a fill; `blueLight` for anything that has to hold against dark.**

~~**A Twitch user colour cannot survive on the brand blue.**~~ **REVERSED by
George — see "The chat goes back to Twitch's own black" below.** The
reasoning was sound and the premise was wrong: the answer was not to repaint
the usernames, it was not to paint the panel blue. The blue panel stays as
the measured record of what white-on-#2E5CFF costs; it is not what we do.

**The 2px keyline is gone.** It existed because the graphite chassis
measured 1.67:1 against the board and needed an edge drawn on it. At 3.52:1
the blue does not, and leaving it would be the stacked compensation this
file keeps warning about.

**Typography: Inter, and the reason Archivo was chosen no longer applies.**
Archivo was picked on measurement — a `wdth` axis so figure/label/context
could separate by weight and width instead of colour, and digits at a 0.35%
spread so the counters stopped reflowing. **This cut has no counters and no
figure cards**, so neither argument survives. What is left to serve is
Polymarket's register, and their wordmark is a neo-grotesque; Inter is OFL,
is the de facto UI face of this category, and is the closer match. Archivo
stays vendored — if figure cards come back it is still the better tool,
because Inter's digits run a **37% spread** by default and need `tnum`
switched on explicitly.

Their wordmark is probably custom and not ours to redistribute. This matches
the register, not the letterforms, and should be described that way.

**The dead cards were re-pointed, not deleted.** `Chips.tsx`, `Graphics.tsx`,
`People.tsx` and `Tweet.tsx` are out of the cut but still import `C.surface`,
`C.keyline`, `C.accent` and the rest. Those names now map onto the Polymarket
palette, so the build does not break AND a card put back comes back blue
instead of reappearing in a warm graphite that is no longer the house look.

### Only the chat and two stories — so the chat has to cycle itself

George: *"i want the twitch chat visible with no other animations other
than the story pop ups of jingg and jonahp/jerwwin as they are relevent to
what he's saying ... keep the chat visible on these clips."*

Gone: the tweet, the figure pair, the ratio bar, the roster grid and the
KRU exhibit. Left: his own chat, and two published news stories at 37.60
and 42.10.

**Which breaks the scheduling model that has run for four versions.** The
chat used to live in the GAPS between cards. With two cards the first free
stretch is **37.6 seconds**, and one unbroken 37-second window is not "let
it come in and out" — it is just leaving it on.

So a long stretch is now CYCLED: `ON = 7.0s` of chat, `OFF = 2.5s` of bare
board, repeating, with the leftover shared across the cycles so the last one
is not a stub. The gaps are not empty — the board is the thing he is looking
at, and it gets a beat to itself.

| | |
|---|---|
| chat windows | **4**, 7.48s each |
| chat on screen | **29.9s of 46.9s (64%)** |
| cards | 2, 8.25s |
| states | 6 — one change every 7.8s |

For comparison the complaint that started this was v47 at one change every
2.6s. This is three times slower again.

**The shutter is the whole sound design now.** "Make the snapshot noise
louder" a second time: −12.0 → **−9.5 dBFS** target peak. That is
defensible here in a way it would not have been before — with every drawn
card gone there are no thunks left for it to sit against, so it is not
competing with another cue, it is the only one.

### Buying chat time out of card durations was the wrong lever

George, on v47: *"now it's going way too quickly - keep the twitch chat and
remove chip amer, stat card is pointless, just keep the stories for future
reference, keep chat on the screen and let it come in and out."*

The previous pass took **7.45s out of the card durations** to open a chat
window after every card. It worked arithmetically and failed on screen,
and the reason is measurable: **it is the SWITCHING RATE that reads as
fast, not the individual durations.**

| | v47 | v48 |
|---|---|---|
| cards | 9 | **7** |
| chat windows | 9 | **4** |
| states in 46.9s | **18** | **11** |
| one change every | **2.6s** | **4.3s** |
| card durations | shortened to 2.3–3.1s | **back to full, 3.5–4.8s** |

So the room comes from **removing cards, not from shortening them.**
Dropping `rm_ChipAmer` and `rm_StatCard` buys the same chat time as
shortening six cards did, and nothing is rushed. The lesson generalises:
when a pane has to carry two kinds of element, cut the count before you cut
the durations — a shorter card still costs a state change, and the state
changes are what the viewer feels.

`rm_ChipAmer` was also the one card the rhythm could never accommodate: it
started at 1.20 against the tweet's 3.30, and 2.10s cannot hold a card and
a chat window.

**And a note on the other direction.** The card durations restored here
(Tweet 3.57, Pair 4.80, Ratio 3.50, Grid 4.00, ExKru 4.30, StoryPrx 4.25,
StorySen 4.00) are the ones that shipped through v44 and v46 without a
pacing complaint. The shortened set was never independently wrong — every
card still cleared its own animation with 1.4s+ of settled hold — it was
wrong *in aggregate*.

### The back half has no room for chat, and the anchors are why

With the two cards out, three remain back to back: **Grid → ExKru →
StoryPrx → StorySen**, 28.80 to 46.10, 17.3s of continuous card. Their
anchors sit 4.4s apart and the cards are 4.0–4.3s, so there is no gap to
put chat in without shortening them again — which is the lever that just
failed.

Two honest options, both modelled before choosing:

| | cards | states | change every | longest chat stretch |
|---|---|---|---|---|
| **A** (shipped as v48) | 7 | 11 | 4.3s | 5.7s |
| **B** — Grid and ExKru out too | 5 | 9 | 5.2s | **14.5s** |

B reads more calmly and gives the chat 25s, but it opens a 14.5s unbroken
chat stretch in the middle, which is not "come in and out" either. B only
works if a story card moves earlier to break it — and the story cards CAN
move, unlike the exhibits: `rm_ExKru` is anchored to "those people that get
replaced", while the two news stories are free-floating inserts with no
line of their own. Moving `StoryPrx` to ~28.0 and `StorySen` to ~37.0 gives
5 cards, 4 chat windows, a change every 5.2s and a longest stretch of 5.9s.

Recorded rather than decided, because which cards survive is George's call
and "just keep the stories" reads both ways.

### The chat is the DEFAULT state; the graphics interrupt it — PARTLY SUPERSEDED

**The inversion stands; the way it was paid for does not.** Buying chat
time out of card durations made the clip read fast — see the section
above. The durations are back at full and the room comes from removing
two cards instead.

George: *"it needs to be more apparent throughout the whole video. So it
needs to be like on the screen, and then it needs to go out when we're
putting an animation in. Then the animation needs to go out. Then the chat
comes back in. So it's like constantly there."*

That is an **alternation**, and it inverts which element owns the lower
pane. Up to now the cards owned it and the chat took what was left — two
windows, 7.6s. Now the chat is the resting state and a card is the
interruption.

**The pane holds one thing at a time, so the chat's share has to come out
of the cards.** A card's START is anchored to the line it supports and must
not move — that rule is already in this file and it still holds — so the
room comes out of DURATIONS only.

| | before | after |
|---|---|---|
| card time | 33.75s (72%) | **26.30s (56%)** |
| chat time | 7.6s (16%) | **18.8s (40%)** |
| chat appearances | 2 | **9** |
| lower pane occupied | 88% | **96%** |

**Shorten against the card's own animation, not to a round number.** Each
one was checked for the frame its entrance completes and the frame its exit
begins, and the settled hold between them:

| card | frames | entrance done | settled hold |
|---|---|---|---|
| Tweet | 214 → **156** | f22 | 1.98s |
| StatCard | 210 → **138** | f36 | 1.50s |
| Grid | 240 → **162** | f44 | 1.77s |
| ExKru | 258 → **162** | f64 | **1.43s** |
| StoryPrx | 255 → **168** | f24 | 2.15s |
| StorySen | 240 → **184** | f24 | 2.42s |

`ExKru` is the tightest and the reason is its own marker: the ring draws
from frame 34 to 64, a full second, so a 2.70s card spends 37% of itself
being annotated. `Pair` and `Ratio` already had more spacing than they used
and are untouched.

**The one place the rhythm breaks is structural.** `ChipAmer` starts 1.20
and `Tweet` starts 3.30 — 2.10s apart, which cannot hold a card AND a chat
window. Those two run back to back and the chat sits either side. Nothing
to fix there short of dropping a card or moving an anchor, and both are
worse.

**LEAD and TAIL came down to 0.10 / 0.08**, from 0.34 / 0.30. The chat is
on V3 *below* the cards, so a few frames of overlap are covered, not
collided — the generous margins were protecting against a collision that
the track order already prevents, and they were eating a third of every
short window.

The resulting rhythm, which is the thing to look at rather than the table:

```
 0.08  chat        1.20  ChipAmer    3.30  Tweet
 5.98  chat        7.60  StatCard    9.98  chat
11.60  Pair       16.48  chat       19.40  Ratio
22.98  chat       28.80  Grid       31.58  chat
33.20  ExKru      35.98  chat       37.60  StoryPrx
40.48  chat       42.10  StorySen   45.25  chat
```

### A dark panel over the board must not go translucent — AGAIN

George: *"i didn't mean the twitch chat should be overlayed completely on
the screen, it should be inside of a box so you can see the text itself, im
just saying always keep the bottom screen for what fns is looking at - tilt
the chat slightly put it on an axis a bit, remove the NRG popup, rest are
all good, also i like the way you handled these animations here - make the
twitch chat a bit smaller too, make sure it has animations coming in and
out."*

**"Remove the border" was over-read.** He was pointing at R5's chrome — the
64px radius and the cyan shoulder plate — not asking for the chat to be set
loose on the board. Borderless over a busy roster board leaves the text with
no ground and the pane with no owner. The box is back, and a SMALL box is
what satisfies "always keep the bottom screen for what fns is looking at":
the board stays the pane's subject and the chat is a visitor on it.

**580×420 at 36px**, against the borderless 716-wide full-height band at
46px. It occupies 23% of the content pane where the previous version
effectively claimed all of it. Tilted **−2.4°**, shallower than the story
cards' −3.4/+3.1 so three tilted objects in one clip do not read as one
repeated gesture, and spring-driven so it settles into the angle.

**AND THE REPEATED MISTAKE, which is the thing worth keeping.** The previous
build dimmed the box to 0.32 behind a drawn card. This file already contains
the finding — *a dark card must not fade, because at 40-60% opacity the
board's own rows read through it and it dematerialises into mud* — written
for card exits, and it was repeated here within two turns. Measured on the
transition frames: at partial opacity the chat text was ghosting over the
roster rows with nothing behind it, on both the entrance and the exit.

So the chat is now **present or absent, never see-through.** `presence`
drives SHAPE only — a 34px lift, a 0.90→1.00 scale and the tilt settling in
— while opacity reaches full in the first quarter of the entrance and stays
there. Verified on the alpha: the box measures **82.2% fully-opaque pixels
at every sampled frame** of entrance, hold and exit, the remainder being
the shadow and the antialiased tilted edge. There is no frame where the
board shows through it.

The general rule, now stated twice because it was learned twice:
**anything dark composited over this board transitions by GEOMETRY — a
scale, a travel, a clip — and never by opacity.** Paper and stroked type
may fade; a dark panel may not.

### Nine graphics, and the chat gets 7.6 seconds — SUPERSEDED

**Re-timed; see the section above.** The cards gave back 7.45s and
the chat went from two windows to nine. Kept for the reasoning about
why the pane cannot hold both at once, which is unchanged.

`rm_ExNrg` is gone on George's instruction. It was the weakest exhibit of
the set anyway: the crop is mostly an empty BENCH / OPTIONS column, so a
full 5/5 roster read as white space next to KRU's 1/5.

Dropping it opens **22.90–28.80, the clip's only long gap**, and that is
where the chat now gets the pane to itself.

The chat lives in the gaps between graphics, entering after one leaves and
exiting before the next lands (0.30s tail, 0.34s lead). A gap has to be
worth an entrance — under `MIN_GAP = 1.8s` the box would appear and go
inside a second, which is the flicker, not the feature. That leaves:

| window | length |
|---|---|
| 16.70–19.06 | 2.36s |
| 23.20–28.46 | 5.26s |
| **total** | **7.6s of 46.9s (16%)** |

**Be straight about that number.** Two appearances is not much chat, and it
is a direct consequence of nine graphics covering 76% of the clip. The pane
cannot hold both at once: measured, the 816-wide cards span x 132–948 and
the 1008-wide ones x 36–1044, so there is no horizontal lane for a box to
live in beside them, and below the cards there are only 80px before the
platform-UI line. **The dial is card durations, not chat opacity** — the
previous attempt to buy more chat by making it translucent is exactly the
defect above.

The windows are generated from `resolve_lean.EXHIBITS`, so they cannot
drift from the cards they are dodging.

### The chat overlay, developed — and three reversals of what R5 measured

George, on the first test: *"the overlay looks good was that taken directly
from the moment of fns talking? - also it doesn't look animated at all, add
the remotion stuff, remove the border, make it so it APPEARS over what he's
looking at on stream, and make it so the other pop ups you did for the
earlier version show up too - when the pictures of jingg and jonah come up
the chat should fade out - so the chat can come in and out you know?"*

**Yes, it is his own chat from that moment.** VOD 2905408276, offsets
5978.8–6045.9, which is clip 8's source window, each message remapped
through the same keeps `build_v7.py` cut with. The messages sit on the line
he was speaking when they were typed.

**THREE REVERSALS, all his call, all recorded as reversals.** The first
build was instant, borderless-less and self-contained because that is what
R5 measures. He has watched it and wants otherwise:

| | R5 measures | we now do | why |
|---|---|---|---|
| arrival | one frame, whole message height, no fade | spring over 11f, rise 16px, fade in | "it doesn't look animated at all" |
| container | dark card, 64px radius, cyan shoulder plate | nothing drawn | "remove the border" |
| placement | replaces the lower pane | floats over the board | "make it so it APPEARS over what he's looking at" |

The R5 measurements stay in this file as a record of what R5 does. They are
no longer what we do.

**ANIMATING A STACK WITHOUT MEASURING IT.** A new message has to displace
the ones above, and its height is unknown until the browser has wrapped it
— so there is nothing to interpolate. The grid trick does it: a single-row
grid whose `grid-template-rows` goes `0fr -> 1fr` animates from zero to the
child's natural height with the child clipped meanwhile. No ref, no measure
pass, correct for every wrap and every emote. Animate the gap on the same
progress or the spacing opens before the text arrives. Verified on the
alpha: across one arrival the stack centroid moves −17.3, +35.0, −3.0px over
successive samples and coverage goes 122080 → 101422 → 131913, i.e. it is
genuinely growing rather than cutting.

**With no panel behind it, the text needs a ground.** A coloured username
over a busy roster board is unreadable on its own, and a scrim would be the
border he asked to remove. A two-layer text shadow does it instead, plus a
`drop-shadow` on the badge images.

### Ten graphics and a chat do not both fit, and the number says so

Taking "the chat should fade out" literally and applying it to every card
puts the chat at full strength for **0.35 seconds of 47** — the ten cards
cover 76% of the clip, so a blanket rule makes the chat a flicker rather
than a presence. The first attempt did exactly that and was invisible.

So the fade is graded by what the graphic IS, in `build_chat.py`'s `LEVEL`:

| level | which | reasoning |
|---|---|---|
| **0.00** | `Tweet`, `StoryPrx`, `StorySen` | a photograph or a whole document. George named these two by name; a face on screen takes the eye completely |
| **0.32** | the drawn exhibits and figure cards | the chat survives as movement behind them, which is what keeps the pane alive. 0.15 was tried and is not there at all |
| **0.70** | `ChipAmer` | a 1.8s tab anchored off the frame edge. It displaces nothing |

**It blurs as it dims.** Dimming alone leaves it legible, and legible text
behind a graphic is still competing for the eye — 2.4px at full dim.
Leaving takes 0.35s and returning 0.5s, the same asymmetry as a card exit
and for the same reason: the viewer is reading the graphic, not the chat.

The schedule is generated from `resolve_lean.EXHIBITS` rather than typed,
so it cannot drift from the cards it is reacting to.

**The honest caveat.** Even graded, this is a crowded pane: ten graphics and
a chat track in 47 seconds, with the chat at full strength only in the gaps.
If it reads busy the fix is fewer cards on a chat build, not a lower chat —
and that is an editorial call, not a measurement.

### Track order, with the chat in it

`V1 content | V2 facecam | V3 chat | V4 cards | V5 titles | V6 captions`

V3 is the slot the pane dip used to occupy, which is now free. The chat
belongs **below** the cards: a graphic should land on top of it, not beside
it. The dimming is baked into the clip because Resolve's `Opacity` is one
static value per timeline item and this needs ten of them.

### Emotes come back, but almost none of them are Twitch's

`twitch_chat.py` reads emote fragments and the component renders them from
the CDN. In practice they barely appear: **0 of 47 fragments** in the
densest crowd burst found in the archive (vod 2882589453 @15965, an ace),
and 0 across clip 8's whole window. The hype there is typed as words —
"gg", "ACE", "WWWW", "Hooolyyy".

The limit to know about: Twitch's GQL returns **first-party emotes only**
(global and channel subscriber). **BTTV, FFZ and 7TV do not appear** — a
big channel's chat is mostly those, and they would need their own APIs and
their own emote-name-to-image maps. Until that is built, an emote-heavy
window will render as plain text where the viewer saw pictures. Not a
blocker for this clip; it would be for a hype moment.

### LottieFiles — licence-clean, and mostly the wrong shape for this project

George sent the free-animations library. Checked rather than assumed,
because this file has recorded two licence traps already.

* **The Lottie Simple License permits commercial use** — "download,
  reproduce, modify, publish, distribute, publicly display, and publicly
  digitally perform ... including for commercial purposes" — and
  **attribution is not required**, only encouraged. One clause worth
  knowing: distribution of the FILES must carry the same terms, a
  share-alike on the asset. Rendering an animation into pixels is not
  redistributing the file, so a delivered clip is clear; shipping the .json
  to a client is not.
* **Check per file.** The site mixes Free and Premium, and a creator can
  set other terms. Same rule as npm: read the field on the thing you are
  taking, not the field on the site.
* **`@remotion/lottie` is `SEE LICENSE IN LICENSE.md`** — the Remotion
  company licence, i.e. the same seat gate as `cli`, `renderer` and
  `bundler`. Adding it changes nothing, because that gate already applies
  to rendering at all. `lottie-web` itself is **MIT (5.13.0)** and can be
  driven from a plain component if the gate ever needs avoiding — but drive
  it with `goToAndStop(frame)`, never let it animate on rAF, or it is the
  same determinism trap already recorded for framer-motion and anime.js.

**Where it does NOT belong.** This project's rule is that nothing on screen
is a phrase or a shape I invented — every figure is read off the board or
independently sourced. A generic Lottie flourish is invented by
definition, and the catalogue is full of exactly the product-hook furniture
already refused once: confetti, light bursts, odometer counters, logo
stings. Reaching for it to make a clip livelier would repeat the mistake
the zoom punches made.

**Where it might.** Things that are structure rather than content and that
we currently hand-build: a pointer or arrow, a transition wipe, a
progress/reveal on a figure that is already sourced. Worth a look only
against a specific need, with George picking the file.

### The pane dip is REMOVED, and the obvious argument for it is wrong

Asked to re-solve the dip's depth against the new chassis, the measurement
removed the dip instead. **But the argument that first looked decisive is
false, and it must not go in this file as a reusable test.**

**THE TEST THAT DOES NOT WORK.** "An alpha overlay multiplies every pixel in
the pane, so the brightest pixel must fall with the mean — R1 holding YMAX
255 through its dark runs proves those are the game's own black frames, not
an edit." Four independent judges led with this. It is disproved by **our
own dip**: dip 1 at 14.80s holds YMAX at a dead-flat 255 and p99.9 at a
dead-flat 253.0 on every one of its 34 frames while the pane mean falls
31.85 → 15.65. 15,120 pixels — 1.556% of the pane, bounding box y1003-1614,
i.e. the card — hold their exact pre-dip values, median ratio 1.0000.
Anything composited ABOVE the dip is untouched, and a dip on V3 under cards
on V4 is built to do exactly that. R1's protected block is one connected
region at frame y1486-1560, visually confirmed as the `renyan` Twitch
watermark, which OBS composites above the game. **Consistent with a content
change or with an editorial dip. The pixels do not discriminate.**

**THE GROUNDS THAT HOLD** are independent of the reference, which matters
because the standing rule is that "the reference does not do this" is not by
itself a reason to remove anything.

1. **It punctuates nothing.** The content pane's frame-to-frame delta
   measures **median 0.0005, max 0.27, with ZERO frames above 0.5 across all
   2822** — one static roster board start to finish. The dip's own rule when
   it was built was "it goes where a document changes and nowhere else", and
   in this cut there is nowhere. (The older note recording a change at 5.5s
   was true of the 67.2s cut, which began before the tweet-to-board switch.)
2. **Dip 1 fired mid-hold under a motionless card.** Measured across it: the
   board falls uniformly — right edge 94.0 → 54.7, left edge 50.2 → 29.5,
   board top 40.8 → 24.1, all ×0.58-0.59 — while the card body reads
   **82.3361 before and 82.3371 during**. Identical to four decimals. For
   0.567s everything except the card got 41% darker and came back, with
   nothing arriving or leaving. That reads as a brightness glitch.
3. **Dip 2 ramped through an entrance.** It sits in a real card gap, but its
   hold runs past 33.20 where `rm_ExKru` begins, so the biggest graphic in
   the clip played its 22-frame reveal — scale 0.78→1.00, blur 9→0,
   clip-path wipe — on a backdrop that was changing exposure.
4. **The act boundaries cannot rescue it.** The CDL steps on V2, the
   facecam; the dip darkens V1, the content pane. Different panes, so it
   cannot cover the grade step.

**And the one alternative worth naming was rejected on merit, not missed:**
holding dip 1 as a permanent scrim under the card. Dimming the board so a
card can land is the same stacked compensation the palette pass deleted the
hairline, the shadow bloom, the inset highlight and the gold rule for. The
chassis measures 1.67:1 against the board with its own 2px keyline; it does
not need the board to get out of the way.

**What survives from the original dip work:** Resolve composites in linear
light and the transfer is `(1 - alpha) ** 2.4` — the identical clip measures
0.189 luma ratio in ffmpeg and 0.015 in Resolve, a 12x difference — so
anything composited in Resolve with an intended opacity still has to be
solved through that gamma. The track order it motivated is unaffected.

### Re-solving the colour arc: a white in his own room is the measurement

**Invert the CDL rather than re-render.** ASC CDL is `(in*S + O)^P` then a
saturation lerp toward luma, and every step is invertible, so a candidate
grade can be applied to the *recovered ungraded* pixels of a delivered frame.
`scratchpad/v44/cdl.py` is nine lines. It made twelve candidates comparable
in minutes instead of twelve renders — **but see the warning below; it is a
screening tool, not the answer.**

**The first thing it showed is that the clash was manufactured.** The
ungraded facecam measures **R−B +5 to +7**: his room is naturally warm and
already sits where the chassis (+11) and the paper (+9) sit. The arc pushed
act 1 to −4.8, a 12-point swing into cool away from both.

**THE MEASUREMENT THAT DISCRIMINATED is a real white in his room** — the
IKEA shelf, the picture frame, the YouTube plaque. Mask the near-neutral
brights (luma > 165, chroma < 45) **on the recovered ungraded pixels**, so
the identical pixel set is tracked through every candidate, then read their
R−B back off each one. Pane-mean R−B separated nothing; this separated
everything. A white that swings across a clip is the definition of footage
that has been graded.

| | act 1 | act 2 | act 3 | swing |
|---|---|---|---|---|
| white-point error, before | −18.1 | −6.0 | +29.8 | **48.0** |
| after | **−4.6** | −6.0 | **−0.1** | **5.9** |
| face pixels at R ≥ 254, before | 0.003% | 0.330% | **2.327%** | |
| after | 0.002% | 0.393% | **0.730%** | |
| pane R−B, after | +7.4 | +5.1 | +18.9 | |
| saturation, after | 31.3 | 41.3 | 49.6 | |

The arc survives and still grows on both axes; what went is the swing.

**COUNT BLOWN FACE PIXELS PER CHANNEL, AND CHECK WHETHER THEY ARE A SLAB.**
Act 3 of the old grade put 2.33% of his face at R ≥ 254 with a red standard
deviation of **1.53** across the top luminance decile — approaching one dead
value, which renders as a solid blown patch on the cheekbone rather than a
speckle of specular highlights. Now 0.73% at sd **7.60**: real variation.
This is also what rejected the candidate that won the panel's vote outright
— it moved the same defect into act 2, putting **15.93% of his face at one
dead value** at t=30, on the act that is 39% of the clip.

**PUT THE WARMTH IN OFFSET, NOT SLOPE.** Slope is gain, so it scales the
highlights hardest and lands the warmth on exactly the white objects the
test is watching. Act 3 moves red from slope to offset and mirrors it in
blue, which holds the skin and cools only the highlights. Act 1's cool was a
**blue gain of 1.09**; taking it down removes the cool with red left
untouched, so no new face clipping is even possible.

**ACT 2 IS UNTOUCHED AND SHOULD HAVE STAYED THAT WAY ALL ALONG.** Measured
in S-CIELAB on the real graded pixels, one R−B point of pane shift is worth
0.249 ΔE00 (sd 0.018 across seven pairs), so act 2's spread across all
candidates is at or inside the just-noticeable difference. It is also the
grade that has shipped for many versions. Changing it could only lose.

**THE MODEL IS NOT THE RENDER, AND THAT COST A CYCLE.** The inversion
round-trips to 0.000/255 — which proves only that the arithmetic is
self-consistent, not that Resolve grades in the same space. Measured against
the actual render, **Resolve responds about half as much as the code-value
model predicts**: the model said act 1's whites would land 0.2 off source
and act 3's 2.3 off; the render gave 9.1 and 8.3. Use the model to screen
candidates, then **take two real renders, measure the sensitivity, and solve
from that** — one iteration of exactly this took 9.1/8.3 to 4.6/0.1.

**One judge's pivotal evidence did not reproduce, and it is worth
recording.** It reported the ungraded skin arc as 73.5 → 49.6 → 37.8 — "his
face is warmest in the news and coolest on the cost" — and three of four
judges ranked its pick first partly downstream of that. Measured across
eleven frames the skin is **72.3 / 77.6 / 75.3, flat**; what cools is the
room's *neutrals* (−0.8 → −8.8 → −14.7). A white-balance drift read as a
skin arc. The conclusions survived on other evidence; the reasoning did not,
which is the reason to run the adversarial pass at all.

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
| ~~adopt~~ **REFUSED** | `remotion-bits` | **no LICENSE file of any name** — see "Licences — three corrections". The MIT field in package.json is not a licence document |
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

1. ~~Reference clips in the style he actually wants.~~ **ONE ARRIVED** —
   R5, the chat-overlay Short, measured in "R5: the chat-overlay
   reference" above. Still worth two or three more; R5 re-aims the
   lower pane and the seam but says nothing about cutting or pacing.
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
2. ~~**HyperFrames is unavailable**~~ **WRONG — STRUCK.** That tested the
   hosted USAGE endpoint, not the renderer. HyperFrames is Apache-2.0 and
   renders locally in headless Chrome + FFmpeg, with no seat gate. See
   "The thirteen tools George sent". Plain HTML through headless Chrome
   still does the job for static furniture.
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

### The black dip — SUPERSEDED, see "The pane dip is REMOVED" above

**Its premise is withdrawn.** R1's two dark runs are not established as
edits, the pixel test below cannot tell an overlay from a content change,
and the dip punctuates nothing in this cut. What survives is the
linear-light transfer. Kept for the reasoning, not as instruction.

#### (superseded) The black dip, and what Resolve does to an alpha overlay

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

## TWO BOOMS, AND THE PIPELINE AS A WEBSITE

### The third boom was a count problem, not a pick problem

George rejected the THIRD boom twice, on two different moments — *"you HAVE
the freedom to choose your own teammates"*, then *"you don't get paid FOR a
couple months"* — the second time as *"third boom is pointless - remove from
logic and video"*. Two rejections of two different picks is not selection,
it is **count**: a 45s clip carries two of these and the third pads whatever
it lands on. `MAX_PUNCHES = 2`, recorded as what it is — an editorial
constant from repeated review, not a measurement — and a CAP, so a clip with
one qualifying moment still gets one.

### Clip 8 rebuilt on the pipeline, and it lost its zooms

The flagship clip was still on the old bespoke scripts, and AGENTS.md
recorded that **its eight hallucinated caption cards were still shipping**.
Rebuilt through `make_clip`: 45.00s, −14.04 LUFS, nine of nine gates, and
**the eight cards are dropped**.

**But it came back with 0 bold moments**, so no zooms and no booms at all,
where it used to carry three punches. Eight emphasised cards to anchor to
and not one qualifying peak beside them. That is the "zero is an allowed
answer" path doing what it was built to do, and on this clip it is probably
too strict — the claim-only anchor filter plus the `DB_FRAC` floor compound.
**Stated rather than shipped quietly: clip 8 is currently a flat cut.**

### `web/` — the factory as a local site

`web/server.py`, stdlib `http.server`, no framework (the venv has no pip).
It drives the real commands — `run.py ingest/analyse/rank`, then
`batch.py screen/prep/specs/build/report` — as subprocesses with each
stage's output tee'd to `jobs/<job>/web/<stage>.log`. Nothing about the
editing is reimplemented, so the site follows the pipeline for free.

Three things it refuses to hide:

* **One job at a time.** A single worker thread. Resolve's API is on its GUI
  thread and `public/` is shared, so the queue is the constraint stated
  honestly rather than a UI limit.
* **The screen is the product.** 10 of 50 buildable on this VOD, and the
  table shows a verdict and a reason per clip. A spinner that emitted three
  clips from fifty would be lying about the yield.
* **Rights are a required field**, not a default, because the build refuses
  to start without one.

Verified against the real job: 50 screened / 10 buildable rendered in the
table, three clips playing from `renders/`, and the three validation paths
(bad URL, missing rights, duplicate job) each refused with their reason.

**A bug worth keeping, because it is the generic one for polled UIs.** The
job list re-rendered every 1.5s, so a row was torn out from under a click
and the click landed on nothing. Both lists now rebuild only when their own
signature changes — the same fix the clips grid already needed so a playing
`<video>` is not replaced mid-frame.
