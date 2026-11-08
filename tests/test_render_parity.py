"""The renderer parity gate must reject a renderer that got it wrong.

Resolve stays the format workbench; the native ffmpeg path is the
production line. Both run the same edit, so `engine.render_parity.compare`
is what says the two agree — and a gate that cannot fail is not a gate.
This repo has shipped that defect twice on one check alone (`chat_on_screen`
printed FAIL and reported PASS because `fatal` was left at its default, then
was never passed `chat_expected` at all), so the gate is proved against
controls BEFORE it is trusted on a real render.

Controls are built here from a delivered clip rather than kept as fixtures,
so the test is reproducible and cannot drift from the renderer:

    HONEST   a re-encode; a softer bicubic/crf26 pass
    WRONG    a 10px pane shift            (geometry)
             the seam moved 0.42 -> 0.45  (geometry)
             a mismatched facecam CDL     (grade)
             a different clip entirely    (both)

THE ORTHOGONALITY IS ITSELF ASSERTED, because it is the reason there are
two instruments. The grade failure moves the row profile by only 1.5x the
honest floor — a knife edge — and the geometry failures barely move the
white point at all. A single-instrument gate passes a real failure, and the
test says which instrument caught which control so that a later "tidy-up"
cannot quietly drop one.

Run: .venv/bin/python tests/test_render_parity.py
"""
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import render_parity as rp               # noqa: E402

FAILURES: list[str] = []
SECONDS = 10
CUT = 806          # 0.42 * 1920, the seam in output pixels


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def _enc(src, out, *, vf=None, fc=None, crf=20, flags=None, t=SECONDS):
    args = ["ffmpeg", "-v", "error", "-i", str(src), "-t", str(t)]
    if fc:
        args += ["-filter_complex", fc, "-map", "[v]", "-map", "0:a"]
    elif vf:
        args += ["-vf", vf]
    if flags:
        args += ["-sws_flags", flags]
    args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
             "-c:a", "aac", "-y", str(out)]
    subprocess.run(args, check=True, capture_output=True)
    return out


def build(src: pathlib.Path, d: pathlib.Path) -> dict:
    """Reference plus controls, all the same duration so the duration check
    is not what fails them — each control must fail for its OWN reason."""
    ref = _enc(src, d / "ref.mp4")
    return {
        "ref": ref,
        # honest: the same decisions, a different encode
        "honest_reencode": _enc(ref, d / "h_reencode.mp4", flags="lanczos"),
        "honest_softer": _enc(ref, d / "h_softer.mp4",
                              vf="scale=1080:1920:flags=bicubic", crf=26),
        # wrong, geometry
        "wrong_shift": _enc(ref, d / "w_shift.mp4",
                            vf="crop=1080:1910:0:10,scale=1080:1920"),
        "wrong_seam": _enc(ref, d / "w_seam.mp4", fc=(
            "[0:v]split=2[a][b];"
            f"[a]crop=1080:{CUT}:0:0,scale=1080:864:flags=bicubic[top];"
            f"[b]crop=1080:{1920 - CUT}:0:{CUT},scale=1080:1056:flags=bicubic[bot];"
            "[top][bot]vstack=inputs=2[v]")),
        # wrong, grade — the facecam ONLY, which is the pane that is graded
        "wrong_grade": _enc(ref, d / "w_grade.mp4", fc=(
            "[0:v]split=2[a][b];"
            f"[a]crop=1080:{CUT}:0:0,eq=gamma_r=1.18:gamma_b=0.88:saturation=1.25[top];"
            f"[b]crop=1080:{1920 - CUT}:0:{CUT}[bot];"
            "[top][bot]vstack=inputs=2[v]")),
    }


def failed(rep) -> set[str]:
    return {f.name for f in rep.findings if f.fatal and not f.ok}


def main():
    src = ROOT / "deliver" / "fns-12-stop-complaining-about-unpaid-months.mp4"
    other = ROOT / "deliver" / "fns-16-winning-teams-have-issues-too.mp4"
    if not src.exists():
        sys.exit(f"missing the clip this test is built from: {src}")

    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td)
        c = build(src, d)
        if other.exists():
            c["wrong_otherclip"] = _enc(other, d / "w_other.mp4")
        ref = c.pop("ref")

        reps = {k: rp.compare(ref, v, samples=5) for k, v in c.items()}

        print("test_honest_renders_pass")
        for k in [k for k in reps if k.startswith("honest")]:
            check(f"{k} is parity", reps[k].ok,
                  "" if reps[k].ok else f"rejected on {sorted(failed(reps[k]))}")
        print()

        print("test_every_wrong_renderer_is_rejected")
        for k in [k for k in reps if k.startswith("wrong")]:
            check(f"{k} is rejected", not reps[k].ok,
                  f"caught by {sorted(failed(reps[k]))}" if not reps[k].ok
                  else "PASSED THE GATE — the gate is useless for this case")
        print()

        print("test_the_two_instruments_are_orthogonal")
        # Each instrument must be the ONLY one catching at least one control,
        # or it is redundant and the second one is not earning its runtime.
        geo = {"geometry", "top pane", "bottom pane"}
        gra = {"grade sat", "grade white"}
        for k, want, other_set, why in (
                ("wrong_seam", geo, gra, "a moved seam is geometry"),
                ("wrong_grade", gra, geo,
                 "a mismatched CDL moves the row profile only 1.5x the "
                 "honest floor — the geometry instrument cannot see it")):
            if k not in reps:
                continue
            f = failed(reps[k])
            check(f"{k} is caught by the right instrument",
                  bool(f & want), f"caught by {sorted(f)} — {why}")
            check(f"{k} would survive the other instrument alone",
                  not (f & other_set) or bool(f & want),
                  f"{sorted(f)}")
        print()

        print("test_a_gate_finding_can_actually_fail")
        # The sibling defect: a check that runs, measures correctly, prints
        # FAIL and still reports PASS overall because it is not fatal.
        allf = [f for r in reps.values() for f in r.findings]
        check("every finding the gate emits is fatal",
              all(f.fatal for f in allf),
              f"non-fatal: {sorted({f.name for f in allf if not f.fatal})}")
        check("the gate emitted findings at all", bool(allf), f"{len(allf)}")
        print()

        print("detail — what each control was caught on")
        for k, r in reps.items():
            print(f"  {k:<18} {'PARITY ' if r.ok else 'REJECTED'} "
                  f"{sorted(failed(r)) if not r.ok else ''}")
        print()
        for k in ("honest_softer", "wrong_grade"):
            if k in reps:
                print(f"--- {k} ---")
                print(reps[k])
                print()

    if FAILURES:
        sys.exit(f"{len(FAILURES)} failed: {FAILURES}")
    print("the parity gate rejects every wrong renderer and passes the honest ones")


if __name__ == "__main__":
    print(__doc__.strip().splitlines()[0])
    print()
    main()
