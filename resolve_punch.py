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
MIN_WINDOW = 0.50         # shorter than this is a flick, not a punch
PUNCH_BACKOFF = 0.45      # how early a punch may open to find room
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
# 0.70 WAS DOING THE ANCHOR FILTER'S JOB, BADLY, AND STACKING WITH IT.
# With `anchors` in play the dB floor is no longer what stops a moment being
# arbitrary — the emphasised card is. Keeping both at full strength is two
# gates on one decision, and on clip 12 it left exactly ONE punch: the floor
# at 0.70 x 4.28 = 3.00 dB admitted only three candidate peaks and the anchor
# filter then dropped two of them.
#
# Swept with anchors on, the plan is IDENTICAL at 0.55, 0.45, 0.35 and 0.25
# on both clips — a plateau, where the old absolute threshold was a knife
# edge that a fraction of a dB flipped. 0.55 is the top of that plateau, so
# it is the most conservative value that still behaves, and the exact number
# does not matter, which is the point.
#
#   clip 12  -> 3.54 (+2.7), 13.02 (+4.3), 28.73 (+2.7)
#   clip 6   -> 9.30 (+3.5) = "CHEATERS", 26.64 (+4.4), 34.80 (+3.7)
DB_FRAC = 0.55            # of the clip's own peak-over-baseline range
# TWO. George has now rejected the THIRD boom twice, on two different
# moments — "you HAVE the freedom to choose your own teammates" and then
# "you don't get paid FOR a couple months" — and the second time with
# *"third boom is pointless - remove from logic and video"*. Two rejections
# of two different picks is not a selection problem, it is a COUNT problem:
# a 45s clip carries two of these and the third is padding whatever it
# lands on.
#
# Recorded as what it is — an editorial constant from repeated review, not a
# measurement — and it is a CAP, so a clip with only one qualifying moment
# still gets one. Worth revisiting for a clip much longer than this one,
# where one boom every ~22s would allow a third.
MAX_PUNCHES = 2           # the ceiling; see the note above and `boom_budget`

# ONE BOOM PER ~22 SECONDS, because the count is the only lever that has ever
# survived review.
#
# George has now rejected a boom on two clips, and both times the word was
# *"pointless"* — about the boom EXISTING, not about where it sat:
#
#   clip 12, 45.2s, 3 booms -> "third boom is pointless"          -> 2
#   clip 16, 30.8s, 2 booms -> "first boom is basically pointless" -> 1
#
# AND NO ACOUSTIC METRIC SEPARATES WHAT HE KEEPS FROM WHAT HE DROPS. Measured
# against his six verdicts (clip 16 4.84 no / 21.92 yes, clip 12 2.87 yes /
# 12.87 yes / 27.25 no, clip 6 9.30 yes, which he named himself):
#
#   level over baseline  clip 16's REJECTED moment is the LOUDEST candidate
#                        in the clip, +3.96 against the accepted +3.83
#   rise over 1.2s       worse — clip 16's two rejected candidates have the
#                        two HIGHEST rises in the clip, +5.82 and +6.10
#   sustain              swept 50 parameterisations (window 0.15-0.40s, hop
#                        0.02-0.10s, fixed thresholds 1.5-3.0 dB and adaptive
#                        ones at 0.6-1.0x this clip's own floor, both
#                        "containing run" and "walk out from the peak").
#                        ZERO separate all six: clip 12's accepted 2.87 sits
#                        at the floor under nearly every setting
#   position in clip     accepted span 6-76%, rejected 15% and 63%
#   clause-finality      rejected are 0 and 12 words from their utterance
#                        end, accepted are 0, 5, 13 and 20 — and whisper's
#                        VAD merges utterances into 20-word blocks here
#   claim vs consequence backwards: clip 12's REJECTED "couple months" is in
#                        BOTH fields, the accepted ones in the claim only
#
# A first pass reported sustain separating all six and it was an artifact of
# one parameter choice. **That is why the sweep is in this comment and not
# just the conclusion.**
#
# So the budget scales with duration and the PICK among near-ties is not
# decidable from the audio — `Clip.booms` carries a watched human's call, the
# same arrangement `chat_mode` has for a gate whose default was wrong once.
#
# BOOM_EVERY is bracketed on both sides rather than chosen: round(d/E) must
# give 1 at 30.96s (E > 20.6) and 2 at 38.3s (E <= 25.5).
BOOM_EVERY = 22.0
KEEP_SNAP = 0.60       # how far a spec's boom may be from a measured candidate


def boom_budget(duration: float, *, limit: int = MAX_PUNCHES) -> int:
    """How many booms a clip of this length carries. At least one, at most
    `limit` — a clip with one qualifying moment still gets it."""
    return max(1, min(limit, round(duration / BOOM_EVERY)))
# ANCHOR A MOMENT TO WHAT THE CLIP ITSELF CALLS ITS POINT.
#
# George, on clip 12: *"the boom effect was too late the first time and the
# second one was also a bit too late - it's random, but we need to add some
# kind of logic to it."* Both halves of that are measurable, and they have
# the SAME cause.
#
# "TOO LATE" IS THE 0.30s WINDOW. An RMS window is a smoother, so its maximum
# sits after the stressed syllable that caused it — measured against the word
# the moment is named for: clip 6's peak is **695 ms** after "CHEATERS", clip
# 12's three were 280 / 1170 / 695 ms after their own anchors. On clip 6 the
# phrase snap rescued this, because whisper gave it an utterance boundary to
# snap to. On clip 12 it did not: two of the three punches landed at exactly
# `peak - PUNCH_LEAD`, i.e. the snap found nothing, because whisper's VAD had
# merged the utterances (this file already records the median inter-word gap
# on this VOD as 0.000s). So the snap is sound and it was starved of targets.
#
# "RANDOM" IS THE SAME STARVATION. Measured on clip 12, the three delivered
# moments changed the level by **+1.5, +0.3 and -0.2 dB** against the two
# seconds before them — the last one is QUIETER than what preceded it. In a
# clip whose entire range is 3.9 dB the loudest windows are near-ties, and
# ranking near-ties is indistinguishable from choosing at random.
#
# WHAT WORKS IS THE EMPHASISED CAPTION CARD. Those come from
# `emphasis_keys(claim, consequence)` — the clip's own thesis, written by the
# model that selected it — and this file already records that they "marked
# the right ones". They are also VISIBLE: the card is drawn in accent colour
# at that instant, which satisfies the standing rule that a sound must mark
# something the viewer can see, not a vocal peak.
#
# So a candidate peak is walked back to its onset, and must find an
# emphasised card in [onset - ANCHOR_BACK, onset + ANCHOR_FWD]. If it finds
# none it marks nothing and is DROPPED — a clip with no qualifying moment
# gets no punches, which is the honest answer for a flat read.
#
# Checked against the regression that killed two simpler rules: per-word rise
# ranks clip 6's "cheaters" 6th among content words (+2.02) and a
# pause-then-hit score ranks it 31st of 138. This rule HITS it.
ANCHOR_BACK = 1.10        # how far behind the onset a card may sit
ANCHOR_FWD = 0.30         # and how far ahead
# AND THE CARD'S START IS NOT THE ATTACK EITHER.
#
# George, one round later: *"second boom was slightly too late same with the
# third one - tighten."* The card anchored the moment to the right PHRASE and
# it still fired late inside it, because a card begins on whichever word
# whisper grouped first — often a function word — and that start is a
# contiguous guess placed inside the join, not an onset. Measured on clip 12,
# **12 of the 16 emphasised cards sit LATE of their own speech run's onset,
# median +59 ms**; the two he flagged were the card "THE FREEDOM" at +220 ms,
# where the boom landed on "the" rather than on the stressed "have", and a
# card whose stressed syllable ("that's IT") was 240 ms earlier.
#
# So the anchor is refined once more: take the loudest 40 ms in
# [t - STRESS_BACK, t + 0.10] — the stressed syllable — and then its ATTACK,
# walking back to 6 dB under that syllable's own peak. That is where a
# listener puts the beat.
#
# STRESS_BACK IS BRACKETED ON BOTH SIDES BY MEASUREMENT, which is why it is
# 0.22 and not a round number:
#   0.30 drags clip 6's second punch 305 ms back onto "which", a function
#        word in the middle of the PREVIOUS phrase;
#   0.18 leaves clip 12's second boom where it was (+15 ms), i.e. it does
#        not answer the note at all;
#   0.22 moves clip 12 onto "hear" / "it" / "have" (-180 / -240 / -185 ms)
#        and leaves clip 6's "ping issues cheaters" punch alone at -35 ms.
STRESS_BACK = 0.22
STRESS_DROP = 6.0         # dB under the syllable's peak that counts as its attack
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


def _attack(env_db, hop, t, back=STRESS_BACK, fwd=0.10, drop=STRESS_DROP):
    """The attack of the stressed syllable nearest `t`. See STRESS_BACK."""
    lo = max(0, int((t - back) / hop))
    hi = min(len(env_db) - 1, int((t + fwd) / hop))
    if hi <= lo:
        return t
    j = lo + int(max(range(hi - lo + 1), key=lambda k: env_db[lo + k]))
    peak = env_db[j]
    k = j
    while k > 0 and env_db[k] > peak - drop and (j - k) * hop < 0.14:
        k -= 1
    return round((k + 1) * hop, 3)


def _onset(rms, times, i, base, d, max_back=1.20):
    """Walk back from a 0.30s-window maximum to where the rise began.

    The window is a smoother; its peak is not the attack. Halfway between the
    baseline and the peak is the crossing that corresponds to the syllable.
    """
    tgt = base + d * 0.5
    j = i
    while j > 0 and rms[j] > tgt and times[i] - times[j] < max_back:
        j -= 1
    return float(times[j])


def bold_moments(path=SRC, *, min_db=MIN_DB, min_sep=MIN_SEP,
                 skip_head=SKIP_HEAD, limit=MAX_PUNCHES, db_frac=DB_FRAC,
                 anchors=None, keep=None, words=None, on_gate=None):
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
    fh, fw = int(0.005 * sr), int(0.040 * sr)      # for the attack refinement
    fine = 20 * np.log10(np.maximum(np.array(
        [float(np.sqrt(np.mean(a[i:i + fw] ** 2)))
         for i in range(0, max(1, len(a) - fw), fh)]), 1e-9))
    # relative to THIS speaker in THIS clip — see the DB_FRAC note above
    floor = max(min_db, db_frac * (float(rms.max()) - base))
    cand = []
    for i in range(2, len(rms) - 2):
        d = rms[i] - base
        if d < floor or times[i] < skip_head:
            continue
        if rms[i] < max(rms[i - 2:i + 3]):
            continue
        t = round(float(times[i]), 2)
        if anchors:
            # ANCHOR OR DROP. See the ANCHOR_BACK note: the window's maximum
            # is not the moment, and a moment with no emphasised card beside
            # it is not one of the clip's points.
            on = _onset(rms, times, i, base, d)
            # THE WINDOW SPANS ONSET TO PEAK, not onset +- a margin. A card
            # may sit anywhere inside the rise it belongs to, and measuring
            # the margin only from the ONSET threw away cards sitting near
            # the PEAK: clip 12's opening moment has its card at 2.865, which
            # is 0.065s after its own peak at 2.80 and so obviously correct,
            # but 0.665s ahead of the walked-back onset at 2.20 — outside
            # ANCHOR_FWD, and the moment George had accepted vanished.
            near = [a for a in anchors
                    if on - ANCHOR_BACK <= a <= float(times[i]) + ANCHOR_FWD]
            if not near:
                continue
            card = min(near, key=lambda c: abs(c - on))
            # NEVER WALK BACK OFF THE CARD. The attack refinement was added
            # when the cue's LEAD was wrong (108 ms on a sound whose weight
            # sits at 508), and it was compensating for that by dragging the
            # moment earlier. With `perceptual_lead` corrected to the energy
            # centroid the compensation became an over-correction, and it
            # lands on whatever syllable is loudest rather than on the card's
            # own word: clip 16's first boom went to **"had"** — an auxiliary
            # verb that happens to be the loudest thing in its phrase at
            # -19.3 dB — while the card sat 85 ms later on "prior", and
            # George called it early. Its second boom was already at a card
            # start ("end up making runs") and he called that one fine.
            #
            # So the attack may still refine FORWARD off a late whisper
            # boundary, and may never precede the card. Two corrections for
            # one symptom, which is the stacked compensation this file keeps
            # deleting.
            t = round(max(card, _attack(fine, 0.005, card)), 2)
            if t < skip_head:
                continue
        cand.append((t, round(float(d), 1)))
    if words:
        # THE NUCLEUS GATE. A boom does not go on the clause a connective is
        # about to overrule — see `engine/nucleus`. A filter, so it runs
        # before the ranking, and a gated candidate is DROPPED rather than
        # nudged. Its only failure mode is one boom fewer, which is the
        # direction George's two complaints have both pointed.
        from engine import nucleus                        # noqa: PLC0415
        wt = [w[0] for w in words]
        wx = [w[1] for w in words]
        live = []
        for t, d in cand:
            why = nucleus.gate(t, wt, wx)
            if why and on_gate:
                on_gate(t, d, why)
            if not why:
                live.append((t, d))
        cand = live
    if keep:
        # A WATCHED HUMAN'S CALL, snapped to the measured candidates so the
        # moment keeps its own attack refinement and its dB. A time with no
        # candidate near it is taken literally and reported as such, because
        # silently moving it would be the same defect as silently dropping it.
        out = []
        for want in keep:
            near = [c for c in cand if abs(c[0] - want) <= KEEP_SNAP]
            out.append(min(near, key=lambda c: abs(c[0] - want))
                       if near else (round(float(want), 2), None))
        return base, sorted(out)
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
            # A MOMENT NEAR THE END OF ITS SEGMENT HAS NO ROOM, AND USED TO
            # VANISH WITHOUT SAYING SO. Clip 12's middle moment sits at 12.78
            # with its segment ending at 12.96, so the window was 0.23s, fell
            # under the 0.5s minimum and was skipped — the plan printed three
            # punches and the build delivered two, and the sfx bed followed
            # the build, so George got two booms where the log said three.
            # A plan that prints what it cannot build is the same defect as a
            # gate that measures nothing. So the punch OPENS EARLIER to fit,
            # bounded by its segment and by PUNCH_BACKOFF from the moment,
            # and the boom stays on the moment rather than on the piece — a
            # zoom already in when the word lands is the normal shape anyway.
            if b - a < MIN_WINDOW:
                a = max(o0, min(a, o1 - MIN_WINDOW), t - PUNCH_BACKOFF)
                b = min(o1, a + PUNCH_HOLD)
            if b - a >= MIN_WINDOW:
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
