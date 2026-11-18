#!/usr/bin/env python3
"""Fast local previews of a job's clips, for iterating on how clips look.

    python3 preview.py                 every clip of the FNS job
    python3 preview.py 3 9             just clips 3 and 9
    python3 preview.py --job <name> -j 2
    python3 preview.py --font anton 3  set clip 3's caption font, then build

Builds with CLIP_PREVIEW=1, which skips the facecam super-resolution pass
(engine/upscale) — most of a clip's build time on a Mac — so this is for
judging layout, timing and graphics, not final picture. Modal never sets it.
Several clips build at once. Renders land in renders/<job>-NN.mp4.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(ROOT))
from engine import caption_fonts  # noqa: E402
from pipeline import core  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("clips", nargs="*", type=int, help="clip numbers; all when omitted")
    ap.add_argument("--job", default="fns-2926995155")
    ap.add_argument("-j", type=int, default=3, help="clips built at once")
    ap.add_argument("--font", choices=sorted(caption_fonts.FONTS),
                    help="write this caption font into the chosen clips' specs first")
    a = ap.parse_args()
    os.environ["CLIP_PREVIEW"] = "1"
    os.environ["CLIP_NATIVE_CHAT"] = "1"      # draw chat the way Modal does
    specs = ROOT / "jobs" / a.job / "specs"
    nums = a.clips or sorted(int(p.stem) for p in specs.glob("[0-9][0-9].json"))
    for n in nums if a.font else []:
        p = specs / f"{n:02d}.json"
        spec = json.loads(p.read_text())
        spec["clip"]["caption_font"] = a.font
        p.write_text(json.dumps(spec, indent=1, ensure_ascii=False) + "\n")
    t0 = time.time()

    def one(n: int) -> str:
        t = time.time()
        try:
            out = core.build(specs / f"{n:02d}.json", log_path=specs / f"{n:02d}.log")
            return f"clip {n}: {out.relative_to(ROOT)} in {time.time() - t:.0f}s"
        except Exception as e:  # noqa: BLE001
            return f"clip {n}: FAILED, see {specs.relative_to(ROOT)}/{n:02d}.log ({str(e)[-160:]})"

    with ThreadPoolExecutor(a.j) as ex:
        for line in ex.map(one, nums):
            print(line, flush=True)
    print(f"{len(nums)} clip(s) in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
