#!/usr/bin/env python3
"""Build clip 8's finished master in Resolve, end to end, in one pass.

L2 split, graded facecam, word captions with emphasis, picture cuts with a
punch on each, then render and loudness-finish. Idempotent: deletes and
rebuilds its own timeline.

Run:  ./.venv/bin/python build_master.py
"""
import json, sys, time
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from engine.resolve_driver import connect
from engine.resolve_layout import Frame, plan, apply
from engine.resolve_captions import (cards, plan_windows, expression, colour_expression,
                                     style_tool, Style, emphasis_keys, mark_emphasis,
                                     _frame_to_tc)
from engine.cuts import (cut_points, framings, content_framings,
                         content_scenes, exhibit_framings)
from engine.render_ffmpeg import _finish_audio
from engine import qc

SP = Path("/private/tmp/claude-501/-Users-georgegeddes-Library-Application-Support-Claude-scratch-workspaces-6d38ae6d-05dd-4827-8e46-76304910d38e-68f1a3b0-a8d1-4d98-a822-3205d41bec7a-scratch-2026-10-28-f045e2/ce92e562-40cc-4445-80fa-a3607729fc90/scratchpad")
FPS, SEAM, CHROME, MIN_SHOT = 60, 0.42, 92, 4.0
CAM = (1456, 818, 1920, 1080)
CANVAS = Frame(1080, 1920, 1920, 1080)
GRADE = {"NodeIndex": "1", "Slope": "1.06 1.06 1.07",
         "Offset": "-0.012 -0.012 -0.010", "Power": "1.06 1.06 1.06",
         "Saturation": "1.18"}

r = connect()
r.OpenPage("edit")                     # never leave it on Color while scripting
proj = r.GetProjectManager().GetCurrentProject()
mp = proj.GetMediaPool()
import glob as _glob
clip = _glob.glob(str(ROOT / "jobs/fns-2905408276/clips_1080/08_*.mp4"))[0]
item = next(i for i in mp.GetRootFolder().GetClipList() if i.GetName().startswith("08_"))
frames = int(item.GetClipProperty("Frames"))
dur = frames / FPS

tr = json.loads((SP / "clip08_words.json").read_text())
meta = json.loads((ROOT / "jobs/fns-2905408276/ranked.json").read_text())[7]
words = [w for u in tr["utterances"] for w in u["words"]]
cs = cards(words)
n_emph = mark_emphasis(cs, emphasis_keys(meta["claim"], meta["consequence"]))

cuts = cut_points(words, dur, min_shot=MIN_SHOT)
# A document change in the content pane is a MANDATORY cut: a shot that
# straddles it shows the wrong exhibit for half its length.
scenes = content_scenes(clip)
for s in scenes:
    if 0.5 < s < dur - 0.5 and all(abs(s - c) > 1.0 for c in cuts):
        cuts.append(s)
cuts.sort()
print(f"document changes at {scenes} -> forced cuts")
bounds = [0.0] + cuts + [dur]
shots = list(zip(bounds, bounds[1:]))
rects = framings(len(shots), CAM)
print(f"{len(cs)} cards ({n_emph} accented) | {len(cuts)} picture cuts, "
      f"{len(shots)} shots, mean {dur/len(shots):.1f}s")

for i in range(proj.GetTimelineCount(), 0, -1):
    t = proj.GetTimelineByIndex(i)
    if t and t.GetName() == "clip08-master":
        mp.DeleteTimelines([t])
tl = mp.CreateEmptyTimeline("clip08-master")
while tl.GetTrackCount("video") < 3:
    tl.AddTrack("video")
proj.SetCurrentTimeline(tl)
for i, nm in ((1, "content"), (2, "facecam"), (3, "captions")):
    tl.SetTrackName("video", i, nm)
start = tl.GetStartFrame()

# 1. captions FIRST -- the title insert ripples every unlocked track, so V1
#    must still be empty and V3 must be locked across each insert.
st = Style()
t0 = time.time()
for w in plan_windows(cs, fps=FPS, total_frames=frames):
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
print(f"captions {time.time()-t0:.0f}s")

# 2. video. Content is one unbroken clip; the facecam is cut into shots so the
#    FRAME cuts while the audio runs continuous underneath. Audio rides with
#    the content clip only -- the facecam copies are video-only.
# endFrame is EXCLUSIVE. Measured: startFrame=0 endFrame=100 yields a
# 100-frame clip. Subtracting 1 drops a frame from every shot, and at a cut
# that shows as ONE BLACK FRAME in the pane -- which is what "the screen
# randomly goes black" was. It was black at exactly the five cut points.
entries = []
for (a, b) in shots:
    sf, ef = round(a * FPS), round(b * FPS)
    for track in (1, 2):
        entries.append({"mediaPoolItem": item, "startFrame": sf, "endFrame": ef,
                        "trackIndex": track, "recordFrame": start + sf,
                        **({} if track == 1 else {"mediaType": 1})})
mp.AppendToTimeline(entries)

seam_y = SEAM * CANVAS.canvas_h
# Scene 0 is the news tweet he is reading; frame it as the exhibit it is.
# Measured off the source frame: the post column is x 600-1190, y 170-950.
# Match the PANE's aspect (1080/1114 = 0.969) or fill crops the headline off:
# a 590x780 rect scaled to 1080 wide becomes 1427 tall in a 1114 pane and
# loses 313px top and bottom. 590 wide needs 609 tall.
TWEET = (600, 200, 1190, 809)
_pan = content_framings(len(shots), chrome=CHROME)
crects = exhibit_framings(shots, scenes, {0: TWEET}, lambda i: _pan[i])
con_items = sorted(tl.GetItemListInTrack("video", 1) or [], key=lambda i: i.GetStart())
for it, rect in zip(con_items, crects):
    apply(it, plan(CANVAS, rect, (0, seam_y, 1080, 1920)))
cam_items = sorted(tl.GetItemListInTrack("video", 2) or [], key=lambda i: i.GetStart())
for it, rect in zip(cam_items, rects):
    apply(it, plan(CANVAS, rect, (0, 0, 1080, seam_y)))
    it.SetCDL(GRADE)
print(f"video: V1 {len(con_items)} shots, V2 {len(cam_items)} shots")

# 3. render + loudness
t0 = time.time()
proj.LoadRenderPreset("H.264 Master")
proj.SetRenderSettings({"TargetDir": str(ROOT / "renders"),
                        "CustomName": "clip08_v6_raw", "SelectAllFrames": True})
job = proj.AddRenderJob()
proj.StartRendering([job])
while proj.IsRenderingInProgress():
    time.sleep(1)
print(f"render {time.time()-t0:.0f}s {(proj.GetRenderJobStatus(job) or {}).get('JobStatus')}")

out = ROOT / "renders/clip08_MASTER_v6.mp4"
_finish_audio(ROOT / "renders/clip08_v6_raw.mov",
              {"audio": {"target_lufs": -12.0, "true_peak_dbtp": -1.0},
               "render": {"audio_codec": "aac"}}, out)
print()
print(qc.check(out).report())
