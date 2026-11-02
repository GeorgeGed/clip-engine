import React from 'react';
import {AbsoluteFill, Img, staticFile, interpolate, spring,
        useCurrentFrame, useVideoConfig, Easing} from 'remotion';
import {TEXT} from './theme';

// The streamer's own chat, replayed over the thing he is looking at.
//
// THREE OF GEORGE'S NOTES REVERSE WHAT THE REFERENCE MEASURED, and that is
// his call on all three:
//
// 1. "it doesn't look animated at all, add the remotion stuff." The first
//    build was deliberately instant, because correlating R5's frames showed
//    its chat jumping a whole message height in ONE frame — 110/178/206/
//    220/240px, residual 2.0-2.9, no intermediate frames anywhere. That is
//    how Twitch's own chat renders and I argued an eased scroll would be
//    the tell. He has watched it and wants it animated. The measurement
//    stands as a record of what R5 does; it is no longer what we do.
// 2. "remove the border." The card, its 64px radius and the cyan shoulder
//    plate are gone. Nothing is drawn behind the text.
// 3. "make it so it APPEARS over what he's looking at on stream." So the
//    chat floats on the board rather than replacing it, and the board shows
//    through between the lines. That is what the text shadow is for — with
//    no panel, a coloured username over a busy roster board needs a ground,
//    and a shadow gives it one without drawing a box.
//
// HOW THE STACK PUSHES UP WITHOUT MEASURING ANYTHING. A new message has to
// displace the ones above it, and its height is unknown until the browser
// has wrapped it. The grid trick does it: a single-row grid whose
// `grid-template-rows` interpolates `0fr -> 1fr` animates from zero to the
// child's natural height, with the child clipped meanwhile. No ref, no
// measure pass, correct for every wrap. The gap animates with it or the
// spacing pops in before the text does.

const BAND = {x: 56, w: 716, top: 1060, bottom: 1620};
const SIZE = 46;
const LINE = 1.32;
const GAP = 30;
const BADGE = 32;
const IN_FRAMES = 11;

/** A window in which a graphic displaces the chat. */
export type Fade = {from: number; to: number; level: number};

export type Frag = {text: string; emote: string | null};
export type Msg = {t: number; author: string; colour: string;
                   badges: string[]; frags: Frag[]};

const SHADOW = '0 2px 7px rgba(0,0,0,0.95), 0 0 2px rgba(0,0,0,0.9)';

/** How present the chat is at time `t`: 1 alone, lower behind a graphic. */
const levelAt = (t: number, fades: Fade[]) => {
  let lv = 1;
  for (const f of fades) {
    // 0.35s to get out of the way, 0.5s to come back — leaving is quicker
    // than returning for the same reason an exit is quicker than an
    // entrance: the viewer is reading the graphic, not the chat.
    const a = interpolate(t, [f.from - 0.35, f.from], [1, f.level],
      {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
    const b = interpolate(t, [f.to, f.to + 0.5], [f.level, 1],
      {easing: Easing.out(Easing.quad),
       extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
    lv = Math.min(lv, t < f.from ? a : b);
  }
  return lv;
};

export const ChatScroll: React.FC<{
  messages: Msg[];
  badgeMap: Record<string, string>;
  fades?: Fade[];
}> = ({messages, badgeMap, fades = []}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const now = frame / fps;
  const shown = messages.filter((m) => m.t <= now && m.t > now - 400);
  const level = levelAt(now, fades);
  if (level < 0.004) return null;

  return (
    <AbsoluteFill style={{opacity: level}}>
      <div style={{
        position: 'absolute', left: BAND.x, top: BAND.top,
        width: BAND.w, height: BAND.bottom - BAND.top,
        display: 'flex', flexDirection: 'column', justifyContent: 'flex-end',
        overflow: 'hidden',
        fontFamily: TEXT, fontSize: SIZE, lineHeight: LINE,
        // a graphic is landing, so the chat goes soft as well as dim —
        // dimming alone leaves it legible and competing for the eye
        filter: level < 0.98 ? `blur(${((1 - level) * 2.4).toFixed(2)}px)` : undefined,
      }}>
        {shown.map((m, i) => {
          const age = (now - m.t) * fps;
          const p = spring({frame: Math.max(0, age), fps,
                            config: {stiffness: 170, damping: 20, mass: 0.5},
                            durationInFrames: IN_FRAMES});
          return (
            <div key={`${m.t}-${m.author}-${i}`} style={{
              display: 'grid',
              gridTemplateRows: `${p.toFixed(4)}fr`,
              marginTop: GAP * p,
            }}>
              <div style={{
                overflow: 'hidden',
                opacity: Math.min(1, p * 1.5),
                transform: `translateY(${((1 - p) * 16).toFixed(2)}px)`,
                color: '#FFFFFF', textShadow: SHADOW,
              }}>
                {m.badges.map((b) => badgeMap[b] ? (
                  <Img key={b} src={staticFile(badgeMap[b])} style={{
                    width: BADGE, height: BADGE, verticalAlign: '-5px',
                    marginRight: 9, borderRadius: 4,
                    filter: 'drop-shadow(0 2px 4px rgba(0,0,0,0.9))',
                  }} />
                ) : null)}
                <span style={{
                  color: m.colour, fontWeight: 700,
                  fontVariationSettings: '"wght" 700, "wdth" 100',
                }}>{m.author}</span>
                <span style={{color: m.colour, fontWeight: 700}}>: </span>
                {m.frags.map((f, k) => f.emote ? (
                  <Img key={k} src={f.emote} style={{
                    height: SIZE * 1.1, verticalAlign: '-11px', margin: '0 2px',
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
