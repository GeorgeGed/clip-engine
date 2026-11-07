"""Is the chat panel actually ON SCREEN in the finished file?

Clip 07 shipped with no chat while every log line said it had worked:
`91 messages on the cut`, `1717 frames -> rm_Chat.mov`, `appended 4 of 4:
V3:1`. A 13 MB overlay rendered, resolved by path and reached the timeline
with an EMPTY window list, so not one frame of it was ever visible. Nothing
downstream could tell that from chat being deliberately off.

This measures the artifact, which is the only thing that settles it.

TWO SIGNALS, BECAUSE EITHER ALONE IS WRONG:

* **Dark fill.** The panel is Twitch's own `#18181B`, reading modal (8,8,11)
  after a limited-range encode, and it COVERS the lower pane. With it gone
  the VCT roster board shows through, which is bright and busy — clip 07
  without chat measured 18.9% dark against 83% with it.
* **Coloured usernames on that fill.** Dark alone is not enough: a clip
  whose lower pane is a dark page would look identical. The chatters' own
  colours are saturated and sit on near-black, which no dark document does.

The first version of this probe counted ONLY coloured pixels and reported
backwards — the clip with no chat scored highest, because the board it
failed to cover is full of team colours and flags. Calibrating against a
known-good and a known-bad is what caught it, and is why both are in the
test rather than one.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

# From vendor/remotion-clip08/src/Chat.tsx — read, not guessed.
BOX = (64, 1090, 580, 420)
DARK_MIN = 0.50          # clip 07 without chat: 0.19; with it: 0.83
COLOUR_MIN = 400         # saturated pixels per frame inside the panel


def _frame(mp4: Path, at: float, box=BOX) -> bytes:
    x, y, w, h = box
    return subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{at:.2f}", "-i", str(mp4),
         "-frames:v", "1", "-vf", f"crop={w}:{h}:{x}:{y},format=rgb24",
         "-f", "rawvideo", "-"], capture_output=True).stdout


def measure(mp4, at: float, box=BOX) -> tuple[float, int]:
    """(share of near-black pixels, count of saturated ones) in the panel."""
    raw = _frame(Path(mp4), at, box)
    if not raw:
        return 0.0, 0
    dark = colour = tot = 0
    for i in range(0, len(raw) - 2, 3):
        r, g, b = raw[i], raw[i + 1], raw[i + 2]
        mx, mn = max(r, g, b), min(r, g, b)
        tot += 1
        if mx < 46 and mx - mn < 16:
            dark += 1
        elif mx > 90 and mx - mn > 60:
            colour += 1
    return dark / max(tot, 1), colour


def visible(mp4, dur: float, *, samples=(0.15, 0.35, 0.55, 0.75, 0.9)):
    """(is it on screen, a line saying why)."""
    darks, cols = [], []
    for f in samples:
        d, c = measure(mp4, dur * f)
        darks.append(d)
        cols.append(c)
    if not darks:
        return False, "could not read any frame"
    dk = sum(darks) / len(darks)
    cl = sum(cols) / len(cols)
    ok = dk >= DARK_MIN and cl >= COLOUR_MIN
    return ok, (f"panel fill {dk:.0%} of the box (want >={DARK_MIN:.0%}), "
                f"{cl:.0f} coloured px/frame (want >={COLOUR_MIN})")
