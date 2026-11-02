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
LEAD, TAIL = 0.10, 0.08      # the chat is on V3 BELOW the cards, so a few
                             # frames of overlap are covered, not collided

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
            "colour": m["colour"],
            "badges": m["badges"][:2],
            "frags": [{"text": f["text"], "emote": f["emote"]} for f in m["fragments"]],
        })
    kept.sort(key=lambda m: m["t"])

    text = " ".join("".join(f["text"] for f in m["frags"]) for m in kept)
    on_topic = [m for m in kept
                if TOPIC.search("".join(f["text"] for f in m["frags"]))]

    OUT.write_text(json.dumps(kept, indent=1))

    # the windows, read off resolve_lean's own EXHIBITS so the two cannot
    # drift apart the way a hand-typed copy would
    import resolve_lean
    cards = sorted((at, at + dur) for _n, at, dur in resolve_lean.EXHIBITS)
    edges, prev = [], 0.0
    for a, b in cards:
        if a - prev >= MIN_GAP:
            edges.append({"from": round(prev + TAIL, 2), "to": round(a - LEAD, 2)})
        prev = max(prev, b)
    if FRAMES_S - prev >= MIN_GAP:
        edges.append({"from": round(prev + TAIL, 2), "to": round(FRAMES_S, 2)})
    WINDOWS.write_text(json.dumps(edges, indent=1))
    on = sum(w["to"] - w["from"] for w in edges)
    print(f"  {len(edges)} chat windows, {on:.1f}s of {FRAMES_S:.1f}s "
          f"({100 * on / FRAMES_S:.0f}%) — gaps under {MIN_GAP}s are skipped")
    for w in edges:
        print(f"    {w['from']:5.2f}-{w['to']:5.2f}  ({w['to']-w['from']:.2f}s)")
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
