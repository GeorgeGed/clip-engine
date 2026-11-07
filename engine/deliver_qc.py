"""The delivery gate: every defect this project has shipped, checked on the file.

`engine/qc.py` judges a render generically — resolution, loudness, dead
audio. This judges a CLIP THE WAY WE BUILD THEM, and every check in it
exists because something got past and reached George. Gates judge the plan;
this judges the artifact, and the split matters: at least three of these
defects passed a plan-level check and still shipped.

| check | the version it would have caught |
|---|---|
| `black_frames` | the one-frame pane blackout from `endFrame` being exclusive, and the head/tail frames from Resolve's MarkIn offset and overlay overhang |
| `hallucinated_captions` | "I AGREE WE AGREE ON THIS" burned over 1.4s of digital zero at whisper confidence 1.000 |
| `dead_space` | 21.6% quiet after three separate instructions to cut all of it |
| `words_survived` | a splice eating a word — the check the 15 dead-space joins needed and did not have |
| `loudness` | every clip shipping ~7 dB quiet before normalisation was a step |
| `caption_cadence` | a caption track running at twice the reference rate |

**A WARNING IS NOT A PASS.** `ok` is false only for a defect that must not
ship; everything else is a `warn` that still prints. The one thing this
cannot judge is whether the clip is WORTH watching — one narrative, explains
itself, ends on the payoff. Those are editorial and a human or a judging
pass decides them, which is why `batch.py` keeps them in a separate stage.
"""
from __future__ import annotations

import difflib
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# the house targets, every one of them measured and recorded in AGENTS.md
LUFS_TARGET, LUFS_TOL = -14.0, 0.7
TRUE_PEAK_MAX = -1.0 + 0.45          # loudnorm lands a shade over its ceiling
QUIET_MAX = 0.08                     # share of the clip at the 0.35s floor
CAPTION_RATE = (1.2, 2.6)            # cards/second; the reference is "~twice a second"
WORD_SIMILARITY_MIN = 0.95
SEAM = 0.42


@dataclass
class Finding:
    check: str
    ok: bool
    detail: str
    fatal: bool = False


@dataclass
class Report:
    path: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(f.fatal and not f.ok for f in self.findings)

    def text(self) -> str:
        head = f"{'PASS' if self.ok else 'FAIL'}  {Path(self.path).name}"
        lines = [head]
        for f in self.findings:
            mark = "ok  " if f.ok else ("FAIL" if f.fatal else "warn")
            lines.append(f"   {mark} {f.check:22s} {f.detail}")
        return "\n".join(lines)


def _ff(args):
    return subprocess.run(args, capture_output=True, text=True)


def black_frames(path, *, seam: float = SEAM, floor: int = 16):
    """Per-frame YMAX on each pane, at FULL RATE.

    A one-frame drop is invisible to a 10fps sample, and `blackdetect` misses
    it entirely because only one PANE goes dark while the rest of the frame
    is lit. `scale=1:1` is also wrong — it point-samples under the default
    bicubic flags and invents black frames that do not exist.
    """
    out = []
    h = int(round(1920 * seam))
    for name, crop in (("top", f"1080:{h}:0:0"), ("bottom", f"1080:{1920-h}:0:{h}")):
        # `metadata=print` writes at INFO level, so `-v error` SILENCES it and
        # the regex then matches nothing — which this gate reported as "0
        # frames, no black frames found", i.e. a PASS from a check that
        # measured nothing. Write to a file instead and read it back.
        tmp = Path(f"/tmp/_ymax_{name}_{abs(hash(str(path))) % 99999}.txt")
        _ff(["ffmpeg", "-v", "error", "-i", str(path),
             "-vf", f"crop={crop},signalstats,metadata=print:"
                    f"key=lavfi.signalstats.YMAX:file={tmp}", "-f", "null", "-"])
        txt = tmp.read_text() if tmp.exists() else ""
        tmp.unlink(missing_ok=True)
        vals = [float(x) for x in re.findall(r"YMAX=(\d+\.?\d*)", txt)]
        if not vals:
            raise RuntimeError(
                f"signalstats returned no frames for the {name} pane of {path} — "
                "the check measured nothing, which must not read as a pass")
        bad = [i for i, v in enumerate(vals) if v < floor]
        out.append((name, len(vals), min(vals), bad))
    return out


def hallucinated_captions(cards, absent, *, min_share: float = 0.5):
    """Cards whose own span is mostly digital zero — whisper inventing words.

    Whisper's confidence is worthless for this: it is HIGHEST where there is
    nothing to transcribe (1.000 and 0.999 on the two words it invented over
    clip 6's mutes). The audio is the check, not the model.
    """
    out = []
    for c in cards:
        a, b = (c["start"], c["end"]) if isinstance(c, dict) else (c.start, c.end)
        txt = c["text"] if isinstance(c, dict) else c.text
        span = max(b - a, 1e-6)
        mute = sum(max(0.0, min(b, y) - max(a, x)) for x, y in absent)
        if mute / span > min_share:
            out.append((round(a, 2), txt, round(mute / span, 2)))
    return out


def words_survived(src_words, delivered_path, *, model="base"):
    """Re-transcribe the FINISHED cut and diff it against the source.

    "Every word must survive." This is the check the dead-space joins always
    needed: a splice that ate a word is invisible to every other measurement
    here, because the file is clean, correctly timed and correctly loud.
    """
    from engine import transcribe
    tr = transcribe.transcribe(delivered_path, model_size=model)
    heard = [w["text"].strip().lower().strip(".,!?")
             for u in tr["utterances"] for w in u["words"]]
    said = [w["text"].strip().lower().strip(".,!?") for w in src_words]
    ratio = difflib.SequenceMatcher(None, said, heard).ratio()
    missing = [w for w in said if w not in heard]
    return ratio, len(said), len(heard), missing[:12]


def check(path, *, cards=None, absent=None, src_words=None, seam: float = SEAM,
          duration_range=(15.0, 90.0), verify_words: bool = False,
          chat_expected: bool | None = None) -> Report:
    from engine import qc
    path = Path(path)
    rep = Report(str(path))
    # the measurements live under "measured", not at the top level — reading
    # the wrong key gave duration 0.00 and a caption rate of 9e7 cards/s,
    # both of which the gate happily printed as warnings rather than noticing
    # it had been handed nothing
    d = qc.check(path).as_dict().get("measured", {})
    dur = float(d.get("duration") or 0.0)
    if dur <= 0:
        raise RuntimeError(f"no duration measured for {path}")

    rep.findings.append(Finding(
        "duration", duration_range[0] <= dur <= duration_range[1],
        f"{dur:.2f}s (want {duration_range[0]:.0f}-{duration_range[1]:.0f})",
        fatal=False))

    lufs, tp = d.get("lufs"), d.get("true_peak")
    if lufs is not None:
        rep.findings.append(Finding(
            "loudness", abs(lufs - LUFS_TARGET) <= LUFS_TOL,
            f"{lufs:.2f} LUFS (target {LUFS_TARGET})", fatal=True))
    if tp is not None:
        rep.findings.append(Finding(
            "true_peak", tp <= TRUE_PEAK_MAX, f"{tp:.2f} dBTP", fatal=True))

    for name, n, mn, bad in black_frames(path, seam=seam):
        rep.findings.append(Finding(
            f"black_{name}", not bad,
            f"{n} frames, YMAX min {mn:.0f}" +
            (f", BLACK at {bad[:6]}" if bad else ""), fatal=True))

    q = qc.quiet_runs(path, min_run=0.35)["runs"]
    qt = sum(b - a for a, b in q)
    rep.findings.append(Finding(
        "dead_space", dur > 0 and qt / dur <= QUIET_MAX,
        f"{qt:.2f}s quiet ({100*qt/max(dur,1e-6):.1f}%, max {100*QUIET_MAX:.0f}%)"))

    da = qc.dead_audio(path, min_run=0.3)["runs"]
    rep.findings.append(Finding(
        "absent_audio", not da,
        f"{sum(b-a for a,b in da):.2f}s in {len(da)} runs", fatal=False))

    if cards is not None:
        rate = len(cards) / max(dur, 1e-6)
        rep.findings.append(Finding(
            "caption_cadence", CAPTION_RATE[0] <= rate <= CAPTION_RATE[1],
            f"{rate:.2f} cards/s ({len(cards)} cards)"))
        if absent is not None:
            bad = hallucinated_captions(cards, absent)
            rep.findings.append(Finding(
                "hallucinated_captions", not bad,
                "none" if not bad else
                f"{len(bad)} over a mute: " +
                ", ".join(f"{t}s {txt!r} {s:.0%}" for t, txt, s in bad[:4]),
                fatal=True))

    if verify_words and src_words:
        ratio, n_said, n_heard, missing = words_survived(src_words, path)
        rep.findings.append(Finding(
            "words_survived", ratio >= WORD_SIMILARITY_MIN,
            f"similarity {ratio:.3f}, {n_said} said / {n_heard} heard" +
            (f", missing {missing}" if missing else "")))
    # AN OVERLAY THAT RENDERED IS NOT AN OVERLAY THAT IS VISIBLE. Clip 07
    # shipped with no chat while the build log said "91 messages on the cut",
    # "1717 frames -> rm_Chat.mov" and "appended 4 of 4: V3:1" — the window
    # list was empty, so 13 MB of overlay sat on the timeline and was never
    # on screen for a frame. Only the file settles it.
    if chat_expected is not None:
        from engine import chat_visible                   # noqa: PLC0415
        seen, why = chat_visible.visible(path, dur)
        # FATAL. `Report.ok` only fails on fatal findings, and the first
        # version of this left the default — so it printed FAIL on the line
        # and PASS overall, which is the "a gate that measures nothing reads
        # as a pass" defect this file already records. A clip that was
        # supposed to carry chat and carries none is not deliverable.
        rep.findings.append(Finding(
            "chat_on_screen", seen == bool(chat_expected),
            (f"{'visible' if seen else 'NOT VISIBLE'} — {why}"
             if chat_expected else
             f"{'VISIBLE but was not planned' if seen else 'absent, as planned'} — {why}"),
            fatal=True))

    return rep
