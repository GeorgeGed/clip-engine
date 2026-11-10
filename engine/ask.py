"""Turn "remove the booms" into a validated spec patch.

George: *"i want to add a feature that allows me to cut a video, then i can
ask the ai 'remove the booms' or cut the end of the video, etc, and then it
will make the changes then and there and re-load the video."*

**THE MODEL NEVER WRITES THE SPEC.** It returns a patch over the same five
reviewable fields the editor drawer exposes — `in_point`, `out_point`,
`booms`, `chat_mode`, `hook` — and that patch goes through `server._clean`,
the identical validator a human's edit goes through, before `write_spec`
merges it. So the worst a bad reply can do is be refused. Everything the
house style owns — captions, exits, punch geometry, sound, palette — is in
code and is not reachable from here by design.

THREE THINGS THIS FILE EXISTS TO GET RIGHT:

1. **TWO CLOCKS, AND THEY ARE EASY TO MIX.** `in_point` and `out_point` are
   SOURCE seconds, positions in the original region file. `booms` are OUTPUT
   seconds, positions in the finished clip. A model asked to "cut the last
   three seconds" will happily subtract three from an out_point measured on
   a different clock, and the result looks plausible and is wrong. Both are
   labelled in the prompt and every transcript line carries both.

2. **NEVER INVENT A TIMESTAMP.** The oldest rule in this project. The
   transcript is supplied with each word's own source and output times, and
   the instruction is to pick one — not to compute one. `make_clip`'s
   `_snap_out_point` and `_snap_in_point` then move it onto a real word
   boundary anyway, so a near-miss is recoverable; a number from nowhere is
   not.

3. **IT MUST BE ABLE TO SAY NO.** "Make the captions bigger" is not
   expressible in these fields, and a model that must return a patch will
   return a bad one. `refused` is a first-class answer and the page shows
   it instead of silently rebuilding something nobody asked for.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from engine.tier3 import MODEL_DEFAULT, _api_key

SYSTEM = """You turn a video editor's spoken instruction into a small JSON
patch over a clip's editable fields. You are not writing the file and
you are not editing the video; you are choosing values.

THE ONLY FIELDS YOU MAY SET
  in_point    SOURCE seconds. Where the cut starts in the original footage.
  out_point   SOURCE seconds, or null to run to the planned end.
  booms       a list of OUTPUT seconds for the bass-hit sound effect.
              []   means no booms at all.
              null means let the pipeline choose them.
              A boom marks a zoom on the facecam, so these are one event:
              setting [] removes the zooms with the sounds. Say so in "why"
              when you set it, because it is more than the words ask for.
  chat_mode   "continuous" (always on), "reactive" (only on chat bursts),
              "off", or null to let the pipeline decide.
  hook        the title burned on screen, in capitals.
  caption_emph  the colour of the EMPHASISED subtitle words, by name, or
              null for the house colour. One of: white, blue, gold,
              vermilion, green, cyan, pink, red, orange, violet, yellow.
  caption_fill  the colour of the ordinary subtitle words, same names.
              Almost always white; change it only if asked directly.
  stories     "auto" to let the pipeline find a news photo card when one
              fits the clip's subject, "off" to show none.

COLOURS ARE NAMES, NOT HEX. Every name above is measured against the
caption's own hard black outline and clears a 4.5:1 floor. If the editor
asks for a specific hex, use the nearest name and say so in "why" — a hex
you pick may be refused for being illegible, and "our brand blue"
(#2E5CFF) is one that IS refused.

TWO CLOCKS. in_point and out_point are SOURCE seconds. booms are OUTPUT
seconds. They are different numbers for the same moment and mixing them
produces a plausible, wrong answer. Every transcript line below gives you
both, as [output | source].

NEVER INVENT A TIMESTAMP. Pick a time that appears in the transcript. Do not
calculate one by adding or subtracting. If the editor says "cut the last
sentence", find where that sentence starts in the transcript and use the
SOURCE time of the word before it.

SAY NO WHEN YOU SHOULD. If the instruction cannot be expressed in those
fields — caption SIZE or position, the facecam framing, music, adding
graphics, how fast it cuts, anything else about how it LOOKS — set
"refused" to a short sentence saying so and what you can change instead.
Do not approximate. An empty patch with a clear refusal is a good answer;
a wrong patch is not. (Caption COLOUR is now settable; caption SIZE is
not.)

Only include fields you are actually changing.

Reply with JSON only:
{"patch": {...}, "why": "one sentence, what you changed and why",
 "refused": null or "one sentence"}"""


@dataclass
class Answer:
    patch: dict = field(default_factory=dict)
    why: str = ""
    refused: str | None = None


def _transcript(words: list[tuple[float, float, float, str]], limit: int = 420) -> str:
    """`[output | source] word`, one per line, both clocks on every line."""
    if len(words) > limit:                      # keep the head and the tail
        head, tail = words[: limit // 2], words[-limit // 2:]
        rows = head + [(-1.0, -1.0, -1.0, "…")] + tail
    else:
        rows = words
    out = []
    for ot, st, _se, text in rows:
        if ot < 0:
            out.append("   …")
            continue
        out.append(f"  [{ot:6.2f} | {st:7.2f}]  {text}")
    return "\n".join(out)


def _state(spec: dict, detail: dict) -> str:
    booms = spec.get("booms")
    if booms is None:
        auto = [b.get("t") for b in (detail.get("booms") or [])]
        bl = (f"not set — the pipeline chose {len(auto)}: "
              + ", ".join(f"{t:.2f}" for t in auto) + " output-seconds"
              ) if auto else "not set — the pipeline chose none"
    elif not booms:
        bl = "[] — explicitly none"
    else:
        bl = ", ".join(f"{float(b):.2f}" for b in booms) + " output-seconds"
    out = spec.get("out_point")
    return "\n".join([
        f"  title       {spec.get('hook') or '(none)'}",
        f"  in_point    {spec.get('in_point')} source-seconds",
        f"  out_point   {out if out is not None else 'null (runs to the planned end)'}",
        f"  booms       {bl}",
        f"  chat_mode   {spec.get('chat_mode') or 'null (the pipeline decides)'}",
        f"  finished    {detail.get('dur')} seconds long, "
        f"{detail.get('splices')} audio splices",
    ])


def interpret(ask: str, *, spec: dict, detail: dict,
              words: list[tuple[float, float, float, str]],
              model: str = MODEL_DEFAULT, client=None) -> Answer:
    """One instruction in, one patch out. Raises ValueError on a bad reply."""
    ask = (ask or "").strip()
    if not ask:
        return Answer(refused="Say what you want changed.")
    import anthropic

    client = client or anthropic.Anthropic(api_key=_api_key())
    msg = client.messages.create(
        model=model, max_tokens=1500, system=SYSTEM,
        messages=[{"role": "user", "content": (
            f"THE CLIP AS IT STANDS\n{_state(spec, detail)}\n\n"
            f"TRANSCRIPT  [output | source]  word\n"
            f"{_transcript(words)}\n\n"
            f"THE EDITOR SAYS:\n{ask}")}],
    )
    raw = "".join(b.text for b in msg.content if b.type == "text").strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    if not raw.startswith("{"):
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            raw = m.group(0)
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        # Which failure it was, because they need opposite fixes — the same
        # distinction `tier3` and `editorial` both had to learn.
        raise ValueError(
            "the reply was cut off — raise max_tokens"
            if msg.stop_reason == "max_tokens"
            else f"the reply was not JSON: {raw[:140]}") from None
    refused = d.get("refused")
    patch = d.get("patch") or {}
    if not isinstance(patch, dict):
        patch = {}
    return Answer(patch=patch, why=str(d.get("why", "")).strip(),
                  refused=str(refused).strip() if refused else None)
