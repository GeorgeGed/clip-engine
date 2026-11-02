#!/usr/bin/env python3
"""Fetch the VOD chat for clip 8's window and map it onto the finished cut.

George, on a reference Short with the streamer's chat running under the
facecam: "i think this is good - i want you to conduct a test - see if
there's a way you could find this part of the stream, then overlay his
stream chat live so you can their reaction."

Two things this has to get right.

**ANCHOR TO SOURCE TIME.** A chat message happened at a VOD second. The
delivered cut removed 15 dead spans, so output seconds are not source
seconds, and a message written during a removed span has no home in the cut
at all. `build_overlays.at()` remaps through the same keeps `build_v7.py`
used, so the chat and the speech stay in sync by construction rather than
by a hand-typed offset. Messages that fall inside a removed span are
DROPPED, not nudged — a reaction that lands on the wrong line is worse than
one that is missing.

**REPORT WHETHER CHAT IS ACTUALLY REACTING.** The point of the overlay is
the reaction. Chat that happens to be asking unrelated questions is noise
with usernames on it, so this prints the relevance of the window before
anything is rendered and leaves the editorial call to a human.

Usage:  ./.venv/bin/python build_chat.py
"""
import colorsys
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from engine import twitch_chat                                  # noqa: E402
import build_overlays                                           # noqa: E402

VOD = "2905408276"
FRAMES_S = 2812 / 60
REGION_START = 5978.8        # clip 8's in_point in the VOD, from ranked.json
REGION_END = 6045.89
CHAT = ROOT / "jobs/fns-2905408276/chat_clip08.json"
OUT = ROOT / "vendor/remotion-clip08/public/chat.json"
WINDOWS = ROOT / "vendor/remotion-clip08/public/chat_windows.json"

# WHEN THE CHAT IS ON SCREEN AT ALL.
#
# George: "it should be inside of a box so you can see the text itself, im
# just saying always keep the bottom screen for what fns is looking at ...
# make sure it has animations coming in and out."
#
# The previous build dimmed the box to 0.32 behind a drawn card. That is the
# defect this project already wrote down for card exits and then repeated
# here: **a dark panel over the board must not go translucent.** At 32% the
# roster rows read straight through it, the text loses its ground, and the
# thing stops being a box at exactly the moment it is supposed to be one.
# Measured on the transition frames, the entering and leaving states were
# both unreadable for the same reason.
#
# So the chat is PRESENT OR ABSENT, never see-through. It lives in the gaps
# between graphics and leaves before each one lands. A gap has to be long
# enough to be worth an entrance: under MIN_GAP the box would appear and go
# inside a second, which is the flicker, not the feature. The cards were
# re-timed to open a gap after each one — see Root.tsx — so this now
# yields nine windows instead of two.
MIN_GAP = 1.5

# THE GAP IS DEAD SPACE, AND SHORTENING IT IS NOT THE SAME LEVER AS SPEEDING
# THE CLIP UP.
#
# George: "the twitch chat needs to come back quicker make sure there's no
# dead space maybe at the end its fine."
#
# He is right about what an OFF gap IS here. The content pane's frame-to-frame
# delta over this cut measures **median 0.0005, max 0.27, zero frames above
# 0.5 across all 2822** — one motionless roster board start to finish. So
# while the chat is away the lower pane is a frozen frame, and 2.5s of that
# three times over is 7.5s of nothing happening.
#
# THE FIX IS LONGER WINDOWS, NOT MORE OF THEM, and that distinction is the
# whole lesson from v47. Cutting OFF alone would have made n go 4 -> 5 and
# added two state changes, which is exactly the "going way too quickly" that
# removing two cards was meant to solve. Raising ON by the same amount holds
# n at 4, so the switching rate is IDENTICAL and only the dead air moves:
#
#            ON    OFF   windows   each    gaps    chat      changes
#   v49      7.0   2.5      4      7.48s   7.5s    29.9s        7
#   v50      9.0   0.9      4      8.68s   2.7s    34.7s        7
#
# 4.8s of frozen pane becomes 4.8s of chat for no extra cut. 0.9s is still a
# beat and not a blink — 54 frames, against a 0.34s entrance — so the board
# keeps the pause it earns without the pane going still.
ON, OFF = 9.0, 0.9   # the chat's own cycle inside a long free stretch
LEAD, TAIL = 0.10, 0.08      # the chat is on V3 BELOW the cards, so a few
                             # frames of overlap are covered, not collided

# THE CHATTER'S OWN COLOUR, MADE READABLE THE WAY TWITCH MAKES IT READABLE.
#
# George: "the normal colours of the twitch chatters." Those colours are the
# record and they stay in `colour` untouched. But raw hex is not what a viewer
# sees: Twitch ships **"Readable Colors" ON by default**, which lifts a dark
# user colour against the dark chat column, so #0000FF already reaches the
# viewer's screen lifted. Rendering the raw value would be LESS faithful to
# what the chatter looks like on Twitch, not more.
#
# Measured against Twitch's own #18181B, 17 of the window's 41 names (41%)
# sit under the 4.5:1 body floor and four of them are unreadable: #0000FF at
# 2.06:1, #000000 at 1.19:1, #B22222 at 2.65:1, #8A2BE2 at 2.97:1.
#
# The lift holds HUE AND SATURATION and raises lightness to the floor by
# bisection — the identical move `theme.tsx` makes for `blueLight`, so there
# is one rule in the project for this and not two. Most moves are invisible
# (#FF0000 -> #FF1010, #2E8B57 -> #30915B); the four that matter become
# #6E6EFF, #808080, #DD4F4F and #A55DE9.
PANEL_BG = (0x18, 0x18, 0x1B)
CONTRAST_FLOOR = 4.5


def _rel_l(rgb):
    def ch(v):
        v /= 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(float(v)) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _ratio(a, b):
    la, lb = _rel_l(a), _rel_l(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def readable(hex_colour, bg=PANEL_BG, floor=CONTRAST_FLOOR):
    """`hex_colour` with its lightness raised until it clears `floor` on `bg`."""
    s = hex_colour.lstrip("#")
    rgb = [int(s[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    if _ratio([v * 255 for v in rgb], bg) >= floor:
        return hex_colour.upper()
    h, l, sat = colorsys.rgb_to_hls(*rgb)
    if sat < 0.02:
        sat = 0.0                      # a grey has no hue to preserve
    lo, hi = l, 1.0
    for _ in range(40):
        mid = (lo + hi) / 2
        out = [v * 255 for v in colorsys.hls_to_rgb(h, mid, sat)]
        if _ratio(out, bg) < floor:
            lo = mid
        else:
            hi = mid
    out = [v * 255 for v in colorsys.hls_to_rgb(h, hi, sat)]
    return "#%02X%02X%02X" % tuple(int(round(v)) for v in out)


# The words the clip is actually about, for the relevance read.
TOPIC = re.compile(
    r"\b(job|jobs|security|contract|contracts|sign|signed|signing|org|orgs|"
    r"partner|partnered|partnership|team|teams|roster|salary|paid|pay|"
    r"replace|replaced|cut|dropped|free agen|tier ?2|t2|scene)\b", re.I)


def main():
    if CHAT.exists():
        raw = json.loads(CHAT.read_text())
        print(f"  {len(raw)} messages from cache")
    else:
        msgs = twitch_chat.fetch(VOD, REGION_START, REGION_END)
        twitch_chat.to_json(msgs, CHAT)
        raw = json.loads(CHAT.read_text())
        print(f"  fetched {len(raw)}")

    # The cut starts 8.85s into the region. Messages from just before that
    # get NEGATIVE times so the card opens already half full — a chat panel
    # that starts empty and fills up reads as a graphic booting, not as a
    # stream you joined.
    IN_POINT = build_overlays.IN_POINT
    kept, dropped, pre = [], 0, 0
    for m in raw:
        region_t = m["offset"] - REGION_START
        if region_t < IN_POINT:
            out_t = region_t - IN_POINT        # negative: already on screen
            pre += 1
        else:
            out_t = build_overlays.at(region_t, fallback=-9999.0)
            if out_t < -1000:
                dropped += 1      # written during a span the cut removed
                continue
        kept.append({
            "t": round(out_t, 2),
            "author": m["author"],
            "colour": m["colour"],              # the raw value: the record
            "display": readable(m["colour"]),   # what Twitch itself would draw
            "badges": m["badges"][:2],
            "frags": [{"text": f["text"], "emote": f["emote"]} for f in m["fragments"]],
        })
    kept.sort(key=lambda m: m["t"])
    lifted = [m for m in kept if m["display"] != m["colour"].upper()]

    text = " ".join("".join(f["text"] for f in m["frags"]) for m in kept)
    on_topic = [m for m in kept
                if TOPIC.search("".join(f["text"] for f in m["frags"]))]

    OUT.write_text(json.dumps(kept, indent=1))

    # The windows, read off resolve_lean's own EXHIBITS so the two cannot
    # drift apart.
    #
    # WITH ONLY TWO CARDS LEFT the free stretches are enormous — 37.6s before
    # the first story — and one unbroken 37-second window is not "let it come
    # in and out", it is just leaving it on. So a long stretch is CYCLED:
    # ON seconds of chat, OFF seconds of bare board, repeating. The board is
    # what he is looking at, so the gaps are not empty, they are the pane
    # doing its own job for a moment.
    import resolve_lean
    cards = sorted((at, at + dur) for _n, at, dur in resolve_lean.EXHIBITS)
    free, prev = [], 0.0
    for a, b in cards:
        if a - prev >= MIN_GAP:
            free.append((prev + TAIL, a - LEAD))
        prev = max(prev, b)
    if FRAMES_S - prev >= MIN_GAP:
        free.append((prev + TAIL, FRAMES_S))

    edges = []
    for a, b in free:
        span = b - a
        if span <= ON + OFF:                 # short enough to hold in one go
            edges.append({"from": round(a, 2), "to": round(b, 2)})
            continue
        # share the leftover out across the cycles so the last one is not a stub
        n = max(1, int(round((span + OFF) / (ON + OFF))))
        each = (span - OFF * (n - 1)) / n
        t0 = a
        for _ in range(n):
            edges.append({"from": round(t0, 2), "to": round(t0 + each, 2)})
            t0 += each + OFF
    WINDOWS.write_text(json.dumps(edges, indent=1))
    on = sum(w["to"] - w["from"] for w in edges)
    print(f"  {len(edges)} chat windows, {on:.1f}s of {FRAMES_S:.1f}s "
          f"({100 * on / FRAMES_S:.0f}%), cycling {ON}s on / {OFF}s off")
    prev_to = None
    dead, lost = 0.0, 0
    for w in edges:
        if prev_to is not None and w["from"] > prev_to:
            g = w["from"] - prev_to
            dead += g
            lost += sum(1 for m in kept if prev_to <= m["t"] < w["from"])
            print(f"          gap {g:.2f}s")
        print(f"    {w['from']:5.2f}-{w['to']:5.2f}  ({w['to']-w['from']:.2f}s)")
        prev_to = w["to"]
    # What a gap COSTS, both ways: a frozen lower pane, and the messages
    # written during it that nobody sees.
    print(f"  dead space between windows: {dead:.2f}s, "
          f"{lost} messages written while the box was away")
    print(f"  {len(lifted)} of {len(kept)} names lifted for readability on "
          f"{'#%02X%02X%02X' % PANEL_BG}")
    vis = [m for m in kept if m["t"] >= 0]
    span = vis[-1]["t"] - vis[0]["t"] if vis else 0
    print(f"  {len(kept)} mapped onto the cut ({pre} of them pre-roll, already "
          f"on screen at frame 0), {dropped} dropped into removed spans")
    print(f"  {len(vis) / max(span, 1) * 60:.0f} messages/min over {span:.1f}s "
          f"(the reference runs ~75/min)")
    print(f"  ON TOPIC: {len(on_topic)} of {len(kept)} "
          f"({100 * len(on_topic) / max(len(kept), 1):.0f}%) mention the clip's subject")
    print(f"  -> {OUT}")
    if on_topic:
        print("\n  the ones that are reacting:")
        for m in on_topic[:10]:
            t = "".join(f["text"] for f in m["frags"])
            print(f"    {m['t']:5.1f}s  {m['author'][:16]:16s} {t[:58]}")


if __name__ == "__main__":
    main()
