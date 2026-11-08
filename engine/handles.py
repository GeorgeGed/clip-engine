"""Player handles in captions, spelled the way the player spells them.

George, on a delivered clip: *"FNS was saying s0m — the VALORANT player —
whereas the subtitle said Psalm, as in a Bible verse."*

This file's oldest caption rule is *preserve handle casing, acronyms, map
names — Leviatán, not Leviathan — whisper garbles these constantly*. It has
been written down since the first style pass and nothing ever enforced it.

THE LEXICON ALREADY EXISTED, in the quote desk. `config/roster.json` there
carries 444 players, and 88 of them already have the phonetic aliases
whisper produces: `sad hawk` for saadhak, `zeck in` for zekken, `john cutie`
for johnqt, `jing gee` for Jinggg, `angel` for ANGE1. Those were collected
by hand for the quote cards and are exactly what a caption needs. This reads
them rather than starting a second list.

**EXACT MATCHES ONLY.** No soundex, no edit distance, no "close enough".
The rule this desk runs on is that nothing on screen is a phrase nobody
said, and a fuzzy matcher turns an ordinary word into a player's name
eventually — `psalm` really is a word, and on a clip about scripture it
would be the right one. A garble is added to `config/handle_garbles.json`
when it has been SEEN, with the clip it shipped in.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GARBLES = ROOT / "config" / "handle_garbles.json"

# The desk's rosters, in preference order. Read-only: this pipeline never
# writes to them, so the two projects cannot disagree about a handle.
# READ AS UTF-8 EXPLICITLY. `Path.read_text()` uses the LOCALE's encoding,
# which is UTF-8 in an interactive shell and ASCII in a subprocess or under
# launchd — and this roster is full of Leviatán, Óscar Cañellas and Tarık
# Çelik. The direct run worked and the identical call through `batch.py`
# died with UnicodeDecodeError on byte 0xe2. Same family as launchd's
# minimal PATH: the environment, not the code, is what differed.
ROSTERS = [
    Path.home() / "quotes-pipeline" / "config" / "roster.json",
    Path.home() / "valorant-quote-desk" / "worker" / "roster_supplement.json",
]

_MAP: dict[str, str] | None = None


def _add(m: dict[str, str], alias: str, canon: str) -> None:
    a = re.sub(r"\s+", " ", (alias or "").strip().lower())
    # One character is not a handle, and matching it would rewrite ordinary
    # text. `v1c`'s alias `vlc` is three and is the shortest worth having.
    if len(a) < 3 or not canon:
        return
    m.setdefault(a, canon)


def load() -> dict[str, str]:
    """{alias in lower case: handle as the player spells it}."""
    global _MAP
    if _MAP is not None:
        return _MAP
    m: dict[str, str] = {}
    for p in ROSTERS:
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        players = d.get("players", d) if isinstance(d, dict) else d
        if isinstance(players, dict):
            players = list(players.values())
        for pl in players or []:
            if not isinstance(pl, dict):
                continue
            h = (pl.get("handle") or "").strip()
            if not h:
                continue
            _add(m, h, h)                       # the handle itself, for casing
            for a in pl.get("aliases") or []:
                _add(m, a, h)
    # THE GARBLE CONFIG IS NOT OPTIONAL, because it carries the deny list.
    # Swallowing a read error here would silently restore the defect below,
    # which is the wrong direction to fail in.
    g = json.loads(GARBLES.read_text(encoding="utf-8"))
    norm = lambda a: re.sub(r"\s+", " ", str(a).strip().lower())  # noqa: E731
    confirmed = {norm(a) for a in (g.get("garbles") or {})}

    # A HANDLE THAT IS ALSO AN ORDINARY ENGLISH WORD IS NEVER APPLIED FROM THE
    # TOKEN ALONE. `_add(m, h, h)` puts every handle in as its own alias so
    # casing can be corrected — and 123 of the 599 resulting keys are ordinary
    # words. `after` is the player AfteR, `less` is Less, `life` is Life,
    # `texture` is t3xture, `tick` is TcK, `rose` is Rosé. Uncorrected, "the
    # texture of the game" is burned on screen as "the t3xture of the game"
    # and "after the match" names a Turkish player. It SHIPPED: clip 08's
    # build log reads `'after'->AfteR` and clip 12's `'life'->Life`.
    #
    # This is the exact mirror of the bug this module was written for, and the
    # module's own rule — exact matches only, no fuzzy matching — does not
    # catch it, because `after` IS an exact match for AfteR's own handle.
    #
    # NO MEASUREMENT SEPARATES THE TWO CLASSES. Swept against how often the
    # speaker himself says each one across 31 transcripts: `oxy` 5 (a real
    # player) beside `after` 4 (a preposition), `psalm` 2 (a real garble)
    # beside `less` 2. A dictionary test alone would also deny `psalm`,
    # `forsaken`, `leviathan` and `narrate`, which are the valuable ones.
    #
    # So the ASYMMETRY decides it, the same way MAX_PUNCHES and the nucleus
    # gate's direction were decided. Denying costs a casing or spelling miss
    # on a real handle: recoverable, visible, and it only ever reproduces
    # whisper's own spelling. Applying wrongly puts a real person's name over
    # words nobody said, which is the worst thing this pipeline can do.
    # An entry is restored ONLY by `garbles`, i.e. a garble a human has seen
    # on screen — which is how `psalm` -> s0m survives.
    amb = g.get("ambiguous_with_english")
    if amb is None:
        raise RuntimeError(
            f"{GARBLES} has no `ambiguous_with_english` list. Without it every "
            f"roster handle that is also an English word gets applied to "
            f"ordinary speech — `after` becomes AfteR. Refusing to load a map "
            f"that would do that.")
    for a in amb:
        k = norm(a)
        if k not in confirmed:
            m.pop(k, None)

    skip = {norm(x) for x in g.get("do_not_apply", [])}
    for a, canon in (g.get("garbles") or {}).items():
        if norm(a) not in skip:
            m[norm(a)] = canon
    _MAP = m
    return m


# The English suffixes that /usr/share/dict/words does NOT carry. The
# dictionary holds base forms, so `sign` is in it and `signed` is not — which
# let a whole class of ordinary words back through the deny list: `tens` ->
# TenZ, `kicks` -> Kicks, `sharks` -> Sharks, `fields` -> Fields, `pancakes`
# -> Paincakes, `darker` -> Darker. "he got tens" would have read "he got
# TenZ".
_SUFFIXES = [("s", ""), ("es", ""), ("ed", ""), ("ed", "e"), ("d", ""),
             ("ing", ""), ("ing", "e"), ("er", ""), ("er", "e"), ("ly", ""),
             ("ies", "y"), ("ied", "y")]
_DICTS = ("/usr/share/dict/words", "/usr/dict/words")


def english_words() -> set[str]:
    """The system word list, or an empty set when there is none."""
    for d in _DICTS:
        p = Path(d)
        if p.exists():
            return {w.strip().lower()
                    for w in p.read_text(encoding="utf-8", errors="replace").splitlines()
                    if w.strip()}
    return set()


def is_english(key: str, words: set[str]) -> str | None:
    """The English word `key` is, directly or as an inflection of a word in
    the list. Returns the stem it matched, or None.

    Multi-word aliases are exempt: `paper rex` is not an English word however
    its parts read, and a phrase that long is not something a speaker says by
    accident. So is anything under four characters, where suffix-stripping
    produces noise rather than stems."""
    k = key.strip().lower()
    if k in words:
        return k
    if " " in k or len(k) < 4:
        return None
    for suf, repl in _SUFFIXES:
        if k.endswith(suf) and len(k) - len(suf) >= 3:
            stem = k[:len(k) - len(suf)] + repl
            if stem in words:
                return stem
    return None


def rebuild_deny_list() -> int:
    """Regenerate `ambiguous_with_english` in the garble config from the
    system dictionary, and write it back. Run this after the roster changes:

        .venv/bin/python -m engine.handles --rebuild-deny-list

    The list is VENDORED rather than computed at load time because two
    machines deciding differently about a name on screen is this repo's
    most-repeated defect with a person's name attached.
    """
    words = english_words()
    if not words:
        raise RuntimeError(f"no system word list at any of {_DICTS}")
    cfg = json.loads(GARBLES.read_text(encoding="utf-8"))
    # Build the raw roster map, BEFORE any denial, so the list is complete.
    global _MAP
    saved, _MAP = _MAP, None
    try:
        cfg_no_deny = dict(cfg, ambiguous_with_english=[])
        GARBLES.write_text(json.dumps(cfg_no_deny, indent=1, ensure_ascii=False) + "\n",
                           encoding="utf-8")
        _MAP = None
        raw = dict(load())
    finally:
        _MAP = saved
        GARBLES.write_text(json.dumps(cfg, indent=1, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    amb = sorted(k for k in raw if is_english(k, words))
    cfg["ambiguous_with_english"] = amb
    GARBLES.write_text(json.dumps(cfg, indent=1, ensure_ascii=False) + "\n",
                       encoding="utf-8")
    _MAP = None
    return len(amb)


def fix(text: str, *, on_change=None) -> str:
    """Rewrite handles in one caption's text.

    Longest alias first, so `sad hawk` wins over `sad`. Word boundaries on
    both ends, so `som` never rewrites the inside of `something` — that one
    is real: `som` is an alias of s0m and the transcripts are full of
    `something`, `some`, `sometimes`.
    """
    m = load()
    if not text or not m:
        return text
    out = text
    for alias in sorted(m, key=len, reverse=True):
        canon = m[alias]
        pat = r"(?<![\w'])" + re.escape(alias).replace(r"\ ", r"\s+") + r"(?![\w'])"
        new, n = re.subn(pat, canon.replace("\\", r"\\"), out, flags=re.I)
        if n and new != out:
            if on_change:
                on_change(alias, canon, n)
            out = new
    return out


def fix_cards(cards, *, on_change=None) -> int:
    """Rewrite `.text` on caption cards in place. Returns how many changed.

    `resolve_captions.Card` is an ordinary mutable dataclass, so this assigns
    rather than reconstructing — rebuilding it would hard-code a field order
    that is not this module's to know.

    `.words` is left alone deliberately: `captions_video.kinetic` draws
    `c["text"]`, and the word list is used for timing, not for what appears.
    """
    changed = 0
    for c in cards:
        new = fix(c.text, on_change=on_change)
        if new != c.text:
            c.text = new
            changed += 1
    return changed


if __name__ == "__main__":                                    # pragma: no cover
    import sys
    if "--rebuild-deny-list" in sys.argv:
        n = rebuild_deny_list()
        print(f"{GARBLES}: ambiguous_with_english = {n} keys")
    else:
        print(__doc__)
