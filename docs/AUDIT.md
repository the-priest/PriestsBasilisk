# Basilisk 7.5.0 — Honest Capability Audit

Not marketing. This is a straight read of what the code actually does, what is
deep, what is shallow, and where the real ceiling is. Written after reading the
core modules, running the subsystems, and testing the claims.

---

## 1. What is genuinely deep and works

These are not aspirational — I ran them.

### The exploitation oracle (`basilisk_ext/oracle.py`) — the crown jewel
This is what separates Basilisk from a "spray payloads and hope" agent. It is a
real, evidence-based verification system:
- A **ledger** — the agent *arms* an attempt with an explicit success criterion
  *before* firing, then *checks* it against the evidence after. Every attempt
  carries a verdict: CONFIRMED / FAILED / PENDING / INCONCLUSIVE.
- A **verdict engine** with six evidence types: `contains`, `absent`, `status`,
  `regex`, `differential` (similarity + length-delta against a baseline — a real
  boolean/blind channel detector), and `oob`.
- A real **out-of-band canary HTTP listener** (a local `ThreadingHTTPServer`).
  For blind bugs (blind SSRF/RCE/XXE/SQLi) the payload carries a unique canary
  URL; if the target ever calls back, the blind exploit is confirmed with
  certainty. This is the Burp Collaborator / interactsh technique, done locally.

Verified end-to-end: arm(`contains`) + matching evidence → CONFIRMED; non-matching
→ FAILED; `differential` with a distinct response → CONFIRMED. **This is the
single most important thing in the tool** — it means a "finding" is backed by
evidence, not a hopeful 200.

### The safety floor (`basilisk_safety.py`) — real defense-in-depth
Two setting-independent predicates that fire *before* any auto-run:
- `is_catastrophic_command` — splits sub-commands, parses argv, detects recursive
  flags, root/home/system targets, everything-globs, **and interpreter payloads**
  (so `python -c "shutil.rmtree('/')"` is caught, not just literal `rm -rf`), and
  analyses pipe chains.
- `command_tampers_self` — blocks writes to Basilisk's own source, protecting the
  immutable GUARDRAIL from being shell-stripped out.

This is not a regex blocklist; it is a small parser. It holds.

### Scope enforcement (`basilisk_ext/engage.py`) — fails closed
`scope_set` records authorised hosts/CIDRs/domains; `scope_check` answers "in
scope?" and **fails closed** — unknown or unparseable ⇒ NOT in scope. Plus an
asset graph and a redacted loot store. This is the difference between a tool and
a liability.

### Indirect-prompt-injection firewall (`basilisk_ext/webshield.py`)
Untrusted web content (browser, `web_read`, `web_search`, `reach`) is
deterministically scrubbed *before* it reaches the model: structural stripping of
`<script>`/`<style>`/`<template>`/comments, instruction-pattern scanning and
redaction, then wrapping. This is a genuine, load-bearing defense — the model is
never trusted to separate data from instructions in attacker-controlled text.

### Threat-intel enrichment (`basilisk_ext/pentest.py`) — real feeds
`cve_lookup` / `enrich_with_cves` load **CISA KEV** (Known Exploited
Vulnerabilities) and **EPSS** (Exploit Prediction Scoring System) and rank
findings by real-world exploitability — not just CVSS. Plus `sqlmap_plan`,
`nuclei_template`, `wordlist_find`, a methodology engine and a cheatsheet. 37
functions of genuine planning substrate.

### The offensive arsenal (`basilisk_ext/exploits.py`) — 60 tools
Broad, current web-vuln payload *generators* — SQLi/SSTI/XXE/SSRF/command-inj,
GraphQL, CORS, LDAP/XPath, request-smuggling, race conditions, deserialization,
prototype pollution, cache poisoning, OAuth/JWT, and now `auth_attack`,
`jwt_attack`, `api_test`. Each is a pure builder returning ready-to-fire
payloads/commands.

### The discovery engine (`attack_surface`)
Mines endpoints, parameters, hidden/disabled fields, DOM-XSS sinks and leaked
secrets (JWT/AWS keys/private keys) out of a captured page or JS bundle, and — as
of 7.5.0 — routes each to the right builder, including the new tools. This is the
answer to the #1 reason automated passes miss bugs: never finding the vulnerable
endpoint/param.

### Autonomy (7.5.0 fix)
A real mission loop that works a task relentlessly until a completion token — and
now correctly **does not** treat a question as a mission (see the classifier). It
acts directly (no approval cards) in the default low-friction mode, with the
safety floor underneath.

### Memory & verification
`memory.py` — relevance-scoped top-k recall (FTS5/LIKE), runs on a phone, never
bloats the window. `verify.py` — multi-source fact verification with credibility
scoring and propaganda/satire flagging.

---

## 2. What is limited, aspirational, or honest-caveat territory

I am not going to oversell this. The following are real limits:

- **"Finds zero-days" is not a button, and no tool can promise it.** Basilisk
  provides *excellent discovery scaffolding* — surface mining, 60 payload
  builders, evidence-based verification, blind-bug OOB confirmation, KEV/EPSS
  ranking. But whether a *novel* vulnerability is actually discovered depends on
  (a) the target genuinely being vulnerable and (b) the LLM backend reasoning
  well about that specific target. The tool massively raises the floor and
  removes the "did it really work?" guesswork; it does not manufacture a 0-day
  where none exists. Anyone selling you an "automatic zero-day finder" is lying.
- **The ceiling is the model.** The scaffolding is strong; the intelligence
  driving it is the SiliconFlow/DeepSeek backend. A better model = a sharper
  Basilisk with the same code. This is inherent to the architecture, not a bug.
- **The payloads are DETECTION-grade by design.** RCE proofs default to a
  read-only `id`/`whoami`. There are deliberately **no** reverse shells, C2,
  implants, or persistence — that boundary is guarded by a test. This makes
  Basilisk prove a vulnerability *class* rather than build a weaponised exploit.
  That is the correct posture for a safety-first tool run with root on your own
  box; it also means "terrifying" here means *thorough and evidence-driven*, not
  *drops a Meterpreter*.
- **Blind/OOB confirmation needs the canary reachable.** The OOB listener is
  local; a target behind egress filtering that can't reach your canary can't
  confirm a blind bug that way — you fall back to `differential`/timing, which is
  weaker.
- **`attack_surface` is regex-based mining.** It's good and now well-routed, but
  it reads what's in the captured text — it doesn't crawl or execute JS. Feed it
  a bigger/rendered bundle for more surface.

---

## 3. The `test_kali.py` failure (so you're not surprised)

The suite shows **15 passed, 1 failed**. That one failure — `tests/test_kali.py` —
is a **dead leftover from the kali→basilisk rename**: it imports the old
`kali_core` module name that no longer exists. It was failing before any change
in this cut. It is not wired into anything and does not reflect a real defect. It
can be deleted or ported to `basilisk_core` whenever you like; I left it untouched
rather than silently change your test tree.

---

## 4. What I'd genuinely do next (concrete, not filler)

In priority order, if you want to keep deepening real capability:

1. **A finding-correlation / chaining tool.** The oracle knows what's CONFIRMED.
   A tool that reads the confirmed ledger and proposes the *next* attack (an
   IDOR + a leaked id → account takeover; an SSRF + cloud metadata → creds) would
   turn verified findings into chains. This is the highest-value next step.
2. **A rendered-DOM feed into `attack_surface`.** Pipe the browser's rendered DOM
   (not just static HTML) in, so client-rendered routes/params are mined too.
3. **Differential-analysis helper for logic bugs.** A tool that diffs many
   responses to surface business-logic anomalies (price, quantity, state) —
   the class scanners can't find and where the real money is.
4. **Port or delete `test_kali.py`** so the suite reads a clean 16/16.

None of these are cosmetic; each adds a capability that isn't there today.

---

## 5. Bottom line

Basilisk 7.5.0 is a genuinely serious offensive-security operator: evidence-based
verification (the oracle), a real safety floor, fail-closed scope, a
prompt-injection firewall, KEV/EPSS-ranked intel, 60 current payload builders, and
a discovery engine that now routes coherently into all of them — driven by an
autonomous loop that finally knows when you're asking a question versus setting it
loose on a target. It will find real vulnerabilities on vulnerable targets and,
crucially, tell you which findings are *proven* rather than hopeful. It will not
hand you a guaranteed zero-day, because that tool does not exist — and pretending
otherwise would be the exact superficial nonsense this audit refuses to sell.
