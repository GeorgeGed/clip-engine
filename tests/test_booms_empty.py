"""`booms: []` MUST MEAN NO BOOMS, and `booms: null` must mean "nobody said".

George asked the ask feature to "remove the booms". It wrote `booms: []` to
the spec, `_punch_plan` logged that the spec was overriding the pick, the
clip rebuilt and all ten gates passed — and the boom was still in the file,
measured identical at 3.51x the low-band baseline before and after.

`bold_moments` tested `if keep:`. An empty list is falsy, so `keep=[]` fell
through to the automatic pick. `_punch_plan` draws the line correctly one
call earlier (`if clip.booms is not None`), so two places decided the same
thing differently — this repo's most-repeated defect, and the first time it
reached a feature the client had just asked for.

Reverted to `if keep:` the first two checks below fail.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import resolve_punch as rp                                     # noqa: E402

SRC = Path(__file__).resolve().parents[1] / "renders" / "styles" / "_base.mov"

fails = []


def check(name, ok, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))
    if not ok:
        fails.append(name)


if not SRC.exists():
    print(f"skipped: no {SRC}")
    raise SystemExit(0)

# An empty keep list is an ANSWER: no booms.
_, empty = rp.bold_moments(SRC, keep=[])
check("booms=[] yields no moments", empty == [], f"got {empty}")

# And it is not the same answer as None.
_, auto = rp.bold_moments(SRC, keep=None)
check("booms=[] differs from booms=None", empty != auto or not auto,
      f"[]={empty}  None={auto}")

# A named time is still honoured, so the fix did not disable the override.
if auto:
    want = round(auto[0][0], 2)
    _, named = rp.bold_moments(SRC, keep=[want])
    check("a named boom is still kept", len(named) == 1,
          f"asked {want}, got {named}")
    check("a named boom keeps its own measurement",
          named and named[0][1] is not None,
          f"got {named}")
else:
    print("note: this source has no automatic moments; override check skipped")

# The guard `_punch_plan` uses must agree with the one above.
src = (Path(__file__).resolve().parents[1] / "make_clip.py").read_text()
check("_punch_plan distinguishes [] from None",
      "if clip.booms is not None:" in src)
check("bold_moments distinguishes [] from None",
      "if keep is not None:" in
      (Path(__file__).resolve().parents[1] / "resolve_punch.py").read_text())

print()
print(f"{'FAILED: ' + ', '.join(fails) if fails else 'all checks passed'}")
raise SystemExit(1 if fails else 0)
