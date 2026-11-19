"""Find the streamer's own multi-kills in a Valorant VOD from the kill feed.

HIS KILLS ARE MARKED ON SCREEN. Valorant's kill feed (top right) lists every
kill as killer -> victim. Rows that involve the player whose screen it is carry
a yellow marker on his portrait, and with streamer mode on his name reads "Me".
So a row with the yellow marker on its KILLER side is a kill by him, and one
with it on the VICTIM side is his death. Measured on s0m's VOD 2889934935:
237 rows carry the marker, and his kills ("Me -> Notexxd") and deaths
("Notexxd -> Me") split cleanly by which side it is on.

ONLY HIS OWN GAMES. George wants kill clips of the streamer playing, not of
matches he is watching, and a pro broadcast marks the player its camera is
following with the SAME yellow marker: FNS's watchparty VOD 2885323336 came
out with ten "streaks" by 100T Asuna, FUT xeus and others. Faces do not
separate them (a pro the camera stays on through his multi-kill looks exactly
like the streamer on his agent), but NAMES do: a broadcast tags every player
with his team, "100T Asuna", "FUT xeus", "VIT Jamppi", and a ranked game does
not. So the kill feed for five minutes around each streak is read with OCR,
and a streak whose feed shows enough "TAG Name" pairs is dropped
(broadcast_score). Measured on every streak in both VODs: 3-10 per
broadcast streak, 0-2 per streak in his own games, where the hits are OCR
junk off the HUD ("FS NETWORK", "FS Packet") or an agent name ("GE Clove").

Colours, from the kill feed: the killer's team is teal when it is his team and
red when it is the enemy; the victim takes the other colour. A kill by him is a
row whose teal half is on the left with the yellow marker on that side.
"""
from __future__ import annotations

import subprocess

import numpy as np

FPS = 2                           # kill-feed rows stay up ~5 s, so 2 fps sees each
# The kill feed's box at 1080p: x 1360-1920, y 40-380.
BOX = (1360, 40, 1920, 380)
W, H = 560, 340
STREAK_GAP = 25.0                 # kills further apart than this are separate fights
MIN_STREAK = 3

# FIND HIS ROWS BY THE MARKER, NOT BY THE ROW. The rows are translucent and
# stack with no gap, so cutting the feed into rows by colour merged them and
# missed two kills in three on s0m's 4k. The marker is a solid pale-yellow
# strip a full row tall (~(235, 230, 125), not saturated yellow), at the left
# end of the row when he is the killer and beside the victim's portrait at the
# right end when he died. Assist icons are yellow too but half a row tall.
KILL_SIDE = 400                   # a marker left of this x is on the killer side
MIN_STRIP_H = 18
MIN_STRIP_W = 5
# Tracking a marker from frame to frame: rows only ever slide UP as older ones
# expire, by at most two rows (~85 px) between frames, and its x holds.
TRACK_DX, TRACK_UP, TRACK_DOWN = 14, 85, 14
ROW_LIFE = 3.0                    # a marker unseen this long has expired
# Team tags in the VCT leagues and Challengers, as broadcasts print them.
TEAM_TAGS = {
    "100T", "2G", "AG", "BBL", "BLG", "C9", "DFM", "DRG", "DRX", "EDG", "EG", "FNC",
    "FPX", "FS", "FUR", "FUT", "G2", "GE", "GEN", "GIA", "GX", "JDG", "KC", "KOI",
    "KRU", "LEV", "LOUD", "M8", "MIBR", "NAVI", "NOVA", "NRG", "NS", "PRX", "RRQ",
    "SEN", "T1", "TE", "TEC", "TH", "TL", "TLN", "TYL", "VIT", "WOL", "XLG", "ZETA",
}
BROADCAST_TAGS = 3                # a broadcast_score this high = a broadcast
# Words that follow a tag-like token in his own games and are not players:
# the network HUD inside the kill-feed box, and agent names, which the feed
# shows for players in streamer mode.
NOT_NAMES = ("Packet", "Loss", "Network", "Problem", "Client",
             "Astra", "Breach", "Brimstone", "Chamber", "Clove", "Cypher", "Deadlock", "Fade",
             "Gekko", "Harbor", "Iso", "Jett", "KAYO", "Killjoy", "Neon", "Omen", "Phoenix",
             "Raze", "Reyna", "Sage", "Skye", "Sova", "Tejo", "Viper", "Vyse", "Waylay", "Yoru")
TAG_PAD = 150.0                   # read the feed this far either side of a streak
TAG_FPS = 1 / 3


def _tag(t: str) -> str:
    """A team tag as OCR spells it either way: T1 reads as "Tl", 100T as "1O0T"."""
    return t.upper().replace("O", "0").replace("I", "1").replace("L", "1")


_TAGS = {_tag(t) for t in TEAM_TAGS}


def _masks(f):
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    red = (r > 180) & (g < 120) & (b < 120)
    teal = (g > 150) & (r < 150) & (b > 110)
    yel = (r > 200) & (g > 190) & (b < 165) & (r - b > 70) & (np.abs(r - g) < 40)
    return red, teal, yel


def own_kills_in_frame(f) -> list[tuple[int, int]]:
    """(x, y) of each marker in this kill-feed frame that sits on the killer
    side of a row, i.e. one kill by the player."""
    red, teal, yel = _masks(f.astype(np.int16))
    rows = yel[:, :KILL_SIDE].sum(1)
    out, y = [], 0
    while y < H:
        if rows[y] < MIN_STRIP_W:
            y += 1
            continue
        y1 = y
        while y1 < H and rows[y1] >= MIN_STRIP_W:
            y1 += 1
        h = y1 - y
        # A strip cut off by the top of the box is the HUD above the feed,
        # not a row: on s0m's VOD it added a phantom kill to a 2-kill fight.
        if h >= MIN_STRIP_H and y > 4:
            cols = np.where(yel[y:y1, :KILL_SIDE].sum(0) >= h * 0.5)[0]
            # His name and weapon follow on teal and the victim's panel ends the
            # row in red. The agent-select screen's yellow name on blue passed
            # the teal test alone and read as an "8k".
            right = cols.max() + 30 if len(cols) else 0
            if (len(cols) >= MIN_STRIP_W and teal[y:y1, right:right + 190].sum() > h * 15
                    and red[y:y1, right + 60:].sum() > h * 15):
                out.append((int(np.median(cols)), y))
        y = y1 + 1
    return out


def _frames(path, start: float, dur: float, fps: float):
    """The kill-feed box, as W x H RGB frames."""
    x0, y0, x1, y1 = BOX
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{start:.2f}", "-i", str(path)]
    if dur:
        cmd += ["-t", f"{dur:.2f}"]
    cmd += ["-vf", f"fps={fps},crop=iw*{x1 - x0}/1920:ih*{y1 - y0}/1080:iw*{x0}/1920:ih*{y0}/1080,"
                   f"scale={W}:{H}", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    n = W * H * 3
    while True:
        b = p.stdout.read(n)
        if len(b) < n:
            break
        yield np.frombuffer(b, np.uint8).reshape(H, W, 3)
    p.wait()


def scan(path, *, start: float = 0.0, dur: float | None = None) -> list[float]:
    """VOD seconds at which the marked player got a kill."""
    # One kill per marker TRACKED across frames, counted once it has been seen
    # twice. Counting markers on screen and reading every rise as a kill
    # turned a 1-kill fight into a 7k: a flash or a fading row drops markers
    # for a frame and they come back as "new". Checked against hand counts on
    # s0m's VOD 2889934935: a 4k (with a Clove killed twice), a 3k over 25 s,
    # a 1-kill and a 2-kill fight all come out exact.
    live: list[list] = []          # [x, y, last seen, first seen, sightings]
    kills: list[float] = []
    for i, frame in enumerate(_frames(path, start, dur, FPS)):
        t = start + i / FPS
        live = [m for m in live if t - m[2] <= ROW_LIFE]
        used: set[int] = set()
        for x, y in own_kills_in_frame(frame):
            near = [(abs(m[0] - x) + abs(m[1] - y) * 0.2, j) for j, m in enumerate(live)
                    if j not in used and abs(m[0] - x) <= TRACK_DX and m[1] - TRACK_UP <= y <= m[1] + TRACK_DOWN]
            if not near:
                live.append([x, y, t, t, 1])
                used.add(len(live) - 1)
                continue
            m = live[min(near)[1]]
            used.add(min(near)[1])
            m[0], m[1], m[2], m[4] = x, y, t, m[4] + 1
            if m[4] == 2:
                kills.append(m[3])
    return kills


def streaks(kills: list[float], *, gap: float = STREAK_GAP, least: int = MIN_STREAK) -> list[dict]:
    """Runs of kills close together: a 3k, 4k or ace and where it starts and ends."""
    out, cur = [], []
    for t in sorted(kills):
        if cur and t - cur[-1] > gap:
            if len(cur) >= least:
                out.append({"start": cur[0], "end": cur[-1], "kills": len(cur)})
            cur = []
        cur.append(t)
    if len(cur) >= least:
        out.append({"start": cur[0], "end": cur[-1], "kills": len(cur)})
    return out



def tag_pairs(path, streak: dict) -> list[str]:
    """The "TAG Name" pairs OCR reads in the kill feed around a streak.

    A pair, not a bare tag: two-letter tags (TE, TH, GE) turn up in OCR junk
    on any frame, but never followed by a name on the same line."""
    import io
    import re
    from concurrent.futures import ThreadPoolExecutor

    from PIL import Image

    def one(f) -> list[str]:
        x = f.astype(np.int16)
        text = (x[..., 0] > 170) & (x[..., 1] > 170) & (x[..., 2] > 170)
        buf = io.BytesIO()
        Image.fromarray(np.where(text, 0, 255).astype(np.uint8)).resize(
            (W * 3, H * 3), Image.LANCZOS).save(buf, "PNG")
        out = subprocess.run(["tesseract", "stdin", "stdout", "--psm", "6"], input=buf.getvalue(),
                             capture_output=True, check=True).stdout.decode(errors="ignore")
        return [f"{_tag(a)} {b}" for line in out.splitlines()
                for a, b in re.findall(r"\b([A-Za-z0-9]{2,4}) ([A-Za-z][A-Za-z0-9]{2,})", line)
                if _tag(a) in _TAGS]

    a = max(0.0, streak["start"] - TAG_PAD)
    frames = list(_frames(path, a, streak["end"] + TAG_PAD - a, TAG_FPS))
    with ThreadPoolExecutor(4) as ex:
        return [p for ps in ex.map(one, frames) for p in ps]


def broadcast_score(pairs: list[str]) -> int:
    """How many of `tag_pairs` look like a pro's name. A tag of three or more
    characters (100T, FUT, SEN) counts on its own; a two-character one (T1,
    FS, GE) only with a real-looking name, since those are what OCR junk
    makes. Nothing counts whose "name" is HUD text or an agent."""
    from rapidfuzz import fuzz
    n = 0
    for p in pairs:
        tag, name = p.split(" ", 1)
        if any(fuzz.ratio(name.lower(), w.lower()) >= 70 for w in NOT_NAMES):
            continue
        if len(tag) >= 3 or (len(name) >= 4 and not name.isupper()):
            n += 1
    return n


def multikills(path, kills: list[float]) -> list[dict]:
    """The streaks among `scan`'s kills from the streamer's own games: each
    with its team-tag count, and those reading as a broadcast left out."""
    out = []
    for s in streaks(kills):
        s["tags"] = broadcast_score(tag_pairs(path, s))
        if s["tags"] < BROADCAST_TAGS:
            out.append(s)
    return out
