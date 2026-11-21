"""What is in a clip, measured, so the planner plans from facts.

The reference workflow George sent (spec.md, section 1) puts one rule before
any cut: *"before you cut anything, read the clip: the facecam, the game, the
clutter, every word and who said it. plan from these facts."* This is that
read, with no model in it.

THE SENTENCE IS THE UNIT. The planner never sees a timestamp it could copy
wrongly: it sees numbered sentences and names beats by sentence id, and code
turns ids back into times. That makes "never invent a timestamp" structural
rather than a validation step. A sentence ends on terminal punctuation or on a
pause of at least GAP_S, because whisper punctuates only 38% of utterances
(AGENTS.md) and its VAD merges utterances, so neither is a boundary on its own.

WHO SAID IT. `resolve_captions.background` already separates the streamer
from quieter voices by level (#14). Where there is audio to measure, a
sentence that is mostly background words is `other`; where there is not,
there is no label at all. Never a guess.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

GAP_S = 0.5          # a pause this long ends a sentence
LONG_S = 9.0         # a longer one splits at its widest pause
MIN_PART_S = 2.0     # ...as long as neither side is shorter than this
QUIET_S = 1.0        # a gap between words this long is a quiet stretch
OTHER_SHARE = 0.6    # a sentence this much background is someone else's
ENDERS = ".?!"


def slice_words(utterances: list[dict], a: float, b: float) -> list[dict]:
    """The utterances inside [a, b] of the VOD, rebased so `a` is 0."""
    out = []
    for u in utterances:
        ws = [dict(w, start=round(w["start"] - a, 3), end=round(w["end"] - a, 3))
              for w in u["words"] if w["start"] >= a and w["end"] <= b]
        if ws:
            out.append({"start": ws[0]["start"], "end": ws[-1]["end"],
                        "text": " ".join(w["text"] for w in ws), "words": ws})
    return out


def _flat(utterances: list[dict]) -> list[dict]:
    return [w for u in utterances for w in u["words"] if w["text"].strip()]


def _split_long(words: list[dict], i: int, j: int, long: float) -> list[tuple[int, int]]:
    """Split words[i..j] at its widest pause until every part is under `long`.

    FNS talks at 175+ wpm with no punctuation from large-v3, so one "sentence"
    measured 47s on 2885323336 clip 5. The widest pause inside a run is the
    likeliest phrase boundary. Each side keeps at least 30% of the run (and
    MIN_PART_S), or a run with no real pauses shatters into 2s slivers."""
    span = float(words[j]["end"]) - float(words[i]["start"])
    if span <= long:
        return [(i, j)]
    floor = max(MIN_PART_S, 0.3 * span)
    best, k = -1.0, None
    for m in range(i, j):
        left = float(words[m]["end"]) - float(words[i]["start"])
        right = float(words[j]["end"]) - float(words[m + 1]["start"])
        g = float(words[m + 1]["start"]) - float(words[m]["end"])
        if left >= floor and right >= floor and g > best:
            best, k = g, m
    if k is None:
        return [(i, j)]
    return _split_long(words, i, k, long) + _split_long(words, k + 1, j, long)


def sentences(utterances: list[dict], *, gap: float = GAP_S,
              long: float = LONG_S) -> list[dict]:
    """Numbered sentences `s1..sN` with start, end, text and word range."""
    words = _flat(utterances)
    runs: list[tuple[int, int]] = []
    first = 0
    for i, w in enumerate(words):
        nxt = words[i + 1] if i + 1 < len(words) else None
        pause = (float(nxt["start"]) - float(w["end"])) if nxt else gap
        if nxt is None or w["text"].strip()[-1] in ENDERS or pause >= gap:
            runs += _split_long(words, first, i, long)
            first = i + 1
    out = []
    for i, j in runs:
        ws = words[i:j + 1]
        out.append({"id": f"s{len(out) + 1}", "start": round(float(ws[0]["start"]), 3),
                    "end": round(float(ws[-1]["end"]), 3),
                    "text": " ".join(x["text"].strip() for x in ws),
                    "first": i, "last": j})
    return out


def quiet(utterances: list[dict], *, min_s: float = QUIET_S) -> list[list[float]]:
    """Gaps between words of at least `min_s`: silence or a mute."""
    words = _flat(utterances)
    return [[round(float(a["end"]), 2), round(float(b["start"]), 2)]
            for a, b in zip(words, words[1:])
            if float(b["start"]) - float(a["end"]) >= min_s]


def levels(src: Path, a: float, b: float):
    """Loudness in dB every 10 ms over [a, b] of `src`, as make_clip measures it."""
    import numpy as np
    pcm = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{a:.3f}",
                          "-t", f"{b - a:.3f}", "-i", str(src), "-ac", "1", "-ar", "16000",
                          "-f", "f32le", "-"], capture_output=True).stdout
    x = np.frombuffer(pcm, dtype="<f4")
    if not len(x):
        return None
    ms = np.convolve(x * x, np.ones(400) / 400, "same")[::160]
    return 10 * np.log10(ms + 1e-12)


def speakers(sents: list[dict], utterances: list[dict], db) -> None:
    """Label each sentence `streamer` or `other` in place, when `db` exists."""
    if db is None:
        return
    from engine.resolve_captions import background
    bg = background(_flat(utterances), db, 0.01)
    for s in sents:
        part = bg[s["first"]:s["last"] + 1]
        s["speaker"] = "other" if sum(part) >= OTHER_SHARE * len(part) else "streamer"


def chat_near(spikes: list[dict], a: float, b: float) -> list[dict]:
    """Chat spikes peaking inside [a, b] of the VOD, in clip seconds."""
    out = []
    for s in spikes:
        c = s.get("chat") or {}
        t = c.get("t")
        if t is None or not a - 2 <= t <= b + 5:
            continue
        out.append({"t": round(max(0.0, t - a), 1), "count": c.get("count"),
                    "baseline": c.get("baseline"), "laugh": c.get("laugh"),
                    "hype": c.get("hype")})
    return out


def build(clip: dict, utterances: list[dict], *, streamer: str,
          spikes: list[dict] | None = None, db=None) -> dict:
    """The facts sheet for one ranked clip. `utterances` are the VOD
    transcript's; `db` is `levels()` over the clip's own span, or None."""
    a, b = float(clip["in_point"]), float(clip["out_point"])
    us = slice_words(utterances, a, b)
    sents = sentences(us)
    speakers(sents, us, db)
    return {"genre": clip.get("genre", "take"), "duration": round(b - a, 2),
            "streamer": streamer, "subject": clip.get("subject", ""),
            "setup": clip.get("setup", ""), "claim": clip.get("claim", ""),
            "consequence": clip.get("consequence", ""),
            "sentences": [{k: s[k] for k in ("id", "start", "end", "text", "speaker") if k in s}
                          for s in sents],
            "quiet": quiet(us), "chat": chat_near(spikes or [], a, b)}


def render(f: dict) -> str:
    """The facts as the planner reads them."""
    who = any("speaker" in s for s in f["sentences"])
    lines = [f"STREAMER: {f['streamer']}",
             f"GENRE: {f['genre']}   LENGTH: {f['duration']:.1f}s",
             f"WHAT THE SELECTOR SAW: {f['subject']}",
             f"  setup: {f['setup']}", f"  claim: {f['claim']}",
             f"  consequence: {f['consequence']}", "",
             "SENTENCES ([start-end] in clip seconds"
             + (", then who said it: him = the streamer, other = a quieter voice "
                "such as a caster, co-host or the game" if who else "") + "):"]
    for s in f["sentences"]:
        tag = {"streamer": " him  ", "other": " other"}.get(s.get("speaker"), "")
        lines.append(f"{s['id']:>4} [{s['start']:6.1f}-{s['end']:6.1f}]{tag}  {s['text']}")
    if f["quiet"]:
        lines += ["", "QUIET STRETCHES (no words; silence or a muted stretch): "
                  + ", ".join(f"{x:.1f}-{y:.1f}" for x, y in f["quiet"])]
    for c in f["chat"]:
        lines += ["", f"CHAT spiked at {c['t']:.0f}s: {c['count']} messages in 10s against a "
                  f"usual {c['baseline']}, {round(100 * (c['laugh'] or 0))}% laughing, "
                  f"{round(100 * (c['hype'] or 0))}% hyping a play. Chat reacts a few "
                  "seconds after the moment."]
    return "\n".join(lines)
