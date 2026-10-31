#!/usr/bin/env python3
"""Clip 8 v7 — one narrative, dead space gone, then a juice pass.

Three things George called out and all three are addressed here:

  * ONE NARRATIVE. The clip opened on the Global Esports announcement and then
    became a general argument about job security. Two topics. The in-point
    moves to 8.85s, where the argument starts ("obviously non-partnered orgs
    only picking up teams..."). That also drops 4.2s of mute that sat in the
    first nine seconds.
  * DEAD SPACE FULLY CUT. He has asked twice. Every absent run >= MIN_DEAD is
    removed, leaving a 0.10s beat. The integrity caveat stands and is printed
    at the end: on a DMCA-muted VOD these joins splice across speech nobody
    can hear.
  * MOTION. Resolve has no keyframe API for transforms, so smooth animation
    cannot come from the Edit page. The structural edit is built here; the
    juice (zoom punches, flashes, shake) is a separate ffmpeg pass.
"""
import json, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from engine.resolve_driver import connect
from engine.resolve_layout import Frame, plan, apply
from engine.resolve_captions import (cards, plan_windows, expression, colour_expression,
                                     style_tool, Style, emphasis_keys, mark_emphasis,
                                     _frame_to_tc)
from engine.cuts import framings, content_framings
from engine.tighten import removals, keeps, remap_card, joins
from engine import qc

SP = Path("/private/tmp/claude-501/-Users-georgegeddes-Library-Application-Support-Claude-scratch-workspaces-6d38ae6d-05dd-4827-8e46-76304910d38e-68f1a3b0-a8d1-4d98-a822-3205d41bec7a-scratch-2026-10-28-f045e2/ce92e562-40cc-4445-80fa-a3607729fc90/scratchpad")
FPS, SEAM, CHROME = 60, 0.42, 92
IN_POINT = 8.85            # where the job-security argument starts
MIN_DEAD = 0.50            # shorter removals read as jitter, not tightening
CAM = (1456, 818, 1920, 1080)
CANVAS = Frame(1080, 1920, 1920, 1080)
GRADE = {"NodeIndex": "1", "Slope": "1.06 1.06 1.07",
         "Offset": "-0.012 -0.012 -0.010", "Power": "1.06 1.06 1.06",
         "Saturation": "1.18"}

import glob
clip = glob.glob(str(ROOT / "jobs/fns-2905408276/clips_1080/08_*.mp4"))[0]
src_dur = 4026 / FPS

# ---- plan the cut -------------------------------------------------------
dead = [r for r in qc.dead_audio(clip, min_run=0.3)["runs"] if r[0] >= IN_POINT]
spans = removals(dead, src_dur, min_remove=MIN_DEAD, beat=0.10)
kp = [k for k in keeps(spans, src_dur) if k.end > IN_POINT]
if kp:
    kp[0].start = max(kp[0].start, IN_POINT)
out_dur = sum(k.length for k in kp)
print(f"in-point {IN_POINT}s (was 0.0) | {len(spans)} dead removals "
      f"({sum(s.length for s in spans):.1f}s)")
print(f"{src_dur:.1f}s -> {out_dur:.1f}s in {len(kp)} shots "
      f"(mean {out_dur/len(kp):.1f}s, {len(kp)-1} cuts = "
      f"{(len(kp)-1)/(out_dur/60):.1f}/min)")

tr = json.loads((SP / "clip08_words.json").read_text())
meta = json.loads((ROOT / "jobs/fns-2905408276/ranked.json").read_text())[7]
words = [w for u in tr["utterances"] for w in u["words"]]
cs = cards(words)
mark_emphasis(cs, emphasis_keys(meta["claim"], meta["consequence"]))
# remap every card through the new timeline
out_cards = []
for c in cs:
    r = remap_card(c.start, c.end, kp)
    if r:
        c2 = type(c)(r[0], r[1], c.text, c.words, c.emphasis)
        out_cards.append(c2)
print(f"captions: {len(cs)} -> {len(out_cards)} after the cut")

# ---- build --------------------------------------------------------------
r = connect(); r.OpenPage("edit")
proj = r.GetProjectManager().GetCurrentProject()
mp = proj.GetMediaPool()
item = next(i for i in mp.GetRootFolder().GetClipList() if i.GetName().startswith("08_"))
for i in range(proj.GetTimelineCount(), 0, -1):
    t = proj.GetTimelineByIndex(i)
    if t and t.GetName() == "clip08-v7":
        mp.DeleteTimelines([t])
tl = mp.CreateEmptyTimeline("clip08-v7")
while tl.GetTrackCount("video") < 3:
    tl.AddTrack("video")
proj.SetCurrentTimeline(tl)
start = tl.GetStartFrame()
total = round(out_dur * FPS)

st = Style()
t0 = time.time()
for w in plan_windows(out_cards, fps=FPS, total_frames=total):
    if not w["cards"]:
        continue
    tc = _frame_to_tc(start, FPS)
    tl.SetCurrentTimecode(tc); tl.SetCurrentTimecode(tc)
    tl.SetTrackLock("video", 3, True)
    ti = tl.InsertFusionTitleIntoTimeline("Text+")
    tl.SetTrackLock("video", 3, False)
    ti.SetPosition({"trackIndex": 3, "startFrame": start + w["offset_frames"]})
    tool = list(ti.GetFusionCompByIndex(1).GetToolList().values())[0]
    style_tool(tool, st)
    tool.StyledText.SetExpression(expression(w["cards"]))
    for ch, inp in enumerate(("Red1", "Green1", "Blue1")):
        getattr(tool, inp).SetExpression(
            colour_expression(w["cards"], ch, st.fill, st.accent))
print(f"captions built {time.time()-t0:.0f}s")

entries, rec = [], start
for k in kp:
    sf, ef = round(k.start * FPS), round(k.end * FPS)
    for track in (1, 2):
        entries.append({"mediaPoolItem": item, "startFrame": sf, "endFrame": ef,
                        "trackIndex": track, "recordFrame": rec,
                        **({} if track == 1 else {"mediaType": 1})})
    rec += ef - sf
mp.AppendToTimeline(entries)

seam_y = SEAM * CANVAS.canvas_h
rects = framings(len(kp), CAM)
crects = content_framings(len(kp), chrome=CHROME)
for trk, rl, pane in ((1, crects, (0, seam_y, 1080, 1920)),
                      (2, rects, (0, 0, 1080, seam_y))):
    items = sorted(tl.GetItemListInTrack("video", trk) or [], key=lambda i: i.GetStart())
    for it, rect in zip(items, rl):
        apply(it, plan(CANVAS, rect, pane))
        if trk == 2:
            it.SetCDL(GRADE)
print(f"video: V1 {len(tl.GetItemListInTrack('video',1))} / "
      f"V2 {len(tl.GetItemListInTrack('video',2))} shots, "
      f"{(tl.GetEndFrame()-start)/FPS:.1f}s")

t0 = time.time()
proj.LoadRenderPreset("H.264 Master")
proj.SetRenderSettings({"TargetDir": str(ROOT / "renders"),
                        "CustomName": "clip08_v7_raw", "SelectAllFrames": True})
job = proj.AddRenderJob(); proj.StartRendering([job])
while proj.IsRenderingInProgress():
    time.sleep(1)
print(f"render {time.time()-t0:.0f}s")

# cut points in OUTPUT time, for the juice pass
acc, cutpts = 0.0, []
for k in kp[:-1]:
    acc += k.length
    cutpts.append(round(acc, 3))
json.dump({"cuts": cutpts, "duration": out_dur,
           "emphasis": [[c.start, c.end] for c in out_cards if c.emphasis]},
          open(SP / "v7_plan.json", "w"), indent=1)
print(f"\ncuts for the juice pass: {cutpts}")
print("\nJOINS MADE (each splices across unheard speech):")
for j in joins(spans, words):
    print(f"  @{j['at']:6.2f} -{j['removed']:.2f}s  ...{j['before'][-40:]!r} -> {j['after'][:40]!r}...")
