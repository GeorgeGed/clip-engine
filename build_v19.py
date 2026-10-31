"""v19 — popups with low dings, and the loose impacts removed.

George: "again random sound effect out of place and useless ... i'd prefer to
have popups with low volume dings."

The diagnosis the earlier passes missed: a cue tied to a VOCAL PEAK has
nothing on screen to explain it, so it reads as random however well the peak
was measured. A cue tied to a VISUAL EVENT explains itself — the viewer sees
a card arrive and hears it arrive. So every sound in this version belongs to
a popup, and there are no sounds that do not.

Out: the three `impact` cues at 25.70 / 35.65 / 40.90 (vocal peaks).
In:   four supporting chips at the beats of the argument, plus the tweet
      card, each with a soft `pop` at gain 0.11 — a 0.22s two-partial ding,
      not the 0.55s four-partial bell that was rejected at 0.45-0.80.
"""
import json, subprocess, sys
from pathlib import Path
ROOT = Path("/Users/georgegeddes/Library/Application Support/Claude/scratch-workspaces/"
            "6d38ae6d-05dd-4827-8e46-76304910d38e/68f1a3b0-a8d1-4d98-a822-3205d41bec7a/"
            "scratch-2026-10-28-f045e2")
sys.path.insert(0, str(ROOT))
from engine.juice import shot_push_expr
from engine.sfx import Cue, bed
from engine.titles import hook, banner, chip
from engine.render_ffmpeg import _finish_audio
from engine import qc

SP = Path(__file__).parent
plan = json.load(open(SP / "v7_plan.json")); CUTS, DUR = plan["cuts"], plan["duration"]
b = [0.0] + CUTS + [DUR]; shots = list(zip(b, b[1:]))
pushes = [0.055, 0, 0.05, 0, 0.06]

hook(["YOU CAN END UP", "WITH NOTHING"], SP / "hook.png", accent_words=("NOTHING",))
banner("FNS ON JOB SECURITY IN VALORANT", SP / "banner.png")

# Each chip sits on the line it supports, and holds while he finishes it.
# No chip on the payoff at 50.6s: the hook title already says those words.
POPUPS = [
    (7.05,  '"BLOWN OUT OF PROPORTION"', 'his claim, as he states it'),
    (17.45, "NO JOB SECURITY",           'the cost he names'),
    (31.30, "1-YEAR CONTRACTS",          'the concrete term he cites'),
    (37.85, "REPLACED = NO JOB",         'the consequence he lands on'),
]
HOLD = 2.6
for i, (t, text, _) in enumerate(POPUPS):
    chip(text, SP / f"chip{i}.png")

CARD_IN, CARD_OUT = 1.65, 4.65
cues = [Cue(CARD_IN, "pop", 0.11, "the tweet card arrives")]
cues += [Cue(t, "pop", 0.11, f"popup appears: {m}") for t, _, m in POPUPS]
print(bed(cues, DUR, out=SP / "sfxbed.wav"))

z = shot_push_expr(shots, pushes)
HOOK_Y, BAN_Y, CARD_Y, CHIP_Y = 1050, 1500, 900, 1180
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
    f"[v2][cd]overlay=x=(W-w)/2:y={CARD_Y}:enable='between(t,{CARD_IN},{CARD_OUT})'[v3]",
]
# Chips are inputs 5.. ; the bed is input 4.
prev = "v3"
for i, (t, _text, _m) in enumerate(POPUPS):
    src, out = 5 + i, f"p{i}"
    end = t + HOLD
    fg.append(f"[{src}]setpts=PTS+{t}/TB,fade=t=in:st={t}:d=0.10:alpha=1,"
              f"fade=t=out:st={end-0.25}:d=0.25:alpha=1[{src}f]")
    # 14px settle over 0.16s — a real pop, since overlay y CAN take t
    # (scale cannot, which is why this is a move and not a grow).
    fg.append(f"[{prev}][{src}f]overlay=x=(W-w)/2"
              f":y='{CHIP_Y}+14*max(0\\,1-(t-{t})/0.16)'"
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
for i in range(len(POPUPS)):
    cmd += ["-loop", "1", "-framerate", "60", "-t", str(HOLD + 0.4),
            "-i", str(SP / f"chip{i}.png")]
cmd += ["-filter_complex", ";".join(fg), "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-crf", "19", "-preset", "medium", "-pix_fmt", "yuv420p",
        "-c:a", "pcm_s16le", "-shortest", str(ROOT / "renders/clip08_v19_t.mov")]
subprocess.run(cmd, check=True)

_finish_audio(ROOT / "renders/clip08_v19_t.mov",
              {"audio": {"target_lufs": -14.0, "true_peak_dbtp": -1.0},
               "render": {"audio_codec": "aac"}}, ROOT / "renders/clip08_v19.mp4")
print(qc.check(ROOT / "renders/clip08_v19.mp4").report())
