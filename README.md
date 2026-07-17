<div align="center">

<img src="banner.png" alt="Basilisk" width="820">

# Basilisk

**An autonomous penetration-testing agent that runs as a native Linux desktop app on your own machine.**

You bring the model; Basilisk gives it hands — a full offensive toolchain, shell and desktop control, a verified-exploitation loop, a tamper-evident evidence ledger, and a hard safety floor it cannot cross. It runs locally and answers only to you. The only thing that leaves your machine is the API call to the model you chose.

![version](https://img.shields.io/badge/version-7.5.5-7d121b?style=for-the-badge&labelColor=08090b)
![license](https://img.shields.io/badge/license-MIT-7d121b?style=for-the-badge&labelColor=08090b)
![platform](https://img.shields.io/badge/Linux-X11%20%7C%20Wayland-6d7680?style=for-the-badge&logo=linux&logoColor=white&labelColor=08090b)
![python](https://img.shields.io/badge/python-3.10+-6d7680?style=for-the-badge&logo=python&logoColor=white&labelColor=08090b)
![mobile](https://img.shields.io/badge/runs%20on-NetHunter-6d7680?style=for-the-badge&labelColor=08090b)
![benchmark](https://img.shields.io/badge/Juice%20Shop-81%2F113%20black--box-7d121b?style=for-the-badge&labelColor=08090b)
![api-benchmark](https://img.shields.io/badge/Duck%20Store%20API-22%2F22%20black--box-7d121b?style=for-the-badge&labelColor=08090b)

</div>

---

## What it is

Basilisk is a GTK4/libadwaita desktop application (Python, ~46k LOC) that turns an off-the-shelf LLM into a working pentester. Point it at an authorized target and it runs the full engagement end to end — recon, exploitation across every web-vuln class, verification, and a reproducible write-up — turn after turn, on its own, until the objective is confirmed or you stop it.

It is **provider-agnostic** (SiliconFlow, Groq), runs **black-box** (no target source required), and keeps a **hashed receipt for every command** it executes. It also audits your own code across ten scanners, hardens a host, and drives your shell and desktop. Full tool reference: [`BASILISK_MANUAL.md`](BASILISK_MANUAL.md).

## Install

Basilisk runs shell commands **as you**. Read the installer before you run it.

**One line:**

```bash
curl -fsSL https://raw.githubusercontent.com/the-priest/Basilisk/main/install.sh | bash
```

**Or clone, read, run:**

```bash
git clone https://github.com/the-priest/Basilisk.git basilisk
```
```bash
cd basilisk
```
```bash
less install.sh
```
```bash
./install.sh
```

Plain Python plus one shell script — no Docker, no daemon, no account, nothing phoning home. The installer auto-detects your distro, parse-checks every file before it touches disk, and backs up your chat history. The same command updates in place. Test suites are stdlib-only, so you can run them before trusting it with anything:

```bash
for t in tests/test_*.py; do python3 "$t"; done
```

## Benchmark

The claim is only worth the number you can regenerate. Basilisk is scored against **OWASP Juice Shop**, which marks a challenge solved only when the exploit genuinely fires — no partial credit, no checklist to recall, graded by difficulty (1–6 stars). It's the comparable benchmark the security community already uses.

Turned loose **fully autonomously** and **black-box** — no per-command approval, no source on the machine — Basilisk solved **81 of 113 challenges (71.7%)**.

*Full board, `NODE_ENV=unsafe`, v7.5.3, target `172.17.0.2:3000` (Docker). Solved through the exploit builders + `run` only — no web reader, no source. Scorecard: [`benchmarks/juice-shop-scoreboard-2026-07-17.txt`](benchmarks/juice-shop-scoreboard-2026-07-17.txt).*

| Difficulty | Solved | Rate |
|---|---|---|
| ★ | 13 / 13 | 100% |
| ★★ | 16 / 18 | 89% |
| ★★★ | 21 / 26 | 81% |
| ★★★★ | 11 / 25 | 44% |
| ★★★★★ | 13 / 19 | 68% |
| ★★★★★★ | **7 / 12** | **58%** |

The curve is the honest part: it clears the easy and mid tiers almost completely, then thins as the chains get deeper — the shape a real tool should have. It now takes **7 of 12 6-star** challenges (SSRF, SSTi, Forged Coupon, Forged Signed JWT, Login Support Team, Premium Paywall, Arbitrary File Write) and **13 of 19 5-star** (unsigned JWT, XXE DoS, NoSQL exfiltration, three password resets, frontend typosquatting, retrieve blueprint, leaked access logs/API key, and more). Misses cluster where one builder isn't enough and the chain runs long: RCE/DoS variants, NoSQL manipulation/DoS, and the LLM-chatbot challenges (prompt injection, system-prompt extraction).

**Context.** Published work generally puts fully-autonomous LLM pentest agents around **20–30%** on comparable tasks, so ~72% black-box on the full board sits well above that. The same board, scored the same way (other agents' figures are from the earlier v6-era session, not re-run):

| Agent | Black-box | White-box *(source provided)* |
|---|---|---|
| **Basilisk** *(v7.5.3)* | **81 / 113** | — |
| Basilisk *(v7.1.0)* | 73 / 113 | — |
| Basilisk *(v6.0.0)* | 58 / 113 | — |
| Cascade *(Windsurf)* | 36 / 113 | 49 / 113 |
| Claude Opus 4.8 | 23 / 113 | 24 / 113 |

Progression, same scoring: **51 → 58 (v6.0.0) → 73 (v7.1.0) → 81 (v7.5.3)**. The gains over v7.1.0 are concentrated in the deep end — 5-star jumped 42% → 68% and 6-star 33% → 58% — as the oracle stopped re-running solved bugs and the verified-exploitation loop got sharper about what was left. A separate coverage run confirms all **14 OWASP vuln classes** end to end (F1 0.95).

**Reproduce it:**

```bash
docker run -d -p 3000:3000 -e NODE_ENV=unsafe --name juiceshop bkimminich/juice-shop
```

Then point Basilisk at the board and call `juiceshop_report` — it reads the live scoreboard (`/api/Challenges`) and reports solved/available by difficulty. Score any other tool against the same container and compare.

### Second target: Escape Duck Store (API security)

Juice Shop is a web app; the second benchmark is a **deliberately-vulnerable REST API** — [Escape's "Duck Store"](https://duck-store.escape.tech/). The planted flaws are API-first: broken object- and function-level authorization (BOLA / BFLA), mass-assignment privilege escalation, SSRF, and business-logic abuse, rather than the web-app classes Juice Shop leans on. Run **fully autonomously** and **black-box** against the live API surface — no schema handed to it — Basilisk confirmed **22 / 22**.

*Classes covered: BOLA / IDOR · BFLA · mass assignment · SSRF · SQLi · stored XSS · broken auth · file upload · excessive data exposure · business logic. Scoring is class-based and target-agnostic (`benchmark_score` grades findings against a known set, or your own), so the same rig scores any API.*

## How it works

Basilisk runs a **closed loop**, not a payload spray. It reads a target's *behaviour* to identify the vuln class, reaches for the matching **exploit builder**, fires it, and **confirms the hit against ground truth** before moving on. Every attempt and verdict lands in an exploitation oracle, so the loop never re-runs a solved bug and gets sharper about what's left.

**Exploit builders** — general-purpose generators, parameterised for any authorized target (not Juice-Shop-bound toys):

- **SQLi** — DBMS-aware (MySQL / PostgreSQL / MSSQL / Oracle / SQLite), plus sqlmap
- **JWT** — `alg:none`, RS256→HS256 key confusion
- **NoSQL**, **XXE**, **SSTi** (per template engine), **SSRF** (internal + cloud-metadata + blocklist bypass)
- **Insecure deserialization** (Node / YAML / pickle / Java → RCE), **prototype pollution**
- **Path traversal** (read, null-byte, zip-slip write), context-aware **XSS** (filter/CSP bypass + AngularJS CSTI)
- **OS command injection**, **IDOR / broken access control**, **race conditions (TOCTOU)**, **file-upload bypass**, **GraphQL** abuse, **open redirect**, **CORS** misconfig

**Analysis layer** — a trick detector (hidden encodings, HTML-comment hints, client-side-only "protection," stale tokens, rate limits), a payload encoder that slips blocked payloads past filters (URL / double-URL / base64 / unicode / mixed-case), a WAF/filter analyzer, and a stack fingerprinter so it picks the payload that fits.

**Four subsystems bridge the gap between a CTF and an arbitrary host:**

- **Structural (AST) payload mutation** — parses a JSON/XML body, injects at *every* node, and serialises back to valid syntax, so the payload actually reaches each field instead of breaking the parser.
- **State-machine & session management** — extracts every dynamic token from a response (cookies, CSRF, bearer/JWT, nonces) and threads it into the next request, reaching steps a stateless scanner never gets to.
- **Differential & time-based oracles** — proves blind bugs by *measuring*: diffs TRUE vs FALSE responses (length, status, DOM, similarity) for a boolean channel, and analyses latency statistically (mean, stddev, z-score) to confirm time-based blind SQLi/RCE past network jitter.
- **Verified-exploitation oracle** — before firing, Basilisk *arms* an attempt with the marker that would prove it (a dumped row, another user's token, a status, a measurable difference); after, it *checks* the response and records **confirmed / failed / pending** in a ledger it consults every planning turn. For blind bugs that echo nothing back (blind SSRF/RCE/XXE, OOB SQLi) it stands up a local **out-of-band canary listener** — the payload carries a unique callback URL, and a hit proves the bug with certainty (interactsh technique, running locally and offline).

When an approach stalls, it **researches** — pulls the exact technique from a vetted source and applies it on the next move. It clears easy wins first, then goes deep on hard chains, hashing every command into the evidence ledger as it goes. You can **walk away**: it survives errors, retries past them, and runs until the objective is *verifiably* done or you press Stop.

## Security model

An agent that reads the outside world *and* runs shell commands is a prompt-injection target. Basilisk removes the doors rather than bolting on a filter.

- **The injection surface was removed, then gated.** The tools that fetched *attacker-chosen* URLs are gone. What's left, `web_read`, reads only from a fixed allow-list split into two tiers **in code**: *trusted* sources an attacker can't plant content in (NVD, MITRE, CISA, vendor advisories) fetch automatically; *community* sources that are user-authored (GitHub, Stack Overflow, PyPI, exploit-db) are held **outside the autonomous loop** — Basilisk raises a one-tap approval request in the notification bell, and a compromised model still can't reach one without your click. Off-list URLs, redirects, and link-local / cloud-metadata addresses are refused.
- **The irreversible class can never run — enforced twice.** A structural detector hard-blocks disk wipes, recursive root/`$HOME` deletes, fork bombs, and raw block-device writes — seeing through quoting, `$IFS`, and `bash -c` tricks a regex misses. It's refused at the UI gate *and* again inside the command-execution primitive, so no caller can route around it. There is no "Run anyway." (Verified against real bypass forms; zero false positives on legitimate work like `rm -rf ~/loot`.)
- **Untrusted input is quarantined.** Anything from outside — a target's response, an MCP result, an analyzed image — passes a deterministic content firewall and is wrapped as *data, never instructions*.
- **Your sudo password never touches the model.** Self-written code runs only in a bubblewrap jail after passing its own test, and Basilisk's own safety code can't be overwritten by a shell command.

All of it is pinned in the test suite. Basilisk writes and runs real exploits against authorized targets — that's the job — but it will not produce standalone weaponized malware (reverse shells, implants, ransomware, backdoors), and the destructive class can never run through it at all.

## Bring your own model

Multi-provider — you only need a key for the one you want. Set it in **Settings → Backends**.

| Provider | Get a key | Notes |
| --- | --- | --- |
| **SiliconFlow** | <https://cloud.siliconflow.com/account/ak> | **Default.** Large open models (DeepSeek, Qwen, Kimi) + SenseVoice STT |
| **Groq** | <https://console.groq.com/keys> | Very fast, generous free tier, Whisper STT. Keys look like `gsk_...` |

Keys live only in `~/.config/basilisk/settings.json`, locked to your user — they go nowhere but the provider's own API.

## Requirements

- **Python 3.10+**, Linux with GTK4 / libadwaita (X11 or Wayland)
- Runs on desktop Kali and on **NetHunter Pro** (Phosh/Wayland) on a phone
- Standard offensive tooling (nmap, sqlmap, etc.) is auto-detected; missing tools are flagged with an install hint, never assumed

## License

**MIT.** Take it, fork it, use it on what you're allowed to break.
