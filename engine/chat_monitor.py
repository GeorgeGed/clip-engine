"""Tier 1b: live chat velocity, over Twitch's official IRC gateway.

VOD chat replay is not exposed by the API, so chat has to be captured while the
stream is running. Anonymous read-only IRC is the documented, supported way:
connect as `justinfan<n>`, join a channel, read. No credentials, no private
endpoints.

Two jobs:
  watch    capture a live channel to JSONL, with wall-clock offsets
  analyse  turn that into the same shaped signal detect_audio.py produces,
           so the ranker can treat them alike

A chat spike means "the room reacted". Combined with a vocal spike it means the
streamer reacted too — that pair is the strongest cheap evidence of a moment.
"""

from __future__ import annotations

import json
import random
import re
import socket
import statistics
import time
from dataclasses import dataclass, asdict
from pathlib import Path

HOST, PORT = "irc.chat.twitch.tv", 6667
HOP_S = 1.0
ROLLING_WINDOW_S = 120.0
Z_THRESHOLD = 3.0
MIN_SEPARATION_S = 20.0
MAD_FLOOR_FRAC = 0.25

# A jump from 1 message to 4 is statistically loud and editorially meaningless.
# A spike has to clear an absolute bar as well as a relative one, and it has to
# come from several people rather than one person spamming.
MIN_ABS_RATE = 6.0        # messages in the spike second
MIN_RATE_MULTIPLE = 2.5   # ... and this many times the local median
MIN_UNIQUE_CHATTERS = 4

# Crude but useful intent buckets. Chat says what kind of moment it was.
LAUGH = {"kekw", "lul", "omegalul", "lmao", "lmfao", "icant", "deadass", "xd", "😂", "💀"}
SHOCK = {"pog", "pogchamp", "poggers", "pogu", "what", "wtf", "omg", "nowayfr", "😱"}
HYPE = {"letsgo", "lesgo", "ezclap", "gigachad", "w", "dub", "🔥"}
NEGATIVE = {"l", "ratio", "copium", "sadge", "pepehands", "yikes"}

TAG_RE = re.compile(r"^@(?P<tags>[^ ]*) :(?P<who>[^!]+)![^ ]* PRIVMSG #(?P<ch>[^ ]+) :(?P<msg>.*)$")
PLAIN_RE = re.compile(r"^:(?P<who>[^!]+)![^ ]* PRIVMSG #(?P<ch>[^ ]+) :(?P<msg>.*)$")


@dataclass
class ChatEvent:
    t: float
    rate: float
    uniq: int
    z: float
    mood: str
    sample: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


# ── capture ───────────────────────────────────────────────────────────────

def watch(channel: str, out_path: str | Path, *, seconds: float = 3600,
          verbose: bool = True) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    nick = f"justinfan{random.randint(10000, 99999)}"

    s = socket.create_connection((HOST, PORT), timeout=15)
    s.settimeout(1.0)
    s.sendall(b"CAP REQ :twitch.tv/tags\r\n")
    s.sendall(f"PASS SCHMOOPIIE\r\nNICK {nick}\r\n".encode())
    s.sendall(f"JOIN #{channel.lower()}\r\n".encode())

    t0 = time.time()
    n = 0
    buf = b""
    with out_path.open("a") as f:
        while time.time() - t0 < seconds:
            try:
                chunk = s.recv(8192)
            except socket.timeout:
                continue
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
            while b"\r\n" in buf:
                line, buf = buf.split(b"\r\n", 1)
                txt = line.decode("utf-8", errors="replace")
                if txt.startswith("PING"):
                    s.sendall(b"PONG :tmi.twitch.tv\r\n")
                    continue
                m = TAG_RE.match(txt) or PLAIN_RE.match(txt)
                if not m:
                    continue
                rec = {"t": round(time.time() - t0, 3),
                       "user": m.group("who"),
                       "msg": m.group("msg")[:200]}
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n += 1
                if verbose and n % 250 == 0:
                    f.flush()
                    print(f"   {n} messages, {time.time()-t0:.0f}s elapsed", flush=True)
    s.close()
    if verbose:
        print(f"  captured {n} messages over {time.time()-t0:.0f}s -> {out_path}")
    return out_path


# ── analysis ──────────────────────────────────────────────────────────────

def _mood(samples: list[str]) -> str:
    score = {"laugh": 0, "shock": 0, "hype": 0, "negative": 0}
    for sm in samples:
        for w in re.findall(r"[\w\U0001F300-\U0001FAFF]+", sm.lower()):
            if w in LAUGH: score["laugh"] += 1
            elif w in SHOCK: score["shock"] += 1
            elif w in HYPE: score["hype"] += 1
            elif w in NEGATIVE: score["negative"] += 1
    best = max(score, key=score.get)
    return best if score[best] else "neutral"


def analyse(jsonl: str | Path, *, offset: float = 0.0) -> dict:
    """Spike-detect chat rate the same way detect_audio does vocal energy."""
    import numpy as np

    rows = [json.loads(l) for l in Path(jsonl).read_text().splitlines() if l.strip()]
    if not rows:
        return {"events": [], "messages": 0}

    span = max(r["t"] for r in rows)
    nbuck = int(span / HOP_S) + 1
    rate = np.zeros(nbuck)
    users: list[set] = [set() for _ in range(nbuck)]
    texts: list[list[str]] = [[] for _ in range(nbuck)]
    for r in rows:
        b = min(int(r["t"] / HOP_S), nbuck - 1)
        rate[b] += 1
        users[b].add(r["user"])
        if len(texts[b]) < 10:
            texts[b].append(r["msg"])

    win = max(3, int(ROLLING_WINDOW_S / HOP_S))
    pad = win // 2
    padded = np.pad(rate, (pad, pad), mode="edge")
    strides = np.lib.stride_tricks.sliding_window_view(padded, win)[:nbuck]
    med = np.median(strides, axis=1)
    mad = np.median(np.abs(strides - med[:, None]), axis=1)
    mad = np.maximum(mad, MAD_FLOOR_FRAC * max(float(np.median(rate)), 1.0))
    z = (rate - med) / (1.4826 * mad)

    events: list[ChatEvent] = []
    taken: list[int] = []
    minsep = int(MIN_SEPARATION_S / HOP_S)
    for i in np.argsort(-z):
        if z[i] < Z_THRESHOLD:
            break
        if rate[i] < MIN_ABS_RATE:
            continue                       # loud relative to nothing
        if rate[i] < MIN_RATE_MULTIPLE * max(med[i], 0.5):
            continue
        if len(users[i]) < MIN_UNIQUE_CHATTERS:
            continue                       # one person, not a room
        if any(abs(i - j) < minsep for j in taken):
            continue
        taken.append(int(i))
        events.append(ChatEvent(
            t=round(i * HOP_S + offset, 2),
            rate=float(rate[i]),
            uniq=len(users[i]),
            z=round(float(z[i]), 2),
            mood=_mood(texts[i]),
            sample=texts[i][:4],
        ))
    events.sort(key=lambda e: e.t)
    return {
        "messages": len(rows),
        "span_s": round(span, 1),
        "mean_rate": round(len(rows) / max(span, 1), 2),
        "events": [e.as_dict() for e in events],
    }


def chat_score(ev: dict) -> float:
    """0..1. Rate matters, but a crowd beats one spammer."""
    import math

    loud = math.tanh(float(ev["z"]) / 8.0)
    crowd = min(int(ev["uniq"]) / max(float(ev["rate"]), 1.0), 1.0)
    return round(0.7 * loud + 0.3 * crowd, 3)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="live Twitch chat velocity")
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("watch")
    w.add_argument("--channel", required=True)
    w.add_argument("-o", "--out", required=True)
    w.add_argument("--seconds", type=float, default=3600)
    a_ = sub.add_parser("analyse")
    a_.add_argument("jsonl")
    a_.add_argument("-o", "--out", default="-")
    a_.add_argument("--offset", type=float, default=0.0)
    a = ap.parse_args()

    if a.cmd == "watch":
        watch(a.channel, a.out, seconds=a.seconds)
    else:
        res = analyse(a.jsonl, offset=a.offset)
        for e in res["events"]:
            e["score"] = chat_score(e)
        blob = json.dumps(res, indent=2, ensure_ascii=False)
        if a.out == "-":
            print(blob)
        else:
            Path(a.out).write_text(blob)
            print(f"{res['messages']} msgs, {len(res['events'])} spikes -> {a.out}")
