"""A per-clip input a Clip may override must not be read off the Channel.

THE "UNEXPLAINED RESOLVE OFFSET" WAS THIS, AND IT WAS RECORDED AS A RESOLVE
CONVENTION FOR A WHOLE ROUND. `render_parity` reported clip 12's facecam
3.75 source px left and 1.5px wider in the Resolve render than in the native
one, with a LOW residual at a NON-ZERO shift — right crop, wrong place. Fitting
position and width against the source said the native path matched
`resolve_layout.plan()` to a quarter of a pixel, so the conclusion written down
was that Resolve departs from plan(), cause unknown, hypothesis a quantised
ZoomX.

Both renderers were correct. They had been handed DIFFERENT RECTANGLES:

    clips/fns-12.json  channel.cam  [1456, 818, 1920, 1080]   -> x0 1512.55
                       clip.cam     [1450, 816, 1920, 1080]   -> x0 1508.21
    measured           native        x0 1512.25   Resolve  x0 1508.50

`make_clip` resolves the rect through `_cam(clip, ch, st)`, which prefers the
clip's own override and otherwise runs `facecam.detect`. `render_native` read
`ch.cam` directly — so it lost the override AND the detection. This repo's
most-repeated defect is two numbers that are supposed to be the same number,
derived twice; this was that, wearing a geometry costume.

`cam` is the ONLY Channel field a Clip can currently shadow, so the rule is
clean and general: a shadowed field never reaches a geometry call off the
Channel. If the set of shadowed fields grows, the first test here fails and
says so, rather than silently covering one field out of two.

Run: .venv/bin/python tests/test_native_inputs.py
"""
import ast
import dataclasses as dc
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.clipspec import Channel, Clip                    # noqa: E402

FAILURES: list[str] = []
# Every helper that consumes the facecam rect to build geometry.
GEOMETRY = {"two_pane", "panes", "plan", "split_l2", "framings",
            "resolve_delta", "visible"}


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def _fn(tree, name):
    return next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == name)


def _calls(node, names):
    """Every Call in `node` whose callee's last name part is in `names`."""
    for n in ast.walk(node):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        who = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
        if who in names:
            yield who, n


def _reads_channel(node, field):
    """True if this expression reads `<something>.field` off a channel-ish
    name. Catches `ch.cam`, `tuple(ch.cam)` and `channel.cam` alike."""
    for n in ast.walk(node):
        if (isinstance(n, ast.Attribute) and n.attr == field
                and getattr(n.value, "id", "") in ("ch", "channel", "chan")):
            return True
    return False


SHADOWED = sorted({f.name for f in dc.fields(Channel)}
                  & {f.name for f in dc.fields(Clip)})


def test_the_shadowed_set_is_what_this_file_covers():
    """A new overridable field must not inherit this test's silence."""
    check("the only Channel field a Clip shadows is `cam`", SHADOWED == ["cam"],
          f"shadowed={SHADOWED} — extend this file to cover the rest")


def test_render_native_resolves_the_cam_through_make_clip():
    """`_cam` is the single implementation, and it is also where
    `facecam.detect` lives. Reading the spec field directly skips both."""
    tree = ast.parse((ROOT / "engine" / "render_native.py").read_text())
    called = {w for w, _ in _calls(_fn(tree, "plan"), {"_cam"})}
    check("render_native.plan calls make_clip._cam", called == {"_cam"},
          "without it the clip's own rect and facecam.detect are both lost")
    body = _fn(tree, "plan")
    returns = [n for n in ast.walk(body) if isinstance(n, ast.Return)]
    keys = {k.value for r in returns for d in ast.walk(r)
            if isinstance(d, ast.Dict)
            for k in d.keys if isinstance(k, ast.Constant)}
    check("plan() returns the rect it resolved", "cam" in keys, f"{sorted(keys)}")


def test_no_geometry_call_takes_a_shadowed_field_off_the_channel():
    """The precise defect: `nl.two_pane(ch, segs, cam=tuple(ch.cam), ...)`.
    Checked on the arguments of the geometry calls themselves, so an ordinary
    log line comparing the two rects is not a false positive."""
    for mod in ("engine/render_native.py", "make_clip.py"):
        tree = ast.parse((ROOT / mod).read_text())
        bad = []
        for who, call in _calls(tree, GEOMETRY):
            for arg in list(call.args) + [k.value for k in call.keywords]:
                for field in SHADOWED:
                    if _reads_channel(arg, field):
                        bad.append(f"{who}(... ch.{field} ...)")
        check(f"{mod} passes no `ch.<override>` into a geometry call",
              not bad, "; ".join(sorted(set(bad))))


def test_the_two_rects_really_do_differ_on_a_real_spec():
    """A structural test proves the wiring, not that the wiring MATTERS. At
    least one spec on disk must override the channel, or this whole file is
    guarding a difference that never arises."""
    import json
    diff = []
    for f in sorted((ROOT / "clips").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        a, b = d.get("channel", {}).get("cam"), d.get("clip", {}).get("cam")
        if b and tuple(a or ()) != tuple(b):
            diff.append(f"{f.stem}: {tuple(b)} vs channel {tuple(a)}")
    check("a real spec overrides the channel's cam", bool(diff),
          f"{len(diff)} of them, e.g. {diff[0] if diff else ''}")


def _x0(cam):
    """Visible source x0 of the facecam pane under `plan()`, fill=True."""
    from engine import resolve_layout as rl
    f = rl.Frame(1080, 1920, 1920, 1080)
    p = rl.plan(f, tuple(cam), (0, 0, 1080, 0.42 * 1920))
    vis = 1080 / (f.fit * p["ZoomX"])
    return (cam[0] + cam[2]) / 2 - vis / 2, vis


def test_the_difference_exceeds_the_gates_tolerance():
    """3.75 source px is ~1% of the visible width and DID fail the geometry
    check. The gate was right; the renderer was wrong. Pinned so nobody is
    ever tempted to widen `OFFSET_PX` to make this disappear."""
    from engine import render_parity as rp
    a, wa = _x0((1456, 818, 1920, 1080))         # channel default
    b, wb = _x0((1450, 816, 1920, 1080))         # clip 12's override
    src_px = abs(a - b)
    canvas_px = src_px * 1080 / wa               # what the gate measures in
    check("the two rects differ by more than one source pixel", src_px > 1.0,
          f"{src_px:.2f} src px, width {wa:.1f} vs {wb:.1f}")
    check("and by more than the gate's OFFSET_PX, so it must fail",
          canvas_px > rp.OFFSET_PX,
          f"{canvas_px:.1f} canvas px against OFFSET_PX {rp.OFFSET_PX}")


if __name__ == "__main__":
    print(__doc__.strip().splitlines()[0])
    print()
    for fn in (test_the_shadowed_set_is_what_this_file_covers,
               test_render_native_resolves_the_cam_through_make_clip,
               test_no_geometry_call_takes_a_shadowed_field_off_the_channel,
               test_the_two_rects_really_do_differ_on_a_real_spec,
               test_the_difference_exceeds_the_gates_tolerance):
        print(fn.__name__)
        fn()
        print()
    if FAILURES:
        sys.exit(f"{len(FAILURES)} failed: {FAILURES}")
    print("every per-clip input comes from one place")
