"""Chat spikes: the moments the room reacted, as candidate regions.

George's note on the first live delivery: "we need more twitch chat moments,
the speed of the chat spikes means that there might be a funny moment". The
hosted pipeline found candidates from the streamer's VOICE only
(`detect_audio`), and chat was read per clip only AFTER ranking, to draw the
overlay. A moment chat exploded over while he spoke at a normal level could
never be picked.

So the whole VOD's chat replay is read once, binned into messages per
`BIN` seconds, and a bin is a spike when it clears its own neighbourhood by
a robust margin (z against a rolling median and MAD) AND an absolute floor.
Chat reacts AFTER the moment — people type — so the region a spike points at
runs back from it. Laughter is scored separately, because a wall of KEKW is
the strongest "this was funny" signal a stream has.

`fetch_all` pages by OFFSET, never by cursor (see `twitch_chat._page`), and
steps to the last message it has seen rather than a fixed 40s, so a busy
chat that fills a page in ten seconds is still read without gaps. Measured
on FNS VOD 2926995155: a page holds 59 messages, about 75s of that chat, and
overlapping pages agree message for message (31 of 31 in the shared span).
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import numpy as np

from engine import twitch_chat as tc

BIN = 10.0              # seconds per velocity bin
BASE_WIN = 300.0        # rolling baseline, either side summed
Z_MIN = 3.0             # robust sigmas over the local median
MIN_RATE = 6            # messages in the bin, whatever the baseline
MIN_GAP = 90.0          # seconds between two spikes
TOP = 25                # spikes passed to the judge
LEAD, TAIL = 75.0, 10.0 # region around a spike: chat lags the moment
HYPE_PLAY = 0.12        # share of hype messages that marks a reaction to a play

LAUGH = re.compile(
    r"\b(kekw|kekl|lul|lulw|omegalul|icant|lmao+|lmfao|lol+|xdd+|pepelaugh|"
    r"aware|haha+h*|ahaha+|dead|deadass|bruh+)\b|😂|🤣|💀", re.I)

# The room reacting to a PLAY rather than a joke. George wants these: a clutch
# or an ace makes chat explode with Pog and caps while the streamer may only
# yell, so the transcript alone undersells them.
HYPE = re.compile(
    r"\b(pog+|pogg+ers|pogchamp|pogu|poggies|ace+|clutch|clip+ (it|that|this)|"
    r"clip+|let'?s+ go+|lets+ go+|lfg+|w+|dub|ez+|sheesh+|insane+|holy+|omg+|"
    r"no way+|what+ the|wtf|1v[1-5]|nt|monkaw|monkas|clap|goated|cracked|"
    r"aim|diff|filthy|nasty|disgusting)\b|🔥|😱|🤯|‼|!!", re.I)


def fetch_all(video_id: str, duration: float, *, pause: float = 0.3,
              log=print) -> tuple[list[dict], int]:
    """Every replay message as {t, text}, and how many jumps it saw between
    pages — a skipped stretch, or simply a silent one; the API cannot say."""
    seen: dict[str, dict] = {}
    off, last_t, gaps, calls = 0.0, None, 0, 0
    while off < duration:
        edges = tc._page(video_id, off)["edges"]
        calls += 1
        ts = []
        for e in edges:
            n = e["node"]
            t = float(n["contentOffsetSeconds"])
            ts.append(t)
            if n["id"] not in seen:
                seen[n["id"]] = {"t": t, "text": "".join(
                    f.get("text") or "" for f in n["message"]["fragments"])}
        if not ts:
            off += 40.0
            continue
        if last_t is not None and min(ts) > last_t + 1.0:
            gaps += 1
        last_t = max(ts)
        off = max(off + 10.0, last_t)
        time.sleep(pause)
        if calls % 100 == 0:
            log(f"  chat: {calls} pages, {len(seen)} messages, at {off / 60:.0f} min")
    msgs = sorted(seen.values(), key=lambda m: m["t"])
    return msgs, gaps


def spikes(msgs: list[dict], duration: float) -> list[dict]:
    """The strongest chat bursts, strongest first."""
    if not msgs:
        return []
    nb = int(duration // BIN) + 1
    t = np.array([m["t"] for m in msgs])
    idx = np.clip((t // BIN).astype(int), 0, nb - 1)
    count = np.bincount(idx, minlength=nb).astype(float)
    laugh = np.bincount(idx, weights=[bool(LAUGH.search(m["text"])) for m in msgs],
                        minlength=nb)
    hype = np.bincount(idx, weights=[bool(HYPE.search(m["text"])) for m in msgs],
                       minlength=nb)
    w = int(BASE_WIN // BIN)

    def robust_z(series, i):
        nbh = np.concatenate([series[max(0, i - w):max(0, i - 1)], series[i + 2:i + 1 + w]])
        if len(nbh) < 6:
            return None, None
        med = float(np.median(nbh))
        mad = float(np.median(np.abs(nbh - med))) * 1.4826
        return (series[i] - med) / max(mad, np.sqrt(med), 1.0), med

    cand = []
    for i in range(nb):
        z, med = robust_z(count, i)
        if z is None:
            continue
        busy = z >= Z_MIN and count[i] >= max(MIN_RATE, 2 * med)
        # A PLAY can make chat hype without making it much busier: on FNS VOD
        # 2885323336 "crazy read / LETS GO BOY" and "W BUZZ / eco monster"
        # were hype bursts in an already fast chat. So hype counts on its own.
        hz, hmed = robust_z(hype, i)
        hyped_burst = hz >= Z_MIN and hype[i] >= max(MIN_RATE, 2 * hmed)
        if not (busy or hyped_burst):
            continue
        share, hyped = laugh[i] / count[i], hype[i] / count[i]
        score = 0.7 * float(np.tanh(max(z, hz) / 6)) + 0.3 * max(share, hyped)
        cand.append({"t": round((i + 0.5) * BIN, 1), "count": int(count[i]),
                     "baseline": round(med, 1), "z": round(float(z), 1),
                     "laugh": round(float(share), 2), "hype": round(float(hyped), 2),
                     "score": round(float(score), 3)})
    out = []
    for c in sorted(cand, key=lambda c: -c["score"]):
        if all(abs(c["t"] - o["t"]) >= MIN_GAP for o in out):
            out.append(c)
    return out[:TOP]


def describe(sp: dict, msgs: list[dict], n: int = 8) -> str:
    """One line for the judge: when chat spiked, how hard, and what it said."""
    lo, hi = sp["t"] - BIN / 2, sp["t"] + BIN / 2
    said = [m["text"].strip() for m in msgs if lo <= m["t"] < hi and m["text"].strip()]
    said = sorted(set(said), key=said.index)[:n]
    hyped = sp.get("hype", 0.0)
    play = (f" {hyped:.0%} of chat is hyping a PLAY (Pog, caps, 'clip it'): "
            f"this is a gameplay reaction moment, so the clip is the play and "
            f"his reaction to it, see REACTION MOMENTS."
            if hyped >= HYPE_PLAY and hyped >= sp["laugh"] else "")
    return (f"Twitch chat spiked at {sp['t']:.0f}s: {sp['count']} messages in "
            f"{BIN:.0f}s against a usual {sp['baseline']:.0f}, "
            f"{sp['laugh']:.0%} of them laughing.{play} Chat reacts a few seconds "
            f"AFTER the moment, so look just before {sp['t']:.0f}s. Some of what "
            f"chat said: " + " | ".join(said[:n]))


def regions(job: Path, video_id: str, duration: float, *, log=print) -> list[dict]:
    """Chat-spike regions for `job`, cached in chat_spikes.json."""
    p = job / "chat_spikes.json"
    if p.exists():
        return json.loads(p.read_text())
    try:
        msgs, gaps = fetch_all(video_id, duration, log=log)
    except Exception as e:                                # noqa: BLE001
        log(f"  chat: replay unavailable ({type(e).__name__}: {e}); voice only")
        return []
    sp = spikes(msgs, duration)
    out = [{"start": round(max(0.0, s["t"] - LEAD), 2),
            "end": round(min(duration, s["t"] + TAIL), 2),
            "chat": s, "hint": describe(s, msgs)} for s in sp]
    log(f"  chat: {len(msgs)} messages, {gaps} gap(s), {len(out)} spike(s)")
    p.write_text(json.dumps(out, indent=1))
    return out
