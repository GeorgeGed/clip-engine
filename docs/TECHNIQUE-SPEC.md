# Technique spec — measured parameters

Per-technique numbers pulled off the three references. Where a value was
measured it says so; where a technique is claimed but not demonstrated, it says
that too.

| | R1 | R2 | R3 (Pause) |
|---|---|---|---|
| | CS2 receipts, 80.3s | VALORANT take, 20.2s | product demo, 27.8s |
| Frame | 1080×1920 | 1080×1920 | **1920×1080 landscape** |

R3 is an advert for an AI editing product. Its *wrapper* is marketing design,
but the clip it shows as output is real edited gameplay, and that section is
what's measured below.

---

## 1. Captions

The three references disagree completely, which makes this the clearest
technique to choose deliberately rather than default into.

| | R1 | R2 | **R3 (Pause)** |
|---|---|---|---|
| Centre y | ~0.44 (on the seam) | 0.747 | **0.897** |
| Centre x | 0.5 | 0.5 | **0.500** |
| Glyph height | ~0.052 of frame | ~0.039 | **0.110** |
| Word width | — | 0.197 | **0.111–0.270** |
| Cadence | ~2.0 cards/s | ~2.0 | **3.14 cards/s** |
| Card duration | — | — | **median 167ms, min 100ms, max 700ms** |
| Case | mixed / CAPS accents | sentence | **lowercase, as spoken** |
| Treatment | white + heavy stroke | white on blue box | **white + thick stroke + shadow** |
| Placement logic | avoids content | avoids content | **fixed, covers HUD** |

### What Pause does differently, and the cost
Pause places captions at a **fixed bottom position and accepts covering the
game HUD** — in the sampled frame the word sits directly on top of the
inventory hotbar. R1 and R2 both move their captions to avoid what's
underneath.

For reaction content that's fine; the HUD carries nothing. For a VALORANT clip
where the killfeed *is* the evidence, a fixed bottom placement throws
information away. **Placement should follow the footage, not a constant.**

### Their caption numbers are worth stealing
- **0.110 of frame height is big** — more than double R1's. Phone-legible
  without squinting.
- **median 167ms per card, floor of 100ms (3 frames at 30fps).** That's fast.
  It reads as energy rather than as subtitles.
- **Lowercase, transcribed as spoken** — "now u", not "NOW YOU". Keeps the
  speaker's voice. Fights the instinct to tidy a transcript.

## 2. Cutting

R3's output runs a **long hold then a stinger**: 2.4s of uncut gameplay, then a
burst at the end with cuts **29–140ms apart** — several shorter than two frames
at 30fps.

```
18.93 ──940ms──▶ 19.87 ─59ms─▶ 19.93 ─140ms─▶ 20.07 ─30ms─▶ 20.10
   ─29ms─▶ 20.13 ─70ms─▶ 20.20 ─100ms─▶ 20.30
```

That's a deliberate device: hold long enough to establish, then compress hard
to end on energy. Neither R1 (even 8.9s shots) nor R2 (no cuts) does it.

**Use it for an outro, not a body.** Sub-frame cutting for 30 seconds is noise.

## 3. Zoom / punch-in

**Advertised, not demonstrated.** Pause's demo captions a feature as "knows
where to zoom", but tracking a fixed HUD badge through the output section shows
scale pinned at **1.000 for 2.4 seconds**, then a discontinuity that is a cut,
not a ramp.

So there's no measured zoom parameter to copy. What stands up from their about
page is the *method*: punch-ins on their own adjustment layer, eased, so they
can be moved or removed without touching the cut. That's a construction note,
and it's already how `segments[].punch` / `punch_to` / `punch_ease` work.

## 4. Audio

| | R1 | R2 | R3 |
|---|---|---|---|
| Integrated | −11.79 LUFS | −14.26 | **−15.64** |
| True peak | **+1.25** (clips) | −0.44 | **−1.42** |
| Range | 13.70 LU | 1.30 LU | **4.90 LU** |

R3 is the most conservative of the three and the only one that is unambiguously
correct: comfortably under full scale, moderate range. **−1.42 dBTP is the
model to copy, not R1's +1.25.**

## 5. Effects

Pause advertises shakes, flashes, glows and overlays on separate tracks, timed
to the frame. **None appear in the sampled output** — the energy there comes
entirely from caption cadence and the end burst.

Treat the effects vocabulary as available, not mandatory. Every effect in
`effects[]` needs a `motivation`; flashes are capped at 3/second and intensity
0.8 for photosensitivity.

## 6. Sound design

Claimed: whooshes and hits timed to the frame, including on jokes; music cut to
the edit and faded under the voiceover. Not separable by measurement from a
mixed track, so this stays a claim rather than a number.

Worth noting **none of the three references has an obvious music bed**.

---

## Caption presets

Three measured systems, in `config/style.yaml`. Pick per job.

```yaml
caption_presets:
  seam:            # R1 — rides the facecam/content seam
    position_y: 0.44
    glyph_height: 0.052
    cards_per_sec: 2.0
    case: as_spoken
    treatment: { fill: white, stroke_px: 8, shadow: true }
    placement: content_aware

  boxed:           # R2 — white on a solid box, low in the pane
    position_y: 0.747
    glyph_height: 0.039
    cards_per_sec: 2.0
    case: sentence
    treatment: { fill: white, box: "#2B5CE6", stroke_px: 0 }
    placement: content_aware

  bottom_loud:     # R3 — big, fast, fixed low placement
    position_y: 0.897
    glyph_height: 0.110
    cards_per_sec: 3.14
    card_ms: { min: 100, median: 167, max: 700 }
    case: lowercase_as_spoken
    treatment: { fill: white, stroke_px: 10, shadow: true }
    placement: fixed       # will cover HUD — only for footage where that is free
```

**Default to `seam` or `boxed` for VALORANT**, where the killfeed and minimap
carry meaning. `bottom_loud` is for reaction and tutorial footage where the HUD
is disposable — and it is the most energetic of the three.
