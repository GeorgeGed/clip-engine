"""Title options for a finished clip: the line a scroller reads in the first
second, so it decides whether the rest gets watched.

One model call per clip over the clip's own transcript returns several
candidates, each from a different angle, and names the strongest. A person
picks; nothing here writes a spec.

What the references and George's notes ask of the line:

* It says what the clip is about, in a way that makes you want the answer —
  George: "a line of text that says what the video is talking about ... It
  needs to be clickbaity", with an emoji at the end.
* It is SHORT. The title is on screen for about a second, and ohnepixel's
  banners run 4-7 words ("Bro is losing his mind 😭", "The #1 knife
  tradeup 😳"). One keyword is coloured.
* It is TRUE. The clickbait is in the framing, never in the facts: every
  claim in the title is something the clip actually says or shows. This
  file's standing rule is that nothing on screen is a sentence nobody said
  the substance of.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict

from engine.tier3 import MODEL_DEFAULT, _api_key

MAX_CHARS = 38

SYSTEM = """You write the on-screen title for a vertical VALORANT esports Short cut
from a streamer's VOD. The title appears over the clip for its first second or
two. It is the single biggest factor in whether a scroller keeps watching, so
it has to make them NEED the next 30 seconds.

You get the clip's transcript. Return ONE json object, no prose, no fence:

{"options":[{"title":"...","keyword":"...","emoji":"...","angle":"..."}, ... 5 total],
 "best":<index 0-4>,
 "why":"<one sentence under 160 characters: why the best one wins>"}

RULES FOR EVERY TITLE
- At most %(max)d characters, emoji excluded. Shorter is better; 4-7 words is the sweet spot.
- Sentence case, like a person typed it. Not ALL CAPS. No full stop at the end.
- TRUE. Every claim must be something the clip itself says. Exaggerate the
  framing, never the facts. No made-up quotes, numbers, results or people.
- Self-explanatory to someone who has never heard of anyone in it. Use the
  streamer's handle (given below) when the line is his claim. Name a team or
  player only if the clip names them, and spell them as the scene does.
- Lead with the most surprising, spicy or high-stakes part, not the setup.
- "keyword" is ONE word copied exactly from the title, the one to colour.
- "emoji" is one emoji that matches the emotion (😳 💀 😭 🤯 😤 🔥 🤣 👀 🗣️ 💸 🚮 ...).

USE FIVE DIFFERENT ANGLES, and name each in "angle":
- "claim": his boldest line, compressed, in his own words where possible.
- "stakes": what is at risk or what happens to someone.
- "curiosity": withhold the answer so they must watch (no fake mystery; the
  clip must pay it off).
- "callout": who he is coming for, and how hard.
- "reaction": how outrageous or funny the moment is, from a viewer's seat.

Patterns that work on Shorts: "FNS says <spicy claim>", "<Team> should
<consequence>", "Why FNS won't <surprising choice>", "FNS has no mercy for
<target>", "This is why <surprising outcome>". Avoid vague words like
"thoughts", "talks about", "discusses", "on <topic>" — they describe, they
do not hook."""


@dataclass
class Option:
    title: str
    keyword: str
    emoji: str
    angle: str


def _clean(t: str) -> str:
    from engine import handles                       # noqa: PLC0415
    t = handles.fix(re.sub(r"\s+", " ", (t or "").strip().strip("\"'")))
    return t.rstrip(".")


def suggest(words: dict, *, handle: str, subject: str = "", claim: str = "",
            model: str = MODEL_DEFAULT, client=None) -> dict:
    import anthropic
    body = "\n".join(f'[{float(u["start"]):.1f}] {u["text"].strip()}'
                      for u in words.get("utterances", []) if u.get("text", "").strip())
    client = client or anthropic.Anthropic(
        api_key=_api_key(), max_retries=8,
        default_headers={"Accept-Encoding": "gzip"})
    msg = client.messages.create(
        model=model, max_tokens=8000, system=SYSTEM % {"max": MAX_CHARS},
        messages=[{"role": "user", "content":
                   f"Streamer handle: {handle}\nThe ranker summarised it as: {subject}\n"
                   f"Its claim: {claim}\n\nTranscript:\n\n{body}"}])
    raw = "".join(b.text for b in msg.content if b.type == "text").strip()
    start = raw.find("{")
    if start < 0 or msg.stop_reason == "max_tokens":
        raise ValueError(f"no complete json (stop_reason={msg.stop_reason}): {raw[:140]}")
    d, _end = json.JSONDecoder().raw_decode(raw[start:])
    opts = []
    for o in d.get("options", []):
        title = _clean(o.get("title", ""))
        if not title:
            continue
        kw = o.get("keyword", "")
        opts.append(Option(title, kw if kw and kw.lower() in title.lower() else "",
                           o.get("emoji", ""), o.get("angle", "")))
    best = int(d.get("best", 0))
    return {"options": [asdict(o) for o in opts],
            "best": best if 0 <= best < len(opts) else 0,
            "why": str(d.get("why", "")).strip(),
            "usage": {"input": msg.usage.input_tokens, "output": msg.usage.output_tokens}}


def suggest_many(clips: list[dict], *, handle: str, workers: int = 6) -> dict[str, dict]:
    """`clips` is [{n, words, subject, claim}]. Returns {n: suggest() result}."""
    def one(c):
        err = None
        for _ in range(3):  # an unescaped quote in a title breaks the JSON now and then
            try:
                return str(c["n"]), suggest(c["words"], handle=handle,
                                            subject=c.get("subject", ""), claim=c.get("claim", ""))
            except Exception as e:                      # one clip must not sink the rest
                err = e
        return str(c["n"]), {"error": f"{type(err).__name__}: {err}"}
    with ThreadPoolExecutor(workers) as ex:
        return dict(ex.map(one, clips))
