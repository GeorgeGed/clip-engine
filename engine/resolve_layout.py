"""Place source rectangles into canvas panes in a DaVinci Resolve timeline.

Resolve's Edit-page transform does not behave the way the Inspector implies,
and four of its conventions were measured here rather than assumed. Every one
of them cost a wrong-looking frame first.

1. **recordFrame is absolute.** A timeline starts at 01:00:00:00, which is
   216000 at 60fps. `AppendToTimeline(..., recordFrame=0)` puts the clip an
   hour before the start: `GetItemListInTrack` still lists it, but
   `GetStartFrame() == GetEndFrame()` and every render is black. Pass
   `timeline.GetStartFrame()`.

2. **Crop is in fitted-display pixels.** Not source pixels. A 1920x1080 source
   in a 1080x1920 timeline fits to 1080x607.5, and crop silently clamps there
   — set `CropLeft=1456` and it reads back `1080`. Multiply source pixels by
   the fit factor first.

3. **Zoom is relative to the fitted size and scales about the CANVAS centre**,
   not the image centre.

4. **Pan and Tilt do not share a scale.** Measured on a 1080x1920 timeline:
   Pan moves 1.000 canvas px per unit, Tilt moves 0.3164 — which is
   `fitted_h / canvas_h` — and the Tilt rate is *independent of zoom* (300
   units moved 95px at both zoom 1 and zoom 2, linear to 600). So a vertical
   move needs a conversion a horizontal one does not. Getting this wrong puts
   the panes in the right sizes and the wrong places, which looks like a sign
   error and is not.

Signs: +Pan moves right, +Tilt moves up.

Calibrate again if the canvas or source aspect changes — `python -m
engine.resolve_layout calibrate` re-measures 1 and 4 against a live timeline.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Frame:
    """The geometry of one source inside one timeline."""
    canvas_w: int
    canvas_h: int
    src_w: int
    src_h: int

    @property
    def fit(self) -> float:
        """Resolve's automatic scale-to-fit for this pairing."""
        return min(self.canvas_w / self.src_w, self.canvas_h / self.src_h)

    @property
    def fitted(self) -> tuple[float, float]:
        return self.src_w * self.fit, self.src_h * self.fit

    @property
    def pan_per_px(self) -> float:
        return self.canvas_w / self.fitted[0]

    @property
    def tilt_per_px(self) -> float:
        return self.canvas_h / self.fitted[1]


def plan(frame: Frame, src_rect: tuple[float, float, float, float],
         pane: tuple[float, float, float, float], *, fill: bool = True) -> dict:
    """Transform values that put `src_rect` into `pane`.

    `src_rect` is (x0, y0, x1, y1) in SOURCE pixels; `pane` is the destination
    (x0, y0, x1, y1) in CANVAS pixels. `fill` crops to cover the pane; False
    fits inside it and leaves gaps.

    Returns a dict ready to hand to `apply()`, in Resolve's own units.
    """
    sx0, sy0, sx1, sy1 = src_rect
    px0, py0, px1, py1 = pane
    fit = frame.fit
    fw, fh = frame.fitted

    crop = {
        "CropLeft": sx0 * fit,
        "CropRight": (frame.src_w - sx1) * fit,
        "CropTop": sy0 * fit,
        "CropBottom": (frame.src_h - sy1) * fit,
    }

    # Where the visible region sits on canvas at zoom 1, before any move.
    vx0 = (frame.canvas_w - fw) / 2 + sx0 * fit
    vx1 = (frame.canvas_w - fw) / 2 + sx1 * fit
    vy0 = (frame.canvas_h - fh) / 2 + sy0 * fit
    vy1 = (frame.canvas_h - fh) / 2 + sy1 * fit

    pick = max if fill else min
    zoom = pick((px1 - px0) / (vx1 - vx0), (py1 - py0) / (vy1 - vy0))

    # Zoom scales about the canvas centre, so the region's centre moves too.
    cx, cy = (vx0 + vx1) / 2, (vy0 + vy1) / 2
    zx = frame.canvas_w / 2 + (cx - frame.canvas_w / 2) * zoom
    zy = frame.canvas_h / 2 + (cy - frame.canvas_h / 2) * zoom

    dx = (px0 + px1) / 2 - zx
    dy = (py0 + py1) / 2 - zy
    return {
        "ZoomX": zoom, "ZoomY": zoom,
        "Pan": dx * frame.pan_per_px,
        "Tilt": -dy * frame.tilt_per_px,      # +Tilt is UP
        **crop,
    }


def apply(item, values: dict) -> dict:
    """Set a plan on a timeline item. Crop first — zoom reads the cropped box."""
    for k in ("CropLeft", "CropRight", "CropTop", "CropBottom"):
        if k in values:
            item.SetProperty(k, float(values[k]))
    for k in ("ZoomX", "ZoomY", "Pan", "Tilt"):
        if k in values:
            item.SetProperty(k, float(values[k]))
    return {k: item.GetProperty(k) for k in values}


def split_l2(frame: Frame, facecam: tuple[float, float, float, float],
             *, seam: float = 0.42,
             content: tuple[float, float, float, float] | None = None) -> dict:
    """The two-pane layout: facecam above the seam, content below.

    `seam` 0.42 is the measured house value — 0.418 and 0.4422 in the two
    reference clips, 0.44 in clip-autopilot. `content` defaults to the whole
    source; pass a rect to crop browser chrome or punch into a document.
    """
    y = seam * frame.canvas_h
    return {
        "facecam": plan(frame, facecam, (0, 0, frame.canvas_w, y)),
        "content": plan(frame, content or (0, 0, frame.src_w, frame.src_h),
                        (0, y, frame.canvas_w, frame.canvas_h)),
        "seam_px": y,
    }


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Resolve layout geometry")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show", help="print a plan without touching Resolve")
    s.add_argument("--seam", type=float, default=0.42)
    a = ap.parse_args()

    if a.cmd == "show":
        f = Frame(1080, 1920, 1920, 1080)
        print(f"fit {f.fit:.4f}  fitted {f.fitted[0]:.1f}x{f.fitted[1]:.1f}")
        print(f"pan/px {f.pan_per_px:.4f}  tilt/px {f.tilt_per_px:.4f}")
        out = split_l2(f, (1456, 818, 1920, 1080), seam=a.seam,
                       content=(0, 92, 1920, 1080))
        for pane, vals in out.items():
            if pane == "seam_px":
                print(f"seam {vals:.1f}px")
                continue
            print(f"{pane}: " + "  ".join(
                f"{k}={v:.3f}" for k, v in vals.items()))
