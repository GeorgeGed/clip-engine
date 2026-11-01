#!/usr/bin/env python3
"""Render Remotion compositions to alpha movies Resolve can composite.

This existed only as a shell command retyped each turn, which is how a
previous round shipped four cards whose SOURCE had been edited but whose
.mov files had not been rebuilt. Stills prove the source changed; they do
not rebuild the clips on the timeline. So it is a script now.

Two things the CLI will not tell you:

* **Remotion cannot write alpha from the CLI here.** `--codec=prores
  --prores-profile=4444` yields `yuv422p12le`, which has no alpha plane,
  and `--pixel-format=yuva444p10le` errors out. `npx remotion render --help`
  does not list the transparency flags either. The route that works is
  `--sequence --image-format=png` and then our own encode.
* **It cannot fetch its own headless shell here** — it dies with "No browser
  found for rendering frames". System Chrome works.

qtrle, not ProRes 4444: both are lossless with alpha, but these frames are
almost entirely transparent and RLE collapses that. ProRes filled the disk.

Usage:  ./.venv/bin/python render_remotion.py Tweet StoryPrx StorySen
        ./.venv/bin/python render_remotion.py --all
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
PROJ = ROOT / "vendor/remotion-clip08"
OUT = ROOT / "jobs/fns-2905408276/overlays"
TMP = Path("/private/tmp/claude-501/remotion-seq")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
FPS = 60


def render(comp: str) -> Path:
    seq = TMP / comp
    if seq.exists():
        shutil.rmtree(seq)
    seq.mkdir(parents=True)
    subprocess.run(
        ["npx", "remotion", "render", "src/index.ts", comp, str(seq),
         "--sequence", "--image-format=png", "--concurrency=4",
         f"--browser-executable={CHROME}", "--log=error"],
        cwd=PROJ, check=True)
    n = len(list(seq.glob("*.png")))
    dst = OUT / f"rm_{comp}.mov"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-framerate", str(FPS),
         # Remotion zero-pads to the sequence's width (element-000.png for
         # 210 frames, element-0000.png past 1000), so the pattern has to be
         # derived from the frame count, not hard-coded to %d.
         "-i", str(seq / f"element-%0{len(str(n - 1))}d.png"),
         "-c:v", "qtrle", "-pix_fmt", "argb", str(dst)], check=True)
    shutil.rmtree(seq)
    mb = dst.stat().st_size / 1e6
    print(f"  {comp:12s} {n:4d} frames -> {dst.name}  {mb:.0f} MB")
    return dst


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        sys.exit("name the compositions, or --all")
    if args == ["--all"]:
        import re
        src = (PROJ / "src/Root.tsx").read_text()
        args = re.findall(r'<Composition id="([A-Za-z0-9_]+)"', src)
    print(f"rendering {len(args)}: {', '.join(args)}")
    for c in args:
        render(c)
