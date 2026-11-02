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
  // POLYMARKET. George sent the logo and asked for "polymarket blue colours
  // and their design typography ... blue and white text for example - blue
  // and white for animations etc". Sampled off the file he sent: the mark is
  // exactly two colours, #2E5CFF over 96.1% of it and #FFFFFF over 3.0%.
  blue: '#2E5CFF',
  // The same hue and saturation (227 deg, S 1.00) lifted from L 0.59 to
  // 0.68. The brand blue reads 4.09:1 against a hard black caption stroke,
  // under the 4.5 floor; this reads 5.99:1, which matches the 6.06:1 of the
  // vermilion it replaces. Use it for anything that has to hold against
  // dark; use `blue` on white and as a fill.
  blueLight: '#5C80FF',

  white: '#FFFFFF',
  paper: '#FFFFFF',        // the press cards. Polymarket's white is pure.
  ink: '#0B0B0C',
  inkSecondary: 'rgba(11,11,12,0.62)',

  // TWITCH'S OWN CHAT BLACK, and it is not ours to restyle.
  //
  // George: "the twitch chat needs to stay black with the normal colours of
  // the twitch chatters." The chat is a REPLAY of a real interface, so the
  // panel is Twitch's value (#18181B, its dark-theme chat column) and the
  // names are the chatters' own. A blue panel with white usernames was a
  // graphic that quoted chat; this is chat.
  //
  // WHICH COSTS IT ITS EDGE, measured: against the real board pixels under
  // the box footprint this reads **1.03:1 median, and its outline is
  // distinguishable along only 7.2% of its own perimeter** (pure black 7.2%,
  // #070C11 7.0%). The box disappears into the board and the tilt with it —
  // the identical 1.08:1 defect the palette pass deleted four devices for.
  // So the black panel is MOUNTED on `blue`, which is 3.41:1 on the board
  // with 97.5% of the outline visible. That is R5's own answer (its
  // near-black card sits on a cyan plate with square corners) in our
  // palette, and it is ONE element carrying the edge rather than a hairline,
  // a bloom, an inset highlight and a rule stacked on a panel nobody can
  // see.
  twitchBg: '#18181B',
  twitchText: 'rgba(255,255,255,0.95)',

  // Measured per-pixel against the real roster board: the brand blue sits at
  // **3.52:1 median with 98.2% of its footprint above 1.6:1**, against the
  // warm graphite chassis it replaces at 1.67:1. A blue panel does not need
  // a keyline to be seen on this board — it has its own edge — which is why
  // the 2px keyline is gone with everything else.
  hairline: 'rgba(255,255,255,0.14)',

  // The cards this cut no longer uses — the figure cards, the exhibits, the
  // chips — are still in the component files and still import these names.
  // Mapping them onto the Polymarket palette rather than deleting them means
  // the build does not break AND a card put back comes back blue, instead of
  // re-appearing in the warm graphite that is no longer the house look.
  surface: '#2E5CFF',
  surfaceDeep: '#1E3FCC',
  keyline: 'rgba(255,255,255,0.22)',
  textPrimary: '#FFFFFF',
  textSecondary: 'rgba(255,255,255,0.74)',
  accent: '#FFFFFF',          // on blue, the accent IS white
  accent2: '#5C80FF',
  tab: 'rgba(255,255,255,0.45)',
  pipOff: 'rgba(255,255,255,0.22)',
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
// INTER, not Archivo. Archivo was chosen for a measured reason — a width
// axis and default-tabular digits, so a figure, its label and a context
// line could separate by weight and width instead of colour, and so the
// counters stopped reflowing. **That reason is gone**: this cut has no
// counters and no figure cards left, only the chat and two press stories.
// What is left to serve is Polymarket's register, and their wordmark is a
// neo-grotesque. Inter is OFL, it is the de facto UI face of this category,
// and it is the closer match. Archivo stays vendored: if figure cards come
// back, its `wdth` axis and 0.35% digit spread are the better tool (Inter's
// digits run a 37% spread by default and need `tnum` switched on).
//
// Their wordmark itself is probably custom and is not ours to redistribute,
// so this matches the register, not the exact letterforms.
export const TEXT = 'Inter, "Helvetica Neue", system-ui, sans-serif';
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
  background: C.blue,
  border: 'none',            // the blue is 3.52:1 on the board; it needs no edge
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
