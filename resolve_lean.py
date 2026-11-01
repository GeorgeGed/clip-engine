"""The lean cut: back to what was approved, plus the colour arc and the
Impact caption style.

George: "way too much in the edit there, and didnt include the new text
style that i liked."

Dropped from the loaded version: the 10 light sweeps, the 3 act cards, and
the seam glow / vignette. Those were the overcorrection — I went from
nothing to an event every few seconds.

Kept, because each was asked for or approved:
  dip at the exhibit handoffs | exhibit cards | the KRU marker |
  the two mid-clip titles | the colour arc (a grade, not an event)

Sound goes back to 4 cues, one per card arriving, not 12.

    V1 content (exhibit punches)   V4 cards + tweet
    V2 facecam (colour arc)        V5 mid-clip titles
    V3 dips                        V6 captions, Impact      A2 sound
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from engine.resolve_driver import connect
from engine.sfx import Cue, bed, cue_gain
from build_overlays import PLAN as OPLAN

FPS = 60
OUT = ROOT / "jobs/fns-2905408276/overlays"
MASTER_GAIN, TARGET_RMS = 6.2, -29.0
CARDS = {o["name"]: o for o in OPLAN}
DIPS = (14.80, 32.92)

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


def main():
    r = connect(); r.OpenPage("edit")
    p = r.GetProjectManager().GetCurrentProject()
    tl = p.GetCurrentTimeline(); mp = p.GetMediaPool()
    s = tl.GetStartFrame(); total = tl.GetEndFrame() - s
    print(f"timeline {tl.GetName()}  {total} frames ({total/FPS:.2f}s)")

    # render() appends a job every call and never clears; a stale job whose
    # output already exists is a likely source of the overwrite dialog that
    # wedged the API last time.
    for j in (p.GetRenderJobList() or []):
        p.DeleteRenderJob(j["JobId"])
    print("cleared the render queue")

    while tl.GetTrackCount("video") < 6:
        tl.AddTrack("video")
    stale = []
    for t in range(3, tl.GetTrackCount("video") + 1):
        stale += tl.GetItemListInTrack("video", t) or []
    stale += tl.GetItemListInTrack("audio", 2) or []
    if stale:
        tl.DeleteClips(stale)
    print(f"cleared {len(stale)} clips from V3+ and A2")

    v2 = sorted(tl.GetItemListInTrack("video", 2) or [], key=lambda i: i.GetStart())
    t = 0.0
    for it in v2:
        dur = (it.GetEnd() - it.GetStart()) / FPS
        it.SetCDL(next(g for a, b, g in GRADES if a <= t + dur / 2 < b))
        t += dur
    print(f"colour arc on {len(v2)} shots")

    gain = cue_gain("thunk", TARGET_RMS, MASTER_GAIN)
    cues = [Cue(at + 0.02, "thunk", gain, f"{n} exhibit lands")
            for n, at, _d in [("tweet", 3.30, 0), ("news", 7.60, 0),
                              ("strip1", 15.08, 0), ("nrg", 24.32, 0),
                              ("kru", 33.20, 0)]]
    print("sfx:", bed(cues, total / FPS, out=OUT / "sfx.wav"))

    names = ["dip.mov", "cap_kin.mov", "sfx.wav", "tweet.mov",
             "news.mov", "strip1.mov", "nrg.mov", "kru.mov"]
    r.GetMediaStorage().AddItemListToMediaPool([str(OUT / n) for n in names])
    pool = {c.GetName(): c for c in mp.GetRootFolder().GetClipList()}

    ents = []

    def add(name, at, dur, track, media=None):
        c = pool.get(name)
        if c is None:
            print(f"  !! {name} missing"); return
        e = {"mediaPoolItem": c, "startFrame": 0, "endFrame": int(round(dur * FPS)),
             "recordFrame": s + int(round(at * FPS)), "trackIndex": track}
        if media:
            e["mediaType"] = media
        ents.append(e)

    for d in DIPS:
        add("dip.mov", d, 0.567, 3)
    # George: "i dont need random text popping up during the video makes no
    # sense." sec1/sec2 were words I wrote, not evidence — they are gone.
    # Every graphic here is now either a crop of what is on his screen or a
    # sourced fact. strip2 (the same strip a second time) is replaced by NRG,
    # a full 5/5 roster, over the line about getting signed.
    EXHIBITS = [("tweet", 3.30, 3.00), ("news", 7.60, 3.40),
                ("strip1", 15.08, 3.40), ("nrg", 24.32, 3.60),
                ("kru", 33.20, 4.40)]
    for n, at, dur in EXHIBITS:
        add(f"{n}.mov", at, dur, 4)
    add("cap_kin.mov", 0.0, total / FPS, 6)
    add("sfx.wav", 0.0, total / FPS, 2, media=2)

    placed = mp.AppendToTimeline(ents)
    print(f"appended {len(placed or [])} of {len(ents)}")
    for t_ in range(3, 7):
        print(f"  V{t_}: {len(tl.GetItemListInTrack('video', t_) or [])} clips")


if __name__ == "__main__":
    main()
