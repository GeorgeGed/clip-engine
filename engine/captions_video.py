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


def kinetic(cards, out: Path, *, dur: float, size=78, y=0.44, canvas=CANVAS, fps=60,
            settle=0.085, lift=12, grow=0.055, accent=ACCENT, tilt_emph=1.4):
    """The C style, damped.

    George: "number three probably has the best subtitle style, if it was a
    little bit smaller and less bouncy." So: 78px instead of 104-136, the
    scale travel cut from 0.24 to 0.055, the lift from 26px to 12, the tilt
    from 4.5 degrees to 1.4, and a critically-damped ease instead of a
    spring that overshoots. It still arrives; it no longer bounces.
    """
    import math

    import numpy as np
    from PIL import Image, ImageDraw

    w, h = canvas
    n = int(round(dur * fps))
    font = _font(size)
    big = _font(int(size * 1.16))

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
        # critically damped: fast in, no overshoot
        k = 1.0 - math.exp(-age / max(1e-4, settle * 0.38))
        k = min(1.0, k)
        fnt = big if c.get("emph") else font
        col = accent if c.get("emph") else (255, 255, 255, 255)

        layer = Image.new("RGBA", canvas, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        tw = d.textlength(c["text"], font=fnt)
        cy = int(y * h) + int(lift * (1 - k))
        d.text(((w - tw) / 2, cy), c["text"], font=fnt, fill=col,
               stroke_width=max(4, int(size * 0.085)), stroke_fill=(0, 0, 0, 255))

        s = 1.0 - grow * (1 - k)
        if c.get("emph"):
            layer = layer.rotate(tilt_emph * k, resample=Image.BICUBIC, center=(w // 2, cy))
        if s < 0.999:
            nw, nh = int(w * s), int(h * s)
            layer = layer.resize((nw, nh), Image.LANCZOS)
            pad = Image.new("RGBA", canvas, (0, 0, 0, 0))
            pad.paste(layer, ((w - nw) // 2, (h - nh) // 2), layer)
            layer = pad
        if k < 0.999:
            layer.putalpha(layer.getchannel("A").point(lambda v: int(v * k)))
        proc.stdin.write(np.asarray(layer, dtype=np.uint8).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed writing {out}")
    return out
