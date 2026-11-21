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


def test_unknown_channel_uses_house_defaults():
    ch = core.channel_for({"uploader_id": "Someone_Else", "uploader": "Someone Else"})
    assert ch["name"] == "someone_else" and ch["handle"] == "Someone Else"
    assert ch["permission"] == "operator" and ch["seam"] == 0.4 and ch["cam"]


def test_vod_without_uploader_is_refused():
    with pytest.raises(ValueError):
        core.channel_for({})


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
    # chat on, its mode left to engine.chat_reaction; drawn natively on Modal
    assert d["clip"]["chat_mode"] is None and d["clip"]["stories"] == "off"
    assert d["clip"]["caption_font"] == "baloo"
    assert (d["clip"]["caption_fill"], d["clip"]["caption_emph"]) == ("cream", "lime")
    assert d["channel"]["vod_id"] == "123" and "twitch" not in d["channel"]
    from engine.clipspec import load
    load(p)
    ranked[0]["genre"] = "frag"
    (p,) = core.specs(tmp_path, ranked, ch, "123", tl, caption_fill="white", caption_emph="red")
    assert json.loads(p.read_text())["clip"]["chat_mode"] == "off"
    assert load(p)[0].caption_fill == "white" and load(p)[0].caption_emph == "red"


def test_a_renumbered_clip_forgets_what_was_cached_under_its_number(tmp_path):
    old = [{"in_point": 10.0, "out_point": 40.0}, {"in_point": 100.0, "out_point": 130.0},
           {"in_point": 200.0, "out_point": 260.0}]
    (tmp_path / "ranked.json").write_text(json.dumps(old))
    for d in ("words", "popups", "specs", "clips_1080", "photos", "overlays_01", "overlays_02"):
        (tmp_path / d).mkdir()
    for n in ("01", "02", "03"):
        (tmp_path / "words" / f"{n}.json").write_text("{}")
        (tmp_path / "popups" / f"{n}.json").write_text("[]")
        (tmp_path / f"chat_{n}.json").write_text("[]")
        (tmp_path / "specs" / f"{n}.json").write_text("{}")
        (tmp_path / "specs" / f"{n}.log").write_text("")
    (tmp_path / "clips_1080" / "02_0h01m40s_x.mp4").write_text("")
    (tmp_path / "photos" / "stories_02.json").write_text("[]")
    (tmp_path / "overlays_02" / "keeps.json").write_text("[]")
    (tmp_path / "titles.json").write_text(json.dumps({"1": {"options": []}, "2": {"options": []}}))
    new = [old[0], {"in_point": 300.0, "out_point": 330.0}]
    assert core.forget_renumbered(tmp_path, new) == [2]
    assert (tmp_path / "words" / "01.json").exists() and (tmp_path / "overlays_01").exists()
    assert not (tmp_path / "words" / "02.json").exists()
    assert not (tmp_path / "popups" / "02.json").exists()
    assert not (tmp_path / "chat_02.json").exists()
    assert not list((tmp_path / "specs").glob("02.*"))
    assert not list((tmp_path / "clips_1080").glob("02_*"))
    assert not (tmp_path / "photos" / "stories_02.json").exists()
    assert not (tmp_path / "overlays_02").exists()
    assert json.loads((tmp_path / "titles.json").read_text()).keys() == {"1"}
    assert (tmp_path / "words" / "03.json").exists()


def test_a_first_run_forgets_every_number(tmp_path):
    assert core.forget_renumbered(tmp_path, [{"in_point": 1.0, "out_point": 2.0}]) == [1]
