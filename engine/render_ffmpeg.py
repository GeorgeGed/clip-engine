"""Backend A: render an edit.json with ffmpeg. Headless, parallel, free.

This is the volume path and the preview path. It is deliberately not the hero
path: ffmpeg does hard speed changes, so a `ramp_frames` value is approximated
by a short staircase rather than a true ease. True ramps, grades and Fusion
titles belong in the Resolve backend (engine/fcpxml.py + engine/resolve_driver.py).

This build of ffmpeg has no drawtext, subtitles or ass filter — the Homebrew
core bottle ships without them — so captions and overlays are rendered to PNG
with Pillow and composited with `overlay`. That path works on any ffmpeg.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

FONT_DEFAULT = Path(__file__).parent.parent / "fonts" / "LuckiestGuy-Regular.ttf"
RAMP_STEPS = 3


def _run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed\n{' '.join(cmd[:14])}...\n{p.stderr[-2500:]}")


def _atempo_chain(speed: float) -> str:
    """atempo only accepts 0.5..100, so compose a chain for anything outside."""
    parts, s = [], float(speed)
    while s < 0.5:
        parts.append("atempo=0.5")
        s /= 0.5
    while s > 100.0:
        parts.append("atempo=100")
        s /= 100.0
    parts.append(f"atempo={s:.6f}")
    return ",".join(parts)


# ─── Stage 1: segments ─────────────────────────────────────────────────────

def _segment_plan(edit: dict) -> list[dict]:
    """Expand each segment, turning a ramp into a short staircase."""
    fps = float(edit["source"]["fps"])
    plan: list[dict] = []
    segs = edit["segments"]
    for i, s in enumerate(segs):
        speed = float(s["speed"])
        ramp = int(s.get("ramp_frames") or 0)
        t0, t1 = float(s["in"]), float(s["out"])
        if speed == 1.0 or ramp <= 0:
            plan.append({"in": t0, "out": t1, "speed": speed})
            continue
        ramp_s = min(ramp / fps, (t1 - t0) / 3.0)
        step = ramp_s / RAMP_STEPS
        cur = t0
        for k in range(RAMP_STEPS):               # ease in
            sp = 1.0 + (speed - 1.0) * ((k + 1) / RAMP_STEPS)
            plan.append({"in": cur, "out": cur + step, "speed": sp})
            cur += step
        body_end = t1 - ramp_s
        if body_end > cur:
            plan.append({"in": cur, "out": body_end, "speed": speed})
            cur = body_end
        for k in range(RAMP_STEPS):               # ease out
            sp = speed + (1.0 - speed) * ((k + 1) / RAMP_STEPS)
            plan.append({"in": cur, "out": min(cur + step, t1), "speed": sp})
            cur += step
    return [p for p in plan if p["out"] - p["in"] > 1e-4]


def _has_audio(path: str | Path) -> bool:
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
         "stream=index", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    return bool(p.stdout.strip())


def _cut_segments(edit: dict, work: Path) -> list[Path]:
    src = edit["source"]["path"]
    fps = float(edit["render"]["fps"])
    has_a = _has_audio(src)
    out: list[Path] = []
    for i, p in enumerate(_segment_plan(edit)):
        dst = work / f"seg_{i:04d}.mp4"
        dur = p["out"] - p["in"]
        speed = p["speed"]
        vf = f"setpts=PTS/{speed},fps={fps}"
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-ss", f"{p['in']:.4f}", "-t", f"{dur:.4f}", "-i", src,
            "-filter:v", vf,
        ]
        if has_a:
            cmd += ["-filter:a", _atempo_chain(speed), "-c:a", "aac", "-b:a", "192k"]
        else:
            cmd += ["-an"]
        cmd += [
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
            "-pix_fmt", "yuv420p", "-fps_mode", "cfr", "-r", str(fps), str(dst),
        ]
        _run(cmd)
        out.append(dst)
    return out


def _concat(parts: list[Path], work: Path) -> Path:
    lst = work / "concat.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in parts))
    dst = work / "joined.mp4"
    _run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
          "-i", str(lst), "-c", "copy", str(dst)])
    return dst


# ─── Stage 2: layout ──────────────────────────────────────────────────────

def _layout_filter(edit: dict) -> str:
    L = edit["layout"]
    mode = L["mode"]
    W = int(edit["render"]["width"])
    H = int(edit["render"]["height"])

    if mode == "L1":
        # Full 16:9 intact, centred over a blurred fill of itself.
        return (
            f"[0:v]scale={W}:-2[fg];"
            f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},gblur=sigma=30,"
            f"scale=iw*1.06:ih*1.06,crop={W}:{H}[bg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2[v]"
        )

    if mode == "L2":
        fc = L.get("facecam_source") or {"x": 0.0, "y": 0.73, "w": 0.23, "h": 0.27}
        ratio = float(L.get("split_ratio", 0.44))
        top_h = int(H * ratio) // 2 * 2
        bot_h = (H - top_h) // 2 * 2
        sharpen = ",unsharp=5:5:1.0:5:5:0.0" if L.get("facecam_sharpen", True) else ""
        return (
            f"[0:v]crop=iw*{fc['w']}:ih*{fc['h']}:iw*{fc['x']}:ih*{fc['y']},"
            f"scale={W}:{top_h}:flags=lanczos{sharpen}[cam];"
            f"[0:v]scale={W}:{bot_h}:force_original_aspect_ratio=increase,"
            f"crop={W}:{bot_h}[game];"
            f"[cam][game]vstack=inputs=2[v]"
        )

    # L3: crop to fill, then put the lost HUD back.
    crop = L.get("crop") or {}
    ax = float(crop.get("anchor_x", 0.5))
    punch = float(crop.get("punch", 1.0))
    # A 9:16 window out of 16:9 uses the FULL height and crops horizontally,
    # so anchor_y only does anything once a punch crops vertically too.
    cw = f"ih*9/16/{punch:.4f}"
    ch = f"ih/{punch:.4f}"
    ay = float(crop.get("anchor_y", 0.5)) if punch > 1.0 else 0.5
    chain = [
        f"[0:v]crop={cw}:{ch}:(iw-{cw})*{ax:.4f}:(ih-{ch})*{ay:.4f},"
        f"scale={W}:{H}:flags=lanczos[main]"
    ]
    last = "main"
    for i, el in enumerate(L.get("hud_recomposite", []) or []):
        sx, sy, sw, sh = el["src"]
        dx, dy = el["dst"]
        sc = float(el.get("scale", 0.85))
        chain.append(
            f"[0:v]crop=iw*{sw}:ih*{sh}:iw*{sx}:ih*{sy},"
            f"scale=iw*{sc}*{W}/1920:-2[hud{i}]"
        )
        chain.append(f"[{last}][hud{i}]overlay={int(dx * W)}:{int(dy * H)}[st{i}]")
        last = f"st{i}"
    chain.append(f"[{last}]null[v]")
    return ";".join(chain)


def _apply_layout(joined: Path, edit: dict, work: Path) -> Path:
    dst = work / "layout.mp4"
    _run([
        "ffmpeg", "-y", "-v", "error", "-i", str(joined),
        "-filter_complex", _layout_filter(edit),
        "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "medium", "-crf", "17",
        "-pix_fmt", "yuv420p", "-c:a", "copy", str(dst),
    ])
    return dst


# ─── Stage 3: captions and overlays, as PNGs ──────────────────────────────

def _text_png(
    text: str, path: Path, *, width: int, font_size: int,
    emphasis: str | None = None, max_lines: int = 2,
) -> tuple[int, int]:
    font_path = FONT_DEFAULT if FONT_DEFAULT.exists() else None
    font = (ImageFont.truetype(str(font_path), font_size) if font_path
            else ImageFont.load_default(font_size))

    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        probe = Image.new("RGBA", (10, 10))
        if ImageDraw.Draw(probe).textlength(trial, font=font) > width * 0.86 and cur:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    lines = lines[:max_lines]

    pad, lh = 18, int(font_size * 1.22)
    img = Image.new("RGBA", (width, lh * len(lines) + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    stroke = max(3, font_size // 16)
    for i, ln in enumerate(lines):
        tw = d.textlength(ln, font=font)
        x, y = (width - tw) / 2, pad + i * lh
        if emphasis and emphasis.lower() in ln.lower():
            # Draw the line in parts so only the emphasised word changes colour.
            cx = x
            for tok in ln.split(" "):
                col = (255, 214, 0, 255) if tok.lower().strip(".,!?") == emphasis.lower() else (255, 255, 255, 255)
                d.text((cx, y), tok, font=font, fill=col,
                       stroke_width=stroke, stroke_fill=(0, 0, 0, 235))
                cx += d.textlength(tok + " ", font=font)
        else:
            d.text((x, y), ln, font=font, fill=(255, 255, 255, 255),
                   stroke_width=stroke, stroke_fill=(0, 0, 0, 235))
    img.save(path)
    return img.size


def _timeline_map(edit: dict) -> list[tuple[float, float, float]]:
    """(source_in, source_out, output_start) for each planned sub-segment."""
    out, t = [], 0.0
    for p in _segment_plan(edit):
        dur_out = (p["out"] - p["in"]) / p["speed"]
        out.append((p["in"], p["out"], t))
        t += dur_out
    return out


def _to_output_time(edit: dict, t_src: float) -> float | None:
    for (a, b, start) in _timeline_map(edit):
        if a - 1e-6 <= t_src <= b + 1e-6:
            speed = (b - a) / max(1e-9, (b - a))
            seg = next(p for p in _segment_plan(edit) if abs(p["in"] - a) < 1e-6)
            return start + (t_src - a) / seg["speed"]
    return None


def _burn_overlays(video: Path, edit: dict, work: Path) -> Path:
    W = int(edit["render"]["width"])
    H = int(edit["render"]["height"])
    caps = edit.get("captions") or {}
    overlays = edit.get("overlays") or []

    inputs: list[str] = ["-i", str(video)]
    chain: list[str] = []
    last = "0:v"
    idx = 1

    if caps.get("enabled") and caps.get("cards"):
        size = 76 if caps.get("style") == "word" else 68
        y_frac = float(caps.get("position_y", 0.64))
        for n, c in enumerate(caps["cards"]):
            o_in = _to_output_time(edit, float(c["in"]))
            o_out = _to_output_time(edit, float(c["out"]))
            if o_in is None or o_out is None or o_out <= o_in:
                continue
            png = work / f"cap_{n:04d}.png"
            w_, h_ = _text_png(c["text"], png, width=W, font_size=size,
                               emphasis=c.get("emphasis"),
                               max_lines=int(caps.get("max_lines", 2)))
            inputs += ["-i", str(png)]
            y_px = int(y_frac * H - h_ / 2)
            chain.append(
                f"[{last}][{idx}:v]overlay=0:{y_px}:"
                f"enable='between(t,{o_in:.3f},{o_out:.3f})'[c{n}]"
            )
            last = f"c{n}"
            idx += 1

    for n, ov in enumerate(overlays):
        if ov.get("type") != "credit" or not ov.get("text"):
            continue
        png = work / f"credit_{n}.png"
        size = int(ov.get("size", 38))
        margin = int(ov.get("margin", 36))
        w_, h_ = _text_png(ov["text"], png, width=int(W * 0.5), font_size=size, max_lines=1)
        inputs += ["-i", str(png)]
        pos = ov.get("position", "top-left")
        x = margin if "left" in pos else W - int(W * 0.5) - margin
        y = margin if "top" in pos else H - h_ - margin
        chain.append(f"[{last}][{idx}:v]overlay={x}:{y}[o{n}]")
        last = f"o{n}"
        idx += 1

    dst = work / "overlaid.mp4"
    if not chain:
        shutil.copy(video, dst)
        return dst
    chain.append(f"[{last}]null[v]")
    _run(["ffmpeg", "-y", "-v", "error", *inputs,
          "-filter_complex", ";".join(chain),
          "-map", "[v]", "-map", "0:a?",
          "-c:v", "libx264", "-preset", "medium", "-crf", "17",
          "-pix_fmt", "yuv420p", "-c:a", "copy", str(dst)])
    return dst


# ─── Stage 4: audio ───────────────────────────────────────────────────────

def _finish_audio(video: Path, edit: dict, out_path: Path) -> Path:
    a = edit.get("audio") or {}
    lufs = float(a.get("target_lufs", -14.0))
    tp = float(a.get("true_peak_dbtp", -1.0))
    if not _has_audio(video):
        _run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-c", "copy",
              "-movflags", "+faststart", str(out_path)])
        return out_path

    # Two-pass loudnorm. The single-pass filter only estimates, and lands a
    # dB or more off target — which on a platform that re-normalises is the
    # difference between your clip and the one next to it.
    import re as _re

    probe_p = subprocess.run(
        ["ffmpeg", "-i", str(video), "-af",
         f"loudnorm=I={lufs}:TP={tp}:LRA=11:print_format=json", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    blob = _re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", probe_p.stderr, _re.S)
    af = f"loudnorm=I={lufs}:TP={tp}:LRA=11"
    if blob:
        m = json.loads(blob.group(0))
        af = (
            f"loudnorm=I={lufs}:TP={tp}:LRA=11"
            f":measured_I={m['input_i']}:measured_TP={m['input_tp']}"
            f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}"
            f":offset={m['target_offset']}:linear=true:print_format=summary"
        )
    _run([
        "ffmpeg", "-y", "-v", "error", "-i", str(video),
        "-af", af, "-c:v", "copy",
        "-c:a", edit["render"].get("audio_codec", "aac"), "-b:a", "192k",
        "-ar", "48000", "-movflags", "+faststart", str(out_path),
    ])
    return out_path


# ─── Entry point ──────────────────────────────────────────────────────────

def render(edit: dict, out_path: str | Path, *, keep_work: bool = False) -> dict:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="clipeng_"))
    try:
        parts = _cut_segments(edit, work)
        joined = _concat(parts, work) if len(parts) > 1 else parts[0]
        laid = _apply_layout(joined, edit, work)
        over = _burn_overlays(laid, edit, work)
        final = _finish_audio(over, edit, out_path)

        from engine.ingest import probe, measure_loudness

        info = probe(final)
        loud = measure_loudness(final)
        return {
            "output": str(final),
            "duration": info["duration"],
            "fps": info["fps"],
            "resolution": [info["width"], info["height"]],
            "measured_lufs": loud.get("measured_lufs"),
            "true_peak_dbtp": loud.get("true_peak_dbtp"),
            "work_dir": str(work) if keep_work else None,
        }
    finally:
        if not keep_work:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="render an edit.json with ffmpeg")
    ap.add_argument("edit_json")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--keep-work", action="store_true")
    ap.add_argument("--skip-gates", action="store_true")
    a = ap.parse_args()

    edit = json.loads(Path(a.edit_json).read_text())

    if not a.skip_gates:
        from engine import gates

        errs = gates.validate_schema(edit)
        if errs:
            raise SystemExit("schema invalid:\n  " + "\n  ".join(errs))
        res = gates.check(edit)
        print(res.report())
        if not res.passed:
            raise SystemExit("gates rejected this edit; nothing rendered")
        edit = res.edit

    print(json.dumps(render(edit, a.out, keep_work=a.keep_work), indent=2))


# THE VOICE CHAIN, measured on this source rather than applied on faith.
# `scenario-auto-edit` lists six moves; four measured as unnecessary here and
# were refused (de-esser: sibilance already -20.2 dB; "a little air": we CUT
# the top because it measured +10.7 dB hot against R1/R2; +2 dB at 3.6 kHz:
# we already do +4 at 3 k; 3:1 compression: speech runs LRA 0.5-0.8 on
# mute-free spans, flatter than R2, so there is no dynamic to compress).
# These two measured as needed: rumble sat -5.1 dB against the speech body
# and 280 Hz was +1.6 dB boxy.
#
# It lived at module scope in `finish_audio.py` next to a `print(qc.check(...))`
# on a hardcoded v27 render, so importing it re-QC'd an unrelated old file.
HOUSE_EQ = ("highpass=f=85,"
      "equalizer=f=280:t=q:w=1.0:g=-2.5,"
      "equalizer=f=3000:t=q:w=1.1:g=4,"
      "equalizer=f=9500:t=q:w=1.0:g=-7")

# THE HIGH-PASS IS A MEASUREMENT, NOT A HOUSE CONSTANT — and leaving it one
# cost the Vine Boom half its body.
#
# `highpass=f=85` was set because ONE clip's master measured rumble at -5.1 dB
# against the speech body. It then applied to every clip, and to the sfx bed,
# which Resolve renders into the master on A2.
#
# Measured on the Vine Boom: 52.8% of its magnitude sits UNDER 85 Hz, so the
# full chain costs it **7.09 dB RMS** (-7.67 -> -14.76 dBFS) while costing its
# peak only 1.83 dB — i.e. it hollows the sound out rather than quietening it.
# Meanwhile clip 12's own base measures sub-85 at **-36.95 dBFS against a
# 200-4000 Hz body of -24.50**, which is 12.45 dB down and already masked.
#
# So on this clip the filter removed nothing audible and took 7 dB off the one
# cue whose whole point is low end. The floor is -10 dB: rumble within 10 dB
# of the speech body gets filtered, anything further down is inaudible and the
# filter costs more than it buys. Raising the boom to compensate would have
# been the stacked compensation this project keeps deleting.
RUMBLE_FLOOR_DB = -10.0


def _band_rms_db(src: str | Path, af: str) -> float:
    """RMS of one band of `src`, in dBFS."""
    import array, math, subprocess
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(src), "-af", af,
         "-ac", "1", "-ar", "48000", "-f", "s16le", "-"],
        capture_output=True).stdout
    a = array.array("h"); a.frombytes(raw)
    if not a:
        return -999.0
    r = math.sqrt(sum((v / 32768.0) ** 2 for v in a) / len(a))
    return 20 * math.log10(r) if r > 0 else -999.0


def house_eq(src: str | Path) -> tuple[str, dict]:
    """The voice chain for THIS source, with the high-pass only if earned.

    Returns the filter string and what was measured, so the decision lands in
    the build log rather than in a constant nobody re-checks.
    """
    rumble = _band_rms_db(src, "lowpass=f=85")
    body = _band_rms_db(src, "highpass=f=200,lowpass=f=4000")
    margin = rumble - body
    keep = margin > RUMBLE_FLOOR_DB
    chain = HOUSE_EQ if keep else HOUSE_EQ.split(",", 1)[1]
    return chain, {"rumble_dbfs": round(rumble, 2), "body_dbfs": round(body, 2),
                   "margin_db": round(margin, 2), "highpass": keep}
