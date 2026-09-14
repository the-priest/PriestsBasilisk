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

**4,750 assertions across 79 suites**, zero red. Four new suites:
`test_tasks.py`, `test_plangate.py`, `test_browsersearch.py`,
`test_repotools.py`.

The system prompt grew ~800 tokens: the ledger (~180), real search (~230), and
the acting rules (~180) — all three used on nearly every turn, none of them
lazy-loadable without breaking what they were added for. The workspace group is
**not** in that number; it ships only when a repo is open.

The immutable `GUARDRAIL` block is byte-identical
(`sha256 0ccebd17786bfaaf…`).
