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


# C's look came from IMPACT, not the repo's Tungsten stack — that is why the
# "smaller, less bouncy" rebuild did not read as the style George liked. Same
# typeface, same tight tracking, same heavy stroke; only the scale and the
# spring change.
IMPACT = "/System/Library/Fonts/Supplemental/Impact.ttf"
BALOO = Path(__file__).resolve().parent.parent / "fonts" / "Baloo2[wght].ttf"
TIKTOK_SANS = (Path(__file__).resolve().parent.parent / "fonts"
               / "TikTokSans[opsz,slnt,wdth,wght].ttf")
EMOJI_SWIFT = Path(__file__).resolve().parent / "emoji_png.swift"
TITLE_SIZE, TITLE_MAX_W, TITLE_MIN_SIZE = 80, 880, 64


def _title_font(size: int):
    from PIL import ImageFont
    fnt = ImageFont.truetype(str(TIKTOK_SANS), size)
    fnt.set_variation_by_name(b"SemiBold")
    return fnt


def title_fits(text: str) -> bool:
    """True when the opening title sits on one line at full size."""
    return _title_font(TITLE_SIZE).getlength(text) <= TITLE_MAX_W


NOTO_EMOJI = ("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
              "/usr/share/fonts/noto/NotoColorEmoji.ttf")


def _emoji_png(emoji: str):
    """One emoji as an RGBA image, cropped to its ink.

    On a Mac, AppKit draws it through `emoji_png.swift` — Apple's glyph, the
    one an iPhone shows, which PIL cannot draw on this build. Elsewhere (the
    Linux render workers) PIL draws Noto Color Emoji, a CBDT bitmap font that
    only exists at 109px; the caller scales it like the Apple one.
    """
    import shutil
    import sys
    import tempfile
    from PIL import Image, ImageFont
    if sys.platform == "darwin" and shutil.which("swift"):
        png = Path(tempfile.mkdtemp()) / "emoji.png"
        subprocess.run(["swift", str(EMOJI_SWIFT), emoji, str(png), "160"],
                       check=True, capture_output=True)
        big = Image.open(png).convert("RGBA")
    else:
        import os
        font = next((p for p in (os.environ.get("CLIP_EMOJI_FONT"), *NOTO_EMOJI)
                     if p and Path(p).exists()), None)
        if not font:
            raise FileNotFoundError("no colour emoji font: install fonts-noto-color-emoji "
                                    "or set CLIP_EMOJI_FONT")
        f = ImageFont.truetype(font, 109)
        big = Image.new("RGBA", (220, 220), (0, 0, 0, 0))
        from PIL import ImageDraw
        ImageDraw.Draw(big).text((20, 20), emoji, font=f, embedded_color=True)
        big = big.resize((int(big.width * 160 / 109), int(big.height * 160 / 109)),
                         Image.LANCZOS)
    box = big.getbbox()
    return big.crop(box) if box else None


def _title_image(text: str, *, emoji: str | None = None, keyword: str | None = None,
                 size=TITLE_SIZE, max_w=TITLE_MAX_W, stroke_frac=0.05,
                 key_fill=(222, 255, 157, 255)):
    """The opening title in TikTok's own text style: TikTok Sans SemiBold,
    white with a thin black outline, no box, the emoji alone on the line
    underneath. Wraps to as many lines as `max_w` needs. `keyword`, one
    word of the title, is drawn in `key_fill` (the captions' lime)."""
    from PIL import Image, ImageDraw
    fnt = _title_font(size)
    while fnt.getlength(text) > max_w and size > TITLE_MIN_SIZE:
        size -= 2
        fnt = _title_font(size)
    sw = max(2, int(size * stroke_frac))
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if cur and fnt.getlength(trial) > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    lines.append(cur)
    asc, desc = fnt.getmetrics()
    lh = asc + desc + 2 * sw
    em = None
    if emoji:
        big = _emoji_png(emoji)
        if big is not None:
            em = big.resize((int(big.width * size / 160), int(big.height * size / 160)),
                            Image.LANCZOS)
    bw = int(max(fnt.getlength(x) for x in lines)) + 2 * sw + 4
    bh = lh * len(lines) + (em.height + int(size * 0.1) if em else 0)
    im = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    key = (keyword or "").strip(".,!?:;\"'").lower()
    space = fnt.getlength(" ")
    for k, line in enumerate(lines):
        x = (bw - fnt.getlength(line)) / 2
        for word in line.split(" "):
            hit = key and word.strip(".,!?:;\"'").lower() == key
            d.text((x, sw + k * lh), word, font=fnt,
                   fill=key_fill if hit else (255, 255, 255, 255),
                   stroke_width=sw, stroke_fill=(0, 0, 0, 255))
            x += fnt.getlength(word) + space
    if em:
        im.paste(em, ((bw - em.width) // 2, lh * len(lines) + int(size * 0.1)), em)
    return im


def pop(cards, out: Path, *, dur: float, size=92, y=0.44, canvas=CANVAS, fps=60,
        fill=None, accent=None, stroke=(0, 0, 0, 255), stroke_frac=0.10,
        title: str | None = None, title_s: float = 1.0,
        title_emoji: str | None = None, title_keyword: str | None = None,
        font: str | None = None):
    """jiyu val's caption style, measured off his Shorts at 60fps.

    Baloo 2 ExtraBold at normal letter spacing, lowercase as spoken, a pastel
    fill on a heavy black outline, and a POP entrance: the card appears at
    60% size, overshoots to 106% by 0.05s and settles at 100% by 0.10s. No
    fade, no lift, no tilt; an emphasised card changes colour only.

    Each card is drawn once and only rescaled per frame, so the outline
    keeps its weight relative to the glyphs as it pops.

    `font` is an `engine.caption_fonts` key, the web app's dropdown pick;
    None is Baloo 2 ExtraBold, the look above.
    """
    from . import caption_fonts
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    if fill is None or accent is None:
        raise ValueError("pop: fill and accent must be explicit")
    w, h = canvas
    n = int(round(dur * fps))

    def face(px):
        return caption_fonts.face(font, px)

    def card_image(c):
        px = size
        while True:
            fnt = face(px)
            sw = max(4, int(px * stroke_frac))
            l, t, r, b = fnt.getbbox(c["text"], stroke_width=sw)
            if r - l <= w - 80 or px <= 48:
                break
            px = int(px * (w - 80) / (r - l))
        im = Image.new("RGBA", (r - l + 4, b - t + 4), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((2 - l, 2 - t), c["text"], font=fnt,
                                fill=accent if c.get("emph") else fill,
                                stroke_width=sw, stroke_fill=stroke)
        return im

    def scale_at(age):
        if age < 0.05:
            q = age / 0.05
            return 0.60 + 0.46 * (1 - (1 - q) ** 2)
        if age < 0.10:
            return 1.06 - 0.06 * (age - 0.05) / 0.05
        return 1.0

    by_frame, imgs = {}, {}
    if title:
        # THE TITLE TAKES THE CAPTION SLOT for the opening `title_s`, with
        # the same pop. Index -1 so no card can collide with it; the caller
        # has already moved the cards off this span.
        imgs[-1] = _title_image(title, emoji=title_emoji, keyword=title_keyword)
        for f in range(min(n, int(round(title_s * fps)))):
            by_frame[f] = (-1, f / fps)
    for i, c in enumerate(cards):
        a, b = int(c["start"] * fps), int(c["end"] * fps)
        for f in range(max(0, a), min(n, b)):
            by_frame.setdefault(f, (i, (f - a) / fps))
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
         "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
         "-c:v", "qtrle", "-pix_fmt", "argb", str(out)],
        stdin=subprocess.PIPE)
    blank = np.zeros((h, w, 4), np.uint8).tobytes()
    cy = int(y * h)
    for f in range(n):
        hit = by_frame.get(f)
        if hit is None:
            proc.stdin.write(blank)
            continue
        i, age = hit
        if i not in imgs:
            imgs[i] = card_image(cards[i])
        im = imgs[i]
        s = scale_at(age)
        if abs(s - 1.0) > 1e-3:
            im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))),
                           Image.LANCZOS)
        layer = Image.new("RGBA", canvas, (0, 0, 0, 0))
        layer.paste(im, ((w - im.width) // 2, cy - im.height // 2), im)
        proc.stdin.write(np.asarray(layer, dtype=np.uint8).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed writing {out}")
    return out


def kinetic(cards, out: Path, *, dur: float, size=88, y=0.44, canvas=CANVAS, fps=60,
            settle=0.085, lift=10, grow=0.045, accent=None, tilt_emph=1.2,
            font_path=IMPACT, emph_scale=1.27, track=-1,
            fill=WHITE, stroke=(0, 0, 0, 255)):
    """The C style, damped.

    George: "number three probably has the best subtitle style, if it was a
    little bit smaller and less bouncy." So: 78px instead of 104-136, the
    scale travel cut from 0.24 to 0.055, the lift from 26px to 12, the tilt
    from 4.5 degrees to 1.4, and a critically-damped ease instead of a
    spring that overshoots. It still arrives; it no longer bounces.

    `fill` is the body colour, `accent` the emphasised cards', `stroke` the
    outline every card is drawn with. All three used to be literals in the
    draw loop.

    **TWO SILENT FAILURE MODES CLOSED HERE, and both were defaults.**
    `accent` defaulted to `titles.ACCENT`, which is GOLD — the v43 caption
    accent, from before the palette changed — so any caller that forgot the
    argument got gold captions beside blue cards, which is exactly the
    "two videos stacked on each other" this project renamed a whole file to
    avoid. It is `None` now and resolves to the house blue, with one
    definition shared with `make_clip.CAPTION_ACCENT`.

    And PIL's `ImageDraw.text(fill=None)` draws **white** rather than
    raising, so a missing or mistyped colour would have shipped as "looks
    almost right" instead of failing. Both are now explicit and validated by
    `engine.caption_colour` before they reach here.
    """
    from .caption_colour import DEFAULT_EMPH, rgba                # noqa: PLC0415
    if accent is None:
        accent = rgba(DEFAULT_EMPH)
    if fill is None or stroke is None:
        raise ValueError("kinetic: fill and stroke must be explicit — PIL "
                         "draws white on fill=None instead of raising")
    import math

    import numpy as np
    from PIL import Image, ImageDraw

    w, h = canvas
    n = int(round(dur * fps))
    from PIL import ImageFont
    if font_path and Path(font_path).exists():
        font = ImageFont.truetype(font_path, size)
        big = ImageFont.truetype(font_path, int(size * emph_scale))
    else:
        font, big = _font(size), _font(int(size * emph_scale))

    by_frame = {}
    for c in cards:
        a, b = int(c["start"] * fps), int(c["end"] * fps)
        for f in range(max(0, a), min(n, b)):
            by_frame.setdefault(f, (c, (f - a) / fps))

    def draw_tracked(d, xy, s, fnt, col, sw):
        """C set letterSpacing -1; PIL has no tracking, so step per glyph."""
        x, yy = xy
        for ch in s:
            d.text((x, yy), ch, font=fnt, fill=col, stroke_width=sw,
                   stroke_fill=stroke)
            x += d.textlength(ch, font=fnt) + track

    def tracked_w(d, s, fnt):
        return sum(d.textlength(c, font=fnt) for c in s) + track * (len(s) - 1)

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
        col = accent if c.get("emph") else fill

        layer = Image.new("RGBA", canvas, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        tw = tracked_w(d, c["text"], fnt)
        # Shrink to fit rather than letting a long emphasis card run off the
        # frame — "OUT OF PROPORTION" at 1.27x is 970px of a 1080px frame.
        if tw > w - 70:
            shrunk = max(44, int((fnt.size if hasattr(fnt, "size") else size)
                                 * (w - 70) / tw))
            fnt = ImageFont.truetype(font_path, shrunk) if font_path and Path(font_path).exists() else _font(shrunk)
            tw = tracked_w(d, c["text"], fnt)
        cy = int(y * h) + int(lift * (1 - k))
        draw_tracked(d, ((w - tw) / 2, cy), c["text"], fnt, col,
                     max(5, int(size * 0.095)))

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
