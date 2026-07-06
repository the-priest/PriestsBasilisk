<!--
title: Basilisk — the AI security operator that runs on your own machine
description: Basilisk is an open-source AI security operator that runs as a native GTK4 desktop app on your own Linux box. You bring a large language model (SiliconFlow, Groq); Basilisk gives it hands — a full offensive-security toolchain, code & dependency auditing, a tamper-evident evidence ledger, real web browsing through Brave, external tools over MCP, a memory, and a voice — all behind a hard structural safety floor and under your control. A private, security-native, self-hosted alternative to cloud AI assistants.
keywords: ai security operator, kali linux ai, ai pentest tool, offensive security ai, llm security agent, autonomous pentest agent, deepseek security agent, evidence ledger, sast sca ai, cve enrichment, kev epss, model context protocol, mcp client, nethunter ai, gtk4 app, deepseek, siliconflow, brave automation, red team assistant
-->

<div align="center">

<img src="banner.png" alt="BASILISK — the serpent on your machine" width="820">

### An AI security operator that lives on **your** machine — not someone else's cloud.

*You bring the model. Basilisk brings the hands, the toolchain, the discipline, and the paper trail.*

<br>

![version](https://img.shields.io/badge/version-5.1.2-7d121b?style=for-the-badge&labelColor=08090b)
![license](https://img.shields.io/badge/license-MIT-7d121b?style=for-the-badge&labelColor=08090b)
![platform](https://img.shields.io/badge/Linux-X11%20%7C%20Wayland-6d7680?style=for-the-badge&logo=linux&logoColor=white&labelColor=08090b)
![python](https://img.shields.io/badge/python-3.10+-6d7680?style=for-the-badge&logo=python&logoColor=white&labelColor=08090b)

![toolkit](https://img.shields.io/badge/GTK4-libadwaita-6d7680?style=for-the-badge&labelColor=08090b)
![mobile](https://img.shields.io/badge/runs%20on-NetHunter-6d7680?style=for-the-badge&labelColor=08090b)
![ledger](https://img.shields.io/badge/evidence-tamper--evident-7d121b?style=for-the-badge&labelColor=08090b)
![benchmark](https://img.shields.io/badge/Juice%20Shop-43%2F113%20autonomous-7d121b?style=for-the-badge&labelColor=08090b)

</div>

<br>

---

<div align="center">

## ⚡ Install — and update — in one line

</div>

```bash
curl -fsSL https://raw.githubusercontent.com/the-priest/Basilisk/main/install.sh | bash
```

No Docker. No daemon. No account. No cloud. Paste it once to install; paste the **exact same line** any time to update. It auto-detects your distro, installs what it needs, parse-checks every file before it touches your disk, backs up your chat history, and drops a launcher in your app grid. About a minute from `curl` to a dragon on your desktop.

<br>

---

<div align="center">

## ▶ See it in action

**5★ challenges from the benchmark — solved fully autonomously, caught live.**

*Model in the loop, tools on the target, a receipt for every move. No source access — pure black-box, start to finish.*

</div>

https://github.com/user-attachments/assets/7df7b6a9-744d-46ec-9ce6-c8ae924fc786

https://github.com/user-attachments/assets/8b633570-a7b2-4345-a5ee-41b02e5ddfc3

https://github.com/user-attachments/assets/8ab0cb29-a66d-4cfd-880b-0365a32cc3a7

<br>

---

## What Basilisk is

Basilisk is a **native Linux desktop application** that turns a large language model into a working **security operator** — one that runs entirely on your own hardware and answers only to you.

A language model on its own is just a brain in a jar. It can *talk* about a port scan, but it can't run one. It can't see your desktop, touch your files, remember yesterday's engagement, or prove what it did. **Basilisk is the body around that brain.** You supply the model through an API key you own; Basilisk supplies everything that turns "a clever chatbot" into "an operator who can actually do the work — and hand you a receipt for every move."

That distinction is the whole point:

- **It is not a website.** Nothing runs on someone else's server. The app runs on your box; the only thing that ever leaves is a single API call to the model provider *you* picked.
- **It is not a jailbroken chatbot.** It doesn't beg a hosted model to ignore its rules. It's a purpose-built operator's tool with real engineering around it — a structural safety floor, a cryptographic evidence trail, a full toolchain.
- **It is yours.** Open source, MIT-licensed. Your data, your keys, your machine, your rules. Choose the model. Fork the code. Own the whole thing.

Where a hosted AI *product* refuses half of real security work and wraps the model in policy you can't see or change, Basilisk gives you the **raw model** through a provider and key you choose, running on your own machine wired to your own tools. It doesn't moralize over a scan you're authorized to run, and it leaves a tamper-evident record you can put in front of a client. Your evidence ledger, memory, and chat history stay on your machine — the model calls themselves go out to the provider you picked (SiliconFlow / DeepSeek by default), the same as any API-backed tool.

> **In one sentence:** every "AI hacking tool" is a chatbot behind a prompt. Basilisk is the opposite — a disciplined, auditable operator's tool that runs on your hardware, draws a hard line at the one mistake you can't undo, and never forgets what it touched.

<br>

<div align="center">

<img src="dragon.png" alt="Basilisk" width="360">

*A dragon that lives on your machine, answers only to you,<br>and never forgets where the bodies are buried.*

</div>

<br>

---

## What you can use it for

Basilisk isn't a single-trick tool. It's one app that covers a security operator's whole day. Here's what that looks like in practice.

### 🎯 Run a penetration test, end to end
Point Basilisk at an authorized target and walk the full engagement without leaving the window. It inventories your installed tooling, builds an **ordered recon plan** (passive first, then active), proposes each command for you to approve, parses the raw output into clean findings, and **auto-ranks the CVEs by what's actually being exploited in the wild** (NVD + CISA KEV + EPSS). When you get in, it writes the **reproducible "how we got in" report section straight from the evidence ledger** — backed by the real hashed commands that ran, not a freeform retelling. It can **benchmark itself** against known-vulnerable practice targets (Juice Shop, DVWA, WebGoat) and score the run — precision, recall, coverage — so its performance is a reproducible number you can put next to any other tool's. It maintains a live **engagement graph** (hosts, services, footholds) that populates itself from the scans it runs, enforces your authorised **scope** before touching a target, and records everything to a tamper-evident trail you can hand to the client as proof of work.

### 🔍 Audit your own code and dependencies
Give it a repo. It detects the languages, lockfiles and IaC, then drives the industry-standard scanners — **Semgrep, Bandit, gitleaks, OSV-Scanner, Trivy, pip-audit, `npm audit`** — and does the part those tools *don't*: it **normalizes ten scanners into one finding list and triages across them**, so two tools flagging the same issue collapse into one *corroborated* finding, the weak ones get flagged for review, and you get a clean, prioritized list with concrete fixes instead of ten different JSON dumps.

### 🛡️ Harden a machine
Ask for a posture check and it runs a read-only system audit — firewall, SSH hardening, open listeners, world-writable files, failed logins, pending updates — scored by severity, with the reasoning shown. No guessing: facts about your system are read live with a tool, never invented.

### 🕵️ Investigate a footprint
Check your own exposure or research a handle across public profile sites and public APIs, fetch and clean web pages, and fact-check claims through an **anti-propaganda engine** that scores sources for credibility and corroboration instead of laundering state media or satire into "fact."

### 🖥️ Use it as a hands-on desktop agent
It drives your **actual desktop** — launches apps, manages windows, types, presses keys, reads what's on screen with OCR — and runs your **shell** behind a hard safety floor. It's a sysadmin and a pair of hands, not just a chat box.

### 📱 Take it into the field
The same tool runs on a **Kali NetHunter phone** — a real operator's assistant in your pocket, something no hosted swarm can ever be.

### 🧩 Bend it to your workflow
It **writes and sandbox-tests its own Python tools** when you need a capability it doesn't have, **connects external tool servers over MCP**, **remembers across sessions**, and **talks and listens** so you can work hands-free.

<br>

---

## How it works

Three pieces, and understanding them is understanding Basilisk.

**1 — You bring the brain.** Basilisk is model-agnostic. You point it at a large open model through a provider you choose (SiliconFlow with DeepSeek by default, Groq as a fast fallback) using your own API key. The intelligence is rented by the call, for pennies; nothing is baked in or locked down.

**2 — Basilisk is the body.** Around that model sits the part that actually matters and that a hosted chatbot can never give you: a full offensive-security toolchain, code and dependency auditing, real web browsing, desktop and shell control, an on-disk memory, a voice, and external-tool integration. This is where the value lives.

**3 — Two things keep it honest.** A **structural safety floor** refuses the one irreversible class of mistake outright — no confirm, no override — no matter how the model was steered. A **tamper-evident evidence ledger** records every command and hashes its output, so you can prove exactly what happened. Decisive on routine work, un-catastrophic by construction, auditable end to end.

<br>

---

## Everything Basilisk can do

Read-only **sensing** runs freely. Anything that changes your system just runs — Basilisk is autonomous, with no approval prompts (the only prompt is a one-time sudo password, then cached). The irreversible class is refused outright regardless, no override. The lists below are grouped by what you'd actually reach for.

<details>
<summary><b>🛡️ Offensive security</b> — recon, scanning, CVE intel, exploitation write-ups</summary>

<br>

- **`audit`** — system posture scan (firewall, SSH, listeners, world-writable files, failed logins, updates), scored by severity. Read-only.
- **`scan_net`** — discovery on your own segment.
- **`tooling_check`** — inventories **59** offensive tools (recon, probing, port-scan, fuzzing, vuln, secrets, creds, AD) with exact install lines, command aliases, and freshness nudges.
- **`pentest_plan`** — an **ordered** recon plan (passive first) with profiles `web · network · ad · api · full · quick` and a `stealth / normal / aggressive` intensity knob. Every step runs behind the approval gate.
- **`parse_output`** — turns raw scanner output into structured findings for **20+ tools** (nmap, httpx, nuclei, naabu, masscan, subfinder, ffuf, feroxbuster, gobuster, katana, whatweb, wpscan, sslscan/testssl, smbmap, netexec, nikto, gitleaks, dalfox, arjun…), strips ANSI, and **auto-chains into CVE intel** for every confirmed service+version.
- **`cve_lookup`** — NVD CVEs enriched with **CISA KEV** (exploited in the wild?) and **EPSS** (exploit probability), re-ranked **KEV → EPSS → CVSS**.
- **`nuclei_template`** — generate a structurally-valid Nuclei template from a simple spec, or validate one and get the exact list of problems before you run it.
- **`reflect_findings`** — a false-positive self-check that flags unsupported, over-rated, hedged, host-less or duplicate findings *before* they reach a report.
- **`attack_writeup`** — the **exploitation narrative**: a reproducible account of how access was obtained, pulled straight from the evidence ledger so the steps are backed by real hashed commands; secrets auto-redacted. This tool *documents* an authorized, already-executed path (the exploiting happens through the run gate; this writes it up).
- **`methodology` · `wordlist_find` · `cheatsheet` · `report_findings`** — PTES / OWASP / AD-killchain checklists, installed-wordlist finder, correct tool syntax, and clean markdown engagement reports.

*Offensive tooling runs behind the approval gate, against scope you set. Basilisk plans, inventories, parses, enriches, **writes and runs real exploits**, and documents the results — you approve the actions and stay on the trigger. The line it holds isn't "no exploits" (that's the whole job) — it's no **standalone weaponized malware** (reverse-shell binaries, self-propagating implants, ransomware, persistent backdoors) and no firing of irreversible/destructive actions on its own.*

</details>

<details>
<summary><b>🔍 Code &amp; dependency audit</b> — SAST, SCA, secrets, cross-tool triage</summary>

<br>

The static half of the job — finding vulnerabilities in source, dependencies, secrets and IaC. Safe on your own code; it drives standard installed scanners and makes sense of them.

- **`code_tooling_check`** — inventories the code-security stack (SAST / SCA / secrets / IaC / container / web-DAST) with install lines for the gaps.
- **`code_scan_plan`** — auto-detects languages, lockfiles and IaC in a path and builds an **ordered, proposed** scan plan (Semgrep, Bandit, OSV-Scanner, gitleaks, pip-audit, `npm audit`…) with JSON flags set. Runs nothing — every step goes through the approval gate.
- **`parse_scan`** — normalizes raw JSON from **Semgrep, Bandit, gitleaks, trufflehog, OSV-Scanner, Trivy, pip-audit, npm audit, retire.js, Nuclei** into one unified finding schema.
- **`triage_findings`** — the differentiator: **dedups across scanners** (two tools on the same CVE+package or `file:line:rule` collapse into one *corroborated* finding recording which agreed), maps every severity dialect onto one scale, sorts worst-first, and flags the low-confidence ones for manual review.
- **`remediation_hint`** — a short, standard, **non-exploit** fix pointer per finding (upgrade to the fixed version, or the CWE-class fix).

</details>

<details>
<summary><b>🧾 Evidence &amp; engagement record</b> — the tamper-evident paper trail</summary>

<br>

Every command Basilisk runs is recorded automatically to an append-only JSONL ledger — timestamp, command, exit code, duration, and the **SHA-256** of its output, with full output saved as a hashed artifact.

- **`evidence_engagement`** — name/switch the case you're working; commands file under it.
- **`evidence_report`** — summary, integrity check, and a readable markdown ledger of everything run.
- **`evidence_verify`** — re-hash every captured artifact and prove nothing was altered after the fact.

*This is the difference between a chat log and a defensible engagement deliverable.*

</details>

<details>
<summary><b>🌐 Web, search &amp; OSINT</b> — real browsing, fact-checking, footprinting</summary>

<br>

- **`browser`** — full **Playwright** automation that drives **Brave** when installed: Shields kill ads and trackers, cookie/consent walls are auto-dismissed, and the worst hosts are blocked at the network layer, so pages actually load and read. Falls back to bundled Chromium, and to headless HTTP for read-only fetches. goto, read, click, fill, submit, scroll, links, screenshot — and it self-heals a dead session instead of getting stuck.
- **`web_search` · `web_read`** — ranked search and headless clean-text page fetch.
- **`web_verify`** — anti-propaganda engine: gathers independent sources, scores each for credibility, checks corroboration (including high-signal anchors like CVE IDs and versions), and returns a confidence label instead of laundering state media or satire into fact.
- **`osint_username` · `osint_lookup` · `social_read`** — public-profile and public-API readers (a hit means a public page exists, not that it's the same person).
- **`image_search`** — searches the web for images and **shows them inline in chat** (no API key). Toggle off for OPSEC.
- **`github`** — search/read repos, code, trees, READMEs, releases, issues (public; private with a token).

</details>

<details>
<summary><b>🖥️ Desktop &amp; system control</b> — hands on your actual machine</summary>

<br>

**System sensing (read-only, read live — never guessed):** `quick_facts` · `system_info` (real RAM/CPU/OS) · `disk_usage` · `processes` · `network_status` · `service_status` · `journal_tail` · `recent_downloads` · `check_updates` · `path_info`.

**Desktop control (confirm-gated):** `launch_app` · `list_apps` · `list_windows` · `focus_window` · `close_window` · `type_text` · `press_key` · `open_url` · `screenshot` · `read_screen` (on-screen **OCR**) · `media_control` · `notify`. Auto-detects **X11 vs Wayland** and picks the right backend.

**Files &amp; shell (everything runs — autonomous):** `read_file` · `list_dir` · `find_file` · `make_dir` · `copy_path` · `move_path` · `delete_path` · **`run`** any shell command (runs directly, the catastrophic class refused outright, sudo password collected once then cached). **Write any file** — applied directly.

</details>

<details>
<summary><b>🧠 Memory, self-written tools &amp; self-modification</b> — it grows with you</summary>

<br>

- **Memory (optional, stored on your machine):** `memory_remember` · `memory_recall` · `memory_forget` — relevance-scoped recall that connects security paraphrases ("SQL injection" finds "SQLi") and injects only the top-k per turn. The memory files live on your machine; recalled snippets are sent to the model as context only when they're relevant.
- **Self-written tools (optional, sandboxed):** `skill_write` → Basilisk drafts a Python tool, it's `ast`-parsed and statically screened, run in a **bubblewrap** jail, and must pass its **own test** before you Apply it. Then it's callable as `skill_run`.
- **Self-modification:** Basilisk can rewrite its own source and persona — proposed as a diff you Apply. Python is parse-checked, the original is backed up, writes are atomic, and the **guardrail block is immutable by design**.

</details>

<details>
<summary><b>🎙️ Voice &amp; ⚡ working smart</b> — talk to it, and it runs lean</summary>

<br>

- **Voice:** STT via SiliconFlow SenseVoice or Groq Whisper (auto-picked), with a *Test microphone* button. TTS via Piper (neural) or espeak-ng, tuned for natural pacing with no dead air, and per-message play/pause.
- **Working smart:** batched parallel tool calls · trimmed history · context compression that always preserves findings while cutting token cost · a collapsed **💭 Thoughts** reasoning panel · live status banner · `/panic` health sweep · degraded-output failover to your next provider.
- **Background worker (optional):** a `systemd --user` service for genuinely-headless jobs (periodic checks, memory consolidation). Fully optional — Basilisk works identically without it.

</details>

<br>

---

## The safety model — why you can hand it root

Basilisk is **decisive by default and un-catastrophic by construction.**

- **Autonomous — no confirmation, ever.** Basilisk runs every command it decides on, immediately, and continues the chain on its own until the task is done or you hit Stop. There is no "confirm every command", no approval card, no mode to pick — you turn it on a job, walk away, and come back to results. The **only** dialog that can appear is a one-time prompt to collect a **sudo password** when a root command has no cached credential; after that it's cached and reused silently and you never see it again.
- **The irreversible class is refused outright — no confirm, no override.** A **structural** detector (shlex-tokenized, `$IFS`/quote-normalized, recursing into `sh -c` / `eval`) **hard-blocks** disk/filesystem wipes, recursive root/`$HOME` deletes, fork bombs, and raw block-device writes — before the shell, no matter what steered the model. There is no "Run anyway" and no setting that turns it off. It sees through tricks a regex misses — `rm '-rf' /`, `rm${IFS}-rf${IFS}/`, `cd / && rm -rf *`, `find / -delete`, `echo … | base64 -d | sh` — while staying narrow enough that `nmap`, `nuclei`, `sqlmap` and `rm -rf ~/loot` never trip it. A raw shell write to Basilisk's own source is refused the same way, so a malicious page can't overwrite the safety code. Both are pinned in the test suite.
- **Basilisk's own safety code can't be shell-stripped**, your **sudo password is never stored or shown to the model**, and self-written code runs only in a **bubblewrap jail** after passing its own test.
- **It can't lie about your machine.** Hardware and system facts are read live with a tool, never guessed.
- **Exploitation is the job.** Basilisk writes and runs real exploits (SQLi, XSS, JWT forgery, SSRF, sqlmap-driven attacks, and more) against targets you're authorized to test, within scope you set. The line it holds: no **standalone weaponized malware** (reverse shells, implants, ransomware, backdoors), and the irreversible/destructive class is refused outright and can never run through Basilisk at all.

> The guarantee isn't "asks every time" — it never asks. It's that the one mistake that can't be undone — wiping the system or its storage — **can never run through Basilisk at all**, while everything else runs unattended.

<br>

---

## Install &amp; update

```bash
curl -fsSL https://raw.githubusercontent.com/the-priest/Basilisk/main/install.sh | bash
```

Run it once to install; run the **exact same line** any time to update. The installer is idempotent and genuinely careful — it treats your machine the way you'd want it treated:

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

## Benchmark

Basilisk can score itself against known targets — and it does so by objective,
reproducible measures, not claims. Two benchmarks, from hardest to easiest.

### The hard one: Juice Shop challenge scoreboard — 43 / 113 solved (38%), fully autonomous

*Full challenge set, `NODE_ENV=unsafe`, Basilisk v5.1.2, 2026-07-06*

OWASP Juice Shop ships 100+ individual hacking challenges rated 1–6 stars, and
the app itself tracks which ones you've solved — it only marks a challenge solved
when the exploit **genuinely works**. That makes this the real, hard, comparable
benchmark the security community uses: unlike a vuln-class checklist, it can't be
passed by recall, and it's graded by difficulty. Human CTF players and other
tools report their numbers against the same scoreboard.

Left to run **fully autonomously** — pointed at the target and turned loose, with
no per-command approval and no human clicking — Basilisk solved **43 of the 113
available challenges (38%)**:

| Difficulty | Solved | Rate |
|---|---|---|
| ★ | 9 / 13 | 69% |
| ★★ | 10 / 18 | 56% |
| ★★★ | 9 / 26 | 35% |
| ★★★★ | 4 / 25 | 16% |
| ★★★★★ | **10 / 19** | **53%** |
| ★★★★★★ | 1 / 12 | 8% |

Hardest cracked: **Login Support Team** (6★).

**What this number means, and why the shape is the interesting part.** This was a
**pure black-box run** — Basilisk had no access to Juice Shop's source (the source
files aren't even on the machine); it exploited everything from the outside, the
same way other tools and human CTF players are scored. 38% fully autonomous and
black-box on the *full* board is a strong result — published research puts
fully-autonomous LLM pentest agents in roughly the 20–30% range on comparable
tasks. But look at the **5★ row: 10 of 19 (53%)** — a higher solve rate than the
3★ and 4★ tiers below it. That inversion tracks the 5.x work: the class exploit
builders map directly onto specific hard challenges — JWT forgery
(*Unsigned JWT*), the security-question
password resets (*Reset Bjoern's / Morty's Password*, *Change Bender's Password*),
leaked-secret recon (*Leaked API Key*, *Leaked Access Logs*, *Email Leak*), and
supply-chain / typosquatting analysis (*Frontend Typosquatting*, *Blockchain
Hype*). So Basilisk isn't just clearing easy wins and stalling — it reaches deep
into the 5★ tier and even takes a 6★.

**Where it stops, honestly.** The 4★ tier (16%) and the top of 6★ are the soft
spots: challenges needing full RCE/SSTi/SSRF chains, DoS conditions, or
multi-step business-logic abuse (*SSRF*, *SSTi*, *Successful RCE DoS*, *Wallet
Depletion*, *Arbitrary File Write*) are still red — as you'd expect; those are
brutal, and a human expert doesn't clear the whole board either. This is **not** a
claim to beat any specific tool — nobody's published a like-for-like scoreboard
number on the same version. It's an honest, reproducible measure of where
Basilisk actually stands: strong and autonomous through the middle and into the
hard-exploit tier, with obvious room to grow on the full-chain RCE class at the
very top.

Score it yourself:

```bash
docker run -d -p 3000:3000 -e NODE_ENV=unsafe --name juiceshop bkimminich/juice-shop
```

Then turn Basilisk loose on the board and call `juiceshop_report`, which reads the
live scoreboard (`/api/Challenges`) and reports solved/available by difficulty.
Full scorecard: [`benchmarks/juice-shop-scoreboard-2026-07-06.txt`](benchmarks/juice-shop-scoreboard-2026-07-06.txt).

#### How the autonomous run works — the 5.x arsenal (black-box)

No source access, no cheating — Basilisk worked the board from the outside. 5.x
runs a feedback loop plus per-class exploit builders, so the agent can tell
whether an attempt landed, retry intelligently, and keep going on its own:

- **Closed-loop harness** — `juiceshop_score` reads the live board, `juiceshop_next`
  returns what's still unsolved (easiest-first, each mapped to the tool that
  solves it, carrying its live objective + hint from the public scoreboard;
  `per_tier` gives a focused ~30-challenge board), and `juiceshop_diff` confirms a
  hit by diffing the board. The agent works the board → tries a target → confirms
  → moves on.
- **Class exploit builders** — `jwt_forge` (alg:none + RS256→HS256 confusion),
  `nosql_injection`, `xxe_payload`, `coupon_forge` (z85), `captcha_solve`
  (auto-reads the arithmetic CAPTCHA), `reset_password` (security-question flow,
  demo accounts only) — the same model as `sqlmap_plan`.
- **Recon sweep** — `webapp_recon` enumerates the high-signal leak surface
  (`/ftp`, `/encryptionkeys/jwt.pub`, exposed config/logs/backups, the SPA bundle)
  so the leaked-key / backup challenges stop failing on missed recon.
- **Browser reliability** — `goto`/`submit`/`click` wait (bounded) for the Angular
  SPA to render before reading, fixing browser-dependent challenges.

The distribution shows it working: on an earlier one-shot run (before the loop),
the 5★ tier was 1/19. With the closed loop and the builders, it's **10/19** — that
jump is the feedback loop and the exploit builders doing their job, entirely
black-box.

### The methodology check: OWASP vuln-class coverage — 14 / 14 (F1 0.95)

A separate, easier run confirms the workflow end to end: Basilisk found and
confirmed all 14 OWASP vuln *classes* on Juice Shop (SQLi, DOM/stored/reflected
XSS, broken access control, sensitive data exposure, misconfig, directory
listing, mass assignment, vulnerable components, input validation, SSRF, XXE,
JWT deserialization). This proves the orchestration and scoring are sound — but
Juice Shop is heavily documented, so a high coverage score is partly recall.
That's exactly why the scoreboard number above is the one that counts.

**On comparing to other tools:** run your tool of choice against the same Juice
Shop, score it the same way, and compare — `benchmark_compare` (coverage) and the
scoreboard both give like-for-like numbers. Published figures we didn't measure
aren't in this README; an honest, reproducible number beats a marketing table.

## Get an API key

Basilisk is multi-provider — you only need a key for the one(s) you want. Set the active provider and key in **Settings → Backends**.

| Provider | Get a key | Notes |
| --- | --- | --- |
| **SiliconFlow** | <https://cloud.siliconflow.com/account/ak> | **Default.** Big open models (DeepSeek, Qwen, Kimi) + SenseVoice STT |
| **Groq** | <https://console.groq.com/keys> | Blistering speed, generous free tier. Whisper STT. Keys look like `gsk_...` |

Keys live only in `~/.config/kali/settings.json` — they never go anywhere but the provider's own API.

<br>

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                       kali.py  (UI)                       │
│            GTK4 + libadwaita · chat, cards, voice         │
└───────────────┬───────────────────────┬──────────────────┘
                │                       │
      ┌─────────┴────────┐   ┌──────────┴───────┐   ┌──────────────┐
      │  kali_core.py    │   │  kali_persona.py │   │ kali_voice.py│
      │ providers/router │   │ system prompt    │   │ STT + TTS    │
      │ 75+ agent tools  │   │ + immutable      │   │ (provider-   │
      │ web · github     │   │   guardrail      │   │  aware ASR)  │
      │ brave · chat DB  │   └──────────────────┘   └──────────────┘
      └──┬────────┬───┬──┘
         │        │   │
   ┌─────┴───┐ ┌──┴───┴────────┐
   │kali_    │ │ kali_ledger.py│  tamper-evident evidence ledger
   │safety.py│ │ (JSONL+SHA256)│  (every command, hashed)
   │hard auto│ └───────────────┘
   │-run floor (structural, evasion-resistant, setting-independent)
   └─────────┘
         │
   ┌─────┴───────────────────────────────────────────────────────┐
   │  kali_ext/  (optional sidecar — off by default, 17 modules)  │
   │  memory · skills · sandbox · foresight · mcp · verify · reach │
   │  worker · headroom · pentest · codescan · engage · bench ·    │
   │  extman · juiceshop · xbow                                    │
   └─────────────────────────────────────────────────────────────┘
```

Provider stack: **SiliconFlow / DeepSeek** primary with a **Groq** fallback. The router reads your active provider and model live, and fails over to your next backend on a degraded response.

<details>
<summary>Development &amp; test suites</summary>

<br>

```bash
git clone https://github.com/the-priest/Basilisk.git kali && cd kali
python3 kali.py                    # run from source

# offline test suites (stdlib only — no display, no keys, no network)
python3 tests/test_kali.py         # core: safety floor, settings, self-edit, ChatStore, ledger, CVE chain, Nuclei, reflection, memory, MCP screen
python3 tests/test_codescan.py     # code audit: every scanner parser, cross-tool triage/dedup, secret redaction
python3 tests/test_writeup.py      # exploitation narrative: ledger-grounded steps, secret redaction, honesty on thin input
python3 tests/test_headroom.py     # token savings: protocol safety, signal preservation, compression ratio, fail-safe
```

For per-machine persona tweaks that survive upgrades, use **Settings → Persona → Custom addendum** — direct edits to `kali_persona.py` are replaced on the next `install.sh` run.

</details>

<br>

---

## What Basilisk will *not* do

- **Destroy your system or its storage — ever.** Disk/FS wipes, recursive root/`$HOME` deletes, fork bombs and raw block-device writes are *refused outright* — hard-blocked before any dialog, in every mode (including autonomous), even via quoting / `$IFS` / `bash -c` tricks. No "Run anyway", no setting to disable it.
- **Be an always-on autonomous fleet agent.** Autonomous execution is the default *within a session you start and stop* — you can turn it on, walk away, and come back to results, but it's not a background daemon roaming your machines on its own, and **Stop halts it instantly**. Destructive commands are refused even here.
- **See your sudo password**, or reach private content it hasn't been given a token for.
- **Invent facts about your machine.** Hardware and system state are read with a tool, not guessed.
- **Generate standalone weaponized malware.** Writing and running exploits against *authorized, in-scope* targets is the whole point, and it does exactly that — but it won't churn out reverse-shell binaries, self-propagating implants, ransomware or persistent backdoors, and the irreversible/destructive class can never run through it at all.

<br>

---

<div align="center">

## License

**MIT.** Take it, fork it, ship it.

## Credits

Forged by **The Priest** ⟁

*A dragon that lives on your machine, answers only to you, and never forgets where the bodies are buried.*

</div>
