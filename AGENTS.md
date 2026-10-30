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

## Three rules from review

**Status: stated, NOT enforced.** Three approaches were tried against the three
clips George flagged, and all three failed:

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
