"""Find the facecam in a stream frame, per clip, by MOTION.

**THE FACECAM RECT IS NOT A CHANNEL CONSTANT.** That assumption shipped a
broken second clip and is the most useful thing the generalisation pass
found. Clip 8 (VOD 1:39:38) has FNS bottom-right at (1456, 818, 1920, 1080);
clip 6 (VOD 0:36:34), the same streamer on the same stream, has him at
roughly (1630, 340, 1920, 620) — smaller and higher. Reusing clip 8's rect
rendered clip 6's top pane as a corner of a browser sidebar with no face in
it. A streamer moves their own layout between scenes, so this is measured
per clip or it is wrong.

**MOTION, NOT A FACE MODEL.** A webcam feed is the only part of this frame
that changes continuously: the rest is a browser page that is pixel-static
for most of its length (measured on clip 8, the content region's
frame-to-frame delta is median 0.0005 with zero frames above 0.5 across all
2822). So the facecam is the region that moves, and that needs no face
detector, no model download and no per-game tuning. It also finds the right
thing when the streamer is turned away, which a face detector does not.

**ADJACENT FRAMES, IN SHORT BURSTS — NOT VARIANCE ACROSS THE CLIP.** The
first version sampled 24 frames spread over the whole clip and took their
per-pixel standard deviation, which measures "did this change over a
minute". That is the wrong question and it answered it wrongly: on clip 8
the PAGE scored a higher median (5.52) than the facecam (3.99), because he
switches document once and a one-off change of the whole page dwarfs a
webcam. Consecutive frames separate them completely — a webcam differs
every frame, a static page differs by nothing at all.

What it cannot do, stated so it is not trusted too far: if the page itself
plays video — a VOD review, a watch party, an embedded clip — that region
moves too and may win. `detect` returns its confidence as the margin
between the chosen region and the next-best column run, and `main` prints
it, so a low margin is the signal to look at the frame yourself.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass

import numpy as np

BURSTS = 10           # places in the clip to look
RUN = 5               # consecutive frames at each, for adjacent-frame deltas
SCALE = 240           # analysis width; the rect is scaled back up
ASPECT = 16 / 9


@dataclass
class Facecam:
    rect: tuple[int, int, int, int]       # x0, y0, x1, y1 in SOURCE pixels
    coverage: float                       # share of frame area
    margin: float                         # motion inside / motion outside
    motion: float                         # mean temporal sd inside it


def _motion(path, bursts=BURSTS, run=RUN, width=SCALE):
    """Mean |frame[i+1] - frame[i]| per pixel, over short bursts."""
    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout)
    h = int(round(width * 9 / 16))
    acc, n = np.zeros((h, width), np.float32), 0
    for i in range(bursts):
        t = dur * (i + 0.5) / bursts
        raw = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(path),
             "-frames:v", str(run), "-vf", f"scale={width}:{h}",
             "-pix_fmt", "gray", "-f", "rawvideo", "-"],
            capture_output=True).stdout
        k = len(raw) // (width * h)
        if k < 2:
            continue
        fr = np.frombuffer(raw[:k * width * h], np.uint8).reshape(k, h, width)
        acc += np.abs(np.diff(fr.astype(np.float32), axis=0)).mean(0)
        n += 1
    return (acc / max(n, 1)), n, dur


def _run_containing_max(profile, thr):
    """The contiguous run over `thr` that contains the profile's maximum."""
    peak = int(np.argmax(profile))
    if profile[peak] < thr:
        return None
    a = peak
    while a > 0 and profile[a - 1] >= thr:
        a -= 1
    b = peak
    while b < len(profile) - 1 and profile[b + 1] >= thr:
        b += 1
    return a, b


def detect(path, *, bursts=BURSTS, aspect=ASPECT) -> Facecam | None:
    sd, n, _dur = _motion(path, bursts)
    if n < 3:
        return None
    h, w = sd.shape
    # A static browser page differs by ~0 between consecutive frames, so the
    # floor is LOW AND ABSOLUTE. Measured on clip 8 at this analysis scale:
    # inside the facecam the adjacent-frame delta runs median 0.125, outside
    # it median 0.000 with a 99th percentile of 0.050. At 0.15 the cam is
    # 46.3% lit and the page 0.1%. A high threshold (the first attempt used
    # 0.8) finds only the streamer's FACE, because the room behind him is
    # as still as the page — which is how clip 8 came back as a 128x72 box
    # on his hands.
    thr = max(float(np.percentile(sd, 99)) * 0.05, 0.12)
    mask = sd >= thr
    if mask.sum() < 0.002 * h * w:
        return None
    cols, rows = mask.sum(0).astype(float), mask.sum(1).astype(float)
    # 12% of the peak, not 25%: a webcam's quiet edges (a shoulder, a
    # static wall) still belong to the cam rect.
    cx = _run_containing_max(cols, max(cols.max() * 0.12, 1))
    cy = _run_containing_max(rows, max(rows.max() * 0.12, 1))
    if not cx or not cy:
        return None
    x0, x1 = cx
    y0, y1 = cy
    inside = sd[y0:y1 + 1, x0:x1 + 1]
    # CONFIDENCE = how many times more the chosen region moves than the rest
    # of the frame. On a browser page the rest is ~0, so this runs very high;
    # a page PLAYING VIDEO (a watch party, a VOD review) moves too and drags
    # it toward 1, which is the signal to look at the frame yourself.
    out = sd.copy()
    out[y0:y1 + 1, x0:x1 + 1] = np.nan
    outside = float(np.nanmean(out))
    margin = float(inside.mean() / max(outside, 1e-6))

    sx = 1920 / w
    sy = 1080 / h
    fx0, fy0 = x0 * sx, y0 * sy
    fx1, fy1 = (x1 + 1) * sx, (y1 + 1) * sy
    # Snap to the pane's aspect about the detected centre, growing the short
    # side, then clamp into frame. The L2 top pane is 16:9, and a rect far
    # off that aspect gets cropped by `fill` — which is how a card once lost
    # 313px top and bottom.
    cxm, cym = (fx0 + fx1) / 2, (fy0 + fy1) / 2
    bw, bh = fx1 - fx0, fy1 - fy0
    if bw / bh < aspect:
        bw = bh * aspect
    else:
        bh = bw / aspect
    fx0, fx1 = cxm - bw / 2, cxm + bw / 2
    fy0, fy1 = cym - bh / 2, cym + bh / 2
    if fx0 < 0: fx1, fx0 = fx1 - fx0, 0
    if fy0 < 0: fy1, fy0 = fy1 - fy0, 0
    if fx1 > 1920: fx0, fx1 = fx0 - (fx1 - 1920), 1920
    if fy1 > 1080: fy0, fy1 = fy0 - (fy1 - 1080), 1080
    rect = (int(max(0, fx0)), int(max(0, fy0)),
            int(min(1920, fx1)), int(min(1080, fy1)))
    area = (rect[2] - rect[0]) * (rect[3] - rect[1]) / (1920 * 1080)
    return Facecam(rect, round(area, 4), round(margin, 3),
                   round(float(inside.mean()), 2))


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        f = detect(p)
        print(f"{p.split('/')[-1][:34]:36s} {f}")
