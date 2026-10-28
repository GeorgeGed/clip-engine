# The `edit.json` contract

What Opus emits. What the renderers consume. The whole methodology reduced to a file you
can read, diff, approve and re-render.

Times are **seconds, source-relative, float**. Lengths that must be frame-exact are given
in frames at the source rate.

## Worked example — an ace, L3 layout

```json
{
  "clip_id": "2026-10-28-tarik-ace-ascent",
  "genre": "frag",
  "source": {
    "path": "vods/tarik/2890592017.mp4",
    "url": "https://www.twitch.tv/videos/2890592017",
    "owner": "tarik",
    "rights_basis": "explicit",
    "fps": 60,
    "resolution": [1920, 1080]
  },
  "detection": {
    "tier": 2,
    "event": "ace",
    "round_kills": 5,
    "stakes": ["spike_down", "match_point"],
    "reaction_rms_peak": 0.81,
    "chat_velocity_x": 4.2,
    "score": 0.93
  },
  "range": { "in": 4871.40, "out": 4896.80, "anchor_rule": "first_kill_minus_1.5s" },
  "hook": { "device": "flash_forward", "payoff_in": 4893.10, "length_frames": 30, "black_frames": 2 },
  "layout": {
    "mode": "L3",
    "crop": { "anchor_x": 0.5, "anchor_y": 0.38 },
    "hud_recomposite": [
      { "element": "killfeed",    "src": [0.62, 0.05, 0.38, 0.22], "dst": [0.44, 0.09], "scale": 0.85 },
      { "element": "spike_timer", "src": [0.44, 0.02, 0.12, 0.07], "dst": [0.42, 0.04], "scale": 0.85 }
    ]
  },
  "segments": [
    { "in": 4871.40, "out": 4876.20, "speed": 1.0 },
    { "in": 4876.20, "out": 4879.90, "speed": 2.0, "ramp_frames": 8, "reason": "rotate_dead_time" },
    { "in": 4879.90, "out": 4892.95, "speed": 1.0 },
    { "in": 4892.95, "out": 4893.45, "speed": 0.35, "ramp_frames": 8, "reason": "payoff" },
    { "in": 4893.45, "out": 4896.80, "speed": 1.0 }
  ],
  "captions": {
    "enabled": true,
    "style": "word",
    "position_y": 0.64,
    "cards": [
      { "in": 4884.10, "out": 4885.00, "text": "he's one", "emphasis": null },
      { "in": 4885.00, "out": 4886.20, "text": "HE'S ONE", "emphasis": "ONE" }
    ]
  },
  "audio": {
    "target_lufs": -14.0,
    "true_peak_dbtp": -1.0,
    "duck": { "amount_db": 7.0, "attack_ms": 120, "release_ms": 400 },
    "music": null,
    "sfx": []
  },
  "overlays": [
    { "type": "credit", "text": "tarik", "position": "top-left", "size": 38, "margin": 36 }
  ],
  "tail_frames": 72,
  "gates": { "passed": true, "warnings": [], "held": [] },
  "render": { "backend": "ffmpeg", "width": 1080, "height": 1920, "fps": 60, "codec": "h264", "audio_codec": "aac" }
}
```

## Worked example — a take clip, L2 layout with a subject cutaway

```json
{
  "clip_id": "2026-10-28-gofns-nrg-roster",
  "genre": "take",
  "source": {
    "path": "vods/gofns/2897760313.mp4",
    "owner": "gofns",
    "rights_basis": "explicit",
    "fps": 60
  },
  "speaker": { "name": "FNS", "flag": "CA", "host_stream": "gofns", "confidence": 0.97 },
  "subject": { "entity": "NRG", "type": "team", "in_roster_json": true },
  "claim": {
    "setup":       "the way the region's gone this year",
    "claim":       "I don't know how this region has gotten worse",
    "consequence": "evidently worse at playing the game",
    "min_lines_ok": true,
    "contiguous":  true
  },
  "range": { "in": 4871.00, "out": 4902.60, "anchor_rule": "setup_first_word" },
  "hook": { "device": "none", "text": "FNS on China's decline", "seconds": 2.5 },
  "layout": {
    "mode": "L2",
    "split_ratio": 0.44,
    "facecam_source": { "x": 0.72, "y": 0.26, "w": 0.28, "h": 0.27 },
    "facecam_sharpen": true
  },
  "segments": [
    { "in": 4871.00, "out": 4878.40, "speed": 1.0, "punch": 1.0 },
    { "in": 4879.10, "out": 4886.70, "speed": 1.0, "punch": 1.06, "cut_reason": "gap_620ms" },
    { "in": 4887.30, "out": 4902.60, "speed": 1.0, "punch": 1.0, "cut_reason": "false_start" }
  ],
  "inserts": [
    { "in": 4886.70, "length": 1.6, "asset": "hermes_images/nrg/roster_2026.jpg",
      "push": [1.0, 1.04], "covers_cut": true }
  ],
  "captions": { "enabled": true, "style": "phrase", "words_per_card": 4, "position_y": 0.55, "max_lines": 2 },
  "audio": { "target_lufs": -14.0, "duck": { "amount_db": 7.0 }, "music": { "bed": "licensed/calm_01.wav", "lufs": -22.0 } },
  "tail_frames": 48,
  "gates": { "passed": true, "warnings": ["'NRG' confirmed in roster.json"], "held": [] },
  "render": { "backend": "fcpxml", "width": 1080, "height": 1920, "fps": 60 }
}
```

## Field rules the renderers enforce

| Field | Rule |
|---|---|
| `segments[].speed` | `1.0` during any fight. Dead time `1.6`–`2.2`. Exactly one segment may be `< 1.0`, length ≤ 30 source frames |
| `segments[].ramp_frames` | `8` unless overridden |
| `segments[]` boundaries | For `genre: "take"`, must fall on a word boundary |
| `captions.position_y` | `0.62`–`0.68` for L1/L3; `0.55` for L2 |
| `captions.style` | `"phrase"` for take, `"word"` allowed for frag |
| `tail_frames` | `36`–`90` |
| `hook.device` | one of `cold_open`, `flash_forward`, `none` — never two |
| `audio.music` | must be `null` for `genre: "frag"` unless explicitly overridden |
| `range` duration | frag `12`–`35s`, take `18`–`45s` |
| `source.rights_basis` | must be `explicit`, `affiliate` or `client_owned` |

## Backends

- **`ffmpeg`** — volume. Reads `edit.json` directly. Headless and parallel.
- **`fcpxml`** — emit an FCPXML timeline from the same file, import into Resolve (works in
  the Free edition, no scripting API). For hero clips, client deliverables and anything a
  human editor will take over.
- **`resolve_mcp`** — only for triggering renders, applying grades and driving Fusion.
  Requires Resolve **Studio**. Not needed to build a timeline.
