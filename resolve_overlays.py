"""Place clip 08's overlays and SFX onto the Resolve timeline.

George: "stop being lazy, edit this in davinci." Until now the hook, cards
and sound were composited in ffmpeg AFTER Resolve rendered, so they were
invisible in the timeline and could not be nudged in the UI. Now they are
clips on V4/V5 and A2 — Resolve composites them and Resolve renders them.

What still cannot happen in Resolve, with the reason measured rather than
assumed:

* **Animation.** There is no keyframe API on the Edit page. `Opacity` is a
  settable TimelineItem property (verified: set 40, reads back 40) but holds
  one static value; numeric Fusion inputs refuse keyframes; and
  `AddTransition` does not exist — `hasattr` returns True for it, and for
  any nonsense name, because these are remote proxies. So each overlay's
  fade and settle are baked into an alpha clip, and Resolve composites it.
* **Loudness.** `Timeline.NormalizeAudioLevel` applies gain without
  true-peak limiting, so the two-pass `loudnorm` stays as a finishing step.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from engine.resolve_driver import connect
from engine.sfx import Cue, bed, cue_gain
from build_overlays import PLAN

OUT = ROOT / "jobs/fns-2905408276/overlays"
FPS = 60
MASTER_GAIN, TARGET_RMS = 6.2, -30.0


def main():
    r = connect()
    proj = r.GetProjectManager().GetCurrentProject()
    tl = proj.GetCurrentTimeline()
    mp = proj.GetMediaPool()
    start = tl.GetStartFrame()
    # Take the length FROM the timeline. Hard-coding 51.5s put the sound bed
    # 5 frames past the picture, which extended the timeline and left a black
    # frame at 51.42s — QC caught it, a 10fps scan would not have.
    total_frames = tl.GetEndFrame() - start
    total_s = total_frames / FPS
    print(f"timeline {tl.GetName()}  start {start}  {total_frames} frames ({total_s:.3f}s)")

    # ---- the sound bed: one cue per FACT CARD arriving, nothing else ------
    # Titles get no sound. Keeping the thunk exclusively for cards means a
    # sound always says the same thing — a fact just arrived — and after two
    # notes about level, salting six events rather than four is the wrong
    # direction. The marker draw-on gets none either: it starts 0.55s after
    # its card's cue, well inside the 3s spacing floor.
    SOUNDED = {"tweet", "strip1", "strip2", "kru"}
    cues = [Cue(o["at"] + 0.02, "thunk", cue_gain("thunk", TARGET_RMS, MASTER_GAIN),
                f"{o['name']} card arrives")
            for o in PLAN if o["name"] in SOUNDED]
    wav = OUT / "sfx.wav"
    print("sfx:", bed(cues, total_s, out=wav))

    # ---- clear anything we put on V4/V5 before, and A2 -------------------
    while tl.GetTrackCount("video") < 5:
        tl.AddTrack("video")
    while tl.GetTrackCount("audio") < 2:
        tl.AddTrack("audio")
    # V3 is the dip, V4/V5 the cards and titles. V6 is the CAPTIONS — never
    # clear it: the 11 Text+ titles were lifted there to free V3, and
    # rebuilding them means re-running the whole Fusion caption pass.
    stale = []
    for t in (3, 4, 5):
        stale += tl.GetItemListInTrack("video", t) or []
    stale += tl.GetItemListInTrack("audio", 2) or []
    if stale:
        print(f"clearing {len(stale)} existing overlay clip(s):",
              [s.GetName() for s in stale])
        tl.DeleteClips(stale)

    # ---- import ----------------------------------------------------------
    paths = [str(OUT / f"{o['name']}.mov") for o in PLAN] + [str(wav)]
    added = r.GetMediaStorage().AddItemListToMediaPool(paths)
    print("imported:", len(added or []), "item(s)")

    by_name = {}
    for c in mp.GetRootFolder().GetClipList():
        by_name[c.GetName()] = c

    # ---- place, ALL in one AppendToTimeline call -------------------------
    # trackIndex is ignored across separate calls, so a per-clip loop
    # silently stacks everything on one track.
    entries = []
    for o in PLAN:
        clip = by_name.get(f"{o['name']}.mov")
        if clip is None:
            print(f"  !! {o['name']}.mov not in media pool"); continue
        n = int(round(o["dur"] * FPS))
        entries.append({"mediaPoolItem": clip, "startFrame": 0, "endFrame": n,
                        "recordFrame": start + int(round(o["at"] * FPS)),
                        "trackIndex": o["track"]})
    snd = by_name.get("sfx.wav")
    if snd is not None:
        entries.append({"mediaPoolItem": snd, "startFrame": 0,
                        "endFrame": total_frames,
                        "recordFrame": start, "trackIndex": 2, "mediaType": 2})
    placed = mp.AppendToTimeline(entries)
    print(f"appended {len(placed or [])} of {len(entries)}")

    for t in (3, 4, 5, 6):
        for it in tl.GetItemListInTrack("video", t) or []:
            print(f"  V{t}  {it.GetName():14} {it.GetStart()-start:5d}..{it.GetEnd()-start:5d}"
                  f"  ({(it.GetEnd()-it.GetStart())/FPS:.2f}s)")
    for it in tl.GetItemListInTrack("audio", 2) or []:
        print(f"  A2  {it.GetName():14} {it.GetStart()-start:5d}..{it.GetEnd()-start:5d}")


if __name__ == "__main__":
    main()
