"""Re-transcribe the finished cut and check every word survived the splices.

Taken from the scenario-auto-edit finish standard: "Re-transcribe the cut and
the final mix: every word must survive." We made 15 joins removing dead space;
this is the check that none of them ate a word.
"""
import sys, json, difflib, re
R="/Users/georgegeddes/Library/Application Support/Claude/scratch-workspaces/6d38ae6d-05dd-4827-8e46-76304910d38e/68f1a3b0-a8d1-4d98-a822-3205d41bec7a/scratch-2026-10-28-f045e2"
sys.path.insert(0,R)
from engine.transcribe import transcribe

def norm(s):
    return [w for w in re.findall(r"[a-z']+", s.lower()) if w]

SP="/private/tmp/claude-501/-Users-georgegeddes-Library-Application-Support-Claude-scratch-workspaces-6d38ae6d-05dd-4827-8e46-76304910d38e-68f1a3b0-a8d1-4d98-a822-3205d41bec7a-scratch-2026-10-28-f045e2/ce92e562-40cc-4445-80fa-a3607729fc90/scratchpad"
src = json.load(open(f"{SP}/clip08_words.json"))
IN_POINT = 8.85
expected = norm(" ".join(w["text"] for u in src["utterances"] for w in u["words"]
                         if float(w["start"]) >= IN_POINT))
print(f"source words from the in-point: {len(expected)}")

out = transcribe(f"{R}/renders/clip08_FINAL.mp4", model_size="small")
got = norm(" ".join(u["text"] for u in out["utterances"]))
print(f"words heard in the delivered cut: {len(got)}")

sm = difflib.SequenceMatcher(None, expected, got, autojunk=False)
missing, added = [], []
for tag,i1,i2,j1,j2 in sm.get_opcodes():
    if tag in ("delete","replace"): missing += expected[i1:i2]
    if tag in ("insert","replace"): added   += got[j1:j2]
print(f"\nsimilarity {sm.ratio():.3f}")
print(f"MISSING from the cut ({len(missing)}): {' '.join(missing[:60])}")
print(f"HEARD but not in source ({len(added)}): {' '.join(added[:40])}")
