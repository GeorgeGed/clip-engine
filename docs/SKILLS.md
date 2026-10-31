# Edit skills — the inventory, ready for Resolve

Every technique observed across the four references, with its measured
parameters and how to build it. This is what I should be able to execute when
Resolve opens.

| | R1 | R2 | R3 | **R4** |
|---|---|---|---|---|
| | CS2 receipts | VALORANT take | Pause (ad) | **PlatChat podcast** |
| Duration | 80.3s | 20.2s | 27.8s | **47.1s** |
| Cuts/min | 6.0 | **0** | 10.8 | **14.0** |
| Median shot | 7.9s | — | 1.8s | **2.09s** |
| Loudness | −11.79 | −14.26 | −15.64 | **−20.38** |
| Layout | split 0.418 | split 0.442 | floating window | **full-frame + replacement** |

Four references, four loudness targets spanning **8.6 LU**. There is no single
correct level — it is set by format. Podcast clips run quiet.

---

## 1. Multicam speaker cutting *(R4)*

PlatChat cuts **14 times a minute, median shot 2.09s, shortest 0.46s** — to
whoever is talking. Three participants, each full-frame.

This is the dominant technique in podcast clips and nothing else in the
reference set uses it. It is also the cheapest energy available: no effects, no
graphics, just cutting on the speaker change.

**Resolve:** one video track per participant, all synced. Blade at each speaker
change and disable the inactive ones. With an `edit.json` this is a list of
`{t, active_track}` and nothing more.

## 2. Full-frame evidence replacement *(R4)*

R1 put evidence in a lower pane. **PlatChat replaces the whole frame with it** —
VCT partnered-team lists, the 2027 schedule grid, a signing announcement, event
poster art — then cuts back to the speaker.

Stronger than a split when the graphic is dense and genuinely needs the room.
Weaker when you want the reaction visible at the same time.

**Resolve:** stills on V2 above the speaker, scaled to fill, hard cut in and
out. Hold is short — one to three seconds.

## 3. Tilted card overlays *(R4)*

Tweet screenshots dropped over the speaker at an angle, two or three at once,
not squared to frame. Reads as "receipts" without losing the face.

**Resolve:** PNG on V3, **Transform > Rotation ±4–8°**, drop shadow, scale to
roughly 60% of frame width. Animate in over 6–8 frames.

## 4. Meme reaction cutout *(R4)*

A face cutout with bold caption dropped in as punctuation — one appears for
about a second. Use sparingly; one per clip is the ceiling.

## 5. Two-pane split *(R1, R2)*

Facecam above, content below. **Seam at 0.42** — the most reproducible number
in the whole set (0.418, 0.4422, and clip-autopilot's 0.44 independently).

**Resolve:** facecam V2 zoom 1.322 / Position Y +558; content V1 zoom 1.0 /
Position Y −147. See `docs/RESOLVE-BUILD.md`.

## 6. Word-level captions *(all four)*

Universal across every reference. Placement and size are not.

| | position_y | glyph height | cadence |
|---|---|---|---|
| R1 | 0.44 (on the seam) | 0.052 | ~2.0/s |
| R2 | 0.747 | 0.039 | ~2.0/s |
| R3 | 0.897 | 0.110 | 3.14/s |
| R4 | ~0.62 | ~0.045 | ~2.5/s |

The rule is **put the caption where the content isn't**, not a fixed value.

## 7. Persistent topic banner *(R2, R4)*

R2 held a blue-boxed claim for the whole clip. R4 runs a headline along the
lower third throughout. Both answer "what am I watching" for someone who
arrives mid-scroll.

Distinct from R1's hook title, which is on for 1.5s then fades by 2.0s.

## 8. Hook title *(R1)*

Two lines, ALL CAPS, cap height ~140px, one coloured keyword per line, on at
0.00, holds to 1.5s, 0.5s dissolve out.

## 9. Speed ramps and punch-ins

Not observed in any reference — all four are talking-head formats. Carried from
the methodology for gameplay: dead time 1.6–2.2x with 8-frame ramps, one
slow-mo per clip at 0.35x on the payoff.

## 10. Audio

| | target |
|---|---|
| Podcast / multi-speaker | **−20 LUFS** (R4) |
| Talking head | **−14 LUFS** (R2) |
| Reaction / receipts | **−12 LUFS** (R1, R3) |
| True peak, always | **−1.0 dBTP** |

Duck game audio 7dB under speech, 120ms attack / 400ms release. Two-pass
loudnorm — single-pass lands a dB off. **No music bed in any of the four.**

---

## 11. Sound design — CORRECTED, and the honest state

**The earlier version of this section was wrong and led to a bad edit. Read
the correction before using any of it.**

**R1 and R2 are not on disk.** `reference/` is empty; only R3 and R4 survive
in the session scratchpad. R1 and R2 are the ONLY two references in our
format — facecam over content — so everything "known" about them is the
measurement table in STYLE-BASELINE.md from an earlier session that had the
files. **Re-supply them before making any further claim about how a clip in
this format should sound.**

**Neither R1 nor R2 is recorded as using sound effects.** STYLE-BASELINE.md
documents both closely — act structure, caption cadence, the 0.36s median
cut-to-sentence distance — and notes "neither reference has a music bed" and
"no cutting on music". No SFX observation appears anywhere for either.

**The SFX idea came from Pause's FEATURE LIST, not from a clip.** The row
"Frame-timed SFX on the punchline" sits in a table mapping Pause's
*advertised features* onto our schema. Nobody watched a clip in our format
doing it.

**R3 is an ADVERT, not a clip.** Its ~1.12 transients/second — which an
earlier pass used as the density target — are UI text-appear clicks as "Make
this / go viral." types on screen. Frames at 4.44/5.87/6.24/6.60/7.77s show
exactly that. It is a product demo with typing sounds and it models nothing
about editing a talking head.

**R4's transients cannot be separated from speech by the method tried.** A
harmonicity test misclassified 4 of 5 pure-speech control samples from our
own clip as non-speech, so no conclusion was drawn from it.

What survives: three `impact` cues on measured vocal peaks, which George
accepted. Everything else — the opening ding, whooshes on cuts, the closing
boom — had no reference behind it and was removed.

`engine/sfx.py` and `assets/sfx/` remain as a working synthesised palette
with a clean rights basis. The library is sound; the PLACEMENT needs a
reference nobody can currently see.

## 11b. Original measurements, kept for the record

**The inventory had no sound section and that was the biggest hole in it.**
Measured by spectral-flux onset detection on the reference audio:

| | transients | rate | bands (spectral centroid) |
|---|---|---|---|
| **R3 Pause** | 31 in 27.7s | **1.12/s** | bright **5.0–6.4 kHz**, mid **1.9–2.8 kHz** |
| **R4 PlatChat** | 46 in 47.0s | 0.98/s | mid 1.5–3.8 kHz, some low <600 Hz |

R3 carries roughly **one audio hit per second**. That density is most of why
it reads as produced next to a bare edit, and it is invisible if you only look
at the picture. R4's hits land within **0.1–0.3s of a picture cut**.

Visual cut rate at a frame-diff threshold of 18: R4 **56/min**, R3 **48/min** —
both far above the 6/min of R1 and the 0 of R2.

**`engine/sfx.py` synthesises the palette** rather than sourcing it, so the
rights basis is `synthesised` and travels in `assets/sfx/manifest.json`.
Measured centroids against the reference bands: `ding` 5984 Hz and `sparkle`
7080 Hz (bright), `impact` 1921 Hz (mid), `boom` 824 Hz (low), plus `whoosh`
and `riser` for movement.

Tuning note: a noise component will hijack the centroid. `impact` first
measured 6168 Hz because its crack was lowpassed at 2600 and mixed at 0.8 —
a bright tick, not an impact. Cutoff 1100 at level 0.30 put it at 1921 Hz.

**Cues carry a motivation and `Cue` refuses one without it**, exactly like a
visual effect.

## 12. The opening *(George's note)*

"Start the video with a ding and FNS coming into frame." A clip cut to start
on speech has nowhere for an entrance to live, so prepend a short hold:
`tpad=start_duration=0.6:start_mode=clone` clones the first frame, a zoompan
scales it in from 1.18, and the ding rings over it. Speech then begins exactly
where it did. Everything downstream shifts by the lead-in — overlay windows,
cue times, and the audio via `adelay`.

Measured: the ding sits **+6.3 dB over speech**, which reads as a hit without
ducking the first words.

---

## What I can and cannot do yet

**Can, today, headless:** cuts, the two-pane split, L1/L3 layouts with HUD
re-composite, word captions with emphasis, speed ramps, punch-ins, overlays,
two-pass loudness, FCPXML export. All in `engine/`, all tested.

**Cannot yet:** multicam speaker cutting (no speaker diarisation — I can't tell
who is talking), full-frame evidence replacement (no asset library, no way to
source the right graphic), tilted card overlays (no compositing path), meme
cutouts, persistent banners.

**The honest gap:** of the ten skills above, the engine does six. The four it
cannot do are the four that make R4 look expensive — and three of them need
*assets*, not code. Sourcing the right tweet screenshot at the right second is
an editorial problem, not a rendering one.

---

## 13. Camera movement — measured on R1, 2026-10-31

**R1 and R2 are now in `reference/`.** Keep them there; every earlier sound
and motion claim was extrapolated from an advert and a podcast because these
two were missing.

**R1 moves on roughly 40% of its shots, by 2-10%, eased in at the head of the
shot.** Measured by matching each shot's first frame against one 1.5s later
across a scale sweep: **8 of 18 facecam shots** and **6 of 15 content shots**
move; the rest are static. R2 is a single shot and does not move.

It is not continuous drift and it is **not** punch-and-settle. A push eases
in over roughly 1.5-2s and holds for the rest of the shot.

**A warning about measuring this.** Integrating a per-frame Fourier-Mellin
scale estimate drifted the cumulative zoom to **12x over 80s** with 3.5
direction reversals per second — pure noise accumulation, and it produced a
confident, wrong answer ("R1 moves constantly"). Match two frames seconds
apart instead: nothing accumulates. The per-frame method also claimed R1's
facecam moved 1.5%/frame, which the robust method shows is mostly noise.

`juice.shot_push_expr` implements it. Verified on our render: pushes measured
1.050 / 1.000 / 1.065 against 1.055 / 0 / 1.060 intended.

## 14. Audio tone — our clips do not sound like the references, and it is not SFX

Average spectrum, normalised at 300-1000 Hz so loudness is not the variable:

| band | R1/R2 | ours before | ours after EQ |
|---|---|---|---|
| 2-4 kHz (presence) | — | **−4.0 dB** | −1.6 dB |
| 6-8 kHz | — | +4.2 dB | +0.6 dB |
| 8-11 kHz | — | **+10.7 dB** | +4.3 dB |

Our source is **thin where articulation lives and hot where Twitch's AAC
leaves artifacts.** That tonal mismatch is why a reference sounds produced
and a raw cut sounds raw — it is not the absence of sound effects. Fix:
`equalizer=f=3000:w=1.1:g=4` and `equalizer=f=9500:w=1.0:g=-7`.

**Measurement trap:** the first comparison said we were 21 dB DULL at
7-14 kHz. That was an artifact of comparing a 16 kHz extraction of our audio
against 48 kHz references — our file had no content above 8 kHz by
construction. **Always extract every file at the same sample rate** before
comparing spectra.


## Skill 15 — The magnified exhibit (R1, 0:08)

**This one IS observed.** R1 composites a real Leetify stats page over the
footage at 0:08: flat dark navy panel, square corners, no shadow, no accent
rule, the page's own light wide sans, label above value, emphasis values in
orange. It is a screenshot, not a designed graphic.

The lesson that cost three rejected designs: **when you need data on screen,
show the document — do not redraw it.** A drawn card has to survive a taste
judgement; a screenshot does not, and it cannot be mis-transcribed.

| | |
|---|---|
| Source | a crop of the SOURCE frame at full resolution |
| Magnification | ~2x (the strip is only 11px tall in a 1080p frame) |
| Plate | flat dark, square corners, no shadow, 1px accent rule along the top |
| Kicker | the page name, small grey caps, letter-spaced |
| Emphasis | accent rule under the figures being pointed at |
| Entrance | 16px settle over 0.16s under a 0.10s alpha fade |
| Hold | 3.4s |
| Sound | `sfx.thunk` at `cue_gain(..., -30.0, 6.2)` |

**Crop a contiguous run.** Stitching non-adjacent figures together fabricates
an adjacency the source does not have.

Related: R2's persistent banner is a CLAIM in the speaker's voice ("IT'S
EITHER PRX OR G2"), never a description of the video. A banner that names the
subject instead of asserting something reads as metadata and should be cut.


## Skills 16-18 — found by a per-second sweep of R1, NOT YET BUILT

A contact-sheet sweep at 1fps turned up three techniques the earlier
once-over missed. Recorded here so they are not re-derived.

**16. Hand-drawn marker annotation (R1, 0:31).** A red/orange marker circle
drawn over the gameplay, caught mid-stroke. This is the "reference" overlay
in its purest form: it points at the thing being discussed. Closest thing we
have is `titles.panel(boxes=...)`, which draws a clean rectangle — a marker
stroke would read far less like a UI and more like someone making a case.

**17. Mid-clip section title (R1, 0:31).** "150K POV:" — ALL CAPS, white
fill, heavy stroke, no panel, appearing 31 seconds in. Titles are not just a
hook at the head; R1 re-titles as the argument moves.

**18. Black dip between exhibits (R1, 1:11).** The content pane goes to full
black for about a second between two exhibits. It separates one piece of
evidence from the next and is the only "transition" observed anywhere in the
references — note it is a DIP, not a wipe or a whoosh.

Density note: R1's lower pane changes roughly once per 1-2s in its busiest
stretches. Clip 8's source is pixel-static for 61 of 67s, so matching that
means moving around inside one document rather than cutting between many.
