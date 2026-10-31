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
