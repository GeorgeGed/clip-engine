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
TREATMENTS = {
    "take": ("none", "banner", "card", "big_cam", "emphasis"),
    "receipts": ("none", "banner", "card", "big_cam", "emphasis"),
    # A reaction to gameplay: the play stays clear (no big-cam, settled
    # 2026-11-19), and a card would sit over the action.
    "frag": ("none", "banner", "emphasis"),
}
MAX_BEATS = 5
MAX_TREATED = 3          # beats with a treatment other than none
BIG_SHARE = 0.40         # make_clip's own cap on the grown facecam
BIG_MIN_S = 2.0
BANNER_MIN_S = 2.0
BANNER_MAX_CHARS = 28
EMPH_MAX_WORDS = 4

SYSTEM = """You are the editor of vertical Shorts cut from a streamer's Twitch VOD. \
A selector has already chosen where this clip starts and ends; you cannot change \
that. Your job is to find the STORY in it and decide, beat by beat, what the \
viewer should feel and what (if anything) the edit does about it. You plan from \
the facts you are given and nothing else.

WHAT YOU RETURN
1. A logline: one line saying what this clip is about, the way you would pitch \
it to someone. If you need "and then" to describe it, it is two clips and you \
should drop it.
2. Beats: 2 to %(max_beats)d contiguous stretches covering every sentence from \
the first to the last. Name them by sentence id ("from": "s1", "to": "s4"). The \
next beat starts at the sentence after the previous one ends.
3. For each beat: a role, ONE feeling, ONE treatment, and why.

ROLES: setup (who/what this is about), turn (the moment it changes), escalation \
(it gets bigger), payoff (the line people will quote or the reaction it was all \
for; exactly one per clip), button (a short last line that lands it).

FEELINGS (pick one per beat): %(feelings)s.

TREATMENTS. "none" is a real answer and usually the right one: his delivery \
carries most beats. Story first: never use a graphic just because it exists. \
At most %(max_treated)d beats get a treatment other than none. Allowed for this \
clip: %(allowed)s.
- banner: a short topic label (at most %(banner_max)d characters, ALL CAPS) naming \
WHO or WHAT the clip is about, like "SENTINELS ROSTER" or "OPEN QUALIFIERS", shown \
over the beat. It is a label, never the take, the punchline or a headline: the \
clip already opens on a title that says the take. Use it once at most, on a beat \
where a viewer arriving cold would not yet know the subject. Give "banner".
- card: a picture of a player or team, shown when he names them. Only for a \
name actually said in THIS beat, and only when the viewer needs to know who \
that is to follow the beat. Give "card": the name as said.
- big_cam: his facecam grows to fill more of the frame for the beat. For a beat \
whose point is his face: the reaction, the disbelief, the deadpan button. The \
beat must last at least %(big_min).0fs, and big_cam beats together stay under \
%(big_share)d%% of the clip.
- emphasis: the payoff's key words light up in the captions. Give "words": 1 to \
%(emph_max)d single content words copied exactly from the beat (not "to", "the", \
"is"). Use it on the payoff or turn only.

THE EDITORIAL RULES THE CLIPS ARE HELD TO
- One clip = one narrative. A pivot to another subject is a boundary.
- The clip must explain itself to someone who joined at the first second.
- A question and its answer are one narrative.
- Sentences marked "other" are not the streamer (a caster, co-host, the game). \
Do not build a beat's point on them unless the clip is his reaction to them.
- No music, no zoom-ins, no sound effects: you cannot ask for them.

DROP THE CLIP when it has no story: no payoff, it does not explain itself, it \
is two narratives, or most of it is someone other than the streamer. Say why in \
"drop" and return no beats. Dropping is better than shipping a clip with \
nothing thought behind it.

NOTES FROM REVIEW (complaints that became rules; follow them):
%(rules)s

Reply with ONLY a JSON object:
{"logline": str, "drop": null or str,
 "beats": [{"from": "s1", "to": "s3", "role": str, "feeling": str,
            "treatment": str, "why": str,
            "banner": str (banner only), "card": str (card only),
            "words": [str] (emphasis only)}]}"""


def _rules() -> str:
    try:
        lines = [ln for ln in RULES.read_text().splitlines() if ln.startswith("- ")]
    except OSError:
        return "(none yet)"
    return "\n".join(lines) or "(none yet)"


def system(genre: str) -> str:
    return SYSTEM % {"max_beats": MAX_BEATS, "feelings": ", ".join(FEELINGS),
                     "max_treated": MAX_TREATED, "allowed": ", ".join(TREATMENTS[_genre(genre)]),
                     "banner_max": BANNER_MAX_CHARS, "big_min": BIG_MIN_S,
                     "big_share": round(100 * BIG_SHARE), "emph_max": EMPH_MAX_WORDS,
                     "rules": _rules()}


def _genre(g: str | None) -> str:
    return g if g in TREATMENTS else "take"


def _tokens(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (s or "").lower())


def _same_name(a: str, b: str) -> bool:
    """Whether two strings share a name word of 3+ letters, one a prefix of
    the other: whisper writes "tenzz" for TenZ."""
    return any(x.startswith(y) or y.startswith(x)
               for x in _tokens(a) if len(x) >= 3 for y in _tokens(b) if len(y) >= 3)


def _said(name: str, text: str) -> bool:
    return _same_name(name, text)


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
    out, nxt, big, treated, banners = [], 0, 0.0, 0, 0
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
        if tr not in TREATMENTS[genre]:
            errs.append(f"{tag}: treatment {tr!r} is not allowed here; "
                        f"pick from {', '.join(TREATMENTS[genre])}")
        beat = {"from": b.get("from"), "to": b.get("to"), "start": round(start, 3),
                "end": round(end, 3), "text": text, "role": role, "feeling": feeling,
                "treatment": tr, "why": why}
        if tr != "none":
            treated += 1
            if not why:
                errs.append(f"{tag}: a {tr} needs a why tied to this beat")
        if tr == "banner":
            banners += 1
            label = str(b.get("banner") or "").strip().upper()
            if not 3 <= len(label) <= BANNER_MAX_CHARS:
                errs.append(f"{tag}: banner must be 3 to {BANNER_MAX_CHARS} characters")
            if end - start < BANNER_MIN_S:
                errs.append(f"{tag}: a banner needs a beat of at least {BANNER_MIN_S:.0f}s")
            beat["banner"] = label
        elif tr == "card":
            name = str(b.get("card") or "").strip()
            if not name or not _said(name, text):
                errs.append(f"{tag}: card {name!r} is not said in this beat")
            beat["card"] = name
        elif tr == "big_cam":
            if end - start < BIG_MIN_S:
                errs.append(f"{tag}: big_cam needs a beat of at least {BIG_MIN_S:.0f}s")
            big += end - start
        elif tr == "emphasis":
            words = [str(w).strip() for w in (b.get("words") or []) if str(w).strip()]
            have = set(_tokens(text))
            if not 1 <= len(words) <= EMPH_MAX_WORDS:
                errs.append(f"{tag}: emphasis needs 1 to {EMPH_MAX_WORDS} words")
            missing = [w for w in words if not set(_tokens(w)) <= have]
            if missing:
                errs.append(f"{tag}: emphasis words not in this beat: {missing}")
            elif not _content(words):
                errs.append(f"{tag}: emphasis needs a content word, not only {words}")
            beat["words"] = words
        out.append(beat)
    if out and nxt != len(sents):
        errs.append(f"the beats stop at {sents[nxt - 1]['id']}; they must run to {sents[-1]['id']}")
    if sum(1 for b in out if b["role"] == "payoff") != 1:
        errs.append("exactly one beat must be the payoff")
    if treated > MAX_TREATED:
        errs.append(f"{treated} treated beats; at most {MAX_TREATED}")
    if banners > 1:
        errs.append("at most one banner per clip")
    if big > BIG_SHARE * float(facts["duration"]):
        errs.append(f"big_cam covers {big:.0f}s; keep it under {BIG_SHARE:.0%} of the clip")
    if errs:
        return None, None, errs
    return {"logline": logline, "beats": out}, None, []


def _ask(client, model: str, genre: str, messages: list[dict]) -> tuple[str, dict | None]:
    msg = client.messages.create(model=model, max_tokens=3000, system=system(genre),
                                 messages=messages)
    raw = "".join(b.text for b in msg.content if b.type == "text").strip()
    a, z = raw.find("{"), raw.rfind("}")
    try:
        return raw, json.loads(raw[a:z + 1]) if 0 <= a < z else None
    except json.JSONDecodeError:
        return raw, None


def write(facts: dict, *, client, model: str = MODEL_DEFAULT) -> dict:
    """{"plan", "drop", "errors", "attempts"} for one clip's facts."""
    genre = facts.get("genre")
    messages = [{"role": "user", "content": render_facts(facts)}]
    errs: list[str] = []
    for attempt in (1, 2):
        raw, d = _ask(client, model, genre, messages)
        plan, drop, errs = validate(d, facts) if d is not None else (None, None, ["reply was not JSON"])
        if plan or drop:
            return {"plan": plan, "drop": drop, "errors": [], "attempts": attempt}
        messages += [{"role": "assistant", "content": raw},
                     {"role": "user", "content": "That plan fails these checks:\n- "
                      + "\n- ".join(errs) + "\nReturn the corrected JSON only."}]
    return {"plan": None, "drop": None, "errors": errs, "attempts": 2, "raw": raw[-1500:]}


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


def _content(words: list[str]) -> set[str]:
    """The words worth an accent: 3+ letters and not a stopword, upper-cased
    the way `resolve_captions.mark_emphasis` compares them. A plan asked for
    "needs to disband" and lit "TO" on the first probe."""
    from engine.resolve_captions import emphasis_keys
    return emphasis_keys(" ".join(words), min_len=3)


def emphasis(plan: dict | None) -> tuple[set[str], list[tuple[float, float]]]:
    """Caption keys and the clip-second spans they may light up in."""
    bs = beats_with(plan, "emphasis")
    return _content([w for b in bs for w in b.get("words", [])]), [(b["start"], b["end"]) for b in bs]


def summary(plan: dict | None) -> dict | None:
    """What the web app shows on the clip card."""
    if not plan:
        return None
    return {"logline": plan["logline"],
            "beats": [{k: b.get(k) for k in ("role", "feeling", "treatment", "why")}
                      for b in plan["beats"]]}
