"""VOD chat replay — the messages, their colours, badges and emotes.

**This reverses a finding recorded here on 2026-10-29.** That note said VOD
chat replay "is NOT reachable legitimately", on the evidence that
`chat-downloader` (v0.2.8, abandoned) fails with `PersistedQueryNotFound`.
That is true of that package and says nothing about the endpoint: it
hardcodes a persisted-query hash that Twitch has since rotated. With the
current hash the same query returns everything — text, `contentOffsetSeconds`,
`userColor`, `userBadges` and emote fragments. Verified on VOD 2905408276.

The lesson is the one this file keeps relearning: **a dead client is not a
dead capability.** The earlier conclusion generalised from one abandoned
dependency to the whole interface.

WHAT THIS IS. `VideoCommentsByOffsetOrCursor` is the query Twitch's own web
player issues when you open a VOD with chat replay on, called with the
public web client-id the site itself ships. It is the public replay feature,
read the way the page reads it — not a private or authenticated surface.
It is also, separately, the standard way every chat-overlay tool in this
space works. Rights posture is unchanged and unexamined by this module:
`permission` still has to be set on the source like any other footage, and
a viewer's chat message is their words appearing on screen, which is worth
a thought before it ships to a wide audience.

Helix genuinely does omit chat; that part of the old note stands. So does
everything about live IRC (`engine/chat_monitor.py`) and the crowd signal
(`engine/detect_crowd.py`), which solve different problems.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path

GQL = "https://gql.twitch.tv/gql"
# Twitch's own public web client-id, as the site sends it.
WEB_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"
# The persisted hash for VideoCommentsByOffsetOrCursor. ROTATES. When this
# starts returning PersistedQueryNotFound, read a fresh one out of the
# network tab on a VOD page rather than concluding the feature is gone.
QUERY_HASH = "b70a3591ff0f4e0313d126c6a1502d79a1c02baebb288227c582044aa76adf6a"

EMOTE_CDN = "https://static-cdn.jtvnw.net/emoticons/v2/{id}/default/dark/2.0"


@dataclass
class Fragment:
    text: str
    emote: str | None = None          # CDN url, or None for plain text


@dataclass
class Message:
    offset: float                     # seconds into the VOD
    author: str
    colour: str                       # "#RRGGBB"; Twitch's default-grey when unset
    badges: list[str] = field(default_factory=list)
    fragments: list[Fragment] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "".join(f.text for f in self.fragments)


# Twitch assigns one of these to a chatter who never picked a colour. Reading
# them back is better than rendering a grey wall: in the reference clip the
# username colours are most of what makes the chat look like chat.
DEFAULT_COLOURS = [
    "#FF0000", "#0000FF", "#00FF00", "#B22222", "#FF7F50", "#9ACD32",
    "#FF4500", "#2E8B57", "#DAA520", "#D2691E", "#5F9EA0", "#1E90FF",
    "#FF69B4", "#8A2BE2", "#00FF7F",
]


UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
_DEVICE = uuid.uuid4().hex[:32]


def _post(body: list) -> list:
    req = urllib.request.Request(
        GQL, data=json.dumps(body).encode(),
        headers={"Client-ID": WEB_CLIENT_ID, "Content-Type": "application/json",
                 "User-Agent": UA, "Device-ID": _DEVICE,
                 "Origin": "https://www.twitch.tv", "Referer": "https://www.twitch.tv/"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def _page(video_id: str, offset: float):
    """One page, addressed BY OFFSET.

    **Do not follow the `cursor`.** Cursor paging is what Twitch's bot
    detection watches: the first offset call succeeds and the cursor
    follow-up returns `IntegrityCheckFailed`, which looks exactly like a
    rotated hash and is not. Offset calls are what the player itself makes
    when a viewer scrubs, and they work indefinitely. Each returns ~59
    comments spanning roughly -17s to +57s around the offset asked for, so
    stepping by 40s covers a window with overlap to spare.
    """
    body = [{"operationName": "VideoCommentsByOffsetOrCursor",
             "variables": {"videoID": str(video_id),
                           "contentOffsetSeconds": int(offset)},
             "extensions": {"persistedQuery": {"version": 1,
                                               "sha256Hash": QUERY_HASH}}}]
    for attempt in range(4):
        try:
            d = _post(body)
            break
        except urllib.error.HTTPError:
            if attempt == 3:
                raise
            time.sleep(1.5 * (attempt + 1))
    errs = d[0].get("errors")
    if errs:
        raise RuntimeError(
            f"GQL: {errs}. If this is PersistedQueryNotFound the hash has "
            f"rotated — read a fresh one off a VOD page. If it is "
            f"IntegrityCheckFailed, something is paging by cursor.")
    return d[0]["data"]["video"]["comments"]


STEP = 40.0


def fetch(video_id: str, start: float, end: float, *, pause: float = 0.6) -> list[Message]:
    """Every chat message between `start` and `end` seconds into the VOD."""
    out: dict[str, Message] = {}
    off = max(0.0, start - 10)
    while off < end + STEP:
        for e in _page(video_id, off)["edges"]:
            n = e["node"]
            t = float(n["contentOffsetSeconds"])
            if not (start <= t <= end) or n["id"] in out:
                continue
            c = n["commenter"] or {}
            m = n["message"]
            name = c.get("displayName") or c.get("login") or "?"
            out[n["id"]] = Message(
                offset=t, author=name,
                colour=m.get("userColor")
                       or DEFAULT_COLOURS[sum(name.encode()) % len(DEFAULT_COLOURS)],
                badges=[b["setID"] for b in (m.get("userBadges") or []) if b.get("setID")],
                fragments=[Fragment(text=f.get("text") or "",
                                    emote=EMOTE_CDN.format(id=f["emote"]["emoteID"])
                                          if f.get("emote") else None)
                           for f in m["fragments"]])
        off += STEP
        time.sleep(pause)
    return sorted(out.values(), key=lambda m: m.offset)


def to_json(messages: list[Message], out: Path) -> Path:
    out.write_text(json.dumps([asdict(m) for m in messages], indent=1))
    return out


if __name__ == "__main__":
    import sys
    vid, a, b = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
    msgs = fetch(vid, a, b)
    print(f"{len(msgs)} messages over {b - a:.0f}s "
          f"({len(msgs) / max(b - a, 1) * 60:.0f}/min)")
    if len(sys.argv) > 4:
        print("->", to_json(msgs, Path(sys.argv[4])))
