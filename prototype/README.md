# The prototype site

`clip-factory.html` is a prototype of the PRODUCT — what an operator sees — as
distinct from `web/`, which is the local control surface that actually drives
the pipeline. Published as an Artifact so it can be opened and shared without
this machine.

    python3 build.py        # concatenates a-*.html / a-app.js, inlines factory.json

## It follows OpusClip's shape, deliberately

George: *"clip factory is good but i want us to take the opus clip route and
build it like that."* So the three screens are theirs:

| | |
|---|---|
| **New project** | one source field, then clip settings — timeframe, clip length, a prompt for what to look for |
| **Clips** | every candidate as a scored card, sorted by score or in order, with a re-rank box, filters and like/dislike |
| **Editor** | one clip open: canvas, filmstrip, timeline, and tabs for transcript, layout, captions and sound |

Export carries MP4, **XML for Resolve** and Schedule, which is their handoff
too. Their palette is not borrowed — the tokens stay
`vendor/remotion-clip08/src/theme.tsx`, so the interface and the clips it
makes agree about blue, white and `RADIUS = 0`.

## Where it deliberately differs, and why

**OpusClip shows a score with no reason and never says what it refused.** The
research pass was explicit: *"No page shows clips considered versus clips
returned. No page explains why a segment was rejected."*

We have the reasons already — `ranked.json` carries `strength`, `genre`, the
claim, the setup and a written `why`, and `screened.json` carries the block
and its cause. So the card keeps OpusClip's score badge and adds the state
(**Rendered / Ready to cut / Blocked**) with the reason under it. The yield
stays visible in the tally instead of being the whole page.

**One tension worth naming.** This file records that *ranking by virality
picks clips the pipeline cannot cut* — 4 of 12 buildable, and the second clip
chosen by virality had to be abandoned at 44% muted. Sorting by score first
is OpusClip's route and it is what was asked for; the block state on each
card is what keeps that from being a trap.

## Everything on it is real

Every figure, title, score, frame and transcript comes from one run of
`jobs/fns-2905408276`:

* 50 candidates with their real `virality` score, genre, claim and block reason;
* a real frame from each candidate's own source clip, letterboxed 16:9 in the
  tile because nothing has reframed it yet — the tile says at a glance which
  clips are cut;
* the 4 delivered clips with poster, 8-frame filmstrip, word-level transcript
  in cut time, audio splice count and their real boom placements, including
  what the nucleus gate refused and which word did it.

The only simulated thing is the pipeline replay on the New project screen,
and it shows stage STATE with no durations, because the per-stage timings
were never measured.

## Two house rules carry the design

* **Nothing coloured is ever a number.** The score is ink or white; the blue
  under it is a bar. The accent is structure — a key, a rule, a seam marker.
* **The accent never touches a photograph.** Frames sit on the sunk neutral.

## A high score on a clip you cannot use is a tease

George, on the first OpusClip-shaped build: *"you gave it a 63 and yet it's
blocked because it's 43% muted. Why are you even showing that to me if we
can't even use it?"*

He is right, and it was the first card in the grid. The yield still matters —
40 of 50 refused is the honest number and the reason the tool is worth
anything — but it does not have to cost him the top of the page. The default
filter is now **Usable** (10), with **Refused** (40) one click away and the
count on the chip either way.

## The editor plays the actual cut

Four preview copies at 540×960 ship beside the page as artifact files
(`clips/NN.mp4`, 2.5–3.5 MB each, re-encoded from the 18–24 MB masters).
The cards preview on hover with `preload="none"`, the editor plays with
controls, the filmstrip seeks, and clicking a word in the transcript jumps
the video to it. The guides — seam at 0.42 and the platform-UI safe bands —
sit over the video and can be hidden, because the bottom band lands exactly
where the player's own controls are.
