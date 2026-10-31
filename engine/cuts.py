"""Picture cuts for a take clip, and the framing of each shot.

Why PICTURE cuts and not real ones. Clip 8 has six inter-word gaps over 0.8s
and every one of them is a Twitch mute sitting MID-SENTENCE -- "was never
kind" [1.25s gone] "to job stability". Removing any of them joins speech
across content nobody can hear, which is exactly what the non-contiguous
speech gate rejects. So the audio runs unbroken and only the FRAME cuts:
shots change on a pause, the viewer reads it as cutting, and nothing is
spliced.
"""
import json

MIN_GAP = 0.22          # a pause has to be real to hide a cut
MIN_SHOT = 4.0          # below this the cutting reads as a twitch
TARGET_SHOT = 8.9       # R1's measured mean


def cut_points(words, duration, *, min_gap=MIN_GAP, min_shot=MIN_SHOT):
    """Midpoints of the widest inter-word gaps, spaced at least min_shot apart."""
    gaps = sorted(((float(b["start"]) - float(a["end"]),
                    (float(a["end"]) + float(b["start"])) / 2)
                   for a, b in zip(words, words[1:])), reverse=True)
    cuts = []
    for g, mid in gaps:
        if g < min_gap:
            break
        if min_shot < mid < duration - min_shot and \
           all(abs(mid - c) >= min_shot for c in cuts):
            cuts.append(mid)
    return sorted(cuts)


def framings(n, rect, *, cycle=(0.0, 0.10, 0.04, 0.14, 0.06)):
    """One source rect per shot. A cycle rather than strict alternation, so
    the rhythm does not become a metronome. Each entry is an inset fraction;
    the crop biases upward because the face sits above the box centre."""
    x0, y0, x1, y1 = rect
    w, h = x1 - x0, y1 - y0
    out = []
    for i in range(n):
        f = cycle[i % len(cycle)]
        dx, dy = w * f / 2, h * f / 2
        out.append((x0 + dx, y0 + dy * 0.6, x1 - dx, y1 - dy * 1.4))
    return out


if __name__ == "__main__":
    import sys
    SP = "/private/tmp/claude-501/-Users-georgegeddes-Library-Application-Support-Claude-scratch-workspaces-6d38ae6d-05dd-4827-8e46-76304910d38e-68f1a3b0-a8d1-4d98-a822-3205d41bec7a-scratch-2026-10-28-f045e2/ce92e562-40cc-4445-80fa-a3607729fc90/scratchpad"
    tr = json.load(open(f"{SP}/clip08_words.json"))
    words = [w for u in tr["utterances"] for w in u["words"]]
    DUR = 67.1
    for ms in (4.0, 5.0, 6.0):
        c = cut_points(words, DUR, min_shot=ms)
        segs = [0.0] + c + [DUR]
        lens = [b - a for a, b in zip(segs, segs[1:])]
        print(f"min_shot {ms}: {len(c)} cuts, {len(lens)} shots, "
              f"mean {sum(lens)/len(lens):4.1f}s, {len(c)/(DUR/60):.1f} cuts/min")


def content_framings(n, src_w=1920, src_h=1080, *, chrome=92,
                     cycle=((0.50, 1.00), (0.34, 1.12), (0.62, 1.06),
                           (0.44, 1.18), (0.58, 1.02))):
    """One source rect per shot for the CONTENT pane.

    R1 ran seven different exhibits through its lower pane — gameplay, a
    scoreboard, a Steam profile, a stats card, a chat log, the report dialog,
    a banner. The pane is a document viewer and it MOVES. With a single static
    document all we can do is read different parts of it, so each shot gets its
    own horizontal centre and zoom, which both matches the reference behaviour
    and stops the bottom 58% of frame sitting still for a minute.

    Each cycle entry is (centre_x as a fraction of width, zoom). Zoom > 1
    narrows the window, which makes the text BIGGER and more legible, not less.
    """
    out = []
    for i in range(n):
        cx, z = cycle[i % len(cycle)]
        vis_w = src_w / z
        x0 = min(max(cx * src_w - vis_w / 2, 0.0), src_w - vis_w)
        out.append((x0, chrome, x0 + vis_w, src_h))
    return out


def content_scenes(clip, *, region=(0, 0, 1400, 1080), fps=2.0, thresh=12.0):
    """Times where the DOCUMENT in the content pane changes.

    R1's lower pane ran seven exhibits. Where the source switches document,
    that is the strongest cut motivation available — AGENTS.md's "cut when the
    point changes" is literally true here — and it must be a cut, because a
    shot that straddles the change reframes the wrong document for half its
    length.
    """
    import subprocess
    import numpy as np
    x, y, w, h = region
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(clip), "-vf",
         f"fps={fps},crop={w}:{h}:{x}:{y},scale=64:48",
         "-pix_fmt", "gray", "-f", "rawvideo", "-"], capture_output=True).stdout
    n = len(raw) // (64 * 48)
    a = np.frombuffer(raw, dtype=np.uint8)[: n * 64 * 48].reshape(n, 48, 64).astype(float)
    d = np.abs(np.diff(a, axis=0)).mean(axis=(1, 2))
    return [round((i + 1) / fps, 2) for i, v in enumerate(d) if v > thresh]


def exhibit_framings(shots, scenes, rects_by_scene, default):
    """Pick a content rect per shot from which document is on screen.

    `rects_by_scene` maps a scene index to a source rect; anything unmapped
    falls back to `default(i)`, which is the pan-across-the-document cycle.
    """
    out = []
    for i, (a, _b) in enumerate(shots):
        idx = sum(1 for s in scenes if s <= a + 0.05)
        out.append(rects_by_scene.get(idx) or default(i))
    return out
