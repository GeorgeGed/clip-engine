"""Cut raw clips at the chosen in/out points. No styling, no reframe, no captions.

Deliberately unedited: the point is to judge WHERE the clip starts and stops.
Any crop or caption would hide the thing being reviewed.

Re-encodes rather than stream-copying, because `-c copy` snaps to keyframes and
would move the in-point by up to a second — which is exactly the error under
review.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def cut(video: str | Path, t_in: float, t_out: float, out_path: str | Path,
        *, crf: int = 20, preset: str = "veryfast") -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    dur = float(t_out) - float(t_in)
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-ss", f"{float(t_in):.3f}", "-i", str(video), "-t", f"{dur:.3f}",
        "-c:v", "libx264", "-crf", str(crf), "-preset", preset,
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart", str(out_path),
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed for {out_path.name}:\n{p.stderr[-800:]}")
    return out_path


def slug(text: str, limit: int = 46) -> str:
    import re
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (text or "clip")).strip("-").lower()
    return (s[:limit] or "clip").rstrip("-")
