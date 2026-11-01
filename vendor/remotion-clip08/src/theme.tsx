import React from 'react';

// COLOUR, GEOMETRY, TYPE AND TIMING — all of it, in one place.
//
// George: "the design is still very like AI looking in terms of the remotion
// ... I just think we could perhaps change the palette a little bit ... I'd
// like this to be something that we continue working towards as like a
// foundation, but we're on the right track." So the shape stays and the
// surface changes, and the surface is now a token rather than fifty literals.
//
// THE DEFECT THE PALETTE FIXES, measured rather than argued. The old dark
// glass panel was #1A1E28-ish over a near-black roster board, and against
// the real board pixels of the lower pane that is **1.08:1 median, with
// 95.1% of its footprint under 1.25:1**. It had no edge. Everything bolted
// on to compensate — a 1px 9%-white hairline, a 28/64px shadow bloom, a 2px
// inset highlight and a gold rule — was a prosthetic for a rectangle that
// could not be seen. Stacked compensation is the generated-design signature;
// the panel was the symptom.
//
// The chassis below measures **1.67:1 median, 94.1% of footprint above
// 1.6:1, 1.1% under 1.25**. It needs no hairline, no bloom and no rule, so
// all three are gone and the radius with them.
//
// TWO RULES CARRY THIS, and they are what dissolve "vibe coded":
//
//   1. NOTHING COLOURED IS EVER A NUMBER. The accent is a key bar, a marker
//      stroke or a bar segment — structure, never data. Before this, gold
//      marked the eyebrow dash, the date chip, a chip border, the bar fill,
//      the highlighted row, the sub-line, the status line AND the emphasised
//      caption; and its meaning inverted between adjacent cards (PairCounter
//      made 274 gold, RatioBar made 32 gold, eight seconds apart). An accent
//      on everything marks nothing. White figures are also LOUDER: 10.79:1
//      on the chassis.
//   2. THE ACCENT NEVER TOUCHES A PHOTOGRAPH OR PAPER. Measured across the
//      eight VCT press photos: 35.2% of pixels are saturated and 56.0% of
//      those sit in the 0-15 degree band where #F4512A lives. VCT stage
//      lighting is red-magenta and Riot's own brand red is #FF4655, so this
//      is structural, not an artifact of these eight files.

export const C = {
  // The chassis. Flat, fully opaque, no gradient. 1.67:1 median against the
  // board, which is the entire point — a surface instead of a tint.
  surface: '#413D36',
  // The well an exhibit crop sits in.
  surfaceDeep: '#2B2823',
  // 2px, all four sides. 1px at 1.84:1 goes sub-pixel on a 720x1280
  // re-encode and aliases frame to frame; top-and-left-only is the oldest
  // bevel convention there is. Against an exhibit crop (Y~0.011) it reads
  // 2.51:1, so it frames the crop on both sides.
  keyline: '#6B6458',

  textPrimary: '#FFFFFF',      // every figure, every time. 10.79:1
  textSecondary: '#BDB5A8',    // the ONE second-rank line. 5.31:1
  // There is no third text tier. `textMuted` is deleted rather than kept
  // unused: its only jobs were the micro-caps source strips, the kicker over
  // every panel and the name under a photo, all of which George rejected by
  // name. A token that exists gets reached for.

  accent: '#F4512A',           // 3.11:1 on chassis, 5.21:1 median on the board
  accent2: '#818EA7',          // 3.27:1 on chassis
  // HARD CONSTRAINTS ON accent2: it never touches the board and is never a
  // figure. Its hue is 219.5 degrees against the board's 217 — the exact
  // fault diagnosed in gold — so it is defensible inside a chassis slab and
  // nowhere else.
  //
  // And on the pair: accent Y 0.2529, accent2 Y 0.2680 — **1.06:1,
  // isoluminant**. On RatioBar that is fine, because the hues are 206 apart
  // on the blue/yellow axis (intact under both deuteranopia and protanopia),
  // the figures above the bars are white, and 32 against 274 is a 10% sliver
  // against a full bar, so LENGTH is the primary encoding. The rule, for
  // anything else: any pair encoded by colour alone must separate by 15-20%
  // in luminance.

  paper: '#F4F1EB',            // the press cards. Flat; the gradient goes.
  ink: '#1A1611',              // 15.97:1 on paper
  inkSecondary: 'rgba(26,22,17,0.68)',

  // The three neutrals that are not text: a row divider, an un-highlighted
  // row tab, and an unfilled roster pip. Tokens for the same reason as the
  // rest — five formula-derived greys `(n, n+8, n+24)` with no two values
  // reused is how the old set drifted.
  hairline: 'rgba(255,255,255,0.07)',
  tab: 'rgba(255,255,255,0.45)',
  pipOff: 'rgba(255,255,255,0.12)',
} as const;

// A slab moved above the seam is fragile: 13.9% of facecam pixels sit within
// 1.25:1 of the chassis. Every `top` in Root.tsx is >= 975 except
// ClickbaitLine at 700, which is stroked type with no slab behind it.
export const BOARD_SAFE_TOP = 975;

// TYPE BY ROLE, NOT BY SIZE.
//
// Before: everything >= 28px was Impact and everything <= 25px was Helvetica
// Neue — EIGHTEEN distinct Impact sizes, nine of them (28/30/31/32/34/38/40/
// 42/44) doing one job, three of those within 2px of each other in three
// files. That is per-component authoring with no scale. Worse, setting the
// label in Impact at 44px made both tiers display type, so "PARTNER TEAMS
// PER REGION" carried the same optical weight as the figure above it.
//
// IMPACT IS THE VOICE FACE — CAPTIONS ONLY. A sourced figure set in Impact
// looks like a meme caption, which is why the cards and the captions read as
// the same object. Figures and labels go to Archivo, which has a width axis,
// so figure/label/context separate by WEIGHT AND WIDTH instead of by colour
// — and that is what frees the accent to mean one thing.
//
// Archivo also fixes the counters. `fontVariantNumeric: 'tabular-nums'` was
// a no-op on Impact: its GSUB carries only `locl`, and its digit advances
// span 780-1109/2048 upm — a 30% spread — so CounterCard's 0->274 roll had a
// worst single-frame shift of 28px. Measured on the file here, Archivo's
// digits are 575-577/1000 upm, a **0.35% spread**, tabular before the
// feature is even enabled.
export const CAPTION = 'Impact, Haettenschweiler, "Arial Narrow", sans-serif';
export const TEXT = 'Archivo, "Helvetica Neue", system-ui, sans-serif';
export const SERIF = '"Source Serif 4", Charter, Georgia, serif';

// Four sizes. Not nine near-but-never-equal values for one role.
export const SIZE = {
  figure: 150,        // one figure alone
  figurePair: 96,     // two side by side
  label: 40,          // the word that explains the figure
  context: 30,        // the one second-rank line
  headline: 52,       // a published press headline
} as const;

// Riot's own production CSS has a 0.64px tracking ceiling across both sites.
// The micro-caps strips George called an AI-ism ran 0.2-0.3em, which at 14px
// is 4-6x that. Labels get +1% and nothing gets more.
export const TRACK = {label: 0.4, none: 0} as const;

/** The caption treatment George picked himself after four style versions:
 *  white fill, hard black stroke at ~9.5% of the size, no box. The hook line
 *  over the facecam is set the same way, which is what makes the two one
 *  system instead of a pill and a caption. */
export const CAPTION_STROKE = '5px #000000';

/** Figures: heavy, slightly narrowed, tabular. */
export const figureStyle = (size: number): React.CSSProperties => ({
  fontFamily: TEXT, fontWeight: 800, fontSize: size, lineHeight: 0.84,
  fontVariationSettings: '"wght" 800, "wdth" 86',
  fontFeatureSettings: '"tnum" 1, "lnum" 1',
  color: C.textPrimary, letterSpacing: TRACK.none,
});

/** Labels: the same family a weight and a width down, so the figure leads. */
export const labelStyle: React.CSSProperties = {
  fontFamily: TEXT, fontWeight: 600, fontSize: SIZE.label, lineHeight: 1.0,
  fontVariationSettings: '"wght" 600, "wdth" 94',
  color: C.textPrimary, letterSpacing: TRACK.label,
  textTransform: 'uppercase',
};

/** The one second-rank line. */
export const contextStyle: React.CSSProperties = {
  fontFamily: TEXT, fontWeight: 500, fontSize: SIZE.context, lineHeight: 1.1,
  fontVariationSettings: '"wght" 500, "wdth" 100',
  color: C.textSecondary, letterSpacing: TRACK.label,
  textTransform: 'uppercase',
};

// GEOMETRY. Before: six radii (1/2/3/4/5/999), three near-miss shadow stacks
// (30 vs 28px blur, 0.92 vs 0.85 alpha — one decision typed twice, plus a
// third at 66px), eleven padding shorthands with eight horizontal insets,
// and nine left edges / seven tops / eleven widths across eleven graphics
// with four tops inside 40px of each other. 864 vs 884 vs 814 is one width
// typed three times. That is drift, not intent, because nobody can perceive
// it as a decision.
export const WIDTHS = {full: 1008, mid: 816, narrow: 624} as const;
export const MARGIN = 36;
/** The usable band for a lower-pane graphic: above 1000 the captions own it
 *  (they draw from y 845 as the TOP and reach 933, or 957 emphasised); below
 *  1600 is the platform's UI. Everything centres on 1300 so eleven cards
 *  share one axis. */
export const SLOT = {top: 1000, bottom: 1600, centre: 1300} as const;
export const PAD = {card: 28, tight: 20, chip: 14} as const;
export const RADIUS = 0;

/** The one shadow in the system, which is what makes it a decision rather
 *  than a default. PAPER ONLY — a rgba(0,0,0,0.75) bloom does nothing over
 *  board pixels at Y' 22, which is the same vestigial prosthetic the old
 *  dark panel was wearing. */
export const PAPER_SHADOW =
  '0 26px 56px -16px rgba(0,0,0,0.92), 0 3px 10px rgba(0,0,0,0.5)';

/** The chassis every drawn card is built on. Flat, square, opaque, 2px
 *  keyline on all four sides, and nothing else. */
export const surface: React.CSSProperties = {
  background: C.surface,
  border: `2px solid ${C.keyline}`,
  borderRadius: RADIUS,
  overflow: 'hidden',
};

/** The seat an exhibit crop sits in. */
export const well: React.CSSProperties = {
  background: C.surfaceDeep,
  borderRadius: RADIUS,
  overflow: 'hidden',
};

/** Paper, for a press story arriving from outside the frame. It stays
 *  9.57:1 away from the chassis, which is the wordless difference between
 *  "what the outlet published" and "what the board says". */
export const paperSurface: React.CSSProperties = {
  background: C.paper,
  borderRadius: RADIUS,
  boxShadow: PAPER_SHADOW,
  overflow: 'hidden',
};
