"""Tier 0: the crowd signal, via Twitch's official Helix API.

What viewers chose to clip is a stronger "something happened here" signal than
chat velocity, and unlike VOD chat replay it is available through the
documented API. Each clip made from a VOD carries `vod_offset` — the second it
starts at — so a cluster of clips around a timestamp is a crowd vote.

VOD chat replay is deliberately absent from Helix. Reading it means hitting
Twitch's private GraphQL endpoint with a borrowed web client-id, which this
module does not do. For real chat velocity, capture it live off
`irc.chat.twitch.tv` (anonymous read-only is officially supported) while the
stream is running — see `capture_chat_live()` below.

Credentials come from a .env with TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET.
Values are never logged.
"""

from __future__ import annotations

import json
import pathlib
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict

CRED_CANDIDATES = [
    "~/valorant-quote-desk/.env",
    "~/valorant-quote-bot-n8n/.env",
    "~/clip-autopilot/.env",
]


def _load_env(path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        txt = pathlib.Path(path).expanduser().read_text(errors="replace")
    except Exception:
        return out
    for line in txt.splitlines():
        m = re.match(r'^\s*(?:export\s+)?([A-Z0-9_]+)\s*=\s*["\']?([^"\'\n]*)["\']?\s*$', line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def _credentials() -> tuple[str, str, str]:
    for src in CRED_CANDIDATES:
        env = _load_env(src)
        cid, sec = env.get("TWITCH_CLIENT_ID"), env.get("TWITCH_CLIENT_SECRET")
        if cid and sec:
            return cid, sec, src
    raise RuntimeError(
        "no TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET found in " + ", ".join(CRED_CANDIDATES)
    )


class Helix:
    def __init__(self) -> None:
        cid, sec, src = _credentials()
        self.client_id = cid
        self.cred_source = src
        req = urllib.request.Request(
            "https://id.twitch.tv/oauth2/token",
            data=urllib.parse.urlencode(
                {"client_id": cid, "client_secret": sec, "grant_type": "client_credentials"}
            ).encode(),
            method="POST",
        )
        self.token = json.load(urllib.request.urlopen(req))["access_token"]

    def get(self, path: str, **params) -> dict:
        url = f"https://api.twitch.tv/helix/{path}?" + urllib.parse.urlencode(params, doseq=True)
        req = urllib.request.Request(
            url, headers={"Client-ID": self.client_id, "Authorization": f"Bearer {self.token}"}
        )
        return json.load(urllib.request.urlopen(req))

    def user_id(self, login: str) -> str:
        return self.get("users", login=login)["data"][0]["id"]

    def clips_for_vod(self, login: str, video_id: str, *, pages: int = 20) -> list[dict]:
        bid = self.user_id(login)
        out, cursor = [], None
        for _ in range(pages):
            p = {"broadcaster_id": bid, "first": 100}
            if cursor:
                p["after"] = cursor
            r = self.get("clips", **p)
            out += r.get("data", [])
            cursor = (r.get("pagination") or {}).get("cursor")
            if not cursor:
                break
        return [
            c for c in out
            if c.get("video_id") == str(video_id) and c.get("vod_offset") is not None
        ]


@dataclass
class CrowdMoment:
    t: float
    n_clips: int
    views: int
    titles: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


def cluster(clips: list[dict], *, window: float = 60.0) -> list[CrowdMoment]:
    """Clips within `window` seconds are one crowd moment."""
    pts = sorted(clips, key=lambda c: c["vod_offset"])
    groups: list[list[dict]] = []
    for c in pts:
        if groups and c["vod_offset"] - groups[-1][-1]["vod_offset"] <= window:
            groups[-1].append(c)
        else:
            groups.append([c])
    out = []
    for g in groups:
        best = max(g, key=lambda c: c.get("view_count", 0))
        out.append(CrowdMoment(
            t=float(best["vod_offset"]),
            n_clips=len(g),
            views=sum(c.get("view_count", 0) for c in g),
            titles=[c.get("title", "")[:70] for c in sorted(
                g, key=lambda c: -c.get("view_count", 0))][:3],
        ))
    out.sort(key=lambda m: (-m.views, -m.n_clips))
    return out


def crowd_score(m: CrowdMoment, *, max_views: int) -> float:
    """0..1. Views dominate; several independent clips is corroboration."""
    import math

    v = math.log1p(m.views) / math.log1p(max(max_views, 1))
    corroboration = min(m.n_clips / 4.0, 1.0)
    return round(0.75 * v + 0.25 * corroboration, 3)


def capture_chat_live(channel: str, out_path: str, *, seconds: int = 3600) -> None:
    """Anonymous read-only IRC capture — the officially supported chat path.

    Use this while a stream is live. It is the only legitimate route to chat
    velocity; VOD replay is not exposed by the API.
    """
    import socket
    import time

    s = socket.create_connection(("irc.chat.twitch.tv", 6667), timeout=10)
    s.sendall(b"PASS SCHMOOPIIE\r\nNICK justinfan12345\r\n")
    s.sendall(f"JOIN #{channel}\r\n".encode())
    t0 = time.time()
    with open(out_path, "a") as f:
        buf = b""
        while time.time() - t0 < seconds:
            buf += s.recv(4096)
            while b"\r\n" in buf:
                line, buf = buf.split(b"\r\n", 1)
                txt = line.decode(errors="replace")
                if txt.startswith("PING"):
                    s.sendall(b"PONG :tmi.twitch.tv\r\n")
                elif "PRIVMSG" in txt:
                    f.write(json.dumps({"t": round(time.time() - t0, 2), "raw": txt}) + "\n")
                    f.flush()
    s.close()


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Tier 0 crowd signal from Twitch clips")
    ap.add_argument("--login", required=True)
    ap.add_argument("--video-id", required=True)
    ap.add_argument("-o", "--out", default="-")
    a = ap.parse_args()

    h = Helix()
    clips = h.clips_for_vod(a.login, a.video_id)
    moments = cluster(clips)
    mx = max((m.views for m in moments), default=1)
    payload = {
        "login": a.login, "video_id": a.video_id,
        "clips_found": len(clips),
        "moments": [dict(m.as_dict(), score=crowd_score(m, max_views=mx)) for m in moments],
    }
    blob = json.dumps(payload, indent=2)
    if a.out == "-":
        print(blob)
    else:
        pathlib.Path(a.out).write_text(blob)
        print(f"{len(clips)} clips -> {len(moments)} crowd moments -> {a.out}")
