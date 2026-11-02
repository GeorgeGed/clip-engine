import React from 'react';
import {AbsoluteFill, Img, staticFile, interpolate, spring,
        useCurrentFrame, useVideoConfig, Easing} from 'remotion';
import {C, TEXT, RADIUS} from './theme';

// The streamer's own chat, in a box, over the thing he is looking at.
//
// George: "i didn't mean the twitch chat should be overlayed completely on
// the screen, it should be inside of a box so you can see the text itself,
// im just saying always keep the bottom screen for what fns is looking at -
// tilt the chat slightly put it on an axis a bit ... make the twitch chat a
// bit smaller too, make sure it has animations coming in and out."
//
// **I over-read "remove the border" once.** He was pointing at R5's chrome —
// the 64px radius and the cyan shoulder plate — not asking for the chat to
// be set loose on the board. Borderless over a busy roster board means the
// text has no ground and the pane has no owner. A box fixes both, and a
// SMALL box is what satisfies "always keep the bottom screen for what fns is
// looking at": the board stays the pane's subject and the chat is a visitor.
//
// 580x420 against the old 716-wide full-height band, 36px type against 46.
// It occupies 23% of the content pane where the borderless version
// effectively claimed all of it.
//
// TILTED, on the R4 precedent already in docs/SKILLS.md — 4-8 degrees with a
// shadow is what stops a rectangle reading as a UI panel. -2.4 here,
// shallower than the story cards' -3.4/+3.1 so three tilted things in one
// clip do not read as one repeated gesture, and spring-driven so it settles
// into the angle rather than arriving at it.
//
// ─────────────────────────────────────────────────────────────────────────
// TWITCH'S OWN BLACK, AND NOTHING DRAWN ON IT.
//
// George: "the twitch chat needs to stay black with the normal colours of
// the twitch chatters" — then, on the mounted version: "twitch chat does
// not need a blue border."
//
// The blue panel with white usernames was a graphic that QUOTED chat. This
// is chat: Twitch's own `#18181B`, the chatters' own colours, square
// corners like Twitch's own column, and no border, no plate, no shadow.
//
// WHAT THAT COSTS, recorded rather than argued, because it was measured
// before he ruled on it: against the real board under this footprint the
// panel reads 1.03:1 and its OUTLINE is distinguishable along about 7% of
// its own perimeter, so the edge and the tilt are nearly invisible and the
// box reads as its text block rather than as a box. The blue plate (R5's
// own construction) fixed that at 97.5%. He has seen both and wants it
// bare, so bare it is — the fill still gives the text its ground, which is
// the job the box came back for, and the shadow goes because a
// rgba(0,0,0,0.55) bloom does nothing over board pixels at Y' 22.
//
// IT NO LONGER CYCLES. George: "why does it randomly disappear and come
// back at the start of the video? ... keep the twitch chat in place." The
// 9s-on / 0.9s-off cycle punctuated nothing — it was an arbitrary clock on
// a pane whose board never changes — so the chat is now ONE presence for
// the whole clip. It does not need to dodge the two story cards: measured
// off their own alpha, each covers **100% of this footprint at alpha > 250**,
// so a card lands on the chat and lifts off it.

const BOX = {x: 64, y: 1090, w: 580, h: 420};
const TILT = -2.4;
const PAD = 22;
const SIZE = 36;
const LINE = 1.3;
const GAP = 22;
const BADGE = 26;
const IN_FRAMES = 11;

/** A stretch of the clip where the chat is on screen. */
export type Win = {from: number; to: number};

export type Frag = {text: string; emote: string | null};
export type Msg = {t: number; author: string; colour: string;
                   display?: string; badges: string[]; frags: Frag[]};

/**
 * PRESENT OR ABSENT, NEVER SEE-THROUGH.
 *
 * An early build dimmed this box to 0.32 behind a drawn card, and both its
 * transition states were unreadable: at partial opacity the roster rows read
 * straight through the panel and the text lost its ground. That is the same
 * finding already written down for card exits — a dark panel over this board
 * must not fade — and it was repeated here. It matters MORE now that the
 * panel is black again, not less.
 *
 * So the box is opaque the whole time it exists. `presence` drives SHAPE
 * only: a lift, a scale and the tilt settling in. Opacity reaches full in
 * the first quarter of the entrance and stays there, so there is never a
 * frame where the board is visible through the box.
 */
const presenceAt = (t: number, wins: Win[]) => {
  let p = 0;
  for (const w of wins) {
    const inAt = interpolate(t, [w.from, w.from + 0.34], [0, 1],
      {easing: Easing.out(Easing.back(1.5)),
       extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
    const outAt = interpolate(t, [w.to - 0.26, w.to], [1, 0],
      {easing: Easing.in(Easing.quad),
       extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
    p = Math.max(p, Math.min(inAt, outAt));
  }
  return p;
};

export const ChatScroll: React.FC<{
  messages: Msg[];
  badgeMap: Record<string, string>;
  windows?: Win[];
}> = ({messages, badgeMap, windows = []}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const now = frame / fps;
  const shown = messages.filter((m) => m.t <= now && m.t > now - 400);
  const p = presenceAt(now, windows);
  if (p < 0.004) return null;

  // the box's own arrival: it rises, scales up and settles into its tilt.
  // Opacity is NOT part of it beyond the first quarter — see presenceAt.
  const lift = (1 - p) * 34;
  const scale = 0.90 + 0.10 * p;

  return (
    <AbsoluteFill style={{opacity: Math.min(1, p * 4)}}>
      <div style={{
        position: 'absolute', left: BOX.x, top: BOX.y,
        width: BOX.w, height: BOX.h,
        // Twitch's own dark chat column. Not a restyle of it.
        background: C.twitchBg,
        // Square, like Twitch's own column and like every other card in the
        // system. The 52px top radius only ever existed to cut the blue
        // plate into R5's shoulder triangles; with the plate gone it is a
        // sixth radius in a system whose geometry is RADIUS = 0.
        borderRadius: RADIUS,
        overflow: 'hidden',
        display: 'flex', flexDirection: 'column', justifyContent: 'flex-end',
        padding: `0 ${PAD}px ${PAD}px`,
        // Twitch's own UI face is Inter, so `TEXT` is already the right one.
        fontFamily: TEXT, fontSize: SIZE, lineHeight: LINE,
        // A pasted link is one unbreakable token, and at 580px wide it ran
        // straight through the padding and was clipped mid-word by the
        // panel edge — which reads as a broken render, not as chat.
        overflowWrap: 'anywhere',
        transform: `translateY(${lift.toFixed(2)}px) scale(${scale.toFixed(4)}) `
                 + `rotate(${(TILT * p).toFixed(3)}deg)`,
        transformOrigin: `${(BOX.w / 2).toFixed(1)}px ${(BOX.h * 0.6).toFixed(1)}px`,
      }}>
        {shown.map((m, i) => {
          // The message arrival George approved: a spring, a 14px rise and a
          // grid row growing 0fr -> 1fr, which animates to the child's
          // natural height without anyone measuring the wrap.
          const age = (now - m.t) * fps;
          const q = spring({frame: Math.max(0, age), fps,
                            config: {stiffness: 170, damping: 20, mass: 0.5},
                            durationInFrames: IN_FRAMES});
          return (
            <div key={`${m.t}-${m.author}-${i}`} style={{
              display: 'grid',
              gridTemplateRows: `${q.toFixed(4)}fr`,
              marginTop: GAP * q,
            }}>
              <div style={{
                overflow: 'hidden',
                opacity: Math.min(1, q * 1.5),
                transform: `translateY(${((1 - q) * 14).toFixed(2)}px)`,
                color: C.twitchText,
              }}>
                {m.badges.map((b) => badgeMap[b] ? (
                  <Img key={b} src={staticFile(badgeMap[b])} style={{
                    width: BADGE, height: BADGE, verticalAlign: '-4px',
                    marginRight: 7, borderRadius: 3,
                  }} />
                ) : null)}
                {/* THE CHATTER'S OWN COLOUR. `display` is that colour with
                    its lightness raised to clear 4.5:1 on #18181B, hue and
                    saturation untouched — which is not a liberty, it is what
                    Twitch itself renders: "Readable Colors" is ON by default
                    in dark mode, so #0000FF is already lifted on the viewer's
                    own screen. Measured here, 17 of 41 names (41%) sat under
                    the floor raw, and only four move enough to see.
                    `colour` keeps the raw value so the record stays true. */}
                <span style={{
                  color: m.display ?? m.colour, fontWeight: 700,
                  fontVariationSettings: '"wght" 700',
                }}>{m.author}</span>
                <span style={{fontWeight: 700}}>: </span>
                {m.frags.map((f, k) => f.emote ? (
                  <Img key={k} src={f.emote} style={{
                    height: SIZE * 1.1, verticalAlign: '-9px', margin: '0 2px',
                  }} />
                ) : (
                  <span key={k}>{f.text}</span>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
