"""Tier 2 detection: read the VALORANT killfeed and group kills into rounds.

Design follows what the open-source work in this space actually measured, not
what it hoped for:

  * OCR reads the killfeed in only ~13-16% of sampled frames, so a kill MUST be
    tracked across frames rather than trusted from one read.
  * ~94% row accuracy *when a row is located* — locating is the hard part.
  * The classic bug is counting kills and deaths together, so two kills and a
    death read as a triple. VALORANT draws a highlight border on the local
    player's own killfeed rows; gating on that highlight removes the bug.

So: sample sparsely, locate rows by shape, gate on the local-player highlight,
OCR only the surviving rows, then dedupe across time with fuzzy matching.

CALIBRATION REQUIRED. The ROI and the highlight colour below are starting
values, not measured ones. Run `calibrate` against a real VOD and adjust
config/killfeed.yaml before trusting any output. Do not import faster_whisper
in this process.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path

import cv2
import numpy as np
from rapidfuzz import fuzz

# ─── Defaults. Calibrate these. ────────────────────────────────────────────

ROI = (0.60, 0.04, 0.40, 0.26)      # x, y, w, h as fractions — top-right
SAMPLE_FPS = 5.0
ROW_MIN_H_FRAC = 0.055              # a killfeed row, as a fraction of ROI height
ROW_MAX_H_FRAC = 0.30
ROW_MIN_W_FRAC = 0.30
HIGHLIGHT_MIN_FRAC = 0.012          # fraction of row pixels matching the highlight
ROW_PITCH_FRAC = 0.193              # one killfeed row's pitch, as a fraction of ROI height
ROW_BAND_MIN_H_PX = 2               # a highlight band thinner than this is noise
FEED_CLEAR_S = 2.0                  # highlight count at 0 this long = feed cleared
ROUND_GAP_S = 10.0                  # cleared feed for this long ends a round
FUZZ_THRESHOLD = 92                 # only for labelling; detection does not rely on it

# The local player's own-kill highlight, in HSV. VALORANT's own-row border reads
# as a warm yellow/amber. Width of the band matters more than the exact hue.
HIGHLIGHT_HSV_LO = (18, 90, 140)
HIGHLIGHT_HSV_HI = (38, 255, 255)


@dataclass
class KillRead:
    t: float
    text: str
    highlight_frac: float
    row_box: tuple[int, int, int, int]


@dataclass
class KillEvent:
    t_first: float
    t_last: float
    text: str
    reads: int
    mean_highlight: float

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Round:
    index: int
    start: float
    end: float
    kills: list[dict] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.kills)

    def as_dict(self) -> dict:
        d = asdict(self)
        d["kills"] = self.kills
        d["n_kills"] = self.n
        d["label"] = label_for(self.n)
        return d


def label_for(n: int) -> str:
    return {0: "none", 1: "single", 2: "2k", 3: "3k", 4: "4k", 5: "ace"}.get(n, "ace+")


def load_config(path: str | Path | None = None) -> dict:
    """Merge config/killfeed.yaml over the defaults, if it exists."""
    cfg = {
        "roi": list(ROI),
        "sample_fps": SAMPLE_FPS,
        "highlight_hsv_lo": list(HIGHLIGHT_HSV_LO),
        "highlight_hsv_hi": list(HIGHLIGHT_HSV_HI),
        "highlight_min_frac": HIGHLIGHT_MIN_FRAC,
        "row_min_h_frac": ROW_MIN_H_FRAC,
        "row_max_h_frac": ROW_MAX_H_FRAC,
        "row_min_w_frac": ROW_MIN_W_FRAC,
        "require_highlight": True,
        "row_pitch_frac": ROW_PITCH_FRAC,
    }
    path = Path(path or Path(__file__).parent.parent / "config" / "killfeed.yaml")
    if path.exists():
        import yaml

        cfg.update(yaml.safe_load(path.read_text()) or {})
    return cfg


def _crop_roi(frame: np.ndarray, roi) -> np.ndarray:
    h, w = frame.shape[:2]
    x, y, rw, rh = roi
    return frame[int(y * h): int((y + rh) * h), int(x * w): int((x + rw) * w)]


def highlight_mask(roi_bgr: np.ndarray, cfg: dict) -> np.ndarray:
    hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
    return cv2.inRange(
        hsv,
        np.array(cfg["highlight_hsv_lo"], np.uint8),
        np.array(cfg["highlight_hsv_hi"], np.uint8),
    )


def find_rows(roi_bgr: np.ndarray, cfg: dict) -> list[tuple[int, int, int, int]]:
    """Locate the local player's own-kill rows from the highlight colour alone.

    Contour/morphology row-finding bridges vertically adjacent rows into one
    blob and loses the count, which is the number that actually matters. A
    horizontal projection of the highlight mask does not: each own-kill row is
    its own band of rows-with-amber-pixels, separated by clean gaps.
    """
    h, w = roi_bgr.shape[:2]
    mask = highlight_mask(roi_bgr, cfg)
    if mask.max() == 0:
        return []

    pitch = max(4.0, float(cfg.get("row_pitch_frac", ROW_PITCH_FRAC)) * h)

    # Per-scanline highlight count. A row's indicator spans most of the width,
    # whether it is a thin border or a filled tint.
    prof = (mask > 0).sum(axis=1)
    on = prof >= max(3, int(cfg["row_min_w_frac"] * w * 0.5))
    if not on.any():
        return []

    # Bridge a row's interior: with a thin border the top and bottom edges are
    # separated by nearly a full row, so the gap tolerance has to cover that.
    # Over-bridging is corrected below by splitting on pitch.
    gap_tol = int(pitch * 0.9)

    raw: list[tuple[int, int]] = []
    y = 0
    while y < h:
        if not on[y]:
            y += 1
            continue
        y0 = y
        gap = 0
        while y < h and (on[y] or gap < gap_tol):
            gap = 0 if on[y] else gap + 1
            y += 1
        y1 = y - gap
        if y1 - y0 >= ROW_BAND_MIN_H_PX:
            raw.append((y0, y1))

    # A band taller than ~1.4 pitch is adjacent rows merged together. Split it
    # into however many rows its height implies, so the COUNT stays right —
    # the count is the signal the event detector runs on.
    bands: list[tuple[int, int]] = []
    for (y0, y1) in raw:
        bh = y1 - y0
        n = max(1, int(round(bh / pitch)))
        if n == 1 or bh < pitch * 1.4:
            bands.append((y0, y1))
            continue
        step_ = bh / n
        for k in range(n):
            bands.append((int(y0 + k * step_), int(y0 + (k + 1) * step_)))

    rows = []
    for (y0, y1) in bands:
        sub = mask[max(0, y0):min(h, y1)]
        if sub.size == 0:
            continue
        cols = np.where((sub > 0).any(axis=0))[0]
        if cols.size == 0:
            continue
        x0, x1 = int(cols[0]), int(cols[-1])
        if (x1 - x0) < cfg["row_min_w_frac"] * w:
            continue
        rows.append((x0, y0, x1 - x0, y1 - y0))
    rows.sort(key=lambda r: r[1])
    return rows


def highlight_fraction(row_bgr: np.ndarray, cfg: dict) -> float:
    """How much of this row matches the local player's highlight colour."""
    hsv = cv2.cvtColor(row_bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array(cfg["highlight_hsv_lo"], np.uint8),
                       np.array(cfg["highlight_hsv_hi"], np.uint8))
    return float(mask.mean()) / 255.0


def ocr_row(row_bgr: np.ndarray) -> str:
    """OCR a single row. Upscaled and binarised — tesseract needs the help."""
    import subprocess
    import tempfile

    g = cv2.cvtColor(row_bgr, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
    g = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        cv2.imwrite(f.name, g)
        try:
            out = subprocess.run(
                ["tesseract", f.name, "stdout", "--psm", "7",
                 "-c", "tessedit_char_whitelist="
                       "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-. "],
                capture_output=True, text=True, timeout=20,
            )
            return " ".join(out.stdout.split())
        except Exception:
            return ""
        finally:
            Path(f.name).unlink(missing_ok=True)


def scan(
    video: str | Path,
    *,
    cfg: dict | None = None,
    offset: float = 0.0,
    start: float = 0.0,
    end: float | None = None,
    do_ocr: bool = True,
) -> dict:
    """Walk the video and return deduped kill events grouped into rounds."""
    cfg = cfg or load_config()
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open {video}")

    src_fps = cap.get(cv2.CAP_PROP_FPS) or 60.0
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    step = max(1, int(round(src_fps / float(cfg["sample_fps"]))))

    first = int(start * src_fps)
    last = int(end * src_fps) if end is not None else (n_frames or 10**9)

    samples: list[dict] = []
    frames_seen = 0
    frames_with_rows = 0
    rows_located = 0

    idx = first
    cap.set(cv2.CAP_PROP_POS_FRAMES, first)
    while idx < last:
        ok, frame = cap.read()
        if not ok:
            break
        if (idx - first) % step == 0:
            frames_seen += 1
            t = idx / src_fps + offset
            roi = _crop_roi(frame, cfg["roi"])
            rows = find_rows(roi, cfg)
            if rows:
                frames_with_rows += 1
            rows_located += len(rows)
            samples.append({
                "t": round(t, 3),
                "count": len(rows),
                "rows": [{"box": r, "crop": roi[r[1]:r[1] + r[3], r[0]:r[0] + r[2]].copy()}
                         for r in rows],
            })
        idx += 1
    cap.release()

    events = _events_from_counts(samples, do_ocr=do_ocr)
    rounds = _group_rounds(events)

    return {
        "source": str(video),
        "offset": offset,
        "sample_fps": cfg["sample_fps"],
        "stats": {
            "frames_sampled": frames_seen,
            "frames_with_rows": frames_with_rows,
            "row_hit_rate": round(frames_with_rows / frames_seen, 4) if frames_seen else 0.0,
            "rows_located": rows_located,
            "kills_detected": len(events),
        },
        "events": [e.as_dict() for e in events],
        "rounds": [r.as_dict() for r in rounds],
    }


def _events_from_counts(samples: list[dict], *, do_ocr: bool = True) -> list["KillEvent"]:
    """A new own-kill is a RISING EDGE in the highlighted-row count.

    This is the fix for the two failures that fuzzy text matching causes:
    killfeed rows differ by a character or two, so text similarity merges
    distinct kills; and OCR only reads the feed in a small minority of frames,
    so text cannot be the trigger at all. The count is robust to both. OCR is
    used afterwards, for a label.
    """
    events: list[KillEvent] = []
    prev = 0
    for s_ in samples:
        n = s_["count"]
        if n > prev:
            for k in range(n - prev):
                row = s_["rows"][min(prev + k, len(s_["rows"]) - 1)] if s_["rows"] else None
                text = ocr_row(row["crop"]) if (do_ocr and row is not None) else ""
                events.append(KillEvent(
                    t_first=s_["t"], t_last=s_["t"], text=text, reads=1, mean_highlight=0.0,
                ))
        prev = n

    # Carry t_last forward while the count stays up, so a round's span is real.
    for e in events:
        for s_ in samples:
            if s_["t"] >= e.t_first and s_["count"] > 0:
                e.t_last = s_["t"]
            elif s_["t"] > e.t_first and s_["count"] == 0:
                break
    return events


def _dead(reads):
    events = _dedupe(reads)
    rounds = _group_rounds(events)

    return {
        "source": str(video),
        "offset": offset,
        "sample_fps": cfg["sample_fps"],
        "stats": {
            "frames_sampled": frames_seen,
            "frames_with_rows": frames_with_rows,
            "row_hit_rate": round(frames_with_rows / frames_seen, 4) if frames_seen else 0.0,
            "rows_located": rows_located,
            "rows_passing_highlight": rows_highlighted,
        },
        "events": [e.as_dict() for e in events],
        "rounds": [r.as_dict() for r in rounds],
    }


def _dedupe(reads: list[KillRead]) -> list[KillEvent]:
    """One kill shows up in many sampled frames. Collapse by time + fuzzy text."""
    events: list[KillEvent] = []
    buckets: list[list[KillRead]] = []

    for r in sorted(reads, key=lambda x: x.t):
        placed = False
        for b in buckets:
            if r.t - b[-1].t > DEDUPE_WINDOW_S:
                continue
            ref = b[-1].text
            same = (
                (not ref and not r.text)
                or (ref and r.text and fuzz.ratio(ref, r.text) >= FUZZ_THRESHOLD)
            )
            if same:
                b.append(r)
                placed = True
                break
        if not placed:
            buckets.append([r])

    for b in buckets:
        texts = [x.text for x in b if x.text]
        best = max(set(texts), key=texts.count) if texts else ""
        events.append(
            KillEvent(
                t_first=b[0].t,
                t_last=b[-1].t,
                text=best,
                reads=len(b),
                mean_highlight=round(sum(x.highlight_frac for x in b) / len(b), 4),
            )
        )
    events.sort(key=lambda e: e.t_first)
    return events


def _group_rounds(events: list[KillEvent]) -> list[Round]:
    """Split on a cleared feed. Kills inside one round are seconds apart; the
    buy phase between rounds leaves the feed empty far longer."""
    rounds: list[Round] = []
    cur: list[KillEvent] = []
    for e in events:
        if cur and (e.t_first - cur[-1].t_first) > ROUND_GAP_S:
            rounds.append(_mk_round(len(rounds), cur))
            cur = []
        cur.append(e)
    if cur:
        rounds.append(_mk_round(len(rounds), cur))
    return rounds


def _mk_round(i: int, evs: list[KillEvent]) -> Round:
    return Round(
        index=i,
        start=evs[0].t_first,
        end=evs[-1].t_last,
        kills=[e.as_dict() for e in evs],
    )


def calibrate(video: str | Path, out_dir: str | Path, *, cfg: dict | None = None,
              at: list[float] | None = None) -> dict:
    """Dump ROI crops, located rows and highlight masks for eyeballing.

    Run this FIRST on real footage. If the ROI crop is not the killfeed, or no
    rows are located, nothing downstream means anything.
    """
    cfg = cfg or load_config()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 60.0
    dur = (cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / fps
    at = at or [dur * f for f in (0.2, 0.4, 0.6, 0.8)]

    report = []
    for t in at:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
        ok, frame = cap.read()
        if not ok:
            continue
        roi = _crop_roi(frame, cfg["roi"])
        rows = find_rows(roi, cfg)
        vis = roi.copy()
        hls = []
        for (x, y, w, h) in rows:
            hl = highlight_fraction(roi[y:y + h, x:x + w], cfg)
            hls.append(round(hl, 4))
            colour = (0, 255, 0) if hl >= cfg["highlight_min_frac"] else (0, 0, 255)
            cv2.rectangle(vis, (x, y), (x + w, y + h), colour, 2)
        stem = f"t{int(t):06d}"
        cv2.imwrite(str(out_dir / f"{stem}_frame.png"), frame)
        cv2.imwrite(str(out_dir / f"{stem}_roi.png"), roi)
        cv2.imwrite(str(out_dir / f"{stem}_rows.png"), vis)
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array(cfg["highlight_hsv_lo"], np.uint8),
                           np.array(cfg["highlight_hsv_hi"], np.uint8))
        cv2.imwrite(str(out_dir / f"{stem}_highlight.png"), mask)
        report.append({"t": round(t, 2), "rows": len(rows), "highlight_fracs": hls})
    cap.release()
    return {"out_dir": str(out_dir), "roi": cfg["roi"], "samples": report}


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="VALORANT killfeed detection")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s1 = sub.add_parser("scan")
    s1.add_argument("video")
    s1.add_argument("-o", "--out", default="-")
    s1.add_argument("--offset", type=float, default=0.0)
    s1.add_argument("--start", type=float, default=0.0)
    s1.add_argument("--end", type=float)
    s1.add_argument("--no-ocr", action="store_true")

    s2 = sub.add_parser("calibrate")
    s2.add_argument("video")
    s2.add_argument("-o", "--out-dir", required=True)
    s2.add_argument("--at", type=float, nargs="*")

    a = ap.parse_args()
    if a.cmd == "scan":
        res = scan(a.video, offset=a.offset, start=a.start, end=a.end, do_ocr=not a.no_ocr)
        blob = json.dumps(res, indent=2)
        if a.out == "-":
            print(blob)
        else:
            Path(a.out).write_text(blob)
            print(f"{len(res['events'])} kills in {len(res['rounds'])} rounds -> {a.out}")
            print(f"row hit rate {res['stats']['row_hit_rate']:.1%}")
    else:
        print(json.dumps(calibrate(a.video, a.out_dir, at=a.at), indent=2))
