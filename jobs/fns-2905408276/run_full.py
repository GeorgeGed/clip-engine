import json, pathlib, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))
import soundfile as sf

SP = "/private/tmp/claude-501/-Users-georgegeddes-Library-Application-Support-Claude-scratch-workspaces-6d38ae6d-05dd-4827-8e46-76304910d38e-68f1a3b0-a8d1-4d98-a822-3205d41bec7a-scratch-2026-10-28-f045e2/ce92e562-40cc-4445-80fa-a3607729fc90/scratchpad/fns"
JOB = pathlib.Path(__file__).parent
T_PATH = pathlib.Path(SP) / "transcript_full.json"
OUT = JOB / "tier3.json"

# ── 1. transcribe the whole VOD once ──────────────────────────────────────
if T_PATH.exists():
    utt = json.loads(T_PATH.read_text())
    print(f"[1/2] transcript cached: {len(utt)} utterances", flush=True)
else:
    from faster_whisper import WhisperModel
    print("[1/2] transcribing 103 min (this is the slow part)...", flush=True)
    t0 = time.time()
    audio, sr = sf.read(f"{SP}/fns.wav", dtype="float32")
    m = WhisperModel("small", device="cpu", compute_type="int8")
    segs, _ = m.transcribe(audio, language="en", vad_filter=True,
                           vad_parameters={"min_silence_duration_ms": 400},
                           condition_on_previous_text=False)
    utt = []
    for s in segs:
        if s.text.strip():
            utt.append({"start": round(s.start, 1), "text": s.text.strip()})
            if len(utt) % 200 == 0:
                print(f"      {len(utt)} utterances, at {s.start/60:.0f}min, "
                      f"{time.time()-t0:.0f}s elapsed", flush=True)
    T_PATH.write_text(json.dumps(utt, indent=2))
    print(f"[1/2] done: {len(utt)} utterances in {time.time()-t0:.0f}s", flush=True)

# ── 2. Tier 3 over every region ───────────────────────────────────────────
from engine.tier3 import judge
import anthropic
from engine.tier3 import _api_key

regions = json.loads((pathlib.Path(SP) / "regions.json").read_text())
done = json.loads(OUT.read_text()) if OUT.exists() else []
seen = {tuple(r["region"]) for r in done}
client = anthropic.Anthropic(api_key=_api_key())
print(f"[2/2] Tier 3 over {len(regions)} regions ({len(done)} already done)", flush=True)

def ts(t): return f"{int(t//3600)}:{int(t%3600//60):02d}:{int(t%60):02d}"

for i, r in enumerate(regions, 1):
    key = (r["start"], r["end"])
    if key in seen:
        continue
    try:
        vs = [v.as_dict() for v in judge(utt, (r["start"], r["end"]), client=client, pad=60)]
    except Exception as e:
        vs = [{"has_clip": False, "genre": "none", "why": f"error: {type(e).__name__}: {e}"}]
    for v in vs:
        done.append({"region": [r["start"], r["end"]], "audio_rank": i,
                     "audio_peak": r["peak"], "audio_mean": r["mean"], **v})
    OUT.write_text(json.dumps(done, indent=2))
    got = [v for v in vs if v.get("has_clip")]
    if got:
        parts = " | ".join(f"{ts(v['in_point'])} {v['out_point']-v['in_point']:.0f}s" for v in got)
        print(f"   {i:>2}/{len(regions)}  {ts(r['start'])}  ->  {len(got)} clip(s): {parts}", flush=True)
    else:
        print(f"   {i:>2}/{len(regions)}  {ts(r['start'])}  ->  none", flush=True)

print(f"\nDONE: {sum(1 for d in done if d.get('has_clip'))} clips found across {len(done)} regions", flush=True)
