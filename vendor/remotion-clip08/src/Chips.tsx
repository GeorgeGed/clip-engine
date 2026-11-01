import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, spring, Easing} from 'remotion';
import {C, SIZE, PAD, WIDTHS, figureStyle, labelStyle, contextStyle,
        surface, TEXT, TRACK} from './theme';
import {FIGURE, useStagger} from './motion';

// George: "I like the fact that we're kind of having pop-ups like every other
// second. I think that keeps retention quite well." Eleven graphics in 47s,
// roughly one every four seconds. Nothing here argues for fewer — the earlier
// "way too much" note was about EFFECTS, and the rule that makes density safe
// is that every figure is read off the board or independently sourced and
// nothing on screen is a phrase I wrote.
//
// WHAT CHANGED IN THIS FILE, all of it named by George or measured:
//
// * The `note` prop is GONE from all four cards that had it. RatioBar's was
//   still rendering at 19.40s in the delivered cut — 18px grotesque, weight
//   600, letterSpacing 1.5, "VCT ROSTER BOARD · ALL REGIONS" — which is
//   exactly the tracked-out micro-caps provenance strip he pointed at and
//   called "an ai-ism design". The prop goes with the render, because
//   leaving the strings at the call sites is how it comes back.
// * NO FIGURE IS COLOURED. In PairCounter the gold figure was 274; twenty
//   seconds later in RatioBar the gold figure was 32 and 274 was white — the
//   same two numbers, opposite assignment, eight seconds apart. Gold also
//   marked the eyebrow dash, the date chip, a chip border, the bar fill, the
//   highlighted row and the sub-line. An accent on everything marks nothing.
// * The three `textShadow: 0 0 34-40px rgba(255,206,0,...)` glows are gone.
// * Figures are Archivo, not Impact. `fontVariantNumeric: 'tabular-nums'` was
//   a no-op on Impact (its GSUB has only `locl`; digit advances span 30%), so
//   CounterCard's 0->274 roll shifted up to 28px per frame and PairCounter's
//   274 column swung 52px while the static 139 held still. Archivo's digits
//   measure 575-577/1000 upm — a 0.35% spread — with a real `tnum`.

/**
 * Small, one figure, slides in from the side it is anchored to.
 *
 * This is the FIRST graphic in the clip and it was the rejected combination
 * assembled: `borderRadius: 4`, a `boxShadow`, and `borderLeft: '4px solid
 * #FFCE00'` with `overflow: hidden` from the surface token, so the gold
 * bar's own ends were rounded off. It read as the selected-row indicator in
 * a settings list, and it set the register for everything after it.
 *
 * With a flat opaque square chassis a chip needs no rule to separate it from
 * the board, so the side anchoring is expressed with POSITION — the chip
 * bleeds off the frame edge, reading as pushed in from outside — rather than
 * with a stripe.
 */
export const StatChip: React.FC<{
  figure: string; label: string; side: 'left' | 'right'; top: number;
}> = ({figure, label, side, top}) => {
  const frame = useCurrentFrame();
  // A tab SLIDES; it does not materialise. 9 frames in, 6 out, so 15 of 110
  // frames are in transition instead of 47 — and no opacity fade at all.
  const dx = interpolate(frame, [0, 9], [side === 'left' ? -56 : 56, 0],
    {easing: Easing.out(Easing.exp), extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  return (
    <AbsoluteFill style={{
      alignItems: side === 'left' ? 'flex-start' : 'flex-end',
      paddingTop: top,
    }}>
      <div style={{
        ...surface, display: 'flex', alignItems: 'baseline', gap: 16,
        padding: `${PAD.chip}px ${PAD.card}px`,
        // bleeds off the frame edge, so it is a tab pushed in from outside
        marginLeft: side === 'left' ? -24 : 0,
        marginRight: side === 'right' ? -24 : 0,
        transform: `translateX(${dx.toFixed(2)}px)`,
      }}>
        <span style={figureStyle(62)}>{figure}</span>
        <span style={{...labelStyle, fontSize: SIZE.context}}>{label}</span>
      </div>
    </AbsoluteFill>
  );
};

/** A figure that counts up — the number does the work, so it holds a beat. */
export const CounterCard: React.FC<{
  to: number; label: string; top: number; countFrames?: number;
}> = ({to, label, top, countFrames = 46}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const panel = interpolate(frame, [0, 12], [0, 1],
    {easing: Easing.out(Easing.poly(5)), extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const land = spring({frame: Math.max(0, frame - 8), fps, config: FIGURE});
  const p = interpolate(frame, [6, 6 + countFrames], [0, 1],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const shown = Math.round(to * (1 - Math.pow(1 - p, 3)));
  const rule = interpolate(frame, [6 + countFrames - 4, 6 + countFrames + 5], [0, 1],
    {easing: Easing.out(Easing.exp), extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  return (
    <AbsoluteFill style={{alignItems: 'center', paddingTop: top}}>
      <div style={{
        ...surface, padding: `${PAD.card}px ${PAD.card + 12}px`, textAlign: 'center',
        transform: `translateY(${interpolate(panel, [0, 1], [18, 0])}px)`,
        opacity: interpolate(frame, [0, 5], [0, 1], {extrapolateRight: 'clamp'}),
      }}>
        <div style={{
          ...figureStyle(SIZE.figure),
          transform: `translateY(${interpolate(land, [0, 1], [14, 0])}px)`,
        }}>{shown}</div>
        <div style={{position: 'relative', height: 3, margin: '10px 0 8px'}}>
          <span style={{
            position: 'absolute', left: '50%', transform: 'translateX(-50%)',
            height: 3, width: `${100 * rule}%`, background: C.accent,
          }} />
        </div>
        <div style={labelStyle}>{label}</div>
      </div>
    </AbsoluteFill>
  );
};

/**
 * Two quantities as bars, so the ratio is SEEN rather than read.
 *
 * The old version rendered the remainder as a 7px diagonal candy-stripe
 * (`repeating-linear-gradient(135deg, rgba(255,255,255,.40) 0 7px, ...)`) in
 * a 20px track at radius 2, with the gold fill butted straight against it.
 * That is the default "no data / projected" hatch in every charting library,
 * so the 274 read as ABSENT rather than as the larger quantity; and with no
 * gap, a 10.5% fill against a continuous bar read as a 10%-complete progress
 * bar. Both are the opposite of the argument.
 *
 * Two solid bars, 8px apart, square ends, each figure directly above its own
 * bar. The reading "that tiny one against that huge one" then happens in the
 * geometry, which is the whole job.
 */
export const RatioBar: React.FC<{
  aLabel: string; aValue: number; bLabel: string; bValue: number; top: number;
}> = ({aLabel, aValue, bLabel, bValue, top}) => {
  const frame = useCurrentFrame();
  const panel = interpolate(frame, [0, 12], [0, 1],
    {easing: Easing.out(Easing.poly(5)), extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const st = useStagger();
  const total = aValue + bValue;
  const inner = WIDTHS.full - 2 * PAD.card;
  const bars = inner - 8;

  const Row = ({v, l, w, colour, grow, d}: {
    v: number; l: string; w: number; colour: string; grow: number; d: number;
  }) => (
    <div style={{opacity: st(d)}}>
      <div style={{display: 'flex', alignItems: 'baseline', gap: 14}}>
        <span style={figureStyle(SIZE.figurePair)}>{v}</span>
        <span style={labelStyle}>{l}</span>
      </div>
      <div style={{height: 22, marginTop: 6, width: w * grow, background: colour}} />
    </div>
  );

  const grow = interpolate(frame, [10, 40], [0, 1],
    {easing: Easing.out(Easing.poly(5)), extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  return (
    <AbsoluteFill style={{alignItems: 'center', paddingTop: top}}>
      <div style={{
        ...surface, width: WIDTHS.full, padding: PAD.card,
        display: 'flex', flexDirection: 'column', gap: 18,
        transform: `translateY(${interpolate(panel, [0, 1], [18, 0])}px)`,
        opacity: interpolate(frame, [0, 5], [0, 1], {extrapolateRight: 'clamp'}),
      }}>
        <Row v={aValue} l={aLabel} w={(bars * aValue) / total} colour={C.accent}
          grow={grow} d={4} />
        <Row v={bValue} l={bLabel} w={(bars * bValue) / total} colour={C.accent2}
          grow={grow} d={10} />
      </div>
    </AbsoluteFill>
  );
};

/**
 * The Americas board as a populating grid — eight real counts read off the
 * page, each row landing in turn, so KRU's 1/5 is SEEN against seven others
 * rather than asserted.
 *
 * The eight team brand hues are gone. G2's `#F5D020` sat 1.1 degrees of hue
 * from the old gold highlight, so in this card the team colour and the
 * highlight colour were indistinguishable — the card's one job, undone by
 * its own decoration. One neutral tab for everyone, and the highlighted row
 * is the only coloured thing in the card.
 *
 * And the stagger: `d = 7 + i*4` with a 10-frame ramp put 2.5 rows mid-fade
 * at any moment, which reads as one wash rather than a sequence. Eight rows
 * now land in 20 frames as a ripple.
 */
export const RosterGrid: React.FC<{
  rows: {team: string; signed: number; of: number}[];
  top: number; highlight?: string;
}> = ({rows, top, highlight}) => {
  const frame = useCurrentFrame();
  const panel = interpolate(frame, [0, 12], [0, 1],
    {easing: Easing.out(Easing.poly(5)), extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const spacing = Math.max(2, Math.min(7, Math.round(18 / rows.length)));

  return (
    <AbsoluteFill style={{alignItems: 'center', paddingTop: top}}>
      <div style={{
        ...surface, width: WIDTHS.mid, padding: PAD.tight,
        transform: `translateY(${interpolate(panel, [0, 1], [18, 0])}px)`,
        opacity: interpolate(frame, [0, 5], [0, 1], {extrapolateRight: 'clamp'}),
      }}>
        {rows.map((r, i) => {
          const d = 6 + i * spacing;
          const a = interpolate(frame, [d, d + 7], [0, 1],
            {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
          const hot = highlight === r.team;
          return (
            <div key={r.team} style={{
              display: 'flex', alignItems: 'center', gap: 14, padding: '6px 0',
              opacity: a, transform: `translateX(${interpolate(a, [0, 1], [-14, 0])}px)`,
              borderBottom: i < rows.length - 1
                ? `1px solid ${C.hairline}` : 'none',
            }}>
              <span style={{
                width: 5, height: 30,
                background: hot ? C.accent : C.tab,
              }} />
              <span style={{
                fontFamily: TEXT, fontWeight: hot ? 700 : 500, fontSize: SIZE.context,
                fontVariationSettings: `"wght" ${hot ? 700 : 500}, "wdth" 94`,
                width: 250, color: C.textPrimary, letterSpacing: TRACK.label,
                textTransform: 'uppercase',
              }}>{r.team}</span>

              {/* the pips count out, two frames apart, so a full roster
                  visibly reaches five and KRU visibly stops at one */}
              <span style={{flex: 1, display: 'flex', gap: 5}}>
                {Array.from({length: r.of}).map((_, k) => {
                  const on = k < r.signed
                    ? interpolate(frame, [d + 4 + k * 2, d + 10 + k * 2], [0, 1],
                        {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})
                    : 1;
                  return (
                    <span key={k} style={{
                      flex: 1, height: 13,
                      background: k < r.signed
                        ? C.textPrimary : C.pipOff,
                      transform: `scaleX(${k < r.signed ? on : 1})`,
                      transformOrigin: 'left',
                    }} />
                  );
                })}
              </span>

              <span style={{
                ...figureStyle(34), width: 86, textAlign: 'right', lineHeight: 1,
                fontVariationSettings: `"wght" ${hot ? 800 : 600}, "wdth" 86`,
              }}>{r.signed}/{r.of}</span>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

/**
 * A dated news item. Out of the current cut, but cleaned anyway: the
 * micro-caps source strip and the accent date chip would otherwise come
 * back for free on the next card built from this component.
 */
export const NewsCard: React.FC<{
  stamp: string; headline: string; sub?: string; top: number;
}> = ({stamp, headline, sub, top}) => {
  const frame = useCurrentFrame();
  const st = useStagger();
  const panel = interpolate(frame, [0, 12], [0, 1],
    {easing: Easing.out(Easing.poly(5)), extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  return (
    <AbsoluteFill style={{alignItems: 'center', paddingTop: top}}>
      <div style={{
        ...surface, width: WIDTHS.mid, padding: PAD.card,
        transform: `translateY(${interpolate(panel, [0, 1], [18, 0])}px)`,
        opacity: interpolate(frame, [0, 5], [0, 1], {extrapolateRight: 'clamp'}),
      }}>
        {/* the accent is a key bar — structure — not a pill around a date */}
        <div style={{display: 'flex', alignItems: 'center', gap: 14, marginBottom: 14,
                     opacity: st(2)}}>
          <span style={{width: 4, height: 26, background: C.accent}} />
          <span style={{...contextStyle, color: C.textSecondary}}>{stamp}</span>
        </div>
        <div style={{
          fontFamily: TEXT, fontWeight: 800, fontSize: SIZE.headline, lineHeight: 1.02,
          fontVariationSettings: '"wght" 800, "wdth" 88',
          color: C.textPrimary, textTransform: 'uppercase', opacity: st(6),
        }}>{headline}</div>
        {sub ? (
          <div style={{...contextStyle, marginTop: 10, opacity: st(11)}}>{sub}</div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

/**
 * Two figures from the board, the second counting up against the first.
 *
 * George: "274 what? doesnt make sense." He is right, and it broke a rule
 * already written down — a lone figure can argue the opposite of the point,
 * so a card shows a PAIR. "274 NOT YET CONFIRMED" alone has no subject; "139
 * SIGNED" beside it supplies one by contrast, and both are the board's own
 * labels, so no noun has to be invented.
 */
export const PairCounter: React.FC<{
  aValue: number; aLabel: string; bValue: number; bLabel: string;
  top: number; countFrames?: number;
}> = ({aValue, aLabel, bValue, bLabel, top, countFrames = 46}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const panel = interpolate(frame, [0, 12], [0, 1],
    {easing: Easing.out(Easing.poly(5)), extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const land = spring({frame: Math.max(0, frame - 8), fps, config: FIGURE});
  const p = interpolate(frame, [6, 6 + countFrames], [0, 1],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const eased = 1 - Math.pow(1 - p, 3);

  const Col = ({v, l, count}: {v: number; l: string; count: boolean}) => (
    <span style={{display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8}}>
      <span style={{
        ...figureStyle(SIZE.figurePair),
        transform: `translateY(${interpolate(land, [0, 1], [14, 0])}px)`,
      }}>{count ? Math.round(v * eased) : v}</span>
      <span style={{...labelStyle, fontSize: SIZE.context, color: C.textSecondary}}>{l}</span>
    </span>
  );

  return (
    <AbsoluteFill style={{alignItems: 'center', paddingTop: top}}>
      <div style={{
        ...surface, padding: `${PAD.card}px ${PAD.card + 16}px`, textAlign: 'center',
        transform: `translateY(${interpolate(panel, [0, 1], [18, 0])}px)`,
        opacity: interpolate(frame, [0, 5], [0, 1], {extrapolateRight: 'clamp'}),
      }}>
        <div style={{display: 'flex', alignItems: 'flex-start', gap: 44}}>
          <Col v={aValue} l={aLabel} count={false} />
          <span style={{
            width: 2, alignSelf: 'stretch', background: C.keyline,
            margin: '6px 0 14px',
          }} />
          <Col v={bValue} l={bLabel} count />
        </div>
      </div>
    </AbsoluteFill>
  );
};
