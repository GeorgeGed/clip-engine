"""Pull source media. Twitch VODs, Twitch clips, YouTube, or a local file.

A full VOD is hours long, so a VOD URL with a time window downloads only that
window via yt-dlp --download-sections. Nothing else in the pipeline cares where
the media came from.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class Source:
    path: str
    url: str | None
    owner: str
    duration: float
    fps: float
    width: int
    height: int
    window_offset: float = 0.0  # seconds added to local time to get VOD time

    def as_dict(self) -> dict:
        return asdict(self)


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def _hhmmss(sec: float) -> str:
    sec = max(0.0, float(sec))
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def owner_from_url(url: str) -> str:
    m = re.search(r"twitch\.tv/([^/?#]+)/clip/", url) or re.search(r"twitch\.tv/([^/?#]+)", url)
    if m and m.group(1) not in ("videos", "directory"):
        return m.group(1).lower()
    return "unknown"


def probe(path: str | Path) -> dict:
    out = _run([
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_streams", "-show_format", str(path),
    ]).stdout
    data = json.loads(out)
    v = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    if v is None:
        raise RuntimeError(f"no video stream in {path}")
    num, den = (v.get("r_frame_rate") or "60/1").split("/")
    fps = float(num) / float(den or 1)
    return {
        "duration": float(data["format"].get("duration") or 0.0),
        "fps": round(fps, 4),
        "width": int(v["width"]),
        "height": int(v["height"]),
        "has_audio": any(s["codec_type"] == "audio" for s in data["streams"]),
    }


def _require_height(info: dict, min_height: int | None, what: str) -> None:
    """Refuse a source too small for a 1080x1920 master."""
    if min_height is None:
        return
    h = int(info.get("height") or 0)
    if h < min_height:
        raise RuntimeError(
            f"{what} is {info.get('width')}x{h}; a 1080x1920 master needs at "
            f"least {min_height}px of source height. Check the available "
            f"renditions (`yt-dlp --list-formats`) and pull the taller one, or "
            f"pass min_height=None if this really is the best available."
        )


# A 9:16 master is 1920 tall. Anything under 1080p source is upscaled, and the
# cost is invisible until the look has already been tuned against soft footage.
# Measured the hard way: the first FNS run pulled 720p60 and all 50 clips were
# cut from it before anyone checked.
MIN_SOURCE_HEIGHT = 1080


def fetch(
    url_or_path: str,
    out_dir: str | Path,
    *,
    start: float | None = None,
    end: float | None = None,
    owner: str | None = None,
    min_height: int | None = MIN_SOURCE_HEIGHT,
) -> Source:
    """Download (or adopt) the source and return a probed Source.

    Raises if the result is shorter than `min_height` pixels tall. Pass
    `min_height=None` to accept whatever the platform offers — correct for a
    Twitch clip or an old VOD that genuinely has no better rendition.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    local = Path(url_or_path)
    if local.exists():
        info = probe(local)
        _require_height(info, min_height, str(local))
        return Source(
            path=str(local.resolve()), url=None, owner=(owner or "local"),
            duration=info["duration"], fps=info["fps"],
            width=info["width"], height=info["height"],
        )

    target = out_dir / "source.mp4"
    cmd = [
        "yt-dlp", "-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "--merge-output-format", "mp4", "-o", str(target), "--no-playlist", "--no-progress",
    ]
    offset = 0.0
    if start is not None:
        tail = _hhmmss(end) if end is not None else ""
        cmd += ["--download-sections", f"*{_hhmmss(start)}-{tail}", "--force-keyframes-at-cuts"]
        offset = float(start)
    cmd.append(url_or_path)
    _run(cmd)

    if not target.exists():
        found = sorted(out_dir.glob("source.*"))
        if not found:
            raise RuntimeError("yt-dlp produced no file")
        target = found[0]

    info = probe(target)
    _require_height(info, min_height, url_or_path)
    return Source(
        path=str(target.resolve()), url=url_or_path,
        owner=(owner or owner_from_url(url_or_path)),
        duration=info["duration"], fps=info["fps"],
        width=info["width"], height=info["height"],
        window_offset=offset,
    )


def extract_audio(video: str | Path, out_wav: str | Path, *, sr: int = 16000) -> Path:
    out_wav = Path(out_wav)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    _run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-vn",
          "-ac", "1", "-ar", str(sr), "-c:a", "pcm_s16le", str(out_wav)])
    return out_wav


def measure_loudness(path: str | Path) -> dict:
    """Integrated loudness and true peak via ffmpeg's loudnorm, first pass."""
    p = subprocess.run(
        ["ffmpeg", "-i", str(path), "-af", "loudnorm=print_format=json", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    blob = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", p.stderr, re.S)
    if not blob:
        return {}
    d = json.loads(blob.group(0))
    return {
        "measured_lufs": float(d["input_i"]),
        "true_peak_dbtp": float(d["input_tp"]),
        "lra": float(d["input_lra"]),
    }


def opening_frames_qa(video: str | Path, *, seconds: float = 0.5) -> dict:
    """Is the opening black, or sitting on a menu / loading screen?

    Black: mean luma under 16. Menu: very low motion plus low edge density,
    which is what a static UI screen looks like next to live gameplay.
    """
    import numpy as np
    import cv2

    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 60.0
    n = max(3, int(fps * seconds))
    frames = []
    for _ in range(n):
        ok, fr = cap.read()
        if not ok:
            break
        frames.append(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY))
    cap.release()
    if not frames:
        return {"first_frames_black": True, "first_frames_menu": False}

    lumas = [float(f.mean()) for f in frames]
    diffs = [float(np.abs(frames[i].astype(np.int16) - frames[i - 1].astype(np.int16)).mean())
             for i in range(1, len(frames))] or [0.0]
    edges = float(np.mean([cv2.Canny(f, 100, 200).mean() for f in frames]))

    return {
        "first_frames_black": max(lumas) < 16.0,
        "first_frames_menu": (sum(diffs) / len(diffs) < 0.8) and edges < 6.0,
        "_luma": round(sum(lumas) / len(lumas), 2),
        "_motion": round(sum(diffs) / len(diffs), 3),
        "_edges": round(edges, 2),
    }


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="fetch and probe a source")
    ap.add_argument("url_or_path")
    ap.add_argument("-o", "--out-dir", default="jobs/_scratch")
    ap.add_argument("--start", type=float)
    ap.add_argument("--end", type=float)
    ap.add_argument("--owner")
    a = ap.parse_args()
    s = fetch(a.url_or_path, a.out_dir, start=a.start, end=a.end, owner=a.owner)
    print(json.dumps(s.as_dict(), indent=2))
