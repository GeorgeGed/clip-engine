"""Measure a RENDERED file. The other half of engine/gates.py.

The distinction matters and it is easy to lose:

  * `gates.check` reads an `edit.json` and judges the PLAN. It runs before a
    frame exists. It can tell you the plan asks for a cut inside a word.
  * `qc.check` reads the mp4 and judges the ARTIFACT. It runs after. It can
    tell you the render landed 2 dB hot, dropped the audio track, or ended on
    fourteen black frames.

A clip can pass the gate and still be broken, because nothing about an
`edit.json` guarantees ffmpeg did what it was told. "Never claim a clip was
exported without reading the file back" is the project rule this implements.

Everything here is measured, not inferred. One ffmpeg pass collects loudness,
silence and black-frame data; ffprobe collects the container facts.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import gates

# A rendered clip that opens on silence buries its own hook.
LEAD_SILENCE_WARN_S = 0.35
# Trailing silence is normal (tail_frames) but a long one is dead air.
TAIL_SILENCE_WARN_S = 1.5
SILENCE_FLOOR_DB = -50
BLACK_PIX_THRESHOLD = 0.10
BLACK_MIN_S = 0.05
# How far the rendered duration may drift from the plan before it is a defect.
DURATION_TOLERANCE_S = 0.5


@dataclass
class QCResult:
    path: str = ""
    passed: bool = True
    rejected: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    measured: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "passed": self.passed,
            "rejected": self.rejected,
            "warnings": self.warnings,
            "measured": self.measured,
        }

    def report(self) -> str:
        m = self.measured
        head = f"{'PASS' if self.passed else 'REJECT'}  {Path(self.path).name}"
        bits = []
        if m.get("width"):
            bits.append(f"{m['width']}x{m['height']}@{m.get('fps', '?')}")
        if m.get("duration") is not None:
            bits.append(f"{m['duration']:.2f}s")
        if m.get("lufs") is not None:
            bits.append(f"{m['lufs']:.2f} LUFS")
        if m.get("true_peak") is not None:
            bits.append(f"{m['true_peak']:+.2f} dBTP")
        if m.get("lra") is not None:
            bits.append(f"LRA {m['lra']:.2f}")
        lines = [head + ("   " + "  ".join(bits) if bits else "")]
        for it in self.rejected:
            lines.append(f"  reject  {it}")
        for it in self.warnings:
            lines.append(f"  warn    {it}")
        return "\n".join(lines)


def _probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path}: {out.stderr.strip()[:300]}")
    return json.loads(out.stdout)


def _fps(stream: dict) -> float | None:
    raw = stream.get("r_frame_rate") or stream.get("avg_frame_rate") or ""
    if "/" not in raw:
        return None
    num, den = raw.split("/", 1)
    try:
        num, den = float(num), float(den)
    except ValueError:
        return None
    return round(num / den, 3) if den else None


def _analyse(path: Path) -> dict:
    """One ffmpeg pass: loudness, silence runs and black runs."""
    cmd = [
        "ffmpeg", "-nostdin", "-hide_banner", "-i", str(path),
        "-af", f"silencedetect=noise={SILENCE_FLOOR_DB}dB:d=0.2,"
               f"loudnorm=print_format=json",
        "-vf", f"blackdetect=d={BLACK_MIN_S}:pix_th={BLACK_PIX_THRESHOLD}",
        "-f", "null", "-",
    ]
    err = subprocess.run(cmd, capture_output=True, text=True).stderr

    out: dict[str, Any] = {"silences": [], "blacks": []}

    # loudnorm prints a JSON object last; take the final balanced block.
    blocks = re.findall(r"\{[^{}]*\}", err, re.S)
    for b in reversed(blocks):
        try:
            d = json.loads(b)
        except json.JSONDecodeError:
            continue
        if "input_i" in d:
            def num(k):
                v = d.get(k)
                try:
                    f = float(v)
                except (TypeError, ValueError):
                    return None
                return None if f <= -90 else f  # -inf sentinel on silent audio
            out["lufs"] = num("input_i")
            out["true_peak"] = num("input_tp")
            out["lra"] = num("input_lra")
            break

    for m in re.finditer(r"silence_start:\s*(-?[\d.]+)", err):
        out["silences"].append([float(m.group(1)), None])
    ends = [float(m.group(1)) for m in re.finditer(r"silence_end:\s*(-?[\d.]+)", err)]
    for i, e in enumerate(ends):
        if i < len(out["silences"]):
            out["silences"][i][1] = e

    for m in re.finditer(r"black_start:\s*([\d.]+)\s+black_end:\s*([\d.]+)", err):
        out["blacks"].append([float(m.group(1)), float(m.group(2))])

    return out


def check(path: str | Path, *, edit: dict | None = None,
          expect_canvas: bool = True) -> QCResult:
    """Measure a rendered clip and judge it.

    `edit` is the plan it was rendered from, when there is one. Without it the
    container and audio checks still run — which is what makes this usable on
    raw cuts as well as finished clips.

    `expect_canvas` off for raw source cuts, which are still 16:9.
    """
    p = Path(path)
    r = QCResult(path=str(p))

    if not p.exists():
        r.passed = False
        r.rejected.append("file does not exist")
        return r
    if p.stat().st_size == 0:
        r.passed = False
        r.rejected.append("file is zero bytes")
        return r

    meta = _probe(p)
    vs = next((s for s in meta.get("streams", []) if s.get("codec_type") == "video"), None)
    as_ = next((s for s in meta.get("streams", []) if s.get("codec_type") == "audio"), None)

    m = r.measured
    m["size_bytes"] = p.stat().st_size
    try:
        m["duration"] = round(float(meta["format"]["duration"]), 3)
    except (KeyError, ValueError):
        m["duration"] = None

    if vs is None:
        r.rejected.append("no video stream")
    else:
        m["width"] = int(vs.get("width") or 0)
        m["height"] = int(vs.get("height") or 0)
        m["fps"] = _fps(vs)
        m["video_codec"] = vs.get("codec_name")
        m["pix_fmt"] = vs.get("pix_fmt")
        if expect_canvas:
            want_w, want_h = gates.CANVAS
            if (m["width"], m["height"]) != (want_w, want_h):
                r.rejected.append(
                    f"canvas is {m['width']}x{m['height']}, expected {want_w}x{want_h}")

    if as_ is None:
        r.rejected.append("no audio stream — the render dropped the audio")
    else:
        m["audio_codec"] = as_.get("codec_name")
        m["sample_rate"] = int(as_.get("sample_rate") or 0)
        m["channels"] = int(as_.get("channels") or 0)

    # Duration against the absolute gate, and against the plan when given.
    lo, hi = gates.DURATION_ABSOLUTE
    if m["duration"] is not None and not (lo <= m["duration"] <= hi):
        r.rejected.append(f"duration {m['duration']:.2f}s outside the absolute {lo}-{hi}s")

    if edit and m["duration"] is not None:
        planned = _planned_duration(edit)
        if planned is not None:
            m["planned_duration"] = round(planned, 3)
            drift = abs(planned - m["duration"])
            m["duration_drift"] = round(drift, 3)
            if drift > DURATION_TOLERANCE_S:
                r.rejected.append(
                    f"rendered {m['duration']:.2f}s but the plan asks for "
                    f"{planned:.2f}s — drift {drift:.2f}s")

    if as_ is not None:
        a = _analyse(p)
        m["lufs"], m["true_peak"], m["lra"] = a.get("lufs"), a.get("true_peak"), a.get("lra")
        m["silences"] = a["silences"]
        m["blacks"] = a["blacks"]

        if m["lufs"] is None:
            r.rejected.append("audio stream is silent")
        else:
            glo, ghi = gates.LOUDNESS_RANGE
            if not (glo <= m["lufs"] <= ghi):
                r.warnings.append(
                    f"{m['lufs']:.2f} LUFS is outside the house band {glo} to {ghi}")
        if m["true_peak"] is not None and m["true_peak"] > gates.TRUE_PEAK_CEILING:
            r.rejected.append(
                f"true peak {m['true_peak']:+.2f} dBTP is above the "
                f"{gates.TRUE_PEAK_CEILING} ceiling — the master clips")

        dur = m["duration"] or 0.0
        for start, end in m["silences"]:
            if end is None:
                end = dur
            if start <= 0.05 and (end - start) > LEAD_SILENCE_WARN_S:
                r.warnings.append(
                    f"opens on {end - start:.2f}s of silence — buries the hook")
            if dur and end >= dur - 0.05 and (end - start) > TAIL_SILENCE_WARN_S:
                r.warnings.append(f"ends on {end - start:.2f}s of silence")

        for start, end in m["blacks"]:
            if dur and end >= dur - 0.05:
                r.warnings.append(f"ends on {end - start:.2f}s of black")
            elif start > 0.05:
                r.warnings.append(f"black frames mid-clip at {start:.2f}s")

    r.passed = not r.rejected
    return r


def _planned_duration(edit: dict) -> float | None:
    """Output duration the plan implies, accounting for speed changes."""
    segs = edit.get("segments")
    if not segs:
        rng = edit.get("range") or {}
        if "in" in rng and "out" in rng:
            return float(rng["out"]) - float(rng["in"])
        return None
    total = 0.0
    for s in segs:
        try:
            span = float(s["out"]) - float(s["in"])
        except (KeyError, TypeError, ValueError):
            return None
        total += span / float(s.get("speed", 1.0) or 1.0)
    fps = float((edit.get("source") or {}).get("fps") or 0) or None
    if fps and edit.get("tail_frames"):
        total += float(edit["tail_frames"]) / fps
    return total


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="measure a rendered clip")
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--edit", help="the edit.json it was rendered from")
    ap.add_argument("--raw", action="store_true",
                    help="raw source cut, not a 1080x1920 master")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    edit = json.loads(Path(a.edit).read_text()) if a.edit else None
    results = [check(p, edit=edit, expect_canvas=not a.raw) for p in a.paths]
    if a.json:
        print(json.dumps([r.as_dict() for r in results], indent=2))
    else:
        for r in results:
            print(r.report())
        bad = [r for r in results if not r.passed]
        warn = [r for r in results if r.passed and r.warnings]
        print(f"\n{len(results)} measured, {len(bad)} rejected, {len(warn)} with warnings")
    raise SystemExit(1 if any(not r.passed for r in results) else 0)
