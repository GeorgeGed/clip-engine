"""Remove dead space from a clip and keep everything else in sync.

A removed span becomes a CUT, so the dead-air pass and the picture-cut pass
are the same pass: each join is a shot change with its own framing.

The integrity caveat, stated plainly because it does not go away. On a VOD
with Twitch mutes, most dead space is absent audio sitting MID-SENTENCE.
Removing it joins words that had unheard speech between them — "was never
kind" [1.25s gone] "to job stability" becomes one continuous line. Nobody can
hear what was removed, so nothing audible is lost, but the join implies a
continuity the original may not have had. `joins()` reports every one with
the words either side so a human can read them before it ships.
"""

from __future__ import annotations

from dataclasses import dataclass

BEAT = 0.12          # breath left at each join, so it does not feel clipped
MIN_REMOVE = 0.45    # shorter than this is not worth a cut


@dataclass
class Span:
    start: float
    end: float

    @property
    def length(self) -> float:
        return self.end - self.start


def removals(dead_runs, duration, *, beat: float = BEAT,
             min_remove: float = MIN_REMOVE, edge: float = 0.25) -> list[Span]:
    """Spans to delete, derived from measured absent-audio runs.

    Each run is shrunk by `beat` at both ends so a little silence survives,
    and runs touching the clip's own edges are left alone — trimming those is
    an in/out-point decision, not a dead-air one.
    """
    out = []
    for a, b in dead_runs:
        s, e = float(a) + beat, float(b) - beat
        if s <= edge or e >= duration - edge:
            continue
        if e - s >= min_remove:
            out.append(Span(round(s, 3), round(e, 3)))
    return out


def keeps(spans: list[Span], duration: float) -> list[Span]:
    """The complement: what survives, in order."""
    out, t = [], 0.0
    for s in sorted(spans, key=lambda x: x.start):
        if s.start > t:
            out.append(Span(round(t, 3), round(s.start, 3)))
        t = max(t, s.end)
    if t < duration:
        out.append(Span(round(t, 3), round(duration, 3)))
    return out


def remap(t: float, keep: list[Span]) -> float | None:
    """Source time -> output time. None if t fell in a removed span."""
    acc = 0.0
    for k in keep:
        if k.start <= t < k.end:
            return round(acc + (t - k.start), 3)
        acc += k.length
    return None


def remap_card(start: float, end: float, keep: list[Span]) -> tuple[float, float] | None:
    """Remap a caption card, clamping to the nearest kept edge."""
    s = remap(start, keep)
    e = remap(end, keep)
    if s is None:
        s = remap(next((k.start for k in keep if k.start >= start), None) or 0.0, keep)
    if e is None:
        prev = [k.end for k in keep if k.end <= end]
        e = remap(max(prev) - 1e-4, keep) if prev else None
    if s is None or e is None or e <= s:
        return None
    return s, e


def joins(spans: list[Span], words: list[dict]) -> list[dict]:
    """What each removal splices together. Read these before shipping."""
    out = []
    for s in spans:
        before = [w for w in words if float(w["end"]) <= s.start]
        after = [w for w in words if float(w["start"]) >= s.end]
        out.append({
            "at": s.start, "removed": round(s.length, 2),
            "before": " ".join(w["text"] for w in before[-5:]),
            "after": " ".join(w["text"] for w in after[:5]),
        })
    return out
