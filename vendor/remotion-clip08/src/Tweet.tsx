import React from 'react';
import {AbsoluteFill, Img, useCurrentFrame, useVideoConfig, interpolate, spring, Easing} from 'remotion';
import {C, WIDTHS, RADIUS} from './theme';
import {PAPER, EXIT, useHold} from './motion';

/** The announcement, as a tilted card like the news stories.
 *
 *  George: "this still is cutting off the top part of the tweet". The old
 *  card was a PNG cropped below the author row, so the post appeared to
 *  start mid-sentence with no one attached to it. The crop now begins above
 *  the avatar and ends where the TEXT ends — two automated scans put the
 *  bottom edge mid-paragraph because a full line of white tweet text is as
 *  bright as a photograph, so the boundary was read off the frame instead.
 *
 *  NO SHADOW. The other story cards are white paper at 15.6:1 against the
 *  board, where a shadow is a real contact cue; this is a DARK-MODE
 *  screenshot — 82.4% of its pixels sit below luma 20 — so a
 *  rgba(0,0,0,0.92) bloom under it does nothing over board pixels at Y' 22.
 *  It is the same vestigial prosthetic the old dark glass panel was wearing.
 *  A 2px keyline is what actually separates a dark document from a dark
 *  board, which is the whole finding behind the new chassis.
 */
export const TweetCard: React.FC<{src: string; top: number; tilt: number}> =
({src, top, tilt}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const hold = useHold(EXIT.paper);

  const rot = spring({frame, fps, config: PAPER});
  const rise = interpolate(frame, [0, 18], [54, 0],
    {easing: Easing.out(Easing.poly(5)), extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  // EVIDENCE: it resolves from a blur, which is what sells a scale as depth
  const scale = interpolate(frame, [0, 22], [0.88, 1], {
    easing: Easing.bezier(0.34, 1.28, 0.64, 1),
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const blur = interpolate(frame, [0, 14], [7, 0],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const reveal = interpolate(frame, [2, 20], [0, 1],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  return (
    <AbsoluteFill style={{alignItems: 'center', paddingTop: top}}>
      <div style={{
        width: WIDTHS.full, borderRadius: RADIUS, overflow: 'hidden',
        border: `2px solid ${C.keyline}`, background: C.surfaceDeep,
        transform: `rotate(${(tilt * rot).toFixed(3)}deg) `
                 + `translateY(${(rise + 5 * hold).toFixed(2)}px) `
                 + `scale(${(scale * (1 + 0.010 * hold)).toFixed(4)})`,
        filter: blur > 0.05 ? `blur(${blur.toFixed(2)}px)` : undefined,
        opacity: interpolate(frame, [0, 6], [0, 1], {extrapolateRight: 'clamp'}),
        clipPath: `inset(0 0 ${((1 - reveal) * 100).toFixed(2)}% 0)`,
      }}>
        <Img src={src} style={{width: '100%', display: 'block'}} />
      </div>
    </AbsoluteFill>
  );
};
