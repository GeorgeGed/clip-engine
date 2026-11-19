"""engine.resolve_captions.snap_words: stretched words move onto their speech."""
import numpy as np

from engine.resolve_captions import snap_words

HOP = 0.01


def _db(spans, total=5.0):
    db = np.full(int(total / HOP), -60.0)
    for a, b in spans:
        db[int(a / HOP):int(b / HOP)] = -25.0
    return db


def test_glued_word_moves_to_where_it_is_said():
    db = _db([(0.0, 1.0), (2.4, 2.7)])
    words = [{"text": "away", "start": 0.6, "end": 1.0},
             {"text": "and", "start": 1.0, "end": 2.7}]
    out = snap_words(words, db, HOP)
    assert out[0] is words[0]
    assert abs(out[1]["start"] - 2.2) < 0.02


def test_word_held_over_silence_ends_with_its_speech():
    db = _db([(0.0, 0.3)])
    words = [{"text": "is", "start": 0.0, "end": 1.5}]
    out = snap_words(words, db, HOP)
    assert out[0]["start"] == 0.0 and out[0]["end"] < 0.5


def test_short_or_continuous_words_are_untouched():
    db = _db([(0.0, 3.0)])
    words = [{"text": "a", "start": 0.0, "end": 0.4},
             {"text": "long", "start": 0.4, "end": 2.0}]
    out = snap_words(words, db, HOP)
    assert out[0] is words[0] and out[1] is words[1]
