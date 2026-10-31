"""Hook title and persistent topic banner — both straight from the references.

`docs/SKILLS.md` catalogues ten techniques across the four reference clips.
Two of them are titles, both were missing, and between them they are most of
what separates a finished clip from a bare two-pane layout:

* **Skill 8, hook title (R1).** Two lines, ALL CAPS, cap height ~140px, one
  coloured keyword, on at 0.00, holds to 1.5s, 0.5s dissolve out.
* **Skill 7, persistent topic banner (R2, R4).** R2 held a blue-boxed claim
  for the whole clip; R4 runs a headline along the lower third throughout.
  Both answer "what am I watching" for someone arriving mid-scroll.

Also worth recording what the references do NOT have. **Skill 9: speed ramps
and punch-ins are "not observed in any reference" — all four are talking-head
formats.** Zoom punches on a talking head are a gameplay technique imported
where it does not belong.

Rendered as PNGs because this ffmpeg has no `drawtext` (no libfreetype); they
are composited with `overlay`, which also gives a real alpha dissolve.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = Path.home() / "Library" / "Fonts"
FONT_STACK = ("Tungsten-Bold.otf", "Tungsten-Black.otf",
              "Proxima Nova Extrabold.ttf", "OpenSans-Bold.ttf")
ACCENT = (255, 206, 0, 255)
WHITE = (255, 255, 255, 255)
STROKE = (0, 0, 0, 240)


def _font(size: int):
    for name in FONT_STACK:
        p = FONT_DIR / name
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default(size)


def hook(lines, out: Path, *, width=1080, cap_px=140, accent_words=()):
    """R1's hook: two ALL-CAPS lines with a coloured keyword each."""
    font = _font(cap_px)
    pad, lh = 26, int(cap_px * 1.14)
    img = Image.new("RGBA", (width, lh * len(lines) + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    sw = max(5, cap_px // 14)
    acc = {w.upper() for w in accent_words}
    for i, ln in enumerate(lines):
        ln = ln.upper()
        toks = ln.split(" ")
        tw = d.textlength(ln, font=font)
        x, y = (width - tw) / 2, pad + i * lh
        for tok in toks:
            col = ACCENT if tok.strip(".,!?") in acc else WHITE
            d.text((x, y), tok, font=font, fill=col,
                   stroke_width=sw, stroke_fill=STROKE)
            x += d.textlength(tok + " ", font=font)
    img.save(out)
    return img.size


def banner(text: str, out: Path, *, width=1080, size=46, pad_x=30, pad_y=16):
    """R2/R4's persistent headline. Boxed so it reads over any content."""
    font = _font(size)
    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    tw = probe.textlength(text.upper(), font=font)
    bw, bh = int(tw) + pad_x * 2, int(size * 1.5) + pad_y
    img = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, bw - 1, bh - 1], radius=8, fill=(12, 14, 20, 225))
    d.rounded_rectangle([0, 0, bw - 1, bh - 1], radius=8, outline=ACCENT, width=3)
    d.text(((bw - tw) / 2, (bh - size * 1.22) / 2), text.upper(),
           font=font, fill=WHITE)
    img.save(out)
    return img.size


def chip(text: str, out: Path, *, width=1080, size=46,
         pad_x=28, pad_y=16, accent=ACCENT):
    """A small supporting popup that tracks the argument.

    George: "I'd prefer to have popups with low volume dings." The sound
    belongs to a VISUAL event — a chip arriving — which is why the earlier
    cues read as random: they fired with nothing on screen to explain them.

    Filled accent with dark text, deliberately INVERTED against the banner.
    First pass drew both as outlined dark cards and they read as two
    banners; the popup has to be visibly a different kind of object from the
    thing that sits there all clip.
    """
    font = _font(size)
    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    tw = probe.textlength(text.upper(), font=font)
    bw, bh = int(tw) + pad_x * 2, int(size * 1.45) + pad_y
    img = Image.new("RGBA", (bw + 8, bh + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([5, 6, bw + 5, bh + 6], radius=9, fill=(0, 0, 0, 120))  # drop shadow
    d.rounded_rectangle([0, 0, bw, bh], radius=9, fill=accent)
    d.text(((bw - tw) / 2, (bh - size * 1.2) / 2 - 1), text.upper(),
           font=font, fill=(12, 12, 14))
    img.save(out)
    return img.size
