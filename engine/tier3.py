"""Tier 3: a model reads one region's transcript and locates the clip in it.

Tiers 0-2 are cheap and run over everything. This runs only on a region a
cheaper tier already flagged, because it costs real money per call.

It exists because the regex approach measurably failed. Across 12 regions of
FNS VOD 2905408276, `candidates.find_in_point` found no marker in 9 and threw
false positives in the other 3. Where a clip starts is a judgement about
meaning — a topic opening, a claim beginning — and there is no acoustic or
lexical feature that reliably marks it.

Returns strict JSON, validated against the transcript: an in-point that does
not match an utterance boundary inside the region is rejected rather than
trusted, so the model cannot invent a timestamp.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
from dataclasses import dataclass, asdict

MODEL_DEFAULT = "claude-sonnet-5-5"
KEY_SOURCES = ["~/valorant-quote-desk/.env", "~/quotes-pipeline/.env"]

SYSTEM = """You select clips from esports streams. You are given ONE region of a \
stream transcript with timestamps, already flagged as interesting by a cheaper \
detector. Decide whether a clip lives in it and exactly where it starts.

GENRES
- take: a claim delivered fast. The value is the claim.
- receipts: a case argued with evidence, where silence carries the proof.
- frag: gameplay tension then release.
- none: nothing clippable here.

THE IN-POINT IS THE HARD PART
Start at the first word of the SETUP, never at the claim. A claim without its \
setup is unintelligible. Prefer the moment a NEW topic opens — someone \
announcing a disclosure, answering a chat question, changing subject. Do not \
start mid-thought, and do not start at the loudest point: loudness marks where \
someone got excited, not where the moment began.

MIN_LINES
A take needs setup, claim AND consequence. If the region cannot carry all \
three, it is not a clip — return genre "none".

WHAT IS WORTH CLIPPING
Controversy, a named judgement about a player or org, roster and transfer news, \
a reveal, a strong reaction, a real exchange with chat. Not: logistics, \
scheduling, generic explanation, thinking aloud.

CONSTRAINTS
- in_point and out_point MUST be timestamps that appear in the supplied \
utterances. Never invent one.
- Quote setup/claim/consequence verbatim from the transcript, briefly.
- Names from speech-to-text are often wrong. List any in names_to_verify.
- If more than one person speaks, say so in risks.

Reply with ONLY a JSON object:
{"has_clip": bool, "genre": "take|receipts|frag|none", "in_point": number, \
"out_point": number, "setup": str, "claim": str, "consequence": str, \
"subject": str, "strength": number 0..1, "why": str, \
"names_to_verify": [str], "risks": [str]}"""


def _api_key() -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    for src in KEY_SOURCES:
        try:
            txt = pathlib.Path(src).expanduser().read_text(errors="replace")
        except Exception:
            continue
        m = re.search(r'^\s*(?:export\s+)?ANTHROPIC_API_KEY\s*=\s*["\']?([^"\'\n]+)',
                      txt, re.M)
        if m:
            return m.group(1).strip()
    raise RuntimeError("no ANTHROPIC_API_KEY in env or " + ", ".join(KEY_SOURCES))


@dataclass
class Verdict:
    has_clip: bool
    genre: str
    in_point: float | None
    out_point: float | None
    setup: str = ""
    claim: str = ""
    consequence: str = ""
    subject: str = ""
    strength: float = 0.0
    why: str = ""
    names_to_verify: list[str] | None = None
    risks: list[str] | None = None
    validation: list[str] | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _snap(t: float | None, starts: list[float], tol: float = 1.5) -> tuple[float | None, bool]:
    """Snap a model timestamp to a real utterance boundary, or reject it."""
    if t is None:
        return None, False
    near = min(starts, key=lambda s: abs(s - float(t)))
    return (near, True) if abs(near - float(t)) <= tol else (float(t), False)


def judge(utterances: list[dict], region: tuple[float, float], *,
          model: str = MODEL_DEFAULT, client=None, pad: float = 60.0) -> Verdict:
    """`pad` widens the transcript shown to the model beyond the flagged region.

    Regions come from acoustic clustering and do not respect where a topic
    starts or ends. Unpadded, region 0:45:43-0:48:03 of FNS VOD 2905408276 cut
    the coaching reveal in half, and the model correctly trimmed before it —
    producing a defensible clip of the wrong moment. The region is a POINTER,
    not a boundary.
    """
    import anthropic

    client = client or anthropic.Anthropic(api_key=_api_key())
    lo, hi = region
    inside = [u for u in utterances if lo - pad <= float(u["start"]) <= hi + pad]
    if not inside:
        return Verdict(False, "none", None, None, why="no transcript in region")

    lines = "\n".join(f'[{float(u["start"]):.1f}] {u["text"].strip()}' for u in inside)
    msg = client.messages.create(
        model=model, max_tokens=1200, system=SYSTEM,
        messages=[{"role": "user", "content":
                   f"A detector flagged {lo:.1f}s to {hi:.1f}s as interesting, but that "
                   f"boundary is acoustic and may cut a topic in half. Transcript below "
                   f"runs {inside[0]['start']:.1f}s to {inside[-1]['start']:.1f}s. Start "
                   f"and end the clip wherever the material actually begins and ends, "
                   f"inside or outside the flagged window.\n\n{lines}"}],
    )
    raw = "".join(b.text for b in msg.content if b.type == "text").strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        return Verdict(False, "none", None, None, why=f"unparseable reply: {raw[:120]}")

    starts = [float(u["start"]) for u in inside]
    notes: list[str] = []
    in_t, ok_in = _snap(d.get("in_point"), starts)
    out_t, _ = _snap(d.get("out_point"), starts + [hi])
    if not ok_in:
        notes.append(f"in_point {d.get('in_point')} matches no utterance — not trusted")
    if in_t is not None and not (lo - pad - 2 <= in_t <= hi + pad + 2):
        notes.append("in_point outside the padded window")
    if out_t is not None and in_t is not None and out_t <= in_t:
        notes.append("out_point not after in_point")

    return Verdict(
        has_clip=bool(d.get("has_clip")) and not notes,
        genre=d.get("genre", "none"),
        in_point=in_t, out_point=out_t,
        setup=d.get("setup", ""), claim=d.get("claim", ""),
        consequence=d.get("consequence", ""), subject=d.get("subject", ""),
        strength=float(d.get("strength") or 0.0),
        why=d.get("why", ""),
        names_to_verify=d.get("names_to_verify") or [],
        risks=d.get("risks") or [],
        validation=notes,
    )


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Tier 3: locate the clip in a region")
    ap.add_argument("transcript", help="JSON list of {start, text}")
    ap.add_argument("--start", type=float, required=True)
    ap.add_argument("--end", type=float, required=True)
    ap.add_argument("--model", default=MODEL_DEFAULT)
    a = ap.parse_args()
    utt = json.loads(pathlib.Path(a.transcript).read_text())
    print(json.dumps(judge(utt, (a.start, a.end), model=a.model).as_dict(), indent=2))
