#!/usr/bin/env python3
"""Build a clip from a spec. One script, any clip, any channel.

George: *"let's finalize this logic now. Lock it in. And let's develop this
into other clips ... I want to mass produce these clips for different
channels. So figure out how you can kind of do that from here."*

**WHAT WAS IN THE WAY.** Clip 8's pipeline was eight top-level scripts with
its constants at the top of each — the VOD id in four of them, the facecam
rect in two, the in-point in two, the duration typed into Root.tsx. Every
one of those is a value that differs per clip or per channel, sitting in
code. `engine/clipspec.py` splits them into a `Channel` (measured once per
streamer) and a `Clip` (mostly derived), and this runs the pipeline off
them. The house style — captions, exits, punch geometry, sound, palette —
stays in code, because it is the same on every clip by definition.

    ./.venv/bin/python make_clip.py clips/fns-07.json
    ./.venv/bin/python make_clip.py clips/fns-07.json --only chat,punch

STAGES, in order, each skippable:

  cut       tighten the dead air, build V1/V2 in Resolve with per-shot
            framings and the channel's grade
  captions  word cards -> one alpha movie (the PIL track, which is what
            ships; the Fusion path is slower and is not delivered)
  chat      fetch the VOD chat, CLASSIFY IT, build the windows, render
  assemble  cap/sfx/chat/hook/cards onto V3-V6
  punch     split V2 on the measured bold moments
  render    render, EQ, two-pass loudnorm, QC

THE CHAT STAGE IS THE ONE THAT THINKS. Everything else is clip 8's logic
with its constants pulled out. `engine/chat_reaction` decides whether this
clip's chat is a steady background (so the box is the pane's resting state,
as in clip 8) or a crowd reacting in bursts (so the box comes up ON the
reactions). That is George's gameplay case — "after the streamer has like
got a 3K ... then we can see the Twitch chat's reaction" — without needing
a killfeed detector, because the burst IS the signal.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from engine import qc                                            # noqa: E402
from engine.clipspec import load                                 # noqa: E402
from engine import facecam                                       # noqa: E402
from engine.resolve_driver import connect                        # noqa: E402
from engine.resolve_layout import Frame, plan, apply             # noqa: E402
from engine.resolve_captions import cards, emphasis_keys, mark_emphasis  # noqa: E402
from engine.cuts import framings, content_framings               # noqa: E402
from engine.tighten import removals, keeps, remap_card, joins    # noqa: E402
from engine import captions_video, twitch_chat                   # noqa: E402
from engine import chat_reaction as cr                           # noqa: E402
from engine.sfx import Cue, bed, cue_gain_peak                   # noqa: E402

VENDOR = ROOT / "vendor/remotion-clip08"
PUBLIC = VENDOR / "public"
CHROME_APP = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# HOUSE STYLE — the same on every clip, which is why it is here and not in a
# spec. Each number is justified in AGENTS.md next to the measurement that
# produced it; they are repeated here only so one file can be read top to
# bottom.
MIN_DEAD = 0.35          # shorter removals read as jitter, not tightening
BEAT = 0.12              # what is LEFT of each pause
CAPTION_ACCENT = (92, 128, 255, 255)      # theme.tsx C.blueLight
MASTER_GAIN = 6.2        # what loudnorm adds; cues are solved through it
BAIT_SECONDS = 17.0      # the hook holds the stretch where a scroller decides
STAGES = ("cut", "captions", "chat", "assemble", "punch", "render")


def log(*a):
    print(*a, flush=True)


def _cut_audio(clip, ch, st):
    """The tightened cut's audio, straight from the source.

    The punch pass needs the speaker's own levels, and AGENTS.md records why
    it must not read a delivered mp4: `render_and_finish` overwrites the
    delivery every version, so the plan moved underneath the build. This is
    derived from the source and the keeps, so it is identical every run and
    carries no sfx bed and no loudnorm — his delivery, not our mix.
    """
    dst = st["base_wav"]
    if dst.exists():
        return dst
    src = clip.source(ROOT)
    parts = "".join(
        f"[0:a]atrim=start={k.start:.4f}:end={k.end:.4f},asetpts=PTS-STARTPTS[a{i}];"
        for i, k in enumerate(st["keeps"]))
    joined = "".join(f"[a{i}]" for i in range(len(st["keeps"])))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
                    "-filter_complex",
                    f"{parts}{joined}concat=n={len(st['keeps'])}:v=0:a=1[o]",
                    "-map", "[o]", "-ac", "1", "-ar", "16000", str(dst)],
                   check=True)
    return dst


# ---------------------------------------------------------------- cut ----
def _cam(clip, ch, st):
    """The facecam rect for THIS clip: the spec's, or detected."""
    if "cam" in st:
        return st["cam"]
    if clip.cam:
        st["cam"] = tuple(clip.cam)
        log(f"  facecam {st['cam']} (from the spec)")
        return st["cam"]
    f = facecam.detect(clip.source(ROOT))
    if f is None:
        st["cam"] = ch.cam
        log(f"  facecam NOT DETECTED — falling back to the channel's "
            f"{ch.cam}. Check the frame.")
        return st["cam"]
    st["cam"] = f.rect
    flag = "" if f.margin >= 4 else "   LOW CONFIDENCE — check the frame"
    log(f"  facecam {f.rect} detected: {f.coverage:.1%} of frame, "
        f"moves {f.margin:.0f}x the rest{flag}")
    return st["cam"]


def stage_cut(clip, ch, st):
    src = clip.source(ROOT)
    fps = ch.fps
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
         "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(src)],
        capture_output=True, text=True).stdout.strip()
    src_dur = int(probe) / fps
    # Dead air is BOTH kinds: digital zero (the Twitch mutes) and ordinary
    # room tone. A fixed dBFS floor means something different on every clip
    # because raw VOD audio runs ~7 dB under target, so `quiet_runs` measures
    # against the speaker's own level.
    absent = qc.dead_audio(src, min_run=0.3)["runs"]
    quiet = qc.quiet_runs(src, min_run=MIN_DEAD)["runs"]
    dead = sorted([r for r in absent + quiet if r[0] >= clip.in_point])
    spans = removals(dead, src_dur, min_remove=MIN_DEAD, beat=BEAT)
    kp = [k for k in keeps(spans, src_dur) if k.end > clip.in_point]
    if kp:
        kp[0].start = max(kp[0].start, clip.in_point)
    out_dur = sum(k.length for k in kp)
    log(f"  {src.name}")
    log(f"  in-point {clip.in_point}s | {len(spans)} dead removals "
        f"({sum(s.length for s in spans):.1f}s)")
    log(f"  {src_dur:.1f}s -> {out_dur:.1f}s in {len(kp)} shots, "
        f"{(len(kp)-1)/(out_dur/60):.1f} cuts/min")
    st["keeps"] = kp
    st["out_dur"] = out_dur
    st["total"] = round(out_dur * fps)

    r = connect(); r.OpenPage("edit")
    proj = r.GetProjectManager().GetCurrentProject()
    mp = proj.GetMediaPool()
    r.GetMediaStorage().AddItemListToMediaPool([str(src)])
    item = next(i for i in mp.GetRootFolder().GetClipList()
                if i.GetName() == src.name)
    name = f"{clip.slug}"
    for i in range(proj.GetTimelineCount(), 0, -1):
        t = proj.GetTimelineByIndex(i)
        if t and t.GetName() == name:
            mp.DeleteTimelines([t])
    tl = mp.CreateEmptyTimeline(name)
    while tl.GetTrackCount("video") < 6:
        tl.AddTrack("video")
    proj.SetCurrentTimeline(tl)
    # recordFrame is ABSOLUTE: a timeline starts at 01:00:00:00 = 216000 at
    # 60fps, so recordFrame=0 puts the clip an hour before the start and
    # renders black while GetItemListInTrack still lists it.
    start = tl.GetStartFrame()
    ents, rec = [], start
    for k in kp:
        sf, ef = round(k.start * fps), round(k.end * fps)
        for track in (1, 2):
            ents.append({"mediaPoolItem": item, "startFrame": sf, "endFrame": ef,
                         "trackIndex": track, "recordFrame": rec,
                         **({} if track == 1 else {"mediaType": 1})})
        rec += ef - sf
    mp.AppendToTimeline(ents)

    canvas = Frame(1080, 1920, 1920, 1080)
    seam_y = ch.seam * canvas.canvas_h
    rects = framings(len(kp), _cam(clip, ch, st))
    crects = content_framings(len(kp), chrome=ch.chrome)
    for trk, rl, pane in ((1, crects, (0, seam_y, 1080, 1920)),
                          (2, rects, (0, 0, 1080, seam_y))):
        items = sorted(tl.GetItemListInTrack("video", trk) or [],
                       key=lambda i: i.GetStart())
        for it, rect in zip(items, rl):
            apply(it, plan(canvas, rect, pane))
            if trk == 2 and ch.grade:
                it.SetCDL(ch.grade)
    log(f"  V1 {len(tl.GetItemListInTrack('video',1))} / "
        f"V2 {len(tl.GetItemListInTrack('video',2))} shots, "
        f"{(tl.GetEndFrame()-start)/fps:.1f}s")
    # Every join splices across speech nobody can hear, on a muted VOD. The
    # caveat has been overruled twice and is still printed every time.
    js = joins(spans, st.get("words", []))
    if js:
        log(f"  {len(js)} joins splice across unheard speech")


# ----------------------------------------------------------- captions ----
def stage_captions(clip, ch, st):
    tr = json.loads(clip.words(ROOT).read_text())
    words = [w for u in tr["utterances"] for w in u["words"]]
    st["words"] = words
    meta = st["meta"]
    cs = cards(words)
    mark_emphasis(cs, emphasis_keys(meta.get("claim", ""),
                                    meta.get("consequence", "")))
    out = []
    for c in cs:
        rm = remap_card(c.start, c.end, st["keeps"])
        if rm:
            out.append(type(c)(rm[0], rm[1], c.text, c.words, c.emphasis))
    st["cards"] = out
    dst = st["overlays"] / "cap_kin.mov"
    captions_video.kinetic([{"start": c.start, "end": c.end, "text": c.text,
                             "words": c.words, "emph": c.emphasis}
                            for c in out],
                           dst, dur=st["out_dur"], accent=CAPTION_ACCENT)
    log(f"  {len(cs)} cards -> {len(out)} after the cut "
        f"({sum(1 for c in out if c.emphasis)} emphasised), "
        f"{len(out)/max(st['out_dur'],1):.2f}/s -> {dst.name}")


# --------------------------------------------------------------- chat ----
def stage_chat(clip, ch, st):
    """Fetch, CLASSIFY, and place. The one stage that makes a decision."""
    if not (ch.vod_id and clip.region):
        log("  no vod_id/region on the spec — skipping chat")
        st["chat_windows"] = []
        return
    t0, t1 = clip.region
    cache = ROOT / f"jobs/{clip.job}/chat_{clip.index:02d}.json"
    if cache.exists():
        raw = json.loads(cache.read_text())
        log(f"  {len(raw)} messages from cache")
    else:
        # Context either side, because the RESTING RATE has to come from
        # outside the clip: a 20s ace clip is hype end to end and would read
        # as flat against its own mean.
        msgs = twitch_chat.fetch(ch.vod_id, t0 - cr.CONTEXT_PAD, t1 + cr.CONTEXT_PAD)
        twitch_chat.to_json(msgs, cache)
        raw = json.loads(cache.read_text())
        log(f"  fetched {len(raw)} (clip +/- {cr.CONTEXT_PAD:.0f}s of context)")
    for m in raw:
        m.setdefault("frags", m.get("fragments", []))

    # output time <- source time, through the same keeps the cut used
    kp = st["keeps"]

    def remap(src_t):
        acc = 0.0
        for k in kp:
            if k.start <= src_t < k.end:
                return acc + (src_t - k.start)
            acc += k.length
        return None

    mode, wins, info = cr.windows(raw, t0, t1, remap=remap, mode=clip.chat_mode)
    log(f"  resting {info['resting_rate']:.0f}/min, clip {info['clip_rate']:.0f}/min "
        f"(x{info['clip_rate']/info['resting_rate']:.2f}), hype {info['hype_share']:.2f}")
    log(f"  MODE: {mode}  ({len(info['bursts'])} bursts, "
        f"{info['burst_coverage']:.0%} of the clip)")
    for b in info["bursts"]:
        log(f"     burst {b.start-t0:5.1f}-{b.end-t0:5.1f}s  x{b.mult:.2f} "
            f"peak {b.peak_rate:.0f}/min  hype {b.hype:.2f}")
    for w in wins:
        log(f"     window {w['from']:6.2f}-{w['to']:6.2f}  ({w['to']-w['from']:.2f}s)")
    st["chat_windows"] = wins
    st["chat_mode"] = mode

    # the messages, mapped onto the cut. Pre-roll ones get negative times so
    # the box opens already half full — a chat panel that starts empty and
    # fills up reads as a graphic booting, not as a stream you joined.
    import build_chat as bc
    kept, dropped, pre = [], 0, 0
    for m in raw:
        src_t = m["offset"]
        if src_t < t0:
            out_t = src_t - t0
            if out_t < -40:
                continue
            pre += 1
        elif src_t >= t1:
            continue
        else:
            # `remap` works in CLIP-FILE time, not VOD time: the keeps span
            # 0..file_duration while a message's offset is a VOD second.
            # Passing the raw offset matched no keep and silently dropped
            # every message inside the clip — 60 of 116 on the first run,
            # with the 56 survivors all pre-roll.
            o = remap(src_t - t0)
            if o is None:
                dropped += 1
                continue
            out_t = o
        kept.append({"t": round(out_t, 2), "author": m["author"],
                     "colour": m["colour"], "display": bc.readable(m["colour"]),
                     "badges": m["badges"][:2],
                     "frags": [{"text": f["text"], "emote": f["emote"]}
                               for f in m["frags"]]})
    kept.sort(key=lambda m: m["t"])
    (PUBLIC / "chat.json").write_text(json.dumps(kept, indent=1))
    (PUBLIC / "chat_windows.json").write_text(json.dumps(wins, indent=1))
    log(f"  {len(kept)} messages on the cut ({pre} pre-roll, {dropped} dropped "
        f"into removed spans)")

    # Remotion reads the duration and the hook from here rather than from a
    # constant in Root.tsx.
    (PUBLIC / "clip.json").write_text(json.dumps({
        "durationInFrames": st["total"],
        "baitFrames": min(st["total"], round(BAIT_SECONDS * ch.fps)),
        "hook": clip.hook or "", "emoji": clip.emoji}))
    comps = ["Chat"] + (["Bait"] if clip.hook else [])
    for comp in comps:
        _render_comp(comp, st["overlays"], ch.fps)


def _render_comp(comp, out_dir, fps):
    """Remotion cannot write alpha from the CLI here: prores 4444 yields
    yuv422p12le with no alpha plane. `--sequence --image-format=png` then our
    own qtrle encode is the route that works."""
    seq = Path("/private/tmp/claude-501/remotion-seq") / comp
    if seq.exists():
        subprocess.run(["rm", "-rf", str(seq)], check=True)
    seq.mkdir(parents=True)
    subprocess.run(["npx", "remotion", "render", "src/index.ts", comp, str(seq),
                    "--sequence", "--image-format=png", "--concurrency=4",
                    f"--browser-executable={CHROME_APP}", "--log=error"],
                   cwd=VENDOR, check=True)
    n = len(list(seq.glob("*.png")))
    dst = out_dir / f"rm_{comp}.mov"
    # Remotion zero-pads to the SEQUENCE's width, so the pattern depends on
    # the frame count and cannot be hardcoded to %d.
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", str(fps),
                    "-i", str(seq / f"element-%0{len(str(n-1))}d.png"),
                    "-c:v", "qtrle", "-pix_fmt", "argb", str(dst)], check=True)
    subprocess.run(["rm", "-rf", str(seq)], check=True)
    log(f"  {comp}: {n} frames -> {dst.name}")


# ----------------------------------------------------------- assemble ----
def stage_assemble(clip, ch, st):
    r = connect(); r.OpenPage("edit")
    proj = r.GetProjectManager().GetCurrentProject()
    mp = proj.GetMediaPool()
    tl = proj.GetCurrentTimeline()
    fps = ch.fps
    start = tl.GetStartFrame()
    # THE PICTURE IS WHAT V1 HOLDS, and the overlays are cut to it. Sizing
    # them from `round(out_dur * fps)` instead let them hang 2 frames past
    # V1, and a frame with an overlay and no picture under it renders black.
    v1 = sorted(tl.GetItemListInTrack("video", 1) or [], key=lambda i: i.GetStart())
    total = v1[-1].GetEnd() - v1[0].GetStart()
    if total != st["total"]:
        log(f"  picture is {total} frames, not round(out_dur*fps)="
            f"{st['total']} — overlays cut to the picture")
    st["total"] = total
    # render() appends a job every call and never clears one; a stale job
    # whose output exists is what wedged the API on an overwrite dialog.
    for j in (proj.GetRenderJobList() or []):
        proj.DeleteRenderJob(j["JobId"])
    stale = []
    for t in range(3, tl.GetTrackCount("video") + 1):
        stale += tl.GetItemListInTrack("video", t) or []
    stale += tl.GetItemListInTrack("audio", 2) or []
    if stale:
        tl.DeleteClips(stale)

    # Two sounds, one meaning each: `paper` when the chat panel settles in,
    # `shutter` when a photo card lands.
    cues = []
    wins = st.get("chat_windows")
    if wins is None and (PUBLIC / "chat_windows.json").exists():
        # the chat stage ran in an earlier invocation; its windows are the
        # truth about when the box arrives, so read them rather than
        # silently shipping no cue (which is what the first run did)
        wins = json.loads((PUBLIC / "chat_windows.json").read_text())
    for w in (wins or []):
        cues.append(Cue(w["from"] + 0.02, "paper",
                        cue_gain_peak("paper", -13.0, MASTER_GAIN),
                        "the chat box settles in"))
    shut = cue_gain_peak("shutter", -9.5, MASTER_GAIN)
    for c in clip.cards:
        cues.append(Cue(c["at"] + 0.04, "shutter", shut, f"{c['id']} lands"))
    log(f"  sfx: {bed(cues, total / fps, out=st['overlays'] / 'sfx.wav')}")

    names = ["cap_kin.mov", "sfx.wav", "rm_Chat.mov"]
    if clip.hook:
        names.append("rm_Bait.mov")
    names += [f"rm_{c['id']}.mov" for c in clip.cards]
    have = [n for n in names if (st["overlays"] / n).exists()]
    r.GetMediaStorage().AddItemListToMediaPool(
        [str(st["overlays"] / n) for n in have])
    pool = {c.GetName(): c for c in mp.GetRootFolder().GetClipList()}

    def frames_of(name):
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
             "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0",
             str(st["overlays"] / name)], capture_output=True, text=True).stdout.strip()
        return int(out) if out.isdigit() else None

    ents = []

    def add(name, at, dur, track, media=1):
        it = pool.get(name)
        if it is None:
            return
        n = round(dur * fps)
        # A clip Resolve trims short loses the END OF ITS EXIT, which is the
        # jolt the exit exists to remove. Take the length from the FILE.
        f = frames_of(name)
        if f and f < n:
            n = f
        ents.append({"mediaPoolItem": it, "startFrame": 0, "endFrame": n,
                     "recordFrame": start + round(at * fps),
                     "trackIndex": track, "mediaType": media})

    # V1 content | V2 facecam | V3 chat | V4 cards | V5 titles | V6 captions
    add("rm_Chat.mov", 0.0, total / fps, 3)
    for c in clip.cards:
        add(f"rm_{c['id']}.mov", c["at"], c["dur"], 4)
    if clip.hook:
        add("rm_Bait.mov", 0.8, min(BAIT_SECONDS, total / fps - 0.8), 5)
    add("cap_kin.mov", 0.0, total / fps, 6)
    add("sfx.wav", 0.0, total / fps, 2, media=2)
    placed = mp.AppendToTimeline(ents)
    log(f"  appended {len(placed or [])} of {len(ents)}: " +
        " ".join(f"V{t}:{len(tl.GetItemListInTrack('video', t) or [])}"
                 for t in range(3, 7)))


# -------------------------------------------------------------- punch ----
def stage_punch(clip, ch, st):
    import resolve_punch as rp
    r = connect(); r.OpenPage("edit")
    proj = r.GetProjectManager().GetCurrentProject()
    tl = proj.GetCurrentTimeline(); mp = proj.GetMediaPool()
    start = tl.GetStartFrame()
    v1 = sorted(tl.GetItemListInTrack("video", 1) or [], key=lambda i: i.GetStart())
    v2 = sorted(tl.GetItemListInTrack("video", 2) or [], key=lambda i: i.GetStart())
    item = v1[0].GetMediaPoolItem()
    # The base shots come off V1, never V2: a second run would otherwise take
    # the already-split pieces as its base shots and punch the punches.
    segs = [((it.GetStart() - start) / ch.fps,
             (it.GetEnd() - it.GetStart()) / ch.fps,
             it.GetLeftOffset() / ch.fps) for it in v1]
    # Measure the CLEAN CUT, never the last delivery — see AGENTS.md.
    base, moments = rp.bold_moments(_cut_audio(clip, ch, st))
    log(f"  baseline {base:.1f} dBFS; {len(moments)} bold moments:")
    for t, d in moments:
        log(f"     {t:6.2f}s  +{d} dB")
    pieces = rp.split(segs, moments)
    tl.DeleteClips(v2)
    canvas = Frame(1080, 1920, 1920, 1080)
    rects = framings(len(segs), _cam(clip, ch, st))
    ents = [{"mediaPoolItem": item, "startFrame": round(s0 * ch.fps),
             "endFrame": round(s0 * ch.fps) + round(d * ch.fps),
             "recordFrame": start + round(o0 * ch.fps),
             "trackIndex": 2, "mediaType": 1}
            for o0, d, s0, _i, _p in pieces]
    mp.AppendToTimeline(ents)
    seam_y = ch.seam * canvas.canvas_h
    items = sorted(tl.GetItemListInTrack("video", 2) or [], key=lambda i: i.GetStart())
    for it, (o0, d, _s, idx, isp) in zip(items, pieces):
        rect = rects[idx]
        if isp:
            rect = rp.inset(rect, rp.PUNCH_INSET)
        apply(it, plan(canvas, rect, (0, 0, 1080, seam_y)))
        if ch.grade:
            it.SetCDL(ch.grade)
    log(f"  V2 {len(segs)} shots -> {len(pieces)} "
        f"({sum(1 for *_x, p in pieces if p)} punched at "
        f"{1/(1-rp.PUNCH_INSET):.3f}x)")


# ------------------------------------------------------------- render ----
def stage_render(clip, ch, st):
    from engine.render_ffmpeg import _finish_audio, HOUSE_EQ as EQ
    r = connect()
    proj = r.GetProjectManager().GetCurrentProject()
    for j in (proj.GetRenderJobList() or []):
        proj.DeleteRenderJob(j["JobId"])
    tag = clip.slug
    raw = ROOT / f"renders/{tag}_src.mov"
    raw.unlink(missing_ok=True)
    tl = proj.GetCurrentTimeline()
    v1 = sorted(tl.GetItemListInTrack("video", 1) or [], key=lambda i: i.GetStart())
    # MARK THE PICTURE, do not render "all frames". The timeline is as long
    # as its LONGEST track, so an overlay that outruns V1 adds frames with
    # nothing under them and those render BLACK.
    #
    # **`MarkIn` RENDERS ONE FRAME BEFORE THE MARK.** Measured on this
    # timeline: marking [216000..218586] gave 2587 frames whose frame 0 was
    # pure black (timeline 215999, where nothing is), and marking
    # [216001..218587] gave a frame 0 of real picture. So the mark is
    # shifted by one, and the clip opened on a black frame until it was.
    # The tail is then handled where it always was — `-frames:v` on the
    # delivery, trimming to the PICTURE count.
    picture = v1[-1].GetEnd() - v1[0].GetStart()
    st["total"] = picture
    mark_in, mark_out = v1[0].GetStart() + 1, v1[-1].GetEnd() + 1
    proj.LoadRenderPreset("H.264 Master")
    proj.SetRenderSettings({"TargetDir": str(ROOT / "renders"),
                            "CustomName": f"{tag}_src",
                            "MarkIn": mark_in, "MarkOut": mark_out,
                            "SelectAllFrames": False})
    job = proj.AddRenderJob(); proj.StartRendering([job])
    t0 = time.time()
    while proj.IsRenderingInProgress():
        time.sleep(1)
    log(f"  resolve render {time.time()-t0:.0f}s")
    eq, mid = ROOT / "renders/_eq.mov", ROOT / "renders/_mid.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(raw),
                    "-t", f"{st['total']/ch.fps:.4f}", "-af", EQ,
                    "-c:v", "libx264", "-crf", "17", "-preset", "medium",
                    "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", str(eq)], check=True)
    # Loudness is finished HERE, not in Resolve: NormalizeAudioLevel applies
    # gain without true-peak limiting, so the lift to -14 would clip.
    _finish_audio(eq, {"audio": {"target_lufs": -14.0, "true_peak_dbtp": -1.0},
                       "render": {"audio_codec": "aac"}}, mid)
    out = ROOT / f"renders/{tag}.mp4"
    # -t with -c:v copy cuts at a keyframe, so trim the PICTURE with -frames:v
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mid),
                    "-frames:v", str(st["total"]), "-c:v", "libx264", "-crf", "18",
                    "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "copy",
                    "-movflags", "+faststart", str(out)], check=True)
    eq.unlink(missing_ok=True); mid.unlink(missing_ok=True)
    log("  " + qc.check(out).report())
    st["out"] = out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--only", default=",".join(STAGES))
    a = ap.parse_args()
    clip, ch = load(a.spec)
    want = [s for s in a.only.split(",") if s]
    bad = set(want) - set(STAGES)
    if bad:
        sys.exit(f"unknown stage(s) {sorted(bad)}; pick from {list(STAGES)}")

    overlays = ROOT / f"jobs/{clip.job}/overlays_{clip.index:02d}"
    overlays.mkdir(parents=True, exist_ok=True)
    ranked = json.loads((ROOT / f"jobs/{clip.job}/ranked.json").read_text())
    st = {"overlays": overlays, "meta": ranked[clip.index - 1],
          "base_wav": ROOT / f"jobs/{clip.job}/overlays_{clip.index:02d}/_cut.wav"}
    log(f"=== {clip.slug} / channel {ch.name} ===")
    log(f"    {st['meta']['subject']}")

    # captions needs the words and the keeps; chat needs the keeps. Stages
    # run in order and share `st`, so a partial run has to rebuild what it
    # depends on — cheap, because the expensive parts are Resolve and
    # Remotion, not these.
    for s in STAGES:
        if s not in want:
            if s == "cut" and any(x in want for x in
                                  ("captions", "chat", "assemble", "punch")):
                log("[cut] (re-planning, not rebuilding — needed downstream)")
                _plan_only(clip, ch, st)
            continue
        log(f"[{s}]")
        globals()[f"stage_{s}"](clip, ch, st)
    log("done.")


def _plan_only(clip, ch, st):
    """The cut's PLAN without touching Resolve, for partial runs."""
    src = clip.source(ROOT)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
         "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(src)],
        capture_output=True, text=True).stdout.strip()
    src_dur = int(probe) / ch.fps
    absent = qc.dead_audio(src, min_run=0.3)["runs"]
    quiet = qc.quiet_runs(src, min_run=MIN_DEAD)["runs"]
    dead = sorted([r for r in absent + quiet if r[0] >= clip.in_point])
    spans = removals(dead, src_dur, min_remove=MIN_DEAD, beat=BEAT)
    kp = [k for k in keeps(spans, src_dur) if k.end > clip.in_point]
    if kp:
        kp[0].start = max(kp[0].start, clip.in_point)
    st["keeps"] = kp
    st["out_dur"] = sum(k.length for k in kp)
    st["total"] = round(st["out_dur"] * ch.fps)
    st["base_wav"].parent.mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    main()
