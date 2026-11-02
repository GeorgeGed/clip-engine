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
            min_window: float = MIN_WINDOW, lead: float = LEAD, tail: float = TAIL):
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
        a = out(t0)
        b = out(t1 - 0.05)
        return mode, ([{"from": round(a, 2), "to": round(b, 2)}]
                      if a is not None and b is not None else []), info

    wins = []
    for b in info["bursts"]:
        a_src = max(t0, b.start - lead)
        b_src = min(t1, b.end + tail)
        a, bb = out(a_src), out(b_src)
        if a is None or bb is None or bb - a < min_window:
            continue
        if wins and a - wins[-1]["to"] < min_window:
            wins[-1]["to"] = round(bb, 2)      # too close to be two visits
            continue
        wins.append({"from": round(a, 2), "to": round(bb, 2)})
    return mode, wins, info
