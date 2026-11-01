"""Render a whole caption track to one alpha movie.

Overlaying 106 cards as 106 ffmpeg inputs is not workable, and Resolve's
Fusion route costs a 300-frame title per 5s window. Drawing every card into
a single alpha clip is simpler than both, and it lets one caption track be
restyled completely by swapping a style dict — which is what the four style
versions of clip 8 need.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from .titles import _font, ACCENT, WHITE

CANVAS = (1080, 1920)


def track(cards, out: Path, *, style: dict, dur: float, canvas=CANVAS, fps=60) -> Path:
    import numpy as np

    w, h = canvas
    n = int(round(dur * fps))
    size = style.get("size", 96)
    font = _font(size)
    y = style.get("y", 0.44)
    kind = style.get("kind", "stroke")
    fill = style.get("fill", WHITE)
    accent = style.get("accent", ACCENT)
    box = style.get("box", (23, 58, 214, 245))
    stroke = style.get("stroke", max(5, size // 14))
    rise = style.get("rise", 0)          # px the card rises as it appears
    ease = style.get("ease", 0.09)       # seconds of that rise

    # index cards by frame so each frame draws at most one
    by_frame = {}
    for c in cards:
        a, b = int(c["start"] * fps), int(c["end"] * fps)
        for f in range(max(0, a), min(n, b)):
            by_frame.setdefault(f, (c, (f - a) / fps))

    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
         "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
         "-c:v", "qtrle", "-pix_fmt", "argb", str(out)],
        stdin=subprocess.PIPE)

    blank = np.zeros((h, w, 4), np.uint8).tobytes()
    for f in range(n):
        hit = by_frame.get(f)
        if hit is None:
            proc.stdin.write(blank)
            continue
        c, age = hit
        img = Image.new("RGBA", canvas, (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        txt = c["text"]
        tw = d.textlength(txt, font=font)
        k = min(1.0, age / ease) if ease else 1.0
        cy = int(y * h) + int(rise * (1 - k))
        col = accent if c.get("emph") else fill
        if kind == "box":
            pad_x, pad_y = int(size * 0.34), int(size * 0.20)
            bw, bh = int(tw) + pad_x * 2, int(size * 1.18) + pad_y
            x0 = (w - bw) // 2
            d.rounded_rectangle([x0, cy, x0 + bw, cy + bh], radius=8, fill=box)
            d.text(((w - tw) / 2, cy + pad_y * 0.4), txt, font=font,
                   fill=(WHITE if not c.get("emph") else accent))
        else:
            d.text(((w - tw) / 2, cy), txt, font=font, fill=col,
                   stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
        a = int(255 * k) if ease else 255
        if a < 255:
            alpha = img.getchannel("A").point(lambda v: v * a // 255)
            img.putalpha(alpha)
        proc.stdin.write(np.asarray(img, dtype=np.uint8).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed writing {out}")
    return out
