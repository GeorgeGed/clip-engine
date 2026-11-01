"""Assemble clip 08 on the Resolve timeline.

    V1 content   V2 facecam (colour arc)   V3 dips
    V4 graphics  V6 captions               A2 sound

George: "I like the fact that we're kind of having pop-ups like every other
second. I think that keeps retention quite well." Five graphics became ten,
roughly one every four seconds. Every figure is read off the board or
sourced — the density goes up and the invented text stays at zero, which is
the line he drew earlier ("i dont need random text popping up").

Everything not cropped from the footage is a Remotion composition rendered
to an alpha clip; PIL cannot make a card look designed.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from engine.resolve_driver import connect
from engine.sfx import Cue, bed, cue_gain

FPS = 60
OUT = ROOT / "jobs/fns-2905408276/overlays"
MASTER_GAIN, TARGET_RMS = 6.2, -29.0
DIPS = (14.80, 32.92)

# (clip, start seconds, duration seconds)
EXHIBITS = [
    ("rm_ChipAmer",  1.20, 1.83),   # 34/40 Americas slots filled
    ("tweet",        3.30, 3.00),   # the Global Esports announcement
    ("rm_StatCard",  7.60, 3.50),   # 10 -> 8 partner teams per region
    ("rm_Counter",  11.60, 3.50),   # 274 not yet confirmed, counting up
    ("rm_ExStrip",  15.08, 3.50),   # the board's header strip
    ("rm_Ratio",    19.40, 3.50),   # 32 open slots against 274
    ("rm_ExNrg",    24.32, 3.75),   # NRG 5/5, a full roster
    ("rm_Grid",     28.80, 4.00),   # all eight Americas teams populating
    ("rm_ExKru",    33.20, 4.50),   # KRU 1/5, with the marker
    # The three freshest facts, each through an independent verification
    # pass. Wording is the checker's, not mine: "part ways with" because no
    # org stated a reason, "five years at the org" because he was a reserve
    # for part of it. The free-agency card closes the clip on the hardest
    # fact available — it happens tomorrow.
    ("rm_NewsPrx",  37.90, 3.75),   # PRX part ways with Jinggg
    ("rm_NewsSen",  41.90, 3.50),   # Sentinels release JonahP and Jerrwin
    ("rm_NewsFA",   44.60, 2.25),   # free agency opens 2 Nov
]

# Three acts, three grades: cool and flat over the news, the house grade
# through the argument, warm on the cost. SetCDL is per CLIP, so the grade
# cannot ramp — but the cut is already 11 segments, so it can step.
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
    print(f"timeline {tl.GetName()}  {total} frames ({total / FPS:.2f}s)")

    # render() appends a job every call and never clears one; a stale job
    # whose output exists is what wedged the API on an overwrite dialog.
    for j in (p.GetRenderJobList() or []):
        p.DeleteRenderJob(j["JobId"])

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
    cues, last = [], -9.0
    for n, at, _d in EXHIBITS:
        if at - last >= 2.4:            # keep two cues off each other's tail
            cues.append(Cue(at + 0.05, "thunk", gain, f"{n} lands"))
            last = at
    print("sfx:", bed(cues, total / FPS, out=OUT / "sfx.wav"))

    names = ["dip.mov", "cap_kin.mov", "sfx.wav"] + [f"{n}.mov" for n, _a, _d in EXHIBITS]
    r.GetMediaStorage().AddItemListToMediaPool([str(OUT / n) for n in names])
    pool = {c.GetName(): c for c in mp.GetRootFolder().GetClipList()}

    ents = []

    def add(name, at, dur, track, media=None):
        c = pool.get(name)
        if c is None:
            print(f"  !! {name} missing from the media pool")
            return
        e = {"mediaPoolItem": c, "startFrame": 0, "endFrame": int(round(dur * FPS)),
             "recordFrame": s + int(round(at * FPS)), "trackIndex": track}
        if media:
            e["mediaType"] = media
        ents.append(e)

    for d in DIPS:
        add("dip.mov", d, 0.567, 3)
    for n, at, dur in EXHIBITS:
        add(f"{n}.mov", at, dur, 4)
    add("cap_kin.mov", 0.0, total / FPS, 6)
    add("sfx.wav", 0.0, total / FPS, 2, media=2)

    placed = mp.AppendToTimeline(ents)
    print(f"appended {len(placed or [])} of {len(ents)}  "
          f"({len(EXHIBITS)} graphics, {len(cues)} cues)")
    for t_ in range(3, 7):
        print(f"  V{t_}: {len(tl.GetItemListInTrack('video', t_) or [])} clips")


if __name__ == "__main__":
    main()
