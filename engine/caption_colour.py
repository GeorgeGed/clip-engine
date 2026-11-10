"""WHICH COLOUR A CAPTION MAY BE, and the measurement that decides it.

George: *"some of them will just need basic cuts with different colour
subtitles and no chat"*.

Two readings, and both are served: the **emphasis** colour (the ~13% of
cards drawn in accent, which is the existing argument) and the **body**
fill. Nothing else about the caption style moves — Impact, 88px, emphasis
1.27x, a 9.5% hard black stroke, critically damped, riding the seam at
y 0.44 — because George picked that himself after four style versions and
only the colour was ever in question.

**THE STROKE IS THE BACKGROUND, NOT THE VIDEO.** A caption sits on a 9.5%
hard black outline, so what a colour has to survive is `#000000`, whatever
is behind the clip. That is why this is checkable at all: the contrast is a
property of the style, not of the footage.

Measured here with `build_chat._ratio`, the same WCAG implementation the
username lift already uses — one implementation, not two:

    name        hex        vs black   vs white
    white       #FFFFFF       21.00       1.00
    yellow      #FFE94E       17.02       1.23
    gold        #FFCE00       14.08       1.49
    cyan        #22D3EE       11.62       1.81
    green       #2BD96B       11.24       1.87
    orange      #FF8A3D        8.95       2.35
    pink        #FF5CA8        7.35       2.86
    red         #FF4655        6.26       3.36
    vermilion   #F4512A        6.06       3.47
    blue        #5C80FF        5.99       3.51
    violet      #A855F7        5.31       3.96
    brandblue   #2E5CFF        4.09       5.13   <- REFUSED

**THE OBVIOUS REQUEST IS THE ONE THAT FAILS.** "Use our brand blue" is
`#2E5CFF` at **4.09:1**, under the 4.5 floor — which is exactly why
`C.blueLight` exists: the same hue and saturation lifted from L 0.59 to
0.68, reading 5.99:1. So the palette refuses the brand blue by name and
offers the lifted one, rather than letting a reasonable-sounding choice ship
as unreadable type.

**IT IS A NAMED PALETTE, VENDORED, NOT A FREE COLOUR FIELD.** Two reasons.
A free field invites `#2E5CFF`. And this file's own record is that the
newsprint palette failed at 3.15:1 and that gold captions beside vermilion
cards read as two videos stacked — a coherence failure no contrast ratio
predicts. A name can carry that judgement; a hex string cannot.
"""

from __future__ import annotations

FLOOR = 4.5                  # WCAG AA for large text is 3.0; this is stricter
STROKE = (0, 0, 0, 255)      # the house stroke, and what every colour is measured against

# name -> hex. Everything here clears FLOOR against STROKE; `check()` proves
# it rather than trusting the table.
PALETTE: dict[str, str] = {
    "white":     "#FFFFFF",
    "blue":      "#5C80FF",   # theme.tsx C.blueLight — what ships today
    "gold":      "#FFCE00",   # titles.ACCENT, the v43 caption accent
    "vermilion": "#F4512A",   # the palette before Polymarket
    "green":     "#2BD96B",
    "cyan":      "#22D3EE",
    "pink":      "#FF5CA8",
    "red":       "#FF4655",   # Riot's own brand red
    "orange":    "#FF8A3D",
    "violet":    "#A855F7",
    "yellow":    "#FFE94E",
}

# Named and refused, with the reason, so the answer is "not that one, this
# one" rather than "unknown colour".
REFUSED: dict[str, tuple[str, str]] = {
    "brandblue": ("#2E5CFF", "4.09:1 against the caption stroke, under the "
                             "4.5 floor — use \"blue\" (#5C80FF), the same "
                             "hue lifted to 5.99:1"),
}

# What ships. `make_clip.CAPTION_ACCENT` is this value; one definition.
DEFAULT_FILL = "white"
DEFAULT_EMPH = "blue"


def rgba(name_or_hex: str) -> tuple[int, int, int, int]:
    """A palette name, or a hex string that clears the floor.

    A hex string is allowed — somebody will want one — but it goes through
    the same measurement, so the floor cannot be walked round by spelling
    the colour differently.
    """
    key = str(name_or_hex).strip().lower()
    if key in REFUSED:
        hexv, why = REFUSED[key]
        raise ValueError(f"caption colour {key!r} ({hexv}) is refused: {why}")
    if key in PALETTE:
        key = PALETTE[key]
    if not key.startswith("#"):
        raise ValueError(
            f"unknown caption colour {name_or_hex!r} — "
            f"one of {', '.join(sorted(PALETTE))}, or a #hex")
    s = key.lstrip("#")
    if len(s) not in (6, 8) or any(c not in "0123456789abcdefABCDEF" for c in s):
        raise ValueError(f"{name_or_hex!r} is not a #RRGGBB colour")
    rgb = tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    r = ratio(rgb)
    if r < FLOOR:
        raise ValueError(
            f"{name_or_hex!r} reads {r:.2f}:1 against the caption's own hard "
            f"black stroke, under the {FLOOR} floor — it would not be "
            f"legible over either pane")
    return (*rgb, int(s[6:8], 16) if len(s) == 8 else 255)


def ratio(rgb) -> float:
    """WCAG contrast against the caption stroke, via the ONE implementation
    this project already has. A second one is how two places come to
    disagree about a number."""
    import build_chat as bc                                   # noqa: PLC0415
    return bc._ratio(tuple(rgb)[:3], STROKE[:3])


def check() -> list[str]:
    """Every entry clears the floor. Returns the failures, which must be []."""
    bad = []
    for name, hexv in PALETTE.items():
        s = hexv.lstrip("#")
        r = ratio([int(s[i:i + 2], 16) for i in (0, 2, 4)])
        if r < FLOOR:
            bad.append(f"{name} ({hexv}) is {r:.2f}:1")
    return bad
