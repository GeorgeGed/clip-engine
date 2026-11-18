"""engine.chat_spikes and pipeline.core._with_chat."""
from engine import chat_spikes as cs
from pipeline.core import _budget, _with_chat


def _chat(duration, rate, bursts):
    msgs = [{"t": i / rate, "text": "hello"} for i in range(int(duration * rate))]
    for t, n, text in bursts:
        msgs += [{"t": t + k * (cs.BIN / n) * 0.9, "text": text} for k in range(n)]
    return sorted(msgs, key=lambda m: m["t"])


def test_a_laughing_burst_is_the_top_spike():
    msgs = _chat(1800, 0.5, [(600, 40, "KEKW"), (1200, 40, "yes")])
    sp = cs.spikes(msgs, 1800)
    assert [round(s["t"]) for s in sp[:2]] == [605, 1205]
    assert sp[0]["laugh"] > 0.8 and sp[1]["laugh"] == 0.0


def test_steady_chat_has_no_spikes():
    assert cs.spikes(_chat(1800, 1.0, []), 1800) == []


def test_a_burst_under_the_absolute_floor_is_ignored():
    assert cs.spikes(_chat(1800, 0.02, [(600, 4, "LOL")]), 1800) == []


def _spike(t, score):
    return {"start": t - cs.LEAD, "end": t + cs.TAIL, "hint": f"spike {t}",
            "chat": {"t": t, "score": score}}


def test_spike_inside_a_voice_region_becomes_its_hint():
    regs = [{"start": 100.0, "end": 200.0, "peak": 0.8, "mean": 0.6}]
    out = _with_chat(regs, [_spike(210.0, 0.7)])
    assert len(out) == 1 and out[0]["hint"] == "spike 210.0"
    assert "chat" not in regs[0]


def test_spike_no_voice_region_covers_is_its_own_region():
    regs = [{"start": 100.0, "end": 200.0, "peak": 0.8, "mean": 0.6}]
    out = _with_chat(regs, [_spike(900.0, 0.5)])
    assert len(out) == 2 and out[1]["start"] == 900.0 - cs.LEAD


def test_budget_takes_chat_regions_first_then_voice_order():
    voice = [{"start": float(i), "end": i + 1.0} for i in range(50)]
    chat = [{"start": 900.0, "end": 990.0, "chat": {"score": 0.4}},
            {"start": 800.0, "end": 890.0, "chat": {"score": 0.9}}]
    got = _budget(voice + chat, 5)
    assert [r["start"] for r in got] == [800.0, 900.0, 0.0, 1.0, 2.0]
