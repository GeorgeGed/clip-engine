"""v20 — the popups carry facts, and the sound stops ringing.

George: "why are you adding a text of 'blown out of proportion', makes no
sense, stop making these random text cards - if you had useful information to
put on the screen like you did at the start it'd be fine - also i dont like
the specific ding you chose."

Both notes land on something I already had written down and then broke.

CARDS. The v19 chips restated his own captions in a box. The thing he points
at as the good one is the tweet card: it shows the viewer something they do
not have. The clip has such a thing sitting in frame the whole time and
illegible at phone size — the VCT Roster Board header he is reading from.
Three independent reads agree on it: 32 teams, 139 signed, 32 open slots,
82 bench/options, 78 staff, 274 not yet confirmed.

Two of those pairings survived a three-lens judging pass; "78 staff" was
unanimously filler (he never mentions staff) and so was dropping cards
altogether. The pass also caught a real error before it shipped: a lone
figure argues the opposite of his point — "32 OPEN SLOTS" reads as 32 jobs
going spare until you see the 274 chasing them. So every card is a PAIR, and
labels are verbatim from the board ("bench / options", never "bench"; "not
yet confirmed", never "274 players", since the board counts staff and bench
in other columns).

SOUND. `ding` decays over 547ms and `pop` over 216ms — the two longest in the
palette, and the two he rejected. Sustain is what makes a sound read as a
chime rather than an event landing. `tock` decays in 65ms.
"""
import json, subprocess, sys
from pathlib import Path
ROOT = Path("/Users/georgegeddes/Library/Application Support/Claude/scratch-workspaces/"
            "6d38ae6d-05dd-4827-8e46-76304910d38e/68f1a3b0-a8d1-4d98-a822-3205d41bec7a/"
            "scratch-2026-10-28-f045e2")
sys.path.insert(0, str(ROOT))
from engine.juice import shot_push_expr
from engine.sfx import Cue, bed
from engine.titles import hook, banner, stat
from engine.render_ffmpeg import _finish_audio
from engine import qc

SP = Path(__file__).parent
plan = json.load(open(SP / "v7_plan.json")); CUTS, DUR = plan["cuts"], plan["duration"]
b = [0.0] + CUTS + [DUR]; shots = list(zip(b, b[1:]))
pushes = [0.055, 0, 0.05, 0, 0.06]

hook(["YOU CAN END UP", "WITH NOTHING"], SP / "hook.png", accent_words=("NOTHING",))
banner("FNS ON JOB SECURITY IN VALORANT", SP / "banner.png")

SRC = "VCT Roster Board"
CARDS = [
    # over "you don't have enough job security" — the thesis, and its receipt
    (17.45, [("32", "open slots"), ("274", "not yet confirmed")],
     "scarcity behind the job-security claim"),
    # over "those people that get replaced won't have jobs for a while"
    (37.85, [("139", "signed"), ("82", "bench / options")],
     "how many are in the limbo he describes"),
]
HOLD = 3.2
sizes = [stat(items, SRC, SP / f"card{i}.png") for i, (_, items, _) in enumerate(CARDS)]
print("card sizes:", sizes)

CARD_IN, CARD_OUT = 1.65, 4.65
cues = [Cue(CARD_IN, "tock", 0.095, "the tweet card arrives")]
cues += [Cue(t, "tock", 0.095, f"fact card appears: {m}") for t, _, m in CARDS]
print(bed(cues, DUR, out=SP / "sfxbed.wav"))

z = shot_push_expr(shots, pushes)
HOOK_Y, BAN_Y, TWEET_Y, CARD_Y = 1050, 1500, 900, 1150
EQ = ("equalizer=f=3000:t=q:w=1.1:g=4,"
      "equalizer=f=9500:t=q:w=1.0:g=-7")

fg = [
    f"[0:v]zoompan=z='min(max({z},1.0),1.25)':d=1:x='iw/2-(iw/zoom/2)'"
    f":y='ih/2-(ih/zoom/2)':s=1080x1920:fps=60[base]",
    "[1]fade=t=out:st=1.5:d=0.5:alpha=1[hk]",
    f"[3]setpts=PTS+{CARD_IN}/TB,fade=t=in:st={CARD_IN}:d=0.12:alpha=1,"
    f"fade=t=out:st={CARD_OUT-0.3}:d=0.3:alpha=1[cd]",
    f"[base][hk]overlay=x=(W-w)/2:y={HOOK_Y}:enable='lt(t,2.05)'[v1]",
    f"[v1][2]overlay=x=(W-w)/2:y={BAN_Y}[v2]",
    f"[v2][cd]overlay=x=(W-w)/2:y={TWEET_Y}:enable='between(t,{CARD_IN},{CARD_OUT})'[v3]",
]
prev = "v3"
for i, (t, _items, _m) in enumerate(CARDS):
    src, out = 5 + i, f"p{i}"
    end = t + HOLD
    fg.append(f"[{src}]setpts=PTS+{t}/TB,fade=t=in:st={t}:d=0.10:alpha=1,"
              f"fade=t=out:st={end-0.25}:d=0.25:alpha=1[{src}f]")
    fg.append(f"[{prev}][{src}f]overlay=x=(W-w)/2"
              f":y='{CARD_Y}+16*max(0\\,1-(t-{t})/0.16)'"
              f":enable='between(t,{t},{end})'[{out}]")
    prev = out
fg.append(f"[{prev}]null[vout]")
fg.append(f"[0:a]{EQ}[eq]")
fg.append("[eq][4:a]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]")

cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(ROOT / "renders/clip08_v7_raw.mov"),
       "-loop", "1", "-framerate", "60", "-t", "3", "-i", str(SP / "hook.png"),
       "-i", str(SP / "banner.png"),
       "-loop", "1", "-framerate", "60", "-t", "3.2", "-i", str(SP / "tweet_card.png"),
       "-i", str(SP / "sfxbed.wav")]
for i in range(len(CARDS)):
    cmd += ["-loop", "1", "-framerate", "60", "-t", str(HOLD + 0.4),
            "-i", str(SP / f"card{i}.png")]
cmd += ["-filter_complex", ";".join(fg), "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-crf", "19", "-preset", "medium", "-pix_fmt", "yuv420p",
        "-c:a", "pcm_s16le", "-shortest", str(ROOT / "renders/clip08_v20_t.mov")]
subprocess.run(cmd, check=True)

_finish_audio(ROOT / "renders/clip08_v20_t.mov",
              {"audio": {"target_lufs": -14.0, "true_peak_dbtp": -1.0},
               "render": {"audio_codec": "aac"}}, ROOT / "renders/clip08_v20.mp4")
print(qc.check(ROOT / "renders/clip08_v20.mp4").report())
