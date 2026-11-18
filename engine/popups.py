"""Pop-up images: when the streamer names a player or a team, show them.

George's note on the first live delivery: "it's better if we had more options
with graphics, like say fns is talking about tenz so an image of tenz pops up
on the screen".

Three steps, each one checkable on its own:
  1. `find` asks the model which players, teams and orgs are NAMED in a
     clip's own words, and anchors each to the word where it is first said.
     A name nobody says is never shown, and the streamer himself is excluded.
  2. `image` looks the name up on Liquipedia, the esports wiki, and takes
     the infobox photo (a player) or logo (a team). No match, no pop-up:
     guessing a face onto a name is the one failure this must not have.
  3. `card` draws it as a tilted, bordered card with the name under it, and
     `render` throws it in with `overlays.exhibit_reveal`'s motion.

LIQUIPEDIA'S API TERMS: a descriptive User-Agent, gzip, and at most one
request every 2 seconds, so every call goes through `_api`. Images there
are uploaded under their own licences (player photos mostly CC BY-SA with a
credited photographer, team logos are trademarks); `image` records the page
and file so a credit can be given.
"""
from __future__ import annotations

import gzip
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

UA = "clip-engine/1.0 (hosted Twitch clip service; github.com/GeorgeGed/clip-engine)"
API = "https://liquipedia.net/{wiki}/api.php"
GAP = 2.1               # seconds between API calls, per Liquipedia's terms
MAX_PER_CLIP = 3
DUR = 2.8               # seconds on screen
MIN_SPACING = 4.0       # between two pop-ups
HEAD = 1.5              # the hook title owns the opening
CARD_W = 470
TOP = 1010              # card top in the 1080x1920 frame: inside the lower
                        # pane, under the captions (y 0.44 = 845px)

_last = [0.0]

FIND = """You read the transcript of one short clip from a {game} stream by \
{streamer}. List the pro players, teams and esports organisations that are \
NAMED in it, at most {n}, most important to the clip first.

Rules:
- Only names actually spoken. Never the streamer himself ({streamer}).
- Skip game terms, maps, agents, weapons, casual first names you cannot \
place, and generic words.
- Speech-to-text mangles names. "spoken" is the word exactly as it appears \
in the transcript; "name" is the handle the scene knows them by ("TenZ", \
never a legal name like "Tyson Ngo"; "Sentinels" for a team); "page" is \
that player's or team's Liquipedia {game} page title, normally the same \
handle. If you are not confident who it is, leave it out.
- "at" is the start time of the first word of the spoken name.

Reply with ONLY JSON: {{"names": [{{"name": str, "kind": "player|team", \
"page": str, "spoken": str, "at": number}}]}}"""


def find(words: dict, *, client, streamer: str, game: str = "VALORANT",
         model: str = "claude-sonnet-5-5") -> list[dict]:
    """The named players and teams, each anchored to a spoken word's start."""
    flat = [w for u in words["utterances"] for w in u["words"]]
    if not flat:
        return []
    lines = "\n".join(f'[{u["start"]:.2f}] ' + " ".join(
        f'{w["text"]}@{w["start"]:.2f}' for w in u["words"]) for u in words["utterances"])
    msg = client.messages.create(
        model=model, max_tokens=800,
        system=FIND.format(game=game, streamer=streamer, n=MAX_PER_CLIP),
        messages=[{"role": "user", "content": lines}])
    raw = "".join(b.text for b in msg.content if b.type == "text").strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    try:
        names = json.loads(raw).get("names") or []
    except json.JSONDecodeError:
        return []
    out = []
    for e in names[:MAX_PER_CLIP]:
        first = (e.get("spoken") or "").split()[:1]
        if not first or not e.get("page"):
            continue
        key = re.sub(r"\W", "", first[0]).lower()
        # Anchor on a REAL word: the first transcript word matching the spoken
        # name, nearest the model's time. No match means it was never said.
        hits = [w for w in flat if re.sub(r"\W", "", w["text"]).lower() == key]
        if not hits:
            continue
        w = min(hits, key=lambda w: abs(w["start"] - float(e.get("at") or 0)))
        out.append({"name": e.get("name") or e["page"], "kind": e.get("kind", "player"),
                    "page": e["page"], "at": round(float(w["start"]), 3)})
    return out


def _api(wiki: str, **params) -> dict:
    wait = GAP - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    q = urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(f"{API.format(wiki=wiki)}?{q}",
                                 headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
    finally:
        _last[0] = time.time()
    return json.loads(body)


def _infobox_file(wikitext: str) -> str | None:
    """The infobox's own picture: `image` for a player, the dark-mode logo
    first for a team (it is drawn on a dark tile)."""
    box = re.search(r"\{\{Infobox (player|team|organization)(.*?)\n\}\}", wikitext, re.S | re.I)
    if not box:
        return None
    fields = dict(re.findall(r"^\|\s*(\w+)\s*=\s*(.*?)\s*$", box.group(2), re.M))
    for k in ("imagedark", "image"):
        if fields.get(k):
            return fields[k]
    return None


def image(page: str, out_dir: Path, *, wiki: str = "valorant") -> dict | None:
    """Download `page`'s infobox image into `out_dir`. None when there is no
    page or no image; `path` in the result is relative to `out_dir`."""
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"\W+", "_", page).strip("_").lower()
    meta = out_dir / f"{slug}.json"
    if meta.exists():
        m = json.loads(meta.read_text())
        return m if m.get("path") else None
    m: dict = {"page": page, "path": None}
    d = _api(wiki, action="query", titles=page, prop="revisions", rvprop="content",
             rvslots="main", redirects=1)
    pg = next(iter(d.get("query", {}).get("pages", {}).values()), {})
    if "revisions" in pg:
        f = _infobox_file(pg["revisions"][0]["slots"]["main"]["*"])
        if f:
            ii = _api(wiki, action="query", titles=f"File:{f}", prop="imageinfo",
                      iiprop="url", iiurlwidth=700)
            info = next(iter(ii["query"]["pages"].values())).get("imageinfo")
            if info:
                url = info[0].get("thumburl") or info[0]["url"]
                dst = out_dir / f"{slug}{Path(urllib.parse.urlparse(url).path).suffix.lower()}"
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=60) as r:
                    dst.write_bytes(r.read())
                m.update(path=dst.name, file=f, title=pg.get("title"),
                         source=f"https://liquipedia.net/{wiki}/File:{f.replace(' ', '_')}")
    meta.write_text(json.dumps(m, indent=1))
    return m if m["path"] else None


def card(img_path: Path, name: str, kind: str, out: Path, *, font: Path) -> Path:
    """The pop-up: the photo (or a logo on a dark tile) with a white border
    and a name pill, tilted 4 degrees, with a soft shadow."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

    src = Image.open(img_path).convert("RGBA")
    w = CARD_W
    if kind == "team":
        h = int(w * 0.8)
        tile = Image.new("RGBA", (w, h), (18, 18, 22, 255))
        logo = ImageOps.contain(src, (int(w * 0.72), int(h * 0.72)), Image.LANCZOS)
        tile.alpha_composite(logo, ((w - logo.width) // 2, (h - logo.height) // 2))
    else:
        h = int(w * 1.0)
        # Portraits keep the head: crop toward the TOP of the photo.
        tile = ImageOps.fit(src, (w, h), Image.LANCZOS, centering=(0.5, 0.2))
    r = 26
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), r, fill=255)
    tile.putalpha(mask)

    fnt = ImageFont.truetype(str(font), 54)
    try:
        fnt.set_variation_by_axes([
            800 if a["name"] in (b"Weight", "Weight") else a["default"]
            for a in fnt.get_variation_axes()])
    except OSError:
        pass
    tw = int(fnt.getlength(name))
    pill_h, pad, border = 84, 34, 10
    W = max(w, tw + 2 * pad) + 2 * border + 60
    H = h + 2 * border + pill_h // 2 + 60
    c = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    x0 = (W - w) // 2
    d = ImageDraw.Draw(c)
    d.rounded_rectangle((x0 - border, 30 - border, x0 + w + border, 30 + h + border),
                        r + border, fill=(255, 255, 255, 255))
    c.alpha_composite(tile, (x0, 30))
    pw = tw + 2 * pad
    px, py = (W - pw) // 2, 30 + h - pill_h // 2 + border
    d.rounded_rectangle((px, py, px + pw, py + pill_h), pill_h // 2, fill=(12, 12, 14, 255))
    d.text((W // 2, py + pill_h // 2), name, font=fnt, fill=(255, 255, 255, 255), anchor="mm")
    c = c.rotate(4, resample=Image.BICUBIC, expand=True)
    sh = Image.new("RGBA", c.size, (0, 0, 0, 0))
    sh.putalpha(c.getchannel("A").point(lambda v: int(v * 0.55)))
    sh = sh.filter(ImageFilter.GaussianBlur(18))
    out_img = Image.new("RGBA", (c.width + 40, c.height + 40), (0, 0, 0, 0))
    out_img.alpha_composite(sh, (28, 34))
    out_img.alpha_composite(c, (20, 20))
    out_img.save(out)
    return out


def schedule(found: list[dict], remap, total_s: float) -> list[dict]:
    """Pop-ups in OUTPUT seconds: on the word, after the hook, spaced apart,
    and dropped when the word was cut or the card would overrun the clip."""
    out = []
    for e in sorted(found, key=lambda e: e["at"]):
        t = remap(e["at"])
        if t is None or t < HEAD or t + DUR > total_s:
            continue
        if out and t - out[-1]["at"] < MIN_SPACING:
            continue
        out.append({**e, "at": round(t, 3)})
    return out
