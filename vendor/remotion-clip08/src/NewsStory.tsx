import React from 'react';
import {AbsoluteFill, Img, useCurrentFrame, useVideoConfig, interpolate, spring, Easing} from 'remotion';
import {C, SIZE, PAD, WIDTHS, SERIF, paperSurface} from './theme';
import {PAPER, EXIT, useHold, useStagger} from './motion';

// George: "use an actual news story headline for both and just add images of
// the players under the headline and make them both tilted." The published
// headline is a sentence and works as one; "PARTS WAYS AFTER FIVE YEARS" was
// VLR's verb chopped out of its sentence and set as a gold fragment under a
// name, which reads as a label nobody wrote.
//
// THIS CARD IS THE REFERENCE SURFACE, and it is not close. Measured against
// the real board pixels of the lower pane, the paper sits at **15.6:1** while
// every dark glass panel sat at 1.08:1. It is the only graphic that reads as
// having arrived from OUTSIDE the frame rather than being a region of the
// board, and the new chassis is specified so it stays 9.57:1 away from it.
// So the paper, the opposed tilts, the spring-driven tilt (it settles INTO
// its angle rather than being baked) and its shadow all stay. That shadow is
// now the only one in the whole system, which makes it a decision rather
// than a default.
//
// WHAT CHANGED:
//
// * THE HEADLINE IS A SERIF. It was Helvetica Neue 800 at 42px with
//   letterSpacing -0.8 — the most generic headline setting on macOS, and the
//   only lowercase text in the system, sharing its family with every
//   micro-label. A press card's authority is carried almost entirely by its
//   face. Nothing else in the clip is a serif, so one appearing reads as a
//   publication rather than an overlay. The -0.8 tracking goes too: it is an
//   optical-size correction borrowed from 100px display settings.
// * THE OUTLET IS A MARK, NOT A NAME. A 72px ink rule above the headline
//   replaces the `VLR.GG · 31 OCT` line — the same tracked micro-caps
//   attribution strip George called an ai-ism. Sourcing stays in the photo
//   manifest and in AGENTS.md; it does not need 15px grey type on the card.
// * IT FITS THE SAFE AREA AND EXITS UPWARD. At `top: 975` with 650px photos
//   it bottomed out at 1703 — 103px past the 1600 platform-UI line — and
//   then exited DOWN into it. And the tilt allowance was never computed: a
//   1008-wide card at 3.4 degrees lifts its raised corner `w * sin(tilt)` =
//   60px above its stated top, which is how `top: 975` rendered at 944 and
//   how the captions clipped it. Both are now solved rather than nudged.

export const NewsStory: React.FC<{
  headline: string;
  photos: {src: string}[];
  top: number; tilt: number;
  photoHeight?: number;
}> = ({headline, photos, top, tilt, photoHeight = 400}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const st = useStagger();
  const hold = useHold(EXIT.paper);

  // PAPER class: the rotation is underdamped (zeta 0.600, peak 1.0947), so
  // -3.4deg arrives via -4.4deg and settles — a sheet of paper dropping onto
  // a desk overshoots. Position is a SEPARATE ease-out-quint, because tying
  // both to one critically-damped spring is what made this card arrive like
  // every other card in the set.
  const rot = spring({frame, fps, config: PAPER});
  const rise = interpolate(frame, [0, 18], [54, 0],
    {easing: Easing.out(Easing.poly(5)), extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  return (
    <AbsoluteFill style={{alignItems: 'center', paddingTop: top}}>
      <div style={{
        ...paperSurface, width: WIDTHS.full,
        padding: `${PAD.tight + 4}px ${PAD.card}px ${PAD.chip - 6}px`,
        transform: `rotate(${(tilt * rot).toFixed(3)}deg) `
                 + `translateY(${(rise + 5 * hold).toFixed(2)}px)`,
        opacity: interpolate(frame, [0, 6], [0, 1], {extrapolateRight: 'clamp'}),
      }}>
        {/* the outlet, as a mark */}
        <div style={{width: 72, height: 3, background: C.ink, opacity: st(2)}} />

        {/* the published headline, verbatim, in sentence case */}
        <div style={{
          marginTop: 14, marginBottom: 14,
          fontFamily: SERIF, fontWeight: 600, fontSize: SIZE.headline - 10,
          fontVariationSettings: '"wght" 600, "opsz" 48',
          lineHeight: 1.08, letterSpacing: 0, color: C.ink, opacity: st(5),
        }}>{headline}</div>

        {/* the people it is about, under it */}
        <div style={{display: 'flex', gap: 10}}>
          {photos.map((p, i) => {
            const a = st(10 + i * 5);
            return (
              <div key={p.src} style={{
                flex: 1, position: 'relative', height: photoHeight,
                overflow: 'hidden', background: C.ink,
                opacity: a, transform: `translateY(${interpolate(a, [0, 1], [16, 0])}px)`,
              }}>
                {/* No name label. George: "this name part is unnecessary" —
                    the headline already names them, so a caption under the
                    photo restates it. The gradient scrim went with it, since
                    it existed only to seat the name. */}
                <Img src={p.src} style={{
                  width: '100%', height: '100%', objectFit: 'cover',
                  objectPosition: 'center 22%', display: 'block',
                  transform: `scale(${(1 + 0.014 * hold).toFixed(4)})`,
                }} />
              </div>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};
