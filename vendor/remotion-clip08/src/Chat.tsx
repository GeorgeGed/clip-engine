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
// IT IS BLACK AGAIN, AND IT IS MOUNTED, AND THOSE ARE ONE DECISION.
//
// George: "the twitch chat needs to stay black with the normal colours of
// the twitch chatters."
//
// The blue panel with white usernames was a graphic that QUOTED chat. This
// is chat: Twitch's own `#18181B` and the chatters' own colours. But a
// near-black panel on this near-black board is the 1.08:1 defect the palette
// pass deleted four devices for — measured here, its outline is
// distinguishable along only **7.2% of its own perimeter** (#070C11 7.0%,
// pure black 7.2%), so the box and the tilt both disappear into the roster
// rows. `C.blue` reads 3.41:1 there with **97.5% of the outline visible**.
//
// So the black card sits on a blue PLATE: square corners against the card's
// top radius, so the blue shows as a rule down the sides and as two
// triangles at the shoulders. That is R5's own construction — its near-black
// card sits on a cyan plate with square corners — in the Polymarket palette,
// and it is ONE element carrying the edge rather than a hairline, a bloom,
// an inset highlight and a rule stacked on a panel nobody can see.
//
// The drop shadow went with the blue. A rgba(0,0,0,0.55) bloom does nothing
// over board pixels at Y' 22, which is the vestigial prosthetic this file
// keeps warning about.

const BOX = {x: 64, y: 1090, w: 580, h: 420};
const MOUNT = 12;         // how much blue shows around the card
const CARD_R = 52;        // R5's top radius, scaled to our 580 (it ran ~64 at 654)
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
      {/* THE PLATE. Square corners, and the card's radius is what turns it
          from a keyline into a mount. */}
      <div style={{
        position: 'absolute',
        left: BOX.x - MOUNT, top: BOX.y - MOUNT,
        width: BOX.w + MOUNT * 2, height: BOX.h + MOUNT * 2,
        background: C.blue,
        borderRadius: RADIUS,
        transform: `translateY(${lift.toFixed(2)}px) scale(${scale.toFixed(4)}) `
                 + `rotate(${(TILT * p).toFixed(3)}deg)`,
        // THE SAME PAGE POINT AS THE CARD'S, expressed in the plate's own
        // box. '50% 60%' of the plate is 9.6px below '50% 60%' of the card,
        // and at -2.4deg that shears the two apart — which rendered as a
        // mount visibly thicker on the top-left than on the bottom-right.
        transformOrigin: `${(BOX.w / 2 + MOUNT).toFixed(1)}px `
                       + `${(BOX.h * 0.6 + MOUNT).toFixed(1)}px`,
      }} />

      <div style={{
        position: 'absolute', left: BOX.x, top: BOX.y,
        width: BOX.w, height: BOX.h,
        // Twitch's own dark chat column. Not a restyle of it.
        background: C.twitchBg,
        borderRadius: `${CARD_R}px ${CARD_R}px 0 0`,
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
