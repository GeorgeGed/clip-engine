"""Gate enforcement for edit.json.

The methodology is only worth something if it is mechanical. Every rule in
CLIP-METHODOLOGY.md that can be checked is checked here, and an edit that fails
a hard gate never reaches a render or a human.

Three outcomes, mirroring the quote desk:
  reject   — the edit is wrong; do not render
  hold     — a human must look before it ships
  fallback — the edit was silently corrected, and says so

Pure logic, no I/O, no cv2. Safe to import anywhere.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ─── Constants straight out of the methodology ─────────────────────────────

# Soft windows, per genre. These WARN; they never reject. Both reference clips
# sat outside the windows I invented before seeing real footage (R1 ran 80s,
# R2 ran 20s), so the clock does not get to veto an edit.
DURATION = {
    "frag": (12.0, 35.0),
    "take": (15.0, 50.0),
    "receipts": (45.0, 110.0),   # R1 measured 80.3s
    "hybrid": (12.0, 90.0),
}
DURATION_ABSOLUTE = (5.0, 180.0)

TAIL_FRAMES = (36, 90)
RAMP_FRAMES_DEFAULT = 8

SLOWMO_MAX_SOURCE_FRAMES = 30
SLOWMO_SPEED_RANGE = (0.2, 0.9)
DEAD_TIME_SPEED_RANGE = (1.6, 2.2)

FRAG_MIN_SECONDS_BETWEEN_CUTS = 4.0

# Measured: R1 puts L2 captions ON the seam at ~0.44; R2 puts them at 0.747,
# low in the pane, in the gap between bracket columns. Both are L2 and both are
# right. So there is no correct y per layout — the only real rule is that the
# caption sits inside the safe band and does not cover what matters underneath.
CAPTION_Y_ADVISORY = {"L1": (0.60, 0.70), "L2": (0.40, 0.76), "L3": (0.60, 0.70)}

SAFE_TOP_PX = 150
SAFE_BOTTOM_PX = 320
CANVAS = (1080, 1920)

# R1 delivered -11.79 LUFS, R2 -14.26. Short-form runs hotter than my first
# guess of -14 exactly. True peak is the thing that is genuinely wrong when it
# is wrong (R1 clips at +1.25 dBTP), so that is checked separately.
LOUDNESS_RANGE = (-16.0, -10.5)
TRUE_PEAK_CEILING = -0.1
SPEAKER_CONFIDENCE_MIN = 0.85
FACECAM_FRAME_FRACTION_FLOOR = 0.02  # UI faces sit near 1%; a real webcam is several %
WORD_BOUNDARY_TOLERANCE_S = 0.06
RIGHTS_OK = {"explicit", "affiliate", "client_owned"}


@dataclass
class GateResult:
    passed: bool = True
    rejected: list[str] = field(default_factory=list)
    held: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    fallbacks: list[str] = field(default_factory=list)
    edit: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "rejected": self.rejected,
            "held": self.held,
            "warnings": self.warnings,
            "fallbacks": self.fallbacks,
        }

    def report(self) -> str:
        lines = []
        verdict = "PASS" if self.passed else "REJECT"
        if self.passed and self.held:
            verdict = "HOLD"
        lines.append(f"{verdict}  {(self.edit or {}).get('clip_id', '?')}")
        for tag, items in (
            ("reject ", self.rejected),
            ("hold   ", self.held),
            ("warn   ", self.warnings),
            ("fixed  ", self.fallbacks),
        ):
            for it in items:
                lines.append(f"  {tag} {it}")
        return "\n".join(lines)


def _dur(seg: dict[str, Any]) -> float:
    return float(seg["out"]) - float(seg["in"])


def _near_word_boundary(t: float, boundaries: list[float]) -> bool:
    return any(abs(t - b) <= WORD_BOUNDARY_TOLERANCE_S for b in boundaries)


def check(
    edit: dict[str, Any],
    *,
    word_boundaries: list[float] | None = None,
    apply_fallbacks: bool = True,
) -> GateResult:
    """Run every gate. Returns a GateResult carrying a (possibly corrected) edit."""
    e = copy.deepcopy(edit)
    r = GateResult(edit=e)

    genre = e.get("genre", "frag")
    fps = float(e.get("source", {}).get("fps") or 60)
    layout = e.setdefault("layout", {})
    mode = layout.get("mode", "L1")

    # ── Rights ─────────────────────────────────────────────────────────────
    basis = e.get("source", {}).get("rights_basis")
    if basis not in RIGHTS_OK:
        r.rejected.append(f"rights_basis {basis!r} is not one of {sorted(RIGHTS_OK)}")
    for ins in e.get("inserts", []) or []:
        if not ins.get("rights_basis"):
            r.held.append(f"insert {ins.get('asset')!r} has no rights basis")
    music = (e.get("audio") or {}).get("music")
    if music and not music.get("rights_basis"):
        r.held.append(f"music bed {music.get('bed')!r} has no rights basis")
    for s in (e.get("audio") or {}).get("sfx", []) or []:
        if not s.get("rights_basis"):
            r.held.append(f"sfx {s.get('asset')!r} has no rights basis")

    # ── Duration ───────────────────────────────────────────────────────────
    rng = e.get("range", {})
    total = float(rng.get("out", 0)) - float(rng.get("in", 0))
    lo_abs, hi_abs = DURATION_ABSOLUTE
    if not (lo_abs <= total <= hi_abs):
        r.rejected.append(f"duration {total:.2f}s outside absolute [{lo_abs}, {hi_abs}]")
    else:
        lo, hi = DURATION.get(genre, DURATION_ABSOLUTE)
        if not (lo <= total <= hi):
            r.warnings.append(f"duration {total:.2f}s outside {genre} window [{lo}, {hi}]")

    # ── Segments: speed discipline ─────────────────────────────────────────
    segs = e.get("segments", []) or []
    slow = [s for s in segs if float(s["speed"]) < 1.0]
    if len(slow) > 1:
        r.rejected.append(f"{len(slow)} slow-mo segments; the methodology allows exactly one")
    for s in slow:
        src_frames = _dur(s) * fps
        if src_frames > SLOWMO_MAX_SOURCE_FRAMES:
            r.rejected.append(
                f"slow-mo covers {src_frames:.0f} source frames; max {SLOWMO_MAX_SOURCE_FRAMES}"
            )
        if not (SLOWMO_SPEED_RANGE[0] <= float(s["speed"]) <= SLOWMO_SPEED_RANGE[1]):
            r.warnings.append(f"slow-mo speed {s['speed']} outside {SLOWMO_SPEED_RANGE}")

    for i, s in enumerate(segs):
        sp = float(s["speed"])
        if s.get("in_fight") and sp != 1.0:
            r.rejected.append(f"segment {i} is in_fight at {sp}x; fights run at 1.0x")
        if sp > 1.0 and not (DEAD_TIME_SPEED_RANGE[0] <= sp <= DEAD_TIME_SPEED_RANGE[1]):
            r.warnings.append(f"segment {i} speed-up {sp}x outside {DEAD_TIME_SPEED_RANGE}")
        if sp != 1.0 and "ramp_frames" not in s:
            if apply_fallbacks:
                s["ramp_frames"] = RAMP_FRAMES_DEFAULT
                r.fallbacks.append(f"segment {i}: ramp_frames defaulted to {RAMP_FRAMES_DEFAULT}")
            else:
                r.warnings.append(f"segment {i} changes speed with no ramp_frames")
        if _dur(s) <= 0:
            r.rejected.append(f"segment {i} has non-positive duration")

    # Monotonic and non-overlapping
    for i in range(1, len(segs)):
        if float(segs[i]["in"]) < float(segs[i - 1]["out"]) - 1e-6:
            r.rejected.append(f"segment {i} overlaps segment {i - 1}")

    # ── Cut density (frag only) ────────────────────────────────────────────
    if genre == "receipts":
        # The format alternates assertion and silent evidence. R1 held seven
        # stretches of 3.2-9.1s with nothing spoken. Flagging that as dead air
        # would destroy the thing that makes it work.
        spoken = (e.get("qa") or {}).get("speech_fraction")
        if spoken is not None and float(spoken) > 0.85:
            r.warnings.append(
                f"speech covers {float(spoken):.0%} — a receipts clip needs room for the evidence"
            )

    if genre == "frag":
        hard_cuts = 0
        for i in range(1, len(segs)):
            gap = float(segs[i]["in"]) - float(segs[i - 1]["out"])
            if gap > 1e-6:
                hard_cuts += 1
        if hard_cuts and total / hard_cuts < FRAG_MIN_SECONDS_BETWEEN_CUTS:
            r.rejected.append(
                f"{hard_cuts} cuts across {total:.1f}s — frag clips allow one per "
                f"{FRAG_MIN_SECONDS_BETWEEN_CUTS:.0f}s"
            )
        for i in range(1, len(segs)):
            gap = float(segs[i]["in"]) - float(segs[i - 1]["out"])
            prev_sp = float(segs[i - 1]["speed"])
            this_sp = float(segs[i]["speed"])
            covered = (
                prev_sp != 1.0
                or this_sp != 1.0
                or segs[i].get("punch", 1.0) != segs[i - 1].get("punch", 1.0)
            )
            if gap > 1e-6 and not covered:
                r.rejected.append(
                    f"bare hard cut at segment {i} — removed time must be covered by a "
                    "speed ramp or punch-in"
                )

    # ── Word-boundary alignment (take / hybrid) ────────────────────────────
    if genre in ("take", "hybrid") and word_boundaries:
        for i, s in enumerate(segs):
            for edge in ("in", "out"):
                if not _near_word_boundary(float(s[edge]), word_boundaries):
                    r.rejected.append(
                        f"segment {i} {edge}={s[edge]:.3f}s does not land on a word boundary"
                    )

    # ── Claim structure (take / hybrid) ────────────────────────────────────
    if genre in ("take", "hybrid"):
        claim = e.get("claim") or {}
        missing = [k for k in ("setup", "claim", "consequence") if not (claim.get(k) or "").strip()]
        if missing:
            r.rejected.append(f"MIN_LINES: missing {', '.join(missing)} — three lines or it is not a clip")
        if claim.get("contiguous") is False:
            r.rejected.append("claim is spliced from non-contiguous speech")

    # ── Hook ───────────────────────────────────────────────────────────────
    hook = e.get("hook") or {}
    device = hook.get("device", "none")
    if device == "flash_forward":
        if hook.get("payoff_in") is None:
            r.rejected.append("flash_forward hook has no payoff_in")
        if not hook.get("length_frames"):
            if apply_fallbacks:
                hook["length_frames"] = 30
                r.fallbacks.append("flash_forward length_frames defaulted to 30")
    if genre == "frag" and hook.get("text"):
        r.warnings.append("hook text on a pure frag clip — the play usually hooks itself")

    # ── Layout and facecam ────────────────────────────────────────────────
    if mode == "L2":
        frac = layout.get("facecam_frame_fraction")
        detected = layout.get("facecam_detected")
        pinned = bool(layout.get("facecam_source"))
        if detected is False and not pinned:
            if apply_fallbacks:
                layout["mode"] = "L1"
                mode = "L1"
                r.fallbacks.append("L2 selected but no facecam found — fell back to L1")
            else:
                r.rejected.append("L2 selected but no facecam found")
        elif frac is not None and float(frac) < FACECAM_FRAME_FRACTION_FLOOR and not pinned:
            if apply_fallbacks:
                layout["mode"] = "L1"
                mode = "L1"
                r.fallbacks.append(
                    f"facecam is {float(frac) * 100:.1f}% of frame (floor "
                    f"{FACECAM_FRAME_FRACTION_FLOOR * 100:.0f}%) — likely a UI face, fell back to L1"
                )
            else:
                r.rejected.append("facecam below size floor — likely a HUD face, not a webcam")

    if mode == "L3" and not layout.get("hud_recomposite"):
        r.warnings.append("L3 without hud_recomposite discards the killfeed")

    # ── Captions ───────────────────────────────────────────────────────────
    caps = e.get("captions") or {}
    if caps.get("enabled"):
        style = caps.get("style")
        if genre in ("take", "hybrid") and style == "word":
            # Not a defect. R2 is a take clip with one-word cards and it reads
            # fine, because the voice carries the claim and the captions carry
            # rhythm. Phrase-level is for when the written sentence is the product.
            r.warnings.append(
                "word-level captions on a take — fine when the voice carries the claim"
            )
        lo, hi = CAPTION_Y_ADVISORY.get(mode, (0.0, 1.0))
        y = caps.get("position_y")
        if y is not None and not (lo <= float(y) <= hi):
            # Advisory only. Never relocate a caption the editor placed
            # deliberately — the safe-area and killfeed checks below are the
            # ones that actually catch a bad placement.
            r.warnings.append(
                f"caption position_y {y} is unusual for {mode} (typical {lo}-{hi})"
            )

        # Safe-area intersection, in canvas pixels
        y = float(caps.get("position_y", 0.65))
        max_lines = int(caps.get("max_lines", 2))
        line_px = 92  # caption line box at 1080x1920
        top_px = y * CANVAS[1] - (max_lines * line_px) / 2
        bot_px = y * CANVAS[1] + (max_lines * line_px) / 2
        if top_px < SAFE_TOP_PX:
            r.rejected.append(f"captions reach y={top_px:.0f}px, inside the top {SAFE_TOP_PX}px exclusion")
        if bot_px > CANVAS[1] - SAFE_BOTTOM_PX:
            r.rejected.append(
                f"captions reach y={bot_px:.0f}px, inside the bottom {SAFE_BOTTOM_PX}px exclusion"
            )

        # Captions must not cover a re-composited killfeed
        for el in layout.get("hud_recomposite", []) or []:
            if el.get("element") != "killfeed":
                continue
            kf_top = float(el["dst"][1]) * CANVAS[1]
            kf_bot = kf_top + 0.22 * float(el.get("scale", 1.0)) * CANVAS[1]
            if not (bot_px < kf_top or top_px > kf_bot):
                r.rejected.append("captions overlap the re-composited killfeed")

        for c in caps.get("cards", []) or []:
            if float(c["out"]) <= float(c["in"]):
                r.rejected.append(f"caption card {c.get('text')!r} has non-positive duration")

    if e.get("source", {}).get("precaptioned") and caps.get("enabled"):
        if apply_fallbacks:
            caps["enabled"] = False
            r.fallbacks.append("source is already captioned — our captions disabled")
        else:
            r.warnings.append("source is pre-captioned and we are captioning it again")

    # ── Audio ──────────────────────────────────────────────────────────────
    audio = e.get("audio") or {}
    meas = audio.get("measured_lufs")
    if meas is not None and not (LOUDNESS_RANGE[0] <= float(meas) <= LOUDNESS_RANGE[1]):
        r.held.append(f"measured loudness {meas} LUFS outside {LOUDNESS_RANGE}")
    tp = audio.get("true_peak_dbtp")
    if tp is not None and float(tp) > TRUE_PEAK_CEILING:
        r.held.append(
            f"true peak {tp} dBTP is over full scale — this is clipping, not loudness"
        )
    if genre == "frag" and audio.get("music"):
        r.warnings.append("music bed on a frag clip — the gunfire is the rhythm")

    # ── Tail ───────────────────────────────────────────────────────────────
    tail = e.get("tail_frames")
    if tail is None:
        if apply_fallbacks:
            e["tail_frames"] = 60
            r.fallbacks.append("tail_frames defaulted to 60")
    elif not (TAIL_FRAMES[0] <= int(tail) <= TAIL_FRAMES[1]):
        r.rejected.append(f"tail_frames {tail} outside {TAIL_FRAMES}")

    # ── Speaker attribution ────────────────────────────────────────────────
    sp = e.get("speaker") or {}
    if genre in ("take", "hybrid"):
        conf = sp.get("confidence")
        if conf is None:
            r.held.append("no speaker confidence recorded")
        elif float(conf) < SPEAKER_CONFIDENCE_MIN:
            r.held.append(f"speaker confidence {conf} below {SPEAKER_CONFIDENCE_MIN}")
        voices = int(sp.get("voices_in_window", 1))
        if voices > 1 and not sp.get("narrated_intro"):
            r.held.append("more than one voice in the window — attribution is ambiguous")
        elif voices > 1:
            r.warnings.append(
                "narrator intro plus subject — keep them under separate bylines"
            )
    if sp.get("identified_by_appearance_only"):
        r.held.append("speaker identified by appearance alone")

    # ── Substance and opening frames ───────────────────────────────────────
    qa = e.get("qa") or {}
    det = e.get("detection") or {}
    has_speech = qa.get("has_speech")
    event = det.get("event", "none")
    if has_speech is False and event in ("none", None):
        r.rejected.append("no speech and no detected event — nothing happened")
    if qa.get("first_frames_black"):
        r.rejected.append("black frames in the opening 0.5s")
    if qa.get("first_frames_menu"):
        r.rejected.append("menu or loading screen in the opening 0.5s")

    r.passed = not r.rejected
    e["gates"] = r.as_dict()
    return r


def validate_schema(edit: dict[str, Any], schema_path: str | Path | None = None) -> list[str]:
    """Structural validation. Returns a list of human-readable errors."""
    import jsonschema

    schema_path = Path(schema_path or Path(__file__).parent.parent / "schema" / "edit.schema.json")
    schema = json.loads(Path(schema_path).read_text())
    v = jsonschema.Draft202012Validator(schema)
    return [f"{'/'.join(str(p) for p in err.path) or '<root>'}: {err.message}" for err in v.iter_errors(edit)]


if __name__ == "__main__":
    import sys

    for p in sys.argv[1:]:
        edit = json.loads(Path(p).read_text())
        errs = validate_schema(edit)
        if errs:
            print(f"SCHEMA INVALID  {p}")
            for e_ in errs:
                print("  ", e_)
            continue
        print(check(edit).report())
