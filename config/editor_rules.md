# Editor rules: every complaint becomes a rule

The planner (`engine/plan.py`) reads every line starting with "- " on every
call. When Jatin or George complains about a clip, the fix lands here in the
same PR, so the same complaint can't come back.

Each rule says who asked and when, then either `CHECKED: <where>` (code
enforces it, with a test) or `NOTE` (only the planner is told).

- (George, 2026-11) One clip is one narrative; a change of subject is a boundary, never something to clip across. NOTE
- (George, 2026-11) The clip must explain itself: every person or team it refers to has to be identifiable from inside it. NOTE
- (George, 2026-11) A question and its answer are one narrative; the clip starts at the question. NOTE
- (George, 2026-11-19) No zoom-ins on gameplay, and no grown facecam over his own kills. CHECKED: plan.TREATMENTS has no big_cam for frag
- (Jatin, 2026-11-19) Reaction clips keep their subtitles; only his own kill clips go uncaptioned. CHECKED: core.specs
- (Jatin, 2026-11-19) Only the streamer is captioned, not casters or the game. CHECKED: resolve_captions.background
- (Jatin, 2026-11-20) The review loop's trims and retitles weren't better; the plan never moves the in- or out-point. CHECKED: plan.validate takes sentence ids inside the cut
- (Jatin, 2026-11-20) No music, no sound effects, no auto-posting. CHECKED: no such treatment exists
- (spec, 2026-11-21) Story first: no graphic just because we have it. A pop-up shows only when a card beat asks for that name. CHECKED: plan.allowed_popups
