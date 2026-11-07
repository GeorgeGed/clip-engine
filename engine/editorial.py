"""The judging pass, which `batch.py` has always read and nothing ever wrote.

`cmd_specs` reads `editorial.json` for each clip's hook, in-point and verdict,
and its own log says the file is one "which a judging pass or a human writes".
No such pass existed in the repo. The ten entries this VOD has were written by
hand in chat, which is why the other seventeen buildable clips reached the UI
with no title and were shown by their `subject` line instead — a description
of the clip rather than a name for it.

WHAT IT DECIDES, and why each field is here rather than guessed downstream:

* `hook` — the title. Burned on screen and used for the delivered filename, so
  it is the one piece of text a viewer reads before anything else.
* `in_point` — where the clip starts. Rules 2 and 3 in AGENTS.md: a response
  begins at the question, and a clip must explain itself to someone who
  arrived at that second.
* `one_narrative` / `verdict` — George's first rule. A region usually holds
  two or three topics and a clip may only hold one.
* `topic` — what `cmd_specs` dedups on, so two clips arguing the same thing
  do not both ship.

THE HOOK IS HIS CLAIM, COMPRESSED — NEVER A PHRASE WE INVENTED. This file's
standing rule is that nothing on screen is a sentence nobody said. The
existing hand-written hooks show the shape: "FNS: STOP COMPLAINING ABOUT
UNPAID MONTHS", "FNS ON WHY THE NEW SYSTEM BEATS FRANCHISE" — the speaker,
then his own argument in his own words, about forty characters so it sets on
two lines.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from pathlib import Path

from engine.tier3 import MODEL_DEFAULT, _api_key

MAX_HOOK = 46          # two lines of ALL CAPS at the reference title size
WORKERS = 6            # the API is the bottleneck, not us

SYSTEM = """You are the editor of a VALORANT esports clip desk. You are given
one candidate clip's transcript and you decide whether it can ship, where it
starts, and what it is called.

Return ONE json object, no prose, no code fence:

{"verdict":"ship"|"drop",
 "hook":"<THE TITLE, ALL CAPS, <=46 CHARACTERS>",
 "topic":"<three or four lowercase words naming the argument>",
 "in_point":<seconds into the clip where it should start, a number>,
 "one_narrative":true|false,
 "explains_itself":true|false,
 "why":"<two short sentences, UNDER 200 CHARACTERS: what it argues, why it starts there>"}

THE HOOK IS THE SPEAKER'S OWN CLAIM, COMPRESSED. Never a phrase he did not
say the substance of, never a question, never clickbait about something the
clip does not contain. Use his words where you can. Open with the speaker's
handle, as "FNS: ..." for a claim or "FNS ON ..." for a subject. ALL CAPS, at
most 46 characters including the handle, because it is burned on screen over
two lines. Examples of the right register, from clips already shipped:
  FNS: STOP COMPLAINING ABOUT UNPAID MONTHS
  FNS ON WHY THE NEW SYSTEM BEATS FRANCHISE
  FNS: WINNING TEAMS HAVE ISSUES TOO

ONE CLIP IS ONE ARGUMENT. If the transcript turns from one subject to another,
that pivot is a boundary: set in_point after it and title the clip by what
follows, or return "drop" if neither half can stand alone. The test: if
describing it needs the words "and then he talks about", it is two clips.

IT MUST EXPLAIN ITSELF. Everyone and everything named has to be identifiable
from inside the clip. If it opens mid-thought, on "as I was saying", or on a
pronoun whose referent was in the part you cut off, move in_point back to
where the setup actually starts, or drop it.

START WHERE THE ARGUMENT STARTS. If the clip is an answer, begin at the
question. in_point is in seconds from the beginning of THIS transcript, not
the stream. 0.0 is correct whenever the material already begins at the top.

Be willing to drop. A clip that is two arguments, or that cannot be followed
by someone who joined at the in-point, is not worth making."""


@dataclass
class Entry:
    verdict: str
    hook: str
    topic: str
    in_point: float
    one_narrative: bool
    explains_itself: bool
    why: str


def _lines(words: dict, limit: int = 240) -> str:
    """The clip as [start] text, which is what the model needs to pick an
    in-point. Utterances, not words: whisper's VAD merges them here and the
    merged block is still the only phrase-level signal there is."""
    out = []
    for u in words.get("utterances", [])[:limit]:
        t = (u.get("text") or "").strip()
        if t:
            out.append(f'[{float(u["start"]):.1f}] {t}')
    return "\n".join(out)


def _clean_hook(h: str, handle: str = "") -> str:
    """Upper-case, collapse whitespace, strip quotes, pin the speaker's handle,
    and keep it short enough to set on two lines.

    THE HANDLE IS PINNED BECAUSE THE MODEL INVENTED ONE. Clip 40 came back as
    "VAL: I NEVER PLANNED ON COACHING" — a speaker prefix nobody uses, on a
    desk whose oldest rule is never to guess a speaker. The channel is known,
    so it is not the model's to choose.

    Truncation cuts at a word boundary: a hook chopped mid-word is a phrase
    nobody said, burned on screen.
    """
    # CORRECT HANDLES BEFORE UPPERCASING, because the aliases are matched in
    # ordinary case. The title is burned on screen like any caption, and the
    # editorial pass inherits whisper's spelling from the transcript it
    # reads — clip 32 came back as "FNS: IT'S NOT AS BAD FOR VALEN AS YOU
    # THINK", where valen is valyn, Jacob Batio of G2.
    from engine import handles                           # noqa: PLC0415
    h = handles.fix(re.sub(r"\s+", " ", (h or "").strip().strip('"\''))).upper()
    if handle:
        H = handle.upper()
        # Drop whatever prefix it chose, then put the real one back.
        h = re.sub(r"^[A-Z0-9_]{2,12}\s*(?::|\bON\b)\s*", "", h).strip(" :")
        h = f"{H}: {h}" if h else H
    if len(h) <= MAX_HOOK:
        return h
    cut = h[:MAX_HOOK].rsplit(" ", 1)[0]
    return cut.rstrip(" ,.;:-")


def judge_clip(words: dict, *, subject: str = "", claim: str = "",
               handle: str = "", model: str = MODEL_DEFAULT,
               client=None) -> Entry | None:
    """One clip in, one editorial entry out. None when there is nothing to read
    or the reply will not parse — the caller logs it and leaves the clip
    without an entry rather than inventing one."""
    import anthropic

    body = _lines(words)
    if not body:
        return None
    client = client or anthropic.Anthropic(api_key=_api_key())
    # 1200 TRUNCATED REAL REPLIES. `tier3.py` records this exact failure —
    # "a low max_tokens silently cut 24 of 39 regions on the first full run
    # and every one was reported as unparseable; they were valid JSON, just
    # chopped" — and this pass reproduced it on its first clip, cut off
    # mid-sentence inside `why`. The reply is small; the ceiling is not the
    # place to economise.
    msg = client.messages.create(
        model=model, max_tokens=2000, system=SYSTEM,
        messages=[{"role": "user", "content":
                   (f"Ranked as: {subject}\n"
                    f"Its claim: {claim}\n\n"
                    f"Transcript of the candidate clip:\n\n{body}")}],
    )
    raw = "".join(b.text for b in msg.content if b.type == "text").strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    # TAKE THE OBJECT OUT OF WHATEVER IT CAME WRAPPED IN. One clip in
    # seventeen came back with the JSON intact but something around it, and
    # requiring the whole reply to parse threw away a perfectly good answer.
    if not raw.startswith("{"):
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            raw = m.group(0)
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        # Say WHICH failure it was. "Unparseable" covers both a malformed
        # reply and a truncated one, and they need opposite fixes.
        raise ValueError(
            "reply truncated (stop_reason=max_tokens) — raise max_tokens"
            if msg.stop_reason == "max_tokens"
            else f"malformed reply: {raw[:140]}") from None
    hook = _clean_hook(d.get("hook", ""), handle)
    if not hook:
        return None
    return Entry(
        verdict="drop" if str(d.get("verdict")).lower() == "drop" else "ship",
        hook=hook,
        topic=re.sub(r"\s+", " ", str(d.get("topic", "")).strip().lower()),
        in_point=max(0.0, float(d.get("in_point") or 0.0)),
        one_narrative=bool(d.get("one_narrative", True)),
        explains_itself=bool(d.get("explains_itself", True)),
        why=str(d.get("why", "")).strip(),
    )


def judge_many(clips: list[dict], *, handle: str = "",
               model: str = MODEL_DEFAULT, on_done=None) -> dict[str, dict]:
    """`clips` is [{n, words, subject, claim}]. Returns {str(n): entry-dict}.

    Threaded because each clip is an independent call and seventeen of them
    one after another is minutes of waiting for no reason.
    """
    import anthropic
    client = anthropic.Anthropic(api_key=_api_key())
    out: dict[str, dict] = {}

    def one(c):
        try:
            e = judge_clip(c["words"], subject=c.get("subject", ""),
                           claim=c.get("claim", ""), handle=handle,
                           model=model, client=client)
        except Exception as exc:                        # noqa: BLE001
            e, err = None, f"{type(exc).__name__}: {exc}"
        else:
            err = None if e else "unparseable or empty reply"
        if on_done:
            on_done(c["n"], e, err)
        return c["n"], e

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for n, e in pool.map(one, clips):
            if e:
                out[str(n)] = asdict(e)
    return out
