#!/usr/bin/env python3
"""Render the Resolve timeline and apply the one finishing pass.

Lived in /tmp for several turns and kept getting cleaned up mid-session.

The finish is ffmpeg for two measured reasons: Resolve's
`NormalizeAudioLevel` applies gain without true-peak limiting, and a caption
title is a fixed 300 frames so the last one overhangs the picture by a few
frames that render black. `-t` with `-c:v copy` cuts at a keyframe and
misses them, hence `-frames:v` on the delivery encode.
"""
import subprocess, sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from engine.resolve_driver import render
from engine.render_ffmpeg import _finish_audio
from engine import qc

PICTURE_FRAMES = 2812
EQ = ("highpass=f=85,equalizer=f=280:t=q:w=1.0:g=-2.5,"
      "equalizer=f=3000:t=q:w=1.1:g=4,equalizer=f=9500:t=q:w=1.0:g=-7")


def main(tag: str) -> None:
    src = ROOT / f"renders/{tag}_src.mov"
    src.unlink(missing_ok=True)
    res = render(out_dir=str(ROOT / "renders"), preset="H.264 Master",
                 filename=f"{tag}_src")
    print("resolve:", res["status"].get("JobStatus"),
          f"{res['status'].get('TimeTakenToRenderInMs', 0) / 1000:.0f}s")

    eq, mid = ROOT / "renders/_eq.mov", ROOT / "renders/_mid.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
                    "-t", f"{PICTURE_FRAMES / 60:.4f}", "-af", EQ,
                    "-c:v", "libx264", "-crf", "17", "-preset", "medium",
                    "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", str(eq)], check=True)
    _finish_audio(eq, {"audio": {"target_lufs": -14.0, "true_peak_dbtp": -1.0},
                       "render": {"audio_codec": "aac"}}, mid)
    out = ROOT / "renders/clip08_FINAL.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mid),
                    "-frames:v", str(PICTURE_FRAMES), "-c:v", "libx264", "-crf", "18",
                    "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "copy",
                    "-movflags", "+faststart", str(out)], check=True)
    eq.unlink(missing_ok=True); mid.unlink(missing_ok=True)
    print(qc.check(out).report())


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "clip08_v35")
