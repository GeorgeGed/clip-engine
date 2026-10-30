"""Mechanical enforcement of the boundary rules.

The Tier 3 prompt ASKS for these. Measured on the three clips George flagged,
it applied one of three. Stating a rule in a prompt is not enforcing it — the
same lesson gates.py exists for. So the checkable parts get checked here.

Whisper only punctuates about half its utterances on fast unbroken speech, so a
punctuation test alone mis-fires. These functions report what they can verify
and say plainly when they cannot, rather than silently passing.
"""

from __future__ import annotations

TERMINAL = (".", "!", "?", '."', '!"', '?"')

# Measured on 50 clips from FNS VOD 2905408276, leading silence sorted:
# 30 clips open on speech (0.00s); 14 cluster at 0.24-0.63s, median 0.42s —
# the natural breath before a first word; then a 1.24s gap; then 6 clips at
# 1.87s and above, which is dead air. The gap is the threshold, not a guess.
# An earlier 0.35s guess flagged 13 clips, 7 of them with normal pre-roll.
LEAD_SILENCE_DEFECT_S = 1.0

# Where to land when walking an in-point forward. Inside the measured natural
# band, and far enough off the word onset to survive detector jitter.
SPEECH_PREROLL_S = 0.3


def utt_at(utterances: list[dict], t: float) -> dict | None:
    ins = [u for u in utterances if float(u["start"]) <= t + 0.01]
    return ins[-1] if ins else None


def check_sentence_end(utterances: list[dict], out_point: float) -> tuple[bool | None, str]:
    """Did the clip stop on a finished sentence? None = cannot tell."""
    u = utt_at(utterances, out_point)
    if u is None:
        return None, "no utterance at the out-point"
    txt = u["text"].rstrip()
    if txt.endswith(TERMINAL):
        return True, "ends on a completed sentence"
    # No punctuation: fall back to whether the NEXT utterance continues the thought.
    nxt = next((x for x in utterances if float(x["start"]) > float(u["start"])), None)
    if nxt is None:
        return True, "end of transcript"
    first = nxt["text"].strip().split(" ")[0].lower().strip(",.")
    CONTINUERS = {"and","but","so","because","which","that","who","to","of","for",
                  "like","then","or","if","when","where","with","just","you","he",
                  "it","they","we","i"}
    if first in CONTINUERS:
        return False, f"next line opens with {first!r} — the sentence runs on"
    return None, "unpunctuated and inconclusive — needs a human ear"


def check_prompt_included(utterances: list[dict], in_point: float) -> tuple[bool | None, str]:
    """If the line before the in-point is a question, the clip should include it."""
    prev = [u for u in utterances if float(u["start"]) < in_point - 0.01]
    if not prev:
        return True, "nothing precedes the in-point"
    p = prev[-1]["text"].rstrip()
    if p.endswith("?"):
        return False, f"the line before the in-point is a question — include it: {p[-60:]!r}"
    QUESTIONY = ("do you think", "what do you", "how do you", "would you",
                 "is it", "are they", "who ", "why ", "what about")
    low = p.lower()
    if any(q in low for q in QUESTIONY):
        return None, f"the preceding line may be a prompt: {p[-60:]!r}"
    return True, "no prompt immediately before the in-point"


def audit(utterances: list[dict], in_point: float, out_point: float) -> dict:
    ok_end, why_end = check_sentence_end(utterances, out_point)
    ok_in, why_in = check_prompt_included(utterances, in_point)
    return {
        "out_point_ok": ok_end, "out_point_note": why_end,
        "in_point_ok": ok_in, "in_point_note": why_in,
        "clean": ok_end is not False and ok_in is not False,
    }

def walk_in_point_to_speech(
    in_point: float,
    lead_silence: float,
    *,
    preroll: float = SPEECH_PREROLL_S,
    threshold: float = LEAD_SILENCE_DEFECT_S,
) -> tuple[float, str]:
    """Move an in-point forward past dead air, leaving `preroll` before speech.

    `lead_silence` is measured from the cut file (see `qc.leading_silence`).
    Returns the in-point to use and why. Leaves the in-point alone when the
    silence is within the natural band — a 0.4s breath before the first word is
    correct, and trimming it clips the onset.

    Only ever moves FORWARD, so it cannot pull in speech the clip did not
    already contain. That keeps it safe against the one-narrative rule: no new
    topic can appear at the front.
    """
    if lead_silence <= 0:
        return in_point, "opens on speech, unchanged"
    if lead_silence < threshold:
        return in_point, (f"opens on {lead_silence:.2f}s, inside the natural "
                          f"{threshold}s band, unchanged")
    shift = lead_silence - preroll
    if shift <= 0:
        return in_point, f"opens on {lead_silence:.2f}s, shorter than the preroll"
    return round(in_point + shift, 3), (
        f"walked +{shift:.2f}s past {lead_silence:.2f}s of dead air, "
        f"leaving {preroll:.2f}s before speech")


def speech_near(utterances: list[dict], t: float, *, window: float = 1.5) -> dict | None:
    """The first utterance starting within `window` after `t`, if any.

    Cross-check for a walked in-point. `silencedetect` fires on any audio above
    the floor, so without this a keyboard clack or a game sound would pass as
    speech and the in-point would land on it.
    """
    for u in sorted(utterances, key=lambda u: float(u["start"])):
        s = float(u["start"])
        if t - 0.35 <= s <= t + window:
            return u
    return None
