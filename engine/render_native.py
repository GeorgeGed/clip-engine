"""The production renderer: the same edit, without Resolve.

Resolve stays the FORMAT WORKBENCH — a new look is built and judged there,
because the timeline can be opened and nudged. This is the PRODUCTION LINE,
for clips whose format is already settled: headless, parallel, cloud-
reachable, and it cannot wedge at 90% CPU behind a modal dialog.

It composes three measured modules and adds no geometry of its own:
    engine.native_layout     the two-pane crop/scale/stack per segment
    engine.native_grade      the facecam ASC CDL as lutrgb + colorchannelmixer
    engine.native_composite  the alpha overlays and the A1+A2 mix
and it takes the CUT from `make_clip._plan_only`, which is the one
implementation of the plan. Deriving the keeps a second time here is exactly
the defect this repo has recorded five times — `_cut.wav` cached, the shared
`punches.json`, the punch plan measured from the overwritten delivery,
`specs` overwriting a reviewed spec, and `bed()` reading a different
waveform than `cue_gain` solved against.

ONE CHAIN PER KEEP, NOT PER SHOT, which is what Resolve's timeline actually
does: it appends one timeline item per keep carrying that shot's framing.
Doing the same here means the dead-space cut and the framing happen in one
pass with no intermediate file, and the segment boundaries are the keeps'
own frame numbers rather than a second rounding of them.

TWO RESOLVE ARTEFACTS ARE DELIBERATELY NOT REPRODUCED, and a strict parity
check will flag both as differences in which the native path is the more
correct one:
  * `MarkIn` renders one frame BEFORE the mark, which `make_clip`
    compensates with `+1`. ffmpeg has no such bug and inherits no
    compensation.
  * the overlays are composited ONE FRAME EARLY — measured by correlating
    cap_kin.mov's own alpha coverage against the dark share of the caption
    band in the raw render across 80 frames: NCC 0.9925 at -1 against
    0.8697 at 0. Here they land on their own frame.

Verified with `engine.render_parity`, which is the gate, not this module's
own opinion.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import native_composite as nc          # noqa: E402
from engine import native_grade as ng              # noqa: E402
from engine import native_layout as nl             # noqa: E402

# Which overlay file sits on which Resolve track, so the composite order is
# the survey's finding and not a guess. V3 chat, V4 cards, V5 titles, V6
# captions — a graphic lands ON TOP of the chat, and the captions on top of
# everything.
TRACKS = {
    "rm_Chat.mov": nc.TRACK_CHAT,
    "rm_Bait.mov": nc.TRACK_TITLES,
    "cap_kin.mov": nc.TRACK_CAPTIONS,
}
BAIT_AT = 0.8          # make_clip places the hook line here


def plan(clip, ch) -> dict:
    """The cut, from make_clip's own planner. Never re-derived here."""
    import make_clip as mc
    overlays = ROOT / f"jobs/{clip.job}/overlays_{clip.index:02d}"
    st = {"overlays": overlays,
          "base_wav": overlays / "_cut.wav",
          "meta": {"subject": ""}}
    pl = mc._plan_only(clip, ch, st)
    keeps = st["keeps"]
    shot_of = mc._shot_index([k.length for k in keeps])
    return {"src": pl["src"], "keeps": keeps, "shot_of": shot_of,
            "out_dur": st["out_dur"], "total": st["total"],
            "overlays": overlays, "n_shots": max(shot_of) + 1 if shot_of else 0}


def cut_graph(keeps, *, fps: float, src: str = "0:v", out: str = "cut") -> str:
    """Trim the keeps out of the source and concat them into the cut picture.

    `native_layout.two_pane` takes the CUT picture and requires its shots to
    be contiguous from frame 0 — it says so and raises if they are not. That
    is the right contract: the dead-space removal is an EDIT decision and the
    two-pane layout is a FRAMING one, and fusing them would hide a keep
    boundary inside a geometry module.

    This stays a filter-graph label rather than an intermediate file, so the
    whole clip is still one ffmpeg pass. Frame numbers, not seconds: the
    keeps are already on the frame grid and `between(t,...)` would re-round
    them a second time.
    """
    parts, labels = [], []
    for i, k in enumerate(keeps):
        # ROUND START AND END INDEPENDENTLY, which is what make_clip:849
        # hands Resolve: `round(k.start*fps), round(k.end*fps)`. Rounding the
        # LENGTH instead drifts, because each keep then rounds on its own
        # origin — on clip 12 that is 6 frames over 16 keeps, 0.1s, and the
        # parity gate's duration tolerance is ONE frame.
        a, b = round(k.start * fps), round(k.end * fps)
        parts.append(f"[{src}]trim=start_frame={a}:end_frame={b},"
                     f"setpts=PTS-STARTPTS[rn_k{i}]")
        labels.append(f"[rn_k{i}]")
    if len(keeps) == 1:
        return parts[0].replace("[rn_k0]", f"[{out}]")
    split = f"[{src}]split={len(keeps)}" + "".join(
        f"[rn_s{i}]" for i in range(len(keeps)))
    parts = [p.replace(f"[{src}]", f"[rn_s{i}]", 1)
             for i, p in enumerate(parts)]
    cat = "".join(labels) + f"concat=n={len(keeps)}:v=1:a=0[{out}]"
    return ";".join([split, *parts, cat])


def segments(p: dict, ch, punches: list[float] | None = None):
    """One `native_layout.Shot` per framing run, in CUT frames from zero.

    Shots are groups of consecutive keeps (`make_clip._shot_index`), and a
    punch splits the shot it lands in because `crop` cannot animate its w/h
    — a framing change is a segment boundary, not a parameter.
    """
    from engine.cuts import content_framings, framings
    try:
        from resolve_punch import PUNCH_HOLD, PUNCH_INSET
    except Exception:
        PUNCH_HOLD, PUNCH_INSET = 2.20, 0.12
    fps = float(ch.fps)

    n = max(1, p["n_shots"])
    unit = framings(n, (0.0, 0.0, 1.0, 1.0))
    cam_cycle = [2 * r[0] for r in unit]
    content_cycle = content_framings(n)

    # cut-frame span of each SHOT, from the keeps it owns
    spans: dict[int, list[int]] = {}
    f = 0
    for k, sh in zip(p["keeps"], p["shot_of"]):
        n_f = round(k.end * fps) - round(k.start * fps)   # as make_clip:849
        r = spans.setdefault(sh, [f, f])
        r[1] = f + n_f
        f += n_f
    total = f

    cuts = set()
    for t in (punches or []):
        cuts.add(max(0, min(total, round(t * fps))))
        cuts.add(max(0, min(total, round((t + PUNCH_HOLD) * fps))))

    out = []
    for sh in sorted(spans):
        a, b = spans[sh]
        pts = sorted({a, b} | {c for c in cuts if a < c < b})
        for m0, m1 in zip(pts, pts[1:]):
            punched = any(round(t * fps) <= m0 < round((t + PUNCH_HOLD) * fps)
                          for t in (punches or []))
            out.append(nl.Shot(
                m0 / fps, m1 / fps,
                inset=cam_cycle[sh % len(cam_cycle)],
                punch=PUNCH_INSET if punched else 0.0,
                content_rect=content_cycle[sh % len(content_cycle)]))
    return out


def overlay_list(p: dict) -> list[nc.Overlay]:
    """Every alpha movie that exists for this clip, on its own track.

    MATCHED BY RESOLVED PATH, never by name. Every clip writes `rm_Chat.mov`
    and `cap_kin.mov` into its own directory, and matching by file NAME is
    how clip 12 shipped with CLIP 6'S CHAT on it — five `rm_Chat.mov` in one
    media pool and the dict kept whichever was added last.
    """
    out = []
    for name, track in TRACKS.items():
        f = (p["overlays"] / name).resolve()
        if f.exists():
            out.append(nc.Overlay(path=f, at=BAIT_AT if "Bait" in name else 0.0,
                                  track=track))
    for f in sorted(p["overlays"].glob("rm_*.mov")):
        if f.name not in TRACKS:
            out.append(nc.Overlay(path=f.resolve(), at=0.0,
                                  track=nc.TRACK_CARDS))
    return nc.order(out)


def punch_times(pj: Path) -> list[float]:
    """The punch starts Resolve ACTUALLY used, read off disk.

    `punches.json` carries BOTH `punches` (the chosen moments) and `applied`
    (where the zoom was opened, which `PUNCH_BACKOFF` can pull earlier when a
    moment sits too close to a cut for the hold to fit). Clip 12 reads
    [2.87, 12.87] and [2.82, 12.82]. **`applied` is what was rendered**, so
    it is what a parity check has to match — the other is the plan, and a
    plan that prints what it did not build is a defect this repo has already
    recorded on this very file.
    """
    if not pj.exists():
        return []
    d = json.loads(pj.read_text())
    if isinstance(d, dict):
        return list(d.get("applied") or d.get("punches") or [])
    return [x.get("at", 0.0) if isinstance(x, dict) else float(x) for x in d]


def render(clip, ch, out: str | Path, *, punches: list[float] | None = None,
           crf: int = 17, log=print) -> dict:
    """Build the master. Returns what was decided, for the record."""
    out = Path(out)
    p = plan(clip, ch)
    if punches is None:
        punches = punch_times(p["overlays"] / "punches.json")
    segs = segments(p, ch, punches)
    log(f"  cut: {len(p['keeps'])} keeps -> {len(segs)} segments, "
        f"{p['n_shots']} shots, {p['out_dur']:.2f}s, {len(punches)} punch(es)")

    grade = ng.chain(ch.grade)                      # facecam only
    cg = cut_graph(p["keeps"], fps=ch.fps, src="0:v", out="rn_cut")
    base = ";".join([cg, nl.two_pane(ch, segs, cam=tuple(ch.cam),
                                     src="rn_cut", out="base",
                                     top_filters=grade)])
    ovs = overlay_list(p)
    log(f"  overlays: " + ", ".join(f"{o.path.name}(V{o.track})" for o in ovs))
    nc.check_schedule(ovs, fps=ch.fps)

    # THE PICTURE IS THE SUM OF THE KEEPS' OWN ROUNDED SPANS, which is what
    # Resolve's V1 holds and what `make_clip` recounts at assemble time —
    # NOT `round(out_dur * fps)`. On clip 12 those are 2716 and 2710, and
    # the caption and chat movies were rendered at the smaller one, so the
    # last 6 frames carry picture with no overlays. Reproduced rather than
    # corrected: the gate compares two renderers, and silently lengthening
    # the picture here would be a different clip, not a parity failure.
    picture = round(segs[-1].end * ch.fps)
    sfx = p["overlays"] / "sfx.wav"
    raw = out.with_name(out.stem + "_raw.mov")
    res = nc.composite(
        base_source=p["src"], base_graph=base, base_label="[base]",
        overlays=ovs, sfx=sfx, out=raw,
        speech_source=p["overlays"] / "_cut.wav",
        speech_for_eq=p["overlays"] / "_cut.wav",
        fps=ch.fps, dur=picture / ch.fps, crf=crf)
    # The loudness finish is `render_ffmpeg._finish_audio` — two-pass
    # loudnorm with true-peak limiting and `-c:v copy`, so no second video
    # encode. ASK FOR -1.5 TO DELIVER -1.0: the delivery is AAC and AAC
    # decode overshoots, which is why a -1.0 request measured -0.41 once and
    # `deliver_qc` correctly rejected that render.
    nc.finish(raw, out)
    log(f"  finished -> {out.name}")
    return {"out": str(out), "raw": str(raw), "picture_frames": picture,
            "segments": len(segs), "keeps": len(p["keeps"]),
            "shots": p["n_shots"], "punches": punches,
            "duration": p["out_dur"], **(res or {})}


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("spec", help="clips/<channel>-<NN>.json")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--parity", help="a Resolve render to compare against")
    a = ap.parse_args(argv)

    from engine.clipspec import load
    clip, ch = load(Path(a.spec))
    r = render(clip, ch, a.out)
    print(json.dumps({k: v for k, v in r.items()
                      if not isinstance(v, (dict, list))}, indent=1))
    if a.parity:
        from engine import render_parity as rp
        rep = rp.compare(a.parity, a.out)
        print(rep)
        return 0 if rep.ok else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
