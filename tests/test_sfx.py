"""The bed must play the sound every measurement was taken from.

WHY THIS FILE EXISTS. `bed()` rendered each cue by reading
`assets/sfx/<name>.wav` while `cue_gain`, `cue_gain_peak` and
`perceptual_lead` all measured `PALETTE[name]()`. For the nine synthesised
cues the two agree, because `build()` writes those files FROM the palette —
so the split was invisible for months. `vine_boom` is the one cue whose
waveform comes from a file George supplied: the palette entry trims his
1.185s original to 0.55s, and the file on disk is the original, so the bed
played a sound 0.63s longer than the one being measured.

The cost was the note George sent four times. The lead was solved as the
trimmed waveform's energy centroid, 237ms, and applied to a waveform whose
centroid is 508ms, so the boom's mass arrived about 270ms LATE no matter
where the anchor was moved — and every round moved the anchor by tens of
milliseconds, which could never reach it.

AGENTS.md has recorded this shape four times (`_cut.wav` cached, the shared
`punches.json` path, the punch plan measured from the overwritten delivery,
`specs` overwriting a reviewed spec) and each time the lesson written down
was "a note is not a gate; write the check". This is the check.
"""
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).parent.parent))
from engine import sfx

fails: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'pass' if cond else 'FAIL'}  {name}{'  — ' + detail if detail and not cond else ''}")
    if not cond:
        fails.append(name)


def _wave(name: str) -> np.ndarray:
    y = sfx.PALETTE[name]()
    y = y[0] if isinstance(y, tuple) else y
    return np.asarray(y, dtype=np.float64)


def run() -> int:
    tmp = Path(tempfile.mkdtemp())
    eps = 2 / 32768          # PCM_16, one quantisation step either way

    print("bed() renders the PALETTE waveform, sample for sample")
    # A threshold-based length check is not good enough here: `riser` ramps
    # out of silence and `shutter` is two clacks with a quiet gap, so both
    # report short at any sensible floor — and a real 0.63s discrepancy
    # could hide behind the same tolerance. Placing one cue in a silent bed
    # and comparing the slice is exact and needs no threshold at all.
    at, gain = 1.0, 0.5
    for name in sorted(sfx.PALETTE):
        out = tmp / f"{name}.wav"
        sfx.bed([sfx.Cue(at, name, gain, "test")], 4.0, out=out)
        got, sr = sf.read(out, dtype="float64")
        want = _wave(name) * gain
        i = int(at * sfx.SR)
        same = sr == sfx.SR and np.allclose(got[i:i + len(want)], want, atol=eps)
        tail = np.abs(got[i + len(want):])
        over = int(np.flatnonzero(tail > eps).max()) + 1 if (tail > eps).any() else 0
        ok(f"{name:<10} {len(want) / sfx.SR:5.3f}s", same and over == 0,
           f"sounds {over / sfx.SR:.3f}s past its palette length")

    print("\nthe measurements and the bed agree on one waveform")
    for name in sorted(sfx.PALETTE):
        y = _wave(name)
        lead = sfx.perceptual_lead(name)
        ok(f"{name:<10} lead {lead * 1000:6.1f}ms inside its own length",
           0.0 <= lead <= len(y) / sfx.SR)

    print("\nthe vine boom trim is live")
    y = _wave("vine_boom")
    ok(f"palette length is BOOM_LEN ({sfx.BOOM_LEN}s)",
       abs(len(y) / sfx.SR - sfx.BOOM_LEN) < 0.005,
       f"got {len(y) / sfx.SR:.3f}s")
    # The centroid IS what `perceptual_lead` returns. It has to sit inside
    # the trimmed sound, not out where the untrimmed file's 508ms does.
    ok("centroid sits in the first half of the trim",
       sfx.perceptual_lead("vine_boom") < sfx.BOOM_LEN / 2)

    print("\nbuild() never overwrites a supplied sample")
    # `vine_boom()` READS `assets/sfx/vine_boom.wav`, so a build() that
    # wrote every palette entry to `<name>.wav` would write its own trimmed
    # output over George's source file — and the next run would trim the
    # trim. Nothing caught this because build() was written when the
    # palette was entirely synthesised.
    man = sfx.build(out=tmp / "built")
    for name in sfx.SAMPLED:
        ok(f"{name} is not in the manifest", name not in man)
        ok(f"{name}.wav not written", not (tmp / "built" / f"{name}.wav").exists())
    ok("the synthesised ones still land", (tmp / "built" / "thunk.wav").exists())
    ok("and carry their rights basis",
       man.get("thunk", {}).get("rights_basis") == "synthesised")

    print("\nthe supplied sample is present and untrimmed on disk")
    for name in sfx.SAMPLED:
        src = sfx.ASSETS / f"{name}.wav"
        if not src.exists():
            ok(f"{name} source exists", False, str(src))
            continue
        w, sr = sf.read(src, dtype="float32")
        ok(f"{name} source is the original, not a trimmed copy",
           len(w) / sr > sfx.BOOM_LEN + 0.1, f"{len(w) / sr:.3f}s")

    print()
    print(f"{'ALL PASS' if not fails else str(len(fails)) + ' FAILED'}")
    for f in fails:
        print("  -", f)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(run())
