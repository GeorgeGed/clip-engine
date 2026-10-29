"""Rank clips by how likely they are to travel.

The honest position: Tier 3's judgement is the best single estimator we have,
because it is the only component that read the words. Everything else is
corroboration — evidence that the room reacted, or that the shape fits the
format. So strength carries the most weight and the rest adjust it.

Nothing here is validated against real view counts yet. It is a stated set of
weights to disagree with, not a learned model. When George rejects a ranking,
the component breakdown shows WHICH signal was wrong.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

WEIGHTS = {
    "strength": 0.45,   # Tier 3 read the transcript; trust it most
    "crowd": 0.25,      # viewers already clipped it
    "reaction": 0.15,   # he got loud — weak on its own, see tier3-finds-the-in-point
    "fit": 0.15,        # right length, names a real subject
}

# A clip about a named player or org is shareable. A clip about a concept is not.
GENRE_WEIGHT = {"take": 1.0, "receipts": 1.0, "frag": 1.0, "hybrid": 1.0, "none": 0.0}

IDEAL_SECONDS = (18.0, 70.0)
HARD_SECONDS = (10.0, 100.0)


@dataclass
class Score:
    total: float
    components: dict
    flags: list

    def as_dict(self) -> dict:
        return asdict(self)


def duration_fit(seconds: float) -> tuple[float, list[str]]:
    lo, hi = IDEAL_SECONDS
    hlo, hhi = HARD_SECONDS
    flags: list[str] = []
    if seconds < hlo:
        flags.append(f"{seconds:.0f}s is too short to carry setup, claim and consequence")
        return 0.0, flags
    if seconds > hhi:
        flags.append(f"{seconds:.0f}s is long for short-form — check the out-point")
        return 0.25, flags
    if seconds < lo:
        return 0.6, [f"{seconds:.0f}s is tight"]
    if seconds > hi:
        return 0.7, [f"{seconds:.0f}s runs past the comfortable window"]
    return 1.0, flags


def score(
    *, strength: float, genre: str, seconds: float,
    crowd: float = 0.0, reaction: float = 0.0,
    subject: str = "", names: list[str] | None = None,
    risks: list[str] | None = None,
) -> Score:
    flags: list[str] = []
    gw = GENRE_WEIGHT.get(genre, 0.0)
    if gw == 0.0:
        return Score(0.0, {}, ["genre is 'none' — Tier 3 found no clip here"])

    dfit, dflags = duration_fit(seconds)
    flags += dflags

    # A concrete subject travels; an abstract one does not.
    named = bool(subject and len(subject) > 3)
    specific = 1.0 if (named and names) else (0.7 if named else 0.35)
    if not named:
        flags.append("no clear subject — hard to title or thumbnail")

    fit = round(0.6 * dfit + 0.4 * specific, 4)
    comp = {
        "strength": round(WEIGHTS["strength"] * max(0.0, min(strength, 1.0)), 4),
        "crowd": round(WEIGHTS["crowd"] * max(0.0, min(crowd, 1.0)), 4),
        "reaction": round(WEIGHTS["reaction"] * max(0.0, min(reaction, 1.0)), 4),
        "fit": round(WEIGHTS["fit"] * fit, 4),
    }
    total = round(sum(comp.values()) * gw, 4)

    for r in (risks or []):
        low = r.lower()
        if "more than one" in low or "second speaker" in low or "voice" in low:
            flags.append("speaker attribution needs checking before this ships")
        if "vague" in low or "teaser" in low:
            flags.append("payoff is a teaser, not news")
    return Score(total, comp, flags)


def rank(rows: list[dict]) -> list[dict]:
    """rows carry tier3 output plus crowd/reaction evidence."""
    out = []
    for r in rows:
        if not r.get("has_clip") or r.get("in_point") is None or r.get("out_point") is None:
            continue
        secs = float(r["out_point"]) - float(r["in_point"])
        s = score(
            strength=float(r.get("strength") or 0),
            genre=r.get("genre", "none"),
            seconds=secs,
            crowd=float(r.get("crowd_score") or 0),
            reaction=float(r.get("audio_peak") or 0),
            subject=r.get("subject", ""),
            names=r.get("names_to_verify") or [],
            risks=r.get("risks") or [],
        )
        out.append({**r, "seconds": round(secs, 1),
                    "virality": s.total, "components": s.components, "flags": s.flags})
    out.sort(key=lambda r: -r["virality"])
    return out
