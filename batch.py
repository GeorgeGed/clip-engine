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

**3. RESOLVE IS A SINGLE GUI APP, SO BUILDS ARE SERIAL.** The scripting API
is served on its GUI thread, one project and one timeline at a time, and it
wedges on a modal dialog. Remotion's `public/` directory is also shared, so
two clips cannot render overlays at once. Everything CHEAP — transcription,
chat, facecam detection — runs in `prep` ahead of time; only the Resolve
build is serialised, and each clip is independent so a failure costs one
clip and not the run.

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
import json
import re
import subprocess
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).parent
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
            log(f"   {n:02d} DROPPED by the editorial pass: {e.get('why','')[:60]}")
            continue
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
        in_pt = float(e.get("in_point", 0.0))
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


def _channel(job):
    c = json.loads((ROOT / f"channels/{job.split('-')[0]}.json").read_text())
    return c


def _channel_obj(job):
    from engine.clipspec import Channel
    c = _channel(job)
    c = dict(c)
    c["cam"] = tuple(c["cam"])
    return Channel(**c)


# -------------------------------------------------------------- build ----
def cmd_build(job, args):
    """Serial, because Resolve is one GUI app and Remotion shares public/."""
    from engine import deliver_qc, qc
    from engine.clipspec import load
    d, _s, _e, manifest = _paths(job)
    chan = _channel(job)
    specs = sorted((ROOT / "clips").glob(f"{chan['name']}-*.json"))
    if args.only:
        want = {int(x) for x in args.only.split(",")}
        specs = [s for s in specs if int(s.stem.split("-")[-1]) in want]
    DELIVER.mkdir(exist_ok=True)
    man = json.loads(manifest.read_text()) if manifest.exists() else {}
    if not chan.get("permission"):
        sys.exit(f"channels/{chan['name']}.json has no `permission` — "
                 "never ship a source without a rights basis. Set it to one of "
                 "explicit | affiliate | client_owned with a note.")

    for spec in specs:
        key = spec.stem
        clip, ch = load(spec)
        out = ROOT / f"renders/{clip.slug}.mp4"
        if man.get(key, {}).get("qc_ok") and out.exists() and not args.force:
            log(f"[{key}] already built and passed — skipping")
            continue
        log(f"\n=== {key} ===")
        t0 = time.time()
        try:
            subprocess.run([sys.executable, str(ROOT / "make_clip.py"), str(spec)],
                           check=True)
        except subprocess.CalledProcessError as e:
            log(f"[{key}] BUILD FAILED: {e}")
            man[key] = {"built": False, "error": str(e)}
            manifest.write_text(json.dumps(man, indent=1))
            continue
        # gate on the ARTIFACT
        try:
            rep = _qc_for(clip, ch, out)
            log(rep.text())
            man[key] = {"built": True, "qc_ok": rep.ok, "seconds": round(time.time()-t0),
                        "render": str(out.relative_to(ROOT)),
                        "findings": [{"check": f.check, "ok": f.ok, "detail": f.detail}
                                     for f in rep.findings],
                        "subject": clip.notes,
                        "permission": chan.get("permission"),
                        "permission_note": chan.get("permission_note", "")}
            if rep.ok:
                # A DELIVERABLE NEEDS A NAME AND A SIDECAR. "fns-2905408276-06.mp4"
                # tells whoever posts it nothing, and they also need the title,
                # the source timestamps and the rights basis in one place —
                # that is the difference between a render and something you can
                # actually publish.
                slug = re.sub(r"[^a-z0-9]+", "-",
                              (clip.notes or "").lower())[:52].strip("-")
                dst = DELIVER / f"{chan['name']}-{clip.index:02d}-{slug}.mp4"
                subprocess.run(["cp", str(out), str(dst)], check=True)
                m = json.loads((d / "ranked.json").read_text())[clip.index - 1]
                side = dst.with_suffix(".json")
                side.write_text(json.dumps({
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
                    # whether the overlay was BUILT, not whether chat was
                    # fetched — the topicality gate refuses it on half the
                    # clips, and a sidecar that claims one that is not there
                    # is a false statement in a deliverable
                    "chat_overlay": (d / f"overlays_{clip.index:02d}/rm_Chat.mov").exists(),
                    "qc": [{"check": f.check, "ok": f.ok, "detail": f.detail}
                           for f in rep.findings],
                }, indent=1))
                man[key]["delivered"] = str(dst.relative_to(ROOT))
                log(f"[{key}] -> {dst.relative_to(ROOT)}  (+ sidecar)")
            else:
                log(f"[{key}] HELD BACK — failed the delivery gate")
        except Exception:
            log(f"[{key}] QC ERROR\n{traceback.format_exc()}")
            man[key] = {"built": True, "qc_ok": False, "error": "qc raised"}
        manifest.write_text(json.dumps(man, indent=1))
    log(f"\n-> {manifest}")


def _qc_for(clip, ch, out):
    """QC with the clip's own caption plan, so the hallucination check is real."""
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
    return deliver_qc.check(out, cards=placed, absent=[], src_words=ws,
                            seam=ch.seam)


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
    ap.add_argument("cmd", choices=["screen", "prep", "specs", "build", "report"])
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--only", default="")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    globals()[f"cmd_{a.cmd}"](a.job, a)


if __name__ == "__main__":
    main()
