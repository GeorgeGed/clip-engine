import React from 'react';
import {AbsoluteFill, Img, staticFile, interpolate, spring,
        useCurrentFrame, useVideoConfig, Easing} from 'remotion';
import {C, TEXT, RADIUS, WIDTHS} from './theme';

// THE MESSAGE HE IS ANSWERING, lifted out of chat and held while he answers.
//
// George: *"ideally we should have something where fns has seen the twitch
// chatter's question and we have an animation of it shown on screen while he
// answers it - then the twitch chat should come in like normal."*
//
// **THIS CARD MAKES A FACTUAL CLAIM ABOUT TWO REAL PEOPLE** — that this
// viewer asked this and the streamer answered it. Nothing else in the system
// asserts an interaction. A lexical-overlap score cannot establish one: a
// streamer and his chat talk about the same subject constantly and reuse the
// same words without either responding to the other, so a high overlap is
// the NULL hypothesis here, not evidence. `engine/chat_reaction.answering()`
// proposes pairs; they are judged and then adversarially refuted before any
// of them reaches this component. See AGENTS.md.
//
// IT IS THE SAME MATERIAL AS THE CHAT BOX, DELIBERATELY: Twitch's own
// `#18181B`, the chatter's own colour, square corners. A viewer has to read
// it as "a message from chat", and inventing a separate visual language for
// it would break that. What separates it from the chat box is SCALE AND
// POSITION, not styling — it is full width, centred, untilted and set 1.5x
// larger, where the chat box is a small tilted panel in the corner. A third
// tilt in one clip would also read as one repeated gesture, which this file
// already warns about for the story cards.
//
// The chat box is ABSENT while this is up (the windows are built around it)
// and returns underneath afterwards, which is the "then the twitch chat
// should come in like normal" half of the note.

const BOX = {x: (1080 - WIDTHS.full) / 2, y: 1080, w: WIDTHS.full};
const PAD = 34;
const NAME = 46;
const SIZE = 54;
const LINE = 1.26;
const BADGE = 34;
const IN = 16;

export type Frag = {text: string; emote: string | null};

export const QuestionCard: React.FC<{
  author: string;
  colour: string;          // the chatter's own, already lifted for readability
  badges?: string[];
  badgeMap?: Record<string, string>;
  frags: Frag[];
}> = ({author, colour, badges = [], badgeMap = {}, frags}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();

  // A DARK PANEL OVER THIS BOARD TRANSITIONS BY GEOMETRY, NEVER BY OPACITY —
  // the rule this file has now learned twice. Opacity reaches full inside the
  // first few frames and the movement does the rest.
  const p = spring({frame, fps, config: {stiffness: 150, damping: 18, mass: 0.6},
                    durationInFrames: IN});
  const out = interpolate(frame, [durationInFrames - 12, durationInFrames],
    [0, 1], {easing: Easing.in(Easing.quad),
             extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  const lift = (1 - p) * 40 + out * 26;
  const scale = (0.93 + 0.07 * p) * (1 - 0.03 * out);
  const alpha = Math.min(1, p * 5) * (1 - out);

  return (
    <AbsoluteFill style={{opacity: alpha < 0.02 ? 0 : 1}}>
      <div style={{
        position: 'absolute', left: BOX.x, top: BOX.y, width: BOX.w,
        background: C.twitchBg,
        borderRadius: RADIUS,
        padding: `${PAD}px ${PAD + 4}px`,
        fontFamily: TEXT, fontSize: SIZE, lineHeight: LINE,
        color: C.twitchText,
        overflowWrap: 'anywhere',
        transform: `translateY(${lift.toFixed(2)}px) scale(${scale.toFixed(4)})`,
        transformOrigin: '50% 40%',
        // the one place opacity IS used: only to erase the last 2% so the
        // composition does not end on a lit card, never as the transition
        opacity: alpha,
      }}>
        <div style={{marginBottom: 14, fontSize: NAME, fontWeight: 700,
                     fontVariationSettings: '"wght" 700'}}>
          {badges.map((b) => badgeMap[b] ? (
            <Img key={b} src={staticFile(badgeMap[b])} style={{
              width: BADGE, height: BADGE, verticalAlign: '-5px',
              marginRight: 9, borderRadius: 3,
            }} />
          ) : null)}
          <span style={{color: colour}}>{author}</span>
        </div>
        <div>{frags.map((f, k) => f.emote ? (
          <Img key={k} src={f.emote} style={{
            height: SIZE * 1.1, verticalAlign: '-10px', margin: '0 3px',
          }} />
        ) : (
          <span key={k}>{f.text}</span>
        ))}</div>
      </div>
    </AbsoluteFill>
  );
};
