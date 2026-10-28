"""Backend B: emit an FCPXML timeline from an edit.json.

Why this exists: DaVinci Resolve imports FCPXML natively, in the FREE edition,
with no Python scripting API and no MCP server. Building the timeline this way
sidesteps the Studio paywall entirely. The scripting API is then only needed to
automate renders and grades, not to construct an edit.

Times are exact rationals in the source frame rate — never decimal seconds —
because a timeline that is a frame out on every cut is worse than no timeline.

UNVALIDATED against a live Resolve install. Import it, eyeball the first
timeline, and adjust before trusting it on client work.
"""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.dom import minidom

FCPXML_VERSION = "1.9"


def _rt(seconds: float, fps: float) -> str:
    """Rational time string, snapped to the frame grid."""
    den = int(round(fps))
    num = int(round(float(seconds) * den))
    f = Fraction(num, den)
    return f"{f.numerator}/{f.denominator}s" if f.denominator != 1 else f"{f.numerator}s"


def _frame_duration(fps: float) -> str:
    den = int(round(fps))
    return f"1/{den}s"


def _segment_plan(edit: dict) -> list[dict]:
    """Same expansion the ffmpeg backend uses, but ramps stay as real ramps
    here — Resolve does them natively via a timeMap, so no staircase."""
    return [
        {"in": float(s["in"]), "out": float(s["out"]),
         "speed": float(s["speed"]), "ramp_frames": int(s.get("ramp_frames") or 0)}
        for s in edit["segments"]
    ]


def build(edit: dict, *, project_name: str | None = None) -> str:
    src = edit["source"]
    fps = float(src["fps"])
    W = int(edit["render"]["width"])
    H = int(edit["render"]["height"])
    sw, sh = (src.get("resolution") or [1920, 1080])
    name = project_name or edit["clip_id"]

    root = ET.Element("fcpxml", version=FCPXML_VERSION)
    res = ET.SubElement(root, "resources")

    ET.SubElement(res, "format", {
        "id": "r1", "name": f"FFVideoFormat{sh}p{int(fps)}",
        "frameDuration": _frame_duration(fps),
        "width": str(sw), "height": str(sh), "colorSpace": "1-1-1 (Rec. 709)",
    })
    ET.SubElement(res, "format", {
        "id": "r2", "name": f"ClipEngineVertical{H}p{int(fps)}",
        "frameDuration": _frame_duration(fps),
        "width": str(W), "height": str(H), "colorSpace": "1-1-1 (Rec. 709)",
    })

    src_path = Path(src["path"]).resolve()
    total_src = max(float(s["out"]) for s in edit["segments"]) + 5.0
    asset = ET.SubElement(res, "asset", {
        "id": "a1", "name": src_path.stem, "start": "0s",
        "duration": _rt(total_src, fps), "hasVideo": "1", "hasAudio": "1",
        "audioSources": "1", "audioChannels": "2", "format": "r1",
    })
    ET.SubElement(asset, "media-rep", {
        "kind": "original-media", "src": src_path.as_uri(),
    })

    lib = ET.SubElement(root, "library")
    event = ET.SubElement(lib, "event", name="clip-engine")
    project = ET.SubElement(event, "project", name=name)

    plan = _segment_plan(edit)
    out_total = sum((p["out"] - p["in"]) / p["speed"] for p in plan)
    seq = ET.SubElement(project, "sequence", {
        "format": "r2", "duration": _rt(out_total, fps),
        "tcStart": "0s", "tcFormat": "NDF",
        "audioLayout": "stereo", "audioRate": "48k",
    })
    spine = ET.SubElement(seq, "spine")

    offset = 0.0
    for i, p in enumerate(plan):
        src_dur = p["out"] - p["in"]
        out_dur = src_dur / p["speed"]
        clip = ET.SubElement(spine, "asset-clip", {
            "ref": "a1", "name": f"{name}-{i:02d}",
            "offset": _rt(offset, fps),
            "start": _rt(p["in"], fps),
            "duration": _rt(out_dur, fps),
            "format": "r1", "tcFormat": "NDF",
        })

        if p["speed"] != 1.0:
            tm = ET.SubElement(clip, "timeMap")
            ramp_s = min(p["ramp_frames"] / fps, src_dur / 3.0) if p["ramp_frames"] else 0.0
            if ramp_s <= 0:
                ET.SubElement(tm, "timept", {
                    "time": "0s", "value": _rt(p["in"], fps), "interp": "linear"})
                ET.SubElement(tm, "timept", {
                    "time": _rt(out_dur, fps), "value": _rt(p["out"], fps), "interp": "linear"})
            else:
                # A real ease: smooth in, hold the target speed, smooth out.
                body_src = src_dur - 2 * ramp_s
                body_out = body_src / p["speed"]
                pts = [
                    (0.0, p["in"], "smooth"),
                    (ramp_s, p["in"] + ramp_s * (1 + p["speed"]) / 2, "smooth"),
                    (ramp_s + body_out, p["out"] - ramp_s, "smooth"),
                    (out_dur, p["out"], "smooth"),
                ]
                for (t_out, t_src, interp) in pts:
                    ET.SubElement(tm, "timept", {
                        "time": _rt(t_out, fps), "value": _rt(t_src, fps), "interp": interp})

        offset += out_dur

    # Captions as titles on a connected lane, so an editor can restyle them.
    caps = edit.get("captions") or {}
    if caps.get("enabled") and caps.get("cards"):
        for n, c in enumerate(caps["cards"]):
            o_in = _source_to_output(plan, float(c["in"]))
            o_out = _source_to_output(plan, float(c["out"]))
            if o_in is None or o_out is None or o_out <= o_in:
                continue
            t = ET.SubElement(spine, "title", {
                "name": f"caption-{n:03d}", "lane": "1",
                "offset": _rt(o_in, fps), "duration": _rt(o_out - o_in, fps),
                "start": "0s",
            })
            txt = ET.SubElement(t, "text")
            ET.SubElement(txt, "text-style", {"ref": "ts1"}).text = c["text"]

    xml = ET.tostring(root, encoding="unicode")
    pretty = minidom.parseString(xml).toprettyxml(indent="  ")
    body = pretty.split("\n", 1)[1]
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<!DOCTYPE fcpxml>\n" + body
    )


def _source_to_output(plan: list[dict], t_src: float) -> float | None:
    off = 0.0
    for p in plan:
        if p["in"] - 1e-6 <= t_src <= p["out"] + 1e-6:
            return off + (t_src - p["in"]) / p["speed"]
        off += (p["out"] - p["in"]) / p["speed"]
    return None


def write(edit: dict, out_path: str | Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(build(edit))
    return out_path


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="emit an FCPXML timeline for Resolve")
    ap.add_argument("edit_json")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    edit = json.loads(Path(a.edit_json).read_text())
    p = write(edit, a.out)
    print(f"wrote {p}")
    print("Resolve: File > Import > Timeline..., pick this file.")
