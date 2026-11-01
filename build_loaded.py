"""The assets for the loaded cut — transitions, act cards, seam treatment.

George: "no transitions, no sounds, no background effects, no coloring ...
no storyline ... you're literally just changing the subtitles." All true of
what I shipped, and the cause was a rule of my own making: only use what is
measurable in R1/R2. Both are restrained talking-head clips, so that rule
caps the work at a two-pane layout with captions. His instruction overrides
it here, and the note in AGENTS.md that "a cut is already an edit event, so
no flashes on cuts" is overruled with it.
"""
from pathlib import Path
import math
import sys

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from PIL import Image, ImageDraw, ImageFilter
from engine.overlays import sequence_clip, alpha_clip
from engine.titles import _font, ACCENT

OUT = ROOT / "jobs/fns-2905408276/overlays"
OUT.mkdir(parents=True, exist_ok=True)
PNG = OUT / "png"; PNG.mkdir(exist_ok=True)
W, H, FPS = 1080, 1920, 60
SEAM = 806

# The 10 splices the dead-space cut created, in output seconds.
CUTS = [8.97, 12.31, 17.55, 20.59, 21.74, 22.38, 27.79, 31.83, 35.92, 44.01]

# Three movements of the argument. The card states the beat in his own terms.
ACTS = [
    (0.70, 2.10, "GLOBAL ESPORTS", "IS OUT"),
    (17.30, 1.90, "SO WHAT HAPPENS", "TO THE PLAYERS"),
    (43.40, 2.20, "YOU CAN END UP", "WITH NOTHING"),
]


def sweep(out: Path, dur=0.20, fps=FPS):
    """A light sweep across the frame — a transition you can actually see.

    A soft bright band travels corner to corner and a short luma lift rides
    with it. Fast enough (0.20s) to read as a wipe between shots rather than
    as an effect sitting on top of one.
    """
    n = int(dur * fps)

    def fn(t, i):
        p = t / dur
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        # the band sweeps from off-frame left to off-frame right
        x = -620 + p * (W + 1240)
        for k, (off, a) in enumerate(((0, 150), (90, 92), (190, 46), (-90, 92), (-190, 46))):
            d.polygon([(x + off, -200), (x + off + 150, -200),
                       (x + off - 330, H + 200), (x + off - 480, H + 200)],
                      fill=(255, 252, 238, a))
        img = img.filter(ImageFilter.GaussianBlur(26))
        # a short overall lift at the midpoint, strongest as the band crosses
        lift = int(34 * math.sin(math.pi * min(1.0, max(0.0, p))) ** 2)
        if lift:
            img.alpha_composite(Image.new("RGBA", (W, H), (255, 250, 235, lift)))
        # ease the whole thing out so it does not clip on or off
        env = math.sin(math.pi * p) ** 0.6
        img.putalpha(img.getchannel("A").point(lambda v: int(v * env)))
        return img

    return sequence_clip(fn, out, dur=dur, fps=fps, fade_in=0.0, fade_out=0.0)


def act_card(line1: str, line2: str, out: Path, cap=118):
    """A full-width act card: accent rule, two lines, heavy stroke, no box."""
    f = _font(cap)
    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    w1, w2 = probe.textlength(line1, font=f), probe.textlength(line2, font=f)
    lh = int(cap * 1.08)
    img = Image.new("RGBA", (W, lh * 2 + 76), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    rw = int(max(w1, w2))
    rx = (W - rw) // 2
    d.rectangle([rx, 0, rx + rw, 7], fill=ACCENT)
    d.text(((W - w1) / 2, 30), line1, font=f, fill=(255, 255, 255, 255),
           stroke_width=10, stroke_fill=(0, 0, 0, 255))
    d.text(((W - w2) / 2, 30 + lh), line2, font=f, fill=ACCENT,
           stroke_width=10, stroke_fill=(0, 0, 0, 255))
    img.save(out)
    return img.size


def seam_glow(out: Path, dur: float):
    """The seam is a hard butt-join between two panes. A thin accent rule with
    a soft glow under it turns the edge into a deliberate divider, and a light
    vignette frames the whole thing instead of leaving four sharp corners."""
    base = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    g = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(g)
    d.rectangle([0, SEAM - 26, W, SEAM + 26], fill=(255, 206, 0, 70))
    g = g.filter(ImageFilter.GaussianBlur(22))
    base.alpha_composite(g)
    d2 = ImageDraw.Draw(base)
    d2.rectangle([0, SEAM - 2, W, SEAM + 1], fill=(255, 206, 0, 190))

    # vignette: a soft dark frame, strongest in the corners
    vig = Image.new("L", (W // 4, H // 4), 0)
    dv = ImageDraw.Draw(vig)
    dv.ellipse([-W // 10, -H // 12, W // 4 + W // 10, H // 4 + H // 12], fill=150)
    vig = vig.filter(ImageFilter.GaussianBlur(34)).resize((W, H), Image.LANCZOS)
    dark = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    dark.putalpha(vig.point(lambda v: int((255 - v) * 0.42)))
    base.alpha_composite(dark)
    base.save(PNG / "seam.png")
    return alpha_clip(PNG / "seam.png", out, dur=dur, y=0,
                      fade_in=0.4, fade_out=0.4, settle_px=0)


if __name__ == "__main__":
    print("sweep      ", sweep(OUT / "sweep.mov"))
    for i, (at, hold, l1, l2) in enumerate(ACTS):
        p = PNG / f"act{i}.png"
        print(f"act {i}      ", act_card(l1, l2, p),
              alpha_clip(p, OUT / f"act{i}.mov", dur=hold, y=820,
                         fade_in=0.16, fade_out=0.40, settle_px=18).name)
    print("seam+vignette", seam_glow(OUT / "seam.mov", 46.93).name)
