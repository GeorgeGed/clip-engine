"""Word-level captions in DaVinci Resolve, driven from Python.

Why it is built this way, because the obvious routes are all dead ends:

* **Subtitle track and Auto Captions cannot be styled from Python.** Font,
  size, colour, stroke and position are all unreachable — a grep of the whole
  3525-line API stub returns no text-style property anywhere, and
  `TimelineItemProperties` is transform/crop only. You can create the track and
  put timed text on it, and it will look like Resolve's default subtitle. That
  is not the house style, so this module does not use it.
* **Text+ gives full style control**, but a title inserted from Python is a
  fixed 300 frames and there is no `SetDuration`. 130 half-second cards cannot
  be 130 titles on one track.
* **`StyledText` does not keyframe.** Writing it at three different times
  leaves one static value, the last write. Numeric inputs do not keyframe
  either.
* **`StyledText` DOES accept a Fusion expression**, and the expression is
  evaluated per frame. That is the whole trick.

So: one Text+ per 300-frame window, chained across the clip (14 for a 67s clip
at 60fps), each carrying a nested `iif(time < f, "…", …)` over comp-local time
that switches its ~10 cards. Styling is set once per title.

Shading elements are the other trap. Element 2 is a disabled "Red Outline"
whose inputs read `None` until `Enabled2 = 1`; only then do Red2/Green2/Blue2/
Thickness2/ElementShape2 exist and take values.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

TITLE_FRAMES = 300          # what InsertFusionTitleIntoTimeline produces; not settable

# Both references use 1-3 words changing about twice a second.
MAX_WORDS = 3
MAX_CARD_S = 0.55
GAP_BREAK_S = 0.60          # a pause this long ends the card and clears the screen

PROFANITY = re.compile(
    r"\b(fuck(ing|ed|er|s)?|shit(ty|s)?|bitch(es)?|cunt|dick(head)?|asshole)\b", re.I)


@dataclass
class Style:
    """House caption look. Fusion units: Size and Center are 0..1 of frame."""
    font: str = "Tungsten"
    face: str = "Bold"
    size: float = 0.115
    y: float = 0.44              # fraction from the TOP of frame
    fill: tuple[float, float, float] = (1.0, 1.0, 1.0)
    stroke: tuple[float, float, float] = (0.0, 0.0, 0.0)
    # 0.30 blobs: the outline merges into a slab and the letterforms vanish.
    # 0.14 follows the glyphs and still reads over any background.
    stroke_thickness: float = 0.14
    accent: tuple[float, float, float] = (1.0, 0.82, 0.10)   # one emphasis colour


@dataclass
class Card:
    start: float                 # seconds, clip-relative
    end: float
    text: str
    words: list[str] = field(default_factory=list)
    emphasis: bool = False       # whole card takes the accent colour


def mask_profanity(word: str) -> str:
    """Mask the caption, never the audio — the master stays untouched."""
    def repl(m):
        w = m.group(0)
        return w[0] + "*" * (len(w) - 1)
    return PROFANITY.sub(repl, word)


def cards(words: list[dict], *, max_words: int = MAX_WORDS,
          max_card_s: float = MAX_CARD_S, gap_break_s: float = GAP_BREAK_S) -> list[Card]:
    """Group word timings into 1-3 word cards.

    Cards are held until the next card starts, so text does not flicker between
    words inside a phrase. A gap longer than `gap_break_s` clears the screen
    instead — on a clip with muted regions that matters, or a stale card sits
    over silence.
    """
    out: list[Card] = []
    cur: list[dict] = []

    def flush():
        if not cur:
            return
        txt = " ".join(mask_profanity(w["text"]).upper() for w in cur).strip()
        if txt:
            out.append(Card(float(cur[0]["start"]), float(cur[-1]["end"]), txt,
                            [w["text"] for w in cur]))
        cur.clear()

    for w in words:
        if cur:
            gap = float(w["start"]) - float(cur[-1]["end"])
            span = float(w["end"]) - float(cur[0]["start"])
            if gap > gap_break_s or len(cur) >= max_words or span > max_card_s:
                flush()
        cur.append(w)
    flush()

    # Hold each card until the next begins, unless the gap is a real pause.
    for i, c in enumerate(out):
        nxt = out[i + 1].start if i + 1 < len(out) else None
        if nxt is not None and nxt - c.end <= gap_break_s:
            c.end = nxt
    return out


STOPWORDS = {
    "that", "this", "with", "from", "they", "them", "their", "there", "then",
    "what", "when", "which", "while", "would", "could", "should", "about",
    "after", "before", "only", "just", "even", "also", "like", "been", "have",
    "into", "more", "most", "some", "than", "because", "says", "said", "reads",
    "means", "being", "other", "every", "where", "your", "will", "much",
}


def emphasis_keys(*texts: str, min_len: int = 5) -> set[str]:
    """Content words from the model's own claim and consequence.

    The claim IS the point of the clip, so its words are what deserve the one
    accent colour. Keying off the Tier 3 output rather than a hand-written list
    means this works on any clip without tuning.
    """
    keys: set[str] = set()
    for tx in texts:
        for raw in re.findall(r"[A-Za-z']+", tx or ""):
            w = raw.lower().strip("'")
            if len(w) >= min_len and w not in STOPWORDS:
                keys.add(w.upper())
    return keys


def mark_emphasis(cards_: list[Card], keys: set[str]) -> int:
    """Flag cards containing a key word. Returns how many were marked."""
    n = 0
    for c in cards_:
        toks = {w.strip(".,!?'\"").upper() for w in c.text.split()}
        if toks & keys:
            c.emphasis = True
            n += 1
    return n


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def expression(window_cards: list[tuple[int, int, str]], ) -> str:
    """Nested iif over comp-local frames. Each entry is (start, end, text).

    Written innermost-last so the first matching window wins, and anything
    outside every card renders as empty string.
    """
    expr = '""'
    for start, end, text, *_ in reversed(window_cards):
        expr = f'iif(time >= {start} and time < {end}, "{_esc(text)}", {expr})'
    return expr


def colour_expression(window_cards: list[tuple[int, int, str, bool]],
                      channel: int, fill: tuple, accent: tuple) -> str:
    """Per-card fill colour, same iif trick as the text.

    Numeric inputs do not keyframe, but they DO take expressions — verified the
    same way StyledText was. So one tool can change colour per card.
    """
    base = fill[channel]
    expr = f"{base}"
    for start, end, _txt, emph in reversed(window_cards):
        val = accent[channel] if emph else fill[channel]
        expr = f"iif(time >= {start} and time < {end}, {val}, {expr})"
    return expr


def plan_windows(cards_: list[Card], *, fps: float, total_frames: int) -> list[dict]:
    """Split the clip into 300-frame title windows and assign cards to each.

    A title cannot be trimmed, so the LAST window is pulled back to end exactly
    on the video rather than overhanging it. Without this the timeline runs
    past the picture by up to 299 frames and the export carries a tail of
    captions over black.
    """
    n = max(1, math.ceil(total_frames / TITLE_FRAMES))
    out = []
    for w in range(n):
        lo = w * TITLE_FRAMES
        if w == n - 1 and total_frames >= TITLE_FRAMES:
            lo = total_frames - TITLE_FRAMES     # sit flush with the end
        hi = lo + TITLE_FRAMES
        entries = []
        for c in cards_:
            s, e = round(c.start * fps), round(c.end * fps)
            if e <= lo or s >= hi:
                continue
            # The pulled-back last window overlaps its predecessor; let it own
            # only the cards the earlier window could not reach.
            if w == n - 1 and n > 1 and s < (n - 1) * TITLE_FRAMES:
                continue
            entries.append((max(0, s - lo), min(TITLE_FRAMES, e - lo),
                            c.text, c.emphasis))
        out.append({"index": w, "offset_frames": lo, "cards": entries})
    return out


def style_tool(tool, style: Style) -> None:
    """Apply the house look to one Text+ tool."""
    tool.SetInput("Font", style.font)
    try:
        tool.SetInput("Style", style.face)
    except Exception:
        pass                      # not every family exposes a Style input
    tool.SetInput("Size", float(style.size))
    tool.SetInput("Center", {1: 0.5, 2: 1.0 - style.y, 3: 0.0})   # Fusion y is from BOTTOM
    tool.SetInput("VerticalJustificationCenter", 0.5)
    tool.SetInput("HorizontalJustificationCenter", 0.5)

    r, g, b = style.fill
    for k, v in (("Red1", r), ("Green1", g), ("Blue1", b), ("Alpha1", 1.0)):
        tool.SetInput(k, float(v))

    # Element 2 is a disabled "Red Outline"; its inputs do not exist until enabled.
    tool.SetInput("Enabled2", 1.0)
    sr, sg, sb = style.stroke
    for k, v in (("Red2", sr), ("Green2", sg), ("Blue2", sb), ("Alpha2", 1.0),
                 ("Thickness2", float(style.stroke_thickness)),
                 ("ElementShape2", 1.0)):
        tool.SetInput(k, v)


def build(timeline, cards_: list[Card], *, fps: float, track: int,
          style: Style | None = None, log=print) -> dict:
    """Lay the caption titles onto `track`. Returns a summary."""
    style = style or Style()
    start_frame = timeline.GetStartFrame()
    total = timeline.GetEndFrame() - start_frame
    windows = plan_windows(cards_, fps=fps, total_frames=total)

    while timeline.GetTrackCount("video") < track:
        timeline.AddTrack("video")

    made = 0
    for w in windows:
        if not w["cards"]:
            continue
        abs_frame = start_frame + w["offset_frames"]
        tc = _frame_to_tc(abs_frame, fps)
        timeline.SetCurrentTimecode(tc)
        timeline.SetCurrentTimecode(tc)
        item = timeline.InsertFusionTitleIntoTimeline("Text+")
        if item is None:
            log(f"  window {w['index']}: insert FAILED")
            continue
        item.SetPosition({"trackIndex": track, "startFrame": abs_frame})
        comp = item.GetFusionCompByIndex(1)
        tool = list(comp.GetToolList().values())[0]
        style_tool(tool, style)
        tool.StyledText.SetExpression(expression(w["cards"]))
        made += 1
        log(f"  window {w['index']:>2} @{w['offset_frames']:>5}  "
            f"{len(w['cards'])} cards  pos={item.GetStart() - start_frame}")
    return {"titles": made, "windows": len(windows), "cards": len(cards_)}


def _frame_to_tc(frame: int, fps: float) -> str:
    f = int(round(fps))
    h, rem = divmod(int(frame), 3600 * f)
    m, rem = divmod(rem, 60 * f)
    s, fr = divmod(rem, f)
    return f"{h:02d}:{m:02d}:{s:02d}:{fr:02d}"
