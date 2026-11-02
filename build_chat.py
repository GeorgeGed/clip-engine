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
FADES = ROOT / "vendor/remotion-clip08/public/chat_fades.json"

# How present the chat stays while each graphic is up.
#
# George: "when the pictures of jingg and jonah come up the chat should fade
# out - so the chat can come in and out you know?"
#
# Taken literally and applied to every card, the chat would be absent for 39
# of the clip's 47 seconds — the graphics cover almost all of it, so a blanket
# rule makes the chat a flicker rather than a presence. So it is graded by
# what the graphic IS:
#
#   0.00  the three cards carrying photographs or a whole document. A face
#         on screen takes the eye completely and nothing should compete.
#   0.32  the drawn exhibits and figure cards: the chat survives as
#         movement behind them, which is what keeps the pane alive. 0.15
#         was tried first and is invisible — with ten cards covering 76%
#         of the clip the chat then exists for 0.35 of 47 seconds.
#   0.70  the side chip, 1.8s and anchored off the frame edge. It displaces
#         nothing.
#
# It also blurs as it dims (in Chat.tsx). Dimming alone leaves it legible,
# and legible text behind a graphic is still competing for the eye.
LEVEL = {
    "rm_Tweet": 0.0, "rm_StoryPrx": 0.0, "rm_StorySen": 0.0,
    "rm_ExKru": 0.32, "rm_ExNrg": 0.32, "rm_Grid": 0.32,
    "rm_StatCard": 0.32, "rm_Pair": 0.32, "rm_Ratio": 0.32,
    "rm_ChipAmer": 0.70,
}

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

    # the schedule, read off resolve_lean's own EXHIBITS so the two cannot
    # drift apart the way a hand-typed copy would
    import resolve_lean
    fades = [{"from": at, "to": round(at + dur, 2),
              "level": LEVEL.get(name, 0.18)}
             for name, at, dur in resolve_lean.EXHIBITS]
    FADES.write_text(json.dumps(fades, indent=1))
    covered = sum(f["to"] - f["from"] for f in fades if f["level"] < 0.3)
    print(f"  {len(fades)} fade windows; the chat is displaced or dimmed for "
          f"{covered:.1f}s of {FRAMES_S:.1f}s ({100 * covered / FRAMES_S:.0f}%)")
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
