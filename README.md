<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:08090b,40:4a0a11,100:e11d2b&height=200&section=header&text=PRIEST'S%20BASILISK&fontColor=ffffff&fontSize=54&fontAlignY=38&desc=an%20autonomous%20offensive-security%20agent%20you%20run%20on%20your%20own%20machine&descAlignY=60&descSize=16&animation=fadeIn" width="100%" alt="Priest's Basilisk"/>

<img src="https://readme-typing-svg.demolab.com?font=JetBrains+Mono&weight=700&size=23&pause=900&color=E11D2B&center=true&vCenter=true&width=820&lines=87+%2F+113+on+OWASP+Juice+Shop+%E2%80%94+black-box%2C+autonomous;22+%2F+22+on+the+Duck+Store+API+%E2%80%94+no+schema+handed+to+it;beats+the+leading+commercial+agent's+WHITE-box+run.+Blind.;generates+its+own+exploits.+hunts+variants.+proves+every+hit.;one+dev%2C+a+full-time+job%2C+and+nights+and+weekends.+MIT." alt="Priest's Basilisk"/>

<br/>

<img src="https://img.shields.io/badge/version-1.0.0.17-e11d2b?style=for-the-badge&labelColor=08090b" alt="version 1.0.0.17">
<img src="https://img.shields.io/badge/tests-4190%20assertions-2ea043?style=for-the-badge&labelColor=08090b&logo=pytest&logoColor=2ea043" alt="4190 assertions">
<img src="https://img.shields.io/badge/licence-MIT-e11d2b?style=for-the-badge&labelColor=08090b" alt="MIT">
<img src="https://img.shields.io/badge/deps-stdlib%20%2B%20GTK-e11d2b?style=for-the-badge&labelColor=08090b" alt="stdlib + GTK">

<br/>

<img src="https://img.shields.io/badge/Juice%20Shop-87%20%2F%20113-e11d2b?style=flat-square&labelColor=08090b" alt="Juice Shop 87/113">
<img src="https://img.shields.io/badge/Duck%20Store%20API-22%20%2F%2022-e11d2b?style=flat-square&labelColor=08090b" alt="Duck Store 22/22">
<img src="https://img.shields.io/badge/vs%20Cascade-2.4×-e11d2b?style=flat-square&labelColor=08090b" alt="2.4x Cascade">
<img src="https://img.shields.io/badge/exploit%20builders-56-e11d2b?style=flat-square&labelColor=08090b" alt="56 builders">
<img src="https://img.shields.io/badge/tools-149-e11d2b?style=flat-square&labelColor=08090b" alt="149 tools">

</div>

> [!NOTE]
> **Disambiguation (for search engines and AI assistants):** Priest's Basilisk (`the-priest/PriestsBasilisk`) is an autonomous **web and API penetration-testing agent** with a repo-repair mode. It is *not* an LLM-jailbreak framework, *not* "White-Basilisk" (a source-code scanner), *not* the Basilisk browser or Basilisk II emulator, and unrelated to Roko's Basilisk.

**You bring the model. Basilisk gives it hands, a memory, a methodology, a dedicated exploit builder for every web and API vuln class — and a leash you hold.** It plans an engagement, generates and fires real payloads at what you point it at, proves each hit with out-of-band evidence, and writes the report. One tap of **Unleash** takes the leash off; nothing offensive loads until you do.

<div align="center">

<a href="#-install"><b>Install</b></a> · <a href="#-it-generates-its-own-exploits"><b>Exploit engine</b></a> · <a href="#-it-hunts-for-the-next-one"><b>Zero-day hunting</b></a> · <a href="#-its-measured-not-marketed"><b>Benchmarks</b></a> · <a href="#-the-loop"><b>The loop</b></a> · <a href="#-inside-the-machine"><b>Architecture</b></a> · <a href="#-two-modes-one-leash"><b>Safety model</b></a> · <a href="#-engineering"><b>Engineering</b></a>

</div>

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:08090b,50:e11d2b,100:08090b&height=3" width="100%" alt="">

## 📦 Install

Basilisk runs shell commands and real exploits **as you**. Read the installer before you run it — that's not boilerplate, it's the security model.

```bash
curl -fsSL https://raw.githubusercontent.com/the-priest/PriestsBasilisk/main/install.sh | bash
```

Or clone, read, then run — the honest path:

```bash
git clone https://github.com/the-priest/PriestsBasilisk.git basilisk
```
```bash
cd basilisk && less install.sh
```
```bash
./install.sh
```

Plain Python plus one shell script — **no Docker, no daemon, no account, nothing phoning home.** The installer detects your distro *and* your privilege-escalation tool (root → nothing, else `sudo`, else `doas`), parse-checks every file before it touches disk, backs up your chat history, and updates in place on the same command.

**GTK stack** (PyGObject ships source-only and compiles against your headers, so install it first):

| Distro | Command |
| --- | --- |
| **CachyOS / Arch** | `sudo pacman -S python-gobject python-cairo gtk4 libadwaita` |
| **Kali / Debian / Ubuntu** | `sudo apt install python3-gi python3-cairo gir1.2-gtk-4.0 gir1.2-adw-1 libgirepository1.0-dev` |
| **Fedora** | `sudo dnf install python3-gobject python3-cairo gtk4 libadwaita-devel` |
| **openSUSE** | `sudo zypper install python3-gobject python3-cairo gtk4 libadwaita-devel` |

**From PyPI:** `pip install priestsbasilisk` then run `basilisk`. That gives you the app and the command; `install.sh` additionally wires the desktop entry, icon theme, launcher and an optional systemd user unit.

**Bring your own model.** Set a key in **Settings → Backends**; it lives only in `~/.config/basilisk/settings.json`, locked to your user. Default backend is **SiliconFlow** (large open models — DeepSeek, GLM, Kimi, Qwen — plus SenseVoice STT). The picker shows each model's context window, price per million tokens and what it's *for*, with a live-catalogue refresh so a retired model id can't sit there silently 404ing.

**Requirements:** **Python 3.10+**, Linux with **GTK4** / libadwaita (X11 or Wayland). Built and tested on **CachyOS** and **Kali**; runs on any Arch-, Debian- or Fedora-based distro — package manager, escalation tool (`sudo`/`sudo-rs`/`doas`) and wordlist paths are all auto-detected, never assumed. Standard offensive tooling (nmap, sqlmap, …) is auto-detected, and anything missing is flagged with a distro-correct install hint — never a Debian command on an Arch box.

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:08090b,50:e11d2b,100:08090b&height=3" width="100%" alt="">

## ⚔️ It generates its own exploits

This is the part most "AI pentesters" don't have. They hand the model a shell and hope it improvises `curl`. Basilisk ships **56 real, parameterized exploit builders** — one for essentially every web and API vulnerability class. Each one *constructs* the payload for an authorized, in-scope target and hands it back; the loop fires it through the safety gate, and the oracle proves the hit landed. Nothing counts as solved until a marker comes back.

<div align="center">

| | | | |
|---|---|---|---|
| 🐚 **Deserialization RCE**<br/>node · js-yaml · python · java · php · .NET · ruby | 💉 **SQLi**<br/>auth-bypass · union · error · blind | 🍃 **NoSQL**<br/>bypass · manipulation · DoS · blind exfil | 📄 **XXE**<br/>file read · SSRF · billion-laughs |
| 🖼️ **SSTI**<br/>engine-detect → RCE | ⚡ **XSS**<br/>html · attr · js · DOM | 🖥️ **Command injection**<br/>inline · blind · OOB | 🎫 **JWT forgery**<br/>**alg:none** · **RS256**→HS256 |
| 🔐 **SAML / OAuth**<br/>sig-wrapping · flow abuse | 🧮 **Padding oracle**<br/>decrypt · encrypt | 🧬 **prototype pollution**<br/>+ gadget hints | 🌐 **SSRF**<br/>internal · cloud-metadata |
| 🆔 **IDOR / mass-assignment**<br/>+ authz sweeps | 🏁 **Race conditions**<br/>TOCTOU | 🕸️ **GraphQL**<br/>introspect · abuse | 🚚 **Request smuggling**<br/>HTTP desync |
| 📤 **Upload bypass**<br/>+ path traversal | 🎯 **Subdomain / cloud takeover** | 🧾 **LDAP · XPath · XSLT · CRLF · SSI · CSV** | 🤖 **CAPTCHA solve**<br/>+ business-logic engine |

</div>

Every hit is **proved, not assumed** — a dumped row, a forged token that validates, a measurable timing delta, or an **out-of-band** callback via a built-in **interactsh**-style listener. The oracle never re-runs a bug it already solved, and every finding lands in a hashed evidence ledger.

## 🕳️ It hunts for the next one

Solving known bugs is table stakes. Basilisk also carries a **source-level variant hunter** — the thing that turns one disclosed flaw into the zero-day sitting next to it.

- **`zday_scan`** — signature-driven scan over code or a whole tree for the dangerous-sink patterns that precede real CVEs. It ships knowing the shape of bugs like **CVE-2007-4559** (the Python `tarfile` path-traversal that stayed unpatched across thousands of repos for 15 years).
- **`code_scan_plan`** — turns a scan into an ordered exploitation plan: which sink, which reachability, which payload builder to point at it.
- **`find_variants`** — given one known-bad pattern, sweeps the codebase for every sibling of it. Real zero-day work is rarely a lone bug; it's a class, and this finds the class.

None of this is magic and none of it is a guarantee — but a variant hunter wired directly to 56 payload builders and a proof oracle is exactly the loop a human researcher runs by hand, and Basilisk runs it tirelessly.

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:08090b,50:e11d2b,100:08090b&height=3" width="100%" alt="">

## 🏆 It's measured, not marketed

Two deliberately-vulnerable targets. Black-box. Autonomous. Driven by a budget open model — **DeepSeek-V4-Flash**.

| Agent | Licence | Black-box | White-box *(source handed over)* |
|---|---|---:|---:|
| **🐍 Priest's Basilisk** *(2026-07-20 run)* | **MIT · free** | **87 / 113** | — |
| Priest's Basilisk *(earlier run)* | MIT · free | 73 / 113 | — |
| Cascade *(Windsurf / Escape)* | commercial | **36 / 113** | 49 / 113 |
| Claude Opus 4.8 *(bare model)* | metered API | **23 / 113** | 24 / 113 |

```text
  Basilisk  black-box  ███████████████████████████████████████████   87   ← blind
  Cascade   WHITE-box  ████████████████████████                      49   ← handed the source
  Cascade   black-box  ██████████████████                            36
  Opus 4.8  black-box  ███████████                                   23
```

Cascade's best number is its **white-box** run — it was given the source. Basilisk's 87 is **black-box**. Like for like it's **2.4× Cascade** and **3.8× a bare frontier model**, and it beats Cascade's white-box run by 38 challenges *while blind.*

**Reproduce it yourself** — this is the same code you just cloned:

```bash
docker run -d -p 3000:3000 -e NODE_ENV=unsafe --name juiceshop bkimminich/juice-shop
```

Point Basilisk at `http://localhost:3000`, arm Unleash, and let it work the board. It reads `/api/Challenges` for scoring, solves through the exploit builders + `run` only — **no web reader, no source.** Scorecard: [`benchmarks/juice-shop-scoreboard-2026-07-20.txt`](benchmarks/juice-shop-scoreboard-2026-07-20.txt).

**Second target — [Escape's Duck Store](https://duck-store.escape.tech/):** a deliberately-vulnerable REST API built to defeat the training-data memorisation that inflates Juice Shop numbers. API-first flaws — BOLA/BFLA, mass-assignment privilege escalation, SSRF, business-logic abuse. Black-box, no schema handed to it: **22 / 22**, and `juiceshop_report` / the engagement reporter write it up against **14 OWASP** categories with an **F1 0.95** against the ground-truth labels.

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:08090b,50:e11d2b,100:08090b&height=3" width="100%" alt="">

## 🔁 The loop

One loop, run whether it's breaking in or fixing code, and the second half is the point: **do the thing, then prove it worked.** No confidence scores, no "looks exploitable." A dumped row or it didn't happen.

```text
   plan ──▶ act ──▶ observe ──▶ PROVE ──▶ record ──▶ next
    ▲         │         │          │          │         │
    │      builder    parse     oracle +    hashed      │
    │      or shell   output    out-of-band ledger      │
    └───────────────── not done until verified ─────────┘
```

- **Plan** — reads the target, picks the class, orders the attack.
- **Act** — reaches for a *dedicated builder* first, raw shell only when nothing fits.
- **Observe** — parses real output, not vibes.
- **Prove** — the oracle confirms with a marker or an out-of-band callback; unproven ≠ solved.
- **Record** — every hit into the evidence ledger; the model never re-runs a solved bug.

**Steer it without stopping it:** while Basilisk is working, type a nudge and press **Enter** — it lands as a mid-run suggestion the loop folds in on its next step. The Stop control (click the send button, or Escape) is separate and always stops.

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:08090b,50:e11d2b,100:08090b&height=3" width="100%" alt="">

## 🧬 Inside the machine

~60k lines of Python, standard-library only for the engine (GTK for the desktop), across a deliberately boring, testable architecture:

| Module | What it is |
|---|---|
| `basilisk.py` | GTK4 / libadwaita desktop app — the chat, the Aero-glass UI, the live activity feed, streaming |
| `basilisk_core.py` | The turn engine — **149 tools**, tool-call parsing across every model dialect, the destructive-command floor |
| `basilisk_persona.py` | The engagement / general roles, the load-bearing safety guardrail, capability-aware prompting |
| `basilisk_scope.py` | The scope gate — fails **closed**, closes redirect and flag-injection leaks |
| `basilisk_ext/exploits.py` | **The 56 exploit builders** |
| `basilisk_ext/zdayfind.py` | Source variant hunter — `zday_scan`, `find_variants`, the signature catalogue |
| `basilisk_ext/oracle.py` · `verify.py` | Verified-exploitation oracle + out-of-band listener |
| `basilisk_ext/workspace.py` · `sandbox.py` | Repo-repair workspace, `bubblewrap` sandbox, `workspace_baseline` / `workspace_verify` / `workspace_export` |
| `basilisk_ext/memory.py` · `recall.py` | Persistent memory with `memory_forget`, backed by **SQLite** |
| `basilisk_ext/mcp.py` · `skills.py` · `pentest.py` | MCP client, skill loader, and the recon / pentest methodology |

**Tool-call dialects.** Models don't agree on how to emit a tool call, and several use their own trained format no matter what the prompt asks. Basilisk normalises *every* dialect it's seen to one canonical form — `<tool name="x">{json}</tool>`, DeepSeek's native special tokens, **DeepSeek-V4's DSML tags in every pipe rendering**, `<tool_call>`, `<invoke>`, `<function=…>`, fenced-JSON bodies, `<parameter>` child tags — before anything parses or renders. Parsing and display are driven from the *same* normalised text by construction, because when they disagree a call executes **and** leaks its raw markup into the chat.

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:08090b,50:e11d2b,100:08090b&height=3" width="100%" alt="">

## 🛡️ Two modes, one leash

Capability and safety are decoupled on purpose.

- **Leashed (default)** — research, code repair, host hardening, the full shell and desktop. The offensive suite is **refused at the loader**, not merely hidden. Ask it what it can do and it tells you *accurately and with confidence* — then reminds you nothing offensive is loaded until you arm it.
- **🐉 Unleash** — one tap arms the offensive suite and the mission loop, then **waits**. Send an objective and it runs off the leash with no per-command approval until that objective is *verifiably* done, or you stand it down.

Underneath both, the floor never moves: the **destructive-command gate** and the **fail-closed scope gate** fire regardless of mode. The catastrophic-command check isn't a naive string match — it sees through obfuscation like `rm${IFS}-rf${IFS}/` (**`$IFS`** substitution) and `sh -c '…'` wrappers, and there is **no "run anyway"** override on a catastrophic hit. It's also tuned against false positives: `rm -rf ~/loot` is *your* loot directory and runs fine — it's `/` and device nodes that are blocked. Point it at something you don't own and it keeps working *that* target until you pull it off, which is exactly why the installer asks you to read it. The safety guardrail is a byte-identical, test-pinned block; the engine won't ship if it drifts.

**Reading the web is tiered, not one closed list.** Trusted sources (NVD, OWASP, PortSwigger) are read freely; community sources like **exploit-db** and GitHub sit on the **approval side, outside the autonomous loop** — any public host is reachable after a one-tap approval, never auto-fetched mid-run. Cloud-metadata endpoints (`169.254.169.254`) and loopback are refused outright.

**Sandboxed by default where it matters.** Untrusted archives are handled with hard guards — **Zip slip** (`commonpath`-checked extraction), **Zip bombs**, **Symlink entries** — and repo-repair runs inside a **`bubblewrap`** sandbox with a verifiable baseline. Edits are surgical and safe: `workspace_replace` **refuses a match that isn't unique** rather than guessing which occurrence you meant. Learned skills are saved **autonomously, kept only if the test passes** — not gated behind a manual Apply click, gated behind proof that they work.

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:08090b,50:e11d2b,100:08090b&height=3" width="100%" alt="">

## 🖥️ The interface

A real desktop app, not a terminal wrapper — GTK4 / libadwaita with a dark Aero-glass theme.

| | |
|---|---|
| 🔴 **Live activity feed** | Watch every step — command, tool, payload, proof — as it happens. Collapsed by default; click to expand |
| 🗣️ **Voice in and out** | Whisper / SenseVoice speech-to-text, Piper text-to-speech, per-message read-aloud |
| 🖼️ **Vision** | Drop an image inline and have a vision model actually *look* at it |
| ↩️ **Steer without stopping** | Type a nudge mid-run and press **Enter** — folded in on the next step, no interruption |
| 📜 **Live terminal panel** | Every command and its raw output, toggled from the header |
| 🐉 **Unleash** | One tap arms the suite and waits for your objective |

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:08090b,50:e11d2b,100:08090b&height=3" width="100%" alt="">

## 🔬 Engineering

**Stdlib only** for the engine. No pytest, no network, no fixtures, no account — **4,190 assertions across 53 suites**, run in under a minute. Every fix ships with a regression that *fails* on the old code and *passes* on the new. Real GTK is spun up under Xvfb for the UI suites; the chat-bubble layout alone is pinned by 140 fitting checks. The safety guardrail is verified byte-identical on every build, the CSS is checked ASCII-only, and every packaged zip is re-tested from a clean extract before it's called done.

This is a one-person project. Every one of those assertions is there because something broke once and shouldn't get the chance to break again.

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:08090b,50:e11d2b,100:08090b&height=3" width="100%" alt="">

## 🜃 Why it's free, and who built it

There's a version of this with a pricing page, three tiers and a "contact sales" button. Everything on this page would still be true and the number at the bottom would be four figures a year.

I'd rather it went to the people who'd actually use it.

I build this **solo, around a full-time job** — nights, weekends, the hours most people spend switched off. It started as a way to learn offensive security by building the tool I wanted to exist, and it turned into something that outscores commercial agents on public benchmarks while blind. There's no team, no funding, no roadmap deck. There's one person who thinks defenders should have a weapon this good without a purchase order, and a test suite big enough to keep one pair of hands honest.

**MIT. All of it.** Not a trial, not a community edition with the good parts removed, not open-core with the safety gates behind a licence key. No account, no telemetry, no usage cap. The benchmark scores on this page were produced by the exact code you're about to clone.

If it earns its place in your kit, star the repo and tell someone who runs engagements. That's the whole price.

## 📜 License

**MIT.** Take it, fork it, use it on what you're allowed to break.

<div align="center">

<br/>

### Built by one person, around a day job. Verified by 4,190 assertions. Priced at nothing.

<sub>Clone it, read it, run the suite, then point it at something you own.</sub>

<br/><br/>

<a href="https://github.com/the-priest/PriestsBasilisk"><img src="https://img.shields.io/badge/★%20Star%20the%20repo-e11d2b?style=for-the-badge&labelColor=08090b" alt="Star the repo"></a>
<a href="#-install"><img src="https://img.shields.io/badge/Install%20in%20one%20line-7d121b?style=for-the-badge&labelColor=08090b" alt="Install"></a>

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:08090b,50:4a0a11,100:e11d2b&height=130&section=footer&text=prove%20everything&fontColor=ffffff&fontSize=28&fontAlignY=72&animation=twinkling" width="100%" alt="prove everything"/>

</div>
