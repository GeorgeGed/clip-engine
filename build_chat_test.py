#!/usr/bin/env python3
"""Assemble the chat-overlay TEST clip.

Layout, following the reference Short George sent:

    y    0 - 806   facecam, from the clean base cut
    y  806 - 985   a black band, where the captions sit
    y  985 -1920   the chat card

The reference puts its seam at y 932 and its chat card at 1055, with the
captions in the band between. **We cannot match that seam.** Its facecam
fills 1080x932, an aspect of 1.16:1, which means a near-square crop out of
the streamer's webcam. Ours is a 464x262 region of the VOD frame — already
a 3x upscale to fill 1080x806 — and cropping it to 1.16:1 would mean
taking 304x262 and blowing it up 3.55x. So the seam stays at 0.42 and the
chat card starts below the captions instead.

Audio is the base cut's, NOT the delivered mix: the delivered bed carries a
thunk or a shutter for each graphics card, and none of those cards is on
screen here. A cue that marks nothing is the defect this project spent four
sound designs learning about.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
BASE = ROOT / "renders/styles/_base.mov"
CAPS = ROOT / "jobs/fns-2905408276/overlays/cap_kin.mov"
CHAT = ROOT / "jobs/fns-2905408276/overlays/rm_Chat.mov"
OUT = ROOT / "renders/clip08_chat_test.mp4"
FRAMES = 2812                    # match the delivered picture length
SEAM, CARD_TOP = 806, 985


def main():
    for p in (BASE, CAPS, CHAT):
        if not p.exists():
            sys.exit(f"missing: {p}")
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-i", str(BASE), "-i", str(CAPS), "-i", str(CHAT),
        "-filter_complex",
        # facecam only, on black
        f"[0:v]crop=1080:{SEAM}:0:0,pad=1080:1920:0:0:black[bg];"
        # the chat card, which is opaque below CARD_TOP
        f"[bg][2:v]overlay=0:0:format=auto[withchat];"
        # captions last, so they sit over everything
        f"[withchat][1:v]overlay=0:0:format=auto[v]",
        "-map", "[v]", "-map", "0:a",
        "-frames:v", str(FRAMES),
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        str(OUT)]
    subprocess.run(cmd, check=True)
    mb = OUT.stat().st_size / 1e6
    print(f"  {OUT.name}  {mb:.1f} MB")


if __name__ == "__main__":
    main()
