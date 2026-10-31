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

from . import boundaries, gates

# A rendered clip that opens on dead air buries its own hook. The threshold is
# measured, not guessed — see engine/boundaries.LEAD_SILENCE_DEFECT_S.
LEAD_SILENCE_WARN_S = boundaries.LEAD_SILENCE_DEFECT_S
# Trailing silence is normal (tail_frames) but a long one is dead air.
TAIL_SILENCE_WARN_S = 1.5
SILENCE_FLOOR_DB = -50
# Absent audio, not quiet audio. Real room tone never reaches this; a muted or
# dropped region does. See dead_audio() for the measurement behind the number.
DEAD_AUDIO_FLOOR_DB = -90.0
DEAD_AUDIO_FLOOR = 10 ** (DEAD_AUDIO_FLOOR_DB / 20)
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

        # loudnorm clamps the integrated loudness of a very quiet signal to
        # -inf, so a missing input_i alone does not mean silence. True peak is
        # the corroborating measurement: present-but-quiet still has one.
        if m["lufs"] is None and (m["true_peak"] is None
                                  or m["true_peak"] < DEAD_AUDIO_FLOOR_DB):
            r.rejected.append("audio stream is silent")
        elif m["lufs"] is None:
            r.warnings.append(
                f"integrated loudness unmeasurable (true peak "
                f"{m['true_peak']:.2f} dBTP) — the audio is present but far "
                f"below any usable level")
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

        dead = dead_audio(p)
        m["dead_audio_total"] = dead["total"]
        m["dead_audio_fraction"] = dead["fraction"]
        m["dead_audio_runs"] = dead["runs"]
        if dead["runs"]:
            r.warnings.append(
                f"{dead['total']:.1f}s of the audio is digital zero "
                f"({dead['fraction']:.0%}), in {len(dead['runs'])} run(s) — "
                f"absent, not quiet; check the source for muted regions")
            first, last = dead["runs"][0], dead["runs"][-1]
            # 0.15s, not 0.05s: the run boundary lands a frame or two in.
            if first[0] <= 0.15:
                r.rejected.append(
                    f"opens on {first[1] - first[0]:.1f}s of absent audio")
            if dur and last[1] >= dur - 0.05:
                r.rejected.append(
                    f"ends on {last[1] - last[0]:.1f}s of absent audio")

        for start, end in m["blacks"]:
            if dur and end >= dur - 0.05:
                r.warnings.append(f"ends on {end - start:.2f}s of black")
            elif start > 0.05:
                r.warnings.append(f"black frames mid-clip at {start:.2f}s")

    r.passed = not r.rejected
    return r


def dead_audio(path: str | Path, *, min_run: float = 0.5) -> dict:
    """Find runs of EXACT digital zero — audio that is absent, not merely quiet.

    This is a different defect from silence and must not be confused with it. A
    pause has a noise floor; a muted or dropped region has literal zero
    samples. Twitch replaces DMCA-flagged audio this way, and a clip whose edge
    sits on one of those boundaries opens or ends on nothing.

    Measured on FNS VOD 2905408276: 35.8% of the audio is absent across 552
    runs, present identically in independently fetched 720p and 1080p
    renditions, so it is in the VOD rather than the download.

    The test is a dB floor, not equality with zero. After AAC the muted region
    decodes to about -122 dBFS rather than exact zeros, while speech in the
    same file peaks at -4.1 dBFS. At the -90 dBFS floor the muted region is
    100% below and speech 0.1% below (its zero crossings), so the separation is
    not close. An earlier exact-zero test silently found nothing.
    """
    import numpy as np

    out = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", str(path),
         "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
        capture_output=True,
    )
    a = np.frombuffer(out.stdout, dtype="<f4")
    if a.size == 0:
        return {"runs": [], "total": 0.0, "fraction": 0.0}

    sr = 16000
    zero = np.abs(a) < DEAD_AUDIO_FLOOR
    d = np.diff(zero.astype(np.int8))
    starts = (np.where(d == 1)[0] + 1).tolist()
    ends = (np.where(d == -1)[0] + 1).tolist()
    if zero[0]:
        starts.insert(0, 0)
    if zero[-1]:
        ends.append(zero.size)

    runs = [[round(s / sr, 3), round(e / sr, 3)] for s, e in zip(starts, ends)
            if (e - s) / sr >= min_run]
    total = sum(e - s for s, e in runs)
    return {"runs": runs, "total": round(total, 3),
            "fraction": round(total / (a.size / sr), 4)}


def leading_silence(path: str | Path) -> float:
    """Seconds of silence at the head of a file. 0.0 if it opens on sound."""
    dur = None
    try:
        dur = float(_probe(Path(path))["format"]["duration"])
    except (KeyError, ValueError, RuntimeError):
        pass
    for start, end in _analyse(Path(path))["silences"]:
        if start is not None and start <= 0.05:
            return round((end if end is not None else (dur or 0.0)) - start, 3)
    return 0.0


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


QUIET_BELOW_SPEECH_DB = 12.0


def quiet_runs(path, *, min_run: float = 0.35, window: float = 0.05,
               below_speech_db: float = QUIET_BELOW_SPEECH_DB) -> dict:
    """Runs of ordinary low-level silence, relative to the speaker's own level.

    `dead_audio` finds DIGITAL ZERO — the Twitch mutes. This finds the other
    kind of dead space: real room tone between sentences. George, on
    talking-head clips: "ensure there is NO dead space."

    The floor is relative, not absolute, because raw VOD audio runs about
    7 dB under target and a fixed dBFS threshold would mean something
    different on every clip. The speech level is taken as the 75th
    percentile of window RMS, and anything `below_speech_db` under that is
    quiet.
    """
    import subprocess

    import numpy as np

    sr = 16000
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr),
         "-f", "f32le", "-"], capture_output=True).stdout
    a = np.frombuffer(raw, np.float32)
    w = max(1, int(window * sr))
    n = len(a) // w
    if n == 0:
        return {"runs": [], "total": 0.0, "fraction": 0.0, "floor_db": None}
    rms = np.array([
        20 * np.log10(max(1e-7, float(np.sqrt(np.mean(a[i * w:(i + 1) * w] ** 2)))))
        for i in range(n)])
    speech = float(np.percentile(rms, 75))
    floor = speech - below_speech_db

    runs, st = [], None
    for i, q in enumerate(rms < floor):
        if q and st is None:
            st = i
        elif not q and st is not None:
            if (i - st) * window >= min_run:
                runs.append([round(st * window, 3), round(i * window, 3)])
            st = None
    if st is not None and (n - st) * window >= min_run:
        runs.append([round(st * window, 3), round(n * window, 3)])
    total = sum(e - s for s, e in runs)
    return {"runs": runs, "total": round(total, 3),
            "fraction": round(total / (len(a) / sr), 4),
            "floor_db": round(floor, 1), "speech_db": round(speech, 1)}
