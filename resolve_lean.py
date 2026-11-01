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
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from engine.resolve_driver import connect
from engine.sfx import Cue, bed, cue_gain, cue_gain_peak

FPS = 60
OUT = ROOT / "jobs/fns-2905408276/overlays"
MASTER_GAIN, TARGET_RMS = 6.2, -29.0
DIPS = (14.80, 32.92)
# The clickbait line George asked for: what the video is about, with an
# Apple emoji, sitting just under the facecam. It runs over the opening
# stretch where a scroller decides, then leaves.
BAIT = ("rm_Bait", 0.80, 17.00)

# (clip, start seconds, duration seconds)
EXHIBITS = [
    ("rm_ChipAmer",  1.20, 1.83),   # 34/40 Americas slots filled
    ("rm_Tweet",     3.30, 3.45),   # the Global Esports announcement
    ("rm_StatCard",  7.60, 3.50),   # 10 -> 8 partner teams per region
    ("rm_Pair",     11.60, 3.50),   # 139 signed vs 274 not yet confirmed
    ("rm_ExStrip",  15.08, 3.50),   # the board's header strip
    ("rm_Ratio",    19.40, 3.50),   # 32 open slots against 274
    ("rm_ExNrg",    24.32, 3.75),   # NRG 5/5, a full roster
    ("rm_Grid",     28.80, 4.00),   # all eight Americas teams populating
    ("rm_ExKru",    33.20, 4.50),   # KRU 1/5, with the marker
    # The two freshest stories, each through an independent verification
    # pass. The free-agency card that used to close the clip is GONE —
    # George: "last graphic dissapears too quickly but is unnecessary". It
    # was 2.25s AND it overlapped rm_StorySen's tail by 1.5s on the same
    # track, so it flashed; dropping it removes the collision as well.
    # Real published headlines, tilted, players under them. The earlier
    # version set VLR's verb as a gold fragment under a name — "PARTS
    # WAYS AFTER FIVE YEARS" — which reads as a label nobody wrote. The
    # headline is a sentence and works as one.
    ("rm_StoryPrx", 37.60, 4.25),   # Paper Rex parts ways with Jinggg
    ("rm_StorySen", 42.10, 4.00),   # Sentinels release JonahP and Jerrwin
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

    # Sound is tied to a movement a viewer can see — the rule that got the
    # fourth sound design accepted after three were rejected. The story
    # cards show photographs, so they get a camera shutter; the counter
    # gets a run of ticks that thins as it eases out.
    gain = cue_gain("thunk", TARGET_RMS, MASTER_GAIN)
    # by PEAK, not RMS: the shutter's 22 dB crest put it 6.4 dB over
    # the thunks when both were set to the same RMS. -14.3 is where
    # the thunks measure in the master, so they now match.
    shut = cue_gain_peak("shutter", -14.3, MASTER_GAIN)
    tck  = cue_gain("tick", -40.0, MASTER_GAIN)
    STORIES = {"rm_StoryPrx", "rm_StorySen"}
    cues, last = [], -9.0
    for n, at, _d in EXHIBITS:
        if at - last < 2.4:             # keep two cues off each other's tail
            continue
        if n in STORIES:
            # a photo card gets a camera shutter, and only that — the paper
            # settle plus a news ding was two cues stacked on one event.
            cues.append(Cue(at + 0.04, "shutter", shut,
                            f"{n}: the player photos land"))
        else:
            cues.append(Cue(at + 0.05, "thunk", gain, f"{n} lands"))
        if n == "rm_Pair":
            # the odometer: ticks across the count, thinning as it eases out
            for k in range(9):
                p = k / 8
                cues.append(Cue(at + 0.14 + 0.80 * (1 - (1 - p) ** 2), "tick", tck,
                                "a digit turns on the counter"))
        last = at
    print("sfx:", bed(cues, total / FPS, out=OUT / "sfx.wav"))

    names = ["dip.mov", "cap_kin.mov", "sfx.wav", f"{BAIT[0]}.mov"] + \
            [f"{n}.mov" for n, _a, _d in EXHIBITS]
    r.GetMediaStorage().AddItemListToMediaPool([str(OUT / n) for n in names])
    pool = {c.GetName(): c for c in mp.GetRootFolder().GetClipList()}

    # Now that every card animates OUT over its last 16 frames, a clip that
    # Resolve trims short loses the end of that exit — which is the jolt the
    # exit was built to remove. Two were already short (rm_Bait 1020 of 1060,
    # rm_Tweet 207 of 210), so the length comes from the FILE, not from a
    # number typed here.
    def clip_frames(name):
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
             "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0",
             str(OUT / f"{name}.mov")], capture_output=True, text=True).stdout.strip()
        return int(out) if out.isdigit() else None

    ents = []

    def add(name, at, dur, track, media=None):
        c = pool.get(name)
        if c is None:
            print(f"  !! {name} missing from the media pool")
            return
        want = int(round(dur * FPS))
        # Only the Remotion cards. `cap_kin.mov` is the whole caption track
        # and `dip.mov` is a measured 0.567s envelope — taking either from the
        # file would overrun the timeline or stretch the dip.
        have = clip_frames(name[:-4]) if name.startswith("rm_") else None
        if have and have != want:
            print(f"  {name}: {want} asked, {have} in the file — using the file "
                  f"so the exit is not cut")
            want = have
        e = {"mediaPoolItem": c, "startFrame": 0, "endFrame": want,
             "recordFrame": s + int(round(at * FPS)), "trackIndex": track}
        if media:
            e["mediaType"] = media
        ents.append(e)

    for d in DIPS:
        add("dip.mov", d, 0.567, 3)
    for n, at, dur in EXHIBITS:
        add(f"{n}.mov", at, dur, 4)
    add(f"{BAIT[0]}.mov", BAIT[1], BAIT[2], 5)
    add("cap_kin.mov", 0.0, total / FPS, 6)
    add("sfx.wav", 0.0, total / FPS, 2, media=2)

    placed = mp.AppendToTimeline(ents)
    print(f"appended {len(placed or [])} of {len(ents)}  "
          f"({len(EXHIBITS)} graphics, {len(cues)} cues)")
    for t_ in range(3, 7):
        print(f"  V{t_}: {len(tl.GetItemListInTrack('video', t_) or [])} clips")


if __name__ == "__main__":
    main()
