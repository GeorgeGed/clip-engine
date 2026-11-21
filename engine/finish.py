"""The two story moves that act on the picture itself: the payoff STAMP and
the COLD OPEN. Both come from the clip's plan (engine/plan) and neither moves
an in- or out-point or invents a second of footage.

THE STAMP freezes the content pane on the frame he says the payoff word,
greys it, and lets one big word land on it, while the facecam, the captions
and his voice keep running. It is a graph stage on the two-pane base, BEFORE
the overlays, because the captions sit on the seam: freezing the finished
file would freeze the half of a caption that falls in the lower pane.

THE COLD OPEN plays a stretch of the payoff (1-4s, sentence-bounded, chosen
by the plan) and then the whole clip from its first frame. It is cut out of
the finished file, so the tease is exactly what the viewer sees again later,
captions and all, and it runs before the delivery gate, which then measures
the file that ships.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

STAMP_S = 1.2            # how long the pane holds still
STAMP_SAT = 0.0          # grey
STAMP_DIM = -0.10        # and a touch darker, so the word reads over anything
JOIN_FADE = 0.02         # an audio fade at each join, so a cut is not a click

COLOUR_BSF = "h264_metadata=colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1"


def still_graph(src: str, out: str, *, frame: int, top: int, height: int,
                width: int = 1080) -> str:
    """[src] to [out]: the lower pane (y >= top) of one frame, greyed. Run on
    its own with -frames:v 1, so it stops decoding at that frame."""
    return (f"[{src}]select='eq(n,{frame})',crop={width}:{height}:0:{top},"
            f"hue=s={STAMP_SAT},eq=brightness={STAMP_DIM}[{out}]")


def hold_graph(src: str, out: str, *, still: Path, first: int, frames: int, top: int,
               fps: float) -> str:
    """[src] to [out] with @still@ laid over the lower pane for @frames@ frames
    from frame @first@.

    THE STILL IS A FILE, NOT A BRANCH OF THE SAME PICTURE. Taking the frozen
    frame from a split of [src] (freezeframes, or a trim of a split) makes
    the overlay wait for that branch, so ffmpeg queued every frame up to the
    stamp in memory: two probe clips sat in the composite for 44 minutes.
    A movie source has its first frame ready at once, so nothing waits.
    Its timestamps are whole frames in a 1/fps timebase: seconds in the
    movie's default timebase rounded, and held 35 or 37 frames for 36."""
    return (f"movie=filename='{still}',loop=loop={frames - 1}:size=1:start=0,"
            f"settb=1/{fps:g},setpts=N+{first}[fz_p];"
            f"[{src}][fz_p]overlay=0:{top}:eof_action=pass[{out}]")


def duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return float(r.stdout.strip())


def cold_open(src: Path, out: Path, *, start: float, end: float, fps: float,
              crf: int = 17) -> float:
    """Write [start, end) of `src` followed by all of it to `out`. Returns the
    tease's length in seconds, which shifts everything after it."""
    a, b = round(start * fps), round(end * fps)
    if b <= a:
        raise ValueError(f"empty cold open {start}-{end}")
    t0, t1 = a / fps, b / fps
    tease = t1 - t0
    full = duration(src)
    f = JOIN_FADE
    graph = (f"[0:v]split[v0][v1];"
             f"[v0]trim=start_frame={a}:end_frame={b},setpts=PTS-STARTPTS[vt];"
             f"[v1]setpts=PTS-STARTPTS[vf];"
             f"[0:a]asplit[a0][a1];"
             f"[a0]atrim={t0:.4f}:{t1:.4f},asetpts=PTS-STARTPTS,"
             f"afade=t=in:d={f}, afade=t=out:st={tease - f:.4f}:d={f}[at];"
             f"[a1]asetpts=PTS-STARTPTS,afade=t=in:d={f}[af];"
             f"[vt][at][vf][af]concat=n=2:v=1:a=1[v][a]")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-filter_complex", graph,
                    "-map", "[v]", "-map", "[a]", "-t", f"{tease + full:.4f}",
                    "-c:v", "libx264", "-crf", str(crf), "-preset", "medium",
                    "-pix_fmt", "yuv420p", "-r", f"{fps:g}",
                    "-color_primaries", "bt709", "-color_trc", "bt709",
                    "-colorspace", "bt709", "-color_range", "tv", "-bsf:v", COLOUR_BSF,
                    "-c:a", "aac", "-b:a", "256k", "-ar", "48000",
                    "-movflags", "+faststart", str(out)], check=True)
    return tease


def shift_cards(cards: list[dict], *, start: float, end: float) -> list[dict]:
    """The caption cards as the cold-opened file shows them: the tease's own
    cards first, then every card later by the tease's length."""
    tease = end - start
    head = [dict(c, start=max(c["start"], start) - start, end=min(c["end"], end) - start)
            for c in cards if c["end"] > start and c["start"] < end]
    return head + [dict(c, start=c["start"] + tease, end=c["end"] + tease) for c in cards]
