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
        cam.json          the streamer's webcam over the whole VOD
        kills.json        his own kills from the kill feed, and the multi-kills
        clips_1080/NN_*.mp4, words/NN.json, titles.json, specs/NN.json

ANY CHANNEL IS ACCEPTED. A channel with a file in `channels/` gets its own
layout and handle, and that file must record a `permission` basis. Any other
channel runs on `channels/_default.json` with permission "operator": the
person submitting the link takes responsibility for having the right to clip it.
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
    """The channel file whose `twitch` login matches this VOD's uploader, or
    the house defaults for a channel with no file of its own.

    Raises PermissionError when a channel file records no rights basis."""
    login = (meta.get("uploader_id") or "").lower()
    for f in sorted((ROOT / "channels").glob("*.json")):
        ch = json.loads(f.read_text())
        if login and login in [x.lower() for x in ch.get("twitch", [])]:
            if ch.get("permission") not in RIGHTS_OK:
                raise PermissionError(f"channel {ch['name']} has no rights basis "
                                      f"(permission={ch.get('permission')!r})")
            return ch
    if not login:
        raise ValueError("this VOD has no uploader login")
    ch = json.loads((ROOT / "channels" / "_default.json").read_text())
    return ch | {"name": login, "twitch": [login], "handle": meta.get("uploader") or login,
                 "permission": "operator",
                 "permission_note": "No channel file: submitted through the web app on "
                                    "the operator's responsibility."}


def vod_cam(job: Path, ch: dict) -> dict:
    """`ch` with its `cam` replaced by the webcam measured on this VOD.

    `cam` is only what a clip falls back to when its own frames give no face
    (make_clip._cam), but a channel with no file of its own inherits FNS's
    corner from _default.json, which on any other streamer is a crop of the
    game. Measured once per VOD and cached, it is this streamer's webcam."""
    from engine import facecam

    out = job / "cam.json"
    if not out.exists():
        rect = facecam.vod_rect(job / "source.mp4")
        out.write_text(json.dumps({"cam": list(rect) if rect else None}))
    cam = json.loads(out.read_text())["cam"]
    return ch | {"cam": cam} if cam else ch


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


def chat(job: Path, *, log=print) -> list[dict]:
    """Chat-spike regions from the VOD's replay (engine/chat_spikes), cached."""
    from engine import chat_spikes
    meta = json.loads((job / "vod.json").read_text())
    vod = re.sub(r"\D", "", str(meta["id"]))
    return chat_spikes.regions(job, vod, float(meta.get("duration") or 0), log=log)


def _with_chat(regs: list[dict], spikes: list[dict]) -> list[dict]:
    """Voice regions with the chat spike they contain attached as a hint, then
    every spike no voice region covers as a region of its own."""
    out = [dict(r) for r in regs]
    for s in spikes:
        t = s["chat"]["t"]
        hit = next((r for r in out if r["start"] - 30 <= t <= r["end"] + 30), None)
        if hit is not None:
            if hit.get("chat", {}).get("score", 0) < s["chat"]["score"]:
                hit["chat"], hit["hint"] = s["chat"], s["hint"]
        else:
            out.append({"start": s["start"], "end": s["end"], "peak": 0.0, "mean": 0.0,
                        "chat": s["chat"], "hint": s["hint"]})
    return out


def save_kills(job: Path, kills: list[float]) -> list[dict]:
    """kills.json: the marked player's kills (engine/kills.scan) and the
    multi-kills among them from the streamer's own games. The scan runs
    wherever the caller runs it: the hosted path splits it over containers
    while the transcript is made."""
    from engine import kills as K
    kills = sorted(kills)
    streaks = K.multikills(job / "source.mp4", kills)
    (job / "kills.json").write_text(json.dumps({"kills": kills, "streaks": streaks}))
    return streaks


# A kill clip opens this long before the first kill reaches the feed, so the
# viewer sees the fight start, and holds this long past the last one.
KILL_LEAD = 2.0
KILL_TAIL = 2.5
# Where a multi-kill ranks against Tier 3's talk clips (0-1). A 4k or an ace is
# rarer and better than nearly anything said on stream, so it ranks above.
KILL_STRENGTH = {3: 0.80, 4: 0.92}
ACE_STRENGTH = 1.0


def _kill_clips(job: Path) -> list[dict]:
    """One clip per multi-kill in kills.json, shaped like a Tier 3 verdict."""
    p = job / "kills.json"
    if not p.exists():
        return []
    out = []
    for s in json.loads(p.read_text())["streaks"]:
        n = s["kills"]
        label = "ACE" if n >= 5 else f"{n}K"
        out.append({"has_clip": True, "genre": "frag", "kills": n,
                    "in_point": round(max(0.0, s["start"] - KILL_LEAD), 2),
                    "out_point": round(s["end"] + KILL_TAIL, 2),
                    "subject": f"{label}: {n} kills in {s['end'] - s['start']:.0f} seconds",
                    "claim": "", "setup": "", "consequence": "",
                    "strength": ACE_STRENGTH if n >= 5 else KILL_STRENGTH[n],
                    "why": "kill feed", "chat_score": 0.0})
    return out


# A chat-backed clip ranks as if this much stronger at full chat score, so a
# moment the room exploded over makes the cut against an equal monologue.
# 0.15 -> 0.30 on George's ask for chat to count for more: on job 3njkcnn5wd
# it takes the top 10 from 6 chat-backed clips to 9.
CHAT_BOOST = 0.30

# THE MODEL BUDGET. Every region is one Claude call, about 2.5 US cents each.
# The 9h24m s0mcs VOD had 209 voice regions, and judging all of them spent the
# whole $5 of API credit before ranking finished. It had found 165 clips by
# then, for a job that ships 10. So only the strongest MAX_REGIONS are judged:
# the regions chat spiked in first, strongest spike first, then the rest in
# the voice detector's own order (strongest first). At most ~$1 a VOD.
MAX_REGIONS = 40
RANK_WORKERS = 6   # parallel Claude calls; one at a time took 15 min on 40 regions


def _budget(regs: list[dict], n: int = MAX_REGIONS) -> list[dict]:
    chat = sorted((r for r in regs if r.get("chat")), key=lambda r: -r["chat"]["score"])
    return (chat + [r for r in regs if not r.get("chat")])[:n]


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
    regs = _with_chat(regions(job), chat(job, log=log))
    log(f"  judging {min(len(regs), MAX_REGIONS)} of {len(regs)} regions")
    regs = _budget(regs)
    utt = json.loads((job / "transcript.json").read_text())["utterances"]
    client = _client()
    out = job / "tier3.json"
    done = json.loads(out.read_text()) if out.exists() else []
    seen = {tuple(d["region"]) for d in done}

    def one(r: dict) -> list[dict]:
        try:
            return [v.as_dict() for v in judge(utt, (r["start"], r["end"]), client=client, pad=60,
                                               chat=r.get("hint", ""))]
        except Exception as e:  # one bad region must not lose the rest
            return [{"has_clip": False, "genre": "none", "why": f"error: {type(e).__name__}: {e}"}]

    todo = [(i, r) for i, r in enumerate(regs, 1) if (r["start"], r["end"]) not in seen]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(RANK_WORKERS) as ex:
        results = ex.map(lambda ir: one(ir[1]), todo)
        for (i, r), vs in zip(todo, results):
            for v in vs:
                done.append({"region": [r["start"], r["end"]], "audio_rank": i,
                             "audio_peak": r["peak"], "audio_mean": r["mean"],
                             "chat_score": r.get("chat", {}).get("score", 0.0), **v})
            out.write_text(json.dumps(done, indent=1))
            got = [v for v in vs if v.get("has_clip")]
            log(f"  {i:>3}/{len(regs)} {ts(r['start'])} -> "
                + (" | ".join(f"{ts(v['in_point'])} {v['out_point'] - v['in_point']:.0f}s"
                              for v in got) or "none"))
    clips, taken = [], []
    for d in sorted([d for d in done if d.get("has_clip")] + _kill_clips(job),
                    key=lambda d: -(d["strength"] + CHAT_BOOST * d.get("chat_score", 0.0))):
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

# AT MOST A THIRD OF A JOB IS KILL CLIPS. They rank above nearly every talk
# clip, so a stream with a dozen multi-kills would otherwise come back as all
# gameplay. Jatin's split: 3 of 10, best first; the commentary keeps the rest,
# and extra kill clips only fill slots the commentary cannot.
KILL_SHARE = 1 / 3


def _pick(clips: list[dict], n: int) -> list[dict]:
    """The top `n` of `clips` (strongest first) with kill clips capped."""
    kills = [c for c in clips if c.get("kills")]
    cap = round(n * KILL_SHARE)
    keep = kills[:cap] + [c for c in clips if not c.get("kills")] + kills[cap:]
    return sorted(keep[:n], key=lambda c: next(i for i, x in enumerate(clips) if x is c))


def cut_sections(job: Path, n_top: int, url: str) -> list[dict]:
    """ranked.json, and each clip's 1080p60 source in clips_1080/.

    From source.mp4 when the whole VOD is here (a re-encode, so the cut is
    frame-accurate and every packet is a frame, which make_clip counts on);
    otherwise a yt-dlp section download per clip.

    The cut is always 1920x1080: every crop in the engine is in those source
    pixels, so a lower rendition kept for local iteration (a 480p VOD is 1.7
    GB against 10.2 GB) is scaled up here rather than breaking the layout."""
    clips = _pick(json.loads((job / "clips.json").read_text()), n_top)
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
                            "-t", f"{b - a:.3f}", "-r", "60",
                            "-vf", "scale=1920:1080:flags=lanczos", "-c:v", "libx264", "-preset", "fast",
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


def popups(job: Path, ranked: list[dict], ch: dict, *, log=print) -> None:
    """popups/NN.json: the players and teams each clip names, with a picture
    of each (engine/popups). Read by make_clip, which places them."""
    from engine import popups as pp
    d = job / "popups"
    d.mkdir(exist_ok=True)
    client = None
    for n in range(1, len(ranked) + 1):
        p = d / f"{n:02d}.json"
        if p.exists():
            continue
        try:
            client = client or _client()
            words = json.loads((job / "words" / f"{n:02d}.json").read_text())
            found = pp.find(words, client=client, streamer=ch.get("handle", ch["name"]),
                            game=ch.get("game", "VALORANT"))
            keep = []
            for e in found:
                m = pp.image(e["page"], d / "img", wiki=ch.get("wiki", "valorant"))
                if m:
                    keep.append({**e, "image": f"img/{m['path']}", "source": m["source"]})
        except Exception as e:  # a pop-up is a garnish; never lose the clip over it
            log(f"  pop-ups for clip {n}: {type(e).__name__}: {e}")
            continue
        p.write_text(json.dumps(keep, indent=1))
        log(f"  clip {n}: " + (", ".join(e["name"] for e in keep) or "no names"))


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
STYLE = {"hook": None, "cards": [], "chat_mode": None, "stories": "off", "booms": [],
         "punch_boom": False, "intro_sfx": None, "caption_case": "spoken",
         "big_cam": "auto", "caption_style": "pop", "caption_fill": "cream",
         "caption_emph": "lime"}
CHANNEL_KEYS = ("name", "cam", "seam", "chrome", "fps", "grade", "arc",
                "permission", "permission_note")


def specs(job: Path, ranked: list[dict], ch: dict, vod_id: str, tl: dict,
          *, caption_font: str | None = None, caption_fill: str | None = None,
          caption_emph: str | None = None) -> list[Path]:
    """One make_clip spec per clip. The facecam is left to make_clip, which
    finds it per clip with the face detector. `caption_font` and the two
    caption colours are the job's picks from the web app (an
    engine.caption_fonts key and engine.caption_colour palette names); a
    colour left out keeps the house STYLE's."""
    from engine import caption_fonts
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
                "notes": f"Tier 3 {c['strength']:.2f}: {c['subject']}", **STYLE,
                "caption_font": caption_fonts.key(caption_font)}
        # A gameplay clip keeps the play clear: the chat panel sat over the
        # middle of the action on the first chat-hype frag clips.
        if c.get("genre") == "frag":
            clip["chat_mode"] = "off"
        clip["caption_fill"] = caption_fill or clip["caption_fill"]
        clip["caption_emph"] = caption_emph or clip["caption_emph"]
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
