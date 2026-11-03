"""WHEN the chat belongs on screen — measured off the chat itself.

George, locking clip 8's logic in and asking for it to generalise: *"if it's
a gameplay video, you know, we can change it. So after the streamer has like
got a 3K or 3 kills, then we can see the Twitch chat's reaction. You see what
I mean? So it's like we have to pick the right moments for when the Twitch
chat is on the screen."*

**The frag does not have to be detected.** A 3K produces a burst of chat, and
the burst is the signal — denser, shorter, more repetitive, more emote-and-
caps than the queue of questions that runs the rest of the time. Reading the
chat is far cheaper than reading the game (one GQL call covers ~75s against
transcribing or vision-scanning the footage), it needs no per-game detector,
and it generalises to anything a crowd reacts to: a frag, a fail, a reveal,
a guest, a donation. Detecting the kill would tell us a kill happened;
measuring the burst tells us the crowd CARED, which is the thing the overlay
is for.

TWO MODES, and a clip is one or the other:

* **continuous** — the chat is a steady background with no burst in it.
  Clip 8 is this: 43 messages/min, flat, a queue of people asking FNS
  questions. There is no moment to pick, so the chat is the lower pane's
  resting state and stays up. This is what shipped as v51.
* **reactive** — the chat spikes. The overlay goes up ON the spikes and is
  away the rest of the time, so its arrival means "look what they said".

**BASELINE FROM OUTSIDE THE CLIP, NEVER FROM INSIDE IT.** A 20-second clip
of an ace is hype end to end; measured against its own mean it is flat and
would be called continuous. The resting rate has to come from a wide
context around the clip — `CONTEXT_PAD` seconds either side — so a window
that is entirely a reaction reads as entirely a reaction.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

# a burst is short; a window wider than this smears it into the baseline
WIN = 6.0
HOP = 0.5
CONTEXT_PAD = 180.0      # the resting rate comes from outside the clip
BURST_MULT = 1.8         # over the resting rate
BURST_MIN = 1.5          # shorter than this is noise, not a reaction
BURST_JOIN = 2.5         # two bursts closer than this are one reaction
LEAD = 0.6               # open the window before the burst crests

# Hype is typed differently from conversation: short, repeated, shouted.
_HYPE = re.compile(r"^(?:[A-Z]{2,}|w+|ez|gg|omg+|lmao+|lul|kekw|pog\w*|"
                   r"hol+y+\w*|no+ way|insane|sheesh|yo+|aw+)[!?.]*$", re.I)


@dataclass
class Burst:
    start: float          # seconds into the VOD
    end: float
    peak_rate: float      # messages/min at the crest
    mult: float           # how many times the resting rate
    hype: float           # share of its messages that are hype-shaped


def _text(m) -> str:
    frags = m.fragments if hasattr(m, "fragments") else m.get("frags", [])
    return "".join((f.text if hasattr(f, "text") else f["text"]) for f in frags)


def _offset(m) -> float:
    return m.offset if hasattr(m, "offset") else m["offset"]


def rate(messages, t0: float, t1: float, *, win: float = WIN, hop: float = HOP):
    """Sliding messages/min across [t0, t1]. Returns (times, rates)."""
    ts = sorted(_offset(m) for m in messages)
    out_t, out_r = [], []
    t = t0
    while t <= t1:
        a, b = t - win / 2, t + win / 2
        n = sum(1 for x in ts if a <= x < b)
        out_t.append(t); out_r.append(n * 60.0 / win)
        t += hop
    return out_t, out_r


def resting_rate(messages, t0: float, t1: float, *, pad: float = CONTEXT_PAD) -> float:
    """The stream's own rate AROUND the clip, excluding the clip itself.

    Falls back to the clip's own median when there is no context fetched,
    which is honest but weaker — a fully-hype clip then reads as flat.
    """
    out = [_offset(m) for m in messages
           if t0 - pad <= _offset(m) < t0 or t1 <= _offset(m) < t1 + pad]
    span = min(pad, t0) + pad
    if len(out) < 8 or span <= 0:
        _t, r = rate(messages, t0, t1)
        return max(float(sorted(r)[len(r) // 2]), 1.0)
    return max(len(out) * 60.0 / span, 1.0)


def hype_share(messages) -> float:
    msgs = list(messages)
    if not msgs:
        return 0.0
    return sum(1 for m in msgs if _HYPE.match(_text(m).strip())) / len(msgs)


def bursts(messages, t0: float, t1: float, *, mult: float = BURST_MULT,
           min_len: float = BURST_MIN, join: float = BURST_JOIN) -> list[Burst]:
    """Stretches where the rate runs `mult` times the resting rate."""
    base = resting_rate(messages, t0, t1)
    ts, rs = rate(messages, t0, t1)
    thr = base * mult
    runs, i = [], 0
    while i < len(ts):
        if rs[i] >= thr:
            j = i
            while j < len(ts) and rs[j] >= thr:
                j += 1
            runs.append((ts[i], ts[j - 1], max(rs[i:j])))
            i = j
        else:
            i += 1
    merged = []
    for a, b, pk in runs:
        if merged and a - merged[-1][1] <= join:
            merged[-1] = (merged[-1][0], b, max(merged[-1][2], pk))
        else:
            merged.append((a, b, pk))
    out = []
    for a, b, pk in merged:
        if b - a < min_len:
            continue
        inside = [m for m in messages if a - WIN / 2 <= _offset(m) <= b + WIN / 2]
        out.append(Burst(round(a, 2), round(b, 2), round(pk, 1),
                         round(pk / base, 2), round(hype_share(inside), 2)))
    return out


def classify(messages, t0: float, t1: float, *, topic=None):
    """'reactive' or 'continuous', with the numbers that decided it."""
    bs = bursts(messages, t0, t1)
    base = resting_rate(messages, t0, t1)
    inside = [m for m in messages if t0 <= _offset(m) < t1]
    own = len(inside) * 60.0 / max(t1 - t0, 1e-6)
    on_topic = (sum(1 for m in inside if topic.search(_text(m))) / len(inside)
                if topic and inside else None)
    covered = sum(b.end - b.start for b in bs)
    mode = "reactive" if bs and covered < 0.75 * (t1 - t0) else "continuous"
    return {
        "mode": mode, "bursts": bs, "resting_rate": round(base, 1),
        "clip_rate": round(own, 1), "messages": len(inside),
        "hype_share": round(hype_share(inside), 2),
        "on_topic": None if on_topic is None else round(on_topic, 2),
        "burst_coverage": round(covered / max(t1 - t0, 1e-6), 2),
    }


# A reaction window has to OPEN BEFORE THE CREST and run past it: the chat
# box takes 0.34s to settle and the viewer needs a beat to start reading, so
# arriving at the peak means arriving late. It also has to be worth an
# entrance — under MIN_WINDOW the box appears and goes, which is the flicker
# the clip-8 work already rejected twice.
MIN_WINDOW = 3.0
TAIL = 1.2


def windows(messages, t0: float, t1: float, *, remap=None, mode: str | None = None,
            out_dur: float | None = None, min_window: float = MIN_WINDOW,
            lead: float = LEAD, tail: float = TAIL):
    """The chat's on-screen windows, in OUTPUT time.

    `remap(src_t) -> out_t | None` maps VOD seconds onto the finished cut,
    because the cut removes dead spans and output seconds are not source
    seconds. Without it the times are returned unmapped, which is only
    correct for an untightened clip.

    **continuous** returns one window covering the clip — the resting state,
    which is what clip 8 ships. **reactive** returns one window per burst.
    """
    info = classify(messages, t0, t1)
    mode = mode or info["mode"]
    span = t1 - t0

    def out(x):
        if remap is None:
            return max(0.0, x - t0)
        return remap(max(0.0, x - t0))

    if mode == "continuous":
        # THE WHOLE OUTPUT, and it must not be derived through `remap`.
        # `remap(0.0)` is None whenever the clip has a non-zero in-point —
        # 0.0 is then before the first keep — so routing the continuous case
        # through the remap silently produced an EMPTY window list, which
        # took the chat off screen entirely and the entrance cue with it.
        # "Continuous" means the whole clip by definition; there is nothing
        # to look up.
        end = out_dur if out_dur is not None else (t1 - t0)
        return mode, [{"from": 0.0, "to": round(end, 2)}], info

    wins = []
    for b in info["bursts"]:
        a_src = max(t0, b.start - lead)
        b_src = min(t1, b.end + tail)
        a, bb = out(a_src), out(b_src)
        if a is None or bb is None or bb - a < min_window:
            continue
        if out_dur is not None:
            bb = min(bb, out_dur)
            if bb - a < min_window:
                continue
        if wins and a - wins[-1]["to"] < min_window:
            wins[-1]["to"] = round(bb, 2)      # too close to be two visits
            continue
        wins.append({"from": round(a, 2), "to": round(bb, 2)})
    return mode, wins, info


# ─────────────────────────────────────────────────────────────────────────
# WHICH MESSAGE HE IS ANSWERING
#
# George: *"ideally we should have something where fns has seen the twitch
# chatter's question and we have an animation of it shown on screen while he
# answers it - then the twitch chat should come in like normal."*
#
# This REFRAMES the finding that clip 8's chat "is not reacting". Measured
# then: 43 messages/min, only 24% on-topic, and reading them they are a Q&A
# queue — "are nrg partnered??", "who would you bring in?". That was recorded
# as the overlay being a poor fit. It is the opposite: a chat that ASKS is
# exactly the material for this card. Reacting chat wants the burst overlay;
# asking chat wants the question card.
#
# **THIS PROPOSES, IT DOES NOT DECIDE.** The card asserts that a specific
# viewer asked something and the streamer answered it — a factual claim about
# two real people, and the only claim about an interaction anything in this
# system makes. Lexical overlap cannot establish one: a streamer and his chat
# discuss the same subject continuously and reuse the same words without
# either responding to the other, so overlap is the NULL hypothesis, not
# evidence. Measured on clip 6, the top-scoring pair by overlap (0.75) was a
# chatter writing "it has everything to do with tech and ping issues" shortly
# before FNS says "ping issues, cheaters" — which is equally well explained
# by both of them reacting to the same thing on screen.
#
# So this returns CANDIDATES with their evidence, and a judged-then-
# adversarially-refuted pass decides. Nothing reaches the screen on a score.
STOP = set(
    "the a an and or but if is are was were be been being to of in on at for with "
    "that this these those it its i you he she we they them his her their my your "
    "do does did will would can could should have has had not no yes so as by from "
    "what when where who why how which u ur im dont like just get got go going gonna "
    "think know really about than then there here all any more most some".split())
# A question word in the FIRST FEW TOKENS, not only at the start. Chat opens
# with a discourse marker constantly, and anchoring to position 0 missed the
# clip's single best candidate: "so how can you say the format is good".
_Q = (r"can|could|would|will|should|do|does|did|is|are|was|were|who|what|when|"
      r"where|why|how|which|any|anyone|someone|whats|whos|hows")
ASK = re.compile(r"\?|^(?:\W*\w+){0,2}\W*\b(?:" + _Q + r")\b", re.I)
LOOKBACK = 75.0          # how far back a message can be and still be the prompt
MIN_CHARS = 8


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']+", s.lower())
            if w not in STOP and len(w) > 2}


def answering(messages, utterances, *, t0: float, lookback: float = LOOKBACK,
              questions_only: bool = True):
    """Candidate (message -> utterance he may be answering) pairs.

    **LEXICAL OVERLAP IS THE WRONG RETRIEVAL SIGNAL, and the adversarial pass
    proved it both ways.** Ranking clip 6's candidates by shared words put
    six pairs up and ALL SIX were refuted as topic co-occurrence — the
    judges found that chat was paraphrasing the streamer, not the other way
    round, so a high overlap is evidence AGAINST a response. Meanwhile the
    one pair that looks genuine has **zero words in common**:

        Perrysuxker_17, +30.2s : "so how can you say the format is good"
        FNS,            +33.84s: "i agree we agree on this i know that the
                                  open qualifier system is going to have its
                                  own issues ... it is still better than
                                  locking players out of franchise forever"

    A question and its answer use DIFFERENT words — that is what makes it an
    answer rather than an echo. So retrieval is now: every message that is a
    QUESTION, within `lookback` of a line, ranked by recency. Overlap is
    still reported, as evidence for the judge to weigh, but it no longer
    selects.

    `utterances` are dicts with `start`/`end` in CLIP-FILE time and `text`;
    `t0` is the clip's VOD offset, so a message's offset can be compared with
    them. Returns one candidate per message, best utterance only, sorted by
    overlap — **for judging, not for shipping.**
    """
    out = []
    for m in messages:
        text = _text(m).strip()
        if len(text) < MIN_CHARS:
            continue
        asking = bool(ASK.search(text))
        if questions_only and not asking:
            continue
        mw = _words(text)
        best = None
        for u in utterances:
            gap = (t0 + u["start"]) - _offset(m)
            # a message sent after he began the line cannot have prompted it
            if not (0 < gap <= lookback):
                continue
            ov = mw & _words(u["text"])
            # RECENCY selects; overlap is only reported as evidence
            if best is None or gap < best["gap_s"]:
                best = {"score": round(len(ov) / max(len(mw), 1), 3),
                        "answer": u["text"].strip(),
                        "answer_t": round(u["start"], 2), "gap_s": round(gap, 1),
                        "overlap": sorted(ov)}
        if best:
            out.append({"author": m["author"] if isinstance(m, dict) else m.author,
                        "msg": text, "msg_t": round(_offset(m) - t0, 2),
                        "is_question": asking, **best})
    out.sort(key=lambda c: c["gap_s"])
    return out


# ─────────────────────────────────────────────────────────────────────────
# IS THE CHAT TALKING ABOUT THE SAME THING HE IS?
#
# **THE ONE-NARRATIVE RULE APPLIES TO EVERY CHANNEL, NOT JUST THE AUDIO.**
# It has only ever been enforced on the transcript. A clip now carries three
# narrative channels — what he SAYS, what is on his SCREEN, and what CHAT is
# saying — and the overlay can put a second story on screen for the whole
# runtime while the audio is clean.
#
# Measured on the delivered clip 6, which had already shipped: of the 52
# chat messages visible in the cut, **4% are about open qualifiers and 29%
# are about an unrelated Sentinels/Oxy roster transfer**. In the first 19
# seconds it is **0 on subject against 11 on the other story** — a viewer
# reads "who is SEN kicking?" and "oxy is out the jail" while he rants about
# qualifier tech problems. The lower pane behind it was a Reddit thread
# headlined "Sentinels Set to Add OXY", the same other story. The audio was
# the only channel telling the clip's narrative.
#
# This file already contained the finding — "a chat overlay is not a
# treatment you apply to a clip, it is a property of the window" — measured
# on clip 8 at 24% on-topic. Nothing gated on it, so clip 6 shipped at 4%.
# Same pattern as the hallucinated captions: a note is not a gate.
#
# The floor is set from the two measured points. Clip 8 at 24% shipped and
# was accepted repeatedly; clip 6 at 4% is wrong. 15% is between them and
# close to the bad one, which is the conservative side to err on.
ON_TOPIC_FLOOR = 0.15
RIVAL_CEILING = 0.20     # a single competing story taking this much is worse


def topicality(messages, subject: str, *, extra_stop=frozenset()):
    """What share of the visible chat is about the clip's own subject.

    Keywords come from the clip's OWN subject line and claim, so this needs
    no per-clip tuning and cannot drift from what the clip is about.
    """
    keys = {w for w in re.findall(r"[a-z]+", subject.lower())
            if w not in STOP and w not in extra_stop and len(w) > 3}
    if not keys:
        return {"on_topic": None, "n": 0, "keys": []}
    stems = {k[:5] for k in keys}
    n = on = 0
    for m in messages:
        t = _text(m).strip()
        if len(t) < 3:
            continue
        n += 1
        words = {w[:5] for w in re.findall(r"[a-z]+", t.lower())}
        if words & stems:
            on += 1
    return {"on_topic": round(on / n, 3) if n else None, "n": n,
            "keys": sorted(keys)}


def chat_is_safe(messages, subject: str, *, floor: float = ON_TOPIC_FLOOR):
    """Should this clip carry a chat overlay at all?"""
    t = topicality(messages, subject)
    if t["on_topic"] is None:
        return False, "no subject keywords", t
    if t["on_topic"] < floor:
        return False, (f"chat is {t['on_topic']:.0%} on-topic, under the "
                       f"{floor:.0%} floor — it would put a second narrative "
                       f"on screen"), t
    return True, f"chat is {t['on_topic']:.0%} on-topic", t
