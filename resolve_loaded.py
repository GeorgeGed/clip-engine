"""Assemble the loaded cut on the Resolve timeline.

    V1 content (exhibit punches)   V5 exhibit cards + the tweet
    V2 facecam (colour arc)        V6 act cards
    V3 seam rule + vignette        V7 captions
    V4 sweeps + dips               A2 sound

The colour ARC is the part that cannot be done with one grade: Resolve has
no keyframe API, but `SetCDL` per CLIP does work, and the cut is already in
11 segments — so the grade can change by act even though it cannot ramp.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from engine.resolve_driver import connect
from engine.sfx import Cue, bed, cue_gain
from build_loaded import CUTS, ACTS

FPS = 60
OUT = ROOT / "jobs/fns-2905408276/overlays"
MASTER_GAIN, TARGET_RMS = 6.2, -29.0

# Three acts, three grades. Cool and flat while he lays out the news; the
# house grade through the argument; warm and rich on the cost.
GRADES = [
    (0.0, 17.55, {"NodeIndex": "1", "Slope": "1.02 1.03 1.09",
                  "Offset": "-0.008 -0.008 0.005", "Power": "1.09 1.09 1.06",
                  "Saturation": "0.92"}),
    (17.55, 35.92, {"NodeIndex": "1", "Slope": "1.06 1.06 1.07",
                    "Offset": "-0.012 -0.012 -0.010", "Power": "1.06 1.06 1.06",
                    "Saturation": "1.18"}),
    (35.92, 99.0, {"NodeIndex": "1", "Slope": "1.12 1.07 0.99",
                   "Offset": "-0.015 -0.012 -0.008", "Power": "1.03 1.05 1.09",
                   "Saturation": "1.30"}),
]

# Exhibit cards and the tweet keep their anchors from build_overlays.
from build_overlays import PLAN as OPLAN

CARDS = {o["name"]: o for o in OPLAN}


def main():
    r = connect(); r.OpenPage("edit")
    p = r.GetProjectManager().GetCurrentProject()
    tl = p.GetCurrentTimeline(); mp = p.GetMediaPool()
    s = tl.GetStartFrame()
    total = tl.GetEndFrame() - s
    print(f"timeline {tl.GetName()}  {total} frames ({total/FPS:.2f}s)")

    while tl.GetTrackCount("video") < 7:
        tl.AddTrack("video")
    while tl.GetTrackCount("audio") < 2:
        tl.AddTrack("audio")

    stale = []
    for t in range(3, 8):
        stale += tl.GetItemListInTrack("video", t) or []
    stale += tl.GetItemListInTrack("audio", 2) or []
    if stale:
        tl.DeleteClips(stale)
    print(f"cleared {len(stale)} clips from V3-V7 and A2")

    # ---- the colour arc, per clip on the facecam ------------------------
    v2 = sorted(tl.GetItemListInTrack("video", 2) or [], key=lambda i: i.GetStart())
    t = 0.0
    for it in v2:
        dur = (it.GetEnd() - it.GetStart()) / FPS
        mid = t + dur / 2
        g = next(g for a, b, g in GRADES if a <= mid < b)
        it.SetCDL(g)
        t += dur
    print(f"graded {len(v2)} facecam shots across {len(GRADES)} acts")

    # ---- sound: one cue per sweep, but not two inside 2.5s --------------
    gain = cue_gain("thunk", TARGET_RMS, MASTER_GAIN)
    cues, last = [], -9.0
    for c in CUTS:
        if c - last >= 2.5:
            cues.append(Cue(c, "thunk", gain, f"light sweep on the cut at {c:.2f}s"))
            last = c
    for nm in ("tweet", "strip1", "strip2", "kru"):
        o = CARDS.get(nm)
        if o:
            cues.append(Cue(o["at"] + 0.02, "thunk", gain, f"{nm} card arrives"))
    cues.sort(key=lambda c: c.at)
    wav = OUT / "sfx.wav"
    print("sfx:", bed(cues, total / FPS, out=wav))

    # ---- import everything ----------------------------------------------
    names = ["seam.mov", "sweep.mov", "dip.mov", "cap_kin.mov", "sfx.wav",
             "tweet.mov", "strip1.mov", "strip2.mov", "kru.mov",
             "act0.mov", "act1.mov", "act2.mov"]
    r.GetMediaStorage().AddItemListToMediaPool([str(OUT / n) for n in names])
    pool = {c.GetName(): c for c in mp.GetRootFolder().GetClipList()}

    def fr(sec):
        return s + int(round(sec * FPS))

    ents = []

    def add(name, at, dur, track, media=None):
        c = pool.get(name)
        if c is None:
            print(f"  !! {name} missing from the media pool"); return
        e = {"mediaPoolItem": c, "startFrame": 0,
             "endFrame": int(round(dur * FPS)), "recordFrame": fr(at),
             "trackIndex": track}
        if media:
            e["mediaType"] = media
        ents.append(e)

    add("seam.mov", 0.0, total / FPS, 3)
    for c in CUTS:
        add("sweep.mov", max(0.0, c - 0.10), 0.20, 4)
    for d in (12.03, 17.27, 31.55, 35.64):
        add("dip.mov", d, 0.567, 4)
    for nm in ("tweet", "strip1", "strip2", "kru"):
        o = CARDS.get(nm)
        if o:
            add(f"{nm}.mov", (3.30 if nm == "tweet" else o["at"]), o["dur"], 5)
    for i, (at, hold, _l1, _l2) in enumerate(ACTS):
        add(f"act{i}.mov", at, hold, 6)
    add("cap_kin.mov", 0.0, total / FPS, 7)
    add("sfx.wav", 0.0, total / FPS, 2, media=2)

    placed = mp.AppendToTimeline(ents)
    print(f"appended {len(placed or [])} of {len(ents)}")
    for t_ in range(3, 8):
        its = tl.GetItemListInTrack("video", t_) or []
        print(f"  V{t_}: {len(its)} clips")
    print(f"  A2: {len(tl.GetItemListInTrack('audio', 2) or [])} clips")
    print(f"  timeline now {(tl.GetEndFrame()-s)/FPS:.2f}s")


if __name__ == "__main__":
    main()
