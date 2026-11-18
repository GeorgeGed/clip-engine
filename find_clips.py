#!/usr/bin/env python3
"""One VOD in, a ranked list of clips out — and, with --build, the clips.

    python3 find_clips.py https://www.twitch.tv/videos/<id>
    python3 find_clips.py https://www.twitch.tv/videos/<id> --build 10

The local driver for `pipeline/core.py`; `modal_app.py` is the hosted one.
Locally only the audio-only rendition is downloaded and each built clip
fetches its own 1080p section, because a home connection makes the whole
video the slow part. Every stage resumes from what is already on disk.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.resolve()))
from pipeline import core  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--model", default="small", help="whisper size for the whole-VOD pass")
    ap.add_argument("--build", type=int, default=0, help="render the top N clips")
    ap.add_argument("--full-video", action="store_true",
                    help="download the whole 1080p VOD instead of per-clip sections")
    a = ap.parse_args()

    meta = core.vod_meta(a.url)
    ch = core.channel_for(meta)
    job = core.job_dir(ch, meta)
    print(f"{meta['uploader']}: {meta['title']} ({core.ts(meta['duration'])}) -> {job}", flush=True)
    core.fetch(a.url, job, video=a.full_video)
    print(f"{len(core.regions(job))} regions", flush=True)
    core.transcribe(job, model=a.model)
    clips = core.rank(job, log=lambda s: print(s, flush=True))
    print(f"\n{len(clips)} clips")
    for n, c in enumerate(clips, 1):
        print(f"{n:>3}. {c['strength']:.2f} {core.ts(c['in_point'])} "
              f"{c['out_point'] - c['in_point']:4.0f}s {c['genre']:9} {c.get('subject', '')[:70]}")
    if not a.build:
        return
    ranked = core.cut_sections(job, a.build, a.url)
    core.clip_words(job, ranked)
    core.popups(job, ranked, ch, log=lambda s: print(s, flush=True))
    tl = core.titles(job, ranked, handle=ch.get("handle", ch["name"].upper()))
    vod = re.sub(r"\D", "", str(meta["id"]))
    for spec in core.specs(job, ranked, ch, vod, tl):
        try:
            out = core.build(spec, log_path=job / "specs" / f"{spec.stem}.log")
            core.preview_and_thumb(out)
            print(f"  built {out.name}", flush=True)
        except RuntimeError as e:
            print(f"  FAILED {spec.name}: {e}", flush=True)


if __name__ == "__main__":
    main()
