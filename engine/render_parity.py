"""Two renderers, one edit — does any DECISION differ?

Resolve is the format workbench: a new look is built and judged there,
because the timeline can be opened and nudged. The native ffmpeg path is the
production line — headless, parallel, cloud-reachable — for clips whose
format is already settled. Both execute the same edit, so a clip rendered
either way has to be the same clip.

IT WILL NEVER BE THE SAME PIXELS. Resolve composites in linear light and
ffmpeg does not — this repo measured the identical alpha clip at a 0.189
luma ratio in ffmpeg and 0.015 in Resolve, a 12x difference. Scalers,
encoders and chroma siting all differ. So a pixel-difference threshold is
the wrong instrument: loose enough to pass two honest renders and it passes
a renderer that dropped a pane.

Parity here means NO DECISION DIFFERS.

TWO INSTRUMENTS, BECAUSE ONE DOES NOT COVER IT. Measured on clip 12 against
controls built from it (honest = re-encode and a softer bicubic/crf26 pass;
wrong = a 10px pane shift, a seam moved to 0.45, a mismatched facecam CDL,
and a different clip):

    instrument                honest      wrong                    gap
    row profile (geometry)    <=0.43      5.0 / 14.0 / 27.0        12x
    facecam d-saturation      <=0.05      1.88 / 15.10            38x
    facecam d(R-B) white pt   <=0.55      11.9                     22x

Those honest figures are the WORST of two calibrations — a straight
re-encode and a softer bicubic/crf26 pass measured 0.163/0.01/0.19, and
tests/test_render_parity.py, which compares a re-encode of a re-encode,
measured 0.429/0.048/0.54. The looser pair is the one recorded, because
two numbers for one thing is this repo's most-repeated defect and the
conservative one is the safe half of it.

They are ORTHOGONAL and that is the point: the geometry failures move the
row profile by 14-80x and the white point by 0.06-0.15, while the grade
failure moves the white point by 12.35 and the row profile by only 0.520 —
1.5x the honest floor, a knife edge. Either instrument alone passes a real
failure. Both thresholds below sit in the middle of a wide plateau, which
is the standard this repo requires after `sustain` separated six points at
exactly one parameter setting and nowhere else.

THE SEAM IS VERIFIED, NOT DETECTED, and that is a correction. The first
version hunted the largest horizontal gradient near 0.42H and reported 842
(0.4385) — the bottom edge of VLR.gg's NAVIGATION BAR, which is static
because the page never scrolls and is a stronger edge than the facecam-to-
document transition it was looking for. A moved seam shifts both panes, so
the row profile already catches it at 14x; a blind detector only added a
way to be wrong.

CALIBRATION CAVEAT, STATED BECAUSE IT IS NOT YET CLOSED. The honest
controls above are ffmpeg against ffmpeg. Resolve against ffmpeg will vary
by more than that, for the linear-light reason above. These thresholds are
provisional until a real native render exists to re-measure them against —
run `python -m engine.render_parity --calibrate <resolve.mp4> <native.mp4>`
and move them if the honest floor has risen. Do not loosen them by
guessing.

A gate that cannot fail is not a gate: tests/test_render_parity.py proves
this one rejects every wrong control above and passes the honest ones.
"""
from __future__ import annotations

import json
import statistics as st
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

SEAM = 0.42
BLACK_FLOOR = 16           # deliver_qc.black_frames uses the same floor
TRUE_PEAK_MAX = -0.55      # -1.0 asked; AAC decode overshoots, so the request carries it
LUFS_DELTA = 0.5           # deliver_qc's own band is +-0.7, so parity is tighter
DUR_FRAMES = 1.0           # one frame. A 1-frame drop cost clip 12 its payoff.

# --- the instruments, each set in the middle of its measured plateau -----
# GEOMETRY IS MEASURED ON THE ROW PROFILE'S GRADIENT, NOT ITS LEVEL, and the
# reason is a third Resolve artefact found when the first real cross-renderer
# pair was gated. Resolve writes an alpha overlay's RGB into the limited-range
# luma slot WITHOUT the full->limited conversion: `rm_Chat.mov`'s panel is
# exactly #18181B (24,24,27) at alpha 255, which a bt709 `tv` file should
# store as Y' 36.8; the native render stores 35.8 and Resolve stores 22.9.
# That uniform 13-code-value crush covers 420 rows and carried 67.5% of the
# whole row-profile residual — a LEVELS artefact contaminating a GEOMETRY
# instrument, pushing an otherwise-clean pair to 2.040 against a 2.0 floor.
# A gradient has no DC term, so it cannot see a uniform offset at all.
# Measured on the full 45s pair, not the 12s calibration slice: honest 0.757
# worst, the nearest failure 1.872. sqrt(0.757*1.872) = 1.19, so 1.2 is the
# geometric MIDDLE of the plateau — 1.58x above honest, 1.56x below wrong.
GRAD_MAX = 1.2             # honest <=0.76, 10px vertical shift 1.87, seam 2.20
LEVEL_MAX = 3.5            # honest <=1.32, a content-pane lift reads 8.02
SAT_MAX = 0.80             # honest <=0.05, wrong >=1.88 — 16x headroom
WHITEPOINT_MAX = 3.0       # honest <=0.55, wrong >=11.9 — 5.5x headroom
OFFSET_PX = 2              # a 2px pane shift is invisible; 3px is a different crop
CAPTION_INK_MIN = 0.002    # share of the caption band above the ink floor

# Row bands that hold NO alpha overlay in this format, so the two renderers
# must agree on their LEVELS exactly — the facecam above the hook line, and
# the content pane below the chat box. Measured honest: +0.16 and +0.00.
OVERLAY_FREE = (("facecam", 100, 660), ("content", 1550, 1880))

PROF_W = 216               # 1080/5. Scaled HORIZONTALLY only, so every row survives.
GRADE_W, GRADE_H = 270, 202


def _raw(args: list[str]) -> bytes:
    return subprocess.run(["ffmpeg", "-v", "error", *args],
                          capture_output=True).stdout


def _probe(path: Path) -> dict:
    return json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, check=True).stdout)


def _video(p: dict) -> dict:
    return next(s for s in p["streams"] if s["codec_type"] == "video")


def _fps(st_: dict) -> float:
    n, _, d = st_.get("r_frame_rate", "60/1").partition("/")
    return float(n) / float(d or 1)


# --- instrument 1: geometry ----------------------------------------------
def row_profile(path: Path, at: float, h: int) -> list[float] | None:
    """Mean luma per OUTPUT ROW. Scaled horizontally only, so a one-row
    event stays a one-row event instead of being smeared by the scaler."""
    raw = _raw(["-ss", f"{at:.3f}", "-i", str(path), "-frames:v", "1",
                "-vf", f"scale={PROF_W}:{h}:flags=bilinear,format=gray",
                "-f", "rawvideo", "-"])
    if len(raw) < PROF_W * h:
        return None
    return [sum(raw[y * PROF_W:(y + 1) * PROF_W]) / PROF_W for y in range(h)]


def row_gradient(prof: list[float]) -> list[float]:
    """The row profile's first difference — the levels-blind geometry signal.

    A uniform brightness offset over any band contributes NOTHING here,
    because every pair of adjacent rows is shifted by the same amount and
    the difference cancels. A geometric displacement moves every edge in the
    profile, so it shows up undiminished. Measured on the real pair: the
    level metric separates a 10px vertical shift from honest by 2.17x and
    this one by 4.30x, and a moved seam by 4.82x against 5.06x — better on
    both, and immune to the overlay-levels artefact that was eating the
    level metric's whole margin.
    """
    return [prof[i + 1] - prof[i] for i in range(len(prof) - 1)]


def pane_cols(path: Path, at: float, y0: int, y1: int, h: int) -> list[float]:
    """Mean luma per COLUMN over a row band — the signal for a lateral fit."""
    raw = _raw(["-ss", f"{at:.3f}", "-i", str(path), "-frames:v", "1",
                "-vf", f"scale={PROF_W}:{h}:flags=bilinear,format=gray",
                "-f", "rawvideo", "-"])
    if len(raw) < PROF_W * h:
        return []
    y0, y1 = max(0, y0), min(h, y1)
    n = max(1, y1 - y0)
    return [sum(raw[y * PROF_W + x] for y in range(y0, y1)) / n
            for x in range(PROF_W)]


def pane_rows(path: Path, at: float, x0: int, x1: int, h: int) -> list[float]:
    """Mean luma per ROW over a column band — the signal for a vertical fit.

    The companion to `pane_cols`, and the gate ran without it for a round.
    The row profile DOES catch a vertical fault — the test's `wrong_shift`
    control is a 10px vertical crop and instrument 1 rejects it — but it
    cannot say which pane moved or by how much, so a report could name a
    horizontal fault while the same cause was also moving content
    vertically. That is what happened to clip 12's facecam rect, and the
    round's own record then carried a `vertical +0px` row for a check that
    did not exist.

    The vertical axis is never downscaled (`row_profile` scales horizontally
    only), so a shift found here is already in output pixels. The column band
    is inset from the pane edges, where the two renderers' rounding of a
    non-integer pane width shows up and is not the fault being looked for.
    """
    raw = _raw(["-ss", f"{at:.3f}", "-i", str(path), "-frames:v", "1",
                "-vf", f"scale={PROF_W}:{h}:flags=bilinear,format=gray",
                "-f", "rawvideo", "-"])
    if len(raw) < PROF_W * h:
        return []
    x0, x1 = max(0, x0), min(PROF_W, x1)
    n = max(1, x1 - x0)
    return [sum(raw[y * PROF_W + x] for x in range(x0, x1)) / n
            for y in range(h)]


def best_offset(a: list[float], b: list[float], span: int = 12) -> tuple[int, float]:
    """Integer shift of `b` against `a` minimising mean |difference|.

    A LOW RESIDUAL AT A NON-ZERO SHIFT is the interesting failure: the pane
    holds the right content and is in the wrong place. This is the check
    that catches a `crop` which renders at exactly 1.00x — a defect that
    shipped here once and passed two eyeball checks on stills."""
    if not a or not b:
        return 0, float("inf")
    best = (0, float("inf"))
    for s in range(-span, span + 1):
        lo, hi = max(0, s), min(len(a), len(b) + s)
        if hi - lo < len(a) // 2:
            continue
        r = sum(abs(a[i] - b[i - s]) for i in range(lo, hi)) / (hi - lo)
        if r < best[1]:
            best = (s, r)
    return best


# --- instrument 2: grade -------------------------------------------------
def facecam_grade(path: Path, at: float, *, seam: float = SEAM,
                  h: int = 1920) -> tuple[float, float, float, int] | None:
    """(white-point R-B, mean saturation, mean luma, n) for the TOP pane.

    The lower pane is a document and is NOT graded, so including it would
    dilute exactly the signal being measured.

    R-B is taken on NEAR-NEUTRAL BRIGHTS — a real white in his room, the
    IKEA shelf or the picture frame. This repo already established that
    pane-mean R-B separates nothing and this separates everything: a white
    that swings across a clip is the definition of footage that has been
    graded."""
    cut = int(round(h * seam))
    raw = _raw(["-ss", f"{at:.3f}", "-i", str(path), "-frames:v", "1",
                "-vf", f"crop=iw:{cut}:0:0,scale={GRADE_W}:{GRADE_H},format=rgb24",
                "-f", "rawvideo", "-"])
    n = GRADE_W * GRADE_H
    if len(raw) < n * 3:
        return None
    wp, sat, lum = [], [], []
    for i in range(0, n * 3, 3):
        r, g, b = raw[i], raw[i + 1], raw[i + 2]
        y = 0.299 * r + 0.587 * g + 0.114 * b
        c = max(r, g, b) - min(r, g, b)
        lum.append(y)
        sat.append(c)
        if y > 165 and c < 45:
            wp.append(r - b)
    return (st.mean(wp) if wp else float("nan"),
            st.mean(sat), st.mean(lum), len(wp))


# --- the rest of the decisions -------------------------------------------
def pane_ymax(path: Path, *, seam: float = SEAM, h: int = 1920,
              floor: int = BLACK_FLOOR) -> dict:
    """Per-frame YMAX for each pane, AT FULL RATE.

    `signalstats`, not `scale=1:1` — a 1x1 downscale point-samples under the
    default bicubic flags and once reported this project's content pane at
    mean 3 where the real frame measures 22.2, inventing 270 black frames
    that do not exist. And crop FIRST, so one pane going dark is not hidden
    by the other being lit: that is how five self-inflicted black frames
    shipped, invisible to a 10fps sample and to `blackdetect` alike."""
    cut = int(round(h * seam))
    out: dict[str, float] = {}
    for name, vf in (("top", f"crop=iw:{cut}:0:0"),
                     ("bottom", f"crop=iw:{h - cut}:0:{cut}")):
        r = subprocess.run(
            ["ffmpeg", "-v", "info", "-i", str(path), "-vf",
             f"{vf},signalstats,metadata=print:key=lavfi.signalstats.YMAX",
             "-f", "null", "-"], capture_output=True, text=True).stderr
        vals = [float(ln.rsplit("=", 1)[1])
                for ln in r.splitlines() if "signalstats.YMAX=" in ln]
        out[f"{name}_frames"] = len(vals)
        out[f"{name}_min"] = min(vals) if vals else -1.0
        out[f"{name}_black"] = sum(1 for v in vals if v <= floor)
    return out


def loudness(path: Path) -> tuple[float, float]:
    r = subprocess.run(["ffmpeg", "-v", "info", "-i", str(path),
                        "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    lufs = peak = float("nan")
    for ln in r.splitlines()[-24:]:
        s = ln.strip()
        if s.startswith("I:") and "LUFS" in s:
            lufs = float(s.split()[1])
        if s.startswith("Peak:") and "dBFS" in s:
            peak = float(s.split()[1])
    return lufs, peak


def caption_ink(path: Path, at: float, h: int, *, band=(0.40, 0.55)) -> float:
    """Share of the caption band above an ink floor.

    The captions are white with a hard black stroke, so they are the
    brightest thing in that band by a wide margin — no text rendering is
    needed to detect them, which matters because THIS FFMPEG HAS NO libass,
    no libfreetype and no `drawtext` filter."""
    y0, y1 = int(band[0] * h), int(band[1] * h)
    raw = _raw(["-ss", f"{at:.3f}", "-i", str(path), "-frames:v", "1",
                "-vf", f"crop=iw:{y1 - y0}:0:{y0},scale={PROF_W}:-1,format=gray",
                "-f", "rawvideo", "-"])
    return (sum(1 for b in raw if b >= 235) / len(raw)) if raw else 0.0


# --- report ---------------------------------------------------------------
@dataclass
class Finding:
    name: str
    ok: bool
    detail: str
    fatal: bool = True


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(f.fatal and not f.ok for f in self.findings)

    def add(self, name, ok, detail, fatal=True):
        self.findings.append(Finding(name, bool(ok), detail, fatal))

    def __str__(self) -> str:
        return "\n".join(["PARITY" if self.ok else "DIFFERS"] + [
            f"   {'ok  ' if f.ok else 'FAIL'} {f.name:<14} {f.detail}"
            for f in self.findings])


def compare(reference: str | Path, candidate: str | Path, *,
            samples: int = 7, seam: float = SEAM,
            chat_expected: bool | None = None) -> Report:
    """Does the candidate make the same decisions as the reference?

    `reference` is the Resolve render and `candidate` the native one.
    Findings are phrased about the CANDIDATE, because that is the one that
    can be fixed — "the candidate is 3px low" is actionable where "they
    differ by 3px" is not."""
    a, b = Path(reference), Path(candidate)
    pa, pb = _probe(a), _probe(b)
    va, vb = _video(pa), _video(pb)
    da, db = float(pa["format"]["duration"]), float(pb["format"]["duration"])
    fps = _fps(va)
    h = int(va["height"])
    r = Report()

    r.add("size", (va["width"], va["height"]) == (vb["width"], vb["height"]),
          f"{vb['width']}x{vb['height']} vs {va['width']}x{va['height']}")
    if not r.findings[-1].ok:
        return r                      # everything below assumes one geometry

    df = abs(da - db) * fps
    r.add("duration", df <= DUR_FRAMES,
          f"{db:.3f}s vs {da:.3f}s ({df:.2f} frames, tol {DUR_FRAMES})")

    # Compare at the same instants in BOTH, over the shorter of the two.
    span = min(da, db)
    ts = [span * (i + 0.5) / samples for i in range(samples)]

    # instrument 1 — geometry (covers the seam: moving it shifts both panes)
    res, grad = [], []
    for t in ts:
        ra, rb = row_profile(a, t, h), row_profile(b, t, h)
        if ra and rb:
            res.append(sum(abs(x - y) for x, y in zip(ra, rb)) / h)
            da, db = row_gradient(ra), row_gradient(rb)
            grad.append(sum(abs(x - y) for x, y in zip(da, db)) / len(da))
    r.add("geometry", grad and max(grad) <= GRAD_MAX,
          f"row gradient {st.mean(grad):.3f} mean / {max(grad):.3f} worst "
          f"(tol {GRAD_MAX}; honest <=0.76, a 10px shift 1.87, a seam 2.20)"
          f"   [level metric {st.mean(res):.3f}, diagnostic only — see "
          f"GRAD_MAX on why it is not the gate]"
          if grad else "no frames read")

    # LEVELS, on the bands that carry no overlay. The geometry instrument is
    # deliberately blind to a uniform offset, so without this a renderer that
    # got every pane in the right place and the wrong brightness would pass.
    lv = []
    for name, y0, y1 in OVERLAY_FREE:
        d = []
        for t in ts:
            pa, pb = row_profile(a, t, h), row_profile(b, t, h)
            if pa and pb and y1 <= len(pa):
                d.append(st.median(pb[y] - pa[y] for y in range(y0, y1)))
        if d:
            lv.append((name, max(d, key=abs)))
    worst = max(lv, key=lambda kv: abs(kv[1])) if lv else None
    r.add("levels", worst is not None and abs(worst[1]) <= LEVEL_MAX,
          (f"{worst[0]} band median {worst[1]:+.2f} (tol {LEVEL_MAX}; honest "
           f"<=1.32, a content-pane lift reads 8.02); "
           + ", ".join(f"{k} {v:+.2f}" for k, v in lv))
          if worst else "no overlay-free band read")

    cut = int(round(h * seam))
    mid = ts[len(ts) // 2]
    scale = int(va["width"]) / PROF_W
    # BOTH AXES, PER PANE. One cause can move a pane on both — clip 12's
    # facecam rect differed in x0 AND y0 — so naming only the lateral shift
    # describes half the fault.
    bx0, bx1 = int(0.15 * PROF_W), int(0.85 * PROF_W)
    for name, y0, y1 in (("top pane", int(0.05 * h), cut - 8),
                         ("bottom pane", cut + 8, int(0.95 * h))):
        s, resid = best_offset(pane_cols(a, mid, y0, y1, h),
                               pane_cols(b, mid, y0, y1, h))
        r.add(f"{name} x", abs(s) * scale <= OFFSET_PX,
              f"best fit {s * scale:+.0f}px, residual {resid:.1f} "
              f"(low residual at a NON-ZERO shift = right crop, wrong place)")
        # The vertical profile is at full output resolution, so no `scale`.
        sy, residy = best_offset(pane_rows(a, mid, bx0, bx1, h)[y0:y1],
                                 pane_rows(b, mid, bx0, bx1, h)[y0:y1])
        r.add(f"{name} y", abs(sy) <= OFFSET_PX,
              f"best fit {sy:+d}px, residual {residy:.1f}")

    # instrument 2 — grade, facecam only
    ga = [facecam_grade(a, t, seam=seam, h=h) for t in ts]
    gb = [facecam_grade(b, t, seam=seam, h=h) for t in ts]
    ok = [(x, y) for x, y in zip(ga, gb) if x and y]
    if not ok:
        r.add("grade", False, "could not read the facecam pane")
    else:
        d_sat = abs(st.mean(x[1] for x, _ in ok) - st.mean(y[1] for _, y in ok))
        wa = [x[0] for x, _ in ok if x[0] == x[0]]
        wb = [y[0] for _, y in ok if y[0] == y[0]]
        d_wp = abs(st.mean(wa) - st.mean(wb)) if wa and wb else float("nan")
        r.add("grade sat", d_sat <= SAT_MAX,
              f"facecam d-saturation {d_sat:.3f} (tol {SAT_MAX}; "
              f"honest <=0.05, a mismatched CDL reads 15.1)")
        r.add("grade white", not (d_wp == d_wp) or d_wp <= WHITEPOINT_MAX,
              f"white-point d(R-B) {d_wp:+.2f} (tol {WHITEPOINT_MAX}; "
              f"honest <=0.55, a mismatched CDL reads 11.9)")

    m = pane_ymax(b, seam=seam, h=h)
    for pane in ("top", "bottom"):
        r.add(f"black {pane}", m[f"{pane}_black"] == 0,
              f"{m[f'{pane}_black']} of {m[f'{pane}_frames']} frames at or "
              f"under YMAX {BLACK_FLOOR} (min {m[f'{pane}_min']:.0f})")

    la, lb = loudness(a), loudness(b)
    r.add("loudness", abs(la[0] - lb[0]) <= LUFS_DELTA,
          f"{lb[0]:.2f} vs {la[0]:.2f} LUFS "
          f"({abs(la[0] - lb[0]):.2f}, tol {LUFS_DELTA})")
    r.add("true peak", lb[1] <= TRUE_PEAK_MAX,
          f"{lb[1]:.2f} dBTP (ceiling {TRUE_PEAK_MAX})")

    ia = [caption_ink(a, t, h) for t in ts]
    ib = [caption_ink(b, t, h) for t in ts]
    agree = sum(1 for x, y in zip(ia, ib)
                if (x >= CAPTION_INK_MIN) == (y >= CAPTION_INK_MIN))
    r.add("captions", agree == len(ia),
          f"{agree}/{len(ia)} sampled frames agree on whether a caption is up")

    if chat_expected is not None:
        from engine import chat_visible as cv
        ra_, rb_ = cv.visible(a, da), cv.visible(b, db)
        oa = ra_[0] if isinstance(ra_, tuple) else bool(ra_)
        ob = rb_[0] if isinstance(rb_, tuple) else bool(rb_)
        r.add("chat", oa == ob == bool(chat_expected),
              f"reference {oa}, candidate {ob}, expected {chat_expected}")
    return r


def calibrate(reference: str | Path, candidate: str | Path,
              *, samples: int = 7) -> dict:
    """The honest floor between these two files, for re-setting thresholds.

    Run this once a real native render exists. If the floor has risen above
    the tolerances, MOVE THEM DELIBERATELY and record the new plateau —
    do not loosen by guessing."""
    a, b = Path(reference), Path(candidate)
    h = int(_video(_probe(a))["height"])
    span = min(float(_probe(a)["format"]["duration"]),
               float(_probe(b)["format"]["duration"]))
    ts = [span * (i + 0.5) / samples for i in range(samples)]
    res, grd = [], []
    for t in ts:
        ra, rb = row_profile(a, t, h), row_profile(b, t, h)
        if ra and rb:
            res.append(sum(abs(x - y) for x, y in zip(ra, rb)) / h)
            da, db = row_gradient(ra), row_gradient(rb)
            grd.append(sum(abs(x - y) for x, y in zip(da, db)) / len(da))
    ga = [facecam_grade(a, t, h=h) for t in ts]
    gb = [facecam_grade(b, t, h=h) for t in ts]
    ok = [(x, y) for x, y in zip(ga, gb) if x and y]
    return {
        "gradient_mean": st.mean(grd) if grd else None,
        "gradient_worst": max(grd) if grd else None,
        "gradient_tol": GRAD_MAX,
        "level_mean": st.mean(res) if res else None,
        "level_worst": max(res) if res else None,
        "sat_delta": abs(st.mean(x[1] for x, _ in ok)
                         - st.mean(y[1] for _, y in ok)) if ok else None,
        "sat_tol": SAT_MAX,
        "headroom": (GRAD_MAX / max(grd)) if grd and max(grd) else None,
    }


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    if args[:1] == ["--calibrate"] and len(args) >= 3:
        print(json.dumps(calibrate(args[1], args[2]), indent=1))
    elif len(args) >= 2:
        rep = compare(args[0], args[1])
        print(rep)
        sys.exit(0 if rep.ok else 1)
    else:
        sys.exit(f"usage: {sys.argv[0]} <reference.mp4> <candidate.mp4>\n"
                 f"       {sys.argv[0]} --calibrate <a.mp4> <b.mp4>")
