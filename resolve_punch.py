#!/usr/bin/env python3
"""Punch the facecam on the bold moments, by rebuilding V2 into more shots.

George: "also need more zooms on fns' player cam in general when there's
important bold moments."

WHAT THIS CAN AND CANNOT BE. Resolve's Edit page has no keyframe API for
transforms — `SetProperty` writes one static value — so a push that MOVES
cannot come from here. What can is a CUT to a tighter framing and a cut
back, which is the ordinary talking-head punch-in. Each punch therefore
costs two picture cuts on V2 only; V1 and the audio are untouched, so
nothing is spliced and the caption timings do not move.

WHERE THEY GO. Measured, not guessed: per-window RMS against his own
baseline, the same measurement that cut 22 effects to 4 back at v6. The
whole clip spans 5.4 dB, so +3.0 dB picks eleven moments and means almost
nothing; the five here are the ones at +4.0 dB or more, thinned to 3.5s
apart. One every ~9s reads as a device rather than a tic.
"""
import json, subprocess, sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from engine.resolve_driver import connect
from engine.resolve_layout import Frame, plan, apply
from engine.cuts import framings

FPS, SEAM = 60, 0.42
CAM = (1456, 818, 1920, 1080)
CANVAS = Frame(1080, 1920, 1920, 1080)

PUNCH_INSET = 0.18        # extra crop on top of the shot's own framing: 1.22x
PUNCH_HOLD = 1.50         # how long it stays tight
PUNCH_LEAD = 0.12         # in just before the peak
MIN_PIECE = 0.40          # a sliver shorter than this reads as a glitch
MIN_SEP = 4.0             # two punches closer than this are one moment
MIN_DB = 4.0              # over his own baseline


def bold_moments(path, *, min_db=MIN_DB, min_sep=MIN_SEP, skip_head=2.5):
    """Local RMS maxima at least `min_db` over the speaker's own baseline."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", "16000",
         "-f", "f32le", "-"], capture_output=True).stdout
    a = np.frombuffer(raw, np.float32)
    sr, w, hop = 16000, int(0.30 * 16000), int(0.10 * 16000)
    rms, times = [], []
    for i in range(0, len(a) - w, hop):
        v = float(np.sqrt(np.mean(a[i:i + w] ** 2)))
        if v > 1e-5:
            rms.append(20 * np.log10(v)); times.append(i / sr)
    rms, times = np.array(rms), np.array(times)
    base = float(np.percentile(rms, 40))
    out = []
    for i in range(2, len(rms) - 2):
        d = rms[i] - base
        if d < min_db or times[i] < skip_head:
            continue
        if rms[i] < max(rms[i - 2:i + 3]):
            continue
        if out and times[i] - out[-1][0] < min_sep:
            continue
        out.append((round(float(times[i]), 2), round(d, 1)))
    return base, out


def inset(rect, f):
    """Tighten a source rect, biased upward — the face sits above centre, the
    same bias `cuts.framings` uses, so successive insets keep tracking it."""
    x0, y0, x1, y1 = rect
    dx, dy = (x1 - x0) * f / 2, (y1 - y0) * f / 2
    return (x0 + dx, y0 + dy * 0.6, x1 - dx, y1 - dy * 1.4)


def split(segments, punches):
    """Cut each V2 segment at the punch windows that start inside it.

    Returns [(out_start_s, dur_s, src_start_s, shot_index, is_punch)].
    A punch window is clamped to its parent segment, and a leading or
    trailing remainder under MIN_PIECE is absorbed rather than left as a
    sliver.
    """
    out = []
    for idx, (o0, dur, s0) in enumerate(segments):
        o1 = o0 + dur
        marks = []
        for t, _db in punches:
            a = max(o0, t - PUNCH_LEAD)
            b = min(o1, a + PUNCH_HOLD)
            if b - a >= 0.5 and o0 <= t < o1:
                marks.append((a, b))
        if not marks:
            out.append((o0, dur, s0, idx, False)); continue
        cur = o0
        for a, b in marks:
            if a - cur < MIN_PIECE:
                a = cur                       # absorb the sliver before it
            if o1 - b < MIN_PIECE:
                b = o1                        # and the one after
            if a > cur:
                out.append((cur, a - cur, s0 + (cur - o0), idx, False))
            out.append((a, b - a, s0 + (a - o0), idx, True))
            cur = b
        if o1 - cur > 1e-6:
            out.append((cur, o1 - cur, s0 + (cur - o0), idx, False))
    return out


def main():
    r = connect(); r.OpenPage("edit")
    p = r.GetProjectManager().GetCurrentProject()
    tl = p.GetCurrentTimeline(); mp = p.GetMediaPool()
    start = tl.GetStartFrame()
    total = tl.GetEndFrame() - start
    print(f"timeline {tl.GetName()}  {total} frames ({total / FPS:.2f}s)")

    # The base shots come off **V1**, not V2. Reading them off V2 looked
    # equivalent and is not: a second run would then read the already-split
    # 23 pieces as its base shots, hand them `framings(23, ...)` and punch
    # the punches. V1 carries the same keeps with the audio and is never
    # touched here, so it is the stable description of the cut.
    v1 = sorted(tl.GetItemListInTrack("video", 1) or [], key=lambda i: i.GetStart())
    v2 = sorted(tl.GetItemListInTrack("video", 2) or [], key=lambda i: i.GetStart())
    item = v1[0].GetMediaPoolItem()
    segs = [((it.GetStart() - start) / FPS,
             (it.GetEnd() - it.GetStart()) / FPS,
             it.GetLeftOffset() / FPS) for it in v1]
    print(f"cut has {len(segs)} shots, "
          f"{sum(d for _o, d, _s in segs):.2f}s total (V2 currently {len(v2)})")

    render = ROOT / "renders/clip08_FINAL.mp4"
    base, moments = bold_moments(render)
    print(f"baseline {base:.1f} dBFS; {len(moments)} bold moments at +{MIN_DB} dB:")
    for t, d in moments:
        print(f"   {t:6.2f}s  +{d} dB")

    pieces = split(segs, moments)
    n_punch = sum(1 for *_x, isp in pieces if isp)
    print(f"V2 {len(segs)} shots -> {len(pieces)} ({n_punch} punched)")

    tl.DeleteClips(v2)
    rects = framings(len(segs), CAM)
    entries = [{"mediaPoolItem": item,
                "startFrame": round(s0 * FPS),
                "endFrame": round(s0 * FPS) + round(d * FPS),
                "recordFrame": start + round(o0 * FPS),
                "trackIndex": 2, "mediaType": 1}
               for o0, d, s0, _i, _p in pieces]
    placed = mp.AppendToTimeline(entries)
    print(f"appended {len(placed or [])} of {len(entries)} to V2")

    seam_y = SEAM * CANVAS.canvas_h
    items = sorted(tl.GetItemListInTrack("video", 2) or [], key=lambda i: i.GetStart())
    for it, (o0, d, _s, idx, isp) in zip(items, pieces):
        rect = rects[idx]
        if isp:
            rect = inset(rect, PUNCH_INSET)
        apply(it, plan(CANVAS, rect, (0, 0, 1080, seam_y)))
    zoom = 1 / (1 - PUNCH_INSET)
    print(f"framed {len(items)} shots; punches at {zoom:.2f}x")
    json.dump({"punches": [t for t, _d in moments], "zoom": round(zoom, 3)},
              open(ROOT / "jobs/fns-2905408276/punches.json", "w"), indent=1)


if __name__ == "__main__":
    main()
