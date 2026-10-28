# Building the reference style in DaVinci Resolve

Every value here is derived from the two reference clips (see
`STYLE-BASELINE.md`). **None of it has been tested in Resolve** — Resolve isn't
installed on this machine, so treat the transform numbers as computed, not
verified. The first clip you build is the one that proves or corrects them.

---

## 1. Project

**File > Project Settings**

| | |
|---|---|
| Timeline resolution | **1080 × 1920** |
| Timeline frame rate | **60 fps** (R1 was 60; R2's 30 was Instagram's re-encode) |
| Playback frame rate | 60 |
| Input scaling | **Scale full frame with crop** |

That last one matters: it decides what "zoom 1.0" means for a 1920×1080 source
in a vertical timeline, and every number below assumes it.

## 2. Track layout

```
V4   hook title / section labels      (Text+)
V3   captions                         (Text+)
V2   facecam                          top band
V1   evidence / gameplay              bottom band
A1   source audio
A2   music bed (usually empty)
```

Facecam on V2 runs continuously and never cuts. Everything that changes happens
on V1 underneath. That's the structural trick in both references — one stable
anchor, one changing exhibit.

## 3. The split

Seam at **y = 803** of 1920 (0.418). Measured 0.418 in R1 and 0.4422 in R2;
George's clip-autopilot independently used 0.44. Use **0.42**.

```
 y 0     ┌──────────────────────────┐
         │  FACECAM      803 px     │   V2
 y 803   ├──────────────────────────┤ ← captions ride here in R1
         │  EVIDENCE    1117 px     │   V1
 y 1920  └──────────────────────────┘
```

### Facecam (V2) — Inspector > Transform
A 1920×1080 source fit to 1080 width displays at 1080 × 607.5.

- **Zoom: 1.322** → height becomes 803 px, width overflows to 1428 and crops at
  the canvas edge. That crop is what tightens the shot onto the face.
- **Position Y: +558** → centres the 803 px band in the top of the frame
  (canvas centre 960 − band centre 401.5).
- **Position X:** nudge so the face sits centre. R1's subject sits slightly
  right of frame; R2's sits right of centre with the room visible.

Add **Crop > Bottom** if the stream's own overlays intrude.

### Evidence pane (V1)
- **Zoom: 1.0**, **Position Y: −147** → places the 607.5 px tall image directly
  under the seam.
- The ~509 px below it: either let the content fill it (R2's bracket does), or
  add a blurred copy of the same clip on a track beneath with **Blur > 30** and
  scale 1.06. R1 uses the blurred fill.

## 4. Text

One typeface for all three tiers. Heavy condensed grotesque — Anton, Archivo
Black, or Montserrat ExtraBold. R2 used a heavy italic.

### Tier 1 — hook title (V4)
| | |
|---|---|
| Lines | 2, ALL CAPS |
| Size | cap height ≈ **140 px** (~7.3% of frame height) |
| Colour | white, **one keyword per line** in yellow or red |
| Stroke | black, **8 px** |
| Position | bottom of the facecam pane, straddling the seam |
| Timing | **in at 0.00, hold to 1.5s, 0.5s dissolve out, gone by 2.0s** |

Colour the accent word by splitting it into its own Text+ rather than inline
markup — Resolve has no per-character colour in Text+.

### Tier 2 — captions (V3)
| | |
|---|---|
| Words per card | **1–3** |
| Size | cap height ≈ **100 px** (~5.2%) |
| Stroke | black, **6 px** |
| Position | **no fixed value** — R1 at y 0.44, R2 at y 0.747 |
| Cadence | ~2 cards/second (speech ran 119 and 256 wpm) |
| Emphasis | one coloured word per card, maximum |

Put the caption **where the content isn't**. On the seam if the lower pane is
busy edge-to-edge; low in the pane if there's a dead gap (R2 drops into the
space between bracket columns so it never covers a team name).

Build one styled Text+, then duplicate it down the timeline. Don't restyle per
card.

### Tier 3 — section labels (V4)
`INSTANT REPLAY`, `150K POV:` — marks an act change. Larger than a caption,
shorter-lived than the hook. R1 used red and white.

### Annotation
R1 draws a **red rectangle around the accused player's scoreboard row**. In
Fusion: Rectangle node, no fill, 6–8 px red border, keyframed if the scoreboard
scrolls. It's the clearest single signal in the whole clip and it costs nothing.

## 5. Pacing

- **Cut when the point changes.** R1 cut once per 8.9s, a median 0.36s from a
  sentence boundary. R2 never cut.
- **Leave the silence in.** R1 held seven stretches of 3.2–9.1s with nobody
  speaking while the evidence played. Half the clip. Removing it kills the format.
- Speed ramps only to cover a removal on continuous gameplay. Retime curve:
  ease in and out over 8 frames.
- One slow-mo per clip, 0.35×, on the payoff, max 0.5s of source.

## 6. Audio (Fairlight)

```
source dialogue ─┬─ compressor ─┬─ bus ─ limiter (−1.0 dBTP) ─ out
game audio ──────┘   duck 7 dB  │
                     120ms atk  │
                     400ms rel  │
music (rare) ───────────────────┘  −22 LUFS
```

- Normalise the mix to **−12 LUFS integrated**.
- **Limiter at −1.0 dBTP, non-negotiable.** R1 ships at +1.25 dBTP — it clips.
  That's the one thing in the references not to copy.
- Game audio keeps running under the silent evidence stretches. The silence is
  editorial, not acoustic: R1 has only 0.39s below −40 dB in 80 seconds.
- No music bed by default. Neither reference has one.

## 7. Delivery

| | |
|---|---|
| Format | MP4, H.264 |
| Resolution | 1080 × 1920 |
| Frame rate | 60 |
| Quality | Restrict to **~6,000 kb/s** (R1 shipped 5.36 Mb/s) |
| Audio | AAC, 192 kb/s, 48 kHz |

## 8. Bringing an edit in from the engine

`engine/fcpxml.py` emits an FCPXML timeline from an `edit.json` with
frame-exact rational times. **File > Import > Timeline**, pick the file.

This works in Resolve **Free** — no scripting API, no MCP, no Studio licence.
It gives you cut points and retimes already placed; you add the look on top.

Studio is only needed for Claude to *drive* Resolve — grading, Fusion titles,
the render queue — via `engine/resolve_driver.py`. Run
`python -m engine.resolve_driver doctor` to see what's missing.

---

## First-build checklist

Work through this once and correct the numbers above where they're wrong.

- [ ] Facecam fills `y 0–803` with the face centred
- [ ] Evidence pane sits flush under the seam, no gap, no overlap
- [ ] Hook title gone by 2.0s
- [ ] Captions land inside `y 150–1600` and cover nothing that matters
- [ ] Cuts fall on sentence boundaries, not mid-phrase
- [ ] The silent evidence stretches survived the edit
- [ ] Limiter shows no overs; integrated reads ≈ −12 LUFS
- [ ] Export plays correctly at phone size, captions readable
