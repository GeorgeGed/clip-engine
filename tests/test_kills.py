import json

import numpy as np

from engine import kills
from pipeline import core


def test_streaks_split_on_gap_and_keep_three_or_more():
    t = [100, 102, 118, 400, 401, 402, 403, 900, 905]
    assert kills.streaks(t) == [
        {"start": 100, "end": 118, "kills": 3},
        {"start": 400, "end": 403, "kills": 4},
    ]


def test_no_marker_no_kills():
    assert kills.own_kills_in_frame(np.zeros((kills.H, kills.W, 3), np.uint8)) == []


def test_a_streak_with_team_tags_in_the_feed_is_a_broadcast(monkeypatch):
    tags = {100: ["FS NETWORK", "GE Cleve", "FS Packet", "T1 ays"],
            400: ["100T Asuna", "T1 Meteor", "FUT xeus"]}
    monkeypatch.setattr(kills, "tag_pairs", lambda path, s: tags[s["start"]])
    got = kills.multikills("v.mp4", [100, 101, 102, 400, 401, 402])
    assert [(s["start"], s["kills"]) for s in got] == [(100, 3)]


def test_kill_clips_rank_as_frag_with_lead_and_tail(tmp_path, monkeypatch):
    monkeypatch.setattr(kills, "tag_pairs", lambda path, s: [])
    core.save_kills(tmp_path, [5460.5, 5462, 5462.5, 5466.5, 9000, 9001, 9002, 9003, 9004])
    c = core._kill_clips(tmp_path)
    assert [x["kills"] for x in c] == [4, 5]
    four, ace = c
    assert four["genre"] == "frag" and four["has_clip"]
    assert four["in_point"] == 5460.5 - core.KILL_LEAD
    assert four["out_point"] == 5466.5 + core.KILL_TAIL
    assert four["subject"].startswith("4K")
    assert ace["subject"].startswith("ACE") and ace["strength"] == core.ACE_STRENGTH
    assert json.loads((tmp_path / "kills.json").read_text())["kills"][0] == 5460.5


def test_kill_clips_take_three_of_ten_or_five_when_strong():
    talk = [{"n": f"t{i}"} for i in range(9)]
    threes = [{"kills": 3, "n": f"k{i}"} for i in range(6)]
    assert [c["n"] for c in core._pick(threes + talk, 10)] == \
        ["k0", "k1", "k2"] + [f"t{i}" for i in range(7)]
    mixed = [{"kills": k, "n": f"k{i}"} for i, k in enumerate([5, 4, 4, 4, 3, 4, 4])]
    assert [c["n"] for c in core._pick(mixed + talk, 10)] == \
        ["k0", "k1", "k2", "k3", "k5"] + [f"t{i}" for i in range(5)]
    few = [c["n"] for c in core._pick(threes + talk[:2], 6)]
    assert few == ["k0", "k1", "k2", "k3", "t0", "t1"]


def test_no_kills_file_no_kill_clips(tmp_path):
    assert core._kill_clips(tmp_path) == []
