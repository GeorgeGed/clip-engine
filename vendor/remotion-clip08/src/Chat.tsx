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
// **I over-read "remove the border" last time.** He was pointing at R5's
// chrome — the 64px radius and the cyan shoulder plate — not asking for the
// chat to be set loose on the board. Borderless over a busy roster board
// means the text has no ground and the pane has no owner. A box fixes both,
// and a SMALL box is what satisfies "always keep the bottom screen for what
// fns is looking at": the board stays the pane's subject and the chat is a
// visitor on it.
//
// 580x420 against the old 716-wide full-height band, 36px type against 46.
// It occupies 23% of the content pane where the borderless version
// effectively claimed all of it.
//
// TILTED, on the R4 precedent already in docs/SKILLS.md — 4-8 degrees with
// a shadow is what stops a rectangle reading as a UI panel. -2.4 here,
// shallower than the story cards' -3.4/+3.1 so three tilted things in one
// clip do not read as one repeated gesture, and spring-driven so it settles
// into the angle rather than arriving at it.

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
                   badges: string[]; frags: Frag[]};

/**
 * PRESENT OR ABSENT, NEVER SEE-THROUGH.
 *
 * The previous build dimmed this box to 0.32 behind a drawn card, and both
 * its transition states were unreadable: at partial opacity the roster rows
 * read straight through the panel and the text lost its ground. That is the
 * same finding already written down for card exits — a dark panel over this
 * board must not fade — and it was repeated here.
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
        background: C.surfaceDeep,
        border: `2px solid ${C.keyline}`,
        borderRadius: RADIUS,
        boxShadow: '0 22px 48px -16px rgba(0,0,0,0.92)',
        overflow: 'hidden',
        display: 'flex', flexDirection: 'column', justifyContent: 'flex-end',
        padding: `0 ${PAD}px ${PAD}px`,
        fontFamily: TEXT, fontSize: SIZE, lineHeight: LINE,
        transform: `translateY(${lift.toFixed(2)}px) scale(${scale.toFixed(4)}) `
                 + `rotate(${(TILT * p).toFixed(3)}deg)`,
        transformOrigin: '50% 60%',
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
                color: '#FFFFFF',
              }}>
                {m.badges.map((b) => badgeMap[b] ? (
                  <Img key={b} src={staticFile(badgeMap[b])} style={{
                    width: BADGE, height: BADGE, verticalAlign: '-4px',
                    marginRight: 7, borderRadius: 3,
                  }} />
                ) : null)}
                <span style={{
                  color: m.colour, fontWeight: 700,
                  fontVariationSettings: '"wght" 700, "wdth" 100',
                }}>{m.author}</span>
                <span style={{color: m.colour, fontWeight: 700}}>: </span>
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
