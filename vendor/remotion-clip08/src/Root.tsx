import React from 'react';
import {Composition, staticFile} from 'remotion';
import './fonts';
import {StatCard, ExhibitFrame} from './Graphics';
import {StatChip, RatioBar, RosterGrid, PairCounter} from './Chips';
import {PlayerCard, ClickbaitLine} from './People';
import {NewsStory} from './NewsStory';
import {TweetCard} from './Tweet';
import {Stage, Dir, Kind, EXIT} from './motion';

const V = {fps: 60, width: 1080, height: 1920} as const;

// ONLY THE COMPOSITIONS IN THE CUT ARE REGISTERED. `render_remotion.py
// --all` regexes every `Composition id` out of this file, so the stale ones
// were costing a render each — including all 2822 frames of `Kinetic`, a
// Style-C artefact whose own exit shrinks to scale 0.72 and then vanishes at
// FULL opacity, i.e. 106 hard cuts. The delivered caption track is the PIL
// one (`cap_kin.mov`), so nothing referenced it. `Counter`, `NewsFA`,
// `NewsPrx`, `NewsSen`, `ChipKru`, `PlJinggg`, `PlSen` and `PlJerrwin` are
// likewise not on the timeline. The components stay in the files; it is the
// registrations that were doing the damage.

/**
 * Every card leaves through the same system, applied HERE rather than inside
 * nine components — but with THREE DURATIONS and a PER-CARD TRAVEL, which is
 * what the first version got wrong by sharing one 18-frame / 118px exit
 * across everything.
 *
 * `exitH` is the card's rendered height, measured off the alpha channel of
 * its own render rather than estimated, because the chassis exit's clip
 * plane sweeps across the CARD and needs to know where the card ends.
 */
const exits = <P extends {top?: number}>(
  Comp: React.FC<P>,
  o: {dir?: Dir; kind?: Kind; travel?: number; frames?: number; drift?: number} = {},
) => {
  const Wrapped: React.FC<P & {exitH?: number}> = ({exitH, ...props}) => (
    <Stage {...o} top={(props as P).top ?? 1000} h={exitH ?? 400}>
      <Comp {...(props as P)} />
    </Stage>
  );
  return Wrapped;
};

// Travel is half each card's own entrance offset, rounded. Atlassian pairs
// SlideInTop8px with SlideOutTop4px; no published exit travels further than
// its entrance.
const XStatCard = exits(StatCard, {travel: 9, frames: EXIT.card});
const XExhibit  = exits(ExhibitFrame, {travel: 10, frames: EXIT.card});
const XGrid     = exits(RosterGrid, {travel: 9, frames: EXIT.card});
const XRatio    = exits(RatioBar, {travel: 9, frames: EXIT.card});
const XPair     = exits(PairCounter, {travel: 9, frames: EXIT.card});
const XPlayer   = exits(PlayerCard, {travel: 9, frames: EXIT.card});
// Paper and a dark screenshot both fade: a 15.6:1 card at 50% opacity is
// still unambiguously a card, where the dark chassis panel turned to mud.
// NewsStory goes UP — it sits against the 1600 platform-UI line, so exiting
// down would slide it into the platform's own furniture.
const XStory    = exits(NewsStory, {dir: 'up', kind: 'paper', travel: 27, frames: EXIT.paper});
const XTweet    = exits(TweetCard, {kind: 'paper', travel: 27, frames: EXIT.paper});
// A side tab leaves the way it came, in 100ms, and is too small and too
// quick to need the geometric exit.
const XChipLeft = exits(StatChip, {dir: 'left', kind: 'plain', travel: 28,
                                   frames: EXIT.chip, drift: 0});
// Stroked type over a moving face: opacity only, no travel, no drift.
const XBait     = exits(ClickbaitLine, {dir: 'up', kind: 'plain', travel: 0,
                                        frames: EXIT.fade, drift: 0});

export const Root: React.FC = () => (
  <>
    <Composition id="ChipAmer" component={XChipLeft} durationInFrames={110} {...V}
      defaultProps={{figure: '34/40', label: 'AMERICAS SLOTS FILLED', side: 'left',
        top: 1230, exitH: 110}} />

    <Composition id="Tweet" component={XTweet} durationInFrames={214} {...V}
      defaultProps={{src: staticFile('tweet_full.png'), top: 1104, tilt: -2.6,
        exitH: 435}} />

    <Composition id="StatCard" component={XStatCard} durationInFrames={210} {...V}
      defaultProps={{from: '10', to: '8',
        label: 'PARTNER TEAMS PER REGION', top: 1205, exitH: 190}} />

    <Composition id="Pair" component={XPair} durationInFrames={288} {...V}
      defaultProps={{aValue: 139, aLabel: 'SIGNED', bValue: 274,
        bLabel: 'NOT YET CONFIRMED', top: 1211, exitH: 178}} />

    {/* `ExStrip` IS DELETED, and the measurement is why. The card showed
        the board's own header line, and its job was the pair "32 open slots"
        / "274 not yet confirmed". Measuring the PNG's ink columns rather
        than trusting the source-coordinate map: `crop_strip.png` holds FOUR
        blocks — 32 open slots | 82 bench / options | 78 staff | 274 not yet
        confirmed — and the two that matter are the FIRST and the LAST, at
        png x 19-178 and 729-988 of 1010. The contiguous run containing both
        is therefore the entire strip, so no magnification is possible
        without dropping one of them, and stitching the two together would
        fabricate an adjacency the page does not have.

        At 1.00x its tallest ink band measures 21px against 88px captions —
        4.2x smaller than the subtitle over it. A graphic that holds the
        frame for 3.5s and cannot be read is decoration that looks like
        evidence. `Ratio` carries the identical two figures 4.3s later, as
        two solid bars, legibly. Re-cropping from the source gains 4%: the
        strip is 670 source px wide and that is the whole ceiling.

        `Pair` lengthens from 3.45s to 4.80s to take up the slack, so the
        remaining ten graphics stay roughly one every 4.4s and no card moves
        off the spoken line it was anchored to. */}

    <Composition id="Ratio" component={XRatio} durationInFrames={210} {...V}
      defaultProps={{aLabel: 'OPEN SLOTS', aValue: 32, bLabel: 'NOT YET CONFIRMED',
        bValue: 274, top: 1153, exitH: 294}} />

    <Composition id="ExNrg" component={XExhibit} durationInFrames={225} {...V}
      defaultProps={{src: staticFile('crop_nrg.png'), width: 816, top: 1057,
        fromX: 668, exitH: 486}} />

    <Composition id="Grid" component={XGrid} durationInFrames={240} {...V}
      defaultProps={{top: 1090, highlight: 'KRÜ ESPORTS', exitH: 420, rows: [
        {team: '100 THIEVES', signed: 5, of: 5},
        {team: 'G2 ESPORTS',  signed: 5, of: 5},
        {team: 'KRÜ ESPORTS', signed: 1, of: 5},
        {team: 'LEVIATÁN',   signed: 5, of: 5},
        {team: 'LOUD',        signed: 5, of: 5},
        {team: 'MIBR',        signed: 4, of: 5},
        {team: 'NRG',         signed: 5, of: 5},
        {team: 'SENTINELS',   signed: 4, of: 5},
      ]}} />

    <Composition id="ExKru" component={XExhibit} durationInFrames={258} {...V}
      defaultProps={{src: staticFile('crop_kru.png'), width: 816, top: 1057,
        fromX: 668, exitH: 486,
        marker: {cx: 560, cy: 212, rx: 150, ry: 128}}} />

    <Composition id="StoryPrx" component={XStory} durationInFrames={255} {...V}
      defaultProps={{tilt: -3.4,
        headline: 'Paper Rex parts ways with Jinggg after five years',
        photos: [{src: staticFile('p_jinggg.jpg')}],
        top: 1029, photoHeight: 430, exitH: 600}} />

    <Composition id="StorySen" component={XStory} durationInFrames={240} {...V}
      defaultProps={{tilt: 3.1,
        headline: 'Sentinels release JonahP and Jerrwin',
        photos: [{src: staticFile('p_jonahp.jpg')},
                 {src: staticFile('p_jerrwin.jpg')}],
        top: 1029, photoHeight: 430, exitH: 600}} />

    <Composition id="Bait" component={XBait} durationInFrames={1020} {...V}
      defaultProps={{text: "FNS ON VALORANT'S JOB SECURITY PROBLEM",
        emoji: '😳', top: 700, exitH: 60}} />
  </>
);
