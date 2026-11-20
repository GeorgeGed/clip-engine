from engine.review import apply_fixes, sentence_ends, to_file, transcript
from engine.tighten import Span


def W(text, start, end):
    return {"text": text, "start": start, "end": end}


WORDS = [{"words": [W("so", 0.4, 0.6), W("uh", 0.7, 0.9), W("he", 4.0, 4.2), W("cheated.", 4.3, 4.9),
                    W("and", 5.0, 5.2), W("then", 5.3, 5.5), W("they", 5.6, 5.8), W("banned", 5.9, 6.3),
                    W("him", 6.4, 6.6)]},
         {"words": [W("forever", 30.0, 30.5), W("wild", 30.6, 31.0)]},
         {"words": [W("anyway", 55.0, 55.4)]}]
CLIP = {"in_point": 0.0, "out_point": 60.0, "title": "He got BANNED", "title_keyword": "BANNED"}
WHOLE = [Span(0.0, 60.0)]
CUT = [Span(0.0, 10.0), Span(29.0, 60.0)]   # the render cut 10-29 out as dead air


def test_sentences_end_on_a_pause_punctuation_or_the_utterance():
    assert sentence_ends(WORDS) == [1, 3, 8, 10, 11]


def test_start_at_snaps_to_a_sentence_start_with_preroll():
    new, done = apply_fixes(CLIP, WORDS, [{"fix": "start_at", "t": 3.8}], WHOLE)
    assert new["in_point"] == 3.7 and done


def test_start_at_never_lands_mid_sentence():
    new, _ = apply_fixes(CLIP, WORDS, [{"fix": "start_at", "t": 5.4}], WHOLE)
    assert new["in_point"] == 4.7          # on "and", the sentence after "cheated."


def test_end_at_lands_on_a_sentence_end():
    new, _ = apply_fixes(CLIP, WORDS, [{"fix": "end_at", "t": 30.8}], WHOLE)
    assert new["out_point"] == 31.25       # after "wild", not after "forever"


def test_a_trim_may_not_take_more_than_half_the_clip():
    new, done = apply_fixes(CLIP, WORDS, [{"fix": "end_at", "t": 6.6}, {"fix": "start_at", "t": 55.0}], WHOLE)
    assert (new["in_point"], new["out_point"], done) == (0.0, 60.0, [])


def test_fixes_cannot_lengthen_the_clip():
    keeps = [Span(3.7, 31.25)]
    clip = dict(CLIP, in_point=3.7, out_point=31.25)
    new, done = apply_fixes(clip, WORDS, [{"fix": "end_at", "t": 80.0}, {"fix": "start_at", "t": -5}], keeps)
    assert (new["in_point"], new["out_point"], done) == (3.7, 31.25, [])


def test_judge_times_go_back_through_the_pause_cuts():
    assert to_file(11.6, CUT) == 30.6
    new, _ = apply_fixes(CLIP, WORDS, [{"fix": "end_at", "t": 12.0}], CUT)
    assert new["out_point"] == 31.25


def test_a_retitle_drops_a_keyword_it_no_longer_contains():
    new, _ = apply_fixes(CLIP, WORDS, [{"fix": "title", "text": "Cheater caught live"}], WHOLE)
    assert new["title"] == "Cheater caught live" and new["title_keyword"] is None


def test_unknown_or_malformed_fixes_are_ignored():
    new, done = apply_fixes(CLIP, WORDS, [{"fix": "zoom"}, {"fix": "start_at"}, {"fix": "end_at", "t": "x"}], WHOLE)
    assert new == CLIP and done == []


def test_transcript_is_in_clip_seconds_after_the_pause_cuts():
    assert transcript(WORDS, CUT).splitlines() == ["[0.4-6.6] so uh he cheated. and then they banned him",
                                                  "[11.0-12.0] forever wild", "[36.0-36.4] anyway"]


class _Msg:
    def __init__(self, text):
        self.content = [type("B", (), {"type": "text", "text": text})()]


def test_a_reply_wrapped_in_prose_or_a_fence_still_parses():
    from engine.review import _json
    assert _json(_Msg('Sure.\n```json\n{"verdict": "pass", "fixes": [{"t": 1}]}\n``` then {"x": 2}')) == \
        {"verdict": "pass", "fixes": [{"t": 1}]}


def test_a_malformed_reply_is_asked_again_once():
    from engine.review import _ask
    replies = iter(["no json here", '{"score": 7}'])

    class Client:
        class messages:
            @staticmethod
            def create(**_):
                return _Msg(next(replies))

    assert _ask(Client, "m", "s", [], 10) == {"score": 7}
