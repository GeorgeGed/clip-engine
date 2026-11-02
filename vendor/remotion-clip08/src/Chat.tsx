import React from 'react';
import {AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {TEXT} from './theme';

// The streamer's own chat, replayed under the facecam.
//
// George, on a reference Short built this way: "i think this is good ...
// overlay his stream chat live so you can their reaction - see if you can
// overlay the stream in real time as an animation on the bottom half."
//
// MEASURED OFF THAT REFERENCE, and the important one is the last:
//
//   seam              y 932 (0.485) — its facecam is taller than our 0.42
//   card              x 212-865, 654 wide, top ~1055, running to the frame
//                     bottom; near-black, large top radius, and a CYAN
//                     plate behind it with square corners so two triangles
//                     of colour show at the shoulders
//   line pitch        68px inside a message
//   message gap       43px, so a one-line message occupies 111px
//   rate              ~75 messages/min
//
//   **IT DOES NOT SCROLL.** Correlating successive frames, the stack moves
//   in exactly ONE frame per message, by a whole message height — measured
//   jumps of 110, 178, 206, 220 and 240px with a post-shift residual of
//   2.0-2.9, i.e. the new state is already fully formed. Ten jumps in eight
//   seconds and no intermediate frames anywhere. That is how Twitch's own
//   chat renders, and it is why the reference reads as chat rather than as
//   a graphic. An eased scroll would be the tell. So: no easing, no fade-in,
//   no slide. The only thing that moves is the stack, instantly.
//
// The layout is a bottom-anchored flex column inside a clipped card, so the
// browser does the pushing-up for free and a message that overruns the top
// is cut off mid-line exactly as it is in the reference. No manual
// measurement of text height, which would be wrong for every wrap.

const CARD = {x: 213, w: 654, top: 985, bottom: 1920};
const PAD = 31;
const SIZE = 50;
const LINE = 68 / 50;              // the reference's 68px pitch, as a ratio
const GAP = 43;
const BADGE = 36;

export type Frag = {text: string; emote: string | null};
export type Msg = {t: number; author: string; colour: string;
                   badges: string[]; frags: Frag[]};

export const ChatScroll: React.FC<{
  messages: Msg[];
  badgeMap: Record<string, string>;
  /** seconds of chat to show before the clip starts, so it opens mid-flow
   *  rather than on an empty card */
  preroll?: number;
}> = ({messages, badgeMap, preroll = 8}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const now = frame / fps;
  const shown = messages.filter((m) => m.t <= now && m.t > now - 400);

  return (
    <AbsoluteFill>
      {/* the cyan plate: square corners, so it shows only at the shoulders */}
      <div style={{
        position: 'absolute', left: CARD.x, top: CARD.top,
        width: CARD.w, height: CARD.bottom - CARD.top,
        background: '#A1F0F0',
      }} />
      <div style={{
        position: 'absolute', left: CARD.x, top: CARD.top,
        width: CARD.w, height: CARD.bottom - CARD.top,
        background: '#070C11',
        borderTopLeftRadius: 64, borderTopRightRadius: 64,
        overflow: 'hidden',
        display: 'flex', flexDirection: 'column', justifyContent: 'flex-end',
        padding: `0 ${PAD}px ${PAD}px`,
        fontFamily: TEXT, fontSize: SIZE, lineHeight: LINE,
      }}>
        {shown.map((m, i) => (
          <div key={`${m.t}-${m.author}-${i}`} style={{marginTop: GAP, color: '#FFFFFF'}}>
            {m.badges.map((b) => badgeMap[b] ? (
              <Img key={b} src={staticFile(badgeMap[b])} style={{
                width: BADGE, height: BADGE, verticalAlign: '-6px',
                marginRight: 10, borderRadius: 4,
              }} />
            ) : null)}
            <span style={{
              color: m.colour, fontWeight: 700,
              fontVariationSettings: '"wght" 700, "wdth" 100',
            }}>{m.author}</span>
            <span style={{color: m.colour, fontWeight: 700}}>: </span>
            {m.frags.map((f, k) => f.emote ? (
              <Img key={k} src={f.emote} style={{
                height: SIZE * 1.1, verticalAlign: '-12px', margin: '0 2px',
              }} />
            ) : (
              <span key={k}>{f.text}</span>
            ))}
          </div>
        ))}
      </div>
    </AbsoluteFill>
  );
};
