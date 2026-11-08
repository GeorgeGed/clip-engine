"""Backend C: drive DaVinci Resolve directly through its scripting API.

Division of labour, and it matters:

  * Timeline CONSTRUCTION goes through engine/fcpxml.py. That works in Resolve
    Free and needs none of this.
  * This module is for what only Resolve can do: importing that timeline,
    applying a grade or a LUT, and running a real render queue.

Requires Resolve STUDIO. Blackmagic moved the Python API behind the paid
edition in 21.1 (their release notes say the free API was being used to unlock
Studio features), and external control was always Studio-only.

Run `python -m engine.resolve_driver doctor` first. It tells you exactly what
is missing instead of failing with an import error.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAC_API = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
MAC_LIB = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"
MAC_APP = "/Applications/DaVinci Resolve/DaVinci Resolve.app"


@dataclass
class Diagnosis:
    app_installed: bool
    api_present: bool
    lib_present: bool
    module_importable: bool
    resolve_running: bool
    studio: bool | None
    notes: list[str]

    def ok(self) -> bool:
        return self.module_importable and self.resolve_running

    def report(self) -> str:
        def mark(b):
            return "yes" if b else ("unknown" if b is None else "NO ")

        lines = [
            f"  Resolve app installed      {mark(self.app_installed)}",
            f"  Scripting API folder       {mark(self.api_present)}",
            f"  fusionscript library       {mark(self.lib_present)}",
            f"  DaVinciResolveScript       {mark(self.module_importable)}",
            f"  Resolve running            {mark(self.resolve_running)}",
            f"  Studio edition             {mark(self.studio)}",
        ]
        return "\n".join(lines + ["", *(f"  - {n}" for n in self.notes)])


def _env() -> None:
    os.environ.setdefault("RESOLVE_SCRIPT_API", MAC_API)
    os.environ.setdefault("RESOLVE_SCRIPT_LIB", MAC_LIB)
    mod = str(Path(MAC_API) / "Modules")
    if mod not in sys.path:
        sys.path.append(mod)


def doctor() -> Diagnosis:
    _env()
    notes: list[str] = []
    app = Path(MAC_APP).exists()
    api = Path(MAC_API).exists()
    lib = Path(MAC_LIB).exists()

    importable = False
    running = False
    studio: bool | None = None
    try:
        import DaVinciResolveScript as dvr  # type: ignore

        importable = True
        r = dvr.scriptapp("Resolve")
        if r is not None:
            running = True
            try:
                studio = "Studio" in (r.GetProductName() or "")
            except Exception:
                studio = None
        else:
            notes.append("Module imported but Resolve is not running, or external "
                         "scripting is off (Preferences > System > General > "
                         "External scripting using: Local).")
    except Exception as e:
        notes.append(f"Cannot import DaVinciResolveScript: {e}")

    if not app:
        notes.append(f"DaVinci Resolve is not installed at {MAC_APP}.")
    if app and not api:
        notes.append("Scripting API folder missing — this usually means the FREE "
                     "edition. Python scripting is Studio-only since 21.1.")
    if studio is False:
        notes.append("This is the free edition. Timeline construction still works "
                     "via FCPXML import (engine/fcpxml.py); rendering and grading "
                     "from here do not.")
    # A DIALOG IS WORSE THAN A CLOSED APP, because the app looks fine. Only
    # worth asking when Resolve is up: with nothing running there are no
    # windows and the question is meaningless.
    if running:
        dlg = blocking_dialog()
        if dlg:
            notes.append(
                f"Resolve has a modal window open — {dlg!r} — and it is "
                f"waiting on a human. The scripting API answers with None "
                f"while it is up, so a render will hang rather than fail. "
                f"Dismiss it in Resolve and retry.")
    if not notes:
        notes.append("Ready.")
    return Diagnosis(app, api, lib, importable, running, studio, notes)


# WHAT COUNTS AS BLOCKING, and why this is a pattern list rather than
# "anything that is not the main window".
#
# The first version flagged any window other than "DaVinci Resolve", and the
# very first thing it caught was **"Project Manager"** — which is Resolve's
# ordinary startup window, not a modal, and which `make_clip` resolves by
# creating or loading its own project. Treating it as blocking would have
# made `doctor()` report "not ready" and the site refuse to build at all.
#
# A false POSITIVE here stops work; a false NEGATIVE only costs the render
# wait its (now bounded) timeout, which fails with a readable message. So
# the asymmetry says be conservative: name the dialogs that are known to
# block, and let the list grow as they are met.
_BLOCKING_PATTERNS = (
    "problem report",      # Blackmagic's own crash reporter — today's culprit
    "crash",
    "error",
    "warning",
    "alert",
    "already exists",      # the overwrite prompt this file has warned about
    "unsaved",
)


def blocking_dialog(timeout: float = 5.0) -> str:
    """The title of a modal window waiting on a human, or "".

    THIS FILE ALREADY RECORDED THE SYMPTOM AND NOTHING EVER CHECKED FOR IT.
    AGENTS.md: *"Resolve wedged again, this time at 3% CPU with the API
    blocked — not a busy loop, so most likely a modal dialog."* It was a
    modal dialog, and today it was **Blackmagic's own crash reporter** —
    "Problem Report for DaVinci Resolve", with Don't Ask Again / Ignore /
    Send. Three builds died on it:

      * API methods resolve to None, so `proj.StartRendering` raises
        `TypeError: 'NoneType' object is not callable` — which reads exactly
        like the `hasattr` lie this file warns about and is nothing of the
        kind;
      * `IsRenderingInProgress()` never returns False, so the render wait
        loop span forever with make_clip alive and Resolve at 0.0% CPU;
      * nothing reported any of it. One build sat for fifty minutes.

    There is no crash report in DiagnosticReports for it, because the dialog
    is Blackmagic's and not Apple's — so looking there says "no crash" while
    a crash dialog is on screen.

    System Events needs Accessibility permission. Without it this returns ""
    rather than raising: a diagnostic that refuses to run must not become the
    reason a build fails.
    """
    import subprocess                                      # noqa: PLC0415
    try:
        r = subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to tell process "Resolve" '
             'to get name of every window'],
            capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return ""
    if r.returncode != 0:
        return ""
    for w in (w.strip() for w in (r.stdout or "").split(",")):
        low = w.lower()
        if w and any(pat in low for pat in _BLOCKING_PATTERNS):
            return w
    return ""


def connect():
    _env()
    import DaVinciResolveScript as dvr  # type: ignore

    resolve = dvr.scriptapp("Resolve")
    if resolve is None:
        raise RuntimeError(
            "Resolve is not reachable. Open DaVinci Resolve, then set "
            "Preferences > System > General > 'External scripting using' to Local."
        )
    return resolve


def import_timeline(fcpxml_path: str | Path, *, project_name: str) -> dict:
    """Import an FCPXML timeline into a (new or existing) project."""
    resolve = connect()
    pm = resolve.GetProjectManager()
    project = pm.LoadProject(project_name) or pm.CreateProject(project_name)
    if project is None:
        raise RuntimeError(f"could not open or create project {project_name!r}")
    mp = project.GetMediaPool()
    ok = mp.ImportTimelineFromFile(str(Path(fcpxml_path).resolve()))
    if not ok:
        raise RuntimeError("Resolve refused the FCPXML import")
    tl = project.GetCurrentTimeline()
    return {
        "project": project.GetName(),
        "timeline": tl.GetName() if tl else None,
        "clips": tl.GetItemListInTrack("video", 1).__len__() if tl else 0,
    }


def build_timeline(edit: dict, *, project_name: str | None = None) -> dict:
    """Construct the timeline through the API instead of FCPXML.

    Only worth using when you are already in Studio and want the speed changes
    applied as Resolve retimes rather than imported.
    """
    resolve = connect()
    name = project_name or edit["clip_id"]
    pm = resolve.GetProjectManager()
    project = pm.CreateProject(name) or pm.LoadProject(name)
    mp = project.GetMediaPool()

    items = mp.ImportMedia([str(Path(edit["source"]["path"]).resolve())])
    if not items:
        raise RuntimeError("Resolve could not import the source media")
    item = items[0]

    fps = float(edit["source"]["fps"])
    tl = mp.CreateEmptyTimeline(name)
    if tl is None:
        raise RuntimeError("could not create a timeline")

    appended = []
    for s in edit["segments"]:
        appended.append({
            "mediaPoolItem": item,
            "startFrame": int(round(float(s["in"]) * fps)),
            "endFrame": int(round(float(s["out"]) * fps)) - 1,
        })
    mp.AppendToTimeline(appended)

    # Apply speed per clip.
    track = tl.GetItemListInTrack("video", 1) or []
    for ti, s in zip(track, edit["segments"]):
        speed = float(s["speed"])
        if speed != 1.0:
            try:
                ti.SetProperty("Speed", speed)
            except Exception:
                pass
    return {"project": project.GetName(), "timeline": tl.GetName(), "clips": len(track)}


def render(
    *, out_dir: str | Path, preset: str = "H.264 Master",
    project_name: str | None = None, filename: str | None = None,
) -> dict:
    """Queue and run a render. Blocks until the job finishes."""
    import time

    resolve = connect()
    pm = resolve.GetProjectManager()
    project = pm.LoadProject(project_name) if project_name else pm.GetCurrentProject()
    if project is None:
        raise RuntimeError("no project open")

    if preset not in (project.GetRenderPresetList() or []):
        raise RuntimeError(f"render preset {preset!r} not found in this project")
    project.LoadRenderPreset(preset)
    project.SetRenderSettings({
        "TargetDir": str(Path(out_dir).resolve()),
        "CustomName": filename or project.GetName(),
    })
    job = project.AddRenderJob()
    project.StartRendering([job])
    while project.IsRenderingInProgress():
        time.sleep(1.0)
    status = project.GetRenderJobStatus(job) or {}
    return {"job": job, "status": status}


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="drive DaVinci Resolve")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")

    s1 = sub.add_parser("import")
    s1.add_argument("fcpxml")
    s1.add_argument("--project", required=True)

    s2 = sub.add_parser("build")
    s2.add_argument("edit_json")
    s2.add_argument("--project")

    s3 = sub.add_parser("render")
    s3.add_argument("--out-dir", required=True)
    s3.add_argument("--preset", default="H.264 Master")
    s3.add_argument("--project")
    s3.add_argument("--filename")

    a = ap.parse_args()
    if a.cmd == "doctor":
        d = doctor()
        print("DaVinci Resolve setup\n")
        print(d.report())
        raise SystemExit(0 if d.ok() else 1)
    if a.cmd == "import":
        print(json.dumps(import_timeline(a.fcpxml, project_name=a.project), indent=2))
    elif a.cmd == "build":
        edit = json.loads(Path(a.edit_json).read_text())
        print(json.dumps(build_timeline(edit, project_name=a.project), indent=2))
    elif a.cmd == "render":
        print(json.dumps(render(out_dir=a.out_dir, preset=a.preset,
                                project_name=a.project, filename=a.filename), indent=2))
