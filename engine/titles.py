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


def stat(items, source: str, out: Path, *,
         num_px=92, label_px=36, src_px=25, pad=24, gap=46, accent=ACCENT):
    """A fact card: one or more figures, what each counts, where they came from.

    George rejected the first chips — "BLOWN OUT OF PROPORTION", "NO JOB
    SECURITY" — as "random text cards": they restated what he was already
    saying, so they carried nothing. His own test was the news screenshot at
    the head of the clip: "if you had useful information to put on the screen
    like you did at the start it'd be fine."

    So a card has to carry a FACT. These come off the exhibit already on his
    screen — the VCT Roster Board header — which is real on-screen data that
    is simply illegible once the frame is letterboxed to a phone. Surfacing it
    is the same move R1 makes by running exhibits through its lower pane.

    **A lone figure can argue the opposite of the point.** Three independent
    judges caught this before it shipped: "32 OPEN SLOTS" on its own reads as
    32 jobs going spare, which undercuts a scarcity argument. It only means
    scarcity next to the 274 chasing them. So `items` is a list — pair a
    figure with its denominator rather than showing it alone.

    Labels are copied VERBATIM from the source ("bench / options", not
    "bench") and no noun is invented ("274 not yet confirmed", never "274
    players"): the board counts staff and bench in other columns, so naming
    the unit would assert something the source does not say. The source line
    is not decoration — an unsourced number on a quote desk is a liability.
    """
    if isinstance(items, tuple):
        items = [items]
    fnum, flab, fsrc = _font(num_px), _font(label_px), _font(src_px)
    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))

    cols = []
    for number, label in items:
        w = max(probe.textlength(number, font=fnum),
                probe.textlength(label.upper(), font=flab))
        cols.append((number, label, w))
    ws = probe.textlength(source.upper(), font=fsrc)
    body_w = sum(c[2] for c in cols) + gap * (len(cols) - 1)
    bw = int(max(body_w, ws)) + pad * 2 + 14
    bh = int(src_px * 1.5 + num_px * 0.82 + label_px * 1.15) + pad * 2

    img = Image.new("RGBA", (bw + 8, bh + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([6, 7, bw + 6, bh + 7], radius=10, fill=(0, 0, 0, 130))
    d.rounded_rectangle([0, 0, bw, bh], radius=10, fill=(13, 15, 20, 242))
    d.rectangle([0, 8, 7, bh - 8], fill=accent)            # accent rule

    x0 = pad + 10
    d.text((x0, pad - 6), source.upper(), font=fsrc, fill=(148, 154, 168, 255))
    y = pad - 6 + int(src_px * 1.5)
    x = x0
    for number, label, w in cols:
        d.text((x, y), number, font=fnum, fill=accent)
        d.text((x, y + int(num_px * 0.82)), label.upper(), font=flab, fill=WHITE)
        x += w + gap
    img.save(out)
    return img.size


# The stat strip of the VCT Roster Board, in SOURCE pixels, measured off
# jobs/fns-2905408276 clip 08 by column-variance. Six blocks, left to right:
# 32 teams | 139 signed | 32 open slots | 82 bench/options | 78 staff |
# 274 not yet confirmed.
STRIP_Y = (152, 180)
STRIP_BLOCKS = [(18, 70), (109, 170), (209, 284), (322, 427), (466, 508), (546, 670)]


def exhibit(src_png: Path, out: Path, *, crop_x=(200, 680), width=1010,
            highlight=(), source="VCT Roster Board", accent=ACCENT,
            pad=22, src_px=25, rule_px=4):
    """Magnify a region of the SOURCE frame and underline what matters.

    George, on a card drawn from scratch: "i dont like the design - looks vibe
    coded." Looking again at R1 for how it handles a stat panel, the answer is
    that **it does not design one** — the Leetify card at 0:08 is a screenshot
    of a real page composited in, exactly like the tweet card at the head of
    this clip. The reference shows the document; it does not redraw it.

    So this does the same. The numbers are the actual pixels from the board on
    his screen, magnified about 2x, with an accent rule under the figures being
    pointed at. It cannot be mis-transcribed, it cannot drift from the source,
    and it cannot look like a generic component because nothing about it is
    styled.

    `crop_x` must be a CONTIGUOUS run of the strip. Stitching non-adjacent
    stats together would fabricate an adjacency the page does not have, which
    is doctoring an exhibit.
    """
    strip = Image.open(src_png).convert("RGBA").crop(
        (crop_x[0], STRIP_Y[0], crop_x[1], STRIP_Y[1]))
    sc = width / (crop_x[1] - crop_x[0])
    strip = strip.resize((width, max(1, round(strip.height * sc))), Image.LANCZOS)

    fsrc = _font(src_px)
    head = int(src_px * 1.7)
    bw, bh = width + pad * 2, strip.height + head + rule_px + 10 + pad * 2
    img = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, bw - 1, bh - 1], fill=(8, 10, 14, 242))   # square, no shadow
    d.rectangle([0, 0, bw - 1, 0], fill=accent)

    x = pad
    for ch in source.upper():                       # tracked-out kicker
        d.text((x, pad - 4), ch, font=fsrc, fill=(150, 157, 170, 255))
        x += d.textlength(ch, font=fsrc) + 2.0

    top = pad - 4 + head
    img.paste(strip, (pad, top), strip)
    for i in highlight:
        a, b = STRIP_BLOCKS[i]
        x0 = pad + round((a - crop_x[0]) * sc)
        x1 = pad + round((b - crop_x[0]) * sc)
        d.rectangle([x0, top + strip.height + 7, x1, top + strip.height + 7 + rule_px],
                    fill=accent)
    img.save(out)
    return img.size


# Regions of the VCT Roster Board worth showing, in SOURCE pixels, measured
# off clip 08's frame. The board is pixel-static for 61 of the clip's 67s
# (content-region frame delta: median 0.13, one change at 5.5s), so variety
# in the lower pane has to come from moving through the document rather than
# from the document changing — which is what R1 gets for free by having
# seven different exhibits.
BOARD_REGIONS = {
    "strip": (10, 152, 680, 180),        # the header stat line
    "kru":   (958, 246, 1417, 480),      # KRU Esports: 1/5 signed, 4 unconfirmed
    "g2":    (489, 246, 951, 480),
    "nrg":   (958, 637, 1417, 880),
    "sen":   (1431, 637, 1894, 880),
}


def panel(src_png: Path, out: Path, rect, *, width=820, kicker="VCT Roster Board",
          boxes=(), rules=(), accent=ACCENT, pad=22, src_px=25, rule_px=4):
    """Magnify any region of a SOURCE frame and mark what matters.

    The general form of `exhibit`. Same principle, which is the one R1
    demonstrates and three rejected designs taught: **show the document, do
    not redraw it.** Real pixels cannot be mis-transcribed, cannot drift from
    the source, and preserve handle casing for free — "KRU ESPORTS",
    "Dantedeu5", "mwzera" come out right without touching the whisper
    transcript that garbles them.

    `rect` is (x0, y0, x1, y1) in source pixels and must be a single
    contiguous region; stitching separated parts together fabricates an
    adjacency the page does not have. `boxes` outlines sub-rects (also in
    source pixels), `rules` underlines them.
    """
    x0, y0, x1, y1 = rect
    img_src = Image.open(src_png).convert("RGBA")
    crop = img_src.crop((x0, y0, x1, y1))
    sc = width / (x1 - x0)
    crop = crop.resize((width, max(1, round(crop.height * sc))), Image.LANCZOS)

    fsrc = _font(src_px)
    head = int(src_px * 1.7) if kicker else 0
    extra = rule_px + 7 if rules else 0
    bw, bh = width + pad * 2, crop.height + head + extra + pad * 2
    img = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, bw - 1, bh - 1], fill=(8, 10, 14, 242))      # square, no shadow
    d.rectangle([0, 0, bw - 1, 0], fill=accent)

    if kicker:
        x = pad
        for ch in kicker.upper():
            d.text((x, pad - 4), ch, font=fsrc, fill=(150, 157, 170, 255))
            x += d.textlength(ch, font=fsrc) + 2.0

    top = pad - 4 + head
    img.paste(crop, (pad, top), crop)

    def to_px(v, origin):
        return round((v - origin) * sc)

    for bx0, by0, bx1, by1 in boxes:
        d.rectangle([pad + to_px(bx0, x0), top + to_px(by0, y0),
                     pad + to_px(bx1, x0), top + to_px(by1, y0)],
                    outline=accent, width=3)
    for rx0, rx1 in rules:
        d.rectangle([pad + to_px(rx0, x0), top + crop.height + 7,
                     pad + to_px(rx1, x0), top + crop.height + 7 + rule_px],
                    fill=accent)
    img.save(out)
    return img.size
