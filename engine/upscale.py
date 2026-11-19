"""Super-resolve the facecam region before it is scaled into the top pane.

THE FACECAM PANE IS A 3.7x UPSCALE. The crop on the FNS clips is ~290x205
source px and the top pane is 1080x806, so lanczos was inventing three of
every four pixels and the face read soft next to the sharp lower pane.
George's note on the first live delivery was "we need to upscale".

So the region the top pane can ever show is run through a learned 4x
super-resolver once, frame for frame, and the pane crops from THAT instead of
the source. Every crop in it is the source crop times exactly 4, so no
geometry moves: the pane shows the same rectangle, drawn from four times the
pixels, and lanczos only ever DOWN-scales.

The model is Real-ESRGAN's `realesr-general-x4v3` (BSD-3-Clause, 4.8 MB each
for it and its wdn twin),
the compact network the project ships for real-world video: one pass of 34
convolutions, fast enough to run every frame. The architecture is the
upstream SRVGGNetCompact, rewritten here so the only dependency is torch.

`CLIP_PREVIEW=1` (set by preview.py) skips it, because on a Mac it is most
of a clip's build time; Modal never sets it, so deliveries always have it.

It is an ENHANCEMENT, never a requirement: with no torch, no weights or any
failure, `upscale` returns None and the renderer keeps its lanczos path.
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from pathlib import Path

SCALE = 4
RELEASE = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/"
# Real-ESRGAN's own denoise-strength control: the weights are a blend of the
# denoising model and its "wdn" twin. At 1.0 skin came out waxy on the FNS
# facecam; 0.5 is upstream's default and keeps some texture.
DENOISE = 0.5
# Grown on every side so a punch-in or the big-facecam rect never reaches
# past what was super-resolved, and kept even so the yuv420 encode is exact.
MARGIN = 16
# Over this many source px wide, the pane (1080 wide) needs under 2x, which
# lanczos does fine, and 4x would be enormous: on job jnvouw6f23 a full-screen
# webcam scene gave a 1034x737 region, 4136x2948 out, 34 MB a frame through a
# pipe for 3400 frames, and clip 5 never finished.
MAX_W = 540


def _weights(name: str) -> Path:
    home = Path(os.environ.get("HF_HOME") or Path.home() / ".cache")
    p = home / "realesrgan" / name
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".part")
        urllib.request.urlretrieve(RELEASE + name, tmp)
        tmp.rename(p)
    return p


def _net(device):
    import torch                                          # noqa: PLC0415
    from torch import nn                                  # noqa: PLC0415
    import torch.nn.functional as F                       # noqa: PLC0415

    class SRVGGNetCompact(nn.Module):
        def __init__(self, feat=64, convs=32, up=SCALE):
            super().__init__()
            self.up = up
            body = [nn.Conv2d(3, feat, 3, 1, 1), nn.PReLU(num_parameters=feat)]
            for _ in range(convs):
                body += [nn.Conv2d(feat, feat, 3, 1, 1), nn.PReLU(num_parameters=feat)]
            body.append(nn.Conv2d(feat, 3 * up * up, 3, 1, 1))
            self.body = nn.ModuleList(body)
            self.upsampler = nn.PixelShuffle(up)

        def forward(self, x):
            out = x
            for layer in self.body:
                out = layer(out)
            return self.upsampler(out) + F.interpolate(x, scale_factor=self.up, mode="nearest")

    def load(name):
        sd = torch.load(_weights(name), map_location="cpu", weights_only=True)
        return sd.get("params_ema") or sd["params"]

    a, b = load("realesr-general-x4v3.pth"), load("realesr-general-wdn-x4v3.pth")
    net = SRVGGNetCompact()
    net.load_state_dict({k: DENOISE * a[k] + (1 - DENOISE) * b[k] for k in a})
    return net.eval().to(device)


def _device():
    import torch                                          # noqa: PLC0415
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def region(*rects, src_w: int = 1920, src_h: int = 1080) -> tuple[int, int, int, int]:
    """The even-sized source rect covering every rect the top pane can show."""
    x0 = max(0, int(min(r[0] for r in rects)) - MARGIN)
    y0 = max(0, int(min(r[1] for r in rects)) - MARGIN)
    x1 = min(src_w, int(max(r[2] for r in rects)) + MARGIN + 1)
    y1 = min(src_h, int(max(r[3] for r in rects)) + MARGIN + 1)
    x0 -= x0 % 2
    y0 -= y0 % 2
    x1 -= (x1 - x0) % 2
    y1 -= (y1 - y0) % 2
    return x0, y0, x1, y1


def _frames(path) -> int:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                          "-count_packets", "-show_entries", "stream=nb_read_packets,r_frame_rate",
                          "-of", "json", str(path)], capture_output=True, text=True).stdout
    s = json.loads(out)["streams"][0]
    return int(s["nb_read_packets"]), s["r_frame_rate"]


def upscale(src, rect, out, *, batch: int = 8, log=print) -> Path | None:
    """`rect` of `src`, super-resolved 4x into `out`, frame for frame.

    Cached beside `out` by source path, size and mtime plus the rect, so a
    rebuild with the same facecam reuses it and a moved rect never does."""
    if os.environ.get("CLIP_PREVIEW"):
        log("  upscale: skipped (CLIP_PREVIEW, a local preview build)")
        return None
    if rect[2] - rect[0] > MAX_W:
        log(f"  upscale: skipped, the region is {rect[2] - rect[0]}px wide "
            f"(over {MAX_W}), so lanczos is enough")
        return None
    out = Path(out)
    key = {"src": str(src), "size": Path(src).stat().st_size,
           "mtime": Path(src).stat().st_mtime, "rect": list(rect), "scale": SCALE, "denoise": DENOISE}
    stamp = out.with_suffix(".json")
    if out.exists() and stamp.exists() and json.loads(stamp.read_text()) == key:
        return out
    try:
        import numpy as np                                # noqa: PLC0415
        import torch                                      # noqa: PLC0415
        dev = _device()
        net = _net(dev)
    except Exception as e:                                # noqa: BLE001
        log(f"  upscale: unavailable ({type(e).__name__}: {e}); lanczos only")
        return None
    x0, y0, x1, y1 = rect
    w, h = x1 - x0, y1 - y0
    n, rate = _frames(src)
    dec = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", str(src), "-map", "0:v:0",
         "-vf", f"crop={w}:{h}:{x0}:{y0}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE)
    tmp = out.with_suffix(".part.mp4")
    enc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{w * SCALE}x{h * SCALE}", "-r", rate, "-i", "-",
         "-c:v", "libx264", "-preset", "fast", "-crf", "12", "-pix_fmt", "yuv444p",
         str(tmp)], stdin=subprocess.PIPE)
    size, done = w * h * 3, 0
    try:
        with torch.inference_mode():
            while True:
                buf = dec.stdout.read(size * batch)
                k = len(buf) // size
                if not k:
                    break
                x = torch.from_numpy(np.frombuffer(buf[:k * size], np.uint8)
                                     .reshape(k, h, w, 3).copy()).to(dev)
                x = x.permute(0, 3, 1, 2).float().div_(255)
                y = net(x).clamp_(0, 1).mul_(255).round_().byte()
                enc.stdin.write(y.permute(0, 2, 3, 1).contiguous().cpu().numpy().tobytes())
                done += k
    finally:
        enc.stdin.close()
        enc.wait()
        dec.wait()
    # ffprobe's packet count can sit one under what the decoder emits (4708
    # against 4709 on clip 8); the renderer decodes the source the same way
    # this did, so only a SHORT file is a failure.
    if enc.returncode or done < n:
        log(f"  upscale: wrote {done} of {n} frames; lanczos only")
        tmp.unlink(missing_ok=True)
        return None
    tmp.rename(out)
    stamp.write_text(json.dumps(key))
    log(f"  upscale: {w}x{h} -> {w * SCALE}x{h * SCALE}, {done} frames on {dev.type}")
    return out
