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
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
         "-filter_complex",
         f"[0]fade=t=in:st=0:d={fade_in}:alpha=1,"
         f"fade=t=out:st={max(0.0, dur - fade_out):.3f}:d={fade_out}:alpha=1[v]",
         "-map", "[v]", "-c:v", "qtrle", "-pix_fmt", "argb", str(out)],
        stdin=subprocess.PIPE)
    for i in range(n):
        img = fn(i / fps, i)
        proc.stdin.write(np.asarray(img.convert("RGBA"), dtype=np.uint8).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed writing {out}")
    return out
