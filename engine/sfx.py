"""A synthesised sound-effect library, and the mixer that places it.

Why synthesised. Every source in this pipeline needs a rights basis and
`gates.py` rejects one without it; a downloaded SFX pack carries a licence
that has to be tracked per clip and per platform. These are generated from
numpy, so the basis is `synthesised` and it travels with the asset in
`assets/sfx/manifest.json`. They are also parametric, so the palette can be
retuned to a reference rather than re-sourced.

Tuned against the references, measured rather than guessed:

* **R3 (Pause) runs ~1.1 audio transients per second** over 27.7s — a dense
  bed, and the single biggest reason it feels produced next to a bare edit.
* Its transients split cleanly by spectral centroid: **bright hits at
  5.0–6.4 kHz** and **mid impacts at 1.9–2.8 kHz**.
* R4 (PlatChat) hits around cuts, within 0.1–0.3s of the picture change.

So the palette covers those bands: `ding` and `sparkle` bright, `impact` and
`thock` mid, `boom` low, `whoosh` and `riser` for movement.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

SR = 48000
ASSETS = Path(__file__).parent.parent / "assets" / "sfx"


def _env(n, attack=0.004, decay=0.25, power=2.0):
    a = int(attack * SR)
    e = np.ones(n, dtype=np.float32)
    e[:a] = np.linspace(0, 1, a, dtype=np.float32)
    tail = np.linspace(0, 1, n - a, dtype=np.float32)
    e[a:] = np.exp(-tail * (n - a) / SR / decay) ** power
    return e


def _noise(n, seed):
    return np.random.default_rng(seed).standard_normal(n).astype(np.float32)


def _lp(x, cutoff):
    """One-pole lowpass — enough shaping for percussive material."""
    a = np.exp(-2 * np.pi * cutoff / SR)
    out = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc = (1 - a) * v + a * acc
        out[i] = acc
    return out


def ding(dur=0.55, f0=2100.0):
    """Bright bell. R3's 5-6 kHz band comes from the upper partials."""
    n = int(dur * SR); t = np.arange(n) / SR
    y = np.zeros(n, dtype=np.float32)
    for mult, amp, dec in ((1.0, 1.0, 0.45), (2.76, 0.62, 0.30),
                           (5.40, 0.38, 0.18), (8.93, 0.20, 0.10)):
        y += (amp * np.sin(2 * np.pi * f0 * mult * t) * _env(n, 0.002, dec)).astype(np.float32)
    return y / np.max(np.abs(y))


def sparkle(dur=0.5):
    """Shimmer: a short upward cascade of bells."""
    n = int(dur * SR); y = np.zeros(n, dtype=np.float32)
    for i, f in enumerate((1800, 2400, 3200, 4300)):
        off = int(i * 0.035 * SR)
        d = ding(dur - off / SR, f) * (0.8 ** i)
        y[off:off + len(d)] += d
    return y / np.max(np.abs(y))


def impact(dur=0.33):
    """Mid thump plus a filtered crack, aimed at R3's 1.9-2.8 kHz band.

    The crack has to be lowpassed HARD and kept quiet. At cutoff 2600 and
    level 0.8 the broadband noise dominated the spectrum and the measured
    centroid came out at 6.2 kHz — a bright tick, not the mid impact the
    reference uses.
    """
    n = int(dur * SR); t = np.arange(n) / SR
    body = np.sin(2 * np.pi * np.linspace(190, 85, n) * t) * _env(n, 0.002, 0.11)
    mid = np.sin(2 * np.pi * np.linspace(900, 380, n) * t) * _env(n, 0.002, 0.07) * 0.55
    crack = _lp(_noise(n, 7), 1100) * _env(n, 0.001, 0.035) * 0.30
    y = (body + mid + crack).astype(np.float32)
    return y / np.max(np.abs(y))


def boom(dur=0.9):
    """Low sub hit for the heaviest beat. One per clip at most."""
    n = int(dur * SR); t = np.arange(n) / SR
    sweep = np.linspace(110, 42, n)
    y = np.sin(2 * np.pi * sweep * t) * _env(n, 0.006, 0.34)
    y += _lp(_noise(n, 11), 160) * _env(n, 0.002, 0.12) * 0.35
    return (y / np.max(np.abs(y))).astype(np.float32)


def whoosh(dur=0.42):
    """Band-swept noise for a transition."""
    n = int(dur * SR)
    base = _lp(_noise(n, 3), 5000)          # cap the top: raw noise measured 12.5 kHz
    low, high = _lp(base, 350), base - _lp(base, 1400)
    mix = np.linspace(0, 1, n, dtype=np.float32)
    y = low * (1 - mix) + high * mix
    shape = np.sin(np.linspace(0, np.pi, n)) ** 1.4
    return ((y * shape) / np.max(np.abs(y * shape))).astype(np.float32)


def riser(dur=0.8):
    """Builds into a beat. Place so it ENDS on the hit."""
    n = int(dur * SR); t = np.arange(n) / SR
    tone = np.sin(2 * np.pi * np.linspace(220, 1500, n) * t)
    noise = _lp(_noise(n, 5), 2200)
    y = (tone * 0.5 + noise * 0.5) * np.linspace(0, 1, n) ** 2.2
    return (y / np.max(np.abs(y))).astype(np.float32)


def thunk(dur=0.09, f0=190.0, seed=9):
    """A low body with a click on top — a card LANDING, not a note played.

    Fourth sound tried. The three rejected ones were a bell (547ms decay), a
    shorter bell (216ms) and a woodblock (65ms) — all pitched, all in the
    chime family. This is the other register: low, physical, and gone in
    87ms. For a card carrying job-loss figures, weight reads better than a
    pretty tone.

    The body sweeps DOWN (`f0 * exp(-8t)`), which is what makes an impact
    read as an impact rather than a tom hit.
    """
    n = int(dur * SR); t = np.arange(n) / SR
    body = np.sin(2 * np.pi * f0 * np.exp(-t * 8) * t) * np.exp(-t * 48)
    cl = int(0.005 * SR)
    click = np.zeros(n)
    click[:cl] = np.random.default_rng(seed).normal(0, 1, cl) * np.linspace(1, 0, cl)
    y = body + 0.30 * click
    return (y / np.max(np.abs(y))).astype(np.float32)


def cue_gain(name: str, target_rms_dbfs: float, master_gain_db: float) -> float:
    """Gain for a cue so it lands at a chosen RMS in the FINISHED master.

    Peak-normalised sounds are not equal-loudness: across the palette the RMS
    of a peak-normalised waveform spans 9 dB, so the same `gain` makes a chirp
    far louder than a tock. Every level note so far ("way too loud", then
    "slightly louder") was partly this. Pick a target RMS instead and let the
    gain fall out, and swapping one sound for another keeps the level.

    `master_gain_db` is what two-pass loudnorm will add — measure it on the
    clip (clip 8: -20.2 -> -14.0 LUFS, so +6.2).
    """
    y = PALETTE[name]()
    rel = 20 * float(np.log10(np.sqrt(np.mean(y.astype(np.float64) ** 2))))
    return float(10 ** ((target_rms_dbfs - master_gain_db - rel) / 20))


def tock(dur=0.10, f0=1180.0, seed=7):
    """A dry woodblock — the popup sound.

    Both earlier choices were rejected, and measuring them side by side says
    why: `ding` decays over 547ms and `pop` over 216ms, the two longest in the
    palette. Sustain is what makes a sound read as a chime playing rather than
    an event landing. This decays in 65ms and does not ring.

    Centroid is 2020 Hz (Hann-windowed; the tonal body alone is 1565 Hz).
    That is in the same region as the mid-impact transients measured off R3,
    but R3's figures came from a different measurement pass, so the decay is
    the claim to lean on, not the band. R3's DENSITY is not copied either:
    it is an advert, and R1 and R2 use no SFX at all.
    """
    n = int(dur * SR); t = np.arange(n) / SR
    body = (np.sin(2 * np.pi * f0 * t) * np.exp(-t * 60)
            + 0.45 * np.sin(2 * np.pi * f0 * 2.76 * t) * np.exp(-t * 115)
            + 0.20 * np.sin(2 * np.pi * f0 * 5.40 * t) * np.exp(-t * 190))
    cl = int(0.004 * SR)
    click = np.zeros(n)
    click[:cl] = np.random.default_rng(seed).normal(0, 1, cl) * np.linspace(1, 0, cl)
    y = body + 0.38 * click
    return (y / np.max(np.abs(y))).astype(np.float32)


def pop(dur=0.22, f0=1650.0):
    """A small soft ding for a popup appearing.

    `ding` is a 0.55s bell with four partials — far too much event for a chip
    sliding in. This is short, two partials, gentle attack, and it is meant to
    sit well under the speech: the sound belongs to the popup, it is not an
    effect in its own right.
    """
    n = int(dur * SR); t = np.arange(n) / SR
    y = (np.sin(2 * np.pi * f0 * t) * _env(n, 0.004, 0.10)
         + 0.35 * np.sin(2 * np.pi * f0 * 2.4 * t) * _env(n, 0.003, 0.05))
    return (y / np.max(np.abs(y))).astype(np.float32)


PALETTE = {"ding": ding, "sparkle": sparkle, "impact": impact,
           "boom": boom, "whoosh": whoosh, "riser": riser, "pop": pop, "tock": tock, "thunk": thunk}


def build(out: Path = ASSETS) -> dict:
    """Render the palette to disk with a manifest carrying the rights basis."""
    import soundfile as sf
    out.mkdir(parents=True, exist_ok=True)
    man = {}
    for name, fn in PALETTE.items():
        y = fn()
        sf.write(out / f"{name}.wav", y * 0.9, SR, subtype="PCM_16")
        peak = float(np.max(np.abs(y)))
        cent = _centroid(y)
        man[name] = {"file": f"{name}.wav", "seconds": round(len(y) / SR, 3),
                     "peak": round(peak, 3), "centroid_hz": round(cent),
                     "rights_basis": "synthesised",
                     "source": "engine/sfx.py — generated, no third-party audio"}
    (out / "manifest.json").write_text(json.dumps(man, indent=1))
    return man


def _centroid(y):
    """Spectral centroid, Hann-windowed.

    WINDOW IT. An un-windowed rfft of a short burst leaks the hard start and
    end across the whole spectrum, and since the sum is unweighted that
    leakage dominates: `tock` read 7173 Hz raw against 2020 Hz windowed, and
    its tonal body is at 1565 Hz. Every figure in the manifest was inflated
    this way before the fix.
    """
    S = np.abs(np.fft.rfft(y * np.hanning(len(y))))
    f = np.fft.rfftfreq(len(y), 1 / SR)
    return float((S * f).sum() / max(S.sum(), 1e-9))


# ─── placement ────────────────────────────────────────────────────────────

from dataclasses import dataclass


@dataclass
class Cue:
    """One sound effect, placed. `motivation` is required, same as a visual
    effect — a sound that punctuates nothing is noise."""
    at: float
    name: str
    gain: float
    motivation: str
    align: str = "start"          # 'start' or 'end' (for risers)

    def __post_init__(self):
        if self.name not in PALETTE:
            raise ValueError(f"no such effect {self.name!r}; have {sorted(PALETTE)}")
        if not (self.motivation or "").strip():
            raise ValueError(f"{self.name} at {self.at}s has no motivation")


def bed(cues, duration, *, out: Path, assets: Path = ASSETS):
    """Render the cue list to a single audio bed the length of the clip."""
    import soundfile as sf
    n = int(duration * SR) + SR
    track = np.zeros(n, dtype=np.float32)
    for c in cues:
        y, sr = sf.read(assets / f"{c.name}.wav", dtype="float32")
        if y.ndim > 1:
            y = y.mean(axis=1)
        start = c.at - (len(y) / SR if c.align == "end" else 0.0)
        i = max(0, int(start * SR))
        seg = y[: n - i] * c.gain
        track[i:i + len(seg)] += seg
    peak = float(np.max(np.abs(track)))
    if peak > 0.99:
        track *= 0.99 / peak
    sf.write(out, track, SR, subtype="PCM_16")
    return {"cues": len(cues), "peak": round(peak, 3),
            "seconds": round(len(track) / SR, 2)}


def newsding(dur=0.42, f0=784.0, f1=1175.0, seed=13):
    """A two-note news sting — George asked for "some kind of news ding".

    Not the popup `thunk`, which says "a fact landed". This says "a story",
    so it is pitched and it RESOLVES: G5 then D6, a fifth apart, the second
    entering while the first still rings. Both are short and the pair is
    gone in 420ms, because a sting that outstays its welcome is the thing
    that got the first four sound designs rejected.
    """
    n = int(dur * SR); t = np.arange(n) / SR
    y = np.zeros(n, dtype=np.float64)

    def note(start, freq, decay, amp):
        i = int(start * SR)
        m = n - i
        if m <= 0:
            return
        tt = np.arange(m) / SR
        env = np.exp(-tt * decay)
        env[:int(0.003 * SR)] *= np.linspace(0, 1, int(0.003 * SR))
        y[i:] += amp * env * (np.sin(2 * np.pi * freq * tt)
                              + 0.30 * np.sin(2 * np.pi * freq * 2 * tt)
                              + 0.12 * np.sin(2 * np.pi * freq * 3 * tt))

    note(0.000, f0, 13.0, 1.00)
    note(0.105, f1, 10.0, 0.92)
    return (y / np.max(np.abs(y))).astype(np.float32)


# newsding is defined after PALETTE, so it registers itself here rather
# than being named in a dict literal above its own def.
PALETTE["newsding"] = newsding


def tick(dur=0.030, f0=2600.0, seed=21):
    """A tiny click — one digit of an odometer turning.

    George: "include natural sound effects to your motion designs." The
    graphics had one cue on arrival and then moved in silence. A counter
    that rolls should tick, and the tick has to be nearly nothing: 30ms, a
    short pitched body under a noise edge, so twenty of them in two seconds
    read as a mechanism rather than as twenty effects.
    """
    n = int(dur * SR); t = np.arange(n) / SR
    body = np.sin(2 * np.pi * f0 * t) * np.exp(-t * 300)
    cl = int(0.0012 * SR)
    edge = np.zeros(n)
    edge[:cl] = np.random.default_rng(seed).normal(0, 1, cl) * np.linspace(1, 0, cl)
    return ((body + 0.5 * edge) / np.max(np.abs(body + 0.5 * edge))).astype(np.float32)


def paper(dur=0.26, seed=29):
    """A card settling on a desk — a soft broadband rustle with a low thud.

    For the tilted news story, which is drawn as paper. Natural rather than
    synthetic: no pitch to speak of, mostly filtered noise, and the body is
    low enough to sit under speech instead of beside it. NOT a whoosh —
    that family was rejected and this has no sweep.
    """
    n = int(dur * SR); t = np.arange(n) / SR
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, 1, n)
    for _ in range(4):                       # roll off the top; paper is dull
        noise = np.convolve(noise, np.ones(5) / 5, mode="same")
    rustle = noise * np.exp(-t * 16) * (1 - np.exp(-t * 180))
    thud = np.sin(2 * np.pi * 120 * np.exp(-t * 6) * t) * np.exp(-t * 26)
    y = 1.0 * rustle / (np.max(np.abs(rustle)) or 1) + 0.55 * thud
    return (y / np.max(np.abs(y))).astype(np.float32)


PALETTE["tick"] = tick
PALETTE["paper"] = paper
