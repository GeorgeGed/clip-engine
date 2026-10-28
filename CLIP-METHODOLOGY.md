# VALORANT Clip Methodology v0.1

The editorial and technical contract for the clipping agency. Written to be read by
Claude at edit time, not just by humans. Numbers are frame-accurate at 60fps source.

Status: **proposal**. Section 12 lists the decisions that are yours, not mine.

---

## 1. What this is built on

From the VALORANT Work chat (@PolymarketVAL desk), the things that carry over:

- **"Three lines or it is not a card."** Committed 2026-10-12 as `MIN_LINES`. A claim
  needs setup, claim and consequence. This rule is the single most important thing you
  have already learned, and it transfers directly to video.
- **Full context beats punchy.** You pushed back twice (Oct 3, Oct 11) on quotes being
  shortened. Short-form convention says cut to the punch; your own editorial standard says
  don't. Your standard wins — see §4.
- **Every channel with a VOD, not pick-and-choose.** Coverage is a quality property.
- **Speaker and host are separate fields.** A watch-party host is not the speaker. Hold
  uncertain attribution rather than guess.
- **The gate architecture.** `crosses_into_live_comms`, `crosses_a_speaker_boundary`,
  `swallowed_question_note` — reject cheaply and early, surface the reason on the card.
  This is the pattern for clips too (§10).
- **The approval deck.** Cards with warnings, approve/reject, nothing ships unreviewed.
- **Subject-photo resolution.** `hermes_images` already answers "who is this quote about"
  and finds a usable photo. That is a cutaway asset the video editor should consume (§4).

Already on disk, and this spec builds on it rather than replacing it:

- `~/clip-autopilot` — working ffmpeg pipeline. Per-streamer facecam coordinates already
  tuned for sliggy, gofns, tarik, marved6, shanks_ttv, subroza. Twitch Helix clip fetch,
  SQLite dedupe, pre-captioned OCR detection, `permission` field per streamer.
- `~/short-form-clip-studio` — the editorial brief. `style/BRIEF.md` ends with an
  "Approval record to fill after examples". This document fills it.

What the VALORANT Work chat does **not** contain: any clip editing methodology, and zero
mentions of DaVinci Resolve. That gap is what this document closes.

---

## 2. Two genres, two grammars

Conflating these is the most common failure in automated clipping, and it is the reason
most AI clip tools produce output that looks machine-made.

| | **Frag clip** | **Take clip** |
|---|---|---|
| Value lives in | tension → release | the claim |
| Retention driver | stakes | curiosity |
| Cut density | very low | high |
| Captions | speech only, if it matters | always |
| Music | none by default | optional bed |
| Duration | 12–35s | 18–45s |
| Hook text | off | on |
| Fails when | you cut the setup | you cut the context |

Everything below is split along this line. A clip that is both (FNS fragging *and*
talking) follows take-clip rules for cuts and frag-clip rules for framing.

---

## 3. Frag clip grammar

### 3.1 Find the in-point by walking backwards

The standard mistake is a fixed offset — 15 seconds before the kill. That imports dead
air and buries the hook. Instead, anchor on the **last** event and walk backwards to the
first irreversible commitment:

| Moment type | In-point rule |
|---|---|
| Ace | first kill of the streak, minus 1.5s approach |
| 1vX clutch | the frame the player becomes last alive |
| Multikill (2–4k) | first kill of the streak, minus 1.0s |
| Flick / one-tap | 1.2s before the shot — enough to see the crosshair off target |
| Clutch defuse | the frame the defuse starts, minus the last kill that enabled it |
| Retake | the frame the first player enters site |

The out-point is the payoff plus a tail of **36–90 frames (0.6–1.5s)**. Cut on the
release. Never let the round-end screen, the "Victory" banner, or the buy phase play.

### 3.2 The hook: first 24 frames

Frame 1 must contain motion or stakes. No logo, no black, no slow build, no "wait for it".

Two devices, pick one:

1. **Cold open on peak tension.** Start at the highest-stakes second available — the 1v3
   with the spike down and 8 seconds left. Works when the round state is legible from the HUD.
2. **Flash-forward.** 0.5s of the payoff, hard cut to black for 2 frames, then the clip
   from its real in-point. The single highest-retention device in gameplay shorts and
   badly under-used. Use it when the setup is longer than ~8s and would otherwise sag.

Do not use both in one clip.

### 3.3 Cuts: fewer than you think

First-person gameplay is spatially continuous. A hard cut breaks the viewer's mental model
of the space and costs more retention than the dead air it removed. Rules:

- **Maximum one cut per 4 seconds** during the runway.
- Cut **only** to remove dead time: rotating, walking, reloading in cover, waiting out a
  timer. Never cut during a fight.
- Every removed segment is covered by a **speed ramp or a punch-in**, not a bare hard cut.
- Dead time runs at **1.6–2.2x**, with an **8-frame ramp** in and out.
- Action runs at **1.0x**. Always.
- **One slow-mo per clip, maximum.** 0.35x, at most 30 frames of source (0.5s → 1.43s
  out), on the payoff only. A second slow-mo destroys the value of the first.
- Cut on the **audio**, not the video: the cleanest edit point is the ~100ms of silence
  after a gunshot tail.

### 3.4 Pacing budget (24s clip, 1440 frames)

```
frames 0–24        hook — motion in frame 1
frames 24–900      runway — tension accumulates, 0–2 cuts total
frames 900–1350    payoff — 1.0x, or one 0.35x ramp on the final shot
frames 1350–1440   tail — 1.5s, then hard out
```

---

## 4. Take clip grammar

### 4.1 In-point includes the setup

Start at the first word of the claim's **setup**, not the claim. A claim without setup is
unintelligible, and this is exactly the failure your quote desk already rejects. Carry
`MIN_LINES` into video: **if the clip cannot hold setup, claim and consequence, it is not
a clip.**

### 4.2 Cuts are expected here

Unlike frag clips, jump cuts are the native grammar:

- Remove ums, false starts, and any inter-word gap **> 350ms (21 frames)**.
- Cut only on **word boundaries** from the Whisper word-level timestamps. A cut inside a
  word is an automatic reject (§10).
- Every jump cut needs a cover. In order of preference:
  1. **Punch-in alternation** — alternate segments at 1.0x and 1.06x scale. Invisible,
     free, and reads as a two-camera edit.
  2. **Subject cutaway** — the photo of the player or team being discussed, pulled from
     `hermes_images`. 1.2–2.0s, slow 1.0→1.04 push. This is the thing that will make your
     clips look produced rather than cropped, and you already have the subsystem that
     resolves it.
  3. **Evidence insert** — the scoreboard, the bracket, the market odds. Only when the
     claim is about a verifiable number.

No stock footage. No decorative B-roll. Your own brief already says this.

### 4.3 Duration

18–45s. Below 15s there is no room for a real claim. Above 50s retention collapses unless
the claim is genuinely news, in which case let it run — a real story beats the curve.

---

## 5. Framing: the part everyone gets wrong

VALORANT's HUD lives at the **edges** of a 16:9 frame:

```
top-left      minimap
top-centre    round timer, spike timer
top-right     killfeed  ← the event record
bottom-left   HP, shield, abilities, ult points
bottom-centre ammo
```

A naive centre crop to 9:16 destroys all of it. Three layouts, chosen by content:

### L1 — Blurred pillar (`fit_blur`)
Full 16:9 intact, centred, blurred copy filling above and below. **Default for anything
where the killfeed or minimap carries meaning, and for all observed/broadcast footage.**
Already your `clip-autopilot` default. Cost: the action is small on a phone.

### L2 — Split: facecam top / gameplay bottom
`split_ratio: 0.44` as configured. Use when the **face is the payoff** — a reaction, a
rant, a watch-party take. You already have per-streamer cam coordinates, and the pinned
coords for tarik and subroza (who both look down, defeating face detection) are the right
call. Keep the fallback: no face detected → L1, never a wrong crop.

### L3 — Crop-to-fill with HUD re-composite
Crop 9:16, anchored horizontally on centre — where VALORANT's crosshair always is, so a
centre crop is genuinely correct for the aim point.

A 9:16 window out of 16:9 uses the **full height** and crops **horizontally only**: from
1920×1080 you keep a 607px-wide column. So the killfeed is lost to the *side*, not off the
top, and a vertical bias does nothing unless you also punch in past 1.0x. (An earlier draft
of this document said to bias the crop upward to save the killfeed. That was wrong, and
`engine/render_ffmpeg.py` implements the correct behaviour: `anchor_y` is ignored unless
`punch > 1.0`.)

Which is exactly why the differentiator is needed: **re-composite the lost HUD**. Take the
top-right killfeed strip and the spike timer from the source frame and overlay them inside
the vertical safe area at 0.85 scale. L3 without a re-composite throws the event record
away, and the gate warns about it.

This is fully scriptable, nobody in the auto-clipping space does it, and it gives you
L3's immersive scale without L1's loss of event legibility. Use it for aim and mechanics
clips.

### Safe areas (1080×1920)
- Top exclusion: **150px** (platform chrome)
- Bottom exclusion: **320px** (caption rail, CTA, profile row on TikTok and Reels)
- Live band: **y = 150 to y = 1600**

Nothing load-bearing outside that band.

---

## 6. Captions

- **Phrase-level, 3–5 words per card.** Not word-by-word.

  Your `clip-autopilot` currently has `words_per_line: 1` — the MrBeast flashing style.
  I would change this for take clips. Word-by-word is good for hype and terrible for
  comprehension of a long sentence, and your whole editorial position is that the claim
  needs its full context. One word at a time actively fights `MIN_LINES`. Keep word-by-word
  for frag clips if you want the energy; use phrase-level wherever the claim is the value.

- Maximum **two lines**. Restrained keyword emphasis — one emphasised word per card, maximum.
- Position: **0.62–0.68** of height for L1 and L3. Your current 0.55 is tuned to sit just
  below the L2 split seam, which is right for L2 and too high elsewhere.
- Never cover the mouth. Never cover the killfeed.
- **Frag clips: caption speech only when it matters.** Comms callouts ("he's one, he's
  one") are gold — caption them. Ambient chatter steals attention from the action; leave
  it uncaptioned.
- **Pre-captioned sources: do not double-caption.** You already detect this by OCR with
  `action: skip_captions`. Keep it.
- Correct transcription spelling without rewriting what was said. Preserve handle casing,
  acronyms, map names. **Leviatán, not Leviathan.**

---

## 7. Audio: the most under-used lever

- Integrated loudness **−14 LUFS**, true peak **−1 dBTP**. Platform-normalisation parity.
- **Duck game audio under speech by 7 dB**, attack 120ms, release 400ms. Automated,
  always on. This single step is the difference between "a clip" and "an edit".
- The payoff needs a **transient**. If the source headshot ding is weak, layer one — from
  a licensed pack only.
- **No music on frag clips by default.** The gunfire is the rhythm, and a bed fights it.
  Music belongs on montages and on take clips, under −22 LUFS.
- Keep the master unsanitised. Profanity stays in a reviewed master; make platform-safe
  variants on request rather than silently cleaning.

---

## 8. Selection: what to clip at all

Detect cheap, understand expensive. Four tiers, each feeding the next:

### Tier 0 — Crowd signal (free, highest precision)
Twitch Helix top clips. The community already did the selection. Your config:
`clips_per_streamer: 3`, `min_views: 50`, `lookback_hours: 24`. Cheapest and most
reliable; also the least differentiated, because everyone can do it.

### Tier 1 — Audio and transcript (cheap)
Whisper on the VOD with word timestamps. Finds every take clip. Also finds reactions:
a spike in **vocal RMS plus pitch** is a near-perfect streamer-highlight detector, and
it costs nothing once you have the audio. **Chat velocity** is the other near-free
signal — Twitch chat message rate spikes hard on highlights.

### Tier 2 — HUD computer vision (cheap per frame)
Killfeed OCR for kill events, grouped by round to flag multikills and aces. Field numbers
from the open-source work in this space, which set realistic expectations:

- OCR reads the killfeed in only **13–16% of sampled frames**
- ~**94%** row accuracy *when the row is located*
- The classic bug: **kills and deaths counted together**, so two kills and a death read
  as a triple

So the implementation rules are:
- Sample at **4–6 fps**, not every frame
- **Track candidates across frames** and dedupe with fuzzy matching; never treat each
  OCR hit as a new event
- **Require the local player's highlighted border.** VALORANT draws a highlight border on
  your own killfeed rows and your assist portraits. Gate on it and the kill/death
  confusion disappears
- Template-match before OCR — it is an order of magnitude cheaper

### Tier 3 — VLM pass (expensive, narrow)
A vision model **only** on the 20–40s window a lower tier already flagged. Never on a
whole VOD. Its job is the thing CV cannot do: is this actually good, what is the story,
where does the tension peak, what is the hook.

### Ranking
```
score = rarity        (ace > 4k > 3k > 2k > single)
      + stakes        (clutch? spike down? match point? economy?)
      + reaction      (vocal energy + chat velocity)
      + claim_strength (take clips only — your existing substance gates)
      − redundancy    (penalise near-duplicates of what you already shipped)
```

---

## 9. Architecture: Opus decides, a renderer executes

Here I want to push back on the stated plan, then give you what I think is better.

### The problem with "Opus drives Resolve"

- **Resolve is not installed on this machine.** Nothing is blocked yet, but nothing is
  ready either.
- **Python scripting is Studio-only.** Resolve 21.1 moved the Python API behind the paid
  edition — Blackmagic's release notes say the API was being used to hack Studio features
  into Free. External control of Resolve was always Studio-only. Studio is a one-time
  $295, which is fine.
- **It does not parallelise.** The scripting API drives a GUI application, one project at
  a time, on one machine. For an agency rendering dozens of clips a day across clients,
  the editor becomes the bottleneck and the single point of failure.
- Community Resolve MCP servers exist and are capable (one exposes 440+ tools, another
  59 timeline-editing tools), but their feature lists are self-reported and they all sit
  on top of that same Studio API.

### The design I would build instead

**Opus writes an Edit Decision List. A deterministic renderer executes it. Resolve is one
of two backends.**

```
VOD ──▶ detect (T0–T3) ──▶ candidates ──▶ OPUS 5.5 ──▶ edit.json ──▶ gates ──▶ render
                                                          │                      ├─▶ ffmpeg   (volume)
                                                          │                      └─▶ FCPXML   (hero/client)
                                                          └──▶ approval deck ────────▶ Resolve
```

`edit.json` carries in/out points, layout choice, speed ramps with ramp lengths, caption
cards with word-level timings, overlay positions, duck envelopes, and the rights basis.
That is a **decision**, and decisions are what Opus is genuinely good at. Pixel-pushing is
not.

**Backend A — ffmpeg, for volume.** Already proven in `clip-autopilot`. Headless,
parallel, free, fast, no GUI, no licence.

**Backend B — Resolve, for hero and client deliverables.** And the important part: you
can build the timeline **without the scripting API at all**, by emitting **FCPXML** (or
OTIO) from the same `edit.json` and importing it. Resolve imports FCPXML natively, in the
Free edition. You then use Resolve for what it is actually best at — Fusion titles, colour,
Fairlight — and for handing a human editor a timeline they can take over.

So the Resolve MCP becomes useful but not load-bearing: triggering renders, applying
grades, driving Fusion. Buy Studio when you want those automated, not to construct
timelines.

### Why the EDL contract is the right call

- The edit is **reviewable before a frame renders** — you can approve 30 clips in two
  minutes by reading in/out points and caption text
- **Reproducible and diffable.** Re-render the whole back catalogue when the brand template
  changes
- **Backend-portable.** ffmpeg today, Resolve for hero clips, whatever comes next
- It is **the same shape as your quote desk**: candidates → gates → deck with warnings →
  approve/reject → ship. You already know this pattern works and you already trust it

---

## 10. Gates (reject before a human looks)

Mirroring the quote-desk rails. Each one surfaces its reason on the card.

**Hard reject**
- Duration outside **[8s, 60s]**
- Cut lands **mid-word** against the word-level transcript
- Captions intersect the safe-area exclusions or the killfeed
- **No speech and no detected event** — nothing happened
- Black frame, loading screen or menu in the first 0.5s
- `permission` is not `explicit` or `affiliate`
- Take clip below **three lines** of setup/claim/consequence
- Claim spliced from **non-contiguous** speech — never create a statement by joining
  unrelated sentences

**Hold for review**
- Speaker attribution uncertain, or more than one voice in the window
- Slur, allegation, or private information detected
- Face identified only by appearance
- Integrated loudness outside **−16…−12 LUFS** (fix, then re-check)

**Auto-fallback**
- L2 selected but no face found → **L1**
- Source already captioned → **skip our captions**
- Facecam crop below the size floor (UI faces are ~1% of frame, a real webcam is several %)
  → **L1**

---

## 11. Rights, because this is the actual business risk

Your own `clip-autopilot` README already takes the right position, and agency work raises
the stakes. Reposting a permitted streamer's clip to your own channel is one posture.
**Selling edits of third-party footage to clients is a materially riskier one.**

The clean agency model: **the client owns or licenses the footage.** Teams, orgs and
tournament organisers with their own VODs. That is a better business anyway — they have
footage, budget, and a reason to need volume.

Keep the `permission` field on every source, keep the proof, and keep per-client job
directories with no shared footage, templates or accounts.

---

## 12. Decisions that are yours

1. **Word-by-word or phrase-level captions** for take clips. I recommend phrase-level
   (§6) and it contradicts your current `words_per_line: 1`.
2. **Buy Resolve Studio now, or start on ffmpeg + FCPXML?** I recommend the latter, and
   buying Studio when automated grading or Fusion titles become the bottleneck.
3. **Own-channel reposting or client-footage agency**, or both as separate workstreams
   with separate rights postures (§11).
4. **Hook text on frag clips** — I say off, your config says off, confirming it is locked.
5. **The first real VOD.** The brief in `~/short-form-clip-studio/style/BRIEF.md` has been
   waiting on "reference clips and the first VOD" since September. Nothing below the
   methodology level can be settled without one.
6. **Reference clips.** Three or four Valorant clips whose look you want. Typography,
   caption treatment and grade get locked against real examples, not described in prose.
