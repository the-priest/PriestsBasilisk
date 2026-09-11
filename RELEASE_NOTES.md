# v1.1.1.0

**Obsidian glass, and a stream that stops lying about itself.** This release is
a theme and a runtime pass: the whole app moves off the red palette onto a cool
glass one, and three streaming symptoms that all looked cosmetic turn out to
have been one parser bug.

## The streaming bug

Reported as *"when it searches it types in chat and it gets deleted, bubble
pops in and out"*. Three symptoms, one cause.

Every stripper in `basilisk_core` answers **"is this text a tool call?"**. A
stream asks a different question: **"could this text still become one?"** Until
a marker is long enough to be recognised, its characters are ordinary text — so
the renderer painted `<`, `<t`, `<to`, `<too` one frame at a time and then
deleted them the instant `<tool ` completed. Measured across every dialect the
app supports: canonical, DSML (both pipe forms), `<invoke>`, `<tool_call>`,
`<function=>`, and `<think>`. All of them leaked.

The third symptom followed from it. The chat bubble is attached lazily on the
first token carrying visible text, precisely so a tool-only step never draws an
empty bubble — but a leaked `<too` *is* visible text by that test. So a search
step attached a bubble, painted a fragment, lost it to the stripper, then hid
itself as a bare tool step. Popped in, typed, deleted, popped out.

Fixed with the rule every incremental parser uses: never emit a tail that could
still turn into markup — hold it one frame. `stream_visible_text()` is now the
one transform both the renderer and the attach decision go through, so they
cannot disagree again. It is stream-only by design: a *finished* message ending
in `<t` is text and still shows.

## Turns that run to completion

The answer-mode stall counter was cumulative, which is why a long job stopped
before it was finished: two stalls early in a 40-step task spent the whole
budget, and the next stall — at step 40, with the work half done — ended the
turn silently. The cap exists to stop a model that *only* narrates; a model
that narrates, gets pushed and then runs something is not that model. The
counter is now consecutive and is cleared by any real tool result, with a
separate absolute ceiling for the pathological narrate-run-narrate case.

## Obsidian glass

- **No brand red anywhere.** Every colour in the stylesheet, the brand art, the
  embedded button art and the SVGs was migrated hue-by-hue onto a cool band,
  keeping each colour's lightness exactly so the four-layer glass recipe kept
  its internal contrast. Red now means one thing: danger. Error, destructive
  and warning colours were deliberately left where they were.
- **Ambient bloom, not a neon rim.** 124 chromatic outer glows damped. Light
  falls from one direction, so the lit edge is the top edge and the rest of
  each outline is a low-alpha hairline.
- **The live feed is joined to the composer** instead of floating between the
  conversation and the box you type in — one control surface, not three glass
  slabs with air between them. Tool-result previews lost their nested box.
- **The composer is calm at rest.** It holds focus from the moment the app
  opens, so its focus state *is* what the app looks like; it no longer opens
  with a 28px accent bloom on all four sides.
- **Monochrome glyphs in the sidebar.** The pinned and agent-mode markers were
  emoji, which the emoji font renders in its own colour and metrics; they take
  the palette now, like the activity feed's glyphs already did.

## Also

- `.gitignore` now excludes `settings.json` — it holds API keys.
- New `tests/test_streamhold.py` (64 assertions), including the counter-property
  that ordinary prose containing `<` survives untouched, and a scaling check
  that the hold is constant-cost in reply length.
- 4,367 assertions across 71 stdlib-only suites, zero red.
