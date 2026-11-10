"""THREE BOOM ANSWERS, AND THE EDITOR COULD ONLY SEND TWO.

`booms: []` means "no booms, decided"; `booms: null` means "nobody has
said"; a list names the times. `resolve_punch.bold_moments` was fixed to
honour that distinction one round ago, after "remove the booms" wrote `[]`
and the clip shipped with the boom in it.

The page then undid it one layer up. `spec.booms ? spec.booms.join(', ') : ''`
is TRUE for `[]` in JavaScript, `[].join()` is `''`, and `_clean` maps `''`
to `None` — so any save of ANY field on a clip with `booms: []` restored its
booms, "Save & cut" rebuilt it with them in, and the spec's own notes kept
asserting they had been removed.

The same drawer had the mirror bug on chat: `if (mode) spec.chat_mode = mode`
omitted the key when the select was on "Decide automatically", so that
option was inoperative and a set mode could never be cleared from the page.

Checked here as the WHOLE PATH: the payload shape the page sends, through
`_clean`, through `write_spec`, through `load()`. The two JS-side checks read
`app.js` directly, because that is where the defect was.
"""
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

import server as web                                          # noqa: E402
from engine.clipspec import load                              # noqa: E402

fails = []


def check(name, ok, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))
    if not ok:
        fails.append(name)


# ---- the validator keeps the three answers apart -----------------------
for sent, want, label in (
        ([], [], "[] stays an empty list"),
        (None, None, "null stays null"),
        ("1.5, 12.87", [1.5, 12.87], "a list of times survives"),
        ([3.0], [3.0], "a one-element list survives")):
    got, err = web._clean({"in_point": 1.0, "booms": sent})
    check(f"booms: {label}", err is None and got.get("booms") == want,
          f"sent {sent!r} -> {got.get('booms')!r} err={err}")

# `[]` and `None` must not collapse into each other.
a, _ = web._clean({"in_point": 1.0, "booms": []})
b, _ = web._clean({"in_point": 1.0, "booms": None})
check("[] and null are different answers after validation",
      a["booms"] is not None and b["booms"] is None,
      f"[]->{a['booms']!r}  null->{b['booms']!r}")

# ---- chat_mode can be cleared -------------------------------------------
got, err = web._clean({"in_point": 1.0, "chat_mode": None})
check("chat_mode clears to null", err is None and got.get("chat_mode") is None,
      f"{got.get('chat_mode')!r} err={err}")
got, err = web._clean({"in_point": 1.0, "chat_mode": "off"})
check("chat_mode 'off' is accepted", err is None and got.get("chat_mode") == "off",
      f"{got.get('chat_mode')!r} err={err}")
got, err = web._clean({"in_point": 1.0, "chat_mode": "nonsense"})
check("an unknown chat_mode is refused", err is not None, f"err={err}")

# ---- and nan/inf are still refused --------------------------------------
for bad in ("nan", "inf", "-inf"):
    _, err = web._clean({"in_point": 1.0, "booms": bad})
    check(f"booms refuses {bad!r}", err is not None, f"err={err}")
    _, err = web._clean({"in_point": bad})
    check(f"in_point refuses {bad!r}", err is not None, f"err={err}")

# ---- through the spec on disk -------------------------------------------
src = ROOT / "clips" / "fns-12.json"
if src.exists():
    tmp = Path(tempfile.mkdtemp()) / "fns-12.json"
    tmp.write_text(src.read_text())
    for sent, want in (([], []), (None, None), ("2.5", [2.5])):
        d = json.loads(tmp.read_text())
        patch, err = web._clean({"in_point": d["clip"]["in_point"], "booms": sent})
        assert err is None, err
        d["clip"].update(patch)
        tmp.write_text(json.dumps(d, indent=1))
        clip, _ch = load(tmp)
        check(f"booms {sent!r} survives the spec file", clip.booms == want,
              f"read back {clip.booms!r}")

# ---- the page sends JSON types, not a joined string --------------------
# COMMENTS STRIPPED FIRST. Both of these defects are named in the comments
# that explain the fix, so searching the raw file reports the fix as the bug.
_raw = (ROOT / "web/static/app.js").read_text()
JS = re.sub(r"//[^\n]*", " ", re.sub(r"/\*.*?\*/", " ", _raw, flags=re.S))
check("the page no longer joins booms through truthiness",
      "spec.booms ? spec.booms.join" not in JS)
check("the page tests Array.isArray for booms", "Array.isArray(b)" in JS)
check("the page sends [] / null / a value for booms",
      re.search(r"spec\.booms\s*=\s*bm === 'none' \? \[\]", JS) is not None)
check("the page always sends chat_mode so it can be cleared",
      "spec.chat_mode = get('chat_mode') || null" in JS
      and "if (mode) spec.chat_mode = mode" not in JS)

print()
print("FAILED: " + ", ".join(fails) if fails else "all checks pass")
raise SystemExit(1 if fails else 0)
