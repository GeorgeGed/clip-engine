"""A licensed photo of a team or player the clip NAMES, and nothing invented.

George, on clip 16: *"surely we should be showing an image of vitality at
champions similar to the jingg/jonahp story of the previous video? include
that in the logic."*

Clip 16's consequence is *"For all you know Vitality was a dead fucking team
that just happened to make a run"* — and he is right that the viewer has no
idea what run. A photo answers it in two seconds where the audio cannot.

WHAT MAKES THIS SAFE TO AUTOMATE, given this file's standing rule that cards
are editorial and that a name on screen needs an independent check:

1. **The name has to be SPOKEN in the clip.** Not inferred from the subject
   line, not guessed from the topic — taken from the clip's own `claim` or
   `consequence` AND confirmed in its transcript. A card naming someone the
   clip never mentions is the "random text cards" defect with a photograph
   attached.
2. **The photo comes from Riot's own four VCT Flickr accounts**, which is
   the same client and the same rights basis the quote desk already uses.
3. **THE CAPTION IS THE SOURCE, AND THE HEADLINE IS BUILT FROM IT.** Riot's
   photo desk writes a full caption on every frame — *"Team Vitality walk
   onstage for the opening ceremony during VALORANT Champions Shanghai Grand
   Finals at Mercedes-Benz Arena on October 18, 2026"* — so the event, the
   venue and the date are a primary source, not a tracker and not one
   outlet. That is a stronger basis than the VLR roster items this file
   records failing an independent check four times out of eight, and it is
   why this one can be automatic where those could not.
4. **Nothing about a RESULT is asserted unless a caption says it.** Several
   of the same set read "after their loss during ... Grand Finals", which is
   how we know Vitality reached the final and lost it; without such a
   caption the card says only that they were there.

RIGHTS: Riot's VCT photos are All Rights Reserved. They are used here on
George's own operator permission, carried over from the quote desk, and the
licence, account and page URL are logged per photo in the job's manifest so
nothing goes out on an assumption. See the rights note in AGENTS.md — a
distributed clip is a different use from a still quote card.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path

# The four official accounts, by the quote desk's own names.
ACCOUNT_ORDER = ("global", "emea", "americas", "pacific")

# A caption that names one of these is about a performance or a broadcast
# guest, not about the team, so the photo is not of the subject.
NOT_THE_SUBJECT = ("preform", "perform", "co-streamer", "costreamer")

UA = {"User-Agent": "clip-engine/1.0"}


@dataclass
class Story:
    subject: str            # "Team Vitality"
    headline: str           # built from the caption, never invented
    photo: Path
    caption: str            # Riot's own words, kept verbatim in the manifest
    event: str
    photo_id: str
    account: str
    licence: str
    page_url: str

    def record(self) -> dict:
        d = asdict(self)
        d["photo"] = str(self.photo)
        return d


def api_key() -> str:
    """The key lives in the environment, never in the code.

    AGENTS.md records the failure mode: running from another directory gives
    an empty key and the finder reports "no photo found on any account",
    which looks like a search miss and is not.
    """
    if os.environ.get("FLICKR_API_KEY"):
        return os.environ["FLICKR_API_KEY"]
    for env in (Path.home() / "valorant-quote-desk/.env",
                Path.home() / "quotes-pipeline/.env"):
        if not env.exists():
            continue
        for ln in env.read_text().splitlines():
            m = re.match(r"\s*(?:export\s+)?FLICKR_API_KEY\s*=\s*['\"]?([^'\"\s]+)",
                         ln)
            if m:
                os.environ["FLICKR_API_KEY"] = m.group(1)
                return m.group(1)
    return ""


def _client(cache: Path):
    sys.path.insert(0, str(Path.home() / "valorant-quote-desk/worker"))
    from hermes_images.flickr import Flickr          # noqa: PLC0415
    return Flickr(api_key(), cache)


def _desc(p: dict) -> str:
    d = p.get("description")
    if isinstance(d, dict):
        d = d.get("_content")
    return (d or "").strip()


def _tag(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _event_from(caption: str) -> str:
    """The event, from Riot's own caption. `during X at Y on DATE`."""
    m = re.search(r"\bduring\s+(.+?)(?:\s+at\s+[A-Z]|\s+on\s+\w+\s+\d|$)",
                  caption)
    return (m.group(1).strip().rstrip(".") if m else "").strip()


def _headline(subject: str, caption: str, event: str, lost: bool) -> str:
    """Sentence case, built from the caption, asserting only what it says.

    This file's rule, learned on `PARTS WAYS AFTER FIVE YEARS`: an outside
    story goes on screen as the outlet published it, as a SENTENCE with its
    own subject, never as a verb lifted out of one.
    """
    ev = event or "VALORANT Champions"
    ev = re.sub(r"^\d{4}\s+", "", ev)
    # "the ... Grand Finals and lost" reads as a plural event; the thing he
    # is talking about is one match.
    ev = re.sub(r"\bGrand Finals\b", "grand final", ev)
    if lost:
        return f"{subject} reached the {ev} and lost"
    return f"{subject} at the {ev}"


def find(subject: str, *, cache: Path, dest_dir: Path,
         limit_pages: int = 2) -> Story | None:
    """A licensed photo of `subject`, or None. Never raises on a miss."""
    if not api_key():
        return None
    try:
        fl = _client(cache)
    except Exception:                                  # noqa: BLE001
        return None
    tag = _tag(subject)
    hits: dict[str, dict] = {}
    for account in ACCOUNT_ORDER:
        for page in range(1, limit_pages + 1):
            try:
                # per_page is 8 deliberately: the client returns ZERO results
                # for 20, which looks like "no photos of this team" and is a
                # paging quirk. Measured on `global`/"Vitality Champions":
                # 8 -> 8 results, 20 -> 0.
                got = fl.search(account, subject, per_page=8, page=page)
            except Exception:                          # noqa: BLE001
                continue
            for p in got:
                if tag in _tag(p.get("tags") or ""):
                    p["_account"] = account
                    hits.setdefault(p["id"], p)
        if hits:
            break                                      # the first account wins
    if not hits:
        return None

    lost = any("after their loss" in _desc(p).lower() for p in hits.values())

    def rank(p: dict) -> tuple:
        cap = _desc(p).lower()
        # ONSTAGE BEATS BACKSTAGE, and this is the whole point of the card.
        # Ranking on "the caption names the subject first" alone chose
        # `55597459595` for Vitality — a posed team-and-staff group against a
        # bare corridor wall. It is identifiably them and it shows no event
        # at all, where the card exists precisely to answer "what run?".
        # The stage shot has the arena in it.
        venue = 0 if "onstage" in cap or " stage " in f" {cap} " else 1
        if "back stage" in cap or "backstage" in cap:
            venue = 2
        other_teams = len([t for t in (p.get("tags") or "").split()
                           if t.startswith("team") and t != tag]) \
            + (1 if "loud" in (p.get("tags") or "").split() else 0)
        # A caption that OPENS with the subject is a photo OF the subject;
        # one that mentions them halfway through is a photo of something
        # else they happen to be in. AGENTS.md: check what the photo shows —
        # the top-ranked Jinggg result was the back of his head.
        leads = 0 if cap.startswith(subject.lower()) else 1
        performer = 1 if any(w in cap for w in NOT_THE_SUBJECT) else 0
        return (performer, venue, leads, other_teams, -len(cap))

    best = sorted(hits.values(), key=rank)[0]
    url = best.get("url_l") or best.get("url_o")
    if not url:
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    photo = dest_dir / f"story_{_tag(subject)}_{best['id']}.jpg"
    if not photo.exists():
        try:
            req = urllib.request.Request(url, headers=UA)
            photo.write_bytes(urllib.request.urlopen(req, timeout=90).read())
        except Exception:                              # noqa: BLE001
            return None
    cap = _desc(best)
    event = _event_from(cap)
    return Story(
        subject=subject,
        headline=_headline(subject, cap, event, lost),
        photo=photo, caption=cap, event=event,
        photo_id=str(best["id"]), account=best.get("_account", "?"),
        licence="All Rights Reserved (flickr license=0); operator permission",
        page_url=f"https://www.flickr.com/photos/{best['owner']}/{best['id']}",
    )


# Teams and orgs this pipeline may put on screen. A name not on this list is
# not looked up — which keeps a whisper mis-hearing ("paper X" for PRX, and
# this file records several) from becoming a photo card of the wrong org.
KNOWN = (
    "Team Vitality", "Paper Rex", "Sentinels", "NRG", "G2 Esports",
    "100 Thieves", "Cloud9", "LOUD", "MIBR", "KRU Esports", "Leviatan",
    "FNATIC", "Team Liquid", "Karmine Corp", "Natus Vincere", "Gentle Mates",
    "Global Esports", "FlyQuest", "Evil Geniuses", "DRX", "Gen.G", "T1",
    "Paper Rex", "Talon Esports", "Rex Regum Qeon", "Team Heretics",
)
# What a speaker actually says, mapped to the org's full name.
SPOKEN = {
    "vitality": "Team Vitality", "prx": "Paper Rex", "paper rex": "Paper Rex",
    "sentinels": "Sentinels", "sen": "Sentinels", "nrg": "NRG",
    "g2": "G2 Esports", "hundred thieves": "100 Thieves", "c9": "Cloud9",
    "cloud nine": "Cloud9", "loud": "LOUD", "mibr": "MIBR",
    "kru": "KRU Esports", "leviatan": "Leviatan", "fnatic": "FNATIC",
    "liquid": "Team Liquid", "karmine": "Karmine Corp", "navi": "Natus Vincere",
    "heretics": "Team Heretics", "drx": "DRX", "geng": "Gen.G",
}


def named_in(text: str, spoken_words: list[str]) -> list[str]:
    """Orgs that `text` (the clip's claim) names AND the clip actually says.

    Both halves are required. The claim is written by the selection model and
    can paraphrase; the transcript is what the viewer hears. A card may only
    go on a name the viewer hears.
    """
    said = {w.lower().strip(".,!?'\"") for w in spoken_words}
    out: list[str] = []
    low = text.lower()
    for spoken, org in SPOKEN.items():
        if org in out:
            continue
        toks = spoken.split()
        heard = (all(t in said for t in toks) if len(toks) > 1
                 else spoken in said)
        if heard and spoken in low:
            out.append(org)
    return out
