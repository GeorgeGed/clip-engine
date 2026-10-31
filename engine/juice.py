"""The visual punctuation layer, applied after the Resolve render.

It lives here rather than in Resolve because the Edit page has NO keyframe API
for transforms — `SetProperty` writes a static value, numeric Fusion inputs
refuse keyframes, and the only animation Resolve exposes to Python is a Fusion
expression. ffmpeg gives frame-level control of the whole frame, so the
structural edit stays in Resolve and the juice is a finishing pass.

Every effect is tied to something in the footage, per the contract: punches
and flashes land on CUTS, shake lands on an emphasised caption. An effect that
punctuates nothing is decoration.

The flash is deliberately gentle. WCAG's general flash threshold is 3 per
second at intensity <= 0.8 and `gates.py` rejects beyond it; a cut flash at
0.22 over 0.18s is far inside that, and cuts here are ~4.7/min, not 3/s.
"""

from __future__ import annotations

PUNCH_AMOUNT = 0.16      # 0.085 was there but barely readable in motion
PUNCH_DECAY = 5.5        # e-folds per second; ~0.5s to settle
FLASH_AMOUNT = 0.07      # measured: 0.22 lifted luma 57->112, a blowout
FLASH_DECAY = 26.0
SHAKE_AMOUNT = 5.0       # pixels
SHAKE_HZ = 11.0


def _terms(times, amount, decay, window, var="t"):
    """Sum of decaying impulses, as an ffmpeg expression.

    CLAMP THE EXPONENT. Writing exp(-k*(t-C)) and gating it with gte(t,C)
    looks right and is not: ffmpeg does not short-circuit, so the exponential
    is evaluated anyway, and for t far BEFORE C it overflows. At t=0 with
    C=39.861 and k=26, exp(1036) is +inf, inf*0 is NaN, and a NaN brightness
    crushed the first 12.5 seconds of a 51s clip to black. max(0, t-C) keeps
    the exponent at or below zero so the term is always finite.
    """
    if not times:
        return "0"
    return "+".join(
        f"{amount}*exp(-{decay}*max(0,{var}-{x:.3f}))*gte({var},{x:.3f})"
        f"*lt({var},{x + window:.3f})" for x in times)


def punch_expr(cuts, *, amount=PUNCH_AMOUNT, decay=PUNCH_DECAY) -> str:
    return f"1+({_terms(cuts, amount, decay, 0.7)})"


def flash_expr(cuts, *, amount=FLASH_AMOUNT, decay=FLASH_DECAY) -> str:
    return f"({_terms(cuts, amount, decay, 0.25)})"


def shake_expr(beats, *, amount=SHAKE_AMOUNT, hz=SHAKE_HZ) -> str:
    """Decaying wobble on an emphasised beat."""
    if not beats:
        return "0"
    return "+".join(
        f"{amount}*sin({hz}*6.2832*(t-{x:.3f}))*exp(-9*max(0,t-{x:.3f}))"
        f"*gte(t,{x:.3f})*lt(t,{x + 0.45:.3f})" for x in beats)


def filtergraph(cuts, beats, *, w=1080, h=1920, fps=60) -> str:
    """Punch and shake by animating a CROP, then the cut flash via eq.

    `crop` rather than zoompan: zoompan needs `it` instead of `t` and brings
    its own warmup quirks, while crop exposes `t` directly. Crop dimensions
    are forced even for yuv420p.

    ffmpeg 9 note: `crop` no longer takes `eval`. Its w/h/x/y are flagged `T`
    (runtime-tunable) and are evaluated every frame already; passing
    `eval=frame` fails with "Option not found". `eq` still needs it.
    """
    z = f"min(max({punch_expr(cuts)},1.0),1.30)"
    sx = shake_expr(beats)
    return (
        f"crop=w='2*floor(iw/(2*({z})))':h='2*floor(ih/(2*({z})))'"
        f":x='(iw-ow)/2+({sx})':y='(ih-oh)/2',"
        f"scale={w}:{h},"
        f"eq=brightness='{flash_expr(cuts)}':eval=frame"
    )
