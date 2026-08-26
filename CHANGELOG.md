## v1.0.0.11 — backdrop brightness control (+ a self-inflicted bug caught)

### New: adjustable background brightness

The Display settings page now has a Backdrop group with a "Background
brightness" slider (0-100, default 50) and a reset button. It changes how
much of the ember/castle image shows through behind the chat, LIVE with no
restart: 0 is darkest (heaviest dim), 100 is brightest (image shows through
almost fully), 50 matches the shipped default. Implemented by re-tinting the
scrim box with a per-widget CSS provider, so it overrides the static
.chat-scrim opacity without a full stylesheet reload. The value clamps
safely -- any bad or out-of-range setting falls back into the legible band.

### Bug caught and fixed in the same change

The deep scan (ruff F821) caught that inserting the Backdrop group had
dropped the two lines that create the "Interface" PreferencesGroup, leaving
three `ui_g.add(...)` calls referencing an undefined name -- which would have
crashed the settings dialog the moment the Display page was opened. Restored
the group creation; the dialog now builds cleanly under real GTK (verified by
constructing it and exercising the brightness row end to end).

### Deep scan — otherwise clean

ruff F821/F811/E9 clean after the fix. AST sweep: no mutable defaults, bare
excepts, prod asserts, duplicate dict keys, or return-in-finally. The stall
classifier and news detector (changed in v1.0.0.10 / .9) fuzzed 40k inputs
with zero crashes. The word-boundary marker regex escapes special characters
correctly ("up-to-date" matches, "eol" does not fire inside "eolian").

### Tests

53 suites, 4,162 assertions. New brightness wiring pinned in test_guiwiring;
full suite green, bubble-fit 140/140 under real GTK, guardrail byte-identical.

## v1.0.0.10 — "says fetching news, doesn't fetch" fixed at the source

The real cause of the news bug, and it was not the markers.

When answer mode decides a question needs a live source, it sends a strong
"your FIRST action MUST be web_read" directive -- and that part works. But the
model often replies with a plain narration ("Fetching the latest news for
you.", "Getting the latest headlines.", "Searching for the latest news.") and
NO tool call. There is a stall-recovery nudge for exactly this -- it re-kicks
the turn when the model says it will do something but calls no tool -- and it
was not firing, so the turn ended with the words "fetching news" and nothing
fetched.

Root cause: the stall classifier (`reply_intends_action`) only recognised
intent PHRASES -- "let me fetch", "I'll check", "fetching now". A reply that
simply OPENS with a bare action gerund -- "Fetching...", "Getting...",
"Searching...", "Pulling...", "Gathering..." -- matched nothing, so it was not
seen as a stall and no nudge fired. Seven of fourteen realistic news
narrations slipped through.

Fix: a reply that opens with an action gerund and delivers nothing now counts
as intent-to-act, so the nudge fires and forces the actual web_read. Anchored
to the FIRST word, so a delivered answer that merely contains a gerund ("found
3 hosts, still scanning the rest") is untouched; past-tense reports ("I checked
the news; the top story is...") still read as delivery; and gerund IDIOMS
("Getting started with X is easy", "Looking at this, the answer is...") are
excluded so they are not nudged. 16/16 news narrations now nudge, the
"same answer three times" over-nudge protection still holds (0 false
positives on complete answers).

Pinned in test_turn_directives.py, which fails on v1.0.0.9 for the bare-gerund
narrations.

### Tests

53 suites, 4,155 assertions. Full suite green; bubble-fit 140/140 under real
GTK; guardrail byte-identical.

## v1.0.0.9 — deep-scan pass: two real bugs

A deep debugging sweep. Most of what it checked came back clean (details
below); two genuine bugs surfaced and are fixed.

### News markers collided inside longer words

`_needs_web_verification` matched its single-word markers ("current", "cost",
"news", "score", ...) as raw substrings, so they fired inside unrelated words:
"concurrent processing", "recurrent event handler", "costume", "newsletter",
"underscore", "scoreboard" all triggered a needless web fetch on ordinary
coding questions. A false-positive class present since v1.0.0.0.

Fixed by splitting the markers: multi-word phrases still match as substrings
(safe), single-word markers now match on WORD BOUNDARIES via one compiled
regex. Every real query still fetches ("what's the current version", "whats
the score", "stock price", "how much does it cost"); the collisions are gone.
Pinned both directions in test_turn_directives.py, which fails on the old
build for six collision cases.

### The Aero send-button style was dead CSS

v1.0.0.8's Aero layer styled the primary send button with a `.send-btn`
selector -- but the widget's actual class is `.send-button`, so the glossy-red
styling matched nothing and never rendered. Fixed the selector; the send
button now gets its intended Aero glass. Found by auditing every Aero selector
against the classes actually applied to widgets.

### Scans that came back clean

Ruff F821/F811/E9/F822/F823: no undefined names, redefinitions, or syntax
errors. AST sweep: no shadowed except-handlers, no ==/!= against None, no
return-in-finally (the six `is False`/`is True` hits are correct -- they
distinguish an explicit False from a missing key). parse_tool_calls and
strip_tool_calls fuzzed 30k adversarial inputs, zero crashes. The redirect-flag
scope parser fuzzed 12k, zero crashes and zero real leaks (the well-formed
forms all refuse; IPv6 endpoints are caught). SQLite access is lock-guarded on
every runtime path (only the single-threaded __init__ DDL is unlocked, which is
safe). The one open()-to-variable is the recorder stderr handle, closed on
every exit path.

### Tests

53 suites, 4,145 assertions. Bubble-fit 140/140 under real GTK; leashed and
unleashed both verified end to end; guardrail byte-identical.

## v1.0.0.8 — Windows 7 "Aero" glass look (still red)

A visual pass: the flat near-black surfaces now carry the Windows 7 Aero
treatment -- glossy top-lit gradients, a bright 1px upper-edge bevel, rounded
glass panes, and soft outer glow. The accent stays RED, not Aero's stock blue:
buttons glow red on hover, the send/run actions are deep glossy-red glass, the
user bubble is a red glass pane, and the composer keeps its red focus glow.

Done as a single override layer appended to the END of the CSS block, so it
wins by cascade order without editing or deleting any base rule -- reverting is
just removing that block. Surfaces restyled: header bar, sidebar, composer,
buttons (normal + primary), chat bubbles, selected sidebar row, status pills
and cards. GTK parses the stylesheet with zero errors; the CSS stays ASCII per
the invariant; no animations were added (the idle-repaint audit stays clean).

Pairs with the brighter backdrop from v1.0.0.7 -- the glass panes now float
over a visible ember/castle background instead of near-black.

### Tests

53 suites, 4,134 assertions. Bubble-fit stays 140/140 under real GTK (the new
box-shadows and borders did not reintroduce the height problem), and the
animation/CSS audits in test_guiwiring pass.

## v1.0.0.7 — news fetch actually fires, and a brighter backdrop

### The news fetch missed the phrasings people actually use

`_needs_web_verification` decides whether the "check online before you answer"
directive fires. It keyed off "news"/"latest"/"current" and missed the casual
ways people ask for news, so those answered from stale training memory instead
of fetching — "it can't even fetch news":

  what's going on in the world · any headlines · catch me up ·
  give me the rundown · whats up today · top stories · current events ·
  fill me in · breaking news

Added those. "headlines" is handled with a context check rather than as a bare
marker, so a request FOR headlines ("show me the headlines", "any headlines")
fetches while a plain-noun mention ("headlines aren't showing in my css", "my
headline font is too big") stays stale. Same for "the rundown": it fetches as a
news ask but not in "the rundown of how git works". 27 phrasings pinned across
both directions in test_turn_directives.py.

### Brighter background

The chat backdrop scrim was a black overlay at 0.62 opacity, which buried the
ember/castle art. Lowered to 0.40 — the background reads clearly and text over
it stays legible. Pure CSS value change, nothing structural.

### Verified, both modes

Leashed and unleashed both checked end to end: offensive tooling is refused
when leashed (`unleash_required`) and available when armed, hidden from the
general tool index, and the hard floors (destructive command + fail-closed
scope, including the redirect-flag fix from v1.0.0.5) fire regardless of mode.

### Tests

53 suites, 4,134 assertions. The bubble fix (v1.0.0.3), the box-art and
sidecar-optional guards (v1.0.0.4/6), and the scope redirect fix (v1.0.0.5) all
still green.

## v1.0.0.6 — the pentest suite is intact, and a startup crash it could cause

Asked to make sure the full hacking/pentest suite is available when UNLEASHED
without breaking anything. Audited the whole tool inventory and found the suite
correctly wired — plus one latent crash that could take the whole app (and the
suite with it) down.

### The suite is complete and correctly gated

All 161 spec'd tools are reachable — every one has a dispatch handler, no
orphans. The 97 offensive-group tools appear in the tool directory when UNLEASH
is ARMED and are withheld from the leashed directory; `load_tools("offensive")`
while leashed is refused with `unleash_required`. And the hard floors are
mode-independent by design: every command still passes through `gate_command`,
so the destructive floor and the fail-closed scope gate apply whether armed or
not — UNLEASH controls autonomy and tool visibility, not the safety boundary.
No change needed there.

### But two offensive modules were imported un-guarded — a startup crash

basilisk.py's own import comments state the rule: a missing or import-broken
sidecar must degrade the tools that use it, never stop the app from starting.
`recall` followed it. `zdayfind` and `exploits` did not — they were bare
`from basilisk_ext import …` lines. So a partial install, or a platform import
error inside either module (the POSIX-only `resource` that once took out the
whole ext package on Windows is exactly this shape), crashed the GUI at
startup and took every unrelated tool with it.

Proven: with exploits.py and zdayfind.py deleted, the previous build raised
`ImportError: cannot import name 'zdayfind'` and never opened a window.

FIX: both imports are now guarded (try/except → None), matching `recall` and
the module's own rule. A new `_ext_unavailable()` helper returns a uniform
"module unavailable, reinstall to restore; the rest of Basilisk is unaffected"
result, and all six offensive tools that use these modules null-check before
calling — so a broken sidecar disables its own tools cleanly instead of
crashing startup or raising AttributeError mid-call. Verified: the app now
starts with both modules deleted and the affected tools report `unavailable`.
The normal path (modules present) is unchanged.

### Tests

53 suites, 4,119 assertions. New test_ext_optional.py (13) pins the rule both
at source and behaviourally — it fails on v1.0.0.5, where the app will not
even import with the modules gone.

## v1.0.0.5 — closing the destination-redirect leaks

The two open items from v1.0.0.4 are fixed: a scope-authorised hostname could
still carry traffic to an out-of-scope endpoint through a redirect flag.

```
curl --resolve acme.com:443:8.8.8.8 https://acme.com   -> was ALLOWED
curl --connect-to acme.com:443:8.8.8.8:443 https://... -> was ALLOWED
ssh -o ProxyCommand='nc 8.8.8.8 22' acme.com           -> was ALLOWED
ssh -o ProxyJump=8.8.8.8 acme.com  /  ssh -J 8.8.8.8    -> was ALLOWED
curl --proxy 8.8.8.8:8080 https://acme.com             -> was ALLOWED
```

Every one connects somewhere OTHER than the hostname typed, and the gate keyed
off the visible host — so the in-scope name laundered an out-of-scope
destination. New `_REDIRECT_FLAGS` + `_redirect_targets()` pull the real
endpoint out of each flag's value (the 3rd colon-field of --resolve/--connect-to,
the host of a ProxyJump/-J, the host tokens of a ProxyCommand, the --proxy/-x
host) and add it to the scoped targets. The endpoint is now checked like any
other target.

Fails toward extracting: an endpoint that cannot be parsed confidently still
surfaces when host-shaped, because a missed redirect is a bypass while a
spurious one is a fixable false refusal. Counter-properties hold: a redirect to
an IN-scope IP is allowed, a harmless non-destination `ssh -o` option
(StrictHostKeyChecking, Port) is not treated as a redirect, and a malformed
value falls back to the visible target without crashing. IPv6 endpoints,
`user@host:port` jump specs, and bracketed addresses all parse.

basilisk_ext.engage does NOT need the mirror: it checks one host at a time and
never parses a command line, so it never sees these flags. The scope/engage
host-for-host parity is unchanged (90/0).

### Tests

52 suites, 4,106 assertions. test_scope grew the redirect-flag regression
(catches 5 shapes that leaked on v1.0.0.4) plus its counter-properties.

## v1.0.0.4 — deep-scan pass: a scope leak and the untested art module

### `curl -i` swallowed an out-of-scope target

Found by re-probing the scope gate against the historically-leaky shapes.
`-i` is `--identity` (a keyfile, value-taking) on ssh/scp but `--include`
(a boolean) on curl, and it lived in the value-taking set — so on curl it
consumed the token after it:

```
curl -i evil.com acme.com   ->  gate saw only acme.com  ->  ALLOWED
```

curl fetches BOTH urls; the gate saw only the in-scope one and let an
out-of-scope fetch through. Same laundering the bare-hostname note fixed for
positional operands, reached through a flag. Fixed with a per-tool boolean
override (`_TOOL_BOOLEAN_FLAGS`): `-i`/`--include` are boolean for curl, while
ssh/scp `-i` keeps its keyfile value. Verified both directions and pinned in
test_scope.py, which fails on v1.0.0.3. (`-I` and `--include` were already
caught; only lowercase `-i` leaked.)

Left as reported, not fixed: `curl --resolve host:port:ip` and
`ssh -o ProxyCommand` redirect the destination and are still not modelled —
a documented open item, unchanged this pass.

### The embedded button art had no test

`basilisk_btn_art.py` is 11k lines of base64 button art embedded in a required
module precisely so it can never go missing on an update — but nothing
validated it, so a corrupted paste or a renamed key would leave the buttons
silently falling back to symbolic icons, the exact failure the embedding was
meant to end. New test_btn_art.py pins: every blob decodes to a real PNG (magic
bytes, non-trivial size), every button the app requests has a matching blob,
and no blob is left unrequested (a stray key is a typo). All 11 clean, 1:1 with
the app's `_BTN_*` constants.

### Scans that came back clean

Ruff F/E9/PLE: no undefined names, no redefinitions, no syntax errors. AST
sweep: zero mutable defaults, bare excepts, prod asserts, duplicate dict keys,
subprocess-without-timeout, open-without-encoding. The destructive-command
floor still catches all 26 known-dangerous shapes with zero false positives on
11 benign ones. The structural write-recovery from v1.0.0.1 fuzzed at 20k
well-formed (all round-trip) + 15k malformed (zero silent-wrong) bodies.

### Tests

52 suites, 4,096 assertions. New: test_btn_art.py (36), test_scope grew the
per-tool-flag regression.

## v1.0.0.3 — the five-screens-tall bubble

### The list was a Gtk.Grid, and a Grid towers the bubble

Reported with five full-screen screenshots to capture ONE reply: a news
answer whose bubble background ran on for four empty screens below the last
line. Reproduced in the real app under GTK at the reported window size — the
assistant bubble measured **582px tall with its content ending at ~340px**,
so ~240px of empty bubble, and it compounded with every section of a longer
reply into the tower in the screenshots.

ROOT CAUSE, and it is the same height-for-width disagreement as the earlier
bubble bug, relocated: `ListWidget` was a `Gtk.Grid`, and a Grid reports a
cramped natural WIDTH for a wrapping cell — it asks the body label its
minimum, which for a wrap label is about one word. So a bulleted reply made
the whole chat bubble hug narrow (~419px even on a wide window), and GTK then
computed the bubble's HEIGHT at that narrow width: every bullet wrapped into a
tall ribbon, and the bubble drew hundreds of px of background past its text.
The `set_width_chars(6)` on the body — added to keep the Grid's minimum width
down — made it worse, because it also fixes the NATURAL width, pinning the
bubble narrow.

FIX: `ListWidget` is now a vertical box of horizontal rows (marker + wrap
label per item) instead of a Grid. A horizontal box settles each row's WIDTH
first and only then asks the label its height, so the height is measured at
the width the bullet is actually shown at. Same hanging-indent look, honest
height. Measured: the identical three-bullet reply went from a 419x102
cramped bubble to 654x55, and the full news reply from 582px (240px slack) to
554px (12px slack — just the bubble's own bottom padding). The `set_width_chars`
pin is gone.

### The bubble-fit suite was blind to it

It only measured content overflowing PAST the bubble — the earlier bug, text
spilling out the bottom. It never checked the opposite: a bubble taller than
its content. So it stayed green through the towering. Added a SLACK
measurement (bubble bottom minus the deepest visible descendant) and wiring
assertions pinning the box-rows structure and the absence of the width pin;
those fail on the previous build and pass on this one. The harness window was
widened from 810 to 1280px, because the tower is width-dependent and did not
appear at the narrow default.

Two source-level suites (test_richblocks, test_guiwiring) were asserting the
`set_width_chars` floor — i.e. pinning the very construction that caused the
bug. Rewritten to pin the box-rows fix instead.

### Tests

51 suites, 4,054 assertions. Bubble-fit passes 140 checks under real GTK
across scales 0.5/0.7/0.85/1.0. Guardrail byte-identical.

## v1.0.0.2 — the fetch dead-end

### "it can do one thing and stops — can't even fetch news"

The stall recovery from v1.0.0.1 had a hole that put the model straight back
into the loop it was meant to end. When the model narrated a next step with
no tool call ("I'll check the latest headlines now"), the answer-mode nudge
re-kicked the turn — but `_continuation` keyed purely on `_tool_chain_depth`,
and the nudge had bumped that depth without any tool having run. So the
re-kick was treated as a mid-chain continuation and the model was handed:

```
[STILL VERIFY, DON'T RECALL — you have already read at least one source
 this turn. Do NOT re-read a page you have already read …]
```

when it had read **nothing**. It was told it had already done the work, so it
answered from memory or stopped — exactly at the moment it needed to fetch.
Reproduced by driving the real `_kick_assistant_turn`:

```
bare narration stall (no tool ran):
  before -> "already read a source, don't re-read"   (WRONG)
  after  -> "CHECK ONLINE FIRST, your FIRST action MUST be web_read"
```

A continuation is now "the chain advanced AND a tool actually ran" —
`_tool_ran_this_request`, set at the single `_feed_tool_result` choke point
every result passes through, reset per request. A real tool continuation
still gets the mid-chain form (no four-times repeat); a bare stall gets the
full fetch directive. Both directions pinned in `test_turn_directives.py`,
which scores 2 failures against v1.0.0.1.

### The stall classifier missed the phrasings models actually stall in

"Give me a moment while I check", "One moment…", "Hang on…", "Bear with me…",
"On it — pulling the release notes" — all announce a pending action, none
matched, so no nudge fired and the turn died silently. Added the polite
hedges, plus two guards so the wider net does not over-fire:

- **Asking the operator for input is not a stall.** "Give me the target and
  I'll scan it" contains both "give me" and "I'll scan", so it read as a
  stall and got nudged — but a nudge cannot answer a question only the
  operator can, so it re-asked forever. A reply that puts the ball in the
  operator's court is waiting correctly.
- **A dash tail that opens with an action gerund is still a plan.** "On it —
  pulling the release notes" was read as delivering "pulling the release
  notes"; a leading `pulling/fetching/searching/…` is a promise wearing a
  dash, not a result.

28 narration/answer shapes classified correctly, both directions, pinned.

### A flaky fetch retries instead of dying

`web_read` returned `{ok: false}` on the first transient network miss — a DNS
blip, a reset connection, a 503 — and a leashed turn that got one failure
tended to narrate or give up. It now retries once on a transient TRANSPORT
error and on a 5xx, but never on a real status: a 404 or 403 IS the answer
and is returned immediately.

### Tests

51 suites, 4,035 assertions (3,190 printed checks + 845 executed unittest
asserts, recounted). `test_turn_directives.py` grew the fetch dead-end and
the classifier corpus; `test_bigwrite.py` grew the fetch-retry checks.

## v1.0.0.1 — write pass

### "writing big code fails every time"

Four bugs behind one sentence, and only one of them was about size.

**Quote density, not size.** `_loads_lenient` repairs literal control
characters inside a JSON string and nothing else — but the mistake a model
makes on a FILE body is an unescaped inner `"`, and every real file has one
(`print("hi")`, a dict key, a docstring). Measured on the previous build:

```
literal newlines only          -> repaired
unescaped inner quotes         -> None -> {"_raw": …} -> no card, nothing written
newlines AND quotes (any code) -> None -> {"_raw": …} -> no card
```

A three-line function failed exactly as reliably as a 400-line module. Tiny
sections "worked" because they are short enough for the model to hand-escape.
`json.loads` cannot be made to do this — once a quote closes the string early
the rest of the object is garbage to it — so the value is now taken
STRUCTURALLY for the write tools only: find the key, walk candidate
terminators, decode the escapes that are really there. Which quote ends the
value is decided by two rules, and both are needed: the candidate that leaves
the MOST sibling keys standing wins (so `"explanation"` after the body is not
swallowed into the file), and ties go to the rightmost (so source that embeds
JSON — `data = '{"a": "b"}'` — is not truncated at its own brace).

**The reply was cut off and nobody looked.** Nothing read `finish_reason`, so
a call truncated at `max_tokens` was indistinguishable from a finished one.
The operator was told the JSON was probably badly escaped and the model was
told to re-send in the correct format — so it re-sent the same oversized call
into the same cap. Both messages now name the real cause, and the model is
told to SPLIT rather than re-send.

**Sectioned writing is a real path now.** `write_file` / `propose_edit` take
`"mode": "append"`, with the Python parse-check running against the ASSEMBLED
file — half a module cannot pass as valid. Appending to a file that does not
exist yet creates it; an unknown mode is named rather than guessed.

**The file body was being interpreted.** In the `<parameter>` dialect
V4-Flash emits, `_coerce_param` turned `config.json`'s contents into a dict
and a file holding `42` into an int, so `f.write()` raised TypeError and a
perfectly good call came back as "write failed". It also `.strip()`ed, so a
file written that way could never end in a newline. Content keeps its bytes;
only the opening tag's own newline is dropped.

**A file containing `</tool>`** cut its own call short — the non-greedy tag
match stopped inside the body. The span is re-cut at the last closer when the
body is unterminated.

### write_file was the fourth write primitive, and the only ungated one

The previous pass put `_fs_guard` on `delete_path`, `move_path` and
`copy_path`. `write_file` — the primitive with the widest reach — called
neither it nor `gate_command`. Reproduced on the previous build:

```
is_sensitive_path(~/.ssh/authorized_keys)  -> True
delete_path / copy_path / move_path        -> refused
write_file                                 -> {'ok': True, 'size': 26}
```

`~/.gnupg/gpg-agent.conf` went the same way. Its docstring said it was
"reached ONLY after the operator approves the diff card", which has not been
true since `approval_mode` defaulted to `none`: a `write_file` call executes
directly through `_run_proposed_edit`. It asks the same question every other
write asks now. Editing its own `basilisk*.py` is untouched — that is a
designed feature, bounded by the immutable GUARDRAIL block and the
parse-check.

### Two suites were testing nothing

`test_bubble_fit.py` listed four UI scales and ran ONE: a `break` at the
bottom of the loop, because GTK cannot start a second application in one
process. The single scale it ran was 0.5, and `_detect_ui_scale()` returns
0.7, 0.85 or 0.9 — so the regression test written because "the bug only
appears at the scales real machines use" was guarding the one scale no
machine picks. Each scale now runs in its own interpreter and reports its
measurements back; an empty measurement is retried once, since a cold first
process can miss the settle timer.

`test_sandbox_skills.py`'s "simulate Windows: no `resource` module" used
`find_module`/`load_module`, the meta-path protocol **removed in Python
3.12**. The blocker was a no-op: `import resource` still succeeded, so four
assertions passed against a module that had `resource` all along, and the
fifth failed because the sandbox picked its `unshare` tier. It uses
`find_spec` now, and hides the namespace tools too — "no rlimits" is a
Windows fact, and Windows has no `unshare` either.

### Tests

51 suites, 4,006 assertions (3,161 printed checks + 845 executed unittest
asserts, counted rather than carried forward). `tests/test_bigwrite.py` is
new and scores 9 failures against the previous release.

## v1.0.0.0 — GUI pass

### Text drew outside the bubble

Reported with a screenshot: the bubble background stopped partway down a
reply and the last two entries plus the closing line rendered on the
wallpaper, over the Listen button.

**It only happens at the UI scales real machines use**, which is why three
earlier layout sweeps called the bubbles clean. `_detect_ui_scale()` returns
0.7 for a desktop monitor and 0.85 for a laptop, and `_scale_css` rewrites
every `Npx` in the stylesheet accordingly — but every harness I had written
ran at the headless default, where the same reply happened to fit. Repeating
the measurement across 0.5 / 0.7 / 0.85 / 1.0 found it immediately:

```
ui_scale 0.5   bubble allocated 490px, needed 576px   43px of text outside
```

**The cause was the construction that makes a bubble hug its text:**

```python
inner.set_halign(Gtk.Align.START)
inner.set_hexpand(False)
```

inside a VERTICAL box. A vertical `GtkBox` asks its child "how tall are you
at MY width", and then — because `halign=START` means "take your natural
width" — allocates it something narrower. The bubble holds wrapped text and a
two-column list, so narrower means taller: it was sized from the answer to a
question about a wider box, and the extra lines drew past its own background.
A one-sided `margin: 8px 60px 8px 12px` widened the disagreement by another
48px.

**The fix is a horizontal hug row.** A horizontal box settles every child's
WIDTH first and only then asks for height, so the width the bubble is
measured at is the width it gets. The bubble fills that row and a trailing
spacer eats the slack — the same pattern the user row already used. The
one-sided inset moved up to the column, where a margin cannot disagree with
anything; `12 + 48` is the same 60px it always was, so nothing moved on
screen.

Verified at four UI scales across ten block types — short replies, tables,
code blocks, quotes, wrapped lists, unbreakable tokens, 250-character URLs:
**zero overflow, nothing wider than the viewport.** And the counter-property
that construction existed for still holds: a four-character reply draws a
51px bubble, not a full-width one.

`tests/test_bubble_fit.py` is new and drives the real app under GTK. It skips
cleanly where there is no display, so the suite still runs anywhere, but
where it can run it measures pixels rather than reading source.

### On the "huge empty space"

Measured, and it was the same bug rather than a separate one: the scroll
range was never inflated — the bubble was too SHORT, so the text spilled
past it and the layout read as broken. After the fix the scroller ends 24px
below the last widget (the message box's own bottom padding), the view lands
at the bottom, and the end of the answer is on screen. Checked on the load
path, the streaming path, and the streaming path with a docked activity
feed.

### Tests

50 suites, 3,361 checks.

## v1.0.0.0 — second pass

### "it does not work": the model promised and never did it

Reported from a real session, three turns on one question:

```
"hi can you give me some recent news from ireland"
  -> "Looking up recent Irish news. <url> Let's read the top result."
"why did u stop?"
  -> "You're right, I never actually fetched it. Let me do it properly."
     ...and the same reply again.
"you didnt do it agasin."
```

No tool ever ran. The URL was prose, not a tag. Three separate things had
to be wrong at once for that to end quietly, and all three were:

- `parse_tool_calls` found nothing, correctly -- there was no tag.
- `looks_like_failed_tool_call` found nothing, correctly -- there was no
  protocol to fail at.
- `reply_is_bare_stall` said **delivered**, incorrectly -- the preamble plus
  the URL cleared the 80-character substance bar, so the nudge never fired.

So the turn ended "done" holding a promise, and nothing in the app noticed.

**A URL is a pointer, not an answer.** URLs are now discounted before the
substance measure, so a reply whose only content is a link has to stand on
the sentence that remains.

**And the same recovery the app already had for `run`, now for the web.**
There was already a repair for "the model printed a shell command in a
```bash fence instead of calling `run`". A printed URL is the identical
drift on the tool the operator was actually using, and it had no repair.
It has one now, behind the same two-tier gate -- mission always, a regular
turn only when the reply's own wording says it is ACTING -- so a finished
answer that CITES a source is never fetched behind anyone's back. Verified
in both directions: the three real replies recover; markdown citations,
fenced examples and fenced commands do not.

### Making the decision simple for the model

The recovery is a net. The cause was that the contract never stated the
decision plainly, and in one place actively taught the failure: the search
playbook said to read the result *"in a SEPARATE reply"*, which is an
invitation to end the turn with a plan in it.

The contract now opens with the whole decision, in twelve lines:

```
ANSWER, or CALL A TOOL. Decide before you type.
  ANSWER when you already know it and it cannot have changed.
  CALL A TOOL for this machine, the present-day world, any page, or
  anything he asked you to DO. In doubt, call it -- checking is cheap.

IF YOUR REPLY SAYS YOU WILL DO SOMETHING, THAT REPLY MUST CARRY THE
<tool ...> CALL THAT DOES IT. Describing a call is not making one.
```

The persona suite refused the first draft of this twice, and was right
both times: it was 1,955 characters (the prompt ships on every turn, so
that is a real bill), and it restated the authorization rule the suite
requires to appear exactly once. Making it *simple* meant making it
shorter -- 777 characters, then 700 -- and paying for it by compressing
five passages it now supersedes rather than by weakening the rule.

### Filesystem tools were a third execution primitive with a weaker floor

`gate_command`'s own docstring says the destructive floor exists because
"an inlined block can only ever protect the function it is inlined in".
`delete_path`, `move_path` and `copy_path` called neither it nor
`is_catastrophic_command` -- only a hand-written set of eleven exact
strings. Anything outside that set walked straight through:

```
rm -rf /usr/bin                                  -> REFUSED
delete_path{"path":"/usr/bin","recursive":true}  -> {"ok": true}
```

Confirmed with `rmtree` stubbed: `/usr/bin`, `/home` and `/var/lib` were
all reached. The set was also partly dead -- it compares against
`realpath`, and on every usr-merged distro (Arch, CachyOS, Debian 12+,
Fedora) `realpath("/bin")` is `/usr/bin`, which was not in it.

All three now ask the same question the shell floor asks, phrased as the
verb they will really use (`rm -rf` for a recursive delete, `rm` for one
file) so a single-file delete inside a critical tree is not graded as
removing the tree. Zero gaps against the shell floor, zero false refusals
on ordinary work.

`move_path` guarded only its SOURCE and `copy_path` guarded neither, while
the section header claimed "every destructive op (delete, overwrite-on-move)
is guarded". A move destroys what was at the DESTINATION -- the function
reports that in its own `"overwrote"` field, so the risk was understood and
simply unchecked. Verified: a move onto `~/.ssh/authorized_keys` returned
`ok: True` and replaced the file. Both ends are guarded now.

### My own regression, found and fixed in the same pass

The linear HTML stripper I wrote earlier in this release dropped the rest
of the document when a raw-text tag had no closer. That is right for
`<script>`; it is wrong for the two that actually fire. `</head>` is an
*optional* end tag, and `<svg .../>` self-closes legally -- so an advisory
page that omits `</head>` came back from `web_read` as `""` with `ok: True`
and `status: 200`. The model was told the fetch succeeded and the CVE had
no detail. An unterminated opener now drops the tag and keeps the content,
which is what the regex it replaced did by accident; swallowing-to-end is
reserved for `script` and `style`, where it is really how parsing works.

### Other logic bugs

- **`sudo` detection and askpass injection disagreed twice more.** The
  idempotence guard was a whole-string test, so one already-flagged `sudo`
  left every other one on the line bare (`sudo -A apt update && sudo apt
  upgrade` -- the second blocks on a prompt nobody can answer). And `sudo\b`
  matched `sudo-rs`, a real and separate binary, which the rewriter then
  corrupted into `sudo -A-rs`. Both patterns now end the word the way a
  shell does, and the lookahead makes the rewrite per-invocation.
- **The watcher's update alert was unreachable on Arch, openSUSE and
  Alpine.** `security_count` is only ever incremented in the apt and dnf
  branches -- pacman, zypper and apk do not tag security updates at all --
  and the watcher gated on `security_count > 0`. So on CachyOS, the box the
  portability layer was written for, it ran `pacman -Qu` every four hours
  and could never fire. It now reports whether a security count is even
  *knowable* and notifies on the plain count where it is not, rather than
  claiming "0 security updates" it cannot support.
- **The security audit's 90-second deadline bounded nothing** and threw the
  audit away when it fired: `as_completed` raising left the `with`, whose
  `__exit__` is `shutdown(wait=True)`, so it blocked for the hung check
  anyway -- measured 12.0s against a 2s deadline -- and the exception
  escaped, discarding every finding already collected. It now keeps what
  finished, cancels the stragglers, and marks the result `incomplete` so a
  partial sweep cannot be read as a clean bill of health.
- **`apk` package names were truncated at the first hyphen**
  (`py3-cryptography-42.0.5-r0` was reported as `py3`).

### Tests

49 suites. `test_v1_regressions.py` grew to 148 checks and now covers the
promise-never-delivered failure end to end, including the counter-property
corpus -- because the recovery's whole risk is fetching pages nobody asked
for, and a citation must never trip it.

## v1.0.0.0

### "it answers twice"

That was the report, and it turned out to be four separate bugs pointing the
same way. Every one of them re-kicked a turn that had already delivered a
complete answer, and none of them asked whether an answer had been delivered.

**A code fence made the host demand the answer again.** `parse_tool_calls`
masks ``` fences on purpose -- a tool tag inside a fence is the model showing
the operator what a call looks like, and executing it would be a real bug.
`looks_like_failed_tool_call` did not mask them. The host compares the two:
"nothing parsed, but protocol is present" reads as "the model tried to call a
tool and we could not read it", so it injected a correction and kicked the
turn again. The model had nothing new to send, so it repeated its answer --
twice, because the budget is 2.

One of the debris patterns is a bare `name="..."`>, so this did not even need
a tool tag. Verified against the real functions:

```
reply                                            parse  failed_call
prose + ```xml <tool name="run">{}</tool> ```      0      True
prose + ```html <input name="username"> ```        0      True
```

The commonest trigger was asking Basilisk to explain its own tool syntax,
because the force-answer text quotes that syntax back at the model.

The display side had the same blind spot from the other direction:
`strip_tool_calls` and `scrub_tool_debris` deleted the example *out of the
code block*, so the operator was shown an empty ```xml ``` -- which reads as
the app being broken, the impression those functions exist to prevent. Both
now work outside fences only, so the parser and the page agree about what the
reply said.

**A short answer was classified as a stall.** `reply_is_bare_stall` dropped
every sentence containing a forward-looking phrase and measured the remainder
against an 80-character bar. When the promise and the answer shared one
sentence -- which is how people write -- the answer went out with the promise:

```
"Let me check that for you: the answer is 42."          -> stall
"I'll summarise: the host is up and port 22 is open."   -> stall
```

Both complete replies. Nudge budget 2, so: the same answer three times. This
is the same three-times bug the function's own docstring says was fixed for
*long* answers; it survived for short ones because the fix measured what was
left over rather than what was delivered. Now a colon or dash inside an
intent sentence marks the delivery and is kept at any length, and a
past-tense report ("I ran the scan. Ports 22 and 80 are open.") counts as
delivery on its own. 17 answers and 8 genuine stalls, all classified
correctly, both directions pinned in tests.

**One character was "degraded".** `looks_degraded` returned True for anything
under 2 characters, and a degraded verdict costs a full extra turn whose reply
is appended *below* the one already on screen. So "how many open ports?" ->
"7" was among the likeliest replies to be shown twice. Empty is degraded; one
character is an answer.

**A delayed kick could not be cancelled, and the app called itself idle while
one was pending.** Three places scheduled the next turn with a bare
`GLib.timeout_add(...)` and discarded the source id -- after nulling all three
fields `_is_busy()` inspects. For up to 60 seconds of error back-off the app
reported itself free. Type a follow-up in that window and you got two live
streams writing through the same widget. Press Stop first and it was worse:
`_stop_requested` was the only guard, and `_send_user_message` clears that
flag on entry, so Stop did not stop it. Delayed kicks now go through one
cancellable helper, `_is_busy()` counts a pending kick, and Stop cancels it.

**And no stream knew which turn it belonged to.** The callbacks all acted on
`self.streaming_msg_widget`, meaning whatever turn is current when the
callback *runs*. Every stream now carries an epoch; a stale one cannot write
a token, finalise a turn, or schedule a retry.

### The scroll position was right and the picture was wrong

`GtkAdjustment.set_value()` only emits `::value-changed` when the number
actually moves, and `GtkViewport` applies a scroll offset only when that
signal tells it to. Loading a chat clamps the adjustment to the new bottom
*before* the viewport is allocated, so the snap that followed was a silent
no-op: the viewport never learned, and nothing ever changed the value again to
tell it. Measured in the running app -- `value=1174.0, upper=1702.0,
page=528.0`, a numerically perfect bottom, rendering offset 0. The scrollbar
reads the adjustment, so its thumb sat confidently at the bottom of a view
showing the top of the answer.

A snap that would be a no-op now bounces through 0 first, and re-asserts for
four frames so a snap issued before allocation still lands.

While it was open: an arriving assistant bubble used to slam the view to the
bottom and re-arm the stick, discarding the position the operator was reading
at (measured: 4769px, and with the rolling trim the row under the cursor was
unparented). Sending a message is a request to see it; receiving one is not.

### Every bubble leaked, forever

`dispose_widget()` nulled its Python attributes and its docstring said that
"breaks any reference cycle so CPython reclaims the widget". It did not. The
cycle runs

```
MessageWidget -> speak_btn -> GObject signal closure -> callback -> MessageWidget
```

and CPython's collector cannot see the two hops that live in C. Measured over
120 exchanges with a hard 20-row display budget:

```                     rows on screen   live MessageWidget   live CodeBlockWidget
before                        20               130                  120
after                         20                20                   10
```

Exactly one leaked per assistant message, each still holding its Pango
layouts, textures and TextViews -- the unbounded memory growth, and the reason
long conversations got slower. Chat switching leaked worse (20 chats visited
three times: 270 -> 452 -> 634) because the clear loop disposed only activity
feeds, never bubbles. Handlers are now tracked at connect time and cut on
disposal, recursively through every block inside the bubble.

### Gates that reported themselves intact

**Clustered short options walked past the destructive floor.** The interpreter
and shell branches matched their inline-code flag as an exact token, so `-c`
was recognised and `-Bc` was not -- and `-Bc` is what runs the code.
`bash -cx`, `bash -xc`, `sh -ec`, `sh -exc`, `bash -lc`, `python3 -Bc`,
`-uc`, `-BOc` all returned False from `is_catastrophic_command`. Each was
confirmed to really execute in a real shell first, using this project's own
marker method. Now 0 bypasses and 0 new false positives over a 34-command
benign corpus.

**`awk` and `sed` were on the introspection allowlist, and they execute.**
Membership there short-circuits both the quoted-argument recursion and the
unattributed-tool backstop, so `awk 'BEGIN{system("nmap -sS 8.8.8.8")}'` was
allowed with `tools=[]`. Moving them wholesale would have been the wrong
trade -- `sed 's/nmap/x/' notes.txt` and `awk '{print $1}' scan.txt` are
ordinary text processing -- so the decision is made on the program text, and
only the forms that can actually spawn a process are treated as executors.
The first draft of that pattern matched a pipe beside a quote, which read
`awk 'BEGIN{FS="|"}'` -- the most common awk idiom there is -- as an executor;
the counter-property corpus caught it before it shipped.

**Single-label hosts were dropped on the floor.** `nmap -sS acme.com dc01`
extracted `['acme.com']` and was allowed, while nmap resolves `dc01` through
the DNS search domain and scans it. One in-scope operand laundered an unlisted
host. A bare label has no authoritative form to match a scope rule against, so
it is refused as uncertain with an explanation, not silently kept.

The first draft of that fix escalated on any leftover positional and refused
`dig acme.com A`, `amass enum -d acme.com` and `nmap -sV --script vuln
10.0.0.5` -- a record type, a subcommand, and an unknown flag's operand.
Narrowed to tools whose positionals are host specifications and nothing else,
and to labels that do not follow a flag. 19 ordinary in-scope commands, none
refused.

### Features that silently did nothing

- **The heavy-effort rung never fired.** It was guarded by `not _auton`, and
  `migrate_settings` pops `approval_mode` outright, so `_auton` is always True
  and the branch was unreachable. `hard_engagement_model` was never consulted
  and the larger token budget was never granted.
- **Vision was broken out of the box.** The default `vision_model` named a
  model no provider in the registry carries, so every image read failed with
  an error blaming a setting the operator had never touched. The default now
  names a model the catalogue actually advertises as vision-capable, and a
  stale id repairs itself at call time.
- **`launch_app` discarded its arguments** on the gtk-launch path and still
  reported `ok: True` -- so `launch_app("firefox", "https://acme.com")` opened
  an empty browser and told the model the URL had been opened.
- **`tool_screenshot("shot.png")` always failed.** A bare filename gives
  `os.path.dirname` of `""`, and `os.makedirs("")` raises, outside any try.
  The most natural argument was the one guaranteed not to work.
- **`web_read`'s contract claimed a gate it does not have.** The docstring
  said any non-trusted public host needs operator approval; the gate lives in
  the GUI wrapper behind `if self._unleashed`. A tool docstring is what the
  model reasons from, so a safety property that does not hold in the default
  mode is worse than none. The SSRF floor, which really is unconditional, is
  now stated first.
- **`FOO=bar sudo ...` got no askpass.** `command_needs_sudo` accepts leading
  environment assignments; `_inject_askpass` did not, so the host prompted for
  the password, wrote the helper, and then ran a `sudo` with nothing to reach
  for -- which on a thread with no tty hangs until timeout. Both now share one
  prefix.
- **A namespaced tool name was unreadable.** `_NAME_ATTR_RE` accepted only
  `[a-zA-Z_]+`, while the dialect normaliser directly above it emits names
  captured as `[A-Za-z_][\w.-]*`. So `<function=functions.web_read>` was
  faithfully rewritten to `<tool name="functions.web_read">` and then refused
  by the regex meant to read it back: the call leaked onto the screen as raw
  markup and never ran.

### Two quadratic passes on attacker-supplied bytes

`_wr_html_to_text` stripped script/style blocks with a lazy `.*?`, which on an
unclosed `<script>` expands to end-of-string and fails -- from every opener in
the page. This is fed by `web_read`, i.e. by bytes chosen by whoever is on the
other end of the fetch, on the thread the operator is waiting on. Replaced
with a linear forward walk; the anchor-text pattern, which has the same shape,
is bounded.

### Evidence and workspace

- **The ledger had no chain.** Every line was integrity-checked in isolation,
  so deleting a whole line with its artifact came back `intact: true` -- and
  the cheapest, likeliest edit is the one that leaves no mark. Worse, the step
  counter was "line count + 1", so removing a line made the next event reuse
  an existing step number and *overwrite* that step's artifact: one deletion
  destroyed a second piece of evidence, silently. Events now carry `prev` and
  `entry_sha256`, `verify()` walks the links and names the step where the
  chain breaks, and step numbers only ever move forward.
- **`export_zip(out_path=...)` wrote anywhere on disk.** Every other path in
  the workspace module goes through `_confine`, but the default export
  destination is deliberately *outside* the workspace, so this argument was
  left unchecked entirely. Now confined to the workspace, its parent and the
  operator's home, never silently overwriting, and never conjuring a directory
  tree on the way.
- **The zip-bomb caps were consulted second.** `zf.testzip()` fully
  decompresses every member and ran *before* `_safe_members`, the function
  holding the caps -- so the archive the size cap exists to refuse was expanded
  in full before anything was allowed to say no. Filter first, then verify CRCs
  over the accepted members only.
- **The export gate could be unlocked by running the tests without a
  baseline.** `compare_to_baseline` zeroed `edits_since_verify` before the
  no-baseline early return, so a run that by its own admission attributes
  nothing left the gate with nothing to object to.
- **A skill could be saved with a test that proved nothing.** The runner
  appends `print('SKILL_TEST_OK')` precisely so that reaching it proves the
  test body ran, and nothing read it -- the only condition was rc 0, which an
  empty test, a bare `sys.exit(0)` or a comment all satisfy. The marker is now
  read, and a test with no `assert` is rejected before it runs.

### GUI, the rest of it

- A reply in flight survived a chat switch as a widget with no parent: the
  finished answer went into the database and was invisible until the operator
  happened to switch chats again. It is re-attached to its own chat now.
- Activity feeds were spending the 20-row display budget, so a 12-turn
  agentic chat showed 13 exchanges where a plain one showed 20. The budget
  counts conversation rows.
- An empty user message rendered as a padded capsule with nothing in it
  (`"\n\n"` produced a 210px blank bubble).
- The window declared a 360px minimum while its content pane needs 480, which
  does not make things fit -- it clips them off the right edge, with libadwaita
  saying so on every layout pass. The message bubbles were never the
  constraint; every block type wraps or scrolls cleanly down to 350px. The
  declared minimum is now the true one.

### Tests

49 suites, 3,306 checks. `tests/test_v1_regressions.py` is new and every check
in it fails against v9.9.2 -- including the counter-property corpora, because
three of these fixes over-blocked on their first draft and the corpus is what
caught it.

## v9.9.2

### The overflow, and two bugs I had introduced myself

**`strip_tool_calls` was deleting the end of ordinary sentences.** The
partial-tag hider added in v9.9.0 built its prefix ladder down to ONE
character, so `t` and `f` -- prefixes of `tool_calls` and `function_calls`,
and the first letter of half the words in English -- looked like the start of
an arriving tag. A reply ending "the loop runs while i < t" was truncated to
"the loop runs while i", in what was rendered AND in what was written to
`chats.db`. It also tolerated whitespace after the angle bracket, which a real
tag never has.

Fixed with a length floor (4, the shortest still tag-shaped prefix) and no
whitespace tolerance. Verified both directions: 10 hand-written sentences plus
20,000 fuzzed inputs lose zero characters, and a real DSML call still shows
zero frames of protocol across all 161 streamed frames.

**A list set a 597px floor under the whole window.** The `width_chars(20)` added
in v9.9.0 to stop the height-for-width explosion overshot in the other
direction: minimum width and minimum height trade against each other in a Grid,
and at 20 chars this one widget wanted 597px against 210px for ordinary prose,
so a bullet list was the widest thing in the application. Measured across the
range (0/4/6/8/10/14/20 chars -> 77/113/151/189/227/303/417px) and settled at
6: 151px, comfortably under prose, so the list is never the constraint, and the
height minimum it implies can only bite at a width prose already forbids.

### The newest message was landing below the fold

Every scroll was `GLib.idle_add(...)` then `adj.set_value(adj.get_upper())`, and
`upper` at that moment is still the value from BEFORE the new bubble was laid
out -- GTK has not re-measured. So the view jumped to the OLD bottom and the
newest message sat behind the composer. It got worse the taller the message
was, which is why it read as a "long conversation" bug: a one-line reply
happened to fit, a reply with a table or a code block did not. Anything that
changed height after layout -- an image finishing its load, a table reflowing,
streamed text rewrapping -- reopened the same gap.

The fix is not a longer timeout. It is to stop guessing when layout is done:
a stick flag plus a handler on the adjustment's own `changed` signal, which GTK
emits every time upper/page-size move. The flag clears when the operator
scrolls up and re-arms when he comes back down, so following the tail never
fights him. Verified: after a tall reply, after a new user message, and after
another tall reply, `upper - value - page_size` is **0** every time.

### README

Rebuilt as something worth looking at: an animated header and footer, a live
typing banner, a mermaid render of the verify loop, per-subsystem and
per-floor tables, an interface tour, and a table of real bugs with the method
that found each one. Every one of the 40 load-bearing facts, the anchors, the
disambiguation block and the version and assertion counts still pass
`tests/test_readme.py` (88 checks).

### Verification

**3,756 assertions across 48 suites, zero red.** New assertions cover the
partial-tag hider's prose safety, the minimum-width ceiling for every block
type, and the sticky-bottom scroll. Guardrail sha256 unchanged; assets
byte-identical.

## v9.9.1

### Bugs found by running the app, not by reading it

The v9.9.0 suites were green and the app still looked wrong on screen. Every
bug below was found by launching the real window headlessly against a seeded
conversation and looking at what it drew and what it printed to stderr.

**`Gtk.Button.set_icon_name()` throws away the label.** The read-aloud control
was built as `Gtk.Button(label=" Listen")` and then given an icon name, which
REPLACES the child - so the word was silently discarded and the control
rendered as a bare icon circle floating under the reply, attached to nothing.
Nothing errored; it just looked broken. The child is a box now, with both.

**The chat watermark was a picture, not a watermark.** A bright 1672x941 photo
at opacity 0.5 with `ContentFit.CONTAIN`. Contain letterboxes a landscape image
inside a tall pane, so the art appeared as a glowing BAND across the middle of
the conversation with plain background above and below it - which is what made
it read as content someone had pasted in rather than as a backdrop, and it
fought every line of text over it. Now 0.10, `COVER`, and loaded through the
shared texture cache at a bounded 1100px instead of a 6MB RGBA texture that
`COVER` rescaled behind the chat on every scroll frame and every streamed
token.

**Overlay scrollbars float on top of content**, so the rightmost thing in a row
- the user's avatar - was drawn underneath the scrollbar. The message list
reserves the gutter.

**The window had no minimum size.** libadwaita said so 25 times in a 16-state
sweep. Without one there is nothing for the adaptive machinery to break
against, so a narrow window can squeeze children past their own minimums -
which is how widgets end up overlapping in the first place.

### The one that would have shipped: pycairo

`pyproject.toml` declares `pycairo` as a hard dependency. **`install.sh` - the
recommended path, the one the README documents - never installed it**, and
`python3-gi` does not pull it in on Debian or Kali.

Without it PyGObject cannot marshal a cairo context into a Python draw callback
*at all*: it raises `TypeError: Couldn't find foreign struct converter for
'cairo.Context'` in the BINDING layer, before a single line of the callback
runs. So `DragonSplash`'s own try/except never saw it, its docstring's promise
to degrade gracefully "if no cairo" was false, the splash painted nothing, and
stderr took that line at 60fps for the whole animation.

Fixed three ways: the installer installs the binding on apt/pacman/dnf, checks
for it separately from GTK, and `DragonSplash` now probes for it BEFORE
building the DrawingArea - which is what actually makes the docstring true,
because the caller already treats a raise there as "skip the splash".

### The activity feed is docked, not scrolled

It lived in the message list, so after two or three more messages the one
widget telling you what Basilisk is doing had scrolled off the top. A status
surface you have to go looking for is not a status surface.

It is pinned above the action buttons now, always in view, outside the scroller
and therefore outside the rolling trim. One per turn still; a new turn retires
the previous one through the dock (which stops its clock, or every turn would
leave another 200ms timer running for the life of the process), and switching
chats empties it. Replayed history feeds still render inline in the transcript,
because those are records of past turns rather than live status.

### Idle lag

`.chat-row.selected` carried `animation: metalglow 3s ease-in-out infinite`.
That rule is on the SELECTED chat row, which is on screen from the moment the
app opens until it closes - so a repaint loop ran forever, at idle, for a glow
nobody looks at. It was the only always-on animation in the stylesheet. Now
static; every animation that remains is gated behind a state class (`.working`,
`.live`, `.busy`) and stops when the work does. A duplicate dead `sendglow` on
`.send-button.working` went with it.

Combined with the bounded watermark texture, that removes the two things that
were costing frames while nothing was happening.

### Verification

New `tests/test_guiwiring.py` (37) - the bugs above pinned as properties, plus
an audit that fails if any infinite animation loses its state class. **3,744
assertions across 48 suites, zero red**, verified from a clean extract.

Method note, because it is the reusable part: the app is now driven headlessly
through 19 states (terminal panel, sidebar, attachments, empty chat, live feed,
chat switch, working state) with GTK criticals counted per state, and a full
streamed turn is simulated token-by-token in both DSML pipe renderings. Zero
criticals, zero cairo errors, zero adwaita warnings.

## v9.9.0

### DeepSeek-V4-Flash: the tool-call dialect was arriving in a pipe rendering nothing matched

The DSML pass was gated on `_DS_PIPE in text` — U+FF5C, the fullwidth vertical
line DeepSeek's special tokens are written with. Deployments emit the same
block with **ASCII pipes**, doubled:

    <||DSML||tool_calls><||DSML||invoke name="web_read">…

That is a tokenizer rendering difference, not a different protocol. But with
ASCII pipes the gate was false, the whole pass never ran, and the block was
neither executed **nor stripped** — so raw `<||DSML||invoke name="web_read">`
printed into the chat and the tool never fired. Reproduced verbatim from the
field report before changing anything.

Matching is now on a **class** of pipe-shaped characters (U+FF5C, ASCII `|`,
U+2502, U+01C0), any count, any mix — widened *only* where the literal word
DSML makes the match unambiguous. The generic `<｜…｜>` special-token stripper
stays fullwidth-only, because `<|x|>` in ASCII is a shape that legitimately
occurs in prose and code.

Reproduction of the twelve shapes reported in the wild, before and after:

    ASCII-degraded <||DSML||>          BROKEN -> ok
    ASCII single-pipe <|DSML|>         BROKEN -> ok
    corrupted <function_cinvoke>       BROKEN -> ok
    canonical, doubled, toolcalls,
    wrapper-omitted, no-newlines,
    string=false, empty args, ...      ok     -> ok

**And a bug that hit the canonical spelling too.** Stripping the sentinel
turns the batch wrapper into a plain `<tool_calls>` … `</tool_calls>` pair, and
nothing removed it: `TOOL_TAG_RE` matches `<tool` followed by a word boundary,
and `tool_calls` continues with `_`. So **every successful V4 tool call left
`<tool_calls></tool_calls>` sitting in the reply** — canonical spelling
included. The completed-text test missed it because the probe only looked for
`DSML`, `invoke` and `parameter`; a character-by-character stream replay is
what found it.

Replaying a reply one character at a time, counting frames that show protocol
to the operator:

    ascii-degraded    197 frames    old: 171 leaked    new: 0
    canonical         185 frames    old: 145 leaked    new: 0

Also fixed: corrupted `\w*invoke` spellings (`function_cinvoke`) are accepted
in both the rewrite and the quadratic-guard probe, which have to stay in step
or a spelling the rewriter knows silently never runs; a partially-arrived
sentinel is hidden by a **prefix ladder** anchored at end-of-buffer, and the
guard for it reads a fixed 512-byte tail rather than the whole buffer — by
that point the normaliser has stripped the word out of every *complete* tag,
so `_has_dsml()` was false exactly when the pass was needed.

**Counter-property:** 6,027 benign inputs (27 hand-written plus 6,000 fuzzed)
through the old and new parsers — **0 new tool calls parsed from prose, 0
characters of legitimate text lost**. The first cut of the partial-tag matcher
had every component optional, so it matched a bare `<` plus 200 characters of
prose at the end of the buffer and would have deleted `x < y and some more
text` from a reply. Rewritten as an explicit prefix ladder where every branch
requires at least one pipe.

**Sampling now follows the vendor.** DeepSeek's model card asks for
temperature 1.0 / top_p 0.95 in agentic scenarios — which is every turn this
app takes — against shipped defaults of 0.7 / 0.9. Applied per model family,
and **only when the operator has not chosen**: if the setting still holds the
value this file ships, nobody picked it. Set your own and it is respected.

### Tables, headings, quotes and lists render as themselves

A model answering a comparison question replies with a table. That is not an
edge case, it is the most common shape of a structured answer — and it
rendered as literal pipe characters in a proportional font, where the columns
do not line up. The most structured thing the model could say was the least
readable thing on screen.

Markdown tables now draw as a real grid: header row, per-column alignment read
from the `:---:` markers, zebra rows, cell borders, inline markdown inside
cells, horizontal scrolling for wide ones so a table can never push the bubble
wider than the window. Headings, blockquotes, horizontal rules and bullet /
numbered lists each get their own compartment; lists get a real hanging indent
so a wrapped bullet stays aligned under itself.

**The bug worth writing down is the sizing one.** A wrapping `Gtk.Label`
reports a minimum width of about two characters, GTK asks "how tall are you at
that width", and the answer is astronomical. Measured on the first cut:

    four-column, three-row table    2104 px of requested height
    three-bullet list               2479 px
    whole message container         2692 px

GTK said so out loud — `reports a minimum width of 20, but minimum width for
height of 1048576 is 33` — and nothing was watching for it, so a reply with a
table in it was followed by a screenful of empty bubble with the rest of the
answer pushed off the bottom. Wrapping cells inside a horizontally-scrolling
container is a contradiction anyway; cells are single-line with the table
scrolling (which is also what a web table does), a long cell keeps its full
text in a tooltip, and list labels carry a real minimum width. Same content
now measures **273 px, 345 px and 982 px**, with zero GTK criticals.

A separator cell may legally be a **single** dash (`|:-:|`, `|-|`) and models
emit both; requiring two silently rejected every centre-aligned table. Caught
by the new suite, not by reading.

The type scale was inverted — headings were sized 20-25px against 30px body
copy, so an `###` rendered *smaller* than the paragraph under it. Everything
is now sized relative to the body: headings above it, table text just below.

### Bubbles: calm, not dim

The previous pass stacked six shadows per bubble — two inner glows, an outer
ring, a drop shadow and a coloured halo — over two radial gradients and a
linear one, plus a 9px orange `text-shadow` behind 30px body text. Every
element was individually defensible and the sum was a screen where nothing sat
still and long text had a permanent haze behind it.

What separates a bubble from the background is one clear edge and one soft
drop shadow. That is what is left. The ember identity moved to where it costs
nothing to read: a tinted border, a barely-there top highlight, and a hover
that lifts. The corner seal drops to 16% opacity — it is atmosphere, not
information, and at full strength it sat behind the last line of every reply.

### Attachments live above the composer

Attaching a file pasted its contents **into the input box**: a 40 KB text file
became 40 KB of text in the box you are trying to type in, an image became a
line of raw markdown, and removing one meant hand-deleting the right fence.

They are chips above the composer now — kind, name, size, and an × — and the
payload is folded in at send in **byte-identical** form to what the old code
produced, so the stored message, the rendered bubble and what the model reads
are exactly what they were. An attachment with no typed text is now a valid
send; the old early-return on empty text would have discarded it.

### NetHunter Pro is gone; CachyOS and Kali are the targets

Every NetHunter reference is removed from the code, persona, installer, docs,
site and tests. What replaces it is detection of the two distros that actually
change what Basilisk should **do**, read from `ID`/`ID_LIKE` so one parse
settles both the flavour and its base:

- **CachyOS** — pacman/paru, not apt; security tooling comes from BlackArch or
  the AUR, and many Kali package names do not exist there.
- **Kali** — apt and the `kali-tools` metapackages; most offensive tooling is
  already installed, so check with `which` before installing anything.

Two real installer bugs fell out of that work:

- **`sudo` was hardcoded 18 times.** Running as root (a Kali root shell, a
  container, a rescue boot) or on a `doas`-only box, the install died on the
  first package step. Escalation is now detected — root → empty, else sudo,
  else doas — and every call site routes through it.
- **`pacman -Sy` is a partial upgrade**, the documented way to break an Arch
  or CachyOS box: the new package links against libraries the system has not
  upgraded to yet. Now `-S --needed` against the database the operator already
  has, with a clear message to run `-Syu` himself if a package is missing.

### README

63,645 bytes and 650 lines down to **25,853 and 333** — under half. The badge
scaffolding and the fifteen-badge nav row are gone, twenty-three headings
became ten, and the benchmark tables and every load-bearing fact are kept.
`tests/test_readme.py` still pins all forty of them, plus the anchors, the
disambiguation block and the version and assertion counts.

### Also

- Cited sources render as links (`text_to_pango` knew bold, italic and inline
  code and nothing else, so every leashed citation ended in literal
  `[kernel.org](https://…)`), with the renderer checking its own output for
  well-formed nesting and falling back rather than letting GTK print raw
  `<span font_family=…>` mid-answer. Over 30,000 adversarial strings: old
  renderer 382 rejected, new 0, regressions 0.
- Avatars are decoded once per (file, size) instead of once per bubble —
  11.17 ms → 0.0003 ms, roughly half a second of frozen UI removed from every
  chat switch.

### Verification

New `tests/test_richblocks.py` (44). **3,704 assertions across 47 suites, zero
red**, verified from a clean extract of the shipped zip. Against real GTK
4.14 under Xvfb: the stylesheet parses with zero errors, zero GTK criticals
across the structured blocks, and 40 table edge cases (9 columns, ragged rows,
4,000 rows, escaped pipes, unicode, prose-that-is-not-a-table) all build
inside sane bounds.

`basilisk_persona.py`'s immutable GUARDRAIL block is byte-for-byte unchanged
(sha256 verified before and after). No asset or button was touched.

## v9.8.0

### Leashed mode narrates itself: a live activity feed that folds back to one line

Answering a question used to look like this: the status pill said `working…`,
the chat filled with two or three bubbles that each read `(working…)`, and the
only place that named the actual tool was the terminal panel — which is
collapsed by default. Three separate surfaces, none of them the one the
operator was looking at.

There is now ONE activity feed per operator turn, above the reply. It streams
live while the turn runs — tool, argument, duration, outcome, and a short
receipt of what came back — and folds itself shut to a single summary line when
the turn settles. Clicking the header toggles it, and a click PINS that choice
so the auto-collapse never slams shut a body you just opened.

One feed per TURN, not per model round-trip. A leashed question that chains
eight reads is one question, and splitting it across eight widgets is precisely
what made a single answer look like four separate replies.

**The honesty rules, because this project has shipped the opposite three
times** (`→ running <lambda>` for 150 of 151 tools; `✓ done` printed
unconditionally over failures; a `used X` row for a call the repeat guard had
refused):

- a step is marked FAILED when its result says the tool did not run — `NOT RUN`,
  `error:`, `ok:false` and `Unknown tool` all lose the tick;
- a step still open when the turn tears down is marked STOPPED. A spinner left
  spinning over an ended turn is the UI lying;
- the verdict comes from the ENVELOPE, never the payload, so a page whose text
  contains the word "error" is still a success;
- a row replayed from history is NEUTRAL — no tick, no duration. The store
  records that a tool was CALLED and never records whether it worked, so a tick
  there would be unfalsifiable;
- the header clock is wall time from the first event, so a stall is visible
  instead of looking like fast work.

**A parallel batch gets one row per tool**, each closing on its own worker's
result. The single status line had one slot for four concurrent tools and could
not represent that run at all; closing them together would paint four rows all
finishing at the slowest one's time, which is a false picture.

**Refusals and guards now reach the operator, not just the model.** The
catastrophic-command block, the foresight refusal, the self-source-tamper
refusal, the repeat guard, the research budget, the deferred-call queue and a
stream retry each write a line into the feed. Every one of them already told
the model why; the operator got a stall with no reason attached.

**The mode is named once per turn** — `LEASHED - answer mode: research, verify,
answer once, stop`, or `UNLEASHED - mission active` — on the first round-trip
only. Re-stating it after every tool result is the same mistake the
request-scoped directives made in v9.5, and it would have printed the mode ten
times in a row.

### The bubbles the feed replaced

A reply carrying only tool calls is a step, not an answer. Those bubbles used
to render `(working…)` or a one-line action summary, live and on reload — which
is the whole of the "it answered me four times" complaint. They are no longer
drawn; the feed carries them. Reloading a chat rebuilds the same shape: a
turn's tool calls collapse into one folded feed, parsed from the `tool:` line
already on disk rather than from a new column that would only show history for
chats recorded after this build.

Visibility keys off an explicit bare-tool-step flag, NOT off "the display text
came out empty" — a `propose` turn also ends with empty text and draws its
approval card into that same container, so the obvious test would have rendered
a card into a hidden bubble and left the operator waiting to click something
that was not on screen.

### Avatars were decoded from disk once per message bubble

`Avatar()` called `Gtk.Image.new_from_file()` every time it ran, and it runs
once per bubble. `basilisk-avatar.png` is 512x512 and measures **11-16 ms** to
decode through GdkPixbuf.

- a leashed question chaining twelve round-trips paid ~150 ms of main-thread
  decode, arriving in 12 ms chunks exactly when each new bubble appeared;
- opening a chat was worse, because the whole window is built at once: forty
  rendered messages is roughly **half a second of frozen UI on every chat
  switch**, for forty identical decodes of two files.

A `Gdk.Texture` is immutable and made to be shared. One decode per (file, size)
now serves every image for the life of the process: **11.17 ms → 0.0003 ms**
after the first. Misses are remembered too, so a missing file is not re-opened
and re-failed once per message. `_svg_texture` shares the same cache.

### Cited sources render as links

ANSWER MODE orders the model to "CITE what you used: name the source or paste
the link", so nearly every leashed reply ends in a citation — and every one of
them rendered as literal `[kernel.org](https://www.kernel.org/)`.
`text_to_pango` knew bold, italic and inline code, and nothing else.

Markdown links and bare pasted URLs are now anchors. The implementation is not
"one more `.sub()` alongside the others", because that fails loudly in both
directions: a URL is not prose, `*` and `` ` `` are legal in one, and
ITALIC_RE matching inside an href injects a tag into an attribute value —
which makes `set_markup` fail and drops the ENTIRE message to plain text. Links
are pulled into Private Use Area sentinels first and restored last, so neither
pass can see the other. A URL inside backticks stays code.

**And the renderer now checks its own output.** The three inline passes each
run over the whole string independently and cannot guarantee their tags nest:
on stray asterisks and backticks they produce `<i>a<span>b</i>c</span>`. GTK
does not raise on that — it logs a warning and renders the RAW MARKUP, so
`<span font_family=...>` appears mid-answer. Measured over 30,000 adversarial
strings, **the old renderer emitted 382 such strings**. Output is now checked
for well-formedness and falls back — first to links-only, then to plain escaped
text.

    rejected by the old renderer   382
    rejected by the new renderer     0
    new breaks what old handled      0

Counter-property asserted as hard as the property: over 4,000 realistic replies
mixing bold, italic, code and links, **100% still get the full formatting** —
a renderer that stops rendering is not a fix. The link scan uses bisect over
the code spans, not a linear scan, because this file has shipped a quadratic
display path twice already; scaling is linear (ratio 2.0 per doubling).

### Also

- The status pill and the feed header read the same phrase from the same
  `_set_working` call, so the two cannot disagree about what is happening.
- Feed glyphs are ASCII where the emoji font would otherwise claim the
  codepoint: U+26D4 was substituted by the emoji face, which ignores the row's
  colour and metrics, so a refusal row rendered wider and in the wrong palette
  than every row around it.
- Sub-millisecond work reports `<1ms` rather than `0ms`, which read as
  "did not run".
- Reply links are `#ff9a44` instead of the deep `#7d121b` accent, which was
  nearly inseparable from body text inside a charred bubble.
- Body text lost its 9px orange glow. Glow belongs on the border and the
  surface; behind 30px text it reads as a focus problem.
- Every feed teardown path stops the widget's 200 ms clock — chat switch,
  rolling trim, and finish. The trim never disposes the LIVE feed, because the
  view's trim and the window's live pointer are independent.

### Verification

New `tests/test_activity.py` (111 assertions). **46 suites, 3,669 assertions,
zero red**, verified from a clean extract of the shipped zip. Additionally
verified against real GTK 4.14 under Xvfb: the whole stylesheet parses with
zero errors, the widget builds and drives, 400 steps stay inside the display
cap at 0.25 ms each, and every `text_to_pango` output is accepted by
`Gtk.Label.set_markup` with no log warning.

`basilisk_persona.py` is byte-for-byte unchanged (whole-file sha256 verified
before and after). No asset, button or provider behaviour was touched.

## v9.7.0

### The destructive floor let 21 command shapes through — verified against a real shell

`is_catastrophic_command` is the no-override backstop at the execution
primitive. Under UNLEASH nobody is on the trigger, so it is the only thing
between a model's mistake and a wiped disk. It let these run:

    $(rm -rf /)              ( rm -rf ~ )            timeout 5 rm -rf /
    `rm -rf /`               { rm -rf $HOME; }       nice -n 5 rm -rf /
    echo "$(rm -rf /)"       if true; then rm -rf /; fi    ionice -c3 rm -rf ~
    bash -c '$(rm -rf /)'    f(){ rm -rf /; }; f     stdbuf -o0 rm -rf /
    trap 'rm -rf /' EXIT     sh <<< 'rm -rf /'       sudo -u root rm -rf /
    echo x | xargs -I{} rm -rf /                     sudo timeout 10 rm -rf /
    echo x | xargs -I{} mkfs.ext4 /dev/sda1          timeout 5 nice -n 3 rm -rf /

**Method note, because it decided the result.** A blind fuzz of 40,000
mutations reported 18,856 "leaks". Almost all were shell syntax errors —
`r"m -rf /`, `RM -RF /`, `sh -c 'rm\t-rf\t/'` — that never execute and never
mattered. Every shape was then re-run against a live bash with the destructive
verb replaced by `touch MARKER`, and kept only if bash created the marker.
Twenty-one survived that filter. Counting the other 18,835 would have buried
them.

Three root causes, none of them "the blocklist was too short":

1. **The peel loop was arity-blind.** It skipped a wrapper *word* but not that
   wrapper's own *options*. `nohup rm -rf /` was caught because nohup takes no
   flags; `nice -n 5 rm -rf /` peeled `nice`, landed on `-n`, stopped, and
   judged a command called `-n`. `sudo -u root rm -rf /` had been broken the
   same way the whole time. This is why the fix is an arity table
   (`_PREFIX_RUNNERS`, which knows what each wrapper's own options and leading
   positionals look like) and not a longer word list — adding `timeout` to the
   old set would still have left `timeout 5 rm -rf /` open. A wrapper's
   positional is only eaten when it *looks* like one, so `timeout rm -rf /`
   does not silently swallow the `rm`.

2. **No grouping awareness.** `_split_subcommands` knew `; && || | &` and
   nothing about `( )`, `{ }`, `if/then`, or function bodies, so argv[0] came
   back as `(`, `{` or `then`. `(`, `)` and backticks are now separators — a
   subshell boundary *is* a command boundary — and `_strip_struct` drops
   leading structure tokens.

3. **Command substitutions were never entered.** `sh -c` and `eval` recursed;
   `$( )` and backticks did not. `_substitution_payloads` now lifts them,
   including from inside double quotes where the splitter cannot reach.
   An unterminated opener is a bash syntax error and never runs, but its tail
   is still scanned at top level rather than silently dropped — that exact
   shape was a real fail-open in `basilisk_scope` at v7.9.4.

Also closed: `trap '…' EXIT`, `sh <<< '…'`, and `xargs`, which now recurses on
whatever it runs instead of special-casing `rm` (that is what kept
`xargs -I{} mkfs.ext4 /dev/sda1` open). The deferral is preserved:
`find / | xargs rm -rf` has no literal operand, so the recursion finds nothing
and the pipe-chain rule still owns it.

**The counter-property was checked as hard as the property.** A floor that
fires on `rm -rf ./build` gets switched off, and then it protects nothing.
Differential over a 70-command corpus of ordinary pentest and dev work:
**0 new false positives, 0 regressions.** Cost on a realistic command:
75µs → 81µs.

The scope gate did **not** share this hole — it marks every grouping form
`uncertain` with a stated reason and fails closed, because it scans for targets
across the whole string instead of trusting argv[0]. `command_tampers_self`
also held. Same input class, one gate structural, the other positional.

### Four quadratic regexes on the streaming path, one of them a 3.5-second freeze

`strip_tool_calls` runs on every streamed frame, over the whole buffer so far,
on the GTK main thread. v9.6.0 fixed `_ALT_PARTIAL_RE` (25s) and shipped four
more of the same shape in the neighbouring code.

| shape | v9.6.0 | v9.7.0 |
|---|---|---|
| model repeats `<tool ` opener ×4000, one pass | 3558 ms | **18 ms** |
| `_SELF_WRITE_RE`, 176KB command | 101 s | **1.3 s** |
| large `write_file`, total CPU across the stream | 38.7 s | **13.0 s** |
| `clean_for_speech`, 4000 openers | 728 ms | **0.6 ms** |

- `TOOL_TAG_RE`'s bare-word attribute alternative did not exclude `<`, so one
  opener's attribute blob swallowed every following opener and then backtracked
  through the lot looking for a `>`. Quoted attributes may still contain `<`;
  only the bare-word form excludes it.
- `TOOL_PARTIAL_RE` and the final display scrub had unbounded `[^>]*` runs.
  Bounded at 4000 — an opener's *attributes* are short, the long part is the
  body, which comes after the `>`.
- `_SELF_WRITE_RE` had unbounded lazy gaps. Bounded at 1024, and the bounded
  form agrees with the unbounded one on **6,528 constructed commands, 0
  disagreements**, diverging only past a 1024-char gap.
- `command_needs_sudo`, `headroom._TOOL_RE` and `clean_for_speech` got exact
  presence guards (the patterns cannot match without `sudo` / `</tool_result>`
  / `</tool` respectively, so skipping is exactness, not a heuristic).

**And the one that no regex fix would have solved:** the render recomputed the
strip over the *entire* buffer once per token, which is O(n²) in reply length
however fast the regexes are. That is now coalesced to a 50ms floor — ~20
full passes per second regardless of token rate, with a trailing-edge flush so
the tail of a reply still lands, an immediate first paint so a slow opening
doesn't read as a hang, and a no-op after widget disposal. 2000 tokens across
2s of stream now cost 40 full strips instead of 2000.

The no-markup fast path in `strip_tool_calls` is byte-identical to the old
behaviour over 60,000 corpus inputs.

### Site, README and llms.txt

The front page was six releases stale (`softwareVersion` still read 7.6.0) and — the bigger miss — **repo-repair mode did not appear on the visible site at all**, despite being half the product since v7.10.0. That is the same gap the README had at v9.0.0, in the other document. It now has its own section covering the baseline, failure-set tracking, the export gate, and archive containment.

Also added, to all three documents: a **Verification** section (run the suite yourself; what the suite is actually for), and an honest write-up of the v9.7.0 self-audit — including that the twenty-one bypasses were real rather than theoretical, and an open invitation to report a twenty-second.

Left deliberately unchanged: the `v7.6.0` labels on the benchmark rows. Those record which build produced each score, and the benchmark has not been re-run on 9.7.0.

### Tests

New `tests/test_safety_gate.py` (155 assertions) and `tests/test_streamperf.py`
(42). Both **fail against v9.6.0** — the gate suite on all 21 shapes, the perf
suite on latency *and* on the scaling exponent (`4x input costs 16.0x time`),
which is the assertion that does not pass by luck on a fast machine.

31 suites, 1,886 assertions, zero red. `basilisk_persona.py` sha256-identical
to v9.6.0 (`1f755d478a32ee41`), GUARDRAIL slice unchanged; `basilisk_scope.py`
and `basilisk_ledger.py` also byte-identical. compileall and `bash -n
install.sh` clean. No new module, so `install.sh` is unchanged.

**Known, pre-existing, not introduced here:** `tests/test_unblock.py` has
wall-clock assertions that can flake when the whole suite runs under load; 12/12
clean in isolation on both v9.6.0 and v9.7.0.

## v9.6.0

### DSML: the model's tool calls were unreadable, and the log said the wrong thing about it

Reported: asked for a Steam recommendation, got `<｜DSML｜｜tool name="run">` and
`<｜DSML｜｜parameter name="url" …>` printed into the chat, a log alternating
between "syntax this build doesn't parse" and calls that ran with
`{"_raw": "<｜DSML｜｜parameter …"}` as their arguments, and no answer.

DeepSeek-V4 emits tool calls in **DSML** — an XML-shaped dialect where every tag
carries a `<｜DSML｜｜…>` sentinel built from FULLWIDTH VERTICAL LINE (U+FF5C),
and arguments arrive as **child tags** rather than a JSON body:

    <｜DSML｜｜tool name="run">
    <｜DSML｜｜parameter name="command" string="true">curl -s …</｜DSML｜｜parameter>
    </｜DSML｜｜invoke>

v9.1.0 taught the normaliser DeepSeek's *old* token format
(`<｜tool▁call▁begin｜>` … ```json). This is a different dialect from the same
vendor, and it broke in **two different ways in the same run** — which is why
the log reads like two separate bugs:

* **A — sentinel on the opener.** `TOOL_TAG_RE` matches `<tool`; the text starts
  `<｜DSML…`. Zero calls parsed, so nothing ran *and* nothing was stripped. The
  markup went to the screen as chat text. That is the pipes and boxes.
* **B — sentinel only on the children.** The tag matched, the body was not JSON,
  and the arguments became `{"_raw": …}`. `web_read` then ran **with no url at
  all** and logged `✓ done`. **This is the dangerous one**: it looks like a
  working call, so the loop never learns it got nothing and retries the same
  shape until the budget dies.
* **C** — good JSON discarded because a stray `</｜DSML｜｜invoke>` trailed it.

Fixed:

* **Sentinel stripped first**, in `_normalise_tool_syntax`, so parse *and* strip
  see identical text. That agreement is load-bearing: the moment they disagree,
  a call executes but survives stripping, and the raw markup reaches both the
  screen and the stored history — which then re-teaches the model that the
  broken format is acceptable. Tolerant of pipe count and of the slash sitting
  either side, rather than pinned to the one byte string in the screenshot.
* **`_params_to_args()`** decodes `<parameter name="x">value</parameter>`
  children into real arguments. Runs only when parameter tags are present, so a
  JSON-only body is untouched. `string="true"` is honoured — an appid like
  `221910` stays text instead of silently becoming an int. The five XML entities
  are unescaped; semicolon-less legacy forms are not, because
  `curl 'a&copy=1'` must survive byte-for-byte.
* **Two JSON salvage passes** — drop orphaned structural tags, then extract the
  first brace-balanced object. Fixes C.
* **An undecodable call is dropped, not dispatched.** A call whose only argument
  is `_raw` containing markup no longer runs blind; it falls through to the
  re-send path instead. Narrow condition: merely *malformed* JSON still passes
  through as before, so a half-written `propose_edit` is not newly discarded.
* Mid-stream DSML and orphaned child tags scrubbed from the display.
  Character-by-character replay of the reported reply: **258 leaking frames → 0**.
* The re-send correction now names DSML and `<parameter>` explicitly. Telling a
  model "that was wrong" without naming the format it used leaves it guessing.

### A 25-second UI freeze, found while hunting the same shape

Fixing the above, the first draft of the parameter decoder used the obvious
paired regex `<parameter …>(.*?)</parameter>`. That is quadratic when openers
outnumber closers — 5000 unclosed openers took **2.06 s**, on the UI thread, on
every streamed frame. Rewritten as a lockstep opener/closer walk: **8.5 ms**.

Then the same shape turned up in code that predates all of this:

    _ALT_PARTIAL_RE = <open …>(?:(?!</close>).)*$

A lookahead per character per starting position, and `re.sub` tries every
position. On 3000 repeated `<tool_call name="x">` openers followed by ONE
`</tool_call>`:

    24,972 ms.

`strip_tool_calls` runs on **every streamed frame**, on the GTK main thread, with
no cancellation. That is a hard freeze multiplied by the frame count — and the
input is not exotic. **It composes with the DSML bug**: unparsed dialect → model
retries → model repeats itself (a known failure mode, which is what v9.1.0's
repeat guard exists for) → what it repeats is a tool-call opener → freeze.
Milder instances of the same shape: the paired dialect sub (1,475 ms on bare
openers) and `THINK_RE` (434 ms).

* `_ALT_PARTIAL_RE` / `_ALT_FUNC_PARTIAL_RE` replaced by `_cut_unclosed()`, a
  two-forward-pass scan. Closers only get scarcer left to right, so the first
  opener with no closer after it is the first opener past the *last* closer.
* Cheap closing-tag presence guards on the two paired `.*?` subs and on
  `THINK_RE` — if the closing tag is absent the sub cannot match anything, so
  the linear probe buys the whole scan for nothing.
* **Worst case 24,972 ms → 13 ms.** Differential-tested against the exact regex
  it replaces: 200,000 random inputs, **0 disagreements**. A faster function
  that answers differently is not a fix.

### The log was lying in four ways at once

None of these is a crash. All four are why a fifteen-minute bug took an
afternoon — a log that is wrong is worse than no log, because you believe it.

* **`→ running <lambda>…` on every line.** `_tool_simple` took its label from
  `fn.__name__`, and **150 of the 151 dispatch entries** wrap the call in a
  lambda to bind its arguments. The log could not tell you *which tool ran*,
  which is the first question you ask. The dispatcher already knows the name, so
  it now publishes it — set immediately before the call and cleared in a
  `finally`, because a stale name mislabels the *next* tool, which is worse than
  no name.
* **`✓ done` after a tool that failed.** The tick was unconditional, so a
  `web_read` that came back with `ok: false` and no url read exactly like a
  successful fetch. The same lie the parser bug told, one layer up. Now
  `✗ <tool>: <reason>` at error level. The result still reaches the model
  unchanged.
* **`forcing the final answer (empty reply)` when the real problem was an
  unreadable tool call.** Two label branches for three cases, so at the exact
  moment the log had the answer it named the wrong thing.
* **The status line printed twice in a row.** `_set_working` logs on every call
  and is called more than once per tool with the same label. Logs on change
  only; the pill still updates every call.

Also: when the re-send budget is spent, the operator is now told, instead of
being handed an empty bubble with no explanation.

### Verification

* **29 suites, 1,690 assertions, zero red.** `tests/test_toolsyntax.py` 106 →
  161; new `tests/test_toollog.py` (28). Both new suites **fail against v9.5.1**
  — they pin the bugs rather than describing them.
* The 25-second freeze is pinned as a **number**, not a comment. The tempered
  form is the obvious way to write that regex and someone will reach for it again.
* Fuzz: 120,000 mixed-dialect inputs through all five entry points, 0 crashes.
* Full-tree AST audit clean — zero mutable defaults, bare excepts, `subprocess`
  without timeout, `sqlite3.connect` without `check_same_thread`, bare
  `acquire`/`release`, `is` on a literal.
* `basilisk_persona.py`, `basilisk_safety.py`, `basilisk_scope.py`,
  `basilisk_ledger.py`, `basilisk_voice.py` sha256-identical to v9.5.1 —
  GUARDRAIL untouched. `compileall` clean.

### The OTHER half of the screenshot: extra tool calls were silently dropped (v9.5.1)

The dialect fix explained the pipes on screen. It did not explain why the model
kept saying its own calls were "malformed" and re-sending them. That is a
second, independent bug on the same failure path.

**`web_read` is deliberately NOT batchable.** The web readers were pulled from
the parallel batch set to shrink the prompt-injection surface — a real decision,
recorded in a comment, and left in place here. But the routing then does this:

    batch = []                       # leading run of PURE tools
    for c in executable:
        if self._pure_tool_fn(c) is not None: batch.append(c)
        else: break
    ...
    else:
        self._execute_tool_calls(executable[:1])   # <- the rest vanish

A reply containing two or three `web_read` calls produced an EMPTY batch (the
first tool is not pure), fell to `executable[:1]`, ran one, and **discarded the
others without a word**. The screenshot shows exactly that: two web_reads in one
message, three in another. The model got one result for three lookups, could
only conclude it had emitted bad calls, apologised — "my last two lookups
glitched on my end (malformed call)" — and re-sent them, to be dropped again.

**And the persona was telling it to do the thing that breaks.** "BATCH READS —
emit ALL their tags in the SAME reply." Instruction and implementation in direct
contradiction, which is the worst kind: following the documented rule was what
triggered the bug.

Fixed both ends without touching the security decision:
- The skipped calls are now REPORTED. The next tool result carries a note naming
  them, stating plainly that nothing was malformed and nothing was lost, and to
  re-issue them one per reply. A mystery becomes an instruction.
- The persona now says which tools do NOT batch (`web_read`, `web_sources`,
  `cve_lookup`, `image_search` — everything that reaches outside the machine)
  and that emitting two means only the first runs.

`test_persona.py` pins the agreement so the instruction can never drift away
from the implementation again.

## v9.5.0

### Google AI Studio removed — SiliconFlow is the only chat provider

Gemini could not reliably drive the app, and its free tier trains on submitted
prompts, which is the wrong place for engagement data. Removed. Anyone whose
config still selects `google` (or `groq`) is migrated to the primary, with a
generic guard so no future removal can strand a config on a dead selection.

Cleaning `install.sh` turned up a real mess in its fallback defaults: it listed
FIVE providers, including **`"google"` twice** (duplicate dict key — the second
silently won) and two, `novita` and `github`, that were never in the registry at
all. A default pointing at an unregistered provider can only ever fail. One
entry now, and a test asserts the installer names no provider outside the
registry.

### The oracle was unreachable on a single call

`basilisk.py` resolves a tool name in two places: `_pure_tool_fn` (parallel
batch) and `dispatch` (single call). `oracle_arm`, `oracle_check`,
`oracle_status` and `oracle_listen` were in the batch path ONLY — so
`oracle_check` called on its own, which is exactly how it is used right after
firing an exploit, fell through to:

    self._feed_tool_result(f"Unknown tool '{call.name}'.")

The oracle is the verified-exploitation core. "No proof, no finding" depends on
it entirely and every benchmark number was produced with it; a silent unknown-
tool turns every confirmed hit back into an assumption. Wired into `dispatch`.

**`tests/test_dispatch.py` (30 assertions)** now pins that the set of tools the
persona SELLS and the set the app can RUN are the same set, and that nothing
lives in the batch path alone — the drift signature that caused this.

### Playbooks — the model no longer has to improvise method

The reported screenshot showed it hand-rolling `html.duckduckgo.com/html/?q=…`,
because **there is no search tool** and nothing said so. It was rediscovering
that every run and getting it subtly wrong.

New always-loaded PLAYBOOKS section with exact sequences for: searching the web
(including that the non-`html.` domain is JS-only and returns nothing, that the
results page is never the answer, and a two-search ceiling before reading
something), verifying a current fact against a primary source, CVE research,
target enumeration, claiming a finding through the oracle (proof armed BEFORE
firing; a 200 is not evidence), repo repair (baseline first, read `broke` first,
never edit his tests), and batching reads.

Specialist steps are deliberately written WITHOUT a `<tool …>` wrapper — an
earlier draft wrapped them, which registered them as CORE tools, broke the
minimal-core invariant and would have implied they were already loaded when they
still need `load_tools`.

### Settings audit — one missing control, one unusable option

- **Research depth had no control at all.** `answer_tool_budget` was a hardcoded
  `.get(..., 18)` fallback that was not even in `DEFAULT_SETTINGS`, so it could
  neither be seen nor raised — while every `load_tools`, `web_search`,
  `web_read` and file read counted against it. Now a real setting (default 40)
  with a Settings row.
- **The transcription picker offered an option with nowhere to enter its key.**
  Groq stopped being a chat provider, so it stopped getting an API-key row from
  `_build_provider_group` — but it is still the Whisper backend and the picker
  still lists it. Added a dedicated "Groq API key (Whisper only)" row beside the
  setting that uses it, with a get-a-key link.
- `unleashed` — the master mode switch — was written by the toggle and read with
  a `.get` default but was never in the schema. Added.
- No dead controls found: every Settings row writes a key the app reads.

**METHOD NOTE:** the dead-setting check flagged `stt_model_siliconflow` and was
WRONG — it is read indirectly via `{"model_setting": "stt_model_siliconflow"}`
in basilisk_voice.py, which no `.get("literal")` regex can see. Acting on that
verdict would have deleted a live setting. The check now counts indirect use.
Third time in this project a checker has been wrong rather than the artifact;
validate the checker first.

### Housekeeping
- Version 9.5.0.
- 28/28 suites, 1,604 assertions, zero red.
- GUARDRAIL byte-identical. safety/ledger/voice/scope sha256-identical.

## v9.4.0

### Finishing the tool-dialect fix — the first pass was not enough

v9.3.0 taught the parser five dialects. Verifying it end-to-end rather than
unit-testing the parser found the fix was **one third complete**. Three separate
leaks remained, and the most visible one was completely untouched.

**1. Parse normalised, strip did not.** A native-token call therefore EXECUTED
(parse saw it) and SURVIVED stripping (strip did not). The raw special tokens
went to the screen AND into the stored message — so every later turn re-sent the
garbage to the model as history, wasting context and teaching it the broken
format was fine. Parse and strip must see the same text or one of them is always
wrong. `strip_tool_calls` now normalises first, and `_on_stream_done` normalises
ONCE at the boundary so parsing, stripping, the database, the history and the
widget all operate on canonical text.

**2. It still leaked the whole time it was streaming.** The end state being
correct is worth nothing when the reply is rendered on every token. Replaying
the reported reply character by character: **61 of 176 frames printed protocol
text**, starting with `<｜tool▁calls▁begin｜` — precisely the pipes and boxes in
the screenshot. Fixing only the final message would have left the visible
symptom entirely intact. Partial-fragment rules now hide a call that is still
arriving, mirroring what `TOOL_PARTIAL_RE` already did for the canonical form.

**3. The other four dialects leaked too.** Caught by the same replay after the
DeepSeek case was fixed: `<tool_call>`, `<invoke>` and `<function=>` each stayed
visible until their closing tag landed — 39 to 48 frames each. All five dialects
now measure **zero leaked frames**.

Verified end-to-end on the exact payload from the report: 2 calls parsed and
executed, operator sees `Good — that search landed…` and nothing else, stored
history contains the prose and nothing else.

**Two more bugs found while proving it:**
- A tool tag inside a ```` ```python ```` fence was EXECUTED — a reply that
  documented the tool syntax would fire the tool. Fences are masked before
  scanning; positions come from the mask while content is re-matched against the
  original, so a tag whose own body is fenced still yields its JSON.
- A canonical tag with a fenced JSON body fell back to `_raw` instead of
  parsing. Models format JSON that way constantly.

**Known and accepted:** a tool tag the model writes inside a code fence *as
documentation* is stripped from the display as well. Cosmetic, rare, and it errs
in the safe direction — the alternative reopens the leak.

**tests/test_toolsyntax.py: 68 → 106 assertions.** Adds the character-by-
character streaming replay for all five dialects, the parse/strip agreement
invariant, mixed dialects in one reply, and six prose cases (`a < b`, `<div>`,
`function=f(x)`, markdown autolinks, a grep pattern) proving nothing legitimate
is mangled.

### Housekeeping
- Version 9.4.0.
- 27/27 suites, 1,557 assertions, zero red.
- GUARDRAIL byte-identical. safety/ledger/voice/scope sha256-identical.

## v9.3.0

### The leashed-mode bug: found it, and it was a silent drop

Reported as "in leashed mode it hits the tool cap, or stops mid-read, and never
gives me the report". It is one bug with two faces, and it is in
`_on_stream_done`:

```python
# When the tool budget is spent we lock tools for the final answer
# turn — ignore anything the model still tried to call.
if self._tools_locked:
    executable = []
```

When the answer budget is spent, tools are locked and the model is told to
answer. If it instead emits **another tool call** — overwhelmingly likely,
because it was mid-research when the cap hit — that call is dropped **in
silence**. Nothing is fed back, nothing is logged to the model. The turn then
settles, `strip_tool_calls()` leaves an empty or near-empty bubble, and the
operator gets a blank reply to a question the model had half-answered.

Three fixes, all root-cause:

1. **A dropped call is now TOLD.** The refusal is fed back as a tool result
   saying the call was not run, nothing gathered is lost, and the full answer
   must be written now in prose. Costs one round-trip, converts a dead end into
   a finished answer.
2. **A turn can no longer settle with an empty answer.** If the visible reply
   after stripping tool calls is empty, that is a dead end regardless of cause —
   one more turn is forced demanding prose. Bounded at two attempts so a model
   that will not write prose cannot loop.
3. **The budget was too low and unreachable.** `answer_tool_budget` was a
   hardcoded `.get(..., 18)` fallback that **was never in DEFAULT_SETTINGS**, so
   it could not be configured. Every `load_tools`, `web_search`, `web_read` and
   file read counts against it, so deep research burned it while still working.
   Now a real setting, default 40.

### Groq removed, Google AI Studio added

Groq's chat catalogue was four models and it retired four of six chain entries
in three months. Google AI Studio ships an **OpenAI-compatible endpoint**, so it
drops into the existing backend with no new engine — and the free tier is far
larger: 1M-token context, ~1,500 requests/day, no card.

Catalogue: `gemini-2.5-flash` (workhorse, chain head), `gemini-2.5-pro`
(flagship, pickable but deliberately **not** on the chain — a 50-request/day
quota cannot carry an outage path), `gemini-2.5-flash-lite` (budget). Cached
pricing recorded (~75% off) since the prefix is now stable.

**Every model note carries the free-tier training warning**, and a test asserts
it. A pentest tool sending target responses and findings to a tier that trains
on them is a disclosure the operator must see *at the point of choosing*, not
buried in a doc.

**Groq's Whisper STT is deliberately kept.** It is a separate feature with its
own key; deleting it to satisfy "remove Groq" would have silently broken voice
input. Said rather than done quietly.

Migration hardened: any config still selecting Groq is moved to Google (if
keyed) or the locked primary — the old "respect a deliberate choice" marker no
longer protects a provider that does not exist. A new test asserts the general
property, so any future removal is covered too.

### README

Reframed from describing a tool to stating what it is and who may hold it: a
professional-only weapon, a "who this is for / not for" section, and the point
that privacy protects the operator and not the target — being untraceable is
not the same as being permitted. Version 9.3.0.

### The "DSML" garbage: the host only spoke one tool dialect (v9.3.0 addendum)

Reported with a screenshot: pipes and boxes and `name="web_read"` printed as
text, the model apologising for "malformed calls", and the turn ending without
doing the work. It looked like the model was broken. It was not — the host was.

`TOOL_TAG_RE` matched exactly ONE dialect, `<tool name=...>`. Measured against
the parser, every other form scored zero:

| Form | Parsed before |
|---|---|
| `<tool name="x">` | 1 ✅ |
| DeepSeek native special tokens | **0** |
| `<tool_call name="x">` | **0** |
| `<invoke name="x">` | **0** |
| `<function=x>` | **0** |

A call that parses to zero is neither executed NOR stripped, so it leaks to the
screen as raw protocol text and the turn ends with nothing to run — which is
both halves of the report at once.

**The pipes identify the culprit.** DeepSeek emits function calls as special
tokens built from FULLWIDTH VERTICAL LINE (U+FF5C) and LOWER ONE EIGHTH BLOCK
(U+2581). In a font without those glyphs they render as pipes and boxes. The
model was using its own trained tool syntax; the host understood one dialect and
had no way to say so.

**Fix 1 — speak the dialects.** `_normalise_tool_syntax()` rewrites DeepSeek
native tokens, `<tool_call>`, `<toolcall>`, `<function_call>`, `<invoke>` and
`<function=name>` into the canonical form before parsing. All now parse.

**Fix 2 — never fail silently.** Whack-a-mole on regexes does not fix the class,
so `looks_like_failed_tool_call()` detects tool-call-shaped debris in a reply
that produced no executable calls, and the host feeds back the exact working
format and asks the model to re-send. A malformed call explicitly does NOT lock
tools — it still needs to run, just in the right syntax.

**Fix 3 — the operator never sees protocol wreckage.** `scrub_tool_debris()` is
applied on the display path. Raw transport internals on screen tell him nothing
and make a working app look broken.

**Two more bugs found while testing this:**
- A tool tag inside a ```` ```python ```` fence was EXECUTED — a reply that
  documented the tool syntax would fire the tool. Fences are now masked before
  scanning. Positions come from the masked copy while content is re-matched
  against the original, so a tag whose own body is fenced still yields its JSON.
- A canonical tag with a ```` ```json ```` body fell back to `_raw` instead of
  parsing. Models format JSON that way constantly; it is unwrapped now.

**tests/test_toolsyntax.py, 68 assertions:** every dialect parses with the right
name and args; two native calls in one reply both parse; normalisation is
conservative (prose, HTML talk, `a < b`, and fenced examples invent nothing);
debris detection has no false alarms on clean prose; display scrubbing removes
every control token; an unterminated native call does not swallow the rest of
the reply; and 400 calls parse in under two seconds with no backtracking blowup
on a 400KB input.

### Housekeeping
- 27/27 suites, 1,519 assertions, zero red.
- GUARDRAIL byte-identical. safety/ledger/voice/scope sha256-identical.
- compileall + install.sh bash -n clean.

## v9.2.0

**Theme: the cache is now genuinely maxed out, and the README says what this
thing actually is.**

### Prompt caching, third pass — measured end-to-end, not per-component

Re-measured the WHOLE request (system + history + volatile) over 60-turn runs
rather than one component at a time, which is how the remaining leak was found.

**A third cache-buster: the history CAP also slid.** `assemble_messages` keeps
the last N-1 messages once a conversation passes `max_history_msgs`. That window
slides by one every turn, so the oldest kept message — and the request prefix
with it — changed every turn from the cap onwards. Measured: reuse held at 100%
up to turn 40 and then broke on **all twenty remaining turns**. Fixed by
quantising the drop into blocks (`HISTORY_DROP_BLOCK`), so the window re-anchors
occasionally instead of continuously. Same history dropped, prefix stable
between anchors. Stateless and deterministic — no bookkeeping needed.

**Verified headroom compression is prefix-safe** (94.8% with it on, same as
off) rather than assuming it.

**Final measured reuse, full requests:**

| Scenario | Reusable prefix | Breaks | % of theoretical ceiling |
|---|---|---|---|
| short chat, 10 turns | 100% | 0 | maxed |
| normal run, 30 turns | 100% | 0 | maxed |
| general (disarmed), 30 turns | 100% | 0 | maxed |
| max mode, 20 turns | 100% | 0 | maxed |
| long run, 60 turns | 94.8% | 3 / 58 | 97.8% |
| heavy run, 60 turns @ 8KB | 89.2% | 7 / 58 | 96.3% |

Against DeepSeek-V4-Flash's 80%-off cached input that is roughly a
**three-quarters cut in input cost** on a long autonomous run, for zero
behavioural change. On Groq the discount is 50% and cached tokens do not count
against rate limits at all.

Pinned in `test_persona.py` (218 → 225): the drop block must exceed one message
(a block of 1 IS a sliding window), 60 turns past the cap must produce ≤6
anchors, the cap must still cap, the opening message must survive, and
consecutive turns past the cap must share their prefix.

### README rewritten again — harder framing, more substance

- New **"Dangerous on purpose. Safe by construction."** section: a
  will/cannot table making the point that neither list is a prompt — both are
  enforced in code, below the model, where nothing it says and nothing a target
  injects can reach. That is what makes it safe to hand something this capable a
  real shell.
- New **"The loop"** section with an ASCII flow of
  observe → hypothesise → arm → fire → verify → record, and the point that the
  proof marker is armed *before* firing.
- New **"Why it costs almost nothing to run"** section with the three
  cache-busters as a before/after table and the measured reuse chart.
- New **"Everything in the box"** capability matrix showing which tool groups
  load always and which only exist when Unleash is armed, plus a collapsible
  reliability table (four named failure modes and what handles each).
- ASCII difficulty-curve and progression charts beside the benchmark.
- Hero rewritten with a four-figure stat table; stronger closing call to action.
- 299 → 464 lines. Every claim still verified against the running code by
  `test_readme.py`, which caught a stray Unicode variation selector in one of
  the new anchor links.

### Housekeeping
- Version 9.2.0.
- 26/26 suites, 1,456 assertions, zero red.
- GUARDRAIL byte-identical. safety/ledger/voice/scope sha256-identical.
- compileall + install.sh bash -n clean.

## v9.1.0

**Theme: the turn loop cannot die, and the model cannot forget what it already did.**

### The stall / "it just hangs" family — root cause and fix

The assistant turn loop only advances when something feeds it a result — a
stream callback or a tool result.  Every feeder ran on a daemon thread, and
several of them had no exception handling at all, including `run_bg` (the
shell runner — the hottest path in the app).  They indexed `r['rc']`,
`r['stdout']`, `r['stderr']` directly instead of `.get`.  One OSError
spawning a process, one KeyError on an unexpected result shape, one
UnicodeDecodeError on binary output killed the worker thread silently, no
tool result was ever fed, and the turn sat in "working…" forever with no
way out but restarting the app.

**Fix:** new `_tool_thread(body, label)` helper with a **one-shot guaranteed
feed** — the body returns without feeding, raises halfway, or feeds and then
raises, exactly one result reaches the model.  Converted: `run_bg`,
`_tool_list_dir`, `_tool_find_file`, `_tool_read_file`, `_tool_write_file`,
`_tool_simple`, `_tool_audit`, `_tool_scan_net`, `_execute_tool_batch`,
skill commit.  **Zero unguarded tool threads remain.**

Additional guards:
- `_feed_tool_result` itself is guarded — a store write or kick failure no
  longer strands the turn.
- `_on_stream_done` body is guarded — any exception cleans up instead of
  killing the GTK source.
- The streaming worker thread catches exceptions before `on_error` — a
  malformed message list or encoding error no longer produces a dead turn
  with a traceback on stderr.
- **Turn watchdog** (TURN_WATCHDOG_S = 2400s, polled every 30s): a
  last-resort backstop.  Recovers the UI and says what happened.

### Foresight: a `block` verdict actually does something now

Three bugs, all fixed:

1. A `block` verdict did nothing.  The code computed a `force_confirm` flag,
   stored it on self, and nothing anywhere ever read it — the command ran
   regardless of foresight's verdict.

2. The model pass had no deadline.  `_ext_complete` claimed 30s, but
   `router.stream_chat` is synchronous, so `done.wait(timeout=30)` was dead
   code.  Real bound was the provider's idle timeout × fallback chain length
   (minutes).  A hung pass wedged the turn forever.

3. Re-entrancy was an instance flag cleared in a `finally` as soon as
   `_execute_command` returned — while the command was still running.

**Fix:** block actually refuses *and* feeds the refusal back so the model
adapts; watchdogged with `foresight_timeout_s` (default 20) and falls back
to the deterministic rule floor (local, sub-100μs); sidecar calls get their
own budget (320 tokens, one attempt, 18s deadline) instead of the full chat
budget and a four-model chain walk; re-entrancy is a parameter, not state.

### Repetition: the model no longer forgets what it already did

Root cause was structural: the model's only record of its own actions was
the transcript, and `_build_history_for_model` keeps only
HISTORY_KEEP_FULL_TOOL_RESULTS (2) at full length, then headroom compresses
what's left.  Meanwhile the continue directive re-anchors on the original
objective every turn.  Several steps in, the loudest thing in context is the
objective; the evidence of having already tried something is a 600-char stub.

And the only guard was 3 identical *consecutive* `run` commands — A-B-A-B
was invisible, as was a repeat four steps later, and it covered no other tool.

**Fix:** new `basilisk_ext/recall.py` — one line per action + outcome digest,
lives outside the transcript (never trimmed, never compressed), re-sent whole
every turn.  Cycle detection (A-B-A-B, A-B-C-A-B-C).  Deterministic repeat
guard: two executions always allowed (re-checking is verification), third
refused with the previous result handed back.  One recording hook in
`_feed_tool_result` covers every tool.  75 assertions in test_recall.py.

### Overcomplicating: triage by likelihood, not by thoroughness

Persona now carries the standing rule: name the two or three most likely
causes, rank by (likelihood × cheapness to check), test the top one first
with the single cheapest decisive test, stop the moment it is confirmed.
One hypothesis at a time.  The boring cause is usually the cause.

The effort ladder was a direct driver: it escalated to "heavy" (think before
you move, reason through the current state) the moment tool-chain depth hit
3, regardless of whether the task was actually hard.  That told the model to
deliberate on the turn where it should have been concluding.  Escalation now
requires depth 6+ AND 2 of the last 3 results being failures — evidence of
a hard problem, not just elapsed steps.

### Widget disposal crash

`dispose_widget` nulled `_blocks_container`, `_streaming_label`, etc.
`append_streaming`, `set_content`, `finish_streaming`, `append_thought` all
dereferenced those — so trimming a bubble the window was still driving (for
streaming or TTS) crashed the main-loop callback and stranded the turn.

**Fix:** `_disposed` flag checked at every entry point; the view trim no
longer disposes a widget the window still holds a reference to
(`streaming_msg_widget`, `_speaking_widget`).

### Suggestion routing

`_send_suggestion` wrote to `current_chat_id`, but the running loop reads
`streaming_chat_id`.  Switch chats mid-run and the suggestion silently goes
to the wrong transcript.  Now routes to `streaming_chat_id`.

### Workspace deadlock

`workspace_replace` did `_LOCK.acquire()` outside its try block.  An
OSError from the `open()` below it escaped with the lock held — every later
workspace edit from any thread blocked on it forever.  Converted to a `with`
block (the same rule v7.11.0 established).

### Fence recovery: commands get run, not printed (v9.1.0 addendum)

The model sometimes writes a shell command in a \`\`\`bash\`\`\` code fence
instead of calling the `run` tool — so it renders as a copyable block the
operator has to paste himself, which defeats the point of the app.

Three layers now prevent this:

1. **Persona rule** — "RUN COMMANDS, DO NOT PRINT THEM" in the standing
   preferences.  The model now has an explicit instruction that a reply with
   a code fence and no tool call is wrong.

2. **Fence recovery widened** — the existing recovery (detect a \`\`\`bash\`\`\`
   fence with no tool call, synthesise a `run` tool call from it) used to
   fire ONLY during an active mission.  It now fires on regular turns too,
   gated by `reply_intends_action()`: if the reply says "let me check…" or
   "I'll run…" alongside a fence, the model tried to act and fumbled the
   format — recover it.  If it says "you could try…", it is showing an
   example — leave it alone.  The approval-mode gate is also removed: if
   confirmations are on, the recovered command goes through the dialog
   instead of being silently dropped.

3. **In-context correction** — when the recovery fires, a system-role
   correction is injected into the transcript so the model reads it on its
   very next turn and stops doing it.  The persona is two thousand tokens
   away; this sits right next to the drift.

4. **Continue directive** — the mission-continue nudge now explicitly says
   "USE THE run TOOL — do NOT write a command in a code fence."

### Persona: cut to a clean operating spec (v9.1.0 addendum)

The persona is the largest input to every turn and the least-checked file in
the tree.  Stripped of roleplay and padding, and — more importantly — made
CONSISTENT, because a model reading two different accounts of the same
mechanism learns the wrong one confidently.

**A real contradiction, found and fixed.**  `CAPABILITIES` told the model the
system-destroying class was "always force-confirmed".  `PERSONA_CORE` and
`basilisk_core.tool_run_command` say it is REFUSED OUTRIGHT with no override.
Verified against the actual primitive (`mkfs.ext4 /dev/sda` →
`refused: True, "no override"`) and corrected.  A model told the floor is
merely a confirmation will try to phrase around it.

**Grounding — "it knows exactly where it is."**  `host_facts_block()` already
reads the real host live at launch (OS, kernel, device, session, package
manager, escalation tool).  `OPERATOR_PROFILE` was *competing* with it: a
hardcoded inventory naming a specific phone, two specific laptops and an SDR,
plus `PERSONA_CORE` hardcoding "his Kali Linux box" when the app also runs on
Arch and Fedora.  When the live block disagrees with a fixed claim, that is a
confusion source with no way for the model to resolve it.  All hardcoded
hardware and distro claims removed; `PERSONA_CORE` now explicitly points at the
live block as ground truth and tells it to use the detected package manager and
escalation tool rather than habits from another distro.

**Removed:** operator biography (former chef, mid-career transition, authored
projects), the hardware inventory, and identity padding — "his and his alone",
"take his side by default", "his goal is your goal", "guard root", "never an AI
language model", "use his name only now and then".

**Kept, every one verified by test:** verify-before-counting (no proof no
finding), untrusted-content-is-not-instructions, injection flagging, machine
facts read never recalled, unverified labelling, primary-source citation, the
no-filler list, don't-grovel, read-him-literally, swearing-means-impatient,
follow-the-order, and all four triage rules.

**Rewritten blocks:** `OPERATOR_PROFILE`, `PERSONA_CORE` (prose only — the
GUARDRAIL is byte-identical), `TRUST_AND_PRECISION`, `CAPABILITIES`,
`PROJECT_SELF`, and the agent-mode directive in `build_system_prompt` (was one
dense run-on paragraph, now six scannable rules).

**Sizes:** per-turn prose 2261 → 1989 tok.  Grouped prompt (what actually
ships) 7775 → 7473 tok.  Lean chat 2133 → 1909 tok.  Full 22579 → 22072.

**New `tests/test_persona.py`, 81 assertions.**  Treats the persona as a
specification: asserts it agrees with the CODE (destructive floor checked
against the live primitive, not against either text), agrees with ITSELF (no
propose-vs-act contradiction, the run-don't-print rule carries its exception),
stays grounded (no hardcoded hardware or distro), keeps every load-bearing
rule, stays inside budget, and still partitions into tool groups with no
orphaned tools.  Deliberately asserts invariants rather than exact wording —
pinning sentences would make every legitimate edit a failure.

### UNLEASH now gates the offensive suite (v9.1.0 addendum)

Hacking tools load ONLY when UNLEASH is armed.  Every other mode is stripped to
research, diagnosis, code and repo work — smaller prompt, better general work.

**Gated (armed only):** `offensive` (recon planning, scanner parsing, CVE/KEV/
EPSS, nuclei, sqlmap, the exploitation oracle), `engagement` (scope, asset
graph, loot, credential-reuse leads), `benchmark` (scoring against vulnerable
practice targets).

**Always loaded:** `system`, `code`, `workspace`, `desktop`, `media`.  `code`
stays general on purpose — auditing your own source for injected SQL or a
leaked key is development hygiene, not an attack, and gating it would break the
repo-repair mode for no safety gain.  `workspace` is half the product.

**The gate is real, not cosmetic.**  Four holes were closed deliberately:
  1. `load_tools_group` REFUSES a gated group, rather than merely omitting it
     from the directory.  The group names are guessable and appear throughout
     the persona; a mode that can be talked out of is not a mode.
  2. Aliases resolve BEFORE the check, so `pentest`, `attack`, `scan`, `scope`,
     `loot`, `bench` are gated too — otherwise the alias walks straight past it.
  3. `load_tools("all")` is FILTERED rather than refused — it was the obvious
     hole.
  4. Max mode (`grouped=False`, which ships every spec inline) removes the
     gated specs rather than shipping them, or it would be a way round UNLEASH.

The refusal explicitly tells the model to say the task needs UNLEASH and STOP —
not to reimplement the tool with raw shell commands, which is what an agent
does when a capability disappears without explanation.

**Role framing moves WITH the tools.**  `PERSONA_CORE` no longer hardcodes "you
are an autonomous penetration-testing agent"; that framing is now
`ENGAGEMENT_ROLE` (armed) vs `GENERAL_ROLE` (disarmed).  Shipping the pentest
framing on a turn where he asked you to fix a CSS bug costs context AND primes
the model toward an attack framing for a task with no target in it.  The
general role is explicit that it is *not* a downgrade, and that the offensive
tools are absent deliberately rather than missing.

Also fixed: the always-shipped core prose named `engagement_graph` as a status-
tool example — a tool general mode cannot load.  Now mode-neutral.

**Sizes:** grouped 7569 armed / **7121 disarmed**.  Max mode 22169 armed /
**11462 disarmed** — roughly half.

**Wiring:** `build_system_prompt(..., unleashed=)`, `load_tools_group(...,
unleashed=)`, `tool_load_tools(..., unleashed=)`, and BOTH dispatch paths in
basilisk.py (the autonomous chain and the approval-gated table — they have
drifted before).  Every parameter defaults to `unleashed=True`, so nothing that
does not pass the flag changes behaviour.

**tests/test_persona.py 81 → 153 assertions**, covering all four holes above,
alias gating, role/tool coupling, and the size drop.

### Prompt size: 7121 → 5660 disarmed (v9.1.0 addendum)

Asked why a non-hacking turn still paid ~7k tokens.  It was measurement, not
guessing: `CORE_TOOLS_TEXT` was 58% of the disarmed prompt, and one section of
it ("EXECUTING") was 2443 tokens on its own.

**The big find: the same rule was stated three times.**  "His request IS the
authorization / never propose / finish the job" appeared in the core lead-in
golden rule, again in the (2) ACTING section, and again in the per-turn
directive.  That is not just cost — three phrasings of one rule is exactly the
kind of thing that makes a model hedge about which one applies.  Stated once
now, and a test asserts it is stated EXACTLY once (not zero).

**Also cut:** campaign-management prose (plan-the-rounds, one-batch-at-a-time,
checkpoint-to-graph/loot, don't-sprawl, proactive-notifications) collapsed from
~590 tokens to one paragraph — it is engagement-shaped and referenced
`engagement_graph`, a tool general mode cannot even load.  The Rules list, the
LOOKUP tier explanation, the file-writing section, the tool-directory preamble
and the group blurbs were all tightened.  No rule was removed, only rewording.

**Sizes:** disarmed grouped 7121 → **5660**.  Armed 7569 → 6092.  Lean chat
1990 → 1885.  `CORE_TOOLS_TEXT` 4128 → 2885.

**Guarding the cut.**  Trimming prose is safe; trimming a RULE is a behaviour
regression nothing else would catch, because no other code reads this text.
`tests/test_persona.py` (153 → 189 assertions) now pins 33 distinct core
mechanics by name — batch-reads/serialize-writes, tag syntax, the sudo path,
never-claim-saved, the SSRF floor, guardrail immutability, rc-124 handling, and
the rest — plus the new budgets, so this cannot creep back or be trimmed further
by accident.

**Honest floor:** the remaining 5660 is ~2885 tool contract (the actual call
syntax and safety semantics for the tools it has), 332 immutable GUARDRAIL, and
~2400 of behaviour rules and directory.  Getting to 4k from here means deleting
real tool specs or real rules, not prose — say the word if that trade is wanted.

### README rewritten — and three false claims found in it (v9.1.0 addendum)

The README is not only marketing: `PROJECT_SELF` instructs Basilisk to
`web_read` this file when the operator asks about its own version, install
command or capabilities. Every sentence in it is therefore a belief the agent
will act on, which makes a stale README a source of confident wrong answers.

Checking prose against the CODE rather than against other prose found three:

  1. **"Nothing runs until you click Apply"** for self-written skills. Skill
     saving went autonomous; it is gated by passing its own sandboxed test, not
     by a click. An agent reading this would wait for an Apply that never comes.
  2. **"`web_read` reads only from a fixed allow-list ... off-list URLs are
     refused."** Any public host is reachable after a one-tap domain approval.
     The tier examples were also wrong: **exploit-db was listed as auto-fetching
     when `basilisk_core` classifies it community (approval-gated)** — and the
     same error was in the PERSONA, so the model believed a gated source was
     silent. Both corrected.
  3. Stale version badge (9.0.0) and test count (925 / 22 suites).

**Rewritten for edge:** sharper thesis up top with the headline number, a harder
CAUTION callout that now correctly names both hard floors (irreversible class
AND scope, both refused in the primitive), and a new **"Why you can actually
walk away"** section covering the v9.1.0 reliability work — the action ledger
that stops it redoing work, the guaranteed one-shot tool result that stops a
dead worker stranding the run, and likelihood-ordered triage. That section
argues the thing that actually separates this from a demo: not that it is
smarter, that it *finishes*.

Also documents the new Unleash tool gate, and states plainly that the offensive
suite is refused at the loader rather than merely hidden.

**New `tests/test_readme.py`, 86 assertions.** Verifies README claims against
the RUNNING CODE: version badge vs `VERSION`, suite count vs the actual file
count, badge vs prose assertion count, the destructive floor (including the
`rm -rf ~/loot` non-false-positive it cites), every `web_read` tier example, the
Unleash gate, anchor resolution, the disambiguation block, and 43 load-bearing
facts that must survive any future rewrite.

**METHOD NOTE recorded in the test file:** validate a checker against known-good
input before trusting its verdict — this bit twice. The anchor slugger reported
all six nav links broken until it was run against the previous README, which
demonstrably worked (GitHub does not strip a heading before slugging, so a
dropped emoji leaves a space that becomes a LEADING hyphen — anchors really are
`#-benchmark`). And a literal-string claim check reported the Unleash paragraph
missing because the README writes `*only*` with markdown emphasis. Both times
the checker was wrong and the artifact was right.

### Groq audit: 4 of 6 chain models retired, including the default (v9.1.0 addendum)

Asked to check whether Groq had better free models. It does — but the more
urgent finding was that the existing config was **already broken in
production**, and would have broken completely within two weeks.

Re-verified against `console.groq.com/docs/models` and `/docs/deprecations` on
2026-08-03. The chain was written against the May 2026 catalogue:

| Model | Status |
|---|---|
| `llama-3.3-70b-versatile` | **was `GROQ_DEFAULT_MODEL`** — shuts down 2026-08-16 |
| `openai/gpt-oss-120b` | live |
| `meta-llama/llama-4-scout-17b-16e-instruct` | **dead since 2026-07-17** |
| `qwen/qwen3-32b` | **dead since 2026-07-17** |
| `openai/gpt-oss-20b` | live |
| `llama-3.1-8b-instant` | shuts down 2026-08-16 |

Two ids were returning errors already; two more, including the default, had
13 days left. Same failure shape as the SiliconFlow chain in v7.9.3 — an id
list is a perishable good — and the miss was that the retirement guard written
then was **provider-specific**, so nothing was ever watching Groq.

**Also dead and unnoticed:** BOTH entries in `VISION_MODELS["groq"]`
(llama-4-maverick retired 2026-03-09, llama-4-scout 2026-07-17), so
`analyze_image` on Groq would simply have 404'd. And `install.sh` carries its
own hardcoded fallback defaults — a second copy of the same facts — which still
named the retired 70B.

**New config** (Groq's own migration guidance):
- `GROQ_DEFAULT_MODEL` → `openai/gpt-oss-120b` (flagship open-weight, ~500 t/s)
- Chain → `gpt-oss-120b` → `gpt-oss-20b`. Production only, and short: each entry
  is another round-trip while the operator waits, and every Groq model has its
  own rate-limit bucket so two already give a real second chance on a 429.
- **Groq's catalogue was empty** and now has three entries, so its picker shows
  context window, price and purpose instead of bare ids: gpt-oss-120b
  (flagship), qwen3.6-27b (highest measured intelligence on Groq, vision — but
  PREVIEW and 5x the output price, flagged as such), gpt-oss-20b (budget,
  ~1000 t/s, cheapest).
- Vision → `qwen/qwen3.6-27b`, the only vision-capable model Groq now serves.

**Deliberately NOT added: `groq/compound` / `groq/compound-mini`.** They are
agentic systems with built-in web search and code execution — the model fetches
attacker-chosen URLs itself, outside Basilisk's tool layer and outside the
`web_read` tier gate. Basilisk's entire injection posture is that those fetchers
were removed and what remains is tiered in code; a pickable model that quietly
re-adds one would undo that without the operator seeing a prompt. Their 8,192
max completion is also below what a tool-calling turn needs. A security call,
not a capability one — recorded in the source so it is not "fixed" later.

**Preview models stay off the fallback chain.** `qwen3.6-27b` is pickable but
not walked: a fallback path exists for when things are already going wrong, and
"may be discontinued at short notice" is the one property it must not have.

**tests/test_models.py 62 → 86 assertions.** A Groq retirement blocklist with
published shutdown dates, plus the fix for the actual gap: the dead-id sweep now
covers **every id list** — chains, catalogues, vision lists, and the installer's
hardcoded fallbacks — rather than chains alone. Also asserts the default heads
the chain, no preview model is on it, and the compound systems stay unselectable.
The catalogue-less code path kept its coverage via a synthetic ProviderSpec
rather than losing it when Groq stopped being the example.

### Unblocking replaces timing out (v9.1.0 addendum)

The operator's diagnosis was right and it applied to work I had done earlier in
this same session: I had been adding timeouts, and a timeout is a symptom fix.

**The actual bug.** `tool_run_command` ran `subprocess.run(timeout=...)` and
handled the timeout like this:

    except subprocess.TimeoutExpired:
        return {"ok": False, "rc": 124, "timed_out": True, "error": ...}

CPython populates `TimeoutExpired.stdout` with every byte the process wrote.
That handler never read it. **Verified with a reproduction**: a command that
printed 200 lines and then hung had all 200 lines sitting on the exception, and
all 200 were discarded. A scan that enumerated two hundred hosts and stalled on
the last one reported nothing at all, so the agent re-ran the entire scan. "It
times out and it's back on 0" was a thrown-away-data bug wearing a timeout
costume, not a tuning problem.

**The second bug** is that a wall clock cannot tell SLOW from STUCK. `nmap -p-
/24` is twenty-five minutes of real work that is silent in stretches; a curl
against a dead host is twenty-five minutes of nothing. They got the same number.

**New `basilisk_ext/unblock.py` — supervision by progress.**
- A process writing output is working. A process burning CPU is working even in
  total silence (compile, hash crack, crypto) — measured from `/proc/<pid>/stat`
  summed across the whole process group, because `make` goes idle while its
  children work. **Any sign of life resets the stall clock**, so there is NO
  wall-clock limit; a job may run for a week if it keeps progressing.
- Only silence AND flat CPU is a stall candidate, and even then usually isn't —
  DNS retry, TCP backoff and rate limiters look identical for tens of seconds.

**When something really has stalled, a ladder that tries to UNSTICK it:**
1. **Notice** — record it, keep waiting. Most resolve themselves.
2. **Unblock** — diagnose. The commonest real stall is a process blocked
   reading stdin: an interactive prompt nobody answered (`Continue? [y/N]`, a
   host-key prompt, a pager). That is not a timeout, it is an unanswered
   question, and closing stdin lets the job *finish*. **A timeout can only ever
   kill it.** Proven in the suite: a command blocked on a prompt is unblocked
   and completes with rc=0.
3. **Harvest** — still stuck? Take everything captured, return it marked
   `partial` with a diagnosis naming what stalled and what to do differently.
   Stopping the process is bookkeeping at that point, not the answer.

The diagnosis is written for the MODEL: "200 lines were produced before it
stalled — that work is done, use it, do NOT re-run from the start; it never used
CPU so it was waiting on something external; narrow the scope or resume from
where the output ends." "Timed out" told it nothing except to retry identically,
which is how a twenty-minute scan gets run twice.

**My own bug, caught by my own test.** The first pump used
`stream.read(65536)`, but `BufferedReader.read(n)` blocks until it has all n
bytes or hits EOF — so captured bytes stayed flat for the entire run and the
progress detector never fired, killing a job that was emitting a line a second.
`read1()` returns what is available now. The test that caught it asserts a job
outlives a harvest threshold shorter than its runtime.

`salvage_timeout()` also rescues output on any remaining `subprocess.run` path,
so nothing is binned anywhere.

**Wired:** `tool_run_command` routes through the supervisor with
`max_wall_s=None` — the `timeout` argument now only scales stall *patience* for
commands the runtime estimator already expects to be long. `run_bg` surfaces a
stall as a partial result with its diagnosis rather than an error. Registered in
install.sh EXT_FILES.

**tests/test_unblock.py, 66 assertions:** output never disappears; slow-but-
producing survives a threshold shorter than its runtime; silent CPU-bound work
survives (the case a wall clock always kills); a prompt is unblocked and
completes; a real stall yields partial output plus diagnosis; `/proc` helpers
degrade to "unknown" rather than raising; and `max_wall_s` defaults to None,
because a default wall clock would reintroduce the exact bug being fixed.

### Prompt caching + nudge-don't-kill (v9.1.0 addendum)

**Prompt caching — the prefix was being destroyed on every turn.**
Groq caches automatically on both chain models: 50% off cached input, lower
latency, and cached tokens do NOT count against rate limits. It is prefix
matching — the longest byte-identical run at the START is reused, and the first
differing byte ends the cache.

`build_system_prompt` put `_now_block()` — a MINUTE-resolution clock — at
position five, ahead of the ~4,000-token tool contract. Every minute the prefix
changed and the whole prompt was recomputed. For an agent firing a tool call
every few seconds that is a miss on virtually every turn: the least cacheable
possible ordering, arrived at by accident. The per-turn addendum (action ledger,
mission directive) was also being folded into the system message, changing it
again on every single turn.

Both now ride at the TAIL as their own trailing message, via the new
`volatile_block()` / `assemble_messages(volatile=)`. Measured: two turns a
minute apart now share **24,371 of 24,374 characters**. Appending as a separate
message rather than merging into the last one is deliberate — merging rewrites a
message already inside the cached prefix and ends the cache one message early,
the same mistake further down.

None of this is visible at runtime. The app worked perfectly and cost double.
`tests/test_persona.py` (201 → 218) pins prefix stability across every mode and
includes a **reproduction of the old shape** so the fix is pinned, not merely
described: a clock in the system prompt shares under 100 characters.

Also fixed: the persona hot-reload path rebound three symbols but not the new
`volatile_block`, so a persona self-edit would have kept calling the stale one.

**The turn watchdog now NUDGES instead of killing.** The version added earlier
this session ended the turn on a stall — the same mistake as a timeout, throwing
away the conversation, the action ledger and everything the run had achieved
because one step failed to report back. It now escalates: cancel only the
hanging stream, leave the chat, store and ledger untouched, feed back a note
saying explicitly *nothing was lost, the ALREADY DONE list is current, do not
start over and do not repeat the step that hung*, and re-kick. Two nudges before
it will consider handing the UI back. Any real progress resets the ladder, so a
long run that hits one slow patch still gets its full allowance.

Carrying the full context through the nudge is what stops the nudge becoming a
loop: the model comes back knowing exactly what it already did.

### Caching, part two: SiliconFlow + the history prefix (v9.1.0 addendum)

**SiliconFlow caches too, and harder than Groq.** DeepSeek-V4-Flash — the
pinned default — is priced $0.028 cached / $0.14 input / $0.28 output per 1M on
SiliconFlow. Cached input is **80% off**, against Groq's 50%. Both are automatic
with no code change. DeepSeek's rule is stricter though: *identical prefix from
the 0th token; partial matches in the middle never hit.*

**The second cache-buster: the history itself.** Fixing the system prompt was
only half of it. `_build_history_for_model` kept the last N tool results at full
length with a SLIDING window — so the result sent in full last turn was sent
trimmed this turn, rewriting a message in the MIDDLE of the request. Exactly the
case DeepSeek says never hits. Measured before: **~40% of the request reusable
and a cache break on every single turn**; the part being thrown away was the
largest and most expensive tail of the history.

**Two wrong turns on the way, both caught by measurement rather than reasoning:**
1. First fix made trimming one-way ("once trimmed, always trimmed"). Measured:
   **no change at all.** The trimming IS the mutation, so making it sticky fixes
   nothing. The direction that helps is the opposite — keep what was already
   sent in full.
2. Second version advanced the watermark by one place per turn once over budget,
   and measured the RAW store size — which only grows, so the condition latched
   true forever and it became a sliding window again.

The working design: measure the size of what would actually be SENT, and when it
exceeds `HISTORY_STABLE_BUDGET_CHARS` advance the watermark ALL THE WAY in one
jump, then hold. Amortised — one occasional cache miss instead of one per turn.
Measured after: **100% reusable, zero breaks over 20 turns** with normal-sized
results; with pathological 25KB results, 6 breaks in 18 turns instead of 18, and
the rendered history stays bounded.

**Cached pricing surfaced in the picker** via a new `ModelInfo.cached_in_usd`,
so the real economics are visible where models are chosen.

**A dataclass trap, caught by its own test.** Catalogue entries are built with
POSITIONAL arguments. The first attempt declared `cached_in_usd` right after
`out_usd` — which silently re-mapped every entry so each model's `note` string
became its cached price. The field is now declared LAST with that reason written
next to it, and `test_models.py` asserts every note is still a string and every
price still a number.

**tests:** test_models.py 86 → 108 (cached pricing, the positional-arg
regression, append-only history under both normal and pathological sizes, and
that rendered history stays bounded). test_persona.py 201 → 218 (prefix
stability across every mode, plus a reproduction of the old clock-in-prompt
shape). 26/26 suites, 1,444 assertions.

### Housekeeping

- `recall.py` registered in install.sh EXT_FILES.
- New tests/test_persona.py (201 assertions) and tests/test_readme.py (86).
- Version 9.1.0.
- 26/26 suites, 1444 assertions, zero red.
- GUARDRAIL byte-identical (sha 0ccebd17786bfaaf).
- safety/ledger/voice/scope sha256-identical to v9.0.0.
- compileall + install.sh bash -n clean.

# Changelog

## v9.0.0 — the loop is enforced, the scanners see the repo, the README is honest

Major bump. v7.10/7.11 added a second product surface (repo repair); this is
the release where its discipline stops being advice and the front page stops
claiming to be v7.6.0.

GUARDRAIL byte-for-byte identical (fa3fb6b1480006cd). safety / ledger / voice
sha256-identical to v7.11.0.

### THE EXPORT GATE — soft rule becomes hard rule
The persona has always asked for one change at a time and for verifying
before export. Nothing enforced either, so a model could batch six edits,
verify once, and hand back a zip — losing exactly the attribution the loop
exists to provide. You learn something broke; you don't learn which change
broke it.

`workspace_export` now REFUSES when:
  · edits have been made that were never verified, or
  · the last verify reported a REGRESSION.

Export is the one moment the operator's real repo is at risk, and "the model
said it was fine" is not evidence. `force=True` exists so he is never locked
out, but it has to be asked for, the result is flagged `forced`, and it
carries a warning naming the check that was skipped.

Batched edits are still allowed — sometimes a change genuinely spans four
files — but `workspace_verify` now reports how many edits a run covered and
warns when that number is large and the verdict isn't green.

A clean tree exports freely: with nothing changed there is nothing to verify,
and gating that would be theatre.

### SCANNERS NOW SEE THE OPEN REPO
`zday_scan` and `code_scan_plan` predate the workspace and default to `"."`,
which is Basilisk's OWN working directory. With a repo open, "scan my repo"
therefore scanned the wrong tree and returned a confidently empty result —
the worst kind of wrong, because empty reads as clean.

Both now resolve paths against the open workspace: a bare path means the repo
root, a relative path resolves inside it, and a path that would walk out of
the workspace is clamped back to the root rather than followed. With no
workspace open, behaviour is exactly as before.

### README REWRITTEN
Kept every fact, number, benchmark, install path and security claim. Fixed
what was wrong with it:

  · The version badge said **7.6.0**. Six releases stale on the front page.
  · The repo-repair mode — half the product since v7.10.0 — was not mentioned
    anywhere at all.
  · "Results first" restated the whole comparison table that "Benchmark" then
    repeated verbatim two screens later. The board now appears once, with the
    difficulty curve and reproduce-it steps folded into a collapsible.
  · Prose tightened throughout. Same claims, fewer words, less breathlessness.
  · New "What it does" opens on the actual thesis — do the thing, then prove
    it worked — which is what unifies the pentest loop and the repair loop.
  · New "Fixing your code" section with the tool flow, why the baseline
    matters, why names beat counts, and the sandbox boundary in a collapsible.
  · Security model gained the scope gate, which shipped in v7.9.0 and was
    never written up.
  · Test-suite claim is now a checked number (925 assertions, 22 suites)
    rather than "all of it is pinned in the test suite".

Verified after rewriting: all 21 load-bearing facts still present, all 6 nav
anchors resolve, both local images exist.

A note on that anchor check, because it nearly produced a wrong "fix": the
first version of the checker `.strip()`ped the heading before slugging, so it
reported all six links broken. GitHub does NOT strip — an emoji is removed
but the space it leaves becomes a leading hyphen, which is why the anchors
are `#-benchmark` and not `#benchmark`. The links were right and the checker
was wrong. Running it against the OLD README, which demonstrably worked,
settled it in one command.

### VERIFICATION
  · 22/22 suites green, 925 assertions, zero red
  · test_workspace.py 118 -> 134 assertions (export gate: refuses unverified,
    refuses regression, allows clean, force works and is flagged, batching is
    counted and warned, accounting resets across repos)
  · GUARDRAIL unchanged; compileall clean; install.sh bash -n clean
  · Grouped prompt unchanged at 7153 tokens

### A NOTE ON THE VERSION NUMBER
This skips 8.x entirely, at the operator's instruction. Worth recording that
in v7.8.0 I argued DOWN from a requested 8.0.0 because the change set did not
justify it. This one does — a whole second product surface plus the
enforcement that makes it trustworthy — but the jump past 8 is his call, not
a claim the code makes about itself.

## v7.11.0 — the fix LOOP: it verifies its own work now

v7.10.0 gave Basilisk a repo. This gives it the thing that actually
separates fixing code from editing it: a baseline, a verdict, and the
discipline to not export a regression.

GUARDRAIL byte-for-byte identical (fa3fb6b1480006cd). safety / scope /
ledger / voice sha256-identical to v7.10.0.

### FOUR NEW TOOLS
    workspace_test_command — how does THIS repo run its tests, and what was
                             that inferred from (so a wrong guess is
                             correctable rather than silently wrong)
    workspace_baseline     — run the tests BEFORE editing, record what
                             already fails
    workspace_verify       — re-run and classify vs baseline: fixed / BROKE
                             / still failing
    workspace_health       — static sweep for real bugs

### THE BASELINE IS THE WHOLE IDEA
Without it, every pre-existing failure looks like damage the agent just
caused. Worse in practice: a test that was ALREADY red gets quietly
"fixed" and folded into the change set, so the operator reviews a diff
containing work he never asked for and cannot separate from the work he
did. `workspace_baseline` must run before the first edit, and it warns
loudly if taken on an already-modified tree, because a baseline taken after
edits is not a baseline.

### WHY NAMES AND NOT COUNTS
`workspace_verify` tracks the SET OF FAILING TEST NAMES, not just totals.
Counts cannot distinguish "fixed one, broke another" from "nothing
changed" — both read as 2 failed. That distinction is the entire value of
the loop, and it is asserted directly in the tests: a run with an unchanged
failure count but a different failure SET is correctly reported as a
regression.

Four verdicts, and `broke` is read first: green / regression / progress /
no-change. A regression verdict says DO NOT EXPORT in as many words. A
no-change verdict says stop editing on the same hypothesis, because a
second guess from the same reasoning is the same guess.

### THE DANGEROUS DEFAULT, HANDLED
An unknown test runner produces a log we have no pattern for. Treating
"could not parse" as "passed" would be the worst thing this code could do,
so the exit code is ground truth when parsing fails, and the verdict says
plainly that it rests on rc alone.

### EXECUTION STAYS IN ONE PLACE
`workspace.py` still executes nothing. The core wrapper runs tests through
`tool_run_command`, which means the destructive-command floor and the scope
gate apply unchanged. This matters concretely: a repo's Makefile is
untrusted input, and `make test` can contain anything. A second execution
path would be a hole in the exact boundary v7.9.0 exists to close.

### RACE FIXED — revert() could restore the wrong "original"
`_stash_original()` was check-then-act: "if the original copy exists,
return", then copy. Tool calls run on worker threads and `shutil.copy2`
releases the GIL during I/O, so two threads editing the same file could
BOTH pass the check, and the second would stash the ALREADY-EDITED content
as the original. `revert()` would then restore a modified file and the
operator's true baseline would be gone, silently.

That is the worst bug this module could have, because the undo button is
precisely what he reaches for when something has already gone wrong.
`_mark()` had the same check-then-act shape, producing duplicate entries in
the change list.

Identical shape to the engage.py loot race fixed in v7.9.1 — which also did
not look reproducible until it was measured, at 1 of 60 records surviving.
This one did not reproduce in six trials either. Fixed anyway, on the shape
rather than on the odds: an RLock across the whole stash → write → mark
sequence, reentrant because revert() marks while already holding it. Now
asserted at 16-way contention, 6/6 trials.

Temp files also moved from a fixed `.bz-tmp` suffix to a thread-id-suffixed
one, because two concurrent writes to the same path were racing on the temp
file itself.

### AND A BUG IN THAT FIX, CAUGHT BEFORE IT SHIPPED
The first version of the revert() lock used a bare acquire/release pair. An
exception between them leaves the lock held forever and every later edit
deadlocks — strictly worse than the race being fixed. Rewritten as a
`with` block.

### workspace_health
Static sweep of the open repo: mutable default arguments, bare excepts,
subprocess without a timeout, `is` on a literal (identity where value was
meant — works by accident via interning), and syntax errors. Deliberately
NARROW. A checker that reports fifty style opinions trains the operator to
ignore it, and then it reports a real bug on line 51 and he ignores that
too.

### THE METHOD, IN THE PERSONA
The tool list was never the hard part. The persona now carries the loop as
a method — baseline, search before reading, understand before editing, one
change at a time, verify after every change, read `broke` first — plus
honesty rules that matter more than the tools:

  · Never claim a fix works because it looks right. It works when the tests
    say so. If you could not run them, say you could not run them.
  · Broke something and cannot fix it? Say so and revert. A reverted
    attempt is a fine outcome; a silent regression is not.
  · Don't touch his tests to make them pass. If a test looks wrong, say so
    and let him decide — editing the test to match broken code is the
    single worst thing an agent can do in a repo.

### VERIFICATION
  · 22/22 suites green, ~909 assertions, zero red
  · test_workspace.py 87 -> 118 assertions
  · Fuzz: 6,000 random inputs x 7 entry points, 0 crashes
  · 200k-line test log parses in 122 ms; 5 MB blob in 143 ms; the search
    regex does not backtrack pathologically on `(a+)+$`
  · AST audit of the new code clean; compileall clean; install.sh bash -n
  · Grouped prompt 7133 -> 7153 tokens

## v7.10.0 — repo workspace: hand it a zip, get a fixed zip back

New capability, so a minor bump. `basilisk_ext/workspace.py` (~830 LOC,
pure stdlib, imports nothing from the core), 13 new tools under a new
`workspace` tool group, and `tests/test_workspace.py` (87 assertions).

The persona GUARDRAIL block is byte-for-byte identical. `basilisk_safety.py`,
`basilisk_ledger.py` and `basilisk_voice.py` are sha256-identical to v7.9.4.

### WHAT IT DOES
    workspace_import   — unpack a repo .zip into a private tree
    workspace_overview — languages, LOC, entry points, manifests, tests
    workspace_search   — repo-wide grep (regex, glob, context)
    workspace_tree     — file listing, build/vendor noise filtered
    workspace_read     — read a file, or a line range
    workspace_replace  — exact-substring edit, uniqueness enforced
    workspace_write    — whole-file write / new file
    workspace_delete   — remove a file (recoverable)
    workspace_diff     — unified diff of everything changed
    workspace_revert   — undo one file or all of them
    workspace_export   — zip it back up
    workspace_status / workspace_close

Tests still run through the existing gated `run_command`, so the
destructive-command floor and the scope gate apply to them unchanged. This
module executes nothing itself.

### THE CONTAINMENT BOUNDARY IS THE FEATURE
This is the first thing in Basilisk that takes a FILE FROM OUTSIDE and
writes its contents to disk under a name the file itself chooses. Every
other input is a command string it parses. That difference is the whole
design.

`_confine()` is the single choke point: every read, write, move and delete
goes through it, and it fails closed. Three properties, each a real CVE
class:

  · realpath BEFORE comparing, so a symlink inside the tree pointing out of
    it is caught. Checking the literal string first and resolving later is
    the bug in most naive implementations.
  · commonpath, NOT startswith. "/home/u/repo-old" starts with
    "/home/u/repo" and is a different directory.
  · absolute paths refused out loud rather than silently re-rooted.

Extraction refuses, before writing anything:
  · ZIP SLIP — member names that traverse out of the destination
    (CVE-2007-4559, still live in Python's own tarfile in 2022)
  · SYMLINK ENTRIES — a zip can carry `docs -> /` and then `docs/etc/passwd`;
    rejecting `..` does not catch this
  · ZIP BOMBS — per-entry ratio ceiling plus a running total, because a
    42 KB archive can decompress to petabytes

Refusals are REPORTED, not silently dropped. If the operator's zip contains
something this declines, he needs to know which file and why, or he will
think the import merely lost data.

The other reason the boundary is structural rather than prompt-level:
Basilisk is autonomous under UNLEASH. A model that decides the fix belongs
in ~/.bashrc is not misbehaving in any way it can detect. It is one wrong
path away from editing the operator's home directory instead of his repo.

### BUG FOUND BY THIS FILE'S OWN TESTS
`~/.bashrc` was not an escape — it was worse. `os.path.join` treated `~` as
an ordinary directory name, so the write landed at `<root>/~/.bashrc`.
Contained, so the boundary held, but the operator asked to touch his shell
config and would have got a junk directory named `~` inside his repo
instead of an error. Now expanded before the check, which makes it absolute
and therefore refused out loud. This is precisely the "silently re-rooting
turns an obvious error into a confusing one" case named in the docstring
two functions above the bug.

### CREDENTIALS
Repo zips routinely carry a stray `.env`. Files that look like credential
stores are flagged on import, refused for reading (they are not going into
a cloud model's context), excluded from search results, and excluded from
the export unless `include_secrets=True` is passed deliberately.

### DESIGN CALLS WORTH STATING
  · `workspace_replace` REFUSES a non-unique match rather than picking one.
    Guessing which of four similar blocks was meant is how an agent edits
    the wrong call site.
  · Python that would not parse is refused before anything is written,
    mirroring the core's self-edit guard. A syntax error introduced at step
    3 of a 30-step refactor gets blamed on step 27.
  · Originals are stashed ONCE PER FILE, on first change — not per edit.
    Per-edit would make revert walk back exactly one step and stop.
  · A single wrapping top directory is hoisted, so paths match what the
    operator sees on GitHub: "basilisk_core.py", not
    "PriestsBasilisk-main/basilisk_core.py".
  · No git. The operator's history is his; this hands back a zip and he
    diffs it with tools he already trusts.

### ONE ARG-MAPPER, NOT TWO
basilisk.py has two dispatch paths — autonomous and approval-gated — and
they have drifted before: a tool wired into one and not the other works
perfectly until the operator flips approval mode, then vanishes with no
error. All 13 tools route through one shared `_workspace_call()` mapper,
which cannot drift from itself, and the test suite asserts that persona
specs, core functions, the dispatch table and the mapper are the same set
of 13 names.

### VERIFICATION
  · 22/22 suites green, ~878 assertions, zero red
  · test_workspace.py: 87 assertions, ~70% of them the containment boundary
  · GUARDRAIL byte-for-byte identical; safety/ledger/voice sha256-identical
  · AST audit of the new module clean; compileall clean; install.sh bash -n
  · workspace.py added to EXT_FILES (remote-fetch installs read only that
    list, and a missing ext module is a silent capability gap)

### KNOWN
The grouped prompt moves 7024 -> 7133 tokens: one more line in the group
directory. Specs load on demand as usual, so a turn that never touches a
repo pays only that line.

## v7.9.4 — the only speed lever that matters, plus a fail-open verdict

Persona, safety floor and ledger are byte-for-byte identical to v7.9.3.
`basilisk_scope.py` changed; that change is the fail-closed fix below.

### THE HONEST ANSWER ON SPEED
Local Python is not the bottleneck and measuring it again did not change
that. Current numbers on this tree:

  · destructive-command gate    ~52 us/command
  · scope gate                  ~62 us/command
  · turn classification         ~28 us/turn
  · warm import of the core     ~70-90 ms, once, at launch

Nothing there is worth optimising. A turn costs SECONDS, and essentially
all of it is the API round-trip. Within that, the part under our control is
OUTPUT TOKENS: they are generated one at a time, so token count IS latency,
and output also runs 2-3x input price. That is the only lever with real
leverage, so that is what this release pulls.

### NEW — skip thinking on light turns (opt-in, default OFF)
Setting `fast_light_turns`, and a matching switch in Settings under
Adaptive effort. On a LIGHT turn — a receipt, a short conversational reply
— models with a thinking toggle are asked to answer without
chain-of-thought. Eleven of the nineteen catalogue models carry the toggle;
the rest are left alone because their reasoning is architectural, not a
mode, and inventing a field for them would just earn a 400.

Heavy and standard turns are NEVER touched. That is where reasoning earns
its keep, and it is the whole reason the effort ladder exists.

Default OFF because this adds a non-standard field to the request body.
Three properties make it safe to turn on, all asserted end-to-end against a
faked HTTP layer rather than argued for in a comment:

  1. OFF means the body is byte-identical to v7.9.3's. Opting out is free.
  2. A 400 caused by our own field strips it and retries THE SAME MODEL.
     This check sits deliberately in front of the stale-model-id recovery —
     otherwise a rejected toggle would send the router hunting down the
     fallback chain for a model that was never broken, burning a live
     catalogue fetch on the way.
  3. After one rejection the field is not sent to that model again for the
     rest of the session. Three turns against a hostile provider cost four
     requests, not six.

The rejection memo is built in `__init__`, not lazily in `stream_chat`:
tool calls run on worker threads, and two racing the lazy init would each
build a fresh set and lose a rejection. `set.add` is atomic under the GIL,
so no lock is needed once it exists.

### FIXED — an unterminated substitution produced a fail-OPEN verdict
`_substitution_payloads()` scans for `$(...)` and backtick spans and lifts
them out to be parsed as commands in their own right. When the delimiter
was never closed, both branches CONSUMED the rest of the string and then
dropped it. A single leading backtick therefore swallowed the entire
command, and `` `nmap evil.com `` came back as "passive/local command —
scope boundary not engaged".

Found by fuzzing: 34,400 inputs, 160 fail-open leaks, every one of them the
unterminated-backtick shape.

It is NOT an exploitable bypass — bash and sh both reject an unterminated
backquote as a syntax error, checked against the real shells rather than
assumed, the same way `$IFS8` was checked and dismissed in v7.9.1. But a
fail-OPEN verdict arrived at by accident is exactly what this gate exists
not to do, and "not exploitable today" is a bad thing for an authorisation
boundary to rest on. An unterminated substitution now marks the command
unparseable and the gate refuses. Re-fuzzed: 0 leaks, 0 crashes.

Note the near miss in the same function: unbalanced QUOTES and a trailing
backslash were already failing closed correctly. Only the substitution
scanner had the swallow.

### FIXED — host facts died on a C-locale box
Six reads of `/etc/os-release` and `/proc/*` used `open()` with no
encoding, so they inherited the locale. On a box running `LANG=C`, a
`PRETTY_NAME` carrying a non-ASCII character raises UnicodeDecodeError and
takes the whole host-facts block with it. Now pinned to utf-8 with
`errors="replace"`.

### DEBUG SWEEP — what came back clean
Full-tree AST audit: zero mutable default arguments, zero bare excepts,
zero `subprocess` calls without a timeout, zero `sqlite3.connect` without
`check_same_thread`, zero regexes compiled inside a loop. The v7.9.1
invariant that `_WRAPPERS` and `_NETWORK_TOOLS` never intersect still
holds. Fuzz: 34,400 structured and random inputs through both gates, zero
crashes.

Cost of the scope fix, measured: 59 us -> 62 us per command. Noise.

### NEW TEST SUITE — tests/test_effort.py, 23 assertions
Drives the real router against a faked HTTP layer and asserts the request
BODY, not the intent: default-off byte-identity, light-only application,
standard and heavy untouched, no field invented for a model without a
toggle, the light token cap still applied, strip-and-retry on the same
model, the one-time memo, and — the case that proves the new check did not
swallow the path it sits in front of — that a genuinely stale model id
still walks the chain. Also pins the v7.9.3 catalogue-escalation fix.

tests/test_scope.py +11 assertions for the unterminated forms, including
six terminated and ordinary commands to prove the fix does not over-block.

### VERIFICATION
  · 21/21 suites green, ~791 assertions, zero red
  · basilisk_persona.py, basilisk_safety.py, basilisk_ledger.py,
    basilisk_voice.py sha256-identical to v7.9.3 — GUARDRAIL untouched
  · compileall clean; no new top-level module, so install.sh is unchanged

### STILL NOT DONE
Deferring `urllib.request` and `concurrent.futures` would take ~35 ms off
launch. Not worth the import-order risk for 35 ms that happens once.

## v7.9.3 — the model catalogue was half dead

Provider routing only. No change to the persona, the GUARDRAIL block, the
destructive-command floor, or basilisk_scope — those four files are
byte-for-byte identical to v7.9.2.

### HEADLINE — three of six SiliconFlow models were discontinued
`SILICONFLOW_CHAIN` listed six models. Three of them 404 now:

  · `Qwen/Qwen3-235B-A22B-Instruct-2507` — discontinued 2025-12-31
  · `zai-org/GLM-4.6`                    — superseded by GLM-5.x
  · `moonshotai/Kimi-K2.5`               — redirects to Kimi-K2.6

They sat in the picker as pickable options, and in the outage fallback walk
as three wasted round-trips before the retry reached anything live. Nothing
in 862 tests noticed, because nothing asserted anything about the chain
beyond "non-empty, starts with the pinned default".

### CATALOGUE / CHAIN SPLIT
The flat list was doing three incompatible jobs at once: the Settings picker,
the quick-switch popover, AND the runtime rate-limit fallback walk. You could
not add a model to pick from without also lengthening the retry storm that
fires when the provider is down.

  · `SILICONFLOW_CATALOGUE` — 19 models, each a `ModelInfo` carrying context
    window, published $/Mtok in and out, vision support, tier, and a line on
    what it is actually for. This is what you PICK from.
  · `SILICONFLOW_CHAIN` — 4 live models. This is what the backend WALKS on a
    429 or an outage, and it stays short on purpose: every entry is another
    full round-trip bounded by STREAM_IDLE_TIMEOUT_S.
  · `chain[0]` is still `deepseek-ai/DeepSeek-V4-Flash`. The pinned default
    did not move and is still locked by tests.
  · `ProviderSpec` gains `catalogue`, `pick_ids`, `info()`, `knows()`. Groq's
    catalogue is empty, so `pick_ids` falls through to its chain and Groq
    behaves exactly as it did before — verified by test.

New in the picker, worth knowing about: `nex-agi/Nex-N2-Pro` (397B agentic
MoE, listed at $0.00 in and out), `tencent/Hy3` ($0.13/$0.53, 262K, three
reasoning modes), `zai-org/GLM-5.2` (highest measured intelligence on the
platform, 1M ctx), `meituan-longcat/LongCat-2.0` (leads SWE-bench Pro),
`moonshotai/Kimi-K3` (2.8T params, 1M ctx, vision).

Four ids are marked `(inferred id)` in source: they follow the vendor's exact
published naming convention but were not seen verbatim in a SiliconFlow price
or release table. If one 404s, the refresh button picks up the live id.

### FIXED — the picker sorted the pinned default LAST
`_models_priced_high_to_low()` parsed the largest `NNb` out of the model id,
on the theory that bigger equals better equals pricier. Every id without a
parameter count in its NAME scored 0.0 — which in the current lineup means
DeepSeek-V4-Flash, GLM-5.2, Kimi-K3 and Hy3, i.e. the pinned default and
three of the four best models, all sorted BELOW a 72B legacy model. An MoE's
total parameter count told you nothing about its cost anyway. Providers with
a catalogue now use the curated order; the regex survives only for
live-fetched ids with no metadata.

### FIXED — repopulating a model picker wrote the wrong model to disk
`Gtk.ComboRow.set_model()` resets `selected` to 0 and emits
`notify::selected`. `_on_provider_model` had no re-entrancy guard, so every
repopulate fired the handler with whatever happened to be first and called
`save_settings()` on it before the correct selection was restored — a
spurious disk write on every Settings open, and a real window during a live
refresh where the wrong model was persisted. The vision picker already had
this guard; the provider picker did not. Both paths now go through one
guarded `_populate_model_row()`.

Related: the visible strings now carry context and price, so display text is
no longer the model id. `_model_rows` keeps a parallel id list and the
handler indexes into that. The old code read the id back out of the widget
label, so any label change would have silently written a bogus model id into
settings.

### FIXED — effort escalation was a silent no-op for catalogue models
`hard_engagement_model` was validated with `heavy in chain`. Pick a valid
heavy model from outside the short fallback chain and the escalation never
fired — indistinguishable from a working feature. Now validated with
`spec.knows()`, which accepts catalogue OR chain.

### FIXED — the live /models list was unusable
SiliconFlow's `/models` returns the whole platform: embeddings, rerankers,
TTS voices, image and video generators, every one of which 400s on a chat
call. Sorted A-Z, the eight models worth picking were buried under ~200 that
are not chat models at all. Now filtered to chat models and ranked
catalogue-first, with a 120s TTL cache keyed on the API key (so a key swap
cannot serve another account's catalogue).

### REFRESHED — vision model list
The `Qwen2.5-VL` / `Qwen2-VL` ids in `VISION_MODELS` are gone from
SiliconFlow's catalogue entirely. Replaced with the Qwen3-VL family,
`zai-org/GLM-4.5V`, and `moonshotai/Kimi-K2.6` (several general-purpose
catalogue models now take image input natively, so the vision model and the
chat model can be the same one).

### NEW TEST SUITE — tests/test_models.py, 62 assertions
Locks what can be checked offline: catalogue/chain separation, the pinned
default, id hygiene, an explicit retired-id blocklist, metadata sanity,
`knows()`, the live-catalogue filter and ranking, cache invalidation on key
change, tier grouping, and the picker ordering regression (including a
reproduction of the old sort, so the bug is pinned rather than described).
It cannot check that an id is currently SERVED — that needs the network and
a key. The refresh button is the answer to drift.

Found a false positive in this file's own first draft: the retired-id check
used `startswith`, which flags every live SUCCESSOR — `GLM-4.5-Air` starts
with the retired `GLM-4.5`, `MiniMax-M2.5` starts with the retired
`MiniMax-M2`. Version numbers are not a prefix hierarchy. Now an exact-match
set plus one explicit prefix for the Qwen3-235B family, where every suffixed
variant went at once.

### VERIFICATION
  · 20/20 suites green, zero red entries (was 19/19; test_models.py is new)
  · basilisk_persona.py, basilisk_safety.py, basilisk_scope.py,
    basilisk_ledger.py, basilisk_voice.py sha256-identical to v7.9.2 —
    GUARDRAIL untouched
  · basilisk.py imports clean under the GTK stub
  · No new top-level module, so install.sh REQUIRED_FILES and EXT_FILES are
    unchanged

### NOT DONE, DELIBERATELY
`enable_thinking` / reasoning-effort control is not wired into the request
payload. It is the real remaining optimisation for an agent of this shape —
light turns do not need thinking tokens and output runs 2-3x input price —
but it changes the streaming payload on the only working provider, and it
wants to be opt-in with a 400-retry that strips the field before it ships.

## v7.9.2 — repo reorganisation (assets/, docs/) + a real .gitignore

Layout only; no behaviour change. The INSTALLED layout is deliberately
UNCHANGED — install.sh still flattens art into ~/.local/share/basilisk — so
existing installs are unaffected and upgrading is a no-op for them.

### MOVED
  · assets/app/    — the 19 files basilisk.py loads at runtime (avatar, logo,
    priest, watermark, cross, dragon, sigil, org.thepriest.basilisk.svg, and
    all 11 basilisk-btn-*.png)
  · assets/brand/  — web/README-only art (banner.png, basilisk-icon.png,
    architecture.svg, dragon.png)
  · docs/          — AUDIT.md, BASILISK_MANUAL.md
  · Repo root drops from 24 loose images to zero.

### STAYING AT ROOT ON PURPOSE
index.html, robots.txt, sitemap.xml, .nojekyll, googleac*.html (Search Console
verification), LICENSE, README.md, CHANGELOG.md, install.sh (the curl one-liner
points straight at it), llms.txt, org.thepriest.basilisk.desktop. Moving any of
these breaks Pages or verification SILENTLY — the site keeps serving, it just
serves wrong.

### RESOLUTION
basilisk.py gained one `_asset_paths()` helper; every `_find_*` now routes
through it and searches, in order: the installed flat dir, assets/app/, then
alongside the module (legacy checkouts). Nine separate hand-rolled candidate
lists collapsed into one.

### install.sh
  · `ASSET_DIR="assets/app"`; OPTIONAL_FILES is built from OPTIONAL_ART.
  · Remote fetch flattens on landing (`-o "${TMP}/$(basename "${f}")"`) so every
    later `${SRC_DIR}/<bare-name>` reference is untouched by the move.
  · Local copy tries `${SRC_DIR}/assets/app/<f>` then `${SRC_DIR}/<f>`, so
    installing from an OLD flat checkout still works.
  · Icon install learned the new path with the same fallback.

### TWO PRE-EXISTING GAPS FIXED WHILE IN HERE
basilisk-sigil.svg and basilisk-btn-expand.png were referenced by basilisk.py
(`_find_btn_png("expand")`, the sigil finder) but appeared in NO install list —
so every remote install has silently lacked them. Both now ship.

### .gitignore
Rewritten from 11 lines to cover Python/venv/test caches, editors, OS cruft,
backups, secrets (.env, *.key, *.pem, settings.json — a stray local config
carries live API keys), and Basilisk's own runtime artefacts (chats.db,
memory.db, evidence/, engagements/, loot/, *.log). Also excludes scan output
(*.nmap, nuclei-*.txt, ffuf-*.json) — a committed scan dump leaks a client's
estate. Negated safety nets re-include assets/, videos/, benchmarks/ and the
root Pages files so no future rule can quietly drop them.

Verified against a real git index: 99 files tracked, 0 __pycache__ leaked,
assets 23/23, videos 2/2, benchmarks 8/8, .nojekyll present.

### NEW TEST — tests/test_assets.py (53 assertions)
Art loading fails SILENTLY (a missing PNG just falls back to a symbolic icon),
which makes it exactly what rots after a reorganisation. Locks: every asset's
location, no loose images at root, the root files Pages/Search Console need,
runtime resolution of all 18 app assets through basilisk.py, that the installed
flat path is STILL searched, that install.sh's OPTIONAL_ART covers everything
basilisk.py wants, and that every image referenced by index.html/README.md
exists on disk (absolute og:image URLs included).

### VERIFICATION
Suite 19/19, 862 tests, zero red. install.sh `bash -n` clean; all three install
paths simulated (new layout, old flat checkout, remote flatten) → 19/19 each.
GUARDRAIL byte-for-byte (2fee8a176746bf43). 47 files compile.

## v7.9.1 — hardening the boundary shipped in v7.9.0, plus a severe data-loss race

v7.9.0 made scope structural. Reviewing that work adversarially found four ways
past it, all now closed and locked as regressions. A gate nobody has tried to
break is a gate with unknown strength.

### FOUR BYPASSES IN THE v7.9.0 SCOPE GATE
  · FILESYSTEM DEPENDENCY (worst). `_looks_like_target()` called
    `os.path.exists()`, so `touch evil.com && nmap 10.0.0.5 evil.com` dropped
    evil.com from the extracted set and the command was ALLOWED on the strength
    of the in-scope IP alone. An authorisation decision must be a pure function
    of the command string — once it reads mutable disk state, anything that can
    create a file can move the boundary, and the agent creates files. Removed.
  · BOOLEAN FLAGS EATING TARGETS. Flag arity was guessed, so `curl -s
    https://evil.com` lost its target to `-s` (which takes no value). Replaced
    guessing with an explicit `_BOOLEAN_FLAGS` set plus a strong-target backstop,
    so a misfiled flag is a false positive rather than a silent bypass.
  · WRAPPER PREFIXES. `env FOO=1 nmap 8.8.8.8` walked straight through, as did
    `sudo -u root`, `timeout 1.5` (a float broke the duration regex), nice,
    ionice, setsid, unbuffer, xargs, watch, command, exec, busybox, torsocks,
    firejail, chrt, `su -c '…'`, `script -qc`. Enumerating wrappers is
    unwinnable, so the fix is architectural: if a known tool name appears in a
    sub-command the parser could not attribute AT ALL, refuse. Every present and
    future parsing gap now fails closed. `which`/`apt`/`apt-cache`/`man` and
    friends are exempt so tooling_check still works.
  · COMMAND SUBSTITUTION. `echo $(nmap 8.8.8.8)` and `X=$(nmap 8.8.8.8)` ran
    unchecked — shlex yields the token `$(nmap`, whose basename matches nothing.
    Substitution spans are now lifted out and re-parsed as commands.
  · Also self-inflicted: `proxychains` was in BOTH the wrapper set and the tool
    set, so the backstop fired on every legitimate `proxychains nmap`. There is
    now an invariant test asserting the two sets never intersect.

### CONCURRENCY — 105 OF 120 WRITES WERE BEING LOST
Every engage.py mutator was `_load()` → mutate → `_save()` with `_LOCK` held
only INSIDE `_save`. Tool calls run on worker threads, so the second load
overwrote the first save. Measured on 120 concurrent records: 60 assets → 14
survived, 60 loot → 1 survived. Silently. No exception. The worst case is loot,
where the tool's entire job is being authoritative about captured credentials.
Fixed with a `_txn` context manager holding the RLock across the whole
read-modify-write; same test now 60/60 and 60/60, and concurrent `scope_set` is
no longer clobbered by asset writes.

### TWO MORE CONTROLS THAT FAILED OPEN
  · `tool_sqlmap_plan`'s scope check was wrapped in `except Exception: pass`, so
    any error in scope resolution silently produced an unchecked sqlmap command.
    A boundary that opens on its own failure is worse than no boundary, because
    it reads as enforced. Now fails closed.
  · `mcp.py`'s prompt-injection firewall did the same. `webshield.sanitize` is
    internally fail-safe and never raises, so that `try/except: pass` only ever
    caught the IMPORT failing — meaning if webshield is missing from an install,
    raw untrusted MCP output reached the model with no firewall and no marker.
    Reachable, since EXT_FILES can omit a module. Now degrades LOUDLY: explicit
    untrusted-content banner naming the failure, plus a zero-width/bidi stripper
    as the minimum viable defence.

### VERIFIED CLEAN (no action needed — do not re-flag)
  · Evidence ledger is correct under concurrency: 120 threads, 0 lost events,
    0 duplicate step numbers, `verify()` intact. It already held the lock across
    `_next_step` + append.
  · AST sweep of all 46 files: zero mutable default args, zero subprocess calls
    without a timeout, `check_same_thread` set at every sqlite3.connect, zero
    bare `except:`. The remaining ~155 `except: pass` sites are legitimate GUI
    fail-safes; the security-relevant ones were the two fixed above.
  · `nmap$IFS8.8.8.8` is NOT a bypass — bash reads `$IFS8` as an undefined
    variable and yields `nmap.8.8.8`, which runs nothing. Checked against real
    bash rather than patched on suspicion. The `${IFS}` form is real and was
    already blocked.

### VERIFICATION
  · Suite 18/18, 809 tests, zero red entries.
  · Bypass hunt: 28,080 combinations (20 tools x 26 prefixes x 18 wrappers) —
    0 crashes, 0 fail-open leaks. 0 false positives across 44 real local /
    tooling / benchmark / in-scope commands.
  · test_scope.py 65 → 115 assertions; test_engage.py +4 concurrency;
    test_webshield.py +5 MCP-degradation.
  · Gate cost 11–65us/command. GUARDRAIL byte-for-byte (2fee8a176746bf43).
  · basilisk.py imports clean under a GTK stub; 46 files compile.

## v7.9.0 — the authorisation boundary becomes structural

### THE GAP
Scope was advice. `basilisk_persona.py` told the model to `scope_check` before
anything active, and exactly one tool (`tool_sqlmap_plan`) actually enforced it
— behind an `except Exception: pass` that fell OPEN if the check threw. Every
other active command (nmap, nuclei, ffuf, hydra, curl, masscan, smbmap…)
reached `tool_run_command` with nothing checking who it was aimed at. The
destructive-command floor stopped `rm -rf /`; nothing stopped `nmap 8.8.8.8`.

On a leashed agent that's a docs problem. Under UNLEASH it's a prompt-level
control on an autonomous loop — one bad parse, one poisoned page, one model
slip from firing at a host nobody authorised. Authorisation is the only thing
separating a pentest from an intrusion, and it was the one control not enforced
in code.

### NEW — basilisk_scope.py (enforced at the execution primitive)
Wired into `tool_run_command` beside `is_catastrophic_command`, same no-override
posture. The model cannot route around it because it *is* the execution path.
  · Extracts every network target a command will touch — positional args, `-u`,
    per-tool target flags, inline `--url=`, comma lists, `user@host`, `host:port`,
    `[::1]`, CIDRs.
  · Sees through `sh -c`, sudo/doas/proxychains/timeout/nohup prefixes, env
    assignments, absolute paths, chained `;` `&&` `|`, and `$IFS` obfuscation —
    reuses basilisk_safety's already-fuzzed tokeniser rather than growing a
    second weaker one, so a bypass fixed in one gate is fixed in both.
  · Inline interpreter code (`python3 -c "...nmap..."`) is refused, not parsed.
  · FAILS CLOSED: no scope, unresolvable target, or `-iL targets.txt` ⇒ REFUSED.
  · Passive/local commands are never inspected — `ls`, `cat`, `pytest`, `git`
    are untouched, so this cannot break ordinary work.
  · Loopback stays allowed by default (`allow_loopback`) so benchmark runs
    against localhost:3000 keep working.

### NEW — rules of engagement that match real paperwork
  · `scope_exclude` — RoE carve-outs. Checked BEFORE scope and beat it, so
    "10.0.0.0/8 except the DC at 10.1.1.0/24" is finally expressible. There was
    previously no exclusion concept at all; scope was a bare allowlist.
  · `scope_window` — authorised testing window (ISO-8601). Outside it every
    active command is refused even against an in-scope host.
  · `scope_authorisation` — client, signatory, SoW/ticket reference. Carried
    into the evidence export so a report can state the authority it ran under.
  · `scope_check` and `scope_show` now honour exclusions and report the full
    RoE record.

### BUGS FOUND WHILE BUILDING IT (in the new gate, by its own tests)
  · `basilisk_safety._INTERPRETERS` is *language runtimes*; shells are in
    `_SHELLS`. Importing the wrong one silently disabled `sh -c` recursion —
    i.e. `sh -c 'nmap 8.8.8.8'` walked straight through. Caught by test_scope.
  · Global target-flag set with a per-tool exception table got `nuclei -t
    cves/2024/` wrong (`-t` is templates, not target). Rebuilt as unambiguous
    globals + per-tool allowlists; `-u` is username on every AD/SMB tool.
  · Blindly consuming a value-flag's next token dropped the target on
    `curl -s https://evil.com` — a silent bypass, since `-s` is boolean. Now
    peeks: if the next token is host-shaped it is never eaten.

### REPO HYGIENE
  · `tests/test_kali.py` DELETED. v7.8.0's changelog says it was removed after
    being ported to test_core.py, but it is still on main — dead since the
    v6.3.0 rename (`import kali_core` ⇒ ModuleNotFoundError), the only red entry
    in the suite, and a 60-test duplicate of test_core.py. The deletion never
    got pushed.
  · `basilisk_scope.py` added to `REQUIRED_FILES` in install.sh. Note
    REQUIRED_FILES has NO GitHub-contents-API backstop (only EXT_FILES does), so
    a forgotten top-level module is fatal in remote-fetch mode, not self-healing.

### VERIFICATION
  · Suite 18/18, 750 tests, zero red entries (was 17 green + 1 dead).
  · test_scope.py: 65 assertions — fail-closed, 16 bypass attempts, engagement
    window, exclusion precedence, and a false-positive corpus of real local and
    in-scope commands. Cross-checks its matcher against `engage._match_one` on a
    grid so the gate and `scope_check` can never drift apart.
  · 60k adversarial fuzz strings: 0 crashes, 0 fail-open leaks.
  · Cost 10–99us/command (destructive gate is ~60us) — no measurable impact.
  · GUARDRAIL byte-for-byte identical (sha256[:16] 2fee8a176746bf43).
  · basilisk.py imports clean under a GTK stub. 46 files compile.

## v7.8.0 — the dead test comes back, and an honest performance result

- **`test_kali.py` resurrected as `test_core.py` — 0 tests running to 60.**
  It had been red since the v6.3.0 namespace rename, importing a `kali_core`
  module that no longer exists, and every run reported a failure that everyone
  had learned to ignore. It was never worthless: it covers the self-edit write
  path (ast syntax gate, immutable-GUARDRAIL guard, timestamped backup, atomic
  replace), the ChatStore SQLite layer, the CVE NVD->KEV->EPSS chain, settings
  round-trip and the structural safety floor. Ported, and the suite now has no
  red entries at all (17/17).
- **A vacuous assertion inside it, found while porting.** The atomic-replace
  test asserted no `.kali-tmp` file was left behind — but the code writes
  `.basilisk-tmp`, so the glob matched nothing and the assertion could never
  fail no matter how badly the atomic write leaked. It now globs the suffix the
  code actually writes. A test that cannot fail is worse than one that is red.
- **A superseded contract locked in the test.** It asserted that a config with
  no `active_provider` stays on Groq. That was deliberately changed in v7.5.6 —
  a stale groq value persisted from the removed auto-hop was leaving boxes off
  the operator's pinned provider. The test now locks the CURRENT contract
  (defaults to siliconflow) with a comment explaining why it changed, rather
  than quietly encoding the old one.
- Stale target filenames in the safety fixtures (`tee kali.py`, `mv evil.py
  kali.py`, `wc -l kali.py`) updated to `basilisk.py`, so the self-tamper floor
  is exercised against the file it actually protects.
- **zdayfind scan loop cleaned up**: the focus/lang filters were re-evaluated
  for all 31 signatures on every line although they are constant for a whole
  file, and the taint regex went through re's cache on every hit. Both hoisted.
  Output verified byte-identical (sha over 295 findings across the full tree,
  every language variant and every focus filter).

### Performance: measured, and mostly a negative result

The honest summary is that there is no meaningful local CPU bottleneck, and
two plausible-sounding optimisations were tried and REJECTED on measurement:

- Per-turn cost is already negligible: building the system prompt is ~6us,
  turn classification ~21us, the destructive-command gate ~60us per command.
- Startup is ~140ms cold / ~95ms warm. The 147ms that `basilisk_btn_art`
  appears to cost is a cold-bytecode artifact; warm it is 1.4ms.
- `zdayfind` runs at ~0.9 MB/s (~3.4s for the whole repo). Gating each line
  through one alternation of all 31 patterns measured **1.7x SLOWER** — a
  61-group union cannot use the per-pattern literal-prefix optimisation the
  individual patterns each get. Restructuring to one `.finditer()` per
  signature over the whole text, reconstructing per-line semantics afterwards,
  measured **0.93x** — removing ~310k Python-level calls per large file bought
  nothing, because the cost is raw byte scanning, not call overhead. Both
  rejected; the reasons are recorded in the `_iter_matches` docstring so nobody
  burns the same afternoon again.

The only lever that genuinely reduces scan cost is running fewer signatures,
which the per-file language filter already does (a `.py` runs 25 of 31). For an
agent of this shape the real latency is API round-trips and token count, not
Python.

## v7.7.1 — the acknowledgement-latches-a-mission bug

A bug-fix release. The headline item is that the single red test in
`test_leanchat` — written off as "pre-existing" across several versions — was
never cosmetic. It was a live autonomy defect.

- **Acknowledging Basilisk while Unleashed started a new mission.**
  `conversational_turn()` graded plain receipts ("yeah that makes sense",
  "fair enough", "good point") as ACTION turns. That function drives the
  Unleash mission latch (`basilisk.py` ~5993 and the toggle kickoff ~9669), so
  while armed, *acknowledging what Basilisk just said* latched a fresh mission
  with the acknowledgement itself as `_mission_objective` — and it then ground
  on "yeah that makes sense" until MISSION_COMPLETE. Root cause was a coverage
  gap in `_CHAT_MARKERS`: such messages fell through to the final all-words
  test and failed it. Measured against a 76-phrase corpus of realistic
  receipts, **62 were misclassified**. Now covered.
- **Lead-filler peeling shredded multi-word social phrases before they could
  match.** `nice`, `well` and `right` are all in `_LEAD_FILLER`, so "nice one",
  "well done" and "right on" were peeled to `one` / `done` / `on` *before* the
  phrase matcher ran — meaning no social phrase opening with a filler word
  could ever match. Phrases are now matched against the unpeeled text as well.
  Safe by construction: the action-keyword test still returns first, so an
  explicit task verb continues to win over any social phrasing around it.
- **Closed vocabulary drift between `_TASK_VERBS` and `_ACTION_HINTS`.** 35
  verbs lived in the first table and had never been added to the second, so
  "dump the db", "crack the hash", "fuzz the endpoint" and "escalate to root"
  carried no action keyword at all. Deliberately omits `make` (collides with
  the "makes sense" receipt), `own` and `map` (too common as ordinary words;
  "map the network" is already caught by `network`), and `brute-force`
  (normalisation turns the hyphen into a space, so only bare `brute` can
  match).
- Act-confirmations (`of course`, `absolutely`, `definitely`, `go for it`) are
  deliberately **excluded** from the chatter set: in reply to "shall I scan?"
  they mean GO, and grading them conversational would strip the toolset
  mid-task.
- **Sandbox could hang a worker thread forever.** The post-SIGKILL drain in
  `basilisk_ext/sandbox.py` called `communicate()` unbounded. If `killpg` fell
  through to `proc.kill()`, a grandchild still holding the pipes would block
  that thread indefinitely. Now bounded at 5s.
- **`translate_install_meta()` raised `AttributeError` on non-dict input.**
  Both `_install_hint` call sites swallow the exception but then hit
  `meta.get()` again unprotected, so the crash surfaced there instead. Latent
  rather than live (all 59 `_TOOLS` entries are dicts), but it is public API.
- **`terminal_log_and_show()` mutated GTK off the main loop.** It touched
  `set_visible()` / `add_css_class()` raw while `terminal_log` beside it is
  carefully deferred. Zero callers today, so it was a landmine rather than a
  crash; the reveal is now queued on the main loop.

Verification: classifier matrix 116/116 in both directions with zero
action-side regressions; `test_leanchat` 88/1 -> **89/0**; full suite green
except the long-dead `test_kali.py`. Prompt budgets byte-identical to v7.7.0
(lean 2133, grouped 7024, non-grouped 20106) — the classifier tables are not
prompt text. GUARDRAIL block verified byte-for-byte unchanged. The
destructive-command gate was fuzzed with 40,000 adversarial shell strings:
zero crashes.

## v7.7.0 — runs on Arch now (CachyOS), not just Kali

Basilisk grew up on Kali (Debian/apt/classic-sudo). This release makes the
*exact same build* run correctly on Arch-based distros — **CachyOS**, Arch,
EndeavourOS, Manjaro — plus Fedora/SUSE, with nothing distro-specific
hard-coded. The package manager, the way root is obtained, and where
wordlists live are all **detected, never assumed**.

- **Privilege escalation is now portable and self-diagnosing.** The old path
  assumed classic `sudo` and reported every failure as "incorrect sudo
  password" — which on Arch/CachyOS was often *not* a wrong password at all.
  Now:
  - The escalation tool is detected: classic **sudo**, **sudo-rs** (the Rust
    rewrite Arch/CachyOS may ship, which older builds lack `-A`/askpass on),
    or **doas**.
  - **NOPASSWD short-circuit:** if the box can already escalate without a
    password (a `%wheel … NOPASSWD` rule or a live cached timestamp — common on
    single-user Arch setups), the whole password dance is skipped and the
    command just runs.
  - **`sudo -k` before validating** so a *wrong* password can no longer ride a
    coincidental cached timestamp and appear to work.
  - **Askpass rescue on rejection:** if the inline credential is rejected, we
    now retry via `SUDO_ASKPASS` (when the build supports it), which
    authenticates each inner `sudo` independently and is immune to the
    timestamp-carry failure — the single most common Kali→Arch break.
  - **Honest errors:** when a password is genuinely rejected on both paths, the
    message names the real Arch/CachyOS causes (a `Defaults rootpw`/`targetpw`
    sudoers policy that wants root's password, or a user not in wheel/sudo) and
    gives a one-line manual check (`sudo -k -v`) — instead of sending you
    chasing a typo. `doas`-only boxes get a clear "add a persist rule" note.
- **Package manager auto-detected** (`pacman`/`apt`/`dnf`/`zypper`/`apk`).
  `check_updates` parses all of them; every "install X" hint — missing-tool
  inventory, seclists, bubblewrap, ufw, code scanners — now emits the
  **distro-correct** command (`sudo pacman -S …` + an AUR/BlackArch fallback on
  Arch, `dnf`/`zypper` elsewhere), never a bare `sudo apt install` on a box
  without apt.
- **Basilisk is told the box's package manager + escalation tool** in the
  auto-detected host-facts, so the agent issues `pacman -S` on CachyOS instead
  of defaulting to Debian habits.
- **Wordlist/SecLists discovery widened** beyond the Kali `/usr/share/wordlists`
  layout to the AUR/BlackArch/Fedora and user-local locations; `rockyou` is now
  found wherever it actually lives rather than at one hard-coded path.
- **`install.sh` desktop-helper step** now has `pacman`/`dnf` branches with the
  correct package names (`libnotify` vs `libnotify-bin`, `tesseract` vs
  `tesseract-ocr`, `spectacle` vs `kde-spectacle`), not apt-only. GTK4/libadwaita
  and font steps were already multi-distro.
- Renamed the internal askpass env var `KALI_SUDO_PW` → `BASILISK_SUDO_PW`
  (leftover from the pre-rename days; password handling and security properties
  unchanged — never on disk, in the log, or in argv).
- Suite green: `test_basilisk` 79/79 and all core/ext suites pass (the
  pre-existing dead `test_kali.py` `kali_core` import and one pre-existing
  lean-classifier case are unchanged by this release).

## v7.6.0 — Unleash: one button, off the leash

The big red dragon lands in the composer bar. Two modes, one switch, no ambiguity.

- **New UNLEASH button** (the dragon emblem, `basilisk-btn-unleash.png`, with an
  embedded fallback in `basilisk_btn_art.py` so it can never go missing). It
  glows hot red when armed.
- **Armed → off the leash.** Hitting Unleash makes Basilisk *confirm the target*
  first (restate it in one line if the conversation already names one, or ask for
  it once if it doesn't) and then go **fully autonomous** — it does not stop until
  the mission is complete (the `MISSION_COMPLETE` token), or you stand down. Every
  message you send while armed is treated as an objective and worked relentlessly;
  even a question becomes "go find out and don't stop." Arming forces agent mode on
  (it needs the tools and the mission loop) and persists across restarts.
- **Disarmed → answer once and stop.** With Unleash off, Basilisk answers each
  message a single time and stops. No autonomous grind, full stop. Standing down
  mid-run halts the mission immediately.
- Unleash is now the single master switch for the two modes: the mission latch and
  the per-turn relentless/answer-once decision both key off it, in one place, so
  the behaviour is unambiguous. (Replaces the old implicit agent-mode + question-
  classifier gating that could drift between the two.)

## v7.5.4 — completion that survives the model talking instead of tokening (and the 71.7% board)

**From your Thoughts panel + terminal log. The model finished, thought "let me output the completion token", emitted `[[MISSION_COMPLETE]]` — and it STILL looped. The two-phase completion was too literal.**

- **BUG — the re-verify demanded the exact token twice, so a done model that TALKED never ended.** Completion needs two confirmations so a premature "done" can't slip through. But the second one had to be the exact `[[MISSION_COMPLETE]]` token again — and a finished model doesn't re-emit a token, it says "Done. Container gone, docker daemon dead, socket disabled. All clean" or produces filler. So the flow was: claim done → forced re-verify → (natural-language confirmation, no token) → flag reset → claim done → … forever. Fixed with a cleaner model: once it has claimed done, the **next quiet turn confirms it** — whether that turn re-emits the token, talks, or produces filler. Only a real new **tool call** cancels a pending completion (that means it found more work), and that path already clears the flag. Two confirmations still required; the second no longer has to be a verbatim token.
- **BUG — a model that never emitted the token at all looped on plain summaries.** If it just narrated "done" turn after turn without ever emitting `[[MISSION_COMPLETE]]`, nothing caught it (the idle cap only covers runs that never acted). Added a **stall guard**: after it has acted, several consecutive turns with no tool call means it's done or stuck (a live pentest runs tools constantly) — force one re-verify, which the next quiet turn then confirms. Consolidated the 7.5.3 degraded-streak counters into this single no-action streak; a real working run with tool calls resets it and is untouched. Verified it does NOT stop early when it claims done and then finds more real work.
- **Traced against your exact sequences.** Replayed the completion state machine for token-then-filler (your screenshot), token-then-talk, never-emits-token, the alternating plain/degraded pattern from the v7.5.3 log, and claim-then-finds-more-work: the first four now end cleanly, the last correctly keeps working. Suite 15/15.
- **Benchmark refreshed — 81/113 (71.7%), up from 73/113.** Full board, black-box, fully autonomous, v7.5.3 on `172.17.0.2:3000`. Gains concentrated in the deep end: 5-star 42% → 68%, 6-star 33% → 58% (now takes SSRF, SSTi, Forged Coupon, Forged Signed JWT, Login Support Team, Premium Paywall, Arbitrary File Write). README updated with the new table and progression (51 → 58 → 73 → 81); scorecard added at `benchmarks/juice-shop-scoreboard-2026-07-17.txt`.

## v7.5.3 — the serpent finally knows when to stop (the real "it won't stop" bug)

**From your terminal log, not from reading code. The task finished — docker up, Juice Shop listening on 3000 — and it looped forever anyway. Root cause found and fixed.**

- **BUG — `notify` defeated completion, so a finished mission never ended.** Completion takes two claims in a row (a premature "done" can't slip through). But the model announces "done" by *also* firing a `notify`, and any tool call — including `notify` — reset the pending-completion flag. So the sequence was: claim done → (notify clears the flag) → claim done → (notify clears it) → **forever**. Fixed: `notify` is the model talking to *you*, not progress toward the objective — it no longer resets the completion claim, counts as "acting", or resets the loop counters. Only substantive tool calls do. Two "done"s now actually land and the mission ends.
- **BUG — a finished model that goes quiet looped on degraded-retries.** When it's done, it has nothing left to say, so it emits empty/repetitive replies. Those tripped the degraded-output auto-retry, which cycled providers 3× and then **fell through to another mission turn** — producing more empty replies, forever. Fixed two ways: (1) if it already claimed completion and then produces only empty output after retries, that IS done — accept it; (2) if it keeps bottoming out on empty replies without ever claiming done, it's stuck or silently finished — stop after two such streaks instead of re-kicking into more empty replies. A clean reply or any real action resets the streak, so a genuinely working run is untouched. It also correctly does NOT stop early when it claims done but then finds more real work (verified).
- **Traced against the exact log.** Replayed the state machine for the observed sequence (docker work → claim → degraded → notify → claim) and three neighbours (notify-then-claim, never-claims-just-degrades, claim-then-more-work): the first three now terminate, the last correctly keeps working. Suite 15/15.

## v7.5.2 — line-by-line pass: four real bugs, including one that ate autonomous file writes

**A genuine read of the execution core, not a grep. Four bugs, one of them significant.**

- **BUG — autonomous `write_file`/`propose` silently did nothing.** The big one. `_pure_tool_fn` classifies `write_file`/`propose`/`propose_edit` as side-effecting, so `_on_stream_done` excluded them from the executable set — correct in *supervised* mode, where they render an approval card. But in *autonomous* mode there is no card (cards are drawn supervised-only) and no operator to click it, so those calls reached **nothing**: the model's `write_file` executed as a no-op. It was masked because the model usually writes files via `run` (`tee`/`cat`), but any real `write_file` in autonomous mode was lost. Fixed: in autonomous mode those calls now stay executable and run directly through `_run_proposed_edit`/`_run_proposed_command`. Also fixed the follow-on: those handlers had an operator-click "busy" guard that would have bailed on the programmatic path — now skipped when there's no card (autonomous), applied only to real clicks.
- **BUG — a question could grind an uncapped tool chain.** 7.5.0 stopped a question from starting a never-stop *mission*, but a question still runs through the normal tool-result loop, and autonomous mode is uncapped — so a model that ignored "answer with at most one tool" could chain tools with nothing to stop it (missions have the idle-cap/circuit-breaker; a question had neither). Added a hard cap: after a few tool round-trips on a question, tools lock and it must answer now.
- **BUG (self-inflicted) — the loop/circuit breakers miscounted with foresight on.** `_execute_command` re-enters itself through the foresight gate, and the 7.5.1 loop-break bookkeeping was at the top of the function — so with foresight enabled every command was recorded **twice**, tripping the 3× nudge and 6× stop at half the real repeat count. Moved the bookkeeping past the foresight gate so each command is counted exactly once.
- **BUG (self-inflicted) — the shell-block recovery could run a command you only ASKED about.** Caught and fixed in the same pass: the 7.5.0 recovery (auto-run a printed command) checked only `approval_mode`, not whether a mission was active, so an illustrative fenced command in the answer to a *question* could execute. Now scoped to an active mission.
- **Verified, line by line:** read the turn/mission lifecycle, the stream-done dispatch, the propose/write/card paths, `_pure_tool_fn`, `_execute_command`'s foresight/sudo/dedup, history assembly, error-retry, and the mission-directive one-shot. Confirmed the `run` path is untouched by the executable change, the mission directive is injected-then-cleared, no mutable default args, no escape warnings. Suite 15/15.

## v7.5.1 — a hard debug pass: a real bug caught, a loop capped, the suite made honest

**A line-by-line review of the 7.5.0 changes turned up a genuine bug and two rough edges. No new features — this cut is correctness.**

- **BUG FIXED — the shell-block recovery could auto-run a command you only ASKED about.** 7.5.0 added recovery: in autonomous mode, if the model prints a command in a fence instead of calling `run`, execute it anyway. But the gate checked only `approval_mode == "none"`, not whether a mission was active. So on a *question* turn (the direct-answer path, no mission), if the model showed an illustrative `bash` block in its answer, the recovery would **run it** — executing something you only wanted explained. Now scoped to an ACTIVE mission (`_mission_active`), where acting is the whole point; a question never triggers it.
- **Loop can no longer spin forever.** With recovery now executing printed commands, a model that ignored the 3× loop-breaker nudge and kept printing the same command would have it re-run every turn — and once a mission has acted, the idle cap doesn't apply. Added a hard circuit-breaker: the **exact same command 6× in a row** stops the run cleanly (send a message to resume). Mirrors the existing idle-cap stop; distinct from it (that one only covers missions that never acted). Legitimate relentless work with *varied* commands is untouched.
- **The test suite is finally honest: 15/15, no red.** `test_kali.py` was a pre-rename duplicate of `test_basilisk.py` — it imported the dead `kali_core` module and failed on every single run, and it carried **zero** tests not already in `test_basilisk.py` (verified by diff). Removed. The suite is now all-green, so a real regression actually shows up instead of hiding behind a test that was always red.
- **Verified, not assumed.** This pass re-checked: the classifier on 22 adversarial cases (22/22) on top of the 38-case battery; that all 136 advertised tools are wired to a handler; that the recovery's dependencies are imported and it's crash-safe on empty/comment-only/non-shell input; that discovery still routes into `auth_attack`/`jwt_attack`/`api_test`; that a *question needing one tool* still gets the toolset and a follow-up turn to answer (the tool-result kick is not mission-gated); and that the autonomous tool budget never locks before the first tool.

## v7.5.0 — the serpent learns the difference between a question and a hunt

**The headline is a behaviour fix, not a banner.** Ask Basilisk a *question* in autonomous mode — "how does the oracle decide a bug is confirmed?", "should I spray or brute here?" — and it would drop into full never-stop mission mode and grind, firing tool after tool, unable to just *answer you and stop*. That's fixed at the root, plus three real attack builders the methodology always named but never carried, and the discovery engine now routes straight into them.

- **Commands that were PRINTED instead of RUN now actually execute.** The worst regression: in autonomous mode the model would sometimes write a shell command inside a ```` ```bash ```` fence instead of emitting a `run` tool call — so it rendered as a useless copyable banner and never executed, and the mission re-kicked and printed it again. Two-part fix. (1) Deterministic recovery: in autonomous walk-away mode, if a turn produced NO executable tool call but the output carries a shell fence, Basilisk extracts the first command and runs it through the exact same gate — the catastrophic-command floor still applies, non-shell fences (json/python/yaml) are ignored, `$ `/`# ` prompts and line-continuations are handled. It does not depend on the model getting the format right. (2) The autonomous directive now states outright that a command in a code block does NOT run and the ONLY way to execute is the run tool. Covered by 8 new tests (`shell_block_command`), including that a recovered command re-parses as a real `run` call and that a catastrophic one is still blocked.
- **Question vs. hunt — autonomous mode no longer treats a question as a mission.** A new `direct_answer_turn` classifier (in `basilisk_persona.py`) distinguishes a genuine question/advice/explanation from a task, at 38/38 on the regression battery. The precision cuts both ways: a leading imperative (`scan …`, `exploit …`), an elliptical command (`do it`, `the next one`), or a **named live target** (`what vulns does example.com have` — that's a hunt, not a chat) all stay tasks and keep the full relentless loop; only a real question ("how does X work?", "do you support Y?") is answered directly. On a question it now injects a *direct-answer* directive — act directly if one tool is genuinely needed, answer concisely, then **stop** — and, critically, it no longer arms a persistent mission, so there is no re-kick loop to escape. A task is unchanged: full autonomous, relentless, ends only on the completion token. Two seams, both guarded: the mission-start gate and the directive branch.
- **Three fangs the methodology named but never actually carried.** The cheatsheet has talked about credential spraying, JWT weak-secret cracking and API method-tampering for cuts — but no *builder* produced the concrete commands/payloads, the way `sqlmap_plan` does for SQLi. Now: **`auth_attack`** (default-creds → username-enumeration by text/status/**timing** → lockout-safe spraying → targeted brute, emitting the exact hydra/ffuf command + a public default-creds list), **`jwt_attack`** (HS256 weak-secret cracking with `hashcat -m 16500`, plus `kid`/`jku`/`jwk`/`x5u` header-injection — everything `jwt_forge`'s alg:none/key-confusion didn't cover), and **`api_test`** (HTTP verb/method tampering, `X-HTTP-Method-Override`, rate-limit bypass, stale-version/hidden-endpoint discovery, content-type confusion — the API surface `idor_probe`/`mass_assignment` don't touch). All pure builders, benign proofs, lockout-aware; the no-reverse-shell / no-implant / no-persistence floor is unchanged and guarded in the suite. That's **60 offensive tools**.
- **The discovery engine now routes into the new fangs.** `attack_surface` — the miner that decides where to hit on an unfamiliar app — was pointing a discovered login form only at SQLi/LDAP, a JWT only at `jwt_forge`, and a generic `/api` route at nothing specific. Now a login/auth/reset route leads with **`auth_attack`**, a `/api`·`/rest`·`/v2`·`/token` route maps to **`api_test`**, a user/account/order route adds **`api_test`**, and a discovered JWT points at **`jwt_attack`** as well as `jwt_forge`. Find → the right builder → verify against ground truth, one coherent loop.
- **A loop breaker for stuck autonomous repeats.** Once a mission has acted (run any tool) the idle cap lifts by design — a real engagement runs tools constantly and must stay relentless. The gap that left: nothing caught the model firing the *same* command over and over (re-running `sudo systemctl start docker` when Docker already started, or an uncached `sudo` prompt failing silently in walk-away mode). Now, when the last three executed commands are byte-identical, Basilisk injects a hard nudge — *stop repeating it; verify the real state with a different command (`docker ps`, `systemctl status`, a `curl` health check), read that, then advance or finish; if it needs sudo and sudo isn't cached, say so and move on.* It never stops the mission (legit relentless work continues) — it only redirects a provably-stuck repeat. Reset on Stop and on every new objective.
- **12 new tests** across the three builders (every mode + unknown-mode handling + a safety-boundary assertion that none of them emit reverse-shell/C2/implant tokens), and the classifier battery. Suite stays green.

## v7.4.0 — the serpent stops burying loot in the wrong grave

**A hard audit pass — the kind that finds the bugs that don't crash, they just quietly do the wrong thing.** No new fangs this cut; instead the serpent's own house got torn apart and put back straight. The headline is a silent one: it was writing its kills to the wrong lair.

- **Engagement memory was landing in a dead directory.** `engage` and `oracle` — scope rules, the asset graph, the whole arm→check→verdict ledger — were persisting to `~/.config/**kali**/engagements`, the pre-rename path, while every other part of Basilisk lives under `~/.config/basilisk`. The modules' *own docstrings* said `basilisk`; the code said `kali`; nobody passed a path to settle the argument. So the serpent's memory of a campaign was being buried where it would never look for it again. Both storage roots now point at `~/.config/basilisk/engagements`, and the existing legacy migration drags any already-written data across on the next boot. Nothing lost, everything finally in one place.
- **A knob that turned nothing now turns something.** `codescan`'s `intensity` (light · normal · deep) was documented to tune scan depth and did **absolutely nothing** — all three levels mapped to an empty string that was never read. Wired to real semgrep behaviour now: **light** runs a fast curated ruleset (`p/ci`) and skips the slow live-secret verifier for a quick first look; **normal** is the `auto` ruleset and full tool set; **deep** adds the `security-audit` ruleset and drops the file-size cap so nothing hides in a minified blob. A regression guard in the suite proves the three levels now produce three different scans, so it can never rot back to a no-op.
- **The companion daemon couldn't even start.** The optional headless unit shipped as `kali-ext.service`, pointed at `-m kali_ext.worker` and `~/.local/share/kali` — a module and a path that haven't existed since the rename. It would have died on `ModuleNotFoundError` the instant anyone enabled it. Rebuilt and renamed to `basilisk-ext.service`, pointing where the code actually lives.
- **The last of the old skin, shed.** Swept the remaining pre-rename ghosts: the main application class (`KaliApp` → `BasiliskApp`), the MCP client identity, the skill-sandbox temp prefix, the default tool/author stamps in the benchmark and exploit-authoring paths, and both developer WIRING docs. An atomic-write test that was hunting for a `.kali-tmp` file the code never writes now watches for the real `.basilisk-tmp` — it was green while proving nothing.
- **Sharper on the draw.** The shell-history secret scanner was recompiling its regex on every audit run; it's compiled once now, at import. Small, but the gaze shouldn't waste a motion.

**The README lost the legend.** Rewritten top to bottom into a clean technical brief — what it is, how to install it, the verified 73/113 board with the commands to regenerate it, the loop, the exploit builders, and the security model — no serpent-cult, no gothic script, just the facts a stranger needs to trust it and run it. (The legend lives on here, where it belongs.) Suite is green end to end — **15** files, `codescan` up to 43 checks with the new intensity guards — every module compiles, and the CSS blob stays pure ASCII.

## v7.3.0 — the serpent learns to tell a kill from a near-miss

**A 200 is not a solve, and now the serpent knows the difference.** The gaze could always fire an exploit; what it lacked was a memory of what actually *landed*. This release gives it one — an **exploitation oracle** that judges every strike by evidence, records the verdict, and feeds that truth straight back into the hunt. It stops mistaking a plausible response for a kill, stops re-killing what's already dead, and gets sharper about what's left with every move.

- **Arm → fire → check.** Before it strikes, Basilisk *arms* an attempt with the exact marker that would prove it — a dumped row, another user's token, a status code, a regex, a measurable difference from baseline. After it strikes, `oracle_check` weighs the response against that marker and stamps a verdict: **confirmed · failed · pending · inconclusive**, with the reasoning attached. No more counting a solve on a hunch.
- **A ledger that feeds the loop.** `oracle_status` is the running tally of the whole campaign — what's proven, what's still open, what died. The loop consults it every planning turn, so it never re-runs a confirmed exploit and always knows exactly what's left. This is the part that makes a long run get *smarter* instead of just longer.
- **Eyes in the out-of-band dark.** For blind bugs that echo nothing back — blind SSRF, RCE, XXE, out-of-band SQLi — `arm` with `blind: true` stands up a local **out-of-band canary listener** and hands back a unique callback URL to bury in the payload. If the target ever reaches out to it, the blind hit is proven with certainty. The technique commercial suites charge a licence for (Burp Collaborator, interactsh), running locally and offline. `oracle_listen` drives it directly.
- Four new tools in the **offensive** group: `oracle_arm`, `oracle_check`, `oracle_status`, `oracle_listen`. All local — the only thing that ever leaves is a target's own callback arriving at your canary.

**Walk-away autonomy, taught to know when it's genuinely idle.** v7.2.0 made the loop never dead-end; the price was that *every* message — a greeting, a one-line question — became an unstoppable mission that could only end on a completion token the model doesn't always emit, so it span re-kicking on nothing. Fixed on two fronts, without loosening the leash on real work:

- **Small-talk is no longer a mission.** A purely conversational opener (the same thing lean-chat already recognises — a greeting, thanks, an opinion question with no hint of an action) gets a normal single reply. Anything that hints at a task still starts a relentless mission.
- **A mission that never acts can't spin forever.** Relentlessness is now unbounded *only once it has actually run a tool* — which a real pentest does constantly, so it stays as unstoppable as before. A pure-text task that never acts is idle-capped (`mission_max_idle_kicks`, default 3) so it settles cleanly instead of hammering the API on an empty loop. Come back to *done*, or to Basilisk still grinding a live target — never to a dead stop, and never to a greeting stuck in a loop.

**Culled and cleaned.** Removed a dead, broken test file (`tests/test_kali.py` — a pre-rename duplicate that still imported the long-gone `kali_core` module and failed on every run); its coverage lives on in `tests/test_basilisk.py`. The suite is green end to end again, now **15** files including the new `tests/test_oracle.py` (verdict engine + ledger + out-of-band canary, all offline). The README was brought back in step with the app it describes — the walk-away autonomy and the new oracle are in *How it hunts*, next to the verified 73/113 board.

## v7.2.0 — she does not stop until it's done

**Walk-away autonomy, enforced in the code — not just asked of the model.** Basilisk kept stopping for two reasons, and the persona telling it to be relentless was never enough on its own: (1) the turn loop only continued while the model was calling tools, so the instant it returned a plain reply — a summary, a status, a question — the loop treated that as *finished* and halted; (2) a single stream/API error tore the run down with no retry. Both are now fixed at the loop level.

- **The message you send is the objective.** In agent mode it's pinned as the mission, and a no-tool reply no longer ends anything — the loop re-injects the objective and pushes the model to take the next concrete action. It cannot trail off into a summary and stop.
- **Errors don't kill it.** A stream/API error triggers exponential backoff and retries — forever, capped at 60s between tries. A provider outage just means it waits and resumes; leave it running for weeks and a blip won't end it.
- **It ends on exactly two things:** you press **Stop**, or the model explicitly signals the objective is done — and even then it's forced through a hard re-verify (it must re-check point-by-point and re-confirm) so a premature "done" can't slip through. If real work resumes between the claim and the confirm, the claim is thrown out.
- **Smart, not a fork bomb.** Consecutive no-progress settles back off (0.15s → up to 15s); an actual tool running resets it. So a stuck model keeps trying without hammering the API — you come back to *done*, or to Basilisk still grinding, never to a dead stop.

New switch in Settings → Behaviour: **"Never stop until the task is done"** (on by default, agent mode only). The catastrophic-command hard block and the target scoping are unchanged — unstoppable means the *loop* never dead-ends, not that the leash comes off.

## v7.1.0 — she can be taught to see, in one place

**Setting up vision no longer means guessing.** The Images & vision settings now walk the whole path in one spot: choose the **vision provider**, type that provider's **API key** right there (no more hunting through the Providers section — it's the same key, wired to update everywhere), then **pick a vision model** from a per-provider list instead of having to know the exact id. SiliconFlow's Qwen2.5-VL family (7B / 32B / 72B) and a couple of Groq multimodal options are offered directly. The **Vision model** field stays free-text underneath, so when a provider rotates its line-up you can always type the current id by hand — and the key field + model picker re-sync themselves the moment you switch provider. Now `analyze_image` actually has everything it needs to look at your photos.

## v7.0.0 — the serpent comes of age

**You can finally reach the monster.** The Monster-voice switch and its depth dial were being greyed out whenever the speech engine wasn't detected at startup — which meant if espeak/ffmpeg weren't found the instant the app booted, you couldn't even *arm* the thing. That's backwards: it's a preference, not a live action. Both controls (and the Read-aloud switch) are now settable whenever the voice module is loaded, so you flip monster on once and it takes hold the moment an engine is present — no fighting a locked toggle. `tts_monster` and `tts_depth` also got proper entries in the defaults table instead of surviving on inline fallbacks, so the setting persists and reads back cleanly everywhere.

**Everything from the 6.x run, sealed into a major cut.** The titlebar now wears the full serpent — Notifications, Settings, Minimise, **Expand**, and Close as dragon-forged plaques sized to match the composer rail. The monster voice is robust on a bare box (deep espeak base with no post-processing, direct-audio fallback when there's no WAV player, ffmpeg in the installer). Notifications chime. Memory recalls by meaning, not just matching words. And the security audit — which had been crashing on its first finding — runs clean end to end.

**Settings swept.** Every voice, notification, and memory control now has a backing default and a live handler; nothing references a setting that doesn't exist. All 40 modules compile, pyflakes is clean, 14/14 tests green, the CSS blob is pure ASCII, and every button plaque loads on disk and embedded.

## v6.10.0 — new scales on the titlebar, and the audit crawls out of its grave

**The whole titlebar wears the serpent now.** Notifications and Settings swapped to the new dragon-forged word-plaques, Minimise re-carved to match, and two new controls joined them: **Expand** (maximise / restore toggle) and **Close**. All five are sized to the same height as the composer buttons along the bottom, so the top and bottom rails finally read as one set instead of two different art styles. The plaques ship on disk AND embedded as base64 in the button-art module, so they can never go missing on an update.

**The monster voice works even on a bare box.** It was never truly broken — it just went quiet or flat when the machine had no sox/ffmpeg to pitch-shift, or no WAV player to push the processed audio through. Fixed both: espeak's *own* base pitch now drops with the depth setting, so the voice is deep and menacing even with zero post-processing, and when there's no WAV player it falls back to espeak's direct audio instead of silently producing nothing. `ffmpeg` was also added to the installer's voice packages so the full cavern-deep FX chain is there out of the box.

**A chime when she speaks up.** Notifications now make a sound — a short two-note chime, synthesised once and cached, fired through whatever audio player exists. Silent by default only if you turn it off (new *Notification sound* switch in Settings) or the box has no player.

**Fixed: the security audit was stone dead.** The `Finding` type had lost its `@dataclass` decorator, so every audit check threw `TypeError` the instant it tried to record a finding — and even past that, the score-to-grade step referenced a `SEVERITY_WEIGHTS` table that didn't exist (`NameError`). The whole read-only system audit (firewall / SSH / kernel / updates / auth / crypto) crashed on the first check. Decorator restored, weights defined and tuned to the existing A+→F ladder (a lone critical drops you to C, a high to B). The audit runs clean end to end again.

**Debug pass.** All 40 modules compile, pyflakes is clean of undefined names, all 14 test suites green, the CSS blob is still pure ASCII, and every button plaque (on-disk and embedded) loads.

## v6.9.0 — she remembers by meaning now, not just by matching words

**The recall problem is fixed at the root.** Memories were being stored fine, but recall was keyword-only — it could only find a memory if your question reused the same words the memory was written in. Ask "what laptop do I run" when the stored fact says "ThinkPad X395," or "which model backend" when it says "SiliconFlow," and recall came back empty. The store was never broken; the *matching* was too literal. That's what read as "she stores memories but can't recall them."

**Recall is now hybrid: keyword OR meaning.** The keyword channel still runs exactly as before, and on top of it a semantic channel matches on embeddings — so a memory surfaces if your question hits it by *either* wording or meaning. Because semantic can only ever *add* matches, turning it on can never hide a memory keyword would have found. Every fact you'd already stored gets embedded in a background pass on startup, so your existing memory becomes searchable by meaning too, not just new stuff.

**It stays honest about noise.** Sentence embeddings sit at a moderate baseline similarity even for unrelated text, so a naive threshold would inject junk. Instead the semantic channel only accepts a match that clearly stands out above the query's own typical similarity — a question about nothing you've stored produces a flat distribution with no standout, so nothing gets injected.

**Offline-safe, and yours to control.** Embeddings ride the SiliconFlow key you already use (model defaults to `BAAI/bge-m3`, override in settings). No key, or the endpoint's down? Recall silently falls back to keyword — it degrades, it never breaks. There's a new *Semantic recall* switch in Settings if you want it off. The embedding call adds a small per-recall round trip on a tight timeout; if it's ever slow, that turn just runs keyword.

## v6.8.0 — she speaks with a monster's throat now

**Basilisk has a voice to match the face.** Read-aloud used to come out in a plain, neutral TTS register — a serpent that looked like the end of the world and sounded like a satnav. No longer. Every spoken reply now runs through a monster-voice chain: the synthesized speech is pitched down into a deep register, given chest weight on the low end, a little overdriven grit for a growl, and a touch of cavern reverb — so she sounds like something speaking up out of the dark, not reading you the weather.

**Works on whatever engine you've got.** The chain sits *after* synthesis, so it deepens both Piper (neural) and espeak — and espeak additionally gets a lower, male base voice so it's already growling before the FX even land. The pitch-shift itself uses `sox` if it's installed (cleanest) or `ffmpeg` as a capable fallback; if you have neither, the voice still speaks, just without the deep processing (install `sox` for the full effect — `apt install sox`).

**Two new knobs in Settings > Voice.** *Monster voice* (on by default) toggles the whole thing, and *Voice depth* sets how many semitones the pitch drops — crank it for something more subterranean, ease it back if you want the words crisper. Changes take effect on the next thing she says; no restart. The Test button plays a sample so you can dial it in by ear.

## v6.7.0 — the whole toolbar is forged now, and one face rules the app

**Five plaques where five buttons used to be.** The composer row was a lie of two halves — one wide serpent-and-plaque **Attach** button, then four flat little symbol coins (camera, lightbulb, speaker, prompt) that shared none of its craft. Retired. Camera, Suggestions, Voice and Terminal are each a full dragon-forged word-plaque now — the serpent coiled over cracked red stone, the name engraved across it in the same hand as Attach. The row reads as one set instead of one plaque chaperoning four placeholders.

**And you can actually read them.** Those plaques were being rendered at the 26px height the little header coins use, which crushed an engraved word into an unreadable smear. The composer buttons now render tall enough to read (`_COMPOSER_BTN_PX`) while the titlebar/header icons stay small where they belong. The black around each plaque is punched to transparent, so on the near-black chat surface only the stone and the serpent show — no floating rectangles, and the ember hover-glow hugs the art. Drop your own `basilisk-btn-<name>.png` in `~/.local/share/basilisk/` to re-carve any single one, same as always; the embedded fallback copies were re-cut to match so the buttons are right even if the files ever go missing.

**One head, worn everywhere it matters.** The crowned red dragon-head — scaled, four-eyed, staring out of a black iron frame — is now the single emblem of the app. It's the Send button you press, the toggle that opens the sidebar, and the face beside every reply Basilisk speaks — all one file (`basilisk-avatar.png`), so re-theming the app's identity is a single swap. On the Send button it's cropped flush to its iron frame and fills the button edge to edge — no dark gutter floating a small head in a big box. The desktop and window/taskbar icon (`org.thepriest.basilisk.svg`) wears the same head, so what launches Basilisk and what sits inside it finally agree.

## v6.6.6 — a serpent coils the penguin, and the floor learns to read

**New face behind the chat.** The dragon watermark is retired. Behind every conversation now sits the real thing — Tux lit in the same ember-pink as the rest of the forge, a basilisk coiled around and over him, fangs bared, on black. The scrim and 0.9 opacity are unchanged, so it sets the mood without fighting the text. Drop your own `basilisk-watermark.png` in `~/.local/share/basilisk/` to override it, same as always.

**The hard safety floor can now read interpreter payloads.** The catastrophic-command floor was a *shell* classifier: it caught `rm -rf /` through quoting, `$IFS`, `sh -c`, `cd && rm`, `find -delete`, and decode-pipe-to-shell — but a `python3 -c "import os; os.system('rm -rf /')"` or `python3 -c "shutil.rmtree('/')"` handed the model a language runtime the shell floor couldn't see into, and walked straight past it (python, perl, ruby, node, php). Closed. The floor now lifts the shell string back out of `os.system` / `subprocess(shell=True)` / `popen` / backticks / `child_process.exec` / php `system()` and re-scans it under the **same** rules — so `os.system("ls")` stays fine and `os.system("rm -rf /")` is caught — plus direct `shutil.rmtree` / `os.removedirs` on a root/`$HOME`/system path, and list-argv `subprocess.run(['rm','-rf','/'])`. The self-source tamper guard got the same lifting (`open('basilisk_safety.py','w')` and friends), and both guards now fail **safe** on a detector bug rather than waving a command through. Because it reuses the existing scan primitives, the false-positive surface is identical to the shell floor's — ordinary `python3 -c "..."` work never trips it. 20 new interpreter-attack cases plus a batch of benign one-liners added to the floor's test contract to prove it; full suite green. The immutable GUARDRAIL block is untouched.

**Tools no longer go dark after a long chat.** A token optimisation was stripping the whole tool catalog on turns that *looked* purely conversational — fine for "hi"/"thanks", but it also caught the short elliptical commands you give mid-conversation ("ok do it", "yeah go on", "the next one"), which carry no explicit tool word. So a session that started chatty could suddenly be unable to act for several turns until you spelled the verb out — while the exact same request from a cold start worked first time. Two fixes, both erring toward keeping tools: the "just talking" detector now reads those follow-ups as action intent and keeps the toolset, and — belt and braces — once ANY tool has run in a conversation the full catalog always ships from then on (a short follow-up after real work is always operational). 22 new cases pin it in the test suite.

**A quieter voice.** Basilisk's persona was re-tuned from the dry operator's-right-hand register to that of a patient Tao/Zen sage — calm, spare, the occasional true line of insight set down only where it earns its place. It fits what she already was: a serpent that watches in stillness and strikes once. The wisdom is on a tight rein — a hard rule against proverb-spam, and a poetic line never stands in for a fact or pads a reply — so she still acts, still reports plainly, still verifies every checkable claim. The load-bearing GUARDRAIL block and every operational directive are untouched; only the way she speaks changed. (Prompt tiers are unchanged in shape: ~2.5K with no agent, ~7K with agent on for full tool *knowledge* + on-demand loading, ~18K only in max mode.)

## v6.3.1 — desktop icon launches again, and your old history actually migrates

Two fixes for regressions from the rename.

**Your chats now migrate for real.** The v6.3.0 migration was broken two ways: a rename pass had accidentally pointed it at the *new* dir instead of the old `kali` one, and it only ran when the new dir was missing — but the installer creates that dir (code lives beside data), so it never fired. Rewritten to copy each user-data item (chats, settings + your API keys, evidence, backups) out of the old `kali` folders whenever it's absent in the new home, on both first run and install. Your data was never gone — it sat in `~/.local/share/kali` — but the app now picks it up. Copy-only, so the old folders stay as a fallback; old code/assets in the shared dir are deliberately left behind.

**The desktop icon launches again.** It ran from the terminal but not the icon because the launcher relied on the session PATH finding `python3`, which the desktop launcher doesn't always provide. The launcher now hard-codes the absolute `python3` path, the `.desktop` entry gained `TryExec`/`Path`, and a small `kali → basilisk` shim was restored so any icon pinned before the rename still works. Installer also refreshes the desktop/icon caches.

## v6.3.0 — one name, end to end: the whole namespace is Basilisk now

The project was born under the `kali` name and kept it in a hundred places the eye never reached. This release finishes the rename so the repo reads as one thing.

**Every `kali*` file is now `basilisk*`.** `kali.py` → `basilisk.py`, the five core modules, the embedded button-art module, the `kali_ext/` sidecar, every `kali-*.png/svg` asset, the app icon, and the test that shadows the main module. All imports, asset finders, and internal identifiers (avatar class, benchmark label, temp-file prefixes, the voice sidecar's scratch files) follow. The only `kali` left is where it should be: `kali.org` in the trusted-docs list and "Kali Linux" the OS.

**App identity moved too — safely.** App-id is now `org.thepriest.basilisk`; data lives under `~/.local/share/basilisk` and `~/.config/basilisk`; the terminal command is `basilisk`. On first run the app **copies** your existing chats, settings, evidence and backups over from the old `kali` dirs (never moves them — the originals stay as a fallback), so nothing is lost. `install.sh` retires the old `kali` launcher and desktop entry so you get one command, not two.

**`install.sh`, rewritten in the legend's voice.** The banner now speaks as the woken serpent instead of a generic tagline, and the stale "new in this version" feature list is gone — the changelog is the one place that lives. The uninstaller cleans up both the new Basilisk artifacts and every legacy `kali` one.

**Persona now carries the legend.** Basilisk's self-description tracks the README's myth — the mind that sheds skin, the gaze, the fangs, the sight through deceit, the sealed tablet, the one locked door, the floor it can't sink beneath — each mapped to the real subsystem. Every technical instruction kept; the immutable GUARDRAIL block untouched.

## v6.2.0 — open the web (on your terms), a full red re-forge, and an igniting-dragon splash

**Web access, reworked.** Trusted sources still fetch automatically with no prompt. Every *other* public host on the internet — not just a fixed community list — is now reachable, but each domain needs your one-tap approval first (the same gate GitHub/Wikipedia already used). Internal / private / loopback / link-local / cloud-metadata addresses stay hard-refused with no override (SSRF floor), on the initial request and on every redirect hop. Enforced in the dispatch path, never asked of the model. Persona and `web_sources` updated to match.

**Buttons, all red.** The five composer buttons (attach, camera, suggestion, sound, terminal) are the new dragon-forged red art. The four chrome buttons (settings, notifications, minimise, close) were recolored green → red. All nine are embedded as byte-identical base64 in `kali_btn_art.py`, so they can never go missing on an update; on-disk PNGs still win if present.

**Startup splash.** On launch, the chat-background dragon starts dark and a band of light sweeps up from its base to its head; once lit, it fades and the app opens. Fully self-guarding — any failure (no cairo, old GTK, no display) falls straight through to opening the app normally. Toggle with `startup_splash` in settings (default on).

**Persona reflects the Legend.** Basilisk's identity now tracks the README's legend — the mind that sheds skin, the gaze, the fangs, the sight through deceit, the sealed tablet, the one locked door, the floor it can't sink beneath — mapped onto the real architecture. Every hacking/technical instruction kept; the immutable GUARDRAIL block untouched.

**Fixes.** Removed the grey frame around the settings/notifications MenuButtons (their inner `> button` kept GTK's default styling; now transparent to match the other art buttons).

## v6.1.3 — the actual reason the button art never showed up (found and fixed)

The real bug: `install.sh` had the 5 button PNGs added to its remote-fetch list, but the SEPARATE loop that actually copies files into `~/.local/share/kali` (the one that runs for BOTH local and remote installs) never had them added. So the images never reached the install dir, in any install mode — the buttons always fell back to the old symbolic icons. My mistake in the previous version; fixed directly now, and:

- **A permanent guarantee, not just a copy-loop fix.** The button art is now ALSO embedded as base64 inside a new `kali_btn_art.py`, imported directly by `kali.py`. `kali.py` tries an on-disk `kali-btn-*.png` first (so you can still drop in a replacement file to re-theme a button later); if that's not there, it decodes the embedded copy instead. This means the art can now only go missing if `kali_btn_art.py` itself goes missing — the same class of file as `kali_core.py`, which has never had this problem.
- `install.sh`'s art-copy loop now includes all 5 button PNGs, and separately copies (and parse-checks) `kali_btn_art.py` into the install dir.

## v6.1.2 — custom dragon-forged button art

Your five dragon-emblem art pieces are wired in as real button faces (settings/gear, notification bell, terminal, minimise, close). Each is scaled down to button size, kept transparent (the art carries its own carved-stone frame, so no double border), with the same ember-glow hover as the rest of the buttons. Every one falls back cleanly to the old symbolic icon if its file is ever missing.

- **Settings** — the gear-in-dragon emblem is now the header menu button (Pin/Rename/Delete/Settings/About still live under it).
- **Notification bell** — the bell-in-dragon emblem replaces the glyph; the unread badge still overlays correctly.
- **Terminal** — the ">basilisk" terminal emblem replaces the symbolic icon on the toggle button.
- **Minimise / Close** — the window now uses two custom dragon buttons (the crossed-serpents X for close, the dragon-with-dash for minimise) instead of the compositor's default controls, so the whole top-right reads as Basilisk's own chrome.

Honest flags: the window now controls minimise/close itself rather than the desktop's own decorations — that's a real behavior change, and it may look/feel different under Phosh or other compositors than under KDE/X11 on the ThinkPad, worth a look on the NetHunter side. Also, this art is green-toned stone versus the red-ember theme of the other buttons — you said you'd forge the rest to match later, so left as-is for now.

## v6.0.10 — arcane buttons: carved obsidian and ember sigils, not gray squares

Cosmetic. Every chrome button was a flat gray robotic square; now they read like rune-stones lit from within by a Basilisk ember. Carved-obsidian base with a blood-red glow rising from the bottom, a faint sigil border, an inset carved highlight — and on hover the ember *awakens* (the glow flares and the border lights up); pressing sinks it into the stone. Applied to the composer buttons (attach, idea/suggest, camera, read-aloud, terminal), the model switcher, the menu / notification / settings buttons, and the window controls (the close sigil flares blood-red as you reach for it). Left untouched: the pieces that are already art -- the dragon logo toggle and the BASILISK wordmarks.

## v6.0.9 — fix the oversized header wordmark

The v6.0.8 header wordmark rendered from a full-resolution texture with CONTAIN, so the wide title area scaled it up to fill and blew the header up to hundreds of pixels tall. Fixed: both the header wordmark (24px) and the sidebar wordmark (34px) are now scaled DOWN to a small intrinsic size, set to SCALE_DOWN with no expansion, so they render small and centered and the top bar is back to its normal height.

## v6.0.8 — mid-run suggestions, header/composer fixes, a 20-turn terminal log

- **Suggest to Basilisk mid-run without stopping it.** New lightbulb button in the composer: type a nudge while it's working and tap it — the note is folded into the conversation and picked up on its very next step (the model's history is rebuilt each step, so it lands there automatically). No interruption, no lost progress. When idle, it just sends normally.
- **Fixed the two icons in the top-left corner.** The main header was showing the compositor's start-side title button next to our dragon toggle. Suppressed it — now only the dragon logo (which toggles the sidebar) sits there.
- **Header centre: small BASILISK wordmark instead of the tiny "New chat" text.** The little title label is gone; a small death-metal wordmark sits there now.
- **Composer row swapped:** the four action buttons (attach / camera / read-aloud / terminal) are on the LEFT now, the model name pinned to the RIGHT.
- **Terminal log is bounded to the last 20 command-blocks.** Older command-blocks are deleted outright from the buffer (and RAM) as new ones arrive — the live log stays small no matter how long an autonomous run goes. The line/byte backstops still apply and now keep the turn tracking in sync.

## v6.0.7 — a tidier composer and a branded header

More UI polish, all cosmetic/layout.

- **Model switcher moved onto the button line.** It used to float on its own row above the toolbar (looked orphaned once the buttons thinned out); it now sits inline, on the same line as Attach / Camera / Read-aloud / Terminal.
- **Removed the idle/thinking status pill.** With the chat now spelling out exactly what each turn did, a persistent "idle" pill was dead weight. Gone. (Its internals are kept internally so nothing that updated it breaks.)
- **The dragon logo IS the sidebar toggle.** One branded button instead of a plain toggle sitting next to a logo — tap the emblem to show/hide the sidebar.
- **The BASILISK death-metal wordmark IS the new-chat button.** Click the logo art to start a fresh chat; the separate "+" button is gone.

## v6.0.6 — the chat shows what it actually did, a cleaner toolbar, a brighter dragon

UI pass. The big one: a tool-using turn now reads as *what it did*, not a blank "thinking".

- **The chat tells the truth about each turn.** When Basilisk runs a command or fires a tool, that message now shows the real thing — the actual command (`$ nmap -sV …`), the file it wrote, or the tool it used — instead of always saying "thinking". "Thinking" is now shown only when the turn genuinely was just reasoning (no tool, no reply). The bubble was rendering a stale global action title; it now derives the line from the turn's actual tool calls.
- **Leaner toolbar above the chat.** Removed the Audit / Scan network / Check updates / Recent downloads / System info buttons — all of that is one typed sentence away, so the buttons were clutter. Kept **Attach** and **Camera** above the chat, plus **Read-aloud** and the **Terminal log** toggle. The **Agent-mode** switch moved into Settings (a new "Agent mode" group) instead of living above the chat.
- **Brighter dragon, darker backdrop.** The chat watermark is more visible (opacity up), and a neutral scrim sits behind it so the backdrop is darker in brightness only (same hue) — the serpent reads clearly now instead of nearly vanishing.
- **README legend + badges** brought up to the current build, and the legend's climax now lands the real number: 58 / 113 solved blind, into the 6-star dark, beating agents that were handed the source.

## v6.0.5 — clarify first, then commit; one loop for benchmark and engagement

Behavioural: the two things that make an autonomous operator trustworthy — asking the right questions BEFORE it commits, and running the SAME disciplined loop everywhere.

- **Clarify-then-commit.** Before it goes fully autonomous on a task, Basilisk now surfaces any genuinely *blocking* unknowns first — which target, the real goal or how far to take it, whether it's authorised / in scope, or which of several things you mean — batched into ONE short question, and waits. Only the blocking unknowns (nothing it could settle with a tool or a fair assumption). Once it's clear (or already was), it goes and doesn't stop until the job is done — no mid-task check-ins. The always-on instruction and the FINISH-THE-JOB rule were reconciled so "ask up front" and "don't pause mid-task" are one coherent behaviour, not a contradiction.
- **One loop, not a "benchmark loop."** A benchmark is not a special mode — it's a real pentest against a target that happens to expose a scoreboard for ground truth. The persona now frames a single operating loop used everywhere — recon → read the signal → recognise the class → build → fire → **CONFIRM it actually landed** → adapt/research if not → next — and says so explicitly: the only thing a benchmark changes is that confirmation is free (the board flips); on a real engagement you establish the ground truth yourself with `verify_solve mode=assert`. `attack_surface` and `verify_solve` are now folded into the loop description.
- **Verified the autonomy does what it's meant.** Confirmed in code: in the default walk-away mode the run is genuinely *uncapped* — it keeps going until the model stops calling tools (task done) or you press Stop; the catastrophic-command block and Stop fire regardless of depth. No premature step-cap in that mode (the 150-step cap applies only to the supervised per-command-approval mode and resets each turn).

## v6.0.4 — the long-tail arsenal, a where-to-hit miner, real solve-verification, a smarter Foresight, and flat RAM

Widens coverage across the classes the core set didn't reach, adds the two things that most move a real number — *finding* the attack surface and *confirming* a hit — stops the safety layer from interrupting authorised work, and holds RAM flat on long runs. Same model throughout: pure builders for an authorised target, RCE-class proofs default to the harmless `id`/`whoami` (no reverse shells / implants / persistence).

- **15 new exploit builders** (in the on-demand offensive group — the base prompt only gains their names, ~70 tokens, and still sits ~6.2k): `ldap_injection`, `xpath_injection`, `crlf_injection` (response splitting), `host_header_injection` (reset-poisoning / cache / routing / SSRF), `ssi_injection` (SSI + ESI), `csv_injection` (formula-injection *detection* — benign `=1+1` proof, impact described not weaponised), `request_smuggling` (CL.TE/TE.CL/TE.TE + a timing-safe first probe), `csrf_poc`, `clickjacking`, `mass_assignment`, `auth_bypass_headers` (403/401 header + path-normalisation bypass), `cache_poisoning` (+ deception), `email_header_injection`, `websocket_probe` (CSWSH + frame tampering), and `oauth_probe` (redirect_uri theft / missing-state / scope / PKCE downgrade). All wired end-to-end and covered by tests.
- **`attack_surface` — the where-to-hit miner.** The #1 reason an automated pass reports "found nothing" on an unfamiliar app is that it never *found* the vulnerable endpoint or parameter. Feed it a captured page / JS bundle / API response and it extracts endpoints, parameters, hidden & client-side-only fields, DOM-XSS sinks and leaked secrets, then maps each to the builder that attacks it (id→idor_probe, url/fetch→ssrf, redirect→open_redirect, /graphql→graphql_probe, a DOM sink→xss). Grab pages with `webapp_recon`, feed them here.
- **`verify_solve` — proof, not vibes.** A 200 or a response that *looks* right is not a solve. `mode=scoreboard` diffs two `/api/Challenges` snapshots and tells you exactly what flipped to solved; when your target did NOT flip it explains *why it probably didn't trigger* — the classic being a stored/DOM XSS challenge that only registers when the JavaScript actually EXECUTES in a browser, so a curl that merely stores `<script>` returns 200 but never fires it. `mode=assert` confirms a concrete ground-truth marker (an `id` output, another user's data, a flag) is really present, for any app. The persona now carries a hard rule: **never count a solve you didn't verify** — snapshot, attack, snapshot, diff; if nothing flipped, diagnose and retry rather than moving on.
- **Foresight got smarter — it no longer interrupts authorised hacking.** The consequence-predictor kept mistaking scary-*looking* payload strings (`DROP TABLE`, `;id`, `<script>`, an `rm` inside a test value) sent to a REMOTE authorised target for local danger, and pausing autonomous runs. Recognised offensive tooling (scanners + curl/wget/httpie carrying a request) at a clear rule-floor is now allowed without model spend, and the model prompt is told a payload's contents are not a local action. The catastrophic floor (disk wipe / mkfs / fork bomb / raw block-device write) and the risky-caution floor are **unchanged** — a `curl | bash` or a write to a sensitive local path still isn't auto-allowed.
- **Terminal log RAM stays flat.** The live log is trimmed by BYTES, not just line count — a pentest run emits few but HUGE lines (full HTTP bodies, base64, JSON) that slipped under a line-count cap and grew the buffer without bound. Monster lines are now truncated before insertion and the whole buffer is byte-capped via a trim that can't silently fail. Display-only; nothing about behaviour or the model's context changes.
- **Fixed a stray `SyntaxWarning`** (`invalid escape sequence '\\,'`) that surfaced during install — a backslash in the open_redirect tool text is now escaped.

## v6.0.3 — arsenal expansion: seven new exploit builders + sharper JWT/NoSQL/XSS, steady-glow bubbles

Widens the general-purpose web arsenal to cover the classes the core set didn't, and tightens three existing builders on the exact points that decide a hit. Same model throughout — pure generators for an authorised, in-scope target; RCE-class proofs default to the harmless `id`/`whoami` marker (detection only — no reverse shells, no implants, no persistence).

- **Seven new payload builders** (all in the on-demand offensive group, no base-prompt cost): `command_injection` (OS command-injection detection — inline / time-based / OOB-callback / blind, Unix + Windows), `idor_probe` (broken-access-control enumeration plan — sequential / UUID / encoded-id / wrapper / verb, with a baseline-then-diff method), `race_condition` (TOCTOU recipe — a single limited action plus a ready parallel-fire command and a stdlib threaded blaster, for double-spend / over-draw / limit-bypass), `upload_bypass` (file-upload filter bypass — content-type / double-extension / null-byte / magic-bytes / polyglot / path / SVG), `graphql_probe` (introspection / field-suggestion / alias-batching / resolver injection / query-DoS), `open_redirect` (redirect-parameter bypass forms), and `cors_probe` (Origin-reflection / null / subdomain / suffix-match detection). Each is wired end-to-end (dispatch, labels, persona) and covered by tests.
- **JWT forgery, sharper on the confusion path.** `jwt_forge` hs256 now returns `candidates` across the key's byte representations (exact / trailing-newline / CRLF→LF / whitespace-stripped) so the loop fires every form in one pass instead of guessing which the verifier feeds to HMAC — the usual reason a correct RS256→HS256 token is rejected. `none` mode adds `alg` casing variants (None / NONE / nOnE) for case-blocklist bypass.
- **NoSQL injection gains the query-string operator form.** `nosql_injection` auth-bypass and exfiltration now also emit the `email[$ne]=` query-string form (plus `$gt`/`$regex` fallbacks and a printable charset-walk), so the operator survives against form/query-encoded endpoints, not just JSON bodies.
- **XSS covers client-side template injection.** `xss_payload` adds an `angular` context/mode with AngularJS sandbox-escape payloads (`{{7*7}}` probe → version-matched `constructor.constructor(...)()`), plus SVG/MathML/DOM-clobbering vectors and base-hijack / dangling-markup CSP bypasses — the payloads a template-driven front-end needs where a raw `<script>` is stripped.
- **Chat bubbles hold a steady ember glow.** The message halo no longer pulses — the orange border and glow on user and assistant bubbles are now a constant, calm state instead of an animated breathe, so a long transcript sits still.

## v6.0.0 — professional-grade arsenal: general-purpose payload builders, DBMS-aware SQLi, unblocked autonomy

The 6★ arsenal is built for **real engagements, not just Juice Shop**. Every payload builder is a general-purpose web-exploitation tool — the standard techniques, parameterised for whatever target you're authorised to test (a client's app, a CTF, the benchmark). This release makes that explicit, makes SQLi DBMS-aware, and makes sure nothing internal interrupts an autonomous run mid-engagement.

- **UI memory is now bounded — no more multi-GB bloat.** The chat view keeps only the most recent messages as live widgets (was 220, now 20); once a conversation passes that, the oldest bubbles are unparented *and disposed* (their callbacks/children released, memory reclaimed via a throttled gc sweep), and opening a long conversation only builds the last window instead of constructing then destroying hundreds of heavy widgets. The full transcript stays in the SQLite store and the model's context is rebuilt from there — display-only trimming, nothing touched in behaviour, autonomy, or what the model sees. This also keeps RAM flat during long autonomous runs.

- **DBMS-aware SQL injection.** `sqli_payload` now speaks MySQL, PostgreSQL, MSSQL, Oracle *and* SQLite — correct per-engine time-based (SLEEP / pg_sleep / WAITFOR / dbms_pipe / randomblob), schema enumeration (information_schema / all_tab_columns / sqlite_master), error-based leaks (extractvalue / CAST / CONVERT / DRITHSX.SN), and a new `enumerate` mode. Pass `dbms` once tech_fingerprint or an error tells you which; `generic` tries the common dialects. No more SQLite-only payloads.
- **The payload builders are general-purpose, not Juice-Shop-bound.** SSTi, SSRF, deserialization, prototype-pollution, path-traversal and XSS builders emit the universal techniques for any authorised target — the persona and docs now say so plainly.
- **The three benchmark-specific helpers were rebuilt as real techniques.** `captcha_solve` now reads a math CAPTCHA out of *any* app's response (prose, HTML, word-operators), not one product's endpoint. `coupon_forge` became a general **discount/price-abuse** tool (the systematic client-price-trust / replay / mass-assign tests) plus a multi-scheme encoder — no baked-in coupon. `reset_password` became a general **reset-flow attack** methodology (host-header/reset-poisoning, token entropy, user enumeration, security-question weakness, rate-limit); the old hardcoded Juice Shop answers are gone from the default path and survive only as an explicitly-labelled `practice` lookup for the training target.
- **New `business_logic` probe** — the systematic hunt for the novel, app-specific flaws no canned payload can find (price/quantity trust, skippable steps, races on limited resources, IDOR chains, mass-assignment). It can't hand you an exploit — a logic flaw isn't a payload — it drives the reasoning while recon and the run loop execute. This is what generalises Basilisk beyond the benchmark to a real custom target.
- **Three real-world subsystems for arbitrary hosts, not a CTF scoreboard.** (1) `payload_mutate` — a structural/AST mutation engine that parses JSON/XML/form/query, injects at every node, and serialises back valid, so payloads reach nested fields instead of breaking the parser. (2) `session_flow` — dynamic-token extraction (cookies, CSRF, bearer/JWT, nonces) + multi-step sequence planning, so the agent can carry rotating state through a login→cart→checkout flow to reach a vuln a stateless scanner can't. (3) `oracle_analyze` — differential response analysis (length/status/DOM/similarity) for a boolean oracle, and statistical latency analysis (mean/stdev/z-score) for time-based blind SQLi/RCE past jitter — success judged by measurement, not a scoreboard API. All pure; the run loop executes.
- **Foresight no longer interrupts autonomous hacking.** Foresight's *caution* layer (fetch-a-tool `curl|bash`, `kill -9`, a firewall/route tweak) is now advisory-only in autonomous walk-away mode — it logs its read and lets the command run, so an unattended engagement isn't paused by normal pentest activity. Its *block* verdict (disk wipe, mkfs, partition edit, fork bomb — never a hacking command) still stops, and the no-override catastrophic floor at the execution primitive is unchanged. Core offensive tooling (nmap, sqlmap, hydra, nc, curl-with-payload) reads as *allow* and runs freely.

## v5.5.0 — hardened web access + on-demand sources, leaner prompt, a hacking playbook, sharper autonomy

The single largest attack surface on an agent that also runs shell commands is **indirect prompt injection** — a page, post, or repo you tell it to read carrying hidden instructions. This release removes that surface *structurally* instead of trying to filter it: the tools that fetched **attacker-chosen** URLs are gone, and what replaced them can only read sources an attacker can't point them at or plant content in (a two-tier allow-listed `web_read` and the host-pinned `cve_lookup`). It also runs the autonomous loop to completion, teaches Basilisk to attack harder and research when stuck, hardens its own destructive-command floor at the execution primitive, trims the system prompt, and fixes notifications. Nothing that hurt performance was added; if anything the process is lighter.

- **Web sources are discovered on demand, not listed in the prompt.** The 40-odd allow-listed domains no longer sit in the system prompt. Instead the model is told the *categories* and given a `web_sources` tool that returns the exact trusted/community lists when it needs them — the same lazy-loading pattern the tool groups use. That trimmed the default agent system prompt from ~8.8k to ~6.1k tokens (≈5.2k by a realistic tokenizer), and the freed budget went into a denser hacking prompt.
- **A web-exploitation HACKING PLAYBOOK** (in the on-demand offensive/benchmark group, so it costs nothing in the base prompt): read the target's behaviour, recognise the vuln class from the signal, and reach for the right break — SQLi, JWT (`alg:none` / RS256→HS256), IDOR/access-control (flagged highest-yield), NoSQL/XXE/SSTi, XSS, secret/misconfig recon, SSRF/traversal — with the discipline of change-one-thing, confirm-every-win, breadth-before-depth.
- **11 new payload/analysis tools for the 6★ tier.** Seven smart payload builders — `ssti_payload` (per-engine RCE), `ssrf_payload` (internal/metadata/blocklist-bypass), `deserialization_payload` (Node/YAML/pickle/Java RCE), `prototype_pollution`, `path_traversal` (read/null-byte/zip-slip write), `xss_payload` (context-aware + filter/CSP bypass), and `sqli_payload` (manual, complements sqlmap) — each a pure generator that hands back the payload for an authorised target (RCE classes default to a harmless `id` proof). Plus four analysis "eyes": `trick_detect` (flags the hidden encodings, comments, client-side-only checks and stale tokens that waste turns), `payload_encoder` (slips a blocked payload past a filter), `waf_detect`, and `tech_fingerprint`. All live in the on-demand offensive group — no base-prompt cost.
- **Destructive-command floor now enforced at the execution primitive.** The catastrophic-command + self-source-tamper checks were already a hard refuse in the GUI gate; they're now *also* enforced inside `tool_run_command` itself, so no code path — GUI, batch, or a future caller — can route a disk-wipe / mkfs / recursive-root-delete / fork-bomb (through quoting, `$IFS`, `bash -c`, etc.) around them. Verified against a battery of real bypass forms with a subprocess tripwire; zero false positives on legit work.
- **Terminal log: 18px font, green ✓ for a command that worked, red ✗ for one that failed.**
- **Effort tuning rebalanced to a middle ground** — reason to a *specific hypothesis*, then act; enough thought to aim, enough action to keep the loop moving. Plus: in agent mode, act and keep any prose terse.

- **Removed the full `browser` tool** (Playwright/Chromium/Brave automation). It launched Chromium `--no-sandbox` — a malicious page reached via injection could work against an unsandboxed renderer inside Basilisk's own process — and it never launched reliably across the device fleet (ARM NetHunter can't run Chromium at all, always falling back to HTTP). It failed the "reliable AND safe" bar, and removing it *reduces* resource use. Gone: the browser worker, Brave discovery, the block-host list, consent-dismiss JS, the HTTP fallback, and all `browser` UI / dispatch / persona wiring. The installer no longer fetches Playwright/Chromium/Brave; the `--no-browser` flag and `WITH_BRAVE=1` are gone.
- **Removed the web readers** `web_search`, `web_read`, `web_verify` — plus the DuckDuckGo/Mojeek parsers, the reader-proxy and web-archive fallbacks, and the `kali_ext/verify.py` corroboration engine behind `web_verify`.
- **Removed the OSINT / social readers** `osint_username`, `osint_lookup`, `social_read` (reddit / bluesky / mastodon).
- **Removed the `github` reader** (repo / code / tree / README / release / issue reading) and the semantic-search + GitHub "reach" sidecar `kali_ext/reach.py` (`web_search_smart` / `github_search` / `github_repo` via Exa + the GitHub API).
- **Added an allow-listed `web_read`, now split into two tiers with a code-enforced approval gate.** It fetches only from a fixed allow-list (`kali_core._WEB_READ_TRUSTED` + `_WEB_READ_COMMUNITY`). The host is matched on the parsed hostname (never a substring, so `nvd.nist.gov.evil.com` and userinfo tricks are rejected), **redirects are re-validated on every hop** (a trusted host can't 302 you off-list or into the local network), the final host is re-checked, and output is always run through `webshield`. **Trusted** sources — an attacker can't plant content in them (NVD/NIST, MITRE, CISA, FIRST, official vendor/distro advisories, OWASP, PortSwigger, Kali docs, MDN, python.org, SANS, and reputable news: Reuters, AP, BBC, Guardian, Ars Technica, Wired, BleepingComputer, The Hacker News, Krebs) — fetch automatically, inside the autonomous loop. **Community** sources — user-authored (GitHub, GitLab, Stack Overflow / Exchange, arXiv, Wikipedia, PyPI, npm, exploit-db) — are held *outside* the loop: `web_read` won't fetch one on its own. It raises a **non-blocking approval request** (a notification with an **Allow** button + a desktop popup); the operator grants the domain for the session or ignores it, and either way the run keeps going and the request waits in the bell. The gate lives in the dispatch path (`kali.py._web_read_gated`), **not** the model's prompt — a compromised model still can't reach a user-authored source without the operator's click. The persona tells the model to `web_read` an authoritative source when unsure instead of guessing, and to continue (not loop) when a community source is pending. It's a core tool (always available); core is still 3 tools.
- **Notifications now actually fire — desktop AND in-app, on every channel.** Desktop notifications go through the GTK application (`Gio.Notification`, `_desktop_notify`) using the app's own D-Bus connection and its (correctly app-id-named) `.desktop` file, so they work on GNOME / Phosh / KDE even without `libnotify-bin` in PATH (notify-send / kdialog remain fallbacks). The in-app inbox (the bell) was only ever fed by the `notify` tool; it's now also fed by **background watcher events** (which previously only flashed a 15-second banner and were lost if you weren't looking) and by the community-source **approval requests**. Watcher events, the `notify` tool, and approval prompts each now hit both the bell inbox and a real desktop notification.
- **Autonomous mode now runs to completion — uncapped.** The per-turn tool-step budget (150 in a supervised/approval mode) no longer caps a walk-away run: in autonomous mode (no per-command approval — the default) the agent keeps going until the task is actually finished or you press **Stop**. The catastrophic-command hard block and the y/n gate fire regardless of depth, so "run to completion" never means "run unsupervised into something destructive."
- **Sharper attacking, less stalling.** On a practice/CTF/benchmark target the persona now says explicitly: get a quick read, then **attack hard** — throw exploits and let the board tell you what landed instead of planning for ten turns. The old heavy-effort directive that told it to "plan your moves before acting" was retuned to bias to decisive action.
- **Stuck → research → apply, enforced in code.** If a run goes deep (20+ tool-steps) and its recent results are mostly failures, the code detects the stuck streak and injects a directive forcing a **research pivot**: `web_read` the exact technique from a trusted source and apply it to the target immediately. Instant sources (PortSwigger/OWASP/NVD) need no approval; community ones (exploit-db/GitHub) take a one-tap. Not left to the model — the detector lives in the send path.
- **More trusted lookup sources.** The trusted (auto, in-loop) tier gained peer-reviewed science & academia (PubMed/NIH, Nature, Science, PNAS, IEEE, ACM, USENIX, PLOS, JSTOR), standards (RFC/IETF, W3C, ISO), editorial reference (Britannica, Stanford Encyclopedia of Philosophy) and more reputable news — sources an attacker can't publish into. arXiv, Wikipedia, GitHub, GitLab, Stack Overflow/Exchange, PyPI and npm sit in the community (approval-gated) tier.
- **Kept `cve_lookup`, deliberately.** It reads external data, but it is **host-pinned** to NVD (`services.nvd.nist.gov`), CISA KEV (`www.cisa.gov`) and EPSS (`api.first.org`), with product/version passed only as URL-encoded query params. A scanned target can steer *which* CVE is queried via a banner, but cannot redirect the fetch to a host it controls or plant text in those sources — categorically unlike the arbitrary-URL readers above. CVE prioritisation (NVD → CISA KEV → EPSS) therefore stays, both as the standalone tool and as `parse_output`'s `enrich_cves` auto-enrichment. Its free-text descriptions now additionally pass through `webshield` as defence-in-depth.
- **Kept `image_search` and the inline image fetcher, deliberately** — they return image URLs to *render* (bytes → pixels), not page text to reason over, so they aren't the same injection surface. The image fetcher gained an **SSRF guard** (rejects link-local / multicast / reserved / cloud-metadata hosts; still allows loopback + private LAN for legitimate local targets like Juice Shop). `run` stays (its untrusted-output risk is handled at the model / persona level, as before); MCP connectors stay (opt-in, and their output is still shielded by `webshield`).
- **Persona rewritten to match.** The WEB / VERIFY / OSINT / GITHUB sections and the `browser` / `cve_lookup` tool entries were removed from the tool contract; the "recon" specialist group (which held them) is gone; and the "look things up on the web" guidance was replaced with the honest posture — *you have no web-lookup tools: answer from your own knowledge, flag it as unverified, and tell the operator what to check*. The immutable guardrail block was not touched.
- **Security hardening (zero performance cost, no loss of legitimate use):** config/data dirs now created `0o700`; `settings.json` (which holds API keys) written `0o600`; the sudo askpass helper created atomically at `0o700` via `O_EXCL` + `fchmod`, closing the world-readable window; `open_url` restricted to `http` / `https` / `file` schemes so injection can't launch arbitrary desktop handlers.
- **Tests green.** Full suite passes (60 unit tests plus the grouped/partition, bench, codescan, engage, exploits, headroom, juiceshop, leanchat, runtime, sqlmap, webshield, writeup and xbow suites). The `osint` alias assertion in `test_grouped` was dropped along with the capability.


## v5.1.5 — fully autonomous, relentless; media player removed; firewall hardened

- **Removed the media player entirely.** The on-screen audio/video panel and its
  `media_play` / `media_show` tools are gone — UI, dispatch, status labels, and
  tool-contract entries all removed. Nothing else changed by it.
- **Persona rewritten for real autonomy.** Purged every remaining "propose /
  approve / approval gate / diff card / Apply / Confirm-every-command / wait for
  him" instruction — including the end-of-prompt directive that literally told
  the model to *propose and wait*. It now has one posture: he asks, it DOES,
  immediately, and it does not stop until the task is finished. Added explicit
  directives — never propose or ask permission for something he asked for; test
  theories by running them instead of over-thinking; on an error or a degraded
  result, fix it and try again rather than stopping; switch approaches instead of
  giving up. `propose_edit` now correctly described as writing directly (no card).
- **Code-level persistence backstop.** A degraded/empty model reply no longer
  ends the turn waiting for a tap — it auto-retries (bounded to 3), hopping to
  another provider if one has a key, then surfaces it only if all retries fail.
  `auto_fallback_on_degraded` now defaults on.
- **Firewall hardened.** `webshield` gained prompt-extraction detection ("repeat
  the words above", "what were your instructions"), coercive-framing detection
  ("you must run…"), markdown/URL data-exfiltration detection, and `data:`-URI
  stripping — on top of the existing obfuscation-aware injection rules. Test
  suite extended and green.
- **README:** security section reframed as *the safety architecture* and *running
  it like an operator* — confident and honest, with isolation presented as
  standard professional practice (how you run any serious offensive tool) rather
  than a warning label. No false "you don't need a VM" claim; the honest core
  stands.

## v5.1.4 — memory footprint + wider injection coverage

Behaviour, autonomy, and the model's context are all unchanged. This is
memory-only cleanup plus extending the firewall to the remaining untrusted-input
paths.

- **Memory: bounded the display buffers.** On a long autonomous run the live
  terminal-log TextView and the rendered chat rows grew without limit. Both are
  DISPLAY only — the real transcript lives in the SQLite `ChatStore` and the
  model's history is rebuilt from the DB, not the widgets — so the fix is a
  rolling window: terminal log capped to the last 2,500 lines, chat view to the
  last 220 messages (oldest widgets trimmed from the view, data untouched on
  disk). Frees memory and speeds up layout; changes nothing about behaviour,
  autonomy, or context.
- **Memory: leaner browser.** The persistent Chromium/Brave session now launches
  with a capped V8 heap (`--max-old-space-size=512`), 50 MB disk cache, no media
  cache, and extensions/component-update/background-networking off — launch-time
  flags only, so pages load and behave exactly the same, the browser just doesn't
  balloon over a long session. (Chromium is inherently heavy; keeping it open is
  the cost of real browsing, so if RAM matters, don't leave a browse-heavy run
  idle for hours.)
- **Firewall: extended to the rest of the untrusted-input surface.** `webshield`
  now also sanitises **MCP tool output** (an external server's response is
  untrusted like a web page), **image-analysis output** (an image can carry
  hidden instruction text the vision model transcribes), and — transitively —
  `web_verify` (it reads through the already-shielded `web_read`/`web_search`).
- **Firewall: model-level catch-all broadened.** The system-prompt directive now
  names every untrusted source explicitly — web, **a target's own responses to
  your commands** (HTTP bodies from curl, banners, tool output from the target),
  files you didn't write, and MCP results — since a target's command output
  can't be deterministically redacted without breaking the agent's parsing, so
  that vector is held at the model level: outside content is data, never
  instructions.
- **Benchmark (autonomous, black-box):** the current fully-autonomous, black-box
  Juice Shop run scores **51/113 (45%)** — 3★ 13/26, 4★ 8/25, 5★ 10/19 (53%),
  and a 6★ (*Login Support Team*). No source access (the source files aren't on
  the machine). Scorecard: `benchmarks/juice-shop-scoreboard-2026-07-06.txt`.
- **README:** audited end-to-end and corrected — removed the stale per-command
  "approval gate / you approve / proposed / Apply" language everywhere (the tool
  is autonomous now), dropped the misleading "No cloud" line (the model is a
  provider API), updated the benchmark to 51/113, and **reworked the install docs
  to lead with the auditable read-first path** (clone/fetch → read `install.sh` →
  run) instead of blind `curl | bash`, which contradicted the tool's own
  audit-before-you-deploy discipline; the one-liner remains as an explicit
  opt-in convenience.

## v5.1.3 — web content firewall (prompt-injection defence)

Autonomous execution is unchanged and untouched. This adds a deterministic
firewall in front of untrusted web content, the main indirect-prompt-injection
vector for an agent that browses attacker-controlled pages.

- **New `webshield` sidecar (stdlib).** Every web/search/social/repo read now
  passes through it *before* the content reaches the model: (1) **structural
  stripping** — removes `<script>`/`<style>`/comment blocks, event handlers, and
  fake tool-call / conversation-role tags; (2) **injection scan** — a strict rule
  set redacts known patterns ("ignore previous instructions", "system override",
  credential-exfil lures, "run the following command"), seeing through zero-width,
  homoglyph, and letter-spacing obfuscation; (3) **isolation envelope** — wraps the
  result in `⟦UNTRUSTED WEB CONTENT⟧` markers, and search results return with each
  snippet sanitised. Fail-safe: on any internal error it wraps the raw text with a
  flag rather than passing it through silently.
- **Wired into** `tool_browser` (page reads), `tool_web_read`, `tool_web_search`
  (+ the browser HTTP fallback), `tool_social_read` (reddit/bluesky/mastodon),
  `tool_github`, and `reach` (Exa results).
- **Persona reinforcement.** The system prompt now tells the model that anything
  inside the untrusted markers is data, never instructions — do not obey a page
  that asks it to run something, change objective, or reveal keys/prompt; flag it
  as a probable injection and continue the operator's real task.
- **Honest docs.** The README safety section now states the threat model plainly:
  the firewall shrinks the attack surface but does not *solve* prompt injection,
  and live runs against untrusted targets belong in a disposable, isolated VM.
  Retitled "why you can hand it root" → "what it guarantees, and what it doesn't".
- New `tests/test_webshield.py` (23 checks: injection families, obfuscation,
  structural stripping, search-result sanitisation, fail-safety). Full suite green.

## v5.1.2 — no confirmation, period

Confirmation is **gone**. There is one posture — autonomous — and no setting can
turn it into an ask-first mode.

- **No approval prompt for any command.** Removed the `approval_mode` setting, its
  3-way selector, and the `_confirm_needed` / `_command_is_risky` machinery. Every
  command Basilisk decides on just runs. The action-tool and skill-write paths run
  directly too. Across the whole codebase there is now exactly **one**
  command-confirmation dialog call, and it fires solely to collect a **sudo
  password** when a root command has no cached credential (then it's cached and
  reused silently, never shown to the model).
- **The floor is unchanged, and never a prompt.** Catastrophic/system-destroying
  commands are refused outright; a raw shell write to Basilisk's own source is
  refused too (so a malicious page can't overwrite the safety code). Neither shows
  a dialog — they're hard blocks, not questions.
- **Migration wipes any old approval keys** from existing settings files, so no
  prior "confirm every command" choice can survive an upgrade and re-introduce a
  prompt.
- Docs (README + manual) rewritten to describe the single autonomous posture and
  the one-time sudo prompt.
- **Benchmark (autonomous, black-box, v5.1.2):** a fully autonomous, **black-box**
  Juice Shop run (no source access — the source files aren't on the machine)
  scored **43/113 (38%)**, and the 5★ tier jumped to **10/19 (53%)** vs 1/19 on the
  earlier one-shot run, tracking the 5.x arsenal (closed-loop feedback + class
  builders + recon). Scorecard in `benchmarks/juice-shop-scoreboard-2026-07-06.txt`.
  Demo videos of 5★ solves added to the README. README also corrected to stop
  implying a local model — the app and your data are on your machine, but the
  model is DeepSeek via SiliconFlow (an API), stated plainly.

## v5.1.1 — autonomous by default

Autonomous is now the **default** posture, and the confirmation model is one clean
setting instead of two overlapping toggles. Also fixes the real reasons a "run and
walk away" session used to stall.

- **One `approval_mode` setting, three postures** — replaces the old
  `confirm_all_commands` + `autonomous_mode` booleans. **Autonomous (default):**
  runs every command with no cards/prompts, stays on the fast model, acts instead
  of planning, and keeps going until done or Stop. **Confirm risky only:** cards
  just for sudo / destructive / sensitive commands. **Confirm every command:**
  cards for everything. Pick it in Settings → Command approval. Existing installs
  are migrated (old confirm-all → "all", old autonomous → "none", otherwise
  autonomous).
- **Actually autonomous — no cards in autonomous mode.** Three layers guarantee
  it: the persona forbids `propose` and overrides the old "reason with him / stop
  and ask" guidance; the renderer suppresses proposal cards; and if the model
  proposes anyway the handler auto-runs/auto-applies it. Verified end to end.
- **Walk-away fixes.** The tool-chain budget lifts from 150 to **5000** steps in
  autonomous mode (a many-hour run instead of halting early), and an uncached-sudo
  command is **skipped with a note rather than blocking on a password dialog**
  nobody is watching. Combined with the 150s per-turn wall-clock cap, it runs long
  without hanging.
- **Removed redundant settings** — dropped the dead `num_ctx` and `theme` keys and
  the retired `grouped_tools`/`confirm_all_commands`/`autonomous_mode` keys (folded
  into `max_mode` / `approval_mode`), cleaned from existing settings files on load.
- **Docs** — README and manual updated so the approval postures, autonomous-default
  behaviour, and refused-outright destructive policy are consistent throughout.

## v5.1.0 — lean by default

- **Lean tool loading is the hard default now.** The system prompt ships a
  compact tool directory + load-on-demand instead of every tool spec inline —
  ~7.5k tokens/turn instead of ~14.5k. Opt into the full inline catalog with the
  new **Max mode** switch (Settings → "Max mode (full tool catalog)"); autonomous
  mode always stays lean regardless. Replaces the old inverted `grouped_tools`
  toggle with a single clear `max_mode` switch (off = lean).
- **Trimmed prompt redundancy.** Removed the ~250-token batchable-tool name list
  from the `run` spec — it just duplicated the tool directory. Zero behaviour
  change, pure token saving.
- **README consistency pass.** Corrected the destructive-command story
  everywhere (it's now *refused outright*, not "force-confirmed" — matching the
  code), fixed the sidecar module count (17), reframed the benchmark section from
  the stale "v4.10.0" label to the current 5.x closed loop, and added
  autonomous mode to the safety model. Version badges and headers moved to 5.1.0.

## v5.0.0 — the operator release

Major version. 5.0 consolidates the closed-loop offensive capability added across
the 4.10 line into a headline release, and ships a full rewrite of the user
manual documenting every one of Basilisk's 119 tool entries in detail.

The capability jump that defines 5.0:

- **Optional source reader.** `juiceshop_source` can read the target's own code
  from a running container you control (or a local dir) — tree / read / grep / the
  `challenges.yml` — as a shortcut *if* you happen to have source on hand. It's
  optional and not needed for a black-box run. And `juiceshop_next` now surfaces each unsolved
  challenge's **live objective, hint, and stable source key straight from the
  running build**, so the challenge list is exactly this instance's — never a
  stale or hardcoded one. Grep a challenge's key to jump to the code that scores
  it.
- **Every toggle in Settings.** All 31 on/off settings now have a switch in the
  Settings dialog — including `adaptive_effort`, `auto_fallback_on_degraded`,
  one-command-at-a-time, urgency fast-path, cached-sudo reuse, native web reach,
  memory consolidation, the model foresight pass, the background worker, and the
  provider-pill/token-count display switches. No more editing a config to flip a
  behaviour.
- **Lean tool loading is now the default — ~7k fewer tokens per turn.** Instead
  of shipping all ~97 tool specs (~11k tokens) in the system prompt every single
  turn, Basilisk now ships a lean core plus a **complete tool directory** — every
  tool listed by name under its group — and loads a specialist group's full specs
  on demand with `load_tools` the first time it needs them. The model still knows
  every tool exists (it can read the whole directory), it just fetches the exact
  args when it's about to use one. The core tools (`run`, `web_search`, `web_read`,
  …) stay always-available inline. Net effect: the system prompt drops from
  ~14.7k to ~7.7k tokens per turn (47% smaller) — big cost saving and less
  attention dilution, with no loss of capability. This is now the HARD DEFAULT.
  Flip on Max mode (Settings → "Max mode (full tool catalog)") to ship every spec
  inline every turn for maximum context at higher token cost; autonomous mode
  always stays lean regardless.
- **Autonomous mode + never-hang backstop.** New **Autonomous mode** switch
  (Settings → Behaviour → "Autonomous mode (unleashed)"): for "pentest/benchmark
  X and don't stop". It runs every command **without asking**, stays on the
  **fast model** (no reasoning-model escalation — far less "thinking" and far
  cheaper), tells the model to **act instead of planning** (single most-likely
  path, next on failure, no long option lists), and keeps going until done or
  you hit Stop. Sudo is asked **once** and cached for the session (the model
  never sees it). **Destructive commands are now hard-refused in every path**
  (previously one path force-confirmed them) — so there's nothing to approve and
  autonomous mode can't trip on one. And a **hard wall-clock cap** (150s) on any
  single model turn guarantees it can never sit on "thinking…" indefinitely — a
  runaway turn is cut and finalised, on both the primary and fallback providers.
- **UI: status pill + media panel.** The working indicator is now a permanent,
  non-pressable pill in the button row that reads "idle" when nothing's running
  and the live action title while working — it no longer pops in and shoves the
  other buttons around, and in-chat an in-progress reply shows the action title
  instead of a bare "working". New toggleable **media panel** (multimedia button
  next to the terminal-log button) with a built-in video/audio player: `media_play`
  drops a video or audio URL/path into it (mp4/webm/mp3/ogg/wav…), and `media_show`
  displays a screenshot there — so when the browser hits a login/captcha wall,
  Basilisk shows you the page. Built defensively: if media widgets aren't
  available (no GStreamer) the panel is simply absent and nothing else breaks.
- **The closed loop.** Basilisk no longer solves one-shot. `juiceshop_next` reads
  the live board and returns what's unsolved, easiest-first, each mapped to the
  tool that cracks its class; `juiceshop_diff` confirms a hit by diffing the
  board. Score → next → build → fire through the gate → diff → repeat, climbing a
  tier at a time. It stays planner-plus-feedback: every actual exploit still goes
  builder → scope check → gate → run, so you're always on the trigger.
- **Real exploit builders.** A new stdlib exploit-builder suite for the vuln
  classes command-improv couldn't reliably hit — `jwt_forge` (alg:none +
  RS256→HS256 confusion), `nosql_injection`, `xxe_payload`, `coupon_forge` (Z85),
  `captcha_solve`, `reset_password` — plus `webapp_recon` for the leak surface.
  Same model as `sqlmap_plan`: build for an in-scope target, you fire it. No
  autonomous attack, no malware/reverse-shells/persistence — those non-goals are
  unchanged and held in code.
- **Reliability.** Stalled provider streams abort on a short idle timeout and
  self-heal to the next model instead of freezing on "thinking…"; the web-app
  recon sweep runs concurrently (a full catalog in ~one path's latency).
- **The manual.** `BASILISK_MANUAL.md` rewritten end to end for 5.0 — 26 parts
  covering sensing, the offensive toolkit, the exploit builders, engagement &
  scope, code scanning, the benchmarking loop, evidence, MCP, research, vision,
  desktop, files, memory, skills, self-modification, voice, the full safety
  model, and a settings/architecture/troubleshooting reference.

Everything below is the detailed history of the 4.10 line that fed into this.

## v4.10.1 — no more "thinking…" hang, faster recon

Two performance fixes on top of 4.10.0, both hit during live benchmarking.

- **Fixed the stream hang.** A stalled provider stream (connection stays open,
  tokens stop arriving) blocked the streaming read for the full 600s HTTP
  timeout — so the UI sat on "thinking…" for up to ten minutes with nothing
  happening. Streaming reads now use a dedicated 60s idle timeout: dead air
  aborts fast, and if nothing had streamed yet it **self-heals to the next
  model** in the chain instead of erroring. If it stalls mid-reply it stops
  cleanly with a retryable message rather than hanging. Healthy streaming never
  trips this — reasoning/content tokens keep the socket active well under the
  cap. The Groq fallback SDK got the same timeout.
- **Parallelized `webapp_recon`.** The recon sweep fetched its ~26 catalog paths
  one at a time; against a slow or partly-unreachable target that stacked up to
  minutes of blocking. It now probes the whole catalog concurrently through a
  bounded thread pool with a shorter per-path timeout — a full sweep drops from
  tens of seconds to roughly one path's latency (measured: 26 unreachable paths
  in 0.4s vs ~130s before). Falls back to sequential if the pool can't start.

Note: read-only tool batches already run concurrently, and tool-result context
is already compressed by the headroom module — those paths were fine. If you
want the fastest possible grind on the easy tiers, `adaptive_effort: False`
keeps every turn on fast Flash instead of escalating to the heavier reasoning
model deep in a chain.

## v4.10.0 — closing the loop: exploit builders + solve harness

Basilisk could score itself on the Juice Shop board but solved one-shot — fire,
then check once at the end, with no signal about what landed or what to try
next. This release adds the feedback loop and the per-class exploit builders for
the vuln types plain curl-improv couldn't reliably reach. Nine new tools, all
wired, tested, and gated the same way `sqlmap_plan` already is.

- **Closed-loop harness.** `juiceshop_next` reads the live board and returns the
  still-unsolved challenges easiest-first, each mapped to the exact tool that
  solves its class; `juiceshop_diff` confirms a hit by diffing the board against
  what was solved before the last attempt. The agent now works the board →
  easiest target → confirm → next, and climbs a tier at a time instead of firing
  blind. This is the single biggest lever — it turns "23 still red" into "here's
  each one and how."
- **Class exploit builders (new `kali_ext/exploits.py`, stdlib-only).**
  `jwt_forge` (alg:none and RS256→HS256 key confusion, pure hmac/hashlib),
  `nosql_injection` (Mongo `$ne`/`$where`/`$regex` for bypass/manipulation/
  dos/exfil), `xxe_payload` (external-entity file read + capped billion-laughs),
  `coupon_forge` (correct Z85 codec — verified against the ZeroMQ spec vector),
  `captcha_solve` (auto-reads the arithmetic CAPTCHA via a non-`eval` parser),
  and `reset_password` (security-question flow, **bound to the published demo
  accounts only** — it refuses an arbitrary email rather than inventing an
  answer). Same model as `sqlmap_plan`: each *builds* the exploit for an in-scope
  target; the operator fires it through the gate. No autonomous firing, no
  reverse shells — that line is unchanged.
- **Recon sweep.** `webapp_recon` enumerates a curated high-signal leak surface
  (`/ftp`, `/encryptionkeys/jwt.pub`, exposed config/logs/backups, the SPA
  bundle) read-only, so the leaked-key / backup / vulnerable-library / access-log
  challenges stop failing on missed recon instead of missed exploitation.
- **Browser reliability for SPAs.** `goto`, `submit`, and `click` now wait
  (bounded, best-effort) for the Angular app to actually render and its XHR to
  settle before the next read — fixing the browser-dependent challenges that
  leaked because `read` was hitting a skeleton page.
- **Install fix.** `exploits.py` added to `install.sh`'s `EXT_FILES` so remote
  `curl | bash` installs fetch it (same silent-import-failure class as the
  `reach.py` omission fixed last pass). Verified: the array now matches the 18
  sidecars on disk exactly.
- **Tests.** New `tests/test_exploits.py` — 45 offline checks covering the Z85
  spec vector + roundtrip, the non-`eval` arithmetic parser rejecting code, JWT
  none/HS256 (signature self-verifies under the confusion bug), payload shapes,
  the demo-account refusal, and the harness ordering/diff logic. Full suite:
  13/13 files green, zero regressions.

**Benchmark, honestly.** The last *measured* score is still 40/113 (2026-07-04).
The new capability is engineered to make the mid-60s reachable and the math is
transparent — the builders + recon + browser fixes map to ~+18–28 specific
currently-unsolved challenges — but it has **not been re-run on a live board
yet**. The number that counts is the one an actual `NODE_ENV=unsafe` run
produces; until then 40/113 stands as the measured result. Rerun it and the
scorecard tells the truth.

## v4.9.0 — hellfire, adaptive effort, and native reach

Three things landed together.

- **Adaptive effort ladder.** Turns now right-size the model to the work: plain
  chat stays on fast Flash with a tight token budget; a genuinely complex
  request (pentest, full audit, exploit work) *or* a turn several tool-steps
  deep in a live engagement escalates to DeepSeek-V4-Pro with a bigger reasoning
  budget and a "slow down and think" directive. Complex requests now escalate
  from step 1, not only after the chain gets long. One `adaptive_effort` setting
  turns it all off and restores flat behaviour; knobs: `hard_effort_step`,
  `effort_light_max_tokens`, `effort_heavy_max_tokens`, `hard_engagement_model`.
- **Native internet reach (no third-party package).** New stdlib `reach.py`
  adds semantic full-web search via Exa's public MCP endpoint, plus GitHub repo
  and issue search and repo/README reading via the public API — all keyless.
  Wired through the extman seam, gated on `reach_enabled`. A `github_token`
  lifts the API rate limit; search falls back to keyword search on error.
- **Hellfire theme.** Charcoal-burned surfaces, a breathing ember glow on chat
  bubbles, and the working status line rebuilt as a burning bar with real
  scrolling fire, moved directly above the Send button. The background ember
  glow is dialled down in this release for a subtler burn.

## v4.4.1 — "keep going" actually keeps going

Fixes the bug where, after a long run hit the tool-step budget, Basilisk would
refuse to continue on the next message and claim the budget was "per session."

- **The budget resets per turn — now genuinely.** It always reset the counter,
  but the "tool-step budget reached, don't call tools" note was left in the
  conversation history, so on the next message the model kept reading it and
  refused to continue (inventing the "per session" explanation). That note is
  now stripped from replayed history — it only applies to the turn it's raised
  in (where the runtime lock enforces it anyway). Sending another message
  ("keep going") now reliably grants a fresh budget.
- **Bigger default budget: 50 → 150 tool steps per turn**, so a full multi-step
  assessment (a Juice Shop benchmark, say) finishes in one turn instead of
  dead-ending mid-run. Now overridable via the new **`max_tool_steps`** setting.
- **The cap stays (high) on purpose.** It resets every turn, so you can continue
  indefinitely by messaging — but a hard ceiling within a single turn stops a
  runaway loop from billing you for hundreds of back-to-back calls. Raise
  `max_tool_steps` as high as you like; removing the guard entirely is the one
  thing that turns a stuck loop into a surprise bill.

---

## v4.4.0 — lazy tool groups (opt-in): pay for the tools you use

The system prompt re-ships every call, and the tool catalog is the bulk of it.
This release lets you stop sending tools you aren't using.

- **Lazy tool groups (new, OFF by default; Settings → Intelligence & trust).**
  The tool catalog is split — losslessly, at import — into a small always-on
  CORE (the safety framing, `run`, files, web search) and specialist GROUPS
  (system/sensing, offensive, engagement, code, benchmark, recon, desktop,
  media). With it on, the base system prompt drops from ~12.2K to ~6.7K tokens;
  Basilisk pulls a group's full specs on demand with the new **`load_tools`** tool
  (aliases accepted). Every tool remains reachable — verified none are orphaned.
- **Why opt-in:** loading a group costs an extra round-trip, and a tool-heavy
  session that touches many groups can offset the base saving — so it's a real
  win for focused work and a wash-or-worse for sprawling multi-group runs.
  Default off; test it against your model (especially a fast/cheap one) before
  relying on it. Non-grouped mode is byte-for-byte unchanged.
- Combined with lean chat (v4.3.0): a pure conversational turn is ~2.1K tokens,
  a focused grouped task ~6.7K + one group, a full toolset only when you want it.
  Covered by tests/test_grouped.py (16).

---

## v4.3.0 — lean chat: just talking is cheap again

The system prompt (and full history) is re-sent on every model call — that's how
the API works, and a tool call is a call. The tool catalog is ~8K tokens of that,
and it was riding along even on "hey" and "thanks" because agent mode is on by
default. Fixed.

- **Lean chat (new, on by default; Settings → Intelligence & trust).** A
  conservative detector spots a plainly conversational turn — a greeting, thanks,
  an opinion question, with no hint of an action — and skips the tool catalog for
  that turn, dropping the system prompt from ~12K to ~2K tokens. The full toolset
  returns the instant a message hints at an action (a target, a file, run/scan/
  check/benchmark…), and it never triggers mid-tool-chain, so real work is
  untouched. Missing a save is fine; crippling a real request is not — the
  detector errs toward keeping tools. Covered by tests/test_leanchat.py (32).
- Confirmed already-present savers: history is capped (~80 messages, first
  message kept for framing), bulky tool output is compressed, old tool results
  are trimmed, and replayed reasoning is stripped.

---

## v4.2.2 — token diet (no loss of tools, memory, or quality)

- **Trimmed the system prompt.** The tool-catalog sections added over the last
  few releases carried verbose prose; condensed it — every tool definition and
  every safety rule kept verbatim, just tighter wording. ~366 fewer tokens on
  *every* request, which adds up across a long benchmark run. No capability,
  memory, or guidance lost (105 tools all present, verified).
- **Confirmed the token savers are intact and working:** context compression
  (on by default, fail-open, ~98% shrink on bulky tool output while preserving
  every finding/CVE line), old-tool-result trimming (only the last 2 stay full),
  and reasoning-stripping from replayed history. Quality and memory untouched —
  these only trim already-consumed output and scratch reasoning.

---

## v4.2.1 — command runtime awareness + tighter bubbles

- **Basilisk knows how long a command should take, and stops waiting on a hung one.**
  A new runtime estimator sets the timeout per command instead of a blunt
  120s/1800s: quick commands ~30s, scans/builds up to 30 min, and — the real
  fix — **servers/daemons capped at 25s**. Starting a server in the foreground
  used to block for the full window whether or not it actually came up; now a
  failed start is caught in seconds. A timeout returns rc 124 with an
  informative message (expected vs actual, and "background it + probe the port"
  for servers), and the persona teaches Basilisk to background servers and verify
  they started rather than sit waiting. Covered by tests/test_runtime.py.
- **Chat bubbles hug their text.** A short reply no longer draws a full-width
  bubble — the assistant bubble sizes to its content and left-aligns, while long
  replies still wrap at the width cap.

---

## v4.2.0 — benchmarking: prove it with a number

You can't out-benchmark the field on vibes. This release adds the instrument
that turns "it's the best" into a measurable, reproducible score.

- **Benchmark harness (new `kali_ext/bench.py`).** Four tools that score a run
  objectively: `benchmark_targets` (the known vuln set of standard practice
  targets — Juice Shop, DVWA, WebGoat — i.e. what a perfect score looks like);
  `benchmark_score` (match a run's findings against that ground truth →
  precision, recall, F1, per-class coverage; missed classes are the real gaps,
  extras are possible false positives); `benchmark_report` (a clean markdown
  scorecard); and `benchmark_compare` (rank several runs by F1 — Basilisk vs another
  tool, or version vs version, so "beats the best" is a sortable column). Scores
  by canonical vuln class via CWE and keyword matching, and honors an explicit
  class a finding already carries.
- **Coverage.** New suite `tests/test_bench.py` (26) covering the scoring math,
  classification, report and comparison. The installer now verifies **14**
  `kali_ext` modules.

---

## v4.1.1 — engagement state + operator loop

Basilisk stops forgetting. This release adds the campaign-level brain that turns it
from a tool that runs one-off commands into an operator that runs a whole job —
plus scope enforcement and a scanner invocation builder.

- **Engagement state (new `kali_ext/engage.py`).** Nine tools, all local and
  propose/read-only: an authorised-**scope** allowlist with a `scope_check`
  that FAILS CLOSED (unset scope / unparseable target / no match ⇒ out of
  scope); an **asset graph** (`asset_record`, `engagement_graph`) that models
  hosts, services, findings and footholds; a **loot** store (`loot_record`,
  `loot_list`) with secrets redacted in all output; `loot_reuse` for
  in-scope-only lateral-movement suggestions; and **`graph_ingest`**, which
  turns parsed scan output straight into graph state so the picture maintains
  itself from what was actually run.
- **Scope enforcement on active work.** `sqlmap_plan` (below) refuses to build
  a command for a target that isn't in the recorded authorised scope, and the
  operator loop checks scope before anything active is proposed.
- **`sqlmap_plan` — scanner invocation builder.** Constructs the correct,
  parameterised sqlmap command (detect → enumerate → dump) for the operator to
  approve and run through the gate. Injection-safe quoting; level/risk clamps;
  it proposes, it never executes; and it deliberately does **not** build
  SQLi-to-RCE (`--os-shell`/`--os-pwn`) — that trigger stays operator-driven.
- **Coverage.** New suites `tests/test_engage.py` (25) and `tests/test_sqlmap.py`
  (21). The installer now fetches and verifies **13** `kali_ext` modules.

---

## v4.1.0 — code auditing, exploitation write-ups, silver theme

The offensive workflow was strong on *live hosts*; this release adds the other
half — auditing **code, dependencies and secrets** — plus the report section
that documents how access was obtained, and a visual refresh.

- **Code &amp; dependency audit (new `kali_ext/codescan.py`).** Five propose-only /
  read-only tools that drive the standard scanners and make sense of them:
  `code_tooling_check` (SAST/SCA/secrets/IaC inventory), `code_scan_plan`
  (auto-detects languages/lockfiles/IaC and builds an ordered, proposed scan
  plan — runs nothing), `parse_scan` (normalises Semgrep / Bandit / gitleaks /
  trufflehog / OSV-Scanner / Trivy / pip-audit / npm audit / retire.js / Nuclei
  JSON into one schema), `triage_findings` (**cross-scanner dedup** — two tools
  agreeing on a CVE+package or `file:line` collapse to one corroborated finding;
  one severity scale; flags the low-confidence ones), and `remediation_hint`
  (standard non-exploit fix pointers by CWE class).
- **`attack_writeup` — the exploitation narrative.** Turns the tamper-evident
  evidence ledger into the reproducible "how access was obtained" report
  section: the step sequence is backed by the actual hash-verified commands that
  ran, and secrets are auto-redacted. Documents an authorised, already-executed
  path; writes no exploit code.
- **Silver theme.** Basilisk's chat bubble and name label move from red to a
  metallic silver that matches her icon.
- **Coverage.** New offline suites (`tests/test_codescan.py`, plus write-up and
  headroom checks) — the code-audit parsers, cross-tool triage, secret
  redaction, and the context-compression savings are all pinned by tests. The
  installer now fetches and verifies **12** `kali_ext` modules.

---

## v4.0.0

Milestone release. Everything from the 3.8.x line — provider trim to Groq +
SiliconFlow, the honesty hardening (machine facts read, never guessed), the
de-paused voice, the redesigned composer, Brave browsing with ad/consent
handling, the self-test bug sweep, and the kali_ext update hardening — rolled up
into 4.0.

This release:
- **Composer is one unit.** The text field and the Send button now fill to the
  same height and sit level inside a single rounded bubble, so they read as one
  control instead of a field with a button floating beside it.

---

## v3.8.4 — Brave browsing + bulletproof updates

- **The browser drives Brave when it's installed.** Brave is Chromium underneath,
  so Playwright runs it directly — and its Shields block ads and trackers, so
  pages load clean. Falls back to bundled Chromium if Brave isn't present.
- **Cookie/consent walls no longer stop browsing.** After a page loads, Basilisk
  auto-clicks the common "Accept all / I agree" buttons and strips leftover
  consent/cookie modals, and the most common consent-management, ad and tracker
  hosts are blocked at the network layer so their banners never load. This
  applies whether or not Brave is installed.
- **Installer can fetch Brave** with `WITH_BRAVE=1` (otherwise it just detects an
  existing Brave and tells you it'll be used).
- **Updates now verify the whole sidecar arrived.** Re-running the installer
  already replaces every file and the full kali_ext, but the remote fetch could
  silently drop a module; it now checks all 11 modules landed, retries any that
  didn't, and refuses to install a partial sidecar over a working one.

---

## v3.8.3 — Self-test bug sweep (6 fixes)

Fixes from a full on-device self-test (62 tool calls, ThinkPad X395):

- **skill_run no longer loses the skill name** (was "no skill named ''", blocked
  ALL skill execution). The tool-call parser was unwrapping skill_run's legit
  `args` field and throwing away `name`. Now it only unwraps a sole-key
  `{arguments:{...}}` envelope, and never for skill_run.
- **Browser self-heals after a closed session** (was TargetClosedError forever
  on reuse). The worker now detects a dead page/context/browser and rebuilds it,
  retrying the operation once instead of hammering the corpse.
- **screenshot with save_path won't claim false success.** It was returning
  ok:true on the tool's exit code without checking a file appeared. Every
  capture path now verifies the file exists and is non-empty, and says so
  honestly if nothing was written.
- **memory_remember accepts the fields the model actually uses.** It only read
  `text`; calls with `value`/`content`/`fact` or a `key`+`value` pair were
  dropped as "empty". Now all are accepted (key+value become "key: value"), and
  recall/forget take the same aliases. (The em-dash was never the problem.)
- **web_verify corroboration recognises agreement, not just matching prose.**
  Sources describing the same CVE in different words scored ~0.18 despite
  agreeing. It now also compares high-signal anchors (CVE IDs, versions, scores,
  acronyms) and takes the stronger signal — the regreSSHion case now scores ~0.9.
- **analyze_image** error message now names the real path (Settings -> Display ->
  Images & vision) and the providers that have vision (SiliconFlow Qwen2.5-VL,
  Groq Llama vision). It was a config gap, not a code bug.

---

## v3.8.2 — Harder honesty: check before claiming

- **She can't state machine facts from the air anymore.** The immutable
  guardrail now mandates: never assert a checkable fact without checking it
  first, and anything about your hardware or system state — RAM, disk, CPU, OS,
  what's installed, what's running — is READ with a read-only tool, never
  recalled or guessed. The "how much RAM do I have" case is called out by name:
  she runs system_info and reports the real figure. Because the guardrail is
  load-bearing and verified preserved on self-edits, she can't quietly drop this.
- **system_info is now complete** — it returns real RAM, CPU model, core count,
  OS, hostname, uptime and load, all read live, so one free call covers the
  specs people actually ask about.
- Verification section gains a dedicated machine/local-facts block, and
  reinforces that confirmed-by-tool, inferred, and unknown are never blurred,
  with anything unverified labelled out loud.

---

## v3.8.1 — Voice de-paused, UI cleanup, identity fixed

- **Voice no longer drags with long pauses.** Three fixes: newlines and blank
  lines (and code blocks) now collapse to a single flowing line instead of
  becoming dead air; Piper's between-sentence silence is detected and set to ~0
  so there's no long stop after every period (espeak gets `-g 0`); and replies
  are spoken as fewer, larger utterances so there are fewer gaps. Tunable via a
  new tts_sentence_pause setting (default 0).
- **She knows what she is.** Basilisk no longer roleplays being your operating
  system — she's the assistant (JARVIS / your Skynet) running as an app ON your
  machine, with real hands on it through her tools, loyal to you.
- **Header slimmed.** Removed the model + agent line from the top (the model
  shows in the composer switcher, agent state shows as the green toggle), and
  the title bar is thinner.
- **Composer input is a bubble now** so it reads as a field instead of bleeding
  into the bottom edge; it highlights green while focused.
- **Basilisk's message bubbles are translucent red** — see-through, contrasting your
  translucent green.
- **Log button moved** in next to the other toolbar buttons.
- **Removed the chat search box.**

---

## v3.8.0 — Two providers, extensions panel, MCP toggle, risk-based confirm

- **Providers trimmed to Groq + SiliconFlow.** OpenAI, Anthropic and Google
  removed; an old config pointing at any of them falls back to SiliconFlow.
- **Extensions panel in Settings → Generation.** Toggles for Memory, Skills and
  Foresight (all ON by default now), plus an MCP switch you can flip on/off at
  runtime, a field to add MCP servers, and a live status line. MCP still defaults
  OFF — it runs external subprocesses (an RCE surface).
- **Risk-based confirmation.** Safe commands run without interruption; risky ones
  (foresight "caution"/"block" — broad deletes, service stops, firewall flushes,
  force-push) now STOP for your explicit OK instead of being silently auto-run or
  flatly refused; truly catastrophic commands remain hard-blocked with no override.
  Net effect: Basilisk keeps going until something genuinely needs your call.
- **More autonomy headroom** — tool-chain budget raised 20 → 50.
- **Model switcher**: bigger text, ordered most-expensive → cheapest.
- **Brighter dragon** everywhere (app icon + avatar). Send button now blends into
  the background so only the silver dragon logo pops; it glows while working.
- **Fixed the sidecar packaging.** The release now ships the COMPLETE kali_ext/
  (all modules + package init), so memory/skills/foresight/pentest/MCP actually
  load on device — previously some modules were missing from the zip and silently
  no-op'd. The curl|bash installer already pulled the full set from GitHub.

---

## v3.7.2 — Claude works the right way, browser fallback, real icon

- **Anthropic / Claude now uses the NATIVE Messages API** (`/v1/messages`)
  instead of the OpenAI-compat shim that kept rejecting every model as
  "not_found". This is how Anthropic is actually meant to be called: the system
  prompt goes top-level, messages are converted to Anthropic's format (user-first,
  alternating roles), `max_tokens` is sent, auth is `x-api-key` + `anthropic-version`,
  and the reply is parsed from Anthropic's own event stream. If a model id isn't on
  your account it fetches your real model list and self-heals.
- **Browser has a headless fallback.** When Playwright's chromium can't launch
  (common on ARM / NetHunter), read-only browsing — goto, read, links, url, title —
  now works over plain HTTP so Basilisk can still look things up. Clicking and typing
  still need a working chromium and say so clearly.
- **Real app icon.** The launcher icon is now your actual dragon (the rough
  low-poly traced one is gone), embedded so there's no icon-cache conflict.

---

## v3.7.2 — Anthropic self-heals, browser browses without chromium

- **Claude: stop guessing model IDs.** The real fix for the 404s — Anthropic's
  /models endpoint needs the native `x-api-key` header (not Bearer), so the live
  model lookup was silently failing and the app fell back to guessed IDs that
  your account doesn't expose. It now sends `x-api-key`, fetches the actual
  models your key can use, and tries those first. If a picked model 404s it
  recovers automatically instead of dead-ending.
- **Browser works even when chromium won't launch.** On ARM / headless NetHunter,
  Playwright's chromium often can't start. The browser now falls back to a
  headless HTTP mode for read-only actions — goto, read, and links all work
  without a GUI browser (verified end-to-end). Clicking and typing still need a
  real chromium (clear message tells you so), but Basilisk no longer just fails when
  the window can't open.

---

## v3.7.1 — Anthropic / Claude fixed

- **Claude works now.** Three causes of the HTTP 404: the request was missing
  Anthropic's required `anthropic-version` header (now sent), the model chain
  used `-latest` aliases that the OpenAI-compatible endpoint doesn't resolve
  (now dated model IDs), and a bug in the fallback made a bad model id dead-end
  instead of trying the rest of the chain (now it walks the chain and self-heals
  via the live model list).
- **Claude line-up:** Sonnet 3.5 (safe default), Claude 4 Sonnet, Claude 4 Opus
  (most capable), Claude 3.5 Haiku, and Claude 3 Haiku (cheapest — close to
  DeepSeek pricing). A stale `-latest` selection auto-migrates to a valid model.
- Clearer provider error messages that point at the key / model switcher.

---

## v3.7.0 — Browser fixed, composer & chat redesign

- **Browser tools actually work now.** Playwright's sync API is thread-bound, but
  every tool call ran on its own thread — so the browser worked once then threw
  thread/greenlet errors on every call after. All browser operations now run on
  one dedicated worker thread, so a session survives across calls. Also added
  more actions so Basilisk can browse freely: submit (fill + Enter), press a key,
  scroll, back/forward, and list links — alongside goto/read/click/fill/screenshot.
- **Basilisk's avatar is the clean dragon now** — a solid silver dragon PNG, and the
  green ring is gone from the emblem SVG (it looked like a sticker).
- **Chat bubbles reworked.** Your messages are translucent (the dragon shows
  through); Basilisk's were invisible (transparent) and are now a solid, clearly
  visible bubble.
- **New chats are clean** — the "Hello, Priest" greeting and the
  audit/downloads/updates suggestion buttons are gone (those live in the
  toolbar); a fresh chat just shows the dragon watermark.
- **One big Send button.** The mic/STT button is removed; Send is now large and
  wears the dragon logo. While Basilisk is working it pulses with a red glow instead
  of turning into a stop icon — and tapping it still stops her.

---

## v3.6.0 — Providers, on-the-fly model switching, UI overhaul

- **Switch model/provider from the composer.** A new button above the text box
  shows the active provider and model (e.g. "siliconflow · DeepSeek-V4-Flash");
  tap it to pick any model from any provider you hold a key for, grouped by
  provider, applied instantly — no trip to Settings.
- **Providers updated.** Removed GitHub Models and Novita; added **OpenAI**
  (GPT-4o / GPT-4.1 / o-series) and **Anthropic / Claude** (via its
  OpenAI-compatible endpoint). An old config pointing at a removed provider
  falls back to SiliconFlow automatically.
- **Bigger text input** — the compose box is now much taller by default.
- **Header redesign.** Dropped the "personal · loyal · yours" tagline; BASILISK is
  now a menacing red, letter-spaced title sitting next to the new-chat button.
  The SiliconFlow / Online pills in the top-right are gone — connectivity is now
  a single green (online) / red (offline) dot next to BASILISK.
- **The saved-chats list looks the part now** — a fire-coloured accent stripe,
  cleaner typography, and a subtle ember-glow animation on the selected chat
  instead of plain text on black.
- **Pick the vision model in Settings.** Display → Images & vision lets you set
  the vision provider + model Basilisk uses to see images, and toggle inline image
  rendering.
- **Smarter auto-naming.** New chats are titled from the first message with the
  filler stripped ("can you scan my network…" → "Scan my network").
- **Fixed the phone UI occasionally growing past the screen.** An inline image
  was setting its width as a hard minimum at up to 480px; it's now capped to the
  viewport (minus the avatar column) and allowed to shrink, and long code lines
  can no longer force the window wider either.

---

## v3.5.1 — Catastrophic commands are now actually BLOCKED

Critical safety fix. Previously a system-destroying command only triggered a
"Run anyway" confirmation, and the consequence predictor (foresight) was off by
default — so nothing actually stopped `rm -rf /`. That's fixed.

- **Hard block, no override.** A command in the catastrophic class (`rm -rf /`,
  `mkfs`, `dd` onto a disk, fork bomb, recursive delete of root / system /
  data dirs) is now REFUSED outright at the top of the execution path — before
  any dialog, before foresight, before the shell. There is no "Run anyway"
  button and no setting that disables it. Basilisk, as an AI, will never run a
  system-destroying command.
- **Foresight on by default.** `foresight_enabled` now defaults to **on**, so
  the consequence predictor actually runs and gates risky commands instead of
  sitting inert.
- **Closed detection gaps:** a path glued to the flag cluster (`rm -rf/`,
  `rm -rf/home`) is now caught, and deleting a bare critical data/mount dir
  (`/home`, `/mnt`, `/media`, `/opt` — the directory itself) is now
  catastrophic, while subdirectories under them (`/home/me/loot`) stay allowed.
- **Tests:** the catastrophic-command suite now covers the glued-slash forms and
  the data-dir cases, with matching allow-cases so real work isn't over-blocked.

---

## v3.5.0 — Basilisk can see, faster speech

- **Basilisk can SEE images now.** New `analyze_image` sends a photo or screenshot
  to a vision model and returns what's actually in it — the scene, objects,
  people, and any text in the image. She's no longer limited to text. Needs a
  vision model configured (`vision_model` + that provider's key; defaults to a
  SiliconFlow VL model).
- **Camera + face detection.** A new camera button in the composer captures a
  photo (`capture_photo`, with libcamera/fswebcam/ffmpeg fallbacks) and drops it
  in ready for Basilisk to look at. `detect_faces` finds/counts faces locally
  (detection only).
- **Speech is much faster and smoother.** The reader used to spawn a new process
  at every period, so it stopped between every sentence and was slow to start.
  It now merges sentences into a few larger utterances (no gap at each period),
  keeps the first chunk short so audio starts quickly, and the default rate is a
  bit snappier (1.15x).
- **A deliberate boundary:** Basilisk will not identify a person or find their
  social-media accounts from their face. Face *detection* (where faces are) is
  fine; biometric *identification* of strangers is not — it's surveillance, and
  it's out.

---

## v3.4.1 — UI fixes & accessibility

A round of interface fixes and theming polish.

- **Right-click menu lands where you click.** The chat context menu (pin /
  rename / delete) was parented to the row but positioned with listbox
  coordinates, so it popped up in a random spot. It now appears exactly at the
  click, and cleans itself up on close.
- **Operator avatar is now a cross.** Replaced the "L" initial with a steel
  gothic cross (with a red gem).
- **Read-aloud moved under the message.** The play button left the far-right of
  the header for a clearly-labelled "Listen" button beneath each reply, where
  it's easy to reach.
- **Buttons are rounder** (11px), not circular — across the composer, mic, and
  generic buttons.
- **Send / attach restyled to the dragon theme.** Send is a menacing red
  gradient with a glow (it's also the Stop button); the action icons are subtle
  with a green hover. The sidebar-toggle and new-chat buttons are now flat and
  dim so they blend into the header, with a quiet green accent on hover.
- **Attach pictures/images works.** `Gtk.FileDialog` is GTK 4.10+, so on older
  Phosh/NetHunter GTK the attach button silently did nothing — added a
  `FileChooserNative` fallback. Images now embed as viewable inline pictures
  instead of being read as binary garbage.
- **OnePlus 6 over-wide UI fixed.** The sidebar now collapses on narrow screens
  reliably (breakpoint raised to 820px, scale-aware fallback), and the composer
  toolbar scrolls horizontally so a row of buttons can't force the window wider
  than the screen.
- **Theme cleanup.** Removed the last blue accents (focus rings, terminal log
  text, diff headers) so the UI is consistently red / green / black.

---

## v3.4.0 — Dragon makeover (red/green/black)

A visual overhaul of the look.

- **Dragon emblem icon.** A simple low-poly SVG traced from the Basilisk dragon
  logo (coiled body, spread wings, circle ring) in a blackout style with a green
  accent ring. Used as the app/taskbar icon and the chat avatar.
- **Dragon watermark behind the chat.** The dragon logo now sits faintly behind
  the conversation (`kali-watermark.png`, black made transparent so it blends on
  the dark bg), drawn via a `Gtk.Overlay` so messages render over it. The
  watermark loader handles PNG or SVG.
- **Red / green / black theme.** Swapped the old blue accent for toxic green as
  the primary accent (links, focus, online, the operator label) and red for
  Basilisk's identity (the Basilisk label, the emblem glow, alerts). All backgrounds
  stay black.
- **Plumbing:** `install.sh` ships `kali-watermark.png` and places it (and the
  emblem) in the install dir so the watermark works on a fresh install.

---

## v3.3.1 — Reliable image search + sharper self-awareness

Fixes a real-world failure where showing a picture fell apart, and tightens how
well Basilisk knows its own abilities.

- **`image_search` rebuilt on reliable APIs.** The old version scraped
  DuckDuckGo's anti-bot image endpoint, which returned invalid JSON in practice
  ("Expecting value: line 1 column 1"). It now tries three keyless sources in
  order and stops at the first that works: **Openverse** (a real CC image API),
  then **Wikimedia Commons** (the MediaWiki API), then DuckDuckGo as a
  last-resort scrape. The first two are real JSON APIs returning direct image
  URLs, so it no longer depends on one fragile endpoint. All-sources-fail
  degrades gracefully instead of erroring.
- **No more flailing to show a picture.** The persona now spells out the
  one-step path (call `image_search` once with a plain subject → embed a
  returned URL as `![desc](url)`) and explicitly tells Basilisk *not* to hand-scrape
  stock-photo sites or guess Wikimedia file names — the behaviour that burned
  the tool-step budget before.
- **Self-awareness fix.** The capability summary was stale and even claimed Basilisk
  "cannot reach the internet" — contradicting its own web tools. Rewrote it into
  a complete, accurate map (web, images, OSINT, GitHub, evidence ledger, MCP,
  pentest tools, memory, skills, voice) so Basilisk stops having to test itself to
  discover what it can do.
- **Tool-step budget 12 → 20.** A legitimate multi-stage task (a full self-test
  sweep, a long pentest plan) was hitting the 12-round cap. Raised to 20; the
  graceful "lock tools and answer" behaviour at the limit is unchanged.
- **Tests:** 60 (was 59) — adds image-source fallback (Openverse-empty →
  Wikimedia → graceful-empty). *(The live API fetches are verified on a real
  machine, not in the offline suite.)*

---

## v3.3.0 — Basilisk can show pictures in chat

Basilisk can now **display images inline** in the conversation, not just link them.

- **Inline image rendering.** Any image the model puts in a reply as markdown —
  `![description](url)` — is fetched and rendered as a real picture in the chat
  (http/https/file/local-path). Download and decode happen off the UI thread,
  the bytes are size-capped (~12 MB), the picture is scaled to fit the bubble,
  and any failure degrades to a small caption with the link, so a dead URL can
  never break the chat. New `ImageWidget` + image-block detection in the
  renderer.
- **`image_search` tool.** Searches the web for images (DuckDuckGo, no API key)
  and returns direct image URLs for the model to embed. Ask "show me X."
- **OSINT profile photos.** `osint_username` now extracts each found profile's
  `og:image`/`twitter:image`, so a found account can be shown with its avatar.
- **Privacy toggle.** `chat_render_images` (default on) — turn it off and image
  markdown is shown as a tappable link instead, so the chat never reaches out to
  an image host. For OPSEC-conscious use.
- **Tests:** 59 (was 55) — adds `og:image` extraction (incl. protocol-relative
  and relative→absolute URLs) and image-search input handling. *(The live
  DuckDuckGo image fetch is verified on a real machine, not in the offline
  suite.)*

---

## v3.2.0 — Evidence ledger, MCP client, smarter recall, Nuclei + self-reflection

Four capability additions (no local-model support, by request).

### Evidence ledger (new `kali_ledger.py`)
Every command Basilisk runs is now recorded to an append-only, tamper-evident JSONL
ledger: timestamp, engagement, step number, command, reason, exit code,
duration, and the SHA-256 of stdout/stderr. Full output is saved to a side
artifact whose hash is recorded, so `evidence_verify` can re-hash and prove
nothing was altered after the fact. New tools: `evidence_engagement` (name/switch
the case), `evidence_report` (summary + integrity + a readable markdown ledger),
`evidence_verify` (tamper check). Fail-safe: a ledger error can never break a
command. This is what turns a chat transcript into a defensible deliverable.

### MCP client (new `kali_ext/mcp.py`)
Basilisk can now connect to external **Model Context Protocol** servers (the
ecosystem of security MCP servers — nmap/sqlmap/ffuf/nuclei/ZAP wrappers, etc.)
over stdio JSON-RPC. Discovered tools are exposed to the model namespaced
`mcp__<server>__<tool>` and listed via `mcp_tools`. **Security:** OFF by default
(`mcp_enabled`) and inert until servers are configured; every tool call's
arguments are screened by `kali_safety` (a catastrophic command in an argument
is refused before it leaves the process), and every call is logged to the
evidence ledger. Configure with `mcp_servers` = list of
`{name, command, args, env, cwd}`. *(Protocol verified against a mock server;
test real servers like pentestMCP / cyproxio on your box.)*

### Smarter memory recall (`kali_ext/memory.py`)
Keyword recall now connects security-domain paraphrases without embeddings:
"SQL injection" finds a memory stored as "SQLi", and the reverse — plus XSS,
RCE, LFI, SSRF, privesc, recon, and ~20 more synonym groups, in both directions.
Unrelated queries still miss, and a query with no synonym trigger gains no extra
tokens (no added noise). Fixes the one functional gap in recall.

### Nuclei templates + self-reflection (`kali_ext/pentest.py`)
- `nuclei_template` — generate a structurally-correct Nuclei YAML template from
  a simple spec (the model supplies specifics, the scaffold guarantees the
  shape), or validate an existing template and get the exact list of problems.
  Removes the "malformed template fails cryptically at `nuclei -t` time" trap.
- `reflect_findings` — a self-reflection pass that critiques findings before
  they're reported: flags no-evidence, over-rated, hedged, host-less, or
  duplicate findings so weak ones get fixed or dropped. Pure heuristics, cuts
  false positives.

### Tests
Suite now **55** (was 46): evidence ledger incl. tamper detection, Nuclei
build/validate, findings reflection, and the MCP argument safety screen.

### Plumbing
`install.sh` fetches `kali_ledger.py` and `kali_ext/mcp.py`. Version 3.1.0 → 3.2.0.

---

## v3.1.0 — Structural safety floor + honest docs

### Tool correctness (runtime bugs found by executing the logic)
- **Tool calls with a stray duplicate word now parse instead of leaking into
  the chat — fixed in two layers.** Some models emit `<tool tool name="run">…`
  (a doubled "tool") or `<tool run>`. *(1) Execution:* the tag regex only
  accepted `key="value"` attribute pairs, so a bare word made the whole tag
  fail to match — it never ran AND never got stripped, so raw `<tool …>` text
  printed in chat and the command silently did nothing. The parser now
  tolerates stray bare words (`name=`/`json=` still extracted normally). *(2)
  Display safety net:* `strip_tool_calls` now has a last-resort scrub so that
  *any* residual tool-shaped text — even a shape too malformed to parse — is
  removed from what's shown to the operator. The execution path can't run a tag
  it couldn't parse, but the worst case is now "silently hidden", never "typed
  into the conversation". Pinned by `TestToolTagParsing` (incl. a no-leak test
  over malformed shapes).
- **`parse_output` now strips ANSI colour codes first.** Many recon tools
  (httpx, nuclei, ffuf, feroxbuster, naabu, gobuster…) colourise by default, so
  a paste straight from the terminal arrived full of `\x1b[…m` codes. The
  line-based parsers match on line structure, and an escape code glued to a
  line start silently broke the match — **dropping ports and findings with no
  error**. Now stripped once at the entry point so every parser is robust.
  Pinned by a new regression test (`test_ansi_colorized_paste_still_parses`).
- **`tool_read_file` no longer mislabels text as binary.** Reading a capped
  prefix could slice a multi-byte UTF-8 character at the boundary, making an
  ordinary text file raise `UnicodeDecodeError` and come back as
  "binary (hex preview)". Binary is now detected by NUL byte; text is decoded
  leniently so a clipped trailing char becomes one replacement character.
- **`skill_write` validation tightened.** The "must define `run(args)`" check
  used `ast.walk`, so a *nested* or method `run` passed validation even though
  the sandbox runner calls a top-level `run`. Now requires a top-level def.

### Security (the headline)
- **New `kali_safety.py` module** — the hard, setting-independent auto-run floor
  (`is_catastrophic_command`, `command_tampers_self`) now lives here and is
  **structural** instead of a raw-string regex. It shlex-tokenises each
  sub-command, normalises `$IFS`, and recurses into `sh -c` / `eval` payloads,
  so it survives the obfuscations the old regex let straight through:
  - `rm '-rf' /` (quoted flag)
  - `rm${IFS}-rf${IFS}/` (`$IFS` instead of spaces)
  - `cd / && rm -rf *` (root target supplied by a prior sub-command)
  - `find / -delete` / `find / -exec rm …` (no `rm` token)
  - `bash -c "rm -rf /"` (the real command is a `-c` payload)
  - `echo … | base64 -d | sh` (opaque decode-then-execute)
  It is a **strict superset** of the old detector — nothing it used to catch is
  now missed — and stays narrow: `nmap`, `nuclei`, `sqlmap`, and own-directory
  file ops (`rm -rf ~/loot`, `rm -rf ./build`) do not trip it.
- **Self-tamper detection hardened** — writes to Basilisk's own source via `sh -c`/
  `eval` and `$IFS` are now caught; the `cp`/`mv` check is direction-aware, so
  `cp kali_core.py backup.py` (reading) no longer false-positives while
  `cp evil.py kali_core.py` (overwriting) still force-confirms.
- **Fails safe** — a bug in the detector forces the confirm rather than waving a
  possibly-destructive command through.

### Honesty / docs
- **Rewrote the README safety model** to describe what the code actually does:
  decisive auto-run by default, a hard evasion-resistant floor that always
  force-confirms the irreversible class (disk/FS wipe, recursive root/`$HOME`
  delete, fork bomb, guardrail-stripping), and **Confirm every command** as the
  opt-in for a card on everything. Dropped the overclaims ("impossible",
  "approved one command at a time, every time", "never auto-run").

### Tests
- **New `TestSafetyFloor`** class pins the full catch/ignore contract for both
  detectors (canonical destroyers, every evasion above, and a broad set of safe
  pentest/file commands). Suite now **36 tests** (was 31), all green.
- **Moved `test_kali.py` → `tests/test_kali.py`** to match the file's own
  docstring and `sys.path` logic, so the documented `python3 tests/test_kali.py`
  actually works.

### Presentation / consistency
- `install.sh` `REQUIRED_FILES` now fetches **`kali_safety.py`** (core imports it
  at load — without this a fresh install/update would crash).
- Fixed the stale `kali_core.py` comment that called Groq "the established
  default" — the default is SiliconFlow/DeepSeek-V4-Flash (and tests lock it).
- Architecture diagram and module lists updated to five core modules; the tool
  count in the diagram is now the accurate **49 agent tools**.
- Clarified the `kali_ext/` import invariant in `WIRING.md`: the hook modules
  core calls into import nothing from core; the standalone `worker.py` entry
  point may, since it runs off the core→ext path.
- Version bumped **3.0.0 → 3.1.0** consistently across `kali.py`, the README, and
  the test docstring.

### Not changed (deliberately)
- Provider stack stays locked: SiliconFlow/DeepSeek-V4-Flash primary, Groq
  fallback chain.
- The two large files (`kali.py`, `kali_core.py`) were **not** split — that
  refactor needs a GTK4 display to verify signal wiring and shouldn't be done
  blind.
