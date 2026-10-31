"""The only step after Resolve: EQ, then two-pass loudness.

Everything visual is now a clip on the Resolve timeline. This stays outside
it for one measured reason: `Timeline.NormalizeAudioLevel` offers BS.1770-4
and EBU R128 but applies GAIN ONLY. Clip 8 sits at -20.2 LUFS with a
-3.5 dBTP peak, so the +6.2 dB to reach -14 would push it to +2.7 dBTP and
clip straight through the ceiling. Two-pass `loudnorm` applies gain and
true-peak limiting together.

The EQ rides along: +4 dB at 3 kHz and -7 dB at 9.5 kHz, the deltas measured
against R1/R2's average spectrum.
"""
import subprocess, sys
from pathlib import Path
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from engine.render_ffmpeg import _finish_audio
from engine import qc

SRC = ROOT / "renders/clip08_v27_resolve.mov"
EQD = ROOT / "renders/clip08_v27_eq.mov"
OUT = ROOT / "renders/clip08_v27.mp4"

EQ = "equalizer=f=3000:t=q:w=1.1:g=4,equalizer=f=9500:t=q:w=1.0:g=-7"

# Trim to the PICTURE. A caption title is a fixed 300 frames and cannot be
# trimmed through the API, so the last one overhangs V1 by however much the
# keeps fall short of round(out_dur * fps) — 4 frames here, which render as
# black and which QC correctly flags. Those frames hold nothing.
PICTURE_FRAMES = 2812
DUR = PICTURE_FRAMES / 60
subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(SRC), "-t", f"{DUR:.4f}",
                "-af", EQ, "-c:v", "copy", "-c:a", "pcm_s16le", str(EQD)], check=True)
_finish_audio(EQD, {"audio": {"target_lufs": -14.0, "true_peak_dbtp": -1.0},
                    "render": {"audio_codec": "aac"}}, OUT)
EQD.unlink(missing_ok=True)
print(qc.check(OUT).report())
