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
    .apt_install("curl", "xz-utils", "fonts-noto-color-emoji", "libsndfile1")
    # A current static ffmpeg: Ubuntu 22.04's is 4.4, older than anything the
    # engine was measured on.
    .run_commands(
        f"curl -sSL {FFMPEG} | tar xJ -C /opt",
        "ln -sf /opt/ffmpeg-*-amd64-static/ffmpeg /usr/local/bin/ffmpeg",
        "ln -sf /opt/ffmpeg-*-amd64-static/ffprobe /usr/local/bin/ffprobe")
    .pip_install("faster-whisper==1.2.1", "numpy", "soundfile", "pillow",
                 "opencv-python-headless", "anthropic", "boto3", "requests", "yt-dlp",
                 "pyyaml", "jsonschema", "rapidfuzz", "fastapi[standard]")
    .env({"CLIP_EMOJI_FONT": "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
          "HF_HOME": f"{DATA}/hf", "PYTHONPATH": REPO})
    .add_local_dir(Path(__file__).parent, REPO, copy=True, ignore=[
        ".git", "**/__pycache__", "jobs", "renders", "deliver", "webapp", "web",
        "vendor/remotion-clip08/node_modules", "**/*.mp4", "**/*.mov", "**/*.wav"])
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


@app.function(gpu="L4", volumes=VOL, secrets=[secret], timeout=3 * 3600)
def transcribe(job_name: str) -> None:
    _setup()
    data.reload()
    os.environ["CLIP_WHISPER_DEVICE"] = "cuda"
    from pipeline import core
    core.transcribe(Path(REPO, "jobs", job_name), model="large-v3")
    data.commit()


@app.function(cpu=8, memory=16384, volumes=VOL, secrets=[secret], timeout=3600,
              retries=modal.Retries(max_retries=1))
def build_clip(job_name: str, n: int, job_id: str, callback_base: str) -> dict:
    _setup()
    data.reload()
    import json
    from pipeline import core
    job = Path(REPO, "jobs", job_name)
    spec = job / "specs" / f"{n:02d}.json"
    clip = json.loads(spec.read_text())["clip"]
    c = json.loads((job / "ranked.json").read_text())[n - 1]
    out = core.build(spec, log_path=job / "specs" / f"{n:02d}.log")
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
            "vod_start": c["in_point"], **keys}
    _post(callback_base, "clip", body)
    return body


@app.function(cpu=4, memory=8192, volumes=VOL, secrets=[secret], timeout=8 * 3600)
def run_job(job_id: str, vod_url: str, clips: int, callback_base: str) -> None:
    _setup()
    from pipeline import core

    def progress(stage, message, p=None, **kw):
        print(f"[{stage}] {message}", flush=True)
        _post(callback_base, "progress", {"job_id": job_id, "status": "running",
                                          "stage": stage, "message": message,
                                          "progress": p, **kw})

    try:
        progress("start", "Reading the VOD", 0.01)
        meta = core.vod_meta(vod_url)
        ch = core.channel_for(meta)
        job = core.job_dir(ch, meta)
        progress("download", f"Downloading {core.ts(meta['duration'] or 0)} of video", 0.03,
                 vod_title=meta.get("title"), channel=meta.get("uploader"))
        core.fetch(vod_url, job, video=True)
        regs = core.regions(job)
        data.commit()
        progress("transcribe", f"Transcribing ({len(regs)} moments to check)", 0.25)
        transcribe.remote(job.name)
        data.reload()
        progress("rank", "Finding and ranking clips", 0.45)
        found = core.rank(job)
        if not found:
            raise RuntimeError("no clips found in this VOD")
        ranked = core.cut_sections(job, min(clips, len(found)), vod_url)
        core.clip_words(job, ranked)
        progress("title", f"Writing titles for {len(ranked)} clips", 0.6)
        tl = core.titles(job, ranked, handle=ch.get("handle", ch["name"].upper()))
        vod = re.sub(r"\D", "", str(meta["id"]))
        core.specs(job, ranked, ch, vod, tl)
        data.commit()
        progress("render", f"Rendering {len(ranked)} clips", 0.65)
        ok, failed = 0, []
        for n, res in enumerate(build_clip.map(range(1, len(ranked) + 1),
                                               kwargs={"job_name": job.name, "job_id": job_id,
                                                       "callback_base": callback_base},
                                               return_exceptions=True), 1):
            if isinstance(res, Exception):
                failed.append(f"clip {n}: {str(res)[-200:]}")
            else:
                ok += 1
            progress("render", f"{ok} of {len(ranked)} clips ready", 0.65 + 0.35 * n / len(ranked))
        if not ok:
            raise RuntimeError("every clip failed to build: " + "; ".join(failed)[:800])
        _post(callback_base, "done", {"job_id": job_id, "status": "done",
                                      "error": ("; ".join(failed)[:800] or None)})
    except Exception as e:
        print(f"job {job_id} failed: {type(e).__name__}: {e}", flush=True)
        _post(callback_base, "done", {"job_id": job_id, "status": "failed",
                                      "error": f"{type(e).__name__}: {e}"[:800]})
        raise


@app.function(secrets=[secret])
@modal.fastapi_endpoint(method="POST")
def start(body: dict, authorization: str | None = Header(default=None)):
    """POST {job_id, vod_url, clips, callback_base} with Bearer PIPELINE_TOKEN."""
    import hmac
    token = os.environ["PIPELINE_TOKEN"]
    given = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(given, token):
        raise HTTPException(status_code=401, detail="bad token")
    url = str(body.get("vod_url", ""))
    if not re.match(r"^https?://(www\.|m\.)?twitch\.tv/videos/\d+", url):
        raise HTTPException(status_code=400, detail="not a Twitch VOD link")
    call = run_job.spawn(str(body["job_id"]), url, int(body.get("clips") or 10),
                         str(body["callback_base"]))
    return {"ok": True, "call_id": call.object_id}
