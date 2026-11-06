"""A boom does not go on the clause that is about to be overruled.

WHERE THIS CAME FROM. Five acoustic and positional metrics were measured
against George's six verdicts on boom placement and none separated them —
level ranks the rejected moment FIRST on clip 16, rise puts the two rejected
candidates at the top of the clip, and sustain failed across 50
parameterisations. `resolve_punch` carries that table. The conclusion drawn
was that the pick is not decidable from the audio, and an adversarial pass
over the same six points refuted that: the signal is not in the audio, it is
in the WORD SEQUENCE, and it had not been looked for there.

THE RULE. A connective like *but*, *though*, *however* or *as well* marks the
clause BEFORE it as the satellite of the one after — the speaker is about to
overrule, qualify or extend what he has just said. A sound effect lands as a
full stop, so putting one on a clause the speaker is in the middle of
demoting punctuates the wrong half of the sentence.

    "for teams that succeed they had PRIOR issues **as well**"   rejected
    "don't get paid for a COUPLE months **but** you have the      rejected
     freedom to choose your own teammates"
    "sometimes teams are dead ... and END up making runs"         accepted
    "i DON'T want to hear no complaints"                          accepted
    "i JUST don't want to hear it"                                accepted
    "ping issues CHEATERS like if a player has an issue"          accepted

Both rejections carry a connective **two words ahead**. None of the four
accepted moments has one within twelve.

WHY THIS IS NOT THE FITTED CONSTANT THE OTHER FIVE WERE. Three reasons, and
the first is the one that killed sustain:

1. **It is invariant from W=3 to W=12** — a plateau, where sustain separated
   at exactly one window/threshold pair and nowhere else.
2. **It holds on clips it was never fitted to.** On clip 6 it gates 34.19
   (*"its own issues / it is **still** better than locking players out"*) and
   so promotes **9.30 "CHEATERS"** — the one moment in this whole job George
   pointed at himself, which the dB ranking had buried at third. On clip 12
   it independently gates 27.25, the moment he rejected, and leaves both he
   accepted. Neither was used to build the rule.
3. **Its only failure mode is dropping a boom**, and George's two complaints
   were both that there was one too many. A filter that errs toward fewer
   errs in the direction he has asked for twice.

STATED PLAINLY: across all four built clips only **three** members of the
list have ever fired — `but` (6 occurrences), `still` (1) and `as well` (1).
The rest are there because the class is closed and writing half of it would
be the fitted version. `yet`, `plus` and `either` have never appeared.

THE KNOWN RISK is `still`, which is adversative in *"it is still better
than"* and temporal in *"he's still playing"*. Every occurrence in the four
clips is the adversative one, and there is one of them. A temporal `still`
in front of a candidate would cost that clip a boom, which is the safe
direction — but if a clip ever comes back with no booms and this is why, the
log says which word did it.

It is a FILTER, applied before the ranking. A gated candidate is DROPPED,
never nudged, on the standing rule that a punch moved off its peak marks
nothing.
"""

from __future__ import annotations

import re

# A connective that makes what PRECEDES it the subordinate half.
ADVERSATIVE = frozenset({
    "but", "though", "although", "however", "yet", "still", "anyway",
    "regardless", "nonetheless", "nevertheless",
})
ADDITIVE = frozenset({
    "also", "either", "besides", "furthermore", "moreover", "plus",
})

# How far ahead to look. Measured invariant over 3-12; 6 is about one clause
# and sits in the middle of the plateau rather than at an edge.
LOOK_AHEAD = 6


def _bare(w: str) -> str:
    return re.sub(r"[^a-z']", "", (w or "").lower())


def demoter_at(words: list[str], i: int) -> str | None:
    """The connective starting at `i`, or None.

    `as well` is matched as a bigram and only when it is NOT `as well as`,
    which is a comparison rather than an additive.
    """
    w = _bare(words[i]) if 0 <= i < len(words) else ""
    if w in ADVERSATIVE or w in ADDITIVE:
        return w
    if w == "as" and i + 1 < len(words) and _bare(words[i + 1]) == "well":
        if i + 2 >= len(words) or _bare(words[i + 2]) != "as":
            return "as well"
    return None


def demoted(words: list[str], i: int, look: int = LOOK_AHEAD
            ) -> tuple[str, int] | None:
    """Is the word at `i` inside a clause that a connective is about to
    demote? Returns (the connective, how many words ahead) or None.

    Only FORWARD. A connective behind the word promotes it — *"but you HAVE
    the freedom"* makes "have" the nucleus — so looking both ways would
    invert the rule.
    """
    for j in range(i, min(i + look + 1, len(words))):
        d = demoter_at(words, j)
        if d:
            return d, j - i
    return None


def word_at(times: list[float], t: float) -> int:
    """Index of the word whose start is nearest `t`. The caller's times and
    `t` must be in the same frame — both CUT seconds, here."""
    if not times:
        return -1
    return min(range(len(times)), key=lambda k: abs(times[k] - t))


def gate(moment: float, times: list[float], words: list[str],
         look: int = LOOK_AHEAD) -> tuple[str, int, str] | None:
    """None if the moment may carry a boom; otherwise why it may not."""
    i = word_at(times, moment)
    if i < 0:
        return None
    hit = demoted(words, i, look)
    if not hit:
        return None
    return hit[0], hit[1], words[i]
