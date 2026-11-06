#!/usr/bin/env python3
"""Build a clip from a spec. One script, any clip, any channel.

George: *"let's finalize this logic now. Lock it in. And let's develop this
into other clips ... I want to mass produce these clips for different
channels. So figure out how you can kind of do that from here."*

**WHAT WAS IN THE WAY.** Clip 8's pipeline was eight top-level scripts with
its constants at the top of each — the VOD id in four of them, the facecam
rect in two, the in-point in two, the duration typed into Root.tsx. Every
one of those is a value that differs per clip or per channel, sitting in
code. `engine/clipspec.py` splits them into a `Channel` (measured once per
streamer) and a `Clip` (mostly derived), and this runs the pipeline off
them. The house style — captions, exits, punch geometry, sound, palette —
stays in code, because it is the same on every clip by definition.

    ./.venv/bin/python make_clip.py clips/fns-07.json
    ./.venv/bin/python make_clip.py clips/fns-07.json --only chat,punch

STAGES, in order, each skippable:

  cut       tighten the dead air, build V1/V2 in Resolve with per-shot
            framings and the channel's grade
  captions  word cards -> one alpha movie (the PIL track, which is what
            ships; the Fusion path is slower and is not delivered)
  chat      fetch the VOD chat, CLASSIFY IT, build the windows, render
  assemble  cap/sfx/chat/hook/cards onto V3-V6
  punch     split V2 on the measured bold moments
  render    render, EQ, two-pass loudnorm, QC

THE CHAT STAGE IS THE ONE THAT THINKS. Everything else is clip 8's logic
with its constants pulled out. `engine/chat_reaction` decides whether this
clip's chat is a steady background (so the box is the pane's resting state,
as in clip 8) or a crowd reacting in bursts (so the box comes up ON the
reactions). That is George's gameplay case — "after the streamer has like
got a 3K ... then we can see the Twitch chat's reaction" — without needing
a killfeed detector, because the burst IS the signal.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import dataclasses
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from engine import qc                                            # noqa: E402
from engine.clipspec import load                                 # noqa: E402
from engine import facecam                                       # noqa: E402
from engine.resolve_driver import connect                        # noqa: E402
from engine.resolve_layout import Frame, plan, apply             # noqa: E402
from engine.resolve_captions import cards, emphasis_keys, mark_emphasis  # noqa: E402
from engine.cuts import framings, content_framings               # noqa: E402
from engine.tighten import removals, keeps, remap_card, joins    # noqa: E402
from engine import captions_video, twitch_chat                   # noqa: E402
from engine import chat_reaction as cr                           # noqa: E402
from engine.sfx import Cue, bed, cue_gain, cue_gain_peak, perceptual_lead                   # noqa: E402

VENDOR = ROOT / "vendor/remotion-clip08"
PUBLIC = VENDOR / "public"
CHROME_APP = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# HOUSE STYLE — the same on every clip, which is why it is here and not in a
# spec. Each number is justified in AGENTS.md next to the measurement that
# produced it; they are repeated here only so one file can be read top to
# bottom.
# CUT ALL THE DEAD SPACE. George, twice: *"ensure there is NO dead space"*,
# then on clip 6: *"remember i said cut ALL dead space too"*. Measured on the
# delivered files at a 0.20s floor, clip 6 was **21.6% quiet** and clip 8
# **14.3%** — the 0.35/0.12 pair left a fifth of the clip as pauses.
MIN_DEAD = 0.20          # every pause at or over this goes
BEAT = 0.08              # what is LEFT of each one; 0 makes words collide
CAPTION_ACCENT = (92, 128, 255, 255)      # theme.tsx C.blueLight
MASTER_GAIN = 6.2        # what loudnorm adds; cues are solved through it
BAIT_SECONDS = 17.0      # the hook holds the stretch where a scroller decides
# THE BOOM IS AN EVENT CUE, SO IT SITS AT THE SHUTTER'S LEVEL, NOT THE
# THUNK'S — and both numbers here are measured in the master, because the
# prediction was wrong by 1.8 dB.
#
# -26 dBFS RMS put its peak at -18.3 in the master, quieter than every cue
# this project has accepted. -21.0 was then chosen on the arithmetic as
# "near -12.8" and MEASURED at -14.57 — the thunk's level. That is the wrong
# tier: a thunk means "a fact arrived" and rides under the speech, while
# this is a punchline on the clip's loudest moment, which is where the
# shutter (-10.4, "a photo card lands") sits. This file's own rule is that a
# sound accompanying motion sits BELOW one marking an event; the boom marks
# one. -16.8 measures **-10.47 dBFS peak** in the master.
#
# RMS, not peak: `cue_gain_peak` exists for clicks, and the boom has the
# LOWEST crest in the palette (7.7 dB) — it is the most sustained sound
# there, so its RMS is what carries.
BOOM_RMS = -16.8
# PUNCH RUNS BEFORE ASSEMBLE. George: *"ensure we are adding sound effects
# for funny moments throughout the video ... has to go on a zoom for
# dramatic effect."* A cue on a zoom needs the zoom's time, and the punch
# plan is only known once that stage has run. The two touch different
# tracks — punch rebuilds V2, assemble clears V3+ and A2 — so the order is
# free to change.
STAGES = ("cut", "captions", "chat", "punch", "assemble", "render")


def log(*a):
    print(*a, flush=True)


# A SHOT IS NOT A KEEP, and conflating them is why cutting dead space has
# always cost picture cadence.
#
# A keep is an AUDIO SPLICE — where a pause was removed. A shot is a PICTURE
# CUT — where the framing changes. The build gave every keep its own framing,
# so the two were forced equal and the only way to cut more dead space was to
# cut the picture faster. Measured on clip 6 at MIN_DEAD 0.20: 14 splices,
# which as shots would be 20.2 cuts/min, but grouped into shots of at least
# MIN_SHOT it is **8 shots and 10.9 cuts/min** — under clip 8's shipped 12.8,
# with 3s more dead air removed.
#
# What the small splices inside a shot become is an ordinary jump cut on a
# talking head, which is the standard language of the format. The framing
# changes at the rate a cut should happen; the splices happen at the rate the
# pauses do.
MIN_SHOT = 3.5


def _shot_index(lengths, min_shot=MIN_SHOT):
    """Group consecutive keeps into shots. Returns a shot index per keep."""
    out, shot, acc = [], 0, 0.0
    for L in lengths:
        out.append(shot)
        acc += L
        if acc >= min_shot:
            shot += 1
            acc = 0.0
    return out

# AN IN-POINT ON A WHISPER WORD BOUNDARY LANDS INSIDE THE PREVIOUS WORD.
#
# George, on clip 6: *"it needs to start a tiny bit later because we hear a
# little fragment of his former word."*
#
# Whisper's word timings are CONTIGUOUS — this file already measures the
# median inter-word gap at 0.000s — so every boundary it reports is a guess
# placed somewhere inside the join, not an onset. Clip 6's in-point was set
# to `i've @ 2.02`; measured at 5ms resolution the envelope shows the vowel
# of the PREVIOUS word peaking -11 dB at 1.95, then **2.03-2.21 sustained at
# -20 to -25 dB** — the /s/ of "this" — and only then a real trough to -39.
# So 2.02 opened the clip on 0.19s of a trailing fricative.
#
# Confirmed by transcribing both candidates: cutting at 2.02 and at 2.42
# BOTH return "I've said this on every single stream", so the 0.4s dropped
# is entirely the previous word's tail and costs no speech.
#
# The fix is general, because the cause is: advance to the next TROUGH, then
# to the onset after it, and leave a short pre-roll. Natural pre-roll on this
# material measures 0.24-0.63s (median 0.42); this only has to clear the
# consonant, so it takes the low end.
SNAP_WINDOW = 0.9        # how far forward to look for the onset
SNAP_PREROLL = 0.06      # breath left in front of the first word
# HOW FAR A SNAP MAY MOVE. The snap only ever moves FORWARD, so when the
# requested in-point is already a correct word START it marches past that
# word to the trough on its far side. Clip 12 asked for "you guys have it
# good now" at 23.30 and got 23.835 — "you" ends at 23.82, so the snap ate
# the word the line opens on.
#
# The distance separates the two cases, because a word TAIL is short and a
# whole word is not: clip 6's trailing fricative put the trough 0.195s away,
# clip 12's next-word trough was 0.525s away. Beyond this, the requested
# point is taken to be deliberate and is left alone.
SNAP_MAX = 0.35
# HOW FAR IT MAY WALK BACK, which is the THIRD case and the one that produced
# George's "remove the uhh".
#
# The snap above has two cases: the in-point sits on a word TAIL (a trough is
# close, snap forward) or it is a real word START (no trough close, leave it).
# Clip 12 was neither. `in_point 23.30` landed **inside the word "you"**,
# which is audible 23.228-23.52 and then decays into a 0.73s Twitch mute. So
# the forward snap refused — correctly, the next trough was 0.535s away — and
# the clip opened on the second half of a word. A half-word with its onset
# missing is not a word; it is the "uhh".
#
# The refusal IS the signal. When the forward trough is beyond SNAP_MAX and
# the audio is CONTINUOUS across the requested point, we are mid-word, and
# the only safe direction is backward to that word's own onset. Measured at
# 23.20-23.23 the level sits -43 to -49 dB against the word's -15, so the
# trough is 0.075s behind. 0.20s is the ceiling: enough to recover a word's
# onset, not enough to pull in the previous word.
SNAP_BACK = 0.20
# THE CLIP MUST NOT OPEN AT FULL LEVEL ON FRAME 0, AND IT MUST NOT OPEN ON A
# WORD THE CAPTION GATE REFUSES. Two rules, one measurement each, both from
# George's second note on this opening: "start of the video is still a bit
# wrong - try again".
#
# 1. FRAME 0. Measured across the clips he has ACCEPTED: clip 6 opens with
#    270ms of lead-in at -47.6 dBFS on frame 0, clip 8 with 100-200ms at
#    -41.5. Clip 12 opened with **0ms of lead-in at -11.9 dBFS** — its own
#    peak is -10.4, so it began at full speech level on the first frame.
#    That is the defect, and it is not subtle.
#
#    Pre-roll cannot be FOUND on this material. Scanning source 20-32s, every
#    word is preceded either by the previous word still sounding (he talks
#    continuously — whisper's median inter-word gap here is 0.000s) or by
#    digital zero (a Twitch mute). Exactly ONE word in twelve seconds has real
#    room tone in front of it. So the in-point backs into whatever quiet is
#    there, and a mute's tail is acceptable as lead-in where room tone is not
#    available: a quarter-second of silence at the head of a clip is how every
#    accepted clip starts, whatever its dBFS.
#
# 2. THE FIRST WORD. `in_point 23.225` opened on "you", whose span is **55.4%
#    digital zero** — so `_drop_hallucinated` had already refused its caption.
#    The viewer heard a word the caption track would not show, and the
#    captions then started on the NEXT word. The audio and the captions
#    disagreed at frame 0. A word we will not quote is not a word to open on.
#    Checked against clip 6: its opening word "i've" is 0.0% silent, so the
#    rule is a no-op there and the earlier fix stands.
LEAD_IN = 0.24           # what frame 0 gets, measured off clip 6's 270ms
LEAD_IN_ABSENT = 0.10    # ...but a mute's tail is silence, not room tone
CUE_SILENT_HEAD = 0.25   # a cue at or before this marks the clip, not an event
LEAD_QUIET_DB = -34.0    # what counts as quiet enough to back into


def _snap_in_point(src, in_point, window=SNAP_WINDOW, preroll=SNAP_PREROLL):
    """Move `in_point` forward off a word tail onto the next real onset."""
    import numpy as np
    t0 = max(0.0, in_point - 0.05)
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{t0:.3f}", "-t", f"{window:.3f}",
         "-i", str(src), "-ac", "1", "-ar", "48000", "-f", "f32le", "-"],
        capture_output=True).stdout
    a = np.frombuffer(raw, np.float32)
    if a.size < 4800:
        return in_point, None
    sr, w = 48000, 240                      # 5ms
    env = np.array([float(np.sqrt(np.mean(a[i:i + w] ** 2)))
                    for i in range(0, a.size - w, w)])
    times = t0 + np.arange(env.size) * (w / sr)
    floor = float(np.percentile(env, 15))
    # THE TROUGH HAS TO BE SUSTAINED. Taking the first point under the
    # threshold caught a 10ms dip BETWEEN the vowel and the fricative of the
    # same word — clip 6 snapped to 2.025, still inside "this". A real word
    # gap holds; a transient inside a word does not.
    thr = max(floor * 2.0, 1e-6)
    hold = 12                               # 60ms
    tr = None
    for i in range(env.size - hold):
        if float(env[i:i + hold].max()) <= thr:
            tr = i
            break
    if tr is None:
        return in_point, None
    # SNAP TO THE TROUGH, NOT TO THE ONSET. Hunting the next onset needs a
    # loudness threshold, and the word after a pause is often quiet — on
    # clip 6 a 5x-floor test skipped a softly-spoken "I've" (peaking 0.024
    # against a 0.004 floor) and landed on "said" 0.14s later, cutting the
    # word the clip was meant to open on. The trough is the word BOUNDARY
    # and it is unambiguous; the pause in front of the next word is then
    # the dead-space pass's job, which already trims it to a BEAT.
    loud = max(floor * 5.0, 1e-5)
    onset = next((i for i in range(tr, env.size - 6)
                  if env[i] >= loud and float(env[i:i + 6].mean()) >= loud), None)
    snapped = float(times[tr]) + 0.01
    if snapped - in_point > SNAP_MAX:
        # MID-WORD: WALK BACK TO THE ONSET. See SNAP_BACK. The test for
        # "mid-word" is that the audio does not stop at the requested point —
        # the 60ms before it is within 10 dB of the 60ms after, i.e. one
        # continuous sound the point is sitting inside. At a genuine word
        # start the before is 20+ dB down and nothing moves.
        back = _snap_back(src, in_point, window=SNAP_BACK)
        if back is not None:
            return round(back, 3), {
                "trough": round(float(times[tr]), 3),
                "moved": round(back - in_point, 3),
                "backward": f"the requested point was INSIDE a word (audio "
                            f"continuous across it, next trough "
                            f"{snapped - in_point:.3f}s away) — walked back to "
                            f"the word's own onset"}
        return in_point, {"trough": round(float(times[tr]), 3),
                          "moved": 0.0,
                          "skipped": f"nearest trough is "
                                     f"{snapped - in_point:.3f}s away, over the "
                                     f"{SNAP_MAX}s limit — treated as a real "
                                     f"word start"}
    return round(snapped, 3), {
        "trough": round(float(times[tr]), 3),
        "next_loud_onset": None if onset is None else round(float(times[onset]), 3),
        "moved": round(snapped - in_point, 3)}

def _open_on_captionable(words, in_point, absent, limit=2.0):
    """Move `in_point` off a word whose caption the hallucination gate drops.

    Same test as `_drop_hallucinated`, applied to the in-point instead of to a
    card: more than `HALLUCINATION_SHARE` of the word's own span is digital
    zero. Returns the new in-point and the word it moved to, or (in_point, None).
    """
    cur = next((w for w in words
                if w["start"] <= in_point < w["end"] - 1e-6), None)
    if cur is None:
        return in_point, None
    def zshare(w):
        span = max(1e-6, w["end"] - w["start"])
        z = sum(max(0.0, min(w["end"], b) - max(w["start"], a)) for a, b in absent)
        return z / span
    if zshare(cur) <= HALLUCINATION_SHARE:
        return in_point, None
    nxt = next((w for w in words
                if w["start"] >= cur["end"] - 1e-6
                and zshare(w) <= HALLUCINATION_SHARE), None)
    if nxt is None or nxt["start"] - in_point > limit:
        return in_point, None
    return float(nxt["start"]), {"was": cur["text"], "zero": round(zshare(cur), 3),
                                 "now": nxt["text"]}


def _lead_in(src, in_point, want=LEAD_IN, quiet_db=LEAD_QUIET_DB):
    """Back the in-point into whatever quiet precedes it, up to `want`.

    Only ever crosses audio under `quiet_db`, so it cannot pull in the tail of
    the previous word — which is the defect `_snap_in_point` exists to remove,
    and this must not reintroduce it. Returns the new in-point and how much
    lead-in it found; 0.0 means there was none to take.
    """
    import numpy as np
    t0 = max(0.0, in_point - want - 0.02)
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{t0:.3f}",
         "-t", f"{in_point - t0:.3f}", "-i", str(src),
         "-ac", "1", "-ar", "48000", "-f", "f32le", "-"],
        capture_output=True).stdout
    a = np.frombuffer(raw, np.float32)
    sr, w = 48000, 240                      # 5ms
    if a.size < w * 2:
        return in_point, 0.0
    env = np.array([float(np.sqrt(np.mean(a[i:i + w] ** 2)))
                    for i in range(0, a.size - w, w)])
    db = 20 * np.log10(np.maximum(env, 1e-9))
    # walk back from the in-point while it stays quiet
    i = len(db) - 1
    while i >= 0 and db[i] <= quiet_db:
        i -= 1
    got = (len(db) - 1 - i) * (w / sr)
    # IS THE LEAD-IN PRESENT AUDIO OR A MUTE? The test above only has an
    # UPPER bound, so digital zero — which is under any quiet threshold —
    # passes it. On clip 12 all 0.255s of the lead-in measures -180.0 dBFS
    # against clip 6's accepted -38.3, and `deliver_qc`'s absent-audio check
    # CANNOT SEE IT: the chat's `paper` cue fires at 0.020s and fills the
    # hole, so the delivered file reports 0 absent runs. A cue masking the
    # thing a gate exists to find is the gate being blinded, which is worse
    # than the hole. It is reported here, on the CUT, where no bed exists.
    taken = db[i + 1:] if i + 1 < len(db) else db[:0]
    absent = bool(taken.size) and float(taken.max()) <= -90.0
    # A MUTE'S TAIL BUYS LESS THAN ROOM TONE DOES. Room tone is the sound of
    # the room and reads as the clip breathing before he speaks; digital zero
    # reads as nothing happening. Clip 6 opens on 270 ms of real tone at
    # -38.3 dBFS; clip 12 has none to take, so it gets a shorter beat.
    if absent:
        got = min(got, LEAD_IN_ABSENT)
    return round(in_point - got, 3), round(got, 3), absent


def _snap_back(src, in_point, window=SNAP_BACK, pad=0.06):
    """The onset of the word `in_point` is sitting inside, or None.

    Returns None unless the audio is CONTINUOUS across `in_point` — which is
    what says the point is mid-word rather than at a word start — and a
    sustained trough exists within `window` behind it.
    """
    import numpy as np
    t0 = max(0.0, in_point - window - pad)
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{t0:.3f}",
         "-t", f"{in_point + pad - t0:.3f}", "-i", str(src),
         "-ac", "1", "-ar", "48000", "-f", "f32le", "-"],
        capture_output=True).stdout
    a = np.frombuffer(raw, np.float32)
    sr, w = 48000, 240                      # 5ms
    if a.size < w * 8:
        return None
    env = np.array([float(np.sqrt(np.mean(a[i:i + w] ** 2)))
                    for i in range(0, a.size - w, w)])
    times = t0 + np.arange(env.size) * (w / sr)
    at = int(np.argmin(np.abs(times - in_point)))
    db = lambda v: 20 * np.log10(max(v, 1e-9))
    before = db(float(np.sqrt(np.mean(env[max(0, at - 12):at] ** 2))))
    after = db(float(np.sqrt(np.mean(env[at:at + 12] ** 2))))
    if before < after - 10.0:               # the audio DOES stop here
        return None
    floor = float(np.percentile(env, 15))
    thr = max(floor * 2.0, 1e-6)
    # the last sustained trough before the point
    for i in range(at - 4, 2, -1):
        if float(env[max(0, i - 4):i].max()) <= thr:
            cand = float(times[i]) - 0.005
            return cand if in_point - cand <= window else None
    return None


def _in_trough(src, t, win=0.04, margin=12.0):
    """Is `t` in an acoustic trough rather than inside audible speech?

    **WHISPER'S WORD BOUNDARY AND THE AUDIO DISAGREE, and the audio wins.**
    George asked for the clip to end on "salary"; the cut that does is 86.30,
    which measures **-36.4 dB against a speech baseline of -19** — a 17 dB
    dip, unmistakably a boundary. Whisper calls 86.30 the middle of "all"
    (86.15-86.41), so `_snap_out_point` would push the cut forward to 86.41
    and put "all" back in. Its word timings here are contiguous guesses; a
    trough is not a guess.
    """
    import array, math
    def rms_db(t0, t1):
        raw = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", f"{t0:.3f}", "-to", f"{t1:.3f}",
             "-i", str(src), "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
            capture_output=True).stdout
        a = array.array("h"); a.frombytes(raw)
        if not a:
            return -99.0
        r = math.sqrt(sum((v / 32768.0) ** 2 for v in a) / len(a))
        return 20 * math.log10(r) if r > 0 else -99.0
    here = rms_db(t - win / 2, t + win / 2)
    around = rms_db(max(0.0, t - 1.5), t)
    return here < around - margin


def _snap_out_point(words, out_point, absent, tol=0.30, src=None):
    """Move `out_point` off the middle of a word onto that word's END.

    **This is the defect George named as `the end "tragic" is cut off`, and it
    was a hand-typed number, not a pipeline bug.** `out_point 86.50` sat inside
    the word "day" (86.410-86.590), so the clip stopped mid-word; the line is
    "...sacrifice a couple months of salary all day. Tragic."

    AGENTS.md already records the policy for the tie — over-including by one
    word is recoverable, losing the payoff is not — so the snap goes FORWARD to
    the containing word's end. It also reports the next word, because that is
    how a human notices a button like "Tragic." has been left outside the clip:
    nothing mechanical can tell that it was the point.

    `absent` lets it say when the word it landed on straddles a mute, which is
    the case where the snap cannot help and the out-point belongs back at the
    last audible sample instead.
    """
    if out_point is None or not words:
        return out_point, None
    inside = next((w for w in words
                   if w["start"] < out_point < w["end"] - 1e-6), None)
    if inside is None:
        return out_point, None
    if src is not None and _in_trough(src, out_point):
        return out_point, {"moved": 0.0,
                           "skipped": f"whisper puts this inside "
                                      f"{inside['text']!r}, but the audio there "
                                      f"is a trough — the audio wins"}
    end = float(inside["end"])
    if end - out_point > tol:
        return out_point, {"moved": 0.0,
                           "skipped": f"inside {inside['text']!r} but its end is "
                                      f"{end - out_point:.2f}s away, over {tol}s"}
    nxt = next((w for w in words if w["start"] >= end - 1e-6), None)
    zero = sum(max(0.0, min(end, b) - max(float(inside["start"]), a))
               for a, b in absent)
    return end, {"word": inside["text"], "moved": round(end - out_point, 3),
                 "next": nxt["text"] if nxt else None,
                 "straddles_mute": round(zero, 2) if zero > 0.05 else None}


def _clamp_out_point(kp, out_point):
    """Truncate the keeps at `out_point`.

    **THE SWALLOW IS GONE HERE TOO, AND IT WAS WORSE AT THIS END.** The same
    `min_last=0.40` sliver guard that `_clamp_in_point` lost earlier this round
    was still merging a short FINAL keep into the one before it — which does
    not shorten anything, it RESTORES the removal between them.

    Measured on clip 12: the last keep ran 87.32-87.70, which is 0.38s, holding
    the one-word button "Tragic." At 0.02s under the limit the guard merged it,
    so the keeps became one span 84.67-87.70 and the 0.59s removal came back —
    delivering **0.75s of quiet with 0.35s of digital zero in it** immediately
    before the payoff word. The clip's last sound before its punchline was a
    dropout, and the gate flagged it as absent audio.

    The guard was correct when every keep got its own framing. Since
    `_shot_index` groups keeps until MIN_SHOT accumulates, a 0.38s final keep
    is just the tail of the last shot and costs nothing. A keep is not a shot —
    which is the same finding twice in one round, at both ends of the clip.
    """
    if out_point is None:
        return kp
    kp = [k for k in kp if k.start < out_point]
    if not kp:
        return kp
    kp[-1].end = min(kp[-1].end, out_point)
    return kp


def _clamp_in_point(kp, in_point, min_first=0.40):
    """Clamp the keeps to `in_point` without leaving a sliver first shot.

    Moving an in-point onto a word often lands it a fraction of a second
    before a removal, and the first keep then becomes a 0.1s stub that gets
    its own framing — a six-frame flash before the clip proper. When that
    happens the honest fix is to KEEP THE PAUSE: merge the stub forward so
    the clip opens on one continuous shot. A natural breath at the head of a
    clip costs nothing; a six-frame shot is a glitch.
    """
    kp = [k for k in kp if k.end > in_point]
    if not kp:
        return kp
    kp[0].start = max(kp[0].start, in_point)
    # THE SWALLOW IS GONE. It was written when every keep got its own
    # framing, so a 0.1s first keep was a six-frame flash and merging it
    # forward was the lesser evil. Since shots were decoupled from keeps a
    # short first keep is simply the opening fragment of shot 0 and costs
    # nothing — while the merge KEEPS THE PAUSE, and on clip 12 that put a
    # clipped "you", then **1.0 second of digital silence at -77 dB**, then
    # "guys have it good now man" at the very top of the clip. That dead
    # second is what George heard as an "uhh".
    #
    # A guard that was correct under one architecture became a defect under
    # the next, which is the same shape as the chat cycle that outlived the
    # cards it was dodging.
    return kp

# WHISPER HALLUCINATES OVER A MUTE, AND IT DOES IT AT p = 1.000.
#
# Found by an adversarial pass that was asked something else entirely —
# whether FNS was answering a chat message — and which kept reporting that
# the line it turned on does not exist. Measured on clip 6's source:
# `qc.dead_audio` finds digital zero at 36.086-36.773 (0.687s) and
# 37.437-38.146 (0.709s), at about -113 dBFS against speech at -19, and
# whisper placed "agree" at 36.240-37.000 and "we" at 37.000-38.020 across
# them with **confidence 1.000 and 0.999**. 1.40s of the 2.80s rendered as
# "i agree we agree on this" is silence.
#
# The clip then BURNED THOSE WORDS ON SCREEN. That breaks the oldest rule in
# this file — nothing on screen is a phrase nobody said — and it is worse
# than an invented card, because a caption is read as a verbatim quote. It
# also poisoned everything downstream: the clip's tier3 risk note "multiple
# speakers in the last few lines" traces to this same hallucination, and
# four independent judges had to measure pitch, mouth motion and the facecam
# to establish that there is no co-host and FNS is alone for the whole clip.
#
# **Whisper's confidence is worthless here** — it is highest exactly where
# there is nothing to transcribe. The audio is the check, not the model.
HALLUCINATION_SHARE = 0.5     # of a card's own span sitting in digital zero


def _drop_hallucinated(cs, absent, min_share=HALLUCINATION_SHARE):
    """Remove caption cards whose span is mostly absent audio."""
    kept, dropped = [], []
    for c in cs:
        span = max(c.end - c.start, 1e-6)
        mute = sum(max(0.0, min(c.end, b) - max(c.start, a)) for a, b in absent)
        (dropped if mute / span > min_share else kept).append((c, mute / span))
    return [c for c, _ in kept], dropped

def _cut_words(clip, st):
    """`[(cut_second, text)]` for the nucleus gate.

    Read off the same `keeps` everything else is remapped through, and from
    disk when the captions stage did not run in THIS invocation — a partial
    run is the normal way this pipeline is driven, and a value that only
    exists in memory is the defect this file has recorded three times.
    """
    words = st.get("words")
    if words is None:
        words = [w for u in json.loads(clip.words(ROOT).read_text())["utterances"]
                 for w in u["words"]]
    remap = _remap_fn(st["keeps"])
    out = []
    for w in words:
        t = remap(w["start"])
        if t is not None:
            out.append((t, w.get("text", "")))
    return out


def _emphasis_anchors(clip, ch, st):
    """The emphasised caption cards' start times, in OUTPUT time.

    These are the clip's own thesis words — `emphasis_keys(claim,
    consequence)` from the model that selected the clip — and they are drawn
    in accent colour, so a punch or a cue landing on one marks something the
    viewer SEES. `resolve_punch` uses them both to FILTER candidate moments
    (a peak with no card beside it marks nothing) and to ANCHOR the ones that
    survive. See the ANCHOR_BACK note there for the measurements.
    """
    from engine.resolve_captions import cards, emphasis_keys, mark_emphasis
    words = [w for u in json.loads(clip.words(ROOT).read_text())["utterances"]
             for w in u["words"]]
    cs = cards(words)
    meta = st["meta"]
    # THE CLAIM, NOT THE CONSEQUENCE. George: *"last boom is pretty
    # irrelevant - remember there should be logic to it."* The third boom sat
    # on "you HAVE the freedom to choose your own teammates" — a calm
    # explanatory line — while the two he kept sat on "I don't want to HEAR
    # no complaints" and "that's IT".
    #
    # Neither metric separates them: measured at their own peaks the three
    # score +2.72 / +1.28 / +2.74 dB over baseline and +0.87 / +5.00 / +1.79
    # dB of rise, so level ranks the irrelevant one FIRST and rise ranks it
    # second. What separates them is where the word comes from. `claim` and
    # `consequence` are separate fields and the cards merge them; the two
    # booms that work are claim words and the one he rejected is a
    # consequence word.
    #
    # A boom punctuates what he is ASSERTING, not the resolution he offers.
    # Captions still emphasise both — that is the style he signed off — and
    # only the cue anchors narrow. Editorial rather than universal: on a clip
    # whose payoff IS its consequence this would need revisiting.
    # MARK WITH BOTH, ANCHOR ON THE CLAIM. Marking with the claim alone also
    # changes WHICH cards are emphasised (16 -> 12 on clip 12), which moves
    # every anchor and cost a boom George had accepted. The caption styling
    # must not move: it is emphasised from claim AND consequence, which is
    # what he signed off. Only the subset usable as a CUE ANCHOR narrows.
    both = emphasis_keys(meta.get("claim", ""), meta.get("consequence", ""))
    mark_emphasis(cs, both)
    claim_keys = emphasis_keys(meta.get("claim", ""), "")
    out = []
    for c in cs:
        if not c.emphasis:
            continue
        if not any(k in c.text.upper() for k in claim_keys):
            continue
        rm = remap_card(c.start, c.end, st["keeps"])
        if rm:
            out.append(round(rm[0], 3))
    return sorted(set(out))


def _phrase_starts(clip, ch, st):
    """Phrase starts in OUTPUT time, for snapping a punch off its RMS peak.

    **UTTERANCE starts, not inter-word gaps.** Whisper's VAD gives contiguous
    word timings — measured on clip 6, the median inter-word gap is 0.000s
    and only 1 of 150 reaches 0.25s — so a gap-based phrase detector finds
    almost nothing. This file already records that trap for finding pauses
    ("whisper's VAD merges utterances ... use WORD gaps") and the inverse is
    true here: for phrase BOUNDARIES the utterance list is the only usable
    signal, because the word timings have none. Clip 6's "ping issues
    cheaters" is utterance 3, starting exactly where George wants the zoom.
    """
    wf = clip.words(ROOT)
    if not wf.exists():
        return []
    tr = json.loads(wf.read_text())
    kp = st["keeps"]

    def remap(t):
        acc = 0.0
        for k in kp:
            if k.start <= t < k.end:
                return acc + (t - k.start)
            acc += k.length
        return None

    marks = [u["start"] for u in tr["utterances"]]
    prev_end = None
    for u in tr["utterances"]:
        for w in u["words"]:
            if prev_end is not None and w["start"] - prev_end >= rp_gap():
                marks.append(w["start"])
            prev_end = w["end"]
    out = sorted({round(remap(t), 3) for t in marks if remap(t) is not None})
    return out


def rp_gap():
    import resolve_punch as rp
    return rp.PHRASE_GAP

def _cut_audio(clip, ch, st):
    """The tightened cut's audio, straight from the source.

    The punch pass needs the speaker's own levels, and AGENTS.md records why
    it must not read a delivered mp4: `render_and_finish` overwrites the
    delivery every version, so the plan moved underneath the build. This is
    derived from the source and the keeps, so it is identical every run and
    carries no sfx bed and no loudnorm — his delivery, not our mix.
    """
    dst = st["base_wav"]
    # NO CACHE. This is derived from the keeps, and the keeps change whenever
    # the in-point or the dead-space floor moves. A stale copy put the punch
    # plan's last moment at 39.80s on a 38.57s clip — measured against a cut
    # that no longer existed.
    dst.unlink(missing_ok=True)
    src = clip.source(ROOT)
    parts = "".join(
        f"[0:a]atrim=start={k.start:.4f}:end={k.end:.4f},asetpts=PTS-STARTPTS[a{i}];"
        for i, k in enumerate(st["keeps"]))
    joined = "".join(f"[a{i}]" for i in range(len(st["keeps"])))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
                    "-filter_complex",
                    f"{parts}{joined}concat=n={len(st['keeps'])}:v=0:a=1[o]",
                    "-map", "[o]", "-ac", "1", "-ar", "16000", str(dst)],
                   check=True)
    return dst


# ---------------------------------------------------------------- cut ----
def _cam(clip, ch, st):
    """The facecam rect for THIS clip: the spec's, or detected."""
    if "cam" in st:
        return st["cam"]
    if clip.cam:
        st["cam"] = tuple(clip.cam)
        log(f"  facecam {st['cam']} (from the spec)")
        return st["cam"]
    f = facecam.detect(clip.source(ROOT))
    if f is None:
        st["cam"] = ch.cam
        log(f"  facecam NOT DETECTED — falling back to the channel's "
            f"{ch.cam}. Check the frame.")
        return st["cam"]
    st["cam"] = f.rect
    flag = "" if f.margin >= 4 else "   LOW CONFIDENCE — check the frame"
    log(f"  facecam {f.rect} detected: {f.coverage:.1%} of frame, "
        f"moves {f.margin:.0f}x the rest{flag}")
    return st["cam"]


def stage_cut(clip, ch, st):
    src = clip.source(ROOT)
    fps = ch.fps
    pl = _plan_only(clip, ch, st)
    src_dur, ip, op = pl["src_dur"], pl["in_point"], pl["out_point"]
    snap, osnap, spans = pl["snap"], pl["out_snap"], pl["spans"]
    kp, out_dur = st["keeps"], st["out_dur"]
    log(f"  {src.name}")
    if pl.get("skipped"):
        k = pl["skipped"]
        log(f"  in-point skipped {k['was']!r} — {k['zero']:.0%} of its span is "
            f"digital zero, so the caption gate drops it; opening on {k['now']!r}")
    if pl.get("lead"):
        kind = ("ABSENT AUDIO, not room tone — there is none on this source; "
                "the chat cue covers it and the delivery gate cannot see it"
                if pl.get("lead_absent") else "room tone")
        log(f"  lead-in {pl['lead']:.3f}s before the first word ({kind})")
    elif pl.get("lead") == 0.0:
        log(f"  NO LEAD-IN AVAILABLE — the clip opens on the word's attack")
    if snap and abs(snap["moved"]) > 0.005:
        why = snap.get("backward") or (
            f"snapped off a word tail to the trough at {snap['trough']}")
        log(f"  in-point {clip.in_point} -> {ip} ({why})")
    if osnap:
        if osnap.get("moved"):
            log(f"  out-point {clip.out_point} -> {op} (was inside "
                f"{osnap['word']!r}; finished the word)")
            if osnap.get("straddles_mute"):
                log(f"    CAREFUL: that word straddles "
                    f"{osnap['straddles_mute']}s of absent audio")
        else:
            log(f"  out-point left at {clip.out_point}: {osnap['skipped']}")
    log(f"  in-point {ip}s | {len(spans)} dead removals "
        f"({sum(s.length for s in spans):.1f}s)")
    log(f"  {src_dur:.1f}s -> {out_dur:.1f}s in {len(kp)} shots, "
        f"{(len(kp)-1)/(out_dur/60):.1f} cuts/min")
    r = connect(); r.OpenPage("edit")
    proj = r.GetProjectManager().GetCurrentProject()
    mp = proj.GetMediaPool()
    r.GetMediaStorage().AddItemListToMediaPool([str(src)])
    item = next(i for i in mp.GetRootFolder().GetClipList()
                if i.GetName() == src.name)
    name = f"{clip.slug}"
    for i in range(proj.GetTimelineCount(), 0, -1):
        t = proj.GetTimelineByIndex(i)
        if t and t.GetName() == name:
            mp.DeleteTimelines([t])
    tl = mp.CreateEmptyTimeline(name)
    while tl.GetTrackCount("video") < 6:
        tl.AddTrack("video")
    # AND AN AUDIO TRACK FOR THE SFX BED — the absence of which meant NO
    # CLIP BUILT BY THIS PIPELINE HAS EVER HAD A SOUND EFFECT. `add()` puts
    # the bed on audio track 2; only video tracks were ever created, so the
    # append went to a track that does not exist and was dropped in silence.
    # `AppendToTimeline` still returned it, so the log read "appended 3 of 3"
    # and the sfx stage still reported its cue count — both describing a bed
    # that was written to disk and never placed. George: "there's no booms?"
    while tl.GetTrackCount("audio") < 2:
        tl.AddTrack("audio")
    proj.SetCurrentTimeline(tl)
    # recordFrame is ABSOLUTE: a timeline starts at 01:00:00:00 = 216000 at
    # 60fps, so recordFrame=0 puts the clip an hour before the start and
    # renders black while GetItemListInTrack still lists it.
    start = tl.GetStartFrame()
    ents, rec = [], start
    for k in kp:
        sf, ef = round(k.start * fps), round(k.end * fps)
        for track in (1, 2):
            ents.append({"mediaPoolItem": item, "startFrame": sf, "endFrame": ef,
                         "trackIndex": track, "recordFrame": rec,
                         **({} if track == 1 else {"mediaType": 1})})
        rec += ef - sf
    mp.AppendToTimeline(ents)

    canvas = Frame(1080, 1920, 1920, 1080)
    seam_y = ch.seam * canvas.canvas_h
    sidx = _shot_index([k.length for k in kp])
    nshots = sidx[-1] + 1 if sidx else 1
    st["shot_index"] = sidx
    rects = framings(nshots, _cam(clip, ch, st))
    crects = content_framings(nshots, chrome=ch.chrome)
    for trk, rl, pane in ((1, crects, (0, seam_y, 1080, 1920)),
                          (2, rects, (0, 0, 1080, seam_y))):
        items = sorted(tl.GetItemListInTrack("video", trk) or [],
                       key=lambda i: i.GetStart())
        for it, si in zip(items, sidx):
            apply(it, plan(canvas, rl[si], pane))
            if trk == 2 and ch.grade:
                it.SetCDL(ch.grade)
    log(f"  {len(kp)} audio splices ({(len(kp)-1)/(out_dur/60):.1f}/min) grouped "
        f"into {nshots} shots ({(nshots-1)/(out_dur/60):.1f} picture cuts/min)")
    log(f"  V1 {len(tl.GetItemListInTrack('video',1))} / "
        f"V2 {len(tl.GetItemListInTrack('video',2))} shots, "
        f"{(tl.GetEndFrame()-start)/fps:.1f}s")
    # Every join splices across speech nobody can hear, on a muted VOD. The
    # caveat has been overruled twice and is still printed every time.
    js = joins(spans, st.get("words", []))
    if js:
        log(f"  {len(js)} joins splice across unheard speech")


# ----------------------------------------------------------- captions ----
def stage_captions(clip, ch, st):
    tr = json.loads(clip.words(ROOT).read_text())
    words = [w for u in tr["utterances"] for w in u["words"]]
    st["words"] = words
    meta = st["meta"]
    cs = cards(words)
    absent = qc.dead_audio(clip.source(ROOT), min_run=0.1)["runs"]
    cs, dropped = _drop_hallucinated(cs, absent)
    if dropped:
        log(f"  {len(dropped)} card(s) DROPPED as whisper hallucination over a mute:")
        for c, share in dropped:
            log(f"     {c.start:6.2f}-{c.end:6.2f}  {c.text!r}  ({share:.0%} silence)")
    mark_emphasis(cs, emphasis_keys(meta.get("claim", ""),
                                    meta.get("consequence", "")))
    out = []
    for c in cs:
        rm = remap_card(c.start, c.end, st["keeps"])
        if rm:
            out.append(type(c)(rm[0], rm[1], c.text, c.words, c.emphasis))
    st["cards"] = out
    dst = st["overlays"] / "cap_kin.mov"
    captions_video.kinetic([{"start": c.start, "end": c.end, "text": c.text,
                             "words": c.words, "emph": c.emphasis}
                            for c in out],
                           dst, dur=st["out_dur"], accent=CAPTION_ACCENT)
    st["story_cards"] = _story_cards(clip, ch, st)
    log(f"  {len(cs)} cards -> {len(out)} after the cut "
        f"({sum(1 for c in out if c.emphasis)} emphasised), "
        f"{len(out)/max(st['out_dur'],1):.2f}/s -> {dst.name}")


# --------------------------------------------------------------- chat ----
# HOW LONG A STORY CARD HOLDS, and where it sits. Both measured earlier in
# this file: the usable band for a lower-pane graphic is y 980-1600 because
# the captions own everything above it, and the two hand-built story cards
# that shipped ran 255 and 240 frames with 2.15s and 2.42s of settled hold.
STORY_FRAMES = 240
STORY_TILT = -3.4

# GEORGE, ON THE VITALITY CARD: *"the vitality pop up needs to take up more
# of the screen like i mentioned for the jingg/jonahp story."*
#
# It was not small — measured off its own alpha at >250 the body ran
# y 1005-1647, 1040px wide, 48.9% of the lower pane, and already 47px past
# the 1600 platform-UI line. What was small was the PEOPLE in it, for a
# reason specific to a one-photo card: the hand-built Jinggg/JonahP cards
# put TWO near-square crops side by side, so each face was ~499px wide,
# while a single 1.5:1 team shot in a 1008x430 box is a 2.34:1 letterbox
# that threw away 36% of the frame and left each player 221px tall.
#
# Three things move, and only the first is a number George named:
#
# * **TALLER, past the safe line, which is a precedent he has already set
#   twice.** AGENTS.md records the Jinggg card ending near y 1740 inside
#   the bottom 320px exclusion as "a deliberate trade for the size he asked
#   for twice" — that band is a CAPTION gate in `gates.py`, not a graphics
#   one. This lands at the same place rather than inventing a new limit.
# * **FOCUS, because `22%` was written for portraits.** Measured on the
#   photo, the five players occupy source y 365-590 of 683 — the lower
#   middle — so centring the crop near the top kept the crowd and the light
#   rig and cut their feet off.
# * **ZOOM — TRIED AT 1.15, AND IT CUT THE FIFTH PLAYER IN HALF.** Under
#   `objectFit: cover` at a fixed card width the scale is set by WIDTH, so a
#   taller box shows more photo and leaves every player the same size on
#   screen; only cropping in enlarges them. But `transform: scale()` crops
#   SYMMETRICALLY about the element centre, and on a found press photo the
#   subject routinely runs to the frame edge. Measured by masking bright,
#   near-neutral pixels (the white kit) against the stage's saturated
#   orange: the five figures span **x 209-1023 of 1024**, so the furthest
#   edge sits 511px from a 512px centre and **a symmetric zoom caps at
#   1.002x before it bisects someone.** Not "1.15 is a bit much" — there is
#   no headroom at all, and shipped at 1.15 it rendered a player sliced down
#   the middle by the card edge.
#   The prop stays, because it is right for a photo whose subject is
#   centred, and the default is 1. **Enlarging the subject on an arbitrary
#   photo needs subject detection, not a constant** — the crop would have to
#   re-centre on the subject, and nothing here knows where that is.
STORY_TOP = 1008
STORY_PHOTO_H = 560
STORY_FOCUS = "62%"
STORY_ZOOM = 1.0


def _story_cards(clip, ch, st):
    """Licensed photo cards for the orgs this clip NAMES. See engine/story.

    Returns card dicts for `stage_assemble`, writes the photos and
    `stories.json` into Remotion's `public/`, and records every photo's
    licence and page URL in the job's manifest. Returns [] on any miss —
    no key, no photo, no org named — because a clip with no card is the
    normal case and must not be an error.
    """
    from engine import story
    meta = st["meta"]
    words = [w["text"] for w in st.get("words", [])] or \
        [w["text"] for u in json.loads(clip.words(ROOT).read_text())["utterances"]
         for w in u["words"]]
    text = f"{meta.get('claim','')} {meta.get('consequence','')}"
    orgs = story.named_in(text, words)
    if not orgs:
        log("  no org named in BOTH the claim and the transcript — no story card")
        (VENDOR / "public/stories.json").write_text("[]")
        return []
    rm = _remap_fn(st["keeps"])
    cards, entries, record = [], [], []
    for org in orgs[:2]:
        s = story.find(org, cache=ROOT / f"jobs/{clip.job}/_flickr",
                       dest_dir=ROOT / f"jobs/{clip.job}/photos")
        if s is None:
            log(f"  {org}: no licensed photo found — no card")
            continue
        # WHERE IT GOES: the line the viewer hears the name on, not a slot.
        at = None
        for w in (st.get("words") or
                  [w for u in json.loads(clip.words(ROOT).read_text())["utterances"]
                   for w in u["words"]]):
            spoken = w["text"].lower().strip(".,!?'\"")
            if spoken in story.SPOKEN and story.SPOKEN[spoken] == org:
                at = rm(w["start"])
                if at is not None:
                    break
        if at is None:
            log(f"  {org}: named but not locatable in the cut — no card")
            continue
        # "Story" + the distinctive word of the org, so the composition id
        # reads in the Remotion list and in the Resolve media pool.
        word = [w for w in re.split(r"[^A-Za-z0-9]", org) if w][-1]
        cid = f"Story{word[:12].capitalize()}"
        dest = VENDOR / "public" / s.photo.name
        if not dest.exists() or dest.stat().st_size != s.photo.stat().st_size:
            shutil.copyfile(s.photo, dest)
        cards.append({"id": cid, "at": round(at, 2),
                      "dur": STORY_FRAMES / ch.fps})
        entries.append({"id": cid, "headline": s.headline, "photo": s.photo.name,
                        "tilt": STORY_TILT, "top": STORY_TOP,
                        "photoHeight": STORY_PHOTO_H, "frames": STORY_FRAMES,
                        "photoFocus": STORY_FOCUS, "photoZoom": STORY_ZOOM,
                        # `at` is not read by Remotion; it is here so a
                        # partial run can recover the schedule off disk —
                        # the same reason `punches.json` carries its own.
                        "at": round(at, 2)})
        record.append(s.record())
        log(f"  story card {cid} at {at:.2f}s — {s.headline!r}")
        log(f"     photo {s.photo.name} · {s.account} · {s.licence}")
    (VENDOR / "public/stories.json").write_text(json.dumps(entries, indent=1))
    if record:
        (ROOT / f"jobs/{clip.job}/photos/stories_{clip.index:02d}.json"
         ).write_text(json.dumps(record, indent=1))
    return cards


def _all_cards(clip, st):
    """The spec's cards plus the ones `_story_cards` found. The spec still
    wins: an `id` named by hand is not overwritten by a generated one."""
    found = st.get("story_cards")
    if found is None:
        # Partial run: `stage_captions` did not execute, so recover the
        # schedule from disk rather than silently dropping every card.
        sj = VENDOR / "public/stories.json"
        try:
            found = [{"id": e["id"], "at": e["at"],
                      "dur": e.get("frames", STORY_FRAMES) / 60.0}
                     for e in json.loads(sj.read_text()) if "at" in e]
        except (OSError, json.JSONDecodeError, KeyError):
            found = []
    by_id = {c["id"]: c for c in found}
    by_id.update({c["id"]: c for c in clip.cards})
    return sorted(by_id.values(), key=lambda c: c["at"])


def _remap_fn(keeps):
    def rm(t):
        acc = 0.0
        for k in keeps:
            if k.start <= t < k.end:
                return acc + (t - k.start)
            acc += k.length
        return None
    return rm


def stage_chat(clip, ch, st):
    """Fetch, CLASSIFY, and place. The one stage that makes a decision."""
    if not (ch.vod_id and clip.region):
        log("  no vod_id/region on the spec — skipping chat")
        st["chat_windows"] = []
        return
    t0, t1 = clip.region
    cache = ROOT / f"jobs/{clip.job}/chat_{clip.index:02d}.json"
    if cache.exists():
        raw = json.loads(cache.read_text())
        log(f"  {len(raw)} messages from cache")
    else:
        # Context either side, because the RESTING RATE has to come from
        # outside the clip: a 20s ace clip is hype end to end and would read
        # as flat against its own mean.
        msgs = twitch_chat.fetch(ch.vod_id, t0 - cr.CONTEXT_PAD, t1 + cr.CONTEXT_PAD)
        twitch_chat.to_json(msgs, cache)
        raw = json.loads(cache.read_text())
        log(f"  fetched {len(raw)} (clip +/- {cr.CONTEXT_PAD:.0f}s of context)")
    for m in raw:
        m.setdefault("frags", m.get("fragments", []))

    # output time <- source time, through the same keeps the cut used
    kp = st["keeps"]

    def remap(src_t):
        acc = 0.0
        for k in kp:
            if k.start <= src_t < k.end:
                return acc + (src_t - k.start)
            acc += k.length
        return None

    # IS THE CHAT EVEN ABOUT THIS CLIP? The one-narrative rule applies to
    # every channel, not just the audio — clip 6 shipped with chat that was
    # 4% on its subject and 29% about an unrelated roster transfer, putting
    # a second story on screen for the whole runtime while the audio was
    # clean. `chat_mode: "force"` in the spec overrides this deliberately.
    meta = st["meta"]
    subject = f"{meta.get('subject','')} {meta.get('claim','')}"
    inside = [m for m in raw if t0 <= m["offset"] < t1]
    safe, why, topic = cr.chat_is_safe(inside, subject)
    log(f"  topicality: {why} ({topic['n']} messages in the window)")
    # AN EXPLICIT `chat_mode` IN THE SPEC IS THE OVERRIDE. The topicality
    # floor is a default for clips nobody has looked at; once George has
    # watched one and said "keep the twitch chat, it was good", his call
    # settles it and the measurement goes in the log as a caveat rather
    # than a veto.
    if not safe and not clip.chat_mode:
        log("  NO CHAT OVERLAY on this clip — it would carry a second narrative")
        st["chat_windows"] = []
        (PUBLIC / "chat_windows.json").write_text("[]")
        (PUBLIC / "chat.json").write_text("[]")
        (PUBLIC / "clip.json").write_text(json.dumps({
            "durationInFrames": st["total"],
            "baitFrames": min(st["total"], round(BAIT_SECONDS * ch.fps)),
            "hook": clip.hook or "", "emoji": clip.emoji}))
        if clip.hook:
            _render_comp("Bait", st["overlays"], ch.fps)
        for c in st.get("story_cards", []):
            _render_comp(c["id"], st["overlays"], ch.fps)
        (st["overlays"] / "rm_Chat.mov").unlink(missing_ok=True)
        return
    # "force" means OVERRIDE THE GATE, not "a mode called force". Passing it
    # through would miss both branches of `windows()` and return an empty
    # window list — the chat would be switched on and then not appear.
    mode_req = None if clip.chat_mode == "force" else clip.chat_mode
    mode, wins, info = cr.windows(raw, t0, t1, remap=remap, mode=mode_req,
                                  out_dur=st['out_dur'])
    log(f"  resting {info['resting_rate']:.0f}/min, clip {info['clip_rate']:.0f}/min "
        f"(x{info['clip_rate']/info['resting_rate']:.2f}), hype {info['hype_share']:.2f}")
    log(f"  MODE: {mode}  ({len(info['bursts'])} bursts, "
        f"{info['burst_coverage']:.0%} of the clip)")
    for b in info["bursts"]:
        log(f"     burst {b.start-t0:5.1f}-{b.end-t0:5.1f}s  x{b.mult:.2f} "
            f"peak {b.peak_rate:.0f}/min  hype {b.hype:.2f}")
    for w in wins:
        log(f"     window {w['from']:6.2f}-{w['to']:6.2f}  ({w['to']-w['from']:.2f}s)")
    st["chat_windows"] = wins
    st["chat_mode"] = mode

    # the messages, mapped onto the cut. Pre-roll ones get negative times so
    # the box opens already half full — a chat panel that starts empty and
    # fills up reads as a graphic booting, not as a stream you joined.
    import build_chat as bc
    kept, dropped, pre = [], 0, 0
    for m in raw:
        src_t = m["offset"]
        if src_t < t0:
            out_t = src_t - t0
            if out_t < -40:
                continue
            pre += 1
        elif src_t >= t1:
            continue
        else:
            # `remap` works in CLIP-FILE time, not VOD time: the keeps span
            # 0..file_duration while a message's offset is a VOD second.
            # Passing the raw offset matched no keep and silently dropped
            # every message inside the clip — 60 of 116 on the first run,
            # with the 56 survivors all pre-roll.
            o = remap(src_t - t0)
            if o is None:
                dropped += 1
                continue
            out_t = o
        kept.append({"t": round(out_t, 2), "author": m["author"],
                     "colour": m["colour"], "display": bc.readable(m["colour"]),
                     "badges": m["badges"][:2],
                     "frags": [{"text": f["text"], "emote": f["emote"]}
                               for f in m["frags"]]})
    kept.sort(key=lambda m: m["t"])
    (PUBLIC / "chat.json").write_text(json.dumps(kept, indent=1))
    (PUBLIC / "chat_windows.json").write_text(json.dumps(wins, indent=1))
    log(f"  {len(kept)} messages on the cut ({pre} pre-roll, {dropped} dropped "
        f"into removed spans)")

    # Remotion reads the duration and the hook from here rather than from a
    # constant in Root.tsx.
    (PUBLIC / "clip.json").write_text(json.dumps({
        "durationInFrames": st["total"],
        "baitFrames": min(st["total"], round(BAIT_SECONDS * ch.fps)),
        "hook": clip.hook or "", "emoji": clip.emoji}))
    comps = ["Chat"] + (["Bait"] if clip.hook else []) \
        + [c["id"] for c in st.get("story_cards", [])]
    for comp in comps:
        _render_comp(comp, st["overlays"], ch.fps)


def _render_comp(comp, out_dir, fps):
    """Remotion cannot write alpha from the CLI here: prores 4444 yields
    yuv422p12le with no alpha plane. `--sequence --image-format=png` then our
    own qtrle encode is the route that works."""
    seq = Path("/private/tmp/claude-501/remotion-seq") / comp
    if seq.exists():
        subprocess.run(["rm", "-rf", str(seq)], check=True)
    seq.mkdir(parents=True)
    subprocess.run(["npx", "remotion", "render", "src/index.ts", comp, str(seq),
                    "--sequence", "--image-format=png", "--concurrency=4",
                    f"--browser-executable={CHROME_APP}", "--log=error"],
                   cwd=VENDOR, check=True)
    n = len(list(seq.glob("*.png")))
    dst = out_dir / f"rm_{comp}.mov"
    # Remotion zero-pads to the SEQUENCE's width, so the pattern depends on
    # the frame count and cannot be hardcoded to %d.
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", str(fps),
                    "-i", str(seq / f"element-%0{len(str(n-1))}d.png"),
                    "-c:v", "qtrle", "-pix_fmt", "argb", str(dst)], check=True)
    subprocess.run(["rm", "-rf", str(seq)], check=True)
    log(f"  {comp}: {n} frames -> {dst.name}")


# ----------------------------------------------------------- assemble ----
def stage_assemble(clip, ch, st):
    r = connect(); r.OpenPage("edit")
    proj = r.GetProjectManager().GetCurrentProject()
    mp = proj.GetMediaPool()
    tl = proj.GetCurrentTimeline()
    fps = ch.fps
    start = tl.GetStartFrame()
    # THE PICTURE IS WHAT V1 HOLDS, and the overlays are cut to it. Sizing
    # them from `round(out_dur * fps)` instead let them hang 2 frames past
    # V1, and a frame with an overlay and no picture under it renders black.
    v1 = sorted(tl.GetItemListInTrack("video", 1) or [], key=lambda i: i.GetStart())
    total = v1[-1].GetEnd() - v1[0].GetStart()
    if total != st["total"]:
        log(f"  picture is {total} frames, not round(out_dur*fps)="
            f"{st['total']} — overlays cut to the picture")
    st["total"] = total
    # render() appends a job every call and never clears one; a stale job
    # whose output exists is what wedged the API on an overwrite dialog.
    for j in (proj.GetRenderJobList() or []):
        proj.DeleteRenderJob(j["JobId"])
    stale = []
    for t in range(3, tl.GetTrackCount("video") + 1):
        stale += tl.GetItemListInTrack("video", t) or []
    stale += tl.GetItemListInTrack("audio", 2) or []
    if stale:
        tl.DeleteClips(stale)

    # Two sounds, one meaning each: `paper` when the chat panel settles in,
    # `shutter` when a photo card lands.
    cues = []
    wins = st.get("chat_windows")
    if not wins and (PUBLIC / "chat_windows.json").exists():
        # the chat stage ran in an earlier invocation; its windows are the
        # truth about when the box arrives, so read them rather than
        # silently shipping no cue (which is what the first run did)
        wins = json.loads((PUBLIC / "chat_windows.json").read_text())
    for w in (wins or []):
        # NO CUE ON A WINDOW THAT STARTS WITH THE CLIP. George, twice on this
        # opening and the second time precisely: *"should remove the 'uhh'."*
        # There is no "uhh" in the speech — the source between the in-point
        # and "guys" is digital zero. **The "uhh" IS this cue.** Measured on
        # the delivered file, the first 0.24s is exactly the paper envelope,
        # -27.1 dB decaying to -56.2, and no speech starts until 0.26s: a
        # soft low noise burst with a 120 Hz thud in it, alone at the top of
        # a clip, reads as a voice clearing its throat.
        #
        # It also marks nothing. The standing rule is no sound without a
        # VISIBLE event, and at frame 0 every element arrives at once — the
        # chat is not "settling in", the clip is starting. A cue for that is
        # a cue for nothing.
        if w["from"] > CUE_SILENT_HEAD:
            cues.append(Cue(w["from"] + 0.02, "paper",
                            cue_gain_peak("paper", -13.0, MASTER_GAIN),
                            "the chat box settles in"))
        else:
            log(f"  no entrance cue: the chat is up from {w['from']:.2f}s, "
                f"so it marks the clip starting rather than the box arriving")
    shut = cue_gain_peak("shutter", -9.5, MASTER_GAIN)
    for c in _all_cards(clip, st):
        cues.append(Cue(c["at"] + 0.04, "shutter", shut, f"{c['id']} lands"))

    # THE BOOM GOES ON THE ZOOM. By RMS, not peak — its crest is 7.7 dB
    # against the shutter's 22.0, so matching peaks would put it far louder
    # in the ear. -26 dBFS RMS sits it above the ticks (-40) and below the
    # speech, and it is verified in the BED after mixing, never from the
    # generator.
    boom = cue_gain("vine_boom", BOOM_RMS, MASTER_GAIN)
    # Read them off disk when the punch stage did not run in THIS
    # invocation. Exactly the failure the chat windows had: a stage's
    # output living only in memory means a partial run silently drops it,
    # and `cues: 0` is not loud enough to notice.
    starts = st.get("punch_starts")
    if starts is None:
        pj = st["overlays"] / "punches.json"
        starts = json.loads(pj.read_text()).get("applied", []) if pj.exists() else []
    for t in starts:
        cues.append(Cue(round(t, 3), "vine_boom", boom,
                        f"the facecam punches in at {t:.2f}s"))
    # FIRE EACH CUE EARLY BY ITS OWN PERCEPTUAL LEAD. See
    # `sfx.perceptual_lead`: a cue is heard where its ENERGY arrives, not
    # where its file starts, and the Vine Boom reaches 10% of its energy at
    # 108 ms. Clicks measure 0.4-5.6 ms and are unaffected, so this is one
    # rule rather than a table.
    cues = [dataclasses.replace(
                c, at=round(max(0.0, c.at - perceptual_lead(c.name)), 3))
            for c in cues]
    log(f"  cue leads: " + ", ".join(
        f"{n} {perceptual_lead(n)*1000:.0f}ms"
        for n in sorted({c.name for c in cues})))
    log(f"  sfx: {bed(cues, total / fps, out=st['overlays'] / 'sfx.wav')}")

    names = ["cap_kin.mov", "sfx.wav", "rm_Chat.mov"]
    if clip.hook:
        names.append("rm_Bait.mov")
    names += [f"rm_{c['id']}.mov" for c in _all_cards(clip, st)]
    have = [n for n in names if (st["overlays"] / n).exists()]
    r.GetMediaStorage().AddItemListToMediaPool(
        [str(st["overlays"] / n) for n in have])
    # MATCH THE POOL BY FILE PATH, NEVER BY NAME.
    #
    # Every clip writes its overlays as `rm_Chat.mov`, `cap_kin.mov`,
    # `sfx.wav` into its OWN directory, and they all land in one shared
    # Resolve media pool. Keyed by name, `{c.GetName(): c}` keeps whichever
    # was added last — so a clip that builds no chat of its own silently
    # picks up the PREVIOUS clip's.
    #
    # That is exactly what shipped: clip 12's chat overlay was refused by the
    # topicality gate and never rendered, and the delivered file carried
    # CLIP 6's chat — real viewers' messages from a different part of the
    # stream, on the wrong lines, ending at 38.3s because that is how long
    # clip 6 is. George saw it as "the chat kind of dies at the end".
    # The pool held FIVE `rm_Chat.mov` entries at the time, and seven
    # `cap_kin.mov`.
    want = {str((st["overlays"] / n).resolve()): n for n in have}
    pool = {}
    for c in mp.GetRootFolder().GetClipList():
        fp = c.GetClipProperty("File Path")
        if fp and str(Path(fp).resolve()) in want:
            pool[want[str(Path(fp).resolve())]] = c
    missing = [n for n in have if n not in pool]
    if missing:
        raise RuntimeError(f"not in the media pool by path: {missing}")
    log(f"  overlays resolved by path: {sorted(pool)}")

    def frames_of(name):
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
             "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0",
             str(st["overlays"] / name)], capture_output=True, text=True).stdout.strip()
        return int(out) if out.isdigit() else None

    ents = []

    def add(name, at, dur, track, media=1):
        it = pool.get(name)
        if it is None:
            return
        n = round(dur * fps)
        # A clip Resolve trims short loses the END OF ITS EXIT, which is the
        # jolt the exit exists to remove. Take the length from the FILE.
        f = frames_of(name)
        if f and f < n:
            n = f
        ents.append({"mediaPoolItem": it, "startFrame": 0, "endFrame": n,
                     "recordFrame": start + round(at * fps),
                     "trackIndex": track, "mediaType": media})

    # V1 content | V2 facecam | V3 chat | V4 cards | V5 titles | V6 captions
    add("rm_Chat.mov", 0.0, total / fps, 3)
    for c in _all_cards(clip, st):
        add(f"rm_{c['id']}.mov", c["at"],
            c.get("dur", STORY_FRAMES / fps), 4)
    if clip.hook:
        add("rm_Bait.mov", 0.8, min(BAIT_SECONDS, total / fps - 0.8), 5)
    add("cap_kin.mov", 0.0, total / fps, 6)
    add("sfx.wav", 0.0, total / fps, 2, media=2)
    placed = mp.AppendToTimeline(ents)
    log(f"  appended {len(placed or [])} of {len(ents)}: " +
        " ".join(f"V{t}:{len(tl.GetItemListInTrack('video', t) or [])}"
                 for t in range(3, 7)))


# -------------------------------------------------------------- punch ----
def stage_punch(clip, ch, st):
    import resolve_punch as rp
    r = connect(); r.OpenPage("edit")
    proj = r.GetProjectManager().GetCurrentProject()
    tl = proj.GetCurrentTimeline(); mp = proj.GetMediaPool()
    start = tl.GetStartFrame()
    v1 = sorted(tl.GetItemListInTrack("video", 1) or [], key=lambda i: i.GetStart())
    v2 = sorted(tl.GetItemListInTrack("video", 2) or [], key=lambda i: i.GetStart())
    item = v1[0].GetMediaPoolItem()
    # The base shots come off V1, never V2: a second run would otherwise take
    # the already-split pieces as its base shots and punch the punches.
    segs = [((it.GetStart() - start) / ch.fps,
             (it.GetEnd() - it.GetStart()) / ch.fps,
             it.GetLeftOffset() / ch.fps) for it in v1]
    # the SAME grouping the cut used, recomputed from the placed items so the
    # two stages cannot drift
    sidx = _shot_index([d for _o, d, _s in segs])
    nshots = sidx[-1] + 1 if sidx else 1
    # Measure the CLEAN CUT, never the last delivery — see AGENTS.md.
    anchors = _emphasis_anchors(clip, ch, st)
    # off disk when the cut stage did not run in THIS invocation — a
    # partial run is the normal way this pipeline is driven
    out_dur = st.get("out_dur") or sum(k.length for k in st["keeps"])
    budget = rp.boom_budget(out_dur)
    gwords = _cut_words(clip, st)
    gated: list = []
    auto_base, auto = rp.bold_moments(
        _cut_audio(clip, ch, st), anchors=anchors, limit=budget,
        words=gwords, on_gate=lambda t, d, why: gated.append((t, d, why)))
    log(f"  baseline {auto_base:.1f} dBFS; {len(anchors)} emphasised cards to "
        f"anchor to; budget {budget} "
        f"({out_dur:.1f}s / one per {rp.BOOM_EVERY:.0f}s)")
    base, moments = auto_base, auto
    if clip.booms is not None:
        # PRINT BOTH. The automatic pick and the human's are two numbers that
        # are supposed to agree, and this file's recurring defect is two such
        # numbers drifting with nothing saying so.
        base, moments = rp.bold_moments(_cut_audio(clip, ch, st),
                                        anchors=anchors, keep=clip.booms)
        log(f"  spec overrides the pick: {[t for t, _ in moments]} "
            f"(automatic would be {[t for t, _ in auto]})")
        for t, d in moments:
            if d is None:
                log(f"     {t:6.2f}s  NOT near any measured candidate — "
                    f"taken literally")
    for t, d, (word, dist, anchor) in gated:
        log(f"     gated {t:6.2f}s +{d} dB on {anchor!r} — "
            f"{word!r} {dist} word(s) ahead demotes the clause")
    for t, d in moments:
        log(f"     {t:6.2f}s  " + (f"+{d} dB" if d is not None else "(spec)"))
    if not moments:
        log("     none — no loud moment sits on one of the clip's own "
            "thesis words, so it gets no punches and no booms")
    # THE MOMENTS ARE THEIR OWN PHRASE STARTS. Passing the raw card list here
    # undid the attack refinement and silently lost a punch: once a moment is
    # moved off its card onto the stressed syllable it is no longer IN that
    # list, so `open_at` snapped it back to the PREVIOUS card — clip 12's
    # middle boom was pulled from 12.78 to 9.35 and merged away, delivering
    # two booms where the plan printed three. Passing the moments themselves
    # makes `open_at` return `t - 0.05`, which is the small pre-roll the zoom
    # wants and still inside the boom's own 15 ms attack.
    pieces = rp.split(segs, moments, shot_of=sidx,
                      phrase_starts=[t for t, _d in moments])
    tl.DeleteClips(v2)
    canvas = Frame(1080, 1920, 1920, 1080)
    rects = framings(nshots, _cam(clip, ch, st))
    ents = [{"mediaPoolItem": item, "startFrame": round(s0 * ch.fps),
             "endFrame": round(s0 * ch.fps) + round(d * ch.fps),
             "recordFrame": start + round(o0 * ch.fps),
             "trackIndex": 2, "mediaType": 1}
            for o0, d, s0, _i, _p in pieces]
    mp.AppendToTimeline(ents)
    seam_y = ch.seam * canvas.canvas_h
    items = sorted(tl.GetItemListInTrack("video", 2) or [], key=lambda i: i.GetStart())
    for it, (o0, d, _s, idx, isp) in zip(items, pieces):
        rect = rects[sidx[idx]]
        if isp:
            rect = rp.inset(rect, rp.PUNCH_INSET)
        apply(it, plan(canvas, rect, (0, 0, 1080, seam_y)))
        if ch.grade:
            it.SetCDL(ch.grade)
    # THE BOOM GOES ON THE MOMENT, NOT ON THE PIECE. They were the same
    # value until a punch was allowed to open early to find room; now a
    # piece can start up to PUNCH_BACKOFF before the word, and a cue there
    # would be exactly the "too late"/"too early" complaint in reverse.
    _starts = []
    for o0, d, _s, _i, p in pieces:
        if not p:
            continue
        near = [t for t, _x in moments if o0 - 0.02 <= t <= o0 + d]
        _starts.append(round(min(near) if near else o0, 3))
    st["punch_starts"] = _starts
    (st["overlays"] / "punches.json").write_text(json.dumps(
        {"punches": [t for t, _d in moments], "zoom": round(1/(1-rp.PUNCH_INSET), 3),
         "applied": [round(o0, 2) for o0, _d, _s, _i, p in pieces if p]}, indent=1))
    log(f"  V2 {len(segs)} splices in {nshots} shots -> {len(pieces)} pieces "
        f"({sum(1 for *_x, p in pieces if p)} punched at "
        f"{1/(1-rp.PUNCH_INSET):.3f}x)")


# ------------------------------------------------------------- render ----
def stage_render(clip, ch, st):
    from engine.render_ffmpeg import _finish_audio, house_eq
    r = connect()
    proj = r.GetProjectManager().GetCurrentProject()
    for j in (proj.GetRenderJobList() or []):
        proj.DeleteRenderJob(j["JobId"])
    tag = clip.slug
    raw = ROOT / f"renders/{tag}_src.mov"
    raw.unlink(missing_ok=True)
    tl = proj.GetCurrentTimeline()
    v1 = sorted(tl.GetItemListInTrack("video", 1) or [], key=lambda i: i.GetStart())
    # MARK THE PICTURE, do not render "all frames". The timeline is as long
    # as its LONGEST track, so an overlay that outruns V1 adds frames with
    # nothing under them and those render BLACK.
    #
    # **`MarkIn` RENDERS ONE FRAME BEFORE THE MARK.** Measured on this
    # timeline: marking [216000..218586] gave 2587 frames whose frame 0 was
    # pure black (timeline 215999, where nothing is), and marking
    # [216001..218587] gave a frame 0 of real picture. So the mark is
    # shifted by one, and the clip opened on a black frame until it was.
    # The tail is then handled where it always was — `-frames:v` on the
    # delivery, trimming to the PICTURE count.
    picture = v1[-1].GetEnd() - v1[0].GetStart()
    st["total"] = picture
    mark_in, mark_out = v1[0].GetStart() + 1, v1[-1].GetEnd() + 1
    proj.LoadRenderPreset("H.264 Master")
    proj.SetRenderSettings({"TargetDir": str(ROOT / "renders"),
                            "CustomName": f"{tag}_src",
                            "MarkIn": mark_in, "MarkOut": mark_out,
                            "SelectAllFrames": False})
    job = proj.AddRenderJob(); proj.StartRendering([job])
    t0 = time.time()
    while proj.IsRenderingInProgress():
        time.sleep(1)
    log(f"  resolve render {time.time()-t0:.0f}s")
    eq, mid = ROOT / "renders/_eq.mov", ROOT / "renders/_mid.mp4"
    # MEASURE THE RUMBLE ON THE SPEECH, NOT ON THE MASTER. `raw` already has
    # the sfx bed mixed in on A2, and a Vine Boom reads as rumble — measuring
    # there would keep the high-pass on BECAUSE the boom is there, and then cut
    # the boom. `base_wav` is the cut speech with no bed and no loudnorm.
    EQ, m = house_eq(_cut_audio(clip, ch, st))
    log(f"  voice chain: sub-85 {m['rumble_dbfs']} dBFS vs body "
        f"{m['body_dbfs']} ({m['margin_db']:+.1f} dB) -> "
        f"high-pass {'ON' if m['highpass'] else 'OFF'}")
    # PAD THE AUDIO TRIM, OR THE LAST WORD'S RELEASE IS CUT OFF.
    # `-t` here exists to drop overlay frames that outran V1 and render
    # black — a PICTURE concern, which `-frames:v` on the delivery already
    # handles. Applying it to the audio as well is what George heard as
    # "ends midway though tragic": the last keep is 0.390s, which is 23.4
    # frames, so the picture holds 23 (0.3833s) while the word's release
    # needs the full 0.390. Measured, the Resolve render's audio ran to
    # 45.888s and ended on the decay at -53 dB — complete — and this trim
    # cut it to 45.833s, ending it at -21 dB, mid-word. Three frames of pad
    # costs nothing: the muxer stops at the last video frame anyway.
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(raw),
                    "-t", f"{(st['total'] + 3)/ch.fps:.4f}", "-af", EQ,
                    "-c:v", "libx264", "-crf", "17", "-preset", "medium",
                    "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", str(eq)], check=True)
    # Loudness is finished HERE, not in Resolve: NormalizeAudioLevel applies
    # gain without true-peak limiting, so the lift to -14 would clip.
    # ASK FOR -1.5 TO DELIVER -1.0. The ceiling is hard (-1.0 dBTP), and
    # loudnorm hits its target on the PCM it limits — but the delivery is AAC,
    # and AAC decode overshoots: a -1.0 request has measured -0.64 and -0.77
    # on this clip, and once the boom went to the event tier it measured
    # -0.41 and the gate rejected the render. The overshoot is the codec's,
    # not the mix's, so the request carries the headroom rather than the cue
    # being backed off to hide it.
    _finish_audio(eq, {"audio": {"target_lufs": -14.0, "true_peak_dbtp": -1.5},
                       "render": {"audio_codec": "aac"}}, mid)
    out = ROOT / f"renders/{tag}.mp4"
    # `-frames:v` BOUNDS THE AUDIO TOO, and that is the other half of
    # "ends midway though tragic". It stops ffmpeg reading once the video
    # stream is done, so the audio is cut to the picture however long the
    # release is — measured, the Resolve render ended the word cleanly at
    # -53 dB and this step delivered it at -14 dB, 67 ms short.
    #
    # The note that put `-frames:v` here was about `-t` cutting at a
    # KEYFRAME, which is true of `-c:v copy` and not of this step: it
    # re-encodes, so `-t` is frame-accurate. The picture is already bounded
    # by the render marks and by the EQ step, so three frames of slack here
    # costs nothing and `black_top`/`black_bottom` would catch it if it did.
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mid),
                    "-t", f"{(st['total'] + 3)/ch.fps:.4f}",
                    "-c:v", "libx264", "-crf", "18",
                    "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "copy",
                    "-movflags", "+faststart", str(out)], check=True)
    eq.unlink(missing_ok=True); mid.unlink(missing_ok=True)
    st["out"] = out
    # THE DELIVERY GATE, on the artifact. `qc.check` judges a render
    # generically; this judges a clip the way we build them, and every check
    # in it exists because something got past and reached George.
    from engine import deliver_qc
    from engine.resolve_captions import cards as _cards
    from engine.tighten import remap_card as _remap
    absent = qc.dead_audio(clip.source(ROOT), min_run=0.1)["runs"]
    cs, _dropped = _drop_hallucinated(_cards(st.get("words") or []), absent) \
        if st.get("words") else ([], [])
    placed = []
    for c in cs:
        r = _remap(c.start, c.end, st["keeps"])
        if r:
            placed.append({"start": r[0], "end": r[1], "text": c.text})
    rep = deliver_qc.check(out, cards=placed or None, absent=[] if placed else None,
                           seam=ch.seam)
    log(rep.text())
    st["qc"] = rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--only", default=",".join(STAGES))
    a = ap.parse_args()
    clip, ch = load(a.spec)
    want = [s for s in a.only.split(",") if s]
    bad = set(want) - set(STAGES)
    if bad:
        sys.exit(f"unknown stage(s) {sorted(bad)}; pick from {list(STAGES)}")

    overlays = ROOT / f"jobs/{clip.job}/overlays_{clip.index:02d}"
    overlays.mkdir(parents=True, exist_ok=True)
    ranked = json.loads((ROOT / f"jobs/{clip.job}/ranked.json").read_text())
    st = {"overlays": overlays, "meta": ranked[clip.index - 1],
          "base_wav": ROOT / f"jobs/{clip.job}/overlays_{clip.index:02d}/_cut.wav"}
    log(f"=== {clip.slug} / channel {ch.name} ===")
    log(f"    {st['meta']['subject']}")

    # captions needs the words and the keeps; chat needs the keeps. Stages
    # run in order and share `st`, so a partial run has to rebuild what it
    # depends on — cheap, because the expensive parts are Resolve and
    # Remotion, not these.
    for s in STAGES:
        if s not in want:
            if s == "cut" and any(x in want for x in
                                  ("captions", "chat", "punch", "assemble",
                                   "render")):
                log("[cut] (re-planning, not rebuilding — needed downstream)")
                _plan_only(clip, ch, st)
            continue
        log(f"[{s}]")
        globals()[f"stage_{s}"](clip, ch, st)
    log("done.")


def _plan_only(clip, ch, st):
    """The cut's PLAN without touching Resolve.

    **ONE IMPLEMENTATION, called by both paths.** This was a second copy of
    `stage_cut`'s planning block, and within one round they diverged: the
    out-point word-end snap went into `stage_cut` only, so a `--only render`
    run planned a different cut than the full build had just rendered. That is
    the same shape as the punch plan being measured from the overwritten
    delivery, and as `_cut.wav` being cached — two numbers that are supposed to
    be the same number, derived twice.
    """
    src = clip.source(ROOT)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
         "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(src)],
        capture_output=True, text=True).stdout.strip()
    src_dur = int(probe) / ch.fps
    # Dead air is BOTH kinds: digital zero (the Twitch mutes) and ordinary
    # room tone. A fixed dBFS floor means something different on every clip
    # because raw VOD audio runs ~7 dB under target, so `quiet_runs` measures
    # against the speaker's own level.
    absent = qc.dead_audio(src, min_run=0.3)["runs"]
    quiet = qc.quiet_runs(src, min_run=MIN_DEAD)["runs"]
    words = [w for u in json.loads(clip.words(ROOT).read_text())["utterances"]
             for w in u["words"]]
    # ORDER MATTERS. Skip the uncaptionable word FIRST, then snap onto the new
    # word's onset, then take the lead-in — snapping before skipping would
    # refine a point we are about to abandon.
    ip0, skipped = _open_on_captionable(words, clip.in_point,
                                        qc.dead_audio(src, min_run=0.1)["runs"])
    ip, snap = _snap_in_point(src, ip0)
    ip, lead, lead_absent = _lead_in(src, ip)
    op, osnap = _snap_out_point(words, clip.out_point, absent, src=src)
    dead = sorted([r for r in absent + quiet if r[0] >= ip])
    spans = removals(dead, src_dur, min_remove=MIN_DEAD, beat=BEAT)
    kp = _clamp_out_point(_clamp_in_point(keeps(spans, src_dur), ip), op)
    st["keeps"] = kp
    st["out_dur"] = sum(k.length for k in kp)
    st["total"] = round(st["out_dur"] * ch.fps)
    st["base_wav"].parent.mkdir(parents=True, exist_ok=True)
    return {"src": src, "src_dur": src_dur, "in_point": ip, "out_point": op,
            "snap": snap, "out_snap": osnap, "spans": spans, "words": words,
            "skipped": skipped, "lead": lead, "lead_absent": lead_absent}


if __name__ == "__main__":
    main()
