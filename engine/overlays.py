"""Turn overlay PNGs into alpha movie clips Resolve can composite.

Why this exists. The overlays were being bolted on in ffmpeg AFTER Resolve
rendered, which meant they were invisible in the Resolve timeline and could
not be nudged in the UI. George: "stop being lazy, edit this in davinci."

What stops the obvious approach. Resolve's Edit page has **no keyframe API**:
`Opacity` is a settable TimelineItem property (verified — set 40, reads back
40) but takes a single static value, numeric Fusion inputs refuse keyframes,
and `AddTransition` does not exist at all. Note `hasattr` is useless here —
these are remote proxies and `hasattr(tl, "ThisDoesNotExist")` returns True,
which is how AddTransition looked available. Call it and it raises.

So the fade and the settle are baked into a **ProRes 4444 clip with an alpha
channel**, full-frame and already in position. Resolve then does the real
work — it is a clip on a video track, composited by Resolve, visible in the
UI, trimmable, and it renders with everything else. Nothing is added after
the render except the loudness pass, which Resolve genuinely cannot do
(`NormalizeAudioLevel` applies gain without true-peak limiting).

A still image cannot be used directly: a PNG in the media pool reports
`Frames == 1` and `AppendToTimeline` ignores `endFrame` for it, so the clip
lands at Resolve's default still length. A movie clip honours `endFrame`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

CANVAS = (1080, 1920)
FPS = 60


def alpha_clip(png: Path, out: Path, *, dur: float, x: int | str = "(W-w)/2",
               y: int = 0, fade_in: float = 0.10, fade_out: float = 0.25,
               settle_px: int = 16, settle_s: float = 0.16,
               canvas=CANVAS, fps: int = FPS) -> Path:
    """Render one overlay as a full-frame ProRes 4444 clip with alpha.

    `settle_px` is the small downward-to-rest move on entry — the thing that
    makes a card read as arriving rather than cutting in. It is a MOVE, not a
    scale: output dimensions must be constant, so `scale` cannot animate, but
    `overlay`'s y accepts `t`.
    """
    w, h = canvas
    yexpr = (f"{y}+{settle_px}*max(0\\,1-t/{settle_s})" if settle_px else str(y))
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         # `,format=rgba` must be INSIDE the lavfi source. `color=black@0.0`
         # alone emits an opaque format, and converting to rgba afterwards
         # gives opaque black — the @0.0 had nothing to be carried in. That
         # produced a clip that looked right in a still and composited in
         # Resolve as a solid black rectangle.
         "-f", "lavfi", "-i",
         f"color=c=black@0.0:s={w}x{h}:r={fps}:d={dur:.3f},format=rgba",
         "-loop", "1", "-framerate", str(fps), "-t", f"{dur:.3f}", "-i", str(png),
         "-filter_complex",
         f"[0]null[bg];"
         f"[1]format=rgba,fade=t=in:st=0:d={fade_in}:alpha=1,"
         f"fade=t=out:st={max(0.0, dur - fade_out):.3f}:d={fade_out}:alpha=1[ov];"
         # format=auto, NOT rgb: `overlay=...:format=rgb` silently flattens the
         # alpha and the clip composites as an opaque black frame in Resolve.
         f"[bg][ov]overlay=x={x}:y='{yexpr}':format=auto[v]",
         # qtrle (QuickTime Animation), not ProRes 4444. Both are lossless
         # with alpha and Resolve reads both, but these frames are almost
         # entirely transparent and RLE collapses that to nothing: a 3.4s
         # overlay is ~2 MB instead of ~250 MB. Five ProRes overlays filled
         # the disk and the render died with exit 228.
         "-map", "[v]", "-c:v", "qtrle", "-pix_fmt", "argb", str(out)],
        check=True)
    return out


def frames(seconds: float, fps: int = FPS) -> int:
    """Seconds to a frame count. `endFrame` is EXCLUSIVE in AppendToTimeline."""
    return int(round(seconds * fps))


def sequence_clip(fn, out: Path, *, dur: float, canvas=CANVAS, fps: int = FPS,
                  fade_in: float = 0.10, fade_out: float = 0.25) -> Path:
    """Render a per-frame function to an alpha clip Resolve can composite.

    `alpha_clip` is enough for a static card that fades and settles. An
    annotation that DRAWS ON cannot be expressed that way — R1's marker
    circle at 0:31 is caught mid-stroke, and a circle that merely fades in
    reads as a UI element rather than someone pointing at something.

    `fn(t, i)` returns an RGBA PIL image the size of the canvas. Frames are
    piped to ffmpeg as raw RGBA, so nothing hits the disk in between.
    """
    import numpy as np

    w, h = canvas
    n = int(round(dur * fps))
    # A zero-length `fade` is NOT a no-op — ffmpeg falls back to a default
    # duration and quietly ramps the whole clip, which turned a measured
    # 0.13s-down / 0.40s-hold envelope into one slow linear fade with no
    # hold at all. When the caller's own function already carries the
    # envelope, emit no fade filter.
    chain = []
    if fade_in > 0:
        chain.append(f"fade=t=in:st=0:d={fade_in}:alpha=1")
    if fade_out > 0:
        chain.append(f"fade=t=out:st={max(0.0, dur - fade_out):.3f}:d={fade_out}:alpha=1")
    graph = f"[0]{','.join(chain)}[v]" if chain else "[0]null[v]"
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
         "-filter_complex", graph,
         "-map", "[v]", "-c:v", "qtrle", "-pix_fmt", "argb", str(out)],
        stdin=subprocess.PIPE)
    for i in range(n):
        img = fn(i / fps, i)
        proc.stdin.write(np.asarray(img.convert("RGBA"), dtype=np.uint8).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed writing {out}")
    return out


SEAM_Y = 806          # 0.42 * 1920, the house seam


def pane_dip(out: Path, *, dur: float = 0.56, down: float = 0.13, up: float = 0.15,
             depth: float = 0.42, seam_y: int = SEAM_Y, canvas=CANVAS,
             fps: int = FPS) -> Path:
    """R1's dip between exhibits (1:11), measured frame by frame.

    What the measurement changed about my assumptions, all three ways:

    * **Only the CONTENT PANE dips.** The facecam sits at 67-69 luma right
      through it, untouched. Dipping the whole frame would be a different,
      much heavier effect.
    * **It does not reach black.** R1's pane bottoms out at ~6 luma from
      ~79, and that FLOOR is what a viewer sees, so match it rather than the
      ratio — clip 8's roster board is far darker (23-30 luma) and the same
      92% would land on literally 0, reading as a dropped frame.

    **RESOLVE COMPOSITES IN LINEAR LIGHT, and it changes the number by 12x.**
    The identical clip over the identical frame gives a 0.189 luma ratio in
    ffmpeg (exactly the 0.18 the alpha asks for) and 0.015 in Resolve.
    Measured at two depths, the transfer is `(1 - alpha) ** 2.4`: alpha 0.82
    predicts 0.0156 and measured 0.015. So an alpha meant to darken by a
    given amount on screen must be solved through that gamma, not set
    directly. For R1's floor here: (1-a)**2.4 = 6/24 -> a = 0.42.
    * **It is a fade, not a cut**, and an asymmetric one: down in ~0.13s,
      hold ~0.40s, up in ~0.15s, 0.56s in all.

    It is the ONLY transition observed anywhere in the four references — no
    wipes, no whooshes. And it earns its place by separating one exhibit
    from the next, so it goes where a document changes and nowhere else.
    """
    from PIL import Image

    hold_end = dur - up
    w, h = canvas

    def fn(t, i):
        if t < down:
            a = t / down
        elif t < hold_end:
            a = 1.0
        else:
            a = max(0.0, (dur - t) / up)
        frame = Image.new("RGBA", canvas, (0, 0, 0, 0))
        band = Image.new("RGBA", (w, h - seam_y), (0, 0, 0, int(255 * depth * a)))
        frame.alpha_composite(band, (0, seam_y))
        return frame

    # No extra fades: the envelope above IS the fade.
    return sequence_clip(fn, out, dur=dur, canvas=canvas, fps=fps,
                         fade_in=0.0, fade_out=0.0)


# --- easing ---------------------------------------------------------------
# The reveal was a linear fade plus a 16px settle, which is why the cards
# read as flat. These are the curves that make a graphic feel thrown rather
# than faded. No dependency needed — the surveyed Python motion libraries
# (movis, pymotion) are mostly these functions plus a compositor we already
# have.

def ease_out_expo(p: float) -> float:
    return 1.0 if p >= 1 else 1 - 2 ** (-10 * p)


def ease_out_back(p: float, overshoot: float = 1.34) -> float:
    c3 = overshoot + 1
    return 1 + c3 * (p - 1) ** 3 + overshoot * (p - 1) ** 2


def ease_in_out_cubic(p: float) -> float:
    return 4 * p ** 3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2


def exhibit_reveal(png: Path, out: Path, *, dur: float, y: int,
                   from_x: float = 0.5, grow_in: float = 0.34,
                   hold_drift: int = 9, canvas=CANVAS, fps: int = FPS,
                   fade_out: float = 0.26, start_scale: float = 0.78,
                   blur_px: float = 9.0) -> Path:
    """A card thrown out of the document, not faded onto it.

    George liked the KRU card and asked for "more graphics and motion like
    that but in a cooler style". The motion is the part that was missing:

    * it SCALES UP from 0.78 on an ease-out-back, so it overshoots a touch
      and settles, instead of arriving at its final size;
    * it comes from `from_x`, the horizontal position of the region it was
      cropped from, so it reads as pulled out of that part of the board;
    * it resolves from a 9px blur as it lands, which is what sells a scale
      as depth rather than as a size change;
    * it drifts a few px while held, so a 3.5s card is never a still.
    """
    from PIL import Image, ImageFilter

    card = Image.open(png).convert("RGBA")
    w, h = canvas
    cw, ch = card.size
    n = int(round(dur * fps))
    hold_end = dur - fade_out
    x_from = from_x * w

    def fn(t, i):
        frame = Image.new("RGBA", canvas, (0, 0, 0, 0))
        p = min(1.0, t / grow_in)
        e = ease_out_back(p) if p < 1 else 1.0
        s = start_scale + (1.0 - start_scale) * e
        drift = hold_drift * ease_in_out_cubic(min(1.0, t / max(dur, 1e-3)))

        nw, nh = max(2, int(cw * s)), max(2, int(ch * s))
        layer = card.resize((nw, nh), Image.LANCZOS)
        if p < 1.0 and blur_px > 0:
            layer = layer.filter(ImageFilter.GaussianBlur(blur_px * (1 - p)))

        # travel from the source region's x toward centre as it grows
        cx = x_from + (w / 2 - x_from) * ease_out_expo(p)
        px = int(cx - nw / 2)
        py = int(y + (h * 0.012) * (1 - e) - drift)
        frame.alpha_composite(layer, (max(-nw, px), max(-nh, py)))

        a = 1.0
        if t < 0.08:
            a = t / 0.08
        elif t > hold_end:
            a = max(0.0, (dur - t) / fade_out)
        if a < 1.0:
            frame.putalpha(frame.getchannel("A").point(lambda v: int(v * a)))
        return frame

    return sequence_clip(fn, out, dur=dur, canvas=canvas, fps=fps,
                         fade_in=0.0, fade_out=0.0)
