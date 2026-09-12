# v1.1.2.0

**The feed moves onto the button tray, and Basilisk stops searching the web
about your own code.**

## The gap above the composer is gone

The activity feed was a full-width panel in a dock of its own between the last
message and the box you type in — with a margin above and below it, sitting
there whether anything was running or not.

It is a status indicator, so it now rides **on the button tray** with Unleash,
attach and the speaker, at the size of the other controls. Clicking it opens
the step list **over the conversation**; the tray never changes height and
there is no hole left behind.

The panel is a `Gtk.Overlay` inside the window and deliberately **not** a
`Gtk.Popover`. A popover is its own native surface, so on X11 with no
compositor it cannot be translucent — it would have been the one surface that
breaks while the rest of the glass still works.

## It searches when it should, and not when it shouldn't

`_needs_web_verification` was a list of markers, and a list of markers can only
ever say yes. Every marker added to stop a missed fetch also made it fire on
ordinary work. Measured against fourteen plain coding questions, **thirteen**
forced a web fetch:

```
"explain the cost of a hash table lookup"             -> cost
"which python version does my pyproject require"      -> version
"refactor the price calculation in cart.py"           -> price
"why is worth() returning None in this file"          -> worth
"the news feed component in my react app is broken"   -> news
```

That is both halves of the complaint at once. It searched when it obviously
should not — and because the promise gate reads the same predicate, the turn
could not *end* where it should have either: it answered, fetched anyway, and
came back with a second reply nobody asked for.

There is now a suppressor, and it needs **positive evidence**. It can only
downgrade a weak signal, never a strong one: "latest", "today", "who won",
"weather", "ceo of", "out yet" name the live state of the world and are never
suppressed. Result on the corpus: 24/24 ordinary questions answer directly,
24/24 world questions still get looked up.

## The card says what it is

The boot card read **AUTONOMOUS SECURITY ASSISTANT**, which is the one thing
Basilisk is *not* until you arm it. It now reads **GENERAL & CODING
ASSISTANT**, with a line underneath saying Unleash arms the autonomous pentest
agent.

## Quieter

- **No competitor comparison.** The README, site and `llms.txt` lead with what
  Basilisk scores and how to reproduce it, not with other people's numbers. The
  cost argument stays, because that one is the actual design claim: a budget
  open model produces the score, and if you need a frontier model to get a
  result you have built a wrapper, not an agent.
- **Less glow.** 125 chromatic box glows damped again (cap 0.12) and 23
  coloured text halos damped for the first time — a halo behind a letterform is
  what makes type look like a screensaver.
- **The artwork came down with it.** The emblem, watermark and logo were the
  brightest, most saturated thing on screen once the chrome went calm; their
  highly-saturated pixels are trimmed on a curve, lightness and alpha
  untouched.

## Also

- New `tests/test_websense.py` (64 assertions), including the three bugs the
  corpus caught while it was being written — the worst being an arithmetic
  guard that read `CVE-2026-1234` as 2026 minus 1234 and suppressed a live
  vulnerability lookup.
- 4,439 assertions across 72 stdlib-only suites, zero red.
