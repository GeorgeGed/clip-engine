"""The nucleus gate, against George's six verdicts and its own edges.

The six are the only labels that exist for boom placement, so they are the
whole test set and they are quoted verbatim from the clips. The point of the
W sweep is that this rule has a PLATEAU where the five refuted metrics had a
knife edge — sustain separated these same six at exactly one window and
threshold pair and nowhere else, which is how it got as far as a conclusion
before the sweep caught it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from engine import nucleus

fails: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'pass' if cond else 'FAIL'}  {name}"
          f"{'  — ' + detail if detail and not cond else ''}")
    if not cond:
        fails.append(name)


# (words, index of the moment's word, may it carry a boom, what it is)
CASES = [
    # --- George's six, verbatim from the cuts -------------------------------
    ("for teams that succeed they had prior issues as well that's why you see",
     "prior", False, "clip 16 4.84, rejected"),
    ("sometimes teams are dead going into whole ass events and end up making "
     "runs for all you know", "end", True, "clip 16 21.92, 'perfect'"),
    ("not sitting here like i don't want to hear no complaints about oh i'm not",
     "don't", True, "clip 12 2.87, accepted"),
    ("it i don't want to hear it sit there and make a fucking team stay humble",
     "just", True, "clip 12 12.87, accepted"),      # 'just' absent -> nearest
    ("don't get paid for a couple months but you have the freedom to choose",
     "couple", False, "clip 12 27.25, rejected"),
    ("ping issues cheaters like if a player has an issue he has to find out",
     "cheaters", True, "clip 6 9.30, he named this one"),
    # --- the edges the rule claims ----------------------------------------
    ("it is still better than locking players out of franchise forever",
     "is", False, "'still' is adversative here — clip 6's gated 34.19"),
    ("but you have the freedom to choose your own teammates",
     "have", True, "a connective BEHIND promotes; only forward demotes"),
    ("he is as well known as anyone in the scene",
     "well", True, "'as well as' is a comparison, not an additive"),
    ("they had prior issues as well", "issues", False, "'as well' at the end"),
]


def run() -> int:
    print("the six verdicts, and the edges")
    for text, word, allow, what in CASES:
        words = text.split()
        try:
            i = words.index(word)
        except ValueError:
            i = 0
        g = nucleus.demoted(words, i)
        got = g is None
        ok(f"{what:46} {'keep' if allow else 'drop'}", got == allow,
           f"gate said {'keep' if got else 'drop on ' + repr(g[0])}")

    print("\na plateau, not a knife edge — the test sustain failed")
    for look in (3, 4, 5, 6, 7, 8, 10, 12):
        good = 0
        for text, word, allow, _w in CASES[:6]:
            words = text.split()
            i = words.index(word) if word in words else 0
            good += (nucleus.demoted(words, i, look) is None) == allow
        ok(f"W={look:<2} reproduces all six", good == 6, f"{good}/6")

    print("\nthe bigram")
    ok("'as well' is a demoter",
       nucleus.demoter_at(["as", "well", "that's"], 0) == "as well")
    ok("'as well as' is not",
       nucleus.demoter_at(["as", "well", "as"], 0) is None)
    ok("'as' alone is not", nucleus.demoter_at(["as", "far"], 0) is None)
    ok("punctuation does not hide one",
       nucleus.demoter_at(["But,"], 0) == "but")
    ok("case does not either", nucleus.demoter_at(["HOWEVER"], 0) == "however")

    print("\nit only ever removes")
    words = "a b c but d e f".split()
    ok("a clause with no connective is untouched",
       nucleus.demoted("a b c d e f g".split(), 0) is None)
    ok("one ahead gates", nucleus.demoted(words, 0) is not None)
    ok("one behind does not", nucleus.demoted(words, 4) is None)
    ok("out of range is safe", nucleus.demoter_at(["x"], 5) is None)
    ok("empty is safe", nucleus.demoted([], 0) is None)
    ok("word_at on empty is safe", nucleus.word_at([], 1.0) == -1)

    print()
    print(f"{'ALL PASS' if not fails else str(len(fails)) + ' FAILED'}")
    for f in fails:
        print("  -", f)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(run())
