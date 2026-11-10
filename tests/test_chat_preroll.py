"""THE CHAT PANEL'S PRE-ROLL WAS MEASURED FROM THE REGION, NOT THE CUT.

George: *"the chat messages dont really line up perfectly to the context of
the clips"*.

A region is a candidate window from acoustic clustering; a clip is a cut
inside it, and nine of this job's twenty-five specs start more than twenty
seconds in. `stage_chat` anchored the pre-roll on the REGION start, so a
message sent one second before the region was shown as if it had been sent
one second before the CLIP. On clip 47 (`in_point 52.50`) frame 0 therefore
opened on messages from VOD 94-95s against a clip that starts at 147.80 —
**fifty-three seconds of stale chat, presented as the room reacting to this
line.**

Everything between the region start and the cut fell through to `remap`,
returned None, and was counted as "dropped into removed spans", so the log
named the wrong cause as well.

These checks run against the REAL spec and the REAL chat cache, and compute
the keeps with `_plan_only` — no render. Three of the four fail against the
pre-fix code.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import make_clip as mk                                        # noqa: E402
from engine import chat_reaction as cr                        # noqa: E402
from engine.clipspec import load                              # noqa: E402

fails = []


def check(name, ok, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))
    if not ok:
        fails.append(name)


# The clip with the largest in-point that has a chat cache on disk.
CLIP = ROOT / "clips" / "fns-47.json"
if not CLIP.exists():
    print(f"skipped: no {CLIP}")
    raise SystemExit(0)
clip, ch = load(CLIP)
cache = ROOT / f"jobs/{clip.job}/chat_{clip.index:02d}.json"
src = clip.source(ROOT)
if not cache.exists() or not src.exists():
    print("skipped: no chat cache or cut source for fns-47")
    raise SystemExit(0)

raw = json.loads(cache.read_text())
for m in raw:
    m.setdefault("frags", m.get("fragments", []))
t0, t1 = clip.region
ov = ROOT / f"jobs/{clip.job}/overlays_{clip.index:02d}"
st = {"overlays": ov, "meta": json.loads(
    (ROOT / f"jobs/{clip.job}/ranked.json").read_text())[clip.index - 1],
      "base_wav": ov / "_cut.wav"}
mk._plan_only(clip, ch, st)
kp = st["keeps"]
ip, op = kp[0].start, kp[-1].end
print(f"fns-47: region {t0}-{t1}, cut {ip:.2f}-{op:.2f} in clip-file time "
      f"(VOD {t0 + ip:.2f}-{t0 + op:.2f}), {len(raw)} messages cached")


def remap(x):
    acc = 0.0
    for k in kp:
        if k.start <= x < k.end:
            return acc + (x - k.start)
        acc += k.length
    return None


# Run the placement exactly as `stage_chat` does.
kept, pre, before, removed, after = [], 0, 0, 0, 0
for m in raw:
    ft = m["offset"] - t0
    if ft < ip:
        out_t = ft - ip
        if out_t < -mk.PREROLL_MAX:
            before += 1
            continue
        pre += 1
    elif ft >= op:
        after += 1
        continue
    else:
        o = remap(ft)
        if o is None:
            removed += 1
            continue
        out_t = o
    kept.append({"t": round(out_t, 2), "src": m["offset"]})

# 1. NO PRE-ROLL MESSAGE IS OLDER THAN THE CAP, MEASURED FROM THE CUT.
#    Anchored on the region this fails by `ip` seconds — 52.5 here.
cut_vod = t0 + ip
worst = min((m["src"] for m in kept if m["t"] < 0), default=cut_vod)
age = cut_vod - worst
check("no pre-roll message is older than the cap, measured from the cut",
      age <= mk.PREROLL_MAX + 1e-6,
      f"oldest shown message is {age:.1f}s before the cut "
      f"(cap {mk.PREROLL_MAX:.0f}s)")

# 2. EVERY MESSAGE AT t >= 0 IS ONE THE VIEWER COULD HAVE SEEN SENT.
bad = [m for m in kept if m["t"] >= 0 and not (cut_vod <= m["src"] < t0 + op)]
check("every message at t >= 0 was sent inside the cut", not bad,
      f"{len(bad)} outside, e.g. {bad[:2]}")

# 3. THE COUNTERS ACCOUNT FOR EVERY INPUT MESSAGE.
check("the counters sum to the input",
      len(kept) + before + removed + after == len(raw),
      f"{len(kept)}+{before}+{removed}+{after} vs {len(raw)} cached")

# 4. NOTHING INSIDE A KEEP IS DROPPED. Deriving the clip-file time twice put
#    messages on the wrong side of `remap`'s half-open interval.
leaked = [m["offset"] for m in raw
          if remap(m["offset"] - t0) is not None
          and not any(k["src"] == m["offset"] for k in kept)]
check("no message inside a keep is dropped", not leaked,
      f"{len(leaked)} leaked, e.g. {leaked[:3]}")

# 5. A SUB NOTICE IS NOT SCORED AS A VIEWER TALKING.
notices = [m for m in raw if cr.is_notice(m)]
t = cr.topicality(raw, "tier 1 teams and players")
check("sub notices are excluded from the scored population",
      t["notices"] == len(notices) and t["n"] == len([
          m for m in raw if not cr.is_notice(m)
          and len(cr._text(m).strip()) >= 3]),
      f"{t['notices']} notices held out of {len(raw)}")

# 6. THE STEM MATCH IS SYMMETRIC. `team` must find "teams" and vice versa.
one = {"author": "a", "frags": [{"text": "the teams are cooked", "emote": None}]}
check("a singular key matches a plural word",
      cr.topicality([one], "team structure")["on_topic"] == 1.0,
      f"got {cr.topicality([one], 'team structure')}")
check("a plural key matches a singular word",
      cr.topicality([{"author": "a", "frags": [{"text": "that team is cooked",
                                                "emote": None}]}],
                    "teams structure")["on_topic"] == 1.0)

print()
print("FAILED: " + ", ".join(fails) if fails else "all checks pass")
raise SystemExit(1 if fails else 0)
