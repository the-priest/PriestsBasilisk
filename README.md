<!--
title: Basilisk — the private AI security operator that runs on your own machine
description: Basilisk is an open-source, self-hosted AI security operator that runs as a native GTK4 desktop app on your own Linux box. You bring a large language model (SiliconFlow/DeepSeek by default, Groq fallback); Basilisk gives it a body — a full offensive-security toolchain, a real exploit-builder suite, code & dependency auditing, a tamper-evident SHA-256 evidence ledger, real Brave/Playwright browsing, external tools over MCP, local memory, and a voice — all behind a hard structural safety floor and under your sole control. Nothing runs in a cloud you don't own; the only thing that ever leaves your machine is one API call to the model provider you picked. A private, security-native alternative to hosted AI assistants that refuse half of real security work and ship every prompt to a datacentre. 119 tool entries across nine capability groups. 40/113 fully-autonomous on the OWASP Juice Shop scoreboard.
keywords: private ai security operator, self-hosted ai, local ai agent, kali linux ai, ai pentest tool, offensive security ai, llm security agent, exploit builder, jwt forge, sqli xss ssrf, evidence ledger, tamper evident, sast sca ai, cve enrichment, kev epss, model context protocol, mcp client, nethunter ai, gtk4 app, deepseek, siliconflow, brave automation, red team assistant, data sovereignty, no telemetry
-->

<div align="center">

<img src="banner.png" alt="BASILISK — the serpent on your machine" width="820">

# There are more things in heaven and earth, than are dreamt of in your philosophy.

**You bring the model. Basilisk brings the body — the hands, the toolchain, the discipline, and the paper trail.**

<br>

![version](https://img.shields.io/badge/version-5.0.0-7d121b?style=for-the-badge&labelColor=08090b)
![license](https://img.shields.io/badge/license-MIT-7d121b?style=for-the-badge&labelColor=08090b)
![privacy](https://img.shields.io/badge/self--hosted-no%20cloud%20%7C%20no%20telemetry-7d121b?style=for-the-badge&labelColor=08090b)
![platform](https://img.shields.io/badge/Linux-X11%20%7C%20Wayland-6d7680?style=for-the-badge&logo=linux&logoColor=white&labelColor=08090b)

![python](https://img.shields.io/badge/python-3.10+-6d7680?style=for-the-badge&logo=python&logoColor=white&labelColor=08090b)
![toolkit](https://img.shields.io/badge/GTK4-libadwaita-6d7680?style=for-the-badge&labelColor=08090b)
![mobile](https://img.shields.io/badge/runs%20on-NetHunter-6d7680?style=for-the-badge&labelColor=08090b)
![ledger](https://img.shields.io/badge/evidence-tamper--evident-7d121b?style=for-the-badge&labelColor=08090b)
![benchmark](https://img.shields.io/badge/Juice%20Shop-40%2F113%20autonomous-7d121b?style=for-the-badge&labelColor=08090b)

**119 tool entries · nine capability groups · one app for a security operator's whole day**

</div>

<br>

---

<div align="center">

## ⚡ Install — and update — in one line

```bash
curl -fsSL https://raw.githubusercontent.com/the-priest/Basilisk/main/install.sh | bash
```

</div>

No Docker. No daemon. No account. No cloud. No telemetry. Paste it once to install; paste the **exact same line** any time to update. It auto-detects your distro, installs what it needs, parse-checks every file before it touches your disk, backs up your chat history, and drops a launcher in your app grid. About a minute from `curl` to a dragon on your desktop.

<br>

---

<div align="center">

## ▶ See it in action

*Model in the loop, tools on the target, a receipt for every move.*

</div>

https://github.com/user-attachments/assets/7df7b6a9-744d-46ec-9ce6-c8ae924fc786

https://github.com/user-attachments/assets/5462d36d-f649-4684-9e09-500a4afe98f5

<br>

---

## What Basilisk is

Basilisk is a **native Linux desktop application** that turns a large language model into a working **security operator** — one that runs entirely on your own hardware and answers only to you.

A language model on its own is a brain in a jar. It can *talk* about a port scan, but it can't run one. It can't see your desktop, touch your files, remember yesterday's engagement, forge a JWT against a target you're testing, or prove what it did. **Basilisk is the body around that brain.** You supply the intelligence through an API key you own; Basilisk supplies everything that turns "a clever chatbot" into "an operator who does the work — and hands you a receipt for every move."

<br>

<div align="center">

<img src="dragon.png" alt="Basilisk" width="360">

</div>

<br>

---

## Why Basilisk is different from every other "AI hacking tool"

Every product in this space is, underneath, **a chatbot behind a prompt on someone else's server.** Basilisk is the opposite on every axis that matters.

| | Hosted AI assistants | **Basilisk** |
|---|---|---|
| **Where it runs** | A datacentre you don't control | **Your machine.** A native app, not a website |
| **Your prompts** | Shipped to a cloud, logged, trained on | **Stay on your box.** Only one API call leaves — to the model *you* chose |
| **Real security work** | Refuses ~half of it, moralises over authorised scans | **Does it.** Plans, scans, and **writes & runs real exploits** on scope you set |
| **Can it actually *do* things?** | Talks only | **Yes.** Runs your shell, drives your desktop, browses the real web, fires built exploits through a gate |
| **Proof of what it did** | A chat log | **A tamper-evident SHA-256 evidence ledger** — a defensible deliverable |
| **In the field** | Never — it's a web tab | **In your pocket** on a Kali NetHunter phone |
| **Safety** | A vendor's content policy you can't see | **A hard floor in code** — the one irreversible mistake always stops for a human |
| **Ownership** | Rented, opaque, closed | **Yours.** Open source, MIT. Choose the model, fork the code, own the whole thing |

> **In one sentence:** every "AI hacking tool" is a chatbot behind a prompt. Basilisk is a disciplined, auditable operator's tool that runs on your hardware, draws a hard line at the one mistake you can't undo, and never forgets what it touched.

<br>

---

## 🔒 Private by architecture — not by promise

Privacy isn't a setting in Basilisk. It's the shape of the thing.

- **It is not a website.** Nothing runs on someone else's server. The app runs on your box. There is **no Basilisk backend, no daemon phoning home, no account, and no telemetry** — none, anywhere in the code.
- **Exactly one thing ever leaves your machine:** a single API call to the model provider *you* selected (SiliconFlow, Groq, or an OpenAI-compatible endpoint you point it at). Nothing else is transmitted, logged remotely, or shared.
- **Your keys never leave the box** except to the provider's own API. They live only in `~/.config/kali/settings.json` — plain, local, yours.
- **Your data stays local.** Chat history, the evidence ledger, memory, self-written skills, engagement state, loot — all of it lives under your home directory (`~/.local/share/kali`) and never syncs anywhere.
- **It can't see your sudo password.** Root is handled inline; the password is never stored, never logged, and never shown to the model.
- **OPSEC controls are built in.** Image search and OSINT readers are toggleable; the browser blocks trackers and the worst hosts at the network layer.
- **It's open source, MIT-licensed.** You don't have to *trust* any of the above — you can read every line, audit it, and fork it.

*Where a hosted assistant ships every prompt to a datacentre you don't control, Basilisk keeps your work on your hardware, doesn't moralise over a scan you're authorised to run, and leaves a record you can put in front of a client.*

<br>

---

## Everything Basilisk can do

One app that covers a security operator's whole day — **119 tool entries across nine capability groups.** You don't call these directly; you talk to Basilisk in plain language and it picks the tools, runs them, reads the results, and continues. Read-only **sensing** runs freely; anything that changes your system runs directly (default) or becomes an approve-first card (*Confirm every command* mode) — and the irreversible class always stops for a card regardless.

<details open>
<summary><b>🛡️ 1 · Offensive security</b> — recon, scanning, CVE intel, methodology</summary>

<br>

- **`tooling_check`** — inventories **59** modern offensive tools (recon, probing, port-scan, fuzzing, vuln, secrets, creds, AD) with exact install lines, command aliases, and freshness nudges. Read-only.
- **`pentest_plan`** — an **ordered** recon plan (passive first) with profiles `web · network · ad · api · full · quick` and a `stealth / normal / aggressive` intensity knob. Every step runs behind the approval gate.
- **`parse_output`** — turns raw scanner output into structured findings for **20+ tools** (nmap, httpx, nuclei, naabu, masscan, subfinder, ffuf, feroxbuster, gobuster, katana, whatweb, wpscan, sslscan/testssl, smbmap, netexec, nikto, gitleaks, dalfox, arjun…), strips ANSI, and **auto-chains into CVE intel** for every confirmed service+version.
- **`cve_lookup`** — NVD CVEs enriched with **CISA KEV** (exploited in the wild?) and **EPSS** (exploit probability), re-ranked **KEV → EPSS → CVSS**.
- **`nuclei_template`** — generate a structurally-valid Nuclei template from a spec, or validate one and get the exact list of problems before you run it.
- **`reflect_findings`** — a false-positive self-check that flags unsupported, over-rated, hedged, host-less or duplicate findings *before* they reach a report.
- **`audit` · `scan_net`** — read-only local posture scan (firewall, SSH, listeners, world-writable files, failed logins, updates, scored by severity) and discovery on your own segment.
- **`methodology` · `wordlist_find` · `cheatsheet` · `report_findings`** — PTES / OWASP / AD-killchain checklists, installed-wordlist finder, correct tool syntax, and clean markdown engagement reports.

</details>

<details>
<summary><b>💥 2 · The exploit builders</b> — it writes and runs real exploits *(new in 5.0)*</summary>

<br>

The line Basilisk holds isn't "no exploits" — *that's the whole job.* It's **no standalone weaponized malware** and **no firing the irreversible/destructive class on its own.** For everything in-scope, it builds the exploit and you fire it through the gate.

- **`jwt_forge`** — forge JSON Web Tokens: `alg:none` bypass and RS256→HS256 key-confusion.
- **`nosql_injection`** — NoSQL auth-bypass and operator-injection payloads.
- **`xxe_payload`** — XML External Entity payloads (file read and more).
- **`sqlmap_plan`** — build a correct, scoped `sqlmap` invocation for an in-scope target; you fire it.
- **`coupon_forge`** (Z85) · **`captcha_solve`** (reads the arithmetic CAPTCHA) · **`reset_password`** (security-question flow) — the class-specific builders for web-app targets.
- **`webapp_recon`** — a read-only sweep of a curated high-signal path catalog (`/ftp`, `/encryptionkeys`, exposed config/logs/backups, the SPA bundle) so leaked-key / backup / vulnerable-library work stops failing on missed recon.
- **`attack_writeup`** — the **exploitation narrative**: a reproducible account of how access was obtained, pulled straight from the evidence ledger so every step is backed by a real hashed command; secrets auto-redacted.

*Every exploit path is `builder → scope check → gate → run`. You're always on the trigger. No reverse-shell binaries, no self-propagating implants, no ransomware, no persistent backdoors — those non-goals are held in code.*

</details>

<details>
<summary><b>🔍 3 · Code &amp; dependency audit</b> — SAST, SCA, secrets, cross-tool triage</summary>

<br>

The static half of the job — vulnerabilities in source, dependencies, secrets and IaC. Safe on your own code; it drives standard installed scanners and makes sense of them.

- **`code_tooling_check`** — inventories the code-security stack (SAST / SCA / secrets / IaC / container / web-DAST) with install lines for the gaps.
- **`code_scan_plan`** — auto-detects languages, lockfiles and IaC and builds an **ordered, proposed** scan plan (Semgrep, Bandit, OSV-Scanner, gitleaks, pip-audit, `npm audit`…) with JSON flags set. Runs nothing — every step goes through the gate.
- **`parse_scan`** — normalizes raw JSON from **ten scanners** (Semgrep, Bandit, gitleaks, trufflehog, OSV-Scanner, Trivy, pip-audit, npm audit, retire.js, Nuclei) into one unified finding schema.
- **`triage_findings`** — the differentiator: **dedups across scanners** (two tools on the same CVE+package or `file:line:rule` collapse into one *corroborated* finding recording which agreed), maps every severity dialect onto one scale, sorts worst-first, and flags the low-confidence ones for review.
- **`remediation_hint`** — a short, standard, **non-exploit** fix pointer per finding (upgrade to the fixed version, or the CWE-class fix).

</details>

<details>
<summary><b>🧾 4 · Evidence &amp; engagement record</b> — the tamper-evident paper trail</summary>

<br>

Every command Basilisk runs is recorded automatically to an append-only JSONL ledger — timestamp, command, exit code, duration, and the **SHA-256** of its output, with full output saved as a hashed artifact.

- **`evidence_engagement`** — name/switch the case you're working; commands file under it.
- **`evidence_report`** — summary, integrity check, and a readable markdown ledger of everything run.
- **`evidence_verify`** — re-hash every captured artifact and prove nothing was altered after the fact.
- **`scope_set` · `scope_show` · `scope_check`** — record the authorised target list at the start of a job; the gate enforces it before anything touches a target.
- **`engagement_graph` · `graph_ingest`** — a live graph of hosts, services and footholds that populates itself from the scans you run.
- **`loot_record` · `loot_list` · `loot_reuse`** — captured credentials/artifacts, redacted by default.

*This is the difference between a chat log and a defensible engagement deliverable.*

</details>

<details>
<summary><b>🌐 5 · Web, search &amp; OSINT</b> — real browsing, fact-checking, footprinting</summary>

<br>

- **`browser`** — full **Playwright** automation that drives **Brave** when installed: Shields kill ads and trackers, cookie/consent walls are auto-dismissed, the worst hosts are blocked at the network layer. Falls back to bundled Chromium, and to headless HTTP for read-only fetches. goto, read, click, fill, submit, scroll, links, screenshot — and it self-heals a dead session instead of getting stuck.
- **`web_search` · `web_read`** — ranked search and headless clean-text page fetch.
- **`web_verify`** — an **anti-propaganda engine**: gathers independent sources, scores each for credibility, checks corroboration (including high-signal anchors like CVE IDs and versions), and returns a confidence label instead of laundering state media or satire into fact.
- **`osint_username` · `osint_lookup` · `social_read`** — public-profile and public-API readers (a hit means a public page exists, not that it's the same person).
- **`image_search`** — searches the web for images and **shows them inline in chat** (no API key). Toggle off for OPSEC.
- **`github`** — search/read repos, code, trees, READMEs, releases, issues (public; private with a token).

</details>

<details>
<summary><b>🖥️ 6 · Desktop &amp; system control</b> — hands on your actual machine</summary>

<br>

**System sensing (read-only, read live — never guessed):** `quick_facts` · `system_info` (real RAM/CPU/OS) · `disk_usage` · `processes` · `network_status` · `service_status` · `journal_tail` · `recent_downloads` · `check_updates` · `path_info`.

**Desktop control (confirm-gated):** `launch_app` · `list_apps` · `list_windows` · `focus_window` · `close_window` · `type_text` · `press_key` · `open_url` · `screenshot` · `read_screen` (on-screen **OCR**) · `media_control` · `media_play` / `media_show` (the in-app player) · `notify`. Auto-detects **X11 vs Wayland** and picks the right backend.

**Files &amp; shell (gated for anything that changes):** `read_file` · `list_dir` · `find_file` · `make_dir` · `copy_path` · `move_path` · `delete_path` · **`run`** any shell command (decisive by default, always force-confirmed for the catastrophic class, sudo handled safely). **Write any file** via a diff card you Apply.

</details>

<details>
<summary><b>🧠 7 · Memory, self-written tools &amp; self-modification</b> — it grows with you</summary>

<br>

- **Memory (optional, local):** `memory_remember` · `memory_recall` · `memory_forget` — relevance-scoped recall that connects security paraphrases ("SQL injection" finds "SQLi") and injects only the top-k per turn. Nothing leaves the box.
- **Self-written tools (optional, sandboxed):** `skill_write` → Basilisk drafts a Python tool, it's `ast`-parsed and statically screened, run in a **bubblewrap** jail, and must pass its **own test** before you Apply it. Then it's callable as `skill_run`.
- **Self-modification:** Basilisk can rewrite its own source and persona — proposed as a diff you Apply. Python is parse-checked, the original is backed up, writes are atomic, and the **guardrail block is immutable by design.**

</details>

<details>
<summary><b>🎯 8 · Benchmarking &amp; CTF</b> — prove it with a number, close the loop *(new in 5.0)*</summary>

<br>

- **`juiceshop_score`** — reads the **live** OWASP Juice Shop scoreboard and reports solved/available by difficulty. **`juiceshop_source`** reads the target's actual code from the running container so the model finds the vulnerable line instead of black-box guessing.
- **`juiceshop_next` · `juiceshop_diff`** — the **closed loop**: what's still unsolved (easiest-first, each mapped to the tool that cracks its class) and confirmation of a hit by diffing the board. Score → next → build → fire through the gate → diff → repeat.
- **`benchmark_targets` · `benchmark_score` · `benchmark_compare` · `benchmark_report`** — the known vuln set for a practice target (Juice Shop / DVWA / WebGoat), scored precision/recall/coverage, so a run is a reproducible number you can put next to any other tool's.
- **`xbow_score` · `xbow_report` · `submit_flag`** — flag-capture scaffolding for CTF-style targets.

</details>

<details>
<summary><b>🎙️ 9 · Voice, MCP &amp; working smart</b> — talk to it, extend it, run lean</summary>

<br>

- **Voice:** STT via SiliconFlow SenseVoice or Groq Whisper (auto-picked), with a *Test microphone* button. TTS via Piper (neural) or espeak-ng, tuned for natural pacing with no dead air, and per-message play/pause.
- **External tools over MCP:** connect **Model Context Protocol** servers and their tools become callable inside Basilisk (off until you add one).
- **Working smart:** batched parallel tool calls · trimmed history · context compression that always preserves findings while cutting token cost · a collapsed **💭 Thoughts** panel · live status pill · `/panic` health sweep · degraded-output failover to your next provider.
- **Background worker (optional):** a `systemd --user` service for genuinely-headless jobs (periodic checks, memory consolidation). Fully optional — Basilisk works identically without it.

</details>

<br>

> ### 📱 …and it all fits in your pocket.
> The **same** tool runs on a **Kali NetHunter** phone — a real operator's assistant in the field, something no hosted swarm can ever be.

<br>

---

## The safety model — why you can hand it root

Basilisk is **decisive by default and un-catastrophic by construction.**

- **Two speeds, you pick.** *Default:* read-only sensing runs free, and when you ask for something Basilisk does it, reads the result, and continues — no clicking through routine work. *Confirm every command (one toggle):* every side-effecting action becomes a card you approve one at a time.
- **The irreversible class always stops for a confirm** — even in auto-run, even if the model was steered by something it read on a webpage. A **structural** detector (shlex-tokenized, `$IFS`/quote-normalized, recursing into `sh -c` / `eval`) force-confirms disk/filesystem wipes, recursive root/`$HOME` deletes, fork bombs, and raw block-device writes. It sees through tricks a regex misses — `rm '-rf' /`, `rm${IFS}-rf${IFS}/`, `cd / && rm -rf *`, `find / -delete`, `echo … | base64 -d | sh` — while staying narrow enough that `nmap`, `nuclei`, `sqlmap` and `rm -rf ~/loot` never trip it. The full catch/ignore contract is **pinned in the test suite.**
- **The safety code can't be shell-stripped**, your **sudo password is never stored or shown to the model**, and self-written code runs only in a **bubblewrap** jail after passing its own test.
- **It can't lie about your machine.** Hardware and system facts are read live with a tool, never guessed.

> The guarantee isn't "asks every time" — it's that the one mistake that can't be undone keeps a human in the loop no matter what, and you can dial friction to full-confirm whenever you want.

<br>

---

## Benchmark — proven with a number, not a claim

Basilisk scores itself against known targets by objective, **reproducible** measures. No marketing table — a number you can regenerate.

### The hard one: OWASP Juice Shop challenge scoreboard — 40 / 113 solved (35.4%)

*Full challenge set, `NODE_ENV=unsafe`, 2026-07-04 — running fully autonomously against a local instance.*

The Juice Shop scoreboard only marks a challenge solved when the exploit **genuinely works** — so unlike a vuln-class checklist it can't be passed by recall, and it's graded by difficulty (1–6 stars). That makes it the real, comparable benchmark the security community uses.

| Difficulty | Solved |
|---|---|
| ★ | 12 / 13 |
| ★★ | 13 / 18 |
| ★★★ | 9 / 26 |
| ★★★★ | 5 / 25 |
| ★★★★★ | 1 / 19 |
| ★★★★★★ | 0 / 12 |

Hardest cracked: **Unsigned JWT** (5★) — forging a JWT with `alg:"none"` and an empty signature to authenticate as another user.

**What this means, honestly.** 35.4% fully autonomous on the *full* board is a strong result — published research puts fully-autonomous LLM pentest agents in roughly the 20–30% range on comparable tasks. Basilisk cleared the easy tiers (92% of 1★, 72% of 2★), held up through the middle, and cracked a 5★. The 6★ tier (SSRF, SSTi, RCE chains) is unsolved — as you'd expect; a human expert doesn't clear the whole board either. It is *not* a claim to beat any specific tool: nobody has published a like-for-like scoreboard number on the same version. It's an honest, reproducible measure of where Basilisk actually stands — with obvious room to grow at the top end.

### The methodology check: OWASP vuln-class coverage — 14 / 14 (F1 0.95)

A separate, easier run confirms the workflow end to end: Basilisk found and confirmed all 14 OWASP vuln *classes* on Juice Shop (SQLi, DOM/stored/reflected XSS, broken access control, sensitive data exposure, misconfig, directory listing, mass assignment, vulnerable components, input validation, SSRF, XXE, JWT deserialization). Juice Shop is heavily documented, so a high coverage score is partly recall — which is exactly why the scoreboard number above is the one that counts.

**Score it yourself:**

```bash
docker run -d -p 3000:3000 -e NODE_ENV=unsafe --name juiceshop bkimminich/juice-shop
```

Then ask Basilisk to work the board and call `juiceshop_score`. Full scorecard: [`benchmarks/juice-shop-scoreboard-2026-07-04.txt`](benchmarks/juice-shop-scoreboard-2026-07-04.txt). To compare another tool, run it against the same target and score it the same way — an honest, reproducible number beats a marketing table.

<br>

---

## Architecture

Model-agnostic brain, self-hosted body, two things that keep it honest.

1. **You bring the brain.** Point Basilisk at a large open model through a provider you choose — **SiliconFlow / DeepSeek-V4-Flash** by default (with DeepSeek-V4-Pro as the heavier reasoning sibling), **Groq** as a fast fallback, or any OpenAI-compatible endpoint. Intelligence rented by the call, for pennies.
2. **Basilisk is the body** — everything a hosted chatbot can never give you: the full toolchain, the exploit builders, code auditing, real browsing, desktop and shell control, memory, voice, MCP.
3. **Two things keep it honest** — a **structural safety floor** (the one irreversible class always stops for a human, in code) and a **tamper-evident evidence ledger** (every command hashed).

```
┌────────────────────────────────────────────────────────────────┐
│ kali.py  —  the UI                                             │
│ GTK4 · libadwaita · chat · cards · voice · media panel         │
└────────────────────────────────────────────────────────────────┘
                                 │
┌────────────────────────────────────────────────────────────────┐
│ kali_core.py  —  the engine                                    │
│ provider router (fail-over) · the agent toolset                │
│ web · search · github · Brave/Playwright · chat DB             │
├────────────────────────────────────────────────────────────────┤
│ kali_persona.py   system prompt + IMMUTABLE guardrail          │
│ kali_voice.py     STT + TTS (provider-aware ASR)               │
└────────────────────────────────────────────────────────────────┘
                                 │
┌────────────────────────────────────────────────────────────────┐
│ kali_safety.py   hard catastrophe floor (in code)              │
│ structural · evasion-resistant · setting-independent           │
├────────────────────────────────────────────────────────────────┤
│ kali_ledger.py   tamper-evident ledger · JSONL+SHA-256         │
└────────────────────────────────────────────────────────────────┘
                                 │
┌────────────────────────────────────────────────────────────────┐
│ kali_ext/   optional sidecar · off by default · 17 modules     │
├────────────────────────────────────────────────────────────────┤
│ memory · skills · sandbox · foresight · mcp · verify           │
│ reach · worker · headroom · pentest · codescan · engage        │
│ bench · extman · juiceshop · xbow · exploits                   │
└────────────────────────────────────────────────────────────────┘
```

The router reads your active provider and model live, and fails over to your next backend on a degraded response. The `kali_ext/` sidecar is entirely optional — absent or disabled, every hook is a no-op and Basilisk behaves exactly as it does without it; nothing in it writes outside `~/.local/share/kali/`.

<details>
<summary>Development &amp; test suites</summary>

<br>

```bash
git clone https://github.com/the-priest/Basilisk.git kali && cd kali
python3 kali.py                    # run from source

# offline test suites (stdlib only — no display, no keys, no network)
python3 tests/test_kali.py         # core: safety floor, settings, self-edit, ChatStore, ledger, CVE chain, Nuclei, reflection, memory, MCP screen
python3 tests/test_codescan.py     # code audit: every scanner parser, cross-tool triage/dedup, secret redaction
python3 tests/test_exploits.py     # exploit builders: jwt/nosql/xxe/coupon/captcha/reset payload correctness
python3 tests/test_writeup.py      # exploitation narrative: ledger-grounded steps, secret redaction, honesty on thin input
python3 tests/test_headroom.py     # token savings: protocol safety, signal preservation, compression ratio, fail-safe
```

Internal plumbing (the `org.thepriest.kali` app-id, the `~/.local/share/kali` data dir, and the lowercase `kali` module names) keeps its original name — that's plumbing, not the brand. For per-machine persona tweaks that survive upgrades, use **Settings → Persona → Custom addendum**; direct edits to `kali_persona.py` are replaced on the next `install.sh` run.

</details>

<br>

---

## Install &amp; update

```bash
curl -fsSL https://raw.githubusercontent.com/the-priest/Basilisk/main/install.sh | bash
```

Run it once to install; run the **exact same line** any time to update. The installer is idempotent and genuinely careful:

- 🐍 Detects **Python 3.10+** and installs **GTK4 + libadwaita** (apt / pacman / dnf, auto-detected).
- 📦 Fetches the core modules **plus** the optional `kali_ext/` sidecar — and **verifies every one of the 17 sidecar modules arrived**, retrying any that didn't, refusing to install a half-broken update over a working one.
- 🛟 **Parse-checks every incoming file before it overwrites anything** — a corrupted download can't replace your working install.
- 💾 **Backs up your chat database** before each update and reports the version move.
- 🧩 Installs optional desktop helpers, voice packages, and optionally Playwright + Chromium.
- 🦁 **`WITH_BRAVE=1`** installs Brave for ad/tracker-free browsing.
- 🚀 Drops a `kali` launcher in `~/.local/bin/` and a `.desktop` entry in your app grid.

**Manual install:** `git clone https://github.com/the-priest/Basilisk.git kali && cd kali && ./install.sh`
**Uninstall:** `~/.local/share/kali/install.sh --uninstall` (chat history kept).

<details>
<summary>Flags &amp; environment overrides</summary>

<br>

| flag | what it does |
| --- | --- |
| `--update` | explicit update (same as the default path) |
| `--uninstall` | remove Basilisk (chat history kept) |
| `--no-systemd` | skip the background-worker systemd unit |
| `--no-helpers` | skip optional desktop-control helpers |
| `--no-browser` | skip Playwright + Chromium |
| `--no-voice` | skip voice setup |
| `--no-prompt` | non-interactive (skips the API-key prompt) |

```bash
GROQ_API_KEY=gsk_...  ./install.sh      # preset a key, no prompt
WITH_BRAVE=1          ./install.sh      # also install Brave
WITH_MCP=1            ./install.sh      # configure a safe starter MCP server
BASILISK_REPO=user/fork  BASILISK_BRANCH=dev  ./install.sh
```

</details>

<br>

---

## Get an API key

Basilisk is multi-provider — you only need a key for the one(s) you want. Set the active provider and key in **Settings → Backends**.

| Provider | Get a key | Notes |
| --- | --- | --- |
| **SiliconFlow** | <https://cloud.siliconflow.com/account/ak> | **Default.** Big open models (DeepSeek, Qwen, Kimi) + SenseVoice STT |
| **Groq** | <https://console.groq.com/keys> | Blistering speed, generous free tier. Whisper STT. Keys look like `gsk_...` |

Keys live only in `~/.config/kali/settings.json` — they never go anywhere but the provider's own API.

<br>

---

## What Basilisk will *not* do

- **Destroy your system or its storage on its own.** Disk/FS wipes, recursive root/`$HOME` deletes, fork bombs and raw block-device writes are *always* force-confirmed — even in decisive auto-run, even via quoting / `$IFS` / `bash -c` tricks.
- **Be an always-on autonomous fleet agent.** A deliberate non-goal — Basilisk keeps you in the loop for the irreversible.
- **See your sudo password**, phone home, or reach private content it hasn't been given a token for.
- **Invent facts about your machine.** Hardware and system state are read with a tool, not guessed.
- **Generate standalone weaponized malware.** Writing and running exploits against *authorized, in-scope* targets is the whole point, and it does exactly that — but it won't churn out reverse-shell binaries, self-propagating implants, ransomware or persistent backdoors, and the irreversible class always keeps you on the trigger.

<br>

---

<div align="center">

## License

**MIT.** Take it, fork it, ship it. Your data, your keys, your machine, your rules.

## Credits

Forged by **The Priest** ⟁

*A dragon that lives on your machine, answers only to you, and never forgets where the bodies are buried.*

</div>
