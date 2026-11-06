#!/usr/bin/env python3
"""Which clips are worth building. Run this BEFORE picking anything.

George: *"I want to mass produce these clips for different channels. So
figure out how you can kind of do that from here."*

The bottleneck is not rendering, it is CHOOSING. Ranking by virality alone
picks clips the pipeline cannot cut: measured on this VOD's top ten, **only
three survive tightening** — the rest are 32-44% DMCA-muted, and removing
that much leaves a clip spliced every three seconds. The second clip chosen
by virality (file 07, the best chat burst in the set at x4.83) had to be
abandoned after it cut to 36.2s in 13 shots at 19.9 cuts/min.

So this screens on what actually decides whether a clip can be built:

  MUTING      the share of the clip with absent audio. Over ~25% and
              tightening it means splicing across speech nobody can hear
              every few seconds.
  CADENCE     cuts/min after tightening. R1 runs 6.0; clip 8 shipped at
              12.8 and that was already called twice the reference. Over
              ~15 is a strobe.
  CHAT        resting rate, the clip's own rate, and the bursts — which
              decides whether the overlay is a RESTING STATE or a REACTION,
              and tells you whether there is any reaction to show.
  FACECAM     detected per clip, with the confidence. Low confidence means
              look at the frame before building.

It prints a verdict per clip and the reason. Nothing here is a taste
judgement: the editorial call (is this clip ABOUT one thing, does it
explain itself) is still a human reading the subject line.

    ./.venv/bin/python screen_clips.py fns-2905408276            # top 12
    ./.venv/bin/python screen_clips.py fns-2905408276 --n 50 --chat
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from engine import qc, facecam                                   # noqa: E402
from engine import chat_reaction as cr                           # noqa: E402
from engine.tighten import removals, keeps                       # noqa: E402

MAX_MUTED = 0.25
MAX_CUTS_MIN = 15.0
MIN_SECONDS = 20.0
# THE REGION IS NOT THE CLIP, AND MEASURING IT AS IF IT WERE THREW AWAY 21
# BUILDABLE CLIPS.
#
# George: *"are we sure those clips were refused? because they were good."*
# He named clip 01 — "speaker reveals he is coaching a team in the open
# qualifier" — which scored 63 and was refused at 43% muted.
#
# He is right, and the defect is that this file measured the whole candidate
# REGION. A clip is a cut: an in-point and an out-point inside that region.
# This project's own history is nothing but that — clip 8's in-point moved to
# 8.85s and "also dropped 4.2s of mute that sat in those 9s", clip 12's to
# 23.30, clip 16's to 7.58. Moving the in-point is HOW mutes get dropped, and
# the screen refused the clip before anyone was allowed to do it.
#
# Measured across the 40 refusals: **21 contain a contiguous window that
# passes this same gate on its own.** Clip 01's seconds 72-101 are **18%
# muted at 14.7 cuts/min** — cleaner than clip 08 (21%), which shipped and
# was accepted, and identical to clip 12 (18%).
#
# Be straight about the quality spread: of the 21, four are comfortably clean
# (01 at 18%, 25 at 17%, 33 at 14%, 47 at 18%) and seventeen sit at 23-25%,
# right on the limit. The gate is the same one the ten survivors passed, so
# they are no worse than what already ships — but "buildable" is not "good".
# Whether a window is ONE NARRATIVE and explains itself is still the
# editorial pass's call, and that has not changed.
WINDOW_STEP = 0.5          # the scan resolution, in seconds
MIN_WINDOW = 25.0          # shorter than this is not worth a search
# A CLEAN WINDOW IS NOT A CLIP, and the first version of this proved it the
# expensive way. Clip 01 — the one George named — was rescued at 72-101s,
# built, and passed every gate: 21.0s, -13.91 LUFS, no absent audio, no
# hallucinated captions. Then read the cut:
#
#   "we'll see we'll see how that goes so yeah the problem is how am i
#    supposed to stream league of legends worlds if the qualifiers..."
#
# The clip's claim is *"I'm gonna be coaching in the open qualifier and
# we're gonna be streaming it"* and **that line is not in the cut.** The
# window found clean audio somewhere else in the region. It opens on a
# trailing fragment, it is about a different subject, and every piece of
# metadata keyed to the region — subject, hook, the emphasis anchors the
# captions and the boom use — still describes the clip it is no longer.
#
# This is the category error this file keeps recording: an ACOUSTIC
# measurement making an EDITORIAL decision. Measured across the 21 rescued
# clips, by how many of the claim's own content words survive the window:
#
#   0%, 0%, 0%, 11%  |  40%, 43%  |  50% and up, fifteen of them
#
# Four lose the point outright. The gap between 11% and 40% is wide, so the
# threshold is a plateau rather than an edge — anything in (0.11, 0.40]
# drops exactly those four, and 0.25 is the middle of it.
CLAIM_KEEP = 0.25
# THE OPENINGS ARE STILL WRONG AND SNAPPING TO UTTERANCES DOES NOT FIX THEM.
#
# Most of the rescued cuts open mid-clause — *"were paying good money,
# decent money for sure..."*, *"um see it as a better system but..."* —
# which is rule 3 and the "as I was saying" opening. The obvious mechanical
# fix is to make the candidate in-points UTTERANCE STARTS instead of a
# half-second grid. **It was tried and it was worse on both axes: 17
# windowed clips became 3, and the three still opened mid-sentence.**
#
# The reason is already in AGENTS.md: whisper's VAD merges utterances on
# this VOD and the median inter-word gap measures 0.000s, so there are
# barely any boundaries to snap to and the few that exist are not sentence
# starts. The utterance list is the only phrase signal available AND it is
# too coarse to carry this.
#
# So the opening stays an EDITORIAL problem, which is what this file has
# said about rules 2 and 3 all along. The window makes a clip CUTTABLE; a
# human or a Tier 3 pass still has to choose where it starts.
_STOP = frozenset(
    "about above after again against because before being below between could doing during "
    "each from further having into itself might more most other over same should some such "
    "than that their them then there these they this those through under until very were "
    "what when where which while will with would your gonna really thing things".split())


def _keys(*texts) -> set:
    """The clip's own content words — the same shape `emphasis_keys` uses."""
    out = set()
    for s in texts:
        out |= {w for w in re.findall(r"[a-z']+", (s or "").lower())
                if len(w) >= 5 and w not in _STOP}
    return out


def best_window(absent, quiet, dur, words=None, keys=None):
    """The longest contiguous window that would pass the gate on its own.

    Returns `(a, b, muted, cut_s, cuts_min, keep)` or None. Only ever called
    when the whole region FAILS, so a region that already passes keeps all of
    itself — searching a passing region could only return something shorter.

    `words` and `keys` are what stop this being an audio measurement making
    an editorial decision: a window must retain `CLAIM_KEEP` of the clip's
    own content words or it is not this clip, however clean it sounds. With
    no transcript the constraint cannot be applied and the window is refused
    rather than guessed at — see the note above for what that costs.
    """
    def kept(a, b):
        if not keys:
            return 0.0
        here = {re.sub(r"[^a-z']", "", w["text"].lower()) for w in (words or [])
                if a <= w.get("start", -1) <= b}
        have = keys & {re.sub(r"[^a-z']", "", w["text"].lower())
                       for w in (words or [])}
        return len(keys & here) / len(have) if have else 0.0
    def muted_in(a, b):
        t = sum(max(0.0, min(b, y) - max(a, x)) for x, y in absent)
        return t / (b - a) if b > a else 1.0

    best = None
    a = 0.0
    while a + MIN_WINDOW <= dur:
        w = MIN_WINDOW
        while a + w <= dur and muted_in(a, a + w) <= MAX_MUTED:
            w += WINDOW_STEP
        w -= WINDOW_STEP
        if w >= MIN_WINDOW:
            b = a + w
            sub = [(max(x, a) - a, min(y, b) - a)
                   for x, y in sorted(absent + quiet) if y > a and x < b]
            kp = keeps(removals(sub, b - a, min_remove=0.35, beat=0.12), b - a)
            out = sum(k.length for k in kp)
            cpm = (len(kp) - 1) / (out / 60) if out else 1e9
            if out >= MIN_SECONDS and cpm <= MAX_CUTS_MIN:
                k = kept(a, b)
                if k >= CLAIM_KEEP:
                    cand = (round(a, 1), round(b, 1), round(muted_in(a, b), 3),
                            round(out, 1), round(cpm, 1), round(k, 2))
                    # the window that keeps the most of the clip's own point,
                    # and only then the longest
                    if best is None or (cand[5], cand[3]) > (best[5], best[3]):
                        best = cand
        a += WINDOW_STEP
    return best


def duration(p):
    return float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(p)], capture_output=True, text=True).stdout)


def screen_one(job, n, meta, *, want_chat=False, want_cam=False):
    hits = sorted(glob.glob(str(ROOT / f"jobs/{job}/clips_1080/{n:02d}_*.mp4")))
    if not hits:
        return None
    src = Path(hits[0])
    dur = duration(src)
    absent = qc.dead_audio(src, min_run=0.3)["runs"]
    quiet = qc.quiet_runs(src, min_run=0.35)["runs"]
    muted = sum(b - a for a, b in absent) / dur
    sp = removals(sorted(absent + quiet), dur, min_remove=0.35, beat=0.12)
    kp = keeps(sp, dur)
    out = sum(k.length for k in kp)
    cpm = (len(kp) - 1) / (out / 60) if out else 0.0
    why = []
    if muted > MAX_MUTED:
        why.append(f"{muted:.0%} muted")
    if cpm > MAX_CUTS_MIN:
        why.append(f"{cpm:.0f} cuts/min")
    if out < MIN_SECONDS:
        why.append(f"only {out:.0f}s left")
    window = None
    if why:
        # The region fails. Does a WINDOW inside it pass? See the note above.
        wf = ROOT / f"jobs/{job}/words/{n:02d}.json"
        tw = None
        if wf.exists():
            tr = json.loads(wf.read_text())
            tw = [w for u in tr["utterances"] for w in u["words"]]
        kk = _keys(meta.get("claim"), meta.get("subject"))
        w = best_window(absent, quiet, dur, words=tw, keys=kk) if tw else None
        if w:
            a, b, wm, wout, wcpm, keep = w
            window = {"in": a, "out": b, "muted": wm, "cut_s": wout,
                      "cuts_min": wcpm, "keeps": keep}
            why = [f"region {' / '.join(why)} — cut to {a:.0f}-{b:.0f}s "
                   f"({wm:.0%} muted, {wcpm:.0f} cuts/min, keeps "
                   f"{keep:.0%} of the claim)"]
            muted, out, cpm = wm, wout, wcpm
    row = {"n": n, "src_s": round(dur, 1), "muted": round(muted, 3),
           "cut_s": round(out, 1), "shots": len(kp), "cuts_min": round(cpm, 1),
           "virality": round(meta.get("virality", 0), 3),
           "strength": meta.get("strength"), "subject": meta.get("subject", ""),
           "verdict": "build" if (not why or window) else "reject",
           "window": window, "why": why}
    if want_cam:
        f = facecam.detect(src)
        row["cam"] = f.rect if f else None
        row["cam_conf"] = f.margin if f else None
    if want_chat:
        cache = ROOT / f"jobs/{job}/chat_{n:02d}.json"
        if cache.exists():
            msgs = json.loads(cache.read_text())
            for m in msgs:
                m.setdefault("frags", m.get("fragments", []))
            info = cr.classify(msgs, meta["in_point"], meta["out_point"])
            row.update(chat_mode=info["mode"],
                       chat_rate=info["clip_rate"],
                       chat_rest=info["resting_rate"],
                       bursts=len(info["bursts"]),
                       best_burst=max((b.mult for b in info["bursts"]), default=0))
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("job")
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--chat", action="store_true")
    ap.add_argument("--cam", action="store_true")
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    ranked = json.loads((ROOT / f"jobs/{a.job}/ranked.json").read_text())
    order = sorted(range(len(ranked)), key=lambda i: -ranked[i].get("virality", 0))
    rows = []
    for i in order[:a.n]:
        r = screen_one(a.job, i + 1, ranked[i], want_chat=a.chat, want_cam=a.cam)
        if r:
            rows.append(r)
    hdr = f"{'clip':>4} {'vir':>5} {'str':>4} {'src':>6} {'mute':>5} {'cut':>6} {'c/min':>6}"
    if a.chat:
        hdr += f" {'chat':>11} {'burst':>6}"
    if a.cam:
        hdr += f" {'cam':>5}"
    print(hdr + "  verdict")
    for r in rows:
        line = (f"{r['n']:>4} {r['virality']:5.3f} {r['strength'] or 0:4.2f} "
                f"{r['src_s']:6.1f} {r['muted']:5.0%} {r['cut_s']:6.1f} "
                f"{r['cuts_min']:6.1f}")
        if a.chat:
            line += (f" {r.get('chat_mode','-')[:10]:>11} "
                     f"{('x%.1f' % r['best_burst']) if r.get('best_burst') else '-':>6}")
        if a.cam:
            line += f" {('%.0fx' % r['cam_conf']) if r.get('cam_conf') else '-':>5}"
        print(line + f"  {r['verdict']}" +
              (f" ({', '.join(r['why'])})" if r["why"] else ""))
    ok = [r for r in rows if r["verdict"] == "build"]
    print(f"\n{len(ok)} of {len(rows)} buildable: {[r['n'] for r in ok]}")
    for r in ok:
        print(f"   {r['n']:02d}  {r['subject'][:76]}")
    if a.json:
        Path(a.json).write_text(json.dumps(rows, indent=1))
        print(f"-> {a.json}")


if __name__ == "__main__":
    main()
