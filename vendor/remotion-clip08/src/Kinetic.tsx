import React from 'react';
import {AbsoluteFill, OffthreadVideo, useCurrentFrame, useVideoConfig, interpolate, spring} from 'remotion';
import {C, DISPLAY, UI, surface} from './theme';
const ACCENT = C.accent;

type Card = {start: number; end: number; text: string; emph: boolean};

// Style C — KINETIC TYPE. The type is the hero, not a subtitle: each card
// springs in at a scale the frame can feel, the emphasised ones take the
// accent and a tilt, and the words sit across the seam so they bind the two
// panes together instead of floating under them.

export const Kinetic: React.FC<{src: string; cards: Card[]}> = ({src, cards}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const t = frame / fps;

  const live = cards.filter((c) => t >= c.start && t < c.end);
  // the running claim, so a scroller landing mid-clip still knows the subject
  const kicker = t > 1.2 && t < 44 ? 'FNS · VCT JOB SECURITY' : null;

  return (
    <AbsoluteFill style={{backgroundColor: 'black'}}>
      <OffthreadVideo src={src} />

      {kicker && (
        <div
          style={{
            position: 'absolute', top: 735, left: 0, width,
            textAlign: 'center', fontFamily: 'Helvetica, Arial, sans-serif',
            fontWeight: 800, fontSize: 25, letterSpacing: 5,
            color: 'rgba(255,255,255,0.74)',
          }}
        >
          {kicker}
        </div>
      )}

      {live.map((c, i) => {
        const age = t - c.start;
        const s = spring({frame: Math.round(age * fps), fps, config: {damping: 13, mass: 0.42}});
        const scale = interpolate(s, [0, 1], [0.76, 1]);
        const lift = interpolate(s, [0, 1], [26, 0]);
        const tilt = c.emph ? interpolate(s, [0, 1], [-4.5, -2.2]) : 0;
        const out = interpolate(t, [c.end - 0.07, c.end], [1, 0.72], {
          extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
        });
        return (
          <div
            key={i}
            style={{
              position: 'absolute', top: height * 0.44, left: 0, width,
              display: 'flex', justifyContent: 'center',
              transform: `translateY(${lift}px) scale(${scale * out}) rotate(${tilt}deg)`,
            }}
          >
            <span
              style={{
                fontFamily: 'Impact, Haettenschweiler, "Arial Narrow", sans-serif',
                fontSize: c.emph ? 136 : 104,
                lineHeight: 0.96,
                letterSpacing: -1,
                color: c.emph ? ACCENT : '#fff',
                WebkitTextStroke: '9px #000',
                paintOrder: 'stroke fill',
                textAlign: 'center',
                maxWidth: width - 90,
                textShadow: '0 10px 28px rgba(0,0,0,0.55)',
              }}
            >
              {c.text}
            </span>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};
