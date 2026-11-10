"""The two data objects a clip is built from, and the split between them.

George, after clip 8 landed: *"let's finalize this logic now. Lock it in.
And let's develop this into other clips ... remember, I want to mass produce
these clips for different channels."*

**THE SPLIT IS THE WHOLE IDEA.** Everything clip 8 hardcoded falls into
exactly one of two buckets, and they have very different lifetimes:

* **`Channel`** — where the facecam sits in the source frame, how much
  browser chrome to crop, the seam, the grade. These are properties of ONE
  STREAMER'S LAYOUT and are measured once, then reused by every clip from
  that channel. Getting a new channel onboarded is this object and nothing
  else.
* **`Clip`** — which cut, where it starts, what the chat did, what (if
  anything) goes in the lower pane. Per clip, and nearly all of it derived
  rather than typed.

What is in NEITHER is the house style — captions, exits, punch geometry,
sound. Those live in `theme.tsx`, `motion.tsx` and the engine, because they
are the same on every clip for every channel by definition. If a value
would differ per channel it belongs in `Channel`; if it would differ per
clip it belongs in `Clip`; if it is a decision we made once about how our
clips look, it belongs in the code and NOT in a spec.

THE PART THAT IS NOT AUTOMATABLE, stated plainly so nobody mistakes this
for a button: `cards` is editorial. A sourced exhibit, a verified news
story, a crop of the right part of the board — those need a human deciding
what the clip is arguing and a verification pass on any name that goes on
screen. A clip with `cards: []` is fully automatic and is what clip 8 is
minus its two stories.
"""
from __future__ import annotations

import glob
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class Channel:
    """One streamer's layout. Measured once; reused by every clip."""
    name: str
    # the facecam's rect in the SOURCE frame, (x0, y0, x1, y1). Clip 8's is
    # (1456, 818, 1920, 1080) — a 464x262 region, 5.9% of frame, which is a
    # 3x upscale into the top pane and is why that facecam is soft.
    cam: tuple[int, int, int, int]
    # L2 seam. 0.42 is the measured house value (R1 0.418, R2 0.4422); R5,
    # the chat-overlay reference, runs 0.485 with a near-square facecam.
    seam: float = 0.42
    # source px of browser chrome to crop off the content pane. 92 removes
    # the tab and address bars, which otherwise sit right under the seam.
    chrome: int = 92
    fps: int = 60
    # ASC CDL on the facecam only — the lower pane is a document and lifting
    # contrast there costs text legibility for no gain.
    grade: dict | None = None
    # the three-act arc, as (start_frac, end_frac, cdl). Solved per channel
    # against a real white in the streamer's own room; see AGENTS.md.
    arc: list | None = None
    vod_id: str | None = None
    # "Never ship a source without a rights basis" is a [checked] gate in
    # this project and the batch path had no field for it. One of
    # explicit | affiliate | client_owned, plus who granted it and when.
    permission: str | None = None
    permission_note: str = ""

    @property
    def cam_wh(self) -> tuple[int, int]:
        return self.cam[2] - self.cam[0], self.cam[3] - self.cam[1]


@dataclass
class Clip:
    """One clip. Mostly derived; `cards` and `hook` are the human parts."""
    job: str                      # jobs/<job>
    index: int                    # 1-based, matches clips_1080/NN_*.mp4
    channel: str
    # where the narrative starts inside the cut file. The one-clip-one-
    # narrative rule lives here: a pivot is a boundary, so this trims the
    # previous topic off the front.
    in_point: float = 0.0
    # where the narrative ENDS inside the cut file. None keeps the whole
    # thing. The payoff is normally last, so trimming the front is the usual
    # lever — but "make it compact" needs both ends available.
    out_point: float | None = None
    # the clip's span in VOD time, for pulling its chat
    region: tuple[float, float] | None = None
    hook: str | None = None       # the clickbait line; written, not derived
    # THE FACECAM IS PER CLIP, NOT PER CHANNEL — a streamer moves their own
    # layout between scenes, and reusing clip 8's rect on clip 6 rendered a
    # top pane with no face in it. Left None it is DETECTED by
    # `engine.facecam`; set it to override a low-confidence detection.
    cam: tuple[int, int, int, int] | None = None
    emoji: str = "\U0001F633"
    cards: list = field(default_factory=list)   # EDITORIAL. see the docstring
    # filled in by the chat pass
    chat_mode: str | None = None  # 'continuous' | 'reactive' | None
    # THE BOOMS, IN CUT SECONDS, once a human has watched the clip.
    #
    # None means the automatic pick: `resolve_punch.boom_budget` scales the
    # count with duration and the loudest qualifying moments win. That is a
    # default for clips nobody has watched. It cannot be better than that,
    # because no acoustic metric separates the placements George keeps from
    # the ones he calls pointless — six verdicts against five metrics and 50
    # parameterisations, all recorded in `resolve_punch`.
    #
    # So this is the same arrangement `chat_mode` has: the measurement is a
    # default, and once he has watched one his call settles it. Each time is
    # snapped to the nearest measured candidate so it keeps its own attack
    # refinement; one with no candidate near it is taken literally and the
    # build log says so.
    booms: list[float] | None = None
    # ---- THE OPTIONS, and why these and not a Look object ----------------
    #
    # George: *"we need to add more options to the actual clips themselves,
    # some of them will just need basic cuts with different colour subtitles
    # and no chat, some will need no booms, some will need other advanced
    # cuts"*.
    #
    # Three of those four already existed — `chat_mode: "off"`, `booms: []`,
    # and the in/out points that make a "basic cut". Subtitle colour did
    # not, and `stories` could not be switched off at all.
    #
    # **THE SCOPE IS DELIBERATELY NARROW, and the reason is measured.** The
    # obvious move is a whole `Look` dataclass covering every style value.
    # Checked: `framings` has five live call sites and none passes `cycle`;
    # `_shot_index` four and none passes `min_shot`; `PUNCH_INSET` and
    # `PUNCH_HOLD` are typed TWICE, in `render_native` and `native_layout`,
    # behind a silent `except`; and `tighten.removals`' own defaults
    # (0.12/0.45) are stale against the shipped 0.08/0.20, so an unset field
    # would quietly revert dead-air policy. Exposing a value that is read
    # from two places gives Resolve one number and the native path another,
    # and `render_parity` would report that as the two RENDERERS
    # disagreeing — which is the "IT WAS NEVER RESOLVE" misdiagnosis, run
    # again. So only fields with ONE call site are here; the rest need the
    # duplicates collapsed first.
    #
    # The other rule: **expose a field only where a fatal check measures its
    # consequence.** Cue level qualifies — true peak caught the boom at
    # -0.41 once. Caption `y` does not: `engine.gates.check` never runs on
    # the production chain, so caption safe-area and caption-vs-graphic
    # overlap are not live, and a preset could put a story card under the
    # captions with nothing to catch it.
    #
    # Caption colours, by NAME from `engine.caption_colour`. `None` is the
    # house pair. The emphasis colour is the ~13% of cards drawn in accent;
    # `caption_fill` is the body. Both are measured against the caption's
    # own hard black stroke at a 4.5:1 floor, so "use our brand blue"
    # (#2E5CFF, 4.09:1) is REFUSED by name with the lifted alternative.
    caption_fill: str | None = None
    caption_emph: str | None = None
    # Whether `engine.story` may find a photo card for an org this clip
    # names. "auto" is the behaviour that shipped; "off" is the switch that
    # was missing. A card that names real people and cannot be turned off is
    # the wrong default on a quote desk.
    stories: str = "auto"
    notes: str = ""

    def source(self, root: Path) -> Path:
        hits = sorted(glob.glob(str(root / f"jobs/{self.job}/clips_1080/"
                                     f"{self.index:02d}_*.mp4")))
        if not hits:
            raise FileNotFoundError(
                f"no clips_1080/{self.index:02d}_*.mp4 under jobs/{self.job}")
        return Path(hits[0])

    def words(self, root: Path) -> Path:
        return root / f"jobs/{self.job}/words/{self.index:02d}.json"

    @property
    def slug(self) -> str:
        return f"{self.job}-{self.index:02d}"


def load(path: str | Path) -> tuple[Clip, Channel]:
    d = json.loads(Path(path).read_text())
    ch = Channel(**d["channel"])
    c = Clip(**d["clip"])
    if c.region:
        c.region = tuple(c.region)
    if c.cam:
        c.cam = tuple(c.cam)
    return c, ch


def save(path: str | Path, clip: Clip, channel: Channel) -> None:
    Path(path).write_text(json.dumps(
        {"channel": asdict(channel), "clip": asdict(clip)}, indent=1))
