import React from 'react';
import {AbsoluteFill, Img, useCurrentFrame, useVideoConfig, interpolate, spring, Easing} from 'remotion';
import {C, SIZE, PAD, WIDTHS, TEXT, TRACK, CAPTION_STROKE,
        figureStyle, contextStyle, surface} from './theme';
import {POP, FIGURE, useStagger} from './motion';

// The photos come from the four official VCT Flickr accounts through the
// quote desk's existing finder, which reads and logs each photo's licence —
// they are All Rights Reserved, used on the operator's own permission.
//
// The per-photo CREDIT LINE is gone from the card. George: "remove credits
// we have full permissions." It was also the smallest type in the project at
// 14px on a 1920-tall frame — 0.73% of frame height, next to 104px captions,
// about 1mm of cap height on a phone. By construction it was there to look
// like information rather than to be it, which is his own definition of the
// tell. The licence is still read and logged per photo in the manifest.

/** A player: photo, handle, and what just happened to them. */
export const PlayerCard: React.FC<{
  src: string; handle: string; team: string; line: string;
  stamp: string; top: number; side?: 'left' | 'right';
}> = ({src, handle, team, line, stamp, top, side = 'left'}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const st = useStagger();
  const panel = interpolate(frame, [0, 12], [0, 1],
    {easing: Easing.out(Easing.poly(5)), extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const land = spring({frame: Math.max(0, frame - 8), fps, config: FIGURE});
  // the portrait wipes in from the side it sits on
  const wipe = interpolate(frame, [4, 24], [0, 1],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  return (
    <AbsoluteFill style={{alignItems: 'center', paddingTop: top}}>
      <div style={{
        ...surface,
        display: 'flex', flexDirection: side === 'left' ? 'row' : 'row-reverse',
        width: WIDTHS.mid, alignItems: 'stretch',
        transform: `translateY(${interpolate(panel, [0, 1], [18, 0])}px)`,
        opacity: interpolate(frame, [0, 5], [0, 1], {extrapolateRight: 'clamp'}),
      }}>
        <div style={{
          width: 230, flexShrink: 0, position: 'relative', overflow: 'hidden',
          clipPath: `inset(0 ${side === 'left' ? (1 - wipe) * 100 : 0}% 0 `
                  + `${side === 'right' ? (1 - wipe) * 100 : 0}%)`,
        }}>
          <Img src={src} style={{
            width: '100%', height: '100%', objectFit: 'cover',
            objectPosition: 'center 22%', display: 'block',
          }} />
          {/* feathers the photo into the chassis so it has no hard edge.
              Matched to C.surface, which is why this cannot simply be
              re-pointed at a light surface — feathering a dark arena photo
              into a bone panel gives a haze. */}
          <div style={{
            position: 'absolute', inset: 0,
            background: side === 'left'
              ? `linear-gradient(90deg, rgba(0,0,0,0) 55%, ${C.surface} 100%)`
              : `linear-gradient(270deg, rgba(0,0,0,0) 55%, ${C.surface} 100%)`,
          }} />
        </div>

        <div style={{flex: 1, padding: PAD.card}}>
          {/* the accent is a key bar; the date is not a coloured pill */}
          <div style={{display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12,
                       opacity: st(3)}}>
            <span style={{width: 4, height: 24, background: C.accent}} />
            <span style={contextStyle}>{stamp} · {team}</span>
          </div>
          <div style={{
            ...figureStyle(84), lineHeight: 0.88, textTransform: 'uppercase',
            transform: `translateY(${interpolate(land, [0, 1], [14, 0])}px)`,
          }}>{handle}</div>
          <div style={{
            fontFamily: TEXT, fontWeight: 600, fontSize: SIZE.label, lineHeight: 1,
            fontVariationSettings: '"wght" 600, "wdth" 94',
            color: C.textPrimary, letterSpacing: TRACK.label,
            textTransform: 'uppercase', marginTop: 10, opacity: st(10),
          }}>{line}</div>
        </div>
      </div>
    </AbsoluteFill>
  );
};

/**
 * The clickbait line, sitting just under the facecam.
 *
 * George asked for "a line of text that says what the video is talking about
 * ... and include an emoji at the end ... slightly under his face cam."
 *
 * THE PILL IS GONE. It was `borderRadius: 999` over `rgba(8,10,14,0.80)`
 * with a backdrop blur and a 1px white border — the only element in the
 * project with a radius above 5, so it belonged to nothing, and it was the
 * first graphic a scroller saw, for 17 of 47 seconds. The line is now set
 * the way the CAPTIONS are set, which is the treatment George picked himself
 * after four style versions: heavy, white, hard black stroke, no box. That
 * survives the mint wall behind him and the Arsenal red with no container at
 * all, and it makes the hook and the captions one system instead of two.
 *
 * The emoji is why this has to be Remotion: PIL cannot render colour emoji,
 * and Chrome on macOS draws Apple Color Emoji natively.
 */
export const ClickbaitLine: React.FC<{text: string; emoji: string; top: number}> =
({text, emoji, top}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  // The one underdamped curve in the project (zeta 0.772, peak 1.0220) and
  // the only one that reads as alive. It fires at frame 13 and then re-fires
  // every four seconds — four events in 17s at zero cost, from a spring that
  // already existed. The TEXT stays dead still; it sits over his face.
  const kicks = [13, 253, 493, 733, 973];
  const last = kicks.filter((k) => frame >= k).pop();
  const pop = last === undefined
    ? 0
    : spring({frame: frame - last, fps, config: POP});
  const first = last === 13 || last === undefined;

  return (
    <AbsoluteFill style={{alignItems: 'center', paddingTop: top}}>
      <div style={{
        display: 'inline-flex', alignItems: 'center', gap: 14,
        opacity: interpolate(frame, [0, 8], [0, 1], {extrapolateRight: 'clamp'}),
      }}>
        <span style={{
          fontFamily: TEXT, fontWeight: 900, fontSize: 33, letterSpacing: 0.2,
          fontVariationSettings: '"wght" 900, "wdth" 96',
          color: C.textPrimary, whiteSpace: 'nowrap', textTransform: 'uppercase',
          WebkitTextStroke: CAPTION_STROKE, paintOrder: 'stroke fill',
        } as React.CSSProperties}>{text}</span>
        <span style={{
          fontSize: 38, lineHeight: 1, display: 'inline-block',
          transform: `scale(${interpolate(pop, [0, 1], [first ? 0.3 : 0.84, 1]).toFixed(3)}) `
                   + `rotate(${interpolate(pop, [0, 1], [first ? -22 : -10, 0]).toFixed(2)}deg)`,
        }}>{emoji}</span>
      </div>
    </AbsoluteFill>
  );
};
