"""Asserts the source-quality guard actually refuses footage too small to use.

The fault this exists for: the first FNS run pulled 720p60 and all 50 clips
were cut from it before anyone measured the files. A 1080x1920 master built
from 720p source is upscaled, and the cost is invisible until the look has
already been tuned against soft footage.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from engine import ingest

fails: list[str] = []


def ok(name: str, cond: bool) -> None:
    print(f"  {'pass' if cond else 'FAIL'}  {name}")
    if not cond:
        fails.append(name)


def frame(d: Path, size: str) -> Path:
    out = d / f"{size}.mp4"
    r = subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", f"color=c=navy:s={size}:r=60:d=1",
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(out)],
        capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:300])
    return out


def run() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ingest-fixtures-"))
    work = tmp / "work"

    print("source height guard")
    p720 = frame(tmp, "1280x720")
    try:
        ingest.fetch(str(p720), work)
        ok("720p source refused", False)
    except RuntimeError as e:
        ok("720p source refused", "1080" in str(e))
        ok("error names the measured size", "1280x720" in str(e))

    s = ingest.fetch(str(p720), work, min_height=None)
    ok("min_height=None opts out", (s.width, s.height) == (1280, 720))

    p1080 = frame(tmp, "1920x1080")
    s = ingest.fetch(str(p1080), work)
    ok("1080p source accepted", (s.width, s.height) == (1920, 1080))

    p4k = frame(tmp, "2560x1440")
    s = ingest.fetch(str(p4k), work)
    ok("taller than 1080 accepted", s.height == 1440)

    ok("default is the 1080 floor", ingest.MIN_SOURCE_HEIGHT == 1080)

    print()
    print(f"{'ALL PASS' if not fails else str(len(fails)) + ' FAILED'}")
    for f in fails:
        print("  -", f)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(run())
