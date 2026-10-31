"""v21 — the card IS the exhibit, the banner is gone, the sound has weight.

George: "the 'fns on job security' bit doesnt really make sense, i prefer not
to have that as a popup ... animations like that are useful and informative
but i dont like the design - looks vibe coded ... ding needs to be slightly
louder and need a different one."

DESIGN. Going back to R1 for how it presents a stat panel settled it: **it
does not design one.** The Leetify card at 0:08 is a screenshot of a real
page composited in, exactly like the tweet card at the head of this clip. So
these cards are now the actual pixels of the roster-board stat strip,
magnified ~2x, with an accent rule under the figures being pointed at. It
cannot be mis-transcribed and it cannot look like a generic component,
because nothing about it is drawn.

BANNER. Removed. Worth recording why it read wrong: R2's persistent banner
says "IT'S EITHER PRX OR G2" — a CLAIM, in the speaker's voice. Mine said
"FNS ON JOB SECURITY IN VALORANT", which is metadata about the video. A
banner that describes the clip instead of asserting something is the defect.

SOUND. Fourth attempt. The three rejected were a bell (547ms), a shorter
bell (216ms) and a woodblock (65ms) — all pitched chimes. `thunk` is the
other register: low, physical, gone in 87ms. Level is now set by TARGET RMS
via sfx.cue_gain, not by a peak gain, because peak-normalised sounds span
9 dB of RMS and that is why levelling kept missing.
"""
import json, subprocess, sys
from pathlib import Path
ROOT = Path("/Users/georgegeddes/Library/Application Support/Claude/scratch-workspaces/"
            "6d38ae6d-05dd-4827-8e46-76304910d38e/68f1a3b0-a8d1-4d98-a822-3205d41bec7a/"
            "scratch-2026-10-28-f045e2")
sys.path.insert(0, str(ROOT))
from engine.juice import shot_push_expr
from engine.sfx import Cue, bed, cue_gain
from engine.titles import hook, exhibit
from engine.render_ffmpeg import _finish_audio
from engine import qc

SP = Path(__file__).parent
plan = json.load(open(SP / "v7_plan.json")); CUTS, DUR = plan["cuts"], plan["duration"]
b = [0.0] + CUTS + [DUR]; shots = list(zip(b, b[1:]))
pushes = [0.055, 0, 0.05, 0, 0.06]

hook(["YOU CAN END UP", "WITH NOTHING"], SP / "hook.png", accent_words=("NOTHING",))

# Blocks 2..5 of the strip, a CONTIGUOUS run: 32 open slots | 82 bench /
# options | 78 staff | 274 not yet confirmed. Same crop both times so the
# viewer learns the graphic once; only the underline moves.
CARDS = [
    (17.45, (2, 5), "scarcity behind the job-security claim"),
    (37.85, (3,),   "how many are in the limbo he describes"),
]
HOLD = 3.4
for i, (_, hl, _m) in enumerate(CARDS):
    print(" card", i, exhibit(SP / "src_plate.png", SP / f"ex{i}.png", highlight=hl))

TWEET_IN, TWEET_OUT = 1.65, 4.65
MASTER_GAIN, TARGET_RMS = 6.2, -30.0       # measured on this clip; -3 dB louder
g = cue_gain("thunk", TARGET_RMS, MASTER_GAIN)
print(f" thunk gain {g:.4f}")
cues = [Cue(TWEET_IN, "thunk", g, "the tweet card arrives")]
cues += [Cue(t, "thunk", g, f"exhibit card appears: {m}") for t, _, m in CARDS]
print(bed(cues, DUR, out=SP / "sfxbed.wav"))

z = shot_push_expr(shots, pushes)
HOOK_Y, TWEET_Y, CARD_Y = 1050, 900, 1180
EQ = ("equalizer=f=3000:t=q:w=1.1:g=4,"
      "equalizer=f=9500:t=q:w=1.0:g=-7")

fg = [
    f"[0:v]zoompan=z='min(max({z},1.0),1.25)':d=1:x='iw/2-(iw/zoom/2)'"
    f":y='ih/2-(ih/zoom/2)':s=1080x1920:fps=60[base]",
    "[1]fade=t=out:st=1.5:d=0.5:alpha=1[hk]",
    f"[2]setpts=PTS+{TWEET_IN}/TB,fade=t=in:st={TWEET_IN}:d=0.12:alpha=1,"
    f"fade=t=out:st={TWEET_OUT-0.3}:d=0.3:alpha=1[cd]",
    f"[base][hk]overlay=x=(W-w)/2:y={HOOK_Y}:enable='lt(t,2.05)'[v1]",
    f"[v1][cd]overlay=x=(W-w)/2:y={TWEET_Y}:enable='between(t,{TWEET_IN},{TWEET_OUT})'[v2]",
]
prev = "v2"
for i, (t, _hl, _m) in enumerate(CARDS):
    src, out = 4 + i, f"p{i}"
    end = t + HOLD
    fg.append(f"[{src}]setpts=PTS+{t}/TB,fade=t=in:st={t}:d=0.10:alpha=1,"
              f"fade=t=out:st={end-0.25}:d=0.25:alpha=1[{src}f]")
    fg.append(f"[{prev}][{src}f]overlay=x=(W-w)/2"
              f":y='{CARD_Y}+16*max(0\\,1-(t-{t})/0.16)'"
              f":enable='between(t,{t},{end})'[{out}]")
    prev = out
fg.append(f"[{prev}]null[vout]")
fg.append(f"[0:a]{EQ}[eq]")
fg.append("[eq][3:a]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]")

cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(ROOT / "renders/clip08_v7_raw.mov"),
       "-loop", "1", "-framerate", "60", "-t", "3", "-i", str(SP / "hook.png"),
       "-loop", "1", "-framerate", "60", "-t", "3.2", "-i", str(SP / "tweet_card.png"),
       "-i", str(SP / "sfxbed.wav")]
for i in range(len(CARDS)):
    cmd += ["-loop", "1", "-framerate", "60", "-t", str(HOLD + 0.4),
            "-i", str(SP / f"ex{i}.png")]
cmd += ["-filter_complex", ";".join(fg), "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-crf", "19", "-preset", "medium", "-pix_fmt", "yuv420p",
        "-c:a", "pcm_s16le", "-shortest", str(ROOT / "renders/clip08_v21_t.mov")]
subprocess.run(cmd, check=True)

_finish_audio(ROOT / "renders/clip08_v21_t.mov",
              {"audio": {"target_lufs": -14.0, "true_peak_dbtp": -1.0},
               "render": {"audio_codec": "aac"}}, ROOT / "renders/clip08_v21.mp4")
print(qc.check(ROOT / "renders/clip08_v21.mp4").report())
