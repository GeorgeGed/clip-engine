"""What the site needs that the pipeline does not already write to disk.

Thumbnails, the per-clip transcript in CUT time, and the candidate list with
its scores joined to its verdicts. All of it is DERIVED and all of it is
cached on disk under `jobs/<job>/ui/`, because ffmpeg frame extraction and
`_plan_only` are both too slow to run inside a request and neither answer
changes unless the thing it came from changes.

Nothing here decides anything. The scores come from `ranked.json`, the
verdicts from `screened.json`, the words from the transcript the pipeline
already made. If a number on the page disagrees with the pipeline, this
file is wrong, not the pipeline.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JOBS = ROOT / "jobs"


def ui_dir(job: str) -> Path:
    p = JOBS / job / "ui"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _fresh(out: Path, *sources: Path) -> bool:
    """Is `out` newer than everything it was made from?"""
    if not out.exists():
        return False
    t = out.stat().st_mtime
    return all(not s.exists() or s.stat().st_mtime <= t for s in sources)


# ------------------------------------------------------------ candidates --
def candidates(job: str) -> list[dict]:
    """Every scored window, with the screen's verdict beside it."""
    d = JOBS / job
    rp, sp = d / "ranked.json", d / "screened.json"
    if not rp.exists():
        return []
    ranked = json.loads(rp.read_text())
    screened = {}
    if sp.exists():
        rows = json.loads(sp.read_text())
        screened = {r["n"]: r for r in (rows if isinstance(rows, list) else [])}

    def why(r):
        w = r.get("why") or r.get("reason") or ""
        return "; ".join(map(str, w)) if isinstance(w, (list, tuple)) else str(w)

    out = []
    for i, r in enumerate(ranked, 1):
        s = screened.get(i, {})
        num = lambda k, dflt=0.0: (float(r[k]) if str(r.get(k, "")) not in ("", "None")
                                   else dflt)                         # noqa: E731
        out.append({
            "n": i,
            "subject": r.get("subject", ""),
            "genre": r.get("genre", ""),
            "claim": r.get("claim", ""),
            "score": round(num("virality") * 100),
            "strength": round(num("strength") * 100),
            "secs": round(num("seconds"), 1),
            "at": round(num("in_point")),
            "verdict": s.get("verdict", ""),
            "block": why(s),
            "muted": s.get("muted"),
            "cuts": s.get("cuts_min"),
            # Set when the screen had to cut INTO the region to make it
            # buildable — see the note in screen_clips.best_window.
            "window": s.get("window"),
        })
    return out


# ------------------------------------------------------------- pictures ---
def _grab(src: Path, at: float, width: int, out: Path) -> Path | None:
    if _fresh(out, src):
        return out
    if not src.exists():
        return None
    out.parent.mkdir(parents=True, exist_ok=True)
    # WRITE SOMEWHERE ELSE AND RENAME. The grid asks for a screenful of these
    # at once and the warm thread is making the same ones, so two ffmpegs can
    # be writing one path while a third request reads it — a half-written
    # JPEG, which renders as a broken thumbnail and looks like nothing.
    # `os.replace` is atomic, so a reader sees the old file or the new one.
    tmp = out.with_name(f".{out.name}.{os.getpid()}.{threading.get_ident()}")
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", f"{max(at, 0):.2f}", "-i", str(src),
         "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "6",
         "-f", "mjpeg", str(tmp)],
        capture_output=True)
    if r.returncode != 0 or not tmp.exists():
        tmp.unlink(missing_ok=True)
        return None
    os.replace(tmp, out)
    return out


def _duration(p: Path) -> float:
    try:
        return float(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(p)], capture_output=True, text=True).stdout)
    except ValueError:
        return 0.0


def candidate_thumb(job: str, n: int) -> Path | None:
    """A frame of the raw candidate region — 16:9, because nothing has
    reframed it yet. The tile showing that is the point."""
    hits = sorted((JOBS / job / "clips_1080").glob(f"{n:02d}_*.mp4"))
    if not hits:
        return None
    src = hits[0]
    return _grab(src, _duration(src) * 0.28, 224, ui_dir(job) / f"cand{n:02d}.jpg")


def render_path(job: str, n: int) -> Path:
    return ROOT / "renders" / f"{job}-{n:02d}.mp4"


def clip_frame(job: str, n: int, at: float, width: int = 250) -> Path | None:
    src = render_path(job, n)
    key = f"clip{n:02d}_{int(at * 10)}_{width}.jpg"
    return _grab(src, at, width, ui_dir(job) / key)


# ------------------------------------------------------------- one clip ---
def clip_detail(job: str, n: int) -> dict:
    """Everything the editor needs: words in CUT time, the boom plan, the
    filmstrip times, and what the nucleus gate refused.

    Cached against the spec and the render, because `_plan_only` re-derives
    the whole cut and that is not a per-request amount of work.
    """
    chan = job.split("-")[0]
    spec = ROOT / "clips" / f"{chan}-{n:02d}.json"
    mp4 = render_path(job, n)
    out = ui_dir(job) / f"detail{n:02d}.json"
    if _fresh(out, spec, mp4):
        return json.loads(out.read_text())
    if not spec.exists():
        return {}

    sys.path.insert(0, str(ROOT))
    import make_clip as mc                                   # noqa: PLC0415
    import resolve_punch as rp                               # noqa: PLC0415
    from engine.clipspec import load                         # noqa: PLC0415

    clip, ch = load(spec)
    ranked = json.loads((JOBS / job / "ranked.json").read_text())
    st = {"overlays": JOBS / job / f"overlays_{n:02d}",
          "base_wav": JOBS / job / f"overlays_{n:02d}" / "_cut.wav",
          "meta": ranked[n - 1]}
    try:
        mc._plan_only(clip, ch, st)
        words = [{"t": round(t, 2), "w": w} for t, w in mc._cut_words(clip, st)]
        gated: list = []
        budget = rp.boom_budget(st["out_dur"])
        _b, booms = rp.bold_moments(
            mc._cut_audio(clip, ch, st),
            anchors=mc._emphasis_anchors(clip, ch, st), limit=budget,
            words=mc._cut_words(clip, st),
            on_gate=lambda t, db, w: gated.append(
                {"t": t, "word": w[2], "by": w[0]}))
    except Exception as exc:                                 # noqa: BLE001
        return {"n": n, "error": f"{type(exc).__name__}: {exc}"}

    dur = _duration(mp4) if mp4.exists() else st["out_dur"]
    d = {
        "n": n, "dur": round(dur, 2),
        "built": mp4.exists(),
        "mb": round(mp4.stat().st_size / 1e6, 1) if mp4.exists() else None,
        "hook": clip.hook, "subject": ranked[n - 1].get("subject", ""),
        "claim": ranked[n - 1].get("claim", ""),
        "in": clip.in_point, "out": clip.out_point,
        "chat": clip.chat_mode, "specBooms": clip.booms,
        "splices": len(st["keeps"]), "budget": budget,
        "words": words,
        "booms": [{"t": t, "db": db} for t, db in booms],
        "gated": gated,
        "strip": [round(dur * (k + 0.5) / 8, 2) for k in range(8)],
    }
    out.write_text(json.dumps(d))
    return d


_WARMED: set[str] = set()


def warm(job: str, ns: list[int]) -> None:
    """Generate the candidate thumbnails once, off the request thread.

    The first open of a finished project asked for fifty frames at once and
    each one is an ffmpeg call, so the grid sat blank while they queued.
    They are cached after the first pass, so this only ever runs once per
    job — and it is a daemon thread, so it never holds the server open.
    """
    if job in _WARMED:
        return
    _WARMED.add(job)

    def go():
        for n in ns:
            try:
                candidate_thumb(job, n)
            except Exception:                            # noqa: BLE001, S110
                pass

    threading.Thread(target=go, daemon=True,
                     name=f"warm-{job}").start()


def invalidate(job: str, n: int) -> None:
    """Drop a clip's cached detail — call it after a spec is written."""
    p = ui_dir(job) / f"detail{n:02d}.json"
    if p.exists():
        p.unlink()
