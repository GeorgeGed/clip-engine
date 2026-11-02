"""Assemble clip 08 on the Resolve timeline.

    V1 content   V2 facecam (colour arc)   V3 chat
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
# NO DIPS. The pane dip was built on the note that it is "the ONLY
# transition anywhere in the four references". Re-measured, it punctuates
# nothing here: the content pane's frame-to-frame delta is median 0.0005,
# max 0.27, with ZERO frames above 0.5 across all 2822 — one static roster
# board start to finish — and the dip's own rule is "where a document
# changes and nowhere else". Both had also drifted onto a card: dip 1 fired
# mid-hold under a card whose body measured 82.3361 before and 82.3371
# during, so for 0.567s everything except the card got 41% darker and came
# back, with no event to mark; dip 2 ramped straight through rm_ExKru's
# 22-frame entrance, so the biggest graphic in the clip arrived on a pane
# that was changing exposure.
DIPS = ()
# The clickbait line George asked for: what the video is about, with an
# Apple emoji, sitting just under the facecam. It runs over the opening
# stretch where a scroller decides, then leaves.
BAIT = ("rm_Bait", 0.80, 17.00)

# The streamer's own chat, replayed OVER the board he is reading from.
# George: "make it so it APPEARS over what he's looking at on stream ...
# when the pictures of jingg and jonah come up the chat should fade out -
# so the chat can come in and out you know?"
#
# It goes on V3, BELOW the graphics on V4. The box is PRESENT OR ABSENT and
# never translucent — a dark panel at partial opacity lets the board read
# through it, which is the same defect the card exits already record. Its
# windows are baked into the clip itself from `chat_windows.json`, since
# Resolve's Opacity is one static value per timeline item.
CHAT = ("rm_Chat", 0.0, None)        # None: the whole picture length

# (clip, start seconds, duration seconds)
#
# EVERY ADJACENT PAIR IS CHECKED BEFORE THE APPEND, because the worst
# entrance in the previous cut was two numbers in this list. `rm_ExKru` ran
# (33.20, 4.50), ending 37.70, against `rm_StoryPrx` at 37.60 — six frames of
# overlap on V4, and those six frames were ExKru's exit. Resolve resolves the
# collision by trimming StoryPrx's HEAD, so the biggest graphic in the clip
# slammed on in one frame at ~70% opacity: luma 23.6 at t=37.683, 165.0 at
# 37.700, 227 by 37.750. `rm_Pair` against `rm_ExStrip` was the same bug, one
# frame, masked by the dip at 14.80. A card that animates out over 12-15
# frames cannot have those frames trimmed away by the schedule.
EXHIBITS = [
    # George: "i want the twitch chat visible with no other animations
    # other than the story pop ups of jingg and jonahp/jerwwin as they are
    # relevent to what he's saying". Everything drawn is gone — the tweet,
    # the figure pair, the ratio bar, the roster grid and the KRU exhibit.
    # What is left is his own chat and two published news stories.

    # rm_ChipAmer and rm_StatCard are GONE. George: "now it's going way
    # too quickly - keep the twitch chat and remove chip amer, stat card
    # is pointless". The chip was also the one card the rhythm could not
    # accommodate — it started 1.20 and the tweet 3.30, too close to fit a
    # chat window between them.
    # Lengthened from 3.45s to take up the slack left by rm_ExStrip, which is
    # gone: the two figures it carried sit at the extreme ends of the strip
    # PNG, so the contiguous run containing both is the whole strip and no
    # magnification was possible. At 1.00x its ink band measured 21px against
    # 88px captions. rm_Ratio carries the same pair, legibly, at 19.40.
    # rm_ExNrg is GONE. George: "remove the NRG popup, rest are all good."
    # It was the weakest exhibit of the set anyway — the crop is mostly an
    # empty BENCH / OPTIONS column, so a full 5/5 roster read as white
    # space. Dropping it also opens 22.90-28.80, the clip's only long gap,
    # which is where the chat now gets the pane to itself.
    # The two freshest stories, each through an independent verification
    # pass. Real published headlines, tilted, players under them.
    ("rm_StoryPrx", 37.60, 4.25),   # Paper Rex parts ways with Jinggg
    ("rm_StorySen", 42.10, 4.00),   # Sentinels release JonahP and Jerrwin
]
MIN_GAP_FRAMES = 6                  # one chip exit

# Three acts, three grades, re-solved against the new palette. SetCDL is per
# CLIP so the grade cannot ramp, but the cut is already 22 segments on V2, so
# it steps by act. It reaches the FACECAM ONLY — V1 is a document and V4 are
# the cards.
#
# WHAT WAS WRONG. Inverting the CDL off the delivered frames recovers the
# ungraded facecam at R-B +5 to +7: his room is naturally warm and already
# sits where the chassis (+11) and the paper (+9) sit. The arc then pushed
# act 1 to -4.8, a 12-point swing into cool away from BOTH, and act 3 to
# +28.0. The clash with the graphics was manufactured by the grade.
#
# THE MEASUREMENT THAT DECIDED IT is a white in his own room — the IKEA
# shelf, the picture frame, the YouTube plaque. Mask the near-neutral brights
# (luma > 165, chroma < 45) on the RECOVERED UNGRADED pixels, so the same
# pixel set is tracked through every candidate, then read their R-B back.
# Measured against their own source value, the old arc moved a real white by
# 18.1 / 6.0 / 29.8 points across the three acts. A white that swings 24
# points across a clip is the definition of footage that has been graded.
# Now: 0.2 / 6.0 / 2.3, and the 6.0 is act 2, untouched.
#
# AND COUNT BLOWN FACE PIXELS PER CHANNEL. Act 3 of the old grade put
# **2.18% of his face at R >= 254** — a solid slab on the cheekbone, not a
# speckle of specular highlights. The replacement puts 0.000% there. The
# candidate that won the panel's vote outright was rejected on this: it moved
# the same defect into act 2, 15.93% of his face at one dead value.
#
# PUT THE WARMTH IN OFFSET, NOT SLOPE. Slope is gain, so it scales the
# highlights hardest and lands the warmth on exactly the white objects the
# test is watching. Act 3 moves R from slope to offset; act 1's cool was a
# BLUE GAIN of 1.09 and taking it to 1.00 removes it with red left byte-
# identical to before, so no new clipping is even possible.
GRADES = [
    (0.0, 17.55, {"NodeIndex": "1", "Slope": "1.02 1.03 0.969",
                  "Offset": "-0.008 -0.008 0.005", "Power": "1.09 1.09 1.06",
                  "Saturation": "0.92"}),      # act 1, the news: flat, neutral
    (17.55, 35.92, {"NodeIndex": "1", "Slope": "1.06 1.06 1.07",
                    "Offset": "-0.012 -0.012 -0.010", "Power": "1.06 1.06 1.06",
                    "Saturation": "1.18"}),    # act 2, the argument: UNTOUCHED
    (35.92, 99.0, {"NodeIndex": "1", "Slope": "1.000 1.070 1.090",
                   "Offset": "0.012 -0.012 -0.034", "Power": "1.03 1.05 1.09",
                   "Saturation": "1.30"}),     # act 3, the cost: warm, no blowout
]


# PairCounter counts on `1 - (1-p)**3` over COUNT_FRAMES frames starting at
# frame COUNT_START, and the ticks have to come off that same curve.
#
# They did not. The old loop was `0.14 + 0.80 * (1 - (1-p)**2)` — quadratic
# against the card's cubic, offset by 0.04s — so FOUR OF NINE TICKS FIRED
# AFTER THE NUMBER HAD STOPPED: the digits reached 274 at 0.783s and ticks
# 5-8 landed at 0.828, 0.890, 0.928 and 0.940s, the last two 12ms apart,
# which is a buzz, on a frozen frame.
#
# A real odometer ticks once per DIGIT TURN, i.e. at equal steps of VALUE,
# so the times are the inverse of the count curve: p = 1 - (1-v)**(1/3).
# That makes the ticks spread as the number settles rather than bunching,
# which is what "thinning as it eases out" always meant, and it tracks the
# curve automatically if the card is re-timed. Measured gaps: 33, 37, 41,
# 47, 56, 70, 99 then 384ms, with the last tick landing exactly on the final
# digit rather than 73ms after it.
COUNT_START, COUNT_FRAMES, TICKS = 6, 46, 8


def odometer(at: float, gain: float | None = None) -> list:
    out = []
    for k in range(TICKS + 1):
        v = k / TICKS
        p = 1 - (1 - v) ** (1 / 3)
        out.append(Cue(at + (COUNT_START + COUNT_FRAMES * p) / FPS, "tick",
                       gain if gain is not None else cue_gain("tick", -40.0, MASTER_GAIN),
                       "a digit turns on the counter"))
    return out


def check_schedule(frames_of) -> None:
    """No card may be trimmed by the one that follows it.

    Measured against the FILE's frame count, not the scheduled duration —
    those are the two numbers that drifted apart, and the file is the one
    Resolve actually places.
    """
    bad = []
    for (a, at_a, _), (b, at_b, _) in zip(EXHIBITS, EXHIBITS[1:]):
        have = frames_of(a)
        if have is None:
            continue
        end = round(at_a * FPS) + have
        if end + MIN_GAP_FRAMES > round(at_b * FPS):
            bad.append(f"{a} ends at frame {end}, {b} starts at "
                       f"{round(at_b * FPS)} — needs {MIN_GAP_FRAMES} clear")
    if bad:
        raise SystemExit("schedule collision:\n  " + "\n  ".join(bad))


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
    # by PEAK, not RMS: the shutter's 22 dB crest put it 6.4 dB over the
    # thunks when both were set to the same RMS.
    #
    # George: "those sound effects for the image popups toward the end is
    # perfect - needs to be slightly louder and it's great." Matched to the
    # thunks it measured -15.2 dBFS in the bed, 0.9 dB UNDER them. Target
    # -12.0 lands it around -12.9 — roughly +2.3 dB, a step you hear without
    # it becoming the loudest thing in the clip, and it leaves the shutter
    # about 1.4 dB over a thunk.
    #
    # Then, again: "make the snapshot noise louder". -12.0 -> -9.5, a
    # further +2.5 dB. It is now the loudest thing in the clip after
    # the speech, which is defensible because it is the ONLY cue left:
    # the two story cards are the only graphics, so the shutter is not
    # competing with a thunk any more, it is the whole sound design.
    shut = cue_gain_peak("shutter", -9.5, MASTER_GAIN)
    tck  = cue_gain("tick", -40.0, MASTER_GAIN)
    STORIES = {"rm_StoryPrx", "rm_StorySen"}
    # A SIDE TAB GETS NO CUE. rm_ChipAmer at 1.20 used to take the thunk and
    # then the 2.4s dedup swallowed rm_Tweet at 3.30 — so the clip's FIRST
    # REAL EXHIBIT arrived silent while a 1.8s chip announced itself. Sound
    # marks a card landing; a tab sliding in off the frame edge is not one.
    SILENT = {"rm_ChipAmer"}
    cues, last = [], -9.0
    for n, at, _d in EXHIBITS:
        if n in SILENT:
            continue
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
            cues += odometer(at, tck)
        last = at
    print("sfx:", bed(cues, total / FPS, out=OUT / "sfx.wav"))

    names = ["cap_kin.mov", "sfx.wav", f"{BAIT[0]}.mov", f"{CHAT[0]}.mov"] + \
            [f"{n}.mov" for n, _a, _d in EXHIBITS]
    r.GetMediaStorage().AddItemListToMediaPool([str(OUT / n) for n in names])
    pool = {c.GetName(): c for c in mp.GetRootFolder().GetClipList()}

    # Every card animates OUT over its last 6-15 frames, so a clip Resolve
    # trims short loses the end of that exit — which is the jolt the exit
    # was built to remove. The length comes from the FILE, not from a number
    # typed above; `check_schedule` has already proved no two files collide.
    def clip_frames(name):
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
             "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0",
             str(OUT / f"{name}.mov")], capture_output=True, text=True).stdout.strip()
        return int(out) if out.isdigit() else None

    check_schedule(clip_frames)
    print(f"schedule clear: {len(EXHIBITS)} graphics, no card trimmed by the next")

    ents = []

    def add(name, at, dur, track, media=None):
        c = pool.get(name)
        if c is None:
            print(f"  !! {name} missing from the media pool")
            return
        want = int(round(dur * FPS))
        # Only the Remotion cards. `cap_kin.mov` is the whole caption
        # track, so taking its length from the file would overrun the
        # timeline.
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

    for n, at, dur in EXHIBITS:
        add(f"{n}.mov", at, dur, 4)
    add(f"{CHAT[0]}.mov", CHAT[1], total / FPS, 3)
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
