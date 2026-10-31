"""Render clip 08's overlays as alpha clips, ready for the Resolve timeline.

Five overlays, up from three. George: "we need more popups on the screen for
things like news, references, etc, for clips like this because it makes
sense, still looks basic."

He is right and the reference says so too: R1 runs SEVEN different exhibits
through its lower pane in 80s. Clip 8 cannot match that from its own
footage — the content region is pixel-static for 61 of its 67 seconds
(frame delta median 0.13, one change at 5.5s when he switches from the tweet
to the board). So the variety has to come from moving around INSIDE the one
document, which is what these do.

Everything here is real pixels from the source frame. Nothing is redrawn.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from engine.titles import hook, panel, section, marker_ellipse, BOARD_REGIONS
from engine.overlays import alpha_clip, sequence_clip, pane_dip, CANVAS

SCRATCH = Path("/private/tmp/claude-501/"
               "-Users-georgegeddes-Library-Application-Support-Claude-scratch-workspaces-"
               "6d38ae6d-05dd-4827-8e46-76304910d38e-68f1a3b0-a8d1-4d98-a822-3205d41bec7a-"
               "scratch-2026-10-28-f045e2/ce92e562-40cc-4445-80fa-a3607729fc90/scratchpad")
PLATE = ROOT / "jobs/fns-2905408276/clip08_src_plate.png"
OUT = ROOT / "jobs/fns-2905408276/overlays"
OUT.mkdir(parents=True, exist_ok=True)
PNG = OUT / "png"; PNG.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Overlays are anchored to SOURCE time — a spoken line — not to a position in
# the finished cut. Tightening the dead space moved every output timestamp,
# and hard-coded ones would all have drifted silently. Anchors survive a
# re-cut; output positions do not.
# ---------------------------------------------------------------------------
import glob
from engine.tighten import removals, keeps, remap_card
from engine import qc

IN_POINT, MIN_DEAD, BEAT = 8.85, 0.35, 0.12
_clip = glob.glob(str(ROOT / "jobs/fns-2905408276/clips_1080/08_*.mp4"))[0]
_src_dur = 4026 / 60


def _keeps():
    """The same cut build_v7.py makes, so the two agree by construction."""
    dead = sorted([r for r in qc.dead_audio(_clip, min_run=0.3)["runs"]
                   + qc.quiet_runs(_clip, min_run=MIN_DEAD)["runs"]
                   if r[0] >= IN_POINT])
    kp = [k for k in keeps(removals(dead, _src_dur, min_remove=MIN_DEAD, beat=BEAT),
                           _src_dur) if k.end > IN_POINT]
    if kp:
        kp[0].start = max(kp[0].start, IN_POINT)
    return kp


KP = _keeps()
OUT_DUR = sum(k.length for k in KP)


def at(src_t: float, fallback: float = 0.0) -> float:
    """Source second -> second in the finished cut."""
    r = remap_card(src_t, src_t + 0.05, KP)
    return round(r[0], 2) if r else fallback


STRIP = (200, 152, 680, 180)          # contiguous: blocks 2..5 of the header
B_OPEN, B_BENCH, B_STAFF, B_UNCONF = (209, 284), (322, 427), (466, 508), (546, 670)
B_SIGNED = (109, 170)

# Each overlay: (name, track, start_s, dur_s, y, how to draw it)
#
# Placement follows the argument, not a rhythm:
#   17.45  "you don't have enough job security"      -> the scarcity
#   30.80  "once you get SIGNED to an org"           -> the signed count
#   37.85  "those people that get replaced"          -> a team with 1 of 5
PLAN = [
    dict(name="hook",   track=4, at=0.00,  dur=2.05, y=1050, fade_in=0.01, fade_out=0.50,
         settle=0,  make=lambda p: hook(["YOU CAN END UP", "WITH NOTHING"], p,
                                        accent_words=("NOTHING",))),
    dict(name="tweet",  track=5, at=at(10.40),  dur=3.00, y=900,  fade_in=0.12, fade_out=0.30,
         settle=0,  make=lambda p: __import__("shutil").copy(SCRATCH / "tweet_card.png", p)),
    dict(name="strip1", track=4, at=at(26.40), dur=3.40, y=1150, fade_in=0.10, fade_out=0.25,
         settle=16, make=lambda p: panel(PLATE, p, STRIP, width=1010,
                                         kicker="VCT Roster Board",
                                         rules=[B_OPEN, B_UNCONF])),
    dict(name="strip2", track=4, at=at(41.30), dur=3.10, y=1150, fade_in=0.10, fade_out=0.25,
         settle=16, make=lambda p: panel(PLATE, p, (100, 152, 680, 180), width=1010,
                                         kicker="VCT Roster Board",
                                         rules=[B_SIGNED])),
    # The KRU card is the only ANNOTATED one — the marker draws on over it,
    # so it is built by sequence_clip rather than alpha_clip. The clean
    # rectangle round the four unconfirmed players is gone; the marker does
    # that job, and does it the way R1 does.
    dict(name="kru",    track=4, at=at(51.40), dur=4.20, y=1060, fade_in=0.10, fade_out=0.25,
         settle=16, marker=True,
         make=lambda p: panel(PLATE, p, BOARD_REGIONS["kru"], width=780,
                              kicker="VCT Roster Board — Americas",
                              boxes=[(1358, 262, 1404, 286)])),
    # Mid-clip section titles (R1, 0:31). Not restatements of his words —
    # they frame the stretch that follows, which is the job the removed
    # banner was doing badly.
    dict(name="sec1",   track=5, at=at(15.20),  dur=2.30, y=1120, fade_in=0.14, fade_out=0.45,
         settle=0,  make=lambda p: section("WHAT IT MEANS FOR PLAYERS", p,
                                           cap_px=84, accent_words=("PLAYERS",))),
    dict(name="sec2",   track=5, at=at(57.90), dur=2.20, y=1120, fade_in=0.14, fade_out=0.45,
         settle=0,  make=lambda p: section("THE TRADE-OFF", p,
                                           cap_px=96, accent_words=("TRADE-OFF",))),
    # The ONE place the dip is earned. R1 dips between exhibits; clip 8's
    # pane never changes document, so there is exactly one handoff — the
    # announcement tweet giving way to the roster board as the card clears.
    # Anywhere else it would punctuate nothing. On V3, below the cards and
    # captions, because in R1 it is the DOCUMENT going dark and the editor's
    # own overlays stay lit straight through it.
    dict(name="dip",    track=3, at=at(10.40)+2.65, dur=0.56, y=0, fade_in=0.0, fade_out=0.0,
         settle=0, dip=True, make=None),
]

# Where the four unconfirmed KRU players land on the 1080x1920 canvas, after
# panel() has cropped (958,246)-(1417,480) to 780 wide and the clip sits at
# y=1060. Derived, not eyeballed: scale 780/459, card x=(1080-824)/2, and
# panel's own pad(22) + kicker height(42).
_SC = 780 / (BOARD_REGIONS["kru"][2] - BOARD_REGIONS["kru"][0])
_CX = (CANVAS[0] - 824) / 2 + 22
_CY = 1060 + 60
MARKER_BOX = (_CX + (1216 - 958) * _SC, _CY + (308 - 246) * _SC,
              _CX + (1404 - 958) * _SC, _CY + (448 - 246) * _SC)


def kru_frame(card_png: Path):
    """Compose the KRU card with the marker drawing on from 0.55s."""
    from PIL import Image
    card = Image.open(card_png).convert("RGBA")
    x0, y0, x1, y1 = MARKER_BOX
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    rx, ry = (x1 - x0) / 2 + 26, (y1 - y0) / 2 + 22

    def fn(t, i):
        frame = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
        frame.alpha_composite(card, (int((CANVAS[0] - card.width) / 2), 1060))
        p = max(0.0, min(1.0, (t - 0.55) / 0.55))
        if p > 0:
            frame.alpha_composite(marker_ellipse(CANVAS, cx, cy, rx, ry, p))
        return frame
    return fn

if __name__ == "__main__":
    for o in PLAN:
        mov = OUT / f"{o['name']}.mov"
        if o.get("dip"):
            pane_dip(mov, dur=o["dur"])
            print(f"  {o['name']:7} V{o['track']}  {o['at']:6.2f}s +{o['dur']:.2f}s  "
                  f"{'pane dip':14} {mov.name}")
            continue
        png = PNG / f"{o['name']}.png"
        o["make"](png)
        if o.get("marker"):
            sequence_clip(kru_frame(png), mov, dur=o["dur"],
                          fade_in=o["fade_in"], fade_out=o["fade_out"])
        else:
            alpha_clip(png, mov, dur=o["dur"], y=o["y"], fade_in=o["fade_in"],
                       fade_out=o["fade_out"], settle_px=o["settle"])
        print(f"  {o['name']:7} V{o['track']}  {o['at']:6.2f}s +{o['dur']:.2f}s  "
              f"y={o['y']:<5} {'marker' if o.get('marker') else '':7} {mov.name}")
