"""The gate that decides delivery must ask what the build's own QC asks.

CLIP 08 SHIPPED HAVING FAILED ITS OWN GATE. Its build log reads, in order:

    FAIL  fns-2905408276-08.mp4
       FAIL chat_on_screen   NOT VISIBLE — panel fill 17% (want >=50%)
    PASS  fns-2905408276-08.mp4
    [fns-08] -> deliver/fns-08-valorant-s-job-security-problem.mp4

Two QC passes over one file, disagreeing. `make_clip` runs
`deliver_qc.check(..., chat_expected=bool(st["chat_windows"]))`; `batch._qc_for`
did not pass `chat_expected` at all, and `deliver_qc` SKIPS the check when it
is None. So the finding was never produced in the only report whose `.ok`
decides whether a clip is copied into `deliver/`. Making it fatal changed
nothing.

This is the repo's most-repeated defect — two numbers that are supposed to be
the same number, derived twice — and it is the SECOND time it has landed on
this one check, after the first version left `fatal` at its default and
printed FAIL while reporting PASS overall.

The guard is structural rather than behavioural: compare the keyword
arguments the two call sites pass. A behavioural test would need a rendered
clip, which is minutes of Resolve; this catches the divergence in
milliseconds and fails for the right reason.

Run: .venv/bin/python tests/test_gate_parity.py
"""
import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
FAILURES: list[str] = []


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def _check_kwargs(path: pathlib.Path) -> set[str]:
    """Keyword names passed to any `deliver_qc.check(...)` in this file."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        name = (f.attr if isinstance(f, ast.Attribute) else
                getattr(f, "id", ""))
        if name != "check":
            continue
        mod = getattr(getattr(f, "value", None), "id", "")
        if isinstance(f, ast.Attribute) and mod not in ("deliver_qc", "dqc"):
            continue
        out |= {k.arg for k in n.keywords if k.arg}
    return out


def test_both_call_sites_pass_the_same_signals():
    build = _check_kwargs(ROOT / "make_clip.py")
    gate = _check_kwargs(ROOT / "batch.py")
    check("make_clip calls deliver_qc.check", bool(build), f"{sorted(build)}")
    check("batch calls deliver_qc.check", bool(gate), f"{sorted(gate)}")
    # Anything the build asks about and the delivery gate does not is a
    # finding that can be printed and then ignored.
    missing = sorted(build - gate)
    check("the delivery gate asks everything the build's QC asks",
          not missing,
          f"batch.py never passes {missing}" if missing else "")


def test_chat_expected_specifically():
    """Named on its own because it is the one that shipped a bad clip, and
    because `deliver_qc` treats None as 'skip' rather than 'assume'."""
    gate = _check_kwargs(ROOT / "batch.py")
    check("the delivery gate passes chat_expected", "chat_expected" in gate,
          "without it deliver_qc skips chat_on_screen entirely")


def test_a_none_chat_expected_skips_rather_than_passes():
    """The skip is deliberate — a clip with chat genuinely off must not fail
    — so the danger is passing None by accident, which is what happened.
    This pins the semantics so a later change cannot quietly invert them."""
    src = (ROOT / "engine" / "deliver_qc.py").read_text(encoding="utf-8")
    check("deliver_qc guards the chat check on `is not None`",
          "if chat_expected is not None:" in src,
          "so None means SKIP, which is why passing nothing was invisible")


def test_the_fatal_flag_is_still_set():
    """The first version of this check printed FAIL and reported PASS because
    `fatal` was left at its default. Both halves have to hold at once."""
    src = (ROOT / "engine" / "deliver_qc.py").read_text(encoding="utf-8")
    i = src.find("chat_on_screen")
    check("chat_on_screen is declared fatal", i != -1 and "fatal=True" in src[i:i + 600],
          "a check that cannot fail the artifact is not a gate")


def test_a_reused_report_is_keyed_to_the_file():
    """THE GATE NOW RUNS ONCE AND IS READ TWICE, so a stale record must not
    read as a pass.

    `make_clip._gate` writes its report to `overlays_NN/qc.json` and
    `batch._recorded_qc` reads it back instead of re-measuring the same mp4
    and re-deriving the cut — about 11s a clip, measured. That is only safe
    because the record names the file: its path, its size and its mtime. A
    reuse keyed on nothing but existence would be the same defect as
    `-v error` silencing `volumedetect` — a check that measures nothing and
    reports a pass.
    """
    import json
    import tempfile
    sys.path.insert(0, str(ROOT))
    import batch

    src = ROOT / "make_clip.py"
    txt = src.read_text(encoding="utf-8")
    i = txt.find('"qc.json"')
    for key in ('"mp4"', '"mtime"', '"size"', '"ok"'):
        check(f"the recorded report carries {key}", key in txt[i - 400:i + 700],
              "without it a stale record cannot be told from a fresh one")

    bt = (ROOT / "batch.py").read_text(encoding="utf-8")
    j = bt.find("def _recorded_qc")
    body = bt[j:j + 1800]
    for want in ("st_size", "st_mtime", "resolve()"):
        check(f"the reuse compares {want}", want in body)

    # and it actually refuses a record that does not match the file
    d = pathlib.Path(tempfile.mkdtemp())
    mp4 = d / "x.mp4"
    mp4.write_bytes(b"x" * 10)
    ov = d / "overlays_99"
    ov.mkdir()

    class C:
        job, index = str(d.name), 99

    def rec(**kw):
        base = {"mp4": str(mp4), "mtime": mp4.stat().st_mtime,
                "size": mp4.stat().st_size, "ok": True, "findings": []}
        base.update(kw)
        (ov / "qc.json").write_text(json.dumps(base))

    old_root = batch.ROOT
    try:
        batch.ROOT = d.parent
        (d.parent / f"jobs").mkdir(exist_ok=True)
        tgt = d.parent / "jobs" / C.job
        tgt.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copytree(ov, tgt / "overlays_99", dirs_exist_ok=True)

        def load_rec(**kw):
            base = {"mp4": str(mp4), "mtime": mp4.stat().st_mtime,
                    "size": mp4.stat().st_size, "ok": True, "findings": []}
            base.update(kw)
            (tgt / "overlays_99" / "qc.json").write_text(json.dumps(base))

        load_rec()
        check("a matching record is reused",
              batch._recorded_qc(C, mp4) is not None)
        load_rec(size=999)
        check("a record whose size disagrees is refused",
              batch._recorded_qc(C, mp4) is None)
        load_rec(mtime=1.0)
        check("a record whose mtime disagrees is refused",
              batch._recorded_qc(C, mp4) is None)
        load_rec(mp4="/somewhere/else.mp4")
        check("a record naming another file is refused",
              batch._recorded_qc(C, mp4) is None)
    finally:
        batch.ROOT = old_root


if __name__ == "__main__":
    print(__doc__.strip().splitlines()[0])
    print()
    for fn in (test_both_call_sites_pass_the_same_signals,
               test_chat_expected_specifically,
               test_a_none_chat_expected_skips_rather_than_passes,
               test_the_fatal_flag_is_still_set,
               test_a_reused_report_is_keyed_to_the_file):
        print(fn.__name__)
        fn()
        print()
    if FAILURES:
        sys.exit(f"{len(FAILURES)} failed: {FAILURES}")
    print("the two QC passes agree")
