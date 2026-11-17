"""VOD link in, finished clips out — the steps, with no idea where they run.

`find_clips.py` (local) and `modal_app.py` (the hosted service) both drive
these functions. Each step writes its result into the job directory and is
skipped when that result already exists, so a run that dies resumes, and a
VOD submitted twice reuses everything already done for it.

    jobs/<channel>-<vod_id>/
        vod.json          yt-dlp's metadata
        source.mp4        the whole VOD (only when the full video is fetched)
        audio16k.wav      16 kHz mono, what detection and transcription read
        regions.json      detect_audio's elevated stretches
        transcript.json   word-level, VOD seconds
        tier3.json        one verdict per region
        clips.json        kept clips, strongest first
        ranked.json       the top N that get built (make_clip reads it)
        clips_1080/NN_*.mp4, words/NN.json, titles.json, specs/NN.json

THE RIGHTS GATE COMES FIRST. A VOD is only processed when its channel has a
file in `channels/` naming its Twitch login and a `permission` basis. That is
the engine's oldest rule — never ship a source without a rights basis — and a
service that takes any link would otherwise clip whoever was pasted in.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RIGHTS_OK = {"explicit", "own", "license", "partner"}


def ts(t: float) -> str:
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{int(t % 60):02d}"


def vod_meta(url: str) -> dict:
    meta = json.loads(subprocess.run(["yt-dlp", "-J", "--no-warnings", url], check=True,
                                     capture_output=True, text=True).stdout)
    return {k: meta.get(k) for k in ("id", "uploader", "uploader_id", "title",
                                     "duration", "upload_date", "webpage_url")}


def channel_for(meta: dict) -> dict:
    """The channel file whose `twitch` login matches this VOD's uploader.

    Raises PermissionError when there is none, or it records no rights basis."""
    login = (meta.get("uploader_id") or "").lower()
    for f in sorted((ROOT / "channels").glob("*.json")):
        ch = json.loads(f.read_text())
        if login and login in [x.lower() for x in ch.get("twitch", [])]:
            if ch.get("permission") not in RIGHTS_OK:
                raise PermissionError(f"channel {ch['name']} has no rights basis "
                                      f"(permission={ch.get('permission')!r})")
            return ch
    raise PermissionError(f"twitch channel {login!r} is not on the allowlist: add a "
                          f"channels/<name>.json with \"twitch\": [\"{login}\"] and its "
                          f"permission basis")


def job_dir(ch: dict, meta: dict) -> Path:
    vod = re.sub(r"\D", "", str(meta["id"]))
    d = ROOT / "jobs" / f"{ch['name']}-{vod}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "vod.json").write_text(json.dumps(meta, indent=1))
    return d


def _retry(cmd: list[str], tries: int = 5) -> None:
    for i in range(tries):
        if subprocess.run(cmd).returncode == 0:
            return
        time.sleep(5 * (i + 1))
    raise RuntimeError(f"failed after {tries} tries: {' '.join(cmd[:3])} ...")


def fetch(url: str, job: Path, *, video: bool) -> None:
    """The VOD. `video=True` takes the whole 1080p60 file once and cuts every
    clip from it (the hosted path, where bandwidth is cheap); otherwise only the
    audio-only rendition, and clips fetch their own sections later."""
    wav = job / "audio16k.wav"
    if video:
        src = job / "source.mp4"
        if not src.exists():
            part = job / "source.dl.mp4"
            _retry(["yt-dlp", "-q", "--no-warnings", "-N", "16", "-f", "1080p60/best",
                    "--no-part", "-o", str(part), url])
            part.rename(src)
        audio_from = src
    else:
        audio_from = next((p for p in job.glob("audio.*") if p.suffix != ".wav"), None)
        if audio_from is None and not wav.exists():
            _retry(["yt-dlp", "-q", "--no-warnings", "-f", "Audio_Only/bestaudio",
                    "-o", str(job / "audio.%(ext)s"), url])
            audio_from = next(p for p in job.glob("audio.*") if p.suffix != ".wav")
    if not wav.exists():
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(audio_from), "-vn",
                        "-ac", "1", "-ar", "16000", str(wav)], check=True)


def regions(job: Path) -> list[dict]:
    p = job / "regions.json"
    if not p.exists():
        from engine import detect_audio
        an = detect_audio.analyse(job / "audio16k.wav")
        p.write_text(json.dumps(detect_audio.regions(an["events"]), indent=1))
    return json.loads(p.read_text())


def transcribe(job: Path, *, model: str) -> None:
    p = job / "transcript.json"
    if p.exists():
        return
    from engine.transcribe import transcribe as tr
    p.write_text(json.dumps(tr(job / "audio16k.wav", model_size=model, language="en")))


def _client():
    import anthropic
    from engine.tier3 import _api_key
    # gzip only: some httpx builds ship a brotli/zstd decoder that throws on
    # every response, which the SDK reports as a connection error.
    return anthropic.Anthropic(api_key=_api_key(), max_retries=8,
                               default_headers={"Accept-Encoding": "gzip"})


def rank(job: Path, *, log=print) -> list[dict]:
    """Tier 3 over every region, then the kept clips strongest first, with
    overlapping verdicts deduplicated."""
    from engine.tier3 import judge
    regs = regions(job)
    utt = json.loads((job / "transcript.json").read_text())["utterances"]
    client = _client()
    out = job / "tier3.json"
    done = json.loads(out.read_text()) if out.exists() else []
    seen = {tuple(d["region"]) for d in done}
    for i, r in enumerate(regs, 1):
        if (r["start"], r["end"]) in seen:
            continue
        try:
            vs = [v.as_dict() for v in judge(utt, (r["start"], r["end"]), client=client, pad=60)]
        except Exception as e:  # one bad region must not lose the rest
            vs = [{"has_clip": False, "genre": "none", "why": f"error: {type(e).__name__}: {e}"}]
        for v in vs:
            done.append({"region": [r["start"], r["end"]], "audio_rank": i,
                         "audio_peak": r["peak"], "audio_mean": r["mean"], **v})
        out.write_text(json.dumps(done, indent=1))
        got = [v for v in vs if v.get("has_clip")]
        log(f"  {i:>3}/{len(regs)} {ts(r['start'])} -> "
            + (" | ".join(f"{ts(v['in_point'])} {v['out_point'] - v['in_point']:.0f}s"
                          for v in got) or "none"))
    clips, taken = [], []
    for d in sorted((d for d in done if d.get("has_clip")), key=lambda d: -d["strength"]):
        span = (d["in_point"], d["out_point"])
        if any(min(span[1], b) - max(span[0], s) > 3.0 for s, b in taken):
            continue
        taken.append(span)
        clips.append(d)
    (job / "clips.json").write_text(json.dumps(clips, indent=1))
    return clips


def _slug(s: str, n: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower())[:n].strip("-")


TAIL = 1.0   # seconds of source kept past the ranked out-point, for the snap


def cut_sections(job: Path, n_top: int, url: str) -> list[dict]:
    """ranked.json, and each clip's 1080p60 source in clips_1080/.

    From source.mp4 when the whole VOD is here (a re-encode, so the cut is
    frame-accurate and every packet is a frame, which make_clip counts on);
    otherwise a yt-dlp section download per clip."""
    clips = json.loads((job / "clips.json").read_text())[:n_top]
    (job / "ranked.json").write_text(json.dumps(clips, indent=1))
    out = job / "clips_1080"
    out.mkdir(exist_ok=True)
    src = job / "source.mp4"
    for n, c in enumerate(clips, 1):
        if list(out.glob(f"{n:02d}_*.mp4")):
            continue
        t = int(c["in_point"])
        dst = out / f"{n:02d}_{t // 3600}h{t % 3600 // 60:02d}m{t % 60:02d}s_{_slug(c['subject'], 30)}.mp4"
        tmp = dst.with_suffix(".tmp.mp4")
        a, b = c["in_point"], c["out_point"] + TAIL
        if src.exists():
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{a:.3f}", "-i", str(src),
                            "-t", f"{b - a:.3f}", "-r", "60", "-c:v", "libx264", "-preset", "fast",
                            "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                            str(tmp)], check=True)
        else:
            _retry(["yt-dlp", "-q", "--no-warnings", "-f", "1080p60/best",
                    "--download-sections", f"*{a:.2f}-{b:.2f}",
                    "--downloader-args", "ffmpeg_i:-rw_timeout 20000000",
                    "--force-keyframes-at-cuts", "--no-part", "-o", str(tmp), url])
        tmp.rename(dst)
    return clips


def clip_words(job: Path, ranked: list[dict]) -> None:
    """words/NN.json in CLIP-FILE seconds, sliced from the whole-VOD transcript.

    One transcription serves both ranking and captions, so the expensive pass
    runs once. Utterances are clipped to the section and rebased to 0."""
    wd = job / "words"
    wd.mkdir(exist_ok=True)
    utt = json.loads((job / "transcript.json").read_text())["utterances"]
    for n, c in enumerate(ranked, 1):
        p = wd / f"{n:02d}.json"
        if p.exists():
            continue
        a, b = c["in_point"], c["out_point"] + TAIL
        us = []
        for u in utt:
            ws = [dict(w, start=round(w["start"] - a, 3), end=round(w["end"] - a, 3))
                  for w in u["words"] if w["start"] >= a and w["end"] <= b]
            if ws:
                us.append({"start": ws[0]["start"], "end": ws[-1]["end"],
                           "text": " ".join(w["text"] for w in ws), "words": ws})
        p.write_text(json.dumps({"language": "en", "offset": a, "utterances": us}, indent=1))


def titles(job: Path, ranked: list[dict], handle: str) -> dict:
    p = job / "titles.json"
    have = json.loads(p.read_text()) if p.exists() else {}
    todo = [{"n": n, "words": json.loads((job / "words" / f"{n:02d}.json").read_text()),
             "subject": c["subject"], "claim": c.get("claim", "")}
            for n, c in enumerate(ranked, 1) if "options" not in have.get(str(n), {})]
    if todo:
        from engine.titler import suggest_many
        have.update(suggest_many(todo, handle=handle))
        p.write_text(json.dumps(have, indent=1, ensure_ascii=False))
    return have


# The house look: what clip 08 settled on after review.
STYLE = {"hook": None, "cards": [], "chat_mode": "off", "stories": "off", "booms": [],
         "punch_boom": False, "intro_sfx": None, "caption_case": "spoken",
         "big_cam": "auto", "caption_style": "pop", "caption_fill": "cream",
         "caption_emph": "lime"}
CHANNEL_KEYS = ("name", "cam", "seam", "chrome", "fps", "grade", "arc",
                "permission", "permission_note")


def specs(job: Path, ranked: list[dict], ch: dict, vod_id: str, tl: dict) -> list[Path]:
    """One make_clip spec per clip. The facecam is left to make_clip, which
    finds it per clip with the face detector."""
    sd = job / "specs"
    sd.mkdir(exist_ok=True)
    channel = {k: ch.get(k) for k in CHANNEL_KEYS} | {"vod_id": vod_id}
    out = []
    for n, c in enumerate(ranked, 1):
        t = tl.get(str(n), {})
        opts = t.get("options") or []
        best = opts[t.get("best", 0)] if opts else {}
        clip = {"job": job.name, "index": n, "channel": ch["name"],
                "in_point": 0.0, "out_point": round(c["out_point"] - c["in_point"], 2),
                "region": [c["in_point"], c["out_point"] + TAIL], "cam": None,
                "emoji": best.get("emoji") or "\U0001F633",
                "title": best.get("title") or None, "title_keyword": best.get("keyword") or None,
                "notes": f"Tier 3 {c['strength']:.2f}: {c['subject']}", **STYLE}
        p = sd / f"{n:02d}.json"
        p.write_text(json.dumps({"channel": channel, "clip": clip}, indent=1, ensure_ascii=False) + "\n")
        out.append(p)
    return out


def build(spec: Path, *, log_path: Path) -> Path:
    """make_clip, all stages, native renderer. Returns the QC-passed delivery.

    Raises when the build fails or QC does not PASS, so a broken clip never
    reaches the bucket."""
    from engine.clipspec import load
    clip, _ch = load(spec)
    with open(log_path, "w") as lf:
        r = subprocess.run(["python3", str(ROOT / "make_clip.py"), str(spec)], cwd=ROOT,
                           stdout=lf, stderr=subprocess.STDOUT)
    text = log_path.read_text()
    out = ROOT / "renders" / f"{clip.slug}.mp4"
    if r.returncode != 0 or not out.exists() or not re.search(r"^PASS\s", text, re.M):
        raise RuntimeError(f"build failed for {spec.name}: " + text[-600:])
    return out


def preview_and_thumb(mp4: Path) -> tuple[Path, Path]:
    prev = mp4.with_name(mp4.stem + "-preview.mp4")
    thumb = mp4.with_name(mp4.stem + ".jpg")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mp4), "-vf", "scale=540:960",
                    "-r", "30", "-c:v", "libx264", "-crf", "28", "-preset", "veryfast",
                    "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(prev)], check=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "1.5", "-i", str(mp4), "-frames:v", "1",
                    "-vf", "scale=540:960", "-q:v", "4", str(thumb)], check=True)
    raw = mp4.with_name(mp4.stem + "_nat_raw.mov")
    raw.unlink(missing_ok=True)
    return prev, thumb


def duration(mp4: Path) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "csv=p=0", str(mp4)], capture_output=True,
                                text=True).stdout.strip() or 0)
