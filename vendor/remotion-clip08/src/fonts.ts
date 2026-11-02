import {continueRender, delayRender, staticFile} from 'remotion';

// Two OFL-1.1 variable faces, served from `public/fonts` rather than a CDN.
//
// A CDN font fetch that arrives late during a frame render silently changes
// glyph metrics mid-sequence, which is a determinism hazard on top of the
// licence one. `@remotion/google-fonts` also reads
// `SEE LICENSE IN LICENSE.md` — it inherits the company licence — so the
// route here is a plain FontFace, which is MIT-free entirely.
//
// Licences are vendored beside the files: `public/fonts/Archivo-OFL.txt` and
// `public/fonts/SourceSerif4-OFL.txt`, both read and confirmed as the SIL
// Open Font License 1.1.
//
// ARCHIVO is here for two measured reasons, not for looks:
//
//   * `wght 100-900` AND `wdth 62-125` in one file, so a figure, its label
//     and a context line separate by WEIGHT AND WIDTH instead of by colour —
//     which is what frees the accent to mean one thing.
//   * a real `tnum`, and digits that measure 575-577/1000 upm (a 0.35%
//     spread) before the feature is even enabled. Impact's GSUB carries only
//     `locl` — no `tnum` at all — and its digits span 780-1109/2048 upm, so
//     `fontVariantNumeric: 'tabular-nums'` was a no-op and the counters
//     visibly reflowed: CounterCard's 0->274 roll shifted up to 28px in a
//     single frame.
//
// Checked and rejected: Oswald (wght 200-700 but NO `tnum`, 378-517 digit
// spread), Anton (single weight, no axes, a '1' 33% narrower than every
// other digit — structurally Impact with a different skeleton), Big
// Shoulders (no width axis). Tungsten Black is on this machine and is the
// better-looking broadcast face, but it is Hoefler&Co licensed to one
// machine, not redistributable, has no `tnum` (digit advances 251-407, a 62%
// spread) and its video-distribution terms are unchecked.
//
// SOURCE SERIF 4 is the press headline, and its digits are 500-500/1000 —
// a 0.00% spread.
//
// Impact stays, for captions only. It is the voice face: a sourced figure
// set in Impact looks like a meme caption, which is why the cards and the
// captions used to read as the same object.

const handle = delayRender('loading Archivo and Source Serif 4');

const FACES: [string, string, FontFaceDescriptors][] = [
  ['Inter', 'fonts/Inter.ttf', {weight: '100 900'}],
  ['Archivo', 'fonts/Archivo.ttf', {weight: '100 900', stretch: '62% 125%'}],
  ['Source Serif 4', 'fonts/SourceSerif4.ttf', {weight: '200 900'}],
];

Promise.all(
  FACES.map(async ([family, file, desc]) => {
    const face = new FontFace(family, `url(${staticFile(file)})`, desc);
    await face.load();
    document.fonts.add(face);
  }),
)
  .then(() => continueRender(handle))
  // A missing font must not hang the render for 30s and then die — fail
  // loudly, keep going, and the fallback stack shows in the frame.
  .catch((err) => {
    // eslint-disable-next-line no-console
    console.error('font load failed, falling back:', err);
    continueRender(handle);
  });
