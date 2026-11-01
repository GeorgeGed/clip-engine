#!/usr/bin/env python3
"""Render the caption track to one alpha movie: `overlays/cap_kin.mov`.

This existed only as a shell command typed by hand, which is how the
captions kept their old gold emphasis through a full palette change — the
cards went warm graphite and vermilion and the subtitles stayed `#FFCE00`,
which is precisely the hybrid the palette work was meant to avoid. A card
set and a caption set that disagree about their accent read as two
different videos stacked on each other.

106 cards, 16 of them emphasised. The style is the one George picked
himself after four style versions and it does not change here: **Impact,
88px, emphasis 1.27x, a 9.5% hard black stroke, critically damped, white
fill, riding the seam at y 0.44.** Impact stays the voice face; it is only
the ACCENT that moves, and only so it matches everything else.

Measured, because the emphasis has to survive its own stroke over both
backgrounds: `#F4512A` reads **6.06:1 against hard black**, against gold's
14.08:1. Lower, and still comfortably over the 4.5:1 floor — where the
newsprint palette's spot red would have given 3.15:1, which is why that
direction lost. The emphasised word also sits at 1.27x with a 9.5% stroke,
so it is large text by any definition.

Usage:  ./.venv/bin/python build_captions.py
"""
from pathlib import Path

from engine import captions_video

ROOT = Path(__file__).parent
CARDS = ROOT / "vendor/remotion-clip08/public/cards.json"
OUT = ROOT / "jobs/fns-2905408276/overlays/cap_kin.mov"

# theme.tsx `C.accent`. One value, two renderers.
ACCENT = (244, 81, 42, 255)
DUR = 2812 / 60          # the delivered picture length


def main():
    import json
    cards = json.loads(CARDS.read_text())
    emph = sum(1 for c in cards if c.get("emph"))
    captions_video.kinetic(cards, OUT, dur=DUR, accent=ACCENT)
    mb = OUT.stat().st_size / 1e6
    print(f"{len(cards)} cards ({emph} emphasised), {DUR:.2f}s -> {OUT.name}  {mb:.0f} MB")


if __name__ == "__main__":
    main()
