"""The hosted clip service on Modal: a VOD link in, finished clips in R2.

    modal deploy modal_app.py

The web app (`webapp/`, a Cloudflare Worker) POSTs a job to `start`; this
app runs `pipeline/core.py` and reports back to the Worker's
`/api/pipeline/*` routes as it goes. Clips are uploaded straight to the R2
bucket with R2's S3 API, so no video passes through the Worker.

    start (web endpoint)  ->  run_job (CPU, orchestrates)
                                 |- transcribe (GPU, once per VOD)
                                 '- build_clip (CPU, one container per clip, in parallel)

Everything a job writes lives on the `clip-engine-data` Volume under
`jobs/<channel>-<vod>/`, so a VOD submitted again reuses its download,
transcript and ranking, and a failed clip can be rebuilt alone.

Secrets, all in one Modal Secret named `clip-engine`:
    ANTHROPIC_API_KEY      ranking and titles
    PIPELINE_TOKEN         shared with the Worker, both directions
    R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import modal
from fastapi import Header, HTTPException

REPO = "/root/clip-engine"
DATA = "/data"
FFMPEG = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"

image = (
    # CUDA + cuDNN 9 for faster-whisper on the GPU; the CPU functions share the
    # image so there is one thing to build.
    modal.Image.from_registry("nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04", add_python="3.12")
    # tesseract: engine/kills reads team tags in the kill feed to tell a
    # broadcast he is watching from his own game.
    .apt_install("curl", "xz-utils", "fonts-noto-color-emoji", "libsndfile1", "tesseract-ocr")
    # A current static ffmpeg: Ubuntu 22.04's is 4.4, older than anything the
    # engine was measured on.
    .run_commands(
        f"curl -sSL {FFMPEG} | tar xJ -C /opt",
        "ln -sf /opt/ffmpeg-*-amd64-static/ffmpeg /usr/local/bin/ffmpeg",
        "ln -sf /opt/ffmpeg-*-amd64-static/ffprobe /usr/local/bin/ffprobe")
    .pip_install("faster-whisper==1.2.1", "av==14.0.1", "numpy==2.5.4", "soundfile==0.14.0",
                 "pillow==11.3.0", "opencv-python-headless==4.13.0.92", "anthropic==2.9.0",
                 "boto3", "requests", "yt-dlp", "pyyaml==6.0.3", "jsonschema==4.23.0",
                 "rapidfuzz==3.14.6", "fastapi[standard]",
                 # engine/upscale's super-resolution pass on the facecam
                 "torch==2.8.0")
    .env({"CLIP_EMOJI_FONT": "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
          "CLIP_NATIVE_CHAT": "1",
          "HF_HOME": f"{DATA}/hf", "PYTHONPATH": REPO})
    .add_local_dir(Path(__file__).parent, REPO, copy=True, ignore=[
        ".git", "**/__pycache__", "jobs", "renders", "deliver", "webapp", "web",
        "vendor/remotion-clip08/node_modules", "**/*.mp4", "**/*.mov"])
)

app = modal.App("clip-engine", image=image)
data = modal.Volume.from_name("clip-engine-data", create_if_missing=True)
secret = modal.Secret.from_name("clip-engine")
VOL = {DATA: data}


def _setup() -> None:
    """Point the repo's jobs/ and renders/ at the Volume."""
    for d in ("jobs", "renders"):
        Path(DATA, d).mkdir(parents=True, exist_ok=True)
        link = Path(REPO, d)
        if not link.exists():
            link.symlink_to(Path(DATA, d))
    os.chdir(REPO)


def _post(callback_base: str, route: str, body: dict) -> None:
    """Tell the Worker. A failed callback is logged, never fatal: the work
    itself is on the Volume and in R2 either way."""
    import requests
    try:
        r = requests.post(f"{callback_base.rstrip('/')}/api/pipeline/{route}", json=body,
                          headers={"Authorization": f"Bearer {os.environ['PIPELINE_TOKEN']}"},
                          timeout=30)
        if r.status_code >= 300:
            print(f"callback {route} -> {r.status_code}: {r.text[:200]}", flush=True)
    except Exception as e:
        print(f"callback {route} failed: {e}", flush=True)


def _r2():
    import boto3
    return boto3.client(
        "s3", region_name="auto",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"])


# Any of these GPUs will do. Job kphkbkal2z sat in transcribe waiting on an
# L4 after a restart; the clip builds already take the same list.
@app.function(gpu=["L4", "A10G", "L40S"], volumes=VOL, secrets=[secret], timeout=3 * 3600)
def transcribe(job_name: str) -> None:
    _setup()
    data.reload()
    os.environ["CLIP_WHISPER_DEVICE"] = "cuda"
    from pipeline import core
    core.transcribe(Path(REPO, "jobs", job_name), model="large-v3")
    data.commit()


# A GPU for engine/upscale: 4x super-resolution of the facecam region runs
# at ~15 frames/s on an M-series Mac and far faster on an L4, where on 8 CPU
# cores it would add minutes to every clip.
# Any of these GPUs will do: on job 3njkcnn5wd only 2-3 L4s came up at once,
# so 10 clips rendered mostly one after another.
# A clip normally builds in a few minutes. The timeout is what a lost or
# runaway build costs before `run_job` gives up on it; see RENDER_BUDGET.
@app.function(gpu=["L4", "A10G", "L40S"], cpu=8, memory=16384, volumes=VOL, secrets=[secret], timeout=2400,
              retries=modal.Retries(max_retries=1))
def build_clip(n: int, job_name: str, job_id: str, callback_base: str) -> dict:
    _setup()
    data.reload()
    import json
    from pipeline import core
    job = Path(REPO, "jobs", job_name)
    spec = job / "specs" / f"{n:02d}.json"
    c = json.loads((job / "ranked.json").read_text())[n - 1]
    try:
        out, review = core.build_reviewed(job, n)
    except RuntimeError as e:
        # A build or QC failure is deterministic: a retry renders the same
        # file again and fails the same way. Retries are for lost containers.
        data.commit()
        return {"n": n, "error": str(e)}
    clip = json.loads(spec.read_text())["clip"]
    prev, thumb = core.preview_and_thumb(out)
    data.commit()
    base = f"jobs/{job_id}/{n:02d}-{core._slug(clip.get('title') or c['subject'], 50)}"
    keys = {"video_key": f"{base}.mp4", "preview_key": f"{base}-preview.mp4",
            "thumb_key": f"{base}.jpg"}
    s3 = _r2()
    for path, key, ct in ((out, keys["video_key"], "video/mp4"),
                          (prev, keys["preview_key"], "video/mp4"),
                          (thumb, keys["thumb_key"], "image/jpeg")):
        s3.upload_file(str(path), os.environ["R2_BUCKET"], key, ExtraArgs={"ContentType": ct})
    body = {"job_id": job_id, "n": n, "title": clip.get("title") or c["subject"],
            "emoji": clip.get("emoji"), "keyword": clip.get("title_keyword"),
            "subject": c["subject"], "score": c["strength"], "duration": core.duration(out),
            "vod_start": c["in_point"] + float(clip.get("in_point") or 0.0),
            "review": {k: review[k] for k in ("verdict", "summary", "revised")}, **keys}
    for path in (out, prev, thumb):
        Path(path).unlink(missing_ok=True)
    data.commit()
    _post(callback_base, "clip", body)
    return body


# KILL CLIPS COST NO WAITING. The kill feed is read at 2 fps from the VOD
# already on the Volume, in KILL_CHUNK pieces on their own containers, while
# the GPU transcribes; a 2h50m VOD scanned in about 2 minutes, well inside its
# transcription.
KILL_CHUNK = 900


@app.function(cpu=4, memory=4096, volumes=VOL, timeout=1800)
def kill_chunk(job_name: str, start: float) -> list[float]:
    _setup()
    from engine import kills
    return kills.scan(Path(REPO, "jobs", job_name, "source.mp4"), start=start, dur=KILL_CHUNK)


RENDER_BUDGET = 45 * 60


def _free_vod(job: Path) -> None:
    """Drop the VOD's video and audio when a job ends, however it ends.

    A 9h VOD is 34 GB of source.mp4 alone, so keeping it for a retry is not
    worth it: a retry re-downloads (minutes) and still reuses the transcript,
    regions and rankings, which stay."""
    import shutil
    data.reload()
    for p in [job / "source.mp4", job / "source.dl.mp4", job / "audio16k.wav",
              *job.glob("audio.*")]:
        p.unlink(missing_ok=True)
    shutil.rmtree(job / "clips_1080", ignore_errors=True)
    data.commit()


# NON-PREEMPTIBLE. Modal may restart a preemptible container at any time, and
# a restarted run_job starts the job again from the top (kphkbkal2z went back
# through download into transcribe). This container only orchestrates, so
# the higher non-preemptible rate is on 4 mostly idle CPUs.
@app.function(cpu=4, memory=8192, volumes=VOL, secrets=[secret], timeout=8 * 3600,
              nonpreemptible=True)
def run_job(job_id: str, vod_url: str, clips: int, callback_base: str,
            caption_font: str | None = None, caption_fill: str | None = None,
            caption_emph: str | None = None) -> None:
    _setup()
    from pipeline import core

    def progress(stage, message, p=None, **kw):
        print(f"[{stage}] {message}", flush=True)
        _post(callback_base, "progress", {"job_id": job_id, "status": "running",
                                          "stage": stage, "message": message,
                                          "progress": p, **kw})

    job = None
    try:
        progress("start", "Reading the VOD", 0.01)
        meta = core.vod_meta(vod_url)
        ch = core.channel_for(meta)
        job = core.job_dir(ch, meta)
        progress("download", f"Downloading {core.ts(meta['duration'] or 0)} of video", 0.03,
                 vod_title=meta.get("title"), channel=meta.get("uploader"))
        core.fetch(vod_url, job, video=True)
        ch = core.vod_cam(job, ch)
        regs = core.regions(job)
        data.commit()
        progress("transcribe", f"Transcribing ({len(regs)} moments to check)", 0.25)
        import threading
        chat = threading.Thread(target=core.chat, args=(job,), daemon=True)
        chat.start()
        scans = [] if (job / "kills.json").exists() else [
            kill_chunk.spawn(job.name, float(s))
            for s in range(0, int(meta.get("duration") or 0), KILL_CHUNK)]
        transcribe.remote(job.name)
        chat.join()
        if scans:
            # A failed scan costs the kill clips, never the job.
            try:
                kt = [k for fc in scans for k in fc.get(timeout=1800)]
                print(f"kills: {len(kt)}, multi-kills: {core.save_kills(job, kt)}", flush=True)
            except Exception as e:                        # noqa: BLE001
                print(f"kill scan failed: {type(e).__name__}: {e}", flush=True)
        data.commit()
        data.reload()
        progress("rank", "Finding and ranking clips", 0.45)
        found = core.rank(job)
        if not found:
            raise RuntimeError("no clips found in this VOD")
        ranked = core.cut_sections(job, min(clips, len(found)), vod_url)
        core.clip_words(job, ranked)
        core.popups(job, ranked, ch)
        progress("title", f"Writing titles for {len(ranked)} clips", 0.6)
        tl = core.titles(job, ranked, handle=ch.get("handle", ch["name"].upper()))
        vod = re.sub(r"\D", "", str(meta["id"]))
        core.specs(job, ranked, ch, vod, tl, caption_font=caption_font,
                   caption_fill=caption_fill, caption_emph=caption_emph)
        data.commit()
        progress("render", f"Rendering {len(ranked)} clips", 0.65)
        # ONE CLIP MUST NOT HOLD THE JOB. Job jnvouw6f23 sat at "3 of 10" with
        # 8 clips already uploaded: `map` yields in clip order, so it blocked
        # on clip 5, which was stuck in its build, and every clip behind it
        # went uncounted. Each clip is its own call, collected as it finishes,
        # and whatever is still running at RENDER_BUDGET is cancelled so the
        # job finishes with what it has.
        import time
        calls = {n: build_clip.spawn(n, job.name, job_id, callback_base)
                 for n in range(1, len(ranked) + 1)}
        deadline = time.time() + RENDER_BUDGET
        ok, failed = 0, []
        while calls and time.time() < deadline:
            for n, fc in list(calls.items()):
                try:
                    res = fc.get(timeout=0)
                except (TimeoutError, modal.exception.TimeoutError):
                    continue
                except Exception as e:                    # noqa: BLE001
                    res = e
                del calls[n]
                if isinstance(res, Exception) or "error" in res:
                    failed.append(f"clip {n}: {str(res.get('error') if isinstance(res, dict) else res)[-200:]}")
                else:
                    ok += 1
                done = len(ranked) - len(calls)
                progress("render", f"{ok} of {len(ranked)} clips ready", 0.65 + 0.35 * done / len(ranked))
            time.sleep(2)
        for n, fc in calls.items():
            fc.cancel(terminate_containers=True)
            failed.append(f"clip {n}: still building after {RENDER_BUDGET // 60} min, cancelled")
        if not ok:
            raise RuntimeError("every clip failed to build: " + "; ".join(failed)[:800])
        _post(callback_base, "done", {"job_id": job_id, "status": "done",
                                      "error": ("; ".join(failed)[:800] or None)})
    except Exception as e:
        print(f"job {job_id} failed: {type(e).__name__}: {e}", flush=True)
        _post(callback_base, "done", {"job_id": job_id, "status": "failed",
                                      "error": f"{type(e).__name__}: {e}"[:800]})
        raise
    finally:
        if job is not None:
            _free_vod(job)


@app.function(secrets=[secret])
@modal.fastapi_endpoint(method="POST")
def start(body: dict, authorization: str | None = Header(default=None)):
    """POST {job_id, vod_url, clips, callback_base, caption_font?, caption_fill?,
    caption_emph?} with Bearer PIPELINE_TOKEN."""
    import hmac
    token = os.environ["PIPELINE_TOKEN"]
    given = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(given, token):
        raise HTTPException(status_code=401, detail="bad token")
    url = str(body.get("vod_url", ""))
    if not re.match(r"^https?://(www\.|m\.)?twitch\.tv/videos/\d+", url):
        raise HTTPException(status_code=400, detail="not a Twitch VOD link")
    from engine.caption_colour import PALETTE
    from engine.caption_fonts import key
    fill, emph = (body.get(k) if body.get(k) in PALETTE else None
                  for k in ("caption_fill", "caption_emph"))
    call = run_job.spawn(str(body["job_id"]), url, int(body.get("clips") or 10),
                         str(body["callback_base"]), key(body.get("caption_font")), fill, emph)
    return {"ok": True, "call_id": call.object_id}
