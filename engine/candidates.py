"""Turn detector output into ranked candidate clips with methodology-correct
in and out points.

This is where the central editorial rule lives: the in-point is found by walking
BACKWARDS from the last event to the first irreversible commitment. It is never
a fixed offset before the payoff, because a fixed offset imports dead air and
buries the hook.

Pure logic. No cv2, no whisper.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any

# ─── Anchor rules: seconds of pre-roll before the first qualifying event ───
PREROLL = {
    "ace": 1.5,
    "4k": 1.2,
    "3k": 1.0,
    "2k": 1.0,
    "clutch": 0.0,     # starts the frame the player becomes last alive
    "flick": 1.2,
    "defuse": 0.0,
    "retake": 0.0,
    "reaction": 2.5,   # a reaction needs the thing being reacted to
}

RARITY = {
    "ace": 1.00, "4k": 0.80, "3k": 0.60, "2k": 0.35,
    "clutch": 0.90, "defuse": 0.75, "retake": 0.55,
    "flick": 0.40, "single": 0.10, "take": 0.50, "reaction": 0.30, "none": 0.0,
}

STAKES_BONUS = {
    "match_point": 0.20, "overtime": 0.20, "spike_down": 0.15,
    "last_alive": 0.15, "thrifty": 0.10, "eco": 0.10, "none": 0.0,
}

WEIGHTS = {"rarity": 0.45, "stakes": 0.20, "reaction": 0.25, "claim": 0.30}
REDUNDANCY_PENALTY = 0.35

TAIL_S = {"frag": 1.2, "take": 0.8, "hybrid": 1.0}
DURATION = {"frag": (12.0, 35.0), "take": (18.0, 45.0), "hybrid": (12.0, 45.0)}


@dataclass
class Candidate:
    candidate_id: str
    genre: str
    event: str
    t_in: float
    t_out: float
    anchor_rule: str
    stakes: list[str] = field(default_factory=list)
    score: float = 0.0
    components: dict[str, float] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return self.t_out - self.t_in

    def as_dict(self) -> dict:
        d = asdict(self)
        d["duration"] = round(self.duration, 3)
        return d


def score_candidate(
    event: str,
    stakes: list[str],
    *,
    reaction: float = 0.0,
    claim_strength: float = 0.0,
    redundant: bool = False,
) -> tuple[float, dict[str, float]]:
    rarity = RARITY.get(event, 0.1)
    stake = min(sum(STAKES_BONUS.get(s, 0.0) for s in stakes), 0.4)
    comp = {
        "rarity": round(WEIGHTS["rarity"] * rarity, 4),
        "stakes": round(WEIGHTS["stakes"] * (stake / 0.4 if stake else 0.0), 4),
        "reaction": round(WEIGHTS["reaction"] * max(0.0, min(reaction, 1.0)), 4),
        "claim": round(WEIGHTS["claim"] * max(0.0, min(claim_strength, 1.0)), 4),
    }
    total = sum(comp.values())
    if redundant:
        comp["redundancy"] = -round(REDUNDANCY_PENALTY, 4)
        total -= REDUNDANCY_PENALTY
    total = max(0.0, min(total, 1.0))
    return round(total, 4), comp


def _clamp_duration(t_in: float, t_out: float, genre: str) -> tuple[float, float, str | None]:
    lo, hi = DURATION[genre]
    dur = t_out - t_in
    note = None
    if dur > hi:
        # Trim from the FRONT. The payoff is at the end and must never be cut.
        t_in = t_out - hi
        note = f"front-trimmed to the {hi:.0f}s ceiling"
    elif dur < lo:
        t_in = max(0.0, t_out - lo)
        note = f"extended back to the {lo:.0f}s floor"
    return round(t_in, 3), round(t_out, 3), note


def from_rounds(
    killfeed: dict,
    *,
    audio: dict | None = None,
    owner: str = "unknown",
    date: str = "0000-00-00",
    min_kills: int = 2,
) -> list[Candidate]:
    """Build frag candidates from killfeed rounds, anchored by walking backwards."""
    audio_events = (audio or {}).get("events", []) or []

    def reaction_near(t0: float, t1: float) -> float:
        from engine.detect_audio import reaction_score

        near = [e for e in audio_events if t0 - 2.0 <= float(e["t"]) <= t1 + 3.0]
        return max((reaction_score(e) for e in near), default=0.0)

    out: list[Candidate] = []
    for rnd in killfeed.get("rounds", []):
        kills = rnd.get("kills", [])
        n = len(kills)
        if n < min_kills:
            continue
        event = {2: "2k", 3: "3k", 4: "4k"}.get(n, "ace")

        first_t = float(kills[0]["t_first"])
        last_t = float(kills[-1]["t_last"])
        pre = PREROLL.get(event, 1.0)
        t_in = max(0.0, first_t - pre)
        t_out = last_t + TAIL_S["frag"]
        t_in, t_out, note = _clamp_duration(t_in, t_out, "frag")

        stakes = list(rnd.get("stakes", []) or [])
        if n >= 5:
            stakes.append("last_alive")
        react = reaction_near(first_t, last_t)
        score, comp = score_candidate(event, stakes, reaction=react)

        out.append(Candidate(
            candidate_id=f"{date}-{owner}-{event}-r{rnd.get('index', 0)}",
            genre="frag",
            event=event,
            t_in=t_in,
            t_out=t_out,
            anchor_rule=f"first_kill_minus_{pre}s" + (f" ({note})" if note else ""),
            stakes=sorted(set(stakes)),
            score=score,
            components=comp,
            evidence={
                "round_index": rnd.get("index"),
                "round_kills": n,
                "first_kill": first_t,
                "last_kill": last_t,
                "reaction": react,
                "kill_texts": [k.get("text", "") for k in kills],
            },
        ))

    out.sort(key=lambda c: -c.score)
    return out


def from_transcript(
    transcript: dict,
    *,
    owner: str = "unknown",
    date: str = "0000-00-00",
    claims: list[dict] | None = None,
) -> list[Candidate]:
    """Build take candidates. `claims` comes from the editorial pass: each entry
    carries setup/claim/consequence word indices and a strength 0..1."""
    flat = [w for u in transcript["utterances"] for w in u["words"]]
    out: list[Candidate] = []
    for i, c in enumerate(claims or []):
        try:
            w0 = flat[int(c["setup_start_word"])]
            w1 = flat[int(c["consequence_end_word"])]
        except (IndexError, KeyError, ValueError):
            continue
        t_in = float(w0["start"])
        t_out = float(w1["end"]) + TAIL_S["take"]
        t_in, t_out, note = _clamp_duration(t_in, t_out, "take")
        score, comp = score_candidate("take", [], claim_strength=float(c.get("strength", 0.5)))
        out.append(Candidate(
            candidate_id=f"{date}-{owner}-take-{i}",
            genre="take",
            event="take",
            t_in=t_in,
            t_out=t_out,
            anchor_rule="setup_first_word" + (f" ({note})" if note else ""),
            score=score,
            components=comp,
            evidence={
                "setup": c.get("setup", ""),
                "claim": c.get("claim", ""),
                "consequence": c.get("consequence", ""),
                "subject": c.get("subject"),
            },
        ))
    out.sort(key=lambda c: -c.score)
    return out


def mark_redundant(cands: list[Candidate], *, overlap_s: float = 3.0) -> list[Candidate]:
    """Penalise candidates that substantially overlap a higher-scoring one."""
    kept: list[Candidate] = []
    for c in sorted(cands, key=lambda x: -x.score):
        clash = any(
            min(c.t_out, k.t_out) - max(c.t_in, k.t_in) > overlap_s for k in kept
        )
        if clash:
            c.score, c.components = score_candidate(
                c.event, c.stakes,
                reaction=c.evidence.get("reaction", 0.0),
                redundant=True,
            )
        kept.append(c)
    kept.sort(key=lambda x: -x.score)
    return kept


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="rank candidate clips")
    ap.add_argument("--killfeed")
    ap.add_argument("--audio")
    ap.add_argument("--owner", default="unknown")
    ap.add_argument("--date", default="0000-00-00")
    ap.add_argument("-o", "--out", default="-")
    a = ap.parse_args()

    cands: list[Candidate] = []
    if a.killfeed:
        kf = json.loads(Path(a.killfeed).read_text())
        au = json.loads(Path(a.audio).read_text()) if a.audio else None
        cands += from_rounds(kf, audio=au, owner=a.owner, date=a.date)
    cands = mark_redundant(cands)

    blob = json.dumps([c.as_dict() for c in cands], indent=2)
    if a.out == "-":
        print(blob)
    else:
        Path(a.out).write_text(blob)
        print(f"{len(cands)} candidates -> {a.out}")
