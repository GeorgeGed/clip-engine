#!/usr/bin/env python3
"""Clip Engine orchestrator.

    ./run.py ingest   <url|path> --job <name> [--start S --end S]
    ./run.py analyse  --job <name> [--skip-transcribe] [--skip-killfeed]
    ./run.py rank     --job <name>
    ./run.py gate     --job <name> --edit <edit.json>
    ./run.py render   --job <name> --edit <edit.json> [--backend ffmpeg|fcpxml]

A job is a directory under jobs/ holding the source, the detector output, the
candidates, every edit.json and every deliverable. Nothing is thrown away, so
any clip can be re-rendered when the style changes.

Deciding the edit is NOT in here. That is Claude's job, under AGENTS.md, and it
produces an edit.json that `gate` and `render` consume.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
JOBS = ROOT / "jobs"
VENV_PY = ROOT / ".venv" / "bin" / "python"

# Re-exec under the project venv so `./run.py` works from any shell. The engine
# needs opencv, jsonschema and faster-whisper, which the system python has not got.
if VENV_PY.exists() and Path(sys.executable).resolve() != VENV_PY.resolve():
    import os

    os.execv(str(VENV_PY), [str(VENV_PY), str(Path(__file__).resolve()), *sys.argv[1:]])


def _py() -> str:
    return str(VENV_PY) if VENV_PY.exists() else sys.executable


def job_dir(name: str) -> Path:
    d = JOBS / name
    d.mkdir(parents=True, exist_ok=True)
    for sub in ("media", "detect", "edits", "out", "calib"):
        (d / sub).mkdir(exist_ok=True)
    return d


def cmd_ingest(a) -> None:
    sys.path.insert(0, str(ROOT))
    from engine import ingest

    d = job_dir(a.job)
    src = ingest.fetch(a.url_or_path, d / "media", start=a.start, end=a.end, owner=a.owner)
    qa = ingest.opening_frames_qa(src.path)
    loud = ingest.measure_loudness(src.path)
    wav = ingest.extract_audio(src.path, d / "media" / "audio.wav")

    manifest = {
        "job": a.job,
        "created": date.today().isoformat(),
        "source": src.as_dict(),
        "audio_wav": str(wav),
        "source_qa": qa,
        "source_loudness": loud,
        "rights_basis": a.rights or "UNSET — set this before any render",
    }
    (d / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))
    if not a.rights:
        print("\n!! rights_basis is UNSET. The gate will reject every edit until it is set.")


def cmd_analyse(a) -> None:
    sys.path.insert(0, str(ROOT))
    d = job_dir(a.job)
    man = json.loads((d / "manifest.json").read_text())
    src_path = man["source"]["path"]
    offset = float(man["source"].get("window_offset") or 0.0)

    # Separate processes on purpose: faster-whisper ships PyAV ffmpeg dylibs
    # that collide with opencv's inside one interpreter.
    if not a.skip_transcribe:
        print("[1/2] transcribing (word timestamps)...")
        subprocess.run([_py(), str(ROOT / "engine" / "transcribe.py"), man["audio_wav"],
                        "-o", str(d / "detect" / "transcript.json"),
                        "--model", a.model, "--offset", str(offset)], check=True, cwd=ROOT)

    print("[2/2] audio reaction spikes...")
    subprocess.run([_py(), str(ROOT / "engine" / "detect_audio.py"), man["audio_wav"],
                    "-o", str(d / "detect" / "audio.json"), "--offset", str(offset)],
                   check=True, cwd=ROOT)

    if not a.skip_killfeed:
        print("[+] killfeed scan (calibrate first if this is a new stream layout)...")
        subprocess.run([_py(), str(ROOT / "engine" / "detect_killfeed.py"), "scan", src_path,
                        "-o", str(d / "detect" / "killfeed.json"), "--offset", str(offset)],
                       check=True, cwd=ROOT)


def cmd_calibrate(a) -> None:
    d = job_dir(a.job)
    man = json.loads((d / "manifest.json").read_text())
    subprocess.run([_py(), str(ROOT / "engine" / "detect_killfeed.py"), "calibrate",
                    man["source"]["path"], "-o", str(d / "calib")], check=True, cwd=ROOT)
    print(f"\nLook at {d / 'calib'}: *_roi.png must BE the killfeed, and *_rows.png "
          f"must box each own-kill row in green. If not, edit config/killfeed.yaml.")


def cmd_rank(a) -> None:
    sys.path.insert(0, str(ROOT))
    from engine import candidates as C

    d = job_dir(a.job)
    man = json.loads((d / "manifest.json").read_text())
    kf_p = d / "detect" / "killfeed.json"
    au_p = d / "detect" / "audio.json"

    cands: list[C.Candidate] = []
    if kf_p.exists():
        cands += C.from_rounds(
            json.loads(kf_p.read_text()),
            audio=json.loads(au_p.read_text()) if au_p.exists() else None,
            owner=man["source"]["owner"],
            date=man["created"],
        )
    cands = C.mark_redundant(cands)
    out = d / "detect" / "candidates.json"
    out.write_text(json.dumps([c.as_dict() for c in cands], indent=2))

    print(f"{len(cands)} candidates -> {out}\n")
    for c in cands[:20]:
        print(f"  {c.score:.3f}  {c.event:<6} {c.t_in:8.2f}-{c.t_out:8.2f} "
              f"({c.duration:5.1f}s)  {c.candidate_id}")


def cmd_gate(a) -> None:
    sys.path.insert(0, str(ROOT))
    from engine import gates

    edit = json.loads(Path(a.edit).read_text())
    errs = gates.validate_schema(edit)
    if errs:
        print("SCHEMA INVALID")
        for e in errs:
            print("  ", e)
        raise SystemExit(1)

    wb = None
    tr_p = job_dir(a.job) / "detect" / "transcript.json"
    if tr_p.exists():
        from engine.transcribe import word_boundaries

        wb = word_boundaries(json.loads(tr_p.read_text()))

    res = gates.check(edit, word_boundaries=wb)
    print(res.report())
    if res.fallbacks:
        Path(a.edit).write_text(json.dumps(res.edit, indent=2))
        print(f"\n  (corrected edit written back to {a.edit})")
    raise SystemExit(0 if res.passed else 1)


def cmd_render(a) -> None:
    sys.path.insert(0, str(ROOT))
    from engine import gates

    d = job_dir(a.job)
    edit = json.loads(Path(a.edit).read_text())
    errs = gates.validate_schema(edit)
    if errs:
        raise SystemExit("schema invalid:\n  " + "\n  ".join(errs))

    wb = None
    tr_p = d / "detect" / "transcript.json"
    if tr_p.exists():
        from engine.transcribe import word_boundaries

        wb = word_boundaries(json.loads(tr_p.read_text()))
    res = gates.check(edit, word_boundaries=wb)
    print(res.report())
    if not res.passed:
        raise SystemExit("\ngates rejected this edit; nothing rendered")
    edit = res.edit

    backend = a.backend or edit["render"].get("backend", "ffmpeg")
    if backend == "fcpxml":
        from engine import fcpxml

        p = fcpxml.write(edit, d / "out" / f"{edit['clip_id']}.fcpxml")
        print(f"\nwrote {p}\nResolve: File > Import > Timeline...")
        return

    from engine import render_ffmpeg

    out = d / "out" / f"{edit['clip_id']}.mp4"
    info = render_ffmpeg.render(edit, out)
    print("\n" + json.dumps(info, indent=2))

    lufs = info.get("measured_lufs")
    if lufs is not None and not (-16.0 <= lufs <= -12.0):
        print(f"\n!! delivered loudness {lufs} LUFS is outside the -16..-12 window")


def main() -> None:
    ap = argparse.ArgumentParser(description="Clip Engine")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ingest"); p.set_defaults(fn=cmd_ingest)
    p.add_argument("url_or_path"); p.add_argument("--job", required=True)
    p.add_argument("--start", type=float); p.add_argument("--end", type=float)
    p.add_argument("--owner"); p.add_argument("--rights",
                   choices=["explicit", "affiliate", "client_owned"])

    p = sub.add_parser("analyse"); p.set_defaults(fn=cmd_analyse)
    p.add_argument("--job", required=True); p.add_argument("--model", default="large-v3")
    p.add_argument("--skip-transcribe", action="store_true")
    p.add_argument("--skip-killfeed", action="store_true")

    p = sub.add_parser("calibrate"); p.set_defaults(fn=cmd_calibrate)
    p.add_argument("--job", required=True)

    p = sub.add_parser("rank"); p.set_defaults(fn=cmd_rank)
    p.add_argument("--job", required=True)

    p = sub.add_parser("gate"); p.set_defaults(fn=cmd_gate)
    p.add_argument("--job", required=True); p.add_argument("--edit", required=True)

    p = sub.add_parser("render"); p.set_defaults(fn=cmd_render)
    p.add_argument("--job", required=True); p.add_argument("--edit", required=True)
    p.add_argument("--backend", choices=["ffmpeg", "fcpxml"])

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
