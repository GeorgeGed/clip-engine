"""The two-pane L2 layout as an ffmpeg filter graph, with no Resolve in it.

Resolve does exactly three things to the picture: this geometry, the per-shot
framings and punches, and one static ASC CDL on the facecam. Everything else
a clip is made of — captions, chat, cards, the sfx bed, the audio finish — is
already a file on disk or already pure ffmpeg. This module is the first of
the three, and it is the one that was load-bearing: it is why builds are
serial, why they need a logged-in desktop, and why they crashed four times
in one day.

`two_pane()` is PURE. It takes a `Channel` and a list of `Shot`s and returns
a filter-graph string. Nothing is rendered, nothing is read off disk, so the
geometry can be asserted on in a test in milliseconds — which matters,
because this repo's most-repeated defect is two numbers that are supposed to
be the same number derived twice, and `panes()` exposes the same integers the
string is built from so a test compares them rather than parsing text.

================================================================ THE SHAPE =

ONE CHAIN PER SHOT, VSTACKED, THEN CONCATENATED. Chosen, not inherited:

* `crop` CANNOT animate its w/h. Output dimensions have to be constant for
  the encoder, so crop evaluates w/h once at init and only x/y move — which
  is why ffmpeg 9 removed its `eval` option. The facecam crop SIZE changes
  every shot (364x272, 327x245, 349x261, 313x234, 342x256, and a 1.1364x
  punched variant of each — ten distinct sizes), so a framing change is a
  SEGMENT BOUNDARY and cannot be an animated parameter.
* `zoompan` can animate a zoom and is the right tool when the zoom RAMPS.
  Here it does not: a framing change is a hard cut between shots. Using it
  would buy an animation nobody asked for and bring its own traps — its
  evaluator has no `t`, only `it`, and it is a second scaler with its own
  rounding.
* The content pane's crop size *is* constant across `cuts.content_framings`
  (see THE CONTENT ZOOM IS A PAN below), so that pane alone could have been
  one chain with `x` as a time expression. It is not, for one reason: both
  panes cut at the same shot boundaries, so building each shot's two panes
  and `vstack`ing them into a whole 1080x1920 frame creates the seam ONCE
  per shot from two integers that sum to the canvas height. The seam cannot
  drift between the panes because neither pane is positioned — they are
  stacked. One concat of whole frames, not two concats of half frames.

So, per shot: trim -> split -> two crops -> two scales -> vstack, then one
concat over the shots. A single-shot clip skips the outer split and the
concat but is still trimmed, so the last shot's `end` bounds the picture on
every branch — see the comment in `two_pane` for the frame count that was
off by one when it did not.

SEGMENT BOUNDARIES ARE FRAMES, NOT SECONDS. `trim=start_frame=A:end_frame=B`
with B EXCLUSIVE, which is both ffmpeg's convention and Resolve's (measured:
`startFrame=0, endFrame=100` yields a 100-frame clip; writing `endFrame =
round(t*fps) - 1` dropped one frame from every segment and put a single black
frame at each of five cut points). The keeps this layout is built over are
already rounded onto the frame grid by `round(t*fps)`, so seconds are
converted the same way and contiguity is ASSERTED: a one-frame gap between
two segments is a dropped frame, and a dropped frame in this pipeline has
read as a black frame before.

DO NOT CARRY OVER THE MarkIn +1. `make_clip` compensates for Resolve
rendering one frame before the mark. That bug does not exist here and the
compensation would shift the whole clip.

=========================================================== THE INTEGERS ==

`crop` and `scale` take integers and the exact geometry does not:

* THE PANE SPLIT IS ROUNDED TO EVEN. seam 0.42 x 1920 = 806.4, so the panes
  are 806 + 1114 = 1920 (0.4px of seam error; the delivered Resolve render
  best-fits at 806.34 against a spec of 806.40, so Resolve is not exact
  either). EVEN, not merely integer, because `vstack` on a subsampled format
  needs each input's height to be even — seam 0.485, R5's chat reference,
  rounds to 931.2 and an odd 931 would mis-site chroma at the seam.
* THE CROPS ARE ROUNDED CENTRE-FIRST. Round the visible width and height,
  then place x/y so the CENTRE is preserved, because a shifted centre moves
  the face in frame while a 0.3% size error only changes the upscale. Worst
  case measured across the cycle: 0.6px of source shift, 0.13% of anisotropy
  between the horizontal and vertical scale factors.
* EVERY CROP CARRIES `exact=1`, AND THE GRAPH CONVERTS TO yuv444p FIRST.
  Measured on this ffmpeg (9.0.2): `crop=365:271:1495:343` on a yuv420p
  source renders 364x270 — it silently rounds an odd w/h DOWN to the chroma
  grid, with no warning, which is a 1px geometry change that looks exactly
  like nothing. Either the 4:4:4 conversion or `exact=1` prevents it; both
  are here so that removing one does not re-open it. The 4:4:4 conversion
  also earns its keep on its own: the facecam is a ~3x upscale of a 464px
  region, so in 4:2:0 its chroma would be interpolated 6x from 232px.

======================================================= THE CONTENT ZOOM ==

`cuts.content_framings` cycles `(cx, zoom)` and its docstring says "Zoom > 1
narrows the window, which makes the text BIGGER". IT DOES NOT, and this
module reproduces what Resolve actually renders rather than what that
sentence says. Under fill the vertical axis always limits for these rects, so
the content scale is pinned at pane_h/(src_h-chrome) and the visible window
is the same size for all five entries; the zoom reaches the picture ONLY as a
horizontal pan, by shifting the clamped x0 across a 169.5px span. Verified in
the delivered file: the fitted source x0 per frame returns the five predicted
values to within 0.09px at NCC 0.999, with the scale held fixed at 1.1271 for
every one. Same class as the crop-based "zoom" this repo once shipped that
rendered at exactly 1.00x and looked plausible in a still.

Reproduce first, then change it deliberately if a bigger document is wanted —
a parity check against Resolve will fail on the lower pane otherwise.

====================================================== THE AXIS GUARD ====

The whole no-masking simplification rests on `src_aspect > pane_aspect`. When
that holds the overflow is HORIZONTAL: Resolve lets it run off the canvas
edges, where it touches nothing, and cropping it away here is equivalent.
When it does not hold the overflow is VERTICAL, and Resolve would let the
facecam bleed DOWN across the seam over the content pane (V2 sits above V1)
while this graph would crop it — a difference that is not sub-pixel. Every
cam in this repo is 1.771-1.779 against the pane's 1.3393, but R5's
chat-overlay reference measures 1.16:1, so the case is real. `panes()`
RAISES there rather than assuming, and says what the fix is.
"""
from __future__ import annotations

from dataclasses import dataclass

CANVAS_W = 1080
CANVAS_H = 1920
SRC_W = 1920
SRC_H = 1080

# lanczos is the house upscaler for the facecam pane — `render_ffmpeg` already
# uses `flags=lanczos` on exactly this crop, and the facecam needs the sharpest
# available because it is a 3x upscale of a soft 464px region.
SCALE_FLAGS = "lanczos"

# `cuts.content_framings`' own cycle, repeated here ONLY as the default for
# callers that do not pass shots built by `shots_from_cuts`. That helper reads
# the real cycle out of `engine.cuts`, so the two cannot drift.
CONTENT_CYCLE = ((0.50, 1.00), (0.34, 1.12), (0.62, 1.06),
                 (0.44, 1.18), (0.58, 1.02))


@dataclass(frozen=True)
class Shot:
    """One picture cut: a span of the source and how each pane frames it.

    `start`/`end` are seconds into THIS graph's input, which is the already-cut
    picture — a shot is a run of consecutive keeps, so its bounds are keep
    bounds and land on the frame grid.

    `inset` is `cuts.framings`' cycle value for the facecam and `punch` is the
    extra inset on top of it (`resolve_punch.PUNCH_INSET`, 0.12, = 1.1364x);
    they are applied in that order with the same upward bias, because the face
    sits above the box centre and successive insets have to keep tracking it.

    `content_cx`/`content_zoom` are `cuts.content_framings`' cycle entry. Read
    THE CONTENT ZOOM IS A PAN above before changing the zoom.

    `content_rect` overrides both with an explicit source rect, which is how an
    exhibit crop (`cuts.exhibit_framings`) gets into the lower pane.
    """
    start: float
    end: float
    inset: float = 0.0
    punch: float = 0.0
    content_cx: float = 0.50
    content_zoom: float = 1.00
    content_rect: tuple[float, float, float, float] | None = None


@dataclass(frozen=True)
class Crop:
    """An integer source crop, and the error that rounding it cost."""
    w: int
    h: int
    x: int
    y: int
    # the exact rect it was rounded from, so the cost is reportable rather
    # than discovered later as a 1px drift in a parity best-fit
    exact: tuple[float, float, float, float]

    @property
    def dx(self) -> float:
        return self.x - self.exact[0]

    @property
    def dy(self) -> float:
        return self.y - self.exact[1]

    def arg(self) -> str:
        return (f"crop=w={self.w}:h={self.h}:x={self.x}:y={self.y}:exact=1")


@dataclass(frozen=True)
class ShotGeom:
    """What one shot renders: two integer crops and its frame span."""
    first: int          # inclusive
    last: int           # EXCLUSIVE, matching trim's end_frame
    top: Crop
    bottom: Crop

    @property
    def nframes(self) -> int:
        return self.last - self.first


@dataclass(frozen=True)
class Panes:
    """The whole layout: the pane split and one ShotGeom per shot."""
    top_h: int
    bottom_h: int
    seam_exact: float
    shots: tuple[ShotGeom, ...]

    @property
    def seam_err(self) -> float:
        return self.top_h - self.seam_exact


def _round_even(v: float) -> int:
    return 2 * round(v / 2)


def pane_split(seam: float, canvas_h: int = CANVAS_H) -> tuple[int, int, float]:
    """(top_h, bottom_h, exact seam) with both panes EVEN and summing to H."""
    exact = seam * canvas_h
    top = _round_even(exact)
    if not 0 < top < canvas_h:
        raise ValueError(f"seam {seam} puts the split at {top} of {canvas_h}")
    return top, canvas_h - top, exact


def visible(src_rect, pane_w: float, pane_h: float) -> tuple[tuple, float]:
    """The part of `src_rect` Resolve actually shows, and the scale it shows it at.

    This is `resolve_layout.plan()` inverted. `plan` is always called with
    fill=True in this pipeline (never overridden), so the pane is covered and
    the overflow axis is centre-cropped; the scale is therefore the LARGER of
    the two ratios and the excess comes off both sides equally.
    """
    sx0, sy0, sx1, sy1 = src_rect
    ws, hs = sx1 - sx0, sy1 - sy0
    if ws <= 0 or hs <= 0:
        raise ValueError(f"empty source rect {src_rect}")
    s = max(pane_w / ws, pane_h / hs)
    ox, oy = ws * s - pane_w, hs * s - pane_h
    return ((sx0 + max(ox, 0) / (2 * s), sy0 + max(oy, 0) / (2 * s),
             sx1 - max(ox, 0) / (2 * s), sy1 - max(oy, 0) / (2 * s)), s)


def _check_axis(src_rect, pane_w: float, pane_h: float, who: str) -> None:
    sx0, sy0, sx1, sy1 = src_rect
    sa, pa = (sx1 - sx0) / (sy1 - sy0), pane_w / pane_h
    if sa <= pa:
        raise ValueError(
            f"{who}: source aspect {sa:.4f} <= pane aspect {pa:.4f}, so the "
            f"overflow is VERTICAL. Resolve lets it bleed across the seam over "
            f"the pane below; this graph crops it instead, and the two renders "
            f"would differ by more than a pixel. Build that case as an overlay "
            f"over the full canvas rather than a vstack, or crop the rect to "
            f"aspect > {pa:.4f} first. See THE AXIS GUARD in native_layout.")


def _to_crop(src_rect, pane_w: float, pane_h: float, who: str,
             src_w: int = SRC_W, src_h: int = SRC_H) -> Crop:
    """Round a visible rect to integers, preserving its CENTRE."""
    _check_axis(src_rect, pane_w, pane_h, who)
    (vx0, vy0, vx1, vy1), _s = visible(src_rect, pane_w, pane_h)
    w, h = round(vx1 - vx0), round(vy1 - vy0)
    if w < 2 or h < 2:
        raise ValueError(f"{who}: visible rect rounds to {w}x{h}")
    cx, cy = (vx0 + vx1) / 2, (vy0 + vy1) / 2
    x, y = round(cx - w / 2), round(cy - h / 2)
    if not (0 <= x and x + w <= src_w and 0 <= y and y + h <= src_h):
        raise ValueError(
            f"{who}: crop {w}x{h} at ({x},{y}) leaves the {src_w}x{src_h} "
            f"source — the rect {tuple(round(v, 2) for v in src_rect)} is "
            f"outside the frame")
    return Crop(w, h, x, y, (vx0, vy0, vx1, vy1))


def _inset(rect, f: float):
    """`cuts.framings`/`resolve_punch.inset`'s shared bias: dy*0.6 off the top,
    dy*1.4 off the bottom, because the face sits above the box centre."""
    x0, y0, x1, y1 = rect
    dx, dy = (x1 - x0) * f / 2, (y1 - y0) * f / 2
    return (x0 + dx, y0 + dy * 0.6, x1 - dx, y1 - dy * 1.4)


def _content_rect(cx: float, zoom: float, chrome: int,
                  src_w: int = SRC_W, src_h: int = SRC_H):
    """`cuts.content_framings`' rect for one cycle entry, clamped as it is there."""
    vis_w = src_w / zoom
    x0 = min(max(cx * src_w - vis_w / 2, 0.0), src_w - vis_w)
    return (x0, float(chrome), x0 + vis_w, float(src_h))


def panes(channel, shots, *, cam=None, src_w: int = SRC_W, src_h: int = SRC_H,
          canvas_w: int = CANVAS_W, canvas_h: int = CANVAS_H) -> Panes:
    """Resolve every shot to integer crops. No ffmpeg, no filesystem.

    `cam` overrides `channel.cam` — the facecam rect is PER CLIP, not per
    channel, because a streamer moves their own layout between scenes and
    reusing clip 8's rect on clip 6 rendered a top pane with no face in it.
    """
    cam = tuple(cam or channel.cam)
    fps = channel.fps
    top_h, bot_h, seam_exact = pane_split(channel.seam, canvas_h)
    if not shots:
        raise ValueError("no shots")

    out, prev_end = [], None
    for i, sh in enumerate(shots):
        a, b = round(sh.start * fps), round(sh.end * fps)
        if b <= a:
            raise ValueError(f"shot {i}: {sh.start}-{sh.end}s is "
                             f"{b - a} frames at {fps}fps")
        if prev_end is None:
            if a != 0:
                raise ValueError(
                    f"shot 0 starts at frame {a}, not 0 — the graph's input is "
                    f"the cut picture, so the first shot owns frame 0")
        elif a != prev_end:
            raise ValueError(
                f"shot {i} starts at frame {a} but shot {i-1} ended at "
                f"{prev_end}: a {a - prev_end:+d} frame "
                f"{'gap' if a > prev_end else 'overlap'}. A gap renders as "
                f"dropped frames and an overlap as duplicated ones.")
        prev_end = b

        rect = _inset(cam, sh.inset)
        if sh.punch:
            rect = _inset(rect, sh.punch)
        crect = sh.content_rect or _content_rect(
            sh.content_cx, sh.content_zoom, channel.chrome, src_w, src_h)
        out.append(ShotGeom(
            a, b,
            _to_crop(rect, canvas_w, top_h, f"shot {i} facecam", src_w, src_h),
            _to_crop(crect, canvas_w, bot_h, f"shot {i} content", src_w, src_h),
        ))
    return Panes(top_h, bot_h, seam_exact, tuple(out))


def two_pane(channel, shots, *, cam=None, src: str = "0:v", out: str = "v",
             top_filters: str = "", bottom_filters: str = "",
             scale_flags: str = SCALE_FLAGS, src_w: int = SRC_W,
             src_h: int = SRC_H, canvas_w: int = CANVAS_W,
             canvas_h: int = CANVAS_H) -> str:
    """The filter graph that makes `src` into the 1080x1920 two-pane layout.

    `top_filters` / `bottom_filters` are inserted after each pane's scale — the
    insertion point for the facecam's ASC CDL, which Resolve applies to V2 only
    because the lower pane is a document and lifting contrast there costs text
    legibility for no gain. Both default to nothing: this function is the
    GEOMETRY and the grade is its own measured problem.

    Returns a string. It renders nothing, so what it claims is checkable
    without ffmpeg — and then has to be checked WITH ffmpeg, because a filter
    graph that runs is not a filter graph that is correct.
    """
    g = panes(channel, shots, cam=cam, src_w=src_w, src_h=src_h,
              canvas_w=canvas_w, canvas_h=canvas_h)
    tf = f",{top_filters.strip(',')}" if top_filters.strip(',') else ""
    bf = f",{bottom_filters.strip(',')}" if bottom_filters.strip(',') else ""
    n = len(g.shots)
    L = []

    # yuv444p ONCE, before the split, so the odd crop offsets below are exact
    # and the facecam's 3x upscale does not interpolate chroma 6x. See THE
    # INTEGERS above for the measurement that put it here.
    head = f"[{src}]format=yuv444p"
    if n == 1:
        L.append(f"{head}[v0]")
    else:
        L.append(f"{head},split={n}[" + "][".join(f"v{i}" for i in range(n)) + "]")

    for i, s in enumerate(g.shots):
        # EVERY shot is trimmed, the single-shot case included. Skipping it
        # there looks free and is not: measured, a one-shot graph passed 1992
        # frames of a source whose shot ends at frame 1991, so the output
        # length stopped being a function of the shots on one branch only.
        # Two code paths that are supposed to produce the same frame count is
        # this repo's most-repeated defect, so there is one rule — the last
        # shot's `end` bounds the picture — and both branches obey it.
        # end_frame is EXCLUSIVE; setpts rebases each segment to 0 so concat
        # sees them head to tail.
        L.append(f"[v{i}]trim=start_frame={s.first}:end_frame={s.last},"
                 f"setpts=PTS-STARTPTS,split=2[a{i}][b{i}]")
        L.append(f"[a{i}]{s.top.arg()},"
                 f"scale={canvas_w}:{g.top_h}:flags={scale_flags},"
                 f"setsar=1{tf}[t{i}]")
        L.append(f"[b{i}]{s.bottom.arg()},"
                 f"scale={canvas_w}:{g.bottom_h}:flags={scale_flags},"
                 f"setsar=1{bf}[c{i}]")
        # vstack, not overlay: the seam is made once from two integers that
        # sum to the canvas height, so it cannot drift between the panes.
        L.append(f"[t{i}][c{i}]vstack=inputs=2[{'f%d' % i if n > 1 else out}]")

    if n > 1:
        L.append("[" + "][".join(f"f{i}" for i in range(n)) +
                 f"]concat=n={n}:v=1:a=0[{out}]")
    return ";".join(L)


def resolve_delta(channel, shots, *, cam=None, canvas_w: int = CANVAS_W,
                  canvas_h: int = CANVAS_H, src_w: int = SRC_W,
                  src_h: int = SRC_H) -> list[dict]:
    """How far this graph's integer geometry sits from what Resolve renders.

    Computed against `resolve_layout.plan()` ITSELF, never against retyped
    survey constants — the two paths have to stay the same geometry and this
    repo's recurring defect is exactly two such numbers drifting with nothing
    saying so. Resolve's reference is the EXACT pane (806.4 / 1113.6); this
    graph renders the even one (806 / 1114), so the error has two parts and
    they are reported separately rather than summed into one misleading px:

      `d_origin`  where the visible source rect starts, in SOURCE px
      `d_scale`   the source->canvas scale, as a fraction
      `aniso`     this graph's own horizontal/vertical scale mismatch, which
                  Resolve does not have because its pane is not integer

    `render_native` should print these in the build log. Nothing here needs
    ffmpeg or a live Resolve.
    """
    from engine.resolve_layout import Frame, plan

    f = Frame(canvas_w, canvas_h, src_w, src_h)
    seam_y = channel.seam * canvas_h
    g = panes(channel, shots, cam=cam, src_w=src_w, src_h=src_h,
              canvas_w=canvas_w, canvas_h=canvas_h)
    cam = tuple(cam or channel.cam)
    out = []
    for i, (sh, geom) in enumerate(zip(shots, g.shots)):
        rect = _inset(cam, sh.inset)
        if sh.punch:
            rect = _inset(rect, sh.punch)
        crect = sh.content_rect or _content_rect(
            sh.content_cx, sh.content_zoom, channel.chrome, src_w, src_h)
        row = {"shot": i}
        for name, srect, pane, crop, pane_h in (
                ("facecam", rect, (0, 0, canvas_w, seam_y), geom.top, g.top_h),
                ("content", crect, (0, seam_y, canvas_w, canvas_h),
                 geom.bottom, g.bottom_h)):
            (rx0, ry0, _rx1, _ry1), rs = visible(
                srect, pane[2] - pane[0], pane[3] - pane[1])
            # cross-check that `visible` IS plan() inverted: plan's zoom is
            # relative to the fitted size, so fit*zoom must be the same scale.
            p = plan(f, srect, pane)
            row[name] = {
                "plan_scale": f.fit * p["ZoomX"],
                "visible_scale": rs,
                "d_plan": abs(f.fit * p["ZoomX"] - rs),
                "d_origin": (crop.x - rx0, crop.y - ry0),
                "d_scale": (canvas_w / crop.w / rs - 1,
                            pane_h / crop.h / rs - 1),
                "aniso": (canvas_w / crop.w) / (pane_h / crop.h) - 1,
            }
        out.append(row)
    return out


def shots_from_cuts(bounds, *, cam_cycle=None, content_cycle=None,
                    punches=()):
    """Build the shot list the way `make_clip` does, from `engine.cuts`' cycles.

    `bounds` is [(start, end)] per shot in cut seconds — `make_clip._shot_index`
    groups consecutive keeps until MIN_SHOT accumulates, and those group
    boundaries are these. `punches` is the set of shot indices that carry a
    punch.

    The cycles are READ OUT OF `engine.cuts` and `resolve_punch` rather than
    retyped, so this cannot drift from what the Resolve path renders.
    """
    if cam_cycle is None or content_cycle is None:
        from engine.cuts import content_framings, framings
        n = len(bounds)
        # the insets, recovered from the cycle by asking `framings` for the
        # rects it would produce on a unit square
        unit = framings(n, (0.0, 0.0, 1.0, 1.0))
        cam_cycle = cam_cycle or [2 * r[0] for r in unit]
        cr = content_framings(n)
        content_cycle = content_cycle or [(None, None, r) for r in cr]
    try:
        from resolve_punch import PUNCH_INSET
    except Exception:          # the punch constant is the only thing needed
        PUNCH_INSET = 0.12
    out = []
    for i, (a, b) in enumerate(bounds):
        cc = content_cycle[i % len(content_cycle)]
        rect = cc[2] if isinstance(cc, tuple) and len(cc) == 3 else None
        out.append(Shot(a, b, inset=cam_cycle[i % len(cam_cycle)],
                        punch=PUNCH_INSET if i in punches else 0.0,
                        content_rect=rect))
    return out


# ------------------------------------------------------------------ probe --
if __name__ == "__main__":
    import argparse
    import json
    import subprocess
    import sys
    from pathlib import Path

    ROOT = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(ROOT))
    import numpy as np
    from engine.clipspec import load as load_spec

    SP = ("/private/tmp/claude-501/-Users-georgegeddes-Library-Application-"
          "Support-Claude-scratch-workspaces-6d38ae6d-05dd-4827-8e46-"
          "76304910d38e-68f1a3b0-a8d1-4d98-a822-3205d41bec7a-scratch-2026-"
          "10-28-f045e2/ce92e562-40cc-4445-80fa-a3607729fc90/scratchpad/native")

    ap = argparse.ArgumentParser(description="render and MEASURE a 3s probe")
    ap.add_argument("--spec", default=str(ROOT / "clips/fns-15.json"))
    ap.add_argument("--out", default=f"{SP}/probe_layout.mp4")
    ap.add_argument("--seconds", type=float, default=3.0)
    a = ap.parse_args()

    clip, ch = load_spec(a.spec)
    srcf = clip.source(ROOT)
    cam = tuple(clip.cam or ch.cam)
    fps = ch.fps

    # three shots inside the probe, so a BOUNDARY and a PUNCH are exercised
    # rather than one static framing that would hide both.
    bnd = [(0.0, 1.2), (1.2, 2.1), (2.1, a.seconds)]
    shots = [Shot(s, e, inset=i, punch=p, content_cx=cx, content_zoom=z)
             for (s, e), i, p, (cx, z) in zip(
                 bnd, (0.0, 0.10, 0.04), (0.0, 0.0, 0.12), CONTENT_CYCLE)]

    G = panes(ch, shots, cam=cam)
    graph = two_pane(ch, shots, cam=cam)
    print(f"source      {srcf.name}")
    print(f"cam         {cam}  {cam[2]-cam[0]}x{cam[3]-cam[1]}  "
          f"aspect {(cam[2]-cam[0])/(cam[3]-cam[1]):.4f}")
    print(f"seam        {ch.seam} x {CANVAS_H} = {G.seam_exact} -> panes "
          f"{G.top_h} + {G.bottom_h} = {G.top_h+G.bottom_h}   "
          f"(seam error {G.seam_err:+.2f}px)")
    print()
    print(f"{'shot':>4} {'frames':>12} | {'facecam crop':>22} "
          f"{'dx,dy':>12} {'Sx/Sy':>15} | {'content crop':>22} {'dx,dy':>12}")
    for i, (s, sh) in enumerate(zip(G.shots, shots)):
        sx, sy = CANVAS_W / s.top.w, G.top_h / s.top.h
        print(f"{i:>4} {f'{s.first}-{s.last}':>12} | "
              f"{f'{s.top.w}x{s.top.h}@{s.top.x},{s.top.y}':>22} "
              f"{f'{s.top.dx:+.2f},{s.top.dy:+.2f}':>12} "
              f"{f'{sx:.4f}/{sy:.4f}':>15} | "
              f"{f'{s.bottom.w}x{s.bottom.h}@{s.bottom.x},{s.bottom.y}':>22} "
              f"{f'{s.bottom.dx:+.2f},{s.bottom.dy:+.2f}':>12}"
              + ("  PUNCH" if sh.punch else ""))
    print()
    # WHAT THE INTEGERS COST, against plan() itself rather than retyped
    # constants. Resolve's pane is fractional and this one is not, so the
    # error has two parts and they are reported apart.
    print("=== vs resolve_layout.plan(), which the Resolve path renders ===")
    print(f"   {'shot':>4} {'pane':>8} {'d_origin src px':>17} "
          f"{'d_scale h,v':>20} {'aniso':>9} {'|visible-plan|':>15}")
    for r in resolve_delta(ch, shots, cam=cam):
        for k in ("facecam", "content"):
            v = r[k]
            o, sc = v["d_origin"], v["d_scale"]
            org = f"{o[0]:+.2f},{o[1]:+.2f}"
            scl = f"{sc[0]:+.3%},{sc[1]:+.3%}"
            print(f"   {r['shot']:>4} {k:>8} {org:>17} {scl:>20} "
                  f"{v['aniso']:+.3%} {v['d_plan']:15.2e}")
    print("   |visible-plan| is this module's geometry against plan()'s own "
          "zoom:\n   it has to be floating-point noise or the two renderers "
          "hold two geometries.")
    print()
    print("graph:")
    for part in graph.split(";"):
        print(f"   {part}")
    print()

    nf = round(a.seconds * fps)
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(srcf),
           "-filter_complex", graph, "-map", "[v]", "-frames:v", str(nf),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
           "-pix_fmt", "yuv420p", "-fps_mode", "cfr", "-r", str(fps), a.out]
    import time
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        print("FFMPEG FAILED\n" + (r.stderr or "")[-3000:])
        raise SystemExit(1)
    print(f"rendered {nf} frames in {time.time()-t0:.1f}s -> {a.out}")

    # ---------------------------------------------------- measure the file --
    def probe(*fields):
        return subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v",
             "-count_frames", "-show_entries",
             "stream=" + ",".join(fields), "-of", "default=nw=1", a.out],
            capture_output=True, text=True).stdout.strip()

    print()
    print("=== THE ARTIFACT ===")
    print(probe("width", "height", "pix_fmt", "r_frame_rate", "nb_read_frames"))

    def plane(path, frame, w, h, cw=None, chh=None):
        """One frame's Y plane. extractplanes, NOT -pix_fmt gray: measured, the
        gray conversion applies a limited->full remap whose rounding depends on
        the frame size (MAE 15.0 against the raw plane), so two differently
        sized reads of the same pixels do not compare."""
        vf = f"select=eq(n\\,{frame}),extractplanes=y"
        raw = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", path, "-vf", vf, "-frames:v", "1",
             "-f", "rawvideo", "-pix_fmt", "gray", "-"],
            capture_output=True).stdout
        if len(raw) < w * h:
            return None
        return np.frombuffer(raw[:w * h], np.uint8).reshape(h, w).astype(float)

    def ncc(x, y):
        x = x - x.mean(); y = y - y.mean()
        d = float(np.sqrt((x @ x) * (y @ y)))
        return float(x @ y / d) if d else 0.0

    def sample(prof, n, origin, s):
        """Model an output profile of `n` px from a source profile, bilinear."""
        v = origin + (np.arange(n) + 0.5) / s - 0.5
        i0 = np.clip(np.floor(v).astype(int), 0, len(prof) - 2)
        fr = v - i0
        return prof[i0] * (1 - fr) + prof[i0 + 1] * fr

    # BEST-FIT AGAINST THE SOURCE, never a row-discontinuity detector. The
    # survey recorded a discontinuity estimator returning 807.89 on two
    # independent files — confident, reproducible and 1.5 rows wrong, because
    # the cam region's own bottom edge has a brightness gradient that differs
    # per inset. Only a fit against the source settles it.
    print()
    print("=== BEST-FIT AGAINST THE SOURCE (the fit is not told the answer) ===")
    ok = True
    for i, (s, sh) in enumerate(zip(G.shots, shots)):
        fr = (s.first + s.last) // 2
        O = plane(a.out, fr, CANVAS_W, CANVAS_H)
        S = plane(str(srcf), fr, SRC_W, SRC_H)
        if O is None or S is None:
            print(f"shot {i}: could not read frame {fr}")
            ok = False
            continue

        # --- vertical: solve (pane-top row, scale) for the FACECAM pane -----
        band = slice(0, max(40, G.top_h - 40))       # inside the pane, off the seam
        o_rows = O[band].mean(axis=1)
        s_rows = S[:, s.top.x:s.top.x + s.top.w].mean(axis=1)
        sy_pred = G.top_h / s.top.h
        best = (-2.0, 0.0, 0.0)
        for sy in np.arange(sy_pred - 0.25, sy_pred + 0.25, 0.002):
            for y0 in np.arange(s.top.y - 6, s.top.y + 6, 0.05):
                r = ncc(o_rows, sample(s_rows, band.stop - band.start, y0, sy))
                if r > best[0]:
                    best = (r, sy, y0)
        r_v, sy_fit, y0_fit = best
        seam_fit = (s.top.y + s.top.h - y0_fit) * sy_fit

        # --- horizontal: solve (source x0, scale) across the facecam pane ---
        o_cols = O[20:G.top_h - 20].mean(axis=0)
        s_cols = S[s.top.y:s.top.y + s.top.h].mean(axis=0)
        sx_pred = CANVAS_W / s.top.w
        best = (-2.0, 0.0, 0.0)
        for sx in np.arange(sx_pred - 0.25, sx_pred + 0.25, 0.002):
            for x0 in np.arange(s.top.x - 8, s.top.x + 8, 0.05):
                r = ncc(o_cols, sample(s_cols, CANVAS_W, x0, sx))
                if r > best[0]:
                    best = (r, sx, x0)
        r_h, sx_fit, x0_fit = best

        # --- the CONTENT pane: solve its own source x0, as the pan check ----
        lo, hi = G.top_h + 40, CANVAS_H - 40
        o_c2 = O[lo:hi].mean(axis=0)
        s_c2 = S[s.bottom.y:s.bottom.y + s.bottom.h].mean(axis=0)
        sxb_pred = CANVAS_W / s.bottom.w
        best = (-2.0, 0.0)
        for xb in np.arange(s.bottom.x - 14, s.bottom.x + 14, 0.1):
            r = ncc(o_c2, sample(s_c2, CANVAS_W, xb, sxb_pred))
            if r > best[0]:
                best = (r, xb)
        r_b, xb_fit = best

        d_seam = seam_fit - G.top_h
        d_sy, d_y0 = sy_fit - sy_pred, y0_fit - s.top.y
        d_sx, d_x0 = sx_fit - sx_pred, x0_fit - s.top.x
        d_xb = xb_fit - s.bottom.x
        print(f"shot {i} (frame {fr}{', PUNCH' if sh.punch else ''})")
        print(f"   facecam V: S {sy_fit:.4f} (asked {sy_pred:.4f}, {d_sy:+.4f})  "
              f"src ytop {y0_fit:7.2f} (asked {s.top.y}, {d_y0:+.2f}px)  "
              f"NCC {r_v:.5f}")
        print(f"      => pane bottom row = {seam_fit:.2f}   seam asked "
              f"{G.top_h} ({d_seam:+.2f}px), exact {G.seam_exact} "
              f"({seam_fit - G.seam_exact:+.2f}px)")
        print(f"   facecam H: S {sx_fit:.4f} (asked {sx_pred:.4f}, {d_sx:+.4f})  "
              f"src xleft {x0_fit:7.2f} (asked {s.top.x}, {d_x0:+.2f}px)  "
              f"NCC {r_h:.5f}")
        print(f"   content H: src x0 {xb_fit:7.2f} (asked {s.bottom.x}, "
              f"{d_xb:+.2f}px)  NCC {r_b:.5f}")
        if min(r_v, r_h, r_b) < 0.90:
            print("   *** a fit under 0.90 is not a measurement — investigate")
            ok = False
        if max(abs(d_seam), abs(d_y0), abs(d_x0), abs(d_xb)) > 1.0:
            print("   *** over 1px off what the graph asked for")
            ok = False

    # the shot boundary has to land on the frame the graph names, which a
    # mid-shot sample cannot show.
    print()
    print("=== THE SHOT BOUNDARIES LAND ON THE NAMED FRAME ===")
    for s in G.shots[1:]:
        a_ = plane(a.out, s.first - 1, CANVAS_W, CANVAS_H)
        b_ = plane(a.out, s.first, CANVAS_W, CANVAS_H)
        c_ = plane(a.out, s.first + 1, CANVAS_W, CANVAS_H)
        if a_ is None or b_ is None or c_ is None:
            print(f"   frame {s.first}: unreadable")
            ok = False
            continue
        across = float(np.abs(b_[:G.top_h] - a_[:G.top_h]).mean())
        within = float(np.abs(c_[:G.top_h] - b_[:G.top_h]).mean())
        print(f"   frame {s.first}: facecam change across the cut {across:6.3f}, "
              f"within the next shot {within:6.3f}  "
              f"ratio {across/within if within else float('inf'):6.1f}x")
        if across < 3 * max(within, 0.05):
            print("   *** no framing change at the boundary — the trim is wrong")
            ok = False

    print()
    print("PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)
