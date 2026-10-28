# Clip Engine

VALORANT clipping, built so the methodology is **enforced** rather than described.

Claude decides the edit and writes an `edit.json`. Gates check it against the
methodology. A renderer executes it — ffmpeg for volume, FCPXML/Resolve for hero
and client work. The edit is reviewable, diffable and re-renderable before a
frame exists.

## Read first

| | |
|---|---|
| [AGENTS.md](AGENTS.md) | the operating rules, read at edit time. Rules marked **[gate]** are enforced in code |
| [CLIP-METHODOLOGY.md](CLIP-METHODOLOGY.md) | why each rule exists |
| [EDIT-CONTRACT.md](EDIT-CONTRACT.md) | the `edit.json` format, with worked examples |
| [docs/RESOLVE-SETUP.md](docs/RESOLVE-SETUP.md) | getting Resolve into the loop |

## Pipeline

```
VOD ──▶ ingest ──▶ analyse ──▶ rank ──▶ [Claude writes edit.json] ──▶ gate ──▶ render
                      │                                                          ├─▶ ffmpeg  (volume)
                      ├── transcribe   word timestamps                           └─▶ fcpxml  (Resolve)
                      ├── detect_audio reaction spikes
                      └── detect_killfeed  kills → rounds → multikills
```

```bash
./run.py ingest https://twitch.tv/videos/... --job fns-oct28 --rights explicit --start 4800 --end 5000
./run.py calibrate --job fns-oct28          # look at the ROI crops BEFORE trusting detection
./run.py analyse   --job fns-oct28
./run.py rank      --job fns-oct28
# Claude writes jobs/fns-oct28/edits/<clip>.json under AGENTS.md
./run.py gate      --job fns-oct28 --edit jobs/fns-oct28/edits/ace.json
./run.py render    --job fns-oct28 --edit jobs/fns-oct28/edits/ace.json
```

`run.py` re-execs itself under `.venv`, so it runs from any shell.

## What is verified, and what is not

**Verified on this machine**

- 38/38 gate tests pass (`tests/test_gates.py`) — every enforceable rule bites
- Killfeed detection on a synthetic feed: finds a 3k and an ace at the correct
  timestamps, and correctly excludes an enemy kill (the kill/death confusion bug)
- Audio detection separates a reaction (0.95) from a dull gunfight burst (0.55)
- Full render: 1080×1920 @ 60fps, L3 crop with the killfeed re-composited,
  captions at 0.64 with keyword emphasis, credit overlay, −14.01 LUFS against
  a −14.0 target
- FCPXML emits with frame-exact rational times and a timeMap on the retimed segment

**Not verified**

- **Killfeed detection on real VALORANT footage.** The ROI and highlight colour
  in `config/killfeed.yaml` are starting values, not measured ones. Run
  `calibrate` on a real VOD first.
- **FCPXML import into Resolve.** Resolve is not installed here, so the file has
  never been opened by the application it is written for.
- The Resolve driver and the MCP server, for the same reason.
- Whisper transcription has not been run on real audio in this project.

## Layout

```
AGENTS.md              edit-time rules
schema/                edit.schema.json
engine/
  ingest.py            yt-dlp fetch, probe, loudness, opening-frame QA
  transcribe.py        faster-whisper word timestamps          [no cv2 in this process]
  detect_audio.py      reaction spikes (RMS + spectral centroid)
  detect_killfeed.py   killfeed rows → kills → rounds          [no whisper in this process]
  candidates.py        walk-backwards anchoring + scoring
  gates.py             enforcement. the methodology, in code
  render_ffmpeg.py     backend A — volume and preview
  fcpxml.py            backend B — Resolve timeline, works in the FREE edition
  resolve_driver.py    backend C — Studio only; grading and render queue
config/
  roster.yaml          per-streamer facecam coords and permission
  style.yaml           the locked house style
  killfeed.yaml        detection ROI + highlight colour  (write this when you calibrate)
jobs/<name>/           media, detect, edits, out, calib
```

`faster-whisper` and `opencv` ship colliding ffmpeg dylibs, so transcription and
vision never run in the same interpreter. `run.py analyse` keeps them apart.
