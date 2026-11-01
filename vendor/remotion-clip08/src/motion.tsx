import React from 'react';
import {AbsoluteFill, Easing, useCurrentFrame, useVideoConfig, interpolate} from 'remotion';

// George: "the remotion video effect animations need to slide out in a more
// efficient way ... right now it's just kind of jolting out of the frame."
//
// The first pass at this found the real cause — NOT ONE component referenced
// `durationInFrames`, so every card held at full opacity and Resolve cut to
// nothing in one frame — and then over-corrected in four separate ways. Each
// one is measured and each one is now reversed:
//
// 1. ANTICIPATION IS DELETED. The first version pulled the card 13px against
//    its exit direction first, on the theory that a counter-move is what
//    separates "it left" from "it was deleted". Across every published exit
//    curve in five design systems — Material (0.3,0,1,1) and (0.3,0,0.8,0.15),
//    Carbon (0.2,0,1,0.9) and (0.4,0.14,1,1), Atlassian (0.6,0,0.8,0.6),
//    Fluent (0.9,0.1,1,0.2) and (1,0,1,1) — **not one has a negative control
//    point.** Anticipation on an exit is published by nobody. It spent 4 of
//    18 frames moving the wrong way, and its own first frame jumped 5.74px
//    out of a dead-still hold (344 px/s): the jolt, relocated to the other
//    end of the exit.
//
// 2. TRAVEL IS HALVED, PER CARD. 118px on a 1080-wide frame is a card
//    physically leaving the canvas, which is literally what "jolting out of
//    the frame" described. Atlassian pairs SlideInTop8px with SlideOutTop4px
//    and SlideIn50PercentLeft with SlideOut15PercentLeft — every published
//    exit travels half its entrance distance or less, never more. So travel
//    is a per-card value derived from that card's own entrance, not a shared
//    constant.
//
// 3. 18 FRAMES IS LONGER THAN ANY PUBLISHED EXIT. Atlassian's ceiling is
//    200ms, Carbon's 240ms. Three tiers below, 100/200/250ms, with the
//    entrance 1.5-2x its own exit.
//
// 4. SCALE AND BLUR ARE OFF. The scale ran about `transformOrigin: 50% top`
//    — the card's top EDGE — so on a 728px-tall story card the centre drifted
//    21.8px UP while the exit travelled down, and the two partly cancelled.
//    The 5px isotropic blur was wrong twice: it blurred across the travel
//    axis as well as along it, and at ~6.5px/frame an honest motion blur is
//    ~3px, LESS than what was there.
//
// AND THE ONE THING THE FIRST PASS GOT WRONG ABOUT DARK CARDS. Measured in
// clip08_v42.mp4: a fixed box inside the KRU card goes 17.4 -> 17.0 -> 18.4
// -> 22.8 luma across the whole 0.3s exit — a change of 5.4 — because at
// 40-60% opacity the board's own team rows read THROUGH the panel while the
// card's crop and marker still overlap them. The card did not leave, it
// dematerialised into mud for six frames. So a chassis card does not fade:
// it stays FULLY OPAQUE and its clip plane sweeps across it in the exit
// direction, which is the exact inverse of the wipe its evidence arrives on.
// Paper and stroked type still fade, because a 9.57:1 card at 50% is still
// unambiguously a card.

/** 100ms / 200ms / 250ms at 60fps. */
export const EXIT = {chip: 6, card: 12, paper: 15, fade: 9} as const;

export type Dir = 'down' | 'up' | 'left' | 'right';
export type Kind = 'chassis' | 'paper' | 'plain';

const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);

// Carbon `exit.expressive`. Monotonic, and it ends at x=1, so the card is at
// maximum velocity the frame it disappears. An exit curve is a standard
// curve with its second control point pushed to x=1 — derived, not chosen.
const CURVE = {
  chip: Easing.bezier(0.8, 0, 0.78, 1),    // Fluent curveAccelerateMin
  card: Easing.bezier(0.4, 0.14, 1, 1),    // Carbon exit.expressive
  paper: Easing.bezier(0.9, 0.1, 1, 0.2),  // Fluent curveAccelerateMax
  plain: Easing.linear,
} as const;

/** How far through the exit we are: 0 before it starts, 1 on the last frame. */
export const useExitProgress = (frames: number) => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  const span = Math.max(1, Math.min(frames, durationInFrames - 1));
  return clamp01((frame - (durationInFrames - span)) / span);
};

/**
 * 0 -> 1 across the stretch between the entrance settling and the exit
 * starting, for the slow drift that keeps a held card from being a still.
 *
 * Measured on v42: frames between entrance settle and exit start were
 * ChipAmer 63, Tweet 161, StatCard 160, Pair 140, ExStrip 160, Ratio 148,
 * ExNrg 175, Grid 165, ExKru 184, StoryPrx 206, StorySen 191 — **29.2s of
 * 39.8s of graphic screen time dead still**, with the identical rhythm
 * eleven times: in, ~2.8s frozen, out. A PNG held for three seconds is what
 * a viewer reads as a template.
 *
 * This was specified once before — `engine/overlays.exhibit_reveal` drifted
 * ~9px while held "so a 3.5s card is never a still frame" — and the React
 * rebuild dropped it. Restored rather than reinvented.
 */
export const useHold = (exitFrames: number, settle = 30) => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  const end = durationInFrames - exitFrames;
  if (end <= settle) return 0;
  return clamp01((frame - settle) / (end - settle));
};

/**
 * Wrap a card in this and it leaves properly.
 *
 * `top`/`h` are the card's own rect in frame space, which is what lets the
 * clip plane sweep across the CARD rather than across the canvas.
 */
export const Stage: React.FC<{
  dir?: Dir;
  kind?: Kind;
  /** The card's top in px — same value the component takes as `top`. */
  top?: number;
  /** The card's height in px. Only the clip needs it; a rough value is fine. */
  h?: number;
  /** px of leave. Half this card's own entrance offset, rounded. */
  travel?: number;
  frames?: number;
  /** px of slow drift while held. 0 for anything short or over a face. */
  drift?: number;
  children: React.ReactNode;
}> = ({dir = 'down', kind = 'chassis', top = 1000, h = 400, travel = 14,
       frames = EXIT.card, drift = 6, children}) => {
  const p = useExitProgress(frames);
  const hold = useHold(frames);

  const e = interpolate(p, [0, 1], [0, 1], {
    easing: CURVE[kind === 'paper' ? 'paper' : kind === 'plain' ? 'plain' : 'card'],
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const d = travel * e;

  // 2px/s over a 3s hold: below the threshold where movement is noticed,
  // above the one where a frame looks dead.
  const sag = drift * hold;

  const x = dir === 'left' ? -d : dir === 'right' ? d : 0;
  const y = (dir === 'up' ? -d : dir === 'down' ? d : 0) + sag;

  // Material's fade pattern puts opacity on `motionEasingLinear` and reserves
  // the accelerate curve for displacement — the one thing the first version
  // explicitly did not do (it shaped the fade as `(p-0.35)/0.60` ^ 1.3).
  const opacity = kind === 'chassis'
    ? 1
    : interpolate(p, [0.35, 1], [1, 0],
        {easing: Easing.linear, extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  // The clip sweeps in the exit direction, eating the card from its trailing
  // edge as it goes, so a flat opaque slab is still legible as a departure.
  // Insets are in frame space because this is a full-frame layer, and only
  // the vertical exits need it — a chip is `plain`, small, and at 100ms has
  // no time to turn to mud.
  const FRAME_H = 1920;
  let clipPath: string | undefined;
  if (kind === 'chassis' && p > 0) {
    const px = (v: number) => (Math.round(v * 100) / 100).toFixed(2);
    clipPath = dir === 'up'
      ? `inset(0 0 ${px(FRAME_H - top - h + e * h)}px 0)`
      : `inset(${px(top + e * h)}px 0 0 0)`;
  }

  return (
    <AbsoluteFill style={{
      opacity,
      transform: `translate(${x.toFixed(2)}px, ${y.toFixed(2)}px)`,
      clipPath,
    }}>
      {children}
    </AbsoluteFill>
  );
};

/**
 * The entrance stagger every card uses. `st(d)` ramps 0->1 over nine frames
 * starting at frame `d`, which is the ~0.15s-apart cadence that makes a card
 * feel composed rather than pasted.
 */
export const useStagger = () => {
  const frame = useCurrentFrame();
  return (d: number, span = 9) =>
    interpolate(frame, [d, d + span], [0, 1],
      {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
};

// FOUR ENTRANCE CLASSES, keyed to what the object IS.
//
// Measured across all seven spring configs in the old build: zeta
// 1.061-1.344, **peak exactly 1.0000 in all seven**, f50 7-8 frames, f90
// 15-17, settle 29-32. Not one overshoots, and the "different" configs
// (damping 15/mass 0.5 vs 16/0.48 vs 16/0.46 vs 17/0.4) are within 2 frames
// of each other at every checkpoint — the same curve with decorative
// variation. Travel: 34, 30, 26, 26, 28, 28, 26, 30, 38, 38px. Eleven
// graphics in 47s that all arrived by rising about 30px.

/** EVIDENCE — a crop pulled off the board. Scale and blur, no rise. */
export const EVIDENCE = {stiffness: 150, damping: 18, mass: 0.6} as const;
/** FIGURE — the panel arrives, then the figure lands separately. */
export const FIGURE = {stiffness: 160, damping: 12, mass: 0.34} as const;
/** PAPER — underdamped, so -3.4deg arrives via -4.4deg and settles. */
export const PAPER = {stiffness: 120, damping: 11, mass: 0.7} as const;
/** The one underdamped curve in the project, and the only one that reads as
 *  alive. Kept from ClickbaitLine's emoji kick. */
export const POP = {damping: 9, mass: 0.34} as const;
