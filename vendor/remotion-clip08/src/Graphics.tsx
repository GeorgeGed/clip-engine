import React from 'react';
import {Img, AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, spring, Easing} from 'remotion';
import {C, SIZE, PAD, WIDTHS, figureStyle, labelStyle, surface, well} from './theme';
import {EVIDENCE, FIGURE, EXIT, useHold, useStagger} from './motion';

// The graphics that come from OUTSIDE the footage. George: the screenshot
// crops are fine because they are real; the cards I DREW "just don't look
// good at all". CSS can do a type scale, a real surface and a clip-path
// reveal; PIL cannot. So these are built here and rendered with alpha.
//
// The `Eyebrow` component that used to head every card is DELETED, not
// hidden. It rendered a 16x3px accent dash followed by 21px weight-800 caps
// at `letterSpacing: 3.4` — "— VCT 2027-28 PARTNERSHIP CYCLE" — which is two
// separately-named tells in one line: an accent dash before a heading, and a
// tracked-out provenance strip. George named both. The `eyebrow` and
// `source` props went with it; leaving the strings at the call sites is how
// this comes back.

/** The sourced fact. The figure transitions 10 -> 8 rather than sitting. */
export const StatCard: React.FC<{
  from: string; to: string; label: string; top: number;
}> = ({from, to, label, top}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const st = useStagger();

  // FIGURE class: the panel arrives on a plain ease-out-quint, and the
  // figure lands SEPARATELY on the one underdamped spring in the project
  // (zeta 0.813, peak 1.0123). Before, panel and figure rose together on the
  // same critically-damped curve as every other card in the set.
  const panel = interpolate(frame, [0, 12], [0, 1],
    {easing: Easing.out(Easing.poly(5)), extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const land = spring({frame: Math.max(0, frame - 8), fps, config: FIGURE});

  const wipe = st(10);
  const swap = interpolate(frame, [22, 31], [0, 1],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  // The landing energy is a 1px accent rule wiping out from under the
  // figure, not a glow behind it. The old `textShadow: 0 0 34px
  // rgba(255,206,0,0.34)` appeared three times across two files, 6px and
  // 0.04 alpha apart — the stock number-goes-up treatment, and the only
  // lighting effect in an otherwise hard-edged set. Same accent, now marking
  // an event instead of sitting as a permanent aura.
  const rule = interpolate(frame, [29, 36], [0, 1],
    {easing: Easing.out(Easing.exp), extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  const fig = (v: string, extra: React.CSSProperties) => (
    <span style={{...figureStyle(SIZE.figure), ...extra}}>{v}</span>
  );

  return (
    <AbsoluteFill style={{alignItems: 'center', paddingTop: top}}>
      <div style={{
        ...surface, width: WIDTHS.mid, padding: PAD.card,
        transform: `translateY(${interpolate(panel, [0, 1], [18, 0])}px)`,
        opacity: interpolate(frame, [0, 5], [0, 1], {extrapolateRight: 'clamp'}),
      }}>
        {/* figures flush left, label on the same row — the old card was 864
            wide with ink spanning x 39-527, so it filled 56% of itself and
            left 337px of empty panel, which is the clearest "component
            slot" signal in the set. */}
        <div style={{display: 'flex', alignItems: 'flex-end', gap: 22}}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 20, position: 'relative',
            transform: `translateY(${interpolate(land, [0, 1], [14, 0])}px)`,
          }}>
            {fig(from, {
              opacity: interpolate(swap, [0, 1], [1, 0.22]),
              filter: `blur(${interpolate(swap, [0, 1], [0, 1.8])}px)`,
              transform: `translateY(${interpolate(swap, [0, 1], [0, -9])}px)`,
            })}

            {/* Tungsten had no arrow glyph and rendered tofu; this is the
                rectangle-plus-triangle that replaced it, kept because it
                wipes and a glyph cannot. */}
            <svg width={84} height={26} style={{overflow: 'visible'}}>
              <defs>
                <clipPath id="arrowwipe">
                  <rect x="0" y="0" width={84 * wipe} height="26" />
                </clipPath>
              </defs>
              <g clipPath="url(#arrowwipe)" fill={C.textSecondary}>
                <rect x="0" y="9" width="58" height="7" />
                <path d="M52 1 L82 12.5 L52 24 Z" />
              </g>
            </svg>

            {fig(to, {
              opacity: swap,
              transform: `translateY(${interpolate(swap, [0, 1], [16, 0])}px)`,
            })}

            <span style={{
              position: 'absolute', left: 0, bottom: -9, height: 3,
              width: `${100 * rule}%`, background: C.accent,
            }} />
          </div>

          <div style={{...labelStyle, paddingBottom: 10, opacity: st(14)}}>{label}</div>
        </div>
      </div>
    </AbsoluteFill>
  );
};

/**
 * A REAL screenshot crop, magnified and seated. Evidence, presented.
 *
 * `view` is the contiguous run of the PNG to show, in the PNG's own pixels.
 * The card used to render the crop at 1.00x native: `crop_strip.png` is
 * 1010x59 and its tallest ink band measured **21px against 88px captions**
 * — the exhibit's type 4.2x smaller than the subtitle over it. The whole
 * argument for these cards is "real data made illegible by the crop, so
 * magnify it", and at 1.00x it was still illegible.
 *
 * `view` must be CONTIGUOUS. The two figures the strip card points at sit in
 * blocks 3 and 6, which are not adjacent — stitching them together would
 * fabricate an adjacency the page does not have, which is doctoring an
 * exhibit. So the run shown is the one that CONTAINS both, and the accent
 * rules say which two matter.
 */
export const ExhibitFrame: React.FC<{
  src: string; width: number; top: number;
  view?: [number, number];
  /** Accent underlines, in the PNG's own pixels. Structure, never data. */
  rules?: [number, number][];
  /** Source x of the region this crop came from, 0-1080, so the card reads
   *  as pulled off that part of the board rather than simply appearing. */
  fromX?: number;
  marker?: {cx: number; cy: number; rx: number; ry: number};
}> = ({src, width, top, view, rules, fromX = 540, marker}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const hold = useHold(EXIT.card);

  // EVIDENCE class. All four of these were in `engine/overlays.
  // exhibit_reveal` and the React rebuild dropped every one, leaving the one
  // entrance with a reason to be unlike the others identical to them — and
  // it serves four of the eleven graphics.
  const s = spring({frame, fps, config: EVIDENCE});
  // overshoots slightly and settles, rather than appearing at size
  const scale = interpolate(frame, [0, 22], [0.78, 1], {
    easing: Easing.bezier(0.34, 1.28, 0.64, 1),
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  // resolving from a blur is what sells a scale as DEPTH rather than as a
  // size change
  const blur = interpolate(frame, [0, 14], [9, 0],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const travelX = interpolate(s, [0, 1], [(fromX - 540) * 0.35, 0]);
  const reveal = interpolate(frame, [2, 18], [0, 1],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  // a slow push into the document while it is held, so a 3.5s card is never
  // a still frame
  const push = 1 + 0.012 * hold;
  const lift = -7 * hold;

  // `view` and `rules` are FRACTIONS of the PNG's width, so they do not
  // depend on which crop this is (1010x59 for the strip, 760x431 for the
  // roster cards) and a re-crop at a different resolution does not move them.
  const inner = width - 2 * PAD.tight;
  const span = view ? view[1] - view[0] : 1;
  const k = inner / span;                       // px per unit image width
  const imgStyle: React.CSSProperties = view
    ? {width: k, display: 'block', marginLeft: -view[0] * k}
    : {width: '100%', display: 'block'};

  return (
    <AbsoluteFill style={{alignItems: 'center', paddingTop: top}}>
      <div style={{
        ...surface, width, padding: PAD.tight,
        transform: `translateX(${travelX.toFixed(2)}px) scale(${scale.toFixed(4)})`,
        filter: blur > 0.05 ? `blur(${blur.toFixed(2)}px)` : undefined,
        opacity: interpolate(frame, [0, 5], [0, 1], {extrapolateRight: 'clamp'}),
      }}>
        <div style={{
          ...well, position: 'relative',
          // the crop wipes up into place so the evidence arrives, not appears
          clipPath: `inset(0 0 ${((1 - reveal) * 100).toFixed(2)}% 0)`,
        }}>
          <div style={{
            position: 'relative', overflow: 'hidden',
            transform: `scale(${push.toFixed(4)}) translateY(${lift.toFixed(2)}px)`,
          }}>
            <Img src={src} style={imgStyle} />
            {rules && view ? (
              <div style={{position: 'absolute', inset: 0}}>
                {rules.map(([a, b], i) => {
                  const w = interpolate(frame, [20 + i * 4, 32 + i * 4], [0, 1],
                    {easing: Easing.out(Easing.exp),
                     extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
                  return (
                    <span key={i} style={{
                      position: 'absolute', bottom: 0, height: 5,
                      left: (a - view[0]) * k, width: (b - a) * k * w,
                      background: C.accent,
                    }} />
                  );
                })}
              </div>
            ) : null}
            {marker ? <MarkerRing {...marker} frame={frame} /> : null}
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};

/**
 * Hand-drawn marker ring — the only genuinely hand-made thing in the set, so
 * it is extended rather than restyled.
 *
 * The React rebuild lost one of its three documented characteristics, the
 * PEN TAPER, and introduced a bug with it: `strokeDasharray` used a 1.08
 * fudge constant for the path length (1037.6px) against a true polyline
 * length of 964.4px, so the ring finished drawing at p 0.93 and the last 2.4
 * frames showed nothing moving. Now the segments are summed for the real
 * length, the draw is eased on `q*q*(3-2*q)`, the path is split into three
 * sub-paths at falling stroke widths so the pen lifts, and the third
 * harmonic is back — noise alone looks like noise, not like a hand.
 */
const MarkerRing: React.FC<{cx: number; cy: number; rx: number; ry: number; frame: number}> =
({cx, cy, rx, ry, frame}) => {
  const raw = interpolate(frame, [34, 64], [0, 1],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const p = raw * raw * (3 - 2 * raw);

  const TURNS = 1.1;                 // a hand closes past its own start
  const N = 180;
  const pts: [number, number][] = [];
  for (let i = 0; i <= N; i++) {
    const a = Math.PI * 0.78 + (i / N) * Math.PI * 2 * TURNS;
    const w = 1
      + 0.035 * Math.sin(a * 2.3 + 1.1)
      + 0.022 * Math.sin(a * 3.7)
      + 0.014 * Math.sin(a * 1.3 + 0.4);
    pts.push([cx + Math.cos(a) * rx * w, cy + Math.sin(a) * ry * w]);
  }

  // real arc length, summed — not 2*pi*r*turns*1.08
  const seg: number[] = [0];
  for (let i = 1; i < pts.length; i++) {
    seg.push(seg[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
  }
  const LEN = seg[seg.length - 1];

  // three sub-paths at falling widths: the pen lifts toward the end
  const cuts = [0, 0.45, 0.8, 1];
  const widths = [9.5, 8, 5.5];
  const subs = widths.map((sw, k) => {
    const i0 = Math.round(cuts[k] * N);
    const i1 = Math.round(cuts[k + 1] * N);
    const slice = pts.slice(i0, i1 + 1);
    const len = seg[Math.min(i1, N)] - seg[i0];
    const drawn = Math.max(0, Math.min(len, p * LEN - seg[i0]));
    return {d: `M ${slice.map((q) => `${q[0].toFixed(1)},${q[1].toFixed(1)}`).join(' L ')}`,
            sw, len, drawn};
  });

  return (
    <svg style={{position: 'absolute', inset: 0, width: '100%', height: '100%',
                 overflow: 'visible'}}>
      {subs.map((s, k) => (
        <path key={k} d={s.d} fill="none" stroke={C.accent} strokeWidth={s.sw}
          strokeLinecap="round" strokeDasharray={s.len}
          strokeDashoffset={s.len - s.drawn}
          style={{filter: 'drop-shadow(0 2px 5px rgba(0,0,0,0.6))'}} />
      ))}
    </svg>
  );
};
