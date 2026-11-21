"""engine/facts: the sentences a plan is written against."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import facts as fx  # noqa: E402


def _w(t, a, b):
    return {"text": t, "start": a, "end": b}


def _utt(*words):
    return [{"start": words[0]["start"], "end": words[-1]["end"],
             "text": " ".join(w["text"] for w in words), "words": list(words)}]


def test_a_sentence_ends_on_punctuation_or_a_pause():
    u = _utt(_w("he", 0.0, 0.2), _w("left.", 0.2, 0.5), _w("then", 0.55, 0.8),
             _w("silence", 0.8, 1.2), _w("again", 2.0, 2.3))
    s = fx.sentences(u)
    assert [x["text"] for x in s] == ["he left.", "then silence", "again"]
    assert [x["id"] for x in s] == ["s1", "s2", "s3"]
    assert (s[1]["start"], s[1]["end"]) == (0.55, 1.2)


def test_an_unpunctuated_run_splits_at_its_widest_pause_without_slivers():
    ws, t = [], 0.0
    for i in range(80):                      # 80 words, ~24s, tiny gaps
        gap = 0.3 if i == 40 else 0.02
        ws.append(_w(f"w{i}", t, t + 0.28))
        t += 0.28 + gap
    s = fx.sentences(_utt(*ws))
    assert len(s) >= 3
    assert all(x["end"] - x["start"] <= fx.LONG_S for x in s)
    assert all(x["end"] - x["start"] >= 0.3 * 9 for x in s)
    assert any(x["text"].endswith("w40") for x in s)


def test_slice_words_rebases_to_the_in_point():
    u = [{"words": [_w("before", 9.0, 9.5), _w("in", 10.2, 10.5), _w("out", 20.0, 21.0)]}]
    got = fx.slice_words(u, 10.0, 15.0)
    assert [w["text"] for w in got[0]["words"]] == ["in"]
    assert got[0]["words"][0]["start"] == 0.2


def test_quiet_stretches_and_chat_are_in_clip_seconds():
    u = _utt(_w("a", 0.0, 0.5), _w("b", 2.0, 2.4))
    assert fx.quiet(u) == [[0.5, 2.0]]
    spikes = [{"chat": {"t": 112.0, "count": 50, "baseline": 10, "laugh": 0.5, "hype": 0.1}},
              {"chat": {"t": 300.0}}]
    assert [c["t"] for c in fx.chat_near(spikes, 100.0, 130.0)] == [12.0]


def test_no_audio_means_no_speaker_label_and_quiet_voices_are_other():
    words = [_w(f"x{i}", i * 0.5, i * 0.5 + 0.4) for i in range(16)]
    u = _utt(*words[:8]) + [{"start": 4.0, "end": 7.9, "text": "", "words": words[8:]}]
    for w in words[7:8]:
        w["text"] += "."
    s = fx.sentences(u)
    fx.speakers(s, u, None)
    assert all("speaker" not in x for x in s)
    db = np.full(int(8.5 / 0.01), -20.0)
    db[int(4.0 / 0.01):] = -40.0             # the second sentence is 20 dB under
    fx.speakers(s, u, db)
    assert [x["speaker"] for x in s] == ["streamer", "other"]


def test_render_shows_ids_times_and_speakers():
    f = fx.build({"in_point": 100.0, "out_point": 103.0, "genre": "take", "subject": "s"},
                 [{"words": [_w("hello.", 100.0, 100.5), _w("world", 101.0, 101.5)]}],
                 streamer="FNS")
    txt = fx.render(f)
    assert "s1 [   0.0-   0.5]  hello." in txt and "s2 [" in txt and "STREAMER: FNS" in txt
