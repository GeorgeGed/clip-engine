"""Fresh eyes on a finished clip: three critics, then a judge.

This runs AFTER the code checks. `engine.gates` judged the plan and
`engine.qc` read the file back, so everything a measurement can settle is
already settled. What is left is what only a viewer sees: does the opening
hook, does it explain itself, can you read the captions, is the face in the
top pane.

THE CRITICS NEVER SEE THE PLAN. They get frames of the render and the words
spoken in it, nothing of Tier 3's subject, claim or reasoning. A critic who
knows what the clip is meant to be about reads that intent into it; one who
does not has only what a viewer has.

THE JUDGE CAN ONLY ASK FOR WHAT THE EDITOR CAN DO. Its fixes are a closed set
(`FIXES`), each applied by `apply_fixes` against word timestamps, so a
verdict can never invent a timestamp or cut inside a word. A fault with no
fix in the set is still reported, and the clip ships flagged.
"""

from __future__ import annotations

import base64
import json
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from engine.tier3 import MODEL_DEFAULT
from engine.tighten import Span, remap

MAX_FRAMES = 24
FRAME_EVERY = 2.5        # seconds between sampled frames
FRAME_SIZE = (360, 640)
MIN_CLIP_S = 12.0        # a trim may not leave less than this
MAX_TRIM = 0.5           # nor remove more than this share of the clip at either end
SNAP_S = 3.0             # how far a trim may move to reach a sentence boundary
PAUSE_S = 0.5            # a gap this long between words ends a sentence
PREROLL = 0.3            # the breath kept before a first word (AGENTS.md)
TAIL = 0.25              # kept past a last word's end

HOUSE = """House rules, which are choices and not faults:
- Vertical 1080x1920. Talk clips are two panes: the streamer's facecam on top (about 42%), the game or the document he is reading below.
- Gameplay clips keep the whole 16:9 game with no zoom-ins. His own kill clips have no captions on purpose.
- No music. No zoom punch-ins on talk clips.
- Captions appear a few words at a time near the middle of the frame; the top 150px and bottom 320px are covered by the phone app and must stay clear.
- Only the streamer's own voice is captioned. Casters, broadcast audio, teammates and other quieter voices are deliberately left uncaptioned, so captions are sparse while someone else talks.
- The opening title shows for the first second only.
- Long quiet stretches can be deliberate when the lower pane shows what he is reacting to."""

CRITICS = {
    "story": "You are the STORY critic. Judge the hook (does the first 2 seconds make you stay), the pace "
             "(dead stretches, a slow start), whether it explains itself to someone who joined at the first "
             "frame, whether it is ONE subject, and whether it ends on its payoff rather than mid-sentence or "
             "after the point has passed.",
    "caption": "You are the CAPTION critic. Judge whether the captions are readable at phone size, clear of the "
               "app buttons (top 150px and bottom 320px of 1920), not covering the face or the key part of the "
               "game, and whether the words on screen match the transcript. Also judge the opening title.",
    "tech": "You are the TECH critic. Judge framing (a face actually in the facecam pane, heads cut off, an empty "
            "or black pane, a pane showing the wrong thing), glitches, frozen or black frames, a seam in the wrong "
            "place, and graphics covering the action.",
}

CRITIC_FORMAT = """Reply with JSON only:
{"score": <1-10, 10 = would post as is>,
 "faults": [{"at": <seconds into the clip or null>, "severity": "major" | "minor", "fault": "<one sentence>"}]}
Major means a viewer would scroll away or the clip looks broken. Report only what you can see in these frames or read in this transcript."""

FIXES = """The editor can make exactly these changes, nothing else:
- {"fix": "start_at", "t": <seconds>}  start the clip later, at the start of the sentence that begins near t (trims the front)
- {"fix": "end_at", "t": <seconds>}    end the clip earlier, at the end of the sentence that ends near t (trims the end)
Each trim snaps to the nearest sentence boundary within 3 seconds, may remove at most half the clip, and must leave at least 12 seconds.
Give t as the time the kept sentence starts (start_at) or ENDS (end_at), not the start of what you are removing.
- {"fix": "title", "text": "<new opening title, under 50 characters>"}
Times are seconds into the clip as it plays now, taken from the transcript. The clip cannot be made longer at either end."""

JUDGE = """You are the JUDGE for a short vertical clip cut from a Twitch stream. Three critics watched it without knowing what it was meant to be. Weigh their faults against the frames and transcript yourself: a critic can be wrong, and a house rule is never a fault.

Pass the clip unless it has a MAJOR fault. If it does, return "not_yet" with the smallest set of fixes that removes the major faults. If no available fix addresses a major fault, return "not_yet" with no fixes; it ships flagged with your summary.

%s

%s

Reply with JSON only:
{"verdict": "pass" | "not_yet",
 "summary": "<one or two sentences George can read on the clip card>",
 "faults": ["<each major fault you agree with>"],
 "fixes": [<fix objects>]}"""


def frames(mp4: Path, duration: float) -> list[tuple[float, bytes]]:
    """Evenly spaced JPEGs of the render, with their times."""
    n = max(4, min(MAX_FRAMES, int(duration / FRAME_EVERY)))
    # The opening title holds only the first second (make_clip.TITLE_S), so
    # the first frame is taken inside it or no critic ever sees the hook.
    times = [0.4] + [round((i + 0.5) * duration / n, 2) for i in range(1, n)]
    out = []
    with tempfile.TemporaryDirectory() as d:
        for i, t in enumerate(times):
            p = Path(d) / f"{i:02d}.jpg"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(mp4), "-frames:v", "1",
                            "-vf", f"scale={FRAME_SIZE[0]}:{FRAME_SIZE[1]}", "-q:v", "5", str(p)], check=True)
            out.append((t, p.read_bytes()))
    return out


def to_file(t: float, keeps: list[Span]) -> float:
    """Clip time -> cut-file time: the inverse of tighten.remap."""
    acc = 0.0
    for k in keeps:
        if t < acc + k.length:
            return round(k.start + max(0.0, t - acc), 3)
        acc += k.length
    return keeps[-1].end


def transcript(words: list[dict], keeps: list[Span]) -> str:
    """The words heard in the clip, one utterance a line, in CLIP seconds.
    A word whose onset was cut away is not heard, so it is left out."""
    lines = []
    for u in words:
        ws = [(remap(w["start"], keeps), w) for w in u["words"]]
        ws = [(t, w) for t, w in ws if t is not None]
        if ws:
            end = remap(ws[-1][1]["end"] - 1e-3, keeps) or ws[-1][0]
            lines.append(f"[{ws[0][0]:.1f}-{end:.1f}] " + " ".join(w["text"] for _, w in ws))
    return "\n".join(lines) or "(no speech)"


def _content(fr, text: str) -> list[dict]:
    parts = []
    for t, jpg in fr:
        parts.append({"type": "text", "text": f"t={t:.1f}s"})
        parts.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                  "data": base64.b64encode(jpg).decode()}})
    parts.append({"type": "text", "text": text})
    return parts


def _json(msg) -> dict:
    """The first JSON object in a reply, ignoring prose or a code fence around it."""
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    i = text.find("{")
    if i < 0:
        raise ValueError("no JSON object in the reply")
    return json.JSONDecoder().raw_decode(text[i:])[0]


def _ask(client, model: str, system: str, content: list[dict], max_tokens: int) -> dict:
    """One model call that must come back as JSON; a malformed reply is asked again once."""
    for attempt in (1, 2):
        msg = client.messages.create(model=model, max_tokens=max_tokens, system=system,
                                     messages=[{"role": "user", "content": content}])
        try:
            return _json(msg)
        except ValueError:
            if attempt == 2:
                raise


def review(mp4: Path, words: list[dict], clip: dict, keeps: list[Span], duration: float, *, client,
           model: str = MODEL_DEFAULT) -> dict:
    """Critics, then the judge. clip is the spec's clip dict, words the
    utterances of words/NN.json in cut-file seconds, keeps the spans of the
    cut file the render kept (overlays_NN/keeps.json)."""
    fr = frames(mp4, duration)
    said = transcript(words, keeps)
    facts = (f"Clip length {duration:.1f}s. Opening title: {clip.get('title') or '(none)'}, "
             "shown for the first second only (the first frame). "
             + ("Captions are OFF on this clip on purpose. " if clip.get("captions") is False else "")
             + f"\n\nTranscript (seconds into the clip):\n{said}")

    def critic(item):
        name, brief = item
        return name, _ask(client, model, f"{brief}\n\n{HOUSE}\n\n{CRITIC_FORMAT}", _content(fr, facts), 1500)

    with ThreadPoolExecutor(len(CRITICS)) as ex:
        critiques = dict(ex.map(critic, CRITICS.items()))
    notes = "\n\n".join(f"{k.upper()} critic: {json.dumps(v)}" for k, v in critiques.items())
    verdict = _ask(client, model, JUDGE % (HOUSE, FIXES), _content(fr, facts + "\n\n" + notes), 2000)
    if verdict.get("verdict") not in ("pass", "not_yet"):
        verdict = {"verdict": "not_yet", "summary": "The judge's reply could not be read.", "faults": [],
                   "fixes": []}
    verdict.setdefault("fixes", [])
    verdict["critics"] = critiques
    return verdict


def sentence_ends(words: list[dict]) -> list[int]:
    """Indexes into the flat word list after which a sentence ends: terminal
    punctuation, the end of an utterance, or a pause of PAUSE_S. Whisper
    punctuates only about a third of utterances, so the pause carries most."""
    flat = [(w, i == len(u["words"]) - 1) for u in words for i, w in enumerate(u["words"])]
    return [i for i, (w, last) in enumerate(flat)
            if last or w["text"].rstrip().endswith((".", "?", "!"))
            or (i + 1 < len(flat) and flat[i + 1][0]["start"] - w["end"] >= PAUSE_S)]


def apply_fixes(clip: dict, words: list[dict], fixes: list[dict], keeps: list[Span]) -> tuple[dict, list[str]]:
    """The judge's fixes applied to a copy of the spec's clip dict, snapped to
    word timestamps. Returns the new clip and a line per applied fix; a fix
    that would invent a time, lengthen the clip or leave under MIN_CLIP_S is
    skipped."""
    new = dict(clip)
    a, b = keeps[0].start, keeps[-1].end
    flat = [w for u in words for w in u["words"]]
    ends = sentence_ends(words)
    # a sentence starts on the word after a sentence end, or on the first word
    starts = [0] + [i + 1 for i in ends if i + 1 < len(flat)]
    length = b - a
    done = []
    for f in fixes:
        kind = f.get("fix")
        if kind == "title" and str(f.get("text", "")).strip():
            text = str(f["text"]).strip()[:60]
            new["title"] = text
            kw = new.get("title_keyword")
            if kw and kw.lower() not in text.lower():
                new["title_keyword"] = None
            done.append(f"title -> {text!r}")
            continue
        try:
            t = to_file(float(f["t"]), keeps)
        except (KeyError, TypeError, ValueError):
            continue
        if kind == "start_at":
            w = min((flat[i] for i in starts if a <= flat[i]["start"] <= b and abs(flat[i]["start"] - t) <= SNAP_S),
                    key=lambda w: abs(w["start"] - t), default=None)
            cut = None if w is None else round(max(a, w["start"] - PREROLL), 2)
            end = float(new["out_point"]) if new.get("out_point") is not None else b
            if cut is not None and a + 0.05 < cut <= a + MAX_TRIM * length and end - cut >= MIN_CLIP_S:
                new["in_point"] = cut
                done.append(f"start {a:.2f} -> {cut:.2f} (on {w['text']!r})")
        elif kind == "end_at":
            w = min((flat[i] for i in ends if a <= flat[i]["end"] <= b + 1e-3 and abs(flat[i]["end"] - t) <= SNAP_S),
                    key=lambda w: abs(w["end"] - t), default=None)
            cut = None if w is None else round(min(b, w["end"] + TAIL), 2)
            start = float(new.get("in_point") or a)
            if cut is not None and b - MAX_TRIM * length <= cut < b - 0.05 and cut - start >= MIN_CLIP_S:
                new["out_point"] = cut
                done.append(f"end {b:.2f} -> {cut:.2f} (after {w['text']!r})")
    return new, done
