"""engine/plan: the validator is the contract, so it is tested hardest."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import plan as pl  # noqa: E402
from engine.tighten import Span  # noqa: E402

FACTS = {"genre": "take", "duration": 30.0, "streamer": "FNS", "subject": "", "setup": "",
         "claim": "", "consequence": "", "quiet": [], "chat": [],
         "sentences": [
             {"id": "s1", "start": 0.0, "end": 4.0, "text": "so sentinels just announced the roster"},
             {"id": "s2", "start": 4.5, "end": 12.0, "text": "and honestly tenzz is wasted there"},
             {"id": "s3", "start": 12.5, "end": 22.0, "text": "that roster needs to disband straight up"},
             {"id": "s4", "start": 22.5, "end": 30.0, "text": "like you should not lose to us"}]}


def _good():
    return {"logline": "FNS says the new Sentinels roster should disband", "drop": None,
            "beats": [
                {"from": "s1", "to": "s1", "role": "setup", "feeling": "curiosity",
                 "treatment": "banner", "banner": "Sentinels roster", "why": "names it"},
                {"from": "s2", "to": "s2", "role": "turn", "feeling": "disbelief",
                 "treatment": "card", "card": "TenZ", "why": "who is wasted"},
                {"from": "s3", "to": "s3", "role": "payoff", "feeling": "outrage",
                 "treatment": "emphasis", "words": ["disband"], "why": "the quote"},
                {"from": "s4", "to": "s4", "role": "button", "feeling": "deadpan",
                 "treatment": "none", "why": ""}]}


def test_a_good_plan_becomes_times():
    p, drop, errs = pl.validate(_good(), FACTS)
    assert errs == [] and drop is None
    assert [(b["start"], b["end"]) for b in p["beats"]] == [(0.0, 4.0), (4.5, 12.0), (12.5, 22.0), (22.5, 30.0)]
    assert p["beats"][0]["banner"] == "SENTINELS ROSTER"


def test_a_drop_is_a_drop():
    p, drop, errs = pl.validate({"drop": "two narratives", "beats": []}, FACTS)
    assert p is None and drop == "two narratives" and errs == []


def _errs(**change):
    g = _good()
    for k, v in change.items():
        i, field = k.split("__")
        g["beats"][int(i)][field] = v
    return pl.validate(g, FACTS)[2]


def test_beats_must_be_contiguous_and_cover_the_clip():
    assert any("must start at s2" in e for e in _errs(**{"1__from": "s3", "1__to": "s3"}))
    g = _good()
    g["beats"] = g["beats"][:3]
    g["beats"][2]["role"] = "payoff"
    assert any("must run to s4" in e for e in pl.validate(g, FACTS)[2])
    assert any("sentence ids" in e for e in _errs(**{"0__from": "s9"}))


def test_closed_vocabularies():
    assert any("role" in e for e in _errs(**{"0__role": "intro"}))
    assert any("feeling" in e for e in _errs(**{"0__feeling": "a mix of emotions"}))
    assert any("not allowed" in e for e in _errs(**{"3__treatment": "slowmo"}))


def test_exactly_one_payoff():
    assert any("one beat must be the payoff" in e for e in _errs(**{"2__role": "escalation"}))
    assert any("one beat must be the payoff" in e for e in _errs(**{"3__role": "payoff"}))


def test_a_card_must_name_someone_said_in_its_beat():
    assert any("not said" in e for e in _errs(**{"1__card": "Aspas"}))


def test_emphasis_words_come_from_the_beat_and_carry_meaning():
    assert any("not in this beat" in e for e in _errs(**{"2__words": ["champions"]}))
    assert any("content word" in e for e in _errs(**{"2__words": ["to"]}))
    p = pl.validate(_good(), FACTS)[0]
    p["beats"][2]["words"] = ["needs to disband"]
    assert pl.emphasis(p)[0] == {"NEEDS", "DISBAND"}


def test_a_treatment_needs_a_why_and_at_most_three_are_used():
    assert any("needs a why" in e for e in _errs(**{"0__why": ""}))
    errs = _errs(**{"3__treatment": "big_cam", "3__why": "his face"})
    assert any("at most 3" in e for e in errs)


def test_big_cam_has_a_budget_and_never_on_gameplay():
    g = _good()
    g["beats"][2] = {"from": "s3", "to": "s3", "role": "payoff", "feeling": "outrage",
                     "treatment": "big_cam", "why": "face"}
    g["beats"][1] = {"from": "s2", "to": "s2", "role": "turn", "feeling": "outrage",
                     "treatment": "big_cam", "why": "face"}
    assert any("under 40%" in e for e in pl.validate(g, FACTS)[2])
    assert any("not allowed" in e for e in pl.validate(_good(), dict(FACTS, genre="frag"))[2])


def test_and_then_is_two_clips():
    g = _good()
    g["logline"] = "FNS rants about Sentinels and then talks about lunch"
    assert any("two narratives" in e for e in pl.validate(g, FACTS)[2])


class _Client:
    def __init__(self, *replies):
        self.replies, self.seen = list(replies), []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.seen.append(kw["messages"])
        text = self.replies.pop(0)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


def test_a_failed_plan_is_sent_back_once_with_its_errors():
    bad = _good()
    bad["beats"][2]["role"] = "escalation"
    c = _Client(json.dumps(bad), json.dumps(_good()))
    r = pl.write(FACTS, client=c)
    assert r["plan"] and r["attempts"] == 2
    assert "exactly one beat must be the payoff" in c.seen[1][-1]["content"]


def test_two_failures_leave_the_clip_unplanned():
    r = pl.write(FACTS, client=_Client("not json", "still not"))
    assert r["plan"] is None and r["drop"] is None and r["errors"]


def test_treatments_reach_the_edit():
    p = pl.validate(_good(), FACTS)[0]
    keeps = [Span(0.0, 10.0), Span(14.0, 30.0)]       # 4s cut out of beat 2
    p["beats"][3]["treatment"] = "big_cam"
    assert pl.output_spans(p, "big_cam", keeps) == [(18.5, 26.0)]
    keys, spans = pl.emphasis(p)
    assert keys == {"DISBAND"} and spans == [(12.5, 22.0)]
    found = [{"name": "TenZ", "spoken": "tenzz", "at": 6.0},
             {"name": "Sentinels", "spoken": "sentinels", "at": 1.0}]
    assert [e["name"] for e in pl.allowed_popups(found, p)] == ["TenZ"]
    assert pl.allowed_popups(found, None) == []
    s = pl.summary(p)
    assert s["logline"].startswith("FNS says") and s["beats"][0] == {
        "role": "setup", "feeling": "curiosity", "treatment": "banner", "why": "names it"}


def test_the_rules_file_reaches_the_prompt():
    assert "Story first" in pl.system("take") and "big_cam" not in pl.system("frag").split("Allowed for this clip:")[1].split(".")[0]
