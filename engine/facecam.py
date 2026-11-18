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


# THE TIGHT FACE CROP, as a ratio of the detected face height. Measured off
# clip 08's hand-set rect (1559, 838, 1821, 1024) around a 67px face centred
# at (1695, 940): the crop is 3.9 faces wide, 2.78 tall, and sits 0.13 faces
# above the face centre so there is headroom rather than chin room.
FACE_W, FACE_H, FACE_LIFT = 3.9, 2.78, 0.13
FACE_SAMPLES = 40
FACE_MIN_HIT = 0.3
FACE_STILL = 0.10
FACE_WILD = 1.0


def _border(profile, lo, hi):
    """The strongest straight edge in profile[lo:hi], or None if nothing there
    stands out — an overlay's border is a hard line the full width of the
    crop, a room is not."""
    lo, hi = max(int(lo), 0), min(int(hi), len(profile))
    if hi - lo < 3:
        return None
    seg = profile[lo:hi]
    k = int(np.argmax(seg))
    # Measured: overlay borders 93-159 grey levels per pixel of edge, the
    # strongest thing in the room (a shelf, a mic arm) 25.
    if seg[k] < 50:
        return None
    return lo + k


def _live_face(hits, samples):
    """The hits of the one cluster that is a live face, or None.

    A LIVE FACE MOVES; A POSTER DOES NOT. On clip 08 the haar cascade
    fires on two objects in his room in 40 of 40 frames, more often than
    on his face (29 of 40), so the busiest cluster is a wall. Their
    positions are identical to the pixel across the clip; a face drifts.

    STILLNESS IS RELATIVE TO THE FACE'S SIZE. A fixed 2px floor shipped a
    crop of a plush toy on clip 9 of the first live run (VOD 2926995155,
    2:05:03): the cascade's box on it wobbles 1.9-2.0px from re-encode
    noise alone, so it scraped past while his face drifted 10px. Measured
    as a share of face height, objects in his room drift 0.016-0.026 and
    his face 0.135-0.24, so 0.06 sits between them with room either side.

    0.06 WAS NOT ENOUGH. On clip 1 of job 3njkcnn5wd (VOD 2885323336, 0:04:15)
    a shelf toy drifted 0.079 with 41 hits against his face's 0.136 with 40,
    so the toy won by one hit and the whole clip showed his shelf. Hence
    0.10, and ties go to the bigger face (toy 67px, face 77px). Players on a
    watchparty broadcast drift 2.5-2.9 face heights, so anything over
    FACE_WILD is the stream content, not the webcam.
    """
    a = np.array(hits) if len(hits) else np.zeros((0, 3))
    best = None
    for p in a:
        near = a[(abs(a[:, 0] - p[0]) < p[2]) & (abs(a[:, 1] - p[1]) < p[2])]
        if len(near) < samples * FACE_MIN_HIT:
            continue
        h = np.median(near[:, 2])
        drift = near[:, 0].std() + near[:, 1].std()
        if not FACE_STILL * h <= drift <= FACE_WILD * h:
            continue
        if best is None or len(near) * h > len(best) * np.median(best[:, 2]):
            best = near
    return best


def face_rect(path, *, samples=FACE_SAMPLES) -> tuple[int, int, int, int] | None:
    """The house facecam crop, found by a FACE DETECTOR rather than motion.

    `detect` reads motion, and a page that plays video moves too: on FNS VOD
    2926995155 the gameplay in his browser out-moved the webcam and the
    detector returned the whole frame. A face does not have that problem.

    THE CROP STAYS INSIDE THE WEBCAM OVERLAY. Sized off the face alone, the
    crop on clip 2 of that VOD reached 13px above the overlay and put a strip
    of roster board across the top of the pane. The overlay's top and left
    borders are hard lines that never move, so they show up in the MEDIAN of
    the sampled frames while the room and the person blur out; the crop is
    pulled inside them and narrowed to keep its aspect.
    """
    import cv2                                           # noqa: PLC0415
    casc = cv2.CascadeClassifier(cv2.data.haarcascades
                                 + "haarcascade_frontalface_default.xml")
    cap = cv2.VideoCapture(str(path))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080
    hits, grays = [], []
    for i in np.linspace(n * 0.05, n * 0.95, samples).astype(int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, fr = cap.read()
        if not ok:
            continue
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        if len(grays) < 15:
            grays.append(g)
        fs = casc.detectMultiScale(g, 1.1, 6, minSize=(40, 40))
        hits += [(x + w / 2, y + h / 2, h) for x, y, w, h in fs]
    cap.release()
    best = _live_face(hits, samples)
    if best is None:
        return None
    cx, cy, fh = np.median(best, axis=0)
    # Wider than the top pane (1080x768 = 1.406), or the native renderer's
    # axis guard refuses it: the overflow has to be horizontal.
    aspect = 1.42
    bh = FACE_H * fh
    bw = max(FACE_W * fh, bh * aspect)
    x0 = min(max(cx - bw / 2, 0), W - bw)
    y0 = min(max(cy - FACE_LIFT * fh - bh / 2, 0), H - bh)
    med = np.median(np.stack(grays), axis=0).astype(np.float32)
    gy = np.abs(np.diff(med, axis=0))
    gx = np.abs(np.diff(med, axis=1))
    top = _border(gy[:, int(x0):int(x0 + bw)].mean(axis=1), y0 - 60, cy - 0.9 * fh)
    left = _border(gx[int(y0):int(y0 + bh), :].mean(axis=0), x0 - 60, cx - 1.2 * fh)
    ymin = top + 2 if top is not None else 0
    xmin = left + 2 if left is not None else 0
    if y0 < ymin:
        y0 = ymin
        bh = min(bh, H - y0)
        bw = bh * aspect
    if x0 < xmin:
        x0 = xmin
    if x0 + bw > W:
        bw = W - x0
        bh = bw / aspect
    x0 = min(max(cx - bw / 2, xmin), W - bw)
    y0 = min(max(cy - FACE_LIFT * fh - bh / 2, ymin), H - bh)
    return (int(round(x0)), int(round(y0)), int(x0 + bw), int(y0 + bh))
