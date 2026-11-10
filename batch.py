#!/usr/bin/env python3
"""Make clips en masse from one VOD job. The production line.

George: *"the main thing is essentially making these en masse, build the
full pipeline for developing this."*

    ./.venv/bin/python batch.py fns-2905408276 screen
    ./.venv/bin/python batch.py fns-2905408276 prep
    ./.venv/bin/python batch.py fns-2905408276 specs
    ./.venv/bin/python batch.py fns-2905408276 build
    ./.venv/bin/python batch.py fns-2905408276 report

WHAT SHAPES THIS, and none of it is throughput:

**1. THE YIELD IS LOW AND THE SCREEN IS THE POINT.** Measured across all 50
clips of this VOD: **10 are buildable**. Forty are rejected, almost all for
DMCA muting at 20-55% — tightening those means splicing across speech
nobody can hear, every few seconds. Ranking by virality picks clips the
pipeline cannot cut, so `screen` runs first and everything downstream reads
its verdict.

**2. FIVE OF THE TEN SURVIVORS ARE THE SAME TOPIC.** Clips 06, 15, 23, 30
and 42 are all "open qualifiers are better/worse than franchising". Shipping
them is shipping one idea five times, which is worse for a channel than
shipping two clips. `specs` groups by topic and keeps the strongest of each
group; the rest stay in the manifest as held, not deleted.

**3. BUILDS RUN IN LANES, AND WHAT LIMITED THEM WAS NOT THE RENDERER.**
This said "Resolve is a single GUI app, so builds are serial" — true of
`--renderer resolve`, and the native ffmpeg path has been the default for a
while. What actually made the native path serial was two silent collisions:
the PNG sequence directory was keyed by COMPOSITION NAME, so two clips wrote
the same 1020 `Bait` filenames into one directory and the mixture encoded
with no error at all; and `Root.tsx` imported its chat, windows, duration
and story list out of one shared `public/` tree, which webpack inlines at
bundle time, so `--public-dir` could not have fixed it either. Both are
fixed, and what is left is MEMORY — `lanes_for()` measures free pages
against ~1.9 GB a lane and runs that many. Everything CHEAP — transcription,
chat, facecam detection — still runs in `prep` ahead of time, and each clip
is independent so a failure costs one clip and not the run.

**4. EVERY CLIP IS GATED ON THE ARTIFACT.** `engine/deliver_qc` runs on the
rendered file, not the plan. A clip that fails does not go in the delivery
folder; it goes in the manifest with the reason.

WHAT THIS DOES NOT DO, stated so it is not mistaken for finished: it does
not decide whether a clip is WORTH watching. One narrative, explains
itself, ends on the payoff, and the hook line — those are editorial. `specs`
reads them from `editorial.json`, which a judging pass or a human writes,
and falls back to safe defaults with a warning when there is none.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from engine import jsonstore                                   # noqa: E402
sys.path.insert(0, str(ROOT))

DELIVER = ROOT / "deliver"
STOP = set("the a an and or but if is are was were to of in on at for with that this "
           "it its he she they them his her their do does did will would can could "
           "should have has had not no yes so as by from what when where who why how "
           "which just get got go going gonna think know really about than then there "
           "all any more most some you your we our us me my i".split())


def log(*a):
    print(*a, flush=True)


def _paths(job):
    d = ROOT / f"jobs/{job}"
    return d, d / "screened.json", d / "editorial.json", d / "manifest.json"


# ------------------------------------------------------------- screen ----
def cmd_screen(job, args):
    d, screened, _e, _m = _paths(job)
    subprocess.run([sys.executable, str(ROOT / "screen_clips.py"), job,
                    "--n", str(args.n), "--json", str(screened)], check=True)


# --------------------------------------------------------------- prep ----
def cmd_prep(job, args):
    """Everything cheap, before Resolve is touched: words, chat, facecam."""
    from engine import facecam, twitch_chat
    from engine.clipspec import load
    d, screened, _e, _m = _paths(job)
    rows = [r for r in json.loads(screened.read_text()) if r["verdict"] == "build"]
    ranked = json.loads((d / "ranked.json").read_text())
    (d / "words").mkdir(exist_ok=True)
    chan = _channel(job)

    todo = [r["n"] for r in rows if not (d / f"words/{r['n']:02d}.json").exists()]
    if todo:
        log(f"[words] transcribing {len(todo)}: {todo}")
        for n in todo:
            src = sorted((d / "clips_1080").glob(f"{n:02d}_*.mp4"))[0]
            from engine import transcribe
            tr = transcribe.transcribe(src)
            (d / f"words/{n:02d}.json").write_text(json.dumps(tr))
            log(f"   {n:02d}: {sum(len(u['words']) for u in tr['utterances'])} words")
    else:
        log("[words] all present")

    log("[facecam] detecting per clip")
    cams = {}
    for r in rows:
        src = sorted((d / "clips_1080").glob(f"{r['n']:02d}_*.mp4"))[0]
        f = facecam.detect(src)
        cams[r["n"]] = {"rect": list(f.rect), "margin": f.margin} if f else None
        flag = "" if (f and f.margin >= 4) else "   LOW CONFIDENCE"
        log(f"   {r['n']:02d}: {f.rect if f else 'NOT FOUND'}"
            f"{f'  {f.margin:.0f}x' if f else ''}{flag}")

    log("[chat] fetching where missing")
    for r in rows:
        cache = d / f"chat_{r['n']:02d}.json"
        if cache.exists():
            continue
        m = ranked[r["n"] - 1]
        try:
            from engine import chat_reaction as cr
            msgs = twitch_chat.fetch(chan["vod_id"],
                                     m["in_point"] - cr.CONTEXT_PAD,
                                     m["out_point"] + cr.CONTEXT_PAD)
            twitch_chat.to_json(msgs, cache)
            log(f"   {r['n']:02d}: {len(msgs)}")
        except Exception as e:
            # CHAT REPLAY IS PERISHABLE — it dies with the VOD, on a rolling
            # ~60-day window. A miss here is not a build failure; the clip
            # ships without the overlay and the manifest says so.
            log(f"   {r['n']:02d}: chat unavailable ({type(e).__name__})")
        time.sleep(1.0)
    (d / "facecams.json").write_text(json.dumps(cams, indent=1))
    log(f"-> {d/'facecams.json'}")


# -------------------------------------------------------------- specs ----
def _topic(subject: str) -> frozenset:
    return frozenset(w for w in re.findall(r"[a-z]+", subject.lower())
                     if w not in STOP and len(w) > 3)


def cmd_editorial(job, args):
    """Title and judge every buildable clip. The stage this file has always
    read and never had.

    `cmd_specs` takes each clip's hook, in-point, topic and verdict from
    `editorial.json`, and its own log warns when the file is missing — but
    nothing in the repo wrote it. This VOD's ten entries were written by hand,
    so the seventeen clips the screen later rescued reached the UI with no
    title at all and were listed by their `subject` line, which is a
    description of a clip rather than a name for it.
    """
    from engine import editorial
    d, screened, ed_path, _m = _paths(job)
    rows = [r for r in json.loads(screened.read_text()) if r["verdict"] == "build"]
    ranked = json.loads((d / "ranked.json").read_text())
    ed = json.loads(ed_path.read_text()) if ed_path.exists() else {}
    force = bool(getattr(args, "force", False))
    only = {int(x) for x in str(getattr(args, "only", "") or "").replace(",", " ").split()}

    todo = []
    for r in rows:
        n = r["n"]
        if only and n not in only:
            continue
        # NEVER REGENERATE AN ENTRY WITHOUT --force. These carry hooks George
        # has seen and in-points he moved; `specs` eating a reviewed spec is
        # already the most-repeated defect in this repo.
        if str(n) in ed and not force:
            continue
        wf = d / f"words/{n:02d}.json"
        if not wf.exists():
            log(f"   {n:02d} no transcript yet — run prep first")
            continue
        m = ranked[n - 1]
        words = json.loads(wf.read_text())
        # JUDGE THE WINDOW, NOT THE REGION.
        #
        # `screen_clips.best_window` returns a span when the whole region
        # FAILS the mute/cadence gate, and that span is the clip. Handing the
        # pass the whole region then asks it where a DIFFERENT, longer piece
        # of audio should start — and on this VOD 15 of 17 windowed clips came
        # back with an in-point at or BEFORE the window's start, i.e. inside
        # audio the clip does not contain. That is why those clips still open
        # mid-clause, which AGENTS.md has carried as unsolved.
        #
        # Times are REBASED to 0 rather than passed through, because the
        # prompt promises "in_point is in seconds from the beginning of THIS
        # transcript" and "0.0 is correct whenever the material already begins
        # at the top". Both stay literally true on a rebased window; passing
        # [82.0] as the first line would make the model guess which origin we
        # meant. The offset goes back on below.
        win = r.get("window")
        off = 0.0
        if win:
            lo, hi = float(win["in"]), float(win["out"])
            us = [dict(u, start=float(u["start"]) - lo)
                  for u in words.get("utterances", [])
                  if lo <= float(u["start"]) < hi]
            if us:
                words, off = {**words, "utterances": us}, lo
                log(f"   {n:02d} judging the screen's window "
                    f"{lo:.1f}-{hi:.1f}s ({len(us)} utterances), not the "
                    f"{m['out_point'] - m['in_point']:.0f}s region")
        todo.append({"n": n, "words": words, "offset": off,
                     "window": win if off or (win and us) else None,
                     "subject": m.get("subject", ""), "claim": m.get("claim", "")})
    if not todo:
        log(f"[editorial] nothing to do ({len(ed)} entries already)")
        return ed

    log(f"[editorial] judging {len(todo)}: {[c['n'] for c in todo]}")

    def done(n, e, err):
        if e is None:
            log(f"   {n:02d} FAILED: {err}")
        else:
            flag = "" if e.verdict == "ship" else "   <- DROP"
            log(f"   {n:02d} {e.hook}{flag}"
                + (f"   in_point {e.in_point}" if e.in_point else ""))

    fresh = editorial.judge_many(todo, handle=_channel(job)["name"], on_done=done)
    # BACK TO CLIP-FILE SECONDS. Every other in-point in this pipeline — the
    # spec, the window, the snap — is measured from the start of the clip
    # FILE, so a windowed judgement is shifted back before it is stored.
    # editorial.json must hold one kind of number, not two.
    for c in todo:
        e = fresh.get(str(c["n"]))
        if e and c.get("window"):
            lo, hi = float(c["window"]["in"]), float(c["window"]["out"])
            e["in_point"] = round(float(e["in_point"]) + c["offset"], 2)
            e["why"] = (f"[judged on the screen's window {lo:.1f}-{hi:.1f}s, "
                        f"not the whole region] " + e.get("why", ""))
    # MERGE UNDER A LOCK, THROUGH A TEMP PATH. `ed` was read at the top of
    # this function, before up to 27 model calls — so two of these running
    # at once (one click on a clip while the chain's `editorial` stage is
    # going) lose everything the other judged, and a write interrupted part
    # way leaves `editorial.json` as JSON that cannot be parsed, which fails
    # every later read of the job. The lock is around the merge only, never
    # around the model calls.
    ed = jsonstore.merge(ed_path, fresh, sort_keys=True)
    ship = sum(1 for v in ed.values() if v.get("verdict") != "drop")
    log(f"[editorial] {len(fresh)} judged, {len(ed)} entries, {ship} ship")
    return ed


def cmd_specs(job, args):
    """One spec per clip we intend to build, after topic dedup."""
    from engine.clipspec import Clip, save
    d, screened, editorial, _m = _paths(job)
    rows = [r for r in json.loads(screened.read_text()) if r["verdict"] == "build"]
    ranked = json.loads((d / "ranked.json").read_text())
    cams = json.loads((d / "facecams.json").read_text()) if (d / "facecams.json").exists() else {}
    ed = json.loads(editorial.read_text()) if editorial.exists() else {}
    if not ed:
        log("!! no editorial.json — in-points default to 0.0 and clips get no "
            "hook line. Run the editorial pass; see the module docstring.")
    chan = _channel(job)

    # TOPIC DEDUP. Five of this VOD's ten survivors argue the same thing;
    # shipping all five is shipping one idea five times.
    # Use the EDITORIAL topic where there is one. The ranked `subject` lines
    # are written per clip and word the same argument differently every
    # time, so overlapping them found nothing — 10 clips in, 10 out — while
    # the editorial pass had already labelled three of them
    # "open qualifiers vs franchising" in as many words.
    groups, kept, held = [], [], []
    for r in sorted(rows, key=lambda r: -(r["strength"] or 0)):
        if ed.get(str(r["n"]), {}).get("verdict") == "drop":
            continue
        t = _topic(ed.get(str(r["n"]), {}).get("topic") or r["subject"])
        # Two shared words is NOT the same topic. "open qualifiers unpaid
        # months" and "open qualifiers vs franchising" are different
        # arguments that happen to name the same thing, and an
        # intersection>=2 rule merged them and took the batch from 10 clips
        # to 3. Jaccard over the whole label is the test: identical labels
        # score 1.0, a shared noun scores 0.4.
        def _sim(a, b):
            return len(a & b) / max(len(a | b), 1)
        hit = next((g for g in groups if _sim(t, g["topic"]) >= 0.5), None)
        if hit:
            hit["also"].append(r)
            held.append((r, hit["lead"]))
        else:
            groups.append({"topic": t, "lead": r, "also": []})
            kept.append(r)
    # `--only N` SKIPS THE DEDUP. Topic dedup is right for a batch — five of
    # this VOD's survivors argue the same thing and shipping all five ships
    # one idea five times. It is wrong when a person has pointed at one clip
    # and asked for it: they are not asking for a balanced batch, they are
    # asking for that clip. So the UI's "make this one" writes its spec here
    # regardless of what leads its topic group.
    want = {int(x) for x in str(getattr(args, "only", "") or "").replace(",", " ").split()}
    if want:
        # A NAMED CLIP ALSO OVERRIDES AN EDITORIAL DROP. The pass vetoes for
        # real reasons — two narratives, opens mid-thought — but those are
        # advice, and a person who has clicked this clip has outvoted them.
        # Silently writing nothing would look like a broken button.
        by_n = {r["n"]: r for r in rows}
        missing = sorted(want - set(by_n))
        if missing:
            log(f"[specs] --only {sorted(want)}: {missing} are not buildable, skipped")
        kept = [by_n[n] for n in sorted(want & set(by_n))]
        log(f"[specs] --only: writing {[r['n'] for r in kept]}, dedup bypassed")
    else:
        log(f"[specs] {len(rows)} buildable -> {len(kept)} after topic dedup")
    for g in groups:
        if g["also"]:
            log(f"   {g['lead']['n']:02d} leads; held: "
                f"{[x['n'] for x in g['also']]}  ({g['lead']['subject'][:52]})")

    (ROOT / "clips").mkdir(exist_ok=True)
    force = bool(getattr(args, "force", False))
    written = []
    for r in kept:
        n = r["n"]
        m = ranked[n - 1]
        e = ed.get(str(n), {})
        if e.get("verdict") == "drop":
            if n not in want:
                log(f"   {n:02d} DROPPED by the editorial pass: {e.get('why','')[:60]}")
                continue
            log(f"   {n:02d} the editorial pass DROPPED this one — "
                f"{e.get('why','')[:70]} — building anyway because it was "
                f"asked for by name")
        cam = (cams.get(str(n)) or {}).get("rect")
        spec = ROOT / f"clips/{chan['name']}-{n:02d}.json"
        # NEVER OVERWRITE A SPEC THAT EXISTS. **Every round of George's review
        # lands in these files** — the in-point he moved, the out-point he
        # chose, `chat_mode`, the pinned facecam rect, the notes recording
        # WHY. Re-running `specs` regenerated clip 12 from `editorial.json`
        # and put its in_point back to 6.7 from 23.3, dropped out_point
        # 86.80 to None and `chat_mode` "continuous" to None: four rounds of
        # his notes gone, silently, from a stage whose job is only to pick
        # which clips to make.
        #
        # `specs` proposes a starting spec; the review owns it afterwards.
        # `--force` is there for when the editorial pass really should win.
        if spec.exists() and not force:
            # FILL WHAT IS MISSING; NEVER CHANGE WHAT IS SET.
            #
            # "Left alone" was right against regenerating a reviewed spec and
            # wrong against one THIS COMMAND wrote moments earlier with
            # placeholder values. `editorial` was not in the pipeline at all,
            # so every spec got `in_point 0.0` — the top of the candidate
            # REGION, which is an acoustic boundary and not where the
            # argument starts. That is George's "it starts too early", on 10
            # of 25 specs, and the real in-point was sitting in
            # editorial.json unable to reach them.
            #
            # 0.0 means "nobody decided", so adopting a real value loses
            # nothing. A non-zero in-point is somebody's decision and is left
            # exactly as it is.
            try:
                cur = json.loads(spec.read_text())
            except json.JSONDecodeError:
                cur = {}
            c = cur.get("clip", {})
            fills = {}
            if not float(c.get("in_point") or 0.0) and float(e.get("in_point") or 0.0):
                fills["in_point"] = float(e["in_point"])
            if not c.get("hook") and e.get("hook"):
                fills["hook"] = e["hook"]
            if fills:
                c.update(fills)
                cur["clip"] = c
                spec.write_text(json.dumps(cur, indent=1) + "\n")
                log(f"   {n:02d} -> {spec.name} kept, filled "
                    + ", ".join(f"{k}={v!r}" for k, v in fills.items()))
            else:
                log(f"   {n:02d} -> {spec.name} EXISTS, left alone "
                    f"(--force to regenerate from editorial.json)")
            written.append(spec)
            continue
        # A WINDOW FROM THE SCREEN BEATS THE EDITORIAL PASS'S IN-POINT.
        # `screen_clips.best_window` only returns one when the whole region
        # FAILED the gate, and it is the span that makes the clip buildable
        # at all — so it is not a suggestion to weigh against a default of
        # 0.0, it is the reason this clip is in the list.
        win = r.get("window")
        # NO ENTRY MEANS NOBODY DECIDED, AND THAT MUST NOT BE SILENT.
        # `editorial` runs before this stage now, so every buildable clip
        # should have a verdict by the time we get here. When one does not —
        # a clip the screen rescued after the pass ran, say — the in-point
        # falls back to 0.0, which is the top of the candidate REGION: an
        # acoustic cluster boundary, not where the argument starts. That is
        # the exact defect the stage was added to fix, so it is named here
        # instead of being written into a spec that looks decided.
        if not e and not win:
            log(f"   {n:02d} !! NO EDITORIAL ENTRY — in_point falls back to "
                f"0.0 (the top of the region, not where the argument "
                f"starts) and the clip gets no hook. Run: batch.py {job} "
                f"editorial --only {n}")
        ed_in = float(e.get("in_point") or 0.0)
        in_pt = ed_in
        out_pt = None
        note = e.get("why") or m["subject"]
        if win:
            in_pt, out_pt = float(win["in"]), float(win["out"])
            note = (f"{note}  Cut to {in_pt:.0f}-{out_pt:.0f}s by the screen: "
                    f"the whole region is {r['src_s']:.0f}s and fails the gate, "
                    f"this window is {win['muted']:.0%} muted at "
                    f"{win['cuts_min']:.0f} cuts/min. The window makes it "
                    f"BUILDABLE; whether it is one narrative and explains "
                    f"itself is still an editorial call.")
        save(spec, Clip(job=job, index=n, channel=chan["name"],
                        in_point=in_pt, out_point=out_pt,
                        region=(m["in_point"], m["out_point"]),
                        hook=e.get("hook"), cards=[],
                        cam=tuple(cam) if cam else None,
                        notes=note), _channel_obj(job))
        written.append(spec)
        log(f"   {n:02d} -> {spec.name}  in_point {in_pt}"
            + (f" out_point {out_pt}  (screen window)" if win else "")
            + f"  hook {e.get('hook')!r}")
    log(f"[specs] wrote {len(written)}")
    return written


def vod_id_for(job: str) -> str:
    """The VOD id, taken from the JOB NAME rather than the channel file.

    A job is `<channel>-<vod id>`, so the id is already in the name — and
    `Channel.vod_id` held a second copy. That is this repo's most-repeated
    defect with a real consequence attached: the id is what
    `twitch_chat.fetch` pulls chat with, so a SECOND VOD from a channel
    already on file would fetch the FIRST one's chat and composite real
    viewers' messages onto lines they were never written about. That exact
    thing has shipped here once, from the media-pool collision, and it took
    George watching the clip to catch.

    A local file has no VOD id and gets "", which is what `make_clip`
    already treats as "no chat for this clip".
    """
    tail = job.rsplit("-", 1)[-1] if "-" in job else ""
    return tail if tail.isdigit() else ""


def _channel(job):
    """The channel spec, created with house defaults the first time a
    channel is seen.

    THIS CRASHED ON ANY CHANNEL BUT `fns`. It was a bare `read_text()` with
    no existence check, so the first thing a new streamer's VOD met was a
    FileNotFoundError several stages in — after ingest and transcription had
    already run. Everything in the file except two values is house style,
    which is the same reason it belongs in code: the seam, the chrome crop,
    the frame rate and the grade are measured once for the project, not per
    streamer, and the facecam rect is DETECTED per clip by `facecam.detect`
    because a streamer moves their own layout between scenes.

    The two that are not defaults:

      * `permission` — a rights basis, which is a human's assertion and
        never a default. The site writes it from the job's declared rights
        when it creates the job; a channel file reaching here without one
        still stops the build, as it always has.
      * `vod_id` — no longer stored at all; `vod_id_for` derives it.
    """
    f = ROOT / f"channels/{job.split('-')[0]}.json"
    if not f.exists():
        name = job.split("-")[0]
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({
            "name": name,
            # a placeholder only: `facecam.detect` measures the real rect
            # per clip, and `prep` writes it into each spec.
            "cam": [1456, 818, 1920, 1080],
            "seam": 0.42, "chrome": 92, "fps": 60,
            "grade": {"NodeIndex": "1", "Slope": "1.06 1.06 1.07",
                      "Offset": "-0.012 -0.012 -0.010",
                      "Power": "1.06 1.06 1.06", "Saturation": "1.18"},
            "arc": None,
            "permission": "", "permission_note": "",
        }, indent=1) + "\n", encoding="utf-8")
        log(f"[channel] created channels/{name}.json with house defaults — "
            f"it has NO rights basis, so set `permission` before building")
    c = json.loads(f.read_text(encoding="utf-8"))
    # ONE SOURCE FOR THE VOD ID, and the job name is it.
    c["vod_id"] = vod_id_for(job) or c.get("vod_id") or None
    return c


def _channel_obj(job):
    from engine.clipspec import Channel
    c = _channel(job)
    c = dict(c)
    c["cam"] = tuple(c["cam"])
    return Channel(**c)


# -------------------------------------------------------------- build ----
def lanes_for(want: int | None = None) -> int:
    """How many clips may build at once, measured against free memory.

    George: *"why doesnt it let me clip multiple clips at once? needs to
    allow this possibility"*. Two things were in the way and neither was a
    policy: a PNG sequence directory keyed by composition name, and
    `Root.tsx` importing its per-clip data out of one shared `public/`
    directory. Both are fixed; what is left is a real resource limit.

    **Measured on this machine**, 16 GB, during an overlay render: a build
    peaks near 1.9 GB (Chrome tabs plus ffmpeg), and free+inactive with
    nothing building reads 2.4-4.1 GB with swap already 90% full. So two
    lanes fit and a third thrashes — and thrashing is worse than queueing,
    because swap pressure slows the lane that is already running.

    This is a BUDGET TO MEASURE AGAINST, not a swept curve: the per-lane
    figure is a fit to one configuration. `CLIP_LANES` overrides it, and a
    machine with less free memory than two lanes need drops to one rather
    than being told it cannot build.
    """
    want = want or int(os.environ.get("CLIP_LANES", "2"))
    want = max(1, want)
    free = _free_gb()
    if free is None:
        return want
    # NOT `free // LANE_GB`. Floating-point floor division on these values
    # is a knife edge: `3.8 // 1.9` is **1.0**, because 3.8 is stored as
    # 3.7999999999999998 — so a machine with exactly two lanes' worth of
    # memory got one, for a reason that is representation and not memory.
    # This repo's own record is full of thresholds that turned out to be
    # knife edges, so the comparison is explicit and has a named reserve
    # either side of it.
    fits = 1
    while free >= (fits + 1) * LANE_GB + RESERVE_GB and fits < want:
        fits += 1
    if fits < want:
        log(f"[build] {want} lanes asked for, {free:.1f} GB free at "
            f"~{LANE_GB:.1f} GB a lane plus {RESERVE_GB:.1f} GB reserved "
            f"— running {fits}")
    return min(want, fits)


# MEASURED, not modelled — see the note in `lanes_for`. `RESERVE_GB` is the
# headroom left for the machine itself, so the last lane never takes the
# final free page: swap on this machine is already 90% full, and thrashing
# slows the lane that is already running.
LANE_GB = float(os.environ.get("CLIP_LANE_GB", "1.0"))
RESERVE_GB = float(os.environ.get("CLIP_RESERVE_GB", "0.8"))


def _free_gb() -> float | None:
    """Free + inactive, in GB. Inactive pages are reclaimable, so counting
    only `free` reads this machine as having almost nothing."""
    try:
        out = subprocess.run(["vm_stat"], capture_output=True, text=True,
                             check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    page = 4096
    m = re.search(r"page size of (\d+)", out)
    if m:
        page = int(m.group(1))
    got = {}
    for key in ("free", "inactive", "speculative"):
        m = re.search(rf"Pages {key}:\s+(\d+)", out)
        if m:
            got[key] = int(m.group(1))
    if "free" not in got:
        return None
    return (got.get("free", 0) + got.get("inactive", 0)) * page / 1024 ** 3


def clip_log(d, index: int) -> Path:
    """Where ONE clip's build output goes.

    With lanes, the parent's stdout cannot carry every clip's output — two
    make_clip processes interleaving line by line is unreadable, and the
    website reads a log per clip to say which one it is on. So each lane
    writes its own file and the parent keeps the headlines.
    """
    f = d / "web" / f"build-{index:02d}.log"
    f.parent.mkdir(parents=True, exist_ok=True)
    return f


def _build_one(spec, chan, d, manifest, args) -> tuple[str, bool]:
    """One clip, start to delivered. Returns (key, shipped)."""
    from engine.clipspec import load
    key = spec.stem
    clip, ch = load(spec)
    out = ROOT / f"renders/{clip.slug}.mp4"
    t0 = time.time()
    lg = clip_log(d, clip.index)
    log(f"[{key}] building — output in {lg.relative_to(ROOT)}")
    with lg.open("w") as fh:
        fh.write(f"$ make_clip.py {spec.name} "
                 f"--renderer {getattr(args, 'renderer', 'native')}\n\n")
        fh.flush()
        try:
            # NATIVE BY DEFAULT — `make_clip`'s own default, passed
            # explicitly so the build log says which renderer made the file.
            # Resolve stays reachable with `--renderer resolve` for format
            # work; it is the one path that cannot run two at a time,
            # because its API is served on its GUI thread.
            #
            # STDERR INTO THE SAME FILE. It used to inherit the parent's, so
            # a traceback went wherever the caller's stderr pointed — under
            # the site that is the service log, not the build log the page
            # reads. A failed clip recorded `returned non-zero exit status 1`
            # and nothing else.
            subprocess.run([sys.executable, str(ROOT / "make_clip.py"),
                            str(spec), "--renderer",
                            getattr(args, "renderer", "native")],
                           check=True, stdout=fh, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            log(f"[{key}] BUILD FAILED: {e} — see {lg.relative_to(ROOT)}")
            jsonstore.merge(manifest, {key: {"built": False, "error": str(e),
                                             "log": str(lg.relative_to(ROOT))}})
            return key, False
    # gate on the ARTIFACT
    try:
        rep = _qc_for(clip, ch, out)
        soft = [f.check for f in rep.findings if not f.ok]
        log(f"[{key}] {'PASS' if rep.ok else 'FAIL'}"
            + (f" — noted: {', '.join(soft)}" if soft else " — every check"))
        lg.open("a").write("\n" + rep.text() + "\n")
        entry = {"built": True, "qc_ok": rep.ok,
                 "seconds": round(time.time() - t0),
                 "render": str(out.relative_to(ROOT)),
                 "log": str(lg.relative_to(ROOT)),
                 "findings": [{"check": f.check, "ok": f.ok, "detail": f.detail}
                              for f in rep.findings],
                 "subject": clip.notes,
                 "permission": chan.get("permission"),
                 "permission_note": chan.get("permission_note", "")}
        if rep.ok:
            entry["delivered"] = str(_deliver(clip, chan, d, out, rep)
                                     .relative_to(ROOT))
            log(f"[{key}] -> {entry['delivered']}  (+ sidecar)")
        else:
            log(f"[{key}] HELD BACK — failed the delivery gate")
        jsonstore.merge(manifest, {key: entry})
        return key, rep.ok
    except Exception:
        log(f"[{key}] QC ERROR\n{traceback.format_exc()}")
        jsonstore.merge(manifest, {key: {"built": True, "qc_ok": False,
                                         "error": "qc raised",
                                         "log": str(lg.relative_to(ROOT))}})
        return key, False


def _deliver(clip, chan, d, out, rep) -> Path:
    """A DELIVERABLE NEEDS A NAME AND A SIDECAR. "fns-2905408276-06.mp4"
    tells whoever posts it nothing, and they also need the title, the source
    timestamps and the rights basis in one place — that is the difference
    between a render and something you can actually publish."""
    # THE HOOK IS THE TITLE, so it names the file. This slugged `clip.notes`,
    # which is the editorial pass's REASONING — clip 04 delivered as
    # "fns-04-it-is-genuinely-one-narrative-no-pivot-titleable-in.mp4", an
    # internal note escaped into the name of a deliverable. The hook opens
    # with the handle ("FNS: ..."), and the file already starts with the
    # channel, so stripping it avoids "fns-04-fns-i-like-people-who...".
    _h = re.sub(rf"^{re.escape(chan['name'])}\s*(?::|\bon\b)\s*", "",
                (clip.hook or clip.notes or ""), flags=re.I)
    slug = re.sub(r"[^a-z0-9]+", "-", _h.lower())[:52].strip("-")
    dst = DELIVER / f"{chan['name']}-{clip.index:02d}-{slug}.mp4"
    # ONE CLIP, ONE DELIVERY. The hook names the file, so editing a hook and
    # rebuilding wrote a SECOND delivery beside the first and left both:
    # clip 07 sat in here twice, under its old subject-derived name and its
    # new title, same clip, two different cuts. Whoever posts from this
    # folder has no way to tell which is current, and the website's spec
    # editor makes a hook edit an ordinary thing to do.
    #
    # Bounded to this channel and this clip index, and it names what it
    # removes — a silent delete in a delivery folder is worse than a stale
    # file.
    for old_mp4 in sorted(DELIVER.glob(f"{chan['name']}-{clip.index:02d}-*.mp4")):
        if old_mp4 == dst:
            continue
        log(f"[{clip.job}-{clip.index:02d}] superseding {old_mp4.name}")
        old_mp4.unlink()
        old_mp4.with_suffix(".json").unlink(missing_ok=True)
    subprocess.run(["cp", str(out), str(dst)], check=True)
    m = json.loads((d / "ranked.json").read_text())[clip.index - 1]
    dst.with_suffix(".json").write_text(json.dumps({
        "title": clip.hook,
        "subject": m.get("subject"),
        "claim": m.get("claim"),
        "duration_s": next((f.detail for f in rep.findings
                            if f.check == "duration"), None),
        "source": {"vod": chan.get("vod_id"),
                   "in_point_s": m.get("in_point"),
                   "out_point_s": m.get("out_point"),
                   "clip_file_in_point_s": clip.in_point},
        "rights": {"permission": chan.get("permission"),
                   "note": chan.get("permission_note")},
        # whether the overlay was BUILT, not whether chat was fetched — the
        # topicality reading is advisory and a sidecar that claims an
        # overlay that is not there is a false statement in a deliverable
        "chat_overlay": (d / f"overlays_{clip.index:02d}/rm_Chat.mov").exists(),
        "qc": [{"check": f.check, "ok": f.ok, "detail": f.detail}
               for f in rep.findings],
    }, indent=1))
    return dst


def cmd_build(job, args):
    """Build the specced clips, up to `lanes_for()` of them at once.

    **What made this serial was never ffmpeg.** Two things were, both
    silent: the PNG sequence directory was keyed by COMPOSITION NAME, so two
    clips wrote the same 1020 `Bait` filenames into one directory and the
    mixture encoded cleanly; and `Root.tsx` imported its chat, windows,
    duration and story list out of one shared `public/` tree, which webpack
    inlines at bundle time. The first is a temp dir per call now and the
    second arrives as `--props`. What remains is memory, which `lanes_for`
    measures.

    `--renderer resolve` forces one lane: its scripting API is served on
    Resolve's GUI thread and two timelines cannot be built at once.
    """
    from engine.clipspec import load
    d, _s, _e, manifest = _paths(job)
    chan = _channel(job)
    specs = sorted((ROOT / "clips").glob(f"{chan['name']}-*.json"))
    if args.only:
        want = {int(x) for x in args.only.split(",")}
        specs = [s for s in specs if int(s.stem.split("-")[-1]) in want]
    DELIVER.mkdir(exist_ok=True)
    if not chan.get("permission"):
        sys.exit(f"channels/{chan['name']}.json has no `permission` — "
                 "never ship a source without a rights basis. Set it to one of "
                 "explicit | affiliate | client_owned with a note.")

    # SKIP BEFORE LAUNCHING, not inside the lane, so the lane count is the
    # number of clips that will actually build.
    man = json.loads(manifest.read_text()) if manifest.exists() else {}
    todo = []
    for spec in specs:
        clip, _ch = load(spec)
        out = ROOT / f"renders/{clip.slug}.mp4"
        if man.get(spec.stem, {}).get("qc_ok") and out.exists() and not args.force:
            log(f"[{spec.stem}] already built and passed — skipping")
            continue
        todo.append(spec)
    if not todo:
        log("[build] nothing to build")
        log(f"\n-> {manifest}")
        return

    lanes = 1 if getattr(args, "renderer", "native") == "resolve" \
        else lanes_for(getattr(args, "lanes", None))
    lanes = min(lanes, len(todo))
    log(f"[build] {len(todo)} clip(s), {lanes} at a time")
    if lanes == 1:
        for spec in todo:
            log(f"\n=== {spec.stem} ===")
            _build_one(spec, chan, d, manifest, args)
    else:
        with cf.ThreadPoolExecutor(max_workers=lanes) as ex:
            futs = {ex.submit(_build_one, spec, chan, d, manifest, args): spec
                    for spec in todo}
            for fut in cf.as_completed(futs):
                # re-raise here rather than letting the executor swallow it
                # on shutdown; one clip's crash must not take the batch
                try:
                    fut.result()
                except Exception:
                    log(f"[{futs[fut].stem}] LANE CRASHED\n"
                        f"{traceback.format_exc()}")
    log(f"\n-> {manifest}")
    log(f"\n-> {manifest}")


class _Reused:
    """A recorded `deliver_qc.Report`, read back rather than recomputed."""

    def __init__(self, d):
        self.ok = bool(d["ok"])
        F = type("F", (), {})
        self.findings = []
        for f in d["findings"]:
            o = F()
            o.check, o.ok, o.detail = f["check"], f["ok"], f["detail"]
            o.fatal = f.get("fatal", True)
            self.findings.append(o)

    def text(self):
        head = "PASS" if self.ok else "FAIL"
        rows = "\n".join(f"   {'ok  ' if f.ok else 'FAIL'} {f.check:22} {f.detail}"
                          for f in self.findings)
        return f"{head}  (reusing the gate's own report)\n{rows}"


def _recorded_qc(clip, out):
    """The report `make_clip._gate` already wrote for THIS file, or None.

    The gate ran twice on every clip: once in `make_clip` on the artifact it
    had just rendered, and again here — and this one also re-derived the cut
    through `_plan_only`, which decodes every frame of the source. Measured
    at roughly 35s a clip, about sixteen minutes across this job, to reach a
    verdict computed seconds earlier.

    **BOTH GATES STAY.** Clip 08 shipped on a PASS from one call site while
    the other printed FAIL, so deleting one is not an option — but reusing
    the SAME report is strictly better than running two that can disagree.
    The reuse is keyed on the mp4's own path, mtime and size, so a stale
    record cannot read as a pass: if anything differs the gate runs again.
    """
    f = ROOT / f"jobs/{clip.job}/overlays_{clip.index:02d}/qc.json"
    if not (f.exists() and out.exists()):
        return None
    try:
        d = json.loads(f.read_text())
    except (OSError, ValueError):
        return None
    st = out.stat()
    # RESOLVE BOTH SIDES. `make_clip` records an absolute path and a caller
    # may hold a relative one for the same file; a string compare then
    # rejects a report that is perfectly valid and silently costs the 35s
    # this exists to save — a failure that looks like nothing at all.
    try:
        same = pathlib.Path(d.get("mp4", "")).resolve() == out.resolve()
    except OSError:
        same = False
    if (not same or d.get("size") != st.st_size
            or abs(float(d.get("mtime", -1)) - st.st_mtime) > 1e-6):
        return None
    return _Reused(d)


def _qc_for(clip, ch, out):
    """QC with the clip's own caption plan, so the hallucination check is real."""
    reused = _recorded_qc(clip, out)
    if reused is not None:
        return reused
    from engine import deliver_qc, qc
    from engine.resolve_captions import cards
    from engine.tighten import remap_card
    import make_clip as mk
    st = {"base_wav": ROOT / f"jobs/{clip.job}/overlays_{clip.index:02d}/_cut.wav"}
    mk._plan_only(clip, ch, st)
    tr = json.loads(clip.words(ROOT).read_text())
    ws = [w for u in tr["utterances"] for w in u["words"]]
    absent = qc.dead_audio(clip.source(ROOT), min_run=0.1)["runs"]
    cs, _dropped = mk._drop_hallucinated(cards(ws), absent)
    placed = []
    for c in cs:
        r = remap_card(c.start, c.end, st["keeps"])
        if r:
            placed.append({"start": r[0], "end": r[1], "text": c.text})
    # THE GATE THAT DECIDES DELIVERY HAS TO ASK THE SAME QUESTION.
    #
    # `make_clip` runs its own QC with `chat_expected=bool(st["chat_windows"])`
    # and this one did not pass it at all — so `chat_on_screen` was SKIPPED
    # here, in the only report whose `.ok` decides whether a clip ships.
    # Clip 08 printed `FAIL chat_on_screen: NOT VISIBLE — panel fill 17%`
    # from make_clip's pass and was delivered seconds later by this one.
    # Making the finding fatal did nothing, because the fatal finding was
    # never produced in the pass that mattered.
    #
    # That is this file's most-repeated defect — two numbers that are
    # supposed to be the same number, derived twice — and it is the SECOND
    # time it has hit this exact check, after the first version left
    # `fatal` at its default and printed FAIL while reporting PASS.
    #
    # The per-clip `chat_windows.json` is the honest source: `rm_Chat.mov`
    # existing only says the overlay was RENDERED, which is precisely the
    # thing clip 07 proved says nothing about whether it is on screen.
    # ONE FUNCTION, BOTH CALL SITES. This read `chat_windows.json`, which
    # exists for only two of the eight clips that have a chat overlay — so
    # for the other six the check silently SKIPPED, which is how a gate
    # reports "not checked" as a pass. `make_clip.chat_expected` answers the
    # question the gate is actually asking, from the spec and the overlay.
    import make_clip as mk
    overlays = ROOT / f"jobs/{clip.job}/overlays_{clip.index:02d}"
    return deliver_qc.check(out, cards=placed, absent=[], src_words=ws,
                            seam=ch.seam,
                            chat_expected=mk.chat_expected(clip, overlays))


# ------------------------------------------------------------- report ----
def cmd_report(job, args):
    d, screened, _e, manifest = _paths(job)
    rows = json.loads(screened.read_text()) if screened.exists() else []
    man = json.loads(manifest.read_text()) if manifest.exists() else {}
    ok = [k for k, v in man.items() if v.get("qc_ok")]
    held = [k for k, v in man.items() if v.get("built") and not v.get("qc_ok")]
    failed = [k for k, v in man.items() if not v.get("built")]
    log(f"JOB {job}")
    log(f"  screened      {len(rows)}")
    log(f"  buildable     {sum(1 for r in rows if r['verdict']=='build')}")
    log(f"  built         {len(man)}")
    log(f"  DELIVERED     {len(ok)}  {sorted(ok)}")
    if held:
        log(f"  held (gate)   {len(held)}  {sorted(held)}")
        for k in held:
            for f in man[k].get("findings", []):
                if not f["ok"]:
                    log(f"      {k}: {f['check']} — {f['detail']}")
    if failed:
        log(f"  build failed  {len(failed)}  {sorted(failed)}")
    for k in sorted(ok):
        v = man[k]
        log(f"\n  {k}  {v['render']}")
        log(f"      {v.get('subject','')[:76]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("job")
    ap.add_argument("cmd", choices=["screen", "prep", "editorial", "specs",
                                    "build", "report"])
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--only", default="")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--lanes", type=int, default=None,
                    help="how many clips to build at once (default: as many "
                         "as free memory allows, at ~1.9 GB a lane; "
                         "CLIP_LANES sets the ceiling)")
    ap.add_argument("--renderer", default="native", choices=("native", "resolve"),
                    help="native: ffmpeg, headless, no GUI app in the path. "
                         "resolve: the timeline, for format work.")
    a = ap.parse_args()
    globals()[f"cmd_{a.cmd}"](a.job, a)


if __name__ == "__main__":
    main()
