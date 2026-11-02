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

THE HEAD WAS BEING CHOPPED, NOT PUNCHED — and the numbers name it exactly.

George: "some of the zooms on the player cams are a bit quick and harsh
toward the start of the video."

Three separate measurements, all of them agreeing with him:

  * **SHOT 0 RUNS 0.00-8.97s, ONE CONTINUOUS SHOT**, the longest in the
    clip's first half — and BOTH head punches landed inside it, at 2.90 and
    7.00. That split one shot into five pieces (2.78 / 1.50 / 2.60 / 1.50 /
    0.58) with four cuts between them, every one of them the same framing
    jumping in, back, in and back again before a single real cut had
    happened. A punch is supposed to tighten a shot; two of them restructure
    it. Hence **one punch per base shot**, which is structural and fixes the
    in-out-in-out wherever it appears, not just here.
  * **THE JUMP WAS 97px.** At 0.18 inset (1.220x) a feature at the pane edge
    moves 97 canvas px in ONE frame. 0.12 (1.136x) moves 65 — a third less,
    and inside the 10-15% a cut punch normally runs on a talking head.
  * **1.50s IS A FLICK, NOT A SHOT.** The base shots it sat between run
    2.6-3.3s, so the punched piece was conspicuously the shortest thing on
    V2 every time. 2.20s makes it a shot.

And `skip_head` goes to 9.0, past the end of shot 0, so the opening shot is
never punched at all. The first punch now lands at 12.80s inside shot 2 —
which is fine: a device does not have to introduce itself in the first three
seconds, and the opening is where the viewer is still reading the frame.

`MIN_SEP` 4.0 -> 5.0 for the same reason the head read dense: the first two
sat at 4.10s, the floor, against 4.6-8.0s for the rest. Note all eight peaks
measured +4.1 to +4.5 dB — a 0.4 dB spread — so the threshold was not
picking BOLDER moments, it was picking the eight loudest windows of a flat
read. Five is what this docstring always claimed and eight was the drift.
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

PUNCH_INSET = 0.12        # extra crop on top of the shot's own framing: 1.136x
PUNCH_HOLD = 2.20         # how long it stays tight — a shot, not a flick
PUNCH_LEAD = 0.12         # in just before the peak, when there is no phrase
PHRASE_GAP = 0.25         # an inter-word gap at or over this starts a phrase
PHRASE_BACK = 2.20        # how far back a peak may be snapped
MIN_PIECE = 0.40          # a sliver shorter than this reads as a glitch
MIN_SEP = 5.0             # two punches closer than this are one moment
# THE FLOOR IS A FRACTION OF THE CLIP'S OWN RANGE, not an absolute dB.
#
# George, on clip 6: *"ping issues, cheaters there should be zooms because
# it's when he's loud you know what i mean?"* He is right and there WAS a
# peak there — 12.00s, **3.9946 dB over baseline** — rejected by `d < 4.0`
# while the printout rounded it to "+4.0". A knife-edge absolute threshold,
# which is the same class of bug the SELECTOR was fixed for last version and
# which was left sitting in the floor.
#
# And 4.0 was never a general number: it was read off clip 8, whose range is
# 5.5 dB over baseline. Clip 6's whole range is **4.55 dB**, so an absolute
# 4.0 keeps only the top 12% of its dynamic and throws away the moment the
# clip is named after. A speaker's emphasis is relative to their own
# delivery in that clip, so the floor is too: the top 30% of the range,
# with a small absolute minimum so a dead-flat clip still gets nothing.
#
#   clip 8  range 5.50 dB -> floor 3.85 -> 23.80 +5.5, 36.90 +4.9, 13.10 +4.5
#                                          (29.20 and 44.60 at +3.5 stay out)
#   clip 6  range 4.55 dB -> floor 3.19 -> 33.90 +4.6, 26.40 +4.1, 12.00 +4.0,
#                                          39.80 +4.0, 18.60 +3.5
MIN_DB = 2.5              # the absolute minimum, for a clip with no dynamic
DB_FRAC = 0.70            # of the clip's own peak-over-baseline range
MAX_PUNCHES = 5           # the cap
# A SMALL GUARD, NOT A STRUCTURAL ONE. This was 9.0, set to clear clip 8's
# 8.97s opening shot — but that attribution was wrong: swept across 9.0 /
# 4.0 / 2.5 / 1.0 clip 8 returns the IDENTICAL plan every time, because its
# loud moments all sit past 13s. What actually stopped its opening shot being
# chopped was MAX_PER_SHOT. 9.0 was a coincidence doing nothing, and on a
# shorter clip it would silently eat a real moment near the head.
SKIP_HEAD = 2.5           # the viewer is still arriving
MAX_PER_SHOT = 1          # a shot that goes in-out-in-out is chopped, not punched

# MEASURE THE CLEAN CUT, NEVER THE LAST DELIVERY.
#
# This read `renders/clip08_FINAL.mp4` — which `render_and_finish.py`
# OVERWRITES every version. So each run measured whatever shipped last, and
# the plan moved underneath the build: v49 and v50 hold identical speech and
# returned [10.5, 20.8, 26.2, 31.9, 39.6] and [10.5, 22.6, 28.2, 36.7].
# `_base.mov` is the tightened cut with PCM audio, no graphics and no sfx
# bed, and it does not change between versions.
SRC = "renders/styles/_base.mov"


def bold_moments(path=SRC, *, min_db=MIN_DB, min_sep=MIN_SEP,
                 skip_head=SKIP_HEAD, limit=MAX_PUNCHES, db_frac=DB_FRAC):
    """The `limit` loudest local RMS maxima at least `min_db` over baseline.

    RANKED, NOT THRESHOLDED, and that is a stability fix rather than a taste
    one. Every candidate on this clip sits +4.0 to +4.9 dB inside a 5.4 dB
    total range, so a hard cut at +4.0 is choosing between near-ties: a
    fraction of a dB — an encode difference, a changed sfx bed — flips which
    ones qualify, and because suppression ran in TIME order a single flip
    cascaded through every later pick. Taking the loudest `limit` after
    suppressing in RANK order is invariant to any global level shift, and a
    weaker peak can no longer suppress a stronger one that follows it.
    `min_db` stays as a floor so a clip with no bold moments gets none.
    """
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
    # relative to THIS speaker in THIS clip — see the DB_FRAC note above
    floor = max(min_db, db_frac * (float(rms.max()) - base))
    cand = []
    for i in range(2, len(rms) - 2):
        d = rms[i] - base
        if d < floor or times[i] < skip_head:
            continue
        if rms[i] < max(rms[i - 2:i + 3]):
            continue
        cand.append((round(float(times[i]), 2), round(float(d), 1)))
    # loudest first, each one suppressing everything within min_sep of it
    out = []
    for t, d in sorted(cand, key=lambda c: (-c[1], c[0])):
        if any(abs(t - u) < min_sep for u, _ in out):
            continue
        out.append((t, d))
        if len(out) >= limit:
            break
    return base, sorted(out)


def inset(rect, f):
    """Tighten a source rect, biased upward — the face sits above centre, the
    same bias `cuts.framings` uses, so successive insets keep tracking it."""
    x0, y0, x1, y1 = rect
    dx, dy = (x1 - x0) * f / 2, (y1 - y0) * f / 2
    return (x0 + dx, y0 + dy * 0.6, x1 - dx, y1 - dy * 1.4)


def split(segments, punches, shot_of=None, phrase_starts=None):
    """Cut each V2 segment at the punch windows that start inside it.

    Returns [(out_start_s, dur_s, src_start_s, shot_index, is_punch)].
    A punch window is clamped to its parent segment, and a leading or
    trailing remainder under MIN_PIECE is absorbed rather than left as a
    sliver.

    AT MOST `MAX_PER_SHOT` PUNCHES IN ONE BASE SHOT. Two punches inside one
    shot is not emphasis, it is the same framing cutting in, back, in and
    back — which is what read as "quick and harsh" at the head, where shot 0
    (0.00-8.97s, the longest shot in the clip's first half) was being split
    into five pieces by two of them. Where a shot holds more than one
    candidate, the LOUDEST wins; the rest are dropped rather than nudged,
    because a punch moved off its peak marks nothing.
    """
    # `shot_of` maps a segment to its SHOT. Since dead-space removal was
    # decoupled from framing, one shot spans several segments, and the
    # one-punch-per-shot rule has to count shots or it silently becomes
    # one-punch-per-splice.
    if shot_of is None:
        shot_of = list(range(len(segments)))

    def open_at(t):
        """Where the punch STARTS: the beginning of the phrase he is landing.

        **The RMS peak is mid-phrase, not its start.** Measured on clip 6:
        George asked for a zoom on "ping issues, cheaters", the phrase begins
        at output 8.78s, and the loudest 0.3s window sits at 10.10 — by which
        point he is four words past it. Opening the punch `PUNCH_LEAD` before
        the PEAK therefore opens it after the words it is meant to mark.
        So the start snaps back to the first word after a real inter-word
        gap, which is where the emphatic delivery actually begins.
        """
        if phrase_starts:
            back = [p for p in phrase_starts if t - PHRASE_BACK <= p <= t]
            if back:
                return max(back) - 0.05
        return t - PUNCH_LEAD
    used = {}
    out = []
    for idx, (o0, dur, s0) in enumerate(segments):
        o1 = o0 + dur
        shot = shot_of[idx]
        room = MAX_PER_SHOT - used.get(shot, 0)
        inside = [(t, db) for t, db in punches if o0 <= t < o1]
        inside.sort(key=lambda p: -p[1])
        marks = []
        for t, _db in inside[:max(0, room)]:
            a = max(o0, open_at(t))
            b = min(o1, a + PUNCH_HOLD)
            if b - a >= 0.5:
                marks.append((a, b))
                used[shot] = used.get(shot, 0) + 1
        marks.sort()
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

    base, moments = bold_moments(ROOT / SRC)
    print(f"baseline {base:.1f} dBFS; {len(moments)} bold moments:")
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
