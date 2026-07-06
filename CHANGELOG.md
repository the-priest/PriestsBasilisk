# Changelog

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
  the stale "v4.10.0" label to the current 5.x closed loop + white-box, and added
  autonomous mode to the safety model. Version badges and headers moved to 5.1.0.

## v5.0.0 — the operator release

Major version. 5.0 consolidates the closed-loop offensive capability added across
the 4.10 line into a headline release, and ships a full rewrite of the user
manual documenting every one of Basilisk's 119 tool entries in detail.

The capability jump that defines 5.0:

- **White-box benchmarking.** `juiceshop_source` reads the target's actual code
  from the running container (or a local dir) — tree / read / grep / the
  authoritative `challenges.yml` — so the model finds the vulnerable line
  instead of black-box guessing. And `juiceshop_next` now surfaces each unsolved
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
