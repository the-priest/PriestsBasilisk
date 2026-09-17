# v1.2.0.8

**Native function-calling done the way DeepSeek actually specifies — whole, not
half. Plus the mic button back, Camoufox driven from its on-disk binary, and a
follow-through gate so a search always becomes a read.**

**Native tool-calling, done right.** The earlier attempt sent the OpenAI `tools`
schema but still fed the conversation *history* back as `<tool_result>` TEXT — so
the model saw two conflicting channels (schema says "call", history says
"narrate") and did the worst thing: it wrote "let me read the page" turn after
turn and never emitted the call. That is now fixed at the cause. When tools are
in play, the **entire conversation the model sees is structured**: every prior
tool call is an `assistant.tool_calls` message and every result a `role:"tool"`
message with the matching `tool_call_id` (`structure_tool_messages`). One
consistent channel, exactly as DeepSeek's own harness drives the V4/V4.1 family.

The transform is **valid by construction** — an assistant call is only
structured when the exact tool-result messages it needs immediately follow it;
anything that can't be paired (an in-flight call, a bare system note) is left as
text — so the request can never contain a dangling `tool_calls` or an orphan
`role:"tool"`, the two shapes an API rejects. The text `<tool>` protocol stays
wired as an automatic fallback and a provider that rejects the field
strips-and-retries onto plain text, so it is the native path with a floor under
it. It's back ON by default.

**A follow-through gate so a search always becomes a read.** Even with the
channel fixed, an open-ended "give me news" could leave the model with a page of
search *results* (sites, not stories). If the reply intends a fetch, a search
already ran, and the model emits no call, the host now **follows the top result
itself** (decoding the real URL out of the results page) — the exact step the
model kept saying it would take and didn't. Bounded so it advances the read
without becoming its own loop.

**The mic button is back.** It had been removed from the composer while all the
record→transcribe machinery stayed, so the feature existed with no way to reach
it. Tap to record, tap to stop → the clip is transcribed (SiliconFlow SenseVoice
or Groq Whisper, per Settings → Voice) and dropped into the composer; with
Auto-send on it sends straight away. Pinned by a test so it can't vanish again.

**Camoufox works from its on-disk binary.** The reported case — the browser
present in `~/.cache/camoufox` but `import camoufox` returning `None`, so
`web_read` fell back to plain HTTP — is fixed by a new `camoufox-bin` engine that
drives that binary directly through Playwright. `browser_status` reports the
path, the diagnostic names the one-line fix, and `install.sh` sets up the browser
stack on a fresh box.

**Security fix:** the `.gitignore` on the pushed repo was missing the
`settings.json` exclusion (which holds API keys). Restored — keys can't be
committed.

**5,025 assertions across 82 suites**, zero red. GUARDRAIL byte-identical.

---

# v1.2.0.6

**Claude-coloured dark theme, the Camoufox browser fixed, and the code-writing
loop killed at the root.**

**The GUI is Claude-coloured now.** The accent had migrated red -> blue -> grey
and a token-only change last round left the *thirty-two* hardcoded grey accent
hexes (`#45484a`, `#292a2b`, and their `rgba(69,72,74,…)` glows, 90 uses in all)
untouched in the custom widgets — which is exactly why it "still looked black and
grey." Those are now Claude's clay/coral: `#d97757` carries every highlight
(focus, links, switches, selection, glows, the ready-dot), suggested-action
buttons fill with `#c15f3c` on white, and the near-black neutrals are warmed a
touch toward charcoal. Danger red, warning amber and success green are semantic
and were left untouched. Verified: parses under real GTK 4.14, ASCII-only, and
pinned by a new `test_theme.py` so it can't silently revert.

**Camoufox works when the browser is on disk but the package isn't.** The
reported case: `~/.cache/camoufox` held the whole Firefox tree (`camoufox-bin`,
`libxul.so`, …) but `import camoufox` returned `None`, so `web_read` dropped to
plain HTTP. New **`camoufox-bin`** engine tier drives that on-disk binary
directly through Playwright's `executable_path` — the browser you already have,
no package import needed. It sits second in the ladder
(camoufox -> camoufox-bin -> firefox -> chromium -> HTTP), `browser_status` now
reports the binary path, and the diagnostic tells you the one-line fix
(`pip install playwright` alone is enough to drive it). `install.sh` now sets up
playwright + camoufox so a fresh box has a real browser on day one.

**The code-writing loop ("propose_edit did not render (unparseable args)") is
fixed at the root.** When a big file was crammed into one call, the token cap cut
the JSON off mid-file and the call was unparseable — and the old correction told
the model to *re-send it as a single call*, so it re-sent the same giant blob and
truncated again, forever. Now the host reads the cut reason it already has and,
either way, **mandates small append chunks** — a concrete `write_file`
create-then-append recipe, with the target path recovered even from the
truncated call, so a call that only ever carries ~40 lines can never be cut off.
The persona was rewritten to match: the self-contradicting "content is the WHOLE
file, never a fragment" line (the thing that caused the giant blobs) is gone,
replaced by a chunk-first rule with a hard ~40-line ceiling.

**4,994 assertions across 82 suites**, zero red. New suites: `test_theme.py`;
new coverage in `test_browsersearch.py` (camoufox-bin) and `test_truncwrite.py`
(the chunk-steering correction). GUARDRAIL byte-identical.

---

# v1.2.0.5

**Three models, a real loop-termination bug fixed, and an aggressive debug pass.**

**The catalogue is now three models, on purpose.** The operator cut it to the
three he actually runs: **DeepSeek-V4.1-Flash** (the new default and the best of
them), **DeepSeek-V4-Flash** (the measured 87/113 build, immediate fallback),
and **GLM-5.3-Flash** (the one-click alternative). Everything else is gone from
the picker and the fallback chain. `hard_engagement_model` ships empty — there
is no heavier sibling to escalate to now, so a heavy turn just deepens the
reasoning dial (on GLM) or keeps the bigger token budget (on DeepSeek, which
steers with `enable_thinking`, not a depth dial). The vision picker and the
default vision model point at GLM-5.3-Flash, the one kept model that takes
images. The live-catalogue recovery still exists, so a hand-typed id that 404s
still self-heals.

**The bug that made it "full of bugs": the degraded-reply loop didn't stop when
it said it did.** When the model returned empty several times (a provider
hiccup, a blocked fetch — the "cant even fetch news" case), the retries-exhausted
branch wrote "I couldn't get a usable reply — tap send to try again" and then
**fell through** into the force-answer path: it orphaned that message, re-locked
tools, and kicked up to two more turns — each re-entering the degraded block with
a **fresh** three-retry budget. A three-retry ceiling was really about eleven
round-trips, and the app printed "giving up" while visibly carrying on. It now
finishes the turn and returns where it says it does. And both degraded dead-ends
write a visible, honest message into the reply instead of leaving a blank bubble.

**Aggressive debug pass** (a subagent audited every changed path and ran the full
suite):

- Native-tools rejection now degrades on **422** as well as 400 (some
  OpenAI-compatible servers reject an unsupported `tools` field with 422), so it
  still falls back to the text protocol instead of dying.
- The repeat-guard content fingerprint now also covers `workspace_replace`'s
  alias argument names (`new_str`/`old_str`/`replace`/`find`), closing the last
  gap where three distinct alias-form edits of one file could false-block.
- Confirmed no dangling runtime reference to any removed model, no double
  dispatch across the structured + text tool channels, and that the
  reasoning-stream recovery never fires on an ordinary prose reply.

**4,965 assertions across 81 suites**, zero red. GUARDRAIL byte-identical.

---

# v1.2.0.4

**Native function-calling — driving the model the way DeepSeek says to, and the
way Claude Code / opencode / DeepSeek's own app do.**

v1.2.0.3 stopped the empty-reply loop. This makes the model *good* at tool use
instead of merely surviving it. DeepSeek's V4/V4.1 family is trained for the
OpenAI `tools` flow: the harness declares the tools as function schemas in the
request, and the model replies with structured `tool_calls`. Basilisk had only
ever used a text `<tool>` protocol and never sent a `tools` array — so the model
was guessing a convention instead of doing what it was trained for, which is
where a lot of the "dumb shit on screen" came from.

Now Basilisk sends a real `tools` schema, **built from the same system prompt
the model is about to read** — so it lists exactly the tools the model was told
about (the leashed and armed tool sets track automatically) and can never
advertise a phantom one. Each tool's parameters and types are lifted from the
persona's own example JSON; the `//` comment becomes the description.

Three properties make this safe rather than a gamble:

- **The text protocol is still the floor.** The persona still documents it, the
  canonicaliser still parses it, and the dispatcher's argument aliasing still
  absorbs any drift — so nothing regresses if the model mixes channels (which
  DeepSeek's own tracker notes it sometimes does).
- **A provider that rejects `tools` degrades automatically.** A 400 naming the
  tools field strips it, retries the *same* model on the text protocol, and
  remembers not to send it again that session — the model is never abandoned
  over an unsupported field.
- **It is a setting.** `native_tool_calls` is on by default and off in one flip;
  sidecar completions never send tools.

Combined with v1.2.0.3's structured-`tool_calls` reader and reasoning-stream
recovery, the model is now driven, and read back, exactly the way the reference
harnesses do it.

**GUI:** the brief was "pro coding-terminal vibes, not a black-and-white movie —
change colour and texture a bit, keep the structure." So the v1.2.0.3 serif
title-card experiment is reverted, a **muted phosphor-green terminal accent**
(desaturated, restrained to highlights — focus, links, switches, the ready-dot)
replaces the flat grey, and the near-black surfaces get a **faint top-to-bottom
gradient** for depth instead of a flat fill. Danger red and warning amber are
untouched. Verified: parses clean under real GTK 4.14, ASCII-only bytes literal.

**4,961 assertions across 81 suites**, zero red. New suite:
`test_nativetools.py` (schema build, payload wiring, the reject-and-degrade
path, the router gates). GUARDRAIL byte-identical.

---

# v1.2.0.3

**The one where V4.1-Flash actually builds the game. From a live build the
operator filmed failing the same way over and over — every fault reproduced
first, then fixed at the root.**

The symptom was brutal and repeatable: ask V4.1-Flash to build a small game and
it "thought for 50,000 characters and said nothing", forever. Three separate
mechanisms were behind it.

## 1. Thinking was ON for exactly the turns that couldn't afford it

The DeepSeek V4/V4.1-Flash family default to a **thinking** mode. In an agentic
tool loop that is the wrong default — the model spends its whole `max_tokens`
budget reasoning and streams back an **empty** answer: no prose, no tool call.
The host saw "reasoning present, content empty", called it degraded, and
retried — which changes nothing, so it looped.

The toggle that turns thinking off (`enable_thinking:false`) existed, but it was
only ever sent on a **light** turn that had *also* opted into `fast_light_turns`.
A build is a **standard/heavy** turn, so on every build the toggle was never
sent. **Now thinking is off by default on any model that has a `think_off`**
(the whole DeepSeek Flash family), on *every* turn — which is how DeepSeek's own
agent harness runs them for tool use. `deepseek_thinking:true` turns it back on
for anyone who wants it. GLM-5.3-Flash is untouched: its reasoning has no
switch, so it keeps steering on `reasoning_effort`.

## 2. A tool call that arrives in the reasoning stream is no longer lost

Two independent backstops, because a provider can still route a call into the
reasoning channel:

- **Structured `delta.tool_calls` are read.** DeepSeek's harness consumes tool
  calls from the OpenAI-style structured channel; so do we now. The streamed
  fragments are reassembled and rendered into the **same** `<tool …>` text every
  other dialect is folded to, so one parser and one dispatcher handle all of
  them — even when `content` came back empty.
- **The reasoning stream is re-parsed.** If a turn ends with an empty answer and
  no call, the host runs the *same* canonicaliser over the captured reasoning; a
  real call the model emitted while thinking is recovered and dispatched instead
  of feeding the degraded-retry loop.

## 3. The repeat guard stopped refusing legitimate re-writes

Writing `index.html`, improving it, and writing it again is three **different**
actions — but the guard labelled them all `write_file: index.html` and refused
the third ("already run 2× — not running it again"), which is the block the
operator filmed. The label for a content-writing tool now carries a **fingerprint
of the content**, so iterating on one file never false-blocks, while a
byte-identical re-write (which genuinely tells you nothing new) still collapses
to one label and is still caught. `run` is deliberately unchanged — its command
*is* its label, so `pytest`/`pytest`/`pytest` still blocks.

## 4. Persona: the build mistakes that cost a whole run

Standing rules added for building an app or game from scratch: a build script
must **never read its own output** (that is what doubled `index.html`); **data
belongs in its own file**, never only inside the page you are about to rewrite
(that is how the champion/item table got destroyed); and **guard every lookup**
so the first frame doesn't crash on `cannot read x of undefined`.

## Numbers

**4,936 assertions across 80 suites**, zero red. One new suite:
`test_structcalls.py` (the structured-call fold, the reasoning recovery, and the
repeat-guard fingerprint, end to end). `test_effort.py` was rewritten around the
new think-off default. The immutable `GUARDRAIL` block is byte-identical.

---

# v1.2.0.2

**Theme: neutral graphite. He said the blue was boring — dark gray and black now.**

The obsidian-glass theme was a cool blue band (a hue migration off the original
red at v1.1.1.0). This neutralises the whole blue/cyan/indigo band to gray while
preserving every lightness and alpha value, so the glass structure — the lit
edges, the depth, the one-hairline composure — is untouched; only the tint is
gone. Applied identically to three places so nothing is left blue:

- **The stylesheet** (462 hex + 620 rgba values in the ASCII bytes literal).
- **The brand + app PNGs** (emblem, wordmark, avatar, watermark, every button)
  — per-pixel, so the emblem's glow is silver on black instead of blue.
- **The 4 blue SVGs and the 11 embedded base64 button PNGs** in
  `basilisk_btn_art.py`, so a remote-fetch install with no assets dir gets the
  gray buttons too — the on-disk and embedded art stay in lockstep, same rule
  as the v1.1.1.0 migration.

**Semantic colour is untouched:** danger red (`#e5484d`) and warning amber
(`#f0a500`) sit outside the neutralised band and stay loud — red still means
danger and nothing else. Verified: 0 saturated blue hexes left in the CSS, CSS
parses clean under real GTK 4.14, ASCII-only bytes literal intact, GUARDRAIL
byte-identical.

Everything below is the v1.2.0.1 write-up, unchanged.

---

# v1.2.0.1

**Follow-up to v1.2.0.0, from a real "build me a game" run that failed. Five
fixes, all reproduced first.**

The operator asked it to build a MOBA at `~/Documents/moba` and watched it fail
in the terminal log. Every failure was real and traced to one of these:

1. **Long files were written with a `run` heredoc, and heredocs truncate.** The
   model did `cat > index.html << EOF …` inside a `run` call; the reply hit the
   token cap mid-file, the JSON string was left unterminated, and the call
   collapsed to `{"_raw": …}` — refused with a useless "missing argument
   ['command']" that sent it to re-issue the same giant heredoc. Fixed at the
   root: **`write_file` now writes long files in sections** even for `.py` (a
   mid-sequence chunk that doesn't parse yet is accepted and reports
   `parses:false` instead of being refused — the old refusal is what made
   sectioned Python impossible and pushed the model to heredocs), it
   **creates parent directories** so no `mkdir -p` dance, and an undecodable
   `run` call now says plainly *the reply was cut off — use write_file in
   append sections, never a heredoc.* The persona says the same.

2. **"make me a moba game" classified as a QUESTION, not a task** — so no work
   mode, no plan, and the checklist/objectives he expected never appeared. The
   intent classifier had no vocabulary for the things he builds. Now
   `make/build/create/code/design/develop me a game|app|website|clone|bot|…`
   is a build task, with zero new false positives on "what is a moba" /
   "make a sandwich" / "make a case for X".

3. **A SiliconFlow HTTP 500 killed the turn.** `{"code":50500,"message":
   "Request failed: Unknown error.","data":null}` is a provider-side hiccup,
   but 500 wasn't in the transient-retry set (only 502/503 were), so the turn
   died with a red toast mid-build. The whole **5xx range now walks the
   fallback chain**, so a single-model 500 self-heals onto the fallback and a
   provider-wide outage still surfaces the real error instead of spinning.
   *(To answer the operator's question directly: that 500 was SiliconFlow's
   fault, not the app's — but the app should survive it, and now does.)*

4. **DeepSeek-V4.1-Flash added and made the default**, at the operator's
   instruction — DeepSeek's Sep-2026 refresh of the V4-Flash line, confirmed
   live on SiliconFlow (`deepseek-ai/DeepSeek-V4.1-Flash`). Same vendor, same
   tool-call dialect, so every V4 behaviour (the DSML/native canonicaliser,
   `enable_thinking`, the sampling profile) applies unchanged — verified. The
   benchmarked **V4-Flash is the immediate fallback**, its 87/113 provenance
   intact and *not* restated as V4.1's, and the backend recovers from a wrong
   model id (a 404 refetches the live catalogue), so even a slug mismatch
   degrades to V4-Flash rather than dying. Existing installs keep their saved
   model; only fresh installs move.

5. **GLM-5.3-Flash parity re-verified** — 90/90 of its dedicated suite green;
   V4.1 correctly does *not* use GLM's reasoning-effort dial, and GLM correctly
   still does.

Everything below is the v1.2.0.0 write-up, unchanged.

---

# v1.2.0.0

**The coding-assistant release. A real browser, real search, a task ledger the
turn loop actually reads, and the repo tools a long job needs.**

The brief was three reported faults and one direction:

> "it still sometimes stops when it's supposed to keep working and it still
> doesn't stop when it's supposed to and sends two answers" — and make leashed
> mode a proper coding and general assistant.

All three faults turned out to be the same missing mechanism.

---

## 1. The turn loop stopped guessing

Nothing in the app ever knew **what the model set out to do**, so "is this turn
finished?" could only be answered by reading the reply's prose. A prose reader
is always one phrasing away from being wrong — and it was wrong in *both*
directions at once:

* `"I've fixed two of the five files. The remaining three need the same
  treatment."` — the stall detector says no stall (correctly: nothing was
  announced), the conclusion detector says no conclusion. Nothing pushed, the
  turn **ended**, three files untouched.
* A complete, finished answer that happened to mention a next step got nudged,
  and the model answered the same question again.

**The task ledger** (`basilisk_ext/tasks.py`) replaces the reading with state
the app owns. The model declares a plan; every item has a status; and the
turn-ending decision becomes arithmetic:

| ledger state | what the host does |
|---|---|
| any item **open** or **doing** | the turn **will not end** — it is pushed back to work, bounded at 6 pushes |
| every item **closed** (done / blocked / dropped) | the turn **ends**, and every other push is suppressed for the rest of the request |

`blocked` and `dropped` both **close** an item and both demand a reason. A
ledger whose only exit is `done` is an infinite loop with extra steps.

The plan renders as a live checklist in the activity feed, ticking off as it
works.

## 2. "Not done until it passes" now includes *what the check said*

v1.1.3.0 made the turn **run** the verifier. Nothing made it care about the
result — so "edit, verify, tests are red, write an honest paragraph about the
tests being red, end the turn" was a perfectly reachable path, and it left the
repo worse than it started while reading as diligence.

`workspace_verify` returns a structured verdict, so the new gate reads a fact:
a turn ending on `broke` non-empty is pushed back to fix it. The verdict is
captured in `_feed_tool_result` — the one choke point every tool result passes
through — not from the model's account of it.

## 3. The second answer

Both end-of-turn gates fire at the same moment: a **complete reply** has been
written, no tool call was emitted, the turn was about to end. The gate then
runs a tool anyway and hands back the result.

From the model's side that is indistinguishable from an ordinary mid-research
tool result, so it does the sensible thing and writes the answer. The answer it
already wrote. Two complete answers, one question — exactly as reported.

The gates were right to fire. What was missing was the one fact only the host
has: **the first answer is already on screen.** Gate-forced continuations now
say so, and ask for the delta — a line confirming the check, or a correction if
the check changed the answer.

## 4. A real browser behind `web_read`

`web_read` was one urllib GET: no JavaScript, a bot-shaped TLS fingerprint, a
static User-Agent. A JS-rendered page came back as an empty shell and an
anti-bot edge came back as a challenge page with **HTTP 200** on it. Neither
looks like a failure from the inside, which is what made them expensive — the
model read "blank" and either guessed or re-fetched until the repeat guard
stopped it.

`web_read` now renders in **Camoufox** (a hardened Firefox), falling back to
Playwright Firefox, then Chromium, then plain HTTP — and the result **says
which reader served it**, so "this page was empty" can be told from "this page
was not really read".

The SSRF floor is **injected, not reimplemented**: `browser.fetch` refuses to
run without the host's own predicate, and applies it to every redirect hop and
every subresource the page requests, aborting and *reporting* each one. There
is one definition of "private address" in the tree.

> **The trap that would have shipped:** Playwright's sync API pins every object
> to the thread that created it, and Basilisk dispatches each tool call on a
> fresh daemon thread. Launch-once-and-reuse works for the first `web_read` of
> a session and dies on the second. Reproduced, then fixed with a dedicated
> owner thread; five sequential fresh-thread calls and six concurrent ones now
> all pass, with the browser staying warm (0.9s cold, 0.55s warm).

## 5. Search that behaves like research

There was no search tool — search was a hand-written DuckDuckGo URL, one query,
one engine, read the first plausible link. Four things go wrong with that, and
the worst is silent: when two sources conflict, reading only one makes the
conflict invisible.

* **`web_research`** — one call: several phrasings, several independent
  engines, top results from **different domains**, read, plus an `agreement`
  block naming the values more than one source carried. It does not decide
  what is true; it reports that four sources say 7.95 and one says 7.94.
* **`web_search`** — merged, de-duplicated links ranked by cross-engine
  agreement rather than any one engine's order.
* **`browser_status`** — which reader is serving `web_read`, for when a page
  comes back empty.

Both route their fetches through the same gated reader as a direct `web_read`.

## 6. Repo work that does not hit a ceiling

Three ceilings, one symptom ("long code keeps failing"):

* **`workspace_edits`** — many exact edits to one file in one call,
  **all-or-nothing**. A rename across nine call sites is one call, not nine
  round-trips. If any anchor is missing or ambiguous, or the result would not
  parse, nothing is written and the error names which edit.
* **`workspace_append`** — the long-file protocol. A whole-file write has to
  fit in one reply, so anything past a few hundred lines was cut off at
  `max_tokens` and landed truncated. First chunk with `create`, then append.
  No size limit.
* **`workspace_insert`**, **`workspace_glob`**, **`workspace_read_many`** —
  positional insert, find-by-name, and batch read.
* **`run` executes with the repo as its working directory**, so `pytest -q`
  just works and the model stops prefixing commands with a guessed `cd`.
* The workspace specs now **ship inline when a repo is open** instead of
  costing a `load_tools` round-trip that would always be made anyway.

## 7. Less restrained, and quieter to look at

The persona now defaults to **acting**: no asking whether to continue, no
permission theatre for work already implied by the request, no hedging a
finding it verified. What it did *not* verify is still labelled unverified just
as plainly — those are the same rule.

The stylesheet gets a **quiet pass**: darker grounds (panels darker than the
frame, not lighter), near-neutral chrome, and drop shadows kept only where
something genuinely floats. Verified against real GTK 4.14: **0 CSS parse
errors**, ASCII-only bytes literal intact.

---

## Also fixed, found on the way

* **`.gitignore` no longer excluded `settings.json`** — the file that holds API
  keys. Caught by `test_secrets.py`; restored.
* **A corrupted SVG on the website.** A past version-bump `sed` matched inside
  path data and turned three `a1 1 0 0 1` arc commands into `a1.1.4.0 1`. The
  icon could not render. Repaired, and this release's version bump is anchored
  so it cannot recur.
* **`read_many` silently raised an unusably small `max_chars`** — now reported.
* `install.sh`'s `EXT_FILES` gained the three new sidecar modules (a missing
  entry is fatal in remote-fetch mode).

## Numbers

**4,770 assertions across 79 suites**, zero red. Four new suites:
`test_tasks.py`, `test_plangate.py`, `test_browsersearch.py`,
`test_repotools.py`.

The system prompt grew ~800 tokens: the ledger (~180), real search (~230), and
the acting rules (~180) — all three used on nearly every turn, none of them
lazy-loadable without breaking what they were added for. The workspace group is
**not** in that number; it ships only when a repo is open.

The immutable `GUARDRAIL` block is byte-identical
(`sha256 0ccebd17786bfaaf…`).
