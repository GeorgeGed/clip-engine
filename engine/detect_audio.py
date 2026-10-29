"""Tier 1 detection: find moments from sound alone.

A spike in vocal energy is a near-perfect streamer-highlight detector and costs
nothing once the audio is on disk. This finds those spikes and scores them.

Reads a 16 kHz mono WAV (engine/ingest.extract_audio). No cv2 here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import soundfile as sf

HOP_S = 0.05            # 50 ms analysis hop
ROLLING_WINDOW_S = 30.0
MIN_SEPARATION_S = 6.0
Z_THRESHOLD = 4.0       # robust-sigmas above the local median
EDGE_GUARD_S = 2.0      # rolling-baseline padding biases the first/last seconds
MAD_FLOOR_FRAC = 0.15   # floor the MAD at this fraction of global median RMS
ABS_RISE_FRAC = 0.8     # spike must also be this much louder than global median


@dataclass
class AudioEvent:
    t: float
    rms_z: float
    centroid_hz: float
    peak_rms: float
    duration: float

    def as_dict(self) -> dict:
        return asdict(self)


def _frame(x: np.ndarray, hop: int) -> np.ndarray:
    n = len(x) // hop
    return x[: n * hop].reshape(n, hop)


def analyse(wav_path: str | Path, *, offset: float = 0.0) -> dict:
    x, sr = sf.read(str(wav_path), dtype="float32", always_2d=False)
    if x.ndim > 1:
        x = x.mean(axis=1)

    hop = max(1, int(sr * HOP_S))
    frames = _frame(x, hop)
    if len(frames) == 0:
        return {"events": [], "sr": sr, "hop_s": HOP_S, "offset": offset}

    rms = np.sqrt((frames ** 2).mean(axis=1) + 1e-12)

    # Spectral centroid per frame: shouting pushes energy upward, which
    # separates a real reaction from a loud gunfight.
    spec = np.abs(np.fft.rfft(frames * np.hanning(hop), axis=1))
    freqs = np.fft.rfftfreq(hop, 1.0 / sr)
    centroid = (spec * freqs).sum(axis=1) / (spec.sum(axis=1) + 1e-12)

    # Robust local baseline — median and MAD over a rolling window.
    win = max(3, int(ROLLING_WINDOW_S / HOP_S))
    pad = win // 2
    padded = np.pad(rms, (pad, pad), mode="edge")
    strides = np.lib.stride_tricks.sliding_window_view(padded, win)[: len(rms)]
    med = np.median(strides, axis=1)
    mad = np.median(np.abs(strides - med[:, None]), axis=1)

    # On a near-constant baseline the MAD collapses to ~0 and z explodes to
    # meaningless thousands. Floor it against the global level so z stays a
    # comparable quantity across clips.
    global_med = float(np.median(rms))
    mad = np.maximum(mad, MAD_FLOOR_FRAC * global_med + 1e-9)
    z = (rms - med) / (1.4826 * mad)

    # Peak picking with a minimum separation.
    events: list[AudioEvent] = []
    min_sep = int(MIN_SEPARATION_S / HOP_S)
    guard = int(EDGE_GUARD_S / HOP_S)
    abs_floor = global_med * (1.0 + ABS_RISE_FRAC)
    order = np.argsort(-z)
    taken: list[int] = []
    for i in order:
        if z[i] < Z_THRESHOLD:
            break
        if i < guard or i >= len(rms) - guard:
            continue                      # padding artefact, not a moment
        if rms[i] < abs_floor:
            continue                      # statistically odd but not actually loud
        if any(abs(i - j) < min_sep for j in taken):
            continue
        taken.append(int(i))

        # Walk out to where the spike falls back to half its height.
        half = med[i] + (rms[i] - med[i]) * 0.5
        a = b = int(i)
        while a > 0 and rms[a] > half:
            a -= 1
        while b < len(rms) - 1 and rms[b] > half:
            b += 1

        events.append(
            AudioEvent(
                t=round(i * HOP_S + offset, 3),
                rms_z=round(float(z[i]), 2),
                centroid_hz=round(float(centroid[i]), 1),
                peak_rms=round(float(rms[i]), 5),
                duration=round((b - a) * HOP_S, 3),
            )
        )

    events.sort(key=lambda e: e.t)
    return {
        "sr": sr,
        "hop_s": HOP_S,
        "offset": offset,
        "events": [e.as_dict() for e in events],
    }


def regions(events: list[dict], *, join_gap: float = 45.0,
            min_events: int = 2, max_len: float = 150.0) -> list[dict]:
    """Group spikes into contiguous elevated stretches.

    The detector finds WHERE something is happening, not WHEN it starts. On FNS
    VOD 2905408276 the 0:46:30-0:49:30 stretch scored 0.69-0.89 throughout, and
    its peak sat 54s after the moment. So emit the stretch and let the
    transcript locate the in-point inside it (candidates.find_in_point).
    """
    if not events:
        return []
    ev = sorted(events, key=lambda e: e["t"])
    groups: list[list[dict]] = [[ev[0]]]
    for e in ev[1:]:
        if e["t"] - groups[-1][-1]["t"] <= join_gap:
            groups[-1].append(e)
        else:
            groups.append([e])

    # A long elevated run is SPLIT, never trimmed. Trimming to a window around
    # the peak silently deletes material: on FNS VOD 2905408276 a single run
    # spanned 0:46:49-0:52:36, and keeping only the peak's 150s threw away the
    # crowd-validated moment at 0:47:33 entirely.
    chunks: list[list[dict]] = []
    for g in groups:
        if len(g) < min_events:
            continue
        if g[-1]["t"] - g[0]["t"] <= max_len:
            chunks.append(g)
            continue
        cur = [g[0]]
        for e in g[1:]:
            if e["t"] - cur[0]["t"] > max_len:
                chunks.append(cur)
                cur = [e]
            else:
                cur.append(e)
        if len(cur) >= min_events:
            chunks.append(cur)

    out = []
    for g in chunks:
        if len(g) < min_events:
            continue
        scores = [reaction_score(e) for e in g]
        out.append({
            "start": round(g[0]["t"], 2), "end": round(g[-1]["t"], 2),
            "n_spikes": len(g),
            "peak_t": round(max(g, key=lambda e: reaction_score(e))["t"], 2),
            "peak": round(max(scores), 3),
            "mean": round(sum(scores) / len(scores), 3),
        })
    out.sort(key=lambda r: -(r["peak"] * 0.6 + r["mean"] * 0.4))
    return out


def reaction_score(ev: dict) -> float:
    """0..1. A reaction is loud *and* bright; a gunfight is loud and dull.

    z saturates slowly (tanh) so a z of 40 and a z of 2000 do not both read as
    1.0, and brightness carries real weight because it is what separates a
    shout from a spray of rifle fire.
    """
    import math

    loud = math.tanh(float(ev["rms_z"]) / 12.0)
    bright = min(max((float(ev["centroid_hz"]) - 700.0) / 1600.0, 0.0), 1.0)
    return round(0.55 * loud + 0.45 * bright, 3)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="find reaction spikes in audio")
    ap.add_argument("wav")
    ap.add_argument("-o", "--out", default="-")
    ap.add_argument("--offset", type=float, default=0.0)
    a = ap.parse_args()

    res = analyse(a.wav, offset=a.offset)
    for e in res["events"]:
        e["reaction_score"] = reaction_score(e)
    blob = json.dumps(res, indent=2)
    if a.out == "-":
        print(blob)
    else:
        Path(a.out).write_text(blob)
        print(f"{len(res['events'])} audio events -> {a.out}")
