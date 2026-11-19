from engine.tighten import Span, remap_card


def test_a_card_past_the_out_point_is_dropped_not_stretched_from_zero():
    keep = [Span(0.0, 24.0)]
    assert remap_card(24.28, 24.6, keep) is None


def test_a_card_straddling_the_out_point_is_clamped():
    assert remap_card(23.78, 24.28, [Span(0.0, 24.0)]) == (23.78, 24.0)


def test_a_card_starting_in_a_removed_span_starts_at_the_next_keep():
    keep = [Span(0.0, 5.0), Span(6.0, 10.0)]
    assert remap_card(5.5, 7.0, keep) == (5.0, 6.0)
