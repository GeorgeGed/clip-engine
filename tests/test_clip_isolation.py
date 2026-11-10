"""NOTHING ONE CLIP WRITES MAY REACH ANOTHER CLIP'S FRAMES.

George: *"why doesnt it let me clip multiple clips at once? needs to allow
this possibility"*. Two clips cannot build at once until this holds, and both
paths below fail SILENTLY — no error, no warning, a clean render of the wrong
material. This repo has shipped that defect three times: clip 6's chat
composited onto clip 12, a story card recovered from the shared
`stories.json`, and the stale `_cut.wav`.

Three properties, each a separate mechanism:

1. the PNG sequence directory is per call, not per composition name —
   `rm_Bait.mov` is 1020 frames on every clip of this job, so a shared
   directory keyed by `Bait` means two clips write the same 1020 filenames
   and the pad width matches, so the mixture encodes with no error;
2. `Root.tsx` reads per-clip data from `inputProps`, not from a webpack
   `import` of the shared `public/` tree — an import is inlined at BUNDLE
   time, which is why `--public-dir` cannot fix it;
3. every render is handed `--props`.

Reverted to the shared-path version, checks 1 and 2 fail.
"""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

fails = []


def check(name, ok, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))
    if not ok:
        fails.append(name)


SRC = (ROOT / "make_clip.py").read_text()
TREE = ast.parse(SRC)
RENDER = next(f for f in ast.walk(TREE)
              if isinstance(f, ast.FunctionDef) and f.name == "_render_comp")
# the CODE, not the docstring — the docstring names the old shared path on
# purpose, and matching it reports a defect that is only a comment.
BODY = "\n".join(ast.get_source_segment(SRC, n) or ""
                 for n in RENDER.body
                 if not (isinstance(n, ast.Expr)
                         and isinstance(n.value, ast.Constant)))

# 1. THE SEQUENCE DIRECTORY IS PER CALL.
check("the PNG sequence directory is a fresh temp dir",
      "mkdtemp" in BODY and "remotion-seq" not in BODY,
      "still keyed by composition name" if "remotion-seq" in BODY else "")
check("the sequence directory is cleaned up on failure too",
      "finally:" in BODY)

# 2. ROOT.TSX TAKES ITS PER-CLIP DATA FROM inputProps.
RT = (ROOT / "vendor/remotion-clip08/src/Root.tsx").read_text()
check("Root.tsx calls getInputProps", "getInputProps()" in RT)

# The five per-clip files. `badgemap.json` is static and shared on purpose.
PER_CLIP = ["chat.json", "chat_windows.json", "clip.json", "stories.json"]
imported = {m.group(1) for m in
            re.finditer(r"import\s+(\w+)\s+from\s+'\.\./public/([\w.]+)'", RT)
            if m.group(2) in PER_CLIP}
# Those names may appear ONLY as the `??` fallback of an inputProps read.
# Strip comments first: the component tree is full of prose that uses the
# words "chat", "clip" and "stories", and matching those reports a defect
# that is only a sentence.
body = RT.split("export const Root")[1]
body = re.sub(r"/\*.*?\*/", " ", body, flags=re.S)
body = re.sub(r"//[^\n]*", " ", body)
leaked = sorted(n for n in imported if re.search(rf"\b{n}\b", body))
check("no per-clip import is read inside the component tree", not leaked,
      f"{leaked} read from the shared public/ files" if leaked else "")

# 3. EVERY RENDER IS HANDED --props.
check("the render command passes --props", "--props=" in SRC)
check("a missing props file is reported, not silently ignored",
      "WARNING: no props.json" in SRC)
check("a props file missing a key is reported",
      "props.json has no" in SRC)

# 4. The shared paths this repo has already been bitten by stay mirrored
#    per clip — the chat-off branch wrote only the shared one.
own = SRC.count('(st["overlays"] / "chat_windows.json").write_text')
check("the chat-off branch writes the clip's own windows file too", own >= 2,
      f"{own} call sites" )
check("_sfx_bed distinguishes [] from None",
      "wins is None" in SRC and "if not wins and" not in SRC)

print()
print("FAILED: " + ", ".join(fails) if fails else "all checks pass")
raise SystemExit(1 if fails else 0)
