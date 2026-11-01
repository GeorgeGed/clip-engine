"""Style A — RECEIPTS, built in DaVinci Resolve.

R1's actual structure, not ours: the lower pane IS the exhibit. Instead of a
small card floating over a static board, the content pane punches full-pane
onto the figure being discussed, and a dip covers each handoff. The overlay
cards come off; the document carries the argument.
"""
import sys
R="/Users/georgegeddes/Library/Application Support/Claude/scratch-workspaces/6d38ae6d-05dd-4827-8e46-76304910d38e/68f1a3b0-a8d1-4d98-a822-3205d41bec7a/scratch-2026-10-28-f045e2"
sys.path.insert(0,R)
from engine.resolve_driver import connect
from engine.resolve_layout import Frame, plan, apply
from engine.cuts import framings, content_framings
from engine.titles import BOARD_REGIONS

FPS, SEAM, CHROME = 60, 0.42, 92
CAM = (1456, 818, 1920, 1080)
CANVAS = Frame(1080, 1920, 1920, 1080)
SEAM_Y = SEAM * 1920
# the two segments that become full-pane exhibits
EXHIBIT = {2: (10, 100, 680, 790),
           8: (958, 240, 1417, 715)}

r = connect(); r.OpenPage("edit")
p = r.GetProjectManager().GetCurrentProject(); tl = p.GetCurrentTimeline()
s = tl.GetStartFrame()

# clear the card/title tracks; the document does this job in a receipts cut
cleared = 0
for t in (4, 5):
    its = tl.GetItemListInTrack("video", t) or []
    if its: tl.DeleteClips(its); cleared += len(its)
print(f"cleared {cleared} card/title clips from V4/V5")

v1 = sorted(tl.GetItemListInTrack("video", 1) or [], key=lambda i: i.GetStart())
v2 = sorted(tl.GetItemListInTrack("video", 2) or [], key=lambda i: i.GetStart())
crects = content_framings(len(v1), chrome=CHROME)
rects = framings(len(v2), CAM)

for i, it in enumerate(v1):
    rect = EXHIBIT.get(i, crects[i])
    apply(it, plan(CANVAS, rect, (0, SEAM_Y, 1080, 1920)))
    if i in EXHIBIT:
        print(f"  seg {i}: content pane punched onto the exhibit {rect}")
for i, it in enumerate(v2):
    apply(it, plan(CANVAS, rects[i], (0, 0, 1080, SEAM_Y)))
print("re-framed V1/V2")
