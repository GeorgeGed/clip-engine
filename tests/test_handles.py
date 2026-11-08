"""A handle that is also an ordinary English word must not reach the screen.

`engine/handles.py` exists because a delivered clip's captions read "Psalm"
where FNS said s0m. Its stated rule is exact matches only, no fuzzy matching,
because "a fuzzy matcher turns an ordinary word into a real person's name
eventually, and that is the worst thing this pipeline can do."

THE RULE WAS NOT ENOUGH, AND THE MIRROR-IMAGE BUG SHIPPED. `load()` adds every
roster handle as its own alias so casing can be corrected, and 123 of the 599
resulting keys are ordinary English words — `after` is the player AfteR, `less`
is Less, `life` is Life, `texture` is t3xture, `tick` is TcK, `rose` is Rosé.
Exactness does not help: `after` IS an exact match for AfteR's own handle. Two
delivered clips carried it, and the build logs name them —

    fns-08: 4 caption(s) corrected: 'after'->AfteR, ...
    fns-12: 1 caption(s) corrected: 'life'->Life

so a caption read "AfteR the match" and another "Life" where he said "life".

This file is the gate. Against the code as it stood every case in
`test_ordinary_words_are_left_alone` fails; against the fix they pass while
`test_confirmed_garbles_still_apply` keeps the original bug fixed.

Run: .venv/bin/python tests/test_handles.py
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import handles                                  # noqa: E402

FAILURES: list[str] = []


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def test_ordinary_words_are_left_alone():
    """Each of these is a real VALORANT handle AND an ordinary English word, so
    it is not applied from the token alone. The right-hand side is what the old
    code produced."""
    for word, was in [
        ("after", "AfteR"),          # a preposition. The one that shipped.
        ("less", "Less"),
        ("life", "Life"),            # the other one that shipped
        ("texture", "t3xture"),      # "the texture of the game"
        ("tick", "TcK"),             # "that tick"
        ("rose", "Rosé"),
        ("key", "KEY"),
        ("net", "neT"),
        ("master", "Master"),
        ("happy", "Happy"),
        ("cloud", "Cloud"),
        ("rain", "Rain"),
        ("heat", "heat"),
        ("exit", "ExiT"),
        ("knight", "Knight"),
        ("spring", "Spring"),
        ("seven", "seven"),
        ("solo", "solo"),
        ("nothing", "nothing"),
        ("something", "something"),
        ("forsaken", "f0rsakeN"),
        ("narrate", "N4RRATE"),
        ("destroyer", "destroyeR"),
    ]:
        got = handles.fix(word)
        check(f"{word!r} is left alone", got == word,
              f"became {got!r}" + (f" (old code: {was!r})" if got != word else ""))


def test_in_a_sentence():
    """The real failure is mid-sentence, where nobody is looking at one token."""
    for src in [
        "after the match he said nothing",
        "that is less of a problem than the texture of the game",
        "every tick of the spike timer",
        "a rose by any other name",
        "the key is that life after a loss is still a life",
    ]:
        got = handles.fix(src)
        check(f"unchanged: {src!r}", got == src, f"became {got!r}")


def test_confirmed_garbles_still_apply():
    """Denying the ambiguous class must not undo the bug this module exists
    for. `psalm` is an English word AND a confirmed garble, and the confirmed
    list wins."""
    for src, want in [
        ("psalm", "s0m"),            # George flagged this one on fns-07
        ("psalms", "s0m"),
        ("leviathan", "Leviatán"),   # and the accent survives
        ("paper x", "PRX"),
        ("hanz", "Hent"),
    ]:
        got = handles.fix(src)
        check(f"{src!r} -> {want!r}", got == want, f"got {got!r}")


def test_unambiguous_handles_still_apply():
    """Nothing about this rule touches a handle that is not an English word."""
    for src, want in [
        ("som", "s0m"),
        ("valen", "valyn"),          # Jacob Batio, G2
        ("jing gee", "Jinggg"),
        ("sad hawk", "saadhak"),
        ("john cutie", "johnqt"),
    ]:
        got = handles.fix(src)
        check(f"{src!r} -> {want!r}", got == want, f"got {got!r}")


def test_the_deny_list_is_vendored_not_computed():
    """It must not depend on the host having /usr/share/dict/words — two
    machines deciding different things about a name on screen is the
    'same number derived twice' defect with a person's name attached."""
    cfg = json.loads((ROOT / "config" / "handle_garbles.json").read_text(encoding="utf-8"))
    amb = cfg.get("ambiguous_with_english")
    check("the ambiguous list is checked in", isinstance(amb, list) and len(amb) > 50,
          f"{len(amb) if isinstance(amb, list) else amb}")
    src = (ROOT / "engine" / "handles.py").read_text(encoding="utf-8")
    check("handles.py does not read a system dictionary at load time",
          "/usr/share/dict" not in src)
    # The override path has to be LIVE, not just present: at least one
    # confirmed garble must also be on the deny list, or nothing proves that
    # `garbles` actually beats it. `psalm` and `leviathan` are both ordinary
    # words and both confirmed, so they are that proof. (`psalms` is not on
    # the list because plural forms are mostly absent from the dictionary, so
    # it was never at risk — which is why this checks for ANY, not ALL.)
    overlap = sorted(set(amb or []) & {k.lower() for k in (cfg.get("garbles") or {})})
    check("a confirmed garble is also on the deny list, so the override is exercised",
          bool(overlap), f"overlap: {overlap}")


def test_a_missing_deny_list_raises():
    """Fail LOUD, not open. Swallowing a read error here restores the defect,
    and the module's own note says a wrong name on screen is the worst thing
    this pipeline can do — so it must not be reachable by a config glitch."""
    import re
    saved_map, saved_path = handles._MAP, handles.GARBLES
    try:
        handles._MAP = None
        handles.GARBLES = ROOT / "config" / "handle_garbles.json"
        cfg = json.loads(handles.GARBLES.read_text(encoding="utf-8"))
        cfg.pop("ambiguous_with_english", None)
        tmp = ROOT / "config" / ".handle_garbles.test.json"
        tmp.write_text(json.dumps(cfg), encoding="utf-8")
        handles.GARBLES = tmp
        raised = False
        try:
            handles.load()
        except RuntimeError as exc:
            raised = "ambiguous_with_english" in str(exc)
        check("a config with no deny list raises rather than loading", raised)
        tmp.unlink(missing_ok=True)
    finally:
        handles._MAP, handles.GARBLES = saved_map, saved_path
        re  # noqa: B018  keep the import used


if __name__ == "__main__":
    print(__doc__.strip().splitlines()[0])
    print()
    for fn in (test_ordinary_words_are_left_alone,
               test_in_a_sentence,
               test_confirmed_garbles_still_apply,
               test_unambiguous_handles_still_apply,
               test_the_deny_list_is_vendored_not_computed,
               test_a_missing_deny_list_raises):
        print(fn.__name__)
        fn()
        print()
    if FAILURES:
        sys.exit(f"{len(FAILURES)} failed: {FAILURES}")
    print("every check passes")
