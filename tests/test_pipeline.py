"""pipeline/core.py: the rights gate, the transcript slicing, the specs."""
import json
import re
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


def _planning_job(tmp_path):
    words, utt = [], []
    for k, a in enumerate((100.0, 200.0, 300.0)):
        ws = [{"start": a + i, "end": a + i + 0.6, "text": f"word{'abc'[k]}{'abcdefghi'[i]}" + ("." if i % 3 == 2 else ""),
               "prob": 1} for i in range(9)]
        utt.append({"start": a, "end": a + 9, "text": "", "words": ws})
    (tmp_path / "transcript.json").write_text(json.dumps({"utterances": utt}))
    clips = [{"in_point": a, "out_point": a + 9, "genre": "take", "subject": f"clip {k}",
              "strength": 0.9 - k / 10} for k, a in enumerate((100.0, 200.0, 300.0))]
    (tmp_path / "clips.json").write_text(json.dumps(clips))
    return clips


class _Planner:
    """Drops 'clip 0', plans the rest; counts calls."""
    def __init__(self):
        from types import SimpleNamespace
        self.calls = 0
        self.messages = SimpleNamespace(create=self.create)

    def create(self, **kw):
        from types import SimpleNamespace
        self.calls += 1
        facts = kw["messages"][0]["content"]
        if "clip 0" in facts:
            reply = {"drop": "no payoff"}
        else:
            reply = {"logline": "a story", "beats": [
                {"from": "s1", "to": "s2", "role": "setup", "feeling": "curiosity", "treatment": "none"},
                {"from": "s3", "to": "s3", "role": "payoff", "feeling": "outrage", "treatment": "none"}],
                "payoff_words": [re.search(r"s3\b[^\n]*?\b(word[a-z]+)", facts).group(1)]}
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(reply))])


def test_a_dropped_clip_frees_its_slot_for_the_next(tmp_path, monkeypatch):
    _planning_job(tmp_path)
    fake = _Planner()
    monkeypatch.setattr(core, "_client", lambda: fake)
    found = core.plan(tmp_path, 2, {"name": "fns"}, log=lambda *a: None)
    assert [c["subject"] for c in found] == ["clip 1", "clip 2"]
    assert all(c["plan"]["logline"] == "a story" for c in found)
    assert found[0]["plan"]["beats"][1]["start"] == 0.0 + 6.0
    assert fake.calls == 3
    again = core.plan(tmp_path, 2, {"name": "fns"}, log=lambda *a: None)
    assert fake.calls == 3 and [c["subject"] for c in again] == ["clip 1", "clip 2"]


def test_a_planner_fault_ships_the_clip_unplanned(tmp_path, monkeypatch):
    _planning_job(tmp_path)

    class Broken:
        def __init__(self):
            from types import SimpleNamespace
            self.messages = SimpleNamespace(create=self.create)

        def create(self, **kw):
            raise ConnectionError("down")
    monkeypatch.setattr(core, "_client", Broken)
    found = core.plan(tmp_path, 2, {"name": "fns"}, log=lambda *a: None)
    assert len(found) == 3 and not any("plan" in c for c in found)


def test_specs_carry_the_plan_and_titles_use_its_logline(tmp_path):
    ranked = _job(tmp_path)
    ranked[0]["plan"] = {"logline": "the story", "beats": [
        {"start": 0.0, "end": 2.0, "text": "setup line", "role": "setup", "treatment": "none"},
        {"start": 2.0, "end": 5.0, "text": "the payoff line", "role": "payoff", "treatment": "none"}]}
    core.clip_words(tmp_path, ranked)
    seen = {}

    def fake(todo, handle):
        seen.update(todo[0])
        return {"1": {"options": [{"title": "T", "keyword": "T", "emoji": "x"}], "best": 0}}
    import engine.titler
    orig = engine.titler.suggest_many
    engine.titler.suggest_many = fake
    try:
        tl = core.titles(tmp_path, ranked, handle="FNS")
    finally:
        engine.titler.suggest_many = orig
    assert seen["subject"] == "the story" and seen["claim"] == "the payoff line"
    ch = core.channel_for({"uploader_id": "GoFNS"})
    sp = core.specs(tmp_path, ranked, ch, "1", tl)
    clip = json.loads(sp[0].read_text())["clip"]
    assert clip["plan"]["logline"] == "the story" and clip["notes"] == "Plan: the story"

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
