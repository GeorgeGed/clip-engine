"""engine/twitch_chat: a transient Twitch error is retried; a rotated hash is not."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import twitch_chat as tc  # noqa: E402

OK = [{"data": {"video": {"comments": {"edges": []}}}}]
BUSY = [{"errors": [{"message": "service error", "path": ["video", "comments"]}]}]
GONE = [{"errors": [{"message": "PersistedQueryNotFound"}]}]


def _replies(monkeypatch, *replies):
    calls = []

    def post(body):
        calls.append(body)
        return replies[min(len(calls), len(replies)) - 1]
    monkeypatch.setattr(tc, "_post", post)
    monkeypatch.setattr(tc.time, "sleep", lambda s: None)
    return calls


def test_a_service_error_is_retried(monkeypatch):
    calls = _replies(monkeypatch, BUSY, BUSY, OK)
    assert tc._page("1", 0)["edges"] == [] and len(calls) == 3


def test_a_service_error_that_persists_still_raises(monkeypatch):
    calls = _replies(monkeypatch, BUSY)
    with pytest.raises(RuntimeError, match="service error"):
        tc._page("1", 0)
    assert len(calls) == tc.TRIES


def test_a_rotated_hash_is_not_retried(monkeypatch):
    calls = _replies(monkeypatch, GONE)
    with pytest.raises(RuntimeError, match="PersistedQueryNotFound"):
        tc._page("1", 0)
    assert len(calls) == 1


def test_paging_stops_at_the_end_of_the_vod(monkeypatch):
    asked = []

    def page(video_id, off):
        asked.append(off)
        if off > 4248:
            raise RuntimeError("GQL: service error")
        return {"edges": []}
    monkeypatch.setattr(tc, "_page", page)
    monkeypatch.setattr(tc.time, "sleep", lambda s: None)
    assert tc.fetch("2920606211", 4161.7, 4245.5, duration=4248) == []
    assert max(asked) < 4248
