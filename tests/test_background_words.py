"""engine.resolve_captions.background: quieter voices are not captioned."""
import numpy as np

from engine.resolve_captions import background

HOP = 0.01


def _setup(levels):
    words, db, t = [], np.full(int(len(levels) * 0.3 / HOP) + 10, -90.0), 0.0
    for i, lv in enumerate(levels):
        words.append({"text": f"w{i}", "start": t, "end": t + 0.25})
        db[int(t / HOP):int((t + 0.25) / HOP)] = lv
        t += 0.3
    return words, db


def test_a_long_quiet_run_is_background():
    words, db = _setup([-15] * 8 + [-25] * 8 + [-15] * 4)
    bg = background(words, db, HOP)
    assert bg[8:16] == [True] * 8 and not any(bg[:8]) and not any(bg[16:])


def test_a_short_quiet_run_is_kept():
    words, db = _setup([-15] * 8 + [-25] * 3 + [-15] * 8)
    assert not any(background(words, db, HOP))


def test_a_mute_inside_a_quiet_run_joins_it():
    words, db = _setup([-15] * 8 + [-25] * 3 + [-90] * 2 + [-25] * 3 + [-15] * 4)
    assert background(words, db, HOP)[8:16] == [True] * 8
