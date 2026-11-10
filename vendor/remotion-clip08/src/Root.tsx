import React from 'react';
import {Composition, getInputProps, staticFile} from 'remotion';
import './fonts';
import {StatCard, ExhibitFrame} from './Graphics';
import {StatChip, RatioBar, RosterGrid, PairCounter} from './Chips';
import {PlayerCard, ClickbaitLine} from './People';
import {NewsStory} from './NewsStory';
import {TweetCard} from './Tweet';
import {ChatScroll} from './Chat';
import chat from '../public/chat.json';
import badgeMap from '../public/badgemap.json';
import chatWindows from '../public/chat_windows.json';
// PER-CLIP, written by make_clip.py before each render. The
// compositions used to hardcode clip 8's 2812 frames and its hook
// line, which is exactly the kind of constant that has to become
// data before a second clip can be built.
import clip from '../public/clip.json';
import stories from '../public/stories.json';
import {Stage, Dir, Kind, EXIT} from './motion';

// ─────────────────────────────────────────────────────────────────────────
// PER-CLIP DATA ARRIVES AS inputProps. THE IMPORTS ABOVE ARE ONLY THE
// STUDIO'S FALLBACK.
//
// Those five imports are webpack MODULES: their contents are compiled into
// the bundle at build time, from the ONE shared `public/` directory every
// clip writes to. So two clips building at once is not a race that can be
// narrowed — whichever wrote last is what both bundles contain. Pointing
// `remotion bundle --public-dir` at a per-clip copy does NOT fix it: that
// moves the copied `public/` tree and not one byte of what `import` already
// inlined, which was measured end to end — a bundle built with a per-clip
// dir compiled the WRONG clip's chat while `<out>/public/clip.json` on disk
// reported the RIGHT one. A silent race turned into a deterministic
// wrong-clip render that passes its own verification, which is worse.
//
// `--props=<this clip's json>` is read per RENDER, so nothing about one
// clip's data can reach another's frames. With no props — the Studio, or a
// hand-run `remotion render` — these fall back to `public/`, so previewing
// still works exactly as before.
const IN = getInputProps() as Record<string, any>;
const CHAT = (IN.chat ?? chat) as any;
const CHAT_WINDOWS = (IN.chatWindows ?? chatWindows) as any;
const BADGE_MAP = (IN.badgeMap ?? badgeMap) as any;
const CLIP = (IN.clip ?? clip) as {
  durationInFrames: number; baitFrames: number; hook?: string; emoji?: string;
};
const STORIES = (IN.stories ?? stories) as any[];

const V = {fps: 60, width: 1080, height: 1920} as const;

// CARD DURATIONS ARE BACK AT FULL. The previous pass took 7.45s out of
// them to buy chat windows and George's verdict was "now it's going way
// too quickly" — measured, that build changed state every 2.6s. Removing
// ChipAmer and StatCard buys the same room without rushing anything:
// 11 states instead of 18, one change every 4.3s.
//
// (kept for the record) CARD DURATIONS WERE SET BY THE CHAT:
//
// George: "it needs to be more apparent throughout the whole video ... it
// needs to be on the screen, and then it needs to go out when we're putting
// an animation in. Then the animation needs to go out. Then the chat comes
// back in. So it's like constantly there."
//
// That is an ALTERNATION, and the lower pane holds one thing at a time, so
// the chat's share has to come out of the cards. A card's START is anchored
// to the line it supports and must not move, so the room comes out of
// DURATIONS: 33.75s of card becomes 26.30s, which opens a ~1.7s gap after
// every card that has the spacing for one.
//
// Each shortened card was checked against its own animation rather than cut
// to a round number — settled hold after the entrance completes and before
// the exit begins: Tweet 1.98s, StatCard 1.50s, Grid 1.77s, ExKru 1.43s,
// StoryPrx 2.15s, StorySen 2.42s. ExKru is the tightest because its marker
// takes a full second to draw on; Pair and Ratio were already short enough
// against their own spacing and are untouched.

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
    {/* The streamer's own chat, replayed OVER what he is looking at. It is
        an alpha overlay on V3 like any other, and it steps out of the way
        when a graphic lands — see chat_windows.json. */}
    <Composition id="Chat" component={ChatScroll}
      durationInFrames={CLIP.durationInFrames} {...V}
      defaultProps={{messages: CHAT, badgeMap: BADGE_MAP,
        windows: CHAT_WINDOWS}} />


    <Composition id="Tweet" component={XTweet} durationInFrames={214} {...V}
      defaultProps={{src: staticFile('tweet_full.png'), top: 1104, tilt: -2.6,
        exitH: 435}} />



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


    <Composition id="ExNrg" component={XExhibit} durationInFrames={225} {...V}
      defaultProps={{src: staticFile('crop_nrg.png'), width: 816, top: 1057,
        fromX: 668, exitH: 486}} />



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

    {/* STORY CARDS ARE GENERATED, NOT HAND-REGISTERED.
        George: "surely we should be showing an image of vitality at
        champions similar to the jingg/jonahp story of the previous video?
        include that in the logic." StoryPrx and StorySen above are typed
        out by hand, which is why there were two of them and why a third
        clip got none. `engine/story.py` finds a licensed Riot photo of a
        team the clip NAMES and writes `stories.json`; every entry here
        becomes a Composition, so `render_remotion.py --all` picks it up
        with no edit to this file. The headline comes from Riot's own photo
        caption — see that module for why that is a strong enough source to
        automate, where a single-outlet roster item was not. */}
    {STORIES.map((s) => (
      <Composition key={s.id} id={s.id} component={XStory}
        durationInFrames={s.frames} {...V}
        defaultProps={{tilt: s.tilt, headline: s.headline,
          photos: [{src: staticFile(s.photo)}],
          top: s.top, photoHeight: s.photoHeight,
          photoFocus: s.photoFocus, photoZoom: s.photoZoom, exitH: 600}} />
    ))}

    <Composition id="Bait" component={XBait}
      durationInFrames={CLIP.baitFrames} {...V}
      defaultProps={{text: CLIP.hook ?? '', emoji: CLIP.emoji ?? '😳',
        top: 700, exitH: 60}} />
  </>
);
