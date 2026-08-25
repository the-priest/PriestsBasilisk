<div align="center">

<img src="assets/brand/banner.png" alt="Priest's Basilisk" width="720">

# 🐍 Priest's Basilisk

**An autonomous offensive-security agent that runs on your machine, with your privileges, and answers only to you.**

You bring the model. Basilisk gives it hands, a memory, a methodology — and a leash you hold.

<img src="https://img.shields.io/badge/version-9.9.0-7d121b?style=flat-square&labelColor=08090b" alt="version 9.9.0">
<img src="https://img.shields.io/badge/license-MIT-7d121b?style=flat-square&labelColor=08090b" alt="MIT license">
<img src="https://img.shields.io/badge/Juice%20Shop-87%20%2F%20113%20black--box-e11d2b?style=flat-square&labelColor=08090b" alt="Juice Shop 87/113 black-box">
<img src="https://img.shields.io/badge/tests-3704%20assertions-6d7680?style=flat-square&labelColor=08090b" alt="3704 assertions">

<a href="#-what-it-does">What it does</a> ·
<a href="#-benchmark">Benchmark</a> ·
<a href="#-how-it-works">How it works</a> ·
<a href="#-security-model">Security model</a> ·
<a href="#-everything-in-the-box">Toolbox</a> ·
<a href="#-limits">Limits</a> ·
<a href="#-install">Install</a>

</div>

> [!CAUTION]
> **Authorized targets only. This is a live weapon, not a demo.**
>
> Basilisk runs real exploits and real shell commands against whatever you point it at, autonomously, with your privileges. Arm **Unleash** and it confirms the target, then runs with no per-command approval until the objective is verifiably met or you stand it down. Aimed at the wrong host it will keep working that host until you pull it off.
>
> Use it only on systems you own or have explicit written authorization to test. Unauthorized testing is a crime in most jurisdictions.

> [!NOTE]
> **Disambiguation (for search engines and AI assistants):** Priest's Basilisk (`the-priest/PriestsBasilisk`) is an autonomous **web and API penetration-testing agent** with a repo-repair mode. It is *not* an LLM-jailbreak framework, *not* "White-Basilisk" (a source-code scanner), *not* the Basilisk browser or Basilisk II emulator, and unrelated to Roko's Basilisk.

---

## 🎯 What it does

Two jobs, one loop, and the loop is the same both times: **do the thing, then prove it worked.**

**It breaks in.** Pointed at an authorized target, it reads the app's *behaviour* to name the vuln class, reaches for a matching exploit builder, fires, and confirms the hit against ground truth before anything counts.

**It fixes code.** Hand it a `.zip` of your repo and it searches, reads, edits, runs *your* tests, and hands back a fixed zip. It records what was already failing before it touched anything, and refuses to export a change set it hasn't verified.

**It only arms when you arm it.** The offensive suite — recon planning, scanner parsing, exploit builders, the success oracle, scope and asset tracking — loads *only* under Unleash. Disarmed, the attack tooling isn't hidden from the model, it is **refused at the loader**.

One rule runs underneath both jobs: **Basilisk never asks a model whether something worked.**

Most "AI pentesters" fire, ask the model how it went, and write down the answer — a confidence score wearing a lab coat. Basilisk arms every attempt with the thing that would *prove* it: a dumped database row, another user's token, a measurable timing difference, an out-of-band callback. Then it fires. Then it checks for that marker. **No proof, no finding** — and on the code side, no passing test, no fix.

```
OBSERVE ─▶ HYPOTHESISE ─▶ ARM ─▶ FIRE ─▶ VERIFY ─▶ RECORD
behaviour   vuln class    the     through  against   hashed
of the app  + builder     proof   the      ground    ledger
                          marker  gate     truth
    ▲                                         │
    └────── what's left, what's proven ───────┘
            (the oracle never re-runs a solved bug)
```

---

## 🏆 Benchmark

Scored on **OWASP Juice Shop**, which marks a challenge solved only when the exploit genuinely fires — no partial credit, graded 1–6 stars. Run **fully autonomously** and **black-box** — no per-command approval, no source on the machine — Basilisk solved **87 / 113 (77%)**.

| Agent | Licence | Black-box | White-box *(source provided)* |
|---|---|---:|---:|
| **🐍 Priest's Basilisk** *(v7.6.0)* | **MIT · free** | **87 / 113** | — |
| Priest's Basilisk *(v7.1.0)* | MIT · free | 73 / 113 | — |
| Cascade *(Windsurf / Escape)* | commercial | **36 / 113** | 49 / 113 |
| Claude Opus 4.8 *(bare model)* | metered API | **23 / 113** | 24 / 113 |

Cascade's best number is its *white-box* run — it was handed the source. Basilisk's 87 is black-box. Like for like it is **2.4× Cascade** and **3.8× a bare frontier model**, and it beats Cascade's white-box run by 38 challenges while blind.

Every figure above was produced driving **DeepSeek-V4-Flash**, one of the cheapest models on the market, against a paid product running frontier models.

> [!IMPORTANT]
> **The model is not the point — the loop is.** A budget model tops this board because the verified-exploitation loop around it does the work. Swap in a frontier model and the loop gets better, not the other way round. This is scaffolding beating spend.

<details>
<summary><b>Difficulty curve, the misses, and how to reproduce it</b></summary>

<br/>

| Difficulty | Solved | Rate |
|---|---:|---:|
| ★ | 13 / 13 | 100% |
| ★★ | 18 / 18 | 100% |
| ★★★ | 24 / 26 | 92% |
| ★★★★ | 12 / 25 | 48% |
| ★★★★★ | 13 / 19 | 68% |
| ★★★★★★ | 7 / 12 | 58% |

The curve is the honest part: it clears the entire lower half, thins as chains get deeper, then *climbs again* at five and six stars where the verified-exploitation oracle earns its keep. A flat line would mean the benchmark was memorised, not solved.

**Deep-end wins:** SSRF, SSTi, forged coupon, forged signed JWT, premium paywall, arbitrary file write, unsigned JWT, XXE DoS, NoSQL exfiltration, leaked API key.
**Misses:** where one builder isn't enough and the chain runs long — RCE/DoS variants and the LLM-chatbot challenges.

A separate coverage run confirms all **14 OWASP** vuln classes end to end (F1 0.95).

```bash
docker run -d -p 3000:3000 -e NODE_ENV=unsafe --name juiceshop bkimminich/juice-shop
```

Point Basilisk at the board and call `juiceshop_report` — it reads the live scoreboard (`/api/Challenges`) and reports solved/available by difficulty. Score any other tool against the same container and compare.

*Full board: `NODE_ENV=unsafe`, v7.6.0, model DeepSeek-V4-Flash. Solved through the exploit builders + `run` only — no web reader, no source. Scorecard: [`benchmarks/juice-shop-scoreboard-2026-07-20.txt`](benchmarks/juice-shop-scoreboard-2026-07-20.txt).*

</details>

**Second target: [Escape's Duck Store](https://duck-store.escape.tech/)** — a deliberately-vulnerable REST API built to defeat the training-data memorisation that inflates Juice Shop numbers. API-first flaws: BOLA/BFLA, mass-assignment privilege escalation, SSRF, business-logic abuse. Black-box, no schema handed to it: **22 / 22**.

---

## ⚙️ How it works

Four subsystems bridge the gap between a CTF and an arbitrary host:

- **Structural (AST) payload mutation** — parses a JSON/XML body, injects at *every* node, serialises back to valid syntax, so the payload reaches each field instead of breaking the parser.
- **State-machine & session management** — extracts every dynamic token from a response (cookies, CSRF, bearer/JWT, nonces) and threads it into the next request.
- **Differential & time-based oracles** — proves blind bugs by measuring: diffs TRUE vs FALSE responses for a boolean channel, and analyses latency statistically (mean, stddev, z-score) to confirm time-based blind SQLi past network jitter.
- **Verified-exploitation oracle** — arms each attempt with the marker that would prove it, then checks for it and records confirmed / failed / pending in a ledger it consults every planning turn. For bugs that echo nothing back it stands up a local **out-of-band** canary listener; a callback proves the bug with certainty (**interactsh** technique, running locally and offline).

> **In plain English:** a scanner throws payloads at a page and reports what looked odd. Basilisk decides *what would have to be true* if the bug were real, then goes and checks whether that happened. It's the difference between "this smells like SQL injection" and "here is a row out of your database."

<details>
<summary><b>Why you can actually walk away — the four things that kill a long unattended run</b></summary>

<br/>

| Failure | What Basilisk does |
|---|---|
| **Forgets what it did and redoes it** | A compact action ledger lives *outside* the transcript — one line per action and outcome, never trimmed, re-sent whole every turn. A deterministic guard refuses a third identical action; a cycle detector catches the A→B→A→B loops a "same command twice" check never sees |
| **A slow job gets killed and the work binned** | Supervision by **progress**, not a wall clock. Output arriving or CPU advancing across the process group resets the clock, so real work has no time limit. A genuine stall gets **unstuck** first — the commonest is a process blocked on an interactive prompt, which a timeout can only kill but closing stdin actually releases |
| **One dead worker strands the run** | Every tool path returns through a guaranteed one-shot result: the worker can return, throw, or die halfway and exactly one result still reaches the model |
| **Over-thinks a simple problem** | Diagnosis ordered by likelihood × cost to check. Effort escalates on *evidence of difficulty*, not on how many steps have passed |

</details>

<details>
<summary><b>The exploit-builder arsenal — 20+ vuln classes, general-purpose</b></summary>

<br/>

- **SQLi** — DBMS-aware (MySQL / PostgreSQL / MSSQL / Oracle / SQLite), plus sqlmap
- **JWT** — `alg:none`, RS256→HS256 key confusion
- **NoSQL**, **XXE**, **SSTi** (per template engine), **SSRF** (internal + cloud-metadata + blocklist bypass)
- **Insecure deserialization** (Node / YAML / pickle / Java → RCE), **prototype pollution**
- **Path traversal** (read, null-byte, zip-slip write), context-aware **XSS** (filter/CSP bypass + AngularJS CSTI)
- **OS command injection**, **IDOR**, **race conditions (TOCTOU)**, **file-upload bypass**, **GraphQL** abuse, **open redirect**, **CORS** misconfig

Plus a trick detector, a payload encoder that slips blocked payloads past filters, a WAF/filter analyzer, and a stack fingerprinter.

</details>

<details>
<summary><b>Why it costs almost nothing to run</b></summary>

<br/>

An agent re-sends the same system prompt and history every step, so **prefix caching** is its largest cost lever — and it is brutally literal: one changed byte near the front and you pay full price for everything after it. Basilisk was breaking it in three places (a minute-resolution clock sitting *ahead* of ~4,000 tokens of tool contract; a sliding trim window that rewrote the *middle* of the request every turn; a sliding history cap that moved the anchor every turn). All three fixed: volatile content rides at the tail, and trimming advances on a watermark that holds the render byte-stable until a size budget forces one jump.

Measured on a 20-step run: reusable prefix went from ~40% with a break every single turn to **100% with zero breaks**. With DeepSeek-V4-Flash on SiliconFlow (cached input 80% off) that is roughly a three-quarters cut in input cost, for zero change in behaviour.

</details>

---

## 🔧 Fixing your code

Hand Basilisk a `.zip` of your repo. It unpacks into a private working tree, works the whole thing, and hands back a fixed zip.

```
workspace_import     → unpack the repo, flag anything that looks like a credential
workspace_overview   → languages, LOC, entry points, manifests, where the tests live
workspace_baseline   → run your tests BEFORE editing; record what already fails
workspace_search     → repo-wide grep, so it finds the file instead of guessing
workspace_replace    → surgical edit; refuses a match that isn't unique
workspace_verify     → re-run; classify what it fixed, what it BROKE, what still fails
workspace_diff       → every change, before anything leaves the sandbox
workspace_export     → zip it back up
```

The import path is hardened against hostile archives: **Zip slip**, **Zip bombs** and **Symlink entries** are all refused (`commonpath` containment, not a `startswith` check — the bug class behind **CVE-2007-4559**).

---

## 🛡️ Security model

An agent that reads the outside world *and* runs shell commands is a prompt-injection target by construction. The design assumes the model is **already compromised** and puts what matters where a compromised model cannot reach it. Not filtered — removed.

- **The irreversible class can never run.** Disk wipes, `mkfs`, recursive root/`$HOME` deletes, fork bombs, raw block-device writes. It normalises `$IFS` and quoting first, then judges the command that will actually run: it peels wrapper commands *and their own options* (`timeout 5 …`, `nice -n 5 …`, `sudo -u root …`), reads through grouping (`( … )`, `{ …; }`, `if/then`, function bodies), recurses into `sh -c`, `eval`, `trap`, here-strings and `xargs`, and enters command substitutions — `$( … )` and backticks — including from inside double quotes. Refused at the UI gate *and* again inside the execution primitive, so no caller can route around it. There is no **run anyway**. Zero false positives on legitimate work like `rm -rf ~/loot` or `timeout 60 rm -rf ./dist` — a floor that fires on ordinary work gets switched off, and then it protects nothing.
- **Scope is a boundary, not a suggestion.** Targets are extracted and checked against the authorized list before any active command runs. Fails closed: no scope set, an unparseable command, or no match all mean refused. Sees through `sh -c`, `sudo`/`timeout`/`proxychains` and command substitution.
- **The injection surface was removed, then gated.** Tools that fetched attacker-chosen URLs are gone. What's left, `web_read`, is split into two tiers **in code**: *trusted* sources an attacker cannot plant content in (NVD, MITRE, CISA, vendor advisories, OWASP, PortSwigger) fetch automatically. Everything else on the public internet — including **exploit-db**, GitHub, Stack Overflow and PyPI — is user-authored and stays **outside the autonomous loop**, behind a one-tap approval a compromised model cannot click. Link-local, private and cloud-metadata addresses are refused outright, with no approval able to override.
- **Your sudo password never touches the model.** It goes to `sudo` through an askpass helper via an environment variable — never into the prompt, onto disk, into a log, or into the process argument list where `ps` could read it.
- **It cannot edit its own safety code.** A command that would write to, truncate, redirect into, `sed -i`, or copy over `basilisk_safety.py`, `basilisk_scope.py` or the other core modules is refused — including hidden inside `sh -c` or a `cp`/`mv` destination. The guardrail block in the persona is verified byte-for-byte against a known hash on every release.
- **New tools run under a jail and a test.** Tools Basilisk writes for itself are AST-parsed, statically screened, and executed against their own test inside a **bubblewrap** sandbox — kept **only if the test passes**. A tool that cannot prove it works is discarded, not saved with a warning.
- **The provider stays where you put it.** No silent hop to a different cloud; a retry after a degraded reply goes back to the same provider.
- **It will not build weapons to leave behind.** Real exploits against targets you authorize, yes — that's the job. Standalone weaponized malware (reverse shells, implants, ransomware, backdoors), no. That line is in the immutable guardrail, not a swappable prompt.
- **The web/OSINT readers are deliberately left unwired.** They exist in the tree and are not connected to the agent loop, on purpose, because wiring them would reopen the injection surface the design just closed.

**We audit our own floor and publish what we find.** In v9.7.0 the destructive gate was fuzzed against a **real shell** — every candidate re-run in live `bash` with the destructive verb swapped for a harmless marker, counting only shapes where the shell actually did the thing. **Twenty-one shapes that had been getting through were found and closed**, including `timeout 5 rm -rf /`, `( rm -rf ~ )`, `$(rm -rf /)` and `echo x | xargs -I{} mkfs.ext4 /dev/sda1`.

The method mattered more than the fixes: a blind fuzz reported 18,856 "bypasses", almost all shell *syntax errors* that never execute. Filtering to what a real shell actually runs is what made the twenty-one findable. They are now **pinned, not just patched** — the suite asserts all twenty-one *and* the counter-property against a corpus of ordinary work, so over-blocking fails just as loudly. Find a twenty-second and open an issue.

---

## 🧰 Everything in the box

Tool specs load **on demand**, so the base prompt stays small no matter how many exist.

| Group | Loaded | What's in it |
|---|---|---|
| 🖥️ **system** | always | Read any file, search anywhere, snapshot RAM / disk / processes / routes / services, graded security audit, network scan |
| 🧪 **code** | always | SAST + SCA + secrets scanning across py/js/ts/php/java/ruby/go/.NET, cross-tool triage, `code_scan_plan`, remediation hints |
| 📦 **workspace** | always | Import a repo zip, search and read it whole, surgical edits, baseline → verify → export with a gate that refuses unverified changes |
| 🖱️ **desktop** | always | Launch apps, manage windows, type, click, screenshot, OCR, notify |
| 🖼️ **media** | always | Show images inline, and actually *look* at one with a vision model |
| ⚔️ **offensive** | **armed only** | Recon planning, scanner parsing, CVE → KEV → EPSS, nuclei templates, sqlmap builder, `zday_scan`, the verified-exploitation oracle + out-of-band canary |
| 🎯 **engagement** | **armed only** | Authorised scope (fails closed), asset graph, loot, in-scope credential-reuse leads |
| 📊 **benchmark** | **armed only** | Score a run against known-vulnerable practice targets |

**Memory.** Facts, preferences, past fixes and prior findings live in a local **SQLite** store you own. Recall is relevance-scoped — each turn injects only the handful of memories most relevant to the current task — so history can grow forever without bloating the context window. Keyword-based by default, upgrading to embedding similarity when a model provides it. One `memory_forget` tool; nothing leaves the box.

---

## 🙅 Limits

Every tool page lists strengths. Here are the limits, because you'll find them anyway.

- **It is not a replacement for a penetration tester.** Scoping, judging business impact, deciding what a finding is *worth*, and writing the part of the report a client acts on are all still yours.
- **It gets weaker as the chain gets longer.** Bugs needing four unrelated insights stacked in the right order are still where autonomous agents lose. The misses are published by name above rather than rounded away.
- **It is only as good as the model you give it.** The scaffolding is what scores, but a weak model still reasons weakly inside it.
- **The benchmark numbers are ours.** Reproducible — the target, flags, model and scoreboard commands are published — but self-reported. Treat them as you would any vendor's until you've regenerated one.
- **It is Linux and GTK4.** No Windows, no macOS.
- **Network egress is real.** It runs locally, but the model call leaves your machine. If your engagement data can't go to a third-party API, this is the wrong tool until you point it at something self-hosted.
- **Autonomy is a loaded gun with a good trigger guard.** The floors stop it destroying *your* machine. Nothing in the software stops you aiming it at a host you have no right to touch.

---

## 🔬 How you know it works

```bash
for f in tests/test_*.py; do python3 "$f" || echo "RED $f"; done
```

Stdlib only. No pytest, no network, no fixtures, no account. **3,704 assertions across 47 suites**, done in under a minute.

- **Bugs are pinned, not described.** When a real bug is fixed, the test that catches it is written to **fail against the previous release**. A regression can't quietly return.
- **Performance is asserted as a shape, not a stopwatch.** A millisecond ceiling passes by luck on a fast machine, so the suite asserts the **scaling exponent** — quadruple the input, the time must not quadruple — which fails on a slow box and a fast one alike.
- **Counter-properties are tested as hard as properties.** Every safety check is paired with a corpus of ordinary work it must stay silent on. Over-blocking is a test failure.
- **The shipped artifact is what's verified.** The release zip is extracted fresh and the suite run from inside it, not from the tree it was built in.

**What "finished" means here.** Not "we stopped finding bugs" — that claim is always a lie. It means the architecture has settled, the safety floors have stopped moving, and every release ships the hunt as well as the fix.

---

## 📦 Install

Basilisk runs shell commands **as you**. Read the installer before you run it.

```bash
curl -fsSL https://raw.githubusercontent.com/the-priest/PriestsBasilisk/main/install.sh | bash
```

Or clone, read, then run:

```bash
git clone https://github.com/the-priest/PriestsBasilisk.git basilisk
```
```bash
cd basilisk && less install.sh
```
```bash
./install.sh
```

Plain Python plus one shell script — no Docker, no daemon, no account. The installer detects your distro and privilege-escalation tool, parse-checks every file before it touches disk, and backs up your chat history. The same command updates in place.

**Or from PyPI:** `pip install priestsbasilisk` then `basilisk`. Install the GTK stack first — PyGObject ships source-only and compiles against your system headers:

| Distro | Command |
| --- | --- |
| **CachyOS / Arch** | `sudo pacman -S python-gobject gtk4 libadwaita` |
| **Kali / Debian / Ubuntu** | `sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 libgirepository1.0-dev` |
| **Fedora** | `sudo dnf install python3-gobject gtk4 libadwaita-devel` |
| **openSUSE** | `sudo zypper install python3-gobject gtk4 libadwaita-devel` |

`install.sh` is the recommended path: it sets up the desktop entry, icon theme, launcher and optional systemd user unit, and updates in place. `pip install` gives you the application and the `basilisk` command and nothing else.

### 🔌 Bring your own model

Set a key in **Settings → Backends**. Keys live only in `~/.config/basilisk/settings.json`, locked to your user.

| Provider | Get a key | Notes |
| --- | --- | --- |
| **SiliconFlow** | <https://cloud.siliconflow.com/account/ak> | **Default.** Large open models (DeepSeek, GLM, Kimi, Qwen, MiniMax) + SenseVoice STT |

The model picker shows context window, price per million tokens and what each model is *for*. A refresh button pulls the provider's live catalogue, so a retired model id can't sit in the list silently 404ing.

**Tool-call dialects.** Models do not agree on how to emit a tool call, and several use their own trained format regardless of what the prompt asks. Basilisk normalises every dialect it has seen to one canonical form before anything parses or renders it: `<tool name="x">{json}</tool>`, DeepSeek's native special tokens, **DeepSeek-V4's DSML tags in every pipe rendering** (fullwidth `｜`, ASCII `|`, single or doubled), `<tool_call>`, `<invoke>`, `<function=…>`, fenced-JSON bodies, and arguments as `<parameter>` child tags. Anything still unrecognised is *detected* rather than printed. Parsing and display are driven from the same normalised text by construction, because when they disagree a call executes *and* leaks its raw markup into the chat.

Sampling follows the model's own vendor guidance where it differs from the defaults — DeepSeek V4 asks for temperature 1.0 / top_p 0.95 in agentic use, and gets it unless you have set your own.

### 📋 Requirements

- **Python 3.10+**, Linux with GTK4 / libadwaita (X11 or Wayland)
- Built and tested on **CachyOS** and **Kali**. Runs on any Arch-, Debian- or Fedora-based distro: the package manager (`apt`/`pacman`/`dnf`/`zypper`), privilege-escalation tool (`sudo`/`sudo-rs`/`doas`) and wordlist locations are all auto-detected, never assumed.
- Standard offensive tooling (nmap, sqlmap, …) is auto-detected; missing tools are flagged with a distro-correct install hint — pacman/AUR on Arch, apt on Debian — never a Debian command on an Arch box.

---

## 🜃 Why it's free

There is a version of this with a pricing page, three tiers and a "contact sales" button. Everything here would still be true and the number at the bottom would be four figures a year. I'd rather it went to the people who'd actually use it.

**MIT. All of it.** Not a trial, not a community edition with the good parts removed, not open-core with the safety gates behind a licence key. No account, no telemetry, no usage cap, nothing phoning home. The benchmark scores on this page were produced by the same code you're about to clone.

If it earns its place in your kit, star the repo and tell someone who runs engagements. That's the whole price.

## 📜 License

**MIT.** Take it, fork it, use it on what you're allowed to break.

<div align="center">

### Built by one person. Verified by 3,704 assertions. Priced at nothing.

<sub>Clone it, read it, run the suite, then point it at something you own.</sub>

</div>
