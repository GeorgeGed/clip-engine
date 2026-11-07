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
    if GARBLES.exists():
        try:
            g = json.loads(GARBLES.read_text(encoding="utf-8"))
            skip = {s.lower() for s in g.get("do_not_apply", [])}
            for a, canon in (g.get("garbles") or {}).items():
                if a.lower() not in skip:
                    m[re.sub(r"\s+", " ", a.strip().lower())] = canon
        except (json.JSONDecodeError, OSError):
            pass
    _MAP = m
    return m


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
