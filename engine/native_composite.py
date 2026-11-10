"""Composite the overlay stack and mix the audio — in ffmpeg, not Resolve.

WHAT RESOLVE IS ACTUALLY DOING HERE, AND WHY IT IS REPLACEABLE. Everything
on V3 and above is already a finished file on disk: `cap_kin.mov` is the
whole caption track as one alpha movie (engine/captions_video.track),
`rm_Chat.mov` and `rm_*.mov` are Remotion renders, `sfx.wav` is the cue bed.
Measured by ffprobe on `overlays_15/`, every one is a FULL-FRAME 1080x1920
qtrle/argb clip, and nothing in make_clip sets Opacity or any clip or track
volume. So Resolve composites them at 0,0 at unity alpha and sums A1+A2 at
unity gain. That is a plain overlay chain plus one amix, with no geometry in
it at all — and it is the half of the Resolve dependency that costs nothing
to leave behind.

TRACK ORDER, from the survey of the live timeline:

    V1 content pane | V2 facecam | V3 chat | V4 cards | V5 titles | V6 captions
    A1 cut speech   | A2 sfx bed

The base picture (V1+V2) arrives here as a filter-graph label, because the
two-pane geometry, the per-shot framings and the facecam grade belong to the
caller. This module starts where the panes are already stacked.

FOUR THINGS THAT ARE MEASURED, NOT ASSUMED
──────────────────────────────────────────

1.  **THE setpts SHIFT IS THE ENTRANCE, AND WITHOUT IT THE CARD JOLTS IN.**
    An overlay's own timeline starts at 0, so a card scheduled at 0.8s has
    to be pushed to meet the main one. `enable=` alone looks like it works
    and does not: it REVEALS the overlay mid-hold. Measured on
    `rm_Bait.mov` at 0.8s, bright pixels in its own band:

        t      0.70   0.78   0.82   0.88   0.95   1.05   1.20   1.50
        shift     0      0      0   1611  12420  12448  12676  12740
        none      0      0  12738  12741  12742  12744  12745  12752

    Unshifted it goes 0 -> 12738 in ONE FRAME. That is exactly the defect
    this project spent a round removing ("right now it's just kind of
    jolting out of the frame", and the same at the other end), reintroduced
    by a missing constant. Shifted, the 20-frame spring entrance plays.

    **SUBSTITUTE THE NUMBER. `T` IS A VARIABLE IN setpts.** AGENTS.md
    records the fix as `setpts=PTS+T/TB`, where T stands for the shift — but
    setpts has its own `T` (the frame's own time in seconds), so writing
    that literally DOUBLES every timestamp instead of offsetting it. It has
    to be `setpts=PTS+0.800000/TB`.

2.  **A CORRECTION TO THE `format=rgb` NOTE, because it does not apply on
    this side.** AGENTS.md says `overlay=...:format=rgb` flattens alpha and
    the fix is `format=auto`. That was written while BUILDING alpha movies
    for Resolve, where the overlay filter's OUTPUT had to keep an alpha
    plane. Here the output is an opaque master and only the overlay's own
    alpha has to be read. Measured on this material, all five values are
    indistinguishable — the overlay-free band reads 119.011 / 119.013 /
    119.014 / 119.011 / 119.011 for auto / yuv420 / yuv444 / rgb / gbrp
    against the base's 120.863.

    `format=auto` is still what this module passes, on the honest grounds
    rather than the recorded ones: the chain composites in RGBA, so `auto`
    keeps it there instead of round-tripping every overlay through yuv420's
    subsampled chroma, which is where an accent-coloured caption edge would
    pay for it.

    WHAT DOES FLATTEN IS THE OVERLAY'S OWN INPUT, and it is the control
    this probe builds: force `format=rgb24` on the overlay before the blend
    and the full-frame argb clip composites as an opaque black rectangle —
    the overlay-free band goes 119.01 -> 0.00 with 100% of pixels under the
    black floor. That is the thing this project shipped once, and it is a
    119-point separation, so it is worth measuring rather than trusting.

3.  **`amix` HALVES THE MIX BY DEFAULT, AND RAMPS WHEN A BRANCH ENDS.**
    Resolve sums A1 and A2 at unity. `amix`'s `normalize` defaults to true,
    which is a 6 dB cut, and its `dropout_transition` then renormalises over
    2 seconds when one input ends. Measured on two equal sines, the second
    outlasting the first:

        opts                      0-2s     3.5-5s    6-8s
        normalize=0             -27.09     -30.11   -30.11
        normalize=1 (default)   -33.12     -32.50   -30.11   <- the ramp

    `normalize=0` is a flat unity sum and makes `dropout_transition` inert
    (setting it to 0 changes nothing), so it is not passed.

5.  **`aformat=channel_layouts=stereo` ON A MONO INPUT COSTS EXACTLY
    3.010 dB, AND THE BED IS MONO.** The survey flagged that `sfx.wav` is
    mono 48k against stereo speech and said to set the layout explicitly —
    which is what `aformat` looked like, and it is not. Measured on a mono
    0 dBFS tone, per output channel:

        no conversion (mono out)          -18.064 dBFS
        aformat channel_layouts=stereo    -21.074      <- -3.010 dB
        pan=stereo|c0=c0|c1=c0            -18.064      <- unity

    On an already-stereo input both are unity to three decimals (-6.934
    either way on the real source), so the branch is chosen by the channel
    count, which is PROBED rather than assumed. A mono bed therefore gets
    `pan=stereo|c0=c0|c1=c0`: an explicit unity copy to both channels, a
    matrix written in the graph where it can be read, instead of a standard
    downmix table applying a gain nobody put there.

    This was caught by the probe's own unity check failing — the sum came
    back 3 dB QUIETER than one of its inputs, which a unity sum cannot be.

    **WHAT RESOLVE DOES WITH A MONO A2 CLIP IS NOT ESTABLISHED, and that is
    a parity question, not this module's.** Two attempts: a least-squares
    fit of `master = a*speech + b*bed` on the 40-120 Hz band of the real
    Resolve render returned b = 0.488 (-6.23 dB) and is WORTHLESS — the
    speech alignment reached ncc 0.157 and the bed term bought 0.06 dB of
    residual, which is the raw-sample trap AGENTS.md already records ("verify
    an alignment on ENVELOPES, not raw samples"). An energy subtraction over
    the cue window, assuming A1 at unity, lands near -4.3 dB, with the 16 kHz
    resample of `_cut.wav` and the render's AAC encode both inside the
    estimate. So: unity is the default because it is the only value this
    module can state, `sfx_gain_db` is the knob, and settling it needs a
    Resolve render built for the measurement — a tone on A2, not a clip.

4.  **A SHORT OVERLAY EARLIER IN THE CHAIN MUST NOT KILL A LATER ONE.**
    `eof_action` defaults to `repeat`, which holds a finished card's last
    frame on screen forever. `pass` is correct, and the worry with `pass` is
    that an early EOF ends the chain. Measured with a 1.0s card at 1.0s on
    V4 and the caption track above it: the card's own box reads 0.907 ->
    0.856 -> 0.907 dark share across t=0.5/1.5/2.5 (on, then gone) while the
    caption band keeps its ink at every one of t=0.5..4.5. Output duration
    and frame count are unchanged — 300 frames / 5.000s in every variant,
    including the flattened and unshifted controls.

NOT EXPOSED TO THE exp() TRAP. AGENTS.md records that ffmpeg does not
short-circuit, so `gte(t,C)*exp(-k*(t-C))` evaluates the exp anyway and
exp(1036) * 0 is NaN. Every expression this module emits is a `between()`,
which has no such term. Anything added here that decays must clamp with
`max(0, t-C)`.

TWO SHAPES, BOTH SUPPORTED. `command()` takes `base_graph` + `base_label`, so
the geometry, the composite and the mix go in ONE ffmpeg invocation — pass
`engine.native_layout.two_pane(...)` straight in, which is what the probe
does. Or render the base to a file first and point `base_source` at it, which
is what the probe then does for the controls, because four composites off one
base file differ only in the thing under test: the reversed-order pair reads
identical to FOUR DECIMALS until the card lands, which a re-run geometry pass
could not promise.

MEASURED, FULL LENGTH, on clip 15's real overlays: base 3.7s + composite and
mix 13.8s + loudness finish 2.0s = 19.5s for a 27.08s clip, 1623 frames,
1080x1920, chat at 87% panel fill and caption ink 0.0152. Resolve's own
render of the same clip is about 9s. Wall clock per clip is the wrong
comparison, though: this runs headless, needs no logged-in desktop, and N of
them run at once, where Resolve serves its API on one GUI thread and the
queue is the constraint.

WHAT THIS MODULE DOES NOT DO. The two-pane geometry, the per-shot framings,
the punches and the facecam CDL are the caller's (engine/native_layout.py and
engine/native_grade.py).
The loudness finish is `engine.render_ffmpeg._finish_audio` and the voice
chain is `engine.render_ffmpeg.house_eq` — both are called, neither is
reimplemented. And this ffmpeg has no libass, no libfreetype, no fontconfig
and no `drawtext`, `subtitles` or `ass` filter (verified: 0 matches in
`-filters`), which is precisely why the caption track arrives as a movie.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

# Resolve track index -> what lives there. Kept as the survey found it so a
# reader can line this module up against `make_clip.stage_assemble`.
TRACK_CHAT, TRACK_CARDS, TRACK_TITLES, TRACK_CAPTIONS = 3, 4, 5, 6

# A card that animates out over 12-15 frames cannot have those frames
# trimmed away by the schedule. `make_clip` learned this when `rm_ExKru`
# overlapped `rm_StoryPrx` by six frames and Resolve resolved the collision
# by trimming the LATER clip's head, so the biggest graphic in the clip
# slammed on in one frame. ffmpeg will not trim — it will composite both at
# once — which is a different wrong, so the same guard applies.
SCHEDULE_GAP_FRAMES = 6


def _run(cmd: Sequence[str]) -> subprocess.CompletedProcess:
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(
            "ffmpeg failed\n  " + " ".join(str(c) for c in cmd[:18]) + " ...\n"
            + (p.stderr or "")[-3000:])
    return p


def file_frames(path: str | Path) -> int | None:
    """The overlay's own frame count, counted rather than estimated.

    `make_clip` takes a clip's length from the FILE for a measured reason:
    two card durations had been typed into a Python list by hand and were
    short, so Resolve trimmed the end of their exits off. The same number is
    what the schedule check has to compare, because the scheduled duration
    and the real one are exactly the two values that drifted apart.
    """
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
         "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True).stdout.strip()
    return int(out) if out.isdigit() else None


def channels(path: str | Path) -> int | None:
    """How many audio channels the file has. Probed, because the branch the
    audio graph takes depends on it and guessing costs 3 dB (see 5 above)."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
         "stream=channels", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True).stdout.strip()
    return int(out) if out.isdigit() else None


def stereo_branch(chans: int | None, *, sample_rate: int = 48000) -> str:
    """Get a branch to stereo without applying a gain on the way.

    Mono goes through an explicit `pan` matrix. Anything already stereo (or
    unknown, where `aformat` is a no-op on stereo and the 3 dB mono case is
    reported rather than silently taken) goes through `aformat`.
    """
    fmt = (f"aformat=sample_fmts=fltp:sample_rates={sample_rate}"
           f":channel_layouts=stereo")
    if chans == 1:
        # unity to both channels, written down. aformat would cost 3.010 dB.
        return f"pan=stereo|c0=c0|c1=c0,{fmt}"
    return fmt


@dataclass
class Overlay:
    """One alpha movie, where it starts, and which Resolve track it was on.

    `at` is OUTPUT seconds. `dur` None means the file's own length, which is
    what it should almost always be; a number shortens it, and the schedule
    check reports when that is throwing an exit away.
    """
    path: Path
    at: float = 0.0
    dur: float | None = None
    track: int = TRACK_CARDS
    x: int = 0
    y: int = 0

    @property
    def name(self) -> str:
        return Path(self.path).name


def _label(s: str) -> str:
    """Accept `v`, `[v]` or `0:v` and return the bracketed form."""
    s = s.strip()
    return s if s.startswith("[") else f"[{s}]"


def _bare(s: str) -> str:
    return s.strip().lstrip("[").rstrip("]")


def order(overlays: Iterable[Overlay]) -> list[Overlay]:
    """Bottom to top: V3 chat, V4 cards, V5 titles, V6 captions.

    A graphic lands ON TOP of the chat — measured off their own alpha,
    `rm_StoryPrx` covers 100% of the chat box footprint at alpha > 250, so
    the order is load-bearing and not cosmetic. Ties inside a track go by
    start time, which is the order Resolve placed them in.
    """
    return sorted(overlays, key=lambda o: (o.track, o.at, o.name))


def check_schedule(overlays: Sequence[Overlay], *, fps: float = 60.0,
                   gap: int = SCHEDULE_GAP_FRAMES) -> list[str]:
    """Problems with the plan, named, before a frame is rendered.

    Two kinds, both of which have shipped:

    * two overlays on ONE track whose FILE lengths overlap. In Resolve that
      silently trimmed the later clip's head; here it would composite both,
      which reads as two cards fighting. Either way the schedule is wrong.
    * a `dur` shorter than the file, which cuts the exit off.
    """
    problems: list[str] = []
    by_track: dict[int, list[Overlay]] = {}
    for o in order(overlays):
        n = file_frames(o.path)
        if n is None:
            problems.append(f"{o.name}: ffprobe could not count its frames")
            continue
        if o.dur is not None and round(o.dur * fps) < n - 1:
            problems.append(
                f"{o.name}: scheduled {o.dur:.2f}s ({round(o.dur*fps)}f) against "
                f"{n}f in the file — {n - round(o.dur*fps)} frames of its exit "
                f"would be cut")
        by_track.setdefault(o.track, []).append(o)
    for track, items in by_track.items():
        for a, b in zip(items, items[1:]):
            na = file_frames(a.path) or 0
            if round(a.at * fps) + na + gap > round(b.at * fps):
                problems.append(
                    f"V{track}: {a.name} at {a.at:.2f}s runs {na}f and collides "
                    f"with {b.name} at {b.at:.2f}s (needs {gap} frames clear)")
    return problems


# ── the video graph ──────────────────────────────────────────────────────

def video_graph(base: str, overlays: Sequence[Overlay], *,
                first_input: int = 1, out: str = "v",
                rgba: bool = True, pix_fmt: str = "yuv420p",
                fps: float = 60.0,
                flatten_alpha: bool = False,
                shift: bool = True) -> tuple[str, list[Path]]:
    """The overlay chain, as a filter_complex fragment.

    `base` is the label carrying the finished two-pane picture. Returns the
    fragment and the overlay files in the order the caller must pass `-i`,
    starting at `first_input`.

    `flatten_alpha` and `shift` exist to build the two CONTROLS this
    module's probe needs — a flattened composite and an unshifted one. A
    gate that cannot fail is not a gate, and neither is a measurement with
    nothing to separate it from.
    """
    ov = order(overlays)
    parts: list[str] = []
    last = _bare(base)

    if rgba:
        parts.append(f"[{last}]format=rgba[nc_bg]")
        last = "nc_bg"

    for i, o in enumerate(ov):
        idx = first_input + i
        pre: list[str] = []
        # THE SHIFT, with the number substituted — `T` is setpts' own
        # variable for the frame's time, so the recorded `PTS+T/TB` form
        # would double the timestamps rather than offset them.
        if shift and o.at > 0:
            pre.append(f"setpts=PTS+{o.at:.6f}/TB")
        if flatten_alpha:
            pre.append("format=rgb24")       # the control: alpha thrown away
        pre.append("null")
        parts.append(f"[{idx}:v]{','.join(pre)}[nc_o{i}]")

        opts = [f"{o.x}:{o.y}", "format=auto", "eof_action=pass"]
        # `enable` bounds the WINDOW; the shift aligns the CONTENT. Both are
        # needed: `enable` alone reveals a card mid-hold (measured above),
        # and the shift alone cannot shorten a card or hide one whose file
        # outlasts its slot.
        dur = o.dur
        if dur is None:
            n = file_frames(o.path)
            dur = (n / fps) if n else None
        if dur is not None:
            opts.append(f"enable='between(t,{o.at:.3f},{o.at + dur:.3f})'")
        elif o.at > 0:
            opts.append(f"enable='gte(t,{o.at:.3f})'")
        parts.append(f"[{last}][nc_o{i}]overlay={':'.join(opts)}[nc_s{i}]")
        last = f"nc_s{i}"

    parts.append(f"[{last}]format={pix_fmt}{_label(out)}")
    return ";".join(parts), [Path(o.path) for o in ov]


# ── the audio graph ──────────────────────────────────────────────────────

def audio_graph(speech: str, sfx: str, *, out: str = "a",
                eq: str | None = None, sfx_gain_db: float = 0.0,
                speech_channels: int | None = None,
                sfx_channels: int | None = None,
                sample_rate: int = 48000) -> str:
    """A1 + A2 at unity, then the voice chain.

    `speech` and `sfx` are input labels (`0:a`, `2:a`, ...). `eq` is the
    string `engine.render_ffmpeg.house_eq` returned — passed in rather than
    computed here, because that function has to be MEASURED ON THE SPEECH
    and the master it is applied to already has the bed in it. Measuring the
    master would keep the high-pass on BECAUSE a Vine Boom reads as rumble,
    and then cut the boom: 52.8% of that cue's energy sits under 85 Hz, and
    the chain costs it 7.09 dB of RMS for 1.83 dB of peak.

    It is applied to the MASTER, after the sum, which is where make_clip
    applies it (`-af EQ` on the Resolve render, bed included). Moving it to
    the speech branch would be an improvement and a DIVERGENCE, and this
    path has to render the same decisions as the one it replaces.

    `speech_channels` / `sfx_channels` pick each branch's route to stereo.
    Pass them — `composite()` probes them for you. Leaving them None takes
    `aformat`, which is a no-op on stereo and a silent 3.010 dB cut on mono.
    """
    g = [f"[{_bare(speech)}]"
         f"{stereo_branch(speech_channels, sample_rate=sample_rate)}[nc_sp]"]
    bed = [stereo_branch(sfx_channels, sample_rate=sample_rate)]
    if abs(sfx_gain_db) > 1e-9:
        bed.append(f"volume={sfx_gain_db:+.3f}dB")
    g.append(f"[{_bare(sfx)}]{','.join(bed)}[nc_bd]")
    # normalize=0 is the unity sum; see the module docstring for the 6 dB
    # cut and the 2-second renormalisation ramp that the default applies.
    mix = "amix=inputs=2:duration=longest:normalize=0"
    g.append(f"[nc_sp][nc_bd]{mix}[nc_mix]")
    g.append(f"[nc_mix]{eq if eq else 'anull'}{_label(out)}")
    return ";".join(g)


# ── the command ──────────────────────────────────────────────────────────

def command(*, base_source: str | Path, overlays: Sequence[Overlay],
            sfx: str | Path, out: str | Path,
            base_graph: str | None = None, base_label: str = "0:v",
            speech_source: str | Path | None = None,
            speech_label: str | None = None,
            eq: str | None = None, fps: float = 60.0,
            dur: float | None = None, crf: int = 17,
            preset: str = "medium", audio_codec: str = "pcm_s16le",
            flatten_alpha: bool = False, shift: bool = True,
            sfx_gain_db: float = 0.0,
            pix_fmt: str = "yuv420p") -> list[str]:
    """The whole ffmpeg argv, with the inputs in the order the graph expects.

    Input order is fixed and is the one thing a caller must not shuffle:
    `base_source` is 0, the overlays follow in track order, and the bed is
    last — with `speech_source` just before it when the speech is a separate
    file. `video_graph` is told `first_input=1` and labels every stage with
    an `nc_` prefix so it cannot collide with a caller's own base graph.

    `dur` bounds the output. PAD IT: make_clip trims at `(frames + 3)/fps`
    because `-t` on the picture bounds the AUDIO too, and the three frames
    are the last word's release — measured, the Resolve render ended a word
    cleanly at -53 dB and the trim handed it over at -14 dB, 67 ms short.
    """
    vg, ov_paths = video_graph(base_label, overlays, first_input=1, out="ncv",
                               fps=fps, pix_fmt=pix_fmt,
                               flatten_alpha=flatten_alpha, shift=shift)

    inputs: list[str] = ["-i", str(base_source)]
    for p in ov_paths:
        inputs += ["-i", str(p)]
    nxt = 1 + len(ov_paths)

    if speech_source is not None:
        sp, sp_ch = f"{nxt}:a", channels(speech_source)
        inputs += ["-i", str(speech_source)]
        nxt += 1
    else:
        sp = speech_label or "0:a"
        # The speech rides input 0 with the base. Probe THAT file — the
        # label is a label and carries no channel count with it.
        sp_ch = channels(base_source) if _bare(sp).startswith("0:") else None
    bed = f"{nxt}:a"
    inputs += ["-i", str(sfx)]

    ag = audio_graph(sp, bed, out="nca", eq=eq, sfx_gain_db=sfx_gain_db,
                     speech_channels=sp_ch, sfx_channels=channels(sfx))
    graph = ";".join(x for x in (base_graph, vg, ag) if x)

    cmd = ["ffmpeg", "-y", "-v", "error", *inputs,
           "-filter_complex", graph, "-map", "[ncv]", "-map", "[nca]"]
    if dur is not None:
        cmd += ["-t", f"{dur:.4f}"]
    # TAG THE COLOUR. The Resolve delivery carries bt709 primaries and
    # transfer; an untagged file leaves a player to guess, and these clips go
    # to platforms that re-encode. It changes no pixel — only the VUI — and
    # the loudness finish is `-c:v copy`, so the tags survive to delivery.
    cmd += ["-c:v", "libx264", "-crf", str(crf), "-preset", preset,
            "-pix_fmt", pix_fmt, "-r", f"{fps:g}",
            "-color_primaries", "bt709", "-color_trc", "bt709",
            "-colorspace", "bt709", "-color_range", "tv",
            # AND THE FLAGS ALONE DO NOT WORK ON THIS BUILD. Measured on a
            # 64x64 testsrc, mov and mp4 alike: ffmpeg's libx264 wrapper
            # writes matrix_coefficients into the VUI and silently DROPS
            # colour_primaries and transfer_characteristics, whatever is
            # passed. `h264_metadata` writes all three, costs no re-encode,
            # and survives the loudness finish because that is `-c:v copy`.
            # The flags above stay: they are what swscale reads, and they
            # state the intent even where the muxer ignores them.
            "-bsf:v", "h264_metadata=colour_primaries=1:"
                      "transfer_characteristics=1:matrix_coefficients=1",
            "-c:a", audio_codec, "-ar", "48000", str(out)]
    return cmd


def composite(*, base_source, overlays, sfx, out, speech_for_eq=None,
              check: bool = True, **kw) -> dict:
    """Run it. Returns what was built and what the voice chain decided.

    `speech_for_eq` is the cut speech with no bed and no loudnorm — the
    16 kHz mono wav `make_clip._cut_audio` writes. Passing it makes the
    high-pass a measurement; leaving it out makes it `anull`, which is
    honest rather than silently applying a constant.
    """
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    report: dict = {"output": str(out), "overlays": [], "schedule": []}

    if check:
        report["schedule"] = check_schedule(overlays, fps=kw.get("fps", 60.0))

    eq = kw.pop("eq", None)
    if eq is None and speech_for_eq is not None:
        from engine.render_ffmpeg import house_eq
        eq, m = house_eq(speech_for_eq)
        report["voice_chain"] = m
    report["eq"] = eq

    sp_src = kw.get("speech_source")
    report["audio"] = {
        "speech_channels": channels(sp_src if sp_src is not None else base_source),
        "sfx_channels": channels(sfx),
        "sfx_gain_db": kw.get("sfx_gain_db", 0.0)}

    for o in order(overlays):
        n = file_frames(o.path)
        report["overlays"].append(
            {"name": o.name, "track": o.track, "at": round(o.at, 3),
             "file_frames": n,
             "dur": round(o.dur, 3) if o.dur is not None else
                    (round(n / kw.get("fps", 60.0), 3) if n else None)})

    cmd = command(base_source=base_source, overlays=overlays, sfx=sfx,
                  out=out, eq=eq, **kw)
    report["command"] = " ".join(cmd)
    _run(cmd)
    report.update(_probe(out))
    return report


def finish(raw: str | Path, out: str | Path, *,
           target_lufs: float = -14.0, true_peak_dbtp: float = -1.5,
           audio_codec: str = "aac") -> Path:
    """The loudness finish, which already exists — so call it.

    `engine.render_ffmpeg._finish_audio` is two-pass loudnorm with true-peak
    limiting and `-c:v copy`, so this costs no second video encode.

    ASK FOR -1.5 TO DELIVER -1.0. The ceiling is hard and loudnorm hits its
    target on the PCM it limits, but the delivery is AAC and AAC decode
    overshoots — a -1.0 request has measured -0.64, -0.77 and -0.41 on this
    material, and `deliver_qc` correctly rejected the last one. The headroom
    belongs in the request, not in a cue being backed off to hide it.
    """
    from engine.render_ffmpeg import _finish_audio
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    _finish_audio(Path(raw),
                  {"audio": {"target_lufs": target_lufs,
                             "true_peak_dbtp": true_peak_dbtp},
                   "render": {"audio_codec": audio_codec}}, out)
    return out


def _probe(path: Path) -> dict:
    d = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True).stdout or "{}")
    v = next((s for s in d.get("streams", []) if s["codec_type"] == "video"), {})
    a = next((s for s in d.get("streams", []) if s["codec_type"] == "audio"), {})
    n, _, den = (v.get("r_frame_rate") or "0/1").partition("/")
    return {"width": v.get("width"), "height": v.get("height"),
            "frames": int(v["nb_read_frames"]) if v.get("nb_read_frames") else None,
            "fps": (float(n) / float(den or 1)) if n else None,
            "duration": float(d.get("format", {}).get("duration", 0.0)) or None,
            "vcodec": v.get("codec_name"), "acodec": a.get("codec_name"),
            "achannels": a.get("channels")}


# ── the probe ────────────────────────────────────────────────────────────
#
# Everything below builds and measures ONE real case. The base it makes is
# PROBE SCAFFOLDING and not the geometry port: it is the first 5 seconds of
# clip 15's source in its shot-0 framing, enough to be a real 1080x1920
# 60fps two-pane picture with the right content under the right overlays.
# The two-pane geometry, the framings, the punches and the grade belong to
# engine/render_native.py.

ROOT = Path(__file__).resolve().parent.parent

# Clip 15, shot 0, from the surveyed plan() inversion. fill=True everywhere,
# so the overflow axis is centre-cropped and the limiting axis is vertical:
# cam aspect 1.779 against the pane's 1.3393.
PROBE = {
    "src": ROOT / "jobs/fns-2905408276/clips_1080"
                  "/15_0h17m30s_open-qualifier-system-is-clearly-bet.mp4",
    "overlays": ROOT / "jobs/fns-2905408276/overlays_15",
    "top": (1496, 344, 364, 272),      # x, y, w, h in source px
    "bot": (481, 92, 958, 988),
    "seam_px": 806,                    # 0.42 * 1920 = 806.4, split 806 + 1114
    "fps": 60.0,
    "secs": 5.0,
}


def base_graph(secs: float) -> tuple[str, str]:
    """(filter fragment, label) producing the two-pane base for the probe.

    PREFER THE REAL THING. `engine.native_layout.two_pane` is the geometry
    port and takes exactly the shape `command()`'s `base_graph` wants, so
    the probe runs the real builder when it is importable — which makes the
    seam between the two modules a thing that is exercised rather than
    asserted. The inline fallback below is scaffolding for when it is not,
    so this module's probe never depends on a sibling to prove its own job.
    """
    try:
        from engine import clipspec, native_layout
        clip, ch = clipspec.load(ROOT / "clips/fns-15.json")
        shot = native_layout.Shot(0.0, secs, inset=0.0)
        g = native_layout.two_pane(ch, [shot], cam=clip.cam or ch.cam,
                                   src="0:v", out="ncbase")
        return g, "[ncbase]"
    except Exception as e:                      # scaffolding, named
        print(f"  (native_layout unavailable — {type(e).__name__}: {e}; "
              f"using the probe's own two-pane scaffolding)")
        tx, ty, tw, th = PROBE["top"]
        bx, by, bw, bh = PROBE["bot"]
        sy = PROBE["seam_px"]
        g = ("[0:v]split=2[nt][nb];"
             f"[nt]crop={tw}:{th}:{tx}:{ty},scale=1080:{sy}:flags=lanczos[ntop];"
             f"[nb]crop={bw}:{bh}:{bx}:{by},"
             f"scale=1080:{1920-sy}:flags=lanczos[nbot];"
             "[ntop][nbot]vstack=inputs=2[ncbase]")
        return g, "[ncbase]"


def _probe_base(dst: Path) -> Path:
    """The base rendered to a file, so the controls all share one picture.

    One file rather than re-running the geometry per variant: four composites
    off one base differ ONLY in the thing under test, which is what makes
    the reversed-order pair read identical to four decimals before the card
    lands.
    """
    g, lab = base_graph(PROBE["secs"])
    _run(["ffmpeg", "-y", "-v", "error", "-t", f"{PROBE['secs']}",
          "-i", str(PROBE["src"]), "-filter_complex", g,
          "-map", lab, "-map", "0:a", "-c:v", "libx264", "-crf", "14",
          "-preset", "veryfast", "-pix_fmt", "yuv420p",
          "-r", f"{PROBE['fps']:g}", "-c:a", "pcm_s16le", str(dst)])
    return dst


def _band(path: Path, at: float, y0: int, y1: int,
          x0: int = 0, x1: int = 1080) -> tuple[float, float]:
    """(mean luma, share under the black floor) over a rectangle.

    `crop` first and no downscale, because a 1x1 or whole-frame mean hides
    one pane going dark behind the other — this repo's `scale=1:1` read
    invented 270 black frames that do not exist.

    THE x RANGE IS NOT OPTIONAL and the first version of the track-order
    check omitted it. Measuring the full 1080 width over the chat box's rows
    puts the story card's paper OUTSIDE the box into the same mean, so the
    reversed-order control came back only 14.8 luma away from the correct
    one and looked like a knife edge. Restricted to the box the same pair
    separates by an order of magnitude more.
    """
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{at:.3f}", "-i", str(path),
         "-frames:v", "1",
         "-vf", f"crop={x1-x0}:{y1-y0}:{x0}:{y0},format=gray",
         "-f", "rawvideo", "-"], capture_output=True).stdout
    if not raw:
        return float("nan"), float("nan")
    return sum(raw) / len(raw), sum(1 for b in raw if b < 16) / len(raw)


def _bright(path: Path, at: float, y0: int, y1: int, thr: int = 200) -> int:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{at:.4f}", "-i", str(path),
         "-frames:v", "1", "-vf", f"crop=1080:{y1-y0}:0:{y0},format=gray",
         "-f", "rawvideo", "-"], capture_output=True).stdout
    return sum(1 for b in raw if b >= thr) if raw else -1


def _audio_lvl(src, start=0.0, dur=None, *, af=None) -> tuple[float, float]:
    import array
    import math
    a = ["-ss", f"{start:.4f}"] + (["-t", f"{dur:.4f}"] if dur else [])
    f = ["-af", af] if af else []
    raw = subprocess.run(["ffmpeg", "-v", "error", *a, "-i", str(src), *f,
                          "-ac", "1", "-ar", "48000", "-f", "s16le", "-"],
                         capture_output=True).stdout
    x = array.array("h")
    x.frombytes(raw[:len(raw) // 2 * 2])
    if not x:
        return -999.0, -999.0
    db = lambda v: 20 * math.log10(v) if v > 0 else -999.0
    pk = max(abs(v) for v in x) / 32768.0
    rm = math.sqrt(sum((v / 32768.0) ** 2 for v in x) / len(x))
    return db(pk), db(rm)


def run_probe(work: Path) -> int:
    import sys
    sys.path.insert(0, str(ROOT))
    from engine import chat_visible, render_parity

    work.mkdir(parents=True, exist_ok=True)
    OV = PROBE["overlays"]
    fps, secs = PROBE["fps"], PROBE["secs"]
    bad = 0

    def line(ok: bool, name: str, detail: str) -> None:
        nonlocal bad
        if not ok:
            bad += 1
        print(f"  {'PASS' if ok else 'FAIL'}  {name:26s} {detail}")

    print("native_composite probe — clip 15's real overlays on a 5s base")
    print(f"  overlays: {OV}")
    base = _probe_base(work / "nc_base.mov")
    b = _probe(base)
    print(f"  base: {b['width']}x{b['height']} {b['fps']:g}fps "
          f"{b['frames']}f {b['duration']:.3f}s")

    # Clip 15's real stack is chat on V3, the hook on V5 at 0.8s and the
    # caption track on V6 — `cards: []` in its spec, so it ships with
    # NOTHING ON V4 and would leave the track order half untested.
    # `rm_StoryVitality.mov` is clip 16's real story card, borrowed to
    # exercise V4, and the claim under test is purely compositional: does a
    # graphic land ON TOP of the chat. Said plainly rather than passed off
    # as clip 15's own card.
    CARD = ROOT / "jobs/fns-2905408276/overlays_16/rm_StoryVitality.mov"
    stack = [
        Overlay(OV / "rm_Chat.mov", 0.0, track=TRACK_CHAT),
        Overlay(OV / "rm_Bait.mov", 0.8, track=TRACK_TITLES),
        Overlay(OV / "cap_kin.mov", 0.0, track=TRACK_CAPTIONS),
    ]
    # The card stack is kept SEPARATE and only the track-order check uses
    # it, because a card that covers the chat box legitimately hides the
    # chat — see the note on that check.
    card_stack = stack + [Overlay(CARD, 1.2, track=TRACK_CARDS)]
    print("  stack (bottom to top):")
    for o in order(stack):
        print(f"    V{o.track}  {o.name:16s} at {o.at:5.2f}s  "
              f"{file_frames(o.path)}f")

    probs = check_schedule(stack, fps=fps)
    line(not probs, "schedule", "no collisions, no clipped exits"
         if not probs else "; ".join(probs))

    rep = composite(base_source=base, overlays=stack, sfx=OV / "sfx.wav",
                    out=work / "nc_good.mp4",
                    speech_for_eq=OV / "_cut.wav", fps=fps,
                    dur=(round(secs * fps) + 3) / fps)
    vc = rep.get("voice_chain", {})
    print(f"  voice chain: sub-85 {vc.get('rumble_dbfs')} dBFS vs body "
          f"{vc.get('body_dbfs')} ({vc.get('margin_db'):+} dB) -> high-pass "
          f"{'ON' if vc.get('highpass') else 'OFF'}")

    # the two controls
    flat = composite(base_source=base, overlays=stack, sfx=OV / "sfx.wav",
                     out=work / "nc_flat.mp4", eq=rep["eq"], fps=fps,
                     check=False, flatten_alpha=True)
    nosh = composite(base_source=base, overlays=stack, sfx=OV / "sfx.wav",
                     out=work / "nc_noshift.mp4", eq=rep["eq"], fps=fps,
                     check=False, shift=False)
    card = composite(base_source=base, overlays=card_stack,
                     sfx=OV / "sfx.wav", out=work / "nc_card.mp4",
                     eq=rep["eq"], fps=fps, check=False)
    # order() has to be able to FAIL, so build the same stack upside down:
    # the chat above the card instead of under it. Same files, same times.
    flip = [Overlay(o.path, o.at, o.dur, track=9 - o.track, x=o.x, y=o.y)
            for o in card_stack]
    rev = composite(base_source=base, overlays=flip, sfx=OV / "sfx.wav",
                    out=work / "nc_reversed.mp4", eq=rep["eq"], fps=fps,
                    check=False)
    good, bad_flat, bad_nosh = (Path(r["output"]) for r in (rep, flat, nosh))
    with_card, bad_rev = Path(card["output"]), Path(rev["output"])

    print("\n-- the artifact ---------------------------------------------")
    line(rep["width"] == 1080 and rep["height"] == 1920,
         "resolution", f"{rep['width']}x{rep['height']}")
    line(abs((rep["frames"] or 0) - b["frames"]) <= 1, "frame count",
         f"{rep['frames']}f against the base's {b['frames']}f "
         f"({rep['duration']:.3f}s)")
    line(rep["achannels"] == 2 and rep["acodec"] == "pcm_s16le", "audio stream",
         f"{rep['acodec']} {rep['achannels']}ch")

    # (a) the caption track is visible
    print("\n-- (a) captions, render_parity.caption_ink ------------------")
    ts = [secs * f for f in (0.15, 0.35, 0.55, 0.75, 0.9)]
    gi = [render_parity.caption_ink(good, t, 1920) for t in ts]
    bi = [render_parity.caption_ink(base, t, 1920) for t in ts]
    mg, mb = sum(gi) / len(gi), sum(bi) / len(bi)
    print("    t        " + " ".join(f"{t:7.2f}" for t in ts))
    print("    base     " + " ".join(f"{v:7.4f}" for v in bi))
    print("    composite" + " ".join(f"{v:7.4f}" for v in gi))
    line(mg >= render_parity.CAPTION_INK_MIN and mb < render_parity.CAPTION_INK_MIN,
         "caption ink",
         f"composite {mg:.4f} vs bare base {mb:.4f}, floor "
         f"{render_parity.CAPTION_INK_MIN} — the base carries none, so the "
         f"ink is the overlay")

    # (b) the chat panel is visible, by engine.chat_visible
    print("\n-- (b) chat, engine.chat_visible ---------------------------")
    ok_g, why_g = chat_visible.visible(good, secs)
    ok_b, why_b = chat_visible.visible(base, secs)
    ok_f, why_f = chat_visible.visible(bad_flat, secs)
    print(f"    composite  {'VISIBLE' if ok_g else 'NOT VISIBLE'}  {why_g}")
    print(f"    bare base  {'VISIBLE' if ok_b else 'NOT VISIBLE'}  {why_b}")
    print(f"    flattened  {'VISIBLE' if ok_f else 'NOT VISIBLE'}  {why_f}")
    cg = sum(chat_visible.measure(good, secs * f)[1] for f in (0.15, 0.5, 0.9)) / 3
    cb = sum(chat_visible.measure(base, secs * f)[1] for f in (0.15, 0.5, 0.9)) / 3
    line(ok_g, "chat_on_screen", why_g)
    # BE HONEST: the gate PASSES the bare base on this clip, because clip
    # 15's lower pane is already a dark page with colour in it — exactly the
    # limitation chat_visible.py documents. The ratio against the base is
    # what actually says the panel landed.
    line(cb > 0 and cg / max(cb, 1e-9) >= 4.0, "chat vs the bare base",
         f"{cg:.0f} coloured px/frame against {cb:.0f} with no chat at all "
         f"= {cg/max(cb,1e-9):.1f}x (the gate alone passes the base here)")

    # (c) alpha preserved
    print("\n-- (c) alpha, the overlay-free band y 0..650 ---------------")
    mb0, kb = _band(base, 2.5, 0, 650)
    mg0, kg = _band(good, 2.5, 0, 650)
    mf0, kf = _band(bad_flat, 2.5, 0, 650)
    print(f"    base       mean {mb0:7.3f}   under the black floor {kb:.4f}")
    print(f"    composite  mean {mg0:7.3f}   under the black floor {kg:.4f}")
    print(f"    flattened  mean {mf0:7.3f}   under the black floor {kf:.4f}")
    line(abs(mg0 - mb0) < 4.0 and kg < 0.10, "alpha preserved",
         f"composite is within {abs(mg0-mb0):.2f} luma of the base")
    line(mf0 < 1.0 and kf > 0.95, "the flatten control fails",
         f"flattened reads {mf0:.3f} with {kf:.0%} of the band black — the "
         f"opaque rectangle this project shipped once")

    # track order: a graphic lands ON TOP of the chat
    print("\n-- track order, V4 card over V3 chat ------------------------")
    # THE INSTRUMENT IS THE PANEL'S OWN DARK FILL, not a luma mean. A mean
    # over the box mixes the card's dark press photo with the panel's white
    # type and separated the two orderings by only 26.9 of ~47 — a knife
    # edge, which this repo has learned not to call a finding. The share of
    # the box under the near-black floor is `chat_visible`'s own signal and
    # separates them by 0.42-0.44 out of 1.
    def covered(path, at):
        return chat_visible.measure(path, at)[0]
    print(f"    share of the chat box {chat_visible.BOX} under the "
          f"near-black floor; the card lands at 1.2s")
    print(f"    {'t':>6} {'V4 over V3':>11} {'V3 over V4':>11} "
          f"{'no card':>9} {'base':>8}")
    for t in (0.60, 1.10, 2.00, 3.00, 4.80):
        print(f"    {t:6.2f} {covered(with_card,t):11.4f} "
              f"{covered(bad_rev,t):11.4f} {covered(good,t):9.4f} "
              f"{covered(base,t):8.4f}")
    pre_c, pre_r = covered(with_card, 1.10), covered(bad_rev, 1.10)
    g3, r3, n3 = covered(with_card, 3.0), covered(bad_rev, 3.0), covered(good, 3.0)
    line(abs(pre_c - pre_r) < 0.005, "identical before the card",
         f"both orderings read {pre_c:.4f} at t=1.10, before the card lands "
         f"— so what follows is the order and nothing else")
    line(r3 - g3 > 0.20, "a graphic lands on the chat",
         f"the card hides {r3-g3:.2f} of the panel's black fill when it is "
         f"ON TOP ({g3:.4f}) and none of it underneath ({r3:.4f}, against "
         f"{n3:.4f} with no card at all) — the plateau is 0.02..0.42, so "
         f"0.20 is not a fitted threshold")

    # AND A PROPERTY OF THE GATE WORTH KNOWING. `chat_visible` measures the
    # chat panel's own dark fill, so a card that lands ON the box hides the
    # chat from it by design — this very stack reads 49% fill against the
    # 50% floor with the card up for 4 of the probe's 5 seconds. On a 45s
    # clip two 4s cards reach ~18% of the gate's samples and it does not
    # bite; on a card-heavy clip it would, and the honest reading is "the
    # panel was covered", not "the chat was missing".
    cardfill = chat_visible.visible(with_card, secs)[1]
    print(f"    with the card up: {cardfill}")

    # the setpts shift, which `enable` alone cannot do
    print("\n-- the entrance: shifted vs unshifted, bait band y 660..820 -")
    print(f"    {'t':>6} {'shifted':>9} {'unshifted':>10} {'base':>8}")
    for t in (0.70, 0.78, 0.82, 0.88, 0.95, 1.05, 1.50, 2.50):
        print(f"    {t:6.2f} {_bright(good,t,660,820):9d} "
              f"{_bright(bad_nosh,t,660,820):10d} {_bright(base,t,660,820):8d}")
    g82, g95 = _bright(good, 0.82, 660, 820), _bright(good, 0.95, 660, 820)
    n82 = _bright(bad_nosh, 0.82, 660, 820)
    line(g82 < g95 * 0.25 and n82 > g95 * 0.75, "setpts shift",
         f"shifted {g82} -> {g95} across its entrance; unshifted is already "
         f"{n82} in one frame")

    # the audio sum, over the WHOLE bed — the 5s picture's bed is silent
    print("\n-- the audio sum, unity -------------------------------------")
    cue = (13.40, 14.00)
    cue_win = (cue[0], cue[1] - cue[0])
    pk_b, rm_b = _audio_lvl(OV / "sfx.wav")
    print(f"    the bed has ONE cue, {cue[0]:.2f}-{cue[1]:.2f}s, peak "
          f"{pk_b:.2f} dBFS — so the 5s picture's bed is digital silence "
          f"and the sum is measured over the whole clip instead")
    sp_ch, bd_ch = channels(OV / "_cut.wav"), channels(OV / "sfx.wav")
    print(f"    speech {sp_ch}ch -> {stereo_branch(sp_ch).split(',')[0]}   "
          f"bed {bd_ch}ch -> {stereo_branch(bd_ch).split(',')[0]}")

    def mix_to(dst: Path, graph: str) -> Path:
        _run(["ffmpeg", "-y", "-v", "error", "-i", str(OV / "_cut.wav"),
              "-i", str(OV / "sfx.wav"), "-filter_complex", graph,
              "-map", "[a]", "-c:a", "pcm_s24le", str(dst)])
        return dst

    g_unity = audio_graph("0:a", "1:a", out="a", speech_channels=sp_ch,
                          sfx_channels=bd_ch)
    full = mix_to(work / "nc_audio_full.wav", g_unity)
    norm = mix_to(work / "nc_audio_norm.wav",
                  g_unity.replace(":normalize=0", ""))
    # the control for finding 5: what `aformat` alone would have done
    upm = mix_to(work / "nc_audio_upmix.wav",
                 audio_graph("0:a", "1:a", out="a"))

    sp = _audio_lvl(OV / "_cut.wav")
    mx, nm, um = _audio_lvl(full), _audio_lvl(norm), _audio_lvl(upm)
    cu_mix = _audio_lvl(full, cue[0], cue[1] - cue[0])
    cu_bed = _audio_lvl(OV / "sfx.wav", cue[0], cue[1] - cue[0])
    cu_upm = _audio_lvl(upm, cue[0], cue[1] - cue[0])
    print(f"    {'speech alone':30s} peak {sp[0]:7.2f}  rms {sp[1]:7.2f}")
    print(f"    {'bed alone, at the cue':30s} peak {cu_bed[0]:7.2f}  "
          f"rms {cu_bed[1]:7.2f}")
    print(f"    {'unity sum (pan matrix)':30s} peak {mx[0]:7.2f}  "
          f"rms {mx[1]:7.2f}")
    print(f"    {'same, aformat upmix':30s} peak {um[0]:7.2f}  "
          f"rms {um[1]:7.2f}   <- the 3.010 dB")
    print(f"    {'same, amix default':30s} peak {nm[0]:7.2f}  "
          f"rms {nm[1]:7.2f}   <- normalize=1")
    # A unity sum can only ADD, so it cannot come back under either input.
    line(mx[0] >= sp[0] - 0.05 and mx[0] <= sp[0] + 1.5, "unity sum",
         f"the mix holds the speech's peak ({sp[0]:.2f} -> {mx[0]:.2f} dBFS). "
         f"`aformat` alone gives {um[0]:.2f} and amix's default {nm[0]:.2f} — "
         f"a unity sum cannot be quieter than one of its inputs")
    # MEASURE THE CUE IN ITS OWN BAND. A peak over the whole window is the
    # SPEECH's peak — -7.28 dBFS there is his voice, not a boom — so the
    # check would pass on a bed that had been silenced. 52.8% of this cue's
    # energy sits under 85 Hz and the voice's does not, which is the band
    # AGENTS.md measures booms in.
    LB = ("-af", "highpass=f=40,lowpass=f=120")
    def lb(src, a, d):
        return _audio_lvl(src, a, d, af="highpass=f=40,lowpass=f=120")
    q0, qd = 5.0, 3.0                       # a quiet stretch, no cue in it
    cu_m, cu_b = lb(full, *cue_win), lb(OV / "sfx.wav", *cue_win)
    cu_s, base_m = lb(OV / "_cut.wav", *cue_win), lb(full, q0, qd)
    cu_u = lb(upm, *cue_win)
    print(f"    40-120 Hz   {'bed at the cue':22s} rms {cu_b[1]:7.2f}")
    print(f"                {'speech at the cue':22s} rms {cu_s[1]:7.2f}")
    print(f"                {'mix at the cue':22s} rms {cu_m[1]:7.2f}")
    print(f"                {'mix, a quiet 3s':22s} rms {base_m[1]:7.2f}   "
          f"-> the cue is {cu_m[1]-base_m[1]:+.2f} dB over its own baseline")
    line(cu_m[1] - base_m[1] >= 5.0 and cu_m[1] >= cu_s[1] + 1.0,
         "the cue survives the mix",
         f"the boom's own band reads {cu_m[1]-base_m[1]:+.2f} dB over the "
         f"clip's baseline and {cu_m[1]-cu_s[1]:+.2f} dB over the speech "
         f"alone there; via `aformat` it would be {cu_u[1]-cu_s[1]:+.2f} dB")

    # the loudness finish, which is render_ffmpeg's and not reimplemented
    print("\n-- the finish, engine.render_ffmpeg._finish_audio -----------")
    fin = finish(good, work / "nc_final.mp4")
    fp = _probe(fin)
    loud = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(fin), "-af",
         "loudnorm=print_format=json", "-f", "null", "-"],
        capture_output=True, text=True).stderr
    import re
    m = re.search(r'"input_i"\s*:\s*"(-?[\d.]+)"', loud)
    tp = re.search(r'"input_tp"\s*:\s*"(-?[\d.]+)"', loud)
    lufs = float(m.group(1)) if m else None
    peak = float(tp.group(1)) if tp else None
    print(f"    {fp['vcodec']}/{fp['acodec']} {fp['frames']}f "
          f"{fp['duration']:.3f}s   {lufs} LUFS / {peak} dBTP")
    line(lufs is not None and abs(lufs + 14.0) < 1.0, "loudness",
         f"{lufs} LUFS against the -14.0 target")
    line(peak is not None and peak <= -1.0, "true peak",
         f"{peak} dBTP under the hard -1.0 ceiling (asked for -1.5 because "
         f"AAC decode overshoots)")

    print(f"\n  wrote {work}")
    print(f"  {'ALL CHECKS PASS' if bad == 0 else f'{bad} CHECK(S) FAILED'}")
    return bad


if __name__ == "__main__":
    import argparse
    import sys

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-o", "--out", default=(
        "/private/tmp/claude-501/-Users-georgegeddes-Library-Application-Support-"
        "Claude-scratch-workspaces-6d38ae6d-05dd-4827-8e46-76304910d38e-"
        "68f1a3b0-a8d1-4d98-a822-3205d41bec7a-scratch-2026-10-28-f045e2/"
        "ce92e562-40cc-4445-80fa-a3607729fc90/scratchpad/native"))
    a = ap.parse_args()
    sys.exit(1 if run_probe(Path(a.out)) else 0)
