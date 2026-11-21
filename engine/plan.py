"""The story plan: what a clip is about, where it turns, and why each
treatment is there, written before anything renders.

George's ask: *"proper story-wise shorts — it should actually feel like
someone reviewed each short and everything had something thought behind
it."* Until this file, nothing between Tier 3 and make_clip decided any of
that: every clip of a genre got the same house STYLE, the facecam grew
wherever the audio was loudest, and a pop-up fired whenever a name was said.
The reference workflow's answer (spec.md) is a plan: find the story, give
every beat ONE feeling and ONE treatment, and no graphic just because we
have it.

WHAT THE MODEL CAN AND CANNOT DO HERE
* It names beats by SENTENCE ID from `engine.facts`, never by time, so it
  cannot invent a timestamp. Code turns ids into times.
* It cannot move the in- or out-point. #19's judge trimmed clips and Jatin
  found the trims were not better; Tier 3 owns the cut. The planner may only
  DROP a clip that has no story, which frees its slot for the next one.
* It picks treatments from a closed list of things make_clip already draws,
  and every one except `none` has to say why, tied to its beat.

A plan that fails validation is sent back once with the errors. A second
failure, or any error, leaves the clip unplanned: it ships exactly as it
would have before this file existed. A planner fault never costs a clip.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from engine.facts import render as render_facts
from engine.tier3 import MODEL_DEFAULT

ROOT = Path(__file__).resolve().parent.parent
RULES = ROOT / "config" / "editor_rules.md"

ROLES = ("setup", "turn", "escalation", "payoff", "button")
FEELINGS = ("curiosity", "tension", "frustration", "outrage", "disbelief", "regret",
            "relief", "triumph", "deadpan", "hype", "amusement")
# What a beat may carry. The PAYOFF gets the one hit; the others may carry
# context. Gameplay reactions never grow the facecam (settled 2026-11-19) and
# take no card, which would sit over the play.
BEAT_TREATMENTS = {
    "take": ("none", "banner", "card", "big_cam"),
    "receipts": ("none", "banner", "card", "big_cam"),
    "frag": ("none", "banner"),
}
PAYOFF_TREATMENTS = {
    "take": ("none", "stamp", "big_cam"),
    "receipts": ("none", "stamp", "big_cam"),
    "frag": ("none", "stamp"),
}
OPENS = {"take": ("straight", "cold"), "frag": ("straight", "cold"),
         # a receipts clip is its build-up; opening on the verdict spends it
         "receipts": ("straight",)}
VERSION = 2              # plans.json entries from another version are re-planned
MAX_BEATS = 5
MAX_GRAPHICS = 2         # banners + cards
BIG_SHARE = 0.40         # make_clip's own cap on the grown facecam
BIG_MIN_S = 2.0
BANNER_MIN_S = 2.0
BANNER_MAX_CHARS = 28
STAMP_MAX_CHARS = 14
PAYOFF_WORDS_MAX = 3
COLD_MIN_S, COLD_MAX_S = 1.0, 4.0

SYSTEM = """You are the editor of vertical Shorts cut from a streamer's Twitch VOD. \
A selector has already chosen where this clip starts and ends; you cannot change \
that. Your job is to find the STORY in it and build the edit around its payoff. \
You plan from the facts you are given and nothing else.

EVERY CLIP IS BUILT AROUND ITS PAYOFF: the line people will quote, or the \
reaction the clip exists for. Find it first. Everything else serves it.

WHAT YOU RETURN
1. logline: one line saying what this clip is about, the way you would pitch it. \
If you need "and then" to describe it, it is two clips: drop it.
2. beats: 2 to %(max_beats)d contiguous stretches covering every sentence from \
the first to the last, named by sentence id ("from": "s1", "to": "s4"). Each \
has a role, ONE feeling and ONE treatment, and says why.
3. payoff_words: 1 to %(pw_max)d content words copied from the payoff beat, the \
words that carry its point. They light up in the captions wherever he says \
them in the clip, so pick the words that ARE the clip, not filler.
4. open: how the clip starts.
   - "straight": it plays from its first sentence. Right when the setup itself \
hooks, or the payoff only lands after the build-up.
   - "cold": a few words of the payoff play FIRST, as a tease, then the clip \
runs from the start. Right when the payoff holds a short, striking phrase that \
makes a scroller need the context. Give "quote": the exact words as written in \
ONE payoff sentence, a phrase of %(cold_min).0f to %(cold_max).0f seconds (he \
says about three words a second), and never a phrase that gives the whole story \
away or only makes sense after the setup.
   Allowed here: %(opens)s. Say why either way.

ROLES: setup (who/what this is about), turn (the moment it changes), escalation \
(it gets bigger), payoff (exactly one), button (a short last line that lands it).
FEELINGS (one per beat): %(feelings)s.

TREATMENTS. "none" is a real answer and usually the right one: his delivery \
carries most beats. Never use a graphic just because it exists; a viewer should \
be able to say why each one is there. At most %(max_graphics)d graphics (banner \
+ card) per clip.
For the PAYOFF beat (allowed here: %(payoff_allowed)s):
- stamp: the picture below his face freezes and greys out for a second while ONE \
big word or two lands on it, copied from the payoff (at most %(stamp_max)d \
characters), like "DISBAND" or "TIER TWO". For a payoff that is a verdict, a \
number or a punchline. Give "stamp".
- big_cam: his facecam grows for the beat. For a payoff that is his face: \
disbelief, a deadpan, a reaction.
For the OTHER beats (allowed here: %(beat_allowed)s):
- banner: a short topic label (at most %(banner_max)d characters, ALL CAPS) naming \
WHO or WHAT a beat is about. The clip already opens on a title naming the \
subject, so a banner is for a beat that brings in something new the viewer \
needs named, never a restatement of the title and never the punchline. Give \
"banner". At most one.
- card: a picture of a player or team, for a name said in THIS beat that the \
viewer must recognise to follow it. Give "card": the name as said.
- big_cam: his facecam grows, for a beat whose point is his face. At least \
%(big_min).0fs, and all big_cam beats together under %(big_share)d%% of the clip.

THE EDITORIAL RULES THE CLIPS ARE HELD TO
- One clip = one narrative. A pivot to another subject is a boundary.
- The clip must explain itself to someone who joined at the first second.
- A question and its answer are one narrative.
- Sentences marked "other" are not the streamer (a caster, co-host, the game). \
Do not build the payoff on them unless the clip is his reaction to them.
- No music, no zoom-ins, no sound effects: you cannot ask for them.

DROP THE CLIP when it has no story: no payoff, it does not explain itself, it \
is two narratives, or most of it is someone other than the streamer. Say why in \
"drop" and return no beats. Dropping is better than shipping a clip with \
nothing thought behind it.

NOTES FROM REVIEW (complaints that became rules; follow them):
%(rules)s

Reply with ONLY a JSON object:
{"logline": str, "drop": null or str,
 "open": {"style": "straight" or "cold", "quote": str (cold only), "why": str},
 "payoff_words": [str],
 "beats": [{"from": "s1", "to": "s3", "role": str, "feeling": str,
            "treatment": str, "why": str,
            "banner": str (banner only), "card": str (card only),
            "stamp": str (stamp only)}]}"""


def _rules() -> str:
    try:
        lines = [ln for ln in RULES.read_text().splitlines() if ln.startswith("- ")]
    except OSError:
        return "(none yet)"
    return "\n".join(lines) or "(none yet)"


def _genre(g: str | None) -> str:
    return g if g in BEAT_TREATMENTS else "take"


def system(genre: str) -> str:
    g = _genre(genre)
    return SYSTEM % {"max_beats": MAX_BEATS, "pw_max": PAYOFF_WORDS_MAX,
                     "cold_min": COLD_MIN_S, "cold_max": COLD_MAX_S,
                     "opens": ", ".join(OPENS[g]), "feelings": ", ".join(FEELINGS),
                     "max_graphics": MAX_GRAPHICS,
                     "payoff_allowed": ", ".join(PAYOFF_TREATMENTS[g]),
                     "beat_allowed": ", ".join(BEAT_TREATMENTS[g]),
                     "stamp_max": STAMP_MAX_CHARS, "banner_max": BANNER_MAX_CHARS,
                     "big_min": BIG_MIN_S, "big_share": round(100 * BIG_SHARE),
                     "rules": _rules()}


def _tokens(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (s or "").lower())


def _same_name(a: str, b: str) -> bool:
    """Whether two strings share a name word of 3+ letters, one a prefix of
    the other: whisper writes "tenzz" for TenZ."""
    return any(x.startswith(y) or y.startswith(x)
               for x in _tokens(a) if len(x) >= 3 for y in _tokens(b) if len(y) >= 3)


def _content(words: list[str]) -> set[str]:
    """The words worth an accent: 3+ letters and not a stopword, upper-cased
    the way `resolve_captions.mark_emphasis` compares them. A plan asked for
    "needs to disband" and lit "TO" on the first probe."""
    from engine.resolve_captions import emphasis_keys
    return emphasis_keys(" ".join(words), min_len=3)


def _spoken(phrase: str, text: str) -> bool:
    """Every word of `phrase` is in `text`: nothing on screen nobody said."""
    return bool(_tokens(phrase)) and set(_tokens(phrase)) <= set(_tokens(text))


def _quote_span(quote: str, sents: list[dict]) -> tuple[float, float] | None:
    """Where @quote@ is said, from the word timestamps: the first run of
    consecutive words in one sentence whose tokens are the quote's."""
    want = _tokens(quote)
    if not want:
        return None
    for s in sents:
        toks = [(t, w) for w in s.get("words") or [] for t in _tokens(w[2])]
        for i in range(len(toks) - len(want) + 1):
            if [t for t, _w in toks[i:i + len(want)]] == want:
                return float(toks[i][1][0]), float(toks[i + len(want) - 1][1][1])
    return None


def validate(raw: dict, facts: dict) -> tuple[dict | None, str | None, list[str]]:
    """(plan, drop, errors). A plan carries times; the model's ids are gone."""
    if not isinstance(raw, dict):
        return None, None, ["reply is not a JSON object"]
    if raw.get("drop"):
        return None, str(raw["drop"]).strip(), []
    errs: list[str] = []
    sents = facts["sentences"]
    if not sents:
        return None, None, ["the clip has no sentences to plan"]
    idx = {s["id"]: i for i, s in enumerate(sents)}
    genre = _genre(facts.get("genre"))
    logline = str(raw.get("logline") or "").strip()
    if not logline:
        errs.append("logline is missing")
    elif re.search(r"\band then\b", logline, re.I):
        errs.append("logline needs 'and then', so it is two narratives: drop it or narrow it")
    beats = raw.get("beats") or []
    want_min = min(2, len(sents))
    if not want_min <= len(beats) <= MAX_BEATS:
        errs.append(f"{len(beats)} beats; want {want_min} to {MAX_BEATS}")
    out, nxt, big, graphics, banners = [], 0, 0.0, 0, 0
    for k, b in enumerate(beats, 1):
        tag = f"beat {k}"
        a, z = idx.get(b.get("from")), idx.get(b.get("to"))
        if a is None or z is None:
            errs.append(f"{tag}: from/to must be sentence ids shown in the facts")
            continue
        if a != nxt:
            errs.append(f"{tag} starts at {b['from']}; the previous beat ended at "
                        f"{sents[nxt - 1]['id'] if nxt else 'the start'}, so it must start at "
                        f"{sents[nxt]['id'] if nxt < len(sents) else 'nothing'}")
        if z < a:
            errs.append(f"{tag}: 'to' comes before 'from'")
            continue
        nxt = z + 1
        start, end = float(sents[a]["start"]), float(sents[z]["end"])
        text = " ".join(s["text"] for s in sents[a:z + 1])
        role, feeling, tr = b.get("role"), b.get("feeling"), b.get("treatment", "none")
        why = str(b.get("why") or "").strip()
        if role not in ROLES:
            errs.append(f"{tag}: role {role!r} is not one of {', '.join(ROLES)}")
        if feeling not in FEELINGS:
            errs.append(f"{tag}: feeling {feeling!r} is not one of {', '.join(FEELINGS)}")
        allowed = (PAYOFF_TREATMENTS if role == "payoff" else BEAT_TREATMENTS)[genre]
        if tr not in allowed:
            errs.append(f"{tag}: treatment {tr!r} is not allowed on a {role or 'beat'} here; "
                        f"pick from {', '.join(allowed)}")
        beat = {"from": b.get("from"), "to": b.get("to"), "first": a, "last": z,
                "start": round(start, 3), "end": round(end, 3), "text": text,
                "role": role, "feeling": feeling, "treatment": tr, "why": why}
        if tr != "none" and not why:
            errs.append(f"{tag}: a {tr} needs a why tied to this beat")
        if tr == "banner":
            banners += 1
            graphics += 1
            label = str(b.get("banner") or "").strip().upper()
            if not 3 <= len(label) <= BANNER_MAX_CHARS:
                errs.append(f"{tag}: banner must be 3 to {BANNER_MAX_CHARS} characters")
            if end - start < BANNER_MIN_S:
                errs.append(f"{tag}: a banner needs a beat of at least {BANNER_MIN_S:.0f}s")
            beat["banner"] = label
        elif tr == "card":
            graphics += 1
            name = str(b.get("card") or "").strip()
            if not name or not _same_name(name, text):
                errs.append(f"{tag}: card {name!r} is not said in this beat")
            beat["card"] = name
        elif tr == "big_cam":
            if end - start < BIG_MIN_S:
                errs.append(f"{tag}: big_cam needs a beat of at least {BIG_MIN_S:.0f}s")
            big += end - start
        elif tr == "stamp":
            word = str(b.get("stamp") or "").strip().upper()
            if not 2 <= len(word) <= STAMP_MAX_CHARS or len(_tokens(word)) > 2:
                errs.append(f"{tag}: stamp must be one or two words, at most {STAMP_MAX_CHARS} characters")
            elif not _spoken(word, text):
                errs.append(f"{tag}: stamp {word!r} must be words he says in this beat")
            beat["stamp"] = word
        out.append(beat)
    if out and nxt != len(sents):
        errs.append(f"the beats stop at {sents[nxt - 1]['id']}; they must run to {sents[-1]['id']}")
    payoffs = [b for b in out if b["role"] == "payoff"]
    if len(payoffs) != 1:
        errs.append("exactly one beat must be the payoff")
    if graphics > MAX_GRAPHICS:
        errs.append(f"{graphics} graphics (banners and cards); at most {MAX_GRAPHICS}")
    if banners > 1:
        errs.append("at most one banner per clip")
    if big > BIG_SHARE * float(facts["duration"]):
        errs.append(f"big_cam covers {big:.0f}s; keep it under {BIG_SHARE:.0%} of the clip")
    words = [str(w).strip() for w in (raw.get("payoff_words") or []) if str(w).strip()]
    if not 1 <= len(words) <= PAYOFF_WORDS_MAX:
        errs.append(f"payoff_words needs 1 to {PAYOFF_WORDS_MAX} words")
    elif len(payoffs) == 1:
        missing = [w for w in words if not _spoken(w, payoffs[0]["text"])]
        if missing:
            errs.append(f"payoff_words not said in the payoff beat: {missing}")
        elif not _content(words):
            errs.append(f"payoff_words need a content word, not only {words}")
    op = raw.get("open") or {}
    style = op.get("style", "straight")
    opening = {"style": style, "why": str(op.get("why") or "").strip()}
    if style not in OPENS[genre]:
        errs.append(f"open {style!r} is not allowed here; pick from {', '.join(OPENS[genre])}")
    elif style == "cold" and len(payoffs) == 1:
        p = payoffs[0]
        quote = str(op.get("quote") or "").strip()
        span = _quote_span(quote, sents[p["first"]:p["last"] + 1])
        if span is None:
            errs.append(f"cold open quote {quote!r} is not words said, in order, in one "
                        f"payoff sentence; copy them exactly")
        else:
            s0, s1 = span
            if not COLD_MIN_S <= s1 - s0 <= COLD_MAX_S:
                errs.append(f"the cold open quote runs {s1 - s0:.1f}s; it must be "
                            f"{COLD_MIN_S:.0f} to {COLD_MAX_S:.0f}s, so quote "
                            f"{'fewer' if s1 - s0 > COLD_MAX_S else 'more'} words")
            opening.update({"quote": quote, "start": round(s0, 3), "end": round(s1, 3)})
    if errs:
        return None, None, errs
    for b in out:
        del b["first"], b["last"]
    return {"logline": logline, "open": opening, "payoff_words": words, "beats": out}, None, []


def _ask(client, model: str, genre: str, messages: list[dict]) -> tuple[str, dict | None]:
    msg = client.messages.create(model=model, max_tokens=3000, system=system(genre),
                                 messages=messages)
    raw = "".join(b.text for b in msg.content if b.type == "text").strip()
    return raw, _json(raw)


def _json(raw: str) -> dict | None:
    """The plan object in a reply. Not first "{" to last "}": a reply that
    mentions a brace in prose before the JSON failed twice on one probe clip."""
    dec = json.JSONDecoder(strict=False)
    i = raw.find("{")
    while i >= 0:
        try:
            d, _end = dec.raw_decode(raw, i)
            if isinstance(d, dict) and ("beats" in d or "drop" in d):
                return d
        except json.JSONDecodeError:
            pass
        i = raw.find("{", i + 1)
    return None


def write(facts: dict, *, client, model: str = MODEL_DEFAULT) -> dict:
    """{"plan", "drop", "errors", "attempts"} for one clip's facts."""
    genre = facts.get("genre")
    messages = [{"role": "user", "content": render_facts(facts)}]
    errs: list[str] = []
    for attempt in (1, 2):
        raw, d = _ask(client, model, genre, messages)
        plan, drop, errs = validate(d, facts) if d is not None else (None, None, ["reply was not JSON"])
        if plan or drop:
            return {"v": VERSION, "plan": plan, "drop": drop, "errors": [], "attempts": attempt}
        messages += [{"role": "assistant", "content": raw},
                     {"role": "user", "content": "That plan fails these checks:\n- "
                      + "\n- ".join(errs) + "\nReturn the corrected JSON only."}]
    plan, why = _salvage(d, facts, errs)
    if plan:
        return {"v": VERSION, "plan": plan, "drop": None, "errors": [], "attempts": 2,
                "salvaged": why}
    return {"v": VERSION, "plan": None, "drop": None, "errors": errs, "attempts": 2,
            "raw": raw[-1500:]}


def _salvage(d: dict | None, facts: dict, errs: list[str]) -> tuple[dict | None, list[str]]:
    """A plan whose story is sound but whose decoration fails twice keeps the
    story: the failing treatments go to "none" and a failing cold open to
    "straight". Clip 6 of VOD 2920606211 lost its whole plan to a stamp
    three words long, written twice. A story fault (beats, roles, payoff
    words, logline) is never salvaged."""
    if not isinstance(d, dict) or not isinstance(d.get("beats"), list):
        return None, []
    d = json.loads(json.dumps(d))
    named = {int(k) for k in re.findall(r"^beat (\d+):", "\n".join(errs), re.M)}
    if any(re.search(r"graphics|at most one banner|big_cam covers", e) for e in errs):
        named |= {k for k, b in enumerate(d["beats"], 1) if b.get("role") != "payoff"}
    why = []
    for k, b in enumerate(d["beats"], 1):
        if k in named and isinstance(b, dict) and b.get("treatment", "none") != "none":
            why.append(f"beat {k} {b['treatment']} dropped")
            b["treatment"] = "none"
    if any("cold open" in e for e in errs):
        d["open"] = {"style": "straight", "why": "the cold open failed its checks"}
        why.append("cold open dropped")
    if not why:
        return None, []
    plan, _drop, left = validate(d, facts)
    return (plan, why) if plan else (None, [])


def beats_with(plan: dict | None, treatment: str) -> list[dict]:
    return [b for b in (plan or {}).get("beats", []) if b["treatment"] == treatment]


def output_spans(plan: dict | None, treatment: str, keeps) -> list[tuple[float, float]]:
    """The beats given `treatment`, in OUTPUT seconds through the cut's keeps."""
    from engine.tighten import remap_card
    out = []
    for b in beats_with(plan, treatment):
        rm = remap_card(b["start"], b["end"], keeps)
        if rm:
            out.append((round(rm[0], 3), round(rm[1], 3)))
    return out


def allowed_popups(found: list[dict], plan: dict | None) -> list[dict]:
    """Only the pop-ups a card beat asked for: that name, said in that beat."""
    keep = []
    for e in found:
        for b in beats_with(plan, "card"):
            named = _same_name(b["card"], e.get("name", "") + " " + e.get("spoken", ""))
            if named and b["start"] - 0.5 <= float(e["at"]) <= b["end"]:
                keep.append(e)
                break
    return keep


def emphasis(plan: dict | None) -> set[str]:
    """The caption accent: the payoff's own words, wherever he says them."""
    return _content((plan or {}).get("payoff_words") or [])


def stamp(plan: dict | None, words: list[dict]) -> dict | None:
    """The stamp's word and the clip-second it lands on: the first time the
    payoff beat says it, so the freeze hits on the word and not ahead of it."""
    b = next(iter(beats_with(plan, "stamp")), None)
    if b is None:
        return None
    want = _tokens(b["stamp"])
    inside = [w for w in words if b["start"] - 0.05 <= float(w["start"]) <= b["end"] + 0.05]
    for w in inside:
        if _tokens(w["text"])[:1] == want[:1]:
            return {"word": b["stamp"], "at": float(w["start"])}
    return {"word": b["stamp"], "at": b["start"]}


def summary(plan: dict | None) -> dict | None:
    """What the web app shows on the clip card."""
    if not plan:
        return None
    return {"logline": plan["logline"], "open": (plan.get("open") or {}).get("style", "straight"),
            "beats": [{k: b.get(k) for k in ("role", "feeling", "treatment", "why")}
                      for b in plan["beats"]]}
