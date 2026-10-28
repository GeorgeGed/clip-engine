"""Word-level transcription. Tier 1 of detection, and the source of truth for
every cut in a take clip.

Word timestamps are not a nicety: engine/gates.py rejects any take-clip cut that
does not land on a word boundary, and it reads the boundaries produced here.

Do not import cv2 in this process. faster-whisper brings its own PyAV ffmpeg
dylibs and they collide with opencv's. Transcription and vision run as separate
processes by design.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path

MODEL_DEFAULT = "large-v3"   # accuracy over speed; George's standing preference
COMPUTE_DEFAULT = "int8"     # CPU-friendly on Apple silicon


@dataclass
class Word:
    start: float
    end: float
    text: str
    prob: float


@dataclass
class Utterance:
    start: float
    end: float
    text: str
    words: list[Word]

    def as_dict(self) -> dict:
        d = asdict(self)
        return d


def transcribe(
    audio_path: str | Path,
    *,
    model_size: str = MODEL_DEFAULT,
    compute_type: str = COMPUTE_DEFAULT,
    language: str | None = None,
    offset: float = 0.0,
) -> dict:
    """Transcribe with word timestamps. `offset` shifts times into VOD time."""
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device="cpu", compute_type=compute_type)
    segments, info = model.transcribe(
        str(audio_path),
        word_timestamps=True,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 300},
        language=language,
    )

    utterances: list[Utterance] = []
    for seg in segments:
        words = [
            Word(round(w.start + offset, 3), round(w.end + offset, 3), w.word.strip(), round(w.probability, 3))
            for w in (seg.words or [])
        ]
        utterances.append(
            Utterance(round(seg.start + offset, 3), round(seg.end + offset, 3), seg.text.strip(), words)
        )

    return {
        "language": info.language,
        "language_probability": round(info.language_probability, 3),
        "duration": round(info.duration, 3),
        "offset": offset,
        "utterances": [u.as_dict() for u in utterances],
    }


def word_boundaries(tr: dict) -> list[float]:
    """Every legal cut point for a take clip."""
    out: list[float] = []
    for u in tr["utterances"]:
        for w in u["words"]:
            out.append(round(float(w["start"]), 3))
            out.append(round(float(w["end"]), 3))
    return sorted(set(out))


def speech_gaps(tr: dict, *, threshold_ms: float = 350.0) -> list[tuple[float, float]]:
    """Inter-word gaps longer than the threshold — the cut list for a take clip."""
    thr = threshold_ms / 1000.0
    flat: list[dict] = [w for u in tr["utterances"] for w in u["words"]]
    gaps = []
    for a, b in zip(flat, flat[1:]):
        gap = float(b["start"]) - float(a["end"])
        if gap > thr:
            gaps.append((round(float(a["end"]), 3), round(float(b["start"]), 3)))
    return gaps


def has_speech(tr: dict) -> bool:
    return any(u["words"] for u in tr["utterances"])


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="word-level transcription")
    ap.add_argument("audio")
    ap.add_argument("-o", "--out", default="-")
    ap.add_argument("--model", default=MODEL_DEFAULT)
    ap.add_argument("--language")
    ap.add_argument("--offset", type=float, default=0.0)
    a = ap.parse_args()

    tr = transcribe(a.audio, model_size=a.model, language=a.language, offset=a.offset)
    blob = json.dumps(tr, indent=2)
    if a.out == "-":
        print(blob)
    else:
        Path(a.out).write_text(blob)
        print(f"{len(tr['utterances'])} utterances, "
              f"{sum(len(u['words']) for u in tr['utterances'])} words -> {a.out}")
