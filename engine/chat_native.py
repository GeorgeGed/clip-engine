"""The chat panel, drawn in Python: `rm_Chat.mov` without Remotion.

The Remotion `ChatScroll` (vendor/remotion-clip08/src/Chat.tsx) needs Node
and Chrome, which the Modal image does not have, so hosted clips shipped
with chat switched off. George asked for chat on hosted clips; this draws
the same panel from the same inputs `make_clip.stage_chat` already plans:
the messages mapped onto the cut (`t` in output seconds, pre-roll negative)
and the windows the panel is on screen for.

Same geometry and behaviour as Chat.tsx, so the two renderers look alike:
  * an opaque #18181B box at (500, 930), 580 wide, growing to 520 tall, the
    newest message at the bottom and the oldest clipped off the top;
  * Inter, 32px, line height 1.3, 22px between messages, the chatter's
    name bold in their own colour lifted to 4.5:1 (`display`), badges and
    emotes inline;
  * a new message grows in over 11 frames (an ease-out standing in for the
    spring) and slides up 14px as it fades in;
  * PRESENT OR ABSENT, NEVER SEE-THROUGH: the box reaches full opacity in
    the first ~0.08s of a window and leaves over its last 0.26s.

Emotes come from Twitch's CDN once per clip and are cached per job.
"""
from __future__ import annotations

import hashlib
import subprocess
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "vendor/remotion-clip08/public"
BOX_X, BOX_Y, BOX_W, BOX_H = 500, 930, 580, 520
PAD, SIZE, LINE, GAP, BADGE = 22, 32, 1.3, 22, 26
IN_FRAMES = 11
BG = (0x18, 0x18, 0x1B, 255)
TEXT = (255, 255, 255, 242)
CANVAS = (1080, 1920)


def _font(weight: int):
    f = ImageFont.truetype(str(PUBLIC / "fonts/Inter.ttf"), SIZE)
    try:
        f.set_variation_by_axes([weight if a["name"] in (b"Weight", "Weight") else a["default"]
                                 for a in f.get_variation_axes()])
    except OSError:
        pass
    return f


def _rgba(hex_colour: str):
    h = (hex_colour or "#FFFFFF").lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (255,)


def _emote(url: str, cache: Path):
    cache.mkdir(parents=True, exist_ok=True)
    p = cache / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".png")
    if not p.exists():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "clip-engine/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                im = Image.open(__import__("io").BytesIO(r.read()))
                im.seek(0)
                im.convert("RGBA").save(p)
        except Exception:                                 # noqa: BLE001
            return None
    h = int(SIZE * 1.1)
    im = Image.open(p).convert("RGBA")
    return im.resize((max(1, round(im.width * h / im.height)), h), Image.LANCZOS)


def _message(m: dict, *, bold, regular, badges: dict, emotes: Path) -> Image.Image:
    """One message, word-wrapped to the box, as its own RGBA image."""
    width = BOX_W - 2 * PAD
    lh = round(SIZE * LINE)
    # tokens: (kind, payload, font, colour)
    toks = []
    # A BADGE IS A GARNISH. v18 was deployed from a checkout without the
    # (then gitignored) badge PNGs, and the first badged message would have
    # crashed the whole clip. A missing file now costs only the badge.
    for b in m.get("badges", [])[:2]:
        if b in badges and (PUBLIC / badges[b]).exists():
            im = Image.open(PUBLIC / badges[b]).convert("RGBA").resize((BADGE, BADGE), Image.LANCZOS)
            toks.append(("img", im, 7, 4))
    toks.append(("text", m["author"], bold, _rgba(m.get("display") or m.get("colour"))))
    toks.append(("text", ": ", bold, TEXT))
    for f in m.get("frags", []):
        if f.get("emote"):
            im = _emote(f["emote"], emotes)
            if im is not None:
                toks.append(("img", im, 2, 9))
                continue
        for i, word in enumerate((f.get("text") or "").split(" ")):
            toks.append(("text", (" " if i else "") + word, regular, TEXT))
    lines, cur, x = [], [], 0
    for t in toks:
        w = (t[1].width + t[2] * 2 if t[0] == "img" else round(t[2].getlength(t[1])))
        if cur and x + w > width:
            lines.append(cur)
            cur, x = [], 0
            if t[0] == "text":
                t = (t[0], t[1].lstrip(" "), t[2], t[3])
                w = round(t[2].getlength(t[1]))
        cur.append((t, x))
        x += w
    lines.append(cur)
    im = Image.new("RGBA", (width, lh * len(lines)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for li, line in enumerate(lines):
        base = li * lh + lh // 2
        for t, x in line:
            if t[0] == "img":
                im.alpha_composite(t[1], (x + t[2], base - t[1].height // 2))
            else:
                d.text((x, base), t[1], font=t[2], fill=t[3], anchor="lm")
    return im


def _presence(t: float, wins: list[dict]) -> float:
    p = 0.0
    for w in wins:
        a = min(1.0, max(0.0, (t - w["from"]) / 0.34))
        a = 1 + 2.5 * (a - 1) ** 3 + 1.5 * (a - 1) ** 2 if a < 1 else 1.0   # ease-out back
        b = min(1.0, max(0.0, (w["to"] - t) / 0.26))
        b = b * (2 - b)
        p = max(p, min(a, b))
    return max(0.0, min(1.0, p))


def render(messages: list[dict], windows: list[dict], out: Path, *, frames: int,
           fps: int = 60, emote_cache: Path | None = None) -> Path:
    """Write `out` as a full-canvas qtrle alpha movie of `frames` frames."""
    import json

    import numpy as np
    badges = json.loads((PUBLIC / "badgemap.json").read_text()) if (PUBLIC / "badgemap.json").exists() else {}
    bold, regular = _font(700), _font(500)
    emotes = emote_cache or out.parent / "emotes"
    imgs: dict[int, Image.Image] = {}
    w, h = CANVAS
    blank = np.zeros((h, w, 4), np.uint8).tobytes()
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
         "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
         "-c:v", "qtrle", "-pix_fmt", "argb", str(out)], stdin=subprocess.PIPE)
    last_key, last = None, blank
    for f in range(frames):
        now = f / fps
        p = _presence(now, windows)
        if p < 0.004:
            proc.stdin.write(blank)
            continue
        shown = [i for i, m in enumerate(messages) if now - 400 < m["t"] <= now]
        qs = [min(1.0, max(0.0, (now - messages[i]["t"]) * fps / IN_FRAMES)) for i in shown]
        qs = [1 - (1 - q) ** 3 for q in qs]
        alpha = min(1.0, p * 4)
        key = (tuple(shown), tuple(round(q, 3) for q in qs), round(alpha, 3))
        if key == last_key:
            proc.stdin.write(last)
            continue
        # stack bottom-up; stop once the box is full
        parts, used = [], 0
        for i, q in zip(reversed(shown), reversed(qs)):
            if i not in imgs:
                imgs[i] = _message(messages[i], bold=bold, regular=regular,
                                   badges=badges, emotes=emotes)
            im = imgs[i]
            hh = round(im.height * q) + round(GAP * q)
            parts.append((im, q, hh))
            used += hh
            if used >= BOX_H - 2 * PAD:
                break
        inner = min(used, BOX_H - 2 * PAD)
        box = Image.new("RGBA", (BOX_W, inner + 2 * PAD), BG)
        y = PAD + inner
        for im, q, hh in parts:
            y -= hh
            msg = im
            if q < 1:
                msg = im.copy()
                msg.putalpha(msg.getchannel("A").point(lambda v, a=min(1.0, q * 1.5): int(v * a)))
            top = round(y + GAP * q + (1 - q) * 14)
            if top + msg.height <= 0:
                continue
            # the oldest message is clipped off the top of the box, as
            # Chat.tsx's overflow: hidden does
            box.alpha_composite(msg, (PAD, max(0, top)), (0, max(0, -top)))
        box = box.crop((0, 0, BOX_W, inner + 2 * PAD))
        if alpha < 1:
            box.putalpha(box.getchannel("A").point(lambda v: int(v * alpha)))
        layer = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
        layer.alpha_composite(box, (BOX_X, BOX_Y))
        last_key, last = key, np.asarray(layer, dtype=np.uint8).tobytes()
        proc.stdin.write(last)
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed writing {out}")
    return out
