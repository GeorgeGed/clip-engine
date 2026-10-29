# Style baseline — what I've learned from the references

Observations, not rules. Confidence grows with each reference. Anything seen in
one clip only is marked **provisional** — it may be that creator's habit rather
than how the format works.

| | **R1** | **R2** |
|---|---|---|
| File | `WE GOT THIS CHEATER BANNED` | `SaveClip.App_AQO5…` |
| Game | CS2 (renyan) | VALORANT (Polymarket bracket) |
| Delivered | 1080×1920, 60fps, 5.4 Mbps | 720×1280, 30fps, 0.55 Mbps |
| Duration | 80.3s | 20.2s |

R2's resolution, frame rate and bitrate are **Instagram's re-encode, not the
editor's choice** — the filename is a SaveClip download. Don't read anything
into them.

---

## 1. The shared skeleton

Both clips, built very differently, sit on the same frame.

### Two panes, facecam on top, seam at ~0.42–0.44

| | seam position |
|---|---|
| R1 | y 803 / 1920 = **0.418** (measured repeatedly, returns to the exact row) |
| R2 | green rule at **0.4422** |

Two unrelated editors landed two percent apart. And your `~/clip-autopilot`
config already says `split_ratio: 0.44`. Three independent sources agree, so
**0.42–0.44 is the real number** and it's the most solid thing I've learned.

R2 makes the seam explicit — a bright green full-width rule. R1 leaves it as a
hard edge. Same geometry, different finish.

### The facecam is the constant, the lower pane is the variable
In both, the talking head runs continuously and never cuts away. Everything
that changes happens underneath. That's what makes the format cheap to produce
and easy to follow: one stable anchor, one changing exhibit.

### Word-level captions
R1: 1–3 words. R2: one word per card. Neither uses sentence-level subtitles.

### A text element that states the topic
R1: a 2-second hook title, then gone. R2: a banner that never leaves.
Both answer "what am I watching" inside the first second.

---

## 2. Where they diverge — these are dials, not settings

Nearly every other parameter is opposite. This is the useful part: it shows
which choices are load-bearing and which are taste.

| | **R1** receipts | **R2** hot take |
|---|---|---|
| Cuts | 8 (6.0/min, mean shot 8.9s) | **0** — one continuous take |
| Speech coverage | **50%** | **96%** |
| Speech rate | 119 wpm | **256 wpm** |
| Silence >1.5s | 7 stretches, 3.2–9.1s | none |
| Integrated loudness | **−11.79 LUFS** | **−14.26 LUFS** |
| True peak | **+1.25 dBTP** (clipping) | −0.44 dBTP |
| Loudness range | **13.70 LU** | **1.30 LU** (flat, heavily limited) |
| Lower pane | changes constantly | **one static graphic** |
| Caption look | white, heavy black stroke | white on a **blue box** |
| Caption y | on the seam, ~0.44 | **0.747**, low in the pane |
| Topic text | hook, 0→1.5s, 0.5s fade | persistent banner, 80% width |

Read that table as two valid answers to different jobs:

**R1 is an argument.** It needs room to breathe, so it cuts slowly, goes quiet
for seconds at a time, and swings 13 LU between a mutter and a shout.

**R2 is a claim.** It needs to land fast, so it never stops talking, never cuts,
and sits flat at 1.3 LU so every word hits identically.

Neither is "better". The job picks the dial.

---

## 3. R1 — the receipts clip

A case argued out loud, alternating assertion and proof.

**Speech is exactly 50% of runtime.** 40.5s talking, 39.8s silent across seven
stretches of 3.2–9.1s. The silence isn't dead air, it's the exhibit: chat logs,
scoreboard, Steam profile, Leetify card, the Match Cancelled banner.

**Never trim the silence out of this format.** An auto-clipper removing "dead
air" destroys it entirely.

**Cuts follow the argument, not a beat.** Median distance from a cut to a
sentence boundary: **0.36s**. Seven of eight land within a second of a thought
starting or ending. No cutting on music, no jump cuts to kill pauses.

Act structure: hook → accusation → **exhibit (9.1s silent)** → escalation →
exhibit → attempt → failure ("no VACLive, no VACLive") → exhibits → despair
("VACLive is sleeping") → turn → **payoff (5.4s silent, Match Cancelled)** →
one-line button.

The despair act is doing the real work. Without it the ban means nothing.

**Text, three tiers:** hook title (two lines, ALL CAPS, ~140px caps, one
coloured keyword per line, 0→1.5s then a 0.5s fade); running captions (1–3
words on the seam, changing ~2×/second, white with yellow/red/orange accents);
section labels (`INSTANT REPLAY`, `150K POV:`) marking act changes.

**Profanity masked in captions (`F***ING`), untouched in audio.** Platform-safe
caption track over an unmodified master.

**A red rectangle is hand-drawn around the accused player's scoreboard row.**
Cheapest and clearest signal in the whole clip.

**At the payoff the evidence stays on screen under the celebration** — proof and
reaction simultaneous, not sequential.

---

## 4. R2 — the hot take

A single claim, delivered fast, with a graphic for context.

**One 20-second take, zero cuts.** Nothing is edited out. Whatever cutting
happened, happened when choosing where to start and stop.

**A narrator intro frames it.** 0.0–3.4s is someone else's voiceover: *"Hanz has
a pretty interesting take on who he thinks will be winning Champions Shanghai."*
Then the subject talks from 3.8s. The clipper supplies context before the quote
rather than letting it start cold.

That maps straight onto your quote-desk rule about speaker and host being
separate fields — here the separation is audible.

**The lower pane is one static graphic** — a Polymarket VCT Champions Shanghai
bracket, with a slow gold light sweep (mean pixel change 1.0–1.4, so it's a
subtle animated background, not a video). It never changes for the whole clip.
It's context, not proof.

**Captions:** one word per card in a blue rounded box, white heavy italic sans,
~20% frame width, at y 0.747 — placed in the dead zone between bracket columns
so it never covers a team name. The topic banner above uses the identical
typeface at 80% width.

**Audio is flat on purpose.** LRA 1.30 means heavy limiting — no dynamics at
all. At 256 wpm with no pauses, that's the right call: every word lands at the
same level and nothing drops below the noise.

---

## 5. What I'd carry into your own clips

Ranked by how much the references support it.

**Confident (both clips plus your existing config):**
- Vertical, two panes, facecam top, **seam at 0.42–0.44**
- Facecam never cuts away; the lower pane carries the change
- Word-level captions, 1–3 words
- Topic established in the first second

**Likely (both clips, different executions):**
- Caption placement avoids whatever matters underneath — R1 rides the seam, R2
  drops to 0.747 to miss the bracket. The principle is the same: **put the
  caption where the content isn't.**
- One typeface, heavy, high contrast, used for every text tier
- Colour used for emphasis, sparingly

**Provisional (one clip only — need more references):**
- 50/50 speech-to-silence for receipts clips *(R1)*
- Cutting on speech boundaries within ~0.4s *(R1)*
- Narrator intro framing a quote *(R2)*
- Blue caption boxes vs stroked text *(R2)* — pure brand choice
- Persistent banner vs fading hook *(both, opposite)*

**A dial, not a default:**
- **Loudness −14.26 to −11.79 LUFS.** Pick by format: flat and quiet for
  continuous talking, loud and dynamic when there are shouts to land. I'd
  target **−13 LUFS** as a house default and move from there.
- **True peak: hold at −1.0 dBTP.** R1 clips at +1.25. That's a defect, not a
  style, and it's the one thing in either reference I wouldn't copy.

---

## 6. What this corrected from my earlier methodology

| I had written | The references show |
|---|---|
| frag 12–35s, take 18–45s | **20s and 80s.** Length follows the content |
| one cut per 4s maximum | 0 cuts and 6 cuts/min — both far slower |
| remove gaps over 350ms | R1 **keeps** 3–9s gaps as its evidence |
| phrase-level captions | **word-level** in both |
| −14 LUFS fixed | a range, −14.26 to −11.79 |
| two genres | at least **three** |

Held up: the ~0.42 split, word-level captions, colour emphasis, a topic
statement in the first second, and caption placement that respects what's
underneath.

---

## 7. R3 — Pause (pausevfx), and what it actually is

`pausevfx.com` / the 28 Oct launch post. **This is not a reference edit — it is
a product advertisement**, and the distinction matters before copying anything
from it.

Pause is an AI video editing product ("1st senior agentic AI content editor",
founders Dev Monga and Fardan Ali). The launch video is captioned "Introducing
ChatGPT 6.1 Terra for Video Editing"; the sign-off card carries a **"Not
affiliated with OpenAI"** disclaimer, so the ChatGPT naming is borrowed brand,
not a partnership.

**Measured:** 27.75s, **1920×1080 landscape**, 30fps, −15.64 LUFS, −1.42 dBTP,
LRA 4.90. Five cuts, but clustered — one 16.2s opening take, then four cuts
inside 1.4s at the end.

**Its own look** is cream-background product marketing: floating rounded video
windows with drop shadows, kinetic marketing copy, orange and green accents, a
Premiere timeline screenshot as proof. Copying that style produces adverts, not
gaming clips. It is not a template for R1/R2-style work.

### What IS worth taking: their technique list

The video and the about page advertise the same checklist, and it's a good one:

| Technique | Clip Engine status |
|---|---|
| Cut dead air and filler | `segments` |
| Reframe the facecam | `layout` L2 + crop |
| Zoom / punch-in on reactions, eased | `segments[].punch` → now animatable |
| Word-level captions | `captions` |
| Music cut to the edit, ducked under VO | `audio.music` + `audio.duck` |
| Frame-timed SFX on the punchline | `audio.sfx` |
| Shakes, flashes, glows on separate tracks | **was missing — now `effects`** |

Two things they do that we didn't express at all: a **visual punctuation layer**
(shake/flash/glow/whip/zoom-punch) and **timed overlays**. Both are now in the
schema.

### The architecture match
Pause delivers an **editable Premiere project, not a flat export** — "every
change stays editable", clips and keyframes as timeline layers. That is
independently the same bet as `edit.json` → FCPXML: hand over a timeline, not a
rendered file. Worth noting that a funded competitor reached the same
conclusion.

### The tension worth naming
**"Cut the dead air" is their headline feature, and it would destroy an R1
receipts clip.** Half of R1's runtime is deliberate silence carrying the
evidence. Pause's defaults are tuned for Roblox/Minecraft/Fortnite reaction
content, where dead air genuinely is dead. For George's material the rule has to
be conditional on genre, not global.

---

## 8. Open questions for the next references

1. Does the 0.42–0.44 seam hold, or do some creators go 50/50?
2. Is the narrator intro common, or just R2?
3. What does a pure gameplay/frag clip look like in this style — neither
   reference is one, and that's the genre your killfeed detection targets.
4. Does anyone use music? **Neither reference has a music bed.** Worth knowing
   whether that's the norm.
