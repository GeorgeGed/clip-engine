"""Asserts the out-point contract: a clip keeps the line the model named.

The fault this exists for. Out-points were snapped to utterance STARTS, so
every clip stopped just before the line it named. Measured on the reviewed top
10 of FNS VOD 2905408276: all ten out-points landed exactly on an utterance
start, so all ten dropped their final line. Usually survivable; on clip 8 it
cut "You sacrifice a lot of time and you could just end up with nothing", the
whole point of the clip, and George's note was "clip ended too early".

Clip 3 proved it was the model's intent and not its mistake: its stated
consequence quoted verbatim the line the cut excluded.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from engine.tier3 import _ends, _snap_out

fails: list[str] = []


def ok(name: str, cond: bool) -> None:
    print(f"  {'pass' if cond else 'FAIL'}  {name}")
    if not cond:
        fails.append(name)


def run() -> int:
    print("deriving ends")
    starts_only = [{"start": 100.0}, {"start": 103.0}, {"start": 106.5}]
    e, real = _ends(starts_only)
    ok("derived ends are the next start", e == [103.0, 106.5, 110.5])
    ok("derived ends are flagged not real", real is False)

    withends = [{"start": 100.0, "end": 102.6}, {"start": 103.0, "end": 106.1}]
    e2, real2 = _ends(withends)
    ok("real ends are used as given", e2 == [102.6, 106.1])
    ok("real ends are flagged real", real2 is True)

    mixed = [{"start": 100.0, "end": 102.6}, {"start": 103.0}]
    ok("a single missing end makes the set derived", _ends(mixed)[1] is False)

    print("derived ends: a named start INCLUDES that line")
    s = [100.0, 103.0, 106.5]
    e, real = _ends(starts_only)
    got, okd = _snap_out(103.0, s, e, real_ends=real)
    ok("naming 103.0 keeps the line through 106.5", got == 106.5 and okd)
    got, _ = _snap_out(100.0, s, e, real_ends=real)
    ok("naming the first start keeps the first line", got == 103.0)
    got, _ = _snap_out(106.5, s, e, real_ends=real)
    ok("naming the last start keeps the last line", got == 110.5)

    print("real ends: taken literally, no over-include")
    rs = [100.0, 103.0, 106.5]
    re_ = [102.6, 106.1, 110.0]
    got, _ = _snap_out(106.1, rs, re_, real_ends=True)
    ok("naming an end ends there", got == 106.1)
    got, _ = _snap_out(102.6, rs, re_, real_ends=True)
    ok("naming the first end ends there", got == 102.6)

    print("rejecting what matches nothing")
    got, okd = _snap_out(500.0, s, e, real_ends=real)
    ok("a far-off value is kept but flagged", got == 500.0 and not okd)
    got, okd = _snap_out(None, s, e, real_ends=real)
    ok("None stays None", got is None and not okd)

    print("the regression that started it")
    # Clip 8's tail, as the small-model transcript had it.
    tail = [{"start": 6034.6}, {"start": 6037.6}, {"start": 6039.0},
            {"start": 6043.2}, {"start": 6046.1}]
    e3, real3 = _ends(tail)
    got, _ = _snap_out(6043.2, [u["start"] for u in tail], e3, real_ends=real3)
    ok(f"clip 8's payoff line is kept (out-point {got})", got == 6046.1)
    ok("and that is later than the shipped cut of 6043.2", got > 6043.2)

    print()
    print(f"{'ALL PASS' if not fails else str(len(fails)) + ' FAILED'}")
    for f in fails:
        print("  -", f)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(run())
