"""The caption fonts a job can pick, by key.

The web app's font dropdown lists these keys, the Worker stores the pick on
the job, Modal passes it to `pipeline.core.specs`, and it reaches
`captions_video.pop` as `Clip.caption_font`. One table, so the dropdown can
never offer a font the renderer cannot draw. Keep `webapp/src/fonts.ts` in
step with it; `tests/test_caption_fonts.py` checks that they match.

Every file is in fonts/ with its licence: SIL OFL for all but Luckiest Guy,
which is Apache 2.0. `scale` evens out how big each face looks at the same
pixel size: the condensed all-caps faces (Anton, Bebas Neue) read small at
the house 92px, a wide one (Luckiest Guy) reads large.
"""
from __future__ import annotations

from pathlib import Path

FONTS_DIR = Path(__file__).resolve().parent.parent / "fonts"
DEFAULT = "baloo"

# key: (label, file, variable-font weight or None, scale)
FONTS = {
    "baloo": ("Baloo 2 ExtraBold", "Baloo2[wght].ttf", 800, 1.00),
    "tiktok": ("TikTok Sans Bold", "TikTokSans[opsz,slnt,wdth,wght].ttf", 700, 1.00),
    "montserrat": ("Montserrat Black", "Montserrat[wght].ttf", 900, 0.92),
    "poppins": ("Poppins ExtraBold", "Poppins-ExtraBold.ttf", None, 0.94),
    "anton": ("Anton", "Anton-Regular.ttf", None, 1.05),
    "bebas": ("Bebas Neue", "BebasNeue-Regular.ttf", None, 1.25),
    "bangers": ("Bangers", "Bangers-Regular.ttf", None, 1.08),
    "luckiest": ("Luckiest Guy", "LuckiestGuy-Regular.ttf", None, 0.92),
}


def key(k: str | None) -> str:
    """`k` when it is a known font, else the default. Never raises: an old
    job or a hand-written spec with no font still builds."""
    return k if k in FONTS else DEFAULT


def face(k: str | None, px: int):
    """The PIL font for key `k` at `px` before its scale."""
    from PIL import ImageFont
    _label, file, wght, scale = FONTS[key(k)]
    f = ImageFont.truetype(str(FONTS_DIR / file), max(8, int(round(px * scale))))
    if wght is not None:
        f.set_variation_by_axes([wght if a["name"] in (b"Weight", "Weight") else a["default"]
                                 for a in f.get_variation_axes()])
    return f
