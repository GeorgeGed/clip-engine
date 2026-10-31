"""Visual punctuation, applied after the Resolve render.

**Every effect carries a motivation and the code refuses one without it.**
That is the contract's rule and the first version broke it: 22 effect events
across 51 seconds, a punch and a flash on every cut regardless of what was
being said, and shakes on `emphasis[:14]` — literally the first fourteen
caption cards, seven of them inside the opening five seconds. George's note
was "so random", and he was reading it correctly. Effects landed on structure
(cuts) rather than on anything happening in the footage.

What actually motivates an effect here, measured rather than assumed:

* **Vocal emphasis.** Per-word RMS against the speaker's own baseline. On
  clip 8 the baseline is −23.3 dBFS and the peak −18.3: a **5 dB** total
  range, so there are exactly FOUR moments above +3.5 dB. The footage does
  not support more than a handful of effects, and spraying 22 at it is what
  made them read as noise.
* **The payoff.** The clip's last claim beat gets the signature move, the
  same way a frag clip gets one slow-mo on the kill.

Deliberately NOT motivated, so deliberately absent:

* **Flashes on cuts.** A cut is already an edit event; flashing it punctuates
  nothing. Neither reference clip uses flashes at all.
* **Shake.** It was decoration on a speaker this measured.

It lives in ffmpeg because Resolve's Edit page has no keyframe API for
transforms — `SetProperty` writes a static value and numeric Fusion inputs
refuse keyframes, so smooth motion cannot come from the Edit page at all.
"""

from __future__ import annotations

from dataclasses import dataclass

MIN_SPACING = 3.0        # two effects closer than this read as one jitter
FLASH_CAP = 0.8          # WCAG, enforced by gates.py
FLASH_RATE_CAP = 3.0     # per second


@dataclass
class Beat:
    """One motivated effect."""
    at: float
    kind: str                 # 'punch' | 'flash'
    intensity: float          # 0..1
    motivation: str           # what in the footage this punctuates

    def __post_init__(self):
        if not (self.motivation or "").strip():
            raise ValueError(
                f"{self.kind} at {self.at}s has no motivation. An effect that "
                f"punctuates nothing is decoration — see AGENTS.md.")
        if self.kind == "flash" and self.intensity > FLASH_CAP:
            raise ValueError(f"flash intensity {self.intensity} exceeds the "
                             f"WCAG cap of {FLASH_CAP}")


def check(beats: list[Beat], duration: float) -> list[str]:
    """Warnings a human should see before this renders."""
    out = []
    ordered = sorted(beats, key=lambda b: b.at)
    for a, b in zip(ordered, ordered[1:]):
        if b.at - a.at < MIN_SPACING:
            out.append(f"{a.kind}@{a.at:.2f} and {b.kind}@{b.at:.2f} are "
                       f"{b.at - a.at:.2f}s apart (min {MIN_SPACING}s)")
    flashes = [b for b in ordered if b.kind == "flash"]
    for i, f in enumerate(flashes):
        window = [g for g in flashes[i:] if g.at - f.at < 1.0]
        if len(window) > FLASH_RATE_CAP:
            out.append(f"{len(window)} flashes within 1s at {f.at:.2f} — "
                       f"over the WCAG {FLASH_RATE_CAP}/s threshold")
    if duration and len(ordered) / (duration / 60) > 20:
        out.append(f"{len(ordered)} effects over {duration:.0f}s is "
                   f"{len(ordered)/(duration/60):.0f}/min — likely decoration")
    return out


def _impulse(var, at, amount, decay, window):
    """A decaying impulse, gated and CLAMPED.

    max(0, t-C) is not cosmetic. ffmpeg does not short-circuit, so a gated
    exp(-k*(t-C)) still evaluates the exponential for t far before C; at t=0
    with C=39.9 and k=26 that is exp(1036) = +inf, inf*0 = NaN, and a NaN
    brightness blacked out the first 12.5s of a 51s clip.
    """
    return (f"{amount}*exp(-{decay}*max(0,{var}-{at:.3f}))"
            f"*gte({var},{at:.3f})*lt({var},{at + window:.3f})")


def filtergraph(beats: list[Beat], *, w=1080, h=1920, fps=60) -> str:
    """Punch via zoompan, flash via eq.

    It has to be zoompan. `crop` CANNOT animate a zoom: a filter's output
    dimensions must stay constant for the encoder, so crop evaluates w/h once
    at init and only x/y can move — which is why ffmpeg 9 dropped crop's
    `eval` option entirely. A crop-based "punch" silently renders at zoom
    1.00; measured against the ungraded source it came back identical,
    residual 0.3. zoompan scales internally and emits a constant size, which
    is the whole reason the filter exists.

    zoompan's evaluator has NO `t` — it offers `it` (input timestamp) and
    errors with "Undefined constant" on `t`. `eq`, later in the chain, does
    use `t`.
    """
    punches = [b for b in beats if b.kind == "punch"]
    flashes = [b for b in beats if b.kind == "flash"]

    z = "1"
    if punches:
        z = "1+(" + "+".join(
            _impulse("it", b.at, round(0.10 + 0.14 * b.intensity, 4),
                     5.0, 0.9) for b in punches) + ")"
    zc = f"min(max({z},1.0),1.35)"

    chain = (f"zoompan=z='{zc}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
             f":s={w}x{h}:fps={fps}")
    if flashes:
        fx = "+".join(_impulse("t", b.at, round(0.09 * b.intensity, 4), 26.0, 0.25)
                      for b in flashes)
        chain += f",eq=brightness='({fx})':eval=frame"
    return chain


# ─── camera movement, measured off R1 ─────────────────────────────────────

SHOT_PUSH_RAMP = 2.0      # seconds; R1's moves run 2-10% over about 1.5s
SHOT_PUSH_RATE = 0.40     # fraction of shots that carry a move


def shot_push_expr(shots, pushes, ramp=SHOT_PUSH_RAMP):
    """Zoom expression for a slow push at the head of selected shots.

    Measured on R1 by matching each shot's first frame against a frame 1.5s
    later across a scale sweep: **8 of 18 facecam shots and 6 of 15 content
    shots move, by 2-10%**; the rest are static. So the reference does NOT
    move continuously, and it does not punch-and-settle either — it eases in
    at the head of a shot and holds.

    An earlier attempt to measure this by integrating per-frame
    Fourier-Mellin scale drifted 12x over 80s and reported 3.5 direction
    reversals a second: pure noise accumulation. Match two frames seconds
    apart instead; there is nothing to accumulate.

    `shots` is [(start, end)], `pushes` the fraction per shot (0 = static).
    """
    terms = []
    for (s, e), p in zip(shots, pushes):
        if p <= 0:
            continue
        terms.append(f"{p}*min(1,max(0,(it-{s:.3f})/{ramp}))"
                     f"*gte(it,{s:.3f})*lt(it,{e:.3f})")
    return "1+(" + "+".join(terms) + ")" if terms else "1"
