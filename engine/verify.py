"""Verification pass: check ONE finished clip against the boundary rules.

ADVISORY, NOT A GATE. Measured twice against six clips George graded:

  strict framing    4/6 — caught clip 6 with the exact right fix, but
                    false-positived clips 1 and 4 which he accepted
  conservative      4/6 — no false positives, but MISSED clips 3 and 6

Same model, same data, verdicts flipped on framing alone. Two of the three
fault types are findable in text; one is not:

  missing prompt      textually detectable (strict framing found it, -11s fix)
  bleeds to new topic textually detectable (conservative framing found it)
  abrupt delivery     NOT textually detectable. Clip 3 reads as a complete
                      sentence and only sounds cut off. The fault is prosodic.

So use this to FLAG, never to reject. A human still decides boundaries.

Separate from tier3.judge() on purpose. During generation the model carries a
dozen constraints at once and the boundary rules got crowded out — measured,
they applied to 1 of 3 clips George flagged. This asks three narrow questions
about a decision already made, which is a much easier job.

It returns corrections, not just verdicts. A verifier that says "the out-point
is wrong" without saying where it should be has moved the problem, not solved it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict

MODEL_DEFAULT = "claude-sonnet-5-5"

SYSTEM = """You are checking ONE already-cut clip from a stream transcript.
Three questions only. Be strict — a clip that fails any of them is unusable.

1. ENDS MID-SENTENCE?
   Look at the last line inside the clip. Does the thought finish, or does it
   stop partway ("...you can't just")? Trailing off mid-clause is a FAIL.
   If it fails, give the timestamp where the sentence actually completes.

2. MISSING ITS PROMPT?
   If the first line inside the clip is a RESPONSE — answering a question,
   reacting to something someone said, continuing from a cue — then the thing
   it responds to must be inside the clip. That cue is often a statement, not a
   question. If it is missing, FAIL and give the timestamp of the cue.

3. UNEXPLAINED REFERENT?
   Could someone who started watching at the in-point tell who and what is
   being discussed? If it opens mid-comparison, or on a name or "they"/"he"
   with no antecedent inside the clip, FAIL and give an earlier timestamp that
   introduces the subject.

Be conservative. A clip that is merely IMPROVABLE is a pass. Fail it only
when a viewer would notice something is broken: a sentence chopped mid-clause,
a reply with no visible cue, a subject that is never named. Natural speech
restarts, self-corrections and a last line that gestures at the next topic are
all normal and are NOT failures.

Timestamps you suggest MUST appear in the transcript. Reply with ONLY:
{"ends_mid_sentence": bool, "fix_out": number|null,
 "missing_prompt": bool, "fix_in": number|null,
 "unexplained_referent": bool, "fix_in_referent": number|null,
 "verdict": "pass|fail", "note": str}"""


@dataclass
class Check:
    verdict: str
    ends_mid_sentence: bool = False
    missing_prompt: bool = False
    unexplained_referent: bool = False
    fix_in: float | None = None
    fix_out: float | None = None
    note: str = ""
    error: str = ""

    @property
    def failed(self) -> bool:
        return self.verdict == "fail"

    def as_dict(self) -> dict:
        return asdict(self)


def _snap(t, starts, tol=2.0):
    if t is None:
        return None
    near = min(starts, key=lambda s: abs(s - float(t)))
    return near if abs(near - float(t)) <= tol else None


def check(utterances: list[dict], t_in: float, t_out: float, *,
          model: str = MODEL_DEFAULT, client=None, pad: float = 45.0) -> Check:
    import anthropic
    from engine.tier3 import _api_key

    client = client or anthropic.Anthropic(api_key=_api_key())
    window = [u for u in utterances if t_in - pad <= float(u["start"]) <= t_out + pad]
    if not window:
        return Check("fail", error="no transcript around the clip")

    lines = []
    for u in window:
        t = float(u["start"])
        mark = ">>" if t_in - 0.01 <= t <= t_out + 0.01 else "  "
        lines.append(f"{mark} [{t:.1f}] {u['text'].strip()}")
    body = (f"Clip runs {t_in:.1f}s to {t_out:.1f}s. Lines inside it are marked >>.\n"
            f"Lines without >> are context either side and are NOT in the clip.\n\n"
            + "\n".join(lines))

    msg = client.messages.create(model=model, max_tokens=2000, system=SYSTEM,
                                 messages=[{"role": "user", "content": body}])
    raw = "".join(b.text for b in msg.content if b.type == "text").strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    d = None
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        # The model sometimes reasons in prose first. Take the last JSON object.
        for m in reversed(list(re.finditer(r"\{[^{}]*\}", raw, re.S))):
            try:
                d = json.loads(m.group(0))
                break
            except json.JSONDecodeError:
                continue
    if d is None:
        # Fail OPEN. Defaulting to "fail" turns every parse error into a false
        # positive, which is exactly what happened on clips 3 and 5.
        return Check("pass", error=f"could not parse ({msg.stop_reason}) — not checked")

    starts = [float(u["start"]) for u in window]
    fix_in = _snap(d.get("fix_in") or d.get("fix_in_referent"), starts)
    fix_out = _snap(d.get("fix_out"), starts)
    return Check(
        verdict=d.get("verdict", "fail"),
        ends_mid_sentence=bool(d.get("ends_mid_sentence")),
        missing_prompt=bool(d.get("missing_prompt")),
        unexplained_referent=bool(d.get("unexplained_referent")),
        fix_in=fix_in, fix_out=fix_out, note=d.get("note", ""),
    )
