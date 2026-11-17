"""pipeline/core.py: the rights gate, the transcript slicing, the specs."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import core  # noqa: E402


def test_allowlisted_channel_is_found():
    ch = core.channel_for({"uploader_id": "GoFNS"})
    assert ch["name"] == "fns" and ch["permission"] in core.RIGHTS_OK


def test_unknown_channel_is_refused():
    with pytest.raises(PermissionError, match="not on the allowlist"):
        core.channel_for({"uploader_id": "someone_else"})


def _job(tmp_path):
    utt = [{"start": 99.0, "end": 101.5, "text": "before and inside",
            "words": [{"start": 99.0, "end": 99.5, "text": "before", "prob": 1},
                      {"start": 100.2, "end": 100.6, "text": "inside", "prob": 1}]},
           {"start": 104.0, "end": 106.0, "text": "tail word",
            "words": [{"start": 104.0, "end": 104.4, "text": "tail", "prob": 1},
                      {"start": 105.9, "end": 106.3, "text": "word", "prob": 1}]}]
    (tmp_path / "transcript.json").write_text(json.dumps({"utterances": utt}))
    return [{"in_point": 100.0, "out_point": 105.0, "subject": "s", "claim": "c",
             "strength": 0.8}]


def test_clip_words_rebases_and_clips_to_the_section(tmp_path):
    ranked = _job(tmp_path)
    core.clip_words(tmp_path, ranked)
    w = json.loads((tmp_path / "words" / "01.json").read_text())
    words = [x for u in w["utterances"] for x in u["words"]]
    assert [x["text"] for x in words] == ["inside", "tail"]   # 'word' ends past out+TAIL
    assert words[0]["start"] == pytest.approx(0.2)
    assert w["offset"] == 100.0


def test_specs_take_the_best_title(tmp_path):
    ranked = _job(tmp_path)
    tl = {"1": {"options": [{"title": "a", "keyword": "a", "emoji": "x", "angle": "claim"},
                            {"title": "Best one", "keyword": "Best", "emoji": "🔥",
                             "angle": "stakes"}], "best": 1}}
    ch = core.channel_for({"uploader_id": "gofns"})
    (p,) = core.specs(tmp_path, ranked, ch, "123", tl)
    d = json.loads(p.read_text())
    assert d["clip"]["title"] == "Best one" and d["clip"]["title_keyword"] == "Best"
    assert d["clip"]["out_point"] == 5.0 and d["clip"]["region"] == [100.0, 106.0]
    assert d["clip"]["chat_mode"] == "off" and d["clip"]["stories"] == "off"
    assert d["channel"]["vod_id"] == "123" and "twitch" not in d["channel"]
    from engine.clipspec import load
    load(p)
