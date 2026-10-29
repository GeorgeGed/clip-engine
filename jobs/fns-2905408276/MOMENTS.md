# FNS — VOD 2905408276, clip candidates

Source: `twitch.tv/videos/2905408276` — "EG FNS | Next stream: Probably WORLDS
WATCHPARTY", 1h43m. His own stream, not a watchparty, so attribution is clean.

Method: Tier 1 only. Audio pulled (103 min), 427 reaction spikes detected by
vocal RMS + spectral centroid, clustered to one per 75s, top 12 windows
transcribed. **No video was downloaded**, so nothing here is based on kills or
anything on screen.

---

## Clip these

### 1. 0:51:36 — he reveals he's coaching in the open qualifiers
> "…because I'm gonna be coaching in the open qualifiers, I have to prepare for
> that, which means I don't think I could watch Worlds."

**This is the news clip of the stream.** A retired pro announcing he's coaching
is a roster story. The line before it — someone asking whether mods can get
"juice" on who he's coaching, and him saying he'll tell the mods but they have
to keep it quiet — is the hook: a withheld reveal.
Genre: **take**. Suggested range **0:51:05 – 0:51:50**.

### 2. 1:35:22 — the cultural-influence claim *(highest reaction spike in the stream, 1.000)*
> "…basically the new Sinatra… it just sets these trends… people just copy it
> because they worship him. He's the overlord of the young gen, at least in NA Val."

Big claim about a named figure, and it peaked the reaction detector across the
whole 103 minutes. Controversial in the useful way — it's an opinion people will
argue with rather than an insult.
Genre: **take**. Suggested range **1:34:55 – 1:35:40**.
⚠ The name is garbled in transcription. Verify before it ships.

### 3. 1:21:46 — the dig at a named player, then the walk-back
> "I can't have cloudy. I already know what cloudy is capable of in the
> competitive environment… I'm kidding, cloudy's a good player."

Strong because of the retraction, not despite it. **Clip must include the walk-back** —
cutting at "I don't think I can have cloudy" turns a joke into a headline, and
that's exactly the context-stripping the quote desk rejects.
Genre: **take**. Suggested range **1:21:20 – 1:22:00**.

### 4. 1:08:07 — teamless players, names Demon1
> "…forgot Demon1. I actually said Demon1 very early on, about five minutes ago,
> when we were discussing teamless players."

Offseason roster speculation naming a marquee free agent. Reliable VALORANT
engagement.
Genre: **take**. Suggested range **1:07:40 – 1:08:20**.

### 5. 0:35:34 — "the worst tournament of all time"
> "…the worst tournament of all time, watching right now the longest final in
> VALORANT history. Why am I watching this? It's 57 minutes long."

Controversial, specific, and checkable. Also carries a chat beat —
"you guys are trolling me, I almost got bamboozled."
Genre: **take**. Suggested range **0:35:08 – 0:35:48**.

### 6. 0:12:08 — recency bias on 100 Thieves
> "This is recency bias… 100 Thieves was a middle-of-the-pack team every year
> except this year."

A real argument with setup, claim and consequence intact. He also pre-empts the
obvious objection by saying he doesn't know Riot's partner payments and won't
speak out of turn — worth keeping, it's what makes the take credible.
Genre: **take**. Suggested range **0:11:42 – 0:12:25**.

### 7. 1:30:41 — chat asks about yay returning
> "Do you know if yay will ever come back to pro Val?" / "I don't think so…
> anyone can have a change of heart."

A clean chat-question-and-answer about a named pro — the "conversations with
chat" category, and the easiest format to repeat weekly.
Genre: **take**. Suggested range **1:30:15 – 1:30:55**.

---

## Considered and passed

| Time | Why not |
|---|---|
| 0:15:04 | Explainer on why orgs invest long-term. True, not clippable. |
| 0:24:16 | Franchising talk, mentions babybay rumours, but mid-thought with no clean in-point. |
| 0:48:27 | Scheduling logistics for streaming Worlds. |
| 1:02:49 | Reinforces the coaching story but #1 says it better. |
| 1:41:43 | "Would you rather" chat question. Mild. |

---

## Before any of these ship

- **Every name needs checking against `roster.json`.** Whisper garbled several
  here, which is the `not in roster` rail doing its job.
- **Speaker attribution.** Parts of this stream are a conversation; confirm FNS
  is the speaker and not a guest before putting it under his byline
  (`crosses_a_speaker_turn`).
- **Word-boundary trim.** The ranges above are approximate. Exact in/out needs
  the word-level pass so no cut lands mid-word.
- **Three lines.** Each pick was chosen to carry setup, claim and consequence.
  Trimming them shorter breaks `MIN_LINES`.

## What this pass could not see

- **Kills / multikills / aces.** Needs video and killfeed detection.
- **Chat velocity.** The single strongest free signal for "something happened",
  and the only one of your four criteria not covered here.
